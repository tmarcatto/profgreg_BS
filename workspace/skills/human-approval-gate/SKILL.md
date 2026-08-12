---
name: human-approval-gate
description: Capture and validate Prof Greg human approval records before deck generation.
---

# Human Approval Gate Skill

Use this skill when the user approves a final study guide or asks to move from study guide to deck production.

Follow:

- `workspace/contracts/human-approval-contract.md`
- `workspace/contracts/v0-process-approval-contract.md`

## Role

You manage the human gate. Your job is to convert a clear human approval into a traceable approval file and prevent deck generation when approval is missing or ambiguous.

## Approval Rules

Create:

```text
approval/lesson_[NN]_study_guide_approval.md
```

Deck generation is allowed only when:

- approval status is `approved` or `approved_with_minor_notes`;
- deck generation permission is `yes`;
- approved artifact points to a final study guide DOCX or PDF.

During v0, approval may be recorded as `approval mode: v0_process`. This means the artifact is approved to continue the pipeline, not declared final for release.

## Ambiguous Approval

If the user says something vague like "ok", "next", or "continue" after seeing a study guide, do not assume formal approval for deck generation.

Ask for explicit approval or continue with non-deck preparation work.
