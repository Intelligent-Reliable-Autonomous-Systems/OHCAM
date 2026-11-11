"""Step 4 of LAMP: ``attain_models`` (paper Section 4.4, Algorithm 5).

The weighted candidate formulas (Step 3) are turned into a PDDL action model.
Following the paper, formulas whose learned weight exceeds a threshold ``delta``
are selected, and the correctness constraints are enforced:

* **A1** (action consistency): an action may not both add and delete the same
  literal under the same condition. Conflicts are resolved in favour of the
  higher-weighted formula, and a literal asserted unconditionally subsumes the
  corresponding conditional effects.
* **A3** (non-emptiness): optionally guarantee at least one effect per action.

(A2, plan consistency, is implicit because weights are learned only from real,
applicable transitions in Step 1.)

The surviving formulas are rendered into a PDDL domain. The situation label is
dropped at this point - it only existed to relate consecutive states inside the
MLN. Preconditions may contain ``forall``/``imply`` and effects may contain
``forall``/``when``/``exists`` (paper's Table 2 target language).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from unified_planning.model import Problem
from unified_planning.model.fnode import FNode

from ohcam.baselines.offline.lamp.formulas import (
    ADD,
    COND_ADD,
    COND_DEL,
    DEL,
    CandidateFormula,
)
from ohcam.baselines.offline.lamp.signature import DomainSignature

# A reasonably permissive requirements set covering the constructs LAMP may emit
# (quantifiers, implications, conditional effects, negation, equality).
_REQUIREMENTS = (
    ":strips :typing :negative-preconditions :disjunctive-preconditions "
    ":universal-preconditions :existential-preconditions "
    ":conditional-effects :equality"
)


@dataclass
class ActionModel:
    """Selected precondition/effect PDDL fragments for one action."""

    name: str
    params: tuple[tuple[str, str], ...]
    preconditions: list[str] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)


def _effect_target(formula: CandidateFormula) -> tuple[str, tuple]:
    """The (predicate, bound-args) the effect formula changes (its ``p``/``p2``)."""
    lit = formula.lits[-1]
    return (lit.pred.name, lit.refs)


def _condition_key(formula: CandidateFormula) -> tuple:
    """The condition (``p1``) of a conditional effect, for conflict detection."""
    p1 = formula.lits[0]
    return (p1.pred.name, p1.refs, p1.positive)


def _resolve_conditionals(
    cond_add: list[CandidateFormula], cond_del: list[CandidateFormula]
) -> list[CandidateFormula]:
    """Resolve add/delete conditional effects that share a condition (A1)."""
    by_cond: dict[tuple, CandidateFormula] = {}
    for f in cond_add + cond_del:
        key = _condition_key(f)
        incumbent = by_cond.get(key)
        if incumbent is None or f.weight > incumbent.weight:
            by_cond[key] = f
    return list(by_cond.values())


def _resolve_effects(effects: list[CandidateFormula]) -> list[CandidateFormula]:
    """Enforce constraint A1 on the selected effect formulas of one action.

    For each literal an action may change, we forbid simultaneously asserting
    and retracting it: unconditional add/delete conflicts are resolved in favour
    of the higher weight, an unconditional effect subsumes the conditional
    effects of the same literal, and two conditional effects that share a
    condition but disagree on the literal's truth keep only the stronger.
    """
    by_target: dict[tuple, list[CandidateFormula]] = {}
    for f in effects:
        by_target.setdefault(_effect_target(f), []).append(f)

    kept: list[CandidateFormula] = []
    for _target, group in by_target.items():
        uncond_add = max(
            (f for f in group if f.kind == ADD), key=lambda f: f.weight, default=None
        )
        uncond_del = max(
            (f for f in group if f.kind == DEL), key=lambda f: f.weight, default=None
        )
        cond_add = [f for f in group if f.kind == COND_ADD]
        cond_del = [f for f in group if f.kind == COND_DEL]

        if uncond_add is not None and uncond_del is not None:
            # Cannot both add and delete the same literal: keep the stronger.
            if uncond_add.weight >= uncond_del.weight:
                uncond_del = None
            else:
                uncond_add = None

        if uncond_add is not None:
            # An unconditional add subsumes conditional changes of the literal.
            kept.append(uncond_add)
        elif uncond_del is not None:
            kept.append(uncond_del)
        else:
            kept.extend(_resolve_conditionals(cond_add, cond_del))
    return kept


def attain_models(
    signature: DomainSignature,
    candidates: list[CandidateFormula],
    threshold: float = 0.5,
    ensure_nonempty: bool = False,
) -> dict[str, ActionModel]:
    """Select above-threshold formulas and assemble per-action models."""
    models: dict[str, ActionModel] = {
        a.name: ActionModel(a.name, a.params) for a in signature.actions
    }

    selected = [c for c in candidates if c.weight > threshold]
    by_action: dict[str, list[CandidateFormula]] = {}
    for c in selected:
        by_action.setdefault(c.action.name, []).append(c)

    for action in signature.actions:
        group = by_action.get(action.name, [])
        preconditions = [c for c in group if c.is_precondition()]
        effects = [c for c in group if not c.is_precondition()]
        effects = _resolve_effects(effects)

        if ensure_nonempty and not effects:
            # Constraint A3: force the single best effect candidate for the action.
            action_effects = [
                c
                for c in candidates
                if c.action.name == action.name and not c.is_precondition()
            ]
            if action_effects:
                effects = [max(action_effects, key=lambda f: f.weight)]

        models[action.name].preconditions = [c.pddl_fragment() for c in preconditions]
        models[action.name].effects = [c.pddl_fragment() for c in effects]

    return models


# ----------------------------------------------------------------------
# PDDL domain rendering
# ----------------------------------------------------------------------
def _render_fnode(node: FNode) -> str:
    """Render a (precondition) UP expression as PDDL; used for fixed precond."""
    if node.is_and():
        return "(and " + " ".join(_render_fnode(a) for a in node.args) + ")"
    if node.is_or():
        return "(or " + " ".join(_render_fnode(a) for a in node.args) + ")"
    if node.is_not():
        return "(not " + _render_fnode(node.args[0]) + ")"
    if node.is_implies():
        return f"(imply {_render_fnode(node.args[0])} {_render_fnode(node.args[1])})"
    if node.is_equals():
        return f"(= {_render_fnode(node.args[0])} {_render_fnode(node.args[1])})"
    if node.is_forall() or node.is_exists():
        kw = "forall" if node.is_forall() else "exists"
        decls = " ".join(f"?{v.name} - {v.type.name}" for v in node.variables())
        return f"({kw} ({decls}) {_render_fnode(node.args[0])})"
    if node.is_fluent_exp():
        args = " ".join("?" + a.parameter().name if a.is_parameter_exp()
                        else a.object().name for a in node.args)
        return f"({node.fluent().name}{(' ' + args) if args else ''})"
    if node.is_parameter_exp():
        return "?" + node.parameter().name
    if node.is_object_exp():
        return node.object().name
    if node.is_bool_constant():
        return "(and )" if node.bool_constant_value() else "(or )"
    raise ValueError(f"Cannot render precondition node: {node}")


def _negate(literal: str) -> str:
    """The PDDL negation of a rendered literal (``(p ...)`` <-> ``(not (p ...))``)."""
    if literal.startswith("(not ") and literal.endswith(")"):
        return literal[len("(not "):-1]
    return f"(not {literal})"


def _conjuncts(node: FNode) -> list[FNode]:
    """The conjuncts of a (possibly nested) conjunction."""
    if node.is_and():
        return [c for a in node.args for c in _conjuncts(a)]
    return [node]


def _render_types(signature: DomainSignature) -> str:
    by_parent: dict[str | None, list[str]] = {}
    for type_name, parent in signature.type_parents.items():
        by_parent.setdefault(parent, []).append(type_name)
    parts: list[str] = []
    for parent, children in by_parent.items():
        children = [child for child in children if child != "object"]
        if not children:
            continue
        # Root types need an explicit `- object`: names listed before a later `- parent` are all its subtypes
        parts.append(f"{' '.join(children)} - {parent or 'object'}")
    return "  ".join(parts)


def _render_predicates(signature: DomainSignature) -> str:
    lines = []
    for predicate in signature.predicates:
        args = " ".join(
            f"?x{k} - {t}" for k, t in enumerate(predicate.arg_types)
        )
        lines.append(f"  ({predicate.name}{(' ' + args) if args else ''})")
    return "\n".join(lines)


def _render_action(model: ActionModel) -> str:
    params = " ".join(f"?{name} - {t}" for name, t in model.params)
    pre = "(and " + " ".join(model.preconditions) + ")" if model.preconditions else "(and )"
    eff = "(and " + " ".join(model.effects) + ")" if model.effects else "(and )"
    return (
        f"  (:action {model.name}\n"
        f"   :parameters ({params})\n"
        f"   :precondition {pre}\n"
        f"   :effect {eff}\n"
        f"  )"
    )


def build_domain_pddl(
    signature: DomainSignature,
    models: dict[str, ActionModel],
    domain_name: str,
    initial_problem: Problem | None = None,
    fixed_preconditions: bool = False,
    extend_fixed_preconditions: bool = False,
) -> str:
    """Assemble the full learned domain as a PDDL string.

    When ``fixed_preconditions`` is set, each action keeps the precondition from
    ``initial_problem`` (mirroring the ``fix_init_precondition`` behaviour of the
    other agents). Without ``extend_fixed_preconditions`` it replaces the learned
    preconditions; with it, the learned preconditions are added to it.
    """
    if fixed_preconditions and initial_problem is not None:
        for action in initial_problem.actions:
            if action.name in models:
                fixed = [_render_fnode(c) for p in action.preconditions for c in _conjuncts(p)]
                learned = models[action.name].preconditions if extend_fixed_preconditions else []
                # A learned precondition that is the exact negation of a fixed
                # one is known to be wrong, so drop it.
                negated = {_negate(p) for p in fixed}
                models[action.name].preconditions = fixed + [
                    p for p in learned if p not in fixed and p not in negated
                ]

    actions = "\n\n".join(
        _render_action(models[a.name]) for a in signature.actions
    )
    return (
        f"(define (domain {domain_name})\n"
        f" (:requirements {_REQUIREMENTS})\n"
        f" (:types {_render_types(signature)})\n"
        f" (:predicates\n{_render_predicates(signature)}\n )\n\n"
        f"{actions}\n"
        f")\n"
    )
