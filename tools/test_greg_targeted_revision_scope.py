from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
