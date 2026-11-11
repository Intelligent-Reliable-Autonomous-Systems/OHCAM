"""Step 3 of LAMP with formula-level WPLL: ``learn_weights`` (paper Section 4.3).

The paper's WPLL treats every ground candidate formula as one 0/1 feature
(Example 6: "f_i ... is the value (0 or 1) of the feature corresponding to the
ith ground formula"). Alchemy instead splits each formula into CNF clauses with
separate weights; LAMP's candidates share clauses (a precondition ``p`` and the
delete effect ``p(i) ^ !p(i+1)`` both contain ``!a v p(i)``), so the split, and
with it the summed formula weight, becomes arbitrary. This module computes the
paper's formula-level WPLL directly and optimizes it with Algorithm 4.

For a ground atom ``X_l`` let ``d_l[k]`` be the change in formula k's number of
true groundings when ``X_l`` is flipped. Then

    log P(X_l = x_l | MB(X_l)) = -log(1 + exp(w . d_l))

so a database's WPLL and its gradient are matrix operations on the sparse
atoms x formulas matrix ``D`` of the ``d_l``, built once per database.

Groundings: action parameters and free variables range over the database's
constants of their (root) type; ``i`` over the situations. Effect formulas only
constrain consecutive situations ``(i, i+1)`` linked by ``succ`` (for any other
pair their antecedent is false), and ``succ`` itself is evidence, not scored.
Closed world: atoms absent from a database are false.
"""

from __future__ import annotations

import logging
import random
import re
from collections import defaultdict
from itertools import product

import numpy as np
from scipy import sparse
from scipy.optimize import minimize

from ohcam.baselines.offline.lamp.encoding import EncodedTrace
from ohcam.baselines.offline.lamp.formulas import (
    ADD,
    COND_ADD,
    COND_DEL,
    DEL,
    PRE,
    PRE_IMPLY,
    CandidateFormula,
    Lit,
)
from ohcam.baselines.offline.lamp.signature import DomainSignature, MLNNaming

logger = logging.getLogger(__name__)

_ATOM = re.compile(r"^(!?)(\w+)\((.*)\)$")


class _Database:
    """One encoded trace: true atoms, constants per MLN domain, situations."""

    def __init__(self, et: EncodedTrace, arg_domains: dict[str, list[str]], succ: str):
        self.true: set[tuple] = set()
        self.constants: dict[str, set[str]] = defaultdict(set)
        self.succ: list[tuple[int, int]] = []
        situations: set[int] = set()
        for line in et.db_text.splitlines():
            m = _ATOM.match(line.strip())
            if not m:
                continue
            neg, pred, args = m.group(1), m.group(2), [a.strip() for a in m.group(3).split(",")]
            if pred == succ:
                self.succ.append((int(args[0]), int(args[1])))
                continue
            situations.add(int(args[-1]))
            for dom, const in zip(arg_domains[pred], args[:-1]):
                self.constants[dom].add(const)
            if not neg:
                self.true.add((pred, *args[:-1], int(args[-1])))
        situations.update(i for pair in self.succ for i in pair)
        self.situations = sorted(situations)
        self.constants = {d: sorted(c) for d, c in self.constants.items()}


def _structure(cand: CandidateFormula):
    """(antecedent literals, consequent literals) as (Lit, situation) pairs; 'i' or 'j'."""
    k = cand.kind
    if k == PRE:
        return [], [(cand.lits[0], "i")]
    if k == PRE_IMPLY:
        return [(cand.lits[0], "i")], [(cand.lits[1], "i")]
    if k in (ADD, DEL):
        p = cand.lits[0]
        before = Lit(p.pred, p.refs, k == DEL)
        return [], [(before, "i"), (Lit(p.pred, p.refs, k == ADD), "j")]
    if k in (COND_ADD, COND_DEL):
        p1, p2 = cand.lits
        before = Lit(p2.pred, p2.refs, k == COND_DEL)
        return [(p1, "i")], [(before, "i"), (Lit(p2.pred, p2.refs, k == COND_ADD), "j")]
    raise ValueError(f"Unknown formula kind: {k}")


def _build_matrix(db, candidates, signature, naming, scored, pred_weight):
    """Sparse atoms x formulas matrix D and per-atom WPLL weights for one database."""
    atom_index: dict[tuple, int] = {}
    rows, cols, vals = [], [], []

    def domain_of(ref):
        return naming.domain(signature.root_type(ref.type))

    for k, cand in enumerate(candidates):
        if cand.existentials:
            raise NotImplementedError("formula-level WPLL does not support existential conditions")
        ant, cons = _structure(cand)
        act = naming.action(cand.action.name)
        effect = any(s == "j" for _, s in cons)
        cparams = [naming.domain(signature.root_type(t)) for _, t in cand.action.params]
        free = list(cand.universals)
        domains = cparams + [domain_of(u) for u in free]
        if any(d not in db.constants for d in domains):
            continue  # a type with no objects in this trace: no groundings
        pairs = db.succ if effect else [(i, None) for i in db.situations]
        for binding in product(*(db.constants[d] for d in domains)):
            cvals = binding[: len(cparams)]
            uvals = dict(zip(((u.kind, u.id) for u in free), binding[len(cparams):]))

            def ground(lit, sit, i, j):
                args = tuple(cvals[r.id] if r.kind == "c" else uvals[(r.kind, r.id)] for r in lit.refs)
                return (naming.pred(lit.pred.name), *args, i if sit == "i" else j), lit.positive

            for i, j in pairs:
                a_atom = (act, *cvals, i)
                lits = [ground(l, s, i, j) for l, s in ant + cons]
                atoms = {a_atom} | {a for a, _ in lits}

                def value(flip):
                    def t(a):
                        return (a in db.true) != (a == flip)
                    if not t(a_atom):
                        return 1
                    if not all(t(a) == pos for a, pos in lits[: len(ant)]):
                        return 1
                    return int(all(t(a) == pos for a, pos in lits[len(ant):]))

                base = value(None)
                for atom in atoms:
                    if atom[0] not in scored:
                        continue
                    d = value(atom) - base
                    if d:
                        idx = atom_index.setdefault(atom, len(atom_index))
                        rows.append(idx)
                        cols.append(k)
                        vals.append(d)
    D = sparse.csr_matrix((vals, (rows, cols)), shape=(len(atom_index), len(candidates)), dtype=float)
    weights = np.array([pred_weight(db, atom[0]) for atom in atom_index], dtype=float)
    return D, weights


def _wpll(w, D, aw):
    """WPLL and its gradient for one database (atoms with all-zero d contribute 0)."""
    z = D @ w
    value = -np.sum(aw * np.logaddexp(0.0, z))
    grad = -(D.T @ (aw / (1.0 + np.exp(-z))))
    return value, grad


def learn_weights(
    signature: DomainSignature,
    naming: MLNNaming,
    candidates: list[CandidateFormula],
    encoded: list[EncodedTrace],
    optimizer: str = "algorithm4",
    n_iterations: int = 100,
    step_size: float = 0.01,
    n_orderings: int = 5,
    prior_stdev: float | None = None,
    equal_pred_weight: bool = True,
    state_pll: bool = False,
    seed: int = 0,
) -> list[CandidateFormula]:
    """Learn a weight per candidate by formula-level WPLL; returns the same objects.

    ``optimizer="algorithm4"`` is the paper's Algorithm 4: weights start at 0;
    each of ``n_iterations`` epochs takes one gradient step of size
    ``step_size`` per database, in a random order; the result is averaged over
    ``n_orderings`` orderings. ``optimizer="lbfgs"`` maximizes the summed WPLL
    to convergence (with an optional Gaussian prior). With ``equal_pred_weight``
    each predicate's atoms share equal total weight (Alchemy's WPLL weighting);
    with ``state_pll`` only state-predicate atoms are scored.
    """
    if not encoded:
        return candidates
    arg_domains = {}
    for p in signature.predicates:
        arg_domains[naming.pred(p.name)] = [naming.domain(signature.root_type(t)) for t in p.arg_types]
    for a in signature.actions:
        arg_domains[naming.action(a.name)] = [naming.domain(signature.root_type(t)) for _, t in a.params]
    scored = {naming.pred(p.name) for p in signature.predicates}
    if not state_pll:
        scored |= {naming.action(a.name) for a in signature.actions}

    def pred_weight(db, pred):
        if not equal_pred_weight:
            return 1.0
        n = len(db.situations)
        for dom in arg_domains[pred]:
            n *= len(db.constants.get(dom, ()))
        return 1.0 / max(n, 1)

    dbs = []
    for et in encoded:
        db = _Database(et, arg_domains, naming.SUCC)
        dbs.append(_build_matrix(db, candidates, signature, naming, scored, pred_weight))
    print(f"Formula-level WPLL: {len(candidates)} formulas, {len(dbs)} databases, "
          f"{sum(D.shape[0] for D, _ in dbs)} informative atoms")

    n = len(candidates)
    if optimizer == "algorithm4":
        rng = random.Random(seed)
        total = np.zeros(n)
        for _ in range(n_orderings):
            w = np.zeros(n)
            for _ in range(n_iterations):
                order = list(range(len(dbs)))
                rng.shuffle(order)
                for d in order:
                    _, g = _wpll(w, *dbs[d])
                    w = w + step_size * g
            total += w
        w = total / n_orderings
    elif optimizer == "lbfgs":
        def neg(w):
            value, grad = 0.0, np.zeros(n)
            for D, aw in dbs:
                v, g = _wpll(w, D, aw)
                value += v
                grad += g
            if prior_stdev:
                value -= np.sum(w ** 2) / (2 * prior_stdev ** 2)
                grad -= w / prior_stdev ** 2
            return -value, -grad
        w = minimize(neg, np.zeros(n), jac=True, method="L-BFGS-B").x
    else:
        raise ValueError(f"Unknown optimizer: {optimizer}")

    for cand, weight in zip(candidates, w):
        cand.weight = float(weight)
    return candidates
