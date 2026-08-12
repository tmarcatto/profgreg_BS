# Prof Greg Localization Production Contract

This contract defines the v0 Markdown-first localization production step.

Localization production is separate from localization policy. The policy says what a good localization means. This contract says how to produce and package the first localized artifacts.

## Purpose

Produce traceable localized Markdown artifacts before automating localized DOCX/PDF/PPTX rendering.

This lets Prof Greg test:

- locale-specific tone;
- terminology choices;
- U.S. market preservation;
- structure preservation;
- QA format;
- file naming;
- future rendering needs.

## V0 Scope

During v0, localization can be one of:

- `smoke_test`: localized title, subtitle, learning objectives, one short body sample, visual caption sample, glossary sample, and QA.
- `full_markdown`: full localized Markdown study guide.
- `deck_text_map`: localized slide text map before PPTX production.

Do not pretend a `smoke_test` is a full localized artifact.

## Required Inputs

- Approved English source artifact.
- English draft Markdown when available.
- Source ledger.
- Localization contract.
- Target locale.
- Scope: `smoke_test`, `full_markdown`, or `deck_text_map`.

## Output Locations

Study guide localization:

```text
localization/[locale]/lesson_[NN]_study_guide_[locale].md
localization/[locale]/lesson_[NN]_localization_qa.md
```

Deck text map localization:

```text
localization/[locale]/lesson_[NN]_deck_text_map_[locale].md
localization/[locale]/lesson_[NN]_deck_localization_qa.md
```

## Required Metadata

Each localized Markdown artifact must include:

- course slug;
- lesson number and title;
- source artifact path;
- source language;
- target locale;
- localization scope;
- approval mode, if known;
- localization date;
- status.

## Preservation Rules

Preserve:

- lesson structure;
- source IDs such as `[S001]`;
- U.S. institution names;
- technical terms where translation would confuse market context;
- imperial units unless metric helps understanding.

## QA Rules

The QA note must state:

- whether this is a smoke test or full localization;
- what was localized;
- what was intentionally not localized;
- terminology decisions;
- unit decisions;
- source/reference preservation;
- visual/caption handling;
- risks before full localization.

## Deck Text Map Rules

For `deck_text_map`, map slide text before generating a localized PPTX.

Each slide entry should include:

- slide number;
- original title;
- localized title;
- localized visible text by role;
- terms intentionally preserved;
- length risk: `low`, `medium`, or `high`;
- layout note when localized text may need resizing or rewriting.

Do not localize footer page numbers.

Brand text may remain unchanged unless the brand itself has an approved localized form.

The map is not the PPTX. It is the controlled input for localized deck rendering.

## Localized Deck Fit Gate

Localized PPTX rendering must not start only from a literal text map.

Before generating a localized PPTX, run:

```text
tools/greg_localized_deck_text_map_check.py localization/[locale]/lesson_[NN]_deck_text_map_[locale].md --qa localization/[locale]/lesson_[NN]_deck_localization_qa.md
```

The checker result has two separate meanings:

- `passed`: the text map is structurally valid.
- `ready_for_pptx_rendering`: the text map is safe to render without a compact rewrite pass.

If the map passes but is not ready for PPTX rendering, create a fit plan:

```text
localization/[locale]/lesson_[NN]_deck_fit_plan_[locale].md
```

The fit plan must identify:

- high-risk slides;
- visible text that is too long;
- which text must be rewritten compactly;
- terms that must remain preserved;
- whether layout should change or text should be shortened first.

Do not solve localized slide fit by shrinking fonts below the approved deck standard. Prefer concise localized rewriting.

## Blockers

Block localization production when:

- target locale is unsupported;
- source artifact is missing;
- approval file is missing when required;
- the requested scope is unclear;
- localization would require unresolved source changes.
