# Add current project to sys path
import os
import sys
import time
import argparse
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from amlgym.util.gen_problems_conditional import *  # do not remove

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
from unified_planning.shortcuts import OneshotPlanner, SequentialSimulator
from conditional_repair.dataset import PDDLPlanParser


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('index', default=0, type=int, help='Index of the problem set to generate')
    parser.add_argument('--domains', nargs='+', default=None,
                        help='Only process these domains (default: all domains in the config)')
    args = parser.parse_args()

    MAX_PLANNING_TIME = 20
    PLANS_MIN_LEN = 5
    DOWNWARD_SEARCH_CFG = 'let(hff,ff(),let(hcea,cea(),lazy_greedy([hff,hcea],preferred=[hff,hcea])))'
    PLANNER_CFG = {  # heuristic planning
        'name': 'fast-downward',
        'params': dict(
            fast_downward_search_config=DOWNWARD_SEARCH_CFG,
            fast_downward_search_time_limit=f"{MAX_PLANNING_TIME}s"
        )}
    logging.basicConfig(
        # filename='out.log',
        level=logging.DEBUG
    )
    GEN_DIR = "pddl-generators"
    BENCHMARK_DIR = "benchmarks"
    DOMAINS_DIR = "conditional/domains"
    PROB_DIR = f"conditional/problems/learning/train{args.index}"
    SOLVE_TRAJ_DIR = f"conditional/traces/solving/train{args.index}" # store the traces of the solved problems
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

    seed += 100 * args.index

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

        # Clean domain problems directory
        if os.path.exists(f"../{BENCHMARK_DIR}/{PROB_DIR}/{domain}"):
            shutil.rmtree(f"../{BENCHMARK_DIR}/{PROB_DIR}/{domain}")
        os.makedirs(os.path.join(f"../{BENCHMARK_DIR}/{PROB_DIR}/{domain}"))

        with alive_bar(len(domains[domain]),
                       title=f'Processing domain {domain}',
                       length=20,
                       bar='halloween') as bar:
        # bar = lambda: None
        # if True:
            # For every domain problem kwargs
            for i, kwargs in enumerate(domains[domain]):

                plan = None

                while (plan is None) or len(plan.actions) < PLANS_MIN_LEN:
                    # Generate a problem
                    logging.debug(f"Generating a new problem")
                    kwargs['seed'] = np.random.randint(1, 1000)
                    generate_prob = getattr(sys.modules[__name__], f'problem_{domain}')
                    problem_str = generate_prob(**kwargs)
                    # Fix hyphens to avoid issues with unified-planning parsing
                    # problem_str = re.sub(r'(?<=\w)-(?=\w)', '_', problem_str)

                    # Write the problem string to a file
                    problems_dir = f"../{BENCHMARK_DIR}/{PROB_DIR}/{domain}"
                    problem_file = f'{problems_dir}/{len(os.listdir(problems_dir))}_{domain}_prob.pddl'
                    with open(problem_file, 'w') as f:
                        f.write(problem_str.lower())

                    # Parse the problem in unified-planning
                    domain_file = f'../{BENCHMARK_DIR}/{DOMAINS_DIR}/{domain}.pddl'
                    problem = reader.parse_problem(domain_file, problem_file)

                    # Solve the problem
                    logging.debug("Computing a new plan...")
                    with contextlib.redirect_stdout(open(os.devnull, 'w')):
                        start_time = time.time()
                        with OneshotPlanner(
                                problem_kind=problem.kind,
                                **PLANNER_CFG
                        ) as planner:
                            result = planner.solve(problem, timeout=MAX_PLANNING_TIME)
                            plan = result.plan
                        planning_time = time.time() - start_time

                    if (plan is None) or len(plan.actions) < PLANS_MIN_LEN:
                        if plan is None:
                            logging.debug(f"Failed to generate a plan. Retrying...")
                        elif len(plan.actions) < PLANS_MIN_LEN:
                            logging.debug(f"Plan is not sufficiently long. Plan length is {len(plan.actions)}"
                                          f", minimum length is {PLANS_MIN_LEN}. Retrying...")
                        else:
                            raise Exception('Something went wrong during plan generation.')
                        plan = None
                        os.remove(problem_file)
                    else:
                        domain_problem = PDDLReader().parse_problem(f"../{BENCHMARK_DIR}/{DOMAINS_DIR}/{domain}.pddl")
                        parser = PDDLPlanParser(domain_problem, prefer_delta=True)
                        os.makedirs(f"../{BENCHMARK_DIR}/{SOLVE_TRAJ_DIR}/{domain}", exist_ok=True)
                        plan_file = f"../{BENCHMARK_DIR}/{SOLVE_TRAJ_DIR}/{domain}/{len(os.listdir(problems_dir))-1}_{domain}.trace"

                        with SequentialSimulator(problem) as simulator:
                            current_state = simulator.get_initial_state()
                            states = [current_state]
                            actions = []
                            executions = []
                            for action in plan.actions:
                                if not simulator.is_applicable(current_state, action):
                                    executions.append("inapplicable")
                                else:
                                    current_state = simulator.apply(current_state, action)
                                    executions.append("applicable")
                                states.append(current_state)
                                actions.append(action)
                        parser.write_trace_file(plan_file, states, actions, executions, problem.all_objects, {'planning_time': planning_time})

                bar()  # update progress bar

    logging.info(f'Total CPU time (s): {(datetime.now() - run_start).seconds}')
