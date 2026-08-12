#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def source_year(source: dict[str, Any]) -> int | None:
    text = str(source.get("publication_date") or "")
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return int(match.group(0)) if match else None


def source_label(source: dict[str, Any]) -> str:
    return f"{source.get('source_id', '?')} {source.get('title', '').strip()}"


def is_more_than_three_years_old(source: dict[str, Any], production_year: int) -> bool:
    year = source_year(source)
    if year is None:
        return False
    return production_year - year > 3


def student_reference_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    return lines


def student_reference_line_for_source(source: dict[str, Any], references_text: str) -> str | None:
    title = str(source.get("title") or "").strip().lower()
    if not title:
        return None
    for line in student_reference_lines(references_text):
        if title in line.lower():
            return line
    return None


def is_formal_publication_reference(source: dict[str, Any]) -> bool:
    source_type = str(source.get("source_type") or "").lower()
    title = str(source.get("title") or "").lower()
    url = str(source.get("url") or "").lower()
    formal_types = {
        "book",
        "published-book",
        "published-book-or-manual",
        "published-book-or-standard",
        "recommended-practice",
        "standard",
        "professional-standard",
        "professional-standard-discussion",
    }
    return (
        source_type in formal_types
        or "/bookstore/book/" in url
        or "practice standard" in title
        or "standards of practice" in title
        or "recommended practice" in title
    )


def eligible_for_student_reference(source: dict[str, Any]) -> bool:
    validation = source.get("currency_validation") or {}
    status = validation.get("status")
    if status == "unresolved":
        return False
    if not source.get("claims_supported"):
        return False
    if source.get("authority_tier") == "supplemental" and status != "validated-current":
        return False
    return True


def title_in_references(source: dict[str, Any], references_text: str) -> bool:
    title = str(source.get("title") or "").strip()
    org = str(source.get("author_or_organization") or "").strip()
    haystack = references_text.lower()
    if title and title.lower() in haystack:
        return True
    if org and title:
        title_words = [word for word in re.findall(r"[a-zA-Z0-9]+", title.lower()) if len(word) > 3]
        return bool(title_words) and org.lower() in haystack and all(word in haystack for word in title_words[:3])
    return False


def run_checks(ledger_path: Path, references_path: Path, production_date: date | None = None) -> dict[str, Any]:
    production_date = production_date or date.today()
    findings: list[Finding] = []

    ledger = load_json(ledger_path)
    references_text = read_text(references_path)
    sources = ledger.get("sources") or []

    if ledger_path.exists():
        findings.append(Finding("pass", "ledger_exists", "Source ledger exists."))
    else:
        findings.append(Finding("fail", "ledger_exists", "Source ledger is missing."))

    if references_path.exists():
        findings.append(Finding("pass", "student_references_exists", "Student references file exists."))
    else:
        findings.append(Finding("fail", "student_references_exists", "Student references file is missing."))

    if sources:
        findings.append(Finding("pass", "sources_present", f"Ledger has {len(sources)} sources."))
    else:
        findings.append(Finding("fail", "sources_present", "Ledger has no sources."))

    required_source_fields = ["source_id", "title", "author_or_organization", "source_type", "authority_tier", "currency_validation", "claims_supported"]
    missing_fields = []
    for source in sources:
        for field in required_source_fields:
            if field not in source:
                missing_fields.append((source.get("source_id", "?"), field))
    if missing_fields:
        findings.append(Finding("fail", "source_required_fields", f"Missing source fields: {missing_fields}."))
    else:
        findings.append(Finding("pass", "source_required_fields", "All sources include required fields."))

    weak_to_replace = set((ledger.get("validation") or {}).get("weak_sources_to_replace") or [])
    old_sources_without_review = []
    old_internal_unresolved = []
    for source in sources:
        if is_more_than_three_years_old(source, production_date.year):
            validation = source.get("currency_validation") or {}
            if not validation.get("required") or validation.get("status") in {None, "", "unresolved"}:
                if not source.get("claims_supported") and source.get("source_id") in weak_to_replace:
                    old_internal_unresolved.append(source_label(source))
                else:
                    old_sources_without_review.append(source_label(source))
    if old_sources_without_review:
        findings.append(Finding("fail", "old_source_currency_review", f"Older sources lack currency/applicability review: {old_sources_without_review}."))
    elif old_internal_unresolved:
        findings.append(Finding("warn", "old_source_currency_review", f"Older unresolved sources exist but are internal/no-claim and flagged weak: {old_internal_unresolved}."))
    else:
        findings.append(Finding("pass", "old_source_currency_review", "Older sources have currency/applicability review or are not used."))

    unresolved_sources = [source_label(source) for source in sources if (source.get("currency_validation") or {}).get("status") == "unresolved"]
    unresolved_unflagged = [label for label in unresolved_sources if label.split()[0] not in weak_to_replace]
    if unresolved_unflagged:
        findings.append(Finding("fail", "unresolved_sources_flagged", f"Unresolved sources not listed as weak sources to replace: {unresolved_unflagged}."))
    elif unresolved_sources:
        findings.append(Finding("warn", "unresolved_sources_flagged", f"Unresolved sources exist but are flagged as weak/internal: {unresolved_sources}."))
    else:
        findings.append(Finding("pass", "unresolved_sources_flagged", "No unresolved sources found."))

    student_forbidden = [
        ("access_dates", r"\bAccessed\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b|\baccessed\s+\d{4}-\d{2}-\d{2}\b"),
        ("local_paths", r"/Users/|/private/|file://|\.codex/|runs/[^ ]+/input/"),
        ("internal_rationale", r"useful for|used to support|reliability|authority_tier|source ledger|context signals|technical authority unless supported|internal context only|do not cite"),
    ]
    for check, pattern in student_forbidden:
        if re.search(pattern, references_text, flags=re.IGNORECASE):
            findings.append(Finding("fail", f"student_refs_{check}", f"Student references contain forbidden pattern `{pattern}`."))
        else:
            findings.append(Finding("pass", f"student_refs_{check}", "Forbidden student-reference pattern not found."))

    ineligible_in_refs = []
    for source in sources:
        if not eligible_for_student_reference(source) and title_in_references(source, references_text):
            ineligible_in_refs.append(source_label(source))
    if ineligible_in_refs:
        findings.append(Finding("fail", "ineligible_sources_in_student_refs", f"Ineligible/internal sources appear in student references: {ineligible_in_refs}."))
    else:
        findings.append(Finding("pass", "ineligible_sources_in_student_refs", "No ineligible/internal source title found in student references."))

    reference_lines = student_reference_lines(references_text)
    if reference_lines:
        findings.append(Finding("pass", "student_reference_lines", f"Student references include {len(reference_lines)} entries."))
    else:
        findings.append(Finding("warn", "student_reference_lines", "No bullet-style student references found."))

    formal_publications_with_links = []
    for source in sources:
        if not is_formal_publication_reference(source):
            continue
        line = student_reference_line_for_source(source, references_text)
        if line and re.search(r"https?://", line, flags=re.IGNORECASE):
            formal_publications_with_links.append(f"{source_label(source)} -> {line}")
    if formal_publications_with_links:
        findings.append(Finding("fail", "formal_publications_not_linked_as_webpages", f"Book/standard references include webpage links: {formal_publications_with_links}."))
    else:
        findings.append(Finding("pass", "formal_publications_not_linked_as_webpages", "Books, standards, and formal publications are not presented as webpage links in student references."))

    eligible_sources = [source for source in sources if eligible_for_student_reference(source)]
    missing_from_student_refs = []
    for source in eligible_sources:
        # Professional books/background sources may be intentionally omitted from short lessons; do not require every eligible source.
        if source.get("source_type") in {"industry-body", "professional-guide", "government", "standard", "code"} and not title_in_references(source, references_text):
            missing_from_student_refs.append(source_label(source))
    if missing_from_student_refs:
        findings.append(Finding("warn", "eligible_core_sources_missing_from_student_refs", f"Eligible core sources not found in student references: {missing_from_student_refs}."))
    else:
        findings.append(Finding("pass", "eligible_core_sources_missing_from_student_refs", "Core eligible sources appear represented in student references."))

    validation = ledger.get("validation") or {}
    if validation.get("unsupported_claims"):
        findings.append(Finding("fail", "unsupported_claims", f"Unsupported claims remain: {validation.get('unsupported_claims')}."))
    else:
        findings.append(Finding("pass", "unsupported_claims", "No unsupported claims listed."))

    if validation.get("all_sources_verified") is True:
        findings.append(Finding("pass", "all_sources_verified_flag", "Ledger marks all sources verified."))
    else:
        if unresolved_sources:
            findings.append(Finding("warn", "all_sources_verified_flag", "Ledger does not mark all sources verified because unresolved/internal sources remain."))
        else:
            findings.append(Finding("warn", "all_sources_verified_flag", "Ledger does not mark all sources verified. Confirm if this is intentional."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "ledger": str(ledger_path),
        "student_references": str(references_path),
        "source_count": len(sources),
        "student_reference_count": len(reference_lines),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Source/reference QA passed: {'yes' if data['passed'] else 'no'}",
        f"Sources: {data['source_count']}",
        f"Student references: {data['student_reference_count']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Ledger: {data['ledger']}",
        f"Student references: {data['student_references']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prof Greg source ledger and student-facing references.")
    parser.add_argument("ledger", help="Path to source_ledger.json.")
    parser.add_argument("student_references", help="Path to student_references.md.")
    parser.add_argument("--production-date", help="Production date YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    production_date = date.fromisoformat(args.production_date) if args.production_date else None
    data = run_checks(Path(args.ledger).expanduser().resolve(), Path(args.student_references).expanduser().resolve(), production_date)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
