# Operator Production Gap Audit - 2026-08-15

## Current Finding

The private UI can create course intake files, upload source materials, edit upload metadata, enqueue jobs, and show status. The `Start / Continue Production` button previously enqueued a fixed `lesson_lifecycle` job, which is only appropriate after core artifacts exist. When a new course is still at `COURSE_MAP`, that job can fail because it tries downstream source/QA actions before the Course Map exists.

## Immediate Fix

`Start / Continue Production` now queues a stage-aware `stage_next` job. The worker runs `greg_run_lesson.py --action next`, which reads the current stage and performs only the safe next action available for that stage. If the next stage is not yet automated, the job completes with an operator report instead of failing.

## Remaining Production Gaps

The server still needs production generators before one click can complete the full course flow:

1. Course Map generator
   - Input: intake, upload manifest, source metadata.
   - Output: `course_map/course_map.md`, `course_map/course_map.json`, `course_map/syllabus_adaptation_log.md`, `course_map/course_map_qa.md`.
   - Required: use configured `course_architect` model role, not hardcoded models.

2. Source ledger generator
   - Input: Course Map, upload manifest policies, web/academic/practitioner research.
   - Output: `sources/source_ledger.json`, `sources/research_log.md`, `sources/student_references.md`, `sources/source_gaps.md`.
   - Required: respect `context_only`, `reference_only`, and `reference_and_images`.

3. Lesson study-guide generator
   - Input: Course Map, source ledger, lesson number.
   - Output: draft, visual plan, study-guide spec, rendered PDF/DOCX, QA report.
   - Required: stop for human review/approval before deck production.

4. Approval UI
   - Show produced study-guide artifact.
   - Capture approval or revision request.
   - Write `approval/lesson_XX_study_guide_approval.md` only after explicit approval.

5. Deck generator
   - Input: approved study guide, deck rules, visual plan.
   - Output: PPTX, rendered slide previews, deck QA.
   - Required: no speaker notes, 10-slide recorded-lesson structure, BuildStak visual identity.

6. Deck approval UI
   - Show produced deck artifact.
   - Capture approval or revision request.
   - Write `approval/lesson_XX_deck_approval.md` only after explicit approval.

## Recommended Next Development Milestone

Build stage execution one stage at a time:

1. Implement Course Map generation behind `stage_next`.
2. Add Course Map status/artifact preview in the UI.
3. Implement source ledger generation behind `stage_next`.
4. Implement study-guide generation and approval UI.
5. Implement deck generation and approval UI.

Until those generators exist, `stage_next` should complete with a clear report rather than fail.
