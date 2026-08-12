#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_render_study_guide_from_spec.py"

spec = importlib.util.spec_from_file_location("greg_render_study_guide_from_spec", MODULE_PATH)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
sys.modules["greg_render_study_guide_from_spec"] = renderer
spec.loader.exec_module(renderer)


class RenderStudyGuideFromSpecTests(unittest.TestCase):
    def test_run_folder_from_relative_spec(self) -> None:
        path = renderer.run_folder_from_spec({"run_folder": "runs/demo"})
        self.assertEqual(path, ROOT / "runs" / "demo")

    def test_run_folder_blocks_absolute_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                renderer.run_folder_from_spec({"run_folder": tmp})

    def test_output_pdf_from_spec(self) -> None:
        spec_data = {"run_folder": "runs/demo", "output": {"pdf": "docx_pdf/lesson_01_study_guide_r02.pdf"}}
        self.assertEqual(renderer.output_pdf_from_spec(spec_data), ROOT / "runs" / "demo" / "docx_pdf" / "lesson_01_study_guide_r02.pdf")


if __name__ == "__main__":
    unittest.main()
