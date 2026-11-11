"""OHCAM: online, hypothesis-guided Bayesian active learning of conditional action models."""

from collections import defaultdict

from frozendict import frozendict
import itertools
import time
from typing import Any, ClassVar, Iterator
import numpy as np
from ohcam.core.condition_hypothesis import (
    ConditionHypothesisFactory,
    ConditionHypothesisSet,
)
from ohcam.core.quantified_chain import QuantifiedChain
from ohcam.core.quantified_hypothesis import QuantifiedHypothesisSet
from ohcam.up_utils import FluentExpLike
from unified_planning.model import Problem, Object as UPObject
from unified_planning.plans import ActionInstance

from ohcam.core.action_model import Action, UPDomainConverter, build_action_vocabulary
from ohcam.core.pddl_repr import Condition, Conjunction, DNF, GroundedAtom, Outcome, Atom, Type
from ohcam.core.pddl_utils import get_groundings
from ohcam.core.utils import get_binary_entropy, softmax

from ohcam.core.config import OHCAMConfig


class OHCAMHypothesisSet:
    """The posterior over a domain's action model: one hypothesis set per precondition and effect literal."""

    def __init__(self,
            actions: dict[str, Action],
            predicates: dict[str, Atom],
            converter: UPDomainConverter,
            config: OHCAMConfig | None = None):
        if config is None:
            config = OHCAMConfig.instance()
        ConditionHypothesisFactory().configure(config)
        self.actions = actions
        self.predicates = predicates
        self.converter = converter
        self.config = config

        self.action_vocabs = {}
        self.action_preconditions: dict[str, ConditionHypothesisSet] = {}
        self.action_effects: dict[str, dict[Atom, ConditionHypothesisSet]] = {}
        self.unidentifiable_effects: dict[str, dict[Atom, QuantifiedHypothesisSet]] = {}
        self.exploration_qsets: dict[str, QuantifiedHypothesisSet] = {}

        self._pattern_scores: dict[Conjunction, float] = {}
        self._pattern_distribution: dict[Conjunction, np.ndarray] = {}
        self._pattern_by_index: dict[Conjunction, int] = {}

        self.dataset: list[tuple[dict[Atom, bool], tuple[str, ...], dict[Atom, bool], bool]] = []

        for name, action in actions.items():
            print(f"Initializing OHCAM hypothesis set for action {name}", end="")
            action_vocab = build_action_vocabulary(action.parameters, predicates)
            print(f" with {len(action_vocab)} literals")
            self.action_vocabs[name] = action_vocab
            if self.config.fix_init_precondition and isinstance(action.precondition.antecedent, DNF):
                fix_pre = action.precondition.antecedent.conjunctions[0]
                pre_action_vocab = [v for v in action_vocab if v not in fix_pre]
            else:
                fix_pre = Conjunction({})
                pre_action_vocab = action_vocab
            # Initialize hypothesis set for precondition
            precondition = ConditionHypothesisFactory().create_precondition(
                f"{name}_precondition", pre_action_vocab,
                fixed_conditions=fix_pre)
            self.action_preconditions[name] = precondition
            if not self.config.fix_init_precondition: # precondition is not fixed, add the initial precondition as a hypothesis
                precondition.add_condition(action.precondition, 1.0)

            precondition.try_expand()
            precondition.normalize()
            precondition.update_pattern_scores()

            effects: dict[Atom, ConditionHypothesisSet] = {}
            self.action_effects[name] = effects

            for literal in action_vocab:
                outcomes = [Outcome.ADD_EFFECT, Outcome.DEL_EFFECT]
                if literal in fix_pre: # if the literal is in the fixed precondition, we only consider the outcome that is not the opposite of the fixed precondition
                    if fix_pre[literal]:
                        outcomes.remove(Outcome.ADD_EFFECT) # literal already holds so can't add
                    else:
                        outcomes.remove(Outcome.DEL_EFFECT) # literal doesn't hold so can't delete
                effects[literal] = ConditionHypothesisFactory().create_effect(
                    f"{name}_effect_{literal}", literal, action_vocab, outcomes=outcomes)
                if literal in action.effects:
                    effects[literal].add_condition(action.effects[literal], 1.0)
                effects[literal].try_expand()
                effects[literal].normalize()
                effects[literal].update_pattern_scores()

            self.unidentifiable_effects[name] = {}
            if self.config.exploration_qsets:
                self.exploration_qsets[name] = QuantifiedHypothesisSet(Atom("???", tuple(), tuple()), action, self.predicates, is_exploration=True, max_qsets=self.config.exploration_qsets)

            self.update_pattern_scores(name)
            print(f", with {len(precondition)} precondition and {sum(len(effects[literal]) for literal in action_vocab)} effect hypotheses")


    def update(self, state: dict[GroundedAtom, bool], action: tuple[str, ...], next_state: dict[GroundedAtom, bool], applicable: bool):
        action_name = action[0]
        action_params = action[1:]
        if len(set(action_params)) != len(action_params):
            # the same object is grounded to multiple parameters
            # to maintain identifiability, we ignore this transition
            return
        action_schema = self.actions[action_name]
        param_mapping = {param: value for param, value in zip(action_schema.parameters.keys(), action_params)}
        pre_hyp_set = self.action_preconditions[action_name]
        pre_hyp_set.observe_transition(param_mapping, state, next_state, applicable, len(self.dataset))
        pre_hyp_set.update_beliefs()
        pre_hyp_set.try_expand()

        if applicable:
            # only update effects for applicable transitions
            for literal, effects in self.action_effects[action_name].items():
                effects.observe_transition(param_mapping, state, next_state, applicable, len(self.dataset))
                effects.update_beliefs()
                effects.try_expand()

            delta_state = {ground_literal: val for ground_literal, val in next_state.items() if state.get(ground_literal, False) != val}
            for ground_literal, val in state.items():
                if val and ground_literal not in next_state:
                    delta_state[ground_literal] = not val
            for ground_literal, val in delta_state.items():
                identity = ground_literal.bind_partial(param_mapping).lift()
                if not identity.is_identified():
                    # this literal is not identifiable; action parameters keep their schema types
                    identity = identity.bind({p:self.actions[action_name].parameters.get(p, t) for p, t in zip(identity.params, identity.types)})
                    if identity not in self.unidentifiable_effects[action_name]:
                        # initialize a new quantified hypothesis set for this unidentifiable literal
                        self.unidentifiable_effects[action_name][identity] = QuantifiedHypothesisSet(identity, self.actions[action_name], self.predicates)
                        for idx, (s, act, ns, app) in enumerate(self.dataset):
                            if app and act == action:
                                self.unidentifiable_effects[action_name][identity].observe_transition(param_mapping, s, ns, app, idx) # observe the backlog

            for quantified_set in self.unidentifiable_effects[action_name].values():
                quantified_set.observe_transition(param_mapping, state, next_state, applicable, len(self.dataset))
                quantified_set.update_beliefs()
                quantified_set.try_expand()
                quantified_set.score_disjunctions()

            if self.exploration_qsets:
                # manage hypotheses sets about unknown effects
                eqset = self.exploration_qsets[action_name]
                eqset.observe_transition(param_mapping, state, next_state, applicable, len(self.dataset))
                eqset.update_beliefs()
                eqset.try_expand()
                eqset.manage_exploration_sets()

        self.dataset.append((state, action, next_state, applicable))
        self.update_pattern_scores(action_name)


    def update_pattern_scores(self, action_name: str):
        # update pattern scores for action sampling heuristic
        pattern_scores = {}
        for pattern, score in self.action_preconditions[action_name]._pattern_scores.items():
            if not isinstance(pattern, Conjunction):
                raise ValueError(f"Invalid pattern: {pattern}")
            if pattern not in pattern_scores:
                pattern_scores[pattern] = 0.0
            pattern_scores[pattern] += score
        for literal, effects in self.action_effects[action_name].items():
            for pattern, score in effects._pattern_scores.items():
                if not isinstance(pattern, Conjunction):
                    raise ValueError(f"Invalid pattern: {pattern}")
                if pattern not in pattern_scores:
                    pattern_scores[pattern] = 0.0
                pattern_scores[pattern] += score
        distribution = np.array([score for pattern, score in pattern_scores.items()])
        if distribution.sum() == 0.0:
            distribution = np.ones_like(distribution) / len(distribution)
        else:
            distribution /= distribution.sum()
        self._pattern_scores[action_name] = pattern_scores
        self._pattern_distribution[action_name] = distribution
        self._pattern_by_index[action_name] = {idx:pattern for idx, pattern in enumerate(pattern_scores.keys())}

    def sample_pattern(self,
        action: str,
        precondition: Condition | None = None,
        relax_precondition_prob: float = 0.1,
        high_ent_prob: float = 0.5,
    ) -> dict[Atom, bool]:
        terms = {}

        # sample a precondition for more informed action selection
        if precondition is None:
            precondition = self.action_preconditions[action].sample(self.config.mc_sample_visited_preconditions)
        if isinstance(precondition.antecedent, DNF):
            # if disjunctive, choose a random branch to satisfy
            rand_branch = np.random.randint(len(precondition.antecedent))
            conj = precondition.antecedent[rand_branch]
            terms = {**conj}
        elif isinstance(precondition.antecedent, Conjunction):
            conj = precondition.antecedent
            terms = {**conj}
        if len(terms) > 1 and np.random.random() < relax_precondition_prob:
            # relax the precondition by removing a random term
            term_keys = list(terms.keys())
            terms.pop(term_keys[np.random.randint(len(term_keys))])

        if np.random.random() < high_ent_prob:
            # sample a high-entropy pattern for more more informative action selection
            idx = np.random.choice(len(self._pattern_distribution[action]), p=self._pattern_distribution[action])
            pattern = self._pattern_by_index[action][idx]
            terms = {**pattern, **terms}
        return terms

    def get_best_model_action(self, action: str, combine_preconditions: bool = False) -> Action:
        precondition = self.action_preconditions[action].get_best_conditions(combine_preconditions)[0]
        action_effects = self.action_effects[action]
        effects = {literal: cset.get_best_conditions(combine_preconditions)[0] for literal, cset in action_effects.items()}
        quantified_hypotheses = self.unidentifiable_effects[action]
        quantified_effects: dict[QuantifiedChain, Condition] = {}
        for atom, quantified_set in quantified_hypotheses.items():
            for chain, condition in quantified_set.get_best_conditions():
                quantified_effects[chain] = condition
        return Action(action, self.actions[action].parameters, precondition, effects, quantified_effects)

    def sample_model_action(self, action: str) -> Action:
        precondition = self.action_preconditions[action].sample(self.config.mc_sample_visited_preconditions)
        effects = {literal: self.action_effects[action][literal].sample() for literal in self.action_vocabs[action]}
        return Action(action, self.actions[action].parameters, precondition, effects)

    def get_bald_utility(self, state: dict[Atom, bool], ground_action: tuple[str, ...]) -> float:
        action_name = ground_action[0]
        action_params = ground_action[1:]
        param_mapping = {param: value for param, value in zip(self.actions[action_name].parameters.keys(), action_params)}

        prob_applicable = self.action_preconditions[action_name].get_consequent_probability(param_mapping, state, False)
        precondition_entropy = get_binary_entropy(prob_applicable)
        if prob_applicable == 0.0:
            return 0.0

        effect_entropy_sum = 0.0
        for effect_literal, hypothesis_set in self.action_effects[action_name].items():
            current_literal = state.get(effect_literal.ground(param_mapping), False)
            effect_entropy = hypothesis_set.get_disagreement_entropy(param_mapping, state, current_literal)
            effect_entropy_sum += effect_entropy

        for quantified_set in self.unidentifiable_effects[action_name].values():
            quantified_entropy = quantified_set.get_disagreement_entropy(param_mapping, state)
            effect_entropy_sum += quantified_entropy * OHCAMConfig.instance().unidentifiable_effect_weight

        # get entropy of unknown effects
        eqs = self.exploration_qsets.get(action_name)
        if eqs is not None:
            exploration_entropy = eqs.get_disagreement_entropy(param_mapping, state) / max(len(eqs.quantified_hypotheses), 1)
            effect_entropy_sum += exploration_entropy

        return self.config.precondition_weight * precondition_entropy + prob_applicable * effect_entropy_sum

    def transition_log_likelihood(self,
            state: dict[Atom, bool],
            ground_action: tuple[str, ...],
            next_state: dict[Atom, bool]) -> float:
        """Compute the likelihood of a successful transition from state to next_state given an action.

        Args:
            state: dict[Atom, bool] The current state.
            ground_action: tuple[str, ...] The grounded action.
            next_state: dict[Atom, bool] The next state.
        Returns:
            float The log likelihood of the transition.
        """
        action_name = ground_action[0]
        action_params = ground_action[1:]
        param_mapping = {param: value for param, value in zip(self.actions[action_name].parameters.keys(), action_params)}

        prob_applicable = self.action_preconditions[action_name].get_consequent_probability(param_mapping, state, False)
        if prob_applicable == 0.0:
            return -np.inf

        log_likelihood = np.log(prob_applicable)
        for effect_literal, hypothesis_set in self.action_effects[action_name].items():
            current_literal = state.get(effect_literal.ground(param_mapping), False)
            next_literal = next_state.get(effect_literal.ground(param_mapping), False)
            prob_next_true = hypothesis_set.get_consequent_probability(param_mapping, state, current_literal)
            literal_likelihood = np.clip(prob_next_true if next_literal else (1 - prob_next_true), 0, 1)
            if literal_likelihood == 0.0:
                return -np.inf
            log_likelihood += np.log(literal_likelihood)
        return log_likelihood


    def get_best_up_model(self, combine_preconditions: bool = False) -> Problem:
        actions = [self.get_best_model_action(name, combine_preconditions) for name in self.actions.keys()]
        new_domain = self.converter.new_up_domain(actions)
        return new_domain

    _EXPANSION_SUM_KEYS: ClassVar[tuple[str, ...]] = (
        "num_hypotheses", "num_expansion_events", "num_nodes_expanded",
        "num_children_generated", "num_literals", "num_singletons",
        "num_surviving_singletons", "num_surviving_literals", "num_literals_pruned_events",
    )
    _EXPANSION_DEPTH_KEYS: ClassVar[tuple[str, ...]] = (
        "hypotheses_by_depth", "expansion_events_by_depth", "children_generated_by_depth",
    )

    @classmethod
    def _aggregate_expansion_stats(cls, stats_list: list[dict[str, Any]]) -> dict[str, Any]:
        """Combine per-set expansion statistics: sum scalar counters, merge depth histograms."""
        agg: dict[str, Any] = {"num_sets": len(stats_list), "max_depth_reached": 0}
        for key in cls._EXPANSION_SUM_KEYS:
            agg[key] = 0
        for key in cls._EXPANSION_DEPTH_KEYS:
            agg[key] = defaultdict(int)
        for stats in stats_list:
            for key in cls._EXPANSION_SUM_KEYS:
                agg[key] += stats[key]
            agg["max_depth_reached"] = max(agg["max_depth_reached"], stats["max_depth_reached"])
            for key in cls._EXPANSION_DEPTH_KEYS:
                for depth, count in stats[key].items():
                    agg[key][depth] += count
        for key in cls._EXPANSION_DEPTH_KEYS:
            agg[key] = dict(sorted(agg[key].items()))
        return agg

    #: Category each hypothesis set is filed under for the ``by_category`` breakdown.
    _EXPANSION_CATEGORIES: ClassVar[tuple[str, ...]] = ("precondition", "effect", "quantified")

    def get_statistics(self) -> dict[str, Any]:
        """Aggregate hypothesis-expansion statistics across the whole learned model.

        Returns a dict with three views over the branch-and-bound expansion:
        - ``per_effect[action][effect_key]``: raw stats for each individual hypothesis set
          (the precondition, each action-parameter effect literal, and each quantified /
          exploration effect), from :meth:`ConditionHypothesisSet.get_expansion_statistics`.
        - ``per_action[action]``: those stats aggregated over each action's hypothesis sets.
        - ``overall``: aggregated across every hypothesis set in the model.

        The precondition set is counted in the ``per_action`` and ``overall`` totals. To
        read its contribution separately, both of those aggregates carry a ``by_category``
        sub-dict splitting the totals into ``precondition``, ``effect`` (action-parameter
        effect literals), and ``quantified`` (UQV + exploration effects).

        Each stats dict reports how many hypotheses exist and how many expansion events
        occurred, both bucketed by antecedent depth (e.g. ``expansion_events_by_depth``
        contrasts refinements of depth-1 vs. depth-3 conditions), how many singleton
        literals survived the pruning bound, and how many refinements were pruned.

        ``max_uqv_sets`` is the most UQV sets (quantified chains) any identified unidentifiable effect has, and
        ``max_uqv_sets_effect`` the ``action:identity`` that has them; ``uqv_sets`` lists every effect's count.
        """
        per_effect: dict[str, dict[str, dict[str, Any]]] = {}
        per_action: dict[str, dict[str, Any]] = {}
        all_stats: list[dict[str, Any]] = []
        global_by_category: dict[str, list[dict[str, Any]]] = {c: [] for c in self._EXPANSION_CATEGORIES}

        for action_name in self.actions:
            effect_stats: dict[str, dict[str, Any]] = {}
            by_category: dict[str, list[dict[str, Any]]] = {c: [] for c in self._EXPANSION_CATEGORIES}

            pre_stats = self.action_preconditions[action_name].get_expansion_statistics()
            effect_stats["precondition"] = pre_stats
            by_category["precondition"].append(pre_stats)
            for literal, cset in self.action_effects[action_name].items():
                s = cset.get_expansion_statistics()
                effect_stats[f"effect:{literal}"] = s
                by_category["effect"].append(s)
            for identity, qset in self.unidentifiable_effects[action_name].items():
                for chain, cset in qset.quantified_hypotheses.items():
                    s = cset.get_expansion_statistics()
                    effect_stats[f"uqv:{identity}:{chain.target}"] = s
                    by_category["quantified"].append(s)
            eqset = self.exploration_qsets.get(action_name)
            if eqset is not None:
                for chain, cset in eqset.quantified_hypotheses.items():
                    s = cset.get_expansion_statistics()
                    effect_stats[f"explore:{chain.target}"] = s
                    by_category["quantified"].append(s)

            per_effect[action_name] = effect_stats
            action_agg = self._aggregate_expansion_stats(list(effect_stats.values()))
            action_agg["by_category"] = {c: self._aggregate_expansion_stats(by_category[c]) for c in self._EXPANSION_CATEGORIES}
            per_action[action_name] = action_agg
            all_stats.extend(effect_stats.values())
            for c in self._EXPANSION_CATEGORIES:
                global_by_category[c].extend(by_category[c])

        overall = self._aggregate_expansion_stats(all_stats)
        overall["by_category"] = {c: self._aggregate_expansion_stats(global_by_category[c]) for c in self._EXPANSION_CATEGORIES}

        # UQV sets (quantified chains) of each identified unidentifiable effect; exploration sets aren't effects
        uqv_sets = {f"{action_name}:{identity}": len(qset.quantified_hypotheses)
                    for action_name in self.actions
                    for identity, qset in self.unidentifiable_effects[action_name].items()}
        max_uqv_effect = max(uqv_sets, key=uqv_sets.get, default=None)
        return {
            "max_uqv_sets": uqv_sets.get(max_uqv_effect, 0),
            "max_uqv_sets_effect": max_uqv_effect,
            "num_uqv_effects": len(uqv_sets),
            "uqv_sets": uqv_sets,
            "overall": overall,
            "per_action": per_action,
            "per_effect": per_effect,
        }




def unify_pattern(pattern: Conjunction, state: dict[GroundedAtom, bool], objects: dict[str, Type], action_schema: Action,
                  preferred_objects: set[str] | None = None) -> Iterator[dict[str, str]]:
    """Find all valid groundings of pattern against state.
    pattern: Conjunction of (Literal, bool) — literal and required truth value
    state: dict[Atom, bool]
    preferred_objects: if given, bindings that use more of these objects are found first
    Yields: dict[str, str] — variable-to-object bindings
    """
    # Index state for fast lookup
    by_predicate = defaultdict(list[tuple[str, ...]])
    for atom, val in state.items():
        if val:
            by_predicate[atom.name].append(atom.objects)

    # Find candidate atoms for each pattern literal
    candidate_lists: list[tuple[tuple[str, ...], list[tuple[str, ...]]]] = []
    for literal, value in pattern.items():
        literal: Atom
        if isinstance(literal, tuple) and literal[0] == 'or':
            dict_candidates = []
            args = []
            for child, cvalue in literal[1:]:
                child: Atom
                child_candidates = by_predicate.get(child.name, [])
                if not cvalue:
                    child_candidates = list(set(get_groundings([action_schema.parameters[arg] for arg in child.params], objects)) - set(child_candidates))
                for candidate in child_candidates:
                    dict_candidates.append({param: obj for param, obj in zip(child.params, candidate)})
                for arg in child.params:
                    if arg not in args:
                        args.append(arg)
            candidates = [tuple(dc.get(arg, None) for arg in args) for dc in dict_candidates]
        else:
            args = literal.params
            candidates = by_predicate.get(literal.name, [])
            if not value:
                all_bindings = set(get_groundings([action_schema.parameters[arg] for arg in literal.params], objects))
                candidates = list(all_bindings - set(candidates))
        # filter out candidates that do not match the parameter types
        candidates = [c for c in candidates if
                all([action_schema.parameters[arg].is_super_type(objects[c[i]]) for i, arg in enumerate(args)])]
        if not candidates:
            return None # No way to satisfy this literal
        np.random.shuffle(candidates)
        if preferred_objects:
            # stable, so candidates that reuse as many preferred objects stay in random order
            candidates.sort(key=lambda c: -sum(obj in preferred_objects for obj in c))
        candidate_lists.append((args, candidates))
    # satisfy (not) predicates first
    # least constrained variables first heuristic
    candidate_lists.sort(key=lambda x: len(x[1]))
    # Backtracking search
    def search(idx, bindings):
        if idx == len(candidate_lists):
            yield bindings
            return
        var_args, candidates = candidate_lists[idx]
        for atom_args in candidates:
            new_bindings = dict(bindings)
            ok = True
            for var, obj in zip(var_args, atom_args):
                if obj is None:
                    continue
                if var in new_bindings:
                    if new_bindings[var] != obj:
                        ok = False # different object grounded to the same variable
                        break
                obj_already_bound = next((v for v, o in new_bindings.items() if o == obj), None)
                if obj_already_bound and obj_already_bound != var:
                    ok = False # object already grounded to a different variable
                    break
                new_bindings[var] = obj
            if ok:
                yield from search(idx + 1, new_bindings)

    yield from search(0, {})

def sample_action(
    ohcam_model: OHCAMHypothesisSet,
    state: dict[Atom, bool],
    objects: dict[str, Type],
    actions: dict[str, Action] | None = None,
    relax_precondition_prob: float = 0.1,
    high_ent_prob: float = 0.5,
    max_tries: int = 10,
    preferred_objects: set[str] | None = None,
    object_reuse_prob: float = 0.0,
) -> tuple[str, ...]:
    """Sample a grounded action whose sampled precondition holds in state, or else a random grounding.

    With probability object_reuse_prob, the grounding prefers preferred_objects (e.g. those a rollout already acted
    on), so sampled sequences tend to chain actions on the same objects.
    """
    if not preferred_objects or object_reuse_prob <= 0.0 or np.random.random() >= object_reuse_prob:
        preferred_objects = None
    for i in range(max_tries):
        if actions is None:
            action_name = np.random.choice(list(ohcam_model.actions.keys()))
            action_schema = ohcam_model.actions[action_name] # initial model schema
            precondition = None
        else:
            action_name = np.random.choice(list(actions.keys()))
            action_schema = actions[action_name] # fixed model schema
            precondition = action_schema.precondition

        pattern = ohcam_model.sample_pattern(action_name, precondition,
            relax_precondition_prob, high_ent_prob)  # list of (literal, value)

        partial = next(unify_pattern(pattern, state, objects, action_schema, preferred_objects), None)
        if partial is not None:
            break
        else:
            partial = {}
    cg = complete_grounding(action_schema, partial, objects, preferred_objects)
    return cg

def complete_grounding(action: Action, partial: dict[str, str], objects: dict[str, Type],
                       preferred_objects: set[str] | None = None) -> tuple[str, ...]:
    grounding = dict(partial)
    for arg, type_ in action.parameters.items():
        if arg not in grounding:
            # avoid grounding the same object to multiple parameters -- identifiability assumption
            compatible = [obj for obj, t in objects.items() if type_.is_super_type(t) and obj not in grounding.values()]
            if not compatible:
                return None
            if preferred_objects:
                compatible = [obj for obj in compatible if obj in preferred_objects] or compatible
            grounding[arg] = np.random.choice(compatible)
    args = [grounding[arg] for arg in action.parameters.keys()]
    return (action.name, *args)

def select_action_monte_carlo(
    ohcam_model: OHCAMHypothesisSet,
    state: dict[Atom, bool],
    objects: dict[str, Type],
    cur_plan: list[tuple[str, ...]] | None = None,
    rollouts: int = 1000,
    horizon: int = 4,
    discount_factor: float = 1.0,
    max_planning_time: float = 5.0,
    baseline_entropy: float = 0.0,
    k_per_step: int = 6,
    max_action_sample_tries: int = 4,
    step_greedy_temp: float = 1.0,
    relax_precondition_prob: float = 0.0,
    cur_plan_frac: float = 0.3,
    high_ent_prob: float = 0.0,
    object_reuse_prob: float = 0.0,
) -> tuple[list[tuple[str, ...]], np.ndarray]:
    """Select an action sequence by imagining rollouts under models sampled from the posterior.

    Args:
        ohcam_model: The OHCAM hypothesis set for BALD computation.
        state: dict[Atom, bool] The current state.
        objects: dict[str, Type] The objects in the state.
        cur_plan: The remainder of the previous plan, used to seed a fraction of the rollouts.
        rollouts: int The number of rollouts to imagine.
        horizon: int The number of steps to plan.
        discount_factor: float The discount factor for the cumulative log likelihood.
        max_planning_time: float Stop imagining rollouts after this many seconds.
        baseline_entropy: float The baseline entropy for noisy utility computation.
        k_per_step: int The number of actions to sample at each step.
        max_action_sample_tries: int Attempts to find a grounding satisfying a sampled pattern.
        step_greedy_temp: float The temperature for the softmax over step utilities.
        relax_precondition_prob: float The probability of relaxing a precondition by 1 term.
        cur_plan_frac: float The fraction of rollouts eligible to start from cur_plan.
        high_ent_prob: float Probability to sample actions that satisfy a high-entropy-belief literal.
        object_reuse_prob: float Probability that a sampled action prefers objects the rollout already acted on.
    Returns:
        The best rollout's action sequence and its per-step discounted utilities.
    """
    if cur_plan is None:
        cur_plan = []
    cur_plan = cur_plan[:horizon]

    bald_cache = {}
    transition_cache = {}

    all_rollout_actions = [[] for _ in range(rollouts)]
    all_rollout_discounted_utilities = np.zeros((rollouts, horizon))
    all_rollout_cum_utilities = np.zeros(rollouts)
    all_rollout_cum_noisy_utilities = np.zeros(rollouts)
    all_rollout_is_prefix = np.zeros(rollouts, dtype=bool)
    start_time = time.time()
    for r in range(rollouts):
        if r % 2 == 0 and r <= rollouts * cur_plan_frac:
            plan_prefix = cur_plan
        else:
            plan_prefix = []
        action_models = {action_name: ohcam_model.sample_model_action(action_name) for action_name in ohcam_model.actions.keys()}

        curr_state = state
        rollout_actions = []
        rollout_objects = set()
        rollout_utilities = np.zeros(horizon)
        cumulative_log_likelihoods = np.zeros(horizon)

        for step, cur_action in itertools.zip_longest(range(horizon), plan_prefix):
            if cur_action is None:
                step_utilities = np.zeros(k_per_step)
                ground_actions = [None] * k_per_step
                for k in range(k_per_step):
                    ground_action = sample_action(ohcam_model, curr_state, objects, action_models, relax_precondition_prob, high_ent_prob, max_tries=max_action_sample_tries,
                                                  preferred_objects=rollout_objects, object_reuse_prob=object_reuse_prob)
                    curr_state_frozen = frozendict(curr_state)
                    bald_utility = bald_cache.get((curr_state_frozen, ground_action), None)
                    if bald_utility is None:
                        bald_utility = ohcam_model.get_bald_utility(curr_state, ground_action)
                        bald_cache[(curr_state_frozen, ground_action)] = bald_utility
                    step_utilities[k] = bald_utility
                    ground_actions[k] = ground_action
                softmax_utilities = softmax(step_utilities, temperature=step_greedy_temp)
                best_index = np.random.choice(k_per_step, p=softmax_utilities)
                best_ground_action = ground_actions[best_index]
                best_step_utility = step_utilities[best_index]
            else:
                best_ground_action = cur_action
                curr_state_frozen = frozendict(curr_state)
                best_step_utility = bald_cache.get((curr_state_frozen, best_ground_action), None)
                if best_step_utility is None:
                    best_step_utility = ohcam_model.get_bald_utility(curr_state, best_ground_action)
                    bald_cache[(curr_state_frozen, best_ground_action)] = best_step_utility

            action_model = action_models[best_ground_action[0]]
            applicable, next_state = action_model.apply(best_ground_action[1:], curr_state)

            # on failures, just assume the state does not change (common PDDL modeling assumption)
            # if assumption violated, this may overestimate the utility past the failure point,
            #    since we continue planning from the wrong state
            # but all future actions will be discounted by the applicable probability, so hopefully it balances out
            if not applicable:
                next_state = curr_state
            if step < horizon - 1:
                # states are plain dicts, so freeze them to key the cache (as for bald_cache above)
                transition_key = (frozendict(curr_state), best_ground_action, frozendict(next_state))
                log_likelihood = transition_cache.get(transition_key, None)
                if log_likelihood is None:
                    log_likelihood = ohcam_model.transition_log_likelihood(curr_state, best_ground_action, next_state)
                    transition_cache[transition_key] = log_likelihood
                cumulative_log_likelihoods[step+1] = cumulative_log_likelihoods[step] + log_likelihood + np.log(discount_factor)

            curr_state = next_state

            rollout_actions.append(best_ground_action)
            rollout_objects.update(best_ground_action[1:])
            rollout_utilities[step] = best_step_utility

        discounted_utilities = rollout_utilities * np.exp(cumulative_log_likelihoods)
        rollout_utility = np.sum(discounted_utilities)
        noisy_utility = rollout_utility + np.random.randn() * baseline_entropy
        all_rollout_actions[r] = rollout_actions
        all_rollout_is_prefix[r] = len(plan_prefix) > 0
        all_rollout_discounted_utilities[r] = discounted_utilities
        all_rollout_cum_utilities[r] = rollout_utility
        all_rollout_cum_noisy_utilities[r] = noisy_utility


        if time.time() - start_time > max_planning_time:
            break

    n_rollouts = r + 1
    best_rollout_index = int(np.argmax(all_rollout_cum_noisy_utilities[:n_rollouts]))
    is_prefix = all_rollout_is_prefix[:n_rollouts]
    if is_prefix.any() and not is_prefix[best_rollout_index]:
        # Keep following the current plan unless a new plan is strictly better than the plan's best continuation.
        # Otherwise ties (e.g. a plan that prepends a worthless action to the same test) are broken at random, and the
        # agent keeps re-planning instead of acting.
        prefix_indices = np.flatnonzero(is_prefix)
        best_prefix_index = int(prefix_indices[np.argmax(all_rollout_cum_utilities[prefix_indices])])
        if all_rollout_cum_utilities[best_prefix_index] >= all_rollout_cum_utilities[best_rollout_index]:
            best_rollout_index = best_prefix_index
    best_rollout_utility = all_rollout_cum_utilities[best_rollout_index]
    best_rollout_sequence = all_rollout_actions[best_rollout_index]
    best_rollout_discounted_utilities = all_rollout_discounted_utilities[best_rollout_index]
    print(f"Imagined {r+1} rollouts in {time.time() - start_time:.2f}s. Best [{best_rollout_index}] utility: {best_rollout_utility:.2f}")
    return best_rollout_sequence, best_rollout_discounted_utilities # return the best rollout sequence and its utility


def initialize_ohcam(init_domain: Problem, config: OHCAMConfig | None = None) -> OHCAMHypothesisSet:
    converter = UPDomainConverter(init_domain)
    ohcam = OHCAMHypothesisSet(converter.actions, converter.predicates, converter, config=config)
    return ohcam

def step_ohcam(
        ohcam: OHCAMHypothesisSet,
        up_state: dict[FluentExpLike, bool], up_objects: list[UPObject], cur_plan: list[ActionInstance] | None = None,
) -> list[ActionInstance]:
    """Plan the next actions to execute from the current state, dropping trailing actions with no utility."""
    state = ohcam.converter.up_state_to_atoms(up_state)
    objects = ohcam.converter.up_objects_to_objects(up_objects)
    config = ohcam.config
    if cur_plan is not None:
        cur_plan = [(act.action.name, *[p.object().name for p in act.actual_parameters]) for act in cur_plan]
    plan, utilities = select_action_monte_carlo(
        ohcam,
        state, objects,
        cur_plan=cur_plan,
        rollouts=config.mc_rollouts,
        horizon=config.mc_horizon,
        k_per_step=config.mc_k_per_step,
        max_planning_time=config.max_planning_time,
        max_action_sample_tries=config.mc_max_action_sample_tries,
        step_greedy_temp=config.mc_step_greedy_temp,
        relax_precondition_prob=config.exploration_relax_precondition_prob,
        high_ent_prob=config.exploration_high_ent_prob,
        baseline_entropy=config.exploration_baseline_entropy,
        object_reuse_prob=config.mc_object_reuse_prob,
    )
    last_value_idx = np.where(utilities > 0)[0]
    last_value_idx = last_value_idx[-1] if len(last_value_idx) > 0 else -1
    plan = plan[:max(last_value_idx + 1, 1)] # drop the trailing worthless actions, keeping at least one

    up_actions = [ohcam.converter.domain.action(act[0]) for act in plan]
    up_argss = [[next(o for o in up_objects if o.name == obj) for obj in act[1:]] for act in plan]
    return [ActionInstance(up_action, up_args) for up_action, up_args in zip(up_actions, up_argss)]

def learn_ohcam_step(
    ohcam: OHCAMHypothesisSet,
    up_state: dict[FluentExpLike, bool], up_objects: list[UPObject],
    up_action: ActionInstance, up_next_state: dict[FluentExpLike, bool], execution: str,
) -> None:
    state, action, next_state, applicable = ohcam.converter.up_transition_to_transition(up_state, up_action, up_next_state, execution)
    ohcam.update(state, action, next_state, applicable)
