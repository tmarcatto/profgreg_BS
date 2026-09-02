#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    status: str
    check: str
    note: str


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "because",
    "by",
    "can",
    "does",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "lesson",
    "of",
    "on",
    "or",
    "pm",
    "project",
    "slide",
    "the",
    "this",
    "to",
    "when",
    "with",
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_ndjson(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"kind": "invalid", "raw": line})
    return rows


def latest_revision(deck_path: Path) -> tuple[str, int]:
    match = re.search(r"_r(\d+)\.pptx$", deck_path.name)
    if match:
        return match.group(0), int(match.group(1))
    return "", 0


def inspect_path_for(deck_path: Path) -> Path:
    return deck_path.with_suffix(deck_path.suffix + ".inspect.ndjson")


def lesson_number_from_name(path: Path) -> str | None:
    match = re.search(r"lesson_(\d+)_", path.name)
    if match:
        return f"{int(match.group(1)):02d}"
    return None


def rendered_slide_dir_for(deck_path: Path) -> Path | None:
    lesson = lesson_number_from_name(deck_path)
    if not lesson:
        return None
    revision_match = re.search(r"_r(\d+)\.pptx$", deck_path.name)
    candidates = []
    if revision_match:
        candidates.append(deck_path.parent / f"rendered_slides_lesson_{lesson}_r{int(revision_match.group(1)):02d}")
    candidates.append(deck_path.parent / f"rendered_slides_lesson_{lesson}")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    legacy = deck_path.parent / "rendered_slides"
    return legacy if legacy.exists() else None


def load_layout_elements(deck_path: Path) -> list[dict]:
    rendered_dir = rendered_slide_dir_for(deck_path)
    if not rendered_dir:
        return []
    elements: list[dict] = []
    for path in sorted(rendered_dir.glob("slide-*.layout.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slide = int(data.get("slide", {}).get("slide", 0) or 0)
        for element in data.get("elements", []):
            row = dict(element)
            row["slide"] = slide
            elements.append(row)
    return elements


def normalize_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", text.lower())
    tokens = {word.strip("'") for word in words if word not in STOPWORDS}
    stems = set()
    for token in tokens:
        for suffix in ("ing", "ed", "s"):
            if len(token) > 5 and token.endswith(suffix):
                token = token[: -len(suffix)]
                break
        stems.add(token)
    return stems


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def visible_text_by_slide(rows: list[dict]) -> dict[int, str]:
    ignored_names = {
        "eyebrow",
        "footer-course",
        "footer-number",
        "brand",
    }
    by_slide: dict[int, list[str]] = defaultdict(list)
    for row in rows:
        if row.get("kind") != "textbox":
            continue
        if row.get("name") in ignored_names:
            continue
        slide = int(row.get("slide", 0) or 0)
        text = row.get("text", "").strip()
        if text:
            by_slide[slide].append(text)
    return {slide: "\n".join(parts) for slide, parts in by_slide.items()}


def sparse_body_slides(rows: list[dict], slide_count: int, minimum_words: int = 8) -> list[int]:
    """Catch rendered body slides whose layout-specific content disappeared."""
    generic = {
        "eyebrow", "footer-course", "footer-number", "slide-title", "slide-subtitle",
        "bottom-line", "takeaway", "final-line", "variance-label",
    }
    words: dict[int, list[str]] = defaultdict(list)
    for row in rows:
        if row.get("kind") != "textbox" or row.get("name") in generic:
            continue
        slide = int(row.get("slide", 0) or 0)
        words[slide].extend(re.findall(r"\b[\w'-]+\b", str(row.get("text") or "")))
    return [slide for slide in range(2, slide_count) if len(words.get(slide, [])) < minimum_words]


def bbox(row: dict) -> tuple[float, float, float, float] | None:
    value = row.get("bbox")
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, w, h = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    return x, y, w, h


def intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def is_brand_or_background(row: dict) -> bool:
    name = row.get("name", "")
    if name in {"brand", "brand-icon", "brand-negative", "footer-course", "footer-number", "eyebrow"}:
        return True
    if name in {"left-navy", "orange-rule"}:
        return True
    alt = row.get("alt", "")
    return "BuildStak icon" in alt or "BuildStak negative wordmark" in alt


def text_capacity_warning(row: dict) -> str | None:
    text = str(row.get("text", "")).strip()
    # These elements intentionally sit on the open slide canvas, rather than
    # inside a panel.  Their safety is covered by slide/footer bounds; fitting
    # them to a fictional box would create false failures.
    open_canvas_text = {"intro", "bottom-line", "takeaway", "final-line"}
    if len(text) < 20 or row.get("name", "") in open_canvas_text or row.get("name", "").startswith("bullet-dot"):
        return None
    box = bbox(row)
    font_size = row.get("resolvedFontSize")
    if not box or not font_size:
        return None
    _x, _y, width, height = box
    if width <= 0 or height <= 0:
        return None
    try:
        font = float(font_size)
    except (TypeError, ValueError):
        return None
    # Conservative estimate: it is better to send a deck back for a smaller
    # font/roomier box than to approve copy that visibly escapes its panel.
    chars_per_line = max(1.0, width / (font * 0.55))
    usable_lines = max(1.0, height / (font * 1.15))
    # Account for the renderer's real line spacing while retaining a margin
    # tight enough to reject copy forced into a single-line row.
    capacity = chars_per_line * usable_lines * 1.10
    if len(text) > capacity:
        return f"slide {row.get('slide')} `{row.get('name')}` may be too dense for its text box"
    return None


def rendered_text_container_name(name: str) -> str | None:
    if re.match(r"^row-\d+-(title|body)$", name):
        return name.rsplit("-", 1)[0] + "-bar"
    if re.match(r"^check-\d+-(title|body)$", name):
        return name.rsplit("-", 1)[0] + "-row"
    if name.startswith("planned-"):
        return "planned-lane"
    if name.startswith("actual-"):
        return "actual-lane"
    if name == "takeaway-copy":
        return "takeaway-box"
    if name.endswith("-title") or name.endswith("-body"):
        return name.rsplit("-", 1)[0] + "-card"
    return None


def rendered_line_fit_warning(row: dict, layout_rows: list[dict] | None = None) -> str | None:
    """Use the renderer's actual wrapping result to reject clipped text.

    Character-count estimates cannot account for language-specific word
    lengths, text-box insets, or the actual font selected by PowerPoint.  The
    layout export already records the final line count, so this is the
    authoritative fit gate whenever that metadata is available.
    """
    name = str(row.get("name") or "")
    open_canvas_text = {
        "course", "lesson", "topics", "slide-title", "title", "subtitle", "slide-subtitle",
        "intro", "bottom-line", "takeaway", "takeaway-title", "final-line", "lesson-label", "variance-label",
    }
    if name in open_canvas_text or is_brand_or_background(row) or name.startswith("bullet-dot"):
        return None
    layout = row.get("textLayout")
    if not isinstance(layout, dict):
        return None
    try:
        line_count = int(layout.get("lineCount") or 0)
    except (TypeError, ValueError):
        return None
    box = bbox(row)
    if not box or line_count <= 0:
        return None
    paragraphs = row.get("paragraphs") or []
    font_size = None
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            continue
        style = paragraph.get("resolvedTextStyle") or {}
        if style.get("fontSize"):
            font_size = style.get("fontSize")
            break
    font_size = font_size or row.get("resolvedFontSize")
    try:
        font = float(font_size)
    except (TypeError, ValueError):
        return None
    height = box[3]
    if height <= 0 or font <= 0:
        return None
    container_name = rendered_text_container_name(name)
    container = next(
        (
            candidate
            for candidate in (layout_rows or [])
            if container_name
            and candidate.get("slide") == row.get("slide")
            and candidate.get("name") == container_name
        ),
        None,
    )
    container_box = bbox(container) if container else None
    if container_box:
        rendered_bottom = box[1] + line_count * font * 1.10
        container_bottom = container_box[1] + container_box[3]
        if rendered_bottom > container_bottom - 2:
            return (
                f"slide {row.get('slide')} `{name}` renders {line_count} lines beyond "
                f"its `{container_name}` container"
            )
        return None
    safe_lines = max(1, math.floor(height / font))
    if line_count > safe_lines:
        return (
            f"slide {row.get('slide')} `{row.get('name')}` renders {line_count} lines "
            f"in a box that safely fits {safe_lines}"
        )
    return None


def classify_slide_function(text: str) -> str:
    low = text.lower()
    if "main topics" in low or "covered" in low:
        return "cover"
    if "takeaway" in low:
        return "takeaway"
    if any(word in low for word in [" vs.", "versus", "overlap", "different"]):
        return "comparison"
    if any(phrase in low for phrase in ["escalate when", "trigger", "leaves normal", "risk threshold"]):
        return "decision_trigger"
    if any(word in low for word in ["habit", "step", "checklist"]):
        return "sequence"
    if any(word in low for word in ["record", "documentation", "traceable"]):
        return "sequence_or_record"
    if "?" in text:
        return "question_frame"
    return "concept"


def run_checks(deck_path: Path, qa_path: Path | None = None) -> dict:
    inspect_path = inspect_path_for(deck_path)
    qa_path = qa_path or deck_path.with_name(re.sub(r"_r\d+\.pptx$|\.pptx$", "_qa.md", deck_path.name))

    rows = load_ndjson(inspect_path)
    layout_rows = load_layout_elements(deck_path)
    qa_text = read_text(qa_path)
    findings: list[Finding] = []

    if not inspect_path.exists():
        findings.append(Finding("fail", "inspect_file", "PPTX inspect NDJSON file is missing. Render/inspect the deck before QA."))
    else:
        findings.append(Finding("pass", "inspect_file", "PPTX inspect NDJSON file exists."))

    slides = [row for row in rows if row.get("kind") == "slide"]
    slide_count = len(slides)
    if slide_count == 10:
        findings.append(Finding("pass", "slide_count", "Deck has 10 slides."))
    else:
        findings.append(Finding("fail", "slide_count", f"Deck has {slide_count} slides; expected 10."))

    notes = [row for row in rows if row.get("kind") == "notes" and row.get("text", "").strip()]
    if notes:
        findings.append(Finding("fail", "speaker_notes", f"{len(notes)} slides contain speaker notes."))
    else:
        findings.append(Finding("pass", "speaker_notes", "No speaker notes found."))

    slide_text = visible_text_by_slide(rows)
    slide_tokens = {slide: normalize_tokens(text) for slide, text in slide_text.items()}
    slide_functions = {slide: classify_slide_function(text) for slide, text in slide_text.items()}

    sparse = sparse_body_slides(rows, slide_count)
    if sparse:
        findings.append(Finding("fail", "body_slide_content", f"Rendered body content is missing or too sparse on slides: {sparse}."))
    else:
        findings.append(Finding("pass", "body_slide_content", "Every body slide contains visible layout-specific teaching content."))

    similar_pairs = []
    duplicate_function_pairs = []
    for i in range(1, slide_count + 1):
        for j in range(i + 1, slide_count + 1):
            if i == 1 or j == 10:
                continue
            score = jaccard(slide_tokens.get(i, set()), slide_tokens.get(j, set()))
            if score >= 0.34:
                similar_pairs.append((i, j, round(score, 2)))
            if (
                abs(i - j) <= 2
                and score >= 0.22
                and slide_functions.get(i) == slide_functions.get(j)
                and slide_functions.get(i) in {"sequence", "sequence_or_record", "decision_trigger"}
            ):
                duplicate_function_pairs.append((i, j, slide_functions[i], round(score, 2)))

    if similar_pairs:
        findings.append(Finding("warn", "slide_text_similarity", f"Potentially similar slide pairs: {similar_pairs}. Verify MECE distinction."))
    else:
        findings.append(Finding("pass", "slide_text_similarity", "No high text-similarity slide pairs found."))

    if duplicate_function_pairs:
        findings.append(Finding("warn", "nearby_slide_function_similarity", f"Nearby slides may share the same teaching function: {duplicate_function_pairs}."))
    else:
        findings.append(Finding("pass", "nearby_slide_function_similarity", "No nearby duplicate slide functions found."))

    all_text = "\n".join(row.get("text", "") for row in rows if row.get("kind") == "textbox")
    forbidden_visible = [
        ("visible_timing", r"\b(in|within)\s+\d+\s+minutes?\b|\b\d+\s+minutes?\b"),
        ("next_lesson_preview", r"\bnext lesson\b|\bcoming next\b"),
        ("image_caption_language", r"\bFigure\s+\d|\bcaption\b|\bsubtitle\b"),
    ]
    for check, pattern in forbidden_visible:
        if re.search(pattern, all_text, re.IGNORECASE):
            findings.append(Finding("fail", check, f"Visible text appears to contain forbidden pattern `{pattern}`."))
        else:
            findings.append(Finding("pass", check, "Forbidden visible pattern not found."))

    images_by_slide: dict[int, int] = defaultdict(int)
    generated_like_by_slide: dict[int, int] = defaultdict(int)
    structured_visual_by_slide: dict[int, int] = defaultdict(int)
    for row in rows:
        slide = int(row.get("slide", 0) or 0)
        if row.get("kind") == "image":
            images_by_slide[slide] += 1
            alt = row.get("alt", "")
            if alt and "BuildStak icon" not in alt and "BuildStak negative wordmark" not in alt:
                generated_like_by_slide[slide] += 1
                structured_visual_by_slide[slide] += 1
        elif row.get("kind") == "shape":
            name = row.get("name", "")
            if name not in {"left-navy", "orange-rule"}:
                structured_visual_by_slide[slide] += 1

    image_slides = sorted(generated_like_by_slide)
    visual_slides = sorted(slide for slide, count in structured_visual_by_slide.items() if count >= 2)
    if image_slides:
        findings.append(Finding("pass", "teaching_image_present", f"Teaching image appears on slide(s): {image_slides}."))
    else:
        findings.append(Finding("pass", "teaching_image_present", "No non-brand teaching image was selected; images are not mandatory when native visuals better serve the lesson."))
    consecutive = [(a, b) for a, b in zip(image_slides, image_slides[1:]) if b == a + 1]
    if consecutive:
        findings.append(Finding("fail", "image_cadence", f"Non-brand images appear on consecutive slides: {consecutive}."))
    else:
        findings.append(Finding("pass", "image_cadence", "No consecutive non-brand image slides found."))

    gaps = []
    previous = 1
    for slide in visual_slides:
        if slide - previous > 3:
            gaps.append((previous, slide))
        previous = slide
    if slide_count and visual_slides and slide_count - visual_slides[-1] > 3:
        gaps.append((visual_slides[-1], slide_count))
    if gaps:
        findings.append(Finding("warn", "visual_gap", f"Potential long visual gaps: {gaps}."))
    else:
        findings.append(Finding("pass", "visual_gap", "No obvious long visual gap found."))

    footer_numbers = Counter()
    for row in rows:
        if row.get("kind") == "textbox" and row.get("name") == "footer-number":
            footer_numbers[int(row.get("slide", 0) or 0)] += 1
    missing_footer = [slide for slide in range(1, slide_count + 1) if footer_numbers[slide] != 1]
    if missing_footer:
        findings.append(Finding("fail", "footer_numbers", f"Footer number missing or duplicated on slides: {missing_footer}."))
    else:
        findings.append(Finding("pass", "footer_numbers", "Each slide has one footer number."))

    outside = []
    footer_overlaps = []
    slide_bounds = (0.0, 0.0, 1280.0, 720.0)
    footer_band = (0.0, 650.0, 1280.0, 70.0)
    for row in rows:
        if row.get("kind") not in {"textbox", "image", "shape"}:
            continue
        box = bbox(row)
        if not box:
            continue
        x, y, w, h = box
        if x < -2 or y < -2 or x + w > slide_bounds[2] + 2 or y + h > slide_bounds[3] + 2:
            outside.append((row.get("slide"), row.get("name"), [round(x), round(y), round(w), round(h)]))
        if not is_brand_or_background(row) and intersects(box, footer_band):
            footer_overlaps.append((row.get("slide"), row.get("name")))
    if outside:
        findings.append(Finding("fail", "bbox_within_slide", f"Elements outside slide bounds: {outside[:8]}."))
    else:
        findings.append(Finding("pass", "bbox_within_slide", "All inspected elements stay within slide bounds."))

    if footer_overlaps:
        findings.append(Finding("fail", "footer_clearance", f"Non-footer elements overlap the footer band: {footer_overlaps[:8]}."))
    else:
        findings.append(Finding("pass", "footer_clearance", "No non-footer elements overlap the footer band."))

    # The renderer records the authoritative text boxes in the inspect file.
    # Revisioned render folders may be retained separately, so their absence
    # must never disable fit validation for an otherwise inspectable deck.
    if any(row.get("kind") == "textbox" for row in rows):
        rendered_text_rows = [
            row
            for row in layout_rows
            if str(row.get("text") or "").strip() and isinstance(row.get("textLayout"), dict)
        ]
        rendered_dense = [
            warning
            for row in rendered_text_rows
            if (warning := rendered_line_fit_warning(row, layout_rows))
        ]
        dense = rendered_dense if rendered_text_rows else [warning for row in rows if row.get("kind") == "textbox" and (warning := text_capacity_warning(row))]
        missing_font_metadata = [
            f"slide {row.get('slide')} `{row.get('name')}`"
            for row in rows
            if row.get("kind") == "textbox"
            and row.get("name") not in {"eyebrow", "footer-course", "footer-number"}
            and not row.get("resolvedFontSize")
        ]
        if dense:
            findings.append(Finding("fail", "text_box_density", f"Text does not fit safely inside its rendered box: {dense[:8]}."))
        elif missing_font_metadata:
            findings.append(Finding("fail", "text_box_density", f"Text-fit metadata is missing for: {missing_font_metadata[:8]}."))
        else:
            findings.append(Finding("pass", "text_box_density", "No obvious text-density issues found in rendered layout metadata."))
    else:
        findings.append(Finding("warn", "text_box_density", "Rendered slide layout metadata not found; text-density check skipped."))

    mixed_visual_mode = []
    for slide in image_slides:
        non_brand_shapes = [
            row
            for row in rows
            if int(row.get("slide", 0) or 0) == slide
            and row.get("kind") == "shape"
            and not is_brand_or_background(row)
        ]
        if len(non_brand_shapes) >= 4:
            mixed_visual_mode.append((slide, len(non_brand_shapes)))
    if mixed_visual_mode:
        findings.append(Finding("warn", "mixed_visual_mode", f"Image slides also contain many diagram shapes: {mixed_visual_mode}. Verify one dominant visual mode."))
    else:
        findings.append(Finding("pass", "mixed_visual_mode", "Image slides do not also carry a competing vector diagram."))

    if "_r" in deck_path.stem:
        revision = latest_revision(deck_path)[1]
        if revision >= 2:
            findings.append(Finding("pass", "cache_safe_revision", f"Deck uses cache-safe revision r{revision:02d}."))
        else:
            findings.append(Finding("warn", "cache_safe_revision", "Deck revision suffix is present but lower than r02."))
    else:
        findings.append(Finding("warn", "cache_safe_revision", "Deck uses canonical name. This is okay only for first delivery before human feedback."))

    qa_requirements = [
        ("qa_latest_revision", deck_path.name),
        ("qa_mece", "MECE"),
        ("qa_no_last_item_highlight", "last-item"),
        ("qa_no_arbitrary_highlight", "highlight"),
        ("qa_visual_inspected", "visually rechecked"),
    ]
    for check, needle in qa_requirements:
        if needle.lower() in qa_text.lower():
            findings.append(Finding("pass", check, f"QA mentions `{needle}`."))
        else:
            findings.append(Finding("warn", check, f"QA does not mention `{needle}`."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "deck": str(deck_path),
        "inspect": str(inspect_path),
        "qa": str(qa_path),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"Deck QA passed: {'yes' if data['passed'] else 'no'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Deck: {data['deck']}",
        f"Inspect: {data['inspect']}",
        f"QA: {data['qa']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Prof Greg deck QA checks against a PPTX inspect file and QA note.")
    parser.add_argument("deck", help="Path to the final PPTX deck.")
    parser.add_argument("--qa", help="Path to deck QA Markdown. Defaults to lesson deck QA beside the PPTX.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    deck_path = Path(args.deck).expanduser().resolve()
    qa_path = Path(args.qa).expanduser().resolve() if args.qa else None
    data = run_checks(deck_path, qa_path)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
