from dataclasses import dataclass
from typing import Any, ClassVar

@dataclass
class OHCAMConfig:
    # Main tuning parameters
    noise: float = 0.00000001
    r"""The expected noise tolerance for perception and execution.

    Corresponds to \epsilon in the paper.
    """
    prior_decay: float = 0.1
    r"""The decay factor for the prior on the complexity of the hypotheses.

    The prior of a hypothesis decays exponentially with the number of conjunctive terms in the antecedent.

    Corresponds to \alpha = \beta in the paper.
    """
    hypothesis_expansion_target: int = 128
    """The target number of active hypotheses to expand to for diversity.

    Corresponds to n in the paper.
    """
    max_planning_time: float = 5.0
    """The maximum time to plan for each action."""
    mc_rollouts: int = 1000
    """The number of imagined rollouts to consider at each time step.

    Corresponds to N in the paper.
    """
    mc_horizon: int = 4
    """The number of steps to imagine for each rollout.

    Corresponds to k in the paper.
    """
    mc_k_per_step: int = 6
    r"""The number of actions to consider at each time step for each rollout.

    Corresponds to \eta in the paper.
    """
    exploration_baseline_entropy: float = 0.0001
    r"""The baseline entropy for the exploration policy.

    Corresponds to \gamma in the paper.
    """
    # Flags
    allow_disjunctions: bool = False
    """Whether to greedily search for a disjunctive (DNF) explanation of conditions, instead of only the single best condition."""
    fix_init_precondition: bool = False
    """Whether the precondition terms of the initial model should be fixed."""
    combine_preconditions: bool = True
    """Whether to use a safe overapproximation of the preconditions."""
    enforce_inequality: bool = False
    """Whether to enforce inequality constraints between action variables and unidentifiable variables."""

    # Allocation
    condition_buffer_size: int = 512
    """The initial buffer size for the condition hypotheses."""
    data_buffer_size: int = 128
    """The initial buffer size for storing data predictions for each condition.

    Memory scales with condition_buffer_size * data_buffer_size.
    It will automatically grow as data is observed.
    """
    max_hypotheses: int = 100000
    """The maximum number of hypotheses to expand as a failsafe."""
    expand_only_tested: bool = True
    """Whether to refine only hypotheses that have been tested, i.e. whose antecedent held in some observation.
    Untested hypotheses (e.g. a precondition needing calibrate's own effect, or A^B never seen together) stay, but
    their refinements, untested too, aren't added, leaving the expansion budget for testable hypotheses."""
    bound_unfixable_fp: bool = True
    """With expand_only_tested, whether the refinement bound counts false positives that no seen literal value could
    exclude as permanent. Off, one observation can make every conjunction of its literal values a candidate."""
    max_unvisited_hypothesis_fraction: float = 1.0
    """The largest fraction of the hypothesis_expansion_target hypotheses that may need a literal value never seen in
    the data. No observation can falsify those (e.g. an action's own effect as its precondition before it first
    succeeds), so without a cap they can fill the budget and crowd out the testable ones. 1 disables the cap."""

    # Belief, quantification and utility settings
    inactive_posterior_threshold: float = 1e-6
    """The threshold for the posterior probability of inactive hypotheses to be considered inactive."""

    max_uqvs: int = 2
    """The maximum number of unidentifiable variables to consider for each effect literal."""
    uqv_chain_only: bool = True
    """Whether to only consider quantified chains that are grounded."""
    uqv_chain_allow_empty: bool = True
    """Whether to allow empty quantified chains."""
    unidentifiable_effect_weight: float = 1
    """The weight of the unidentifiable effect in the utility function."""
    precondition_weight: float = 1
    """The weight of the precondition in the utility function.

    This is used to balance the importance of the precondition and the effect.
    """
    exploration_qsets: int = 0
    """The number of exploratory quantified hypothesis sets per action, for effects on unknown objects. 0 disables."""

    mc_max_action_sample_tries: int = 4
    """How many patterns to try for an action sampled in a rollout before falling back to a random grounding."""
    mc_step_greedy_temp: float = 1.0
    """The softmax temperature over the utilities of the actions considered at each rollout step."""
    mc_sample_visited_preconditions: bool = True
    """Whether rollouts sample each action's precondition only from hypotheses whose literal values were all seen in
    the data. One that needs an unseen value (e.g. calibrate's own effect, before it first succeeds) matches no known
    state, so it would only propose random groundings and imagine the action failing everywhere. This changes which
    actions rollouts propose and what they imagine, not their utility, which uses the full posterior."""
    mc_object_reuse_prob: float = 0.5
    """The probability that an action sampled in a rollout prefers objects the rollout already acted on, so rollouts
    chain actions on the same objects (e.g. switch_on, calibrate, then take_image with one instrument)."""

    exploration_relax_precondition_prob: float = 0.0
    """The probability of dropping one term of a sampled precondition when proposing an action."""
    exploration_high_ent_prob: float = 0.0
    """The probability of also requiring a high-entropy literal when proposing an action."""

    _instance: "ClassVar[OHCAMConfig | None]" = None

    @classmethod
    def instance(cls) -> "OHCAMConfig":
        if cls._instance is None:
            cls._instance = OHCAMConfig()
        return cls._instance

    def configure(self, **overrides: Any) -> None:
        """Override config options by keyword."""
        for key, value in overrides.items():
            if not hasattr(self, key):
                raise ValueError(f"Unknown OHCAMConfig option: {key}")
            setattr(self, key, value)