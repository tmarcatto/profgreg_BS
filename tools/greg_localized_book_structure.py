#!/usr/bin/env python3
"""Structural contracts shared by localized-book production and QA."""
from __future__ import annotations

import re
from typing import Any


CALLOUTS = {
    "en": ("KEY TERM", "APPLY IT", "HANDS-ON EXAMPLE", "SCENARIO", "CALLBACK", "BRIDGE"),
    "pt_br": ("TERMO-CHAVE", "APLIQUE", "EXEMPLO PRÁTICO", "CENÁRIO", "RETOMADA", "PONTE"),
    "es": ("TÉRMINO CLAVE", "APLICACIÓN", "EJEMPLO PRÁCTICO", "ESCENARIO", "RETOMAR", "PUENTE"),
}

SUMMARY_HEADINGS = {
    "en": "Summary and Key Takeaways",
    "pt_br": "Resumo e Principais Conclusões",
    "es": "Resumen y Conclusiones Clave",
}


def _table_shapes(markdown: str) -> list[dict[str, int]]:
    lines = markdown.splitlines()
    shapes: list[dict[str, int]] = []
    index = 0
    delimiter = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
    while index + 1 < len(lines):
        if lines[index].strip().startswith("|") and delimiter.match(lines[index + 1]):
            columns = len([cell for cell in lines[index].strip().strip("|").split("|")])
            index += 2
            rows = 0
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows += 1
                index += 1
            shapes.append({"columns": columns, "rows": rows})
            continue
        index += 1
    return shapes


def markdown_structure(markdown: str, locale: str) -> dict[str, Any]:
    """Return learner-visible structure that translation must preserve."""
    if locale not in CALLOUTS:
        raise ValueError(f"Unsupported locale: {locale}")
    callout_pattern = "|".join(re.escape(label) for label in CALLOUTS[locale])
    headings = re.findall(r"(?m)^#{1,3}\s+\S.*$", markdown)
    callouts = re.findall(
        rf"(?im)^>\s*(?:\*\*)?(?:{callout_pattern})(?:\*\*)?[ \t]*(?::[ \t]*.*)?$",
        markdown,
    )
    summary = re.search(
        rf"(?ims)^#\s+{re.escape(SUMMARY_HEADINGS[locale])}\s*$\n(.*?)(?=^#\s+|\Z)",
        markdown,
    )
    summary_items = len(re.findall(r"(?m)^\s*[-*+]\s+\S", summary.group(1))) if summary else 0
    return {
        "headings": len(headings),
        "callouts": len(callouts),
        "summary_items": summary_items,
        "tables": _table_shapes(markdown),
    }


def structure_parity_issues(source: dict[str, Any], localized: dict[str, Any]) -> list[str]:
    """Describe any lost/added headings, callout boxes, tables, columns, or rows."""
    issues: list[str] = []
    for key, label in (("headings", "headings"), ("callouts", "callout boxes"), ("summary_items", "summary bullet items")):
        expected = int(source.get(key, 0))
        actual = int(localized.get(key, 0))
        if actual != expected:
            issues.append(f"expected {expected} {label}; found {actual}")
    source_tables = source.get("tables") or []
    localized_tables = localized.get("tables") or []
    if len(localized_tables) != len(source_tables):
        issues.append(f"expected {len(source_tables)} tables; found {len(localized_tables)}")
    for index, (expected, actual) in enumerate(zip(source_tables, localized_tables), start=1):
        if expected != actual:
            issues.append(
                f"table {index} expected {expected.get('columns')} columns/{expected.get('rows')} rows; "
                f"found {actual.get('columns')} columns/{actual.get('rows')} rows"
            )
    return issues
