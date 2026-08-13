# Prof Greg Server Bootstrap - 2026-08-13

## Server

- Provider: Hetzner
- Server name: `profgreg`
- Type: CPX12
- Public IPv4: `178.104.245.118`
- OS: Ubuntu 26.04 LTS
- Deployment path: `/opt/profgreg/app`
- Runtime user: `profgreg`
- Git remote: `https://github.com/tmarcatto/profgreg_BS.git`
- Deployed commit: `335b5f6`

## Security Baseline

- SSH key dedicated to Prof Greg.
- SSH password authentication disabled.
- Keyboard-interactive SSH authentication disabled.
- Public-key SSH authentication enabled.
- Root login allowed only by key: `prohibit-password`.
- X11 forwarding disabled.
- Runtime user `profgreg` has no sudo privileges.
- Firewall active.
- Inbound firewall allows only OpenSSH.
- Default inbound firewall policy is deny.

## Installed Runtime Capabilities

- Python 3.14.4
- Node.js 22.22.1
- npm 9.2.0
- Git 2.53.0
- LibreOffice 26.2.4.2
- Poppler `pdftoppm` 26.01.0
- Fontconfig

## Storage Layout

- Code checkout: `/opt/profgreg/app`
- Upload staging: `/srv/profgreg/uploads`
- Generated outputs: `/srv/profgreg/outputs`
- Runtime logs: `/var/log/profgreg`
- Server config/secrets root: `/etc/profgreg`

## Validation

Server deploy-safe QA command:

```bash
python3 tools/greg_pre_push_check.py --no-update-reports --output tmp/deploy_qa.md
```

Result:

- Security QA: pass
- Code quality QA: pass
- Model routing QA: pass
- Renderer reuse QA: pass
- Unit tests: pass, 88 tests
- Git checkout stayed clean after deploy-safe QA.

Dry-run course folder creation:

- Created ignored run folder: `runs/server-dry-run`
- Git checkout stayed clean.

## Systemd Healthcheck

Installed service:

`profgreg-healthcheck.service`

Service type:

- `oneshot`
- runs as `profgreg`
- uses `/etc/profgreg/profgreg.env`
- does not open network ports
- runs deploy-safe QA only

Security restrictions:

- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- limited writable paths
- `RestrictSUIDSGID=true`
- `LockPersonality=true`
- `MemoryDenyWriteExecute=true`
- native syscall architecture only

Validated result:

- `Result=success`
- `ExecMainStatus=0`
- deploy-safe QA passed
- Git checkout stayed clean.

## Secrets Placeholder

Created server-only environment file:

`/etc/profgreg/profgreg.env`

Permissions:

- owner: `root`
- group: `profgreg`
- mode: `640`

The file currently contains variable names only, without real API keys.

## Provider Smoke Test

After server secrets were filled manually, a minimal API smoke test was run from the server without printing secret values.

Validated:

- OpenAI role: `pedagogy_review`
- Anthropic role: `course_architect`
- Local deterministic role: `diagram_rendering`
- DeepSeek candidate: `deepseek-v4-flash`
- DeepSeek candidate: `deepseek-v4-pro`
- xAI candidate: `grok-4.5`
- OpenAI image role: `gpt-image-2`

Result:

- API connectivity passed for all tested providers.
- Image generation passed in a single minimal smoke test.
- Detailed API smoke-test logs remain local/ignored under `runs/_system/api_smoke_tests/`.

## Server Status Operator

Added after bootstrap:

```bash
python3 tools/greg_server_status.py --mode server --output tmp/server_status.md
```

Purpose:

- report deployed commit and branch;
- detect a dirty server checkout;
- confirm server/deployment docs exist;
- confirm latest deploy-safe QA report status;
- confirm runtime environment-file presence without printing secrets;
- confirm expected server storage/config paths exist.

This command is read-only for deployment state except for its optional Markdown report output.

## Backup and Log Operations Policy

Added after bootstrap:

- Server operations contract: `workspace/contracts/server-operations-contract.md`
- Logrotate sample: `workspace/ops/logrotate-profgreg.conf`
- Readiness command:

```bash
python3 tools/greg_server_status.py --mode server --ops-only --output tmp/server_ops_qa.md
```

- Backup command:

```bash
python3 tools/greg_server_status.py --mode server --create-backup --backup-label manual
```

Policy summary:

- uploads, outputs, logs, backups, and secrets stay outside Git;
- ordinary artifact backups must not contain raw API keys;
- server logs under `/var/log/profgreg` must be rotated;
- `/srv/profgreg/backups` is the backup root for future backup jobs and restore manifests.
- `/srv/profgreg/jobs` is the job-state root for future server workers;
- each backup writes a `.tar.gz` archive and a `.manifest.json` restore manifest;
- backup manifests include archive checksum, deployed commit, included roots, log inventory, secret exclusions, and restore notes.

## Job State Operator

Added after bootstrap:

- Server job contract: `workspace/contracts/server-job-contract.md`
- Readiness command:

```bash
python3 tools/greg_server_status.py --jobs-only --output tmp/job_operator_qa.md
```

Purpose:

- define `queued`, `running`, `needs_approval`, `completed`, `failed`, and `cancelled`;
- create/list/transition job records without executing production work;
- prepare a conservative future systemd worker that processes one job at a time.

## Open Items Before 24/7 Operation

- Decide whether to use systemd directly or Docker for the first persistent service.
- Install `/srv/profgreg/backups` and `/etc/logrotate.d/profgreg` on the live server.
- Add a scheduled backup timer after the manual backup job has been validated.
- Add domain/HTTPS only when a public or semi-public interface is introduced.
- Add request authentication and rate limits before exposing any UI/API.
