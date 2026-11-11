# Modifications

This copy of [predicators](https://github.com/Learning-and-Intelligent-Systems/predicators) is
vendored by OHCAM and has been modified from upstream commit `5bd3f5bd` (2025-04-08). It remains
under the original MIT license in `LICENSE.md`.

Changes, by Jeff Jewett (2025-2026):
- Packaging moved from `setup.py` to `pyproject.toml`, with fewer required dependencies and the LLM
  dependencies made optional (LLM helpers moved from `utils.py` to `llm_utils.py`).
- Action binding support in `structs.py` and the STRIPS learners (`base_strips_learner.py`,
  `clustering_learner.py`, `llm_strips_learner.py`).
- Fix for an assertion error in `clustering_learner.py`.
- Removed the Franka and Fetch robot models (`envs/assets/urdf/franka_description/` and
  `envs/assets/urdf/fetch_description/`, about 137 MB) to reduce size. The PyBullet environments
  that load them will not work; OHCAM does not use them.
