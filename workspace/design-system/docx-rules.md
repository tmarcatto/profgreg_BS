# Prof Greg Content Design System - DOCX/PDF Rules

## Output Role

The DOCX/PDF study guide is the deep student-facing artifact. It carries the full explanation, examples, glossary, references, and durable learning structure.

## Page and Typography

- Page size: US Letter.
- Margins: 1 inch unless a later template overrides this.
- Primary font: Arial.
- Body: 11 pt, gray body, 1.4 line spacing.
- Headings: navy, bold, clear hierarchy.
- Accent: orange for lesson labels, dividers, current-state highlights, and selected callout accents.

## Editorial Style

The apostila should feel more academic than the legacy material:

- stronger conceptual framing;
- more careful claims;
- better source discipline;
- less marketing language;
- more precise examples.

But it must remain approachable:

- direct sentences;
- practical construction context;
- no unnecessary academic jargon;
- no dense walls of text without visual anchors.

## Lesson Length

Length is course-level and adaptive:

- Basic: roughly 10 pages per lesson.
- Intermediate: roughly 15 pages per lesson.
- Advanced: roughly 15 pages with higher technicality.

Form follows function. Do not pad content to hit a page target.

## Required Structure

Each DOCX/PDF study guide should include:

1. Cover.
2. Static table of contents.
3. Introduction.
4. Lesson map or course-position visual.
5. Learning objectives.
6. MECE lesson sections.
7. Summary and key takeaways.
8. Glossary.
9. Student-friendly references.

Do not add internal production metadata to the student-facing front matter. Audience, prerequisites, unit policy, source policy, workflow notes, and QA status belong in run files, not on the study guide cover or opening pages.

## Page Flow

- Use simple page breaks for major sections.
- Avoid section breaks unless a renderer requires them for a specific reason.
- Avoid blank-page artifacts.
- Conditional page breaks are allowed before major sections when the current page is too full.
- Cover should occupy one page.
- Lesson roadmap/static TOC should start on its own page.
- Summary/key takeaways, glossary, and references should be clean structural sections.
- Main lesson sections should flow continuously unless a page break improves navigation.

## Visual Embedding

Final DOCX/PDF should embed visuals automatically once the visual pipeline is stable.

Rules:

- Deterministic diagrams should be generated as clean SVG or high-resolution PNG.
- Sourced technical images require attribution.
- Generated conceptual images are fallback only.
- Visuals must be in the artifact language when feasible.
- If an image cannot be regenerated in the target language, translate captions/subtitles and surrounding explanatory text.

## Callouts

Callouts should be visually distinct but not loud.

Use restrained fills, borders, and typography. Callouts must not cluster. Leave enough normal prose between them.
Callouts should not appear in structural sections such as TOC, summary/key takeaways, glossary, or references.
Callouts should usually be short: one paragraph is typical, and three paragraphs is the practical upper bound.

## Footer

Default footer pattern:

- small BuildStak icon on the lower left;
- page number on the lower right;
- no heavy footer bars unless a later template requires them.

## Review Gate

Before final DOCX/PDF delivery:

- Pedagogy Review passes.
- Citation Review passes.
- Design QA passes.
- Visual QA passes.
- Rendered pages are visually inspected when DOCX/PDF rendering tooling is active.

## Human Gate

The English study guide must be human-approved before any PPTX deck is generated.
