# Prof Greg Full-Flow V0 Test Package

This package defines how to run the first full-flow test after the v0 pipeline has been assembled.

The goal is not to prove that every artifact is final quality. The goal is to expose where the workflow, contracts, skills, rendering, gates, and operator experience need improvement before v1.

## When To Use

Use this package when the course creator provides a new material to test the Prof Greg pipeline end to end.

Do not use the existing `ai-for-construction-professionals` Lesson 1 run as the full-flow test. That run is the construction bench used to build the process.

## Required Inputs

The operator should collect or infer the following:

- course working title;
- learner level: Basic, Intermediate, or Advanced;
- source material files or pasted syllabus;
- intended number of lessons, if known;
- whether the test should produce one lesson only or the full course structure;
- whether localization should stop at text maps or produce rendered PPTX outputs;
- any nonstandard visual or citation requirement.

If an item is missing, Greg should make a reasonable assumption and log it unless the missing item would change the course scope or learner level.

## Default Test Path

1. Create a new run folder under `runs/[course-slug]/`.
2. Save the intake package under `input/`.
3. Produce and autonomously QA the Course Map.
4. Produce source ledger, research log, student references, and source gaps.
5. Draft Lesson 1 study guide in English.
6. Run pedagogy, citation, design, and visual QA.
7. Produce DOCX and PDF if the rendering path is available.
8. Request human approval before deck generation.
9. After approval, produce the 10-slide English deck.
10. Produce PT-BR and ES-419 localization checks.
11. Produce localized decks if the English deck and localization text maps pass QA.
12. Write `process_review/full_flow_test_report.md`.

## Human Gates

Only one human gate is required during v0:

- approval of the final English study guide before deck production.

Course Map approval, source checks, reviewer passes, and localization checks can be approved autonomously by Greg when they pass QA.

## Pass Condition

The test passes if Greg produces a complete traceable report that clearly says:

- what worked;
- what failed;
- what was awkward;
- what should change before v1.

A test can pass even when specific artifacts fail, as long as the failure is captured and actionable.

## Files In This Package

- `intake-template.md`: information to gather before starting.
- `execution-checklist.md`: stage-by-stage test checklist.
- `full_flow_test_report_template.md`: required final report structure.
