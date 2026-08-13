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
