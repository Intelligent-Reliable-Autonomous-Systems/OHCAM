import time

from ohcam.baselines.online.online_agent import OnlineAgent
from ohcam.dataset import ExperimentDataset
from ohcam.trace import Trace
from ohcam.up_utils import up_state_to_dict
from ohcam.core.learner import OHCAMConfig, initialize_ohcam, step_ohcam, learn_ohcam_step
from unified_planning.model import UPState, Object as UPObject
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import Problem

APPROACH_NAME = "ohcam"


class OHCAMAgent(OnlineAgent):
    def __init__(self, dataset: ExperimentDataset, approach_key: str | None = None, offline: bool = False):
        self.dataset = dataset
        self._name = approach_key or APPROACH_NAME
        init_domain = dataset.initial_domain
        approach_cfg = dataset.get_approach_cfg(self.name)
        config_params = approach_cfg.get("config", {})
        if offline:
            offline_config = approach_cfg.get("offline_config", {})
            config_params = {**config_params, **offline_config}
            config_params["exploration_qsets"] = 0
            if not config_params.get("combine_preconditions", False) and "hypothesis_expansion_target" not in offline_config:
                config_params["hypothesis_expansion_target"] = 1 # only keep the MAP hypothesis, unless offline_config says otherwise
        OHCAMConfig.instance().configure(**config_params, fix_init_precondition=dataset.fixed_preconditions, exploration_relax_precondition_prob=0.0)
        self.ohcam = initialize_ohcam(init_domain, OHCAMConfig.instance())

        self.best_actions = {action: self.ohcam.get_best_model_action(action) for action in self.ohcam.actions.keys()}
        self.num_steps = 0
        self.combine_preconditions = config_params.get("combine_preconditions", False)

        self._cur_plan = None
        self._learning_time = 0

    @property
    def name(self) -> str:
        return self._name

    def reset_problem(self, problem: Problem):
        self._cur_plan = None

    def get_action(self, state: UPState, objects: list[UPObject]) -> ActionInstance:
        plan = step_ohcam(self.ohcam, up_state_to_dict(state), objects, self._cur_plan)
        self._cur_plan = plan
        if len(self._cur_plan) == 0:
            return None
        return self._cur_plan.pop(0)

    def learn_step(self, state: UPState, objects: list[UPObject], action_instance: ActionInstance, next_state: UPState, status: str) -> bool:
        start_time = time.time()
        learn_ohcam_step(self.ohcam, up_state_to_dict(state), objects, action_instance, up_state_to_dict(next_state), status)
        self._learning_time += time.time() - start_time
        new_best_actions = {action: self.ohcam.get_best_model_action(action) for action in self.ohcam.actions.keys()}
        changed_actions = [act for act in self.ohcam.actions.keys() if new_best_actions[act] != self.best_actions[act]]
        if changed_actions:
            print(f"After learning step {self.num_steps}, updated domain actions: {changed_actions}")
            self.num_steps += 1
            self.best_actions = new_best_actions
            return True
        self.num_steps += 1
        return False

    def learn_offline(self, traces: list[Trace]) -> None:
        """Update the model from each transition of the given traces, in order."""
        start_time = time.time()
        step = 0
        for trace in traces:
            for state, action, next_state, execution in trace.get_transitions():
                learn_ohcam_step(self.ohcam, up_state_to_dict(state), trace.objects, action, up_state_to_dict(next_state), execution)
                step += 1
                if step % 10 == 0:
                    print(f"Learned {step} steps")
        self._learning_time += time.time() - start_time

    def get_learned_domain(self) -> Problem:
        return self.ohcam.get_best_up_model(self.combine_preconditions)

    def get_statistics(self) -> dict:
        return {
            "learning_time": self._learning_time,
            **self.ohcam.get_statistics()
        }
