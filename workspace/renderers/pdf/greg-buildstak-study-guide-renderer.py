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
REQUEST_RED = colors.HexColor("#B91C1C")
REQUEST_PALE = colors.HexColor("#FEF2F2")

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
styles.add(ParagraphStyle(name="CalloutBodySpaced", parent=styles["CalloutBody"], spaceAfter=5))
styles.add(ParagraphStyle(name="CalloutBullet", parent=styles["CalloutBody"], fontSize=9.1, leading=12, leftIndent=0, spaceAfter=1))
styles.add(ParagraphStyle(name="BridgeLabel", parent=styles["CalloutLabel"], fontSize=9, leading=10))
styles.add(ParagraphStyle(name="BridgeBody", parent=styles["CalloutBody"], fontSize=8.5, leading=10.5))
styles.add(ParagraphStyle(name="BridgeLead", parent=styles["BodyGreg"], fontSize=9.2, leading=12, textColor=MUTED, spaceAfter=10))
styles.add(ParagraphStyle(name="Caption", parent=styles["BodyGreg"], fontSize=8.6, leading=11, textColor=MUTED, alignment=TA_CENTER, spaceBefore=4, spaceAfter=10))
styles.add(ParagraphStyle(name="TableHeader", parent=styles["BodyGreg"], fontName=FONT_BOLD, textColor=colors.white, spaceAfter=0))
styles.add(ParagraphStyle(name="TableAtomic", parent=styles["BodyGreg"], splitLongWords=0))
styles.add(ParagraphStyle(name="ImageRequest", parent=styles["BodyGreg"], fontSize=9.2, leading=12.5, textColor=REQUEST_RED, spaceAfter=0))


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    root_resolved = ROOT.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path escapes Prof Greg workspace: {value}")
    return resolved


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


LOCALE_LABELS = {
    "en": {"summary": "Summary and Key Takeaways", "references": "References", "introduction": "Introduction", "section": "Section", "callouts": ["KEY TERM", "APPLY IT", "HANDS-ON EXAMPLE", "SCENARIO", "CALLBACK", "BRIDGE"]},
    "pt_br": {"summary": "Resumo e Principais Conclusões", "references": "Referências", "introduction": "Introdução", "section": "Seção", "callouts": ["TERMO-CHAVE", "APLIQUE", "EXEMPLO PRÁTICO", "CENÁRIO", "RETOMADA", "PONTE"]},
    "es": {"summary": "Resumen y Conclusiones Clave", "references": "Referencias", "introduction": "Introducción", "section": "Sección", "callouts": ["TÉRMINO CLAVE", "APLICACIÓN", "EJEMPLO PRÁCTICO", "ESCENARIO", "RETOMAR", "PUENTE"]},
}


def locale_labels(locale: str) -> dict[str, Any]:
    return LOCALE_LABELS.get(locale, LOCALE_LABELS["en"])


def validate_render_source(markdown: str, locale: str = "en") -> None:
    """Keep direct renderer use from bypassing the summary and dash rules."""
    labels = locale_labels(locale)
    match = re.search(
        rf"(?ims)^#\s+{re.escape(labels['summary'])}\s*$\n(.*?)(?=^#\s+|\Z)",
        markdown,
    )
    if not match:
        raise ValueError("Study-guide source is missing Summary and Key Takeaways.")
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    bullets_only = all(re.match(r"^[-*+]\s+\S", line) for line in lines)
    if not bullets_only or not 4 <= len(lines) <= 6:
        raise ValueError("Summary and Key Takeaways must contain only 4 to 6 concise bullet points; PDF was not rendered.")
    teaching_text = re.split(rf"(?im)^#\s+{re.escape(labels['references'])}\s*$", markdown, maxsplit=1)[0]
    for line in teaching_text.splitlines():
        if re.match(rf"^#{{1,2}}\s+{re.escape(labels['section'])}\s+\d{{1,2}}\s*(?:-|:|–|—)\s+", line):
            continue
        if "—" in line or "–" in line or re.search(r"\s-{1,2}\s", line):
            raise ValueError("Dash punctuation found in study-guide source; PDF was not rendered.")


def inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    return escaped


def wrap_lines(text: str, font: str, size: int, max_width: float, *, break_long_words: bool = True) -> list[str]:
    words: list[str] = []
    for raw_word in text.split():
        if stringWidth(raw_word, font, size) <= max_width or not break_long_words:
            words.append(raw_word)
            continue
        # A narrow process box can be smaller than a legitimate compound word
        # such as "Pre-Construction". Split first at hyphens, then at the
        # character boundary as a last resort. No rendered line may exceed its
        # declared box merely because the token itself is long.
        # Process-flow labels commonly use a slash to join two short concepts
        # (for example, "Lead/Viabilidade").  Treat it as an approved visible
        # break point so a translated label stays inside its node instead of
        # running through the arrow between nodes.
        pieces = re.findall(r"[^-/]+[-/]?", raw_word) or [raw_word]
        for piece in pieces:
            pending = piece
            while pending and stringWidth(pending, font, size) > max_width:
                cut = 1
                while cut < len(pending) and stringWidth(pending[: cut + 1], font, size) <= max_width:
                    cut += 1
                words.append(pending[:cut])
                pending = pending[cut:]
            if pending:
                words.append(pending)
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
    def __init__(self, number: int, title: str, label: str = "Section"):
        super().__init__()
        self.number = number
        self.title = title
        self.label = label
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
        heading = f"{self.label} {self.number:02d} - {self.title}"
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
        # A bridge commonly closes the last teaching section immediately
        # before the mandatory Summary page. Keep it with the preceding prose
        # using a compact, still legible treatment instead of stranding it on
        # a nearly empty page of its own.
        compact_bridge = self.label.upper() in {"BRIDGE", "PONTE", "PUENTE"}
        label_style = styles["BridgeLabel"] if compact_bridge else styles["CalloutLabel"]
        body_flowables = callout_body_flowables(self.body, compact=compact_bridge)
        rows = [
            [Paragraph(self.label, label_style) if index == 0 else "", flowable]
            for index, flowable in enumerate(body_flowables)
        ]
        table = Table(
            rows,
            colWidths=[1.2 * inch, 5.25 * inch] if compact_bridge else [1.6 * inch, 4.85 * inch],
            hAlign="LEFT",
            splitByRow=1,
        )
        padding = 4 if compact_bridge else 10
        table_style = [
            ("BOX", (0, 0), (-1, -1), 1.1, border),
            ("BACKGROUND", (0, 0), (-1, -1), fill),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5 if compact_bridge else 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5 if compact_bridge else 12),
        ]
        for row_index in range(len(rows)):
            table_style.extend([
                ("TOPPADDING", (0, row_index), (-1, row_index), padding if row_index == 0 else 0),
                ("BOTTOMPADDING", (0, row_index), (-1, row_index), padding if row_index == len(rows) - 1 else (1 if compact_bridge else 2)),
            ])
        table.setStyle(TableStyle(table_style))
        return KeepTogether([Spacer(1, 3 if compact_bridge else 7), table, Spacer(1, 3 if compact_bridge else 9)])


def structured_callout_blocks(body: str) -> list[dict[str, Any]]:
    """Preserve author formatting and repair common long-callout walls of text."""
    normalized = body.replace("\r\n", "\n").strip()
    # Repeated labeled cases are learner inputs, not prose. Older correction
    # runs often returned them on separate source lines, but the renderer then
    # flattened those lines. Also recover a legacy single-line Record A/B/C/D
    # wall deterministically so an unchanged draft still renders readably.
    record_matches = list(re.finditer(r"(?<!\w)(Record\s+[A-Z0-9]+)\s*:\s*", normalized, flags=re.I))
    has_explicit_bullets = bool(re.search(r"(?m)^[-*+]\s+\S", normalized))
    if len(record_matches) >= 3 and not has_explicit_bullets:
        first = record_matches[0].start()
        final_start = record_matches[-1].start()
        tail_match = re.search(r"\s+(?=(?:Classify|Decide|Determine|Check)\b)", normalized[final_start:], flags=re.I)
        records_end = final_start + tail_match.start() if tail_match else len(normalized)
        blocks: list[dict[str, Any]] = []
        if normalized[:first].strip():
            blocks.append({"type": "paragraph", "text": normalized[:first].strip()})
        items: list[str] = []
        for index, match in enumerate(record_matches):
            if match.start() >= records_end:
                break
            end = record_matches[index + 1].start() if index + 1 < len(record_matches) else records_end
            end = min(end, records_end)
            text = normalized[match.start():end].strip()
            text = re.sub(r"^(Record\s+[A-Z0-9]+\s*:)", r"**\1**", text, count=1, flags=re.I)
            items.append(text)
        if items:
            blocks.append({"type": "bullets", "items": items})
        tail = normalized[records_end:].strip()
        if tail:
            check = re.search(r"\bCheck\s*:\s*", tail, flags=re.I)
            if check and check.start() > 0:
                blocks.append({"type": "paragraph", "text": tail[:check.start()].strip()})
                blocks.append({"type": "paragraph", "text": "**Check:** " + tail[check.end():].strip()})
            else:
                blocks.append({"type": "paragraph", "text": tail})
        return blocks

    # A long legacy callout with no author structure still needs a readable
    # rhythm. Group complete sentences into short paragraphs without changing
    # or summarizing the student's content. Explicit formatting above always
    # takes precedence over this fallback.
    if not has_explicit_bullets and "\n\n" not in normalized and len(normalized) > 520:
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", normalized) if item.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > 300:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
        if len(chunks) >= 2:
            return [{"type": "paragraph", "text": chunk} for chunk in chunks]

    blocks = []
    paragraphs = re.split(r"\n\s*\n", normalized)
    for paragraph in paragraphs:
        source_lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        index = 0
        prose: list[str] = []
        while index < len(source_lines):
            if re.match(r"^[-*+]\s+\S", source_lines[index]):
                if prose:
                    blocks.append({"type": "paragraph", "text": " ".join(prose)})
                    prose = []
                items: list[str] = []
                while index < len(source_lines) and re.match(r"^[-*+]\s+\S", source_lines[index]):
                    item = re.sub(r"^[-*+]\s+", "", source_lines[index]).strip()
                    item = re.sub(r"^(Record\s+[A-Z0-9]+\s*:)", r"**\1**", item, count=1, flags=re.I)
                    items.append(item)
                    index += 1
                blocks.append({"type": "bullets", "items": items})
                continue
            prose.append(source_lines[index])
            index += 1
        if prose:
            blocks.append({"type": "paragraph", "text": " ".join(prose)})
    return blocks or [{"type": "paragraph", "text": normalized}]


def callout_body_flowables(body: str, *, compact: bool = False) -> list[Any]:
    paragraph_style = styles["BridgeBody"] if compact else styles["CalloutBodySpaced"]
    result: list[Any] = []
    for block in structured_callout_blocks(body):
        if block["type"] == "bullets":
            result.append(ListFlowable(
                [ListItem(Paragraph(inline(item), styles["BridgeBody"] if compact else styles["CalloutBullet"])) for item in block["items"]],
                bulletType="bullet",
                start="•",
                leftIndent=14,
                bulletFontName=FONT_REGULAR,
                bulletFontSize=5.5,
                spaceBefore=1,
                spaceAfter=4 if not compact else 1,
            ))
        else:
            result.append(Paragraph(inline(block["text"]), paragraph_style))
    return result


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


class CostStackDiagram(Flowable):
    """A literal vertical stack for layered cost and price calculations."""
    def __init__(self, title: str, layers: list[dict[str, Any]], total: str = ""):
        super().__init__()
        self.title = title
        self.layers = layers[:8]
        self.total = total
        self.height = 330

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)
        count = max(len(self.layers), 1)
        layer_h = min(42, 225 / count)
        start_y = 38
        if self.total:
            total_x = w * .10
            total_w = w * .80
            total_lines = []
            total_size = 9.0
            for candidate in (9.0, 8.5, 8.0, 7.5):
                candidate_lines = wrap_lines(self.total, FONT_BOLD, candidate, total_w - 20, break_long_words=False)
                if len(candidate_lines) <= 2 and all(
                    stringWidth(line, FONT_BOLD, candidate) <= total_w - 20 for line in candidate_lines
                ):
                    total_lines = candidate_lines
                    total_size = candidate
                    break
            if not total_lines:
                raise ValueError("Cost-stack total does not fit inside its visible result box.")
            total_h = 22 + (len(total_lines) - 1) * (total_size + 2)
            total_y = 258 - (total_h - 24)
            c.setFillColor(PALE_ORANGE)
            c.setStrokeColor(ORANGE)
            c.roundRect(total_x, total_y, total_w, total_h, 5, stroke=1, fill=1)
            c.setFillColor(NAVY)
            c.setFont(FONT_BOLD, total_size)
            first_baseline = total_y + total_h / 2 + (len(total_lines) - 1) * (total_size + 2) / 2 - 3
            for line_index, line in enumerate(total_lines):
                c.drawCentredString(w / 2, first_baseline - line_index * (total_size + 2), line)
        for index, layer in enumerate(self.layers):
            inset = min(index * 13, 75)
            x = 44 + inset
            box_w = w - 88 - inset * 2
            y = start_y + index * layer_h
            c.setFillColor(PALE_ORANGE if index == count - 1 else LIGHT)
            c.setStrokeColor(ORANGE if index == count - 1 else LINE)
            c.roundRect(x, y, box_w, layer_h - 4, 5, stroke=1, fill=1)
            title = str(layer.get("title") or "")
            detail = str(layer.get("detail") or "")
            c.setFillColor(NAVY)
            c.setFont(FONT_BOLD, 8.5)
            c.drawString(x + 10, y + layer_h - 16, title[:58])
            if detail:
                c.setFillColor(colors.HexColor("#4b5563"))
                c.setFont(FONT_REGULAR, 7.4)
                c.drawString(x + 10, y + 8, detail[:72])


class ProcessFlowDiagram(Flowable):
    def __init__(self, title: str, nodes: list[dict[str, Any]]):
        super().__init__()
        self.title = title
        self.nodes = nodes[:6]
        self.height = 235

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)
        count = max(len(self.nodes), 1)
        # Six-stage flows need slightly wider cards than the original layout.
        # Ten points still leaves a clear arrow lane while preventing
        # legitimate labels such as "Procurement & Mobilization" from being
        # squeezed into unreadable fragments.
        gap = 10
        box_w = min(108, (w - gap * (count - 1)) / count)
        text_inset = 6 if count >= 6 else 9
        text_width = box_w - 2 * text_inset
        total_w = box_w * count + gap * (count - 1)
        x0 = (w - total_w) / 2
        y = 42
        box_h = 120
        for index, node in enumerate(self.nodes):
            x = x0 + index * (box_w + gap)
            c.setFillColor(LIGHT)
            c.setStrokeColor(NAVY)
            c.roundRect(x, y, box_w, box_h, 5, stroke=1, fill=1)
            c.setFillColor(ORANGE)
            c.setFont(FONT_BOLD, 9)
            c.drawString(x + text_inset, y + 98, str(index + 1))
            c.setFillColor(NAVY)
            title_size = 8.5
            title_text = str(node.get("title", ""))
            # Localized labels can contain an individual Portuguese or Spanish
            # word that is wider than its English counterpart.  Keep the
            # approved node structure and use the smallest still-readable
            # label size before rejecting the visual for overflow.
            for candidate in (8.5, 8.0, 7.5, 7.0, 6.5, 6.0):
                # A slash is a meaningful, safe break in compact localized
                # labels (for example, "Lead/Viabilidade").  Do not split
                # ordinary words merely to force them into a narrow node.
                title_lines = wrap_lines(re.sub(r"/(?=\S)", "/ ", title_text), FONT_BOLD, candidate, text_width, break_long_words=False)
                title_size = candidate
                if len(title_lines) <= 3 and all(stringWidth(line, FONT_BOLD, candidate) <= text_width for line in title_lines):
                    break
                # A compound may break after its visible hyphen, but ordinary
                # words must never be split at arbitrary character positions.
                title_lines = wrap_lines(
                    re.sub(r"-(?=\S)", "- ", title_text),
                    FONT_BOLD,
                    candidate,
                    text_width,
                    break_long_words=False,
                )
                if len(title_lines) <= 3 and all(stringWidth(line, FONT_BOLD, candidate) <= text_width for line in title_lines):
                    break
            if len(title_lines) > 3 or any(stringWidth(line, FONT_BOLD, title_size) > text_width for line in title_lines):
                raise ValueError(f"Process-flow title does not fit in three visible lines: {node.get('title', '')}")
            c.setFont(FONT_BOLD, title_size)
            title_gap = title_size + 1.5
            title_top = y + 80
            for line_index, line in enumerate(title_lines):
                c.drawString(x + text_inset, title_top - line_index * title_gap, line)
            c.setFillColor(INK)
            detail_lines: list[str] = []
            detail_size = 7.2
            detail_top = title_top - (len(title_lines) - 1) * title_gap - 15
            for candidate in (7.2, 6.8, 6.4):
                candidate_lines = wrap_lines(
                    str(node.get("detail", "")), FONT_REGULAR, candidate, text_width, break_long_words=False
                )
                candidate_gap = candidate + 1.8
                last_baseline = detail_top - max(0, len(candidate_lines) - 1) * candidate_gap
                if len(candidate_lines) <= 4 and last_baseline >= y + 10 and all(
                    stringWidth(line, FONT_REGULAR, candidate) <= text_width for line in candidate_lines
                ):
                    detail_lines = candidate_lines
                    detail_size = candidate
                    break
            if not detail_lines and str(node.get("detail", "")).strip():
                raise ValueError(f"Process-flow detail does not fit in four visible lines: {node.get('detail', '')}")
            c.setFont(FONT_REGULAR, detail_size)
            detail_gap = detail_size + 1.8
            for line_index, line in enumerate(detail_lines):
                c.drawString(x + text_inset, detail_top - line_index * detail_gap, line)
            if index < count - 1:
                start = x + box_w + 3
                end = x + box_w + gap - 3
                mid_y = y + box_h / 2
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
        # The central concept is often a translated asset or scope label.
        # Give it three lines rather than silently dropping the final words.
        c.roundRect(center_x - 70, center_y - 31, 140, 62, 18, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FONT_BOLD, 8.2)
        for line_index, line in enumerate(wrap_lines(str(center.get("title", "")), FONT_BOLD, 8.2, 122)[:3]):
            c.drawCentredString(center_x, center_y + 10 - line_index * 10, line)
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
        self.height = 255

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw_cell_text(self, x: float, y: float, width: float, text: str, *, bold: bool = False):
        c = self.canv
        font = FONT_BOLD if bold else FONT_REGULAR
        size = 8.0 if bold else 7.8
        c.setFont(font, size)
        c.setFillColor(NAVY if bold else INK)
        lines = wrap_lines(text, font, size, width - 18)
        if len(lines) > 3:
            raise ValueError(f"Comparison-matrix cell does not fit in three visible lines: {text}")
        for index, line in enumerate(lines):
            c.drawString(x + 9, y - 11 - index * 9, line)

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
        row_h = 33

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


class ComparisonMatrixDiagram(Flowable):
    """A true comparison: one criterion column plus one column per entity."""
    def __init__(self, title: str, columns: list[str], rows: list[dict[str, Any]]):
        super().__init__()
        self.title = title
        self.columns = [str(column) for column in columns[:4]]
        self.rows = rows[:5]
        self.height = 310
        self._layout: tuple[list[float], list[list[list[str]]], list[float]] | None = None

    def _prepare(self, width: float):
        if not 3 <= len(self.columns) <= 4:
            raise ValueError("Comparison matrix requires one criterion column and 2-3 entity columns.")
        table_w = width - 32
        first_w = table_w * .30
        other_w = (table_w - first_w) / (len(self.columns) - 1)
        widths = [first_w] + [other_w] * (len(self.columns) - 1)
        for column, cell_w in zip(self.columns, widths):
            header_lines = wrap_lines(column, FONT_BOLD, 8.2, cell_w - 16, break_long_words=False)
            if len(header_lines) > 2 or any(
                stringWidth(line, FONT_BOLD, 8.2) > cell_w - 16 for line in header_lines
            ):
                raise ValueError(f"Comparison-matrix header does not fit in two visible lines: {column}")
        wrapped_rows: list[list[list[str]]] = []
        row_heights: list[float] = []
        for row in self.rows:
            cells = [str(cell) for cell in (row.get("cells") or [])]
            if len(cells) != len(self.columns):
                raise ValueError("Every comparison-matrix row must have one cell per visible column.")
            wrapped = []
            for index, (cell, cell_w) in enumerate(zip(cells, widths)):
                font = FONT_BOLD if index == 0 else FONT_REGULAR
                size = 7.6 if index == 0 else 7.3
                lines = wrap_lines(cell, font, size, cell_w - 16, break_long_words=False)
                if len(lines) > 4 or any(stringWidth(line, font, size) > cell_w - 16 for line in lines):
                    raise ValueError(f"Comparison-matrix cell does not fit in four visible lines: {cell}")
                wrapped.append(lines)
            wrapped_rows.append(wrapped)
            row_heights.append(max(34, 16 + 9 * max(len(lines) for lines in wrapped)))
        self._layout = (widths, wrapped_rows, row_heights)
        self.height = 58 + 30 + sum(row_heights)

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self._prepare(availWidth)
        return availWidth, self.height

    def draw(self):
        if self._layout is None:
            self._prepare(self.width)
        widths, wrapped_rows, row_heights = self._layout
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)
        table_x = 16
        table_w = sum(widths)
        table_top = self.height - 52
        header_h = 30

        c.setFillColor(NAVY)
        c.roundRect(table_x, table_top - header_h, table_w, header_h, 6, stroke=0, fill=1)
        x = table_x
        for column, cell_w in zip(self.columns, widths):
            c.setFillColor(colors.white)
            c.setFont(FONT_BOLD, 8.2)
            header_lines = wrap_lines(column, FONT_BOLD, 8.2, cell_w - 16, break_long_words=False)
            if len(header_lines) > 2:
                raise ValueError(f"Comparison-matrix header does not fit in two visible lines: {column}")
            for line_index, line in enumerate(header_lines):
                c.drawString(x + 8, table_top - 18 - line_index * 9, line)
            x += cell_w

        y_top = table_top - header_h
        for row_index, (wrapped, row_h) in enumerate(zip(wrapped_rows, row_heights)):
            c.setFillColor(LIGHT if row_index % 2 == 0 else colors.white)
            c.rect(table_x, y_top - row_h, table_w, row_h, stroke=0, fill=1)
            x = table_x
            for cell_index, (lines, cell_w) in enumerate(zip(wrapped, widths)):
                c.setFillColor(NAVY if cell_index == 0 else INK)
                c.setFont(FONT_BOLD if cell_index == 0 else FONT_REGULAR, 7.6 if cell_index == 0 else 7.3)
                for line_index, line in enumerate(lines):
                    c.drawString(x + 8, y_top - 13 - line_index * 9, line)
                x += cell_w
            c.setStrokeColor(LINE)
            c.line(table_x, y_top - row_h, table_x + table_w, y_top - row_h)
            y_top -= row_h

        c.setStrokeColor(LINE)
        c.setLineWidth(1)
        c.roundRect(table_x, y_top, table_w, table_top - y_top, 6, stroke=1, fill=0)
        x = table_x
        for cell_w in widths[:-1]:
            x += cell_w
            c.line(x, table_top, x, y_top)


class ScheduleBarChartDiagram(Flowable):
    """A real time-scaled activity view, not a table describing one."""
    def __init__(self, title: str, rows: list[dict[str, Any]]):
        super().__init__()
        self.title = title
        self.rows = rows[:8]
        self.height = 255

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        w = self.width
        draw_visual_title(c, self.title, w, self.height)
        label_w = min(132, w * 0.25)
        chart_x = label_w + 12
        chart_w = w - chart_x - 8
        maximum = max((int(row.get("start", 0)) + int(row.get("duration", 1)) for row in self.rows), default=1)
        row_h = min(25, 150 / max(len(self.rows), 1))
        top = 188
        c.setFont(FONT_REGULAR, 7.2)
        c.setFillColor(MUTED)
        for tick in range(maximum + 1):
            x = chart_x + chart_w * tick / maximum
            c.setStrokeColor(LINE)
            c.setLineWidth(0.55)
            c.line(x, top - row_h * len(self.rows), x, top + 10)
            c.drawCentredString(x, top + 14, str(tick))
        status_colors = {
            "complete": NAVY,
            "in-progress": ORANGE,
            "delayed": colors.HexColor("#B4452D"),
            "planned": colors.HexColor("#7B8797"),
        }
        for index, row in enumerate(self.rows):
            y = top - (index + 1) * row_h + 5
            activity = str(row.get("activity") or "")
            c.setFillColor(NAVY)
            c.setFont(FONT_BOLD, 7.8)
            label = wrap_lines(activity, FONT_BOLD, 7.8, label_w - 6)[:2]
            for line_index, line in enumerate(label):
                c.drawString(0, y + 5 - line_index * 8, line)
            start = int(row.get("start", 0))
            duration = int(row.get("duration", 1))
            x = chart_x + chart_w * start / maximum
            bar_w = max(5, chart_w * duration / maximum)
            c.setFillColor(status_colors.get(str(row.get("status") or "planned").lower(), status_colors["planned"]))
            c.roundRect(x, y, bar_w, 12, 3, stroke=0, fill=1)
        c.setFillColor(MUTED)
        c.setFont(FONT_ITALIC, 7.4)
        c.drawRightString(w, 12, "Time units")


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


def numbered_steps(items: list[tuple[str, str]], style: str = "BodyGreg"):
    """Render each ordered Markdown step as its own visible table row."""
    rows = [
        [Paragraph(inline(f"{number}."), styles[style]), Paragraph(inline(item), styles[style])]
        for number, item in items
    ]
    table = Table(rows, colWidths=[20, 6.28 * inch], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def markdown_table(headers: list[str], rows: list[list[str]]):
    """Render source Markdown tables as real, readable PDF tables."""
    columns = len(headers)
    if not columns or any(len(row) != columns for row in rows):
        raise ValueError("Markdown table has inconsistent column counts.")
    available = 6.5 * inch
    if columns == 4 and any("amount" in header.lower() for header in headers):
        # Estimate-control tables need a stable financial reading order:
        # item, basis, amount, inclusion. Content-length weighting makes the
        # amount column unreadably narrow and wastes the decision columns.
        widths = [available * ratio for ratio in (0.18, 0.30, 0.13, 0.39)]
    else:
        header_minimums = [stringWidth(re.sub(r"[*_`]+", "", header), FONT_BOLD, 7.5) + 12 for header in headers]
        numeric = re.compile(r"^\s*(?:[$€£]\s*)?[+-]?\d[\d.,]*(?:\s*(?:%|SF|LF|EA))?\s*$", flags=re.I)
        for column in range(columns):
            atomic_values = [re.sub(r"[*_`]+", "", row[column]).strip() for row in rows if numeric.fullmatch(re.sub(r"[*_`]+", "", row[column]).strip())]
            if atomic_values:
                header_minimums[column] = max(
                    header_minimums[column],
                    max(stringWidth(value, FONT_REGULAR, styles["BodyGreg"].fontSize) + 12 for value in atomic_values),
                )
        if sum(header_minimums) > available:
            raise ValueError("Table headers cannot all fit on one legible line; use shorter labels or a different table layout.")
        weights = [max(10, *(len(row[index]) for row in rows)) for index in range(columns)]
        remaining = available - sum(header_minimums)
        total = sum(weights)
        widths = [header_minimums[index] + remaining * weights[index] / total for index in range(columns)]
    def header_cell(text: str, width: float) -> Paragraph:
        usable_width = width - 12
        plain = re.sub(r"[*_`]+", "", text).strip()
        for size in (10.3, 9.5, 8.5, 7.5):
            if stringWidth(plain, FONT_BOLD, size) <= usable_width:
                style = ParagraphStyle(
                    name=f"TableHeader{size:g}", parent=styles["TableHeader"], fontSize=size, leading=size + 1.4
                )
                return Paragraph(inline(text), style)
        raise ValueError(
            f"Table header cannot fit on one legible line: {text}. Use a shorter label or a different table layout."
        )
    numeric = re.compile(r"^\s*(?:[$€£]\s*)?[+-]?\d[\d.,]*(?:\s*(?:%|SF|LF|EA))?\s*$", flags=re.I)
    data = [
        [header_cell(cell, widths[index]) for index, cell in enumerate(headers)],
        *[[Paragraph(inline(cell), styles["TableAtomic"] if numeric.fullmatch(re.sub(r"[*_`]+", "", cell).strip()) else styles["BodyGreg"]) for cell in row] for row in rows],
    ]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("BACKGROUND", (0, 1), (-1, -1), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def parse_markdown(markdown: str, locale: str = "en") -> list[dict[str, Any]]:
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
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[index + 1]):
            def cells(value: str) -> list[str]:
                return [cell.strip() for cell in value.strip().strip("|").split("|")]
            headers = cells(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = cells(lines[index])
                if len(row) != len(headers):
                    raise ValueError("Markdown table row does not match its header.")
                rows.append(row)
                index += 1
            if not rows:
                raise ValueError("Markdown table needs at least one data row.")
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue
        if re.match(r"^[-*+]\s+\S", line):
            items: list[str] = []
            while index < len(lines) and re.match(r"^[-*+]\s+\S", lines[index].strip()):
                items.append(re.sub(r"^[-*+]\s+", "", lines[index].strip()).strip())
                index += 1
            blocks.append({"type": "bullets", "items": items})
            continue
        if re.match(r"^\d+[.)]\s+\S", line):
            items: list[tuple[str, str]] = []
            while index < len(lines):
                match = re.match(r"^(\d+)[.)]\s+(\S.*)$", lines[index].strip())
                if not match:
                    break
                items.append((match.group(1), match.group(2).strip()))
                index += 1
            blocks.append({"type": "numbered", "items": items})
            continue
        if line.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                stripped = lines[index].strip()[1:].strip()
                quote_lines.append(stripped)
                index += 1
            first_line = quote_lines[0] if quote_lines else ""
            callout_names = "|".join(re.escape(value) for value in locale_labels(locale)["callouts"])
            known_label = re.match(
                rf"^(?:\*\*)?({callout_names})(?:\*\*)?\s*:\s*(.*)$|^\*\*({callout_names}):\*\*\s*(.*)$|^(?:\*\*)?({callout_names})(?:\*\*)?$",
                first_line,
                flags=re.IGNORECASE,
            )
            if known_label:
                label = (known_label.group(1) or known_label.group(3) or known_label.group(5)).strip().upper()
                inline_body = known_label.group(2) or known_label.group(4) or ""
                # Legacy inline labels sometimes wrap the label and first
                # sentence in one bold span. Remove only those unmatched
                # markers; preserve emphasis in the following body lines.
                inline_body = re.sub(r"\*\*", "", inline_body).strip()
                body_lines = [*([inline_body.strip()] if inline_body.strip() else []), *quote_lines[1:]]
                body = "\n".join(body_lines).strip()
            else:
                blocks.append({"type": "paragraph", "text": " ".join(re.sub(r"^\*\*|\*\*$", "", item) for item in quote_lines)})
                continue
            blocks.append({"type": "callout", "label": label, "body": body})
            continue
        paragraph: list[str] = [line]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if (
                not next_line
                or next_line == "---"
                or next_line.startswith(("# ", "## ", "- ", ">"))
                or re.match(r"^\d+[.)]\s+\S", next_line)
            ):
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
        canvas.drawString(1.75 * inch, H - 2.05 * inch, metadata.get("study_guide_label", "STUDY GUIDE"))
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
        canvas.drawString(1.75 * inch, H - 6.25 * inch, f"{metadata.get('lesson_label', 'Lesson')} {metadata['lesson_number']}")
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
    if diagram_type == "image_request":
        request_copy = (
            f"<b>IMAGE REQUIRED — {html.escape(str(visual.get('visual_id') or 'operator request'))}</b><br/>"
            f"<b>Description:</b> {html.escape(str(visual.get('image_description') or 'Required teaching image'))}<br/>"
            f"<b>Pedagogical reason:</b> {html.escape(str(visual.get('pedagogical_reason') or 'This image is required for the planned learning task.'))}<br/>"
            f"<b>Suggested search:</b> {html.escape(str(visual.get('search_phrase') or ''))}"
        )
        flowable = Table([[Paragraph(request_copy, styles["ImageRequest"])]], colWidths=[6.45 * inch], hAlign="CENTER")
        flowable.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 2.2, REQUEST_RED),
            ("BACKGROUND", (0, 0), (-1, -1), REQUEST_PALE),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]))
    elif diagram_type == "image":
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
    elif diagram_type == "cost_stack":
        flowable = CostStackDiagram(visual["title"], visual["nodes"], visual.get("total", ""))
    elif diagram_type == "timeline":
        flowable = TimelineDiagram(visual["title"])
    elif diagram_type == "source_to_wbs_matrix":
        flowable = SourceToWBSMatrix(visual["title"], visual["left_header"], visual["right_header"], visual["rows"])
    elif diagram_type == "comparison_matrix":
        flowable = ComparisonMatrixDiagram(visual["title"], visual["columns"], visual["rows"])
    elif diagram_type == "schedule_bar_chart":
        flowable = ScheduleBarChartDiagram(visual["title"], visual["rows"])
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


def validate_visual_text_fit(visuals: list[dict[str, Any]]) -> None:
    """Validate localized text against the renderer's physical text boxes."""
    for visual in visuals:
        visual_type = visual.get("type")
        if visual_type == "process_flow":
            nodes = visual.get("nodes") or []
            for node in nodes:
                if len(str(node.get("title") or "")) > 30 or len(str(node.get("detail") or "")) > 36:
                    raise ValueError("Process-flow title/detail exceeds the visible 30/36 character limit.")
            probe = ProcessFlowDiagram(str(visual.get("title") or ""), nodes)
            probe.width = 6.5 * inch
            class _FitCanvas:
                def setFillColor(self, *_): pass
                def setStrokeColor(self, *_): pass
                def setLineWidth(self, *_): pass
                def setFont(self, *_): pass
                def drawString(self, *_): pass
                def roundRect(self, *_, **__): pass
                def line(self, *_): pass
                def beginPath(self):
                    class _Path:
                        def moveTo(self, *_): pass
                        def lineTo(self, *_): pass
                        def close(self): pass
                    return _Path()
                def drawPath(self, *_, **__): pass
            probe.canv = _FitCanvas()
            probe.draw()
        if visual_type == "source_to_wbs_matrix":
            rows = visual.get("rows") or []
            for row in rows:
                if len(str(row.get("left") or "")) > 40 or len(str(row.get("right") or "")) > 130:
                    raise ValueError("Comparison-matrix cell exceeds the visible 40/130 character limit.")
            table_width = 6.5 * inch - 48
            left_width = table_width * 0.42
            right_width = table_width - left_width
            cells = [
                (str(visual.get("left_header") or ""), FONT_BOLD, 8.0, left_width),
                (str(visual.get("right_header") or ""), FONT_BOLD, 8.0, right_width),
            ]
            cells.extend(
                cell
                for row in rows
                for cell in (
                    (str(row.get("left") or ""), FONT_REGULAR, 7.8, left_width),
                    (str(row.get("right") or ""), FONT_REGULAR, 7.8, right_width),
                )
            )
            if any(len(wrap_lines(text, font, size, width - 18)) > 3 for text, font, size, width in cells):
                raise ValueError("Comparison-matrix cell does not fit in three visible lines.")
        if visual_type == "comparison_matrix":
            probe = ComparisonMatrixDiagram(
                str(visual.get("title") or ""),
                visual.get("columns") or [],
                visual.get("rows") or [],
            )
            probe._prepare(6.5 * inch)
        if visual_type == "cost_stack":
            total = str(visual.get("total") or "")
            if total:
                total_width = 6.5 * inch * .80 - 20
                fits = False
                for size in (9.0, 8.5, 8.0, 7.5):
                    lines = wrap_lines(total, FONT_BOLD, size, total_width, break_long_words=False)
                    if len(lines) <= 2 and all(stringWidth(line, FONT_BOLD, size) <= total_width for line in lines):
                        fits = True
                        break
                if not fits:
                    raise ValueError("Cost-stack total does not fit inside its visible result box.")
        if visual_type == "schedule_bar_chart":
            rows = visual.get("rows") or []
            if not 3 <= len(rows) <= 8:
                raise ValueError("schedule_bar_chart must contain 3-8 visible activity rows.")
            for row in rows:
                if not str(row.get("activity") or "").strip() or not isinstance(row.get("start"), int) or not isinstance(row.get("duration"), int) or row.get("start", -1) < 0 or row.get("duration", 0) <= 0:
                    raise ValueError("schedule_bar_chart rows require activity, nonnegative integer start, and positive integer duration.")


def validate_visuals(visuals: list[dict[str, Any]]) -> None:
    """Reject diagrams whose stated content cannot be rendered completely."""
    validate_visual_text_fit(visuals)
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
                # Run the exact renderer against the standard content width so
                # QA cannot approve title/detail combinations that only fit in
                # isolation but collide or leave the bottom of a box together.
                probe = ProcessFlowDiagram(str(visual.get("title") or ""), nodes)
                probe.width = 6.5 * inch
                class _FitCanvas:
                    def setFillColor(self, *_): pass
                    def setStrokeColor(self, *_): pass
                    def setLineWidth(self, *_): pass
                    def setFont(self, *_): pass
                    def drawString(self, *_): pass
                    def roundRect(self, *_, **__): pass
                    def line(self, *_): pass
                    def beginPath(self):
                        class _Path:
                            def moveTo(self, *_): pass
                            def lineTo(self, *_): pass
                            def close(self): pass
                        return _Path()
                    def drawPath(self, *_, **__): pass
                probe.canv = _FitCanvas()
                probe.draw()
            else:
                center = nodes[0]
                if len(wrap_lines(str(center.get("title") or ""), FONT_BOLD, 8.2, 122)) > 3:
                    raise ValueError("relationship-map central title exceeds the visible three-line limit.")
                for node in nodes[1:]:
                    if len(wrap_lines(str(node.get("title") or ""), FONT_BOLD, 7.8, 90)) > 2:
                        raise ValueError("relationship-map satellite title exceeds the visible two-line limit.")
        if visual_type == "source_to_wbs_matrix":
            rows = visual.get("rows")
            if not isinstance(rows, list) or not 2 <= len(rows) <= 5:
                raise ValueError("Comparison-matrix diagram must contain 2-5 visible rows.")
            for row in rows:
                if len(str(row.get("left") or "")) > 40 or len(str(row.get("right") or "")) > 130:
                    raise ValueError("Comparison-matrix cell exceeds the visible 40/130 character limit.")
            # Character counts are not enough for localized text: word widths
            # can still force a nominally valid cell onto a hidden fourth line.
            # Measure with the same fonts, sizes, and widths used by draw().
            table_width = 6.5 * inch - 48
            left_width = table_width * 0.42
            right_width = table_width - left_width
            cells = [
                (str(visual.get("left_header") or ""), FONT_BOLD, 8.0, left_width),
                (str(visual.get("right_header") or ""), FONT_BOLD, 8.0, right_width),
            ]
            cells.extend(
                cell
                for row in rows
                for cell in (
                    (str(row.get("left") or ""), FONT_REGULAR, 7.8, left_width),
                    (str(row.get("right") or ""), FONT_REGULAR, 7.8, right_width),
                )
            )
            if any(len(wrap_lines(text, font, size, width - 18)) > 3 for text, font, size, width in cells):
                raise ValueError("Comparison-matrix cell does not fit in three visible lines.")
        if visual_type == "comparison_matrix":
            columns = visual.get("columns")
            rows = visual.get("rows")
            if not isinstance(columns, list) or not 3 <= len(columns) <= 4:
                raise ValueError("Comparison matrix requires one criterion column and 2-3 entity columns.")
            if not isinstance(rows, list) or not 2 <= len(rows) <= 5:
                raise ValueError("Comparison matrix must contain 2-5 visible criterion rows.")
            ComparisonMatrixDiagram(str(visual.get("title") or ""), columns, rows)._prepare(6.5 * inch)
        if visual_type == "cost_stack":
            nodes = visual.get("nodes")
            if not isinstance(nodes, list) or not 2 <= len(nodes) <= 8:
                raise ValueError("cost_stack diagram must contain 2-8 visible layers.")
            if any(re.search(r"\b(proposal price|final total|total price)\b", str(node.get("title") or ""), re.I) for node in nodes):
                raise ValueError("cost_stack must show a proposal price as a separate calculated total, not a stack layer.")
            continue
        if visual_type != "card_row":
            continue
        cards = visual.get("cards")
        if not isinstance(cards, list) or not 2 <= len(cards) <= 8:
            raise ValueError("Card-row diagram must contain 2-8 visible cards.")
        title = str(visual.get("title", "")).lower()
        numbered_cards = sum(bool(re.match(r"^\s*\d+[.)]\s+", str(card.get("title") or ""))) for card in cards)
        sequential_title = bool(re.search(r"\b(step|steps|sequence|order|workflow|process|from .+ to .+)\b", title))
        if sequential_title or numbered_cards >= 2:
            raise ValueError("Card-row diagrams cannot represent ordered steps; use a process-flow with visible connectors.")
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


def starts_structural_page(heading: str, locale: str = "en") -> bool:
    normalized = normalized_heading(heading)
    labels = locale_labels(locale)
    glossary = "Glossário" if locale == "pt_br" else "Glosario" if locale == "es" else "Glossary"
    if normalized in {normalized_heading(labels["introduction"]), normalized_heading(labels["summary"]), normalized_heading(glossary), normalized_heading(labels["references"])}:
        return True
    return bool(re.match(rf"{re.escape(labels['section'])}\s+0?1\s*(?:-|:|–|—)\s+", heading, flags=re.IGNORECASE))


def visual_matches_heading(visual_heading: str, rendered_heading: str) -> bool:
    expected = normalized_heading(visual_heading)
    actual = normalized_heading(rendered_heading)
    return actual == expected or actual.startswith(f"{expected} -")


def build_story(blocks: list[dict[str, Any]], visuals: list[dict[str, Any]], locale: str = "en") -> list[Any]:
    story: list[Any] = [Spacer(1, 1), NextPageTemplate("normal"), PageBreak()]
    visual_after_heading = [item for item in visuals if item.get("after_heading")]
    content_blocks = front_matter_blocks(blocks)
    # A final Bridge immediately before a forced structural page (normally the
    # Summary) can never share the prior full page and otherwise creates an
    # unattractive near-empty page. Preserve its teaching text as a restrained
    # lead-in on the following structural page instead of stranding a box.
    bridge_labels = {"BRIDGE", "PONTE", "PUENTE"}
    for index, block in enumerate(content_blocks[:-1]):
        following = content_blocks[index + 1]
        if (
            block.get("type") == "callout"
            and str(block.get("label") or "").upper() in bridge_labels
            and following.get("type") == "h1"
            and starts_structural_page(str(following.get("text") or ""), locale)
        ):
            content_blocks[index] = {"type": "skip"}
            content_blocks[index + 1] = {**following, "bridge_lead": str(block.get("body") or "")}
    current_heading = ""
    inserted_visuals: set[int] = set()
    pending_section_header: list[Any] = []
    for block in content_blocks:
        block_type = block["type"]
        if block_type == "skip":
            continue
        if block_type == "page_break":
            add_page_break(story)
        elif block_type == "h1":
            current_heading = block["text"]
            if starts_structural_page(current_heading, locale):
                add_page_break(story)
            section_label = locale_labels(locale)["section"]
            match = re.match(rf"{re.escape(section_label)}\s+(\d{{1,2}})\s*(?:-|:|–|—)\s+(.+)", block["text"], flags=re.IGNORECASE)
            if match:
                spacer = Spacer(1, 2)
                spacer.keepWithNext = 1
                pending_section_header = [SectionHeader(int(match.group(1)), match.group(2), section_label), spacer]
            else:
                story.append(Paragraph(inline(block["text"]), styles["H1Greg"]))
                if block.get("bridge_lead"):
                    story.append(Paragraph(inline(str(block["bridge_lead"])), styles["BridgeLead"]))
        elif block_type == "h2":
            current_heading = block["text"]
            if normalized_heading(current_heading) == normalized_heading(locale_labels(locale)["introduction"]):
                add_page_break(story)
            story.append(Paragraph(inline(block["text"]), styles["H2Keep"]))
        elif block_type == "bullets":
            style = "RefGreg" if normalized_heading(current_heading) == normalized_heading(locale_labels(locale)["references"]) else "BodyGreg"
            story.append(bullets(block["items"], style=style))
        elif block_type == "numbered":
            story.append(numbered_steps(block["items"]))
        elif block_type == "table":
            if pending_section_header:
                story.extend(pending_section_header)
                pending_section_header = []
            story.append(KeepTogether([markdown_table(block["headers"], block["rows"])]))
            story.append(Spacer(1, 8))
        elif block_type == "callout":
            opening_headings = {"introduction", "learning objectives", "introdução", "objetivos de aprendizagem", "introducción", "objetivos de aprendizaje"}
            if normalized_heading(current_heading) in opening_headings:
                story.append(p(block["body"], "IntroBody"))
            else:
                story.append(Callout(block["label"], block["body"]).flowable())
        elif block_type == "paragraph":
            paragraph = p(block["text"], "IntroBody" if len(story) < 20 else "BodyGreg")
            # Do not begin a fresh page with a short tail of the preceding
            # paragraph.  ReportLab will still split a paragraph that is taller
            # than a full page, but ordinary teaching paragraphs stay intact.
            if pending_section_header:
                story.append(KeepTogether([*pending_section_header, paragraph]))
                pending_section_header = []
            else:
                story.append(KeepTogether([paragraph]))
            for index, visual in enumerate(visual_after_heading):
                if index not in inserted_visuals and visual_matches_heading(str(visual["after_heading"]), current_heading):
                    story.extend(visual_flowables(visual))
                    inserted_visuals.add(index)
    story.extend(pending_section_header)
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
    locale = str(spec.get("locale") or "en")
    run_folder = resolve_path(spec["run_folder"])
    markdown = resolve_path(spec["source_markdown"]).read_text(encoding="utf-8")
    validate_render_source(markdown, locale)
    validate_visuals(spec.get("visuals", []))
    output = run_folder / spec["output"]["pdf"]
    output.parent.mkdir(parents=True, exist_ok=True)
    blocks = parse_markdown(markdown, locale)
    doc = make_doc(output, spec["metadata"])
    doc.build(build_story(blocks, spec.get("visuals", []), locale))
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
