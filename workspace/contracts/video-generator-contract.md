# Prof Greg Video Generator Contract

This contract defines the approved presentation-to-video workflow through AI Studios.

## Position and Scope

The private UI places `VIDEO_GENERATOR` after Section 5, Operator Action, and before AI Costs. In the production pipeline it follows presentation approval. English, Portuguese, and Spanish are independent lanes for every lesson.

## Entry Gate

A locale may enter video production only when:

- its canonical PPTX exists;
- the operator has explicitly approved that PPTX;
- the PPTX is no larger than 20 MB;
- no active job already exists for the same course, lesson, locale, and source SHA-256.

The approved presentation SHA-256 identifies the source revision. If a different presentation revision is later approved, Prof Greg must create a new AI Studios project and preserve the prior project/download URL as history.

## Fixed AI Studios Options

- workflow: `Docs to Video`;
- purpose: `For Business`;
- language: the single English, Portuguese, or Spanish option shown by AI Studios;
- duration: `Auto`;
- objective: `Teach practical construction knowledge that students can understand`;
- audience: `subcontractors, general contractors, project managers, and construction workers`;
- tone: `practical, empowering, trustworthy, and friendly`;
- speed: default;
- file background: enabled;
- voice only: disabled;
- template: the approved visual pattern with a white circle and avatar in the upper-right corner;
- avatar: the common-library `Gregory - Orange` avatar (verify visually if the label is truncated);
- voice: AI Studios default for the selected language.

The option text stays in English because it instructs AI Studios; it is not student-facing copy.

## Project Naming

Use:

```text
Lesson NN - [Lesson title] - EN
Lesson NN - [Lesson title] - PT-BR
Lesson NN - [Lesson title] - ES
```

## State Model

Each lane is stored outside the canonical artifact manifest at:

```text
runs/[course-slug]/video_generator/lesson_[NN]_[en|pt|es].json
```

Allowed operational states:

- `waiting_approved_presentation`
- `presentation_too_large`
- `ready`
- `ready_new_revision`
- `queued`
- `uploading`
- `configuring`
- `generating_transcripts`
- `awaiting_export_confirmation`
- `exporting`
- `rendering`
- `video_ready`
- `needs_attention`
- `failed`

The record may contain only non-secret operational data: locale, source path, source SHA-256, source size/modification marker, a hash of the temporary upload reference, AI Studios project URL/identifier, export download URL, attempt count, timestamps, and a redacted error summary. It must never contain credentials, tokens, temporary upload URLs, transcripts, or raw API logs. A temporary upload reference needed to continue a supervised pilot must be stored separately in protected, ignored runtime storage with mode `0600`.

## Guided Pilot Gate

The initial Lesson 2 pilot is supervised. Before each external side effect, the operator confirms the next action:

1. upload the approved PPTX;
2. submit the fixed options and start transcript generation;
3. export the project;
4. record the API-provided download URL after export completes.

The transcript is not edited. Before export, Prof Greg may validate through the API that project generation completed successfully. Any unexpected template, avatar, language, missing scene, authentication problem, or changed API response moves the lane to `needs_attention`.

After the pilot is accepted, the same workflow may run unattended one video at a time. English, Portuguese, and Spanish failures remain independent. Automatic retry is limited to two attempts with backoff and must not create a duplicate project for the same source SHA-256.

## Integration Decision

Use the official AI Studios V3 API as the primary integration:

- obtain a 24-hour access token from `/api/odin/v3/auth/token` using server-held AppId and UserKey;
- resolve the Enterprise workspace through `/api/odin/v3/dropdown/workspaces`;
- resolve Gregory through `/api/odin/v3/dropdown/models` and store the confirmed model ID;
- resolve the approved template through `/api/odin/v3/dropdown/templates_automation` with category `business`, orientation `web`, and `fileBackground=true`, then store the visually confirmed template ID;
- upload the PPTX through `/api/odin/v3/automation/docs-to-video/upload-files`;
- create the Docs-to-Video project through `/api/odin/v3/automation/docs-to-video` with the fixed options in this contract;
- poll project creation through `/api/odin/v3/automation/progress`;
- export through `/api/odin/v3/editor/project/export`;
- poll export through `/api/odin/v3/editor/progress/[projectId]` and record the returned download URL.

The export progress response's `downloadUrl` is the final video deliverable. The automated flow does not open AI Studios in Chrome, does not use Share/Copy Link, and does not depend on a browser session. If export reaches completion without a valid HTTPS download URL, preserve the project identifier and move the lane to `needs_attention` instead of guessing a URL.

## Secrets and Server Operation

- Use a dedicated AI Studios service account.
- Store credentials/session material only in server secret storage with least privilege.
- Never commit or expose credentials, cookies, or tokens through the UI.
- Run one video job at a time.
- Persist state after every successful boundary so an interrupted worker can resume safely.
- Show failures and retry controls in the private UI.
- Set `video_ready` only after export progress reaches completion and returns a valid HTTPS download URL.
