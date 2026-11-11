# Modifications

This copy of [AMLGym](https://github.com/LamannaLeonardo/AMLGym) is vendored by OHCAM and has been
modified from upstream commit `e9d8615` (2026-04-04). It remains under the original MIT license in
`LICENSE.md`.

Changes, by Jeff Jewett (2026):
- Fixes to `algorithms/RandomAgent.py`, `algorithms/__init__.py` and `metrics/_solving.py`.
- Added scripts for generating the conditional-effect benchmarks (`util/*_conditional.py`,
  `util/nurikabe_fix.py`, `conditional-domains.txt`). The generated benchmarks and the
  `pddl-generators` checkout they use are not included.
- `requirements.txt`: `pddl-plus-parser>=3.14.7` instead of `==3.14.7`, so the vendored
  pddl_plus_parser (3.17.0) satisfies it.
- `requirements.txt`: removed `n-sam`. It installs its own `sam_learning` package, which would
  shadow the vendored sam_learning that OHCAM needs. AMLGym's `SAM` and ROSAME wrappers, which
  import from it, are not used by OHCAM and may not work.
- Removed `CLAUDE.md`.
