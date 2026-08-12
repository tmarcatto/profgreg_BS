# Prof Greg Content Design System - PPTX Rules

## Output Role

The PPTX deck supports a recorded online video lesson. It is not a compressed version of the apostila.

The study guide carries depth. The deck carries the live teaching path.

## Default Format

- 10 slides per lesson.
- About 10 minutes per lesson.
- No speaker notes by default.
- Lecture material only.
- Focus on the main key points.
- Presentation-native layout, not a direct copy of the DOCX.

## Required Slide Arc

Default 10-slide structure:

1. Title and lesson promise.
2. Why this lesson matters.
3. Core concept 1.
4. Core concept 2.
5. Core concept 3.
6. Practical example or decision frame.
7. Visual summary or process diagram.
8. Common mistake or risk.
9. Key takeaways.
10. Lesson takeaway.

Adjust only when the lesson function clearly requires it.

## Visual Style

- Use the BuildStak palette.
- Use the negative BuildStak wordmark on navy, black, or any dark background. Use the standard logo assets only on white or light backgrounds.
- Prefer large, clear text.
- Use one main idea per slide.
- Use diagrams and structured visuals over decorative images.
- Avoid dense paragraphs.
- Avoid academic citation clutter on slides.
- Keep references in study guide, not slide bodies, unless a source is central to the teaching point.
- Do not highlight the last item in a sequence by default. Highlight only when the highlighted item has a clear student-facing reason: exception, warning, decision point, risk threshold, contrast, or lesson emphasis.
- If all items have equal importance, keep the sequence visually even.

## Typography

Use tokens from `tokens.json`.

Guidelines:

- Slide title: large, navy, bold.
- Section labels: small orange labels.
- Body: readable, sparse, high contrast.
- Captions: small gray only when necessary.
- Key numbers: orange, large, and used sparingly.

## Image Rules

Visual preference order:

1. Deterministic diagram, chart, process flow, map, or structured visual.
2. Trusted technical/source-based image with attribution.
3. Generated conceptual image only as fallback.

Generated images must never pretend to be real jobsite evidence.

## Gate

Do not generate a PPTX deck until the final English study guide has human approval.

This is the main human gate in the workflow.
