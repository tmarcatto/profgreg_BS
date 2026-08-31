#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from greg_security import assert_safe_write_path
from greg_localized_book_structure import markdown_structure, structure_parity_issues


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def extract_pages(pdf_path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit(
            "Missing pypdf. Run this tool with the Codex bundled Python runtime or install pypdf."
        ) from exc

    reader = PdfReader(str(pdf_path))
    return [(page.extract_text() or "") for page in reader.pages]


def norm(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    # PDF extraction inserts whitespace after a visible end-of-line hyphen.
    # Treat `Pre-\nConstruction` as the same complete label as
    # `Pre-Construction`; the renderer separately guarantees box fit.
    return re.sub(r"\s*-\s*", "-", normalized)


def find_page(pages: list[str], pattern: str, min_page: int = 1, heading_only: bool = False) -> int | None:
    compiled = re.compile(pattern, re.IGNORECASE)
    for index, text in enumerate(pages, start=1):
        if index < min_page:
            continue
        if heading_only:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if any(compiled.fullmatch(line) or compiled.match(line) for line in lines):
                return index
            continue
        if compiled.search(text):
            return index
    return None


def contains(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def has_unrendered_markdown(text: str) -> bool:
    return (
        "**" in text
        or bool(re.search(r"(?:^|\s)\*(?:\s|$)", text))
        # A Markdown table delimiter is never student-facing PDF content. If
        # it appears after export, the renderer printed source syntax rather
        # than building an actual table.
        or bool(re.search(r"\|\s*:?-{3,}:?\s*\|", text))
    )


def broken_currency_wraps(pages: list[str]) -> list[tuple[int, str]]:
    """Find currency values whose digits were split onto a second visual line."""
    # A following percentage line (for example `$17.713,50` then `10% da
    # base`) is a separate diagram label, not a continuation of the amount.
    pattern = re.compile(r"([$€£]\s*\d[\d.,]*[.,]\d{1,2})[ \t]*\n[ \t]*(\d{1,3})\b(?!\s*%)")
    return [
        (page_number, f"{match.group(1)} / {match.group(2)}")
        for page_number, text in enumerate(pages, start=1)
        for match in pattern.finditer(text)
    ]


def _markdown_table_first_cells(markdown: str) -> list[list[str]]:
    lines = markdown.splitlines()
    tables: list[list[str]] = []
    delimiter = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
    index = 0
    while index + 1 < len(lines):
        if lines[index].strip().startswith("|") and delimiter.match(lines[index + 1]):
            index += 2
            first_cells: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                first_cells.append(re.sub(r"[*_`]+", "", lines[index].strip().strip("|").split("|")[0]).strip())
                index += 1
            tables.append(first_cells)
            continue
        index += 1
    return tables


def table_orphan_row_issues(pages: list[str], source_markdown: str) -> list[str]:
    """Reject a page segment that strands only one body row of a split table."""
    normalized_pages = [norm(page).casefold() for page in pages]
    issues: list[str] = []
    for table_number, first_cells in enumerate(_markdown_table_first_cells(source_markdown), start=1):
        rows_by_page: dict[int, int] = {}
        for cell in first_cells:
            needle = norm(cell).casefold()
            if len(needle) < 8:
                continue
            matches = [index for index, page in enumerate(normalized_pages, start=1) if needle in page]
            if len(matches) == 1:
                rows_by_page[matches[0]] = rows_by_page.get(matches[0], 0) + 1
        if len(rows_by_page) > 1:
            for page_number, count in sorted(rows_by_page.items()):
                if count == 1:
                    issues.append(f"table {table_number} leaves one body row on page {page_number}")
    return issues


def meaningful_lines(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [
        line
        for line in lines
        if not re.fullmatch(r"\d{1,3}", line)
        and not re.fullmatch(r"(?:The )?Complete Construction Project Manager:.+", line)
        and line not in {
            "STUDY GUIDE",
            "BuildStak Learning Series",
            "Construction Schedule Management",
        }
    ]


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text))


def is_heading_line(line: str) -> bool:
    return bool(
        re.match(r"(?:Section|Seção|Sección)\s+\d{2}\s*[:-]", line, flags=re.I)
        or line in {"Summary and Key Takeaways", "Resumo e Principais Conclusões", "Resumen y Conclusiones Clave", "Glossary", "Glossário", "Glosario", "References", "Referências", "Referencias", "Introduction", "Introdução", "Introducción", "Learning Objectives", "Objetivos de Aprendizagem", "Objetivos de Aprendizaje"}
        or re.fullmatch(r"(KEY TERM|APPLY IT|HANDS-ON EXAMPLE|SCENARIO|CALLBACK|BRIDGE|TERMO-CHAVE|APLIQUE|EXEMPLO PRÁTICO|CENÁRIO|RETOMADA|PONTE|TÉRMINO CLAVE|APLICACIÓN|EJEMPLO PRÁCTICO|ESCENARIO|RETOMAR|PUENTE)", line, flags=re.I)
    )


def figure_numbers(text: str) -> list[str]:
    return re.findall(r"\b(?:Figure|Figura)\s+(\d+\.\d+)\b", text)


def expected_visible_visual_text(spec: dict) -> list[str]:
    expected: list[str] = []
    for visual in spec.get("visuals", []):
        visual_type = str(visual.get("type") or "")
        if visual.get("title"):
            expected.append(str(visual["title"]))
        if visual_type == "process_flow":
            for node in visual.get("nodes") or []:
                expected.extend([str(node.get("title") or ""), str(node.get("detail") or "")])
        elif visual_type == "relationship_map":
            expected.extend(str(node.get("title") or "") for node in visual.get("nodes") or [])
        elif visual_type == "card_row":
            expected.extend(str(card.get("title") or "") for card in visual.get("cards") or [])
        elif visual_type == "source_to_wbs_matrix":
            expected.extend([str(visual.get("left_header") or ""), str(visual.get("right_header") or "")])
            for row in visual.get("rows") or []:
                expected.extend([str(row.get("left") or ""), str(row.get("right") or "")])
    return [text for text in expected if text.strip()]


def localized_visual_parity_issues(pdf_path: Path, localized_spec: dict) -> list[str]:
    """Ensure a localized book preserves every learner-visible English visual."""
    locale = str(localized_spec.get("locale") or "")
    if locale not in {"pt_br", "es"}:
        return []
    match = re.search(r"lesson_(\d{2})_", pdf_path.name)
    if not match or len(pdf_path.parents) < 3:
        return []
    english_specs = sorted((pdf_path.parents[2] / "docx_pdf").glob(f"lesson_{match.group(1)}_study_guide_spec_r*.json"))
    if not english_specs:
        return ["English source visual specification is missing."]
    try:
        english_visuals = json.loads(english_specs[-1].read_text(encoding="utf-8")).get("visuals") or []
    except json.JSONDecodeError:
        return ["English source visual specification is invalid."]
    localized_visuals = localized_spec.get("visuals") or []
    if len(english_visuals) != len(localized_visuals):
        return [f"Expected {len(english_visuals)} visuals from the English source; found {len(localized_visuals)} localized visuals."]
    issues = []
    for source, localized in zip(english_visuals, localized_visuals):
        if source.get("visual_id") != localized.get("visual_id"):
            issues.append(f"Visual ID changed from `{source.get('visual_id')}` to `{localized.get('visual_id')}`.")
        if source.get("type") != localized.get("type"):
            issues.append(f"Visual `{source.get('visual_id')}` changed renderer type.")
        source_section = re.search(r"(?:Section|Seção|Sección)\s+(\d{1,2})", str(source.get("after_heading") or ""), flags=re.I)
        localized_section = re.search(r"(?:Section|Seção|Sección)\s+(\d{1,2})", str(localized.get("after_heading") or ""), flags=re.I)
        if not source_section or not localized_section or source_section.group(1) != localized_section.group(1):
            issues.append(f"Visual `{source.get('visual_id')}` is not anchored to the corresponding English section.")
        if source.get("caption") and not localized.get("caption"):
            issues.append(f"Visual `{source.get('visual_id')}` lost its localized caption/source explanation.")
    return issues


def localized_visual_placement_issues(pages: list[str], localized_spec: dict) -> list[str]:
    """Reject localized figures rendered outside the section of their English source."""
    if str(localized_spec.get("locale") or "") not in {"pt_br", "es"}:
        return []
    issues: list[str] = []
    for visual in localized_spec.get("visuals") or []:
        section_match = re.search(
            r"(?:Section|Seção|Sección)\s+(\d{1,2})",
            str(visual.get("after_heading") or ""),
            flags=re.I,
        )
        figure_match = re.search(
            r"(?:Figure|Figura)\s+(\d+\.\d+)", str(visual.get("caption") or ""), flags=re.I
        )
        if not section_match or not figure_match:
            issues.append(f"Localized visual `{visual.get('visual_id')}` has no section anchor or figure caption.")
            continue
        section_number = int(section_match.group(1))
        section_pattern = rf"(?:Section|Seção|Sección)\s+0?{section_number}\s*[:-]"
        figure_pattern = rf"(?:Figure|Figura)\s+{re.escape(figure_match.group(1))}\b"
        # A long localized heading can wrap in the extracted PDF text.  Its
        # numbered prefix remains unique and is sufficient to locate the
        # actual section without accepting a figure from another section.
        section_page = find_page(pages, section_pattern)
        figure_page = find_page(pages, figure_pattern)
        next_section_page = find_page(
            pages, rf"(?:Section|Seção|Sección)\s+0?{section_number + 1}\s*[:-]"
        )
        if section_page is None or figure_page is None:
            issues.append(f"Figure {figure_match.group(1)} cannot be located with its assigned localized section.")
            continue
        if figure_page < section_page:
            issues.append(f"Figure {figure_match.group(1)} appears before Section {section_number:02d}.")
            continue
        if next_section_page is not None and figure_page > next_section_page:
            issues.append(f"Figure {figure_match.group(1)} appears after Section {section_number + 1:02d} begins.")
            continue
        if figure_page == section_page:
            text = pages[figure_page - 1]
            if re.search(figure_pattern, text, flags=re.I).start() < re.search(section_pattern, text, flags=re.I).start():
                issues.append(f"Figure {figure_match.group(1)} appears before its Section {section_number:02d} heading on the same page.")
                continue
        if next_section_page is not None and figure_page == next_section_page:
            text = pages[figure_page - 1]
            if re.search(figure_pattern, text, flags=re.I).start() > re.search(
                rf"(?:Section|Seção|Sección)\s+0?{section_number + 1}\s*[:-]", text, flags=re.I
            ).start():
                issues.append(f"Figure {figure_match.group(1)} appears after Section {section_number + 1:02d} on the same page.")
    return issues


def content_page_range(sequence: dict[str, int | None], page_count: int) -> range:
    start = sequence.get("section_01") or 4
    end = (sequence.get("summary") or page_count + 1) - 1
    return range(start, max(start, end) + 1)


def run_checks(pdf_path: Path, qa_path: Path | None = None) -> dict:
    qa_path = qa_path or pdf_path.with_name(re.sub(r"_study_guide\.pdf$|\.pdf$", "_render_qa.md", pdf_path.name))
    findings: list[Finding] = []

    if not pdf_path.exists():
        findings.append(Finding("fail", "pdf_exists", "PDF file is missing."))
        pages: list[str] = []
    else:
        findings.append(Finding("pass", "pdf_exists", "PDF file exists."))
        pages = extract_pages(pdf_path)

    qa_text = read_text(qa_path)
    page_count = len(pages)
    all_text = "\n".join(pages)
    all_norm = norm(all_text)

    currency_wraps = broken_currency_wraps(pages)
    if currency_wraps:
        findings.append(Finding("fail", "unbroken_numeric_values", f"Currency values split inside a number: {currency_wraps[:8]}."))
    else:
        findings.append(Finding("pass", "unbroken_numeric_values", "No currency value is split inside its digits."))

    if page_count >= 7:
        findings.append(Finding("pass", "page_count", f"PDF has {page_count} pages."))
    else:
        findings.append(Finding("fail", "page_count", f"PDF has {page_count} pages; expected at least 7 for the approved sequence."))

    if pages:
        cover = pages[0]
        cover_requirements = [("study-guide label", r"STUDY GUIDE|APOSTILA|GUÍA DE ESTUDIO"), ("lesson label", r"Lesson|Lição|Lección"), ("level label", r"Level|Nível|Nivel"), ("series label", r"BuildStak Learning Series")]
        missing = [name for name, pattern in cover_requirements if not re.search(pattern, cover, flags=re.I)]
        if missing:
            findings.append(Finding("fail", "cover_template", f"Cover missing expected elements: {missing}."))
        else:
            findings.append(Finding("pass", "cover_template", "Cover includes expected BuildStak study-guide elements."))

    roadmap_page = find_page(pages, r"(?:Lesson Roadmap|Roteiro da Lição|Ruta de la Lección)", heading_only=True)
    intro_page = find_page(pages, r"(?:Introduction|Introdução|Introducción)", min_page=2, heading_only=True)
    objectives_page = find_page(pages, r"(?:Learning Objectives|Objetivos de Aprendizagem|Objetivos de Aprendizaje)", min_page=2, heading_only=True)
    section_01_page = find_page(pages, r"(?:Section|Seção|Sección)\s+01\s*[:-]", min_page=3)
    summary_page = find_page(pages, r"(?:Summary and Key Takeaways|Resumo e Principais Conclusões|Resumen y Conclusiones Clave)", min_page=3, heading_only=True)
    glossary_page = find_page(pages, r"(?:Glossary|Glossário|Glosario)", min_page=3, heading_only=True)
    references_page = find_page(pages, r"(?:References|Referências|Referencias)", min_page=3, heading_only=True)

    sequence = {
        "introduction": intro_page,
        "learning_objectives": objectives_page,
        "section_01": section_01_page,
        "summary": summary_page,
        "glossary": glossary_page,
        "references": references_page,
    }
    missing_sequence = [name for name, page in sequence.items() if page is None]
    if missing_sequence:
        findings.append(Finding("fail", "required_sections", f"Missing required structural sections: {missing_sequence}."))
    else:
        findings.append(Finding("pass", "required_sections", "All required structural sections were found."))

    if roadmap_page:
        findings.append(Finding("fail", "no_lesson_roadmap", f"Lesson Roadmap appears on page {roadmap_page}, but it is no longer part of the approved template."))
    else:
        findings.append(Finding("pass", "no_lesson_roadmap", "No Lesson Roadmap page found."))

    if intro_page == 2:
        findings.append(Finding("pass", "introduction_page", "Introduction starts directly after the cover on page 2."))
    elif intro_page:
        findings.append(Finding("fail", "introduction_page", f"Introduction starts on page {intro_page}; approved template expects page 2."))

    if intro_page and objectives_page and intro_page == objectives_page:
        findings.append(Finding("pass", "intro_objectives_same_page", "Introduction and Learning Objectives are on the same page."))
    elif intro_page and objectives_page:
        findings.append(Finding("warn", "intro_objectives_same_page", f"Introduction page {intro_page}, objectives page {objectives_page}; approved template expects both together."))

    if objectives_page and section_01_page and section_01_page > objectives_page:
        findings.append(Finding("pass", "body_starts_after_objectives", "Lesson body starts after the front matter page."))
    elif objectives_page and section_01_page:
        findings.append(Finding("fail", "body_starts_after_objectives", "Lesson body starts before or on the Learning Objectives page."))

    ordered_pages = [page for page in [intro_page, section_01_page, summary_page, glossary_page, references_page] if page is not None]
    if ordered_pages == sorted(ordered_pages) and len(ordered_pages) >= 5:
        findings.append(Finding("pass", "page_sequence", "Core sections appear in approved order."))
    else:
        findings.append(Finding("fail", "page_sequence", f"Core section order is unexpected: {sequence}."))

    for name, page in [("summary", summary_page), ("glossary", glossary_page), ("references", references_page)]:
        if page is not None and page > 1:
            previous = pages[page - 2]
            current = pages[page - 1]
            if contains(current, rf"\b{name.replace('_', ' ')}\b"):
                findings.append(Finding("pass", f"{name}_own_page", f"{name.title()} starts on page {page}."))

    forbidden_patterns = [
        ("sec_abbreviation", r"\bSEC\.\s*\d+"),
        ("learning_line_caption", r"\blearning line\b"),
        ("student_access_dates", r"\bAccessed\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b"),
        ("local_file_paths", r"/Users/|/private/|file://|\.codex/"),
        ("internal_reference_rationale", r"Practitioner discussion sources|context signals|technical authority unless supported|source ledger|source reliability"),
    ]
    for check, pattern in forbidden_patterns:
        if contains(all_text, pattern):
            findings.append(Finding("fail", check, f"Found forbidden student-facing pattern `{pattern}`."))
        else:
            findings.append(Finding("pass", check, "Forbidden pattern not found."))

    if has_unrendered_markdown(all_text):
        findings.append(Finding("fail", "unrendered_markdown", "Found unrendered Markdown emphasis markers in the student PDF."))
    else:
        findings.append(Finding("pass", "unrendered_markdown", "No unrendered Markdown emphasis markers found."))

    section_heading_questions = []
    for page_number, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines[:-1]):
            if re.match(r"(?:Section|Seção|Sección)\s+\d{2}\s*[:-]", line, flags=re.IGNORECASE) and lines[index + 1].endswith("?"):
                section_heading_questions.append((page_number, line, lines[index + 1]))
    if section_heading_questions:
        findings.append(Finding("fail", "section_heading_questions", f"Section headings followed by question subtitles: {section_heading_questions[:3]}."))
    else:
        findings.append(Finding("pass", "section_heading_questions", "No question subtitle directly after a section heading found."))

    if summary_page and references_page:
        structural_tail = "\n".join(pages[summary_page - 1 : references_page])
        callout_labels = re.findall(r"\b(KEY TERM|APPLY IT|HANDS-ON EXAMPLE|SCENARIO|CALLBACK|BRIDGE|TERMO-CHAVE|APLIQUE|EXEMPLO PRÁTICO|CENÁRIO|RETOMADA|PONTE|TÉRMINO CLAVE|APLICACIÓN|EJEMPLO PRÁCTICO|ESCENARIO|RETOMAR|PUENTE)\b", structural_tail, flags=re.IGNORECASE)
        if callout_labels:
            findings.append(Finding("fail", "callouts_in_structural_sections", f"Callout labels found in structural tail sections: {sorted(set(callout_labels))}."))
        else:
            findings.append(Finding("pass", "callouts_in_structural_sections", "No callout labels found in summary/glossary/references sections."))

    content_pages = list(content_page_range(sequence, page_count))
    sparse_pages = []
    orphan_endings = []
    orphan_openings = []
    heading_openings = []
    split_callout_labels = []
    figures_by_page: dict[int, list[str]] = {}
    for page_number in content_pages:
        if page_number < 1 or page_number > page_count:
            continue
        text = pages[page_number - 1]
        lines = meaningful_lines(text)
        figures = figure_numbers(text)
        if figures:
            figures_by_page[page_number] = figures
        words = word_count(text)
        is_last_content_page = page_number == content_pages[-1]
        sparse_threshold = 70 if is_last_content_page else 110
        if words < sparse_threshold and not figures:
            sparse_pages.append((page_number, words))
        if lines:
            last = lines[-1]
            if is_heading_line(last):
                orphan_endings.append((page_number, last))
            first = lines[0]
            if (
                re.match(r"^[a-z]", first)
                and len(first.split()) <= 6
                and re.search(r"[.!?]$", first)
            ):
                orphan_openings.append((page_number, first))
            if re.match(r"(?:Section|Seção|Sección)\s+\d{2}\s*[:-]", lines[0], flags=re.I) and len(lines) <= 2:
                heading_openings.append((page_number, lines[:2]))
        for index, line in enumerate(lines):
            if re.fullmatch(r"(KEY TERM|APPLY IT|HANDS-ON EXAMPLE|SCENARIO|CALLBACK|BRIDGE|TERMO-CHAVE|APLIQUE|EXEMPLO PRÁTICO|CENÁRIO|RETOMADA|PONTE|TÉRMINO CLAVE|APLICACIÓN|EJEMPLO PRÁCTICO|ESCENARIO|RETOMAR|PUENTE)", line, flags=re.I):
                remaining = " ".join(lines[index + 1 : index + 3])
                if len(remaining.split()) < 6:
                    split_callout_labels.append((page_number, line))

    if sparse_pages:
        findings.append(Finding("fail", "sparse_content_pages", f"Content pages with very little extracted text and no figure: {sparse_pages}."))
    else:
        findings.append(Finding("pass", "sparse_content_pages", "No sparse body-content pages found."))

    if orphan_endings:
        findings.append(Finding("fail", "orphan_heading_endings", f"Pages end with likely orphan headings: {orphan_endings[:5]}."))
    else:
        findings.append(Finding("pass", "orphan_heading_endings", "No content page ends with a likely orphan heading."))

    if orphan_openings:
        findings.append(Finding("fail", "orphan_line_openings", f"Pages start with likely orphan continuation lines: {orphan_openings[:5]}."))
    else:
        findings.append(Finding("pass", "orphan_line_openings", "No content page starts with an orphan continuation line."))

    if heading_openings:
        findings.append(Finding("fail", "one_line_section_openings", f"Section openings with too little body text: {heading_openings[:5]}."))
    else:
        findings.append(Finding("pass", "one_line_section_openings", "No section opening is limited to only a heading/one line."))

    if split_callout_labels:
        findings.append(Finding("fail", "split_callout_labels", f"Callout labels appear separated from body text: {split_callout_labels[:5]}."))
    else:
        findings.append(Finding("pass", "split_callout_labels", "No isolated callout labels found in content pages."))

    if content_pages:
        figure_pages = sorted(figures_by_page)
        long_gaps = []
        previous = content_pages[0] - 1
        for figure_page in figure_pages:
            if figure_page - previous > 4:
                long_gaps.append((previous + 1, figure_page - 1))
            previous = figure_page
        if figure_pages and content_pages[-1] - figure_pages[-1] > 4:
            long_gaps.append((figure_pages[-1] + 1, content_pages[-1]))
        if not figure_pages:
            findings.append(Finding("warn", "figure_cadence", "No figures found in body content pages."))
        elif long_gaps:
            findings.append(Finding("warn", "figure_cadence", f"Potential long body-content gaps without figures: {long_gaps}."))
        else:
            findings.append(Finding("pass", "figure_cadence", "Body figures appear at a reasonable cadence."))

    expected_figures = []
    expected_visual_text = []
    lesson_match_for_figures = re.search(r"lesson_(\d{2})_", pdf_path.name)
    if lesson_match_for_figures:
        revision_for_figures = re.search(r"_(r\d+)\.pdf$", pdf_path.name)
        revision_suffix = f"_{revision_for_figures.group(1)}" if revision_for_figures else ""
        spec_candidates = sorted(
            pdf_path.parent.glob(f"lesson_{lesson_match_for_figures.group(1)}_study_guide*_spec{revision_suffix}.json")
        )
        spec_path = spec_candidates[-1] if spec_candidates else None
        if spec_path and spec_path.exists():
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                source_structure = spec.get("source_structure")
                localized_source = spec.get("source_markdown")
                if source_structure and isinstance(localized_source, str):
                    source_path = ROOT / localized_source
                    localized_text = read_text(source_path)
                    structure_issues = structure_parity_issues(
                        source_structure,
                        markdown_structure(localized_text, str(spec.get("locale") or "en")),
                    )
                    if structure_issues:
                        findings.append(Finding("fail", "localized_document_structure", "; ".join(structure_issues)))
                    else:
                        findings.append(Finding("pass", "localized_document_structure", "Localized headings, callout boxes, tables, columns, and rows match the English source."))
                    orphan_rows = table_orphan_row_issues(pages, localized_text)
                    if orphan_rows:
                        findings.append(Finding("fail", "table_orphan_rows", "; ".join(orphan_rows)))
                    else:
                        findings.append(Finding("pass", "table_orphan_rows", "No split table segment contains only one body row."))
                parity_issues = localized_visual_parity_issues(pdf_path, spec)
                if parity_issues:
                    findings.append(Finding("fail", "localized_visual_parity", " ".join(parity_issues[:6])))
                elif str(spec.get("locale") or "") in {"pt_br", "es"}:
                    findings.append(Finding("pass", "localized_visual_parity", "Localized visual count, IDs, types, and captions match the English source."))
                placement_issues = localized_visual_placement_issues(pages, spec)
                if placement_issues:
                    findings.append(Finding("fail", "localized_visual_placement", " ".join(placement_issues[:6])))
                elif str(spec.get("locale") or "") in {"pt_br", "es"}:
                    findings.append(Finding("pass", "localized_visual_placement", "Every localized figure is rendered inside its assigned English-source section."))
                expected_figures = [
                    match.group(1)
                    for visual in spec.get("visuals", [])
                    for match in [re.search(r"(?:Figure|Figura)\s+(\d+\.\d+)", str(visual.get("caption") or ""))]
                    if match
                ]
                expected_visual_text = expected_visible_visual_text(spec)
            except json.JSONDecodeError:
                expected_figures = []
                expected_visual_text = []
    actual_figures = sorted({figure for figures in figures_by_page.values() for figure in figures})
    if expected_figures:
        missing_figures = sorted(set(expected_figures) - set(actual_figures))
        extra_figures = sorted(set(actual_figures) - set(expected_figures))
        if missing_figures or extra_figures:
            findings.append(Finding("fail", "figure_caption_alignment", f"Figure captions mismatch spec. Missing: {missing_figures}; extra: {extra_figures}."))
        else:
            findings.append(Finding("pass", "figure_caption_alignment", "Rendered figure captions match the study-guide spec."))

    if expected_visual_text:
        missing_visual_text = [text for text in expected_visual_text if norm(text) not in all_norm]
        if missing_visual_text:
            findings.append(Finding("fail", "figure_visible_text_alignment", f"Diagram text is missing or clipped in the rendered PDF: {missing_visual_text[:10]}."))
        else:
            findings.append(Finding("pass", "figure_visible_text_alignment", "Every required diagram label and cell from the spec is visible in the rendered PDF."))

    revision_match = re.search(r"_(r\d+)\.pdf$", pdf_path.name)
    lesson_match = re.search(r"lesson_(\d{2})_", pdf_path.name)
    exact_rendered_dir = (
        pdf_path.parent / f"rendered_pages_lesson_{lesson_match.group(1)}_{revision_match.group(1)}"
        if lesson_match and revision_match
        else None
    )
    lesson_rendered_dir = pdf_path.parent / f"rendered_pages_lesson_{lesson_match.group(1)}" if lesson_match else None
    if lesson_rendered_dir and not lesson_rendered_dir.exists() and lesson_match:
        lesson_rendered_dir = pdf_path.parent / f"rendered_pages_lesson_{int(lesson_match.group(1))}"
    revision_rendered_dir = pdf_path.parent / f"rendered_pages_{revision_match.group(1)}" if revision_match else None
    if exact_rendered_dir and exact_rendered_dir.exists():
        rendered_dir = exact_rendered_dir
    elif revision_rendered_dir and revision_rendered_dir.exists():
        rendered_dir = revision_rendered_dir
    elif lesson_rendered_dir and lesson_rendered_dir.exists():
        rendered_dir = lesson_rendered_dir
    else:
        rendered_dir = pdf_path.parent / "rendered_pages"
    rendered_pages = sorted(rendered_dir.glob("page-*.png"))
    if rendered_pages:
        if len(rendered_pages) == page_count:
            findings.append(Finding("pass", "rendered_pages_count", "Rendered PNG page count matches PDF page count."))
        else:
            findings.append(Finding("warn", "rendered_pages_count", f"Rendered PNG count {len(rendered_pages)} does not match PDF page count {page_count}."))
    else:
        findings.append(Finding("warn", "rendered_pages_count", "No rendered page PNGs found for visual inspection."))

    if qa_path and qa_path.exists():
        qa_requirements = [
            ("qa_cover", "Cover"),
            ("qa_introduction", "Introduction"),
            ("qa_references_no_access_dates", "access dates"),
            ("qa_orphans", "orphan"),
            ("qa_status", "Passed"),
        ]
        for check, needle in qa_requirements:
            if needle.lower() in qa_text.lower():
                findings.append(Finding("pass", check, f"Render QA mentions `{needle}`."))
            else:
                findings.append(Finding("warn", check, f"Render QA does not mention `{needle}`."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "pdf": str(pdf_path),
        "qa": str(qa_path),
        "page_count": page_count,
        "section_pages": sequence,
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict) -> str:
    lines = [
        f"PDF layout QA passed: {'yes' if data['passed'] else 'no'}",
        f"Pages: {data['page_count']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"PDF: {data['pdf']}",
        f"QA: {data['qa']}",
        "",
        "Section pages:",
    ]
    for name, page in data["section_pages"].items():
        lines.append(f"- {name}: {page if page is not None else 'missing'}")
    lines.extend(["", "Findings:"])
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Prof Greg study-guide PDF layout checks.")
    parser.add_argument("pdf", help="Path to the final study-guide PDF.")
    parser.add_argument("--qa", help="Path to render QA Markdown. Defaults beside the PDF.")
    parser.add_argument("--output", help="Optional path to write the Markdown report.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    qa_path = Path(args.qa).expanduser().resolve() if args.qa else None
    data = run_checks(pdf_path, qa_path)
    markdown = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
