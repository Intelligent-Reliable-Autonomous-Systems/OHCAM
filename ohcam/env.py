import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from ohcam.trace import PDDLPlanParser
from unified_planning.exceptions import UPInvalidActionError, UPTypeError
from unified_planning.model import Problem
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import SequentialSimulator, UPState
from unified_planning.shortcuts import Compiler
from unified_planning.engines import CompilationKind

from ohcam.up_utils import FluentExpLike, copy_problem_into_domain, dict_state_to_up_state, up_state_to_dict

Observation = UPState | dict[FluentExpLike, bool]
StepResult = tuple[Observation, float, bool, bool, dict[str, Any]]


class InteractionDomain:

    def __init__(self, domain: Problem, horizon: int = 100, obs_noise: float = 0.0, obs_as_dict: bool = True):
        self._domain = domain
        self._horizon = horizon
        self._obs_as_dict = obs_as_dict
        self._obs_noise = obs_noise
        self._problem = self._domain.clone()
        self._simulator = SequentialSimulator(self._problem)

    def reset(self, problem: Problem) -> tuple[Observation, dict[str, Any]]:
        self._problem = copy_problem_into_domain(problem, self._domain)

        self._compilation =  Compiler(
            problem_kind=problem.kind,
            compilation_kind=CompilationKind.STATE_INVARIANTS_REMOVING,
        ).compile(self._problem)
        self._simulator = SequentialSimulator(self._compilation.problem)
        self._cur_state = self._simulator.get_initial_state()
        self._step_count = 0

        info = {
            'objects': self._problem.all_objects
        }
        return self._get_obs(self._cur_state), info

    def step(self, action: ActionInstance | tuple[str, ...]) -> StepResult:
        try:
            action = self.to_action_instance(action)
        except UPTypeError:
            # Arguments don't type-check against the true domain (e.g. OLAM trying an object as a possible subtype)
            return self._get_obs(self._cur_state), -1, True, False, {'status': 'inapplicable', 'step_count': self._step_count, 'objects': self._problem.all_objects}
        if not self._simulator.is_applicable(self._cur_state, action):
            try:
                unsatisfied_conditions, _ = self._simulator.get_unsatisfied_conditions(self._cur_state, action)
                unsat = {'unsatisfied_conditions': unsatisfied_conditions}
            except UPInvalidActionError:
                unsat = {}
            return self._get_obs(self._cur_state), -1, True, False, {'status': 'inapplicable', 'step_count': self._step_count, 'objects': self._problem.all_objects, **unsat}
        next_state = self._simulator.apply(self._cur_state, action)
        is_goal = self._simulator.is_goal(next_state)
        self._step_count += 1
        self._prev_state = self._cur_state
        self._cur_state = next_state
        status = 'goal_reached' if is_goal else 'applicable'
        return self._get_obs(next_state), \
            int(is_goal), is_goal, not is_goal and self._step_count >= self._horizon, \
            {'status': status, 'step_count': self._step_count, 'objects': self._problem.all_objects}

    def to_action_instance(self, action: tuple[str, ...] | ActionInstance) -> ActionInstance:
        if isinstance(action, tuple):
            objects = [self._compilation.problem.object(obj) for obj in action[1:]]
            root_action_name = action[0].split('__')[0]
            gt_action = self._compilation.problem.action(root_action_name)
            action = ActionInstance(gt_action, objects[:len(gt_action.parameters)])
        else:
            # ensure action is associated with the problem instance
            root_action_name = action.action.name.split('__')[0]
            gt_action = self._compilation.problem.action(root_action_name)
            action = ActionInstance(self._compilation.problem.action(gt_action.name),
                [self._problem.object(obj.object().name) for obj in action.actual_parameters[:len(gt_action.parameters)]])
        return action

    def step_plan(self, plan: Sequence[ActionInstance], expected_states: list[dict[FluentExpLike, bool]]) -> tuple[list[Observation], float, bool, bool, dict[str, Any]]:
        states = []
        cum_reward = 0
        done = False
        truncated = False
        info = {}
        for action in plan:
            next_state, reward, done, truncated, info = self.step(action)
            cum_reward += reward
            states.append(next_state)
            if done:
                break
        return states, cum_reward, done, truncated, info


    def _get_obs(self, state: UPState) -> UPState | dict[FluentExpLike, bool]:
        if self._obs_noise > 0:
            dict_state = up_state_to_dict(state) # set closed_world=True if you want to flip false->true
            for fluent, value in dict_state.items():
                if np.random.random() < self._obs_noise:
                    dict_state[fluent] = not value
            if self._obs_as_dict:
                return dict_state
            return dict_state_to_up_state(dict_state, self._problem)
        if self._obs_as_dict:
            return up_state_to_dict(state)
        return state

class TraceLoggerWrapper(InteractionDomain):
    def __init__(self, env: InteractionDomain, trace_dir: Path, meta: dict[str, str] | None = None):
        self._env = env
        self._trace_dir = trace_dir
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        self._parser = PDDLPlanParser(env._domain, prefer_delta=True)
        self._meta = meta or {}
        self._reset_idx = 0
        self._cum_step_idx = 0

    def reset(self, problem: Problem) -> tuple[Observation, dict[str, Any]]:
        state, info = self._env.reset(problem)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        self._trace_file = self._trace_dir / f"{timestamp}_{self._reset_idx:03d}_{self._env._problem.name}.trace"
        meta = {
            'domain': self._env._domain.name,
            'problem': self._env._problem.name,
            'step': self._cum_step_idx,
            **self._meta,
        }
        self._reset_idx += 1
        self._parser.initialize_trace_file(self._trace_file, state, object_types=info['objects'], meta=meta)
        self._trace_file.touch()
        return state, info

    def step(self, action: ActionInstance | tuple[str, ...]) -> StepResult:
        try:
            action = self._env.to_action_instance(action)
        except UPTypeError:
            pass  # ill-typed; the env reports it inapplicable and we log the action as given
        state, reward, term, trunc, info = self._env.step(action)
        execution = info['status']
        self._parser.append_trace_step(self._trace_file, action, state, execution)
        self._cum_step_idx += 1
        return state, reward, term, trunc, info
