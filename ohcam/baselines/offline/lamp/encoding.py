"""Step 1 of LAMP: ``encode_traces`` (paper Section 4.1, Algorithm 2).

Each plan trace is encoded as a Markov Logic Network *database* (a set of
ground facts). Following the paper's situation-calculus style encoding, every
predicate and every action is augmented with an extra *situation label*
argument ``i`` that identifies the state ``s_i`` in which the fact holds
(paper: ``is-at(l1, s1)``, ``move(l1, l2, s1)``).

Because an MLN cannot express the arithmetic relation ``i + 1`` directly, the
two states related by an action transition are linked through an explicit
successor relation ``succ(i, j)`` that is supplied as evidence. A candidate
effect formula is then written as ``a(i) ^ succ(i, j) => ...`` (see
``formulas.py``), which reproduces the paper's ``... i ^ ... i+1`` semantics.

Following the paper, each plan trace is encoded as a *single* database whose
situation labels ``0, 1, ..., n`` index the successive states ``s_0, ..., s_n``
of that trace; the executed action of the (applicable) transition ``t`` is
asserted at situation ``t`` together with ``succ(t, t + 1)``. Inapplicable
transitions carry no causal action, so their action/``succ`` atoms are omitted
(only successful state transitions are causal, consistent with the paper's
deterministic-plan assumption and with ConditionalSAM's ``filter_inapplicable``).

Only the atoms that are explicitly observed in a state are written to the
database. ``pracmln``'s learner applies the closed-world assumption to every
unstated ground atom (``MRF.apply_cw``), so the fully observed plan traces used
here are treated as complete - this mirrors the closed-world simplification of
the paper's Example 6.

The ``max_transitions`` argument is purely a scaling knob (it truncates each
trace to its first ``k`` transitions). It is not part of the algorithm and only
exists to let us measure how learning cost grows with the size of the encoded
database; with the default ``None`` the whole trace is encoded as in the paper.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ohcam.trace import Trace
from ohcam.baselines.offline.lamp.signature import (
    DomainSignature,
    MLNNaming,
)


@dataclass
class EncodedTrace:
    """A single plan trace encoded as MLN database text plus its domains.

    ``db_text`` is a ``pracmln`` ``.db`` snippet (one ground fact per line).
    ``domains`` maps each MLN domain (type) name to the set of constants that
    occur in this trace, which lets the caller register them with the MLN.
    """

    db_text: str
    domains: dict[str, set[str]]


class TraceEncoder:
    """Encodes :class:`Trace` objects into MLN databases (Algorithm 2)."""

    def __init__(
        self,
        signature: DomainSignature,
        naming: MLNNaming,
        max_transitions: int | None = None,
    ) -> None:
        self.sig = signature
        self.naming = naming
        # Scaling knob only (not part of LAMP): truncate each trace to its first
        # ``max_transitions`` transitions to bound the size of its database.
        self.max_transitions = max_transitions

    def encode_traces(self, traces: list[Trace]) -> list[EncodedTrace]:
        """Encode each plan trace as one situation-labelled database."""
        encoded = [self._encode_trace(trace) for trace in traces]
        return [e for e in encoded if e is not None and e.db_text.strip()]

    # ------------------------------------------------------------------
    def _encode_trace(self, trace: Trace) -> EncodedTrace | None:
        states = trace.states
        actions = trace.actions
        executions = trace.executions

        n_trans = len(actions)
        if self.max_transitions is not None:
            n_trans = min(n_trans, self.max_transitions)
        if n_trans == 0:
            return None

        lines: list[str] = []
        domains: dict[str, set[str]] = defaultdict(set)

        # Situation labels 0..n index the successive states s_0..s_n.
        for s_idx in range(n_trans + 1):
            state = states[s_idx]
            if state is not None:
                self._encode_state(state, s_idx, lines, domains)
            domains[self.naming.STATE_DOMAIN].add(str(s_idx))

        for t in range(n_trans):
            # Only successful (applicable) transitions are causal evidence.
            if executions[t] == "inapplicable":
                continue
            if states[t] is None or states[t + 1] is None:
                continue
            self._encode_action(actions[t], t, lines, domains)
            lines.append(f"{self.naming.SUCC}({t}, {t + 1})")

        return EncodedTrace("\n".join(lines), dict(domains))

    def _encode_state(self, state, s_idx, lines, domains) -> None:
        """Encode one observed state ``s_i`` (Algorithm 2, Step 5).

        Only observed atoms are emitted; the learner closes the world over the
        rest (see module docstring).
        """
        for fexp, value in state.items():
            pred = fexp.fluent().name
            args = tuple(arg.object().name for arg in fexp.args)
            self._emit_atom(
                self.naming.pred(pred), args, s_idx, value, lines, domains
            )

    def _encode_action(self, action, t, lines, domains) -> None:
        """Encode an executed action as a proposition (Algorithm 2, Step 9)."""
        args = tuple(arg.object().name for arg in action.actual_parameters)
        self._emit_atom(
            self.naming.action(action.action.name), args, t, True, lines, domains
        )

    def _emit_atom(self, mln_pred, obj_args, s_idx, truth, lines, domains) -> None:
        consts = [self.naming.const(o) for o in obj_args]
        # Register constants in their per-argument domains is handled implicitly
        # by pracmln when parsing the DB; we still track them for completeness.
        all_args = consts + [str(s_idx)]
        domains[self.naming.STATE_DOMAIN].add(str(s_idx))
        atom = f"{mln_pred}({', '.join(all_args)})"
        lines.append(atom if truth else f"!{atom}")
