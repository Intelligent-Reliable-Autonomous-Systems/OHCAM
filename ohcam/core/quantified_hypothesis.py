from collections import Counter
import itertools
from typing import Iterator

from frozendict import frozendict
import numpy as np
from scipy.stats import binom

from ohcam.core.action_model import Action, Atom, Condition, Conjunction, GroundedAtom, Outcome, build_action_vocabulary
from ohcam.core.complexity import NULL_COMPLEXITY, get_disjunction_log_complexity, get_uqv_log_complexity
from ohcam.core.condition_hypothesis import (
    ConditionHypothesisFactory,
    ConditionHypothesisSet,
)
from ohcam.core.quantified_chain import QuantifiedChain, get_object_graph, iter_param_chains


class QuantifiedHypothesisSet:

    def __init__(self, identity: Atom, action: Action, predicates: dict[str, Atom], is_exploration: bool = False,
            max_uqvs: int | None = None, prior_decay: float | None = None,
            max_qsets: int = 10):
        self.identity = identity

        self.action = action
        self.predicates = predicates


        self.max_uqvs = ConditionHypothesisFactory().max_uqvs if max_uqvs is None else max_uqvs
        self.uqv_chain_only = ConditionHypothesisFactory().uqv_chain_only
        self.uqv_chain_allow_empty = ConditionHypothesisFactory().uqv_chain_allow_empty
        self._prior_decay = ConditionHypothesisFactory().prior_decay if prior_decay is None else prior_decay

        self.dataset: list[tuple[dict[GroundedAtom, bool], dict[str, str], dict[GroundedAtom, bool], bool, int]] = []
        self.grounding_instance_ids: dict[tuple[int, GroundedAtom], int] = {}
        """Map each (observation_id, grounded_atom) to a unique instance id."""
        self.grounding_instance_deltas: np.ndarray = np.full(1024, False, dtype=bool)
        """Record whether the grounded atom was a delta in the observation."""

        self.quantified_hypotheses: dict[QuantifiedChain, ConditionHypothesisSet] = {}
        self.chain_counts: Counter[QuantifiedChain] = Counter()

        self._need_explanation: dict[GroundedAtom, tuple[dict[str, str], dict[GroundedAtom, bool]]] = {}

        self._max_disjunctions: int = 16
        self._disjunction_samples_per_step: int = 4
        self._disjunctions: list[frozenset[tuple[QuantifiedChain, ConditionHypothesisSet, int]]] = [frozenset()]
        self._disjunction_scores: np.ndarray = np.array([NULL_COMPLEXITY])
        self._disjunction_fn_indices: list[list[int]] = [[]]
        self._disjunction_pruning_threshold: float = 1e-6

        self.max_data_groundings: int = 128
        self.max_bald_groundings: int = 16
        """Maximum number of groundings to consider for each quantified hypothesis in BALD computation."""
        self.is_exploration = is_exploration
        self.max_qsets = max_qsets
        self._instance_id_counter = itertools.count()
        if self.is_exploration:
            self._qset_iter = self.enumerate_variable_sets()
            for _ in range(self.max_qsets):
                try:
                    chain = next(self._qset_iter)
                except StopIteration:
                    break
                self.quantified_hypotheses[chain] = self._initialize_hypothesis_set(chain)


    def observe_transition(self, param_mapping: dict[str, str], state: dict[GroundedAtom, bool], next_state: dict[GroundedAtom, bool], applicable: bool, dataset_size: int):
        # determine deltas to be explained
        delta_state = {ground_literal: val for ground_literal, val in next_state.items() if state.get(ground_literal, False) != val}
        for ground_literal, val in state.items():
            if val and ground_literal not in next_state:
                delta_state[ground_literal] = not val
        self.dataset.append((state, param_mapping, next_state, applicable, dataset_size, delta_state))

        if not self.is_exploration:

            # update chain counts
            state_no_false = {atom: val for atom, val in state.items() if val} # assume quantified variables are chained by true literals
            partial_ground_identity = self.identity.ground(param_mapping)
            object_graph = get_object_graph(state_no_false)
            chains = set(iter_param_chains(param_mapping, object_graph, partial_ground_identity, action_params=self.action.parameters, max_vars=self.max_uqvs, chain_only=self.uqv_chain_only, allow_empty_chain=self.uqv_chain_allow_empty))
            self.chain_counts.update(chains)

            for gatom in delta_state:
                gpatom = gatom.bind_partial(param_mapping)
                if gpatom.lift().submatches(self.identity):
                    self._need_explanation[gpatom] = (param_mapping, state)

        # for each chain, evaluate all possible groundings in this state
        for chain, hypothesis in self.quantified_hypotheses.items():
            self._observe_hypotheses(chain, hypothesis, param_mapping, state, next_state, applicable, dataset_size, delta_state)

    def _observe_hypotheses(self, chain: QuantifiedChain, hypothesis: ConditionHypothesisSet, param_mapping: dict[str, str], state: dict[GroundedAtom, bool], next_state: dict[GroundedAtom, bool], applicable: bool, dataset_size: int, delta_state: dict[GroundedAtom, bool]):
        all_groundings = chain.ground_all(param_mapping, state, max=self.max_data_groundings)
        for quantified_mapping in all_groundings:
            if not self.is_exploration:
                gtarget = chain.ground_target(quantified_mapping).bind(self.identity.params)
                if gtarget in self._need_explanation:
                    # at least one quantified hypothesis is capable of predicting the delta
                    # that is not to say it will predict it correctly
                    self._need_explanation.pop(gtarget)
                instance_id = self.grounding_instance_ids.get((dataset_size, gtarget), len(self.grounding_instance_ids))
                self.grounding_instance_ids[(dataset_size, gtarget)] = instance_id
                if instance_id >= len(self.grounding_instance_deltas):
                    self.grounding_instance_deltas = np.concatenate((self.grounding_instance_deltas, np.full(len(self.grounding_instance_deltas), False, dtype=bool))) # expand the capacity
                self.grounding_instance_deltas[instance_id] = gtarget in delta_state
            else:
                instance_id = next(self._instance_id_counter)
            hypothesis.observe_transition(quantified_mapping, state, next_state, applicable, instance_id)

    def _initialize_hypothesis_set(self, chain: QuantifiedChain) -> ConditionHypothesisSet:
        all_params = {**self.action.parameters, **chain.uqvs}
        action_vocab = build_action_vocabulary(all_params, self.predicates)
        action_vocab = [v for v in action_vocab if v not in chain.literals]
        outcomes=[Outcome.ADD_EFFECT, Outcome.DEL_EFFECT]
        if self.is_exploration:
            outcomes = [Outcome.ADD_EFFECT]
            required_variables = list(chain.uqvs.keys())
            init_max_depth = ConditionHypothesisFactory()._instance._defaults.init_max_depth + 2
        else:
            required_variables = []
            init_max_depth = ConditionHypothesisFactory()._instance._defaults.init_max_depth
        hypothesis = ConditionHypothesisFactory().create_effect(
            f"{self.action.name}_effect_UQV:{chain.target}", chain.target,
            action_vocab, outcomes=outcomes, fixed_conditions=Conjunction(chain.literals), required_variables=required_variables, init_max_depth=init_max_depth)

        # evaluate on all existing data
        for state, param_mapping, next_state, applicable, dataset_size, delta_state in self.dataset:
            self._observe_hypotheses(chain, hypothesis, param_mapping, state, next_state, applicable, dataset_size, delta_state)
        hypothesis.update_beliefs()

        return hypothesis

    def update_beliefs(self):
        for hypothesis in self.quantified_hypotheses.values():
            hypothesis.update_beliefs()

    def try_expand(self):

        # add chains if necessary
        if self._need_explanation:
            chains = [c for c, _ in
                    sorted(self.chain_counts.items(), key=lambda x: 100 * x[0].cost - x[1])
                    if c not in self.quantified_hypotheses]
            while self._need_explanation:
                gatom, (param_mapping, state) = self._need_explanation.popitem()
                for chain in chains:
                    gatom_groundings = chain.ground_all_to_target(gatom, param_mapping, state)
                    if len(gatom_groundings) > 0:
                        self.quantified_hypotheses[chain] = self._initialize_hypothesis_set(chain)
                        self._need_explanation = {
                            gatom:context for gatom, context in self._need_explanation.items() if
                            len(chain.ground_all_to_target(gatom, context[0], context[1])) == 0
                        }
                        break
                else:
                    print(f"Failed to ground {gatom} with any of the chains")

        for chain, hypothesis in self.quantified_hypotheses.items():
            hypothesis.try_expand()

    def get_disagreement_entropy(self, param_mapping: dict[str, str], state: dict[GroundedAtom, bool]) -> float:
        total_entropy = 0.0
        for chain, hypothesis in self.quantified_hypotheses.items():
            all_groundings = chain.ground_all(param_mapping, state, max=self.max_bald_groundings)
            chain_cum_entropy = 0.0
            for quantified_mapping in all_groundings:
                if not self.is_exploration:
                    gtarget = chain.ground_target(quantified_mapping).bind(self.identity.params)
                    current_literal = state.get(gtarget, False)
                else:
                    current_literal = False
                entropy = hypothesis.get_disagreement_entropy(quantified_mapping, state, current_literal)
                chain_cum_entropy += entropy
            if len(all_groundings) > 0:
                total_entropy += chain_cum_entropy / len(all_groundings)
        return total_entropy

    def score_disjunctions(self) -> None:
        """Score DNF hypotheses to allow multiple UQV chains to explain identity effects."""
        epsilon = max(ConditionHypothesisFactory().noise_level, 1e-10)
        beta = np.log((1 - epsilon) /epsilon)
        TP_IDX = ConditionHypothesisSet.TP_IDX
        FP_IDX = ConditionHypothesisSet.FP_IDX

        # sample disjunctions
        for i in range(self._disjunction_samples_per_step):
            disjunction = frozenset()
            predicted_deltas = np.zeros(0, dtype=int)
            num_fp = 0
            while True:
                candidates: list[tuple[ConditionHypothesisSet, int]] = []
                for chain, hypothesis in self.quantified_hypotheses.items():
                    hyp_not_explained = np.where((hypothesis._data_global_indices >= 0) &
                            np.isin(hypothesis._data_global_indices, predicted_deltas, invert=True))[0]
                    if len(hyp_not_explained) == 0:
                        continue
                    indices = np.flatnonzero(hypothesis._occupied)
                    counts = hypothesis.eval_subset_counts(indices, hyp_not_explained)
                    chances = counts[:, TP_IDX] + counts[:, FP_IDX] # if h is ground truth, this is the number of chances to be flipped negative
                    fp_tolerance = binom.ppf(0.95, chances.astype(int), epsilon)
                    filtered = counts[:, FP_IDX] <= fp_tolerance # restrict to hypotheses whose FP could be explained by noise
                    if not filtered.any():
                        continue
                    max_tp = counts[filtered, TP_IDX].max()
                    filtered = filtered & (counts[:, TP_IDX] == max_tp) # restrict to hypotheses who explain the most deltas
                    if not filtered.any() or max_tp == 0:
                        continue
                    for index in indices[filtered]:
                        log_prior = hypothesis._log_prior[index] + get_uqv_log_complexity(len(chain.uqvs))
                        gain = counts[index, TP_IDX] - counts[index, FP_IDX]
                        if beta * gain > -log_prior: # hypothesis must justify its complexity with explanatory power
                            candidates.append((chain, hypothesis, index))
                if len(candidates) == 0:
                    break
                chosen_uqvs, chosen_hypothesis, chosen_index = candidates[np.random.randint(len(candidates))]
                disjunction = disjunction | {(chosen_uqvs, chosen_hypothesis, chosen_index)}
                predicted_tp_mask = chosen_hypothesis._data_predictions[chosen_index, :] == chosen_hypothesis.TP_PRED
                predicted_fp_mask = chosen_hypothesis._data_predictions[chosen_index, :] == chosen_hypothesis.FP_PRED
                num_fp += predicted_fp_mask.sum()
                predicted_global_indices = chosen_hypothesis._data_global_indices[predicted_tp_mask | predicted_fp_mask]
                predicted_deltas = np.concatenate((predicted_deltas, predicted_global_indices))
            if disjunction not in self._disjunctions:
                self._disjunctions.append(disjunction)
                self._disjunction_fn_indices.append([])
                self._disjunction_scores = np.concatenate((self._disjunction_scores, [0.0])) # score will be computed later

        def score_disjunction(disjunction: frozenset[tuple[QuantifiedChain, ConditionHypothesisSet, int]]) -> float:
            predicted_deltas = np.zeros(0, dtype=int)
            num_fp = 0
            for chain, hypothesis, index in disjunction:
                hyp_not_explained = np.where((hypothesis._data_global_indices >= 0) &
                    np.isin(hypothesis._data_global_indices, predicted_deltas, invert=True))[0]
                predicted_tp_mask = hypothesis._data_predictions[index, hyp_not_explained] == hypothesis.TP_PRED
                predicted_fp_mask = hypothesis._data_predictions[index, hyp_not_explained] == hypothesis.FP_PRED
                num_fp += predicted_fp_mask.sum()
                predicted_global_indices = hypothesis._data_global_indices[hyp_not_explained[predicted_tp_mask | predicted_fp_mask]]
                predicted_deltas = np.concatenate((predicted_deltas, predicted_global_indices))
            fn_indices = np.setdiff1d(np.where(self.grounding_instance_deltas)[0], predicted_deltas)
            num_fn = len(fn_indices)
            complexity = get_disjunction_log_complexity(disjunction)
            return complexity - beta * (num_fp + num_fn), list(sorted(set(fn_indices)))

        # rescore disjunctions; prune low-scoring disjunctions
        empty = frozenset()
        if empty not in self._disjunctions:
            self._disjunctions.append(empty)
            dscore, dfn_indices = score_disjunction(empty)
            self._disjunction_scores = np.concatenate((self._disjunction_scores, [dscore]))
            self._disjunction_fn_indices.append(dfn_indices)
        for i, disjunction in enumerate(self._disjunctions):
            self._disjunction_scores[i], self._disjunction_fn_indices[i] = score_disjunction(disjunction)
        sorted_scores, sorted_disjunctions, sorted_dfn = zip(*sorted(
            zip(self._disjunction_scores, self._disjunctions, self._disjunction_fn_indices),
            key=lambda x: x[0], reverse=True))
        self._disjunctions = list(sorted_disjunctions)[:self._max_disjunctions]
        self._disjunction_scores = np.array(sorted_scores)[:self._max_disjunctions]
        self._disjunction_fn_indices = list(sorted_dfn)[:self._max_disjunctions]
        w = np.exp((self._disjunction_scores - self._disjunction_scores.max()))
        self._disjunction_probabilities = w / w.sum()
        keep_indices = np.where(self._disjunction_probabilities > self._disjunction_pruning_threshold)[0]
        null_idx = next((i for i,x in enumerate(self._disjunctions) if len(x) == 0), None) # always keep the empty effect
        if null_idx is not None and null_idx not in keep_indices:
            keep_indices = np.concatenate((keep_indices, [null_idx]))
        self._disjunctions = [self._disjunctions[i] for i in keep_indices]
        self._disjunction_scores = self._disjunction_scores[keep_indices]
        self._disjunction_fn_indices = [x for i, x in enumerate(self._disjunction_fn_indices) if i in keep_indices]
        self._disjunction_probabilities = self._disjunction_probabilities[keep_indices]
        self._disjunction_probabilities /= self._disjunction_probabilities.sum()

    def get_best_conditions(self) -> list[tuple[QuantifiedChain, Condition]]:
        if len(self._disjunctions) == 0:
            return []
        best_disjunction = self._disjunctions[0]
        return [(chain, hypothesis.get_condition_by_index(index)) for chain, hypothesis, index in best_disjunction]

    def manage_exploration_sets(self):
        existing_chains = set(self.quantified_hypotheses.keys())
        for chain in existing_chains:
            qset = self.quantified_hypotheses[chain]
            if qset.get_condition_belief(0) > 0.9:
                self.quantified_hypotheses.pop(chain)
                try:
                    new_chain = next(self._qset_iter)
                except StopIteration:
                    continue
                self.quantified_hypotheses[new_chain] = self._initialize_hypothesis_set(new_chain)
                print(f"Sufficiently explored ??? variable set {chain.uqvs}. Replaced with {new_chain.uqvs}.")


    def enumerate_variable_sets(self) -> Iterator[QuantifiedChain]:
        types = set([t for pred in self.predicates.values() for t in pred.types])
        for i in range(1, self.max_uqvs + 2):
            for combo in itertools.combinations_with_replacement(types, i):
                mapping = frozendict({f"UQV_{j}": t for j, t in enumerate(combo)})
                yield QuantifiedChain(frozendict({}), Atom("???", tuple(mapping.keys()), tuple(mapping.values())), uqvs=mapping)
