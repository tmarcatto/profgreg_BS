# Prof Greg Deployment Environment Contract

## Goal

Run Prof Greg online without mixing code, secrets, user uploads, generated artifacts, and runtime state.

## Source

- Code comes from GitHub: `tmarcatto/profgreg_BS`.
- The server pulls `main` or a tagged release.
- The server should record the deployed commit hash.

## Secrets

- Secrets live outside Git.
- API keys are provided by environment variables or a server secret manager.
- `.env.local` is allowed only on local development machines.
- Production secrets must not be written into logs, reports, source ledgers, or generated material.

## Storage

Use separate storage areas:

- source code checkout;
- runtime dependencies;
- uploaded source materials;
- generated course artifacts;
- logs and QA reports;
- backups.

Generated PDFs, PPTX files, source uploads, rendered pages, rendered slides, and API logs do not belong in Git.

## Runtime

- Run with a least-privilege server user.
- Restrict write permissions to approved runtime/output folders.
- Keep provider routing in `workspace/config/model-routing.json`; only the selected provider credentials change by environment.
- Disable destructive maintenance commands unless explicitly approved.

## Network

- Allow only required outbound provider/API access.
- Keep inbound access behind authenticated UI/API routes.
- Use HTTPS.
- Add rate limits before exposing public or semi-public endpoints.

## Deployment Gate

Before a deployment:

```bash
python3 tools/greg_pre_push_check.py
```

Production deployment is blocked if the check fails.

## First Server Milestone

The first server deployment should prove:

- repository checkout works;
- environment variables are loaded without exposing values;
- pre-push/deploy QA passes;
- a dry-run operator request can create a run folder;
- no course artifact is generated until storage and approval gates are confirmed.
