# Prof Greg Deck Production Contract

This contract defines how Prof Greg produces PPTX lecture decks from approved study guides.

Renderer implementation should follow `workspace/contracts/reusable-renderer-contract.md`.

The deck is for a recorded online lesson. It is not a condensed copy of the study guide.

## Purpose

Produce a presentation-native 10-slide deck that supports a concise recorded lesson.

The deck should:

- teach the main key points;
- use sparse, readable slide text;
- include strong visual structure;
- include purposeful diagrams, images, process visuals, comparisons, or decision frames when they make the recorded lesson clearer;
- follow the approved study guide;
- avoid speaker notes;
- avoid class activities, quizzes, or reflection prompts unless explicitly requested.

## Audience and Visual Anchor

Prof Greg decks are residential-construction-first.

- Default examples, case applications, images, and diagrams to U.S. residential construction.
- Use single-family, townhome, multifamily/light residential, remodeling, small builder, subcontractor, and independent trade contexts before large commercial contexts.
- Large commercial imagery is allowed only as contrast or when the concept requires it; it must not dominate the deck.
- Images with people should respectfully reflect the real U.S. residential construction workforce, including American-born and immigrant workers.
- Do not stereotype nationality, immigration background, language, role, skill, or safety behavior.

## Required Inputs

Before deck production starts, these files must exist:

- `course_map/course_map.md`
- `course_map/course_map.json`
- `sources/source_ledger.json`
- `lesson_draft/lesson_[NN]_draft.md`
- `docx_pdf/lesson_[NN]_study_guide.pdf` or `docx_pdf/lesson_[NN]_study_guide.docx`
- `docx_pdf/lesson_[NN]_render_qa.md`
- `approval/lesson_[NN]_study_guide_approval.md`
- `deck/lesson_[NN]_visual_plan.json` or an approved visual plan adapted from `review/lesson_[NN]_visual_plan.json`
- `workspace/design-system/tokens.json`
- `workspace/design-system/pptx-rules.md`
- `workspace/renderers/deck/buildstak-deck-components.md`

## Hard Gate

Do not generate a PPTX deck unless the approval file exists and allows deck generation.

If the gate fails, write:

```text
deck/lesson_[NN]_deck_blocked.md
```

The blocked note must explain:

- which approval file is missing or invalid;
- what the user needs to approve;
- which artifact is waiting for approval.

## Standard Output

```text
deck/lesson_[NN]_deck.pptx
deck/lesson_[NN]_deck_qa.md
```

## Revision and Cache-Safe Naming

The first delivered deck for a lesson may use the canonical filename:

```text
deck/lesson_[NN]_deck.pptx
```

After any human feedback or revision request, do not overwrite the previously delivered PPTX as the only deliverable. Generate a new cache-safe revision filename:

```text
deck/lesson_[NN]_deck_r[RR].pptx
```

Example:

```text
deck/lesson_01_deck_r02.pptx
```

The revision number must increase for every human-visible deck revision. This prevents stale previews, app cache, Quick Look cache, browser cache, or PowerPoint file handles from showing an older version while the filesystem has newer content.

The QA file must state:

- canonical deck path;
- latest revision deck path;
- revision reason;
- whether the revision was visually inspected after export.

Optional:

```text
deck/assets/
deck/rendered_slides/
```

## Slide Count and Duration

Default:

- 10 slides;
- pacing is used internally only;
- never mention lesson time or slide timing in visible student-facing slide text;
- no speaker notes;
- lecture only.

## Required Slide Arc

Default 10-slide structure:

1. Cover: course name, lesson name, and main topics covered.
2. Why this lesson matters.
3. Core concept 1.
4. Core concept 2.
5. Core concept 3.
6. Practical example or decision frame.
7. Application, synthesis, or visual explanation using the medium that best serves the learning job.
8. Common mistake or risk.
9. Key takeaways.
10. Lesson takeaway.

Adjust only when the lesson function clearly requires it.

## Component System

Use the reusable BuildStak deck component definitions in:

```text
workspace/renderers/deck/buildstak-deck-components.md
```

Deck production should choose components by teaching function, not by decoration:

- cover;
- image plus teaching bullets;
- balanced sequence;
- escalation or decision trigger matrix;
- paired record rows;
- overlap or comparison;
- lesson takeaway.

If a slide does not fit an existing component, record why in the QA file. Do not invent a new ad hoc layout when an existing component covers the teaching function.

## Content Rules

- Use the approved study guide as the source of truth.
- Select the strongest teaching points from the study guide; do not try to compress every paragraph into slides.
- Do not introduce unsupported claims.
- Do not overload slides with paragraphs.
- Keep text large and readable, but include enough written explanation for a student to follow the recorded class. Use short bullets instead of paragraphs when listing is useful.
- Avoid both extremes: no dense walls of text, and no nearly empty slides that require the narrator to supply all meaning.
- Every slide should feel useful for a recorded class: clear enough to follow without reading a dense page, but substantial enough to support instruction.
- Prefer assertion-evidence slide logic: each slide title should state the teaching point, and the body/visual should support it.
- Apply multimedia-learning discipline: remove decorative clutter, signal the important relationship, avoid redundant text, and keep related labels close to the visual element they explain.
- Use citations only when a source is central to the teaching point.
- Keep detailed references in the study guide, not on slide bodies.
- No speaker notes by default.
- No activities, quizzes, or reflection prompts by default.

## Pedagogy-First Visual Decision

Plan every body slide in this order:

1. Define the slide's learning job.
2. Choose the teaching strategy: activate prior knowledge, anchor with a scenario, work an example, compare and contrast, trace a process, inspect evidence, diagnose and decide, or synthesize and recall.
3. Decide whether an image is required, helpful, or not needed, and record the pedagogical reason.
4. Compare all three media: native diagram, trusted real/source image, and generated conceptual image.
5. Select one medium and record why the other two are weaker for this learning job.
6. If an image is selected, choose one acquisition route: reuse supplied reference material, search online, generate, or ask the operator. If no image is selected, use `native-diagram`.
7. Choose the matching slide layout.
8. Define how text complements the visual by directing attention, explaining a rule, labeling essential structure, or stating the takeaway.

Do not start with a preferred component and pour the concept into it. Reusing the same paired-box, card-row, or process treatment without a content-specific rationale is a visual-planning failure.

## Visual Rules

- Use an image-plus-teaching-bullets slide only when a trusted real image or generated conceptual image is the selected instructional medium. The image uses no more than half of the teaching area and the adjacent text tells learners what to notice or do with it.
- Across slides 2-9, use at least four distinct layout types as an anti-repetition floor. Do not repeat a layout on adjacent slides or use one body layout more than twice. Do not choose a weaker medium or mechanism to satisfy variety.
- Include a meaningful image or strong visual break at least once every three slides.
- Generated images should not appear on consecutive slides. A 3:1 text/vector-to-image cadence is preferred; up to 5:1 is acceptable when the lesson is more technical.
- Use one dominant visual mode per slide: a slide may use a generated/sourced image with text, or a native vector diagram with labels, but do not mix a large image and a vector diagram as competing teaching visuals on the same slide.
- Generated images must be connected to the lesson concept, visually coherent with the BuildStak identity, and never take more than half of the slide.
- Generated images should not have visible subtitles, captions, or explanatory labels under/over the image. The slide text should carry the teaching point.
- Visual highlights must have a clear student-facing teaching reason. Do not highlight one item in a sequence only because it is visually convenient, because it is the last item, because it is the final step, or because the layout needs accent color.
- If every item in a sequence has equal importance, do not highlight any single item. Use consistent styling across the sequence.
- A highlighted item must either mark a genuine exception, warning, decision point, risk threshold, comparison contrast, or current lesson emphasis that the student needs to notice.
- Footer and page number must never overlap the main layout, images, or diagrams.
- Before rendering, create a deck visual plan and run `tools/greg_visual_plan_check.py`. The plan must state the teaching purpose and distinct learning claim for every non-brand visual.
- A deck generated image must not have a visible caption, subtitle, or explanatory label. The slide title and bullets carry the teaching point.
- If a slide uses a diagram with explanatory text inside the visual, place that text above or inside the diagram structure, not below where it can be confused with a caption.

Visual media are candidates, not a fixed preference order:

- Use a native diagram, chart, process, comparison, or structured visual when relationships, order, magnitude, mapping, or decision logic are the object of learning.
- Use the direct `process_flow`, `schedule_bar_chart`, and `activity_network` presentation mechanisms when learners must see ordered handoffs, time-scaled schedule behavior, or predecessor/path logic. Generic cards and paired boxes are not substitutes.
- Use a trusted technical/source-based image when learners must inspect authentic details in a real plan, schedule, form, symbol set, record, interface, tool, condition, or completed example.
- Use a generated conceptual image when concrete context, setting, human action, spatial orientation, or a scenario improves understanding and authenticity is not part of the claim.

Generated imagery is forbidden when learners need real evidence or exact technical fidelity. A real image is not automatically superior to a diagram, and a diagram is not automatically superior to a real example.

Generated conceptual images must never pretend to be real jobsite evidence.

Asset acquisition rules:

- `reuse-reference`: use an image that the supplied material permits for reuse and retain its attribution.
- `search-online`: search for a relevant, licensable, attributable real asset; the route is unresolved until a concrete asset and source record are verified.
- `generate`: use only for conceptual context when exact identity, evidence, interface, document, or technical fidelity is not the learning claim.
- `operator-request`: use only after the applicable routes above are unsuitable or exhausted. Render a red placeholder in the intended image frame containing the image description, pedagogical reason, and focused search phrase. This is an operator-facing draft, never a releasable presentation.

## Deck QA

Before delivery, inspect the deck for:

- 10-slide count;
- readable text;
- slide titles;
- one main idea per slide;
- visual consistency;
- figure readability;
- image cadence and image size;
- no image subtitles or captions;
- no arbitrary highlights;
- no automatic "last item" highlights;
- no text outside shapes or boxes;
- highlighted boxes have clear internal spacing between title and body;
- every highlighted box has a stated teaching reason in the production/QA notes;
- footer clear of the main layout;
- no speaker notes;
- no activity/quiz prompts;
- no unsupported claims;
- final slide is a lesson takeaway, not a preview of the next lesson.
- no blank or nearly empty slide, including slides that contain only a title, footer, or isolated text;
- every layout has its required visible payload: complete items, rows, comparison sides, process steps, schedule activities, network nodes, or image-plus-teaching copy;
- every body slide has a non-brand visual or container that makes the teaching relationship explicit;
- one substantive rendered PNG exists for every slide; missing or suspiciously tiny renders are hard failures;
- component choice matches slide teaching function;
- near-duplicate slides have a documented MECE distinction.
- slide similarity warnings are either resolved or explained in the QA file.
- visual plan QA passed before rendering, including the pedagogy-first comparison of all three media and the role of supporting text.
- every body slide records an image-need decision and an asset-acquisition strategy;
- every operator image request renders as a complete red request box, and any unresolved request blocks final release;
- course-level visual registry remains clean or has explicit MECE justification for repeated visual structures.
- all inspected textboxes, shapes, and images remain within slide bounds;
- no non-footer element overlaps the footer band;
- text boxes are not obviously too dense for their rendered size;
- image-led slides do not also carry a competing vector diagram as a second main visual system.

Run the deck QA checker after rendering and slide inspection metadata are available:

```text
tools/greg_deck_quality_check.py deck/lesson_[NN]_deck[_rRR].pptx --qa deck/lesson_[NN]_deck_qa.md
```

The checker uses PPTX inspection data and rendered slide layout metadata when available. It does not replace human visual review, but it must block or warn on objective failures such as footer overlap, off-slide elements, visible timing language, image captions, consecutive generated images, near-duplicate slide functions, and cache-unsafe revisions after feedback.

Run the visual plan checker before rendering:

```text
tools/greg_visual_plan_check.py deck/lesson_[NN]_visual_plan.json
```

Run the deck quality checker when an inspect file exists:

```text
tools/greg_deck_quality_check.py deck/lesson_[NN]_deck[_rRR].pptx --qa deck/lesson_[NN]_deck_qa.md
```

Record findings in:

```text
deck/lesson_[NN]_deck_qa.md
```
