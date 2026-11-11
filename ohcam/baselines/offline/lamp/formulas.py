"""Step 2 of LAMP: ``generate_formulas`` (paper Section 4.2, Algorithm 3).

For every action heading we generate candidate first-order formulas describing
its possible preconditions and effects. The five families correspond to the
paper's formulas F1-F5:

* **F1** preconditions: ``forall i,xi. a(i) -> p(xi, i)``                  (1a)
  and the implication form ``a(i) ^ p1(i) -> p2(i)``                       (1b)
* **F2** positive effects: ``a(i) -> !p(i) ^ p(i+1)``                       (2)
* **F3** negative effects: ``a(i) -> p(i) ^ !p(i+1)``                       (3)
* **F4** positive conditional effects:
  ``a(i) ^ exists xi1. p1(i) -> !p2(i) ^ p2(i+1)``                          (4)
* **F5** negative conditional effects:
  ``a(i) ^ exists xi1. p1(i) -> p2(i) ^ !p2(i+1)``                          (5)

The ``i+1`` of the paper is realized through the ``succ(i, j)`` successor atom
that ``encoding.py`` adds to every database, so an effect formula is written as
``a(i) ^ succ(i, j) -> ...``.

Free variables (the ``xi`` of the paper) are the predicate parameters that are
not bound to an action parameter. In preconditions and (non-conditional)
effects they are universally quantified. For conditional effects the variables
that occur only in the condition ``p1`` (the paper's ``xi1``) are existentially
quantified - which, per PDDL and the paper, is the only place an existential
quantifier may appear.

Each :class:`CandidateFormula` can render itself both as a ``pracmln`` formula
string (for Step 3, weight learning) and as a PDDL precondition/effect fragment
(for Step 4, model construction).
"""

from __future__ import annotations

from dataclasses import dataclass
import itertools

from ohcam.baselines.offline.lamp.signature import (
    ActionSig,
    DomainSignature,
    MLNNaming,
    Predicate,
)

# Formula kinds (the paper's F1-F5).
PRE = "pre"  # F1a: literal precondition
PRE_IMPLY = "pre_imply"  # F1b: implication precondition
ADD = "add"  # F2: positive effect
DEL = "del"  # F3: negative effect
COND_ADD = "cond_add"  # F4: positive conditional effect
COND_DEL = "cond_del"  # F5: negative conditional effect


@dataclass(frozen=True)
class VarRef:
    """A variable occurrence inside a candidate formula.

    ``kind`` is ``'c'`` for an action parameter (``id`` indexes the action's
    parameter list), ``'u'`` for a universally quantified free variable, or
    ``'e'`` for an existentially quantified free variable (conditions only).
    """

    kind: str
    id: int
    type: str

    def mln_name(self) -> str:
        return f"{self.kind}{self.id}"

    def pddl_name(self, action: ActionSig) -> str:
        if self.kind == "c":
            return "?" + action.params[self.id][0]
        return f"?{self.kind}{self.id}"


@dataclass(frozen=True)
class Lit:
    """A (possibly negated) predicate occurrence with bound arguments."""

    pred: Predicate
    refs: tuple[VarRef, ...]
    positive: bool = True


@dataclass
class CandidateFormula:
    action: ActionSig
    kind: str
    lits: tuple[Lit, ...]  # (p,) for F1a/F2/F3; (p1, p2) for F1b/F4/F5
    universals: tuple[VarRef, ...]
    existentials: tuple[VarRef, ...]
    naming: MLNNaming
    weight: float = 0.0

    # ------------------------------------------------------------------
    # MLN rendering (Step 3 input)
    # ------------------------------------------------------------------
    def _mln_action(self, state: str) -> str:
        args = [f"c{k}" for k in range(len(self.action.params))] + [state]
        return f"{self.naming.action(self.action.name)}({', '.join(args)})"

    def _mln_atom(self, lit: Lit, state: str) -> str:
        args = [r.mln_name() for r in lit.refs] + [state]
        atom = f"{self.naming.pred(lit.pred.name)}({', '.join(args)})"
        return atom if lit.positive else f"!{atom}"

    def _mln_succ(self) -> str:
        return f"{self.naming.SUCC}(i, j)"

    def mln_string(self) -> str:
        """Render this candidate as an MLN formula (valid for ``pracmln`` and Alchemy)."""
        act = self._mln_action("i")
        if self.kind == PRE:
            return f"{act} => {self._mln_atom(self.lits[0], 'i')}"
        if self.kind == PRE_IMPLY:
            p1, p2 = self.lits
            return f"{act} ^ {self._mln_atom(p1, 'i')} => {self._mln_atom(p2, 'i')}"
        if self.kind == ADD:
            p = self.lits[0]
            after = self._mln_atom(p, "j")
            before = self._mln_atom(Lit(p.pred, p.refs, not p.positive), "i")
            return f"{act} ^ {self._mln_succ()} => ({before} ^ {after})"
        if self.kind == DEL:
            p = self.lits[0]
            before = self._mln_atom(p, "i")
            after = self._mln_atom(Lit(p.pred, p.refs, not p.positive), "j")
            return f"{act} ^ {self._mln_succ()} => ({before} ^ {after})"
        if self.kind in (COND_ADD, COND_DEL):
            p1, p2 = self.lits
            cond = self._mln_atom(p1, "i")
            if self.existentials:
                evars = ",".join(e.mln_name() for e in self.existentials)
                # The outer parentheses keep Alchemy's parser from overflowing
                # on an unparenthesized quantifier inside a conjunction.
                cond = f"(EXIST {evars} ({cond}))"
            if self.kind == COND_ADD:
                eff = (
                    f"({self._mln_atom(Lit(p2.pred, p2.refs, False), 'i')} ^ "
                    f"{self._mln_atom(Lit(p2.pred, p2.refs, True), 'j')})"
                )
            else:
                eff = (
                    f"({self._mln_atom(Lit(p2.pred, p2.refs, True), 'i')} ^ "
                    f"{self._mln_atom(Lit(p2.pred, p2.refs, False), 'j')})"
                )
            return f"{act} ^ {self._mln_succ()} ^ {cond} => {eff}"
        raise ValueError(f"Unknown formula kind: {self.kind}")

    # ------------------------------------------------------------------
    # PDDL rendering (Step 4 output)
    # ------------------------------------------------------------------
    def _pddl_atom(self, lit: Lit) -> str:
        args = " ".join(r.pddl_name(self.action) for r in lit.refs)
        inner = f"({lit.pred.name}{(' ' + args) if args else ''})"
        return inner if lit.positive else f"(not {inner})"

    def _forall_decls(self, refs: tuple[VarRef, ...]) -> str:
        return " ".join(f"{r.pddl_name(self.action)} - {r.type}" for r in refs)

    def is_precondition(self) -> bool:
        return self.kind in (PRE, PRE_IMPLY)

    def pddl_fragment(self) -> str:
        """Render this candidate as a PDDL precondition or effect fragment."""
        if self.kind == PRE:
            body = self._pddl_atom(self.lits[0])
            if self.universals:
                return f"(forall ({self._forall_decls(self.universals)}) {body})"
            return body
        if self.kind == PRE_IMPLY:
            p1, p2 = self.lits
            body = f"(imply {self._pddl_atom(p1)} {self._pddl_atom(p2)})"
            if self.universals:
                return f"(forall ({self._forall_decls(self.universals)}) {body})"
            return body
        if self.kind == ADD:
            body = self._pddl_atom(Lit(self.lits[0].pred, self.lits[0].refs, True))
            if self.universals:
                return f"(forall ({self._forall_decls(self.universals)}) {body})"
            return body
        if self.kind == DEL:
            body = self._pddl_atom(Lit(self.lits[0].pred, self.lits[0].refs, False))
            if self.universals:
                return f"(forall ({self._forall_decls(self.universals)}) {body})"
            return body
        if self.kind in (COND_ADD, COND_DEL):
            p1, p2 = self.lits
            cond = self._pddl_atom(Lit(p1.pred, p1.refs, True))
            if self.existentials:
                cond = f"(exists ({self._forall_decls(self.existentials)}) {cond})"
            eff_lit = Lit(p2.pred, p2.refs, self.kind == COND_ADD)
            body = f"(when {cond} {self._pddl_atom(eff_lit)})"
            if self.universals:
                return f"(forall ({self._forall_decls(self.universals)}) {body})"
            return body
        raise ValueError(f"Unknown formula kind: {self.kind}")

    # ------------------------------------------------------------------
    def key(self) -> str:
        """Canonical key for de-duplicating structurally identical formulas."""
        return f"{self.action.name}|{self.kind}|{self.pddl_fragment()}"


@dataclass
class _Allocator:
    """Allocates fresh free-variable ids within a single formula."""

    u: int = 0
    e: int = 0

    def new_u(self, type_name: str) -> VarRef:
        ref = VarRef("u", self.u, type_name)
        self.u += 1
        return ref

    def new_e(self, type_name: str) -> VarRef:
        ref = VarRef("e", self.e, type_name)
        self.e += 1
        return ref


class FormulaGenerator:
    """Generates the candidate formulas F1-F5 for a domain (Algorithm 3)."""

    def __init__(
        self,
        signature: DomainSignature,
        naming: MLNNaming,
        max_free_vars: int = 2,
        learn_preconditions: bool = True,
        precondition_implications: bool = True,
        precondition_universals: bool = True,
        conditional_effects: bool = True,
        existential_conditions: bool = True,
        negative_preconditions: bool = False,
    ) -> None:
        self.sig = signature
        self.naming = naming
        self.max_free_vars = max_free_vars
        self.learn_preconditions = learn_preconditions
        self.precondition_implications = precondition_implications
        # When False, preconditions may only use literals whose arguments are
        # all bound to action parameters - no universally quantified free
        # variables (and, with ``precondition_implications`` off too, no
        # implications). This restricts preconditions to plain conjunctions of
        # literals, matching the expressiveness of SAM-style learners.
        self.precondition_universals = precondition_universals
        self.conditional_effects = conditional_effects
        # When False, conditional-effect conditions introduce no existentially
        # quantified variables: the condition may only mention action parameters
        # or the effect's universally quantified variable(s).
        self.existential_conditions = existential_conditions
        # When True, F1a also proposes negated literals as preconditions (the
        # paper's "any literal p can be a precondition").
        self.negative_preconditions = negative_preconditions

    def generate(self) -> list[CandidateFormula]:
        formulas: list[CandidateFormula] = []
        for action in self.sig.actions:
            formulas.extend(self._for_action(action))
        # De-duplicate structurally identical candidates.
        seen: dict[str, CandidateFormula] = {}
        for f in formulas:
            seen.setdefault(f.key(), f)
        return list(seen.values())

    # ------------------------------------------------------------------
    def _action_param_refs(self, action: ActionSig) -> list[VarRef]:
        return [VarRef("c", k, t) for k, (_, t) in enumerate(action.params)]

    def _bind(
        self,
        predicate: Predicate,
        action: ActionSig,
        reusable: list[VarRef],
        new_kind: str | None,
        alloc: _Allocator,
        budget: int,
    ):
        """Yield ``(refs, new_free_refs)`` bindings for ``predicate``'s args.

        Each argument is bound either to a type-compatible action parameter, a
        reusable free variable, or (if ``new_kind`` is given and budget allows)
        a freshly allocated free variable. ``budget`` caps the number of *new*
        free variables introduced in this binding.
        """
        cparams = self._action_param_refs(action)

        # Build, per argument, the list of concrete option refs plus an optional
        # NEW sentinel. ``None`` is the sentinel for "allocate a fresh free var".
        per_arg_options: list[list[VarRef | None]] = []
        for arg_type in predicate.arg_types:
            opts: list[VarRef | None] = [
                r for r in cparams if self.sig.types_compatible(r.type, arg_type)
            ]
            opts += [
                r for r in reusable if self.sig.types_compatible(r.type, arg_type)
            ]
            if new_kind is not None:
                opts.append(None)  # the NEW-free-variable sentinel
            if not opts:
                return  # this predicate cannot be bound here
            per_arg_options.append(opts)

        for combo in itertools.product(*per_arg_options):
            n_new = sum(1 for c in combo if c is None)
            if n_new > budget:
                continue
            local_alloc = _Allocator(alloc.u, alloc.e)
            refs: list[VarRef] = []
            new_refs: list[VarRef] = []
            for opt, arg_type in zip(combo, predicate.arg_types):
                if opt is None:
                    ref = (
                        local_alloc.new_u(arg_type)
                        if new_kind == "u"
                        else local_alloc.new_e(arg_type)
                    )
                    new_refs.append(ref)
                else:
                    ref = opt
                refs.append(ref)
            yield tuple(refs), new_refs

    def _mk(self, action, kind, lits, universals, existentials) -> CandidateFormula:
        return CandidateFormula(
            action=action,
            kind=kind,
            lits=tuple(lits),
            universals=tuple(universals),
            existentials=tuple(existentials),
            naming=self.naming,
        )

    def _for_action(self, action: ActionSig) -> list[CandidateFormula]:
        out: list[CandidateFormula] = []

        # F2 / F3: single-literal (non-conditional) effects. Free variables are
        # universally quantified.
        for predicate in self.sig.predicates:
            alloc = _Allocator()
            for refs, new_refs in self._bind(
                predicate, action, [], "u", alloc, self.max_free_vars
            ):
                lit = Lit(predicate, refs, True)
                universals = tuple(new_refs)
                out.append(self._mk(action, ADD, [lit], universals, ()))
                out.append(self._mk(action, DEL, [lit], universals, ()))

        # F1a: single-literal preconditions. When ``precondition_universals`` is
        # off, the free-variable budget is 0, so only literals fully bound to
        # action parameters become preconditions (no universal quantifier).
        if self.learn_preconditions:
            pre_budget = self.max_free_vars if self.precondition_universals else 0
            for predicate in self.sig.predicates:
                alloc = _Allocator()
                for refs, new_refs in self._bind(
                    predicate, action, [], "u", alloc, pre_budget
                ):
                    for positive in (True, False) if self.negative_preconditions else (True,):
                        lit = Lit(predicate, refs, positive)
                        out.append(self._mk(action, PRE, [lit], tuple(new_refs), ()))

        # F1b: implication preconditions ``p1 -> p2`` (and polarity variants).
        if self.learn_preconditions and self.precondition_implications:
            out.extend(self._implication_preconditions(action))

        # F4 / F5: (quantified) conditional effects ``when p1 then [not] p2``.
        if self.conditional_effects:
            out.extend(self._conditional_effects(action))

        return out

    def _implication_preconditions(self, action: ActionSig) -> list[CandidateFormula]:
        out: list[CandidateFormula] = []
        polarities = [(True, True), (False, True), (True, False)]
        for p1 in self.sig.predicates:
            for p2 in self.sig.predicates:
                alloc = _Allocator()
                for refs1, new1 in self._bind(
                    p1, action, [], "u", alloc, self.max_free_vars
                ):
                    reusable = list(new1)
                    a2 = _Allocator(len(reusable), 0)
                    for refs2, new2 in self._bind(
                        p2,
                        action,
                        reusable,
                        "u",
                        a2,
                        max(0, self.max_free_vars - len(new1)),
                    ):
                        if (p1.name, refs1) == (p2.name, refs2):
                            continue  # ``p -> p`` is vacuous
                        universals = tuple(new1) + tuple(new2)
                        for pol1, pol2 in polarities:
                            out.append(
                                self._mk(
                                    action,
                                    PRE_IMPLY,
                                    [Lit(p1, refs1, pol1), Lit(p2, refs2, pol2)],
                                    universals,
                                    (),
                                )
                            )
        return out

    def _conditional_effects(self, action: ActionSig) -> list[CandidateFormula]:
        out: list[CandidateFormula] = []
        for p2 in self.sig.predicates:  # the effect predicate
            for p1 in self.sig.predicates:  # the condition predicate
                # Bind the effect literal first; its free vars are the universal
                # xi/xi2. Then bind the condition, reusing those universals and
                # introducing existential xi1 variables for condition-only args.
                a_eff = _Allocator()
                for refs2, new2 in self._bind(
                    p2, action, [], "u", a_eff, self.max_free_vars
                ):
                    reusable = list(new2)
                    a_cond = _Allocator(len(reusable), 0)
                    # With existential conditions disabled the condition gets no
                    # fresh variables (budget 0): it may only reuse the effect's
                    # universals or bind to action parameters.
                    cond_kind = "e" if self.existential_conditions else None
                    cond_budget = (
                        max(0, self.max_free_vars - len(new2))
                        if self.existential_conditions
                        else 0
                    )
                    for refs1, new1 in self._bind(
                        p1,
                        action,
                        reusable,
                        cond_kind,
                        a_cond,
                        cond_budget,
                    ):
                        if (p1.name, refs1) == (p2.name, refs2):
                            continue
                        universals = tuple(new2)
                        existentials = tuple(new1)
                        for kind in (COND_ADD, COND_DEL):
                            out.append(
                                self._mk(
                                    action,
                                    kind,
                                    [Lit(p1, refs1, True), Lit(p2, refs2, True)],
                                    universals,
                                    existentials,
                                )
                            )
        return out
