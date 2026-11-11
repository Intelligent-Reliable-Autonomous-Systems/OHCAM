import gc
import resource
import sys
import types

from unified_planning.shortcuts import FluentExp


def peak_memory_mb() -> dict[str, float]:
    """Peak resident memory, in MB, of this process and of its finished child processes (e.g. Alchemy, the
    planner); Linux reports ru_maxrss in KB."""
    return {
        "peak_memory_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "peak_child_memory_mb": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024,
    }


def deep_size_mb(obj, exclude: tuple[type, ...] = ()) -> float:
    """Memory, in MB, of every object reachable from ``obj``, counting shared objects once. Modules, classes,
    functions and instances of ``exclude`` (e.g. the dataset the agent was given) aren't counted or followed."""
    skip = (type, types.ModuleType, types.FunctionType, types.BuiltinFunctionType, types.MethodType) + exclude
    seen = set()
    size = 0
    pending = [obj]
    while pending:
        objects = []
        for o in pending:
            if id(o) in seen or isinstance(o, skip):
                continue
            seen.add(id(o))
            size += sys.getsizeof(o)
            objects.append(o)
        pending = gc.get_referents(*objects)
    return size / 2**20


def agent_memory_mb(agent) -> float:
    """Memory of an agent's own state (its learned model and data), not of the dataset or UP environment it uses."""
    from unified_planning.environment import Environment
    from ohcam.dataset import ExperimentDataset
    return deep_size_mb(agent, exclude=(ExperimentDataset, Environment))























def get_state_delta(previous_state: dict[FluentExp, bool], current_state: dict[FluentExp, bool]) -> dict[FluentExp, bool]:
    delta = {}
    for fluent, value in current_state.items():
        if fluent not in previous_state:
            if value:
                delta[fluent] = True
        elif previous_state[fluent] != value:
            delta[fluent] = value
    for fluent, value in previous_state.items():
        if fluent not in current_state:
            delta[fluent] = False
    return delta
