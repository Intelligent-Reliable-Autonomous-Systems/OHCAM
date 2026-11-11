# Modifications

This copy of [unified-planning](https://github.com/aiplan4eu/unified-planning) is vendored by OHCAM
and has been modified from upstream commit `8915b17c` (2026-11-11). It remains under the Apache
License 2.0 in `LICENSE`.

As required by section 4(b) of that license, the modified files are listed here and carry a notice
stating that they were changed.

Changes, by Jeff Jewett (2026):
- `unified_planning/io/pddl_writer.py`: added formatting options to the PDDL writer.
- `pyproject.toml`: static version `1.3.0+ohcam` in place of the git-derived (hatch-vcs) version,
  which is unavailable without this repository's git history.
