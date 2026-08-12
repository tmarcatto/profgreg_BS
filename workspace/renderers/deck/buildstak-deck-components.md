# BuildStak Deck Components - Phase 3

This file defines reusable deck components for Prof Greg PPTX production.

The goal is to stop rebuilding slide layouts ad hoc. Deck generation should choose from these components, fill them with lesson-specific content, render the deck, and run deck QA before delivery.

## Global Frame

Use on every content slide except the cover:

- white background;
- top-left orange eyebrow: `LESSON [N]`;
- bottom-left BuildStak symbol;
- footer text: course title only;
- bottom-right two-digit slide number;
- footer must stay outside the main content zone.

Main content safe zone:

```text
left: 72
top: 82
right: 1208
bottom: 640
```

Footer zone:

```text
top: 660
bottom: 700
```

No primary layout object may overlap the footer zone.

## Component: Cover

Purpose:

- orient the learner;
- identify course, lesson, and main topics;
- avoid marketing-page composition.

Required content:

- BuildStak brand treatment;
- course title;
- lesson number;
- lesson title;
- 3-4 main topics.

Rules:

- no visible lesson timing;
- no instructor notes;
- no generic inspirational filler;
- no decorative image unless it clearly supports the lesson concept.
- use the negative BuildStak wordmark on navy or any dark cover/sidebar background.

## Component: Image + Teaching Bullets

Purpose:

- soften text-heavy flow;
- anchor an abstract idea in a concrete visual.

Layout:

- left text, right image or right text, left image;
- generated/sourced image must occupy no more than half the slide;
- image must not include subtitles, captions, or visible text labels unless the image is a real technical source where text is intrinsic and legible.
- default image setting is U.S. residential construction, not large commercial construction.
- if people appear, the image should respectfully reflect the U.S. residential construction workforce, including American-born and immigrant workers when appropriate.

Rules:

- no image caption under the image;
- slide title carries the teaching point;
- visible bullets explain what the student should notice.

## Component: Balanced Sequence

Purpose:

- show equal-priority steps, habits, checks, categories, or components.

Layout:

- 3-5 equal cards or rows;
- consistent fill, border, title style, and body style across all items;
- connectors only when order matters.

Rules:

- never highlight the last item by default;
- if all items are equal, no item is highlighted;
- if order matters, numbering may show order without visual emphasis;
- use this for habits, checklists, documentation fields, and equal categories.

## Component: Escalation Or Decision Trigger Matrix

Purpose:

- show when a learner should treat a situation differently.

Layout:

- 4-6 trigger boxes;
- one compact takeaway below or beside the matrix;
- no step arrows unless it is truly a sequence.

Rules:

- highlight only if one trigger is the lesson's current exception or warning;
- do not use the same component immediately after another sequence component unless the teaching function is clearly different.

## Component: Paired Record Rows

Purpose:

- connect a prompt/question to the specific record field the learner should capture.

Layout:

- rows with prompt on left and field/value on right;
- related prompt and answer must be close enough to read as a pair;
- answers must be meaningful, not single vague words unless the slide is intentionally building a mnemonic.

Rules:

- no floating answer column;
- no final-row highlight unless that row is a genuine exception or decision threshold;
- row labels should fit without awkward wrapping.

## Component: Overlap Or Comparison

Purpose:

- explain the difference or overlap between two concepts.

Layout:

- two large regions plus overlap, or two columns plus center bridge;
- each side has comparable density;
- overlap labels must be legible and not crowded.

Rules:

- use only when the comparison is central to the lesson;
- do not use for simple lists.

## Component: Lesson Takeaway

Purpose:

- close the recorded lesson with one durable idea.

Required content:

- short label: `Lesson [N] takeaway`;
- one core takeaway statement;
- optional supporting statement in a single box.

Rules:

- no preview of the next lesson;
- no activity prompt;
- no rhetorical question as the main close unless the course design explicitly asks for it.

## Slide Similarity Rule

Adjacent or near-adjacent slides may share style, but not teaching function.

Prof Greg should treat similarity as a QA signal, not an automatic failure. A slide pair needs review when:

- visible text is highly similar; or
- nearby slides use the same teaching function and also share meaningful vocabulary.

Before delivery, check:

- Are two slides teaching the same action sequence?
- Could the learner explain why both slides exist?
- Does each slide have a distinct main idea?
- If two slides use similar card layouts, does one show routine practice while the other shows a different function such as risk threshold, comparison, or case example?

If not, merge, rewrite, or change the component.

The deck QA tool approximates this with text similarity and simple slide-function classification. Human-readable QA notes should still explain the MECE distinction for any pair that could look similar.

## Highlight Rule

Highlighting is a teaching signal, not decoration.

Allowed reasons:

- exception;
- warning;
- decision point;
- risk threshold;
- comparison contrast;
- current lesson emphasis.

Disallowed reasons:

- last item;
- final step;
- visual balance;
- accent color quota;
- "it looks better";
- arbitrary hierarchy.

If a highlight exists, the QA note must state the reason.
