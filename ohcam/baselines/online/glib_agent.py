"""Online GLIB baseline agent.

Wraps the GLIB relational model-based RL agent (Chitnis & Silver et al., AAAI
2021) behind the :class:`OnlineAgent` interface used by the experiments.

GLIB natively operates on ``pddlgym`` states/actions and learns PDDL operators
from scratch via goal-literal babbling for exploration and LNDR (noisy deictic
rule learning) for operator induction. This wrapper bridges the two worlds:

* the initial (unified-planning) domain supplies the predicates, types and
  action signatures used to build the ``pddlgym`` action/observation spaces;
* per-step ``UPState`` / ``ActionInstance`` values are translated to and from
  ``pddlgym`` structs;
* the learned, determinized PDDL domain is parsed back into a UP ``Problem``.

Like the OLAM baseline, GLIB relearns operators from experience, so only the
*structure* of the initial domain is used - its (possibly buggy) operator
bodies are ignored.
"""

import re
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

from ohcam.baselines.online.online_agent import OnlineAgent
from ohcam.dataset import ExperimentDataset
from ohcam.up_utils import up_state_to_dict

from unified_planning.model import InstantaneousAction, Problem, UPState, Object as UPObject
from unified_planning.plans import ActionInstance
from unified_planning.model import Variable
from unified_planning.shortcuts import And, Equals, Forall, Not, Or, SequentialSimulator
import unified_planning as up

from pddlgym.core import PDDLEnv
from pddlgym.structs import State, TypedEntity, Type, LiteralConjunction

from glib.agent import Agent
from glib.settings import AgentConfig, EnvConfig

up.shortcuts.get_environment().credits_stream = None


def _patch_fast_downward():
    """Load FastDownward's shared library once and reuse it.

    GLIB's ``fast_downward`` binding reloads a fresh copy of ``libdownward.so``
    (from a since-deleted temp dir) and ``dlclose``s it on every plan call.
    Repeatedly ``dlopen``/``dlclose``-ing FastDownward's stateful C++ library
    segfaults after the first call. We instead load it a single time and reset
    its state between plans via ``cleanup()`` rather than unloading it.
    """
    import glib.planning_modules.ff as ff

    if getattr(ff, "_glib_agent_patched", False):
        return
    original_load_lib = ff.load_lib
    cache: dict = {}

    def load_lib_cached():
        if "lib" not in cache:
            cache["lib"] = original_load_lib()
        return cache["lib"]

    def close_lib_reset(lib):
        try:
            lib.cleanup()
        except Exception:  # noqa: BLE001
            pass

    ff.load_lib = load_lib_cached
    ff.close_lib = close_lib_reset
    ff._glib_agent_patched = True


_patch_fast_downward()

APPROACH_NAME = "glib"

# Defaults chosen to reproduce "GLIB-L": lifted goal babbling + LNDR operator
# learning + Fast Downward planning.
DEFAULT_CURIOSITY = "GLIB_L2"
DEFAULT_OPERATOR_LEARNING = "LNDR"
DEFAULT_PLANNER = "ff"


class GlibAgent(OnlineAgent):
    def __init__(self, dataset: ExperimentDataset, approach_key: str | None = None):
        self.dataset = dataset
        self._name = approach_key or APPROACH_NAME
        cfg = dataset.get_approach_cfg(self._name)
        self._curiosity_name = cfg.get("curiosity", DEFAULT_CURIOSITY)
        self._operator_learning_name = cfg.get("operator_learning", DEFAULT_OPERATOR_LEARNING)
        self._planner_name = cfg.get("planner", DEFAULT_PLANNER)
        # How often to re-run (expensive) operator learning, in env steps.
        self._learning_interval = cfg.get("learning_interval", 1)

        self._approach_dir = dataset.get_approach_dir(self._name)
        self._approach_dir.mkdir(parents=True, exist_ok=True)

        # When the benchmark declares the preconditions correct/fixed (the
        # fixed-preconditions setting), seed GLIB with them: prune exploration to
        # applicable actions and keep the initial preconditions in the output.
        self._fixed_preconditions = bool(getattr(dataset, "fixed_preconditions", False))
        self._initial_precond_index = self._build_initial_precond_index()

        self._domain_name = dataset.initial_domain.name or APPROACH_NAME
        self._register_glib_settings()
        self._domain_file = self._write_structure_domain()

        # Lazily created once the first problem (hence a concrete object set) is
        # available, since pddlgym needs a problem file to build its spaces.
        self._glib: Agent | None = None
        self._pddl_domain = None  # pddlgym parsed domain
        self._action_pred_names: set[str] = set()
        self._num_steps = 0

        # Per-problem state.
        self._problem: Problem | None = None
        self._goal = LiteralConjunction([])
        self._episode_reset = False

    @property
    def name(self) -> str:
        return self._name

    # ------------------------------------------------------------------
    # OnlineAgent interface
    # ------------------------------------------------------------------
    def reset_problem(self, problem: Problem):
        self._problem = problem
        # Build the GLIB agent on the first problem, using this problem to seed
        # pddlgym's spaces. Subsequent problems reuse the same agent (its object
        # set updates dynamically from the states we feed it).
        if self._glib is None:
            self._build_glib(problem)

        sim = SequentialSimulator(problem)
        initial_state = sim.get_initial_state()
        objects = list(problem.all_objects)
        pddlgym_state = self._up_state_to_pddlgym(initial_state, objects)
        # pddlgym's action space caches ground literals per object set; refresh it
        # for this problem (normally done by PDDLEnv.reset, which we bypass).
        self._action_space.reset_initial_state(pddlgym_state)
        self._glib.reset_episode(pddlgym_state)
        self._episode_reset = True

    def get_action(self, state: UPState, objects: list[UPObject]) -> ActionInstance | None:
        if not self._episode_reset:
            self._glib.reset_episode(self._up_state_to_pddlgym(state, objects))
            self._episode_reset = True
        try:
            action_lit = self._glib.get_action(self._up_state_to_pddlgym(state, objects))
        except Exception as e:  # noqa: BLE001 - GLIB planners can raise many things
            print(f"[glib] get_action failed: {e}")
            return None
        if action_lit is None:
            return None
        return self._literal_to_up_action(action_lit)

    def learn_step(self, state: UPState, objects: list[UPObject], action_instance: ActionInstance,
                   next_state: UPState, status: str) -> bool:
        pddlgym_state = self._up_state_to_pddlgym(state, objects)
        pddlgym_next = self._up_state_to_pddlgym(next_state, objects)
        action_lit = self._up_action_to_literal(action_instance)
        # Replan when the transition doesn't match the model's prediction, as FF-Replan does (Section 4). An
        # inapplicable action also resets the environment, so the plan no longer applies even if it was predicted
        if status == "inapplicable" or not self._predicted(pddlgym_state, action_lit, pddlgym_next):
            self._glib._curiosity_module._plan = []
        try:
            self._glib.observe(pddlgym_state, action_lit, pddlgym_next)
        except Exception as e:  # noqa: BLE001
            print(f"[glib] observe failed: {e}")
            return False
        self._num_steps += 1
        if self._num_steps % self._learning_interval != 0:
            return False
        try:
            return bool(self._glib.learn())
        except Exception as e:  # noqa: BLE001
            print(f"[glib] learn failed: {e}")
            return False

    @staticmethod
    def _add_uniqueness_precondition(action: InstantaneousAction, extra_names: list[str]):
        """Require that no other binding of the deictic parameters satisfies the preconditions, as GLIB's own
        planner does (base_planner._create_uniqueness_pddl_str), so the exported model matches the one GLIB
        explored with."""
        if not extra_names or not action.preconditions:
            return
        em = action.environment.expression_manager
        extra = [action.parameter(name) for name in extra_names]
        others = [Variable(f"{p.name}_other", p.type, action.environment) for p in extra]
        rename = {em.ParameterExp(p): em.VariableExp(v) for p, v in zip(extra, others)}
        other_binding = And(*[pre.substitute(rename) for pre in action.preconditions])
        same_binding = And(*[Equals(em.VariableExp(v), em.ParameterExp(p)) for p, v in zip(extra, others)])
        action.add_precondition(Forall(Or(same_binding, Not(other_binding)), *others))

    def _predicted(self, state: State, action_lit, next_state: State) -> bool:
        """Whether the current model's most likely effects for the action are the observed ones."""
        ndrs = self._glib._operator_learning_module._ndrs.get(action_lit.predicate)
        predicted = ndrs.predict_max(state.literals, action_lit) if ndrs is not None else set()
        return set(predicted) == set(Agent._compute_effects(state, next_state))

    def get_learned_domain(self) -> Problem | None:
        if self._glib is None or not self._glib.learned_operators:
            return None
        try:
            return self._learned_operators_to_up()
        except Exception as e:  # noqa: BLE001
            print(f"[glib] could not build learned domain: {e}")
            return None

    def _learned_operators_to_up(self) -> Problem:
        """Convert GLIB's determinized operators into a UP domain.

        Works from GLIB's operator *objects* rather than its PDDL string, which
        keeps us clear of the ``(different ...)`` / ``forall`` scaffolding GLIB
        only synthesises when printing PDDL. Mirrors the predicators baseline's
        split-operator convention: operators are named after the underlying
        action (``root``), and when an action is explained by several branches
        they are suffixed ``root__0``, ``root__1``, .... Extra deictic operator
        parameters are kept as trailing action parameters.
        """
        problem = self.dataset.initial_domain.clone()
        problem._actions = []  # replace initial operators with the learned ones

        operators = sorted(self._glib.learned_operators, key=lambda o: o.name)
        # Recover, per operator, the underlying action name from the injected
        # action-predicate literal (a pddlgym operators_as_actions artefact),
        # and the ordered "true" action parameters it binds.
        parsed = [(op, *self._operator_root_and_action_params(op)) for op in operators]
        root_counts = Counter(root for _, root, _ in parsed)
        branch_seen: dict[str, int] = defaultdict(int)

        for op, root, primary_params in parsed:
            if root_counts[root] > 1:
                name = f"{root}__{branch_seen[root]}"
            else:
                name = root
            branch_seen[root] += 1

            # Convert each operator on its own, so one that fails to convert is dropped rather than losing the
            # whole learned model to the initial domain
            try:
                # Action args first (positional match with the ground-truth schema),
                # then any extra deictic variables.
                primary_names = [p.name for p in primary_params]
                extra = [p for p in op.params if p.name not in primary_names]
                ordered = list(primary_params) + extra
                up_params = OrderedDict(
                    (self._var_name(p), problem.user_type(str(p.var_type))) for p in ordered
                )
                action = InstantaneousAction(name, _parameters=up_params,
                                             _env=problem.environment)

                # The given preconditions are known to be correct but may be incomplete, so add them to GLIB's learned
                # ones rather than replacing those
                if self._fixed_preconditions and root in self._initial_precond_index:
                    self._add_fixed_preconditions(problem, action, root, primary_params)
                given = {str(pre) for pre in action.preconditions}
                for lit in op.preconds.literals:
                    if lit.predicate.name in self._action_pred_names:
                        continue  # drop the self-referential action-predicate leak
                    fexp = self._lit_to_up(problem, action, lit)
                    negated = getattr(lit, "is_negative", False) \
                        or getattr(lit, "negated_as_failure", False)
                    pre = Not(fexp) if negated else fexp
                    if str(pre) not in given:
                        action.add_precondition(pre)

                for eff in op.effects.literals:
                    if eff.predicate.name in ("noiseoutcome",):
                        continue
                    fexp = self._lit_to_up(problem, action, eff)
                    add = not getattr(eff.predicate, "is_anti", False)
                    action.add_effect(fexp, add)

                self._add_uniqueness_precondition(action, [self._var_name(p) for p in extra])
                problem.add_action(action)
            except Exception as e:  # noqa: BLE001
                print(f"[glib] dropped operator {op.name} that could not be converted: {e}\n"
                      f"    params={op.params} preconds={op.preconds} effects={op.effects}")
        return problem

    def _build_initial_precond_index(self) -> dict[str, list[tuple[str, bool, list[int]]]]:
        """Index each initial-domain action's preconditions by parameter position.

        Maps action name -> list of ``(predicate_name, is_negative, [param_idx])``
        where ``param_idx`` are positions into the action's parameter list. This
        lets us re-ground the fixed preconditions onto GLIB's operators (whose
        action arguments line up positionally with the initial schema).
        """
        index: dict[str, list[tuple[str, bool, list[int]]]] = {}
        for action in self.dataset.initial_domain.actions:
            param_idx = {p.name: i for i, p in enumerate(action.parameters)}
            lits: list[tuple[str, bool, list[int]]] = []
            for pre in action.preconditions:
                lits.extend(self._flatten_precondition(pre, param_idx))
            index[action.name] = lits
        return index

    def _flatten_precondition(self, fnode, param_idx) -> list[tuple[str, bool, list[int]]]:
        """Flatten a (possibly conjunctive) STRIPS precondition into literals."""
        if fnode.is_and():
            out: list[tuple[str, bool, list[int]]] = []
            for arg in fnode.args:
                out.extend(self._flatten_precondition(arg, param_idx))
            return out
        if fnode.is_not():
            inner = fnode.arg(0)
            if not inner.is_fluent_exp():
                return []
            return [(inner.fluent().name, True, self._precond_arg_indices(inner, param_idx))]
        if fnode.is_fluent_exp():
            return [(fnode.fluent().name, False, self._precond_arg_indices(fnode, param_idx))]
        # Non-STRIPS constructs (forall/or/exists) are not seeded.
        return []

    @staticmethod
    def _precond_arg_indices(fluent_exp, param_idx) -> list[int]:
        indices = []
        for arg in fluent_exp.args:
            if arg.is_parameter_exp():
                indices.append(param_idx[arg.parameter().name])
            else:
                indices.append(-1)  # constant/object arg: not a parameter
        return indices

    def _add_fixed_preconditions(self, problem, action, root, primary_params):
        """Add the initial domain's preconditions to ``action``, grounded on its
        action arguments (``primary_params``)."""
        for pred_name, is_negative, indices in self._initial_precond_index[root]:
            if any(i < 0 or i >= len(primary_params) for i in indices):
                continue  # references a constant or an arg GLIB didn't bind
            params = [action.parameter(self._var_name(primary_params[i])) for i in indices]
            fexp = problem.fluent(pred_name)(*params)
            action.add_precondition(Not(fexp) if is_negative else fexp)

    @staticmethod
    def _var_name(entity) -> str:
        return entity.name.replace("?", "")

    def _given_preconditions_pddl(self, op) -> list[str]:
        """The initial domain's preconditions of a GLIB operator's action, as PDDL literals over its action
        arguments, for GLIB's planner."""
        root, primary_params = self._operator_root_and_action_params(op)
        literals = []
        for pred_name, is_negative, indices in self._initial_precond_index.get(root, []):
            if any(i < 0 or i >= len(primary_params) for i in indices):
                continue  # references a constant or an arg GLIB didn't bind
            literal = "({} {})".format(pred_name, " ".join(primary_params[i].name for i in indices))
            literals.append("(not {})".format(literal) if is_negative else literal)
        return literals

    def _operator_root_and_action_params(self, op):
        """Return (action_name, ordered_action_params) for a GLIB operator."""
        for lit in op.preconds.literals:
            if lit.predicate.name in self._action_pred_names:
                return lit.predicate.name, list(lit.variables)
        # No action literal (shouldn't happen): fall back to stripping the
        # determinization suffix from the operator name.
        return op.name.rstrip("0123456789"), list(op.params)

    def _lit_to_up(self, problem, action, lit):
        fluent = problem.fluent(lit.predicate.name)
        params = [action.parameter(self._var_name(v)) for v in lit.variables]
        return fluent(*params)

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    def _register_glib_settings(self):
        """Seed GLIB's per-domain hyperparameter dicts for our domain.

        GLIB keys many settings by hard-coded domain names in ``settings.py``.
        For a novel domain we register our domain name in every such dict by
        copying the ``"Blocks"`` defaults, which match the STRIPS + LNDR setting.
        """
        for cfg in (AgentConfig, EnvConfig):
            for value in vars(cfg).values():
                if isinstance(value, dict) and "Blocks" in value \
                        and self._domain_name not in value:
                    value[self._domain_name] = value["Blocks"]
        # The paper initializes LNDR's greedy search with the previously learned rules (Appendix A), which the
        # released settings only do for Tireworld
        AgentConfig.zpk_initialize_from_previous_rule_set[self._domain_name] = True
        # Time budget for all of GLIB's planning in one step; the paper used 10s per planning call (Appendix A)
        AgentConfig.planner_timeout = 60

    def _write_structure_domain(self) -> Path:
        """Write the initial domain to PDDL for pddlgym to parse its structure.

        pddlgym requires an explicit ``(:types ...)`` block whenever ``:typing``
        is declared, but UP omits it when every parameter has the implicit
        ``object`` type. We inject the referenced types so the parser accepts it.
        """
        path = self._approach_dir / "structure_domain.pddl"
        self.dataset.get_pddl_writer(self.dataset.initial_domain).write_domain(str(path))
        text = path.read_text()
        if ":typing" in text and "(:types" not in text:
            types = sorted(set(re.findall(r"\s-\s+([\w-]+)", text)))
            if types:
                types_block = "  (:types " + " ".join(types) + ")\n"
                text = re.sub(r"(\(:requirements[^)]*\)\s*\n)", r"\1" + types_block,
                              text, count=1)
                path.write_text(text)
        return path

    def _build_glib(self, problem: Problem):
        # pddlgym parses spaces from a domain file + a directory of problems.
        problem_dir = self._approach_dir / "pddlgym_problems"
        problem_dir.mkdir(parents=True, exist_ok=True)
        problem_path = problem_dir / "problem.pddl"
        self.dataset.get_pddl_writer(problem).write_problem(str(problem_path))
        # UP names the problem's domain after the problem, so force it to match
        # the domain file (pddlgym asserts the two agree).
        domain_text = self._domain_file.read_text()
        pddl_domain_name = re.search(r"\(define\s*\(domain\s+([\w-]+)", domain_text).group(1)
        prob_text = re.sub(r"\(:domain\s+[\w-]+\)", f"(:domain {pddl_domain_name})",
                           problem_path.read_text(), count=1)
        problem_path.write_text(prob_text)

        # Always use the full (non-dynamic) action space: it enumerates every
        # type-consistent grounding, is never empty, and avoids FastDownward's
        # grounder dropping effect-less actions or locking us out of a state.
        # When the preconditions are given (fixed_preconditions) we don't *prune*
        # the space by them - that would hurt whenever the given preconditions
        # are wrong or a state is a dead end - we only *bias* sampling toward
        # applicable actions (see _install_precondition_bias), giving GLIB the
        # same head start our method gets without ever constraining it.
        env = PDDLEnv(
            str(self._domain_file),
            str(problem_dir),
            operators_as_actions=True,
            dynamic_action_space=False,
            raise_error_on_invalid_action=False,
        )
        # pddlgym parses the ':equality' '=' predicate (and anything it leaves
        # untyped) with var_types=None; it is not a real observable predicate and
        # crashes GLIB's planner init. Drop such predicates from the spaces.
        self._sanitize_space_predicates(env.observation_space)
        self._sanitize_space_predicates(env.action_space)

        self._pddl_domain = env.domain
        self._action_space = env.action_space
        self._action_pred_names = {p.name for p in env.action_space.predicates}
        if self._fixed_preconditions and self._initial_precond_index:
            self._install_precondition_bias(env.action_space)
        self._glib = Agent(
            self._domain_name,
            env.action_space,
            env.observation_space,
            self._curiosity_name,
            self._operator_learning_name,
            planning_module_name=self._planner_name,
        )
        # Plan with the given preconditions as well as the learned ones, as OLAM and OHCAM explore with them
        if self._fixed_preconditions:
            self._glib._planning_module.extra_preconditions = self._given_preconditions_pddl

    @staticmethod
    def _sanitize_space_predicates(space):
        """Drop predicates pddlgym left untyped (var_types=None), e.g. the
        ':equality' ``=`` builtin, which is not a real state predicate and breaks
        GLIB's planner init. 0-arity predicates keep ``var_types=[]`` and stay."""
        kept = [p for p in space.predicates if getattr(p, "var_types", None) is not None]
        if len(kept) != len(space.predicates):
            space.predicates = sorted(kept)
            space.num_predicates = len(space.predicates)

    def _install_precondition_bias(self, space):
        """Bias action sampling toward actions applicable under the known,
        fixed preconditions - without ever pruning the space.

        This gives GLIB the same head start our method gets from knowing some
        preconditions: early (pre-operator) exploration and mutex rollouts
        prefer actions that are actually executable, so GLIB gathers
        effect-bearing transitions instead of guessing blindly. It cannot hurt:
        when no action is applicable (e.g. the given preconditions are wrong or
        the state is a dead end) it falls back to the full type-consistent set,
        exactly matching the unbiased baseline. Patches only this instance; no
        library/version change.
        """
        def sample_literal(state):
            all_lits = sorted(space.all_ground_literals(state, valid_only=False))
            if not all_lits:
                return None
            applicable = [lit for lit in all_lits if self._is_applicable(state, lit)]
            pool = applicable if applicable else all_lits
            return pool[space.np_random.choice(len(pool))]

        space.sample_literal = sample_literal

    def _is_applicable(self, state, action_lit) -> bool:
        """Whether ``action_lit`` satisfies the fixed initial preconditions in
        ``state`` (pddlgym literals)."""
        index = self._initial_precond_index.get(action_lit.predicate.name)
        if not index:
            return True
        variables = action_lit.variables
        for pred_name, is_negative, indices in index:
            if any(i < 0 or i >= len(variables) for i in indices):
                continue  # constant/unbound arg: can't check, treat as satisfied
            ground = self._pddl_domain.predicates[pred_name](*[variables[i] for i in indices])
            holds = ground in state.literals
            if holds == is_negative:  # positive-but-absent or negative-but-present
                return False
        return True

    # ------------------------------------------------------------------
    # UP <-> pddlgym conversions
    # ------------------------------------------------------------------
    def _up_object_to_entity(self, obj: UPObject) -> TypedEntity:
        return TypedEntity(obj.name, Type(obj.type.name))

    def _up_state_to_pddlgym(self, state: UPState, objects: list[UPObject]) -> State:
        literals = frozenset(
            self._up_fluent_to_literal(fexp)
            for fexp, value in up_state_to_dict(state).items()
            if value
        )
        entities = frozenset(self._up_object_to_entity(o) for o in objects)
        return State(literals, entities, self._goal)

    def _up_fluent_to_literal(self, fexp):
        pred = self._pddl_domain.predicates[fexp.fluent().name]
        args = [self._up_object_to_entity(arg.object()) for arg in fexp.args]
        return pred(*args)

    def _up_action_to_literal(self, action_instance: ActionInstance):
        pred = self._pddl_domain.predicates[action_instance.action.name]
        args = [self._up_object_to_entity(p.object()) for p in action_instance.actual_parameters]
        return pred(*args)

    def _literal_to_up_action(self, action_lit) -> ActionInstance:
        action = self._problem.action(action_lit.predicate.name)
        params = tuple(self._problem.object(var.name) for var in action_lit.variables)
        return ActionInstance(action, params)
