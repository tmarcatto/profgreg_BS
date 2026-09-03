# Study Guide Draft Contract

This contract defines how Prof Greg turns an approved Course Map and source ledger into an English lesson guide.

The study guide is the main student-facing artifact. It must be academically stronger than the legacy material while remaining practical, readable, and useful for residential construction workers in the United States.

## Audience and Sector Anchor

Prof Greg is residential-construction-first.

- Default examples, scenarios, cases, jobsite language, images, and diagrams to U.S. residential construction.
- Preferred contexts include single-family homes, townhomes, multifamily/light residential where useful, remodeling, small builders, subcontractors, independent tradespeople, and residential field supervisors.
- Large commercial or infrastructure examples are allowed only when they clarify a concept, demonstrate contrast, or are required by a formal source. They must not become the default learner setting.
- Student-facing scenarios and visuals should respectfully reflect the U.S. residential construction workforce, including American-born and immigrant workers.
- Never stereotype role, skill, safety behavior, or language ability by nationality or immigration background.

## Required Inputs

- Approved `course_map.md`.
- Approved or in-progress `course_map.json`.
- `source_ledger.json` or an explicit source research plan.
- Lesson number and title.
- Course level: Basic, Intermediate, or Advanced.
- Prof Greg Content Design System, when available.

## Hard Gates

- Do not draft a lesson without an approved Course Map.
- Do not invent prior or future lesson content.
- Do not invent sources, statistics, standards, or quotes.
- Do not generate the PPTX deck before a human approves the final study guide.
- If a required source is missing, draft around supported content or flag the gap.

## Lesson Depth

Length is adaptive:

- Basic: roughly 10 pages per lesson.
- Intermediate: roughly 15 pages per lesson.
- Advanced: roughly 15 pages per lesson with higher technicality.

The exact length depends on lesson function, source coverage, technical density, and learner needs. Lessons within the same course should stay reasonably consistent, with small variations when the content demands it.

Section word counts are not fixed. Each section should be as deep as needed and no deeper than useful.

## Required Lesson Architecture

Each study guide should include:

1. Cover.
2. Introduction and learning objectives.
3. MECE lesson sections.
4. Summary and key takeaways.
5. Glossary.
6. Student-friendly references.

The Summary and Key Takeaways section must contain 4-6 concise, non-repetitive bullet points. Use one complete sentence per bullet and no paragraph prose.

The study guide is student-facing. Do not include internal production metadata such as audience notes, prerequisite notes, unit policy, source policy commentary, or AI workflow explanations unless the user explicitly asks for an instructor/internal edition.

## Section Rules

- Use 3-6 sections unless the lesson function clearly requires otherwise.
- Do not add a Lesson Roadmap page.
- Do not use H3 or deeper Markdown headings.
- Avoid em dashes, en dashes, and spaced hyphens as sentence punctuation.
- Sections must be mutually exclusive and collectively exhaustive.
- Each section needs a setting question or learning tension.
- Each section should include practical residential construction relevance by default.
- Avoid academic heaviness that does not help the learner act, decide, or understand.
- Avoid shallow motivational filler.

## Callout Rules

Current callout vocabulary:

- `APPLY IT`
- `KEY TERM`
- `HANDS-ON EXAMPLE`
- `SCENARIO`
- `CALLBACK`
- `BRIDGE`

Callouts are allowed only when they improve learning, application, emphasis, or continuity.

Do not use callouts as decoration. Do not use them to repeat adjacent text.
Do not use callouts in structural sections such as table of contents, summary/key takeaways, glossary, or references.
Do not place two callouts back-to-back without explanatory body text between them. If two adjacent callouts serve the same teaching moment, combine them into one callout.
Callouts should usually be short. One paragraph is typical; more than three paragraphs should be rare and justified by the lesson.

Ordered procedures must use a real Markdown numbered list with one step per source line. Never place multiple numbered steps inside one paragraph.

Recommended use:

- `KEY TERM`: for vocabulary with real course value.
- `APPLY IT`: for concrete actions learners can try.
- `HANDS-ON EXAMPLE`: for a short learner task using supplied inputs, followed by a brief answer/check. Do not use it as a container for ordinary explanatory prose.
- `SCENARIO`: for one meaningful applied situation, not every lesson by default.
- `CALLBACK`: for real prior-lesson continuity from the Course Map.
- `BRIDGE`: for one clear transition to the next lesson or future course concept.

## Citation and Reference Style

Use Greg student-friendly references.

Prioritize reading flow. Inline citations are optional and should appear only when they strengthen the learning moment, highlight an important factual claim, or support a high-stakes technical statement.

Every important factual claim must still be traceable in the source ledger, even if it does not carry an inline citation in the lesson body.

## Visual Rules

For every planned visual, first decide whether an image is required, helpful, or not needed and state the pedagogical reason. Then compare a deterministic diagram, trusted real/source image, and generated conceptual image. If an image wins, choose one acquisition route: reuse allowed reference material, search online for a verified attributable asset, generate a conceptual image, or ask the operator after the applicable alternatives are unsuitable or exhausted.

An operator request must render in the operator-facing draft as a red box in the intended figure position. The box must contain the image description, pedagogical reason, and focused search phrase. It remains blocked from final student release until the image is supplied and the course book is rerendered.

Visuals must be visible, coherent, and aligned with the artifact language. In translated versions, if the image cannot be regenerated in the target language, captions/subtitles and surrounding explanatory text must be translated.

Every visual must have a clear internal teaching purpose. Do not print "learning line" language in student-facing captions. If a visual does not teach something distinct, remove it.

Diagram selection must follow content logic. Numbered steps, priority order, sequence, workflow, or first/next/then/finally language requires a process flow with visible direction. Unconnected cards are allowed only for unordered groups. A comparison across shared variables requires a matrix with one variable column plus one dedicated column for each compared entity; never pack both entities into one narrative cell. Visual QA must compare the source content, selected mechanism, visible labels, order, matrix structure, and caption before approval.

When the core message depends on reading a real document, symbol, schedule, plan, or technical drawing, prioritize real-source examples or deterministic diagrams based on verified conventions. Do not use generated imagery to fake a real technical example.

## Glossary Rules

- Include current-lesson terms only.
- Do not redefine a term whose home lesson is earlier in the Course Map.
- If a prior term is needed, use a callback or short reminder.
- Definitions should be clear for construction workers in the U.S. market.
- For multi-lesson courses, update and validate the course registry so glossary home lessons remain explicit.

## Reviewers

Before final approval, run separate reviewer passes:

- Pedagogy Reviewer.
- Citation Reviewer.
- Design QA.
- Visual QA.

Before routing to DOCX/PDF production, run:

```bash
python3 tools/greg_study_guide_content_check.py lesson_draft/lesson_[NN]_draft.md
```

The checker must pass. It blocks activity/quiz language, callouts in structural sections, back-to-back callouts, overlong callouts, visible internal "learning line" language, and student-facing access dates.

The drafter is not the only judge of its own work.

## Human Gate

The final English study guide requires human approval before deck generation.

After human approval, downstream production may continue to:

- PPTX deck for recorded online video lessons;
- PT-BR localization;
- ES-419 localization;
- embedded visual finalization.

## Output Artifacts

For each lesson run, produce:

```text
lesson_draft/lesson_[NN]_draft.md
review/lesson_[NN]_pedagogy_review.md
review/lesson_[NN]_citation_review.md
review/lesson_[NN]_design_qa.md
review/lesson_[NN]_visual_qa.md
```

Once approved for rendering, later stages produce DOCX and PDF.
