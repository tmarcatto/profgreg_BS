---
name: study-guide-draft
description: Draft Prof Greg English study guides from approved course maps and validated source ledgers.
---

# Study Guide Draft Skill

Use this skill when Prof Greg needs to draft, revise, or prepare an English study guide lesson.

The study guide is the main student-facing artifact. It must be academically stronger than the legacy material while remaining practical, readable, and useful for residential construction workers in the United States.

Default all examples, scenarios, case applications, and jobsite language to U.S. residential construction: single-family homes, townhomes, multifamily/light residential where useful, remodeling, small builders, subcontractors, independent tradespeople, and residential field supervisors. Large commercial examples may appear only when they make a concept clearer and are labeled as a contrast, not as the normal learner context.

Represent the real U.S. construction workforce respectfully: American-born workers and immigrant workers may both appear in scenarios and visuals. Do not stereotype by nationality, language, role, or skill level.

## Contract

Follow `workspace/contracts/study-guide-draft-contract.md`.

Use:

- `workspace/contracts/source-ledger-contract.md` for source traceability.
- `workspace/contracts/run-folder-contract.md` for artifact locations.
- `workspace/contracts/model-routing-contract.md` for model/API routing.

Request the `technical_content` role for drafting. Do not hardcode a provider or model ID.

## Hard Gate

Do not write a full study guide unless all are true:

1. The Course Map exists.
2. The Course Map QA status allows drafting.
3. `source_ledger.json` exists.
4. `source_ledger.json.validation.all_sources_verified` is `true`.
5. `source_ledger.json.validation.unsupported_claims` is empty or irrelevant to the requested lesson.

If any condition fails, produce a blocked draft note instead of the lesson:

```text
lesson_draft/lesson_[NN]_blocked.md
```

The blocked note must explain:

- what is missing;
- which claims or sections are unsafe to draft;
- what research is needed next;
- whether a narrower supported draft is possible.

## Required Inputs

- Approved `course_map.md`.
- Approved `course_map.json`.
- Validated `source_ledger.json`.
- Lesson number and title.
- Course level: Basic, Intermediate, or Advanced.
- Prof Greg Content Design System, when available.

## Default Lesson Length

Length is adaptive:

- Basic: roughly 10 pages per lesson.
- Intermediate: roughly 15 pages per lesson.
- Advanced: roughly 15 pages per lesson with higher technicality.

Form follows function. Keep lessons in the same course reasonably consistent, but let complexity control depth.

## Required Lesson Architecture

Each study guide draft should include:

1. Cover metadata.
2. Introduction.
3. Learning objectives.
4. MECE lesson sections.
5. Summary and key takeaways.
6. Glossary.
7. Student-friendly references.

Do not add a Lesson Roadmap. Do not use H3 or deeper Markdown headings. Avoid em dashes, en dashes, and spaced hyphens as prose punctuation.

## Section Drafting Rules

- Use the Course Map as the source of truth for lesson scope.
- Do not invent prior or future lessons.
- Use 3-6 sections unless the lesson function clearly requires otherwise.
- Each section must be mutually exclusive and collectively exhaustive with the other sections.
- Each section needs a practical construction context.
- Each section should help the learner understand, decide, perform, evaluate, or avoid a mistake.
- Avoid motivational filler.
- Avoid academic heaviness that does not improve learning.

## Callout Rules

Current callout vocabulary:

- `APPLY IT`
- `KEY TERM`
- `HANDS-ON EXAMPLE`
- `SCENARIO`
- `CALLBACK`
- `BRIDGE`

Use callouts only when they improve learning, application, emphasis, or continuity.

Do not use callouts as decoration. If a callout repeats adjacent prose, remove it.

Guidance:

- `KEY TERM`: define terms with real course value.
- `APPLY IT`: give concrete learner action.
- `HANDS-ON EXAMPLE`: show worked calculations, workflows, or applied judgment.
- `SCENARIO`: use sparingly for meaningful applied situations.
- `CALLBACK`: use only for real prior-lesson continuity from the Course Map.
- `BRIDGE`: use once to connect to the next lesson or future course concept.

## Citation and References

Use Greg student-friendly references.

Prioritize reading flow. Inline citations are optional and should appear only when they strengthen the learning moment, highlight an important factual claim, or support a high-stakes technical statement.

Every important factual claim must be traceable to the source ledger even if no inline citation appears in the body.

Never cite a source that was not verified in the ledger.

## Visual Planning

Visual preference order:

1. Deterministic diagram, chart, process flow, map, or structured visual.
2. Trusted technical/source-based image with attribution.
3. Generated conceptual image only as fallback.

In the draft, include visual placeholders with purpose and source status:

```text
[FIGURE N.N | diagram | source: S001/S002 or source-needed | description]
```

If a visual depends on an unverified source, mark `source-needed` and flag it in Visual QA.

## Glossary

- Include current-lesson terms only.
- Do not redefine a term whose home lesson is earlier in the Course Map.
- If a prior term is needed, use a callback or short reminder.
- Definitions should be clear for construction workers in the U.S. market.

## Review Passes

After drafting, produce:

- Pedagogy Review.
- Citation Review.
- Design QA.
- Visual QA.

The drafter is not the only judge of its own work.

Before routing to DOCX/PDF production, run:

```bash
python3 tools/greg_study_guide_content_check.py lesson_draft/lesson_[NN]_draft.md
```

Fix failures before rendering. The study guide is lecture support and student theory material, not the LMS quiz/activity layer.

## Output Artifacts

When drafting is allowed:

```text
lesson_draft/lesson_[NN]_draft.md
review/lesson_[NN]_pedagogy_review.md
review/lesson_[NN]_citation_review.md
review/lesson_[NN]_design_qa.md
review/lesson_[NN]_visual_qa.md
```

When drafting is blocked:

```text
lesson_draft/lesson_[NN]_blocked.md
```

## Human Gate

The final English study guide requires human approval before deck generation.

Do not generate PPTX decks from unapproved study guides.
