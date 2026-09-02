#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from greg_localized_deck_guard import LocalizedDeckIntegrityError, validate_localized_deck


PRESENTATION = "http://schemas.openxmlformats.org/presentationml/2006/main"


def write_pptx(path: Path, shape_counts: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "ppt/presentation.xml",
            f'<p:presentation xmlns:p="{PRESENTATION}"><p:sldSz cx="12192000" cy="6858000"/></p:presentation>',
        )
        for index, shape_count in enumerate(shape_counts, start=1):
            shapes = "".join("<p:sp/>" for _ in range(shape_count))
            archive.writestr(
                f"ppt/slides/slide{index}.xml",
                f'<p:sld xmlns:p="{PRESENTATION}"><p:cSld><p:spTree>{shapes}<p:pic/></p:spTree></p:cSld></p:sld>',
            )


def build_run(root: Path, *, localized_shapes: list[int], baseline: str = "deck/lesson_05_deck_r02.pptx") -> tuple[Path, Path]:
    run = root / "runs" / "demo"
    source_deck = run / "deck" / "lesson_05_deck_r02.pptx"
    localized_deck = run / "localization" / "pt-br" / "lesson_05_deck_pt_br_r01.pptx"
    write_pptx(source_deck, [3, 5])
    write_pptx(localized_deck, localized_shapes)
    (run / "approval").mkdir(parents=True)
    (run / "approval" / "lesson_05_deck_approval.md").write_text(
        "- Artifact: runs/demo/deck/lesson_05_deck_r02.pptx\n",
        encoding="utf-8",
    )
    slides = [
        {"layout": "cover", "title": "Plan", "topics": ["One", "Two"]},
        {"layout": "comparison", "title": "Compare", "left": {"title": "A"}, "right": {"title": "B"}},
    ]
    (run / "deck" / "lesson_05_deck_spec_r02.json").write_text(
        json.dumps({"output": {"pptx": "deck/lesson_05_deck_r02.pptx"}, "slides": slides}),
        encoding="utf-8",
    )
    localized_slides = [
        {"layout": "cover", "title": "Plano", "topics": ["Um", "Dois"]},
        {"layout": "comparison", "title": "Compare", "left": {"title": "A"}, "right": {"title": "B"}},
    ]
    (localized_deck.parent / "lesson_05_deck_pt_br_spec_r01.json").write_text(
        json.dumps(
            {
                "approved_baseline_artifact": baseline,
                "output": {"pptx": "localization/pt-br/lesson_05_deck_pt_br_r01.pptx"},
                "slides": localized_slides,
            }
        ),
        encoding="utf-8",
    )
    return run, localized_deck


class LocalizedDeckGuardTests(unittest.TestCase):
    def test_accepts_localized_deck_with_exact_approved_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run, localized_deck = build_run(Path(directory), localized_shapes=[3, 5])

            evidence = validate_localized_deck(run, "lesson_05", localized_deck)

            self.assertEqual("deck/lesson_05_deck_r02.pptx", evidence["approved_deck_path"])
            self.assertTrue(evidence["localized_deck_sha256"])

    def test_rejects_localized_pptx_rendered_from_different_slide_structure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run, localized_deck = build_run(Path(directory), localized_shapes=[2, 8])

            with self.assertRaisesRegex(LocalizedDeckIntegrityError, "does not preserve"):
                validate_localized_deck(run, "lesson_05", localized_deck)

    def test_rejects_localized_spec_pointing_to_another_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run, localized_deck = build_run(
                Path(directory),
                localized_shapes=[3, 5],
                baseline="deck/lesson_05_deck_r01.pptx",
            )

            with self.assertRaisesRegex(LocalizedDeckIntegrityError, "currently approved"):
                validate_localized_deck(run, "lesson_05", localized_deck)


if __name__ == "__main__":
    unittest.main()
