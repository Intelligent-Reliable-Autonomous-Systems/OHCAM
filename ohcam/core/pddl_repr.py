"""The basic data structures for PDDL modeling"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import itertools
from typing_extensions import override
from frozendict import frozendict


class Outcome(StrEnum):
    """The outcome of a precondition or effect clause."""
    APPLICABLE = "applicable"
    NO_EFFECT = "no_effect"
    ADD_EFFECT = "add_effect"
    DEL_EFFECT = "del_effect"

@dataclass(frozen=True)
class Type:
    name: str
    parent: 'Type | None'

    def __getitem__(self, index: int) -> 'str | Type | None':
        if index == 0:
            return self.name
        elif index == 1:
            return self.parent
        else:
            raise IndexError(f"Index out of range: {index}")

    def __repr__(self):
        return f"Type({self.name}, {self.parent})"

    def __str__(self):
        return self.name

    def is_super_type(self, other: 'Type') -> bool:
        """Check if this type is a super type of another type."""
        if other.parent is None:
            return self.name == other.name
        while other is not None:
            if self.name == other.name:
                return True
            other = other.parent
        return False

    def __lt__(self, other: 'Type') -> bool:
        return other.is_super_type(self)

    def __gt__(self, other: 'Type') -> bool:
        return self.is_super_type(other)

    def __hash__(self) -> int:
        return hash((self.name, self.parent))

@dataclass(frozen=True)
class Atom:
    """An atom is a predicate with a tuple of arguments."""
    name: str
    params: tuple[str, ...]
    types: tuple[Type, ...]
    _unbound_params: tuple[str, ...] | None = field(default=None, repr=False)

    def __post_init__(self):
        if self._unbound_params is None:
            object.__setattr__(self, '_unbound_params', self.params)

    def __repr__(self):
        signature = ' '.join(f"{arg} - {type.name}" for arg, type in zip(self.params, self.types))
        return f"Atom({self.name}, {signature})"

    def __str__(self):
        return repr(self)

    def __getitem__(self, index: int) -> str:
        if index == 0:
            return self.name
        if index > len(self.params):
            raise IndexError(f"Index out of range: {index}")
        return self.params[index-1]

    def bind(self, variables: dict[str, Type] | Sequence[str]) -> 'Atom':
        """Bind the parameters to a new set of variables.

        This is used to bind the parameters of an action to a predicate.
        Can also replace the types for type specialization.

        Args:
            variables: If a dict, the keys are the new parameters and the values are the new types.
                If a sequence, the new parameters are the sequence and the types are the same.
        """
        unbound = self.params if self._unbound_params is None else self._unbound_params
        if isinstance(variables, dict):
            return Atom(self.name,
                tuple(variables.keys()),
                tuple(variables.values()),
                unbound)
        else:
            if len(variables) != len(self.params):
                raise ValueError(f"{str(self)}: Wrong number of bindings: {len(variables)} != {len(self.params)}")
            return Atom(self.name, tuple(variables), self.types, unbound)

    def bind_partial(self, variables: dict[str, str]) -> 'Atom':
        """Bind the parameters to a new set of variables, with some parameters being unidentified.

        Any parameters that are not in the dictionary are marked as 'unidentified_'.

        Args:
            variables: A dict mapping old parameters to new parameters.
        """
        unbound = self.params if self._unbound_params is None else self._unbound_params
        counter = itertools.count()
        bound = tuple((variables.get(param, None) or f"unidentified_{next(counter)}") for param in self.params)
        return Atom(self.name, tuple(bound), self.types, unbound)

    def unbind(self) -> 'Atom':
        return Atom(self.name, self._unbound_params, self.types)

    def ground(self, objects: dict[str, str] | Sequence[str]) -> 'GroundedAtom':
        if isinstance(objects, dict):
            for arg in self.params:
                if arg not in objects and not arg.startswith("unidentified_"):
                    raise ValueError(f"{str(self)}: No binding for variable: {arg} in {objects}")
            return GroundedAtom(self.name, self.params, self.types, objects=tuple(objects.get(param, param) for param in self.params), _unbound_params=self._unbound_params)
        else:
            if len(objects) != len(self.params):
                raise ValueError(f"{str(self)}: Wrong number of bindings: {len(objects)} != {len(self.params)}")
            return GroundedAtom(self.name, self.params, self.types, objects=tuple(objects), _unbound_params=self._unbound_params)

    def is_grounded(self) -> bool:
        return False

    def is_identified(self) -> bool:
        return not any(param.startswith("unidentified_") for param in self.params)

    def submatches(self, other: 'Atom') -> bool:
        """If this atom is equivalent to another atom, and the types are descendants of other's types."""
        if self.name != other.name or self.params != other.params:
            return False
        for self_t, other_t in zip(self.types, other.types):
            if not other_t.is_super_type(self_t):
                return False
        return True

@dataclass(frozen=True, init=False)
class GroundedAtom(Atom):
    """A grounded atom is an atom with all arguments bound to objects."""

    objects: tuple[str, ...] = None

    def __init__(self, name: str, params: tuple[str, ...], types: tuple[Type, ...], objects: tuple[str, ...], _unbound_params: tuple[str, ...] | None = None):
        super().__init__(name, params, types, _unbound_params)
        object.__setattr__(self, 'objects', objects)

    @override
    def ground(self, objects: dict[str, str] | Sequence[str]) -> 'GroundedAtom':
        return self

    @override
    def is_grounded(self) -> bool:
        return True

    def eval_in_state(self, state: 'dict[GroundedAtom, bool]') -> bool:
        return state.get(self, False)

    def bind(self, variables: dict[str, Type] | Sequence[str]) -> 'Atom':
        if isinstance(variables, dict):
            return GroundedAtom(self.name,
                tuple(variables.keys()),
                tuple(variables.values()),
                objects=self.objects,
                _unbound_params=self._unbound_params)
        else:
            if len(variables) != len(self.params):
                raise ValueError(f"{str(self)}: Wrong number of bindings: {len(variables)} != {len(self.params)}")
            return GroundedAtom(self.name, tuple(variables), self.types, objects=self.objects, _unbound_params=self._unbound_params)

    def bind_partial(self, param_to_obj: dict[str, str]) -> 'GroundedAtom':
        obj_to_param = {v: k for k, v in param_to_obj.items()}
        bound = []
        counter = itertools.count()
        for obj in self.objects:
            if obj not in obj_to_param:
                bound.append(f"unidentified_{next(counter)}")
            else:
                bound.append(obj_to_param[obj])
        return GroundedAtom(self.name, tuple(bound), self.types, objects=self.objects, _unbound_params=self._unbound_params)

    def unbind(self) -> 'GroundedAtom':
        return GroundedAtom(self.name, self._unbound_params, self.types, objects=self.objects)

    def lift(self) -> 'Atom':
        return Atom(self.name, self.params, self.types, self._unbound_params)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GroundedAtom):
            return self.name == other.name and self.objects == other.objects
        if isinstance(other, tuple):
            return self.name == other[0] and self.objects == other[1:]
        return False

    def __hash__(self) -> int:
        return hash((self.name, self.objects))

    def __str__(self):
        return f"({self.name} {' '.join(self.objects)})"

    def __repr__(self):
        return str(self)

@dataclass(frozen=True, init=False)
class DisjunctiveAtom(Atom):
    """A disjunctive atom is a tuple of atoms to model (or <atom1> ... <atomn>).

    Although OHCAM cannot learn disjunctive atoms, they may appear in the initial domain.
    """
    atoms: tuple[Atom, ...]

    def __init__(self, atoms: tuple[Atom, ...]):
        name = '-or-'.join(atom.name for atom in atoms)
        args = []
        types = []
        for atom in atoms:
            for arg, type_ in zip(atom.params, atom.types):
                if arg not in args:
                    args.append(arg)
                    types.append(type_)
        super().__init__(name, tuple(args), tuple(types))
        object.__setattr__(self, 'atoms', atoms)

    @property
    def objects(self) -> tuple[str, ...]:
        if not self.is_grounded():
            raise ValueError(f"{str(self)}: Cannot get objects of an ungrounded disjunctive atom")
        objects = {}
        for atom in self.atoms:
            atom: GroundedAtom
            for param, obj in zip(atom.params, atom.objects):
                objects[param] = obj
        return tuple(objects.values())


    def __str__(self):
        return f"(or {' '.join(str(atom) for atom in self.atoms)})"

    def __repr__(self):
        return str(self)

    def bind(self, variables: dict[str, Type] | Sequence[str]) -> 'DisjunctiveAtom':
        if isinstance(variables, dict):
            var_seq = {p: v for p, v in zip(self.params, variables.keys())}
            return DisjunctiveAtom(tuple(atom.bind(
                {var_seq[p]: variables[var_seq[p]] for p in atom.params}
                ) for atom in self.atoms))
        var_seq = {p: v for p, v in zip(self.params, variables)}
        return DisjunctiveAtom(tuple(atom.bind(
            [var_seq[p] for p in atom.params]
            ) for atom in self.atoms))

    def unbind(self) -> 'DisjunctiveAtom':
        return DisjunctiveAtom(tuple(atom.unbind() for atom in self.atoms))

    def ground(self, objects: dict[str, str] | Sequence[str]) -> 'DisjunctiveAtom':
        return DisjunctiveAtom(tuple(atom.ground(objects) for atom in self.atoms))

    def is_grounded(self) -> bool:
        return all(atom.is_grounded() for atom in self.atoms)

    def eval_in_state(self, state: 'dict[Atom, bool]') -> bool:
        return any(atom.eval_in_state(state) for atom in self.atoms)

class Conjunction(frozendict):
    """A conjunction is a set of literals."""
    def __init__(self, literals: dict[Atom, bool] | Sequence[Atom]):

        if not isinstance(literals, dict):
            atoms = []
            for literal in literals:
                atoms.append(literal)
            literals = {atom: True for atom in atoms}
        super().__init__(literals)

    def __str__(self):
        def literal_str(atom: Atom, value: bool) -> str:
            if value:
                return str(atom)
            else:
                return f"(not {str(atom)})"
        return f"(and {' '.join(literal_str(atom, value) for atom, value in self.items())})"

    def __repr__(self):
        return str(self)

    def bind(self, variables: dict[str, str]) -> 'Conjunction':
        return Conjunction({atom.bind(variables): value for atom, value in self.items()})

    def unbind(self) -> 'Conjunction':
        return Conjunction({atom.unbind(): value for atom, value in self.items()})

    def ground(self, objects: dict[str, str] | Sequence[str]) -> 'Conjunction':
        return Conjunction({atom.ground(objects): value for atom, value in self.items()})

    def is_satisfied(self, grounding: dict[str, str], state: dict[Atom, bool]) -> bool:
        for atom, value in self.items():
            grounded_atom: GroundedAtom = atom.ground(grounding)
            if grounded_atom.eval_in_state(state) != value:
                return False
        return True


    def is_grounded(self) -> bool:
        return all(literal.is_grounded() for literal in self)

@dataclass(frozen=True)
class DNF:
    """A DNF is a tuple of conjunctions."""

    conjunctions: tuple[Conjunction, ...]

    def __getitem__(self, index: int) -> Conjunction:
        return self.conjunctions[index]

    def __len__(self) -> int:
        return len(self.conjunctions)

    def __str__(self):
        if len(self) == 1:
            return str(self[0])
        else:
            return f"(or {' '.join(str(conjunction) for conjunction in self)})"

    def __repr__(self):
        return str(self)


    def bind(self, variables: dict[str, str]) -> 'DNF':
        return DNF(tuple(conjunction.bind(variables) for conjunction in self.conjunctions))

    def ground(self, objects: dict[str, str] | Sequence[str]) -> 'DNF':
        return DNF(tuple(conjunction.ground(objects) for conjunction in self.conjunctions))

    def is_grounded(self) -> bool:
        return isinstance(self.conjunctions[0], bool) or (isinstance(self.conjunctions[0], DNF) and self.conjunctions[0].is_grounded())

@dataclass(frozen=True)
class Condition:
    """A condition is an antecedent-outcome pair."""

    antecedent: bool | DNF
    outcome: Outcome

    def __post_init__(self):
        if isinstance(self.antecedent, Conjunction):
            object.__setattr__(self, 'antecedent', DNF((self.antecedent,)))
        elif not (isinstance(self.antecedent, bool) or isinstance(self.antecedent, DNF)):
            raise ValueError(f"Invalid antecedent: {self.antecedent}")

    def __getitem__(self, index: int) -> bool | DNF | Outcome:
        if index == 0:
            return self.antecedent
        elif index == 1:
            return self.outcome
        else:
            raise IndexError(f"Index out of range: {index}")

    def __str__(self):
        return f"({str(self.antecedent)} -> {self.outcome})"

    def __repr__(self):
        return str(self)

    def is_satisfied(self, grounding: dict[str, str], state: dict[Atom, bool]) -> bool:
        if isinstance(self.antecedent, bool):
            return self.antecedent
        elif isinstance(self.antecedent, DNF):
            return any(conjunction.is_satisfied(grounding, state) for conjunction in self.antecedent)
        else:
            return self.antecedent.is_satisfied(grounding, state)


    def is_grounded(self) -> bool:
        return isinstance(self.antecedent, bool) or (isinstance(self.antecedent, DNF) and self.antecedent.is_grounded())
