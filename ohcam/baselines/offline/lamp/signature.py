"""Domain signature extraction and MLN naming utilities for LAMP.

LAMP's input (paper Section 3, "Problem definition") consists of a set of
predicates ``P`` and a set of action headings ``A`` (an action name plus a
typed parameter list, with no preconditions/effects). This module extracts
that signature from a Unified-Planning ``Problem`` and provides the bookkeeping
needed to translate between PDDL identifiers and identifiers that are legal in
``pracmln``'s logic grammar.

Naming rules (``pracmln`` ``StandardGrammar``):

* In *formulas*, an argument whose first character is lower-case is a logical
  *variable*; everything else is a *constant*. We therefore use purely
  positional lower-case variable names (``c0`` action parameters, ``u0``
  universally quantified free variables, ``e0`` existentially quantified free
  variables, ``i``/``j`` the before/after situation labels). These MLN variable
  names are internal and never appear in the emitted PDDL.
* In *databases* only ground atoms are allowed and every argument must be a
  constant (i.e. must NOT start with a lower-case letter). Planning objects are
  usually lower-case, so they are mapped to constant-safe tokens by
  :class:`ConstantMap`. Object constants never appear in the output PDDL, so
  the mapping does not need to be inverted.
* Predicate/action names may contain characters (e.g. ``-``) that we sanitize
  to ``_`` for the MLN; :class:`NameMap` keeps the inverse mapping so that the
  learned models can be written back with their original PDDL names.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from unified_planning.model import Problem


@dataclass(frozen=True)
class Predicate:
    """A predicate heading, e.g. ``(at ?x - portable ?l - location)``."""

    name: str
    arg_types: tuple[str, ...]

    @property
    def arity(self) -> int:
        return len(self.arg_types)


@dataclass(frozen=True)
class ActionSig:
    """An action heading, e.g. ``(move ?m - location ?l - location)``.

    ``params`` is the ordered list of ``(pddl_param_name, type_name)`` pairs.
    """

    name: str
    params: tuple[tuple[str, str], ...]

    @property
    def param_types(self) -> tuple[str, ...]:
        return tuple(t for _, t in self.params)


@dataclass
class DomainSignature:
    """The predicates, actions and type hierarchy of a planning domain."""

    predicates: list[Predicate]
    actions: list[ActionSig]
    type_parents: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def from_problem(cls, problem: Problem) -> "DomainSignature":
        type_parents: dict[str, str | None] = {}
        for up_type in problem.user_types:
            type_parents[up_type.name] = (
                up_type.father.name if up_type.father is not None else None
            )
        predicates = [
            Predicate(fluent.name, tuple(p.type.name for p in fluent.signature))
            for fluent in problem.fluents
        ]
        actions = [
            ActionSig(
                action.name,
                tuple((p.name, p.type.name) for p in action.parameters),
            )
            for action in problem.actions
        ]
        return cls(predicates=predicates, actions=actions, type_parents=type_parents)

    def ancestors(self, type_name: str) -> set[str]:
        """All supertypes of ``type_name`` (inclusive)."""
        seen: set[str] = set()
        cur: str | None = type_name
        while cur is not None and cur not in seen:
            seen.add(cur)
            cur = self.type_parents.get(cur)
        return seen

    def root_type(self, type_name: str) -> str:
        """The topmost ancestor of ``type_name`` (itself if it has no parent).

        Used to flatten the PDDL type hierarchy onto MLN domains: pracmln's
        first-order logic has no subtyping and requires every logical variable
        to inhabit a single domain, so a candidate that binds one variable
        across a subtype boundary (e.g. a ``block`` action parameter into a
        ``surface`` predicate slot) would otherwise be rejected. Because every
        type is ``types_compatible`` with its root, mapping each type to its
        root guarantees that any two hierarchy-related types share one MLN
        domain, so no variable can straddle two domains. Candidate generation
        and PDDL rendering still use the real (fine-grained) types.
        """
        cur = type_name
        seen: set[str] = set()
        while cur not in seen:
            seen.add(cur)
            parent = self.type_parents.get(cur)
            if parent is None or parent == cur:
                return cur
            cur = parent
        return cur

    def types_compatible(self, a: str, b: str) -> bool:
        """Whether an object of one type may legally fill a slot of the other.

        Used when deciding whether an action parameter can be bound to a
        predicate argument during candidate generation (paper Section 4.2).
        """
        return a == b or a in self.ancestors(b) or b in self.ancestors(a)

    def predicate(self, name: str) -> Predicate:
        for p in self.predicates:
            if p.name == name:
                return p
        raise KeyError(f"Unknown predicate: {name}")


class NameMap:
    """Bidirectional map between PDDL identifiers and MLN-safe identifiers."""

    def __init__(self) -> None:
        self._to_mln: dict[str, str] = {}
        self._to_pddl: dict[str, str] = {}

    @staticmethod
    def _sanitize(name: str) -> str:
        safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
        if not safe or not safe[0].isalpha():
            safe = "p_" + safe
        return safe

    def to_mln(self, pddl_name: str) -> str:
        if pddl_name in self._to_mln:
            return self._to_mln[pddl_name]
        base = self._sanitize(pddl_name)
        candidate = base
        idx = 0
        while candidate in self._to_pddl and self._to_pddl[candidate] != pddl_name:
            idx += 1
            candidate = f"{base}_{idx}"
        self._to_mln[pddl_name] = candidate
        self._to_pddl[candidate] = pddl_name
        return candidate

    def to_pddl(self, mln_name: str) -> str:
        return self._to_pddl[mln_name]


class ConstantMap:
    """Maps planning object names to constant-safe MLN tokens.

    ``pracmln`` treats lower-case-leading identifiers as variables even inside
    databases, so object names such as ``instrument0`` would be rejected. We
    prefix every object with ``C_`` to guarantee it is parsed as a constant.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def constant(self, obj_name: str) -> str:
        if obj_name not in self._cache:
            safe = "".join(
                ch if (ch.isalnum() or ch == "_") else "_" for ch in obj_name
            )
            self._cache[obj_name] = "C_" + safe
        return self._cache[obj_name]


class MLNNaming:
    """Shared naming used by both the trace encoder and the formula generator.

    Keeping a single instance guarantees that the MLN predicate names used in
    the candidate formulas (Step 2) exactly match those emitted in the
    databases (Step 1).
    """

    #: MLN predicate name for the situation successor relation (``succ(i, i+1)``).
    SUCC = "succ"
    #: MLN domain (type) name used for situation-label arguments.
    STATE_DOMAIN = "lampstate"

    def __init__(self, succ: str | None = None) -> None:
        # Alchemy reserves ``succ`` as a built-in function, so its backend
        # renames the successor predicate.
        if succ is not None:
            self.SUCC = succ
        self._preds = NameMap()
        self._actions = NameMap()
        self._domains: dict[str, str] = {}
        self.constants = ConstantMap()

    def domain(self, type_name: str) -> str:
        """MLN domain (type) name; must start with a lower-case letter."""
        if type_name not in self._domains:
            safe = "".join(
                ch if (ch.isalnum() or ch == "_") else "_" for ch in type_name
            )
            if not safe or not safe[0].islower():
                safe = "t_" + safe
            self._domains[type_name] = safe
        return self._domains[type_name]

    def pred(self, pddl_name: str) -> str:
        """MLN predicate name for a (state) predicate."""
        return self._preds.to_mln(pddl_name)

    def action(self, pddl_name: str) -> str:
        """MLN predicate name for an action (prefixed to avoid clashes)."""
        return "act_" + self._actions.to_mln(pddl_name)

    def const(self, obj_name: str) -> str:
        return self.constants.constant(obj_name)


def predicate_declarations(signature: DomainSignature, naming: MLNNaming) -> list[str]:
    """One MLN predicate declaration per state/action predicate.

    Every predicate gains a trailing situation-label argument (domain
    ``lampstate``); ``succ`` relates two situation labels (Section 4.1). The
    declarations are valid for both ``pracmln`` and Alchemy.
    """
    # Flatten each argument's type to its root ancestor so that the MLN - whose
    # first-order logic has no subtyping - never sees a variable spanning two
    # domains (see ``DomainSignature.root_type``). Candidate generation and PDDL
    # rendering still use the fine-grained types.
    decls: list[str] = []
    for predicate in signature.predicates:
        doms = [naming.domain(signature.root_type(t)) for t in predicate.arg_types]
        doms.append(naming.STATE_DOMAIN)
        decls.append(f"{naming.pred(predicate.name)}({', '.join(doms)})")
    for action in signature.actions:
        doms = [naming.domain(signature.root_type(t)) for _, t in action.params]
        doms.append(naming.STATE_DOMAIN)
        decls.append(f"{naming.action(action.name)}({', '.join(doms)})")
    decls.append(
        f"{naming.SUCC}({naming.STATE_DOMAIN}, {naming.STATE_DOMAIN})"
    )
    return decls
