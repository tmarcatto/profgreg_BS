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

Result:

- API connectivity passed for all tested providers.
- Image generation was not tested in this pass to avoid unnecessary image cost.
- Detailed API smoke-test logs remain local/ignored under `runs/_system/api_smoke_tests/`.

## Open Items Before 24/7 Operation

- Decide whether to use systemd directly or Docker for the first persistent service.
- Add backup policy for uploads, outputs, logs, and server config.
- Add log rotation policy.
- Add domain/HTTPS only when a public or semi-public interface is introduced.
- Add request authentication and rate limits before exposing any UI/API.
