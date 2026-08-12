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

## Visual Preference Order

1. Deterministic diagram, chart, process flow, map, or structured visual.
2. Trusted technical/source-based image with attribution.
3. Generated conceptual image only as fallback.

Use `diagram_planning` for diagram reasoning, `diagram_rendering` for deterministic output, and `image_generation` only for conceptual fallback images.

## Focus

Check:

- teaching purpose;
- source status;
- language fit;
- caption usefulness;
- claim safety;
- whether deterministic diagrams can replace generated images;
- whether sourced images need license or attribution notes.

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
