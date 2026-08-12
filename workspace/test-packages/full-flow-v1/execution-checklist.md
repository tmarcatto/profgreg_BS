# Full-Flow V1 Execution Checklist

Use this checklist for the next from-zero Prof Greg course test after Phase 3A-3C.

## Goal

Validate whether Greg can run a new course through the improved local operator, consolidated QA, source/reference gates, visual-plan gates, renderer checks, and model-routing validation.

## Start Conditions

- A new course run folder exists.
- `input/intake.md` contains course title, level, syllabus/input direction, and source-material notes.
- Source materials are indexed in `input/source_material_index.md` when provided.
- No artifacts from prior runs are copied in as active outputs.

## Required Command Rhythm

At the start of each work session:

```text
python3 tools/greg_run_lesson.py [course-slug] --lesson 1 --qa --include-localization
```

Before claiming the lesson is clean:

```text
python3 tools/greg_lesson_pipeline_qa.py [course-slug] --lesson 1 --include-localization --output runs/[course-slug]/process_review/lesson_01_pipeline_qa.md
```

Renderer and model-routing checks:

```text
python3 tools/greg_renderer_reuse_check.py --output runs/[course-slug]/process_review/renderer_reuse_qa.md
python3 tools/greg_model_routing_check.py --output runs/[course-slug]/process_review/model_routing_qa.md
```

## Stage Checklist

### 1. Intake

- Intake saved.
- Course level explicit.
- Audience remains U.S. construction workers/professionals.
- User-provided books and formal materials are indexed.
- User-provided informal/internal materials are marked internal-only.

### 2. Course Map

- Course Map treats syllabus as initial direction, not fixed contract.
- Adaptation log records kept/changed/flagged items.
- Course Map QA passes.
- Lesson count rationale is traceable.

### 3. Sources

- Source ledger exists.
- Student references are clean.
- Books/formal sources older than 3 years have applicability review before supporting current claims.
- Practitioner-context sweep is logged.
- Source/reference QA passes.

### 4. Study Guide Draft

- Draft follows approved Course Map.
- No activities, quizzes, or reflection prompts.
- Callouts are useful, short, and not in structural sections.
- Study guide content QA passes.

### 5. Visual Plan

- Visual plan exists before rendering.
- Each visual has purpose, learning claim, type, placement, and source status.
- Real-document lessons prioritize real examples or deterministic diagrams.
- Visual plan QA passes.

### 6. DOCX/PDF

- PDF follows approved BuildStak student-guide layout.
- PDF layout QA passes.
- Rendered pages exist when tooling supports it.

### 7. Human Approval

- Human approval file exists before deck production.
- Approval clearly authorizes deck generation.

### 8. Deck

- Deck uses 10-slide lecture-only structure.
- No visible timing.
- No speaker notes.
- No generated-image captions.
- No arbitrary/last-item highlights.
- Deck QA passes.

### 9. Localization Smoke Test

- PT-BR and ES-419 text artifacts exist when tested.
- U.S. market context preserved.
- Deck text maps include fit plans when needed.

### 10. Process Review

- Consolidated pipeline QA saved.
- Operator report saved.
- Renderer reuse QA saved.
- Model routing QA saved.
- Process review summarizes what still required manual work.

## Exit Condition

The test reaches either:

- `FULL_FLOW_CONFIRMATION_COMPLETE`; or
- a documented blocker with exact missing input, failed gate, and next human/system action.
