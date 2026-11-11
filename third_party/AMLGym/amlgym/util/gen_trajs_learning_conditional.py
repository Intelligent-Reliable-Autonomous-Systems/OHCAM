# Add current project to sys path
import os
import sys
import argparse

from datetime import datetime
import yaml
import re
import contextlib
import logging
import random
import shutil
import numpy as np
import unified_planning
from alive_progress import alive_bar
from unified_planning.io import PDDLReader
from unified_planning.model import Problem, UPState
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import OneshotPlanner, SequentialSimulator


from tarski.io import PDDLReader as tarskiPDDLReader
from tarski.grounding import LPGroundingStrategy

from conditional_repair.dataset import PDDLPlanParser
from amlgym.modeling.trajectory import Trajectory
from amlgym.util.gen_problems_conditional import *  # do not remove  # noqa: F403

def replan(problem: Problem,
           current_state: UPState,
           action_instance: ActionInstance) -> any:
    """
    Check action execution does not make the problem unsolvable by simulating the action and computing
    a new plan
    :param problem: solvable problem
    :param action: action to be executed
    :return: new plan (if any)
    """
    # Update the problem initial state
    problem = problem.clone()
    for fluent in problem.initial_values:
        value = current_state.get_value(fluent)
        problem.set_initial_value(fluent, value)

    # Simulate action execution
    with SequentialSimulator(problem=problem) as simulator:
        current_state = simulator.apply(current_state, action_instance)

    # Update the problem state
    problem = problem.clone()
    for fluent in problem.initial_values:
        value = current_state.get_value(fluent)
        problem.set_initial_value(fluent, value)

    # Check a plan still exists
    logging.debug(f"Checking random action {action_instance} preserves solvability.")
    with contextlib.redirect_stdout(open(os.devnull, 'w')):
        with OneshotPlanner(
                problem_kind=problem.kind,
                **PLANNER_CFG,
        ) as planner:
            result = planner.solve(problem, timeout=MAX_REPLANNING_TIME)
            plan = result.plan

    return plan


def generate_traj(
        problem: Problem,
        randomness: float = 0.2) -> Trajectory:

    with SequentialSimulator(problem=problem) as simulator:

        current_state = simulator.get_initial_state()
        states = [current_state]  # init trajectory states
        actions = []  # init trajectory actions
        plan = None

        # Ground actions with tarski since unified-planning (1.2.0) grounder is inefficient
        reader = tarskiPDDLReader(raise_on_error=True)
        reader.parse_domain(domain_file)
        reader.parse_instance(problem_file)
        grounder = LPGroundingStrategy(reader.problem)
        try:
            ground_actions = grounder.ground_actions()
        except:
            logging.debug(f"Problem unsolvable.")
            return Trajectory(states, actions)

        while len(states) < TRAJ_LEN_MAX:

            if plan is None:
                # Update the problem initial state
                logging.debug(f"Updating problem state")
                problem = problem.clone()
                for fluent in problem.initial_values:
                    value = current_state.get_value(fluent)
                    problem.set_initial_value(fluent, value)

                logging.debug("Computing a new plan...")
                # with contextlib.redirect_stdout(open(os.devnull, 'w')):
                with OneshotPlanner(
                        problem_kind=problem.kind,
                        **PLANNER_CFG
                ) as planner:
                    result = planner.solve(problem, timeout=MAX_PLANNING_TIME)
                    plan = result.plan

            # Problem unsolvable
            if plan is None:
                if result.status.name == 'TIMEOUT':
                    logging.debug(f"Planning timout reached ({MAX_PLANNING_TIME}s).")
                    break
                elif result.status.name == 'UNSOLVABLE_INCOMPLETELY':
                    logging.debug(f"Planning unsolvable.")
                    break
                else:
                    raise Exception(f"Planning exited with status: {result.status.name}")

            for action_instance in plan.actions:

                # Possibly execute a random action and replan
                if random.random() < randomness:
                    logging.debug(f"Sampling a random action...")

                    # applicable_actions = list(simulator.get_applicable_actions(current_state))
                    applicable_actions = [(problem.action(k.lower()), [problem.object(o.lower()) for o in objs])
                                          for k, params in ground_actions.items()
                                          for objs in params
                                          if simulator._is_applicable(current_state,
                                                                      problem.action(k.lower()),
                                                                      [problem.object(o.lower()) for o in objs])]

                    applicable_actions = sorted(applicable_actions, key=lambda x: f"{x[0]} - {x[1]}")  # reproducibility
                    action, params = random.choices(applicable_actions)[0]
                    action_instance = ActionInstance(action, params)
                    logging.debug(f"Random action sampled.")

                    # Check random action does not make the problem unfeasible
                    trial = 1
                    plan = replan(problem, current_state, action_instance)
                    # while not check_feasibility(problem, current_state, action_instance):
                    while plan is None:
                        trial += 1
                        logging.debug(f"Random action {action_instance} makes the problem unsolvable."
                                      f" Newly sampling a random action.")

                        # applicable_actions = list(simulator.get_applicable_actions(current_state))
                        applicable_actions = [(problem.action(k.lower()), [problem.object(o.lower()) for o in objs])
                                              for k, params in ground_actions.items()
                                              for objs in params
                                              if simulator._is_applicable(current_state,
                                                                          problem.action(k.lower()),
                                                                          [problem.object(o.lower()) for o in objs])]

                        applicable_actions = sorted(applicable_actions, key=lambda x: f"{x[0]} - {x[1]}")  # reproducibility
                        action, params = random.choices(applicable_actions)[0]
                        action_instance = ActionInstance(action, params)
                        plan = replan(problem, current_state, action_instance)
                        if trial >= MAX_RANDOM_TRIALS and plan is None:
                            break

                    if trial >= MAX_RANDOM_TRIALS and plan is None:
                        logging.debug(f"Maximum number of random action trials reached."
                                      f" Avoiding random action execution.")
                        break

                    logging.debug(f"Simulating random action {action_instance}.")
                    current_state = simulator.apply(current_state, action_instance)
                    states.append(current_state)
                    actions.append(action_instance)
                    break

                logging.debug(f"Simulating action {action_instance}.")
                current_state = simulator.apply(current_state, action_instance)
                actions.append(action_instance)

                if current_state is None:
                    raise Exception(f"Error in applying: {action_instance}")

                states.append(current_state)

            if plan is not None and (len(plan.actions) == 0 or action_instance == plan.actions[-1]):
                logging.debug("A goal state has been reached.")
                break

    return Trajectory(states, actions)


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('index', default=0, type=int, help='Index of the problem set to generate')
    parser.add_argument('--domains', nargs='+', default=None,
                        help='Only process these domains (default: all domains in the config)')
    args = parser.parse_args()

    TRAJ_LEN_MIN = 5
    TRAJ_LEN_MAX = None  # set runtime
    OPTIMAL_TRACES = 0 # I had a bug with this
    MAX_PLANNING_TIME = 60
    MAX_REPLANNING_TIME = 60  # time to check problem feasibility
    MAX_RANDOM_TRIALS = 3  # maximum number of random action samplings at each step
    MAX_TRAJ_TRIALS = 5  # maximum number of trajectory generation attempts per problem
    DOWNWARD_SEARCH_CFG = 'let(hff,ff(),let(hcea,cea(),lazy_greedy([hff,hcea],preferred=[hff,hcea])))'
    HEUR_PLANNER_CFG = {
        'name': 'fast-downward',
        'params': dict(
            fast_downward_search_config=DOWNWARD_SEARCH_CFG,
            fast_downward_search_time_limit=f"{MAX_PLANNING_TIME}s"
        )}
    OPT_PLANNER_CFG = {
        'name': 'fast-downward-opt',
    }

    PLANNER_CFG = OPT_PLANNER_CFG
    logging.basicConfig(
        filename='out.log',
        level=logging.DEBUG
    )
    BENCHMARK_DIR = "benchmarks"
    DOMAINS_DIR = "conditional/domains"
    PROB_DIR = f"conditional/problems/learning/train{args.index}"  # written by gen_probs_conditional_learning.py
    TRAJ_DIR = f"conditional/trajectories/learning/train{args.index}"
    TRACE_DIR = f"conditional/traces/learning/train{args.index}"
    DOM_CFG = f"{BENCHMARK_DIR}/conditional/problems_learning.yaml"

    # Trace CPU time
    run_start = datetime.now()

    # Instantiate a PDDL problem reader
    reader = PDDLReader(force_up_pddl_reader=True)

    # Disable printing of planning engine credits to avoid overloading stdout
    unified_planning.shortcuts.get_environment().credits_stream = None

    # Read domain configs
    with open(f"../{DOM_CFG}") as f:
        cfg = yaml.safe_load(f)
        seed = cfg['SEED']
        domains = cfg['domains']

    seed += 100 * args.index  # match gen_probs_conditional_learning.py

    to_be_avoided = []
    domains = {k: v for k, v in domains.items() if k not in to_be_avoided}
    if args.domains is not None:
        unknown = set(args.domains) - set(domains)
        if unknown:
            parser.error(f"unknown domains {sorted(unknown)}, choose from {sorted(domains)}")
        domains = {k: v for k, v in domains.items() if k in args.domains}

    for domain in domains:

        # Set random seed for reproducibility
        np.random.seed(seed)
        random.seed(seed)

        # Trace CPU time
        domain_run_start = datetime.now()

        problems_dir = f"../{BENCHMARK_DIR}/{PROB_DIR}/{domain}"
        if not os.path.isdir(problems_dir):
            logging.warning(f"No problems found in {problems_dir}, run gen_probs_conditional_learning.py first.")
            continue
        problem_files = sorted(
            (f for f in os.listdir(problems_dir) if re.fullmatch(rf"\d+_{re.escape(domain)}_prob\.pddl", f)),
            key=lambda f: int(f.split('_')[0]))

        # Clean domain trajectories directory
        if os.path.exists(f"../{BENCHMARK_DIR}/{TRAJ_DIR}/{domain}"):
            shutil.rmtree(f"../{BENCHMARK_DIR}/{TRAJ_DIR}/{domain}")
        os.makedirs(os.path.join(f"../{BENCHMARK_DIR}/{TRAJ_DIR}/{domain}"))

        # Clean domain traces directory
        if os.path.exists(f"../{BENCHMARK_DIR}/{TRACE_DIR}/{domain}"):
            shutil.rmtree(f"../{BENCHMARK_DIR}/{TRACE_DIR}/{domain}")
        os.makedirs(os.path.join(f"../{BENCHMARK_DIR}/{TRACE_DIR}/{domain}"))

        domain_file = f'../{BENCHMARK_DIR}/{DOMAINS_DIR}/{domain}.pddl'

        with alive_bar(len(problem_files),
                       title=f'Processing domain {domain}',
                       length=20,
                       bar='halloween') as bar:
            # For every existing domain problem
            for problem_fname in problem_files:
                i = int(problem_fname.split('_')[0])
                TRAJ_LEN_MAX = TRAJ_LEN_MIN + i * 2

                if i >= OPTIMAL_TRACES:
                    PLANNER_CFG = HEUR_PLANNER_CFG
                else:
                    PLANNER_CFG = OPT_PLANNER_CFG

                problem_name = problem_fname[:-len('.pddl')]
                problem_file = f'{problems_dir}/{problem_fname}'
                problem = reader.parse_problem(domain_file, problem_file)

                # Generate a trajectory, retrying since random actions make it stochastic
                trajectory = Trajectory([], [])
                for _ in range(MAX_TRAJ_TRIALS):
                    trajectory = generate_traj(problem)
                    if len(trajectory.states) >= TRAJ_LEN_MIN:
                        break
                    logging.debug(f"Failed to generate a sufficiently long trace. Retrying...")
                else:
                    logging.warning(f"Skipping {problem_file}: no trajectory of length >= {TRAJ_LEN_MIN}.")
                    bar()
                    continue

                traj_file = f'../{BENCHMARK_DIR}/{TRAJ_DIR}/{domain}/{problem_name}_traj'
                trajectory.write(traj_file)
                trace_file = f'../{BENCHMARK_DIR}/{TRACE_DIR}/{domain}/{problem_name}.trace'
                PDDLPlanParser(problem).write_trace_file(trace_file, trajectory.states, trajectory.actions)
                bar()  # update progress bar

        logging.info(f'{domain} CPU time (s): {(datetime.now() - domain_run_start).seconds}')

    logging.info(f'Total CPU time (s): {(datetime.now() - run_start).seconds}')
