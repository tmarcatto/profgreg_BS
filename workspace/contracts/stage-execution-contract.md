# Prof Greg Stage Execution Contract

This contract defines the stage-by-stage operating model for Prof Greg v0.

The operator routes a human request to a stage. The stage execution contract decides whether that stage can start, what it must produce, and where it should route next.

## Stage Order

Default production order:

1. `INTAKE`
2. `COURSE_MAP`
3. `SOURCE_LEDGER`
4. `DRAFT`
5. `REVIEW`
6. `DOCX_PDF`
7. `HUMAN_APPROVAL`
8. `DECK`
9. `LOCALIZATION`
10. `VIDEO_GENERATOR`
11. `PROCESS_REVIEW`

During v0, `LOCALIZATION` may be smoke-test only. Full localized DOCX/PDF/PPTX production comes after the English flow is reliable.

## Stage Table

| Stage | Required inputs | Required outputs | Gate | Next stage |
|---|---|---|---|---|
| `INTAKE` | human syllabus/topic, course level, optional sources | `input/intake.md`, `input/source_material_index.md` when sources exist | enough information to infer course scope | `COURSE_MAP` |
| `COURSE_MAP` | `input/intake.md` | `course_map/course_map.md`, `course_map/course_map.json`, `course_map/syllabus_adaptation_log.md`, `course_map/course_map_qa.md` | autonomous Course Map QA, including syllabus adaptation review | `SOURCE_LEDGER` |
| `SOURCE_LEDGER` | Course Map, source materials, web research when available | `sources/source_ledger.json`, `sources/research_log.md`, `sources/student_references.md`, `sources/source_gaps.md`, `sources/lesson_[NN]_source_refresh.json`, `sources/lesson_[NN]_source_refresh_qa.md` | source validation has no unresolved critical gap and lesson-level source refresh is complete | `DRAFT` |
| `DRAFT` | Course Map, source ledger or accepted source gaps, lesson target | `lesson_draft/lesson_[NN]_draft.md` | no invented sources or unsupported critical claims | `REVIEW` |
| `REVIEW` | lesson draft, source ledger, design system | pedagogy, citation, design, and visual QA files | issues fixed, accepted as v0 limits, or blocked | `DOCX_PDF` |
| `DOCX_PDF` | reviewed lesson draft, design system, visual assets | `docx_pdf/lesson_[NN]_study_guide.docx`, `docx_pdf/lesson_[NN]_study_guide.pdf`, `docx_pdf/lesson_[NN]_render_qa.md` | render QA not blocked | `HUMAN_APPROVAL` |
| `HUMAN_APPROVAL` | final DOCX/PDF | `approval/lesson_[NN]_study_guide_approval.md` | explicit human approval and deck permission | `DECK` |
| `DECK` | approved English study guide, approval record, design system | `deck/lesson_[NN]_deck.pptx`, `deck/lesson_[NN]_deck_qa.md` | deck QA not blocked | `LOCALIZATION` or `PROCESS_REVIEW` |
| `LOCALIZATION` | approved English artifacts | localized study guide/deck text artifacts and QA files | localization QA not blocked | `VIDEO_GENERATOR` or `PROCESS_REVIEW` |
| `VIDEO_GENERATOR` | canonical approved EN, PT-BR, or ES presentation | per-locale video state, AI Studios project ID, and direct download URL | approved PPTX, 20 MB limit, source SHA-256 idempotency, and successful export | `PROCESS_REVIEW` |
| `PROCESS_REVIEW` | run artifacts and QA notes | `process_review/full_flow_test_report.md` | actionable learning captured | end |

## Consolidated Lesson QA

Before saying a lesson pipeline is clean, Greg should run the consolidated QA wrapper:

```text
tools/greg_lesson_pipeline_qa.py [course-slug] --lesson 1 --production-date YYYY-MM-DD
```

When localization text-map checks are in scope, add:

```text
--include-localization
```

For process review, save the Markdown report:

```text
process_review/lesson_01_pipeline_qa.md
```

This wrapper does not replace specialized QA tools. It orchestrates them and reports which gate is blocking or warning.

For multi-lesson courses, the wrapper also runs the course registry gate defined in:

```text
workspace/contracts/course-registry-contract.md
```

The wrapper also runs the lesson-level source refresh gate defined in:

```text
workspace/contracts/source-ledger-contract.md
```

## Entry Behavior

Before starting a stage, Greg must:

1. Check the current run status.
2. Check canonical artifacts.
3. Check whether required inputs exist.
4. Check whether any gate blocks the stage.
5. If blocked, write or update a blocked note in the expected output folder.

For local Phase 3A operation, start with:

```text
tools/greg_run_lesson.py [course-slug] --lesson [NN]
```

To run the safe local lifecycle checks for an already produced lesson, use:

```text
tools/greg_run_lesson.py [course-slug] --lesson [NN] --action lifecycle --write-report
```

This action refreshes lesson sources, saves consolidated pipeline QA, and updates the canonical artifact manifest. It does not generate new student-facing content.

## Exit Behavior

After completing a stage, Greg must:

1. Write the required outputs.
2. Record any accepted v0 limitations.
3. Update or create status/process-review notes when useful.
4. Route to the next allowed stage unless a human gate is reached.

## Blocked Notes

Blocked notes should be short and traceable.

Use one of these paths:

```text
course_map/course_map_blocked.md
sources/source_ledger_blocked.md
lesson_draft/lesson_[NN]_draft_blocked.md
review/lesson_[NN]_review_blocked.md
docx_pdf/lesson_[NN]_production_blocked.md
approval/lesson_[NN]_approval_blocked.md
deck/lesson_[NN]_deck_blocked.md
localization/lesson_[NN]_localization_blocked.md
video_generator/lesson_[NN]_[locale]_blocked.md
process_review/full_flow_test_blocked.md
```

Each blocked note should include:

- blocked stage;
- missing or invalid inputs;
- gate that failed;
- recommended human or system action;
- date.

## Canonical Artifact Rule

Follow `workspace/contracts/canonical-artifacts-contract.md`.

If multiple artifacts exist for the same stage, Greg should use:

1. explicit canonical file in `process_review/canonical_artifacts.json`;
2. standard path from the run-folder contract;
3. latest non-parked artifact only when no canonical artifact exists.

Greg must never silently select a parked artifact.

If no canonical manifest exists and a run has enough artifacts to infer one, Greg should create it with:

```text
tools/greg_canonical_artifacts.py [course-slug] --write
```

## Full-Flow Readiness

Greg is ready to start a fresh full-flow v0 test when:

- operator status behavior exists;
- operator routing behavior exists;
- this stage execution contract exists;
- all primary skills reference the relevant contracts;
- design-system files exist;
- model-routing config exists;
- full-flow test package exists;
- a run-folder structure can be checked before and after each stage.
