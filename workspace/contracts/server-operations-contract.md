# Prof Greg Server Operations Contract

This contract defines the minimum backup, logging, and operational-readiness posture before Prof Greg exposes a persistent interface.

## Goal

Prof Greg must be recoverable without mixing code, secrets, uploads, generated outputs, and logs.

## Storage Ownership

Server runtime paths:

- code checkout: `/opt/profgreg/app`
- upload staging: `/srv/profgreg/uploads`
- generated outputs: `/srv/profgreg/outputs`
- backup root: `/srv/profgreg/backups`
- runtime logs: `/var/log/profgreg`
- server config/secrets root: `/etc/profgreg`

The Git repository is not a backup target for course uploads, generated artifacts, local runs, API logs, or server secrets.

## Backup Policy

Back up:

- `/srv/profgreg/uploads`
- `/srv/profgreg/outputs`
- selected non-secret operational metadata from `/var/log/profgreg`
- deployment commit hash and server bootstrap notes

Do not back up raw API keys into ordinary artifact backups. Secrets must remain in the server secret store or in a separate encrypted backup process controlled by the operator.

Backups must be restorable by course/run and by date. A future automated backup job should write a manifest for each backup set with:

- timestamp;
- deployed commit;
- source paths included;
- excluded secret paths;
- checksum or size summary;
- restore notes.

## Log Policy

Logs must support operations without leaking secrets or full source payloads.

Logs may include:

- stage names;
- run IDs;
- model/provider role names;
- outcome status;
- failure summaries;
- elapsed time and cost metadata when available.

Logs must not include:

- API key values;
- raw uploaded source contents;
- full prompts by default;
- full model responses by default;
- private user documents unless explicitly required for a debug artifact and stored outside general logs.

Server logs under `/var/log/profgreg` must be rotated. The default rotation policy is daily rotation, compression, `missingok`, `notifempty`, and a bounded retention window.

## Readiness Gate

Before exposing a persistent UI/API, the server must pass:

```bash
python3 tools/greg_server_status.py --mode server --ops-only --output tmp/server_ops_qa.md
python3 tools/greg_server_status.py --mode server --output tmp/server_status.md
python3 tools/greg_pre_push_check.py --no-update-reports --output tmp/deploy_qa.md
```

Warnings must be reviewed before exposure. Failures block exposure.
