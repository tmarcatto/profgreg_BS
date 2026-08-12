# Prof Greg DOCX/PDF Production Contract

This contract defines how Prof Greg turns an approved study guide draft into final student-facing DOCX/PDF artifacts.

For the student-facing layout template, follow `workspace/contracts/student-guide-layout-template-contract.md`.

Renderer implementation should also follow `workspace/contracts/reusable-renderer-contract.md`.

Preferred production path:

```text
docx_pdf/lesson_[NN]_study_guide_spec.json
tools/greg_render_study_guide_from_spec.py docx_pdf/lesson_[NN]_study_guide_spec.json
```

The spec-driven renderer is the default path for new work. Course-specific or lesson-specific builders are allowed only as temporary migration references and must not become the canonical production path.

The DOCX/PDF stage is not a writing stage. It is a production, rendering, and visual QA stage.

## Purpose

Produce polished study guide artifacts that are:

- readable for residential construction workers and professionals in the United States;
- academically stronger than the legacy material;
- practical and not intimidating;
- traceable to the approved draft, source ledger, and review files;
- visually consistent with the Prof Greg Content Design System.

## Required Inputs

Before production starts, these files must exist:

- `course_map/course_map.md`
- `course_map/course_map.json`
- `sources/source_ledger.json`
- `lesson_draft/lesson_[NN]_draft.md`
- `review/lesson_[NN]_pedagogy_review.md`
- `review/lesson_[NN]_citation_review.md`
- `review/lesson_[NN]_design_qa.md`
- `review/lesson_[NN]_visual_qa.md`
- `workspace/design-system/tokens.json`
- `workspace/design-system/components.md`
- `workspace/design-system/docx-rules.md`

## Gate Requirements

Production may begin only when:

- Pedagogy Review is not blocked.
- Citation Review is not blocked.
- Design QA is not blocked.
- Visual QA is not blocked.
- Any required visual source gaps are resolved or explicitly deferred.

If a gate fails, write a blocked production note instead of producing final artifacts:

```text
docx_pdf/lesson_[NN]_production_blocked.md
```

## Outputs

Standard outputs:

```text
docx_pdf/lesson_[NN]_study_guide.docx
docx_pdf/lesson_[NN]_study_guide.pdf
docx_pdf/lesson_[NN]_render_qa.md
```

Optional supporting outputs:

```text
docx_pdf/assets/
docx_pdf/rendered_pages/
```

Technical validation revisions may use revisioned outputs such as:

```text
docx_pdf/lesson_[NN]_study_guide_r02.pdf
docx_pdf/rendered_pages_r02/
```

Revisioned outputs do not replace the approved student-facing artifact until a human approval record explicitly promotes them.

## Production Rules

- Preserve the approved lesson meaning.
- Preserve the residential-construction-first audience anchor. Do not make the rendered examples, cases, diagrams, or images feel primarily commercial unless the approved lesson explicitly requires that contrast.
- Do not add unsupported claims during layout.
- Do not expand the lesson just to fill pages.
- Do not expose internal production metadata in student-facing front matter.
- Convert Markdown callout tables into designed callout components.
- Convert visual placeholders into final diagrams or sourced images when available.
- Keep student-friendly references.
- Keep the static TOC clean.
- Use page breaks intentionally.
- Keep cover, lesson roadmap/TOC, summary/key takeaways, glossary, and references as clean structural sections.
- Use the approved BuildStak study-guide cover/layout system; do not create a new cover design per course.
- The lesson body must start on a new page after the Introduction/Learning Objectives page.
- Render the lesson roadmap as a clean list, not a table, unless the user explicitly approves a table.
- Render lesson section headings as `Section NN - Section Name`, not abbreviated labels such as `SEC.`.
- Do not place a question/subtitle immediately under section headings. Lesson section content starts directly after the section heading.
- Never leave a section break with only the heading or one intro line before a page break. Keep the section heading and enough opening body text together.
- Never leave a subsection heading as the last visible element on a page. Keep each subsection heading with its first paragraph, list, diagram, or callout.
- Student-facing references must not include access dates such as "Accessed August 9, 2026"; keep access dates only in the internal source ledger when needed.
- Do not render two callout boxes back-to-back without explanatory body text between them. If they serve the same teaching moment, combine them into one callout.
- Avoid decorative visuals that do not teach.

## Visual Rules

Visual preference order:

1. Deterministic diagram, chart, process flow, map, or structured visual.
2. Trusted technical/source-based image with attribution.
3. Generated conceptual image only as fallback.

Every final visual must have:

- figure number;
- teaching purpose;
- source status;
- caption;
- readable text;
- language consistent with the artifact.
- residential-context fit unless the visual is explicitly a commercial/industrial contrast.
- respectful workforce representation when people are depicted, including the possibility of American-born and immigrant construction workers without stereotyping.

The teaching purpose is an internal QA field. Do not print "learning line" language in student-facing figure captions.

If a diagram includes explanatory text, place that text above or inside the diagram structure. Do not place explanatory diagram text below the diagram where it can be confused with the figure caption or source legend.

## Render QA

Before final delivery, inspect rendered output.

Check:

- cover hierarchy;
- logo placement;
- table of contents;
- student-facing front matter;
- heading hierarchy;
- callout spacing;
- callouts absent from structural sections;
- adjacent callout boxes;
- footer includes the course name and does not need to mention Prof Greg;
- figure placement;
- figure uniqueness and learning value;
- table readability;
- glossary layout;
- references layout;
- page breaks;
- orphan section headings or one-line section openings;
- orphan subsection headings;
- section-heading questions/subtitles;
- access dates in student-facing references;
- blank pages;
- text overflow;
- visual readability;
- visual distortion, overlaps, missing arrows/symbols, and excessive blank areas.

Run the PDF layout checker after text extraction is available:

```text
tools/greg_pdf_layout_check.py docx_pdf/lesson_[NN]_study_guide.pdf --qa docx_pdf/lesson_[NN]_render_qa.md
```

This automated check does not replace visual page inspection. It verifies the structural rules that can be checked from extracted text:

- approved page sequence;
- cover text elements;
- roadmap placement;
- introduction/objectives placement;
- body start after objectives;
- summary, glossary, and references pages;
- forbidden student-facing strings such as `SEC.`, `learning line`, access dates, local paths, and internal source rationale;
- callout labels absent from structural tail sections;
- rendered page PNG count matching PDF page count.
- body-content pages are not suspiciously sparse unless they carry a figure or are the final body page;
- content pages do not end with an explicit section heading or isolated callout label;
- section openings are not limited to only a heading or one line;
- callout labels are not isolated from their body text;
- figures appear at a reasonable cadence through the body;
- rendered figure captions match the expected figure list from the study-guide spec.

Fix failures before delivery. Warnings require either a correction or a note in the render QA explaining why the artifact still passes.

Record findings in:

```text
docx_pdf/lesson_[NN]_render_qa.md
```

## Human Gate After Production

After DOCX/PDF production, the human must approve the study guide before deck generation.

Capture approval in:

```text
approval/lesson_[NN]_study_guide_approval.md
```

Never generate a PPTX deck before this approval exists and clearly approves the study guide.
