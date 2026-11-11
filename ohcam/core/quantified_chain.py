from collections import defaultdict
import random
from dataclasses import dataclass
from functools import cmp_to_key
import heapq
import itertools
from typing import ClassVar, Iterator

from frozendict import frozendict
from ohcam.core.pddl_repr import Atom, GroundedAtom, Type, Condition, Outcome
from ohcam.core.pddl_utils import get_groundings, get_state_objects


@dataclass(frozen=True)
class QuantifiedChain:
    EMPTY_CHAIN_PENALTY: ClassVar[float] = 3.0 # penalty for empty chains

    literals: dict[Atom, bool]
    target: Atom
    uqvs: dict[str, Type]

    def __post_init__(self):
        if any(atom.is_grounded() for atom in self.literals.keys()):
            raise ValueError(f"QuantifiedChain cannot contain grounded atoms: {self.literals}")

    @property
    def cost(self) -> float:
        empty_penalty = QuantifiedChain.EMPTY_CHAIN_PENALTY if len(self.literals) == 0 else 0
        return 10*len(self.uqvs) + len(self.literals) + empty_penalty

    @property
    def is_null(self) -> bool:
        return len(self.uqvs) == 0

    def ground_all(self, action_vars_to_obj: dict[str, str], state: dict[GroundedAtom, bool], max: int = -1) -> list[dict[str, str]]:
        if max == -1:
            return list(self._ground_all(action_vars_to_obj, state))
        else:
            return list(itertools.islice(self._ground_all(action_vars_to_obj, state, shuffle=True), max))


    def ground_target(self, quantified_mapping: dict[str, str]) -> GroundedAtom:
        return self.target.ground(quantified_mapping)

    def ground_all_to_target(self, gpatom: GroundedAtom, param_mapping: dict[str, str], state: dict[GroundedAtom, bool]) -> list[dict[str, str]]:

        partial_quant_mapping = {**param_mapping}
        for param, obj in zip(self.target.params, gpatom.objects):
            if param in partial_quant_mapping and partial_quant_mapping[param] != obj:
                print(f"Grounding failed: {param} is already mapped to {partial_quant_mapping[param]}")
            partial_quant_mapping[param] = obj
        state_with_target = {**state, gpatom: state.get(gpatom, False)}
        return self.ground_all(partial_quant_mapping, state_with_target)

    def pprint(self, condition: Condition) -> str:
        if condition.outcome == Outcome.NO_EFFECT:
            return ""
        if self.is_null:
            outcome_str = "add" if condition.outcome == Outcome.ADD_EFFECT else "del"
            return f"{condition.antecedent} -> {outcome_str} {self.target}"
        quant_str = " ".join(f"{param} - {type_.name}" for param, type_ in self.uqvs.items())
        return f"∀ ({quant_str}) {condition.antecedent} -> {condition.outcome} {self.target}"

    def _free_vars(self) -> dict[str, Type]:
        uqvs = set([var for atom in [*self.literals, self.target] for var in atom.params])
        return {var: type_ for var, type_ in self.uqvs.items() if var not in uqvs}

    def _ground_all(self, action_vars_to_obj: dict[str, str], state: dict[GroundedAtom, bool], shuffle: bool = False) -> Iterator[dict[str, str]]:
        free_vars = self._free_vars()
        literal_order = list(self.literals.items()) + [(self.target, 'any'), (Atom("__FREE_VARS", list(free_vars.keys()), list(free_vars.values())), 'any')]
        by_predicate = defaultdict(list[tuple[str, ...]])
        for atom, val in state.items():
            if val:
                by_predicate[atom.name].append(atom.objects)
        all_objects = get_state_objects(state) # this assumes every object is represented in the state by some grounded atom. usually reasonable
        if shuffle:
            shuffled_items = list(all_objects.items())
            random.shuffle(shuffled_items)
            all_objects = dict(shuffled_items)

        def satisfy(idx: int, vars_to_obj: dict[str, str]) -> Iterator[dict[str, str]]:
            if idx == len(literal_order):
                yield vars_to_obj
                return
            atom, val = literal_order[idx]
            if val == 'any':
                # Variables already bound keep their object, even one no true atom of the state mentions (e.g. the
                # destination of a move that nothing is at yet), which all_objects leaves out
                choices = [[vars_to_obj[param]] if param in vars_to_obj else
                           [obj for obj, obj_type in all_objects.items() if type_.is_super_type(obj_type)]
                           for param, type_ in zip(atom.params, atom.types)]
                candidates = itertools.product(*choices)
            elif val == True:
                candidates = by_predicate[atom.name]
            elif val == False:
                candidates = list(set(get_groundings(atom.types, all_objects)) - set(by_predicate[atom.name]))
            for candidate in candidates:
                new_vars_to_obj = {**vars_to_obj}
                ok = True
                for obj, param, type_ in zip(candidate, atom.params, atom.types):
                    if all_objects.get(obj, None) and not type_.is_super_type(all_objects[obj]):
                        ok = False # object not of the correct type
                        break
                    if param in new_vars_to_obj and new_vars_to_obj[param] != obj:
                        ok = False # variable already bound to different object
                        break
                    existing_var = next((v for v, o in vars_to_obj.items() if o == obj and v != param), None)
                    if existing_var:
                        ok = False # object already bound to a variable
                        break
                    new_vars_to_obj[param] = obj
                if ok:
                    yield from satisfy(idx + 1, new_vars_to_obj)

        yield from satisfy(0, action_vars_to_obj)

    @classmethod
    def null(cls, target: Atom) -> 'QuantifiedChain':
        return cls(frozendict(), target, frozendict())


def get_object_graph(state: dict[GroundedAtom, bool]) -> dict[str, list[tuple[GroundedAtom, bool]]]:
    object_graph: dict[str, list[GroundedAtom]] = {}
    for atom, val in state.items():
        for reached_obj in atom.objects:
            if reached_obj not in object_graph:
                object_graph[reached_obj] = []
            object_graph[reached_obj].append((atom, val))
    return object_graph

def get_object_most_specific_types(object_graph: dict[str, list[tuple[GroundedAtom, bool]]]) -> dict[str, Type]:
    object_most_specific_types: dict[str, Type] = {}
    for obj, gatoms in object_graph.items():
        for gatom, val in gatoms:
            obj_idx = gatom.objects.index(obj)
            obj_type = gatom.types[obj_idx]
            if obj not in object_most_specific_types or object_most_specific_types[obj].is_super_type(obj_type):
                object_most_specific_types[obj] = obj_type
    return object_most_specific_types

def iter_param_chains(
        action_vars_to_obj: dict[str, str],
        object_graph: dict[str, list[tuple[GroundedAtom, bool]]],
        target_atom: GroundedAtom,
        action_params: dict[str, Type],
        max_vars: int = 2,
        chain_only: bool = True,
        allow_empty_chain: bool = False) -> Iterator[QuantifiedChain]:
    # get target variable patterns
    target_patterns = []
    for param, type_, obj, unbound in zip(target_atom.params, target_atom.types, target_atom.objects, target_atom._unbound_params):
        if not param.startswith("unidentified_"):
            continue
        target_patterns.append((type_, obj if not obj.startswith("unidentified_") else None, unbound))
    def compare_target_patterns(x: tuple[Type, str], y: tuple[Type, str]) -> int:
        if x[1]: # x is a grounded pattern
            return 1
        if y[1]: # y is a grounded pattern
            return -1
        return 1 if x[0].is_super_type(y[0]) else -1 # more specific type first
    target_patterns = sorted(target_patterns, key=cmp_to_key(compare_target_patterns))
    def satisfies_target(obj_to_var: dict[str, str], uqv_types: dict[str, Type]) -> list[str]:
        types_left = sorted(uqv_types.items(), key=lambda x: x[1]) # partial order most specific type first
        uqv_bind = {u:p for u, p in zip(target_atom._unbound_params, target_atom.params)}
        for type_, obj, unbound in target_patterns:
            if obj and obj not in obj_to_var:
                return None
            claimed = next(((v, t) for v, t in types_left if type_.is_super_type(t)), None)
            if not claimed:
                return None
            types_left.remove(claimed)
            uqv_bind[unbound] = claimed[0]
        args = [uqv_bind[u] for u in target_atom._unbound_params]
        return args

    obj_to_action_var = {v: k for k, v in action_vars_to_obj.items()}
    # search over sets of objects and expanded edges (grounded atoms)
    # return all valid chains that satisfy the target atom
    tiebreaker = itertools.count()
    init_search = (frozendict(obj_to_action_var), frozendict(), frozendict(), tuple(action_vars_to_obj.values()))
    pqueue: list[tuple[int, int, dict[str, str], dict[GroundedAtom, bool], dict[str, Type], tuple[str, ...]]] = []
    heapq.heappush(pqueue, (len(init_search[0]), next(tiebreaker), *init_search))
    visited = set()
    yielded = set()

    if allow_empty_chain:
        needed_types = {type_ for type_, param in zip(target_atom.types, target_atom.params) if param.startswith("unidentified_")}
        obj_types = get_object_most_specific_types(object_graph)
        for grounding in get_groundings(needed_types, {obj: type_ for obj, type_ in obj_types.items() if obj not in obj_to_action_var}):
            new_obj_to_var = {**obj_to_action_var}
            new_uqv_types = {}
            for obj in grounding:
                for i in itertools.count():
                    var = f"?uqv{i}"
                    if var not in new_obj_to_var.values():
                        new_obj_to_var[obj] = var
                        new_uqv_types[var] = obj_types[obj]
                        break
            heapq.heappush(pqueue, (len(new_obj_to_var) * QuantifiedChain.EMPTY_CHAIN_PENALTY, next(tiebreaker),
                frozendict(new_obj_to_var), frozendict(), frozendict(new_uqv_types), tuple()))


    while len(pqueue) > 0:
        _, _, obj_to_var, literals, uqv_types, prev_objs = heapq.heappop(pqueue)
        if (obj_to_var, literals) in visited:
            continue
        visited.add((obj_to_var, literals))
        if len(obj_to_var) > max_vars + len(action_vars_to_obj):
            continue

        target_args = satisfies_target(obj_to_var, uqv_types)
        if target_args:
            uqv_rename = {v: v for v in obj_to_var.values()}
            type_counts = defaultdict(int)
            for uqv, type_ in uqv_types.items():
                while True:
                    var = f"?uqv-{type_.name}-{type_counts[type_.name]}"
                    type_counts[type_.name] += 1
                    if var not in uqv_rename:
                        uqv_rename[uqv] = var
                        break
            no_target = {}
            for atom, val in literals.items():
                bound = atom.lift().bind({uqv_rename[v]: action_params.get(v, t) for v, t in zip(atom.params, atom.types)})
                no_target[bound] = val
            lifted_target = target_atom.lift().bind({uqv_rename.get(v, v): action_params.get(v, t) for v, t in zip(target_args, target_atom.types)})
            gtarget = lifted_target.ground({uqv_rename[obj_to_var[o]]:o for o in obj_to_var})
            if lifted_target in no_target and not any((gtarget, True) in edges for edges in object_graph.values()):
                no_target.pop(lifted_target) # the target is not grounded in the current state, so remove as a condition
            rename_uqv_types = {uqv_rename.get(v, v):t for v, t in uqv_types.items()}
            chain = QuantifiedChain(frozendict(no_target), lifted_target, frozendict(rename_uqv_types))
            if chain not in yielded:
                yielded.add(chain)
                yield chain

        for reached_obj in (prev_objs if chain_only else obj_to_var):
            for gatom, val in object_graph.get(reached_obj, []):
                # lift the atom
                bound_vars = []
                new_obj_to_var = {**obj_to_var}
                only_new_objs: list[str] = []
                for obj in gatom.objects:
                    if obj in obj_to_var:
                        bound_vars.append(obj_to_var[obj])
                    else:
                        # new obj not already bound
                        for i in itertools.count():
                            var = f"?uqv{i}"
                            if var not in new_obj_to_var.values():
                                new_obj_to_var[obj] = var
                                bound_vars.append(var)
                                only_new_objs.append(obj)
                                break
                if len(new_obj_to_var) == len(obj_to_var):
                    # no new object bound. skip
                    continue
                new_uqv_types = {**uqv_types}
                for obj_, type_ in zip(gatom.objects, gatom.types):
                    param = new_obj_to_var[obj_]
                    if param in action_vars_to_obj:
                        continue
                    if param not in new_uqv_types:
                        new_uqv_types[param] = type_
                    if new_uqv_types[param].is_super_type(type_):
                        new_uqv_types[param] = type_ # get the most specific type

                uqv_bound_gatom = gatom.bind(bound_vars)
                new_literals = {**literals, uqv_bound_gatom: val}

                heapq.heappush(pqueue, (len(new_obj_to_var), next(tiebreaker),
                    frozendict(new_obj_to_var), frozendict(new_literals),
                    frozendict(new_uqv_types), tuple(only_new_objs)))
