# Full-Flow V0 Execution Checklist

Use this checklist during a new test run. Mark each item as pass, fail, blocked, or skipped with a short reason.

## 1. Intake

- Create `runs/[course-slug]/`.
- Save the completed intake under `input/intake.md`.
- Save original user material under `input/`.
- Record assumptions and missing information.

Exit condition: scope, level, and input material are traceable.

## 2. Course Map

- Produce `course_map/course_map.md`.
- Produce `course_map/course_map.json`.
- Produce `course_map/syllabus_adaptation_log.md`.
- Produce `course_map/course_map_qa.md`.
- Include lesson sequence, learner progression, callbacks, bridges, key terms, and rationale.
- If Greg changes lesson count, record the logic.
- Run autonomous Course Map QA with `tools/greg_course_map_quality_check.py`.

Exit condition: Course Map is approved autonomously or blocked with reason.

## 3. Sources

- Produce `sources/source_ledger.json`.
- Produce `sources/research_log.md`.
- Produce `sources/student_references.md`.
- Produce `sources/source_gaps.md`.
- Prefer field bodies of knowledge and authoritative organizations over generic web sources.
- Log every source class used.

Exit condition: every major claim category has source support or a recorded gap.

## 4. Study Guide Draft

- Produce `lesson_draft/lesson_01_draft.md`.
- Match course level and audience.
- Keep English as original generation language.
- Use adaptive depth instead of fixed section word counts.
- Include glossary, references, callouts, examples, and checks for placeholders.
- Run `tools/greg_study_guide_content_check.py` before DOCX/PDF rendering.

Exit condition: draft is ready for reviewer passes.

## 5. Review Gates

- Produce `review/lesson_01_pedagogy_review.md`.
- Produce `review/lesson_01_citation_review.md`.
- Produce `review/lesson_01_design_qa.md`.
- Produce `review/lesson_01_visual_qa.md`.
- Reviewer roles must identify issues, not just approve.

Exit condition: issues are fixed, accepted as v0 limitations, or explicitly blocked.

## 6. DOCX/PDF Production

- Produce `docx_pdf/lesson_01_study_guide.docx` when possible.
- Produce `docx_pdf/lesson_01_study_guide.pdf` when possible.
- Produce `docx_pdf/lesson_01_render_qa.md`.
- Render pages or previews when tooling allows.
- Record any `soffice` or rendering blocker.

Exit condition: final English study guide artifact exists or production blocker is documented.

## 7. Human Approval Gate

- Create `approval/lesson_01_study_guide_approval.md`.
- Ask for human approval before generating the deck.
- If approved as v0, record `Approval mode: v0_process`.

Exit condition: deck generation is either authorized or blocked.

## 8. English Deck

- Produce `deck/lesson_01_deck.pptx`.
- Produce `deck/lesson_01_deck_qa.md`.
- Use 10 slides for about a 10-minute recorded lesson.
- Do not include speaker notes.
- Keep lecture-only focus on key points.
- Render slides and check overflow.

Exit condition: deck passes v0 QA or issues are documented.

## 9. Localization

- Produce PT-BR study guide smoke test or localized text artifact.
- Produce ES-419 study guide smoke test or localized text artifact.
- Produce deck text maps for PT-BR and ES-419.
- Run localization QA for both locales.
- Preserve U.S. construction market context.
- Keep imperial units unless metric helps understanding.

Exit condition: localization text is reviewed or blocked.

## 10. Localized PPTX Production

- Produce PT-BR deck PPTX if enabled.
- Produce ES-419 deck PPTX if enabled.
- Render all localized slides.
- Check real slide count, overflow, and authored speaker-note text.
- Create visual montage for each localized deck.

Exit condition: localized decks pass v0 QA or issues are documented.

## 11. Process Review

- Run `tools/greg_lesson_pipeline_qa.py [course-slug] --lesson 1 --include-localization`.
- Save the consolidated report as `process_review/lesson_01_pipeline_qa.md`.
- Create `process_review/full_flow_test_report.md`.
- Summarize what worked, failed, and felt awkward.
- List required changes to contracts, skills, templates, rendering, visual policy, and localization.
- Recommend v1 improvements.

Exit condition: the test has actionable learning, even if some artifacts failed.
