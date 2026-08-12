# Legacy One-Off Scripts

This folder contains historical scripts created while Prof Greg's pipeline was being discovered and tested.

These files are preserved for traceability, but they are not part of the active reusable renderer surface.

Active production work should prefer:

- `tools/greg_run_lesson.py`
- `tools/greg_lesson_pipeline_qa.py`
- reusable renderer tools created under the `greg_` naming pattern
- contracts under `workspace/contracts/`

The renderer reuse audit intentionally ignores this folder. If a legacy script contains useful rendering logic, migrate the pattern into a reusable `greg_` renderer instead of calling the legacy script directly.
