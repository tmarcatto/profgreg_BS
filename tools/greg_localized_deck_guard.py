#!/usr/bin/env python3
"""Fail-closed provenance and structure checks for localized presentations."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

ENGLISH_DOMAIN_TERMS = re.compile(
    r"\b(?:budget|cash|cost|forecast|variance|decision|billing|retainage|aging|"
    r"invoices?|accruals?|townhomes?|draw|ticket|spend|records?|question|response|job)\b",
    flags=re.IGNORECASE,
)
ENGLISH_GRAMMAR_TERMS = re.compile(
    r"\b(?:the|and|with|when|will|does|within|before|after|higher|more|main|correct)\b",
    flags=re.IGNORECASE,
)


class LocalizedDeckIntegrityError(RuntimeError):
    """Raised when a localized deck cannot be tied to the approved source."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_root_for_run(run: Path) -> Path:
    return run.parent.parent if run.parent.name == "runs" else run.parent


def _resolve_run_path(run: Path, value: str) -> Path:
    raw = value.strip().strip("`").strip()
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.parts and candidate.parts[0] == "runs":
        return (_repo_root_for_run(run) / candidate).resolve()
    return (run / candidate).resolve()


def _artifact_from_approval(run: Path, approval: Path) -> Path:
    if not approval.is_file():
        raise LocalizedDeckIntegrityError("The approved English presentation record is missing.")
    text = approval.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"(?:Artifact approved|Approved artifact|Artifact):\s*(?:`([^`]+)`|([^\n]+))",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise LocalizedDeckIntegrityError("The English presentation approval does not name an artifact.")
    artifact = _resolve_run_path(run, match.group(1) or match.group(2) or "")
    run_root = run.resolve()
    if run_root not in artifact.parents or not artifact.is_file():
        raise LocalizedDeckIntegrityError("The approved English presentation path is invalid or missing.")
    return artifact


def approved_deck_source(run: Path, lesson_tag: str) -> tuple[Path, Path, dict[str, Any]]:
    approval = run / "approval" / f"{lesson_tag}_deck_approval.md"
    approved_deck = _artifact_from_approval(run, approval)
    match = re.fullmatch(rf"{re.escape(lesson_tag)}_deck_r(\d+)\.pptx", approved_deck.name)
    if not match:
        raise LocalizedDeckIntegrityError(
            f"The approved English presentation is not a revisioned pipeline artifact: {approved_deck.name}."
        )
    source_spec = run / "deck" / f"{lesson_tag}_deck_spec_r{int(match.group(1)):02d}.json"
    if not source_spec.is_file():
        raise LocalizedDeckIntegrityError(
            f"The approved English presentation has no matching deck spec: {source_spec.name}."
        )
    try:
        source = json.loads(source_spec.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LocalizedDeckIntegrityError(f"The approved English deck spec is invalid: {source_spec.name}.") from error
    rendered_path = _resolve_run_path(run, str((source.get("output") or {}).get("pptx") or ""))
    if rendered_path != approved_deck.resolve():
        raise LocalizedDeckIntegrityError(
            f"The approved English presentation does not match its deck spec: {source_spec.name}."
        )
    return approved_deck, source_spec, source


def localized_spec_path(run: Path, lesson_tag: str, localized_deck: Path) -> Path:
    match = re.fullmatch(
        rf"{re.escape(lesson_tag)}_deck_(pt_br|es)_r(\d+)\.pptx",
        localized_deck.name,
    )
    if not match:
        raise LocalizedDeckIntegrityError(
            f"The localized presentation is not a revisioned pipeline artifact: {localized_deck.name}."
        )
    return localized_deck.parent / f"{lesson_tag}_deck_{match.group(1)}_spec_r{int(match.group(2)):02d}.json"


def localized_approval_matches(run: Path, lesson_tag: str, localized_deck: Path) -> bool:
    match = re.fullmatch(
        rf"{re.escape(lesson_tag)}_deck_(pt_br|es)_r\d+\.pptx",
        localized_deck.name,
    )
    if not match:
        return False
    approval = run / "approval" / f"{lesson_tag}_{match.group(1)}_deck_approval.md"
    try:
        approved_localized_deck = _artifact_from_approval(run, approval)
    except LocalizedDeckIntegrityError:
        return False
    return approved_localized_deck.resolve() == localized_deck.resolve()


def spec_structure(slides: Any) -> list[dict[str, Any]]:
    if not isinstance(slides, list):
        raise LocalizedDeckIntegrityError("Presentation spec has no valid slide list.")
    result: list[dict[str, Any]] = []
    for slide in slides:
        if not isinstance(slide, dict):
            raise LocalizedDeckIntegrityError("Presentation spec contains an invalid slide.")
        network_paths = slide.get("network_paths")
        result.append(
            {
                "layout": slide.get("layout"),
                "topics": len(slide.get("topics") or []) if "topics" in slide else None,
                "bullets": len(slide.get("bullets") or []) if "bullets" in slide else None,
                "items": len(slide.get("items") or []) if "items" in slide else None,
                "left": isinstance(slide.get("left"), dict) if "left" in slide else None,
                "right": isinstance(slide.get("right"), dict) if "right" in slide else None,
                "schedule_rows": len(slide.get("schedule_rows") or []) if "schedule_rows" in slide else None,
                "network_paths": [
                    len(path.get("activities") or []) if isinstance(path, dict) else -1
                    for path in network_paths or []
                ] if "network_paths" in slide else None,
                "image_path": str(((slide.get("image") or {}).get("path") or "")),
            }
        )
    return result


def pptx_structure(path: Path) -> dict[str, Any]:
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            slide_names = sorted(
                (name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"\d+", name).group()),
            )
            presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
            size = presentation.find(f"{{{PRESENTATION_NS}}}sldSz")
            slide_size = (
                int(size.attrib.get("cx", "0")) if size is not None else 0,
                int(size.attrib.get("cy", "0")) if size is not None else 0,
            )
            slides = []
            for name in slide_names:
                root = ElementTree.fromstring(archive.read(name))
                slides.append(
                    {
                        "shapes": len(root.findall(f".//{{{PRESENTATION_NS}}}sp")),
                        "pictures": len(root.findall(f".//{{{PRESENTATION_NS}}}pic")),
                        "graphic_frames": len(root.findall(f".//{{{PRESENTATION_NS}}}graphicFrame")),
                        "connectors": len(root.findall(f".//{{{PRESENTATION_NS}}}cxnSp")),
                    }
                )
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError) as error:
        raise LocalizedDeckIntegrityError(f"Presentation file is unreadable: {path.name}.") from error
    return {"slide_size": slide_size, "slides": slides}


def pptx_visible_text(path: Path) -> list[dict[str, Any]]:
    """Extract learner-visible text by slide and shape/table container."""
    results: list[dict[str, Any]] = []
    try:
        with ZipFile(path) as archive:
            slide_names = sorted(
                (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"\d+", name).group()),
            )
            for slide_number, name in enumerate(slide_names, start=1):
                root = ElementTree.fromstring(archive.read(name))
                containers = [
                    *root.findall(f".//{{{PRESENTATION_NS}}}sp"),
                    *root.findall(f".//{{{PRESENTATION_NS}}}graphicFrame"),
                ]
                for container in containers:
                    text = " ".join(
                        (node.text or "").strip()
                        for node in container.findall(f".//{{{DRAWING_NS}}}t")
                        if (node.text or "").strip()
                    )
                    if text:
                        results.append({"slide": slide_number, "text": re.sub(r"\s+", " ", text).strip()})
    except (BadZipFile, KeyError, ElementTree.ParseError, OSError) as error:
        raise LocalizedDeckIntegrityError(f"Presentation text is unreadable: {path.name}.") from error
    return results


def untranslated_english_findings(path: Path) -> list[dict[str, Any]]:
    """Return high-confidence English leakage in a PT-BR or ES-419 PPTX."""
    findings: list[dict[str, Any]] = []
    for item in pptx_visible_text(path):
        text = item["text"]
        domain_hits = sorted({match.group(0).lower() for match in ENGLISH_DOMAIN_TERMS.finditer(text)})
        grammar_hits = sorted({match.group(0).lower() for match in ENGLISH_GRAMMAR_TERMS.finditer(text)})
        # Construction schedule durations such as `1d` and `15d` are
        # locale-neutral data labels, not English prose.  Treating them as
        # untranslated text blocked otherwise complete activity-network
        # slides in both supported locales.
        if domain_hits or len(grammar_hits) >= 2:
            findings.append(
                {
                    "slide": item["slide"],
                    "text": text,
                    "hits": [*domain_hits, *grammar_hits],
                }
            )
    return findings


def assert_no_untranslated_english(path: Path) -> None:
    findings = untranslated_english_findings(path)
    if not findings:
        return
    preview = "; ".join(
        f"slide {item['slide']}: {item['text'][:120]} (matched: {', '.join(item['hits'])})"
        for item in findings[:5]
    )
    raise LocalizedDeckIntegrityError(
        "The localized presentation contains likely untranslated English learner-visible text: " + preview
    )


def validate_localized_deck(run: Path, lesson_tag: str, localized_deck: Path) -> dict[str, str]:
    localized_deck = localized_deck.resolve()
    if not localized_deck.is_file():
        raise LocalizedDeckIntegrityError("The localized presentation file is missing.")
    operator_approved = localized_approval_matches(run, lesson_tag, localized_deck)
    approved_deck, source_spec_path, source = approved_deck_source(run, lesson_tag)
    localized_spec_path_value = localized_spec_path(run, lesson_tag, localized_deck)
    if not localized_spec_path_value.is_file():
        raise LocalizedDeckIntegrityError(
            f"The localized presentation has no matching spec: {localized_spec_path_value.name}."
        )
    try:
        localized = json.loads(localized_spec_path_value.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LocalizedDeckIntegrityError(
            f"The localized presentation spec is invalid: {localized_spec_path_value.name}."
        ) from error

    output_path = _resolve_run_path(run, str((localized.get("output") or {}).get("pptx") or ""))
    if output_path != localized_deck:
        raise LocalizedDeckIntegrityError("The localized presentation does not match its render spec.")

    approved_relative = str(approved_deck.resolve().relative_to(run.resolve()))
    provenance = localized.get("source_provenance") or {}
    recorded_baseline = str(
        provenance.get("approved_deck_path") or localized.get("approved_baseline_artifact") or ""
    ).strip()
    if recorded_baseline and _resolve_run_path(run, recorded_baseline) != approved_deck.resolve():
        raise LocalizedDeckIntegrityError(
            "The localized presentation was not generated from the currently approved English presentation."
        )
    if not recorded_baseline and (
        provenance or not localized_approval_matches(run, lesson_tag, localized_deck)
    ):
        raise LocalizedDeckIntegrityError(
            "The localized presentation was not generated from the currently approved English presentation."
        )
    recorded_source_spec = str(provenance.get("approved_deck_spec") or "").strip()
    if recorded_source_spec and _resolve_run_path(run, recorded_source_spec) != source_spec_path.resolve():
        raise LocalizedDeckIntegrityError(
            "The localized presentation points to a different English deck spec than the approved presentation."
        )
    expected_source_hash = str(provenance.get("approved_deck_sha256") or "").strip()
    actual_source_hash = file_sha256(approved_deck)
    if expected_source_hash and expected_source_hash != actual_source_hash:
        raise LocalizedDeckIntegrityError("The approved English presentation changed after localization.")
    expected_spec_hash = str(provenance.get("approved_deck_spec_sha256") or "").strip()
    actual_spec_hash = file_sha256(source_spec_path)
    if expected_spec_hash and expected_spec_hash != actual_spec_hash:
        raise LocalizedDeckIntegrityError("The approved English deck spec changed after localization.")

    if spec_structure(source.get("slides")) != spec_structure(localized.get("slides")):
        raise LocalizedDeckIntegrityError(
            "The localized presentation changed the approved slide structure or layout sequence."
        )
    if pptx_structure(approved_deck) != pptx_structure(localized_deck):
        raise LocalizedDeckIntegrityError(
            "The localized PPTX does not preserve the approved presentation's slide structure."
        )
    # Automatic content rules can become stricter over time. An explicit
    # operator approval remains the final content decision for that exact file;
    # provenance and structural integrity checks above still apply.
    if not operator_approved:
        assert_no_untranslated_english(localized_deck)
    return {
        "approved_deck_path": approved_relative,
        "approved_deck_sha256": actual_source_hash,
        "approved_deck_spec": str(source_spec_path.resolve().relative_to(run.resolve())),
        "approved_deck_spec_sha256": actual_spec_hash,
        "localized_deck_sha256": file_sha256(localized_deck),
    }


def assert_localized_deck_matches_approved_source(run: Path, lesson_tag: str, localized_deck: Path) -> None:
    validate_localized_deck(run, lesson_tag, localized_deck)


def localized_deck_context(path: Path, runs_root: Path) -> tuple[Path, str] | None:
    resolved = path.resolve()
    root = runs_root.resolve()
    if root not in resolved.parents:
        return None
    relative = resolved.relative_to(root)
    if len(relative.parts) < 4 or relative.parts[1] != "localization" or relative.parts[2] not in {"pt-br", "es-419"}:
        return None
    match = re.fullmatch(r"(lesson_\d+)_deck_(?:pt_br|es)_r\d+\.pptx", resolved.name)
    if not match:
        return None
    return root / relative.parts[0], match.group(1)
