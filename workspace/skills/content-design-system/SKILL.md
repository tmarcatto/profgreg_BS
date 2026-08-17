---
name: content-design-system
description: Apply the Prof Greg Content Design System to DOCX/PDF study guides, PPTX decks, visuals, and components.
---

# Content Design System Skill

Use this skill when Prof Greg needs to design, render, audit, or revise study guides, decks, callouts, diagrams, tables, glossary pages, references, or other course artifacts.

## Source Files

Read these files before applying design rules:

- `workspace/design-system/tokens.json`
- `workspace/design-system/components.md`
- `workspace/design-system/docx-rules.md`
- `workspace/design-system/pptx-rules.md`

## Core Principle

Form follows function.

The design should improve learning, navigation, application, trust, and clarity. Do not add visual weight just because a component exists.

## Brand

Preserve BuildStak identity:

- navy, orange, gray, and white palette;
- BuildStak wordmark and icon;
- clear, practical, academic-but-accessible tone.

## Study Guide Direction

Study guides should feel more academic than the legacy material while staying readable for construction workers in the United States.

Prioritize:

- source discipline;
- clear hierarchy;
- useful callouts;
- deterministic diagrams;
- student-friendly references.

## Deck Direction

Decks are for recorded online lessons:

- 10 slides;
- about 10 minutes;
- no speaker notes by default;
- lecture only;
- main key points;
- presentation-native layout.

Do not generate decks before human approval of the final study guide.

## Visual Rules

Use visual preference order:

1. Deterministic diagram, chart, process flow, map, or structured visual.
2. Trusted technical/source-based image with attribution.
3. Generated conceptual image only as fallback.

Captions must teach. They should explain why the figure matters.

## Callout Rules

Callouts are allowed only when they improve learning, practical application, emphasis, or course continuity.

Remove callouts that repeat adjacent prose.

## Audit Checklist

Before approving a designed artifact:

- Brand tokens applied consistently.
- No obsolete Claude/Manus operational wording.
- No BuildStak visual identity drift.
- No excessive callout density.
- Tables are used only for real structured information.
- Each diagram declares why a process flow, relationship map, comparison matrix, or card sequence is the best mechanism for its learning job.
- Figures have source status and pedagogical captions.
- DOCX/PDF remains readable and academic.
- PPTX remains sparse, visual, and presentation-native.
