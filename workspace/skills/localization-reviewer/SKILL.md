---
name: localization-reviewer
description: Review Prof Greg localized artifacts for meaning, tone, terminology, market fit, units, and source preservation.
---

# Localization Reviewer Skill

Use this skill when Prof Greg needs to QA a localized artifact.

Follow:

- `workspace/contracts/localization-contract.md`
- `workspace/contracts/model-routing-contract.md`

## Role

You are not the localizer. Your job is to catch meaning drift, market drift, terminology issues, unit problems, awkward literal translation, and source/reference problems.

Use the `localization_review` role through the model router.

## Review Checks

Check:

- meaning preserved;
- U.S. construction market context preserved;
- tone appropriate for the locale;
- terminology consistent;
- imperial units preserved by default;
- metric equivalents used only when helpful;
- references preserved;
- captions and visible visual text handled;
- no unsupported claims added;
- glossary remains useful;
- callouts remain natural and not excessive.

## Output

Write:

```text
localization/[locale]/lesson_[NN]_localization_qa.md
```
