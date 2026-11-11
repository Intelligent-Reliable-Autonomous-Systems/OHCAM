"""LAMP with Alchemy weight learning ("lamp2").

Same four steps as :mod:`lamp_agent`, set up as close to Zhuo et al. (2010) as
the available tools allow:

* Step 3 runs Alchemy's generative WPLL learner, the system the paper used,
  instead of pracmln (see :mod:`alchemy_runner` for how its settings map to the
  paper's Algorithm 4).
* Step 2 by default generates F1a preconditions (positive and negated
  literals, the paper's "any literal p"), F2/F3 effects and F4/F5 conditional
  effects, all with universally quantified free variables. The paper's F1b
  implication preconditions and existentially quantified conditions are
  available (``precondition_implications`` / ``existential_conditions``) but
  off.

Configuration is read from the experiment's ``lamp2`` approach entry. It takes
the same Step 1/2/4 keys as ``lamp`` (with the defaults below), and for Step 3:

* ``prior_stdev``       - Gaussian prior standard deviation (default 100,
                          Alchemy's generative default).
* ``equal_pred_weight`` - weight predicates equally in WPLL (default True).
* ``add_unit_clauses``  - let Alchemy add per-predicate unit clauses (default
                          False; the paper's MLN holds only the candidates).
* ``state_pll``         - score only the state predicates in WPLL, so actions
                          and the successor relation are evidence (default
                          False; the paper's WPLL covers all atoms).
* ``max_iter`` / ``conv_thresh`` - L-BFGS-B iteration cap / fractional WPLL
                          change to stop at (defaults 10000 / 1e-5, Alchemy's).
* ``learnwts``          - path to Alchemy's ``learnwts`` binary (default
                          ``third_party/alchemy2/bin/learnwts``).
* ``keep_files``        - keep Alchemy's .mln/.db/log files next to the learned
                          model (default False).
* ``extend_fixed_preconditions`` - with fixed preconditions, keep the initial
                          domain's and add learned ones (default True).
* ``learner``           - ``alchemy`` (default) or ``wpll``, the formula-level
                          WPLL of :mod:`wpll_runner`, which takes
                          ``optimizer`` (``algorithm4``, the paper's, or
                          ``lbfgs``), ``n_iterations``, ``step_size`` and
                          ``n_orderings`` (defaults 100 / 0.01 / 5).
"""

from __future__ import annotations

from ohcam.baselines.offline.lamp import alchemy_runner, wpll_runner
from ohcam.baselines.offline.lamp.lamp_agent import LAMPAgent


class LAMP2Agent(LAMPAgent):
    """LAMP with Alchemy weight learning."""

    DEFAULTS = {
        "threshold": 0.5,
        "max_free_vars": 1,
        "precondition_implications": False,
        "precondition_universals": True,
        "negative_preconditions": True,
        "conditional_effects": True,
        "existential_conditions": False,
        "prior_stdev": 100.0,
        "extend_fixed_preconditions": True,
    }
    SUCC_NAME = "nxt"

    def __init__(self, dataset, data_source: str, approach_key: str | None = None):
        super().__init__(dataset, data_source, approach_key=approach_key or "lamp2")
        cfg = dataset.get_approach_cfg(self.name)
        self.equal_pred_weight = cfg.get("equal_pred_weight", True)
        self.add_unit_clauses = cfg.get("add_unit_clauses", False)
        self.state_pll = cfg.get("state_pll", False)
        self.max_iter = cfg.get("max_iter", 10000)
        self.conv_thresh = cfg.get("conv_thresh", 1e-5)
        self.learnwts = cfg.get("learnwts", None)
        self.keep_files = cfg.get("keep_files", False)
        self.learner = cfg.get("learner", "alchemy")
        self.optimizer = cfg.get("optimizer", "algorithm4")
        self.n_iterations = cfg.get("n_iterations", 100)
        self.step_size = cfg.get("step_size", 0.01)
        self.n_orderings = cfg.get("n_orderings", 5)
        self._n_learned = 0

    def _learn_weights(self, signature, naming, candidates):
        if self.learner == "wpll":
            return wpll_runner.learn_weights(
                signature,
                naming,
                candidates,
                self._all_encoded,
                optimizer=self.optimizer,
                n_iterations=self.n_iterations,
                step_size=self.step_size,
                n_orderings=self.n_orderings,
                prior_stdev=self.prior_stdev if self.optimizer == "lbfgs" else None,
                equal_pred_weight=self.equal_pred_weight,
                state_pll=self.state_pll,
            )
        workdir = None
        if self.keep_files:
            workdir = str(self.learned_model_path.parent / f"alchemy-{self._n_learned}")
        self._n_learned += 1
        return alchemy_runner.learn_weights(
            signature,
            naming,
            candidates,
            self._all_encoded,
            prior_stdev=self.prior_stdev,
            equal_pred_weight=self.equal_pred_weight,
            add_unit_clauses=self.add_unit_clauses,
            state_pll=self.state_pll,
            max_iter=self.max_iter,
            conv_thresh=self.conv_thresh,
            learnwts=self.learnwts,
            workdir=workdir,
        )
