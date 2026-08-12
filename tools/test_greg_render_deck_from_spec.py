#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_render_deck_from_spec.py"

spec = importlib.util.spec_from_file_location("greg_render_deck_from_spec", MODULE_PATH)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
sys.modules["greg_render_deck_from_spec"] = renderer
spec.loader.exec_module(renderer)


class RenderDeckFromSpecTests(unittest.TestCase):
    def test_run_folder_from_relative_spec(self) -> None:
        path = renderer.run_folder_from_spec({"run_folder": "runs/demo"})
        self.assertEqual(path, ROOT / "runs" / "demo")

    def test_workspace_defaults_to_deck_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = Path(tmp) / "deck_spec.json"
            spec_path.write_text(json.dumps({"run_folder": "runs/demo"}), encoding="utf-8")
            spec_data = renderer.read_json(spec_path)
            self.assertEqual(renderer.workspace_for_spec(spec_path, spec_data), ROOT / "runs" / "demo" / "deck" / "tmp")

    def test_workspace_can_be_overridden(self) -> None:
        spec_data = {"run_folder": "runs/demo", "renderer_workspace": "tmp/deck-render"}
        self.assertEqual(renderer.workspace_for_spec(Path("spec.json"), spec_data), ROOT / "tmp" / "deck-render")

    def test_run_folder_blocks_absolute_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                renderer.run_folder_from_spec({"run_folder": tmp})


if __name__ == "__main__":
    unittest.main()
