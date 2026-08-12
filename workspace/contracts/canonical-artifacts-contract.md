# Prof Greg Canonical Artifacts Contract

This contract defines how Prof Greg records the current approved artifact for each run stage.

## Purpose

Avoid ambiguity when multiple generated files exist for the same lesson, especially after human feedback, cache-safe revisions, or localization tests.

Prof Greg must be able to answer:

- which Course Map is active;
- which study guide PDF is approved;
- which deck is the approved current deck;
- which source ledger, visual plan, and QA files support the approved artifacts;
- which lesson-level source refresh supports each approved lesson;
- which localization artifacts are smoke tests versus final localized outputs;
- which artifacts are parked or historical.

## Required Manifest

Each production run should maintain:

```text
process_review/canonical_artifacts.json
process_review/canonical_artifacts.md
```

The JSON file is the machine-readable source of truth. The Markdown file is a human-readable mirror.

## Manifest Fields

Each canonical artifact record should include:

- `key`: stable identifier such as `study_guide_pdf` or `deck_pptx`;
- `path`: artifact path relative to the run folder;
- `status`: `active`, `approved`, `smoke_test`, `supporting`, `parked`, or `missing`;
- `stage`: pipeline stage that produced the artifact;
- `lesson`: lesson number when applicable;
- `revision`: revision label when applicable, such as `r03`;
- `approval_path`: approval artifact when human approval exists;
- `qa_path`: QA artifact when available;
- `notes`: short operational note.

## Selection Rules

When multiple artifacts exist:

1. Prefer a human-approved artifact recorded in an approval file.
2. Prefer explicit cache-safe revisions over overwritten canonical filenames after human feedback.
3. Prefer the highest revision number only when approval and QA do not identify a different file.
4. Treat smoke-test localization artifacts as `smoke_test`, never as final localized outputs.
5. Never silently use a parked artifact.

## Revision Rules

For student-facing artifacts revised after human review:

- do not rely only on overwriting the same file;
- create a cache-safe revision filename when the format is sensitive to app/preview cache;
- update the canonical manifest after approval or after a new active revision is generated;
- keep historical revisions in place unless cleanup is explicitly requested.

## Required Updates

Update the manifest after:

- Course Map approval;
- study-guide PDF production;
- human study-guide approval;
- deck production;
- human deck approval;
- visual plan creation or revision;
- lesson-level source refresh creation or revision;
- localization smoke test or full localization;
- process review completion.

## Operator Behavior

When answering status questions, Greg should use `canonical_artifacts.json` if it exists. If it does not exist, Greg may infer canonical artifacts from the run folder and then should create the manifest.

When a requested stage needs an input artifact, Greg should use the canonical manifest rather than guessing from filenames.
