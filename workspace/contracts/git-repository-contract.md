# Prof Greg Git Repository Contract

## Purpose

The Git repository is the durable source of truth for the Prof Greg system, not a storage bucket for generated course artifacts.

## Commit

- Source code under `tools/`.
- Agent contracts, skills, renderers, design-system files, templates, and stable workspace documentation under `workspace/`.
- Root project metadata such as `README.md` and `.gitignore`.
- Central QA summaries under `runs/_system/*.md`.

## Do Not Commit

- Local secrets or `.env.local`.
- API smoke-test logs or raw provider responses.
- User-supplied PDFs, DOCX files, or extracted source text.
- Generated course PDFs, DOCX files, PPTX files, rendered pages, rendered slides, and image drafts.
- Local OpenClaw install, runtime dependencies, caches, or local OpenClaw home/state.

## Promotion Rule

If a generated artifact later needs to become a permanent product asset, promote it deliberately into a named release or artifact-storage process. Do not let generated outputs enter Git by accident.

## Required Gates

Before pushing changes to the shared repository, run:

```bash
python3 tools/greg_pre_push_check.py
```
