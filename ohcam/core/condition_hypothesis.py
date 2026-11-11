from collections import Counter, defaultdict
import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, Literal

import numpy as np

if TYPE_CHECKING:
    from ohcam.core.learner import OHCAMConfig

from ohcam.core.pddl_repr import DNF, Atom, Condition, Conjunction, Outcome
from ohcam.core.utils import get_binary_entropy


def enumerate_conjunctive_conditions(vocab: list[Atom], outcomes: list[Outcome], max_conjunctions: int) -> Iterator[Condition]:
    r"""Enumerate all conjunctive conditions of up to max_conjunctions length.

    This scales according to the formula:
    \sum_{i=1}^{max_conjunctions} \binom{len(vocab)}{i} * 2^i
    """
    for i in range(1, max_conjunctions + 1):
        for combination in itertools.combinations(vocab, i):
            for assignment in itertools.product([True, False], repeat=len(combination)):
                conjunction = Conjunction({atom: value for atom, value in zip(combination, assignment)})
                for outcome in outcomes:
                    yield Condition(conjunction, outcome)

def condition_complexity_prior(condition: Condition, prior_decay: float) -> float:
    """Compute the prior weight of a condition."""
    if isinstance(condition.antecedent, bool):
        if condition.antecedent:
            return 0.5 # unconditional effect
        else:
            return 1.0 # no effect
    if isinstance(condition.antecedent, DNF):
        return float(np.prod(list(
            prior_decay**len(conjunction) for conjunction in condition.antecedent)
        ))
    if isinstance(condition.antecedent, Conjunction):
        return prior_decay**len(condition.antecedent)
    raise ValueError(f"Invalid antecedent: {condition.antecedent}")

class ConditionHypothesisSet:

    TP_IDX = 0
    TN_IDX = 1
    FP_IDX = 2
    FN_IDX = 3
    OCCUPIED_IDX = 4
    DEPTH_IDX = 5
    EFFECT_SIGN_IDX = 6
    EXPANDED_IDX = 7
    TP_PRED = 1
    TN_PRED = 2
    FP_PRED = 3
    FN_PRED = 4
    VACUOUS_PRED = 5

    def __init__(self,
            name: str,
            consequent: Atom | Literal[Outcome.APPLICABLE],
            literal_vocab: list[Atom],
            fixed_conditions: Conjunction | None = None,
            inactive_hypothesis_threshold: float = 1e-6, # 0.0001% probability mass
            noise_level: float = 0.0,
            depth_prior: float = 0.05,
            particle_expansion_target: int = 128,
            condition_buffer_size: int = 1024,
            data_buffer_size: int = 256,
            allow_disjunctions: bool = False,
            max_hypotheses: int = 100000,
            combine_preconditions: bool = True,
            required_variables: list[str] = [],
            max_unvisited_fraction: float = 0.5,
            expand_only_tested: bool = True,
            bound_unfixable_fp: bool = True,
    ):
        """

        Args:
            name: The name of the condition hypothesis set.
            consequent: The literal that the condition hypothesis set is about (or applicable for precondition).
            literal_vocab: The literal vocabulary of the condition hypothesis set that can be used in conjunctive conditions.
            inactive_hypothesis_threshold: The threshold for inactive hypotheses (probability mass), when to stop updating a hypothesis.
            noise_level: The noise level for the condition hypothesis set.
            depth_prior: The exponent base for the prior on the depth of the hypotheses.
            particle_expansion_target: The number of top hypotheses (n) to gather; branch-and-bound expansion prunes refinements that cannot beat the n-th best posterior.
            condition_buffer_size: The initial capacity for hypotheses; grows as needed.
            data_buffer_size: The initial capacity for observations; grows as needed.
            allow_disjunctions: Whether get_best_conditions should search for a disjunctive (DNF) explanation via score_disjunctions.
            max_unvisited_fraction: The largest fraction of the top n that hypotheses with an unvisited literal (one
                whose value never held in the data, so no observation can test it) may fill; 1 disables the cap.
            expand_only_tested: Whether to refine only hypotheses that have been tested, i.e. whose antecedent held in
                some observation. An untested hypothesis is kept, but its refinements, all untested too, aren't added.
        """
        self.name = name
        self.consequent = consequent
        self.fixed_conditions = fixed_conditions or Conjunction({})
        self.literal_vocab = {v: i for i, v in enumerate(lv for lv in literal_vocab if lv not in self.fixed_conditions)}
        self.inactive_hypothesis_threshold = inactive_hypothesis_threshold
        self._inactive_log_threshold = np.log(inactive_hypothesis_threshold) if inactive_hypothesis_threshold > 0.0 else -np.inf
        self.noise_level = noise_level
        self.depth_prior = depth_prior
        self.particle_expansion_target = particle_expansion_target
        self._condition_buffer_size = condition_buffer_size
        self._data_buffer_size = data_buffer_size
        self._allow_disjunction = allow_disjunctions
        self.max_hypotheses = max_hypotheses
        self.combine_preconditions = combine_preconditions
        self.max_unvisited_fraction = max_unvisited_fraction
        self.expand_only_tested = expand_only_tested
        self.bound_unfixable_fp = bound_unfixable_fp
        self._is_precondition = consequent == Outcome.APPLICABLE
        self._dataset: list[tuple[dict[Atom, bool], dict[str, str], dict[Atom, bool], bool, bool, bool, int]] = []
        self._data_belief_idx = 0
        self._data_conjunction_arr: np.ndarray = np.zeros((self._data_buffer_size, len(literal_vocab)), dtype=np.int8)
        self._data_global_indices: np.ndarray = np.full(self._data_buffer_size, -1, dtype=np.int32)
        self._data_predictions: np.ndarray = np.zeros((self._condition_buffer_size, self._data_buffer_size), np.uint8)
        """_data_predictions[condition_index, data_index] = 0 if not evaluated, 1 if TP, 2 if TN, 3 if FP, 4 if FN, 5 if vacuous"""

        self._conditions: set[Condition] = set()
        self._conditions_by_index: dict[int, Condition] = {}
        self._index_by_condition: dict[Condition, int] = {}
        self._conjunction_arr: np.ndarray = np.zeros((condition_buffer_size, len(literal_vocab)), dtype=np.int8)

        self._counts = np.zeros((condition_buffer_size, 8), dtype=np.int16) # Indexed by the *_IDX constants above

        self._log_prior = np.full(condition_buffer_size, -np.inf)
        self._log_likelihood = np.full(condition_buffer_size, -np.inf)
        self._log_posterior = np.full(condition_buffer_size, -np.inf)
        self._expansion_log_threshold = np.full(condition_buffer_size, np.inf)
        """Pruning threshold in effect when a hypothesis was last expanded. +inf = never expanded;
        a partially expanded hypothesis becomes re-expandable when the bound drops below this value."""
        self._posterior_normalization = 0.0
        self._next_condition_index = 0

        self._required_variables = required_variables

        self._sort_indices = np.full(condition_buffer_size, -1, dtype=np.int32)

        self._pattern_scores: dict[Conjunction, float] = {}

        self._disjunction: list[int] = []
        """Condition indices selected by the last call to score_disjunctions, in selection order."""

        # Branch-and-bound expansion statistics (cumulative over the lifetime of the set).
        self._expansion_events_by_depth: Counter[int] = Counter()
        """Parent depth -> number of expansion events (a node may be expanded more than once
        when the pruning threshold later drops and re-opens it)."""
        self._children_generated_by_depth: Counter[int] = Counter()
        """Parent depth -> number of new hypotheses generated by expanding nodes at that depth."""
        self._expanded_node_indices: set[int] = set()
        """Indices of every node expanded at least once (distinct nodes, ignoring re-expansions)."""
        self._literals_pruned_events: int = 0
        """Cumulative count of (literal, value) children skipped because their singleton bound was pruned."""
        self._visited_literals = np.zeros((2, len(literal_vocab)), dtype=bool)
        """_visited_literals[0 / 1, i]: whether literal i was false / true in some state of the data, as of the last
        expansion. Partially expanded hypotheses are reopened when it grows, since the cap on unvisited ones changes."""
        self._visited_cache: np.ndarray | None = None
        self._visited_cache_idx = None

    def add_condition(self, condition: Condition, prior_weight: float) -> tuple[bool, int]:
        """Add a condition to the hypothesis set and return the index of the condition."""
        if condition in self._conditions:
            return False, self._index_by_condition[condition]
        if self._required_variables and isinstance(condition.antecedent, DNF):
            remaining_vars = {*self._required_variables}
            for conjunction in condition.antecedent:
                for literal in conjunction.keys():
                    for param in literal.params:
                        if param in remaining_vars:
                            remaining_vars.remove(param)
                            break
                    if not remaining_vars:
                        break
            if remaining_vars:
                return False, -1
        if self._next_condition_index >= self._condition_buffer_size:
            # Grow the buffer as needed
            new_buffer_size = 2 * self._condition_buffer_size

            new_data_predictions = np.zeros((new_buffer_size, self._data_buffer_size), np.uint8)
            new_data_predictions[:self._condition_buffer_size] = self._data_predictions
            self._data_predictions = new_data_predictions

            new_conjunction_arr = np.zeros((new_buffer_size, len(self.literal_vocab)), dtype=np.int8)
            new_conjunction_arr[:self._condition_buffer_size] = self._conjunction_arr
            self._conjunction_arr = new_conjunction_arr

            log_prior = np.full(new_buffer_size, -np.inf)
            log_prior[:self._condition_buffer_size] = self._log_prior
            self._log_prior = log_prior

            log_likelihood = np.full(new_buffer_size, -np.inf)
            log_likelihood[:self._condition_buffer_size] = self._log_likelihood
            self._log_likelihood = log_likelihood

            log_posterior = np.full(new_buffer_size, -np.inf)
            log_posterior[:self._condition_buffer_size] = self._log_posterior
            self._log_posterior = log_posterior

            expansion_log_threshold = np.full(new_buffer_size, np.inf)
            expansion_log_threshold[:self._condition_buffer_size] = self._expansion_log_threshold
            self._expansion_log_threshold = expansion_log_threshold

            counts = np.zeros((new_buffer_size, 8), dtype=np.int16)
            counts[:self._condition_buffer_size] = self._counts
            self._counts = counts

            self._condition_buffer_size = new_buffer_size

        conjunction = condition.antecedent
        if isinstance(conjunction, DNF):
            conjunction = conjunction[0]
        if isinstance(conjunction, Conjunction):
            for literal, value in conjunction.items():
                self._conjunction_arr[self._next_condition_index, self.literal_vocab[literal]] = 1 if value else -1
        elif isinstance(conjunction, bool):
            self._conjunction_arr[self._next_condition_index] = 0 # unconditional antecedent
        else:
            raise ValueError(f"Invalid antecedent: {conjunction}")
        self._conditions.add(condition)
        self._conditions_by_index[self._next_condition_index] = condition
        self._index_by_condition[condition] = self._next_condition_index

        self._counts[self._next_condition_index, :] = 0
        if condition.outcome in [Outcome.ADD_EFFECT, Outcome.APPLICABLE]:
            self._counts[self._next_condition_index, self.EFFECT_SIGN_IDX] = 1
        elif condition.outcome == Outcome.DEL_EFFECT:
            self._counts[self._next_condition_index, self.EFFECT_SIGN_IDX] = -1
        if condition.outcome == Outcome.NO_EFFECT:
            self._counts[self._next_condition_index, self.EXPANDED_IDX] = 1

        if isinstance(condition.antecedent, Conjunction):
            self._counts[self._next_condition_index, self.DEPTH_IDX] = len(condition.antecedent)
        elif isinstance(condition.antecedent, bool):
            self._counts[self._next_condition_index, self.DEPTH_IDX] = 0
        elif isinstance(condition.antecedent, DNF):
            self._counts[self._next_condition_index, self.DEPTH_IDX] = len(condition.antecedent[0])
        else:
            raise ValueError(f"Invalid antecedent: {condition.antecedent}")
        self._counts[self._next_condition_index, self.OCCUPIED_IDX] = 1

        self._log_prior[self._next_condition_index] = np.log(prior_weight)
        self._log_likelihood[self._next_condition_index] = 0.0
        self._log_posterior[self._next_condition_index] = self._log_prior[self._next_condition_index]
        self._next_condition_index = (self._next_condition_index + 1)
        return True, self._next_condition_index - 1

    def normalize(self):
        """Compute the normalization for the log weights to ensure they are a valid probability distribution."""
        self._log_posterior = self._log_prior + self._log_likelihood
        log_weights = self._log_posterior[self._active]
        log_sum = np.log(np.exp(log_weights).sum())
        self._posterior_normalization = log_sum
        active_indices = np.flatnonzero(self._active)
        self._sort_indices = active_indices[np.argsort(self._log_posterior[active_indices])[::-1]]

    def _get_state_arr(self, state: dict[Atom, bool], param_mapping: dict[str, str]) -> np.ndarray:
        state_arr = np.zeros(len(self.literal_vocab), dtype=np.int8)
        for literal, idx in self.literal_vocab.items():
            state_arr[idx] = 1 if state.get(literal.ground(param_mapping), False) else -1
        return state_arr

    def get_consequent_probability(self, param_mapping: dict[str, str], state: dict[Atom, bool], current_literal: bool) -> float:
        """Get the probability of the literal/applicability being satisfied after applying the condition in the state.

        Args:
            param_mapping: The mapping of action parameters to their values
            state: The current state
            current_literal: The current value of this candidate literal in the state (or False for precondition)
        """
        if not self.fixed_conditions.is_satisfied(param_mapping, state):
            return 1.0 if current_literal else 0.0

        delete_or_add_sign = -1 if current_literal else 1
        # select hypotheses whose effect would predict a change
        relevant_indices = self._active & (self._effect_sign == delete_or_add_sign)
        if len(relevant_indices) == 0:
            return 0.0

        state_arr = self._get_state_arr(state, param_mapping)

        # compute the posterior probability of the hypotheses
        posterior_probabilities = np.exp(self._log_posterior[relevant_indices] - self._posterior_normalization)

        conjunction_satisfied = np.all(self._conjunction_arr[relevant_indices] * state_arr >= 0, axis=1)
        cum_prob_effect_delta = np.sum(posterior_probabilities[conjunction_satisfied])

        if current_literal:
            # literal is already true. subtract probability of delete
            return 1.0 - cum_prob_effect_delta
        else:
            # literal is false. return probability of add
            return cum_prob_effect_delta

    def observe_transition(self,
        param_mapping: dict[str, str],
        state: dict[Atom, bool],
        next_state: dict[Atom, bool],
        applicable: bool,
        global_data_index: int
    ):
        if not self.fixed_conditions.is_satisfied(param_mapping, state):
            return # ignore transitions that do not satisfy the fixed conditions

        if len(self._dataset) >= self._data_buffer_size:
            new_data_buffer_size = 2 * self._data_buffer_size
            new_data_conjunction_arr = np.zeros((new_data_buffer_size, len(self.literal_vocab)), dtype=np.int8)
            new_data_conjunction_arr[:self._data_buffer_size] = self._data_conjunction_arr
            self._data_conjunction_arr = new_data_conjunction_arr
            new_data_predictions = np.zeros((self._condition_buffer_size, new_data_buffer_size), np.uint8)
            new_data_predictions[:self._condition_buffer_size, :self._data_buffer_size] = self._data_predictions
            self._data_predictions = new_data_predictions
            new_data_global_indices = np.full(new_data_buffer_size, -1, dtype=np.int32)
            new_data_global_indices[:self._data_buffer_size] = self._data_global_indices
            self._data_global_indices = new_data_global_indices
            self._data_buffer_size = new_data_buffer_size

        state_arr = self._get_state_arr(state, param_mapping)
        self._data_conjunction_arr[len(self._dataset)] = state_arr
        self._data_global_indices[len(self._dataset)] = global_data_index
        if self._is_precondition:
            prev_val = False
            next_val = applicable
        else:
            ground_literal = self.consequent.ground(param_mapping)
            prev_val = state.get(ground_literal, False)
            next_val = next_state.get(ground_literal, False)
        self._dataset.append((state, param_mapping, next_state, applicable, prev_val, next_val, global_data_index))

    def update_beliefs(self, condition_mask: np.ndarray | None = None, data_indices: np.ndarray | None = None):
        if condition_mask is None:
            condition_mask = self._occupied
        if data_indices is None:
            data_min_idx = self._data_belief_idx
            data_max_idx = len(self._dataset)
            data_indices = np.arange(data_min_idx, data_max_idx)
        prev_vals = [self._dataset[i][4] for i in data_indices]
        next_vals = [self._dataset[i][5] for i in data_indices]
        self._update_hypotheses(
            self._data_conjunction_arr[data_indices],
            prev_vals,
            next_vals,
            condition_mask,
            data_indices,
        )

        def sum_new_predictions(pred_val: int) -> np.ndarray:
            return np.sum(self._data_predictions[np.ix_(condition_mask, data_indices)] == pred_val, axis=1)
        self._counts[condition_mask, self.TP_IDX] += sum_new_predictions(self.TP_PRED)
        self._counts[condition_mask, self.TN_IDX] += sum_new_predictions(self.TN_PRED)
        self._counts[condition_mask, self.FP_IDX] += sum_new_predictions(self.FP_PRED)
        self._counts[condition_mask, self.FN_IDX] += sum_new_predictions(self.FN_PRED)
        self.normalize()
        self.update_pattern_scores()

        self._data_belief_idx = len(self._dataset)

    def _top_n_log_threshold(self) -> float:
        """The n-th best hypothesis score L^(n); -inf while fewer than n hypotheses exist.

        This is the branch-and-bound pruning threshold: a refinement is only worth
        generating if its bound exceeds the score it must beat to enter the top n.
        """
        return self._top_n_log_thresholds()[0]

    def _visited_literal_values(self) -> np.ndarray:
        """_visited[0 / 1, i]: whether literal i was false / true in some state of the data the beliefs include"""
        data = self._data_conjunction_arr[:self._data_belief_idx]
        return np.stack([(data == -1).any(axis=0), (data == 1).any(axis=0)])

    def _visited_unvisited_mask(self) -> np.ndarray:
        """_unvisited_mask for the data the beliefs include, cached until they include more or hypotheses are added"""
        key = (self._data_belief_idx, self._next_condition_index, self._condition_buffer_size)
        if self._visited_cache_idx != key:
            self._visited_cache = self._unvisited_mask(self._visited_literal_values())
            self._visited_cache_idx = key
        return self._visited_cache

    def _unvisited_mask(self, visited: np.ndarray) -> np.ndarray:
        """Mask of hypotheses whose antecedent has a literal value that never held in the data. Every observation
        falsifies such a hypothesis' antecedent, so none can test it, and it predicts no change wherever we've been."""
        conj = self._conjunction_arr[:, :visited.shape[1]]
        return np.any(((conj == 1) & ~visited[1]) | ((conj == -1) & ~visited[0]), axis=1)

    def _top_n_log_thresholds(self, visited: np.ndarray | None = None) -> tuple[float, float]:
        """The thresholds a refinement must beat to enter the top n: (for a refinement whose literals were all
        visited, for one with an unvisited literal).

        Unvisited hypotheses can't be falsified, so the irrefutable refinements of a literal that never held (such
        as an action's own effect, before it first succeeds) could otherwise fill the top n and crowd out testable
        hypotheses. So at most max_unvisited_fraction of the n count toward L^(n), the best of them, and an
        unvisited refinement must also beat the worst of those. Before any data, every literal is unvisited, and
        there is no cap.
        """
        occupied = self._occupied
        n = self.particle_expansion_target
        cap = max(1, int(self.max_unvisited_fraction * n))
        if visited is None:
            visited = self._visited_literal_values()
        if self._data_belief_idx == 0 or cap >= n:
            unvisited = np.zeros_like(occupied)
        else:
            unvisited = self._unvisited_mask(visited) & occupied
        unvisited_scores = self._log_posterior[unvisited]
        unvisited_threshold = -np.inf
        if unvisited_scores.size > cap:
            unvisited_scores = np.partition(unvisited_scores, -cap)[-cap:]
        if unvisited_scores.size >= cap and unvisited.any():
            unvisited_threshold = float(unvisited_scores.min())
        counted = np.concatenate([self._log_posterior[occupied & ~unvisited], unvisited_scores])
        if counted.size < n:
            return -np.inf, unvisited_threshold
        threshold = float(np.partition(counted, -n)[-n])
        return threshold, max(threshold, unvisited_threshold)

    def _refinement_log_bound(self) -> np.ndarray:
        """Admissible upper bound U(h) = (|C_h|+1)log(alpha) + FN_h*log(epsilon) on the
        score of any strict refinement of each hypothesis.

        Refining a conjunction only makes it fire on fewer states, so false negatives are
        permanent: every descendant keeps at least the parent's FNs and pays at least one
        more depth_prior factor. The bound is attained by a depth+1 child that fixes every
        FP without losing a TP.
        """
        depth = self._counts[:, self.DEPTH_IDX].astype(np.float64)
        fn = self._counts[:, self.FN_IDX].astype(np.float64)
        if self.expand_only_tested and self.bound_unfixable_fp and self._data_belief_idx > 0:
            # Refinements may only add literal values seen in the data, so a false positive on a datum where every
            # unseen value is the one that would exclude it is as permanent as a false negative. Without this, one
            # observation makes every conjunction of its own literal values a refinement candidate (2^|vocab|).
            data = self._data_conjunction_arr[:self._data_belief_idx]
            visited = self._visited_literal_values()
            excluding_value = (data == -1).astype(int) # the value of each literal that would make the datum fail
            fixable = np.any(visited[excluding_value, np.arange(data.shape[1])], axis=1)
            unfixable_fp = np.sum((self._data_predictions[:, :self._data_belief_idx] == self.FP_PRED) & ~fixable, axis=1)
            fn = fn + unfixable_fp
        child_log_prior = (depth + 1.0) * np.log(self.depth_prior)
        if self.noise_level > 0.0:
            fn_penalty = fn * np.log(self.noise_level)
        else:
            fn_penalty = np.where(fn == 0, 0.0, -np.inf)
        return child_log_prior + fn_penalty

    def _expansion_frontier(self, log_bounds: np.ndarray, log_threshold: float | np.ndarray) -> np.ndarray:
        """Mask of hypotheses whose refinements could still enter the top n.

        A hypothesis is on the frontier if it is not fully expanded, it has FPs a refinement
        could fix, its refinement bound beats the threshold, and (if partially expanded) the
        threshold has dropped since its last expansion. If the threshold hasn't dropped,
        pruned refinements stay pruned. With expand_only_tested, it must also have been tested
        (see _tested); it joins the frontier once data first satisfies its antecedent.
        """
        frontier = (self._occupied
            & (self._counts[:, self.EXPANDED_IDX] == 0)
            & (log_threshold < self._expansion_log_threshold)
            & (log_bounds > log_threshold))
        if self.expand_only_tested:
            frontier &= self._tested
        return frontier

    @property
    def _tested(self) -> np.ndarray:
        """Mask of hypotheses whose antecedent held in some (non-vacuous) observation, so it made a prediction there.
        Every sub-conjunction of a tested antecedent held there too, so tested hypotheses are reachable by refining
        tested ones."""
        return (self._counts[:, self.TP_IDX] + self._counts[:, self.FP_IDX]) > 0

    def try_expand(self):
        """Grow the hypothesis set with best-first branch-and-bound over the refinement tree.

        The goal is a certified top-n set (n = particle_expansion_target): expansion
        continues while some frontier hypothesis has a refinement bound U(h) above the
        n-th best score L^(n), always expanding the highest-bound hypothesis first.
        Depth is limited only by the bound: each added antecedent literal costs a
        depth_prior factor, so refinement stops paying off once that outweighs L^(n).
        """
        visited = self._visited_literal_values()
        if np.any(visited & ~self._visited_literals):
            # A literal value was seen for the first time, so the refinements that it was kept out of may be added now
            self._expansion_log_threshold[:] = np.inf
            self._visited_literals = visited
        while len(self._conditions_by_index) < self.max_hypotheses:
            log_threshold, unvisited_log_threshold = self._top_n_log_thresholds(visited)
            log_bounds = self._refinement_log_bound()
            # Every refinement of an unvisited hypothesis is unvisited
            unvisited = self._unvisited_mask(visited)
            parent_thresholds = np.where(unvisited, unvisited_log_threshold, log_threshold)
            frontier = np.flatnonzero(self._expansion_frontier(log_bounds, parent_thresholds))
            if len(frontier) == 0:
                break
            # Expand the best: highest refinement bound, ties broken by posterior then TP count
            order = np.lexsort((
                -self._counts[frontier, self.TP_IDX],
                -self._log_posterior[frontier],
                -log_bounds[frontier],
            ))
            idx_to_expand = frontier[order[0]]
            # Refresh stale beliefs before trusting the bound; the score can only drop, so re-select
            unprocessed_data_indices = np.flatnonzero(self._data_predictions[idx_to_expand, :self._data_belief_idx] == 0)
            if len(unprocessed_data_indices) > 0:
                mask = np.zeros_like(self._occupied, dtype=bool)
                mask[idx_to_expand] = True
                self.update_beliefs(mask, unprocessed_data_indices)
                continue
            self._expand_condition(idx_to_expand, parent_thresholds[idx_to_expand], log_bounds,
                                   unvisited_log_threshold, visited)

    def _expand_condition(self, index: int, log_threshold: float, log_bounds: np.ndarray,
                          unvisited_log_threshold: float | None = None, visited: np.ndarray | None = None) -> int:
        """Generate the one-literal refinements of a hypothesis, excluding pruned literals.

        A literal is excluded when its singleton (depth-1) hypothesis' refinement bound is
        pruned: the bound is monotone under refinement, so no conjunction containing that
        literal can enter the top n. If an excluded literal could pass a lower future
        threshold, the parent is left partially expanded so it becomes re-expandable when
        the threshold drops. A literal value that never held in the data (see visited) must
        beat unvisited_log_threshold instead.
        """
        condition = self._conditions_by_index[index]
        if condition.outcome == Outcome.NO_EFFECT:
            self._counts[index, self.EXPANDED_IDX] = 1
            return 0
        if isinstance(condition.antecedent, bool):
            conj = Conjunction({})
        elif isinstance(condition.antecedent, DNF):
            conj = condition.antecedent[0]
        else:
            conj = condition.antecedent

        parent_depth = len(conj)
        self._expansion_events_by_depth[parent_depth] += 1
        self._expanded_node_indices.add(int(index))

        new_indices = []
        pruned_recoverable = False
        for literal in self.literal_vocab:
            if literal == self.consequent or literal in conj.keys():
                continue
            for value in (True, False):
                literal_threshold = log_threshold
                if visited is not None and not visited[int(value), self.literal_vocab[literal]]:
                    if self.expand_only_tested and parent_depth >= 1:
                        # A literal value never seen in the data appears only in its singleton hypothesis, which is
                        # untested, until an observation shows it; then the parent is reopened (see try_expand)
                        pruned_recoverable = True
                        self._literals_pruned_events += 1
                        continue
                    literal_threshold = max(log_threshold, unvisited_log_threshold)
                singleton = Condition(Conjunction({literal: value}), condition.outcome)
                singleton_index = self._index_by_condition.get(singleton)
                if singleton_index is not None and log_bounds[singleton_index] <= literal_threshold:
                    # -inf-bounded literals can never pass any threshold, so they don't block full expansion
                    pruned_recoverable |= bool(log_bounds[singleton_index] > -np.inf)
                    self._literals_pruned_events += 1
                    continue
                new_condition = Condition(conj | {literal: value}, condition.outcome)
                added, new_idx = self.add_condition(new_condition, condition_complexity_prior(new_condition, self.depth_prior))
                if added:
                    new_indices.append(new_idx)
        self._children_generated_by_depth[parent_depth] += len(new_indices)
        if pruned_recoverable:
            self._expansion_log_threshold[index] = log_threshold
        else:
            self._counts[index, self.EXPANDED_IDX] = 1
        if len(new_indices) > 0:
            data_indices = np.arange(0, self._data_belief_idx)
            mask = np.zeros_like(self._occupied, dtype=bool)
            mask[new_indices] = True
            self.update_beliefs(mask, data_indices)
        return len(new_indices)

    def get_expansion_statistics(self) -> dict[str, Any]:
        """Report branch-and-bound expansion statistics for this hypothesis set.

        Mixes cumulative counters recorded during learning (how many expansions happened,
        broken down by the depth of the node being refined) with a snapshot of the current
        frontier (how many singleton literals survived the bound). See
        :meth:`OHCAMHypothesisSet.get_statistics` for the aggregated view.
        """
        occupied = np.flatnonzero(self._occupied)
        depths = self._counts[occupied, self.DEPTH_IDX].astype(int)
        hypotheses_by_depth = {int(d): int((depths == d).sum()) for d in np.unique(depths)} if occupied.size else {}

        # Snapshot of singleton (depth-1) survival under the current pruning threshold.
        log_threshold = self._top_n_log_threshold()
        log_bounds = self._refinement_log_bound()
        singleton_mask = self._occupied & (self._counts[:, self.DEPTH_IDX] == 1)
        surviving_singleton_mask = singleton_mask & (log_bounds > log_threshold)
        surviving_literals = set()
        for idx in np.flatnonzero(surviving_singleton_mask):
            antecedent = self._conditions_by_index[idx].antecedent
            conj = antecedent[0] if isinstance(antecedent, DNF) else antecedent
            if isinstance(conj, Conjunction):
                surviving_literals.update(conj.keys())

        expansion_events_by_depth = {int(d): int(c) for d, c in sorted(self._expansion_events_by_depth.items())}
        children_generated_by_depth = {int(d): int(c) for d, c in sorted(self._children_generated_by_depth.items())}

        best_depth = None
        if len(self._sort_indices) > 0 and self._sort_indices[0] in self._conditions_by_index:
            best_depth = int(self._counts[self._sort_indices[0], self.DEPTH_IDX])

        return {
            "num_hypotheses": int(occupied.size),
            "hypotheses_by_depth": hypotheses_by_depth,
            "max_depth_reached": int(depths.max()) if occupied.size else 0,
            "num_expansion_events": int(sum(self._expansion_events_by_depth.values())),
            "expansion_events_by_depth": expansion_events_by_depth,
            "num_nodes_expanded": len(self._expanded_node_indices),
            "num_children_generated": int(sum(self._children_generated_by_depth.values())),
            "children_generated_by_depth": children_generated_by_depth,
            "num_literals": len(self.literal_vocab),
            "num_singletons": int(singleton_mask.sum()),
            "num_surviving_singletons": int(surviving_singleton_mask.sum()),
            "num_surviving_literals": len(surviving_literals),
            "num_literals_pruned_events": int(self._literals_pruned_events),
            "best_depth": best_depth,
        }

    def _update_hypotheses(self,
            state_arr: np.ndarray,
            prev_literal_arr: np.ndarray,
            next_literal_arr: np.ndarray,
            condition_mask: np.ndarray,
            data_indices: np.ndarray
    ):
        """
        Update the belief over hypotheses on the given D data indices.

        Args:
            state_arr: The state array for the data shape=(D, len(literal_vocab),)
            prev_literal_arr: The previous value of the literal for the data shape=(D,)
            next_literal_arr: The next value of the literal for the data shape=(D,)
            condition_mask: The mask of conditions to update with shape=(condition_buffer_size,) and H true values
            data_indices: The indices of the data to update shape=(D,)
        """

        prev_literal_arr = np.asarray(prev_literal_arr, dtype=bool)
        next_literal_arr = np.asarray(next_literal_arr, dtype=bool)
        effect_sign_h = self._effect_sign[condition_mask]
        # nonvacuous_mask[h, d]: prev_literal[d] -> (effect_sign[h] <= 0), ~prev_literal[d] -> (>= 0)
        nonvacuous_mask = np.where(
            prev_literal_arr[np.newaxis, :],
            effect_sign_h[:, np.newaxis] == -1,
            effect_sign_h[:, np.newaxis] == 1,
        )

        observed_delta = prev_literal_arr != next_literal_arr  # shape=(D,)
        observed_delta_hd = observed_delta[np.newaxis, :]  # (1, D) -> (H, D)
        expected_delta = np.all(
            # conj_arr shape=(H, newaxis, len(literal_vocab))
            # state_arr shape=(newaxis, D, len(literal_vocab))
            self._conjunction_arr[condition_mask][:, np.newaxis, :] * state_arr[np.newaxis, :, :] >= 0,
            axis=-1,
        )  # shape=(H, D)

        pred_hd = np.where(
            expected_delta,
            np.where(observed_delta_hd, self.TP_PRED, self.FP_PRED),
            np.where(observed_delta_hd, self.FN_PRED, self.TN_PRED),
        )
        pred_hd = np.where(nonvacuous_mask, pred_hd, self.VACUOUS_PRED)

        # if we observe True->False, an Add sign is wrong; if we observe False->True, a Delete sign is wrong
        correct_sign_val = np.where(prev_literal_arr, -1, 1)
        wrong_sign_hd = (
            observed_delta_hd
            & (effect_sign_h[:, np.newaxis] != correct_sign_val[np.newaxis, :])
        )
        # if we observe a change in the literal, and the condition sign is wrong, it's a FN
        pred_hd = np.where(wrong_sign_hd, self.FN_PRED, pred_hd)

        self._data_predictions[np.ix_(condition_mask, data_indices)] = pred_hd

        # update posterior: only (h, d) pairs where the effect sign is informative
        pair_match = expected_delta == observed_delta_hd
        pair_likelihood = np.where(pair_match, 1.0, self.noise_level)
        with np.errstate(divide='ignore'):
            self._log_likelihood[condition_mask] += np.sum(
                np.where(nonvacuous_mask, np.log(pair_likelihood), 0.0),
                axis=1,
            )
            self._log_likelihood[condition_mask] += np.sum(
                np.where(wrong_sign_hd, np.log(self.noise_level), 0.0),
                axis=1,
            )

    def update_pattern_scores(self):
        """Identify state patterns with high belief entropy."""
        active = np.flatnonzero(self._active)
        posterior_prob = np.exp(self._log_posterior[active] - self._posterior_normalization)
        effect_sign_prob = float(np.dot(posterior_prob, self._effect_sign[active].astype(np.float64)))

        conj_a = self._conjunction_arr[active]
        w = posterior_prob[:, np.newaxis]
        pos_mass = np.sum((conj_a == 1) * w, axis=0)
        neg_mass = np.sum((conj_a == -1) * w, axis=0)

        entropy_pos = get_binary_entropy(pos_mass.astype(np.float64))
        entropy_neg = get_binary_entropy(neg_mass.astype(np.float64))

        self._pattern_scores = {}
        for atom, idx in self.literal_vocab.items():
            self._pattern_scores[Conjunction({atom: True})] = float(entropy_pos[idx])
            self._pattern_scores[Conjunction({atom: False})] = float(entropy_neg[idx])

        if not self._is_precondition:
            # effect_sign_prob is in range [-1, 1]. 0 is uncertain about sign
            self._pattern_scores[Conjunction({self.consequent: True})] = get_binary_entropy((effect_sign_prob + 1) / 2)
            self._pattern_scores[Conjunction({self.consequent: False})] = get_binary_entropy((1 - effect_sign_prob) / 2)

    def score_disjunctions(self) -> None:
        """Greedy set cover: repeatedly pick the condition covering the most unexplained deltas, within FP noise tolerance."""
        epsilon = max(self.noise_level, 1e-10)
        beta = np.log((1 - epsilon) / epsilon)
        TP_IDX = self.TP_IDX
        FP_IDX = self.FP_IDX

        data_indices = np.arange(self._data_belief_idx)
        observed_delta = np.array([self._dataset[i][4] != self._dataset[i][5] for i in data_indices], dtype=bool)
        delta_indices = data_indices[observed_delta]

        disjunction: list[int] = []
        explained = np.zeros(0, dtype=int)
        while len(np.setdiff1d(delta_indices, explained)) > 0:
            not_explained = np.setdiff1d(data_indices, explained)
            candidate_indices = np.flatnonzero(self._occupied)
            counts = self.eval_subset_counts(candidate_indices, not_explained)
            chances = counts[:, TP_IDX] + counts[:, FP_IDX] # if condition is ground truth, this is the number of chances to be flipped negative
            fp_tolerance = np.random.binomial(chances.astype(int), epsilon)
            filtered = counts[:, FP_IDX] <= fp_tolerance # restrict to conditions whose FP could be explained by noise
            if not filtered.any():
                break
            max_tp = counts[filtered, TP_IDX].max()
            if max_tp == 0:
                break
            filtered = filtered & (counts[:, TP_IDX] == max_tp) # restrict to conditions that explain the most deltas
            tied_candidates = candidate_indices[filtered]
            gain = counts[filtered, TP_IDX] - counts[filtered, FP_IDX]
            justified = beta * gain > -self._log_prior[tied_candidates] # condition must justify its complexity with explanatory power
            if not justified.any():
                break
            tied_candidates = tied_candidates[justified]
            chosen = tied_candidates[np.argmax(self._log_prior[tied_candidates])] # prefer the simplest (highest-prior) condition
            disjunction.append(int(chosen))
            predicted_mask = np.isin(self._data_predictions[chosen, not_explained], [self.TP_PRED, self.FP_PRED])
            explained = np.concatenate((explained, not_explained[predicted_mask]))
        self._disjunction = disjunction


    def eval_subset_counts(self, condition_indices: np.ndarray, data_indices: np.ndarray) -> np.ndarray:
        counts = np.zeros((len(condition_indices), 5))
        for ci, pi in enumerate([self.TP_PRED, self.TN_PRED, self.FP_PRED, self.FN_PRED, self.VACUOUS_PRED]):
            counts[:, ci] = np.sum(self._data_predictions[np.ix_(condition_indices, data_indices)] == pi, axis=1)
        return counts


    def get_best_conditions(self, combine_preconditions: bool = False) -> list[Condition]:
        if len(self) == 0:
            raise ValueError("No conditions in hypothesis set")
        if combine_preconditions and self._is_precondition:
            return [self._get_combined_precondition()]
        if self._allow_disjunction:
            self.score_disjunctions()
            disjunction = self._disjunction
            if len(disjunction) == 0:
                if self._is_precondition:
                    return [Condition(False, Outcome.APPLICABLE)]
                else:
                    return [Condition(False, Outcome.NO_EFFECT)]
            by_effect = defaultdict(list)
            for index in disjunction:
                condition = self._conditions_by_index[index]
                condition = self._extend_condition_fixed(condition)
                by_effect[condition.outcome].append(condition.antecedent)
            return [Condition(DNF(tuple(itertools.chain.from_iterable(dnf.conjunctions for dnf in dnfs))), outcome) for outcome, dnfs in by_effect.items()]

        if len(self._sort_indices) == 0:
            if self._is_precondition:
                return [Condition(False, Outcome.APPLICABLE)]
            else:
                return [Condition(False, Outcome.NO_EFFECT)]
        condition = self._conditions_by_index[self._sort_indices[0]]
        return [self._extend_condition_fixed(condition)]

    def get_condition_by_index(self, index: int) -> Condition:
        condition = self._conditions_by_index[index]
        return self._extend_condition_fixed(condition)

    def _get_combined_precondition(self) -> Condition:
        """Conjoin the antecedent terms of every hypothesis in the active (top-n) set.

        Gathers all antecedent terms appearing in any active hypothesis (together with
        the fixed conditions) into a single conjunction. Every candidate required literal
        must appear in some retained hypothesis, so this relies on a particle set larger
        than one (particle_expansion_target > 1); with a target of 1 only the MAP
        hypothesis is kept and there are no alternative terms to combine.
        """
        terms: dict[Atom, bool] = dict(self.fixed_conditions)
        for index in np.flatnonzero(self._active):
            antecedent = self._conditions_by_index[index].antecedent
            if isinstance(antecedent, bool):
                continue
            for conjunction in antecedent:
                terms.update(conjunction)
        return Condition(Conjunction(terms), Outcome.APPLICABLE)



    def get_disagreement_entropy(self,
        param_mapping: dict[str, str],
        state: dict[Atom, bool],
        current_literal: bool
    ) -> float:
        r"""Compute the disagreement entropy of the hypothesis set.

        The disagreement is the distribution of the next state given the action and the hypothesis set.
        The predictions are weighted by the posterior probability of the hypothesis.
        H[p(s'_{\ell(o)} | s, a(o), D_{a,\ell})] =
            H[ \sum_{h} p(s'_{\ell(o)} | s, a(o), h) * p(h | D_{a,\ell}) ]

        Args:
            param_mapping: The mapping of action parameters to their values
            state: The current state
            current_literal: The current value of this candidate literal in the state (or False for precondition)
        """
        prob_consequent = self.get_consequent_probability(param_mapping, state, current_literal)
        # compute the binary entropy
        return get_binary_entropy(prob_consequent)

    def sample(self, visited_only: bool = False) -> Condition:
        """Sample a hypothesis by its posterior. With visited_only, leave out those that need a literal value never
        seen in the data, unless that leaves none."""
        active = self._active
        if visited_only and self._data_belief_idx > 0:
            visited = active & ~self._visited_unvisited_mask()
            if visited.any():
                active = visited
        active_indices = np.flatnonzero(active)
        if len(active_indices) == 0:
            if self._is_precondition:
                return Condition(False, Outcome.APPLICABLE)
            else:
                return Condition(False, Outcome.NO_EFFECT)
        posterior = np.exp(self._log_posterior[active_indices] - self._posterior_normalization)
        idx = np.random.choice(active_indices, p=posterior / posterior.sum())
        condition = self._conditions_by_index[idx]
        return self._extend_condition_fixed(condition)

    def _extend_condition_fixed(self, condition: Condition) -> Condition:
        if isinstance(condition.antecedent, bool):
            if not condition.antecedent:
                antecedent = False
            else:
                antecedent = self.fixed_conditions
        else:
            antecedent = DNF(tuple(
                Conjunction({**self.fixed_conditions, **conj}) for conj in condition.antecedent.conjunctions
            ))
        return Condition(antecedent, condition.outcome)

    def __len__(self) -> int:
        return np.sum(self._occupied)

    @property
    def _occupied(self) -> np.ndarray:
        return self._counts[:, self.OCCUPIED_IDX] > 0

    @property
    def _active(self) -> np.ndarray:
        active = self._occupied & (self._log_posterior > self._inactive_log_threshold + self._posterior_normalization)
        active[0] = True # always keep the null condition active
        return active

    @property
    def _effect_sign(self) -> np.ndarray:
        return self._counts[:, self.EFFECT_SIGN_IDX]

    def get_condition_belief(self, index: int) -> float:
        return np.exp(self._log_posterior[index] - self._posterior_normalization)




@dataclass
class _HypothesisFactoryDefaults:
    noise_level: float = 0.0
    depth_prior: float = 0.1
    inactive_hypothesis_threshold: float = 1e-6
    particle_expansion_target: int = 128
    condition_buffer_size: int = 512
    data_buffer_size: int = 128
    prior_decay: float = 0.1
    max_uqvs: int = 2
    init_max_depth: int = 1
    no_effect_prior: float = 1.0
    unconditional_prior: float = 0.5
    allow_disjunctions: bool = False
    max_hypotheses: int = 100000
    uqv_chain_only: bool = True
    uqv_chain_allow_empty: bool = True
    combine_preconditions: bool = True
    max_unvisited_fraction: float = 1.0
    expand_only_tested: bool = True
    bound_unfixable_fp: bool = True


class ConditionHypothesisFactory:
    """Singleton factory for :class:`ConditionHypothesisSet` with shared defaults."""

    _instance: "ConditionHypothesisFactory | None" = None
    _defaults: _HypothesisFactoryDefaults | None = None

    def __new__(cls) -> "ConditionHypothesisFactory":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._defaults = _HypothesisFactoryDefaults()
        return cls._instance

    def configure(self, config: "OHCAMConfig | None" = None, **overrides: Any) -> None:
        """Set factory defaults from :class:`~ohcam.core.learner.OHCAMConfig` and/or keyword overrides."""
        if config is not None:
            self._defaults.noise_level = config.noise
            self._defaults.depth_prior = config.prior_decay
            self._defaults.prior_decay = config.prior_decay
            self._defaults.inactive_hypothesis_threshold = config.inactive_posterior_threshold
            self._defaults.particle_expansion_target = config.hypothesis_expansion_target
            self._defaults.condition_buffer_size = config.condition_buffer_size
            self._defaults.data_buffer_size = config.data_buffer_size
            self._defaults.max_uqvs = config.max_uqvs
            self._defaults.allow_disjunctions = config.allow_disjunctions
            self._defaults.max_hypotheses = config.max_hypotheses
            self._defaults.uqv_chain_only = config.uqv_chain_only
            self._defaults.uqv_chain_allow_empty = config.uqv_chain_allow_empty
            self._defaults.combine_preconditions = config.combine_preconditions
            self._defaults.max_unvisited_fraction = config.max_unvisited_hypothesis_fraction
            self._defaults.expand_only_tested = config.expand_only_tested
            self._defaults.bound_unfixable_fp = config.bound_unfixable_fp
        for key, value in overrides.items():
            if not hasattr(self._defaults, key):
                raise ValueError(f"Unknown hypothesis factory option: {key}")
            setattr(self._defaults, key, value)

    @property
    def prior_decay(self) -> float:
        return self._defaults.prior_decay

    @property
    def max_uqvs(self) -> int:
        return self._defaults.max_uqvs

    @property
    def noise_level(self) -> float:
        return self._defaults.noise_level

    @property
    def uqv_chain_allow_empty(self) -> bool:
        return self._defaults.uqv_chain_allow_empty

    @property
    def uqv_chain_only(self) -> bool:
        return self._defaults.uqv_chain_only

    def create(
            self,
            name: str,
            consequent: Atom | Literal[Outcome.APPLICABLE],
            literal_vocab: list[Atom],
            fixed_conditions: Conjunction | None = None,
            **overrides: Any,
    ) -> ConditionHypothesisSet:
        """Create a hypothesis set using configured defaults."""
        kwargs = {
            "noise_level": self._defaults.noise_level,
            "depth_prior": self._defaults.depth_prior,
            "inactive_hypothesis_threshold": self._defaults.inactive_hypothesis_threshold,
            "particle_expansion_target": self._defaults.particle_expansion_target,
            "condition_buffer_size": self._defaults.condition_buffer_size,
            "data_buffer_size": self._defaults.data_buffer_size,
            "allow_disjunctions": self._defaults.allow_disjunctions,
            "max_hypotheses": self._defaults.max_hypotheses,
            "combine_preconditions": self._defaults.combine_preconditions,
            "max_unvisited_fraction": self._defaults.max_unvisited_fraction,
            "expand_only_tested": self._defaults.expand_only_tested,
            "bound_unfixable_fp": self._defaults.bound_unfixable_fp,
        }
        kwargs.update(overrides)
        return ConditionHypothesisSet(name, consequent, literal_vocab, fixed_conditions=fixed_conditions, **kwargs)

    def create_precondition(self, name: str, literal_vocab: list[Atom], fixed_conditions: Conjunction | None = None, **overrides: Any) -> ConditionHypothesisSet:
        """Create a precondition hypothesis set seeded with only the unconditional hypothesis.

        Conditional (depth>=1) hypotheses are generated lazily by branch-and-bound expansion
        once the unconditional hypothesis accumulates false positives (inapplicable executions).
        """
        precondition = self.create(name, Outcome.APPLICABLE, literal_vocab, fixed_conditions=fixed_conditions, **overrides)
        precondition.add_condition(Condition(True, Outcome.APPLICABLE), self._defaults.unconditional_prior)
        precondition.normalize()
        precondition.update_pattern_scores()
        return precondition

    def create_effect(self, name: str, literal: Atom, literal_vocab: list[Atom],
            outcomes: list[Outcome] = [Outcome.ADD_EFFECT, Outcome.DEL_EFFECT],
            fixed_conditions: Conjunction | None = None, init_max_depth: int | None = None,
            **overrides: Any) -> ConditionHypothesisSet:
        """Create an effect hypothesis set seeded with only the depth-0 hypotheses
        (no-effect, unconditional add, unconditional delete).

        Conditional (depth>=1) hypotheses are generated lazily by branch-and-bound expansion
        from the set's literal_vocab, once an unconditional hypothesis accumulates false
        positives — i.e. only when the data demands an effect condition. The exception is
        sets with required_variables (exploration/UQV sets): their valid conditions must
        mention every required variable, so they are not reachable through one-literal
        refinements of invalid intermediates and must be seeded eagerly up to init_max_depth.
        """
        effect_set = self.create(name, literal, literal_vocab, fixed_conditions=fixed_conditions, **overrides)
        effect_set.add_condition(Condition(False, Outcome.NO_EFFECT), self._defaults.no_effect_prior) # outcome doesn't matter for null condition
        effect_set.add_condition(Condition(True, Outcome.ADD_EFFECT), self._defaults.unconditional_prior)
        if Outcome.DEL_EFFECT in outcomes:
            effect_set.add_condition(Condition(True, Outcome.DEL_EFFECT), self._defaults.unconditional_prior)

        if overrides.get("required_variables"):
            exclusive_vocab = list(set(literal_vocab) - {literal})
            init_max_depth = init_max_depth if init_max_depth is not None else self._defaults.init_max_depth
            for condition in enumerate_conjunctive_conditions(exclusive_vocab, outcomes, init_max_depth):
                effect_set.add_condition(condition, condition_complexity_prior(condition, self._defaults.prior_decay))
                if len(effect_set._conditions) > effect_set.particle_expansion_target:
                    break
        effect_set.normalize()
        effect_set.update_pattern_scores()
        return effect_set
