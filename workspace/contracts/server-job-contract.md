# Prof Greg Server Job Contract

This contract defines the first server-side job state model before Prof Greg exposes a UI/API.

## Goal

Server jobs must be traceable, resumable, and safe. A job record may request work, but it must not bypass course-production gates or human approvals.

## Storage

Job state lives outside Git:

```text
/srv/profgreg/jobs
```

Each job has:

```text
/srv/profgreg/jobs/[job_id]/job.json
/srv/profgreg/jobs/[job_id]/events.jsonl
```

## States

Allowed states:

- `queued`
- `running`
- `needs_approval`
- `completed`
- `failed`
- `cancelled`

Allowed transitions:

- `queued` -> `running`
- `running` -> `needs_approval`
- `running` -> `completed`
- `running` -> `failed`
- `needs_approval` -> `running`
- `needs_approval` -> `completed`
- `queued` -> `cancelled`
- `running` -> `cancelled`
- `needs_approval` -> `cancelled`

## Job Shape

```json
{
  "job_id": "job_YYYYMMDDTHHMMSSZ_slug",
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "updated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "state": "queued",
  "request_type": "course_status | lesson_lifecycle | backup | full_flow_v1_test",
  "course_slug": "string or null",
  "lesson": 1,
  "requested_by": "operator",
  "input_summary": "short non-sensitive summary",
  "artifacts": [],
  "last_error": null
}
```

## Safety Rules

- Job IDs must be slug-safe.
- Job records must not include API keys, raw uploaded source text, full prompts, or full model responses.
- Creating a job does not execute the job.
- A worker may only execute request types that have explicit contracts and gates.
- Deck generation remains blocked until the study guide approval gate is present.
- Failed jobs must preserve `last_error` as a summary only, not as a secret-bearing stack dump.

## First Worker Direction

The first persistent worker should be systemd-based and conservative:

- poll queued jobs;
- run one job at a time;
- write events;
- stop cleanly;
- never expose a network port.

The first worker implementation is intentionally narrow:

- command: `tools/greg_server_status.py --worker`;
- service policy: `workspace/ops/profgreg-worker.service`;
- first executable request types: `backup` and safe `lesson_lifecycle`;
- `lesson_lifecycle` runs only source refresh, consolidated QA, and canonical manifest updates;
- unsupported request types fail with a short operator-safe error summary;
- course-production jobs remain gated until their execution contracts are explicit.

## Video Generator Expansion

`video_generation` is an accepted delivery-worker request type. It includes course, lesson, locale, presentation path, source SHA-256, and the lesson title. The official Enterprise API path passed the Lesson 2 English pilot on 2026-08-31, and dedicated queue, deduplication, dry-run execution, and interrupted-job recovery tests gate deployment.

Video jobs run one at a time in the delivery lane. Each locale fails independently and retries at most twice. The worker uploads the approved presentation, preserves AI Studios transcript generation, exports the video, and records the direct download URL. No browser session is part of the worker flow.

The delivery worker runs with `--auto-video`. On every poll it discovers approved canonical presentation revisions whose SHA-256 has never been queued, creates exactly one `video_generation` job for each locale, and processes the queue serially. A worker restart may create one recovery job for an interrupted video; the persisted AI Studios project/export identifiers make that recovery resumable without creating a duplicate project for the same source revision.

## Interrupted Production Recovery

An interrupted `production_stage` job is marked failed for an accurate audit trail and requeued with the same course, lesson, stage, and payload. Production stages persist revision specs and are resumable, so a planned deployment or service restart must not silently discard an operator request. Automatic restart recovery is limited to three attempts; after that, the job remains failed for operator investigation.
