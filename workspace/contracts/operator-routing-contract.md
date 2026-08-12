# Prof Greg Operator Routing Contract

This contract defines how Greg maps a human request to the correct production stage.

The human should not need to know internal skill names. Greg should infer intent from natural language, check the run status, and then route to the safest next stage.

## Routing Principles

- Check status before acting when the user says resume, continue, next step, or where are we.
- Prefer the current run's canonical artifacts over older outputs.
- Never use parked artifacts unless the user explicitly reopens them.
- Enforce gates before routing to downstream production.
- Keep the user-facing explanation short and Portuguese by default.
- Keep course artifacts in English unless the user requests localization.

## Intent Categories

Use these intent categories:

- `status`: show current run state.
- `intake`: create or update course input.
- `course_map`: create, revise, or QA the Course Map.
- `sources`: research, source ledger, source gaps, student references.
- `study_guide`: draft or revise lesson study guide content.
- `review`: pedagogy, citation, design, or visual QA.
- `docx_pdf`: render or prepare student guide DOCX/PDF.
- `approval`: capture human approval for a study guide.
- `deck`: produce PPTX deck after approval.
- `localization`: localize approved artifacts to PT-BR or ES-419.
- `process_review`: summarize full-flow test results and update the system.
- `unknown`: ask for clarification only when a safe default is not available.

## Stage Mapping

| Intent | Stage | Primary skill |
|---|---|---|
| `status` | current stage | `greg-operator` |
| `intake` | `INTAKE` | `greg-operator` |
| `course_map` | `COURSE_MAP` | `course-map` |
| `sources` | `SOURCE_LEDGER` | `source-ledger` |
| `study_guide` | `DRAFT` | `study-guide-draft` |
| `review` | `REVIEW` | reviewer skill by type |
| `docx_pdf` | `DOCX_PDF` | `docx-pdf-producer` |
| `approval` | `HUMAN_APPROVAL` | `human-approval-gate` |
| `deck` | `DECK` | `deck-producer` |
| `localization` | `LOCALIZATION` | localization skill by locale |
| `process_review` | `REVIEW` | `greg-operator` |

## Gate Rules

### Course Map

Greg may route to Course Map generation when intake has enough information to infer:

- course title or topic;
- course level;
- learner audience or default learner profile;
- syllabus, lesson list, or source material.

If lesson count is weak or missing, Greg may choose autonomously and record the logic.

### Sources

Greg may route to sources after a Course Map exists or when the user explicitly asks to build references first.

Sources must distinguish:

- formal technical authority;
- industry and practitioner context;
- user-supplied source material;
- source gaps.

### Study Guide

Greg may route to study-guide drafting when:

- Course Map exists;
- source policy or source ledger exists, or source gaps are explicitly accepted for v0.

### Review

Greg may route to review when a draft exists. Reviewers must identify issues instead of only approving.

### DOCX/PDF

Greg may route to DOCX/PDF when:

- draft exists;
- review issues are fixed, accepted as v0 limitations, or explicitly blocked.

### Approval

Greg may route to approval when a final study-guide DOCX or PDF exists.

If the user says the study guide is approved and gives deck permission, Greg should create the approval record before routing to deck production.

### Deck

Greg may route to deck production only when:

- approval file exists;
- approval status is `approved` or `approved_with_minor_notes`;
- deck generation permission is `yes`.

If approval is missing, route to `approval` instead of `deck`.

### Localization

Greg may route to localization after approved English source artifacts exist. During v0, localization smoke tests may be used before full localized DOCX/PDF/PPTX production.

If approval is missing, route to `approval` instead of `localization`.

## Ambiguity Handling

If the user says "ok", "continue", "segue", or "next", Greg should:

1. Check status.
2. Identify the next allowed stage.
3. Explain the stage and proceed if no human gate is required.

If the next stage is a human gate, ask for or capture explicit approval instead of guessing.

## User-Facing Response

When routing, respond with:

1. Interpreted intent.
2. Current stage.
3. Gate status.
4. Selected next stage.
5. Artifact or skill to use next.

Do not expose long classification logs in conversation.
