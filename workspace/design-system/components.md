# Prof Greg Content Design System - Components

## Purpose

The Prof Greg Content Design System turns course content into student-facing DOCX/PDF study guides and PPTX lecture decks. It preserves the BuildStak palette and brand assets while removing old production dependencies and tool names.

The design should feel more academic than the legacy material, but still practical and readable for construction workers in the United States.

## Core Principle

Form follows function. Every visual, callout, table, diagram, and page break must improve learning, navigation, application, or trust.

## Brand Elements

- Wordmark: `workspace/assets/logos/buildstak-wordmark.png`
- Negative wordmark for dark backgrounds: `workspace/assets/logos/buildstak-wordmark-negative.png`
- Icon: `workspace/assets/logos/buildstak-icon.png`
- Palette: navy, orange, gray, and white from `tokens.json`.

Logo contrast rule:

- Use the standard logo assets on white or light backgrounds.
- Use the negative wordmark on navy, black, or any dark background.
- Do not place the standard navy/orange mark directly on navy or dark backgrounds.

## Cover

The study guide cover is typographic and restrained.

Required elements:

- BuildStak icon as a restrained brand signature.
- Course name as the dominant title.
- Small orange divider.
- Lesson title below the divider.
- `LESSON N` label.
- Course level.
- Short relevant quote or provocative line when available and source-safe.
- Bottom label: `Study Guide for Construction Professionals`.

Avoid:

- Decorative hero images.
- Internal audience, prerequisite, unit, or production notes.
- Heavy boxes.
- Marketing-style slogans.
- Key Concept tags unless later approved.

## Static Table of Contents

Use a clean static TOC.

Rules:

- No page numbers.
- No dotted leaders.
- No automatic Word fields.
- One entry per paragraph line.
- Section entries use `SEC. NN - [title]`.
- Include Introduction, all sections, Summary, Glossary, References, and localization appendix if applicable.

## Section Opener

Each section opens with:

- `SEC. NN` in orange.
- Section title in navy.
- Setting question in italic.
- Mini-index of 3-5 short concepts when useful.
- Thin orange divider.

The opener should orient the reader, not become a decorative card.

## Callouts

Current vocabulary:

- `APPLY IT`
- `KEY TERM`
- `PULL-QUOTE`
- `HANDS-ON EXAMPLE`
- `SCENARIO`
- `CALLBACK`
- `BRIDGE`

Callouts are good, but they must not become heavy, decorative, or excessive.

Use a callout only when it improves:

- learning;
- practical application;
- emphasis;
- continuity across lessons.

Remove a callout if it repeats adjacent prose.
Do not place callouts in structural sections such as the static TOC, summary/key takeaways, glossary, or references.
Keep callouts concise: one paragraph is typical, and three paragraphs is a hard practical ceiling unless the lesson explicitly needs a worked example.

Recommended use:

- `KEY TERM`: vocabulary with course value.
- `APPLY IT`: concrete learner action.
- `HANDS-ON EXAMPLE`: worked calculation, workflow, or applied judgment.
- `SCENARIO`: sparingly, for a meaningful applied situation.
- `CALLBACK`: real prior-lesson continuity from the Course Map.
- `BRIDGE`: one transition to the next lesson or future concept.
- `PULL-QUOTE`: sparingly, only for memorable principles.

## Figures

Visual preference order:

1. Deterministic diagram, chart, process flow, map, or structured visual.
2. Trusted technical/source-based image with attribution.
3. Generated conceptual image only as fallback.

Every figure needs:

- explicit purpose;
- figure number;
- distinct learning line;
- source status;
- pedagogical caption.

Captions are micro-lessons. They should explain why the visual matters, not merely label it.

Visual QA must reject figures with failed arrows, missing symbols, excessive blank space, distorted source images, unreadable text, inconsistent font scale, repeated information without a clear comparison note, or text/shape overlap.

## Tables

Use tables only for true row/column comparison or lookup.

Good table uses:

- glossary;
- compact comparison;
- source matrix;
- checklist;
- decision scorecard.

Avoid tables for normal paragraphs.

Table rules:

- Navy header with white text.
- Alternating light gray rows when useful.
- Clear padding.
- No dense full-page spreadsheet feel.
- Keep tables short where possible.

## Glossary

Glossary uses current-lesson terms only.

Rules:

- Term column: 25%.
- Definition column: 75%.
- Alphabetical order.
- Do not redefine prior lesson terms.
- If a prior term is necessary, use a callback or short reminder.

## References

Use Greg student-friendly references.

References should be useful to students and traceable to the source ledger. They should not read like decorative academic furniture.

Inline citations are optional and reserved for moments where they strengthen trust or emphasize an important claim.
