from collections import OrderedDict
from pathlib import Path

import numpy as np
import gym

from ohcam.baselines.offline.offline_agent import OfflineAgent
from ohcam.trace import Trace
from predicators.settings import CFG
from predicators.structs import GroundAtom, LowLevelTrajectory, PDDLProblemGenerator, ParameterizedOption, Predicate, STRIPSOperator, Segment, Object as PredicatorObject, Action as PredicatorAction
from predicators.envs.pddl_env import _PDDLEnv
from predicators.nsrt_learning.strips_learning.clustering_learner import ClusterAndIntersectSTRIPSLearner
from unified_planning.model import InstantaneousAction, Problem, Type as UPType, Fluent as UPFluent

from ohcam.dataset import ExperimentDataset
from ohcam.up_utils import FluentExpLike, all_objects_from_state, reorder_problem_actions, sort_effects, sort_preconditions
from unified_planning.shortcuts import BoolType, UserType, FluentExp
from ohcam.up_utils import empty_domain

def init_predicators():
    setattr(CFG, 'seed', 42)

class PredicatorPDDLEnv(_PDDLEnv):

    domain_file: Path
    name: str

    @classmethod
    def get_domain_str(cls) -> str:
        return cls.domain_file.read_text()

    def get_name(cls) -> str:
        return cls.name

    @property
    def _pddl_train_problem_generator(self) -> PDDLProblemGenerator:
        return lambda n, rng: []

    @property
    def _pddl_test_problem_generator(self) -> PDDLProblemGenerator:
        return lambda n, rng: []


def up_state_dict_to_predicator_atoms(state: dict[FluentExpLike, bool], env: PredicatorPDDLEnv, object_map: dict[str, PredicatorObject], pred_map: dict[str, Predicate]) -> list[GroundAtom]:
    atoms: set[GroundAtom] = set()
    for fluent, value in state.items():
        if value:
            atoms.add(GroundAtom(pred_map[fluent.fluent().name], [object_map[o.object().name] for o in fluent.args]))
    return atoms

def get_segments(traces: list[Trace], env: PredicatorPDDLEnv) -> list[list[Segment]]:
    segments: list[list[Segment]] = []
    type_map = {t.name: t for t in env._types}
    pred_map = {p.name: p for p in env._predicates}
    dummy_llt = LowLevelTrajectory(
        _states=[{}],
        _actions=[],
        _is_demo=False,
        _train_task_idx=None,
    )
    def dummy_param_policy(state, mem, objects, params) -> PredicatorAction:
        return PredicatorAction(np.array([]))
    def dummy_param_initiable(state, mem, objects, params) -> bool:
        return True
    def dummy_param_terminal(state, mem, objects, params) -> bool:
        return True
    poptions: dict[str, ParameterizedOption] = {}
    for strips_op in env.strips_operators:
        print(strips_op)
        poption = ParameterizedOption(
            strips_op.name,
            [p.type for p in strips_op.parameters],
            gym.spaces.Box(low=0, high=0, shape=(0,), dtype=np.float32),
            dummy_param_policy,
            dummy_param_initiable,
            dummy_param_terminal,
            arg_names=[p.name for p in strips_op.parameters]
        )
        poptions[strips_op.name] = poption
    trace_idx = 0
    for trace in traces:
        states, actions, executions = trace
        seg_list: list[Segment] = []
        all_objects = set([o for s in states for o in all_objects_from_state(s)])
        object_map = {o.name: PredicatorObject(o.name, type_map[o.type.name]) for o in all_objects}
        from_states = states[:-1]
        to_states = states[1:]
        for from_state, action, to_state, execution in zip(from_states, actions, to_states, executions):
            if execution == 'inapplicable':
                continue
            pred_objects = [object_map[o.object().name] for o in action.actual_parameters]
            poption = poptions[action.action.name]
            grounded_option = poption.ground(pred_objects, np.array([]))
            seg = Segment(
                trajectory=dummy_llt,
                init_atoms=up_state_dict_to_predicator_atoms(from_state, env, object_map, pred_map),
                final_atoms=up_state_dict_to_predicator_atoms(to_state, env, object_map, pred_map),
                _option=grounded_option,
            )
            seg._debug_id = f"trace {trace_idx}; step {len(seg_list)}"
            seg_list.append(seg)
        if len(seg_list) > 0:
            segments.append(seg_list)
        trace_idx += 1
    return segments


def predicator_to_up_problem(env: PredicatorPDDLEnv, operators: list[STRIPSOperator], initial_problem: Problem | None = None) -> Problem:
    problem = Problem()
    problem.name = env.name
    if initial_problem is not None:
        # Clone the user types, objects, and fluents, but not the actions, which are learned below
        initial_problem._clone_to_without_actions_and_metrics(problem)
        for fluent in initial_problem.fluents:
            if not problem.has_fluent(fluent.name):
                problem.add_fluent(fluent)
    else:
        up_types: dict[str, UPType] = {}
        for pred_type in env._types:
            if pred_type.parent is not None:
                father = up_types[pred_type.parent.name]
            else:
                father = None
            up_types[pred_type.name] = UserType(pred_type.name, father=father)

        for pred_atom in env._predicates:
            params = OrderedDict()
            type_counts = {pt.name: int(sum(1 for pt in pred_atom.types if pt.name == pt.name) > 1) for pt in set(pred_atom.types)}
            for pt in pred_atom.types:
                count_str = type_counts[pt.name] - 1 if type_counts[pt.name] > 0 else ''
                name = f'{pt.name}{count_str}'
                type_counts[pt.name] += 1
                params[name] = up_types[pt.name]
            fluent = UPFluent(pred_atom.name, BoolType(), params)
            problem.add_fluent(fluent)

    action_name_roots = [op.name.split('__')[0] for op in operators]
    action_name_counts = {root: sum(1 for root_name in action_name_roots if root_name == root) for root in set(action_name_roots)}
    for operator in operators:
        root = operator.name.split('__')[0]
        count = action_name_counts[root]
        if count > 1:
            action_name = operator.name
        else:
            action_name = root
        action = InstantaneousAction(action_name, {p.name.replace('?', ''): problem.user_type(p.type.name) for p in operator.parameters})
        for pred_atom in operator.preconditions:
            pred_name = pred_atom.predicate.name
            up_pred = problem.fluent(pred_name)
            params = [action.parameter(arg.name.replace('?', '')) for arg in pred_atom.entities]
            action_bound_pred = FluentExp(up_pred, params)
            action.add_precondition(action_bound_pred)

        for pred_atom in operator.add_effects:
            pred_name = pred_atom.predicate.name
            up_pred = problem.fluent(pred_name)
            params = [action.parameter(arg.name.replace('?', '')) for arg in pred_atom.entities]
            action_bound_pred = FluentExp(up_pred, params)
            action.add_effect(action_bound_pred, True)

        for pred_atom in operator.delete_effects:
            pred_name = pred_atom.predicate.name
            up_pred = problem.fluent(pred_name)
            params = [action.parameter(arg.name.replace('?', '')) for arg in pred_atom.entities]
            action_bound_pred = FluentExp(up_pred, params)
            action.add_effect(action_bound_pred, False)

        problem.add_action(action)

    return problem

class PredicatorsAgent(OfflineAgent):

    def __init__(self, dataset: ExperimentDataset, data_source: str, approach_key: str | None = None):
        self.dataset = dataset
        self._name = approach_key or "predicators"
        self.data_source = data_source
        self.initial_domain = empty_domain(self.dataset.initial_domain)
        cfg = dataset.get_approach_cfg(self.name)
        CFG.min_perc_data_for_nsrt = cfg.get("min_perc_data_for_nsrt", 0)
        approach_dir = dataset.get_approach_dir(self.name)
        approach_dir.mkdir(parents=True, exist_ok=True)
        self.empty_domain_file = approach_dir / "empty.pddl"
        dataset.get_pddl_writer(self.initial_domain).write_domain(str(self.empty_domain_file))

        init_predicators()
        PredicatorPDDLEnv.domain_file = self.empty_domain_file
        PredicatorPDDLEnv.name = self.initial_domain.name
        self.env = PredicatorPDDLEnv(use_gui=False)

        self.all_segments = []


    @property
    def name(self) -> str:
        return self._name

    def learn_offline(self, traces: list[Trace]) -> None:
        segments = get_segments(traces, self.env)
        self.all_segments.extend(segments)
        print(len(segments))
        self.pnads = ClusterAndIntersectSTRIPSLearner([seg_list[0].trajectory for seg_list in self.all_segments], [], self.env.predicates, self.all_segments, verify_harmlessness=False, annotations=None, verbose=True).learn()

    def get_learned_domain(self) -> Problem:
        learned_domain = predicator_to_up_problem(self.env, [pnad.op for pnad in self.pnads], self.initial_domain)
        reorder_problem_actions(learned_domain, self.dataset.initial_domain)
        sort_preconditions(learned_domain)
        sort_effects(learned_domain)
        return learned_domain
