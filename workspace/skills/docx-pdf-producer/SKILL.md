---
name: docx-pdf-producer
description: Produce final Prof Greg DOCX/PDF study guides from reviewed drafts using the content design system.
---

# DOCX/PDF Producer Skill

Use this skill when Prof Greg needs to turn a reviewed study guide draft into final DOCX/PDF artifacts.

Follow:

- `workspace/contracts/docx-pdf-production-contract.md`
- `workspace/contracts/model-routing-contract.md`
- `workspace/contracts/run-folder-contract.md`
- `workspace/contracts/study-guide-review-contract.md`
- `workspace/skills/content-design-system/SKILL.md`
- `workspace/design-system/docx-rules.md`
- `workspace/design-system/components.md`
- `workspace/design-system/tokens.json`

## Role

You are the production layer. Do not rewrite the lesson unless a review note explicitly requires a small production-safe correction.

Your job is to render, inspect, and package the study guide.

Use the `docx_pdf_generation` role for deterministic production. Do not call LLM providers for rendering.

## Hard Gate

Do not produce final DOCX/PDF if any required review is blocked.

Do not produce final DOCX/PDF if `review/lesson_[NN]_visual_plan.json` exists and fails `tools/greg_visual_plan_check.py`.

Do not produce final DOCX/PDF if `lesson_draft/lesson_[NN]_draft.md` fails `tools/greg_study_guide_content_check.py`.

If production is blocked, write:

```text
docx_pdf/lesson_[NN]_production_blocked.md
```

## Required Outputs

Produce:

```text
docx_pdf/lesson_[NN]_study_guide.docx
docx_pdf/lesson_[NN]_study_guide.pdf
docx_pdf/lesson_[NN]_render_qa.md
```

## Render QA

Rendered output must be visually inspected before delivery.

The QA note must cover:

- cover hierarchy;
- logo placement;
- TOC;
- headings;
- callouts;
- figures;
- tables;
- glossary;
- references;
- page breaks;
- blank pages;
- overflow or readability issues.

Automated layout QA:

- before rendering, run `tools/greg_study_guide_content_check.py` against the lesson draft;
- before rendering, run `tools/greg_visual_plan_check.py` against `review/lesson_[NN]_visual_plan.json` when the lesson includes planned visuals;
- after rendering/extraction, run `tools/greg_pdf_layout_check.py` against the final PDF and render QA file;
- fix failures before delivery;
- warnings require either a correction or a note in the render QA explaining why the study guide still passes;
- this tool supplements visual page inspection; it does not replace rendered-page review.

## Human Gate

After production, the study guide requires human approval before deck generation.

Never route to deck production until `approval/lesson_[NN]_study_guide_approval.md` exists and approves the study guide.
