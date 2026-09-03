---
name: visual-qa
description: Review Prof Greg visual plans for pedagogical purpose, source safety, and production readiness.
---

# Visual QA Skill

Use this skill when Prof Greg needs to check whether planned visuals are useful, accurate, source-safe, and ready for production.

Follow:

- `workspace/contracts/study-guide-review-contract.md`
- `workspace/contracts/model-routing-contract.md`
- `workspace/skills/content-design-system/SKILL.md`
- `workspace/design-system/tokens.json`

## Reviewer Role

You are not the visual producer. Your job is to approve the plan, block unsafe visuals, and identify what must be created or sourced next.

## Pedagogy-First Visual Decision

For presentation body slides, require the planner to:

1. define the learning job;
2. choose a teaching strategy;
3. compare a native diagram, trusted real/source image, and generated conceptual image with a concrete reason for each;
4. state whether an image is `required`, `helpful`, or `not-needed`, with a pedagogical reason;
5. select exactly one medium;
6. select one asset route: `native-diagram`, `reuse-reference`, `search-online`, `generate`, or `operator-request`;
7. choose a matching layout; and
8. explain how the accompanying text directs attention, explains a rule, labels essential structure, or states the takeaway.

No medium has a permanent first-place ranking. Use diagrams for relationships, sequence, magnitude, mapping, or logic; trusted images for authentic details learners must inspect; and generated conceptual images for context, human action, setting, or spatial orientation when authenticity is not the claim.

Use `diagram_planning` and `diagram_rendering` for native diagrams. Use `image_generation` only when a conceptual image wins the documented comparison. Never generate a substitute for required real evidence.

## Focus

Check:

- teaching purpose;
- source status;
- language fit;
- caption usefulness;
- claim safety;
- whether deterministic diagrams can replace generated images;
- whether sourced images need license or attribution notes.
- whether the teaching strategy was chosen before the visual medium and layout;
- whether all three visual media were genuinely compared and exactly one was selected;
- whether the selected medium matches the rendered component and source strategy;
- whether text complements the visual instead of merely repeating it;
- whether the image-need decision is based on learning value rather than decoration or empty-space filling;
- whether the asset route matches the available references, source safety, authenticity requirement, and generation safety;
- whether `search-online` identifies a verified, attributable asset rather than an unresolved search intention;
- whether `operator-request` is used only after applicable alternatives were rejected and includes a complete red request box in the rendered material;
- whether the source content's logic determines the selected diagram mechanism;
- whether ordered or numbered content uses a process flow with visible connectors and preserved order rather than disconnected cards;
- whether a comparison across shared variables uses one variable column and one separate column for every compared entity rather than packing both sides into one narrative cell;
- whether the caption, title, visible labels, and surrounding explanation describe the same relationship.

The review must include a machine-checkable visual plan:

```text
review/lesson_[NN]_visual_plan.json
```

Use this minimum shape:

```json
{
  "artifact_type": "study-guide | deck",
  "lesson_number": 1,
  "visuals": [
    {
      "visual_id": "V01",
      "visual_type": "deterministic-diagram | trusted-source-image | generated-conceptual-image | brand-mark",
      "placement": "section or slide",
      "purpose": "what this visual teaches",
      "learning_claim": "the distinct idea this visual makes clearer",
      "teaching_strategy": "worked-example | compare-and-contrast | trace-a-process | inspect-evidence | diagnose-and-decide | ...",
      "visual_medium": "native-diagram | trusted-source-image | generated-conceptual-image",
      "visual_candidates": [
        {"medium": "native-diagram", "decision": "selected | rejected", "reason": "specific reason"},
        {"medium": "trusted-source-image", "decision": "selected | rejected", "reason": "specific reason"},
        {"medium": "generated-conceptual-image", "decision": "selected | rejected", "reason": "specific reason"}
      ],
      "text_role": "what the words add to the visual",
      "image_need": "required | helpful | not-needed",
      "image_need_reason": "why an image would or would not improve learning",
      "asset_strategy": "native-diagram | reuse-reference | search-online | generate | operator-request",
      "asset_strategy_reason": "why this acquisition route is the best feasible route",
      "request_box": {"image_description": "required when operator-request", "pedagogical_reason": "required when operator-request", "search_phrase": "required when operator-request"},
      "source_status": "not-required | attributed | generated-fallback | source-needed | visual-curation-required",
      "source_id": "S001 or null",
      "source_url": "URL or null",
      "generated": false,
      "max_area_percent": 50,
      "highlighted": false,
      "highlight_reason": ""
    }
  ]
}
```

Run:

```bash
python3 tools/greg_visual_plan_check.py review/lesson_[NN]_visual_plan.json
```

Fix failures before approving visual QA.

## Output

Write:

```text
review/lesson_[NN]_visual_qa.md
```

Use the required sections from the review contract.
