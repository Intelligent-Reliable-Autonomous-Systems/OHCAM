import abc
import argparse
import json
import signal
import sys
import time

from ohcam.dataset import ExperimentDataset, corrupt_traces_with_noise
from unified_planning.model import Problem

from ohcam.trace import Trace
from ohcam.utils import agent_memory_mb, peak_memory_mb


class TimeBudgetExceeded(BaseException):
    """Raised in the main thread when the offline learning time budget elapses.

    Subclasses ``BaseException`` (not ``Exception``) so it propagates cleanly
    through library ``except Exception`` blocks - e.g. pracmln's multi-core
    learner, whose ``finally`` still tears the worker pool down - straight up to
    the runner, which then recovers the best model learned so far.
    """


def _raise_time_budget(signum, frame):
    raise TimeBudgetExceeded()


class OfflineAgent(abc.ABC):

    relearns_from_scratch: bool = False
    """Whether each ``learn_offline`` call re-learns from all the traces seen so far. The runner then learns each
    checkpoint with a fresh agent on the traces up to it, in ``checkpoint_order``, since checkpoints don't depend
    on each other."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    @abc.abstractmethod
    def learn_offline(self, traces: list[Trace]) -> None:
        pass

    @abc.abstractmethod
    def get_learned_domain(self) -> Problem:
        pass

    def get_statistics(self) -> dict:
        return {}

def split_into_checkpoints(traces: list[Trace], checkpoint_freq: int, max_steps: int) -> list[tuple[int, list[Trace]]]:
    """Split traces into consecutive chunks of ``checkpoint_freq`` steps, up to ``max_steps``, splitting a trace that
    crosses a checkpoint. Returns (steps after the chunk, the chunk's traces) for each chunk."""
    traces = list(traces)
    chunks = []
    total_steps = 0
    while len(traces) > 0 and total_steps < max_steps:
        # First, collect all traces up to the checkpoint
        ctraces = []
        steps_to_collect = min(checkpoint_freq, max_steps - total_steps)
        while len(traces) > 0 and sum(len(p.actions) for p in ctraces) < steps_to_collect:
            ctraces.append(traces.pop(0))
        # Then, truncate the last trace at the checkpoint
        last = ctraces.pop()
        nactions = steps_to_collect - sum(len(p.actions) for p in ctraces)
        new_last = Trace(last.states[:nactions+1], last.actions[:nactions], last.executions[:nactions], last.objects, last.meta)
        ctraces.append(new_last)
        if len(last.actions) > nactions:
            remaining = Trace(last.states[nactions:], last.actions[nactions:], last.executions[nactions:], last.objects, last.meta)
            traces.insert(0, remaining)
        total_steps += sum(len(p.actions) for p in ctraces)
        chunks.append((total_steps, ctraces))
    return chunks


def checkpoint_order(steps: list[int]) -> list[int]:
    """Coarse to fine: the last checkpoint, then a 1-2-5 series below it, then repeatedly the checkpoint nearest the
    middle of the widest gap left. Every ten steps up to 100 gives 100, 50, 20, 10, 70, 30, 80, 40, 60, 90."""
    remaining = sorted(set(steps))
    if not remaining:
        return []

    def nearest(target: float, candidates: list[int]) -> int:
        return min(candidates, key=lambda step: (abs(step - target), step))

    smallest = remaining[0]
    order = [remaining.pop()]
    top = order[0]
    factor = 2
    while remaining and top / factor >= smallest / 2:
        step = nearest(top / factor, remaining + order)
        if step not in order:
            remaining.remove(step)
            order.append(step)
        # 2, 5, 10, 20, 50, ...
        factor = factor * 5 // 2 if str(factor)[0] == '2' else factor * 2
    while remaining:
        bounds = [0] + sorted(order)
        gaps = [(low, high) for low, high in zip(bounds, bounds[1:]) if any(low < step < high for step in remaining)]
        low, high = max(gaps, key=lambda gap: (gap[1] - gap[0], -gap[0]))
        step = nearest((low + high) / 2, [step for step in remaining if low < step < high])
        remaining.remove(step)
        order.append(step)
    return order


def learn_checkpoints_incremental(agent, chunks, dataset, approach_key, data, per_checkpoint_time):
    """Feed the agent one chunk after another and save a checkpoint after each. If the time budget runs out, the
    model recovered at that point is saved as the checkpoint and learning stops. ``per_checkpoint_time`` re-arms the
    budget for each chunk; without it, the runner's single alarm covers them all."""
    for total_steps, ctraces in chunks:
        if per_checkpoint_time is not None:
            signal.alarm(int(per_checkpoint_time))  # fresh budget for this checkpoint
        interrupted = False
        try:
            print(f'learning {total_steps - sum(len(p.actions) for p in ctraces)} steps')
            agent.learn_offline(ctraces)
        except TimeBudgetExceeded:
            # Later checkpoints build on this one, so stop
            interrupted = True
        finally:
            if per_checkpoint_time is not None:
                signal.alarm(0)  # pause the clock until the next checkpoint
        learned_domain = agent.get_learned_domain()
        learned_domain_path_step = dataset.get_approach_domain_path(approach_key, data, step=total_steps)
        dataset.get_pddl_writer(learned_domain).write_domain(str(learned_domain_path_step))
        print(f"Learned domain: {learned_domain} at step {total_steps}")
        if interrupted:
            raise TimeBudgetExceeded()


def learn_checkpoints_batch(create_agent, chunks, dataset, approach_key, data, per_checkpoint_time):
    """Learn each checkpoint with a fresh agent on all the traces up to it, in ``checkpoint_order``. A checkpoint
    that runs out of time isn't saved. With ``per_checkpoint_time`` each checkpoint gets its own budget and the
    others are still learned; without it, the runner's single alarm stops learning. Returns the agent of the latest
    saved checkpoint, for the final model, or None if none was saved, and whether the single alarm stopped learning."""
    prefixes = {}
    so_far = []
    for total_steps, ctraces in chunks:
        so_far = so_far + ctraces
        prefixes[total_steps] = so_far
    order = checkpoint_order(list(prefixes))
    print(f"Learning checkpoints in batch mode, in the order {order}")
    best_step, best_agent = None, None
    for step in order:
        if per_checkpoint_time is not None:
            signal.alarm(int(per_checkpoint_time))  # fresh budget for this checkpoint
        agent = create_agent()
        try:
            print(f'learning {step} steps')
            agent.learn_offline(prefixes[step])
        except TimeBudgetExceeded:
            if per_checkpoint_time is None:
                print(f"Time budget exceeded at step {step}; not saving this checkpoint or learning the rest")
                return best_agent, True
            print(f"Time budget ({per_checkpoint_time}s) exceeded at step {step}; not saving this checkpoint")
            continue
        finally:
            if per_checkpoint_time is not None:
                signal.alarm(0)
        learned_domain = agent.get_learned_domain()
        learned_domain_path_step = dataset.get_approach_domain_path(approach_key, data, step=step)
        dataset.get_pddl_writer(learned_domain).write_domain(str(learned_domain_path_step))
        print(f"Learned domain: {learned_domain} at step {step}")
        if best_step is None or step > best_step:
            best_step, best_agent = step, agent
    return best_agent, False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--approach", type=str, required=True)
    parser.add_argument("--data", type=str, required=True)
    parser.add_argument("--checkpoint-freq", type=int, default=None, help="Steps to break up data.")
    parser.add_argument("--max-steps", type=int, default=None, help="Maximum number of steps to learn for. If None, use all traces.")
    parser.add_argument("--seed", type=int, default=42,
        help="RNG seed for corrupting expert traces with obs_noise (default: 42).")
    parser.add_argument("--force", action="store_true", help="Force overwrite of existing approach domain path.")
    parser.add_argument("--max-time", type=int, default=None,
        help="Wall-clock budget (seconds) for offline learning. When it elapses, "
             "learning is interrupted and the best model learned so far is written. "
             "Defaults to the approach's 'max_time' config, else 3600 (1 hour).")
    parser.add_argument("--trial-index", type=int, default=None,
        help="Trial index, used to pick the trial's data and seed the RNGs. Defaults to the config's trial_index.")
    args = parser.parse_args()
    dataset = ExperimentDataset(args.config, trial_index=args.trial_index)
    print(f"Seeding RNGs with trial index {dataset.seed_rngs()}")
    approach_key = args.approach
    approach_type = dataset.get_approach_type(approach_key)
    learned_domain_path = dataset.get_approach_domain_path(approach_key, args.data)
    if learned_domain_path.exists() and not args.force:
        print(f"Learned domain path already exists: {learned_domain_path}")
        exit(0)
    traces = list(dataset.get_traces(args.data))
    if sum(len(p.actions) for p in traces) == 0:
        raise ValueError("No traces found")
    if args.data in ("train", "eval"):  # expert traces from files; online approaches' traces are already noisy
        obs_noise = dataset.get_obs_noise(approach_key)
        print(f"Corrupting expert traces with obs_noise={obs_noise} (seed={args.seed})")
        corrupt_traces_with_noise(traces, obs_noise, seed=args.seed)
    def create_agent() -> "OfflineAgent":
        if approach_type == "ohcam":
            from ohcam.baselines.online.ohcam_agent import OHCAMAgent
            agent = OHCAMAgent(dataset, approach_key=approach_key, offline=True)
        elif approach_type == "conditional-sam":
            from ohcam.baselines.offline.conditional_sam import ConditionalSAMAgent
            agent = ConditionalSAMAgent(dataset, args.data, approach_key=approach_key)
        elif approach_type == "predicators":
            from ohcam.baselines.offline.predicators_agent import PredicatorsAgent
            agent = PredicatorsAgent(dataset, args.data, approach_key=approach_key)
        elif approach_type == "lamp":
            from ohcam.baselines.offline.lamp.lamp_agent import LAMPAgent
            agent = LAMPAgent(dataset, args.data, approach_key=approach_key)
        elif approach_type == "lamp2":
            from ohcam.baselines.offline.lamp.lamp2_agent import LAMP2Agent
            agent = LAMP2Agent(dataset, args.data, approach_key=approach_key)
        else:
            raise ValueError(f"Invalid approach: {approach_type}. Choose from: ohcam, conditional-sam, predicators, lamp, lamp2")
        return agent

    agent = create_agent()
    # Resolve the learning time budget and arm a wall-clock interrupt. When it
    # fires, TimeBudgetExceeded unwinds whatever learning is in progress and we
    # fall through to write the best model recovered so far.
    #
    # ``per_checkpoint_time`` re-arms the budget at the start of every checkpoint
    # instead of running a single cumulative alarm. This suits non-online
    # methods (e.g. LAMP), where each checkpoint re-learns from scratch over all
    # data so far and later checkpoints cost more: each learning call then gets
    # its own ``max_time``, and the first one that overruns stops learning with
    # the last completed checkpoint recovered.
    approach_cfg = dataset.get_approach_cfg(approach_key)
    max_time = args.max_time
    if max_time is None:
        max_time = approach_cfg.get("max_time", 3600)
    per_checkpoint_time = approach_cfg.get("per_checkpoint_time", False)
    arm_budget = bool(max_time and max_time > 0)
    per_checkpoint = per_checkpoint_time and args.checkpoint_freq is not None
    interrupted = False
    learning_start = time.time()
    if arm_budget:
        signal.signal(signal.SIGALRM, _raise_time_budget)
        if not per_checkpoint:
            signal.alarm(int(max_time))  # single cumulative budget
    try:
        if args.checkpoint_freq is not None:
            if args.checkpoint_freq <= 0:
                raise ValueError("checkpoint_freq cannot be less than or equal to 0")
            if args.max_steps is None:
                args.max_steps = 100000
            chunks = split_into_checkpoints(traces, args.checkpoint_freq, args.max_steps)
            if getattr(agent, "relearns_from_scratch", False):  # OHCAMAgent is an OnlineAgent
                agent, interrupted = learn_checkpoints_batch(create_agent, chunks, dataset, approach_key, args.data,
                                                             max_time if arm_budget and per_checkpoint else None)
            else:
                learn_checkpoints_incremental(agent, chunks, dataset, approach_key, args.data,
                                              max_time if arm_budget and per_checkpoint else None)
        else:
            # Truncate traces to max_steps
            if args.max_steps is None:
                args.max_steps = 100000
            ctraces = []
            while len(traces) > 0 and sum(len(p.actions) for p in ctraces) < args.max_steps:
                trace = traces.pop(0)
                ctraces.append(trace)
            last = ctraces.pop()
            nactions = args.max_steps - sum(len(p.actions) for p in ctraces)
            new_last = Trace(last.states[:nactions+1], last.actions[:nactions], last.executions[:nactions], last.objects, last.meta)
            ctraces.append(new_last)
            if len(traces) > 0:
                remaining = traces.pop(0)
                nactions = args.max_steps - sum(len(p.actions) for p in ctraces)
                new_last = Trace(remaining.states[:nactions+1], remaining.actions[:nactions], remaining.executions[:nactions], remaining.objects, remaining.meta)
                ctraces.append(new_last)
            # learn
            agent.learn_offline(ctraces)
    except TimeBudgetExceeded:
        interrupted = True
        scope = "per-checkpoint" if per_checkpoint else "total"
        print(f"Time budget ({max_time}s {scope}) exceeded; recovering best model learned so far.")
    finally:
        signal.alarm(0)
    # Every checkpoint's learning, including batch mode's re-learning from scratch, and writing the checkpoints
    total_learning_time = time.time() - learning_start

    if agent is None:
        # Batch mode, and no checkpoint finished within its budget
        print("No learned domain found: no checkpoint finished learning within its time budget")
        (dataset.get_approach_dir(approach_key) / f'NO_LEARNED_DOMAIN_{args.data}').touch()
        sys.exit(0)

    try:
        learned_domain = agent.get_learned_domain()
        if learned_domain is None:
            print("No learned domain found")
            (dataset.get_approach_dir(approach_key) / f'NO_LEARNED_DOMAIN_{args.data}').touch()
            sys.exit(0)
        dataset.get_pddl_writer(learned_domain).write_domain(str(learned_domain_path))
        print(f"Learned domain{' (partial, interrupted)' if interrupted else ''}: {learned_domain}")
        statistics = {
            "total_learning_time": total_learning_time,
            "agent_memory_mb": agent_memory_mb(agent),
            **peak_memory_mb(),
            **agent.get_statistics(),
        }
        statistics_path = dataset.get_approach_dir(approach_key) / f"statistics-{agent.name}-{args.data}.json"
        with open(statistics_path, "w") as f:
            json.dump(statistics, f, indent=4)
        print(f"Ground truth domain at {dataset.gt_domain_file}")
        print(f"Saved {approach_key} model at {learned_domain_path}")
        print("Evaluate with")
        print(f"python -m ohcam.metrics.eval --config {dataset.experiment_config_path} --approach {approach_key} --data {args.data}")
    except Exception as e:
        print(f"Could not recover a learned domain: {e}")
        if not interrupted:
            raise