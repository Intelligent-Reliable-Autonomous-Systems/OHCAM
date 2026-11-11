"""LAMP (Learning Action Models from Plan traces).

Implementation of the action-model learning algorithm of

    H. H. Zhuo, Q. Yang, D. H. Hu, L. Li,
    "Learning complex action models with quantifiers and logical implications",
    Artificial Intelligence 174 (2010) 1540-1569.

LAMP learns PDDL action models that may contain universal/existential
quantifiers, logical implications in preconditions, and (quantified)
conditional effects. The four high-level steps of the paper's Algorithm 1 are
implemented across the following modules:

* ``encoding``      - Step 1 (``encode_traces``): plan traces -> situation
                      labelled MLN databases.
* ``formulas``      - Step 2 (``generate_formulas``): candidate formulas F1-F5
                      and the correctness constraints A1-A3.
* ``mln_runner``    - Step 3 (``learn_weights``): weight learning with a Markov
                      Logic Network (the vendored ``pracmln`` library, whose
                      pseudo-log-likelihood ``BPLL`` learner optimizes the
                      paper's WPLL objective).
* ``model_builder`` - Step 4 (``attain_models``): threshold selection and
                      conversion of weighted formulas into PDDL action models.
* ``lamp_agent``    - the :class:`OfflineAgent` that wires the steps together.

Scaling (empirical)
-------------------
LAMP is implemented faithfully (no algorithmic shortcuts beyond the paper). Its
practical bottleneck is Step 3: ``pracmln``'s pure-Python ``BPLL`` must ground
and optimize a weight for *every* candidate formula over *every* situation pair
of *every* database, so cost grows steeply in both the number of candidate
formulas and the size of the encoded traces. Measured on the ``miconic-simpleadl``
eval data (single core; ``maxiter=100``):

* Candidate-formula count (1 short trace, 3-transition window, 42 ground atoms):
    - 42 candidates   (F1a/F2/F3, no free vars, no conditionals) -> ~7 s
    - 352 candidates  (+ conditional effects F4/F5)              -> ~57 s
    - 2554 candidates (the full F1-F5 set, ``max_free_vars=1``)  -> intractable
      (did not converge in >13 min)

* Encoded-data size (the minimal 42-candidate set):
    - 1 full trace   (78 ground atoms)    -> ~77 s
    - 3 full traces  (134 ground atoms)   -> ~85 s
    - 10 full traces (627 ground atoms)   -> did not finish in 150 s
    - 30/57 traces   (3205/13257 atoms)   -> did not finish in 150 s

In other words even a drastically reduced hypothesis space cannot consume the
full 57-trace eval set, and the faithful F1-F5 candidate set is already
intractable on a single short trace. The pipeline is verified end-to-end on
small subsets (it emits a PDDL domain that re-parses, and recovers the correct
``up``/``down`` precondition/effect models for ``miconic-simpleadl``). The
``max_free_vars``, ``conditional_effects``, ``precondition_implications`` and
``max_transitions``/``max_traces`` knobs exist purely so this scaling wall can
be probed on data subsets; they are not part of LAMP itself.
"""
