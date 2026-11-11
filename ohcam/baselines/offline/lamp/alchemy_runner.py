"""Step 3 of LAMP with Alchemy: ``learn_weights`` (paper Section 4.3).

The paper learns candidate-formula weights by maximizing the weighted
pseudo-log-likelihood (WPLL) and states that it "exploit[s] the Alchemy System
of MLN to calculate and optimize the score of WPLL". This backend runs
Alchemy's generative weight learner (``learnwts -g``) on the candidate formulas
(Step 2) and the situation-labelled databases (Step 1).

Correspondence with the paper:

* Objective: Alchemy's generative learner optimizes WPLL, by default weighting
  each predicate's atoms equally (``equal_pred_weight``; the "W" in WPLL).
* Per-trace counting: with ``-multipleDatabases`` every database (plan trace)
  is its own domain, so true groundings are counted within one trace only, as
  the paper requires ("we count the true instantiations from one individual DB,
  instead of among different DBs").
* Optimizer: Algorithm 4 runs N epochs of fixed-step gradient ascent over the
  databases and averages five random database orderings. Alchemy instead runs
  L-BFGS-B on the sum of the per-database WPLLs, i.e. on the same objective
  Algorithm 4 ascends, to convergence; the result is order independent, so no
  ordering average is needed. The Alchemy binary does not expose per-database
  gradients, so Algorithm 4's online loop itself cannot be reproduced with it.
* Prior: the paper does not mention one; Alchemy's generative default (a
  zero-mean Gaussian with standard deviation 100) is kept. It is weak enough to
  be nearly unregularized but keeps weights of always-satisfied formulas finite.
* Unit clauses: Alchemy adds a unit clause per predicate by default. The paper's
  MLN contains only the candidate formulas (cf. its Example 6), so they are
  omitted (``add_unit_clauses``).
* Clauses: Alchemy converts each formula to CNF and learns one weight per
  clause; the formula's weight, which Step 4 thresholds, is their sum (as
  Alchemy reports it).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile

from ohcam.baselines.offline.lamp.encoding import EncodedTrace
from ohcam.baselines.offline.lamp.formulas import CandidateFormula
from ohcam.baselines.offline.lamp.signature import (
    DomainSignature,
    MLNNaming,
    predicate_declarations,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, os.pardir)
)
#: Prebuilt Alchemy 2 binaries (github.com/PhDP/alchemy2 release 1.0).
DEFAULT_LEARNWTS = os.path.join(_REPO_ROOT, "third_party", "alchemy2", "bin", "learnwts")

# A formula's learned weight in the output .mln: ``// <weight>  <formula>``.
_FORMULA_WEIGHT = re.compile(r"^// (\S+)\s+(.*)$")


def _normalize(formula: str) -> str:
    return re.sub(r"\s+", "", formula)


def learn_weights(
    signature: DomainSignature,
    naming: MLNNaming,
    candidates: list[CandidateFormula],
    encoded: list[EncodedTrace],
    prior_stdev: float = 100.0,
    equal_pred_weight: bool = True,
    add_unit_clauses: bool = False,
    state_pll: bool = False,
    max_iter: int = 10000,
    conv_thresh: float = 1e-5,
    learnwts: str | None = None,
    workdir: str | None = None,
) -> list[CandidateFormula]:
    """Learn a weight for each candidate formula with Alchemy; returns the same objects.

    With ``state_pll`` the pseudo-log-likelihood covers only the state
    predicates; actions and the successor relation are conditioning evidence.

    ``naming`` must not use ``succ`` for the successor predicate (an Alchemy
    built-in). Files are written to ``workdir`` when given (and kept), otherwise
    to a temporary directory.
    """
    if naming.SUCC == "succ":
        raise ValueError("Alchemy reserves 'succ'; build the naming with MLNNaming(succ=...)")
    learnwts = learnwts or DEFAULT_LEARNWTS
    if not os.path.isfile(learnwts):
        raise FileNotFoundError(
            f"Alchemy learnwts not found at {learnwts}. Unzip the alchemy2 Linux binaries "
            "into third_party/alchemy2/bin."
        )
    if not encoded:
        logger.warning("LAMP: no databases to learn from; weights stay at 0.")
        return candidates

    if workdir is None:
        with tempfile.TemporaryDirectory(prefix="lamp-alchemy-") as tmp:
            return learn_weights(
                signature, naming, candidates, encoded, prior_stdev=prior_stdev,
                equal_pred_weight=equal_pred_weight, add_unit_clauses=add_unit_clauses,
                state_pll=state_pll, max_iter=max_iter, conv_thresh=conv_thresh, learnwts=learnwts, workdir=tmp,
            )

    os.makedirs(workdir, exist_ok=True)
    mln_path = os.path.join(workdir, "lamp.mln")
    out_path = os.path.join(workdir, "learned.mln")
    log_path = os.path.join(workdir, "learnwts.log")
    with open(mln_path, "w") as f:
        f.write("\n".join(predicate_declarations(signature, naming)) + "\n\n")
        for cand in candidates:
            f.write(f"0 {cand.mln_string()}\n")
    db_paths = []
    for i, et in enumerate(encoded):
        path = os.path.join(workdir, f"trace{i}.db")
        with open(path, "w") as f:
            f.write(et.db_text + "\n")
        db_paths.append(path)

    cmd = [
        learnwts, "-g", "-multipleDatabases",
        "-i", mln_path, "-o", out_path, "-t", ",".join(db_paths),
        "-priorStdDev", str(prior_stdev),
        "-gMaxIter", str(max_iter), "-gConvThresh", str(conv_thresh),
    ]
    if not add_unit_clauses:
        cmd.append("-noAddUnitClauses")
    if not equal_pred_weight:
        cmd.append("-gNoEqualPredWt")
    if state_pll:
        cmd += ["-ne", ",".join(naming.pred(p.name) for p in signature.predicates)]

    print(f"Running Alchemy learnwts on {len(candidates)} candidates, {len(db_paths)} databases")
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            returncode = proc.wait()
        finally:
            # A learning-time budget (TimeBudgetExceeded) unwinds through here.
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    with open(log_path) as log:
        log_text = log.read()
    if returncode != 0 or "ERROR" in log_text:
        tail = "\n".join(log_text.splitlines()[-20:])
        raise RuntimeError(f"Alchemy learnwts failed (exit {returncode}):\n{tail}")

    # Alchemy writes the formulas back in input order (unit clauses, if added,
    # are extra entries), so match candidates to output entries sequentially.
    learned: list[tuple[str, float]] = []
    with open(out_path) as f:
        for line in f:
            m = _FORMULA_WEIGHT.match(line.strip())
            if m:
                try:
                    learned.append((_normalize(m.group(2)), float(m.group(1))))
                except ValueError:
                    pass  # a comment line, not a weight
    pos = 0
    missing = 0
    for cand in candidates:
        key = _normalize(cand.mln_string())
        j = pos
        while j < len(learned) and learned[j][0] != key:
            j += 1
        if j == len(learned):
            missing += 1
            cand.weight = 0.0
            continue
        cand.weight = learned[j][1]
        pos = j + 1
    if missing:
        logger.warning("Alchemy returned no weight for %d of %d candidates", missing, len(candidates))
    return candidates
