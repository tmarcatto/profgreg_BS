# Prof Greg Human Approval Contract

This contract defines the human approval gate for Prof Greg.

The main required human gate is the final English study guide approval before PPTX deck generation.

During v0 development, also follow `workspace/contracts/v0-process-approval-contract.md`.

## Purpose

Human approval confirms that the final study guide is acceptable as the version of record for a lesson.

It does not mean:

- every source is newly re-researched;
- every future localization is approved;
- the deck already exists;
- the deck may ignore the study guide.

It means the study guide is approved as the source for the recorded lesson deck.

During v0, this can mean the study guide is approved to unlock the next process stage, while remaining subject to later refinement after full-flow testing.

## Required Approval File

Approval must be captured here:

```text
runs/[course-slug]/approval/lesson_[NN]_study_guide_approval.md
```

## Required Fields

The approval record must include:

- course slug;
- lesson number;
- lesson title;
- approved artifact path;
- approval status;
- approver;
- approval date;
- approval note;
- deck generation permission.
- approval mode, when relevant: `v0_process` or `final_release`.

## Valid Approval Status

Use one of:

- `approved`
- `approved_with_minor_notes`
- `changes_requested`
- `rejected`

Deck generation is allowed only when:

- status is `approved` or `approved_with_minor_notes`;
- deck generation permission is `yes`;
- the approved artifact path points to the final study guide DOCX or PDF.

## Approval Template

```markdown
# Lesson [NN] Study Guide Approval

Course slug: [course-slug]
Lesson: Lesson [NN] - [lesson title]
Approved artifact: [path]
Approval status: approved
Approver: [name]
Approval date: YYYY-MM-DD
Deck generation permission: yes

Approval note:

[short note]
```

## Human Language

The user may approve naturally in Portuguese, for example:

- "Aprovo a apostila da Lesson 1."
- "Pode gerar o deck da Lesson 1."
- "Apostila aprovada, segue para PPT."

Greg should then create the approval file before routing to deck production.

If the approval is ambiguous, Greg should ask for a short confirmation instead of generating a deck.

## Approval Automation

For local Phase 3A operation, approvals should be recorded with:

```text
tools/greg_record_approval.py [course-slug] --lesson [NN] --artifact-type study_guide --artifact [path]
tools/greg_record_approval.py [course-slug] --lesson [NN] --artifact-type deck --artifact [path]
```

Recording an approval must also update `process_review/canonical_artifacts.json` and `process_review/canonical_artifacts.md`, so status and future stages read the approved artifact instead of guessing from filenames or cached previews.
