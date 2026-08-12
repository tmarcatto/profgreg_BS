# Prof Greg Full-Flow Test Contract

This contract defines how Prof Greg should be tested after the v0 pipeline is assembled.

The current Lesson 1 run is a construction bench for building the process. It should not be treated as the definitive quality benchmark.

## Purpose

After the full v0 pipeline exists, Prof Greg should be tested with a different course or lesson material from intake through final artifacts.

The goal is to discover what needs refinement in the actual workflow.

## Test Scope

The full-flow test should cover:

1. Intake.
2. Course Map.
3. Source ledger.
4. Study guide draft.
5. Pedagogy review.
6. Citation review.
7. Design QA.
8. Visual QA.
9. DOCX/PDF production.
10. Human approval gate.
11. PPTX deck production.
12. Localization.
13. Localization QA.
14. Final status summary.

## Evaluation Questions

During the test, evaluate:

- Did Greg ask for too much or too little input?
- Did Greg choose a logical lesson structure?
- Were sources strong enough and logged clearly?
- Did the draft fit the learner level?
- Were reviewer notes useful or generic?
- Did visuals teach or decorate?
- Did DOCX/PDF rendering expose layout problems?
- Did the deck support a 10-minute recorded lesson?
- Did localization preserve the U.S. construction market context?
- Did gates prevent premature artifacts?
- Were files easy to find and trace?

## Output

After the full-flow test, produce:

```text
runs/[course-slug]/process_review/full_flow_test_report.md
```

The report should include:

- what worked;
- what failed;
- what was awkward;
- which contracts need updates;
- which skills need updates;
- which rendering tools need fixes;
- recommended v1 improvements.

## Test Package

Use this package as the operational test kit:

```text
workspace/test-packages/full-flow-v0/
```

It contains:

- `README.md` for the test purpose and pass condition;
- `intake-template.md` for collecting the minimum required input;
- `execution-checklist.md` for stage-by-stage execution;
- `full_flow_test_report_template.md` for the final process review.

When starting a new full-flow test, copy or adapt `intake-template.md` into:

```text
runs/[course-slug]/input/intake.md
```

When finishing the test, use `full_flow_test_report_template.md` as the structure for:

```text
runs/[course-slug]/process_review/full_flow_test_report.md
```

## V0 Rule

Do not over-optimize the current construction-bench artifacts before running a new full-flow test. Build the whole pipeline first, then refine based on a fresh material.
