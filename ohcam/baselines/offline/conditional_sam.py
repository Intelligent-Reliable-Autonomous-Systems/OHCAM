

import time

from ohcam.baselines.offline.offline_agent import OfflineAgent
from ohcam.dataset import ExperimentDataset
from ohcam.up_utils import FluentExpLike
from pddl_plus_parser.models import (
    Domain as PDDLPlusDomain,
    PDDLObject,
    PDDLType as PDDLPlusType,
    GroundedPredicate as PDDLPlusGroundedPredicate,
    ActionCall as PDDLPlusActionCall,
    State as PDDLPlusState,
    Observation as PDDLPlusObservation,
)
from sam_learning.learners.conditional_sam import ConditionalSAM
from sam_learning.learners.universaly_conditional_sam import UniversallyConditionalSAM
from pddl_plus_parser.lisp_parsers.domain_parser import DomainParser as PDDLPlusDomainParser
from pddl_plus_parser.exporters.domain_exporter import DomainExporter
from unified_planning.model import Problem, Object as UPObject
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import FluentExp, Problem as UPProblem
from unified_planning.io import PDDLReader

class UPToPDDLPlusConverter:

    def __init__(self, problem: UPProblem):
        self.problem = problem
        self.pddl_plus_types = self.get_pddl_plus_types(problem)

    def get_pddl_plus_types(self, problem: UPProblem) -> dict[str, PDDLPlusType]:
        pp_types = {}
        for up_type in problem.user_types:
            if up_type.father is not None:
                parent = pp_types.get(up_type.father.name, None)
            else:
                parent = None
            pp_type = PDDLPlusType(up_type.name, parent=parent)
            pp_types[up_type.name] = pp_type
        return pp_types


    def up_fluent_to_pddl_plus_gpredicate(self, fluent: FluentExp, value: bool) -> PDDLPlusGroundedPredicate:
        name = fluent.fluent().name
        signature = {f'?{x.name}':self.pddl_plus_types[x.type.name] for x in fluent.fluent().signature}
        object_mapping = {param_name:arg.object().name for param_name, arg in zip(signature.keys(), fluent.args)}
        return PDDLPlusGroundedPredicate(name, signature, object_mapping, is_positive=value)

    def up_state_to_pddl_plus_state(self, state: dict[FluentExp, bool]) -> PDDLPlusState:
        gpredicates = {}
        for fluent, value in state.items():
            gpred = self.up_fluent_to_pddl_plus_gpredicate(fluent, value)
            gpred_repr = gpred.lifted_untyped_representation
            if gpred_repr in gpredicates:
                gpredicates[gpred_repr].add(gpred)
            else:
                gpredicates[gpred_repr] = set([gpred])
        return PDDLPlusState(gpredicates, {})

    def up_action_to_pddl_plus_action(self, action: ActionInstance) -> PDDLPlusActionCall:
        name = action.action.name
        parameters = [arg.object().name for arg in action.actual_parameters]
        return PDDLPlusActionCall(name, parameters)

    def up_trajectory_to_pddl_plus_trajectory(self, states: list[dict[FluentExp, bool]], objects: list[UPObject],
        actions: list[ActionInstance], executions: list[str]) -> PDDLPlusObservation:
        from_states = states[:-1]
        to_states = states[1:]
        pddl_plus_trajectory = PDDLPlusObservation()
        pddl_plus_trajectory.grounded_objects = {obj.name:PDDLObject(obj.name, self.pddl_plus_types[obj.type.name]) for obj in objects}
        for from_state, action, to_state, execution in zip(from_states, actions, to_states, executions):
            pddl_plus_from_state = self.up_state_to_pddl_plus_state(from_state)
            pddl_plus_to_state = self.up_state_to_pddl_plus_state(to_state)
            pddl_plus_action = self.up_action_to_pddl_plus_action(action)
            pddl_plus_trajectory.add_component(pddl_plus_from_state, pddl_plus_action, pddl_plus_to_state, execution != 'inapplicable')
        return pddl_plus_trajectory







def get_pddl_plus_trajectories(dataset: ExperimentDataset, traces: list[tuple[list[dict[FluentExpLike, bool]], list[ActionInstance], list[str]]], filter_inapplicable: bool = False) -> list[PDDLPlusObservation]:
    converter = UPToPDDLPlusConverter(dataset.initial_domain)
    trajectories = []
    for i, trace in enumerate(traces):
        states, actions, executions = trace
        pddl_plus_trajectory = converter.up_trajectory_to_pddl_plus_trajectory(states, trace.objects, actions, executions)
        pddl_plus_trajectory.components = [component for component in pddl_plus_trajectory.components if not filter_inapplicable or component.is_successful]
        if len(pddl_plus_trajectory.components) == 0:
            continue
        trajectories.append(pddl_plus_trajectory)
    return trajectories


class ConditionalSAMAgent(OfflineAgent):

    def __init__(self, dataset: ExperimentDataset, data_source: str, approach_key: str | None = None):
        self.dataset = dataset
        self._name = approach_key or "conditional-sam"
        approach_cfg = dataset.get_approach_cfg(self.name)
        self.universals_map = approach_cfg.get("uqv", {})
        self.max_ants = approach_cfg.get("max_ants", 2)
        # When set, get_statistics() reports the size of conditional SAM's
        # candidate conditional-effect hypothesis space (per action + total).
        self.num_hypotheses = approach_cfg.get("num_hypotheses", False)
        self.data_source = data_source

        self.learned_model_path = dataset.get_approach_domain_path(self.name, data_source)
        self.initial_domain = None
        self.learned_domain = None
        self.info = None

        self.all_observations = []

        self._learning_time = 0

    @property
    def name(self) -> str:
        return self._name

    def _build_blank_slate_domain(self) -> PDDLPlusDomain:
        """Parse the initial domain and strip every action's effects/preconditions.

        Conditional SAM expects a blank slate: it (re)derives all effects and
        preconditions from the traces, so we clear whatever the ground-truth
        domain declared before handing it to the learner.
        """
        domain_parser = PDDLPlusDomainParser(self.dataset.initial_domain_file)
        initial_domain = domain_parser.parse_domain()
        for action in initial_domain.actions.values():
            # SAM wants a blank slate
            action.discrete_effects = set()
            action.conditional_effects = set()
            action.preconditions.root.operands = set()
        return initial_domain

    def _build_learner(self, initial_domain: PDDLPlusDomain):
        """Construct the (universally) conditional SAM learner for a given domain."""
        if self.universals_map is not None:
            self.universals_map = {**{action_name: [] for action_name in initial_domain.actions}, **self.universals_map}
            return UniversallyConditionalSAM(
                partial_domain=initial_domain, max_antecedents_size=self.max_ants, universals_map=self.universals_map
            )
        return ConditionalSAM(partial_domain=initial_domain, max_antecedents_size=self.max_ants)

    def count_hypotheses(self) -> dict:
        """Count conditional SAM's candidate conditional-effect hypothesis space.

        Conditional SAM begins by treating every (effect literal, antecedent
        conjunction) pair as a possible conditional effect and prunes pairs as
        data arrives. The initial size of that space -- what ``create_cnf_combination``
        enumerates via ``_initialize_actions_dependencies`` (and, for universals,
        ``_initialize_universal_dependencies``) -- is the fair counterpart to the
        number of hypotheses OHCAM covers.

        This depends only on the domain vocabulary and ``max_ants``; it needs no
        traces. We eagerly initialize the dependency sets with a dummy grounded
        action per lifted action (only the action name is used) and count the
        resulting antecedent conjunctions.

        :return: per-action and total hypothesis counts.
        """
        initial_domain = self._build_blank_slate_domain()
        learner = self._build_learner(initial_domain)
        is_universal = isinstance(learner, UniversallyConditionalSAM)

        per_action: dict[str, dict] = {}
        for action_name, action in initial_domain.actions.items():
            # Only grounded_action.name is read during initialization; parameters
            # are irrelevant, so a dummy call over the lifted signature suffices.
            dummy_action = PDDLPlusActionCall(action_name, list(action.signature.keys()))
            learner._initialize_actions_dependencies(dummy_action)
            conditional_antecedents = learner.conditional_antecedents[action_name].possible_antecedents
            conditional_hypotheses = sum(len(conjunctions) for conjunctions in conditional_antecedents.values())
            num_effect_literals = len(conditional_antecedents)

            universal_hypotheses = 0
            universal_effect_literals = 0
            if is_universal:
                learner._initialize_universal_dependencies(dummy_action)
                for dependency_set in learner.quantified_antecedents[action_name].values():
                    universal_hypotheses += sum(len(conjunctions) for conjunctions in dependency_set.possible_antecedents.values())
                    universal_effect_literals += len(dependency_set.possible_antecedents)

            per_action[action_name] = {
                "num_effect_literals": num_effect_literals + universal_effect_literals,
                "num_hypotheses": conditional_hypotheses + universal_hypotheses,
                "conditional_hypotheses": conditional_hypotheses,
                "universal_hypotheses": universal_hypotheses,
            }

        return {
            "max_ants": self.max_ants,
            "universal": is_universal,
            "total_hypotheses": sum(a["num_hypotheses"] for a in per_action.values()),
            "total_effect_literals": sum(a["num_effect_literals"] for a in per_action.values()),
            "per_action": per_action,
        }

    def get_statistics(self) -> dict:
        statistics = super().get_statistics()
        if self.num_hypotheses:
            statistics["hypothesis_space"] = self.count_hypotheses()
        statistics["learning_time"] = self._learning_time
        return statistics

    def learn_offline(self, traces: list[tuple[list[dict[FluentExpLike, bool]], list[ActionInstance], list[str]]]) -> None:
        start_time = time.time()
        self.initial_domain = self._build_blank_slate_domain()
        self.learner = self._build_learner(self.initial_domain)
        print("Converting traces to PDDL+ trajectories")
        self.all_observations.extend(get_pddl_plus_trajectories(self.dataset, traces, filter_inapplicable=True))
        print("Learning action model with", self.learner, f"max_ants={self.max_ants}", f"universals_map={self.universals_map or {}}")
        try:
            learned_domain, info = self.learner.learn_action_model(self.all_observations)
        except Exception:  # reported downstream as no learned domain
            self.learned_domain = None
            self.info = {}
            return
        self._learning_time = time.time() - start_time
        self.learned_domain = learned_domain
        self.info = info

    def get_learned_domain(self) -> Problem:
        if self.learned_domain is None:
            return None
        DomainExporter().export_domain(self.learned_domain, self.learned_model_path)
        return PDDLReader().parse_problem(str(self.learned_model_path))
