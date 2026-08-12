# Run Folder Contract

Each Prof Greg course or lesson production run should write artifacts to a clear folder structure. The goal is traceability without forcing the student-facing content to expose internal production noise.

## Suggested Structure

```text
runs/
  [course-slug]/
    input/
    course_map/
      course_map.md
      course_map.json
      course_map_qa.md
      syllabus_adaptation_log.md
    sources/
      source_ledger.json
      research_log.md
    lesson_draft/
      lesson_01_draft.md
    review/
      lesson_01_pedagogy_review.md
      lesson_01_citation_review.md
      lesson_01_design_qa.md
      lesson_01_visual_qa.md
    docx_pdf/
      lesson_01_study_guide.docx
      lesson_01_study_guide.pdf
      lesson_01_render_qa.md
    approval/
      lesson_01_study_guide_approval.md
    deck/
      lesson_01_deck.pptx
      lesson_01_deck_r02.pptx
      lesson_01_deck_qa.md
    localization/
      pt-br/
        lesson_01_study_guide_pt-br.md
        lesson_01_localization_qa.md
        lesson_01_deck_pt-br.pptx
        lesson_01_deck_pptx_localization_qa.md
      es-419/
        lesson_01_study_guide_es-419.md
        lesson_01_localization_qa.md
        lesson_01_deck_es-419.pptx
        lesson_01_deck_pptx_localization_qa.md
    process_review/
      canonical_artifacts.json
      canonical_artifacts.md
      lesson_01_operator_report.md
      lesson_01_pipeline_qa.md
      full_flow_test_report.md
```

Use `tools/greg_create_run.py` to create this structure for new v0 runs when available.

## Gate Logic

- Course Map can be approved autonomously by Greg after QA.
- Study guide requires human approval before deck generation.
- Deck is generated only after final study guide approval.
- Localization runs after approved English artifacts.
- During v0, localization may be produced as Markdown plus QA before DOCX/PDF/PPTX rendering is automated.
- During full-flow tests, finish with `process_review/full_flow_test_report.md` even when some artifacts are blocked.

## Naming

- Use lowercase slugs for folders.
- Use `lesson_01`, `lesson_02`, etc. for stable ordering.
- Avoid spaces in generated artifact filenames.
- For revised student-facing PPTX decks after human feedback, use cache-safe revision filenames such as `lesson_01_deck_r02.pptx` instead of relying on overwriting the canonical file.
- Maintain `process_review/canonical_artifacts.json` and `process_review/canonical_artifacts.md` so the active approved files are explicit.

## Traceability

Every final student-facing artifact should be traceable back to:

- input syllabus or source material;
- approved Course Map;
- source ledger;
- reviewer notes;
- human approval point, when required.

Use `workspace/contracts/canonical-artifacts-contract.md` for canonical selection and revision rules.
