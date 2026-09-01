from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
MODULE_PATH = ROOT / "tools" / "greg_live_production.py"
spec = importlib.util.spec_from_file_location("greg_live_production_scope_test", MODULE_PATH)
production = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(production)


BASELINE = """# Introduction

Keep intro.

## Learning Objectives

- Keep objective.

# Section 01 - Cost Boxes

Old box.

# Section 02 - Cash Flow

Keep cash flow.

# Summary and Key Takeaways

- Keep summary.

# Glossary

Keep glossary.

# References

- Keep reference.
"""


class TargetedRevisionScopeTests(unittest.TestCase):
    def test_selected_section_patch_preserves_every_other_section(self) -> None:
        candidate = BASELINE.replace("Old box.", "Text-only box.")
        changed = production.changed_study_guide_sections(BASELINE, candidate)
        self.assertEqual({"# Section 01 - Cost Boxes"}, changed)
        production.require_targeted_study_guide_scope(BASELINE, candidate, changed)

    def test_later_revision_cannot_expand_to_an_unselected_section(self) -> None:
        initial = BASELINE.replace("Old box.", "Text-only box.")
        allowed = production.changed_study_guide_sections(BASELINE, initial)
        expanded = initial.replace("Keep cash flow.", "Rewritten cash flow.")
        with self.assertRaisesRegex(RuntimeError, "outside the operator-selected errors"):
            production.require_targeted_study_guide_scope(BASELINE, expanded, allowed)

    def test_renderer_only_request_authorizes_no_content_changes(self) -> None:
        production.require_targeted_study_guide_scope(BASELINE, BASELINE, set())
        with self.assertRaisesRegex(RuntimeError, "outside the operator-selected errors"):
            production.require_targeted_study_guide_scope(
                BASELINE,
                BASELINE.replace("Keep intro.", "Changed intro."),
                set(),
            )

    def test_reviewer_prompt_names_the_only_authorized_heading(self) -> None:
        class Seed:
            title = "Course"

        prompt = production.reviewer_prompt(
            "design_review",
            Seed(),
            {"lesson_number": 6, "title": "Budget"},
            BASELINE.replace("Old box.", "Text-only box."),
            {"sources": []},
            approved_baseline=BASELINE,
            operator_revision_request="Simplify the box text.",
            operator_allowed_headings={"# Section 01 - Cost Boxes"},
        )
        self.assertIn("only the following section headings may change", prompt)
        self.assertIn("# Section 01 - Cost Boxes", prompt)

    def test_visual_audit_metadata_does_not_change_visible_plan(self) -> None:
        plan = {
            "artifact_type": "study-guide",
            "visuals": [{
                "visual_id": "L06V01",
                "visual_type": "deterministic-diagram",
                "placement": "after Section 01 - Cost Boxes",
                "purpose": "Show one cost control sequence",
                "learning_claim": "Every cost follows the same control chain.",
                "diagram_type": "process-flow",
                "diagram_rationale": "A process flow makes the required ordered handoff visible to the learner.",
                "diagram_title": "Cost Control Chain",
                "diagram_nodes": [{"title": "Budget", "detail": ""}],
                "core_message_depends_on_real_example": False,
                "technical_fidelity_required": False,
            }],
        }
        before = copy.deepcopy(plan)
        completed = production.complete_targeted_visual_decision_evidence(plan)
        for key in ("visual_id", "visual_type", "placement", "purpose", "learning_claim", "diagram_type", "diagram_title", "diagram_nodes"):
            self.assertEqual(before["visuals"][0][key], completed["visuals"][0][key])
        self.assertTrue(production.visual_plan_has_decision_evidence(completed))

    def test_visual_only_requests_do_not_authorize_markdown_changes(self) -> None:
        feedback = """## Request 1

The boxes need to have just text written.

Supporting materials:
- screenshot.png

## Request 2

Big space between the title and the beginning of the diagram.

## Request 3

List incomplete, missing number six.
"""
        self.assertTrue(production.study_guide_revision_is_visual_only(feedback))
        self.assertFalse(production.study_guide_revision_is_visual_only("## Request 1\n\nCorrect the factual explanation."))

    def test_approved_draft_ignores_newer_unapproved_candidates(self) -> None:
        with TemporaryDirectory() as directory:
            run = Path(directory)
            drafts = run / "lesson_draft"
            feedback = run / "operator_feedback"
            drafts.mkdir()
            feedback.mkdir()
            paths = []
            for revision in (1, 3, 4):
                path = drafts / f"lesson_06_draft_r{revision:02d}.md"
                path.write_text(BASELINE, encoding="utf-8")
                paths.append(path)
            (feedback / "lesson_06_study_guide_revision_state.json").write_text(
                '{"baseline_artifact":"runs/course/docx_pdf/lesson_06_study_guide_r02.pdf"}',
                encoding="utf-8",
            )
            self.assertEqual(paths[0], production.approved_revision_draft_path(run, "lesson_06", paths))


if __name__ == "__main__":
    unittest.main()
