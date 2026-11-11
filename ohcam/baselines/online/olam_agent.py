from collections import defaultdict
import logging
from pathlib import Path
from ohcam.baselines.online.online_agent import OnlineAgent
from ohcam.dataset import ExperimentDataset
from ohcam.up_utils import initialize_problem_from_state
from olam.modeling.PDDLenv import PDDLEnv
from olam.modeling.trajectory import Trajectory
from unified_planning.io import PDDLReader
from unified_planning.model import Parameter, Problem, UPState, Object as UPObject
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import SequentialSimulator
import unified_planning as up
from amlgym.util.util import empty_domain

import numpy as np
from olam.OLAM import OLAM

up.shortcuts.get_environment().credits_stream = None
APPROACH_NAME = 'olam'


class OlamAgent(OnlineAgent):
    def __init__(self, dataset: ExperimentDataset, approach_key: str | None = None):
        self.dataset = dataset
        self._name = approach_key or APPROACH_NAME
        approach_dir = dataset.get_approach_dir(self.name)
        approach_dir.mkdir(parents=True, exist_ok=True)
        input_domain_path = empty_domain(dataset.initial_domain_file, approach_dir / "empty.pddl")
        self.olam = OlamWrapper(input_domain_path, dataset.initial_domain_file,
                                seed_preconditions=dataset.fixed_preconditions)

    @property
    def name(self) -> str:
        return self._name

    def reset_problem(self, problem: Problem):
        sim = SequentialSimulator(problem)
        initial_state = sim.get_initial_state()
        objects = problem.all_objects
        self.olam.reset_problem(initial_state, objects)

    def get_action(self, state: UPState, objects: list[UPObject]) -> ActionInstance:
        try:
            action = self.olam.step_olam(state)
        except Exception as e:
            print(f"Error in step_olam: {e}")
            action = None
        if action is None:
            # OLAM found nothing left to learn here. Take a random action rather than ending the problem, so it
            # uses its whole step budget like the other approaches, and can still learn from what happens
            action = self.olam.random_action()
            print(f"OLAM has no learning action or plan; taking random action {action}")
        return action

    def learn_step(self, state: UPState, objects: list[UPObject], action_instance: ActionInstance, next_state: UPState, status: str) -> bool:
        try:
            return self.olam.learn_step(state, action_instance, next_state, status)
        except Exception as e:
            print(f"Error in learn_step: {e}")
            return False

    def get_learned_domain(self) -> Problem:
        return self.olam.get_learned_domain()

class OlamWrapper(OLAM):

    def __init__(self, input_domain_path: Path, initial_domain_path: Path, seed_preconditions: bool = False):
        super().__init__(input_domain_path, planning_timeout=60)
        self._num_steps = 0
        if seed_preconditions:
            self._seed_preconditions(PDDLReader().parse_problem(initial_domain_path))

    def _seed_preconditions(self, initial_model: Problem):
        """Record the initial domain's preconditions as certain, so OLAM doesn't spend steps testing them.

        OLAM's candidate preconditions already contain every relevant predicate, so the given preconditions add
        nothing to its model. A singleton {p} in pre_bot says the action fails whenever p is false, which keeps
        OLAM from choosing groundings that violate p as precondition-learning actions. OLAM names its operator
        parameters param_1, param_2, ..., so each precondition is rewritten in those names to match its candidates.
        pre_bot is only initialized in OLAM's constructor, so this is done once rather than on every reset.
        """
        for operator in initial_model.actions:
            if operator.name not in self.pre_bot:
                continue
            rename = {operator.environment.expression_manager.ParameterExp(p):
                      operator.environment.expression_manager.ParameterExp(Parameter(f"param_{i + 1}", p.type, operator.environment))
                      for i, p in enumerate(operator.parameters)}
            candidates = {str(p) for p in self.domain.action(operator.name).preconditions}
            for precondition in operator.preconditions:
                for p in (precondition.args if precondition.is_and() else [precondition]):
                    lifted = str(p.substitute(rename))
                    if lifted in candidates:
                        self.pre_bot[operator.name].add(frozenset({lifted}))
                    else:
                        # OLAM only learns positive preconditions over its candidates; anything else can't be seeded
                        logging.warning(f"OLAM: not seeding precondition {lifted} of {operator.name}, not a candidate")

    def reset_problem(self, initial_state: UPState, objects: list[UPObject]):
        """Initialize the Olam agent.

        Equivalent to olam.reset(...) without simulator.
        """
        # Reconstruct the problem based on the domain and the initial state
        problem = initialize_problem_from_state(self.domain, initial_state, objects)
        sim = SequentialSimulator(problem=problem)
        self._pddl_env = PDDLEnv(sim)
        self.reset(self._pddl_env)
        state = self.infer_state_types(self.initial_state.clone())
        self._traj = Trajectory(observations=[state], actions=list())
        self._plan = None

    def step_olam(self, state: UPState):

        problem = initialize_problem_from_state(self.domain, state, self.all_objects)
        sim = SequentialSimulator(problem=problem)
        state = sim.get_initial_state() # cast into self.domain
        self._pddl_env._state = state
        state = self._pddl_env._get_obs()
        state = self.infer_state_types(state)
        # OLAM assumes a failed action leaves the state unchanged, and after a failure only recomputes which
        # groundings of the failed operator are certain to fail. The environment resets after a failure, so when
        # the state changed, forget the failure to make OLAM recompute every operator's in the new state
        if self.last_failed_action is not None and \
                {str(lit) for lit in state.positive_literals} != self._state_at_failure:
            self.last_failed_action = None
        print(f"Step {self._num_steps}")
        self._num_steps += 1
        # Action for learning preconditions
        self._executing_learning_action = False
        actions_for_preconditions = (
            self.action_generator.get_learning_actions_precs(
                state,
                self.last_failed_action,
                self.pre_bot,
                self.pre_bot_ambiguous_types,
            )
        )
        # Keep OLAM's order, which tries the actions with the most satisfied preconditions first
        actions_for_effects = self.action_generator.get_learning_actions_effs(
            state, self.uncertain_positive_effects, self.uncertain_negative_effects
        )
        learning_actions = actions_for_preconditions + actions_for_effects

        if len(learning_actions) > 0:
            learning_action_label = learning_actions.pop(0)
            self._executing_learning_action = True

            learning_action = self.action_generator.parse_textual_action(
                learning_action_label, self.action_generator.domain
            )
            obj_types = [
                self.problem.object(str(o)).type
                for o in learning_action.actual_parameters
            ]
            action_types = [p.type for p in learning_action.action.parameters]
            compatible_types = [
                p_type.is_compatible(o_type)
                for o_type, p_type in zip(obj_types, action_types, strict=True)
            ]

            if not np.all(compatible_types):
                self.executed_actions_ambiguous[str(state)].add(
                    learning_action_label
                )

            else:
                self.executed_actions[str(state)].add(learning_action_label)

            op = self.action_generator.parse_textual_action(
                learning_action_label, self.action_generator.domain
            )
            logging.debug("Executing learning action")
        else:
            if self._plan is None or len(self._plan.actions) == 0:
                # order the operators based on the number of the preconditions
                operators_to_refine = [
                    a.name
                    for a in sorted(
                        self.domain.actions, key=lambda x: len(x.preconditions)
                    )
                    if a.name not in self.learned_operators
                ]
                for operator_name in operators_to_refine:
                    try:
                        self._plan = self.learner.plan_for_operator(
                            state,
                            self.domain.action(operator_name),
                            self.uncertain_positive_effects,
                            self.uncertain_negative_effects,
                            self.pre_bot,
                            self.pre_bot_ambiguous_types,
                            self.executed_actions_ambiguous,
                            self.problem,
                            self.invalid_actions,
                            self.PLANNER_CFG,
                        )
                    except AssertionError as e:
                        logging.debug(f"Error planning for operator {operator_name}: {e}")
                        return None

                    if self._plan is None:
                        if self.learner.timed_out:
                            # Planning timed out, so the operator may still have something to learn
                            logging.debug(f"Operator {operator_name} not learned: planning timed out")
                            continue
                        logging.debug(f"Operator {operator_name} learned!")
                        self.learned_operators.add(operator_name)
                    else:
                        if len(self._plan.actions) == 0:
                            logging.debug(f"Operator {operator_name} is unsolvable!")
                            return None
                        break
            if self._plan is None:
                return None
            else:
                if len(self._plan.actions) == 0:
                    logging.debug("No plan found!")
                    return None
                op = self._plan.actions[0]
                logging.debug("Executing planned action")
                self._plan.actions.remove(op)
                if len(self._plan.actions) == 0:
                    self._plan = None

        return op

    def learn_step(self, state: UPState, action_instance: ActionInstance, next_state: UPState, status: str):
        problem = initialize_problem_from_state(self.domain, state, self.all_objects)
        sim = SequentialSimulator(problem=problem)
        state = sim.get_initial_state() # cast into self.domain
        self._pddl_env._state = state
        state = self._pddl_env._get_obs()
        state = self.infer_state_types(state)
        problem = initialize_problem_from_state(self.domain, next_state, self.all_objects)
        sim = SequentialSimulator(problem=problem)
        next_state = sim.get_initial_state() # cast into self.domain
        self._pddl_env._state = next_state
        next_state = self._pddl_env._get_obs()
        next_state = self.infer_state_types(next_state)
        executable = status != 'inapplicable'
        updated_model = False
        if not executable:
            next_state = None
        if executable:
            logging.debug(f"Successfully executed action {action_instance}")

            # Update trajectory
            self._traj.add_action(action_instance)
            self._traj.add_obs(next_state)

            # Learn effects from trajectory
            updated_effs = self.learn_effects(action_instance, state, next_state)

            # Learn preconditions from trajectory
            updated_precs = self.learn_preconditions(action_instance, state)

            updated_model = updated_precs or updated_effs
            if updated_model:
                self.learner.goal_gen.unsolvable_goals = defaultdict(set)
                self.learned_operators = set()
            # Update the state
            state = next_state

            self.last_failed_action = None

            # if a learning action is interleaved while executing a plan, and the
            # learning action succeeds, then the agent must replan
            if self._executing_learning_action:
                self._plan = None
        else:
            # Failed action
            logging.debug(f"Failed to execute action {action_instance}")

            # If the action preconditions are satisfied, then the action must
            # involve some wrong object type. This can happen when an object
            # (sub)type is not inferred which cause the agent trying ground actions
            # with all possible subtypes, possibly attempting to execute actions
            # with invalid object types.
            params_map = {
                p: o
                for p, o in zip(
                    action_instance.action.parameters,
                    action_instance.actual_parameters,
                    strict=True,
                )
            }
            ground_precs = {
                str(p.substitute(params_map))
                for p in action_instance.action.preconditions
            }
            pos_literals = {str(lit) for lit in state.positive_literals}
            if ground_precs.issubset(pos_literals):
                obj_types = [
                    self.problem.object(str(o)).type
                    for o in action_instance.actual_parameters
                ]
                action_types = [p.type for p in action_instance.action.parameters]
                compatible_types = [
                    p_type.is_compatible(o_type)
                    for o_type, p_type in zip(obj_types, action_types, strict=True)
                ]
                if all(compatible_types):
                    logging.debug("An action with all satisfied preconditions has failed, and the action object types are *not* ambiguous.")
                    return None

                logging.debug(
                    f"Adding {action_instance} to the list of invalid actions."
                )

                # TODO: open issue in unified planning, the if cond should
                #  not be necessary
                if str(action_instance) not in {
                    str(a) for a in self.invalid_actions
                }:
                    self.invalid_actions.add(action_instance)
                    updated_model = True

            else:
                import copy

                def dicts_different(d1, d2):
                    if d1.keys() != d2.keys():
                        return True
                    for k in d1:
                        if d1[k] != d2[k]:
                            return True
                    return False

                prev_pre_bot = copy.deepcopy(self.pre_bot)
                prev_pre_bot_ambiguous = copy.deepcopy(self.pre_bot_ambiguous_types)
                self.learn_preconditions_from_failed_action(action_instance, state)
                updated_model = (
                    dicts_different(prev_pre_bot, self.pre_bot)
                    or dicts_different(prev_pre_bot_ambiguous, self.pre_bot_ambiguous_types)
                )

            self.last_failed_action = action_instance
            self._state_at_failure = {str(lit) for lit in state.positive_literals}
        return updated_model

    def get_learned_domain(self):
        return self.domain.clone()

    def random_action(self) -> ActionInstance:
        label = self.all_grounded_actions[np.random.randint(len(self.all_grounded_actions))]
        return self.action_generator.parse_textual_action(label, self.action_generator.domain)
