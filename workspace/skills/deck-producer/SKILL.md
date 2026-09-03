---
name: deck-producer
description: Produce Prof Greg 10-slide PPTX lecture decks from human-approved study guides.
---

# Deck Producer Skill

Use this skill when Prof Greg needs to create a PPTX lecture deck from an approved study guide.

Follow:

- `workspace/contracts/deck-production-contract.md`
- `workspace/contracts/human-approval-contract.md`
- `workspace/contracts/model-routing-contract.md`
- `workspace/contracts/run-folder-contract.md`
- `workspace/skills/content-design-system/SKILL.md`
- `workspace/design-system/pptx-rules.md`
- `workspace/design-system/tokens.json`
- `workspace/renderers/deck/buildstak-deck-components.md`

## Role

You are the deck production layer. The deck supports a recorded online lesson.

The study guide carries depth. The deck carries the teaching path.

Use the `pptx_generation` role for deterministic deck production. If deck copy needs model assistance, use `technical_content` only through the model router.

## Hard Gate

Never generate a PPTX deck before human approval exists and permits deck generation.

If approval is missing or invalid, write:

```text
deck/lesson_[NN]_deck_blocked.md
```

## Defaults

- 10 slides.
- About 10 minutes.
- No speaker notes.
- Lecture only.
- Main key points.
- Presentation-native layout.
- Residential construction first: examples, diagrams, cases, and generated/sourced images should default to U.S. residential construction unless the approved study guide explicitly requires a commercial contrast.
- Images with people should respectfully represent the U.S. residential construction workforce as a mix of American-born and immigrant workers without stereotyping.

## Output

Produce:

```text
deck/lesson_[NN]_visual_plan.json
deck/lesson_[NN]_deck.pptx
deck/lesson_[NN]_deck_qa.md
```

Cache-safe revision rule:

- first delivery may use `deck/lesson_[NN]_deck.pptx`;
- any deck revised after human feedback must be exported as `deck/lesson_[NN]_deck_r[RR].pptx`;
- never rely on overwriting the same PPTX when asking the human to re-open or re-review the deck;
- update `deck/lesson_[NN]_deck_qa.md` with the latest revision path and revision reason.

Highlight rule:

- never highlight the last item in a sequence by default;
- highlight only when there is a specific student-facing reason such as exception, warning, decision point, risk threshold, contrast, or lesson emphasis;
- if all sequence items are equally important, use equal styling for all items.

Component rule:

- use `workspace/renderers/deck/buildstak-deck-components.md` as the component source for cover, image-plus-bullets, balanced sequences, paired record rows, trigger matrices, comparisons, and lesson takeaways;
- choose components by teaching function;
- record any ad hoc slide layout in the QA file with a reason.

Visual plan rule:

- before rendering, create `deck/lesson_[NN]_visual_plan.json`;
- for every body slide, decide in this order: learning job, teaching strategy, whether an image would materially improve learning, visual medium, asset-acquisition strategy, layout, and the role of supporting text;
- compare `native-diagram`, `trusted-source-image`, and `generated-conceptual-image` for every body slide; record a concrete fit or rejection reason for all three and select exactly one;
- record `image_need` as `required`, `helpful`, or `not-needed` with a concrete pedagogical reason; unused space alone is never an image need;
- when an image is selected, choose exactly one `asset_strategy`: `reuse-reference`, `search-online`, `generate`, or `operator-request`; use `native-diagram` when an image is not selected;
- inspect reusable reference material first, search online only for a source-safe real asset, generate only when authenticity is not part of the claim, and ask the operator only after the other applicable routes are unsuitable or exhausted;
- an operator request must carry an image description, pedagogical reason, and focused search phrase, and the rendered request draft must show those fields in a conspicuous red box where the image will go;
- use direct process-flow, schedule-bar-chart, or activity-network layouts when the learning job depends on visible sequence, time scale, overlap, dependencies, parallel paths, or the controlling path;
- every non-brand visual needs a purpose and distinct learning claim;
- every non-brand visual needs `context_focus`, defaulting to `U.S. residential construction`;
- people-centered visuals need `workforce_representation`, confirming respectful representation of the U.S. construction workforce, including American-born and immigrant workers when appropriate;
- use an image-plus-teaching-bullets slide only when a trusted real image or generated conceptual image is the strongest instructional medium; never add an image to satisfy a quota;
- generated images are fallback, never consecutive, never captioned/subtitled on deck slides, and never larger than half the slide;
- across slides 2-9, use at least four distinct layouts as an anti-repetition floor; never repeat the same layout on adjacent slides or use one body layout more than twice; never choose a weaker visual merely to increase variety;
- real examples are required when the lesson teaches real documents, plans, schedules, symbols, or technical drawings unless the visual plan explicitly marks `visual_curation_required`;
- highlighted visuals require a valid reason: exception, warning, decision point, risk threshold, contrast, or lesson emphasis.

QA tool:

- before rendering, run `tools/greg_visual_plan_check.py` against the deck visual plan;
- after rendering/inspection, run `tools/greg_deck_quality_check.py` against the final PPTX and deck QA file;
- fix failures before delivery;
- warnings require either a correction or a note in the QA file explaining why the deck still passes;
- if the QA tool flags slide similarity, either merge/rewrite the slides or document the MECE distinction between them.
- never release a slide that contains only chrome, a title, or isolated text; every body slide must have a complete layout payload plus a learner-facing takeaway;
- treat empty renderer fields, missing rendered slide PNGs, suspiciously tiny renders, and text without a non-brand visual/container as hard failures, not warnings.
- never approve or release a presentation containing an unresolved red image-request box; it is an operator-facing draft only.
