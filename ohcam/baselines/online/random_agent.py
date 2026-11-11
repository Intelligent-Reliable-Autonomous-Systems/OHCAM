import numpy as np

from ohcam.baselines.online.online_agent import OnlineAgent
from ohcam.dataset import ExperimentDataset
from ohcam.up_utils import copy_problem_into_domain, sample_action_from_state
from unified_planning.model import Problem, UPState, Object as UPObject
from unified_planning.plans import ActionInstance


class RandomAgent(OnlineAgent):
    def __init__(self, dataset: ExperimentDataset, approach_key: str | None = None):
        self.dataset = dataset
        self._name = approach_key or "random"
        approach_cfg = dataset.get_approach_cfg(self.name)
        self.epsilon = approach_cfg.get("epsilon", 0.0)
        self.use_gt = approach_cfg.get("use_gt", False)

    @property
    def name(self) -> str:
        return self._name

    def reset_problem(self, problem: Problem):
        if self.use_gt:
            self.problem = copy_problem_into_domain(problem, self.dataset._gt_domain)
        else:
            self.problem = copy_problem_into_domain(problem, self.dataset.initial_domain)

    def get_action(self, state: UPState, objects: list[UPObject]) -> ActionInstance:
        if np.random.random() < self.epsilon:
            relax_terms = np.random.choice([1, 1, 1, 1, 1, 2, 2, 3])
        else:
            relax_terms = 0
        return sample_action_from_state(self.problem, state, relax_terms=relax_terms)

    def learn_step(self, state: UPState, objects: list[UPObject], action_instance: ActionInstance, next_state: UPState, status: str) -> bool:
        return False

    def get_learned_domain(self) -> Problem | None:
        return None
