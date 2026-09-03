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

For the first server backup job:

```bash
python3 tools/greg_server_status.py --mode server --create-backup --backup-label manual
```

Scheduled backup policy files live in:

```bash
workspace/ops/profgreg-backup.service
workspace/ops/profgreg-backup.timer
```

For server job-state readiness:

```bash
python3 tools/greg_server_status.py --jobs-only --output tmp/job_operator_qa.md
```

The first conservative worker is:

```bash
python3 tools/greg_server_status.py --worker --once
```

The server systemd policy file is:

```bash
workspace/ops/profgreg-worker.service
```

The private operator interface is:

```bash
python3 tools/greg_operator.py status --course [course-slug]
python3 tools/greg_operator.py request "mostre o status" --course [course-slug]
python3 tools/greg_operator.py lesson-lifecycle --course [course-slug] --lesson 1
python3 tools/greg_operator.py jobs
```

The first private UI is local-bound:

```bash
python3 tools/greg_ui_server.py --host 127.0.0.1 --port 8765
```

On the server, access it through an SSH tunnel instead of opening a public port.

The UI can create a course intake and upload one or multiple source materials at once. Uploaded files are stored outside Git under `/srv/profgreg/uploads/[course-slug]/` on the server, with editable metadata for scope, reference policy, image-use permission, size, and SHA-256 hash. Operators can delete incorrect uploads before production uses them.

After Course Map approval, the intake's Marketing section can research and generate editable website copy, skills, learning outcomes, requirements, career positioning, and a five-page BuildStak-branded PDF brochure. Saving edited copy rebuilds the brochure so the public-facing page and downloadable marketing material stay aligned.

Course intake defaults are level-aware: Basic starts around 10 lessons; Intermediate and Advanced start around 15 lessons unless the operator or Greg's Course Map rationale changes that count.
