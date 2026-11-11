"""Step 3 of LAMP: ``learn_weights`` (paper Section 4.3, Algorithm 4).

The candidate formulas (Step 2) are assembled into a Markov Logic Network whose
weights are learned from the situation-labelled databases (Step 1) by
maximizing the *weighted pseudo-log-likelihood* (WPLL). We delegate this to the
vendored ``pracmln`` library: its ``BPLL`` learner optimizes exactly the
pseudo-(log-)likelihood objective of the paper.

The paper (Section 4.3) averages the gradient over five random orderings of the
databases because it performs *online* gradient ascent, where the result is
order sensitive. ``pracmln``'s ``BPLL`` instead performs batch L-BFGS over all
databases at once and is therefore order independent; a single learning run is
sufficient (``n_orderings`` is kept as a knob for fidelity, averaging the - in
practice identical - runs).
"""

from __future__ import annotations

import logging
import os
import sys

from ohcam.baselines.offline.lamp.encoding import EncodedTrace
from ohcam.baselines.offline.lamp.formulas import CandidateFormula
from ohcam.baselines.offline.lamp.signature import (
    DomainSignature,
    MLNNaming,
    predicate_declarations,
)

logger = logging.getLogger(__name__)

# Make pracmln (python3) importable without installing it. It lives in
# third_party/ at the repository root, so LAMP requires a source checkout rather than an
# installed wheel; every other approach works from either.
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, os.pardir)
)
_PRACMLN_PATH = os.path.join(_REPO_ROOT, "third_party", "pracmln", "python3")
if not os.path.isdir(_PRACMLN_PATH):
    raise ImportError(
        f"pracmln not found at {_PRACMLN_PATH}. The LAMP baseline needs a checkout of "
        "https://github.com/danielnyga/pracmln at third_party/pracmln (see README)."
    )
if _PRACMLN_PATH not in sys.path:
    sys.path.insert(0, _PRACMLN_PATH)


def learn_weights(
    signature: DomainSignature,
    naming: MLNNaming,
    candidates: list[CandidateFormula],
    encoded: list[EncodedTrace],
    n_orderings: int = 1,
    prior_stdev: float = 1.0,
    num_cores: int = 1,
    maxiter: int = 100,
    gtol: float = 1e-2,
    verbose: bool = False,
) -> list[CandidateFormula]:
    """Learn a weight for each candidate formula; returns the same objects.

    Candidates whose predicates never occur in the data are dropped by
    ``pracmln`` during materialization and retain their default weight of 0.

    A zero-mean Gaussian prior (``prior_stdev``) regularizes the weights. It is
    also a numerical safeguard: ``pracmln``'s pseudo-likelihood does not rescale
    its exponentials, so without a prior the unconstrained optimizer can drive
    weights until ``exp`` overflows.

    ``num_cores`` controls parallelism. The dominant cost, BPLL's per-database
    sufficient-statistics computation, is embarrassingly parallel across
    databases; with ``num_cores > 1`` we enable ``pracmln``'s multi-core learner
    and cap its process pool to ``num_cores`` workers (``pracmln`` otherwise
    grabs every core). ``num_cores <= 1`` runs single-threaded.
    """
    from pracmln.mln.base import MLN
    from pracmln.mln.database import parse_db
    from pracmln.mln.learning import multidb as _multidb
    from pracmln.mln.methods import LearningMethods

    multicore = num_cores is not None and num_cores > 1

    mln = MLN(logic="FirstOrderLogic", grammar="StandardGrammar")
    for decl in predicate_declarations(signature, naming):
        mln << decl

    # Add candidate formulas one by one so a single malformed formula cannot
    # abort the whole batch; map each formula's canonical string to its
    # candidate so learned weights can be matched back after materialization.
    by_canonical: dict[str, CandidateFormula] = {}
    for i, cand in enumerate(candidates):
        if i % 200 == 0:
            print(f"Processed {i} candidates")
        try:
            formula = mln.formula(cand.mln_string(), weight=0.0)
        except Exception as exc:  # noqa: BLE001 - skip unparsable candidates
            logger.warning("Skipping candidate %s: %s", cand.mln_string(), exc)
            continue
        by_canonical[str(formula)] = cand

    dbs = []
    for i, et in enumerate(encoded):
        if i % 200 == 0:
            print(f"Processed {i} encoded traces")
        try:
            dbs.extend(parse_db(mln, et.db_text))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping unparsable database: %s", exc)
    if not dbs:
        logger.warning("LAMP: no databases to learn from; weights stay at 0.")
        return candidates

    # Cap pracmln's worker pool to ``num_cores``. ``multidb`` calls a bare
    # ``Pool()`` (which defaults to every logical core), so we temporarily
    # replace the ``Pool`` it looks up with one that injects ``processes``.
    _orig_pool = None
    if multicore:
        _orig_pool = _multidb.Pool

        def _capped_pool(processes=None, *args, **kwargs):
            if processes is None:
                processes = num_cores
            return _orig_pool(processes, *args, **kwargs)

        _multidb.Pool = _capped_pool

    # Average the (order-independent) learned weights over a few runs.
    accumulated: dict[str, float] = {}
    runs = max(1, n_orderings)
    try:
        for r in range(runs):
            print(f"Running BPLL for run {r} of {runs}")
            learned = mln.learn(
                dbs,
                method=LearningMethods.BPLL,
                prior_stdev=prior_stdev,
                multicore=multicore,
                optimizer="bfgs",
                maxiter=maxiter,
                gtol=gtol,
                verbose=verbose,
            )
            for _idx, f in learned.iterformulas():
                accumulated[str(f)] = accumulated.get(str(f), 0.0) + float(f.weight)
    finally:
        if _orig_pool is not None:
            _multidb.Pool = _orig_pool

    for canonical, total in accumulated.items():
        cand = by_canonical.get(canonical)
        if cand is not None:
            cand.weight = total / runs

    return candidates
