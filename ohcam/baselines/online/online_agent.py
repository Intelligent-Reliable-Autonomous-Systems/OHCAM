import abc
import argparse
import json
import time

from pddl.core import Problem
from ohcam.dataset import ExperimentDataset
from unified_planning.model import UPState, Object as UPObject
from unified_planning.plans import ActionInstance
from ohcam.utils import agent_memory_mb, peak_memory_mb


class OnlineAgent(abc.ABC):

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    @abc.abstractmethod
    def reset_problem(self, problem: Problem):
        pass

    @abc.abstractmethod
    def get_action(self, state: UPState, objects: list[UPObject]) -> ActionInstance:
        pass

    @abc.abstractmethod
    def learn_step(self, state: UPState, objects: list[UPObject], action_instance: ActionInstance, next_state: UPState, status: str) -> bool:
        pass

    @abc.abstractmethod
    def get_learned_domain(self) -> Problem | None:
        pass

    def get_statistics(self) -> dict:
        return {}

def run_online_agent(dataset: ExperimentDataset, agent: OnlineAgent, problems: list[Problem], total_steps: int = -1, max_per_problem: int = 25, checkpoint_frequency: int = 10):
    env = dataset.get_environment(approach_to_log_data=agent.name)
    num_steps = 0

    max_steps = dataset.max_steps if total_steps == -1 else total_steps
    prob_idx = 0
    if max_per_problem == -1:
        # Allocate steps per problem. Deal with uneven same as other approaches
        steps_per_problem = [0]
        for j in range(max_steps):
            if j >= max_steps * (prob_idx + 1) / len(problems):
                prob_idx += 1
                steps_per_problem.append(0)
            steps_per_problem[prob_idx] += 1
    else:
        steps_per_problem = [max_per_problem] * len(problems)

    updated_steps = []
    planning_time = 0.0  # in get_action
    planning_calls = 0
    learning_time = 0.0  # in learn_step
    run_start = time.time()
    for i, problem in enumerate(problems):
        if num_steps >= max_steps:
            break
        print(f"[problem {i+1}/{len(problems)} | step {num_steps}/{max_steps}] Solving problem {problem.name}...")
        state, info = env.reset(problem)
        agent.reset_problem(problem)
        steps_in_current_problem = 0
        while steps_in_current_problem < steps_per_problem[prob_idx] and num_steps < max_steps:
            start = time.time()
            action = agent.get_action(state, info['objects'])
            planning_time += time.time() - start
            planning_calls += 1
            if action is None:
                break # Agent has decided it is done with this problem
            next_state, reward, term, trunc, info = env.step(action)
            print(f"Step {num_steps} selected action {action} with status {info['status']}")
            start = time.time()
            updated_model = agent.learn_step(state, info['objects'], action, next_state, info['status'])
            learning_time += time.time() - start
            if updated_model or (i > 0 and num_steps % checkpoint_frequency == 0):
                dpath = dataset.get_approach_domain_path(agent.name, agent.name, step=num_steps)
                learned_domain = agent.get_learned_domain()
                if learned_domain is not None:
                    dataset.get_pddl_writer(learned_domain).write_domain(str(dpath))
                    updated_steps.append(num_steps)
            state = next_state
            steps_in_current_problem += 1
            num_steps += 1
            if num_steps >= max_steps:
                break
            if term or trunc:
                state, info = env.reset(problem)
            else:
                state = next_state
    total_runtime = time.time() - run_start
    if updated_steps:
        print(f"Last updated problem index: {updated_steps[-1]}")
    best_up = agent.get_learned_domain()
    dpath = dataset.get_approach_domain_path(agent.name, agent.name)
    if best_up is not None:
        dataset.get_pddl_writer(best_up).write_domain(str(dpath))
    else:
        dataset.get_pddl_writer(dataset.initial_domain).write_domain(str(dpath))
    print(f"Ground truth domain at {dataset.gt_domain_file}")
    print(f"Saved {agent.name} model at {dpath}")
    print("Evaluate with")
    print(f"python -m ohcam.metrics.eval --config {dataset.experiment_config_path} --approach {agent.name} --data {agent.name}")

    statistics = {
        "num_steps": num_steps,
        "total_runtime": total_runtime,
        "total_learning_time": learning_time,
        "total_planning_time": planning_time,
        "avg_planning_time_per_step": planning_time / planning_calls if planning_calls else 0.0,
        "agent_memory_mb": agent_memory_mb(agent),
        **peak_memory_mb(),
        **agent.get_statistics(),
    }
    statistics_path = dataset.get_approach_dir(agent.name) / f"statistics-{agent.name}-{agent.name}.json"
    with open(statistics_path, "w") as f:
        json.dump(statistics, f, indent=4)

    step_log = dataset.get_approach_dir(agent.name) / f"updated_steps-{agent.name}-{agent.name}.txt"
    with open(step_log, "w") as f:
        for step in updated_steps:
            f.write(f"{step}\n")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--approach", type=str, required=True)
    parser.add_argument("--eval-problems", action="store_true", help="Evaluate the agent on the test problems")
    parser.add_argument("--num-steps", type=int, default=-1, help="Number of steps to run the agent for. If -1, use config max_steps.")
    parser.add_argument("--steps-per-problem", type=int, default=25, help="Number of steps to run the agent for each problem. If -1, use config max_steps.")
    parser.add_argument("--checkpoint-frequency", type=int, default=10, help="Frequency of checkpoints to save the agent.")
    parser.add_argument("--force", action="store_true", help="Force overwrite of existing approach domain path.")
    parser.add_argument("--trial-index", type=int, default=None,
        help="Trial index, used to pick the trial's data and seed the RNGs. Defaults to the config's trial_index.")
    args = parser.parse_args()
    dataset = ExperimentDataset(args.config, trial_index=args.trial_index)
    print(f"Seeding RNGs with trial index {dataset.seed_rngs()}")
    problems = dataset.get_problems(dataset.initial_domain_file, mode="train" if not args.eval_problems else "eval")
    approach_key = args.approach
    approach_type = dataset.get_approach_type(approach_key)
    if approach_type == "ohcam":
        from ohcam.baselines.online.ohcam_agent import OHCAMAgent
        agent = OHCAMAgent(dataset, approach_key=approach_key)
    elif approach_type == "olam":
        from ohcam.baselines.online.olam_agent import OlamAgent
        agent = OlamAgent(dataset, approach_key=approach_key)
    elif approach_type == "random":
        from ohcam.baselines.online.random_agent import RandomAgent
        agent = RandomAgent(dataset, approach_key=approach_key)
    elif approach_type == "glib":
        from ohcam.baselines.online.glib_agent import GlibAgent
        agent = GlibAgent(dataset, approach_key=approach_key)
    else:
        raise ValueError(f"Invalid approach: {approach_type}. Choose from: ohcam, olam, random, glib")
    if dataset.get_approach_domain_path(agent.name, agent.name).exists() and not args.force:
        print(f"Approach domain path already exists: {dataset.get_approach_domain_path(agent.name, agent.name)}")
        exit(0)
    run_online_agent(dataset, agent, problems, args.num_steps, args.steps_per_problem, args.checkpoint_frequency)