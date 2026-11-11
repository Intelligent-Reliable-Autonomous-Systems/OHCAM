# Modifications

This copy of [sam_learning](https://github.com/argaman-aloni/sam_learning) is vendored by OHCAM and
has been modified from upstream commit `8487d70` (2025-11-19). It remains under the original MIT
license in `LICENSE`.

Changes, by Jeff Jewett (2025-2026):
- Restructured into an installable package (`pyproject.toml`); `experiments/`, `validators/` and
  `solvers/` moved under `sam_learning/`, with imports updated.
- Tolerate a learning failure in `learners/universaly_conditional_sam.py`.

The `pddl_plus_parser/` directory is a separately vendored copy of its own upstream; see its
`MODIFICATIONS.md`.
