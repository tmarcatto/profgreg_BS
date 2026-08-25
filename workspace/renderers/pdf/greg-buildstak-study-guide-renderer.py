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

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
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

# Use TrueType fonts so every rendered page remains readable in Poppler and
# browser PDF viewers.  ReportLab's built-in Helvetica is not embedded, which
# caused text to disappear on the production renderer when a viewer lacked it.
FONT_REGULAR = "GregVera"
FONT_BOLD = "GregVera-Bold"
FONT_ITALIC = "GregVera-Italic"
_REPORTLAB_FONTS = Path(reportlab.__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(_REPORTLAB_FONTS / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_REPORTLAB_FONTS / "VeraBd.ttf")))
pdfmetrics.registerFont(TTFont(FONT_ITALIC, str(_REPORTLAB_FONTS / "VeraIt.ttf")))
pdfmetrics.registerFontFamily(
    FONT_REGULAR,
    normal=FONT_REGULAR,
    bold=FONT_BOLD,
    italic=FONT_ITALIC,
    boldItalic=FONT_BOLD,
)


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyGreg", parent=styles["BodyText"], fontName=FONT_REGULAR, fontSize=10.3, leading=15.0, textColor=INK, spaceAfter=6.5, allowWidows=0, allowOrphans=0))
styles.add(ParagraphStyle(name="IntroBody", parent=styles["BodyGreg"], fontSize=10, leading=14.4, spaceAfter=6))
styles.add(ParagraphStyle(name="H1Greg", parent=styles["Heading1"], fontName=FONT_BOLD, fontSize=21, leading=25, textColor=NAVY, spaceBefore=12, spaceAfter=12))
styles.add(ParagraphStyle(name="H2Greg", parent=styles["Heading2"], fontName=FONT_BOLD, fontSize=14.2, leading=17, textColor=NAVY, spaceBefore=12, spaceAfter=6))
styles.add(ParagraphStyle(name="H2Keep", parent=styles["H2Greg"], keepWithNext=1))
styles.add(ParagraphStyle(name="RefGreg", parent=styles["BodyGreg"], fontSize=8.5, leading=11.5, leftIndent=10, firstLineIndent=-10, spaceAfter=5))
styles.add(ParagraphStyle(name="CalloutLabel", parent=styles["BodyGreg"], fontName=FONT_BOLD, fontSize=10, leading=12, textColor=NAVY, spaceAfter=0))
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


def validate_render_source(markdown: str) -> None:
    """Keep direct renderer use from bypassing the summary and dash rules."""
    match = re.search(
        r"(?ims)^#\s+Summary and Key Takeaways\s*$\n(.*?)(?=^#\s+|\Z)",
        markdown,
    )
    if not match:
        raise ValueError("Study-guide source is missing Summary and Key Takeaways.")
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    bullets_only = all(re.match(r"^[-*+]\s+\S", line) for line in lines)
    if not bullets_only or not 4 <= len(lines) <= 6:
        raise ValueError("Summary and Key Takeaways must contain only 4 to 6 concise bullet points; PDF was not rendered.")
    teaching_text = markdown.split("# References", 1)[0]
    for line in teaching_text.splitlines():
        if re.match(r"^#\s+Section\s+\d{2}\s+-\s+", line):
            continue
        if "—" in line or "–" in line or re.search(r"\s-{1,2}\s", line):
            raise ValueError("Dash punctuation found in study-guide source; PDF was not rendered.")


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


def fit_single_line(text: str, font: str, max_width: float, sizes: tuple[float, ...]) -> tuple[str, float]:
    """Return a readable one-line label that cannot collide with adjacent content."""
    for size in sizes:
        if stringWidth(text, font, size) <= max_width:
            return text, size
    size = sizes[-1]
    ellipsis = "..."
    clipped = text
    while clipped and stringWidth(f"{clipped}{ellipsis}", font, size) > max_width:
        clipped = clipped[:-1]
    return f"{clipped.rstrip()}{ellipsis}", size


def fit_two_lines(text: str, font: str, max_width: float, sizes: tuple[float, ...]) -> tuple[list[str], float]:
    """Fit text completely within a two-line fixed canvas area."""
    for size in sizes:
        lines = wrap_lines(text, font, size, max_width)
        if len(lines) <= 2:
            return lines, size
    raise ValueError("Cover quotation is too long for the approved two-line cover area.")


def fit_cover_title(text: str, max_width: float, max_lines: int = 3) -> tuple[list[str], int]:
    """Fit the complete course title into the fixed cover title region."""
    for font_size in (30, 28, 26, 24, 22, 20, 18):
        lines = wrap_lines(text, FONT_BOLD, font_size, max_width)
        if len(lines) <= max_lines:
            return lines, font_size
    raise ValueError("Course title is too long for the approved cover layout.")


def draw_visual_title(canvas, title: str, width: float, height: float) -> int:
    """Draw a readable visual title without crossing the content frame."""
    max_width = width - 4
    for font_size in (15, 14, 13, 12, 11):
        if stringWidth(title, FONT_BOLD, font_size) <= max_width:
            canvas.setFillColor(NAVY)
            canvas.setFont(FONT_BOLD, font_size)
            canvas.drawString(0, height - 18, title)
            return 1
    lines = wrap_lines(title, FONT_BOLD, 11, max_width)[:2]
    canvas.setFillColor(NAVY)
    canvas.setFont(FONT_BOLD, 11)
    for index, line in enumerate(lines):
        canvas.drawString(0, height - 18 - index * 14, line)
    return len(lines)


class SectionHeader(Flowable):
    def __init__(self, number: int, title: str):
        super().__init__()
        self.number = number
        self.title = title
        self.height = 58
        self.keepWithNext = 1

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
        c.setFont(FONT_BOLD, 18)
        if stringWidth(heading, FONT_BOLD, 18) <= w - 4:
            c.drawString(0, self.height - 30, heading)
            return
        c.setFont(FONT_BOLD, 16)
        for index, line in enumerate(wrap_lines(heading, FONT_BOLD, 16, w - 4)[:2]):
            c.drawString(0, self.height - 28 - 19 * index, line)


class Callout:
    def __init__(self, label: str, body: str):
        self.label = label
        self.body = body

    def flowable(self):
        orange_labels = {"APPLY IT", "HANDS-ON EXAMPLE", "SCENARIO"}
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
        self.height = 310 if len(cards) > 5 else (230 if pill else 205)

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)
        rows = [self.cards] if len(self.cards) <= 5 else [self.cards[:4], self.cards[4:]]
        row_y = [58 if self.pill else 42] if len(rows) == 1 else [160, 58]
        card_h = 88 if len(rows) == 1 else 76
        for cards, y in zip(rows, row_y):
            card_gap = 12
            card_w = (w - card_gap * (len(cards) - 1)) / len(cards)
            start_x = (w - (card_w * len(cards) + card_gap * (len(cards) - 1))) / 2
            for index, card in enumerate(cards):
                x = start_x + index * (card_w + card_gap)
                c.setFillColor(PALE_ORANGE if card.get("highlight") else LIGHT)
                c.setStrokeColor(ORANGE if card.get("highlight") else LINE)
                c.roundRect(x, y, card_w, card_h, 6, stroke=1, fill=1)
                c.setFillColor(ORANGE if card.get("highlight") else NAVY)
                title = str(card["title"])
                for font_size in (9.2, 8.6, 8.0, 7.4):
                    title_lines = wrap_lines(title, FONT_BOLD, font_size, card_w - 14)
                    if len(title_lines) <= 2:
                        break
                else:
                    raise ValueError(f"Card title does not fit in the diagram: {title}")
                c.setFont(FONT_BOLD, font_size)
                line_gap = font_size + 1.8
                title_y = y + card_h / 2 + (len(title_lines) - 1) * line_gap / 2
                for line_index, line in enumerate(title_lines):
                    c.drawCentredString(x + card_w / 2, title_y - line_index * line_gap, line)
        if self.pill:
            c.setFillColor(NAVY)
            c.roundRect(w / 2 - 98, 14, 196, 32, 16, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(FONT_BOLD, 9.2)
            c.drawCentredString(w / 2, 26, self.pill)


class ProcessFlowDiagram(Flowable):
    def __init__(self, title: str, nodes: list[dict[str, Any]]):
        super().__init__()
        self.title = title
        self.nodes = nodes[:6]
        self.height = 210

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)
        count = max(len(self.nodes), 1)
        gap = 20
        box_w = min(108, (w - gap * (count - 1)) / count)
        total_w = box_w * count + gap * (count - 1)
        x0 = (w - total_w) / 2
        y = 45
        for index, node in enumerate(self.nodes):
            x = x0 + index * (box_w + gap)
            c.setFillColor(LIGHT)
            c.setStrokeColor(NAVY)
            c.roundRect(x, y, box_w, 96, 5, stroke=1, fill=1)
            c.setFillColor(ORANGE)
            c.setFont(FONT_BOLD, 9)
            c.drawString(x + 9, y + 75, str(index + 1))
            c.setFillColor(NAVY)
            c.setFont(FONT_BOLD, 8.5)
            title_lines = wrap_lines(str(node.get("title", "")), FONT_BOLD, 8.5, box_w - 20)
            if len(title_lines) > 3:
                raise ValueError(f"Process-flow title does not fit in three visible lines: {node.get('title', '')}")
            for line_index, line in enumerate(title_lines):
                c.drawString(x + 9, y + 59 - line_index * 10, line)
            c.setFillColor(INK)
            c.setFont(FONT_REGULAR, 7.2)
            detail_lines = wrap_lines(str(node.get("detail", "")), FONT_REGULAR, 7.2, box_w - 20)
            if len(detail_lines) > 4:
                raise ValueError(f"Process-flow detail does not fit in four visible lines: {node.get('detail', '')}")
            for line_index, line in enumerate(detail_lines):
                c.drawString(x + 9, y + 30 - line_index * 9, line)
            if index < count - 1:
                start = x + box_w + 3
                end = x + box_w + gap - 3
                mid_y = y + 48
                c.setStrokeColor(ORANGE)
                c.setFillColor(ORANGE)
                c.setLineWidth(1.8)
                c.line(start, mid_y, end, mid_y)
                path = c.beginPath()
                path.moveTo(end, mid_y)
                path.lineTo(end - 5, mid_y + 3)
                path.lineTo(end - 5, mid_y - 3)
                path.close()
                c.drawPath(path, stroke=0, fill=1)


class RelationshipMapDiagram(Flowable):
    def __init__(self, title: str, nodes: list[dict[str, Any]]):
        super().__init__()
        self.title = title
        self.nodes = nodes[:6]
        self.height = 230

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        import math
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)
        center_x, center_y = w / 2, 95
        center = self.nodes[0] if self.nodes else {"title": "Coordination", "detail": ""}
        satellites = self.nodes[1:] or [{"title": "Project team", "detail": ""}]
        positions = []
        radius_x, radius_y = min(210, w * 0.34), 58
        for index, node in enumerate(satellites):
            angle = 2 * math.pi * index / len(satellites)
            positions.append((center_x + radius_x * math.cos(angle), center_y + radius_y * math.sin(angle), node))
        c.setStrokeColor(LINE)
        c.setLineWidth(1.2)
        for x, y, _ in positions:
            c.line(center_x, center_y, x, y)
        c.setFillColor(NAVY)
        c.roundRect(center_x - 62, center_y - 24, 124, 48, 18, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FONT_BOLD, 9)
        for line_index, line in enumerate(wrap_lines(str(center.get("title", "")), FONT_BOLD, 9, 105)[:2]):
            c.drawCentredString(center_x, center_y + 7 - line_index * 11, line)
        for x, y, node in positions:
            c.setFillColor(LIGHT)
            c.setStrokeColor(ORANGE)
            c.roundRect(x - 52, y - 20, 104, 40, 5, stroke=1, fill=1)
            c.setFillColor(NAVY)
            c.setFont(FONT_BOLD, 7.8)
            for line_index, line in enumerate(wrap_lines(str(node.get("title", "")), FONT_BOLD, 7.8, 90)[:2]):
                c.drawCentredString(x, y + 5 - line_index * 9, line)


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
        draw_visual_title(c, self.title, w, self.height)
        c.setFont(FONT_BOLD, 10)
        c.drawString(0, 184, "Weak timeline")
        c.setStrokeColor(LINE)
        c.setLineWidth(1.5)
        c.line(110, 189, w - 20, 189)
        c.setFillColor(ORANGE)
        c.circle(120, 189, 4, fill=1, stroke=0)
        c.circle(w - 25, 189, 4, fill=1, stroke=0)
        c.setFillColor(MUTED)
        c.setFont(FONT_ITALIC, 8.2)
        c.drawCentredString(w / 2 + 45, 168, "Shows dates, but not enough logic to manage the work.")
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 10)
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
            c.setFont(FONT_BOLD, 8.6)
            c.drawCentredString(x + (bw - 8) / 2, 120, title)
            c.setFillColor(INK)
            c.setFont(FONT_REGULAR, 7.8)
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
        self.height = 285

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw_cell_text(self, x: float, y: float, width: float, text: str, *, bold: bool = False):
        c = self.canv
        font = FONT_BOLD if bold else FONT_REGULAR
        size = 8.4 if bold else 8.2
        c.setFont(font, size)
        c.setFillColor(NAVY if bold else INK)
        lines = wrap_lines(text, font, size, width - 18)
        if len(lines) > 3:
            raise ValueError(f"Comparison-matrix cell does not fit in three visible lines: {text}")
        for index, line in enumerate(lines):
            c.drawString(x + 9, y - 13 - index * 10, line)

    def draw(self):
        c = self.canv
        w = self.width
        title_lines = draw_visual_title(c, self.title, w, self.height)

        table_x = 24
        table_y = self.height - 52 - (12 if title_lines > 1 else 0)
        table_w = w - 48
        left_w = table_w * 0.42
        right_w = table_w - left_w
        header_h = 28
        row_h = 38

        c.setFillColor(NAVY)
        c.roundRect(table_x, table_y - header_h, table_w, header_h, 6, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FONT_BOLD, 8.7)
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
        c.setFont(FONT_BOLD, 7.8)
        for index, line in enumerate(wrap_lines(title, FONT_BOLD, 7.8, w - 10)[:2]):
            c.drawCentredString(x + w / 2, y + 27 - index * 9, line)
        c.setFillColor(INK)
        c.setFont(FONT_REGULAR, 7.1)
        c.drawCentredString(x + w / 2, y + 7, days)

    def draw(self):
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)

        start_x = 20
        finish_x = w - 68
        node_w = 60
        lane_gap = 80
        top_y = 142
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 8.4)
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
            c.setFont(FONT_BOLD, 8.6)
            c.drawString(0, y - 26, str(path_data.get("label", "")))


def p(text: str, style: str = "BodyGreg"):
    return Paragraph(inline(text), styles[style])


class BulletDot(Flowable):
    """A vector marker that never depends on a PDF viewer's font glyphs."""
    def __init__(self):
        super().__init__()
        self.width = 12
        self.height = 12

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        self.canv.setFillColor(ORANGE)
        self.canv.circle(5.5, 6, 1.7, stroke=0, fill=1)


def bullets(items: list[str], style: str = "BodyGreg"):
    rows = [[BulletDot(), Paragraph(inline(item), styles[style])] for item in items]
    table = Table(rows, colWidths=[14, 6.36 * inch], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


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
        if line.startswith("```"):
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                index += 1
            if index < len(lines):
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
        if line.startswith("### "):
            blocks.append({"type": "paragraph", "text": f"**{line[4:].strip()}**"})
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
            first_line = quote_lines[0] if quote_lines else ""
            known_label = re.match(
                r"^(?:\*\*)?(KEY TERM|APPLY IT|HANDS-ON EXAMPLE|SCENARIO|CALLBACK|BRIDGE)(?:\*\*)?\s*:\s*(.*)$|^\*\*(KEY TERM|APPLY IT|HANDS-ON EXAMPLE|SCENARIO|CALLBACK|BRIDGE)\*\*$",
                first_line,
                flags=re.IGNORECASE,
            )
            if known_label:
                label = (known_label.group(1) or known_label.group(3)).strip().upper()
                body = " ".join([known_label.group(2).strip() if known_label.group(2) else "", *quote_lines[1:]]).strip()
                body = re.sub(r"\*\*", "", body).strip()
            else:
                blocks.append({"type": "paragraph", "text": " ".join(re.sub(r"^\*\*|\*\*$", "", item) for item in quote_lines)})
                continue
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
        footer_width = letter[0] - doc.rightMargin - (doc.leftMargin + 22) - 24
        footer_text, footer_size = fit_single_line(course, FONT_REGULAR, footer_width, (8.5, 8, 7.5, 7))
        canvas.setFont(FONT_REGULAR, footer_size)
        canvas.drawString(doc.leftMargin + 22, y - 2, footer_text)
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
        canvas.setFont(FONT_BOLD, 14)
        canvas.drawString(1.75 * inch, H - 2.05 * inch, "STUDY GUIDE")
        if icon.exists():
            canvas.drawImage(str(icon), W - 2.12 * inch, H - 2.1 * inch, width=0.48 * inch, height=0.48 * inch, mask="auto")
        canvas.setFillColor(NAVY)
        title_lines, title_font = fit_cover_title(course, W - 3.5 * inch)
        canvas.setFont(FONT_BOLD, title_font)
        text = canvas.beginText(1.75 * inch, H - 3.1 * inch)
        text.setLeading(title_font + 4)
        for line in title_lines:
            text.textLine(line)
        canvas.drawText(text)
        canvas.setStrokeColor(ORANGE)
        canvas.setLineWidth(5)
        canvas.line(1.75 * inch, H - 4.58 * inch, W - 2.4 * inch, H - 4.58 * inch)
        canvas.setFillColor(colors.HexColor("#111827"))
        lesson_font = 16
        lesson_lines = wrap_lines(metadata["lesson_short_title"], FONT_BOLD, lesson_font, W - 3.5 * inch)[:3]
        lesson_text = canvas.beginText(1.75 * inch, H - 5.18 * inch)
        lesson_text.setFont(FONT_BOLD, lesson_font)
        lesson_text.setLeading(19)
        for line in lesson_lines:
            lesson_text.textLine(line)
        canvas.drawText(lesson_text)
        canvas.setFillColor(ORANGE)
        canvas.setFont(FONT_BOLD, 15)
        canvas.drawString(1.75 * inch, H - 6.25 * inch, f"Lesson {metadata['lesson_number']}")
        canvas.setFillColor(colors.HexColor("#4b5563"))
        canvas.setFont(FONT_REGULAR, 12)
        canvas.drawString(1.75 * inch, H - 6.55 * inch, metadata.get("level_label", "Basic Level"))
        if metadata.get("quote"):
            quote_lines, quote_size = fit_two_lines(metadata["quote"], FONT_BOLD, W - 3.5 * inch, (13, 12, 11))
            canvas.setFillColor(NAVY)
            quote_text = canvas.beginText(1.75 * inch, 2.20 * inch)
            quote_text.setFont(FONT_BOLD, quote_size)
            quote_text.setLeading(quote_size + 3)
            for line in quote_lines:
                quote_text.textLine(line)
            canvas.drawText(quote_text)
            canvas.setFont(FONT_REGULAR, 10)
            canvas.drawString(1.75 * inch, 1.64 * inch, metadata.get('quote_author', ''))
        canvas.setFillColor(colors.HexColor("#4b5563"))
        canvas.setFont(FONT_REGULAR, 9)
        canvas.drawString(1.75 * inch, 1.48 * inch, "BuildStak Learning Series")
        canvas.restoreState()

    doc = BaseDocTemplate(str(output), pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.72 * inch, bottomMargin=0.76 * inch)
    frame = Frame(doc.leftMargin, doc.bottomMargin + 0.15 * inch, doc.width, doc.height - 0.05 * inch, id="normal")
    doc.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=cover), PageTemplate(id="normal", frames=[frame], onPage=footer)])
    return doc


def visual_flowables(visual: dict[str, Any]) -> list[Any]:
    diagram_type = visual.get("type")
    if diagram_type == "image":
        path = resolve_path(str(visual.get("path") or ""))
        if not path.is_file():
            raise ValueError(f"Visual image does not exist: {path}")
        flowable = Image(str(path))
        max_width = min(float(visual.get("max_width", 6.2)) * inch, 6.9 * inch)
        max_height = min(float(visual.get("max_height", 3.7)) * inch, 4.2 * inch)
        scale = min(max_width / flowable.imageWidth, max_height / flowable.imageHeight, 1.0)
        flowable.drawWidth = flowable.imageWidth * scale
        flowable.drawHeight = flowable.imageHeight * scale
        flowable.hAlign = "CENTER"
    elif diagram_type == "card_row":
        flowable = CardRowDiagram(visual["title"], visual["cards"], visual.get("pill"))
    elif diagram_type == "timeline":
        flowable = TimelineDiagram(visual["title"])
    elif diagram_type == "source_to_wbs_matrix":
        flowable = SourceToWBSMatrix(visual["title"], visual["left_header"], visual["right_header"], visual["rows"])
    elif diagram_type == "process_flow":
        flowable = ProcessFlowDiagram(visual["title"], visual["nodes"])
    elif diagram_type == "relationship_map":
        flowable = RelationshipMapDiagram(visual["title"], visual["nodes"])
    elif diagram_type == "cpm_network":
        flowable = CPMNetworkDiagram(visual["title"], visual["paths"])
    else:
        raise ValueError(f"Unknown visual type: {diagram_type}")
    result = [flowable]
    if visual.get("caption"):
        result.append(Paragraph(inline(visual["caption"]), styles["Caption"]))
    return [KeepTogether(result)]


_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def validate_visuals(visuals: list[dict[str, Any]]) -> None:
    """Reject diagrams whose stated content cannot be rendered completely."""
    for visual in visuals:
        visual_type = visual.get("type")
        if visual_type in {"process_flow", "relationship_map"}:
            nodes = visual.get("nodes")
            if not isinstance(nodes, list) or not 2 <= len(nodes) <= 6:
                raise ValueError(f"{visual_type} diagram must contain 2-6 visible nodes.")
            if visual_type == "process_flow":
                for node in nodes:
                    if len(str(node.get("title") or "")) > 30 or len(str(node.get("detail") or "")) > 36:
                        raise ValueError("Process-flow title/detail exceeds the visible 30/36 character limit.")
        if visual_type == "source_to_wbs_matrix":
            rows = visual.get("rows")
            if not isinstance(rows, list) or not 2 <= len(rows) <= 5:
                raise ValueError("Comparison-matrix diagram must contain 2-5 visible rows.")
            for row in rows:
                if len(str(row.get("left") or "")) > 40 or len(str(row.get("right") or "")) > 130:
                    raise ValueError("Comparison-matrix cell exceeds the visible 40/130 character limit.")
        if visual_type != "card_row":
            continue
        cards = visual.get("cards")
        if not isinstance(cards, list) or not 2 <= len(cards) <= 8:
            raise ValueError("Card-row diagram must contain 2-8 visible cards.")
        title = str(visual.get("title", "")).lower()
        declarations: list[tuple[int, int]] = []
        for word, value in _COUNT_WORDS.items():
            match = re.search(rf"\b{word}\b", title)
            if match:
                declarations.append((match.start(), value))
        digit = re.search(r"\b(\d{1,2})\b", title)
        if digit:
            declarations.append((digit.start(), int(digit.group(1))))
        declared = min(declarations)[1] if declarations else None
        if declared is not None and declared != len(cards):
            raise ValueError(
                f"Card-row title declares {declared} items but contains {len(cards)} cards: {visual.get('title', '')}"
            )


def add_page_break(story: list[Any]) -> None:
    if not story or not isinstance(story[-1], PageBreak):
        story.append(PageBreak())


def normalized_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def starts_structural_page(heading: str) -> bool:
    normalized = normalized_heading(heading)
    if normalized in {"introduction", "summary and key takeaways", "glossary", "references"}:
        return True
    return bool(re.match(r"section\s+01\s+-\s+", heading, flags=re.IGNORECASE))


def visual_matches_heading(visual_heading: str, rendered_heading: str) -> bool:
    expected = normalized_heading(visual_heading)
    actual = normalized_heading(rendered_heading)
    return actual == expected or actual.startswith(f"{expected} -")


def build_story(blocks: list[dict[str, Any]], visuals: list[dict[str, Any]]) -> list[Any]:
    story: list[Any] = [Spacer(1, 1), NextPageTemplate("normal"), PageBreak()]
    visual_after_heading = [item for item in visuals if item.get("after_heading")]
    content_blocks = front_matter_blocks(blocks)
    current_heading = ""
    inserted_visuals: set[int] = set()
    for block in content_blocks:
        block_type = block["type"]
        if block_type == "page_break":
            add_page_break(story)
        elif block_type == "h1":
            current_heading = block["text"]
            if starts_structural_page(current_heading):
                add_page_break(story)
            match = re.match(r"Section\s+(\d{2})\s+-\s+(.+)", block["text"], flags=re.IGNORECASE)
            if match:
                spacer = Spacer(1, 2)
                spacer.keepWithNext = 1
                story.extend([SectionHeader(int(match.group(1)), match.group(2)), spacer])
            else:
                story.append(Paragraph(inline(block["text"]), styles["H1Greg"]))
        elif block_type == "h2":
            current_heading = block["text"]
            if normalized_heading(current_heading) == "introduction":
                add_page_break(story)
            story.append(Paragraph(inline(block["text"]), styles["H2Keep"]))
        elif block_type == "bullets":
            style = "RefGreg" if current_heading == "References" else "BodyGreg"
            story.append(bullets(block["items"], style=style))
        elif block_type == "callout":
            story.append(Callout(block["label"], block["body"]).flowable())
        elif block_type == "paragraph":
            paragraph = p(block["text"], "IntroBody" if len(story) < 20 else "BodyGreg")
            # Do not begin a fresh page with a short tail of the preceding
            # paragraph.  ReportLab will still split a paragraph that is taller
            # than a full page, but ordinary teaching paragraphs stay intact.
            story.append(KeepTogether([paragraph]))
            for index, visual in enumerate(visual_after_heading):
                if index not in inserted_visuals and visual_matches_heading(str(visual["after_heading"]), current_heading):
                    story.extend(visual_flowables(visual))
                    inserted_visuals.add(index)
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
    validate_render_source(markdown)
    validate_visuals(spec.get("visuals", []))
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
