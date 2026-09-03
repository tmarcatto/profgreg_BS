# Prof Greg Study Guide Review Contract

This contract defines the reviewer layer for Prof Greg study guides.

The drafter must not be the only judge of its own work. Reviews are separate passes with separate verdicts, scoped responsibilities, and traceable notes.

## Shared Inputs

Each review pass should use:

- `course_map/course_map.md`
- `course_map/course_map.json`
- `sources/source_ledger.json`
- `lesson_draft/lesson_[NN]_draft.md`
- `workspace/contracts/study-guide-draft-contract.md`
- `workspace/design-system/`, when design or visual review is involved

## Shared Verdicts

Use one of these verdicts:

- `Pass`
- `Pass with revision notes`
- `Pass with constraints`
- `Blocked`

Do not use vague verdicts such as "looks good" or "mostly fine."

## Shared Review Rules

- Review the actual draft, not the intended draft.
- Separate blocking issues from later improvements.
- Do not rewrite the whole lesson during review.
- Do not approve claims, visuals, or structure outside your reviewer scope.
- Preserve the target learner: construction workers and professionals in the United States.
- Preserve the original language: English.
- Respect the course level: Basic, Intermediate, or Advanced.
- Keep notes traceable enough that another agent or human can understand what changed and why.

## Pedagogy Review

Purpose: decide whether the lesson teaches the right thing at the right depth for the target learner.

Check:

- alignment with the Course Map;
- level fit;
- MECE structure;
- practical construction context;
- clarity and learning progression;
- excessive abstraction, filler, or motivational prose;
- callout usefulness and restraint;
- glossary usefulness;
- bridge and callback correctness.

Output:

```text
review/lesson_[NN]_pedagogy_review.md
```

Required sections:

- `Verdict`
- `What Works`
- `Issues to Revise`
- `Pedagogical Risk`
- `Approval Status`

## Citation Review

Purpose: decide whether important factual claims are traceable to verified sources.

Check:

- source ledger exists and is validated;
- every important factual claim is traceable;
- inline citations are used only where they improve learning or highlight a high-value claim;
- source hierarchy is respected;
- weak sources are not used for strong claims;
- quantified claims, legal claims, safety claims, vendor claims, and standards claims have strong support;
- no hallucinated references, publications, standards, URLs, or image sources.

Output:

```text
review/lesson_[NN]_citation_review.md
```

Required sections:

- `Verdict`
- `Source Ledger Check`
- `Claims Properly Supported`
- `Constraints`
- `Required Before Final`
- `Approval Status`

## Design QA

Purpose: decide whether the lesson is ready to be mapped into the Prof Greg Content Design System.

Check:

- required study guide architecture is present;
- student-facing front matter does not expose internal production notes;
- cover content follows the branded study-guide cover hierarchy;
- heading hierarchy is coherent;
- static TOC can be rendered cleanly;
- callouts are marked consistently and not overused;
- callouts do not appear in structural sections such as TOC, summary, glossary, or references;
- summary and key takeaways contain 4-6 concise bullet points and no paragraph prose;
- glossary, references, tables, and figures can be rendered as DOCX/PDF components;
- style is more academic and premium than the legacy prompts without becoming intimidating;
- BuildStak palette and logo use are compatible with the artifact.

Output:

```text
review/lesson_[NN]_design_qa.md
```

Required sections:

- `Verdict`
- `Structure Check`
- `Design Notes for DOCX/PDF Stage`
- `Layout Risks`
- `Approval Status`

## Visual QA

Purpose: decide whether planned visuals are pedagogically necessary, source-safe, and production-ready.

Check:

- each visual has a clear teaching purpose;
- each visual has a distinct learning line and does not merely repeat another figure;
- deterministic diagrams are preferred when precision matters;
- trusted sourced images are attributed;
- generated conceptual images are used only as fallback;
- real-source examples are prioritized when the lesson teaches real documents, plans, schedules, symbols, or technical drawing interpretation;
- visuals do not introduce unsupported claims;
- visuals match the language of the artifact;
- any non-English text inside images is translated or replaced;
- captions teach, not merely label.
- every visual records whether an image would materially improve learning and why;
- image-led visuals explicitly choose reuse from reference material, online search, generation, or operator request;
- online-search selections resolve to a verified attributable asset before production;
- operator requests are used only after applicable alternatives are unsuitable or exhausted and render a red box containing the image description, pedagogical reason, and focused search phrase;
- the selected mechanism matches the source logic: process flow for ordered steps, relationship map for roles, comparison matrix for shared attributes, cost stack for cumulative amounts, schedule bars for timing, and activity network for predecessor/successor logic;
- ordered or numbered content is blocked when rendered as disconnected cards or boxes without visible direction;
- comparisons across shared variables use one variable column and one dedicated column for each compared entity; both entities must never be packed into one narrative cell;
- the caption, title, visible labels, and source prose describe the same relationship and preserve the same order.
- failed arrows, missing symbols, bad spacing, blank areas, distorted images, unreadable text, inconsistent font scale, repeated information, and overlaps are blocking issues unless explicitly accepted as v0 limitations.

Before DOCX/PDF production, create or update:

```text
review/lesson_[NN]_visual_plan.json
```

Then run:

```bash
python3 tools/greg_visual_plan_check.py review/lesson_[NN]_visual_plan.json
```

The visual plan checker must pass before production. It checks that each visual has a type, placement, teaching purpose, distinct learning claim, source status, generated-image fallback status, image cadence, size constraints, highlight rationale, and diagram text placement. It also blocks generated imagery when the lesson's core message depends on a real document, plan, schedule, symbol, technical drawing, or sourced example unless the lesson is explicitly marked `visual_curation_required`.

Output:

```text
review/lesson_[NN]_visual_qa.md
```

Required sections:

- `Verdict`
- `Visual Inventory`
- `Visual Policy Check`
- `Required Before DOCX/PDF`
- `Approval Status`

## Human Gate

Greg may autonomously approve Course Maps and internal review passes after QA.

The final English study guide still requires human approval before deck generation.

Never generate a PPTX deck from a study guide that has not passed the human approval gate.
