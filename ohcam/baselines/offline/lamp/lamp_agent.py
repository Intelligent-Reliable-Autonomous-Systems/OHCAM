"""Offline learning agent implementing LAMP (Zhuo et al. 2010).

The agent wires together the four steps of the paper's Algorithm 1:

1. ``encoding.TraceEncoder``      - encode plan traces as situation-labelled
                                    MLN databases (Section 4.1).
2. ``formulas.FormulaGenerator``  - generate the candidate formulas F1-F5
                                    (Section 4.2).
3. ``mln_runner.learn_weights``   - learn formula weights by WPLL with pracmln
                                    (Section 4.3).
4. ``model_builder.attain_models``- threshold and assemble the PDDL action
                                    model (Section 4.4).

Configuration is read from the experiment's ``lamp`` approach entry via
``dataset.get_approach_cfg("lamp")``. Recognized keys (all optional):

* ``threshold``                 - weight threshold ``delta`` (default 0.5).
* ``max_free_vars``             - cap on free variables per formula (default 1).
* ``learn_preconditions``       - learn preconditions too (default True, but
                                  False when the experiment fixes preconditions
                                  without ``extend_fixed_preconditions``).
* ``extend_fixed_preconditions`` - when the experiment fixes preconditions, keep
                                  them and add the learned preconditions instead
                                  of discarding those (default False).
* ``precondition_implications`` - generate F1b implication preconditions
                                  (default False; the paper's F1b, enable for
                                  domains with implicative preconditions).
* ``precondition_universals``   - allow universally quantified (free-variable)
                                  preconditions (default False). Set False to
                                  restrict preconditions to plain conjunctions
                                  of parameter-bound literals.
* ``conditional_effects``       - generate F4/F5 conditional effects (default
                                  True).
* ``existential_conditions``    - allow existential quantifiers in conditional-
                                  effect conditions (default False).
* ``negative_preconditions``    - also propose negated literals as F1a
                                  preconditions (default False). Set False to
                                  forbid existentials entirely.

  To match the effect-only expressiveness of SAM-style learners (conditional
  and universally quantified effects, simple preconditions, no existentials),
  set ``precondition_implications: false``, ``precondition_universals: false``
  and ``existential_conditions: false`` with ``conditional_effects: true``.
* ``prior_stdev``               - Gaussian weight prior / regularizer (default
                                  1.0).
* ``num_cores``                 - worker processes for MLN weight learning
                                  (default 1 = single-threaded). BPLL's per-
                                  database statistics parallelize near-linearly,
                                  so this is the main speed lever. Values > 1
                                  cap pracmln's pool to that many cores.
* ``maxiter`` / ``gtol``        - BFGS iteration cap / gradient tolerance for
                                  the weight optimizer (defaults 100 / 1e-2).
* ``ensure_nonempty``           - enforce constraint A3 (default False).
* ``max_transitions``           - cap on encoded transitions (bounds MLN size).
* ``max_traces``                - subsample the first N traces (default all).
* ``n_orderings``               - learning runs to average (default 1).
"""

from __future__ import annotations

from ohcam.baselines.offline.lamp.encoding import TraceEncoder
from ohcam.baselines.offline.lamp.formulas import FormulaGenerator
from ohcam.baselines.offline.lamp.encoding import EncodedTrace
from ohcam.baselines.offline.lamp.model_builder import (
    ActionModel,
    attain_models,
    build_domain_pddl,
)
from ohcam.baselines.offline.lamp.signature import (
    DomainSignature,
    MLNNaming,
)
from ohcam.baselines.offline.offline_agent import OfflineAgent
from ohcam.dataset import ExperimentDataset
from ohcam.trace import Trace
from unified_planning.io import PDDLReader
from unified_planning.model import Problem


class LAMPAgent(OfflineAgent):
    """LAMP (Learning Action Models from Plan traces), Zhuo et al. 2010."""

    # Each call re-learns from every trace so far, so checkpoints can be learned independently (batch mode)
    relearns_from_scratch = True

    #: Defaults for the approach config, overridden by its entries.
    DEFAULTS: dict = {}
    #: MLN name of the successor predicate (None keeps ``MLNNaming.SUCC``).
    SUCC_NAME: str | None = None

    def __init__(self, dataset: ExperimentDataset, data_source: str, approach_key: str | None = None):
        self.dataset = dataset
        self._name = approach_key or "lamp"
        self.data_source = data_source
        cfg = {**self.DEFAULTS, **dataset.get_approach_cfg(self.name)}

        self.threshold = cfg.get("threshold", 0.5)
        self.max_free_vars = cfg.get("max_free_vars", 1)
        self.precondition_implications = cfg.get("precondition_implications", False)
        self.precondition_universals = cfg.get("precondition_universals", False)
        self.conditional_effects = cfg.get("conditional_effects", True)
        self.existential_conditions = cfg.get("existential_conditions", False)
        self.negative_preconditions = cfg.get("negative_preconditions", False)
        self.prior_stdev = cfg.get("prior_stdev", 1.0)
        self.num_cores = cfg.get("num_cores", 1)
        self.maxiter = cfg.get("maxiter", 100)
        self.gtol = cfg.get("gtol", 1e-2)
        self.ensure_nonempty = cfg.get("ensure_nonempty", False)
        self.max_transitions = cfg.get("max_transitions", None)
        self.max_traces = cfg.get("max_traces", None)
        self.n_orderings = cfg.get("n_orderings", 1)
        # When the experiment fixes preconditions, only effects are learned and
        # the initial domain's preconditions are preserved (cf. OHCAM's
        # ``fix_init_precondition``).
        self.fixed_preconditions = bool(getattr(dataset, "fixed_preconditions", False))
        # With ``extend_fixed_preconditions``, fixed preconditions are kept and
        # learned preconditions are added to them, so learning stays on.
        self.extend_fixed_preconditions = cfg.get("extend_fixed_preconditions", False)
        self.learn_preconditions = cfg.get(
            "learn_preconditions",
            not self.fixed_preconditions or self.extend_fixed_preconditions,
        )

        self.learned_model_path = dataset.get_approach_domain_path(
            self.name, data_source
        )
        self._domain_pddl: str | None = None

        # Cumulative state (mirrors ConditionalSAMAgent.all_observations): each
        # ``learn_offline`` call appends the new traces' encoded databases and
        # re-learns from everything seen so far, so the agent works as a drop-in
        # under the runner's ``--checkpoint-freq`` loop (which feeds it disjoint
        # batches). The signature/naming are built once and reused so the
        # accumulated databases stay consistent with the candidate formulas.
        self._all_encoded: list[EncodedTrace] = []
        self._setup: tuple | None = None

    @property
    def name(self) -> str:
        return self._name

    def _ensure_setup(self) -> tuple:
        """Build (and cache) the signature, naming, encoder and generator."""
        if self._setup is None:
            initial = self.dataset.initial_domain
            signature = DomainSignature.from_problem(initial)
            naming = MLNNaming(succ=self.SUCC_NAME)
            encoder = TraceEncoder(
                signature, naming, max_transitions=self.max_transitions
            )
            generator = FormulaGenerator(
                signature,
                naming,
                max_free_vars=self.max_free_vars,
                learn_preconditions=self.learn_preconditions,
                precondition_implications=self.precondition_implications,
                precondition_universals=self.precondition_universals,
                conditional_effects=self.conditional_effects,
                existential_conditions=self.existential_conditions,
                negative_preconditions=self.negative_preconditions,
            )
            self._setup = (initial, signature, naming, encoder, generator)
        return self._setup

    def learn_offline(self, traces: list[Trace]) -> None:
        if self.max_traces is not None:
            traces = traces[: self.max_traces]

        initial, signature, naming, encoder, generator = self._ensure_setup()

        # Step 1: encode the new traces and accumulate them (cumulative learning).
        self._all_encoded.extend(encoder.encode_traces(traces))
        if not self._all_encoded:
            return

        print(f"Generating candidates for {len(self._all_encoded)} traces")
        # Step 2: generate candidate formulas F1-F5 (fresh, zero-weight objects).
        candidates = generator.generate()

        print(f"Generated {len(candidates)} candidates. Learning weights...")

        # Step 3: learn weights (WPLL) over everything so far. A timeout during
        # this call propagates out; ``self._domain_pddl`` is left untouched, so
        # ``get_learned_domain`` still returns the last completed model (or an
        # empty one if none has completed yet).
        candidates = self._learn_weights(signature, naming, candidates)

        print(f"Learned weights for {len(candidates)} candidates. Assembling model...")

        # Step 4: select above-threshold formulas and assemble the PDDL model.
        models = attain_models(
            signature,
            candidates,
            threshold=self.threshold,
            ensure_nonempty=self.ensure_nonempty,
        )
        print(f"Assembled model. Writing to {self.learned_model_path}")
        self._domain_pddl = build_domain_pddl(
            signature,
            models,
            domain_name=initial.name or "domain",
            initial_problem=initial,
            fixed_preconditions=self.fixed_preconditions,
            extend_fixed_preconditions=self.extend_fixed_preconditions,
        )

    def _learn_weights(self, signature, naming, candidates):
        """Step 3 with pracmln's BPLL learner."""
        from ohcam.baselines.offline.lamp.mln_runner import learn_weights

        return learn_weights(
            signature,
            naming,
            candidates,
            self._all_encoded,
            n_orderings=self.n_orderings,
            prior_stdev=self.prior_stdev,
            num_cores=self.num_cores,
            maxiter=self.maxiter,
            gtol=self.gtol,
        )

    def get_learned_domain(self) -> Problem:
        # Recover whatever is available: the last completed model, or - if a
        # timeout struck before any learning finished - a valid empty-effect
        # domain assembled straight from the signature (rather than raising).
        if self._domain_pddl is None:
            initial, signature, _naming, _encoder, _generator = self._ensure_setup()
            empty = {a.name: ActionModel(a.name, a.params) for a in signature.actions}
            self._domain_pddl = build_domain_pddl(
                signature,
                empty,
                domain_name=initial.name or "domain",
                initial_problem=initial,
                fixed_preconditions=self.fixed_preconditions,
                extend_fixed_preconditions=self.extend_fixed_preconditions,
            )
        self.learned_model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.learned_model_path, "w") as f:
            f.write(self._domain_pddl)
        return PDDLReader().parse_problem(str(self.learned_model_path))
