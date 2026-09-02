# Prof Greg Localization Contract

This contract defines how Prof Greg localizes approved English course artifacts.

Localization is a separate stage. Do not mix localization into original English generation.

## Purpose

Create localized student-facing versions that preserve the technical meaning, U.S. construction market context, source traceability, and learning intent of the approved English artifact.

## Supported Locales

Default supported locales:

- `pt-br`
- `es-419`

## Required Inputs

Localization may begin after approved English artifacts exist.

For study guide localization:

- `docx_pdf/lesson_[NN]_study_guide.pdf` or approved source text;
- `lesson_draft/lesson_[NN]_draft.md`;
- `sources/source_ledger.json`;
- `docx_pdf/lesson_[NN]_render_qa.md`;
- `approval/lesson_[NN]_study_guide_approval.md`.

For deck localization:

- the exact revisioned PPTX named in `approval/lesson_[NN]_deck_approval.md`;
- the deck spec whose revision and declared output match that approved PPTX;
- `deck/lesson_[NN]_deck_qa.md`;
- approved English study guide;
- `approval/lesson_[NN]_study_guide_approval.md`;
- `approval/lesson_[NN]_deck_approval.md`.

Never select a deck for localization by newest filename, modification time, cached preview, or latest spec alone.

## Outputs

Study guide localization:

```text
localization/[locale]/lesson_[NN]_study_guide_[locale].md
localization/[locale]/lesson_[NN]_localization_qa.md
```

Rendered localized artifacts, when production tooling is active:

```text
localization/[locale]/lesson_[NN]_study_guide_[locale].docx
localization/[locale]/lesson_[NN]_study_guide_[locale].pdf
```

Deck localization, when requested:

```text
localization/[locale]/lesson_[NN]_deck_[locale].pptx
localization/[locale]/lesson_[NN]_deck_localization_qa.md
```

Every localized deck spec must record the approved English deck path, its SHA-256, the matching English deck-spec path, and that spec's SHA-256. After rendering, the localized PPTX must preserve the approved deck's slide count, canvas size, layout sequence, and per-slide object structure.

If provenance or structure validation fails, the localized deck is blocked. It must not appear as ready for review, be approved, be downloaded, or enter video generation.

## Global Localization Rules

- Preserve technical meaning.
- Preserve U.S. construction market context.
- Preserve source references.
- Do not localize legal, code, institutional, or standard names unless a recognized translated name exists.
- Do not convert the course into a different market.
- Keep imperial units by default.
- Add metric equivalents only when useful for understanding.
- Keep reading smooth.
- Avoid word-for-word translation when it hurts clarity.
- Do not simplify away technical precision.
- Do not add unsupported claims.
- Translate figure captions, subtitles, labels, and visible text when feasible.
- If an image cannot be regenerated in the target language, translate the caption and surrounding explanatory text.

## PT-BR Rules

Target learner:

- Brazilian learners working in or preparing for the U.S. construction market.

Tone:

- Use `você`.
- Friendly, informal, and clear.
- Still professional and technically serious.

Terminology:

- Preserve U.S. market terms when translating them would confuse the learner.
- Use Portuguese explanations to clarify U.S. terms rather than replacing the market context.
- Keep acronyms when they are used in the U.S. field, with a short explanation when first introduced.

Units:

- Imperial units remain default.
- Metric annotations appear only when they help comprehension.
- Do not aggressively convert every measurement.

## ES-419 Rules

Target learner:

- Spanish-speaking learners working in or preparing for the U.S. construction market.

Tone:

- Neutral Latin American Spanish.
- Clear, direct, and professional.

Terminology:

- Use mainstream pan-regional terminology.
- Avoid country-specific slang.
- When construction terms vary regionally, choose the mainstream option and preserve U.S. context.

Units:

- Imperial units remain default.
- Metric annotations appear only when they help comprehension.

## Localization QA

Every localized artifact needs QA.

Check:

- meaning preserved;
- U.S. market context preserved;
- tone appropriate;
- terminology consistent;
- units handled correctly;
- references preserved;
- captions and visible visual text handled;
- no new unsupported claims;
- no awkward literal translation;
- glossary still useful.

## V0 Note

During v0, localization may first be produced as Markdown and QA notes before full DOCX/PDF/PPTX rendering is automated.

For Markdown-first production rules, follow `workspace/contracts/localization-production-contract.md`.
