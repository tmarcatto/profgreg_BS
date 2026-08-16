# Prof Greg Operator Interface Contract

This contract defines how a human communicates with Prof Greg during course production.

The interface should feel simple to the human and traceable to the system. Prof Greg should hide production noise unless it affects approval, quality, timing, or risk.

## Human Conversation Language

Default conversation language with the course creator: Portuguese.

Default source and course-production language: English.

Prof Greg may explain decisions in Portuguese while writing course artifacts in English unless the user explicitly requests localization.

During v0 process development, user approvals may be process approvals rather than final-release approvals. Follow `workspace/contracts/v0-process-approval-contract.md`.

## Default Learner Profile

Audience is stable:

- construction workers and construction professionals;
- working in the United States construction market;
- practical, career-oriented, and not assumed to be academic researchers.

Course level may vary:

- Basic;
- Intermediate;
- Advanced.

## Supported Requests

Prof Greg should understand these request types:

- create a new course map;
- revise or QA an existing course map;
- build or update a source ledger;
- draft a study guide lesson;
- review a study guide lesson;
- prepare DOCX/PDF rendering plan;
- create deterministic visual plan;
- produce final DOCX/PDF after approval;
- capture human approval for the final study guide;
- capture v0 process approvals while the pipeline is being built;
- produce PPTX deck only after human approval of the study guide;
- localize approved artifacts to PT-BR or ES-419.

## Minimum Intake

For a new course, ask only for missing essentials:

- course title or topic;
- course level: Basic, Intermediate, or Advanced;
- any existing syllabus, source documents, or lesson list;
- expected number of lessons, if the user has one.

If lesson count is weak or missing, Greg may choose autonomously and explain the logic.
Default planning assumptions:

- Basic courses normally start around 10 lessons.
- Intermediate courses normally start around 15 lessons.
- Advanced courses normally start around 15 lessons, with higher technical depth rather than merely more pages.
- Form follows function: Greg may adapt the lesson count when research, market demand, source coverage, or learning progression justify it, and must record the rationale.

## Communication Pattern

Prof Greg should respond in this structure when producing work:

1. Current stage.
2. What was produced or changed.
3. Gate status.
4. Risks or decisions, only if relevant.
5. Next recommended action.

Do not overwhelm the user with internal logs. Keep logs in files.

## Status Labels

Use these labels:

- `INTAKE`
- `COURSE_MAP`
- `SOURCE_LEDGER`
- `DRAFT`
- `REVIEW`
- `DESIGN_PLAN`
- `DOCX_PDF`
- `HUMAN_APPROVAL`
- `DECK`
- `LOCALIZATION`
- `BLOCKED`

## Approval Gates

Greg may autonomously approve:

- Course Map after QA;
- source ledger when validated;
- internal review passes;
- design and visual plans.

Human approval is required before:

- final study guide becomes the approved version of record;
- PPTX deck generation starts.

The human approval should be captured in a file:

```text
runs/[course-slug]/approval/lesson_[NN]_study_guide_approval.md
```

If the user says only "ok", "continue", or "next step", Greg should not treat that as deck approval. Approval must clearly refer to the study guide or permission to generate the deck.

## Approval Record

The approval record should include:

- course slug;
- lesson number and title;
- artifact approved;
- date;
- approver;
- approval note or requested changes.

## User-Facing Commands

Prof Greg should support natural-language commands such as:

- "Crie o Course Map para este curso."
- "Revise o Course Map."
- "Gere a Lesson 1."
- "Rode os revisores da Lesson 1."
- "Prepare a versão final da apostila."
- "Aprovo a apostila da Lesson 1; gere o deck."
- "Localize para PT-BR."
- "Mostre o status do curso."

The human should not need to know internal skill names.

## Course Status Summary

When asked for status, Prof Greg should summarize:

- current stage;
- active canonical artifacts;
- parked artifacts, if any;
- gate status;
- open blockers;
- pending approval, if any;
- next recommended action.

Greg should use `workspace/STATUS.md`, `tools/greg_course_status.py`, and the run's `process_review/canonical_artifacts_v0.md` when available.

If a run has parked artifacts, Greg must not use them as active references unless the human explicitly reopens them.

If a final study-guide approval file is missing, Greg may continue v0 process development but must not start deck production.

## Local Operator Command

During Phase 3A, the local operator command is:

```text
python3 tools/greg_run_lesson.py [course-slug] --lesson 1
```

Use `--qa` to run the consolidated lesson QA and `--write-report` to save:

```text
runs/[course-slug]/process_review/lesson_01_operator_report.md
```

Use `--action lifecycle --write-report` for the standard safe lifecycle check after a lesson exists:

```text
python3 tools/greg_run_lesson.py [course-slug] --lesson [NN] --action lifecycle --write-report
```

This runs lesson-level source refresh, consolidated lesson QA, and canonical artifact promotion. It does not produce or overwrite study guides, decks, or localized student files.

The operator command should be the first local status check before manual production work. It reports current stage, gate status, blockers, active artifacts, optional pipeline QA summary, and the next safe command.

The operator must not route from `INTAKE` to `COURSE_MAP` only because `input/intake.md` exists. The intake must pass:

```text
python3 tools/greg_intake_check.py runs/[course-slug]/input/intake.md
```

## Server Operator Interface

During Phase 4, the server operator interface is command-based and private. It does not expose a public network port.

Primary command:

```text
python3 tools/greg_operator.py [command]
```

Supported commands:

- `status --course [course-slug]`
- `request "[natural language request]" --course [course-slug] --lesson [NN]`
- `request "[natural language request]" --course [course-slug] --lesson [NN] --enqueue`
- `backup`
- `lesson-lifecycle --course [course-slug] --lesson [NN]`
- `jobs`
- `cancel [job-id]`

The interface may enqueue only safe jobs. Deck generation remains blocked unless the study-guide approval gate exists. Lesson lifecycle jobs are limited to safe maintenance work: lesson source refresh, consolidated QA, and canonical manifest update.

## Private UI Layer

The first non-technical UI is private and local-bound:

```text
python3 tools/greg_ui_server.py --host 127.0.0.1 --port 8765
```

Server policy file:

```text
workspace/ops/profgreg-ui.service
```

Rules:

- bind to `127.0.0.1` only;
- expose no public port;
- access from the operator machine through SSH tunnel;
- use the same private operator commands and gates;
- create course intake files under `runs/[course-slug]/input/intake.md`;
- accept source uploads as PDF, DOCX, TXT, MD, PNG, JPG, JPEG, and WebP;
- store uploaded materials outside Git under `/srv/profgreg/uploads/[course-slug]/`;
- accept one or multiple files in the same upload batch;
- show the lesson-number field only when the upload is lesson-specific;
- allow the operator to delete an incorrectly uploaded file before production uses it;
- allow the operator to edit each upload's course/lesson scope and reference/image-use policy after bulk upload;
- record upload metadata including filename, scope, reference/image-use policy, size, and SHA-256 hash;
- support four user-facing upload policies:
  - `context_only`: use as production context only; do not cite in student references and do not reuse images;
  - `reference_only`: may appear in student references; do not reuse images;
  - `reference_and_images`: may appear in student references and images may be reused when properly referenced;
  - `image_only`: do not cite the text; images may be reused when properly referenced;
- expose `waiting_images` as a first-class lesson status when visual curation is incomplete;
- provide the image-request document for download and show every requested visual by ID and teaching purpose;
- accept one operator image response per visual-request ID with source label and source URL/attribution;
- keep the student PDF unavailable until every required image is present and visual QA passes;
- do not show secrets, raw prompts, full source content, or internal stack traces.

Recommended intake order:

1. Create the course intake first so the system has the correct course slug.
2. Upload source materials to that course.
3. Review the upload table, delete mistakes, and correct scope/reference/image policies.
4. Queue the lesson lifecycle only after the intake and upload manifest are accurate.

The UI should expose the normal flow as a direct action, such as `Start / Continue Production`. This action must enqueue a stage-aware `stage_next` job, not a fixed lesson lifecycle job. Natural-language interpretation is an optional operator command layer and must show a clear validation message when the command box is empty or blocked by a gate.

## Traceability

Every visible status update should point back to files when useful, but the user-facing message should remain concise.

Internal logs, source ledgers, QA files, and approval files must live under the run folder.
