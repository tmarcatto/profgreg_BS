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

## Synchronization and Recovery Standard

For an approved production update, synchronize in this order: local workspace,
GitHub `main`, then the server checkout. Make code changes locally whenever
possible; the server must not become the only copy of a change.

Before replacing the server checkout, the deployer must create a dated recovery
point outside the checkout that includes a binary Git patch of any uncommitted
work and must preserve that work on a named Git branch. Only then may the
server fast-forward to the tested `main` commit. Run the deployment gate before
restart, restart the UI and both workers, and confirm their active status and
the deployed commit afterward. If a checkout is dirty or histories diverge,
merge and test locally first; never discard server work to force an update.

Before a deployment:

```bash
python3 tools/greg_pre_push_check.py --no-update-reports --output tmp/deploy_qa.md
```

Production deployment is blocked if the check fails.

The deploy gate includes environment QA. Environment QA may report whether keys are present and their length, but must never print secret values.

For a non-destructive deployment status report:

```bash
python3 tools/greg_server_status.py --mode server --output tmp/server_status.md
```

This status command may report branch, commit, working-tree cleanliness, expected storage paths, runtime environment-file presence, and deploy-QA status. It must not print secret values and must not generate course artifacts.

## First Server Milestone

The first server deployment should prove:

- repository checkout works;
- environment variables are loaded without exposing values;
- pre-push/deploy QA passes;
- server status report passes or has only reviewed warnings;
- a dry-run operator request can create a run folder;
- no course artifact is generated until storage and approval gates are confirmed.
