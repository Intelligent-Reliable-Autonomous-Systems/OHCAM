from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from typing import IO, Iterator
from unified_planning.exceptions import UPValueError
from unified_planning.model import Fluent, Object as UPObject, Problem, Type as UPType
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import FluentExp as get_fluent_exp

from ohcam.up_utils import FluentExpLike, up_state_to_dict


STATE_PREFIX = "(:state"
ACTION_PREFIX = "(:action"
DELTA_PREFIX = "(:delta"
OBSERVE_PREFIX = "(:observe"
OBJECTS_PREFIX = "(:objects"
META_PREFIX = "(:meta"
GOAL_REACHED_STR = "(:goal-reached)"
INAPPLICABLE_STR = "(:inapplicable)"

@dataclass
class Trace:
    states: list[dict[FluentExpLike, bool]]
    actions: list[ActionInstance]
    executions: list[str]
    objects: list[UPObject]
    meta: dict[str, str] | None = None

    def __post_init__(self):
        if len(self.states) != len(self.actions) + 1:
            raise ValueError("Number of states must be one more than the number of actions")
        if len(self.actions) != len(self.executions):
            raise ValueError("Number of actions must be equal to the number of executions")

    def __iter__(self) -> Iterator[object]:
        # Support tuple-style unpacking: states, actions, executions = trace
        yield self.states
        yield self.actions
        yield self.executions

    def get_transitions(self) -> Iterator[tuple[dict[FluentExpLike, bool], ActionInstance, dict[FluentExpLike, bool], str]]:
        for state, next_state, action, execution in zip(self.states[:-1], self.states[1:], self.actions, self.executions):
            yield state, action, next_state, execution



class PDDLPlanParser:

    def __init__(self, domain: Problem, prefer_delta: bool = False, trajectory_only: bool = False):
        self.domain: Problem = domain
        self.prefer_delta: bool = prefer_delta
        self._obj_name_to_obj: dict[str, UPObject] = {}
        self.last_meta: dict[str, str] = {}
        self._trace_prev_states: dict[Path, dict[FluentExpLike, bool]] = {}
        self.trajectory_only: bool = trajectory_only

    def parse_trace_file(self, trace_file: Path, with_meta: bool = False):
        with open(trace_file, "r") as f:
            return self._parse_plan(f.read(), with_meta=with_meta)

    def write_trace_file(self, plan_file: Path | IO[str], states: list[dict[FluentExpLike, bool]], actions: list[ActionInstance],
            executions: list[str] | None = None, objects: list[UPObject] | None = None, meta: dict[str, str] | None = None):
        states = [up_state_to_dict(state) for state in states]
        if executions is None:
            executions = []
        if meta is None:
            meta = {}
        if len(states) == 0:
            raise ValueError("Trace writing requires at least one initial state")
        self.initialize_trace_file(plan_file, states[0], object_types=objects, meta=meta)
        for action, next_state, execution in zip_longest(actions, states[1:], executions):
            if action is None:
                continue
            self.append_trace_step(plan_file, action, next_state, execution)
        self.close_trace_file(plan_file)

    @staticmethod
    def _trace_key(trace_file: Path | IO[str]) -> Path | IO[str]:
        return Path(trace_file) if isinstance(trace_file, (str, Path)) else trace_file

    @staticmethod
    @contextmanager
    def _open_trace(trace_file: Path | IO[str], mode: str):
        if isinstance(trace_file, (str, Path)):
            f = open(trace_file, mode)
            try:
                yield f
            finally:
                f.close()
        else:
            yield trace_file

    def initialize_trace_file(self, trace_file: Path | IO[str], initial_state: dict[FluentExpLike, bool],
            object_types: dict[str, set[str]] | list[UPObject] | None = None, meta: dict[str, str] | None = None) -> None:
        initial_state = up_state_to_dict(initial_state)
        if meta is None:
            meta = {}
        if object_types is None:
            object_types = self._collect_object_types([initial_state], [])
        elif isinstance(object_types, list):
            objects = object_types
            object_types = defaultdict(set)
            for obj in objects:
                object_types[obj.type.name].add(obj.name)
            object_types = dict(object_types)
        with self._open_trace(trace_file, "w") as f:
            if meta and not self.trajectory_only:
                meta_str = " ".join([f"({k} {v})" for k, v in meta.items()])
                f.write(f"{META_PREFIX} {meta_str})\n")
            if not self.trajectory_only:
                type_strs = [' '.join(names) + ' - ' + type for type, names in object_types.items()]
                f.write(f"{OBJECTS_PREFIX} {' '.join(type_strs)})\n")
            f.write(self._state_line(initial_state, prev_state=None) + "\n")
        self._trace_prev_states[self._trace_key(trace_file)] = initial_state

    def append_trace_step(self, trace_file: Path | IO[str], action: ActionInstance,
            next_state: dict[FluentExpLike, bool] | None = None, execution: str | None = None) -> None:
        trace_key = self._trace_key(trace_file)
        if trace_key not in self._trace_prev_states:
            raise ValueError(f"Trace stream not initialized for {trace_file}; call initialize_trace_file first")

        with self._open_trace(trace_file, "a") as f:
            action_str = f'({action.action.name} {" ".join([str(arg) for arg in action.actual_parameters])})'
            f.write(f"{ACTION_PREFIX} {action_str})\n")
            prev_state = self._trace_prev_states[trace_key]
            if next_state is not None:
                next_state = up_state_to_dict(next_state)
                f.write(self._state_line(next_state, prev_state=prev_state) + "\n")
                self._trace_prev_states[trace_key] = next_state

            if execution is not None and not self.trajectory_only:
                if execution == 'goal_reached':
                    f.write(f"{GOAL_REACHED_STR}\n")
                elif execution == 'inapplicable':
                    f.write(f"{INAPPLICABLE_STR}\n")

    def close_trace_file(self, trace_file: Path | IO[str]) -> None:
        self._trace_prev_states.pop(self._trace_key(trace_file), None)

    def _collect_object_types(self, states: list[dict[FluentExpLike, bool]], actions: list[ActionInstance]) -> dict[str, set[str]]:
        object_types: dict[str, set[str]] = defaultdict(set)
        for state in states:
            for pred in state.keys():
                for arg in pred.args:
                    obj = arg.object()
                    object_types[obj.type.name].add(obj.name)
        for action in actions:
            for arg in action.actual_parameters:
                obj = arg.object()
                object_types[obj.type.name].add(obj.name)
        return object_types

    def _state_line(self, state: dict[FluentExpLike, bool], prev_state: dict[FluentExpLike, bool] | None) -> str:
        if self.prefer_delta and prev_state is not None:
            assignments = {x: state[x] for x in state if x not in prev_state or state[x] != prev_state[x]}
            assignments.update({x: False for x in prev_state if x not in state})
            prefix = DELTA_PREFIX
        else:
            assignments = state
            prefix = STATE_PREFIX
        pred_strs = []
        for pred, value in assignments.items():
            pred_str = f'({pred.fluent().name} {" ".join([str(arg) for arg in pred.args])})'
            if not value:
                pred_str = f'(not {pred_str})'
            pred_strs.append(pred_str)
        return f"{prefix} {' '.join(pred_strs)})"

    def _parse_plan(self, plan_text: str, with_meta: bool = False):
        self._domain_instance = self.domain.clone()
        self._obj_name_to_obj = {}
        self.last_meta = {}

        cur_state = None
        step = 0
        states = []
        actions = []
        executions = []
        for line in plan_text.splitlines():
            line = line.strip()
            if line.startswith(";"):
                line = line[:line.index(";")]
            if len(line) == 0:
                continue

            if line.startswith(META_PREFIX):
                self.last_meta = self._parse_meta(line[len(META_PREFIX):-len(")")])
                continue
            if line.startswith(OBJECTS_PREFIX):
                self._parse_objects(line[len(OBJECTS_PREFIX):-len(")")])
                continue
            # A state uses closed world assumption; overrides all previous predicates, including not stated ones
            if line.startswith(STATE_PREFIX):
                cur_state = self._parse_predicates(line[len(STATE_PREFIX):-len(")")])
                while len(states) <= step:
                    # fill in the missing states with the previous state
                    if len(states) == 0:
                        states.append(None)
                    else:
                        states.append(states[-1])

                states[step] = cur_state
                continue

            # An observation can be a partial state, modifying a subset of the predicates
            if line.startswith(OBSERVE_PREFIX):
                cur_observation = self._parse_predicates(line[len(OBSERVE_PREFIX):-len(")")])
                if cur_state is None:
                    cur_state = {}
                next_state = {**cur_state, **cur_observation}
                while len(states) <= step:
                    # don't fill in the missing states; nothing was observed
                    states.append(None)
                states[step] = next_state
                cur_state = next_state

                continue

            # A delta specifies only the predicates that changed. It is a strict observation
            if line.startswith(DELTA_PREFIX):
                assignments = self._parse_predicates(line[len(DELTA_PREFIX):-len(")")])
                if cur_state is None:
                    raise ValueError("Full state or observation must be specified before deltas")
                next_state = {**cur_state, **assignments}
                while len(states) <= step:
                    # fill in the missing states with the previous state
                    if len(states) == 0:
                        states.append(None)
                    else:
                        states.append(states[-1])
                states[step] = next_state
                cur_state = next_state

                continue
            if line.startswith(ACTION_PREFIX):
                grounded_action = self._parse_action(line[len(ACTION_PREFIX):-len(")")])
                actions.append(grounded_action)
                step += 1
                continue
            if line.startswith(GOAL_REACHED_STR):
                while len(executions) < step:
                    executions.append('applicable')
                executions[step-1] = 'goal_reached'
                continue
            if line.startswith(INAPPLICABLE_STR):
                while len(executions) < step:
                    executions.append('applicable')
                executions[step-1] = 'inapplicable'
                continue

        while len(executions) < len(actions):
            executions.append('applicable')
        trace = Trace(
            states=states,
            actions=actions,
            executions=executions,
            objects=list(self._obj_name_to_obj.values()),
            meta=self.last_meta,
        )
        return trace

    def _parse_meta(self, meta_text: str) -> dict[str, str]:
        meta: dict[str, str] = {}
        text = meta_text.strip()
        while text:
            if not text.startswith("("):
                break
            depth = 0
            close_idx = None
            for i, ch in enumerate(text):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        close_idx = i
                        break
            if close_idx is None:
                raise ValueError(f"Malformed meta line: {meta_text}")
            pair = text[1:close_idx].strip()
            if not pair:
                text = text[close_idx + 1:].strip()
                continue
            key, _, value = pair.partition(" ")
            key = key.strip()
            value = value.strip()
            if len(key) == 0:
                raise ValueError(f"Malformed meta key in: {meta_text}")
            meta[key] = value
            text = text[close_idx + 1:].strip()
        return meta

    def _parse_predicates(self, state_text: str):
        text = state_text.strip()
        predicates: dict[FluentExpLike, bool] = {}
        while len(text) > 0:
            if not text.startswith("("):
                break
            predicate, is_positive, remainder = self._parse_predicate(text)
            predicates[predicate] = is_positive
            text = remainder.strip()
        return predicates

    def _parse_action(self, action_text: str):
        """
        Parse a grounded PDDL action string, e.g. "(move robot loc1 loc2)", into an action instance.
        """
        action_text = action_text.strip()
        if not (action_text.startswith("(") and action_text.endswith(")")):
            raise ValueError(f"Invalid action: {action_text!r}")

        tokens = action_text[1:-1].split()
        if not tokens:
            raise ValueError("Empty action")

        action = next((a for a in self.domain.actions if a.name == tokens[0]), None)
        if action is None:
            raise ValueError(f"No action found for {tokens[0]}")

        objects = [self._match_object(token, param.type) for token, param in zip(tokens[1:], action.parameters)]
        action_instance = ActionInstance(action, objects)
        return action_instance

    def _parse_predicate(self, predicate: str) -> tuple[FluentExpLike, bool, str]:
        """
        Parse the first PDDL predicate in a string, handling negation.

        Returns:
            (fluent expression, is_positive, the rest of the string)
        """
        s = predicate.strip()
        if not s.startswith("("):
            raise ValueError(f"Expected '(' at start of: {s!r}")

        def find_matching_close(s: str, open_pos: int) -> int:
            """Return index of the closing paren matching the one at open_pos."""
            depth = 0
            for i in range(open_pos, len(s)):
                if s[i] == "(":
                    depth += 1
                elif s[i] == ")":
                    depth -= 1
                    if depth == 0:
                        return i
            raise ValueError(f"Unmatched '(' in: {s!r}")

        close = find_matching_close(s, 0)
        remainder = s[close + 1:]
        inner = s[1:close].strip()

        if inner.startswith("not"):
            rest = inner[3:].strip()
            if not rest.startswith("("):
                raise ValueError(f"Expected predicate inside (not ...): {predicate!r}")
            inner_close = find_matching_close(rest, 0)
            inner = rest[1:inner_close].strip()
            positive = False
        else:
            positive = True

        tokens = inner.split()
        if not tokens:
            raise ValueError("Empty predicate")

        try:
            matched_fluent: Fluent = self.domain.fluent(tokens[0])
            if matched_fluent.arity != len(tokens[1:]):
                raise ValueError
        except ValueError:
            raise ValueError(f"No fluent found for {tokens[0]} with signature {tokens[1:]}")
        objects = [self._match_object(token, param.type) for token, param in zip(tokens[1:], matched_fluent.signature)]
        fluent_exp: FluentExpLike = get_fluent_exp(matched_fluent, objects)

        return fluent_exp, positive, remainder

    def _parse_objects(self, objects_text: str):
        """
        Parse a PDDL typed list string into a dict mapping names to types.

        Examples:
            "obj1 obj2 - mytype1 obj3 - mytype2"
            -> {'obj1': 'mytype1', 'obj2': 'mytype1', 'obj3': 'mytype2'}
        """
        result = {}
        tokens = objects_text.split()
        current_names = []

        i = 0
        while i < len(tokens):
            if tokens[i] == "-":
                type_name = tokens[i + 1]
                for name in current_names:
                    result[name] = type_name
                current_names = []
                i += 2
            else:
                current_names.append(tokens[i])
                i += 1

        for name in current_names:
            result[name] = 'object'

        for name, type_name in result.items():
            up_type = self._domain_instance.user_type(type_name)
            self._match_object(name, up_type)

    def _match_object(self, token: str, type: UPType) -> UPObject:
        if token in self._obj_name_to_obj:
            return self._obj_name_to_obj[token]
        try:
            obj = self._domain_instance.object(token)
        except UPValueError:
            obj = UPObject(token, type)
        self._obj_name_to_obj[token] = obj
        return obj
