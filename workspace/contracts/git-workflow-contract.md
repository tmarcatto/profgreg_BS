# Prof Greg Git Workflow Contract

## Branches

- `main` is the deployable branch.
- Use short-lived feature branches for meaningful changes.
- Branch names should describe the work, for example `phase3/pre-push-checks` or `server/deploy-contract`.

## Commits

- Commit small coherent changes.
- Do not mix generated course artifacts with system changes.
- Commit messages should start with an action verb, for example `Add pre-push QA gate`.

## Before Push

Run:

```bash
python3 tools/greg_pre_push_check.py
```

The push is allowed only when this check passes.

## Protected Content

Never push:

- `.env.local` or secrets;
- API logs;
- uploaded books, PDFs, DOCX files, or extracted source text;
- generated study guides, decks, rendered slides, rendered pages, or generated images;
- local runtime, OpenClaw home/state, cache, or server-only files.

## Remote

The canonical GitHub remote is:

`https://github.com/tmarcatto/profgreg_BS.git`

## Server Rule

The server must deploy from `main` or a tagged release. It should not run from uncommitted local changes.
