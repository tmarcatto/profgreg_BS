---
name: localization-producer
description: Produce Prof Greg Markdown-first localization artifacts and QA packages for supported locales.
---

# Localization Producer Skill

Use this skill when Prof Greg needs to produce localized Markdown packages before full localized rendering.

Follow:

- `workspace/contracts/localization-contract.md`
- `workspace/contracts/localization-production-contract.md`
- `workspace/contracts/model-routing-contract.md`
- `workspace/contracts/run-folder-contract.md`
- `workspace/contracts/v0-process-approval-contract.md`

## Role

You are the production layer for localization.

Do not invent new source claims. Preserve structure, source IDs, and U.S. construction market context.

Use the `localization` role through the model router. Do not hardcode provider or model IDs.

## Supported Scopes

- `smoke_test`
- `full_markdown`
- `deck_text_map`

During v0, prefer `smoke_test` before full localization.

## Supported Locales

- `pt-br`
- `es-419`

## Output

Write localized Markdown and QA under:

```text
runs/[course-slug]/localization/[locale]/
```

## Gate

If the requested scope is a smoke test, clearly label it as a smoke test.

Never present a smoke test as a complete localized study guide.

For `deck_text_map`, produce:

```text
localization/[locale]/lesson_[NN]_deck_text_map_[locale].md
localization/[locale]/lesson_[NN]_deck_localization_qa.md
```

The map must flag text-expansion risks before PPTX localization.

Localized deck fit gate:

- run `tools/greg_localized_deck_text_map_check.py` after producing a deck text map;
- if `ready_for_pptx_rendering` is false, do not generate a localized PPTX yet;
- create `localization/[locale]/lesson_[NN]_deck_fit_plan_[locale].md`;
- prefer compact localized rewriting over shrinking fonts.
