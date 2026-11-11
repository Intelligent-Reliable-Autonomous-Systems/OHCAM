import argparse
import json
import os
import socket
from pathlib import Path
import time
from typing import Any, Literal, Sequence
from ohcam.dataset import ExperimentDataset
from ohcam.planning import FDPlanner
from ohcam.up_utils import FluentExpLike, dict_state_to_up_state, initialize_problem_from_state, sample_action_from_state, up_state_to_dict
from ohcam.utils import get_state_delta
from tqdm import tqdm
from unified_planning.exceptions import UPInvalidActionError, UPValueError
from unified_planning.model import Problem, UPState
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import SequentialSimulator


def eval_approach_solving(approach_name: str, data_source: str, dataset: ExperimentDataset, num_iters: int = 10, timeout: int = 20, eval_problems: bool = False, step: int | None = None) -> dict[str, Any]:
    learned_domain_path = dataset.get_approach_domain_path(approach_name, data_source=data_source, step=step)

    print(f"Evaluating {approach_name} domain {learned_domain_path}")
    problems = dataset.get_problems(learned_domain_path, mode="eval" if eval_problems else "train")

    print(f"Number of problems: {len(problems)}, number of iters: {num_iters}, timeout: {timeout}")
    print("--------------------------------")
    env = dataset.get_environment(mode='eval')

    planner = FDPlanner()
    metrics = {
        "num-iters": num_iters,
        "num-problems": len(problems),
        "total-episodes": 0,
        "goal-reached": 0,
        "goal-not-reached": 0,
        "no-plan": 0,
        "inapplicable": 0,
        "horizon-exceeded": 0,
        "planning-times": [],
        "cum-reward": [],
        "step-count": [],
        "plan-len": [],
    }
    num_timeouts = 0
    for i in range(num_iters):
        for pidx, problem in enumerate(problems):
            print(f"[{i}/{num_iters}; {pidx}/{len(problems)}] Evaluating problem {problem.name}...", end="")
            start_time = time.time()
            env.reset(problem)
            metrics["total-episodes"] += 1
            plan = planner.plan(problem, timeout)
            print(f"plan: {plan}")
            expected_states = planner.get_plan_states(problem, plan)
            planning_time = time.time() - start_time
            metrics["planning-times"].append(planning_time)
            if plan is None:
                metrics["no-plan"] += 1
                num_timeouts += 1
                cum_reward = -1
                info = {'status': 'no-plan', 'step_count': 0}
                metrics["plan-len"].append(None)
            else:
                states, cum_reward, done, truncated, info = env.step_plan(plan, expected_states)
                if not done:
                    metrics["goal-not-reached"] += 1
                elif truncated:
                    metrics["horizon-exceeded"] += 1
                elif info["status"] == "inapplicable":
                    metrics["inapplicable"] += 1
                else:
                    metrics["goal-reached"] += 1
                metrics["cum-reward"].append(cum_reward)
                metrics["step-count"].append(info["step_count"])
                metrics["plan-len"].append(len(plan))
            print(f" {planning_time:.2f}s; {info['status']}; rew={cum_reward:.2f}; steps={info['step_count']}; avg={metrics['goal-reached'] / metrics['total-episodes']:.2f}")

    print(metrics)
    metrics["avg-step-count"] = sum(metrics['step-count']) / (len(metrics['step-count']) or 1)
    metrics["avg-cum-reward"] = sum(metrics['cum-reward']) / (len(metrics['cum-reward']) or 1)
    metrics["avg-goal-reached"] = metrics['goal-reached'] / metrics['total-episodes']
    metrics["avg-goal-not-reached"] = metrics['goal-not-reached'] / metrics['total-episodes']
    metrics["avg-no-plan"] = metrics['no-plan'] / metrics['total-episodes']
    metrics["avg-inapplicable"] = metrics['inapplicable'] / metrics['total-episodes']
    metrics["avg-horizon-exceeded"] = metrics['horizon-exceeded'] / metrics['total-episodes']
    metrics["avg-planning-time"] = sum(metrics['planning-times']) / (len(metrics['planning-times']) or 1)
    print(f"Average step count: {metrics['avg-step-count']}")
    print(f"Average cum reward: {metrics['avg-cum-reward']}")
    print(f"Average goal reached: {metrics['avg-goal-reached']}")
    print(f"Average goal not reached: {metrics['avg-goal-not-reached']}")
    print(f"Average no plan: {metrics['avg-no-plan']}")
    print(f"Average inapplicable: {metrics['avg-inapplicable']}")
    print(f"Average horizon exceeded: {metrics['avg-horizon-exceeded']}")
    print(f"Average planning time: {metrics['avg-planning-time']}")
    return metrics

def eval_predictive_effects(approach_name: str, data_source: str, dataset: ExperimentDataset, mode: Literal["train", "eval"] = "eval", step: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    learned_domain = dataset.get_learned_domain(approach_name, data_source=data_source, step=step)

    traces = list(dataset.get_traces(mode))
    total_transitions = sum(len(trace.states) - 1 for trace in traces)
    per_action_metrics = {}
    for action in dataset._gt_domain.actions:
        per_action_metrics[action.name] = {
            "raw_count": 0,
            "count": 0,
            "all_correct": 0,
            "true_pos_sum": 0,
            "false_pos_sum": 0,
            "true_neg_sum": 0,
            "false_neg_sum": 0,
            "precision_sum": 0,
            "recall_sum": 0
        }
    with tqdm(total=total_transitions, desc="Evaluating transitions") as pbar:
        for trace in traces:
            for state, action, next_state, execution in trace.get_transitions():
                pbar.update(1)
                if execution == "inapplicable":
                    continue
                per_action_metrics[action.action.name]["raw_count"] += 1
                learned_problem = initialize_problem_from_state(learned_domain, state, objects=trace.objects)
                learned_sim = SequentialSimulator(learned_problem)
                root_action_name = action.action.name
                try:
                    learned_action = learned_problem.action(root_action_name)
                except UPValueError:
                    continue # action is not in the learned model
                learned_action_instance = ActionInstance(learned_action,
                    [learned_problem.object(obj.object().name) for obj in action.actual_parameters[:len(learned_action.parameters)]])
                if not learned_sim.is_applicable(dict_state_to_up_state(state, learned_problem), learned_action_instance):
                    # Stern et al., 2025
                    # "we consider above only state-action pairs s and a where a is applicable in s in the environment
                    # and in the learned model. Otherwise, the outcome of applying a in s is not defined"
                    continue
                action_name = action.action.name

                state_set = set(state.items())
                per_action_metrics[action_name]["count"] += 1
                pred_next_state = up_state_to_dict(learned_sim.apply(dict_state_to_up_state(state, learned_domain), learned_action_instance), closed_world=True)
                pred_delta = set(get_state_delta(state, pred_next_state).items())
                pred_next_state_set = set(pred_next_state.items())
                gt_next_state = up_state_to_dict(next_state, closed_world=True)
                gt_delta = set(get_state_delta(state, gt_next_state).items())
                gt_next_state_set = set(gt_next_state.items())
                true_pos = pred_delta.intersection(gt_delta)
                false_pos = pred_delta.difference(gt_delta)
                true_neg = state_set.intersection(pred_next_state_set).intersection(gt_next_state_set)
                false_neg = pred_next_state_set.intersection(state_set).difference(gt_next_state_set)
                n_tp = len(true_pos)
                n_fp = len(false_pos)
                n_tn = len(true_neg)
                n_fn = len(false_neg)
                per_action_metrics[action_name]["true_pos_sum"] += n_tp
                per_action_metrics[action_name]["false_pos_sum"] += n_fp
                per_action_metrics[action_name]["true_neg_sum"] += n_tn
                per_action_metrics[action_name]["false_neg_sum"] += n_fn
                if n_tp + n_fp == 0:
                    recall = 0 # in accordance with Stern et al., 2025
                    precision = 1
                else:
                    precision = n_tp / (n_tp + n_fp)
                    if n_tp + n_fn == 0:
                        recall = 1
                    else:
                        recall = n_tp / (n_tp + n_fn)
                per_action_metrics[action_name]["precision_sum"] += precision
                per_action_metrics[action_name]["recall_sum"] += recall
                per_action_metrics[action_name]["all_correct"] += int(n_fp + n_fn == 0)

    for action_name, metrics in per_action_metrics.items():
        metrics["precision"] = metrics["precision_sum"] / metrics["count"] if metrics["count"] > 0 else 1
        metrics["recall"] = metrics["recall_sum"] / metrics["count"] if metrics["count"] > 0 else 0
        metrics["frac_correct"] = metrics["all_correct"] / metrics["count"] if metrics["count"] > 0 else int(metrics["raw_count"] == 0)

    total_count = sum(metrics["count"] for metrics in per_action_metrics.values())
    total_raw_count = sum(metrics["raw_count"] for metrics in per_action_metrics.values())
    averaged_metrics = {
        "precision": sum(metrics["precision"] for metrics in per_action_metrics.values()) / len(per_action_metrics),
        "recall": sum(metrics["recall"] for metrics in per_action_metrics.values()) / len(per_action_metrics),
        "frac_correct": sum(metrics["all_correct"] for metrics in per_action_metrics.values()) / total_count if total_count > 0 else int(total_raw_count == 0),
    }
    total_tp = sum(metrics["true_pos_sum"] for metrics in per_action_metrics.values())
    total_fp = sum(metrics["false_pos_sum"] for metrics in per_action_metrics.values())
    total_fn = sum(metrics["false_neg_sum"] for metrics in per_action_metrics.values())
    if total_tp + total_fp == 0:
        recall2 = 0
        precision2 = 1
    else:
        precision2 = total_tp / (total_tp + total_fp)
        if total_tp + total_fn == 0:
            recall2 = 1
        else:
            recall2 = total_tp / (total_tp + total_fn)
    averaged_metrics["precision2"] = precision2
    averaged_metrics["recall2"] = recall2

    print("Averaged metrics:", averaged_metrics)
    print("Per-action metrics:\n   ", "\n".join([f"{action_name}: {metrics}" for action_name, metrics in per_action_metrics.items()]))
    return averaged_metrics, per_action_metrics

def _action_instance_for_problem(action: ActionInstance, problem: Problem) -> ActionInstance | None:
    """Re-bind a grounded action to another problem, matching by name.

    Returns None if the problem has no action with this name. Extra parameters are
    dropped when the target action has a shorter signature (as in eval_predictive_effects).
    """
    try:
        target_action = problem.action(action.action.name)
    except UPValueError:
        return None
    try:
        params = [problem.object(obj.object().name)
                  for obj in action.actual_parameters[:len(target_action.parameters)]]
    except UPValueError:
        return None
    return ActionInstance(target_action, params)

def _is_applicable(simulator: SequentialSimulator, up_state: UPState, action: ActionInstance) -> bool:
    try:
        return bool(simulator.is_applicable(up_state, action))
    except (UPInvalidActionError, UPValueError):
        return False

def eval_predictive_applicability(approach_name: str, data_source: str, dataset: ExperimentDataset,
                                  mode: Literal["train", "eval"] = "eval", step: int | None = None,
                                  relax_terms_range: Sequence[int] = (1, 2, 3, 4, 5),
                                  samples_per_relaxation: int = 1,
                                  timeout: float = 60) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate how well the learned model predicts *applicability*.

    The dataset transitions are almost all applicable (a trace only rarely contains a
    failure), so they are interleaved with actions sampled from the same state via
    ``sample_action_from_state`` with ``relax_terms`` in ``relax_terms_range``: relaxing
    k ground-truth precondition terms yields near-misses that are usually inapplicable in
    the ground-truth domain. Ground truth applicability is decided by the ground-truth
    domain, the prediction by the learned domain; an action missing from the learned
    domain counts as predicted-inapplicable.
    """
    learned_domain = dataset.get_learned_domain(approach_name, data_source=data_source, step=step)
    gt_domain = dataset._gt_domain

    traces = list(dataset.get_traces(mode))
    total_transitions = sum(len(trace.states) - 1 for trace in traces)
    per_action_metrics = {}
    for action in gt_domain.actions:
        per_action_metrics[action.name] = {
            "count": 0,
            "dataset_count": 0,
            "sampled_count": 0,
            "missing_action": 0,
            "gt_applicable": 0,
            "true_pos": 0,   # applicable in gt and in the learned model
            "false_pos": 0,  # applicable in the learned model only (over-permissive precondition)
            "false_neg": 0,  # applicable in gt only (over-restrictive precondition)
            "true_neg": 0,
        }

    def score(action: ActionInstance, state: dict[FluentExpLike, bool], gt_problem: Problem,
              gt_sim: SequentialSimulator, learned_problem: Problem, learned_sim: SequentialSimulator,
              source: Literal["dataset", "sampled"]) -> None:
        action_name = action.action.name
        if action_name not in per_action_metrics:
            return
        metrics = per_action_metrics[action_name]
        gt_action = _action_instance_for_problem(action, gt_problem)
        if gt_action is None:
            return
        gt_applicable = _is_applicable(gt_sim, dict_state_to_up_state(state, gt_problem), gt_action)

        learned_action = _action_instance_for_problem(action, learned_problem)
        if learned_action is None:
            metrics["missing_action"] += 1
            pred_applicable = False
        else:
            pred_applicable = _is_applicable(learned_sim, dict_state_to_up_state(state, learned_problem), learned_action)

        metrics["count"] += 1
        metrics[f"{source}_count"] += 1
        metrics["gt_applicable"] += int(gt_applicable)
        if gt_applicable and pred_applicable:
            metrics["true_pos"] += 1
        elif pred_applicable:
            metrics["false_pos"] += 1
        elif gt_applicable:
            metrics["false_neg"] += 1
        else:
            metrics["true_neg"] += 1

    start_time = time.time()
    with tqdm(total=total_transitions, desc="Evaluating applicability") as pbar:
        for trace in traces:
            if time.time() - start_time > timeout:
                print(f"timeout after {timeout} seconds")
                break
            # objects are fixed within a trace, and applicability is evaluated on an explicit
            # state, so the problems only need to be built once per trace
            gt_problem = initialize_problem_from_state(gt_domain, trace.states[0], objects=trace.objects)
            learned_problem = initialize_problem_from_state(learned_domain, trace.states[0], objects=trace.objects)
            gt_sim = SequentialSimulator(gt_problem)
            learned_sim = SequentialSimulator(learned_problem)

            for state, action, _next_state, _execution in trace.get_transitions():
                if time.time() - start_time > timeout:
                    print(f"timeout after {timeout} seconds")
                    break
                pbar.update(1)
                score(action, state, gt_problem, gt_sim, learned_problem, learned_sim, "dataset")
                for relax_terms in relax_terms_range:
                    for _ in range(samples_per_relaxation):
                        sampled_action = sample_action_from_state(gt_problem, state, relax_terms=relax_terms)
                        if sampled_action is None or any(param is None for param in sampled_action.actual_parameters):
                            continue
                        score(sampled_action, state, gt_problem, gt_sim, learned_problem, learned_sim, "sampled")

    for metrics in per_action_metrics.values():
        metrics.update(_applicability_rates(metrics["true_pos"], metrics["false_pos"],
                                            metrics["true_neg"], metrics["false_neg"]))

    total_count = sum(metrics["count"] for metrics in per_action_metrics.values())
    scored_actions = [metrics for metrics in per_action_metrics.values() if metrics["count"] > 0] or list(per_action_metrics.values())
    averaged_metrics = {
        # macro averages over actions, so rare actions are not drowned out
        "app-precision": sum(metrics["precision"] for metrics in scored_actions) / len(scored_actions),
        "app-recall": sum(metrics["recall"] for metrics in scored_actions) / len(scored_actions),
        "app-accuracy": sum(metrics["accuracy"] for metrics in scored_actions) / len(scored_actions),
        "app-f1": sum(metrics["f1"] for metrics in scored_actions) / len(scored_actions),
        "app-count": total_count,
        "app-dataset-count": sum(metrics["dataset_count"] for metrics in per_action_metrics.values()),
        "app-sampled-count": sum(metrics["sampled_count"] for metrics in per_action_metrics.values()),
        "app-missing-action": sum(metrics["missing_action"] for metrics in per_action_metrics.values()),
    }
    # micro (transition-level) averages
    total_tp = sum(metrics["true_pos"] for metrics in per_action_metrics.values())
    total_fp = sum(metrics["false_pos"] for metrics in per_action_metrics.values())
    total_tn = sum(metrics["true_neg"] for metrics in per_action_metrics.values())
    total_fn = sum(metrics["false_neg"] for metrics in per_action_metrics.values())
    micro = _applicability_rates(total_tp, total_fp, total_tn, total_fn)
    averaged_metrics.update({f"app-{name}2": value for name, value in micro.items()})

    print("Averaged applicability metrics:", averaged_metrics)
    print("Per-action applicability metrics:\n   ", "\n".join([f"{action_name}: {metrics}" for action_name, metrics in per_action_metrics.items()]))
    return averaged_metrics, per_action_metrics

def _applicability_rates(n_tp: int, n_fp: int, n_tn: int, n_fn: int) -> dict[str, float]:
    """Precision/recall/accuracy for the applicability decision, guarding empty denominators."""
    count = n_tp + n_fp + n_tn + n_fn
    precision = n_tp / (n_tp + n_fp) if n_tp + n_fp > 0 else 1.0
    recall = n_tp / (n_tp + n_fn) if n_tp + n_fn > 0 else 1.0
    specificity = n_tn / (n_tn + n_fp) if n_tn + n_fp > 0 else 1.0
    return {
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "accuracy": (n_tp + n_tn) / count if count > 0 else 1.0,
        "balanced_accuracy": (recall + specificity) / 2,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0,
    }





if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--approach", type=str, required=True)
    parser.add_argument("--data", type=str, required=True)
    parser.add_argument("--step", type=int, default=None, help="If provided, evaluate the model at the given step.")
    parser.add_argument("--eval-problems", action=argparse.BooleanOptionalAction, default=True, help="Evaluate solving on the evaluation problems instead of the training problems.")
    parser.add_argument("--timeout", type=int, default=20, help="Planner time limit per problem, in seconds.")
    parser.add_argument("--epochs", type=int, default=1, help="Number of times to attempt each problem.")
    parser.add_argument("--force", action=argparse.BooleanOptionalAction, default=False, help="Re-evaluate even if a cached result exists.")
    args = parser.parse_args()
    dataset = ExperimentDataset(args.config)

    print("Evaluating approach", args.approach, "with data", args.data, "and step", args.step)

    approaches: list[str] = args.approach.split(",")
    for approach in approaches:
        approach = approach.strip()
        step = args.step
        if step is not None:
            # Fall back to the most recent existing step model at or below the requested step.
            while step > 0 and not dataset.get_approach_domain_path(approach, data_source=args.data, step=step).exists():
                step -= 1
            if step <= 0:
                print(f"No step model found for {approach} {args.data} at or below step {args.step}; skipping.")
                continue

        step_str = f"-step-{args.step:03d}" if args.step is not None else ""
        result_file = dataset.get_approach_dir(approach) / f"results-{approach}-{args.data}{step_str}.json"
        learned_domain_path = dataset.get_approach_domain_path(approach, data_source=args.data, step=step)
        cache_file = dataset.get_eval_cache_path(learned_domain_path)
        if cache_file.exists() and not args.force:
            result = json.loads(cache_file.read_text())
            print('Identical result found in cache, skipping evaluation (re-evaluate with --force)')
            print('Loading result from', cache_file)
        else:
            predictive_failed = False
            try:
                metrics_agg, metrics_per_action = eval_predictive_effects(approach, args.data, dataset, step=step)
            except Exception as e:
                print('error evaluating predictive effects', e)
                metrics_agg = {}
                metrics_per_action = {}
                predictive_failed = True
            try:
                app_metrics_agg, app_metrics_per_action = eval_predictive_applicability(approach, args.data, dataset, step=step)
            except Exception as e:
                print('error evaluating predictive applicability', e)
                app_metrics_agg = {}
                app_metrics_per_action = {}
                predictive_failed = True
            solving_metrics = eval_approach_solving(approach, args.data, dataset, args.epochs, args.timeout, args.eval_problems, step=step)
            result = {
                "solving": solving_metrics,
                "pred_app": {**app_metrics_agg, **app_metrics_per_action},
                "pred_eff": {**metrics_agg, **metrics_per_action}
            }
            if not predictive_failed:  # a failed evaluation must not be reused by later runs
                # Write and rename, so a parallel evaluation never reads a half-written entry
                tmp_file = cache_file.with_name(f"{cache_file.name}.{socket.gethostname()}.{os.getpid()}.tmp")
                tmp_file.write_text(json.dumps(result, indent=4))
                os.replace(tmp_file, cache_file)
        print('Writing result to', result_file)
        with open(result_file, "w") as f:
            json.dump(result, f, indent=4)
