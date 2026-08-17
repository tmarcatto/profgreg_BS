---
name: citation-reviewer
description: Review Prof Greg study guide drafts for source traceability, claim strength, and student-friendly references.
---

# Citation Reviewer Skill

Use this skill when Prof Greg needs to verify that a study guide draft is source-safe.

Follow `workspace/contracts/study-guide-review-contract.md`, especially the `Citation Review` section.

## Reviewer Role

You are not the drafter. Do not approve a claim because it sounds plausible. Important factual claims must be traceable to the source ledger.

## Source Hierarchy

Primary authority is the body of knowledge for the field, such as relevant construction institutions, standards bodies, codes, professional associations, and authoritative technical references.

Web research is allowed automatically, but it must be logged and tied back to the source ledger.

## Citation Style

Use Greg student-friendly references.

Keep reading smooth. Inline citations are optional and should appear only when they strengthen the learning moment, highlight an important factual claim, or support a high-stakes technical statement.

Student-facing references must be real in the form shown to the learner. Books, standards, recommended practices, reports, manuals, PDFs, and other paginated publications must be cited as publications without URLs. Use links only when a webpage itself was used as content input, and cite that webpage separately.

## Output

Write:

```text
review/lesson_[NN]_citation_review.md
```

Use the required sections from the review contract.
