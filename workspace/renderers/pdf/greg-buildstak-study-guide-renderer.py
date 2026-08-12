#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[3]

NAVY = colors.HexColor("#1f3f67")
ORANGE = colors.HexColor("#ff6b13")
INK = colors.HexColor("#343a40")
MUTED = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#f5f7fb")
PALE_ORANGE = colors.HexColor("#fff2e9")
LINE = colors.HexColor("#d5dce8")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyGreg", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.3, leading=15.3, textColor=INK, spaceAfter=7))
styles.add(ParagraphStyle(name="IntroBody", parent=styles["BodyGreg"], fontSize=10, leading=14.4, spaceAfter=6))
styles.add(ParagraphStyle(name="H1Greg", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=NAVY, spaceBefore=12, spaceAfter=12))
styles.add(ParagraphStyle(name="H2Greg", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14.2, leading=17, textColor=NAVY, spaceBefore=12, spaceAfter=6))
styles.add(ParagraphStyle(name="H2Keep", parent=styles["H2Greg"], keepWithNext=1))
styles.add(ParagraphStyle(name="RefGreg", parent=styles["BodyGreg"], fontSize=8.5, leading=11.5, leftIndent=10, firstLineIndent=-10, spaceAfter=5))
styles.add(ParagraphStyle(name="CalloutLabel", parent=styles["BodyGreg"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=NAVY, spaceAfter=0))
styles.add(ParagraphStyle(name="CalloutBody", parent=styles["BodyGreg"], fontSize=9.5, leading=13, textColor=INK, spaceAfter=0))
styles.add(ParagraphStyle(name="Caption", parent=styles["BodyGreg"], fontSize=8.6, leading=11, textColor=MUTED, alignment=TA_CENTER, spaceBefore=4, spaceAfter=10))


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    root_resolved = ROOT.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path escapes Prof Greg workspace: {value}")
    return resolved


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    return escaped


def wrap_lines(text: str, font: str, size: int, max_width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if stringWidth(test, font, size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class SectionHeader(Flowable):
    def __init__(self, number: int, title: str):
        super().__init__()
        self.number = number
        self.title = title
        self.height = 58

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        c.setStrokeColor(ORANGE)
        c.setLineWidth(2)
        c.line(0, self.height - 4, w, self.height - 4)
        heading = f"Section {self.number:02d} - {self.title}"
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 18)
        if stringWidth(heading, "Helvetica-Bold", 18) <= w - 4:
            c.drawString(0, self.height - 30, heading)
            return
        c.setFont("Helvetica-Bold", 16)
        for index, line in enumerate(wrap_lines(heading, "Helvetica-Bold", 16, w - 4)[:2]):
            c.drawString(0, self.height - 28 - 19 * index, line)


class Callout:
    def __init__(self, label: str, body: str):
        self.label = label
        self.body = body

    def flowable(self):
        orange_labels = {"WATCH OUT", "DID YOU KNOW?", "KEY PRINCIPLE"}
        border = ORANGE if self.label.upper() in orange_labels else NAVY
        fill = PALE_ORANGE if self.label.upper() in orange_labels else LIGHT
        table = Table(
            [[Paragraph(self.label, styles["CalloutLabel"]), Paragraph(inline(self.body), styles["CalloutBody"])]],
            colWidths=[1.6 * inch, 4.85 * inch],
            hAlign="LEFT",
        )
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.1, border),
            ("BACKGROUND", (0, 0), (-1, -1), fill),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        return KeepTogether([Spacer(1, 7), table, Spacer(1, 9)])


class CardRowDiagram(Flowable):
    def __init__(self, title: str, cards: list[dict[str, Any]], pill: str | None = None):
        super().__init__()
        self.title = title
        self.cards = cards
        self.pill = pill
        self.height = 230 if pill else 205

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(0, self.height - 18, self.title)
        card_gap = 12
        card_w = (w - card_gap * (len(self.cards) - 1)) / len(self.cards)
        y = 58 if self.pill else 42
        for index, card in enumerate(self.cards):
            x = index * (card_w + card_gap)
            c.setFillColor(PALE_ORANGE if card.get("highlight") else LIGHT)
            c.setStrokeColor(ORANGE if card.get("highlight") else LINE)
            c.roundRect(x, y, card_w, 88, 6, stroke=1, fill=1)
            c.setFillColor(ORANGE if card.get("highlight") else NAVY)
            c.setFont("Helvetica-Bold", 9.2)
            for line_index, line in enumerate(wrap_lines(str(card["title"]), "Helvetica-Bold", 9.2, card_w - 14)[:2]):
                c.drawCentredString(x + card_w / 2, y + 58 - line_index * 11, line)
            c.setFillColor(INK)
            c.setFont("Helvetica", 7.8)
            for line_index, line in enumerate(card.get("lines", [])[:2]):
                c.drawCentredString(x + card_w / 2, y + 31 - line_index * 11, str(line))
        if self.pill:
            c.setFillColor(NAVY)
            c.roundRect(w / 2 - 98, 14, 196, 32, 16, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9.2)
            c.drawCentredString(w / 2, 26, self.pill)


class TimelineDiagram(Flowable):
    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.height = 250

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(0, self.height - 18, self.title)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(0, 184, "Weak timeline")
        c.setStrokeColor(LINE)
        c.setLineWidth(1.5)
        c.line(110, 189, w - 20, 189)
        c.setFillColor(ORANGE)
        c.circle(120, 189, 4, fill=1, stroke=0)
        c.circle(w - 25, 189, 4, fill=1, stroke=0)
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 8.2)
        c.drawCentredString(w / 2 + 45, 168, "Shows dates, but not enough logic to manage the work.")
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(0, 120, "Usable baseline")
        labels = [("Layout", "field start"), ("Framing", "trade work"), ("Rough-ins", "MEP path"), ("Inspection", "approval gate"), ("Drywall", "next phase")]
        x0 = 112
        bw = (w - 132) / 5
        for index, (title, sub) in enumerate(labels):
            x = x0 + index * bw
            c.setFillColor(LIGHT)
            c.setStrokeColor(ORANGE if title == "Inspection" else LINE)
            c.roundRect(x, 92, bw - 8, 48, 5, stroke=1, fill=1)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 8.6)
            c.drawCentredString(x + (bw - 8) / 2, 120, title)
            c.setFillColor(INK)
            c.setFont("Helvetica", 7.8)
            c.drawCentredString(x + (bw - 8) / 2, 107, sub)
            if index < 4:
                c.setStrokeColor(ORANGE)
                c.line(x + bw - 6, 116, x + bw + 2, 116)


class SourceToWBSMatrix(Flowable):
    def __init__(self, title: str, left_header: str, right_header: str, rows: list[dict[str, Any]]):
        super().__init__()
        self.title = title
        self.left_header = left_header
        self.right_header = right_header
        self.rows = rows
        self.height = 245

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw_cell_text(self, x: float, y: float, width: float, text: str, *, bold: bool = False):
        c = self.canv
        font = "Helvetica-Bold" if bold else "Helvetica"
        size = 8.4 if bold else 8.2
        c.setFont(font, size)
        c.setFillColor(NAVY if bold else INK)
        for index, line in enumerate(wrap_lines(text, font, size, width - 18)[:2]):
            c.drawString(x + 9, y - 13 - index * 10, line)

    def draw(self):
        c = self.canv
        w = self.width
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(0, self.height - 18, self.title)

        table_x = 24
        table_y = self.height - 52
        table_w = w - 48
        left_w = table_w * 0.42
        right_w = table_w - left_w
        header_h = 28
        row_h = 29

        c.setFillColor(NAVY)
        c.roundRect(table_x, table_y - header_h, table_w, header_h, 6, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.7)
        c.drawString(table_x + 11, table_y - 18, self.left_header)
        c.drawString(table_x + left_w + 11, table_y - 18, self.right_header)

        for index, row in enumerate(self.rows[:5]):
            y_top = table_y - header_h - index * row_h
            c.setFillColor(LIGHT if index % 2 == 0 else colors.white)
            c.rect(table_x, y_top - row_h, table_w, row_h, stroke=0, fill=1)
            c.setStrokeColor(LINE)
            c.line(table_x, y_top - row_h, table_x + table_w, y_top - row_h)
            self.draw_cell_text(table_x, y_top - 2, left_w, str(row.get("left", "")), bold=True)
            self.draw_cell_text(table_x + left_w, y_top - 2, right_w, str(row.get("right", "")))

        c.setStrokeColor(LINE)
        c.setLineWidth(1)
        c.roundRect(table_x, table_y - header_h - row_h * min(len(self.rows), 5), table_w, header_h + row_h * min(len(self.rows), 5), 6, stroke=1, fill=0)
        c.line(table_x + left_w, table_y, table_x + left_w, table_y - header_h - row_h * min(len(self.rows), 5))


class CPMNetworkDiagram(Flowable):
    def __init__(self, title: str, paths: list[dict[str, Any]]):
        super().__init__()
        self.title = title
        self.paths = paths
        self.height = 255

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw_node(self, x: float, y: float, w: float, title: str, days: str, critical: bool = False):
        c = self.canv
        c.setFillColor(PALE_ORANGE if critical else LIGHT)
        c.setStrokeColor(ORANGE if critical else LINE)
        c.roundRect(x, y, w, 42, 5, stroke=1, fill=1)
        c.setFillColor(ORANGE if critical else NAVY)
        c.setFont("Helvetica-Bold", 7.8)
        for index, line in enumerate(wrap_lines(title, "Helvetica-Bold", 7.8, w - 10)[:2]):
            c.drawCentredString(x + w / 2, y + 27 - index * 9, line)
        c.setFillColor(INK)
        c.setFont("Helvetica", 7.1)
        c.drawCentredString(x + w / 2, y + 7, days)

    def draw(self):
        c = self.canv
        w = self.width
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(0, self.height - 18, self.title)

        start_x = 20
        finish_x = w - 68
        node_w = 60
        lane_gap = 80
        top_y = 142
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 8.4)
        c.drawCentredString(start_x + 26, top_y + 22, "Start")
        c.drawCentredString(finish_x + 30, top_y + 22, "Finish")
        c.setStrokeColor(NAVY)
        c.setLineWidth(1.5)
        c.circle(start_x + 26, top_y + 6, 12, stroke=1, fill=0)
        c.circle(finish_x + 30, top_y + 6, 12, stroke=1, fill=0)

        for lane_index, path_data in enumerate(self.paths[:2]):
            y = top_y - lane_index * lane_gap
            activities = path_data.get("activities", [])[:4]
            critical = bool(path_data.get("critical"))
            color = ORANGE if critical else LINE
            c.setStrokeColor(color)
            c.setLineWidth(2.4 if critical else 1.6)
            c.line(start_x + 38, y + 6, start_x + 70, y + 6)
            if activities:
                gap = (finish_x - start_x - 98 - node_w * len(activities)) / max(len(activities) - 1, 1)
                node_xs = [start_x + 72 + i * (node_w + gap) for i in range(len(activities))]
                for index, activity in enumerate(activities):
                    x = node_xs[index]
                    self.draw_node(x, y - 15, node_w, str(activity.get("title", "")), str(activity.get("duration", "")), critical)
                    c.setStrokeColor(color)
                    if index < len(activities) - 1:
                        c.line(x + node_w, y + 6, node_xs[index + 1], y + 6)
                    else:
                        c.line(x + node_w, y + 6, finish_x + 18, y + 6)
            c.setFillColor(ORANGE if critical else MUTED)
            c.setFont("Helvetica-Bold", 8.6)
            c.drawString(0, y - 26, str(path_data.get("label", "")))


def p(text: str, style: str = "BodyGreg"):
    return Paragraph(inline(text), styles[style])


def bullets(items: list[str], style: str = "BodyGreg"):
    return ListFlowable(
        [ListItem(Paragraph(inline(item), styles[style]), leftIndent=14) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=18,
        bulletFontSize=7,
        bulletColor=ORANGE,
    )


def parse_markdown(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line == "---":
            blocks.append({"type": "page_break"})
            index += 1
            continue
        if line.startswith("# "):
            blocks.append({"type": "h1", "text": line[2:].strip()})
            index += 1
            continue
        if line.startswith("## "):
            blocks.append({"type": "h2", "text": line[3:].strip()})
            index += 1
            continue
        if line.startswith("- "):
            items: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                items.append(lines[index].strip()[2:].strip())
                index += 1
            blocks.append({"type": "bullets", "items": items})
            continue
        if line.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                stripped = lines[index].strip()[1:].strip()
                if stripped:
                    quote_lines.append(stripped)
                index += 1
            label = re.sub(r"^\*\*|\*\*$", "", quote_lines[0]) if quote_lines else "NOTE"
            body = " ".join(quote_lines[1:]).strip()
            blocks.append({"type": "callout", "label": label, "body": body})
            continue
        paragraph: list[str] = [line]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if not next_line or next_line == "---" or next_line.startswith(("# ", "## ", "- ", ">")):
                break
            paragraph.append(next_line)
            index += 1
        blocks.append({"type": "paragraph", "text": " ".join(paragraph)})
    return blocks


def front_matter_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_break = next((i for i, block in enumerate(blocks) if block["type"] == "page_break"), None)
    if first_break is None:
        return blocks
    return blocks[first_break + 1 :]


def make_doc(output: Path, metadata: dict[str, Any]):
    course = metadata["course_title"]
    icon = resolve_path(metadata.get("icon", "workspace/assets/logos/buildstak-icon.png"))

    def footer(canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        y = 0.43 * inch
        if icon.exists():
            canvas.drawImage(str(icon), doc.leftMargin, y - 7, width=16, height=16, mask="auto")
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(doc.leftMargin + 22, y - 2, course)
        canvas.setFillColor(colors.HexColor("#8a8f98"))
        canvas.drawRightString(letter[0] - doc.rightMargin, y - 2, str(doc.page))
        canvas.restoreState()

    def cover(canvas, doc):
        canvas.saveState()
        W, H = letter
        canvas.setFillColor(NAVY)
        canvas.rect(0.45 * inch, 0.45 * inch, W - 0.9 * inch, H - 0.9 * inch, fill=1, stroke=0)
        canvas.setStrokeColor(ORANGE)
        canvas.setLineWidth(3)
        canvas.rect(0.95 * inch, 0.95 * inch, W - 1.9 * inch, H - 1.9 * inch, fill=0, stroke=1)
        canvas.setFillColor(colors.white)
        canvas.rect(1.35 * inch, 1.35 * inch, W - 2.7 * inch, H - 2.7 * inch, fill=1, stroke=0)
        canvas.setFillColor(ORANGE)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(1.75 * inch, H - 2.05 * inch, "STUDY GUIDE")
        if icon.exists():
            canvas.drawImage(str(icon), W - 2.12 * inch, H - 2.1 * inch, width=0.48 * inch, height=0.48 * inch, mask="auto")
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 30)
        text = canvas.beginText(1.75 * inch, H - 3.1 * inch)
        text.setLeading(34)
        for line in metadata.get("course_title_lines") or wrap_lines(course, "Helvetica-Bold", 30, W - 3.5 * inch)[:3]:
            text.textLine(line)
        canvas.drawText(text)
        canvas.setStrokeColor(ORANGE)
        canvas.setLineWidth(5)
        canvas.line(1.75 * inch, H - 4.58 * inch, W - 2.4 * inch, H - 4.58 * inch)
        canvas.setFillColor(colors.HexColor("#111827"))
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawString(1.75 * inch, H - 5.27 * inch, metadata["lesson_short_title"])
        canvas.setFont("Helvetica", 11.2)
        canvas.drawString(1.75 * inch, H - 5.56 * inch, metadata.get("lesson_subtitle", ""))
        canvas.setFillColor(ORANGE)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(1.75 * inch, H - 6.35 * inch, f"Lesson {metadata['lesson_number']}")
        canvas.setFillColor(colors.HexColor("#4b5563"))
        canvas.setFont("Helvetica", 12)
        canvas.drawString(1.75 * inch, H - 6.65 * inch, metadata.get("level_label", "Basic Level"))
        if metadata.get("quote"):
            canvas.setFillColor(NAVY)
            canvas.setFont("Helvetica-Bold", 13)
            canvas.drawString(1.75 * inch, 2.02 * inch, metadata["quote"])
            canvas.setFont("Helvetica", 10)
            canvas.drawString(1.75 * inch, 1.78 * inch, f"- {metadata.get('quote_author', '')}")
        canvas.setFillColor(colors.HexColor("#4b5563"))
        canvas.setFont("Helvetica", 9)
        canvas.drawString(1.75 * inch, 1.48 * inch, "BuildStak Learning Series")
        canvas.restoreState()

    doc = BaseDocTemplate(str(output), pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.72 * inch, bottomMargin=0.76 * inch)
    frame = Frame(doc.leftMargin, doc.bottomMargin + 0.15 * inch, doc.width, doc.height - 0.05 * inch, id="normal")
    doc.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=cover), PageTemplate(id="normal", frames=[frame], onPage=footer)])
    return doc


def visual_flowables(visual: dict[str, Any]) -> list[Any]:
    diagram_type = visual.get("type")
    if diagram_type == "card_row":
        flowable = CardRowDiagram(visual["title"], visual["cards"], visual.get("pill"))
    elif diagram_type == "timeline":
        flowable = TimelineDiagram(visual["title"])
    elif diagram_type == "source_to_wbs_matrix":
        flowable = SourceToWBSMatrix(visual["title"], visual["left_header"], visual["right_header"], visual["rows"])
    elif diagram_type == "cpm_network":
        flowable = CPMNetworkDiagram(visual["title"], visual["paths"])
    else:
        raise ValueError(f"Unknown visual type: {diagram_type}")
    result = [flowable]
    if visual.get("caption"):
        result.append(Paragraph(inline(visual["caption"]), styles["Caption"]))
    return result


def build_story(blocks: list[dict[str, Any]], visuals: list[dict[str, Any]]) -> list[Any]:
    story: list[Any] = [Spacer(1, 1), NextPageTemplate("normal"), PageBreak()]
    visual_after_heading = {item["after_heading"]: item for item in visuals if item.get("after_heading")}
    content_blocks = front_matter_blocks(blocks)
    current_heading = ""
    for block in content_blocks:
        block_type = block["type"]
        if block_type == "page_break":
            story.append(PageBreak())
        elif block_type == "h1":
            current_heading = block["text"]
            match = re.match(r"Section\s+(\d{2})\s+-\s+(.+)", block["text"], flags=re.IGNORECASE)
            if match:
                story.append(KeepTogether([SectionHeader(int(match.group(1)), match.group(2)), Spacer(1, 2)]))
            else:
                story.append(Paragraph(inline(block["text"]), styles["H1Greg"]))
        elif block_type == "h2":
            current_heading = block["text"]
            story.append(Paragraph(inline(block["text"]), styles["H2Keep"]))
        elif block_type == "bullets":
            style = "RefGreg" if current_heading == "References" else "BodyGreg"
            story.append(bullets(block["items"], style=style))
        elif block_type == "callout":
            story.append(Callout(block["label"], block["body"]).flowable())
        elif block_type == "paragraph":
            story.append(p(block["text"], "IntroBody" if len(story) < 20 else "BodyGreg"))
        if block.get("text") in visual_after_heading:
            story.extend(visual_flowables(visual_after_heading[block["text"]]))
    return story


def render_pages(pdf_path: Path, rendered_dir: Path) -> None:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return
    rendered_dir.mkdir(parents=True, exist_ok=True)
    font_cache = ROOT / "workspace" / ".cache" / "fontconfig"
    font_cache.mkdir(parents=True, exist_ok=True)
    font_config = font_cache / "fonts.conf"
    if not font_config.exists():
        font_config.write_text(
            "\n".join([
                "<?xml version=\"1.0\"?>",
                "<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">",
                "<fontconfig>",
                f"  <cachedir>{font_cache}</cachedir>",
                "  <dir>/System/Library/Fonts</dir>",
                "  <dir>/Library/Fonts</dir>",
                "</fontconfig>",
                "",
            ]),
            encoding="utf-8",
        )
    for old in rendered_dir.glob("page-*.png"):
        old.unlink()
    env = {
        **dict(os.environ),
        "XDG_CACHE_HOME": str(font_cache),
        "FONTCONFIG_CACHE": str(font_cache),
        "FONTCONFIG_FILE": str(font_config),
    }
    subprocess.run([pdftoppm, "-png", str(pdf_path), str(rendered_dir / "page")], check=True, env=env)
    for page in sorted(rendered_dir.glob("page-*.png")):
        match = re.search(r"page-(\d+)\.png$", page.name)
        if match:
            page.rename(rendered_dir / f"page-{int(match.group(1)):02d}.png")


def render(spec_path: Path) -> Path:
    spec = read_json(spec_path)
    run_folder = resolve_path(spec["run_folder"])
    markdown = resolve_path(spec["source_markdown"]).read_text(encoding="utf-8")
    output = run_folder / spec["output"]["pdf"]
    output.parent.mkdir(parents=True, exist_ok=True)
    blocks = parse_markdown(markdown)
    doc = make_doc(output, spec["metadata"])
    doc.build(build_story(blocks, spec.get("visuals", [])))
    rendered_dir = run_folder / spec["output"].get("rendered_dir", "docx_pdf/rendered_pages")
    render_pages(output, rendered_dir)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Prof Greg BuildStak study-guide PDF from a JSON spec.")
    parser.add_argument("spec", help="Path to study-guide PDF spec JSON.")
    args = parser.parse_args()
    output = render(resolve_path(args.spec))
    print(f"Rendered study guide PDF: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
