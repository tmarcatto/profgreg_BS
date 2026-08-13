# Prof Greg

Prof Greg is the local production pipeline for BuildStak learning materials.

The repository keeps the durable system pieces:

- agent identity, contracts, skills, and design-system rules;
- reusable PDF and deck renderers;
- model-routing configuration examples;
- QA tools and automated checks;
- central process QA reports.

The repository does not track local secrets, OpenClaw/runtime installs, generated course outputs, user-supplied source files, local caches, or API smoke-test logs.

## Local Checks

Run these before committing meaningful changes:

```bash
python3 tools/greg_pre_push_check.py
```

## Configuration

Copy `workspace/config/model-routing.env.example` into a local `.env.local` file and fill in provider keys locally. Do not commit `.env.local`.

## GitHub

Canonical remote:

`https://github.com/tmarcatto/profgreg_BS.git`

`main` is the deployable branch. Generated course artifacts stay local unless promoted deliberately through a release/artifact-storage process.

On a server checkout, use the deploy-safe check so the working tree stays clean:

```bash
python3 tools/greg_pre_push_check.py --no-update-reports --output tmp/deploy_qa.md
```

This includes environment QA that reports only whether provider keys are present and their length, never secret values.

For a non-destructive local or server status report:

```bash
python3 tools/greg_server_status.py --mode auto --output tmp/server_status.md
```

For backup/log operations readiness:

```bash
python3 tools/greg_server_status.py --mode auto --ops-only --output tmp/server_ops_qa.md
```
