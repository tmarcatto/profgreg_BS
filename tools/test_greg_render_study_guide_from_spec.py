#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "greg_render_study_guide_from_spec.py"
PDF_RENDERER_PATH = ROOT / "workspace" / "renderers" / "pdf" / "greg-buildstak-study-guide-renderer.py"

spec = importlib.util.spec_from_file_location("greg_render_study_guide_from_spec", MODULE_PATH)
assert spec and spec.loader
renderer = importlib.util.module_from_spec(spec)
sys.modules["greg_render_study_guide_from_spec"] = renderer
spec.loader.exec_module(renderer)

pdf_spec = importlib.util.spec_from_file_location("greg_buildstak_study_guide_renderer", PDF_RENDERER_PATH)
assert pdf_spec and pdf_spec.loader
pdf_renderer = importlib.util.module_from_spec(pdf_spec)
sys.modules["greg_buildstak_study_guide_renderer"] = pdf_renderer
try:
    pdf_spec.loader.exec_module(pdf_renderer)
except ModuleNotFoundError as error:
    if error.name != "reportlab":
        raise
    pdf_renderer = None


class RenderStudyGuideFromSpecTests(unittest.TestCase):
    def test_bare_localized_callout_label_still_renders_as_a_box(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("> EXEMPLO PRÁTICO\n> Corpo.", locale="pt_br")
        self.assertEqual("callout", blocks[0]["type"])
        self.assertEqual("EXEMPLO PRÁTICO", blocks[0]["label"])

    def test_markdown_table_becomes_a_table_block_not_a_paragraph(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown(
            "| Direct cost item | Quantity or pricing basis | Amount | Stated inclusions |\n"
            "|---|---|---:|---|\n"
            "| Excavation | Synthetic quote | $7,500 | Tax included |\n"
            "| Framing | 600 SF | $22,800 | Delivery included |\n"
        )
        self.assertEqual("table", blocks[0]["type"])
        self.assertEqual(["Direct cost item", "Quantity or pricing basis", "Amount", "Stated inclusions"], blocks[0]["headers"])
        self.assertEqual(2, len(blocks[0]["rows"]))
        table = pdf_renderer.markdown_table(blocks[0]["headers"], blocks[0]["rows"])
        self.assertEqual(pdf_renderer.colors.white, table._cellvalues[0][0].style.textColor)
        self.assertGreater(table._colWidths[1], table._colWidths[0])
        self.assertGreater(table._colWidths[3], table._colWidths[2])
        for index, header in enumerate(blocks[0]["headers"]):
            cell = table._cellvalues[0][index]
            self.assertLessEqual(
                pdf_renderer.stringWidth(header, pdf_renderer.FONT_BOLD, cell.style.fontSize),
                table._colWidths[index] - 12,
            )

    def test_generic_table_reserves_a_single_line_header_width(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        table = pdf_renderer.markdown_table(
            ["Estimate-control item", "Basis", "Status"],
            [["Temporary facilities", "Quote", "Included"]],
        )
        first = table._cellvalues[0][0]
        self.assertLessEqual(
            pdf_renderer.stringWidth("Estimate-control item", pdf_renderer.FONT_BOLD, first.style.fontSize),
            table._colWidths[0] - 12,
        )

    def test_currency_table_cell_is_atomic_and_column_is_wide_enough(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        table = pdf_renderer.markdown_table(
            ["Item de custo indireto do projeto", "Valor", "Inclusões declaradas"],
            [["Supervisão e coordenação do local", "$12,000", "Imposto não aplicável."]],
        )
        value = table._cellvalues[1][1]
        self.assertEqual(0, value.style.splitLongWords)
        self.assertGreaterEqual(
            table._colWidths[1] - 12,
            pdf_renderer.stringWidth("$12,000", pdf_renderer.FONT_REGULAR, value.style.fontSize),
        )

    def test_story_keeps_a_short_table_together(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        story = pdf_renderer.build_story(
            [{"type": "table", "headers": ["Item", "Value"], "rows": [["First item", "$1"], ["Second item", "$2"]]}],
            [],
        )
        self.assertTrue(any(isinstance(item, pdf_renderer.KeepTogether) for item in story))

    def test_cost_stack_total_clears_the_title_area(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        class Canvas:
            def __init__(self): self.boxes = []
            def setFillColor(self, *_): pass
            def setStrokeColor(self, *_): pass
            def setFont(self, *_): pass
            def roundRect(self, x, y, w, h, *_ , **__):
                self.boxes.append((x, y, w, h))
            def drawString(self, *_): pass
            def drawCentredString(self, *_): pass
        diagram = pdf_renderer.CostStackDiagram("Five Additive Cost Layers", [{"title": "Direct", "detail": "Base"}] * 5, "Calculated proposal price")
        diagram.width = 6.5 * pdf_renderer.inch
        diagram.canv = Canvas()
        diagram.draw()
        total_box = next(box for box in diagram.canv.boxes if abs(box[0] - diagram.width * .25) < 1)
        self.assertLess(total_box[1] + total_box[3], 300)

    def test_localized_source_accepts_plain_localized_callout_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "lesson_01_pt_br.md"
            source.write_text(
                "\n".join([
                    "# Seção 01: Primeiro", "# Seção 02: Segundo", "# Seção 03: Terceiro", "# Seção 04: Quarto",
                    "> TERMO-CHAVE  ", "> Definição.", "> APLIQUE  ", "> Ação.",
                    "# Resumo e Principais Conclusões", "- Um", "- Dois", "- Três", "- Quatro",
                    "# Referências",
                ]),
                encoding="utf-8",
            )
            renderer.validate_localized_source(source, "pt_br")

    def test_localized_source_accepts_equivalent_numbered_heading_formatting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "lesson_01_pt_br.md"
            source.write_text(
                "\n".join([
                    "## Seção 1 — Primeiro", "# Seção 2 – Segundo", "## Seção 3: Terceiro", "# Seção 4 - Quarto",
                    "> TERMO-CHAVE", "> Definição.", "> APLIQUE", "> Ação.",
                    "# Resumo e Principais Conclusões", "- Um", "- Dois", "- Três", "- Quatro",
                    "# Referências",
                ]),
                encoding="utf-8",
            )
            renderer.validate_localized_source(source, "pt_br")

    def test_card_row_never_draws_unwrapped_detail_text(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        class Canvas:
            def __init__(self): self.text = []
            def setFillColor(self, *_): pass
            def setStrokeColor(self, *_): pass
            def setFont(self, *_): pass
            def roundRect(self, *_ , **__): pass
            def drawString(self, _, __, text): self.text.append(text)
            def drawCentredString(self, _, __, text): self.text.append(text)
        diagram = pdf_renderer.CardRowDiagram("Title", [{"title": "Card", "lines": ["This detail must not cross the diagram."]}])
        diagram.width = 400
        diagram.canv = Canvas()
        diagram.draw()
        self.assertNotIn("This detail must not cross the diagram.", diagram.canv.text)

    def test_card_row_count_must_match_its_title(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        with self.assertRaisesRegex(ValueError, "declares 7 items but contains 5 cards"):
            pdf_renderer.validate_visuals([{
                "type": "card_row",
                "title": "Seven Core Responsibilities",
                "cards": [{"title": "Item"}] * 5,
            }])

    def test_cost_stack_is_a_supported_pdf_visual(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        pdf_renderer.validate_visuals([{
            "type": "cost_stack",
            "title": "Cost Stack",
            "nodes": [{"title": "Direct cost", "detail": "Measured work"}, {"title": "Price", "detail": "Final proposal"}],
        }])

    def test_relationship_map_central_title_keeps_three_visible_lines(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        class Canvas:
            def setFillColor(self, *_): pass
            def setStrokeColor(self, *_): pass
            def setLineWidth(self, *_): pass
            def roundRect(self, *_ , **__): pass
            def line(self, *_): pass
            def setFont(self, *_): pass
            def drawString(self, *_): pass
            def drawCentredString(self, *_): pass
        title = "Fogão elétrico fornecido pelo proprietário"
        diagram = pdf_renderer.RelationshipMapDiagram("Responsabilidades", [{"title": title}] + [{"title": "Papel"}] * 5)
        diagram.width = 468
        diagram.canv = Canvas()
        diagram.draw()
        pdf_renderer.validate_visuals([{"type": "relationship_map", "title": "Responsabilidades", "nodes": [{"title": title}] + [{"title": "Papel"}] * 5}])

    def test_comparison_matrix_rejects_a_fourth_visible_line_even_within_character_limit(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        text = "W" * 120
        self.assertLessEqual(len(text), 130)
        with self.assertRaisesRegex(ValueError, "does not fit in three visible lines"):
            pdf_renderer.validate_visuals([{
                "type": "source_to_wbs_matrix",
                "left_header": "Conceito",
                "right_header": "Significado em campo",
                "rows": [
                    {"left": "Primeira opção", "right": text},
                    {"left": "Segunda opção", "right": "Texto curto"},
                ],
            }])

    def test_card_row_uses_first_count_declared_in_title(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        pdf_renderer.validate_visuals([{
            "type": "card_row",
            "title": "Five Operating Responsibilities Applied to One Change",
            "cards": [{"title": "Item"}] * 5,
        }])

    def test_seven_card_diagram_keeps_every_title(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        class Canvas:
            def __init__(self): self.text = []
            def setFillColor(self, *_): pass
            def setStrokeColor(self, *_): pass
            def setFont(self, *_): pass
            def roundRect(self, *_ , **__): pass
            def drawString(self, _, __, text): self.text.append(text)
            def drawCentredString(self, _, __, text): self.text.append(text)
        cards = [{"title": title} for title in [
            "Review the job file", "Maintain two schedule horizons", "Conduct daily home walks",
            "Coordinate trades and dependencies", "Document progress and records",
            "Coordinate jobsite safety", "Address homeowner concerns",
        ]]
        diagram = pdf_renderer.CardRowDiagram("Seven Core Responsibilities", cards)
        diagram.width = 500
        diagram.canv = Canvas()
        diagram.draw()
        self.assertIn("safety", " ".join(diagram.canv.text).lower())
        self.assertIn("homeowner", " ".join(diagram.canv.text).lower())

    def test_wrap_lines_never_leaves_a_word_wider_than_the_box(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        lines = pdf_renderer.wrap_lines("Pre-Construction", pdf_renderer.FONT_BOLD, 8.5, 48)
        self.assertGreaterEqual(len(lines), 2)
        self.assertTrue(all(pdf_renderer.stringWidth(line, pdf_renderer.FONT_BOLD, 8.5) <= 48 for line in lines))

    def test_process_flow_keeps_combined_title_and_detail_inside_each_box(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        class Canvas:
            def __init__(self): self.text = []
            def setFillColor(self, *_): pass
            def setStrokeColor(self, *_): pass
            def setLineWidth(self, *_): pass
            def setFont(self, *_): pass
            def roundRect(self, *_ , **__): pass
            def drawString(self, x, y, text): self.text.append((x, y, text))
            def line(self, *_): pass
            def beginPath(self):
                class Path:
                    def moveTo(self, *_): pass
                    def lineTo(self, *_): pass
                    def close(self): pass
                return Path()
            def drawPath(self, *_, **__): pass
        nodes = [
            {"title": "Porta de Lead/Viabilidade", "detail": "Screen job; brief risks and gaps"},
            {"title": "Pre-Construction Plan", "detail": "Define scope, budget, controls"},
            {"title": "Design & Permit Readiness", "detail": "Route questions; permit filed"},
            {"title": "Procurement & Mobilization", "detail": "Order long-leads; set up site"},
            {"title": "Construction Control", "detail": "Track changes, cost, quality"},
            {"title": "Closeout & Warranty", "detail": "Punch, records, callback response"},
        ]
        diagram = pdf_renderer.ProcessFlowDiagram("Residential Project Lifecycle Stages", nodes)
        diagram.width = 468
        diagram.canv = Canvas()
        diagram.draw()
        node_text = [(y, text) for _, y, text in diagram.canv.text if text not in {"1", "2", "3", "4", "5", "6"}]
        self.assertTrue(node_text)
        self.assertTrue(all(y >= 52 for y, _ in node_text))
        rendered_lines = {text for _, text in node_text}
        self.assertTrue(any("Lead/" in line for line in rendered_lines))
        self.assertIn("Viabilidade", rendered_lines)
        self.assertIn("Procurement", rendered_lines)
        self.assertIn("Construction", rendered_lines)
        self.assertNotIn("Opportun", rendered_lines)

    def test_source_with_paragraph_summary_is_blocked_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as tmp:
            draft = Path(tmp) / "draft.md"
            draft.write_text(
                "# Introduction\n\nCourse orientation.\n\n"
                "# Section 01 - One\n\nBody text.\n\n"
                "# Section 02 - Two\n\nBody text.\n\n"
                "# Section 03 - Three\n\nBody text.\n\n"
                "# Section 04 - Four\n\nBody text.\n\n"
                "# Summary and Key Takeaways\n\nThis must be bullets, not a paragraph.\n\n"
                "# References\n\n- A formal source.\n",
                encoding="utf-8",
            )
            relative = str(draft.relative_to(ROOT))
            with self.assertRaisesRegex(RuntimeError, "Summary must contain only 4 to 6 bullet points"):
                renderer.validate_source_markdown({"source_markdown": relative})

    def test_portuguese_localized_structure_passes_content_validation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as tmp:
            draft = Path(tmp) / "draft.md"
            sections = "\n\n".join(f"# Seção {number:02d}: Título\n\nTexto." for number in range(1, 5))
            draft.write_text(
                "# Introdução\n\nOrientação.\n\n" + sections
                + "\n\n> **TERMO-CHAVE**\n>\n> Definição.\n\nTexto.\n\n> **CENÁRIO**\n>\n> Situação.\n\n"
                + "# Resumo e Principais Conclusões\n\n- Um.\n- Dois.\n- Três.\n- Quatro.\n\n"
                + "# Glossário\n\nTermo.\n\n# Referências\n\n- Fonte formal.\n",
                encoding="utf-8",
            )
            renderer.validate_source_markdown({"source_markdown": str(draft.relative_to(ROOT)), "locale": "pt_br"})

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

    def test_structural_pages_are_enforced_by_heading(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        self.assertTrue(pdf_renderer.starts_structural_page("Introduction"))
        self.assertTrue(pdf_renderer.starts_structural_page("Section 01 - The First Decision"))
        self.assertTrue(pdf_renderer.starts_structural_page("Summary and Key Takeaways"))
        self.assertFalse(pdf_renderer.starts_structural_page("Section 02 - The Next Decision"))
        self.assertFalse(pdf_renderer.starts_structural_page("Seção 02: A Próxima Decisão", "pt_br"))
        self.assertFalse(pdf_renderer.starts_structural_page("Sección 02: La Próxima Decisión", "es"))

    def test_visual_heading_matches_section_prefix(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        self.assertTrue(pdf_renderer.visual_matches_heading("Section 01", "Section 01 - The First Decision"))
        self.assertFalse(pdf_renderer.visual_matches_heading("Section 01", "Section 02 - The Next Decision"))

    def test_approved_inline_callout_keeps_short_label_and_full_body(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown(
            "> **Scenario: These responsibilities are one job, not six.** The duties run simultaneously."
        )
        self.assertEqual(blocks[0]["label"], "SCENARIO")
        self.assertEqual(
            blocks[0]["body"],
            "These responsibilities are one job, not six. The duties run simultaneously.",
        )

    def test_all_common_markdown_bullet_markers_render_as_bullets(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("* Primeiro\n+ Segundo\n- Terceiro")
        self.assertEqual(blocks, [{"type": "bullets", "items": ["Primeiro", "Segundo", "Terceiro"]}])

    def test_unapproved_callout_label_is_not_rendered_as_box(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("> **A Clever New Box:** This must remain ordinary prose.")
        self.assertEqual(blocks[0]["type"], "paragraph")

    def test_plain_canonical_callout_syntax_is_rendered_as_box(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("> KEY TERM: Scope is the agreed work.")
        self.assertEqual(blocks[0], {"type": "callout", "label": "KEY TERM", "body": "Scope is the agreed work."})

    def test_fenced_ascii_visual_is_not_rendered_as_prose(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        blocks = pdf_renderer.parse_markdown("Body before.\n\n```\n[A] -> [B]\n```\n\nBody after.")
        self.assertEqual([block["text"] for block in blocks if block["type"] == "paragraph"], ["Body before.", "Body after."])

    def test_long_cover_title_fits_three_lines_without_dropping_words(self) -> None:
        if pdf_renderer is None:
            self.skipTest("ReportLab is not installed in this Python environment.")
        title = "The Complete Construction Project Manager From Pre-Construction to Closeout"
        lines, font_size = pdf_renderer.fit_cover_title(title, 360)
        self.assertLessEqual(len(lines), 3)
        self.assertGreaterEqual(font_size, 18)
        self.assertEqual(" ".join(lines), title)


if __name__ == "__main__":
    unittest.main()
