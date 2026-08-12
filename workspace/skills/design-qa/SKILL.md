---
name: design-qa
description: Review Prof Greg study guide drafts for DOCX/PDF readiness under the Prof Greg Content Design System.
---

# Design QA Skill

Use this skill when Prof Greg needs to check whether a study guide draft can be rendered cleanly as a DOCX/PDF artifact.

Follow:

- `workspace/contracts/study-guide-review-contract.md`
- `workspace/skills/content-design-system/SKILL.md`
- `workspace/design-system/docx-rules.md`
- `workspace/design-system/components.md`
- `workspace/design-system/tokens.json`

## Reviewer Role

You are not the drafter. Your job is to catch structure and rendering risks before production.

## Focus

Check:

- required study guide architecture;
- heading hierarchy;
- static TOC readiness;
- callout consistency and restraint;
- glossary, references, tables, and figure placeholders;
- DOCX/PDF render risks;
- BuildStak palette and logo fit;
- academic but approachable editorial style.

## Output

Write:

```text
review/lesson_[NN]_design_qa.md
```

Use the required sections from the review contract.
