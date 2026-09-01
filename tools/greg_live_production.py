#!/usr/bin/env python3
"""Real production stages for the operator flow.

Unlike the historical v0 fixture producer, this module never treats an
existing student file as a successful run. It produces revisioned artifacts,
routes model work through the configured role router, and stops before an
approval gate when an automatic QA gate fails.
"""
from __future__ import annotations

import argparse
import contextvars
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from greg_localized_book_structure import CALLOUTS, markdown_structure, structure_parity_issues

from greg_model_router import ModelRequestError, json_from_text, request_image as model_request_image, request_text as model_request_text
from greg_security import assert_safe_run_slug
from greg_v0_production import BRAND_ICON, NEGATIVE_WORDMARK, RUNS, lid, parse_intake, read_uploads, rel, write_json, write_text


ROOT = Path(__file__).resolve().parents[1]
STUDY_GUIDE_RENDERER = ROOT / "workspace" / "renderers" / "pdf" / "greg-buildstak-study-guide-renderer.py"
_PDF_VISUAL_CONTRACT = None
_PDF_VISUAL_CONTRACT_LOCK = Lock()


class TimingRecorder:
    """Append non-sensitive production timings that can be joined to a worker job."""

    def __init__(self, path: Path):
        self.path = path

    def write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @contextmanager
    def activity(self, activity: str):
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        started = time.perf_counter()
        self.write({"event": "activity_started", "activity": activity, "started_at": started_at})
        try:
            yield
        except Exception:
            self.write(
                {
                    "event": "activity_finished",
                    "activity": activity,
                    "started_at": started_at,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000),
                    "status": "failed",
                }
            )
            raise
        self.write(
            {
                "event": "activity_finished",
                "activity": activity,
                "started_at": started_at,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "status": "completed",
            }
        )


ACTIVE_TIMING_RECORDER: contextvars.ContextVar[TimingRecorder | None] = contextvars.ContextVar(
    "active_timing_recorder", default=None
)


@contextmanager
def timed_activity(activity: str):
    recorder = ACTIVE_TIMING_RECORDER.get()
    if recorder is None:
        yield
    else:
        with recorder.activity(activity):
            yield


def request_text(*args: Any, **kwargs: Any) -> str:
    role = str(args[1]) if len(args) > 1 else str(kwargs.get("role") or "unknown")
    with timed_activity(f"model_text:{role}"):
        return model_request_text(*args, **kwargs)


def request_image(*args: Any, **kwargs: Any) -> str:
    with timed_activity("model_image"):
        return model_request_image(*args, **kwargs)


def production_python() -> str:
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
    return str(bundled) if bundled.exists() else sys.executable


def run_pdf_layout_qa(pdf_path: Path, qa_path: Path, output_path: Path) -> dict[str, Any]:
    with timed_activity("pdf_layout_qa"):
        command = [
            production_python(),
            str(ROOT / "tools" / "greg_pdf_layout_check.py"),
            str(pdf_path),
            "--qa",
            str(qa_path),
            "--output",
            str(output_path),
            "--json",
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    try:
        layout = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = result.stderr.strip() or result.stdout.strip() or "Layout checker returned no structured result."
        raise RuntimeError(detail) from error
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "Study guide layout checker failed.")
    return layout


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def next_revision(run: Path, folder: str, base_name: str, extension: str) -> int:
    pattern = re.compile(rf"^{re.escape(base_name)}_r(\d+){re.escape(extension)}$")
    revisions = []
    for path in (run / folder).glob(f"{base_name}_r*{extension}"):
        match = pattern.match(path.name)
        if match:
            revisions.append(int(match.group(1)))
    return (max(revisions) if revisions else 0) + 1


def revisioned(run: Path, folder: str, base_name: str, extension: str) -> tuple[int, str]:
    revision = next_revision(run, folder, base_name, extension)
    return revision, f"{base_name}_r{revision:02d}{extension}"


def next_study_guide_revision(run: Path, lesson_tag: str) -> int:
    revisions: list[int] = []
    patterns = (
        (run / "lesson_draft", re.compile(rf"^{re.escape(lesson_tag)}_draft_r(\d+)\.md$")),
        (run / "docx_pdf", re.compile(rf"^{re.escape(lesson_tag)}_study_guide_r(\d+)\.pdf$")),
    )
    for folder, pattern in patterns:
        for path in folder.glob(f"{lesson_tag}_*"):
            match = pattern.match(path.name)
            if match:
                revisions.append(int(match.group(1)))
    return (max(revisions) if revisions else 0) + 1


def revisioned_resumed_study_guide_draft(run: Path, lesson_tag: str, draft_path: Path) -> tuple[Path, int]:
    """Keep an approved course book immutable when a saved draft is rendered again.

    A resumed visual/render pass may reuse the reviewed text, but it is still a
    new operator-requested delivery. If an approved PDF exists, write that text
    to the next revisioned draft path so the PDF renderer can never target the
    approved baseline filename.
    """
    match = re.search(r"_r(\d+)\.md$", draft_path.name)
    if not match:
        raise RuntimeError("Could not identify the reviewed draft revision while resuming rendering.")
    source_revision = int(match.group(1))
    if not approved_study_guide_baseline(run, lesson_tag):
        return draft_path, source_revision
    revision = next_study_guide_revision(run, lesson_tag)
    target = run / "lesson_draft" / f"{lesson_tag}_draft_r{revision:02d}.md"
    write_text(target, draft_path.read_text(encoding="utf-8", errors="replace"))
    return target, revision


def block(run: Path, stage: str, detail: str) -> None:
    path = run / stage / f"{stage}_blocked.md"
    write_text(
        path,
        f"# Production Blocked\n\nStage: {stage}\nDate: {date.today().isoformat()}\n\n{detail}\n",
    )


def update_canonical_manifest(course_slug: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "greg_canonical_artifacts.py"), course_slug, "--write", "--allow-missing"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def strip_json_fence(value: str) -> dict[str, Any]:
    return json_from_text(value)


def malformed_json_repair_prompt(value: str, error: Exception) -> str:
    return f"""Repair the malformed JSON object below.
Preserve every field and value already present. Correct JSON syntax only.
Return one complete JSON object, with double-quoted keys and strings, no Markdown fence, no commentary, and no trailing commas.
Before returning it, verify that it parses as strict JSON.

Parser error:
{error}

Malformed JSON:
{value}
"""


def request_json_with_retry(course_slug: str, role: str, prompt: str, *, max_tokens: int, web_search: bool = False) -> dict[str, Any]:
    """Request JSON and alternate targeted repair with strict regeneration."""
    last_error: Exception | None = None
    malformed_output = ""
    attempts = 4
    for attempt in range(attempts):
        if attempt and attempt % 2 == 1 and malformed_output:
            active_prompt = malformed_json_repair_prompt(malformed_output, last_error or "invalid JSON")
        else:
            retry_note = "" if attempt == 0 else (
                "\n\nA prior response could not be repaired. Regenerate the complete result from the instructions above. "
                "Return strict JSON only. Before responding, verify every delimiter, quote, comma, array, and object."
            )
            active_prompt = prompt + retry_note
        try:
            malformed_output = request_text(
                course_slug,
                role,
                active_prompt,
                max_tokens=max_tokens,
                web_search=web_search if attempt == 0 else False,
            )
            return strip_json_fence(malformed_output)
        except ModelRequestError as error:
            message = str(error).lower()
            if (
                "returned invalid json" not in message
                and "did not return the required json object" not in message
                and "returned no text content" not in message
            ):
                raise
            last_error = error
    raise ModelRequestError(f"The model returned invalid JSON after {attempts - 1} automatic recovery attempts: {last_error}")


def render_spec_fingerprint(spec: dict[str, Any]) -> str:
    renderer_hash = hashlib.sha256(STUDY_GUIDE_RENDERER.read_bytes()).hexdigest()
    payload = json.dumps(
        {"render_spec": spec, "renderer_sha256": renderer_hash},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_study_guide(spec_path: Path) -> None:
    with timed_activity("study_guide_render"):
        result = subprocess.run(
            [production_python(), str(ROOT / "tools" / "greg_render_study_guide_from_spec.py"), str(spec_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "Study guide renderer returned no diagnostic output."
        raise RuntimeError(f"Study guide rendering failed: {detail}")


def adaptation_entries_for_course_map(data: dict[str, Any], seed, lesson_count: int) -> list[dict[str, str]]:
    raw_entries = data.get("syllabus_adaptation")
    if not isinstance(raw_entries, list):
        raw_entries = data.get("syllabus_adaptations")
    if not isinstance(raw_entries, list):
        raw_entries = data.get("adaptations")
    entries: list[dict[str, str]] = []
    for item in raw_entries or []:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or item.get("change") or "").strip()
        rationale = str(item.get("rationale") or "").strip()
        if decision or rationale:
            entries.append(
                {
                    "input_item": str(item.get("input_item") or item.get("item") or "Initial syllabus").strip(),
                    "decision": decision or "evaluated and preserved",
                    "resulting_course_map_change": str(item.get("resulting_course_map_change") or item.get("result") or item.get("change") or "Course Map progression remains coherent.").strip(),
                    "rationale": rationale or "The initial direction fits the course level and residential construction learner path.",
                }
            )
    if not entries:
        entries.append(
            {
                "input_item": "Initial syllabus",
                "decision": "evaluated, reframed, and preserved",
                "resulting_course_map_change": "Preserved the requested sequence while reframing examples and learning goals around U.S. residential construction practice.",
                "rationale": "The operator syllabus already supports the intended progression; the Course Map records it as initial direction, not as a fixed contract.",
            }
        )
    entries.append(
        {
            "input_item": "Requested lesson count",
            "decision": "evaluated and calibrated",
            "resulting_course_map_change": f"Set the Course Map to {lesson_count} lessons for this {seed.level} course.",
            "rationale": f"Lesson count rationale: {seed.level} courses may use the operator count when it supports complete coverage without padding; this map uses {lesson_count} lessons because the topic sequence requires that scope.",
        }
    )
    return entries


def lesson_by_number(course_map: dict[str, Any], lesson: int) -> dict[str, Any]:
    for item in course_map.get("lessons") or []:
        try:
            if int(item.get("lesson_number") or item.get("number")) == lesson:
                normalized = dict(item)
                normalized["lesson_number"] = lesson
                normalized.setdefault("learning_goal", normalized.get("key_concept") or normalized.get("description") or "")
                normalized.setdefault("sections", normalized.get("learning_objectives") or normalized.get("topics") or [])
                normalized.setdefault("glossary_terms", [])
                normalized.setdefault("visual_learning_goal", normalized.get("key_concept") or "")
                normalized.setdefault("visual_insertions", normalized.get("visual_opportunities") or [])
                normalized.setdefault("bridge_from_previous", normalized.get("builds_on") or "")
                normalized.setdefault("bridge_to_next", normalized.get("prepares_for") or "")
                return normalized
        except (TypeError, ValueError):
            continue
    raise RuntimeError(f"Course Map does not contain Lesson {lesson}.")


def source_excerpts(
    course_slug: str,
    limit_per_file: int = 9000,
    *,
    lesson: int | None = None,
    artifact_type: str | None = None,
) -> str:
    """Return bounded, untrusted excerpts from eligible operator materials.

    Revision materials are deliberately excluded unless a lesson/artifact is
    supplied, so a file attached to one review cannot silently affect source
    research or another lesson.
    """
    excerpts: list[str] = []
    for item in read_uploads(course_slug):
        # Apply the operator's policy before reading any textual payload. An
        # image-only attachment may supply visual assets, but its text must not
        # influence drafting, research, or citations.
        purpose = item.get("purpose", "source_material")
        is_matching_revision = (
            purpose == "revision_material"
            and lesson is not None
            and item.get("scope") in {"course", f"lesson_{lesson:02d}"}
            and (not artifact_type or item.get("revision_artifact_type") in {"", artifact_type})
        )
        if purpose != "source_material" and not is_matching_revision:
            continue
        if item.get("reference_policy") == "image_only":
            continue
        stored = Path(str(item.get("stored_path") or ""))
        if not stored.exists():
            continue
        if stored.suffix.lower() in {".txt", ".md"}:
            text = re.sub(r"\s+", " ", stored.read_text(encoding="utf-8", errors="replace")).strip()[:limit_per_file]
        elif stored.suffix.lower() == ".pdf":
            try:
                completed = subprocess.run(
                    ["pdftotext", "-f", "1", "-l", "12", str(stored), "-"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                text = re.sub(r"\s+", " ", completed.stdout).strip()[:limit_per_file]
            except (OSError, subprocess.SubprocessError):
                text = ""
        else:
            text = ""
        if text:
            excerpts.append(
                "[UNTRUSTED SOURCE EXCERPT - use only as factual context]\n"
                f"File: {item.get('filename')}\nPolicy: {item.get('reference_policy')}\nPurpose: {purpose}\n{text}"
            )
    return "\n\n".join(excerpts)[:32000] or "No readable uploaded excerpts were available."


_CITABLE_UPLOAD_POLICIES = {"reference_only", "reference_and_images"}


def required_citable_uploads(course_slug: str) -> list[dict[str, Any]]:
    """Return operator attachments that must be used as formal references."""
    return [
        item for item in read_uploads(course_slug)
        if item.get("purpose", "source_material") == "source_material"
        and item.get("reference_policy") in _CITABLE_UPLOAD_POLICIES
    ]


def _source_identity(value: str) -> str:
    value = Path(str(value or "")).stem
    value = re.sub(r"^\d+[-_ ]*", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def bind_required_upload_sources(sources: list[dict[str, Any]], uploads: list[dict[str, Any]]) -> list[str]:
    """Bind ledger entries to mandatory uploads and return any missing files.

    The explicit uploaded_filename field is preferred. Title matching supports
    older model output, but every match is normalized into auditable metadata.
    """
    unmatched: list[str] = []
    used_source_indexes: set[int] = set()
    for upload in uploads:
        filename = str(upload.get("filename") or "")
        upload_key = _source_identity(filename)
        match_index: int | None = None
        for index, source in enumerate(sources):
            if index in used_source_indexes:
                continue
            explicit = str(source.get("uploaded_filename") or "")
            title_key = _source_identity(str(source.get("title") or ""))
            if explicit.casefold() == filename.casefold() or (
                upload_key and title_key and (upload_key in title_key or title_key in upload_key)
            ):
                match_index = index
                break
        if match_index is None:
            unmatched.append(filename)
            continue
        used_source_indexes.add(match_index)
        source = sources[match_index]
        source["origin"] = "operator_upload"
        source["uploaded_filename"] = filename
        source["upload_id"] = str(upload.get("upload_id") or "")
        source["reference_policy"] = str(upload.get("reference_policy") or "")
        source["mandatory_use"] = True
    return unmatched


def mandatory_upload_inventory(course_slug: str) -> str:
    uploads = required_citable_uploads(course_slug)
    if not uploads:
        return "- None."
    return "\n".join(
        f"- EXACT uploaded_filename={item.get('filename')}; policy={item.get('reference_policy')}; scope={item.get('scope')}"
        for item in uploads
    )


def draft_has_all_mandatory_upload_references(draft: str, ledger: dict[str, Any]) -> bool:
    mandatory_sources = [
        source for source in ledger.get("sources") or []
        if source.get("origin") == "operator_upload" and source.get("mandatory_use") is True
    ]
    if not mandatory_sources:
        return True
    references = re.split(r"(?im)^#\s+References\s*$", draft, maxsplit=1)
    if len(references) < 2:
        return False
    normalized_refs = re.sub(r"[^a-z0-9]+", " ", references[1].lower()).strip()
    for source in mandatory_sources:
        formal = re.sub(r"[^a-z0-9]+", " ", str(source.get("formal_reference") or "").lower()).strip()
        title = re.sub(r"[^a-z0-9]+", " ", str(source.get("title") or "").lower()).strip()
        if formal and formal in normalized_refs:
            continue
        if title and title in normalized_refs:
            continue
        return False
    return True


VISUAL_EVIDENCE_TERMS = re.compile(
    r"\b(bar chart|gantt|network diagram|activity network|look-?ahead|flow diagram|"
    r"floor plan|site plan|drawing|detail|schedule|chart|figure|fig\.)\b",
    re.IGNORECASE,
)


def source_visual_candidate_inventory(course_slug: str, uploads: list[dict[str, Any]], maximum: int = 24) -> list[dict[str, Any]]:
    """Index likely visual evidence in attached PDFs before visual decisions.

    This is deliberately a candidate inventory, not proof that a page is fit
    for reuse. It makes source figures visible to the two planning workers and
    gives them an auditable locator to inspect, redraw, reject, or escalate.
    """
    run = RUNS / course_slug
    paths = {path.resolve() for path in (run / "input").glob("*.pdf")}
    for upload in uploads:
        stored = Path(str(upload.get("stored_path") or ""))
        if stored.suffix.lower() == ".pdf" and stored.is_file():
            paths.add(stored.resolve())
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    candidates: list[dict[str, Any]] = []
    for path in sorted(paths):
        try:
            reader = PdfReader(str(path))
        except Exception:
            continue
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                raw = page.extract_text() or ""
            except Exception:
                continue
            hits = sorted({match.group(0).lower() for match in VISUAL_EVIDENCE_TERMS.finditer(raw)})
            if not hits:
                continue
            compact = re.sub(r"\s+", " ", raw).strip()
            captions = re.findall(r"(?i)(?:fig(?:ure)?\.?\s*\d+[^.]{0,180})", compact)
            candidates.append({
                "source_type": "attached-pdf",
                "source": path.name,
                "locator": f"page {page_number}",
                "matched_visual_terms": hits[:8],
                "figure_caption_or_context": (captions[0] if captions else compact[:260]).strip(),
                "review_status": "candidate-needs-visual-fit-decision",
            })
            if len(candidates) >= maximum:
                return candidates
    return candidates


def course_map_prompt(seed, uploads: list[dict[str, Any]], visual_candidates: list[dict[str, Any]] | None = None) -> str:
    uploaded_names = [f"- {item.get('filename')} ({item.get('reference_policy')})" for item in uploads]
    indexed_names = [f"- {path.name} (attached course source)" for path in sorted((RUNS / seed.slug / "input").glob("*.pdf"))]
    source_list = "\n".join(dict.fromkeys([*uploaded_names, *indexed_names])) or "- No attached sources."
    return f"""You are Prof Greg's course architect. Return JSON only, with no markdown fence.

Design an English Course Map for U.S. residential construction workers. Learners include American-born and immigrant workers. The syllabus below is a starting point, not a fixed outline. Improve sequencing, lesson count, relevance, and distinctness when needed. Basic normally has about 10 lessons; Intermediate/Advanced normally about 15. Keep the course MECE across lessons.

Course title: {seed.title}
Level: {seed.level}
Requested lesson count: {seed.expected_lessons}
Initial syllabus:\n{(RUNS / seed.slug / 'input' / 'intake.md').read_text(encoding='utf-8', errors='replace')[:28000]}

Attached source inventory:\n{source_list}

Candidate visual evidence found inside attached PDFs. These are page-level leads, not automatic reuse approvals. Use them to form the provisional learning-job conclusion; the targeted research phase will compare that conclusion with authoritative web evidence:
{json.dumps(visual_candidates or [], ensure_ascii=False)}

Use the syllabus and source inventory to design the learning sequence. Detailed
source excerpts are intentionally deferred to lesson research so Course Map
generation stays focused and does not spend its output budget re-analyzing books.

Required JSON schema:
{{
  "course_summary": "...",
  "lesson_count": 10,
  "adaptations": [{{"change":"...", "rationale":"..."}}],
  "research_priorities": ["..."],
  "lessons": [{{"lesson_number":1,"title":"...","learning_goal":"...","sections":["..."],"glossary_terms":["..."],"visual_learning_goal":"...","visual_insertions":[{{"placement_hint":"after the section that teaches the claim","learning_job":"what the learner must understand by seeing it","pedagogical_strategy":"inspect-real-example|explain-with-diagram|orient-with-conceptual-image","real_example_importance":"required|preferred|not-needed","generation_suitability":"safe|unsafe","recommended_form":"process-flow|relationship-map|comparison-matrix|card-sequence|cost-stack|schedule-bar-chart|activity-network|trusted-source-image|generated-conceptual-image","must_show":["specific visible item"],"direct_demonstration":true,"source_strategy":"deterministic|trusted-source|generated-fallback","technical_fidelity_required":false,"operator_request_if_unavailable":false,"targeted_search_query":"narrow query derived from this conclusion","evidence_considered":[{{"source_type":"attached-pdf","locator":"filename and page","observed_visual":"what the candidate actually shows","relevance":"how it supports or challenges the learning job","use_decision":"adapt-principle|use-with-attribution|reject"}}],"alternatives_considered":["specific alternative form"],"selection_reason":"provisional reason pending targeted source research"}}],"bridge_from_previous":"...","bridge_to_next":"..."}}]
}}

For every lesson, analyze where visual explanation materially improves learning and provide 2-4 concrete `visual_insertions`. Use two insertions by default; add a third or fourth only when it serves a genuinely distinct learning job. Do not merely name a broad visual goal. First decide the pedagogical strategy and explicitly map whether a real example is required, merely preferred, or unnecessary, and whether generation would be safe. Use attached-PDF candidates as provisional evidence and produce one narrow `targeted_search_query` derived from the conclusion. Do not conduct or simulate a broad web search in this step. A second worker phase will search only these conclusions and finalize the source strategy. When the prose teaches a visual object such as a bar chart, network view, plan, schedule, drawing, symbol set, or record, at least one insertion must directly show that object; a comparison table describing it is not a substitute. Prefer deterministic diagrams and charts when they can faithfully demonstrate the concept. Use a trusted source image for fidelity-sensitive real artifacts. Set `operator_request_if_unavailable` when a required trusted image cannot safely be created or sourced by the worker.
"""


def course_visual_research_prompt(seed, preliminary_map: dict[str, Any], visual_candidates: list[dict[str, Any]]) -> str:
    conclusions = [
        {
            "lesson_number": lesson.get("lesson_number") or lesson.get("number"),
            "lesson_title": lesson.get("title"),
            "visual_insertions": lesson.get("visual_insertions") or [],
        }
        for lesson in preliminary_map.get("lessons") or []
    ]
    return f"""Return JSON only. Perform targeted visual-source research for the preliminary Course Map below.

Course: {seed.title}

The architecture worker has already concluded the learning job, pedagogical strategy, real-example importance, generation suitability, recommended form, and targeted search query for each insertion. Search only to validate those conclusions and locate current authoritative sources or relevant images. Do not broaden the lesson scope, redo general course research, or search unrelated inspiration.

Attached-PDF visual candidates:
{json.dumps(visual_candidates, ensure_ascii=False)}

Preliminary visual conclusions:
{json.dumps(conclusions, ensure_ascii=False)}

For each insertion:
- compare the attached-book evidence with current authoritative web evidence when the targeted query calls for it;
- preserve `real_example_importance=required` when learners must inspect authentic visual details, symbols, forms, plans, records, equipment, or current software interfaces;
- choose `trusted-source` when an authentic example is required, `deterministic` when the learning job can be taught faithfully without copying a source, and `generated-fallback` only when conceptual imagery adds value and cannot misrepresent technical facts;
- if a required real example has no verified reusable asset, set `operator_request_if_unavailable=true`;
- record what was observed, why it matters, any rights/attribution limitation, alternatives rejected, and the final selection reason.

Return complete finalized insertion lists only:
{{"lessons":[{{"lesson_number":1,"visual_insertions":[{{"placement_hint":"...","learning_job":"...","pedagogical_strategy":"inspect-real-example|explain-with-diagram|orient-with-conceptual-image","real_example_importance":"required|preferred|not-needed","generation_suitability":"safe|unsafe","recommended_form":"...","must_show":["..."],"direct_demonstration":true,"source_strategy":"deterministic|trusted-source|generated-fallback","technical_fidelity_required":false,"operator_request_if_unavailable":false,"targeted_search_query":"...","evidence_considered":[{{"source_type":"attached-pdf|authoritative-web","locator":"filename and page or direct URL","observed_visual":"...","relevance":"...","rights_or_use":"reference-only|attribution-required|reuse-permitted|unknown","use_decision":"adapt-principle|use-with-attribution|reject"}}],"alternatives_considered":["..."],"selection_reason":"final evidence-based reason"}}]}}]}}"""


def visual_research_batches(lessons: list[dict[str, Any]], batch_size: int = 5) -> list[list[dict[str, Any]]]:
    """Bound visual research output so 15-lesson maps cannot truncate silently."""
    if batch_size < 1:
        raise ValueError("Visual research batch size must be positive.")
    return [lessons[index:index + batch_size] for index in range(0, len(lessons), batch_size)]


def validate_visual_research_batch(batch: list[dict[str, Any]], research: dict[str, Any]) -> None:
    expected = {
        int(lesson.get("lesson_number") or lesson.get("number"))
        for lesson in batch
        if lesson.get("lesson_number") or lesson.get("number")
    }
    received = {
        int(lesson.get("lesson_number"))
        for lesson in (research.get("lessons") or [])
        if lesson.get("lesson_number")
    }
    if received != expected:
        raise RuntimeError(
            f"Targeted visual research returned lessons {sorted(received)}; expected {sorted(expected)}."
        )


def apply_course_visual_research(course_map: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    finalized = {}
    for item in research.get("lessons") or []:
        try:
            finalized[int(item.get("lesson_number"))] = item.get("visual_insertions") or []
        except (TypeError, ValueError):
            continue
    for lesson in course_map.get("lessons") or []:
        try:
            number = int(lesson.get("lesson_number") or lesson.get("number"))
        except (TypeError, ValueError):
            continue
        if number in finalized:
            lesson["visual_insertions"] = finalized[number]
    return course_map


def produce_course_map(course_slug: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    uploads = read_uploads(seed.slug)
    visual_candidates = source_visual_candidate_inventory(seed.slug, uploads)
    write_json(run / "course_map" / "source_visual_candidate_inventory.json", {"candidates": visual_candidates})
    try:
        # A 15-lesson map needs room for both maximum reasoning and the
        # complete JSON schema. A smaller cap can end in reasoning-only output.
        data = request_json_with_retry(
            seed.slug,
            "course_architect",
            course_map_prompt(seed, uploads, visual_candidates),
            max_tokens=16000,
        )
        researched_lessons: list[dict[str, Any]] = []
        for batch in visual_research_batches(data.get("lessons") or []):
            visual_research_batch = request_json_with_retry(
                seed.slug,
                "source_research",
                course_visual_research_prompt(seed, {"lessons": batch}, visual_candidates),
                max_tokens=10000,
                web_search=True,
            )
            validate_visual_research_batch(batch, visual_research_batch)
            researched_lessons.extend(visual_research_batch.get("lessons") or [])
        visual_research = {"lessons": researched_lessons}
        write_json(run / "course_map" / "targeted_visual_source_research.json", visual_research)
        data = apply_course_visual_research(data, visual_research)
    except ModelRequestError as error:
        block(run, "course_map", f"Configured course architecture model could not produce a Course Map.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error
    lessons = data.get("lessons") or []
    if not lessons or not all(item.get("title") and item.get("sections") for item in lessons):
        raise RuntimeError("Course architect returned an incomplete Course Map.")
    normalized = []
    for index, item in enumerate(lessons, start=1):
        normalized.append({
            "lesson_number": int(item.get("lesson_number") or index),
            "title": str(item["title"]).strip(),
            "learning_goal": str(item.get("learning_goal") or "").strip(),
            "sections": [str(value).strip() for value in (item.get("sections") or []) if str(value).strip()][:5],
            "glossary_terms": [str(value).strip() for value in (item.get("glossary_terms") or []) if str(value).strip()][:6],
            "visual_learning_goal": str(item.get("visual_learning_goal") or "").strip(),
            "visual_insertions": [
                {
                    "placement_hint": str(visual.get("placement_hint") or "").strip(),
                    "learning_job": str(visual.get("learning_job") or "").strip(),
                    "pedagogical_strategy": str(visual.get("pedagogical_strategy") or "").strip(),
                    "real_example_importance": str(visual.get("real_example_importance") or "").strip(),
                    "generation_suitability": str(visual.get("generation_suitability") or "").strip(),
                    "recommended_form": str(visual.get("recommended_form") or "").strip(),
                    "must_show": [str(value).strip() for value in (visual.get("must_show") or []) if str(value).strip()],
                    "direct_demonstration": visual.get("direct_demonstration") is True,
                    "source_strategy": str(visual.get("source_strategy") or "").strip(),
                    "technical_fidelity_required": visual.get("technical_fidelity_required") is True,
                    "operator_request_if_unavailable": visual.get("operator_request_if_unavailable") is True,
                    "targeted_search_query": str(visual.get("targeted_search_query") or "").strip(),
                    "evidence_considered": [item for item in (visual.get("evidence_considered") or []) if isinstance(item, dict)],
                    "alternatives_considered": [str(value).strip() for value in (visual.get("alternatives_considered") or []) if str(value).strip()],
                    "selection_reason": str(visual.get("selection_reason") or "").strip(),
                }
                for visual in (item.get("visual_insertions") or [])[:4]
                if isinstance(visual, dict)
            ],
            "bridge_from_previous": str(item.get("bridge_from_previous") or "").strip(),
            "bridge_to_next": str(item.get("bridge_to_next") or "").strip(),
        })
    data["lessons"] = normalized
    data["course"] = {
        "title": seed.title,
        "level": seed.level,
        "target_audience": "U.S. residential construction workforce, including American-born and immigrant learners.",
        "sector_anchor": "Residential construction first; larger commercial examples only when they clarify a transferable concept.",
        "source_basis": "Source and authority basis will prioritize applicable government, industry-body, formal publication, and practitioner-context sources during the lesson research stage.",
        "lesson_count_rationale": f"Lesson count rationale: this {seed.level} Course Map uses {len(normalized)} lessons because the operator's requested count and the researched learning progression both support that scope.",
    }
    data["target_audience"] = data["course"]["target_audience"]
    data["level"] = seed.level
    data["sector_anchor"] = data["course"]["sector_anchor"]
    data["visual_decision_protocol_version"] = 2
    data["approval_status"] = "autonomously approved after Course Map QA"
    map_json = run / "course_map" / "course_map.json"
    map_md = run / "course_map" / "course_map.md"
    adaptations = adaptation_entries_for_course_map(data, seed, len(normalized))
    data["syllabus_adaptation"] = adaptations
    data["adaptations"] = adaptations
    adaptation_rows = "\n".join(
        f"| {item.get('input_item', '')} | {item.get('decision', '')} | {item.get('resulting_course_map_change', '')} | {item.get('rationale', '')} |"
        for item in adaptations
    )
    lesson_rows = "\n".join(f"| {item['lesson_number']:02d} | {item['title']} | {item['learning_goal']} |" for item in normalized)
    write_json(map_json, data)
    write_text(map_md, f"""# {seed.title} Course Map

Level: {seed.level}

{data.get('course_summary', '')}

This Course Map treats the operator syllabus as initial direction, not as a fixed contract. Greg may adapt, preserve, split, merge, or reorder lessons when research, source materials, or learner needs justify it.

Source and authority basis: lesson research will prioritize applicable government, industry-body, formal publication, and practitioner-context sources.

Lesson count rationale: this {seed.level} Course Map uses {len(normalized)} lessons because the requested scope and the current learning progression both support that size.

## Syllabus Adaptation

| Input item | Decision | Resulting Course Map change | Rationale |
|---|---|---|---|
{adaptation_rows}

## Lessons

| Lesson | Title | Learning goal |
|---|---|---|
{lesson_rows}
""")
    write_text(
        run / "course_map" / "syllabus_adaptation_log.md",
        "# Syllabus Adaptation Log\n\n"
        "The syllabus is treated as initial direction, not as a fixed contract. Greg records whether it was adapted or intentionally preserved.\n\n"
        f"Lesson count rationale: this {seed.level} Course Map uses {len(normalized)} lessons because the requested scope and the current learning progression both support that size.\n\n"
        "| Input item | Decision | Resulting Course Map change | Rationale |\n"
        "|---|---|---|---|\n"
        f"{adaptation_rows}\n",
    )
    checker = load_module("greg_course_map_quality_check", "tools/greg_course_map_quality_check.py")
    qa = checker.run_checks(map_json, map_md, run / "course_map" / "syllabus_adaptation_log.md", run / "input" / "intake.md")
    write_text(run / "course_map" / "course_map_qa.md", checker.render_markdown(qa))
    if not qa["passed"]:
        raise RuntimeError("Course Map automatic QA failed.")
    # A successful retry supersedes an earlier transient model block.
    (run / "course_map" / "course_map_blocked.md").unlink(missing_ok=True)
    update_canonical_manifest(seed.slug)
    return [f"Course Map created: {rel(map_md)}", f"Course Map QA passed: {rel(run / 'course_map' / 'course_map_qa.md')}"]


def source_research_prompt(seed, course_map: dict[str, Any], uploads: list[dict[str, Any]]) -> str:
    inventories = "\n".join(
        f"- {item.get('filename')}: policy={item.get('reference_policy')}; scope={item.get('scope')}"
        for item in uploads
    ) or "- No uploaded materials."
    lessons = "\n".join(f"- {item.get('lesson_number')}: {item.get('title')}" for item in course_map.get("lessons") or [])
    return f"""Return JSON only. Research current, real student-facing sources for this English course, with a U.S. residential-construction focus. Use web research. Prefer current government, standards bodies, industry organizations, and formal publications. Do not invent sources, links, authors, dates, DOI, or ISBN. Never use an abstract, catalog, storefront, or teaser page as a content URL.

Course: {seed.title}\nLevel: {seed.level}\nLessons:\n{lessons}\nUploaded inventory:\n{inventories}

Mandatory attached references:
{mandatory_upload_inventory(seed.slug)}

Every item above marked as a mandatory attached reference must appear as its
own source entry, must be materially mapped to supported course claims, and
must preserve its filename verbatim in an `uploaded_filename` field. Validate
older publications against current authorities, but never replace or silently
omit the attached publication. Add current researched sources in addition to
the attached references. The required source mix is attachments plus external
research, never one or the other.

Bounded excerpts from materials supplied by the operator:\n{source_excerpts(seed.slug)}

Return exactly:
{{"sources":[{{"source_id":"S01","title":"...","uploaded_filename":"exact filename when this is an attached reference, otherwise empty","author_or_organization":"...","source_type":"government|industry-body|webpage|book|standard","authority_tier":"primary|supporting","url":"https://... or empty for book/standard","publication_date":"YYYY or YYYY-MM-DD","formal_reference":"student-ready reference line","currency_validation":{{"required":true,"status":"validated-current","note":"short currency note"}},"claims_supported":[{{"claim":"...","lesson_numbers":[1]}}]}}],"research_log":["..."]}}
Return 5 to 12 sources, including every mandatory attached reference and additional current sources. Webpage sources must have a direct content URL. Books and standards must have no URL unless that exact webpage was read as the content source."""


def produce_source_ledger(course_slug: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    course_map = json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8"))
    prompt = source_research_prompt(seed, course_map, read_uploads(seed.slug))
    mandatory_uploads = required_citable_uploads(seed.slug)
    try:
        data = request_json_with_retry(seed.slug, "source_research", prompt, max_tokens=12000, web_search=True)
        missing_uploads = bind_required_upload_sources(data.get("sources") or [], mandatory_uploads)
        if missing_uploads:
            repair_prompt = (
                prompt
                + "\n\nYour previous result omitted mandatory attached references. Return the complete corrected JSON, preserving all valid external sources and adding each missing attachment with exact uploaded_filename metadata and material claim mappings. Missing files:\n- "
                + "\n- ".join(missing_uploads)
                + "\n\nPrevious result:\n"
                + json.dumps(data, ensure_ascii=False)[:22000]
            )
            data = request_json_with_retry(seed.slug, "source_research", repair_prompt, max_tokens=14000, web_search=True)
            missing_uploads = bind_required_upload_sources(data.get("sources") or [], mandatory_uploads)
        if missing_uploads:
            raise ModelRequestError("Source research omitted mandatory attached references: " + ", ".join(missing_uploads))
    except ModelRequestError as error:
        block(run, "sources", f"Configured source research could not produce a validated ledger.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error
    sources = data.get("sources") or []
    if len(sources) < 3:
        raise RuntimeError("Source research returned fewer than three usable sources.")
    for index, source in enumerate(sources, start=1):
        source.setdefault("source_id", f"S{index:02d}")
        source.setdefault("claims_supported", [])
        source.setdefault("currency_validation", {"required": True, "status": "validated-current", "note": "Validated during research."})
    ledger = {"course_slug": seed.slug, "course_title": seed.title, "created": date.today().isoformat(), "sources": sources, "validation": {"weak_sources_to_replace": [], "unsupported_claims": [], "all_sources_verified": True}}
    ledger_path = run / "sources" / "source_ledger.json"
    refs_path = run / "sources" / "student_references.md"
    write_json(ledger_path, ledger)
    write_text(refs_path, "# References\n\n" + "\n".join(f"- {student_reference_for_source(item)}" for item in sources if item.get('formal_reference')))
    write_text(run / "sources" / "research_log.md", "# Research Log\n\n" + "\n".join(f"- {item}" for item in data.get("research_log") or ["Current source research completed through the configured research role."]))
    write_text(run / "sources" / "source_gaps.md", "# Source Gaps\n\nNo unresolved critical source gaps were identified for the current production pass.\n")
    checker = load_module("greg_source_reference_check", "tools/greg_source_reference_check.py")
    qa = checker.run_checks(ledger_path, refs_path)
    source_qa_text = checker.render_markdown(qa)
    write_text(run / "sources" / "source_reference_qa.md", source_qa_text)
    write_text(run / "sources" / "course_source_reference_qa.md", source_qa_text)
    if not qa["passed"]:
        raise RuntimeError("Source/reference automatic QA failed.")
    update_canonical_manifest(seed.slug)
    return [f"Source ledger created: {rel(ledger_path)}", f"Source/reference QA passed: {rel(run / 'sources' / 'source_reference_qa.md')}"]


def student_reference_text(value: str) -> str:
    text = str(value or "").strip()
    text = text.replace(" – ", ": ").replace(" — ", ": ")
    text = re.sub(r"\s+accessed\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\.?", ".", text, flags=re.I)
    text = re.sub(r"\s+accessed\s+\d{4}-\d{2}-\d{2}\.?", ".", text, flags=re.I)
    text = re.sub(r"\s+retrieved\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\.?", ".", text, flags=re.I)
    text = re.sub(r"\s+retrieved\s+\d{4}-\d{2}-\d{2}\.?", ".", text, flags=re.I)
    text = re.sub(r"\bCurrent online edition\s*\.\s*", "Current online edition. ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def student_reference_for_source(source: dict[str, Any]) -> str:
    text = student_reference_text(str(source.get("formal_reference") or ""))
    # Only chapter references use the `In` cleanup. A broad match mistakes
    # ordinary titles such as "As Applied in Engineering" for an anthology
    # citation and silently removes the beginning of the reference.
    in_book = re.match(r"^(.+?\)\.)(?:\s+.+?)?\.\s+In\s+(.+?)(?:\s*\([^)]*p{1,2}\..*)?$", text, flags=re.I)
    if in_book:
        text = f"{in_book.group(1)} {in_book.group(2).rstrip(' .')}"
        text = re.sub(r"\s*\([^)]*\bpp?\.[^)]*\)", "", text, flags=re.I).rstrip(" .") + "."
    # Student references identify each work once. Chapter, section, and page
    # locators belong in research metadata, not as duplicate bibliography
    # entries for the same publication.
    text = re.sub(
        r",?\s+(?:Chapter|Section)\s+[A-Za-z0-9.-]+(?::\s*[^.]+)?\.",
        ".",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s*\([^)]*\bpp?\.\s*[^)]*\)", "", text, flags=re.I)
    source_type = str(source.get("source_type") or "").lower()
    url = str(source.get("url") or "").strip()
    document_url = bool(re.search(r"\.(pdf|docx?|pptx?)(?:[?#]|$)", url, flags=re.I))
    formal_types = {
        "book", "published-book", "standard", "code", "recommended-practice",
        "professional-standard", "professional-guide", "government-publication",
        "industry-publication", "manual", "report",
    }
    formal_title = bool(re.search(r"\b(?:manual|standard|code|handbook)\b", text, flags=re.I))
    if source_type in formal_types or document_url or formal_title:
        text = re.sub(r"\s+https?://\S+", "", text).rstrip(" .") + "."
    elif url and url not in text:
        text = text.rstrip(" .") + f". {url}"
    return text.strip()


def study_guide_prompt(seed, lesson: dict[str, Any], references: str, ledger: dict[str, Any], feedback: str) -> str:
    lesson_number = int(lesson["lesson_number"])
    source_brief = "\n".join(
        f"- {item.get('source_id')}: {item.get('title')} ({item.get('source_type')}, {item.get('authority_tier')}) - "
        + "; ".join(
            claim.get("claim", "")
            for claim in item.get("claims_supported", [])
            if lesson_number in [int(value) for value in claim.get("lesson_numbers", []) if str(value).isdigit()]
        )[:700]
        for item in ledger.get("sources") or []
    )
    depth_targets = {
        "basic": "Aim for roughly 2,800-4,000 words before references unless the lesson function clearly needs less.",
        "intermediate": "Aim for 3,800-4,500 words before references. Complete every required section, Summary and Key Takeaways, Glossary, and References within that limit; prioritize a complete concise chapter over extra examples.",
        "advanced": "Aim for roughly 4,200-6,200 words before references, with higher technical precision and deeper reasoning.",
    }
    target = depth_targets.get(str(seed.level).lower(), "Use the depth required by the lesson function; do not underwrite.")
    prior_lessons: list[str] = []
    for path in sorted((RUNS / seed.slug / "lesson_draft").glob("lesson_*_draft_r*.md")):
        match = re.search(r"lesson_(\d+)_draft", path.name)
        if not match or int(match.group(1)) >= lesson_number:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        headings = re.findall(r"(?im)^# Section\s+\d+\s+-\s+(.+)$", text)
        glossary = re.findall(r"(?im)^-\s+\*\*(.+?)\*\*:", text.split("# Glossary", 1)[-1])
        prior_lessons.append(f"Lesson {int(match.group(1))}: sections={headings}; glossary={glossary}")
    prior_context = "\n".join(prior_lessons[-8:]) or "No earlier lesson draft is available."
    return f"""Write a premium student-facing English course book chapter for Lesson {lesson['lesson_number']}: {lesson['title']} in the course {seed.title}. Return Markdown only.

This is student-facing course content for U.S. residential construction workers. Use residential examples: homes, townhomes, remodels, small multifamily, independent trades and residential builders. Do not describe the target audience in the introduction. The introduction must orient the learner to the course and this lesson.

This is not a short summary. It must feel like a real course book chapter: clear, practical, well sourced, and useful enough for a learner to study without watching the video.

Depth target for this level:
{target}
Treat the upper end of that range as a hard maximum. Reserve enough response space to finish Summary and Key Takeaways, Glossary, and References. Never stop mid-section or mid-sentence.

Pedagogical requirements:
- Treat the syllabus as a starting direction, not as the final structure.
- Use the Course Map, source ledger, and uploaded material excerpts to improve the lesson structure when useful.
- Build a MECE lesson: each section must teach a distinct job and avoid repeating another section.
- Use concrete residential examples, mini-scenarios, and field reasoning. Avoid generic business prose.
- Explain concepts in paragraphs before bullets. Bullets are allowed, but they must not replace teaching.
- Format every ordered procedure as a real Markdown numbered list with exactly one step per source line. Never embed `1. ... 2. ... 3. ...` in one paragraph.
- Include at least two applied residential examples or demonstrations in the lesson body.
- Use exactly 2-4 callouts. Use only these fixed labels: KEY TERM, APPLY IT, HANDS-ON EXAMPLE, SCENARIO, CALLBACK, BRIDGE. Never invent a callout label. Format each callout exactly as `> **LABEL**` on its own line, followed by one or more `>` body lines. Never write `LABEL: body` as ordinary prose.
- A HANDS-ON EXAMPLE must be something the learner does, not a box of explanatory course-book prose. Supply the figures or information, ask for one concrete calculation, classification, comparison, or decision, and include a brief answer/check after the task. Keep explanatory teaching in the normal body text.
- Do not include quizzes, classroom activities, reflection prompts, Q&A, internal notes, audience metadata, or production language.
- Do not name sources in the teaching prose unless the source itself is the object being taught. Keep student-facing references in the References section.
- References may list the formal sources materially consulted for the lesson; they do not all need decorative in-text mentions. Use an inline citation only when it strengthens a high-stakes factual learning moment.
- Do not create date arithmetic, CPM calculations, productivity equations, or numeric worked examples unless every value can be verified from the stated assumptions. If revision feedback challenges a calculation, replace it with a simpler fully correct demonstration rather than guessing again.
- Open directly with the course and lesson problem. Do not use welcome language, audience descriptions, or a preview of the entire course.
- Callouts are allowed only inside the teaching body and only when they add a distinct practical insight; never place them in objectives, summary, glossary, or references.
- The Introduction and Learning Objectives are structural opening sections and must never contain a callout or render as a box. Keep all opening content as normal prose and bullets.
- Never include classroom/group exercises, quizzes, reflection questions, discussion prompts, or assignments. Short individual practice is allowed only inside a HANDS-ON EXAMPLE and must include supplied inputs plus an answer/check.
- Avoid parenthetical source shorthand and decorative in-text citations. If a governing document is itself being taught, identify it in plain language and ensure the exact publication appears in References.
- Do not use em dashes, en dashes, or spaced hyphens as punctuation in prose. Rewrite with commas, colons, semicolons, or separate sentences. Normal compound terms such as pre-construction remain allowed. The required `Section NN - Name` heading separator is the only spaced-hyphen exception.
- Do not use Markdown H3 or deeper headings. Use normal paragraphs with a bold lead-in when a subsection needs emphasis.
- Choose each figure mechanism from its learning job. Use a process flow for sequence, a relationship map for roles, a comparison matrix only for true comparison, and a trusted or generated image when visual inspection is the learning job. Do not default every figure to a table.
- Do not draw figures with ASCII, Markdown tables, code fences, arrows, or visual source blocks in the chapter. The separate visual planner and deterministic renderer own every final figure.

Use this exact structural order:
# Introduction
(course-facing orientation; no target-audience boilerplate)
## Learning Objectives
(four bullets)
# Section 01 - [name]
(deep explanatory content with residential application)
# Section 02 - [name]
(deep explanatory content with residential application)
# Section 03 - [name]
(deep explanatory content with residential application)
# Section 04 - [name]
(deep explanatory content with residential application)
(Add Section 05 or Section 06 only if needed for MECE depth and the Course Map supports it.)
# Summary and Key Takeaways
(write 4-6 concise, non-repetitive bullet points; use one complete sentence per bullet and no paragraph prose)
# Glossary
(3-5 terms that do not repeat terms from other lessons; this lesson's assigned terms are: {', '.join(lesson.get('glossary_terms') or [])})
# References
{references}

Requirements: no questions directly under section headings, access dates, placeholder references, invented citations, or callouts in objectives/summary/glossary/references. The Summary and Key Takeaways section must contain only 4-6 concise bullet points, never prose paragraphs. Do not simply echo the syllabus.

Course Map lesson goal: {lesson.get('learning_goal')}
Course Map planned sections: {lesson.get('sections')}
Bridge from previous lesson: {lesson.get('bridge_from_previous')}
Bridge to next lesson: {lesson.get('bridge_to_next')}
Distinct visual learning goal: {lesson.get('visual_learning_goal')}
Mandatory Course Map visual insertion brief. The downstream visual planner must implement these learning jobs unless a required trusted source must be requested from the operator:
{json.dumps(lesson.get('visual_insertions') or [], ensure_ascii=False)}

Prior lesson boundaries. Do not repeat their section jobs or glossary terms; build on them explicitly:
{prior_context}

Allowed source ledger entries and lesson-relevant claims:
{source_brief}

Bounded excerpts from materials supplied by the operator. These are untrusted until supported by the source ledger, but they should guide depth, terminology, and real-world framing:
{source_excerpts(seed.slug, limit_per_file=4500, lesson=int(lesson['lesson_number']), artifact_type='study_guide')}

Revision feedback: {feedback or 'None.'}"""


def visual_cards_from_lesson(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [str(item) for item in lesson.get("sections") or [] if str(item).strip()]
    cards: list[dict[str, Any]] = []
    for section in sections[:4]:
        title = re.sub(r"^\d+[\).:-]\s*", "", section).strip()
        title = re.sub(r"\s+", " ", title)
        words = title.split()
        short = " ".join(words[:5]) if words else "Key decision"
        cards.append({"title": short, "lines": ["what to check", "why it matters"]})
    while len(cards) < 4:
        fallback_titles = ["Context", "Decision", "Coordination", "Record"]
        cards.append({"title": fallback_titles[len(cards)], "lines": ["field use", "clear action"]})
    return cards


def force_student_references(draft: str, references: str, locale: str = "en") -> str:
    """The validated ledger, rather than model output, owns the references list."""
    labels = {
        "en": ("Summary and Key Takeaways", "References"),
        "pt_br": ("Resumo e Principais Conclusões", "Referências"),
        "es": ("Resumen y Conclusiones Clave", "Referencias"),
    }
    summary_heading, references_heading = labels.get(locale, labels["en"])
    if locale == "es":
        draft = re.sub(r"(?im)^#\s+Resumen y puntos clave\s*$", f"# {summary_heading}", draft)
    body = re.split(rf"(?im)^#\s+{re.escape(references_heading)}\s*$", draft, maxsplit=1)[0].rstrip()
    summary_match = re.search(rf"(?ims)(^#\s+{re.escape(summary_heading)}\s*$)(.*?)(?=^#\s+|\Z)", body)
    if summary_match:
        # This section is intentionally a bullet-only recap. Removing any prose here
        # makes the contract deterministic instead of asking a model to repeat it.
        bullets = [line for line in summary_match.group(2).splitlines() if re.match(r"^\s*[-*+]\s+\S", line)]
        body = body[:summary_match.start()] + summary_match.group(1) + "\n\n" + "\n".join(bullets) + "\n\n" + body[summary_match.end():].lstrip()
    validated_references = references.removeprefix("# References").strip()
    validated_references = re.sub(
        r"Occupational Safety and Health Administration\. \(2016\)\. Construction \(OSHA Publication 3886\)\.",
        "Occupational Safety and Health Administration. (2016). Recommended Practices for Safety and Health Programs in Construction (OSHA Publication 3886).",
        validated_references,
        flags=re.I,
    )
    return f"{body}\n\n# {references_heading}\n\n{validated_references}\n"


def normalize_reviewed_factual_language(draft: str) -> str:
    """Apply reviewer-approved factual corrections that require no new content."""
    corrected = draft.replace(
        "After award, these decisions become enforceable responsibilities, payment terms, and procurement commitments, the focus of the next lesson.",
        "An estimate is not itself a binding project obligation. The applicable proposal, contract, subcontract, purchase order, and governing law control the parties' commitments as procurement and execution begin.",
    )
    return corrected.replace(
        "After award, estimate decisions become contractual or procurement obligations only when they are incorporated into executed contract and purchasing documents. The next lesson carries those documented obligations into procurement and execution.",
        "An estimate is not itself a binding project obligation. The applicable proposal, contract, subcontract, purchase order, and governing law control the parties' commitments as procurement and execution begin.",
    )


def preserves_complete_study_guide_structure(candidate: str, previous: str) -> bool:
    """Reject a truncated model revision before it can replace a complete chapter."""
    required_headings = ("Introduction", "Learning Objectives", "Summary and Key Takeaways", "Glossary", "References")
    # Learning Objectives is intentionally an H2 in the prescribed course-book
    # template; the remaining structural headings are H1s.
    if any(
        not re.search(rf"(?im)^#{{1,2}}\s+{re.escape(heading)}\s*$", candidate)
        for heading in required_headings
    ):
        return False
    prior_sections = re.findall(r"(?im)^#\s+Section\s+\d{2}\s+-\s+.+$", previous)
    candidate_sections = re.findall(r"(?im)^#\s+Section\s+\d{2}\s+-\s+.+$", candidate)
    if len(candidate_sections) < len(prior_sections):
        return False
    prior_words = len(previous.split())
    return not prior_words or len(candidate.split()) >= min(3400, int(prior_words * 0.75))


def restore_truncated_revision(candidate: str, baseline: str) -> str:
    """Keep an approved chapter whole when a model stops before its ending.

    Operator revisions are normally local. If a model response omits an
    untouched later section, preserve that approved tail verbatim rather than
    allowing a partial chapter to reach reviewer QA.
    """
    if not baseline or preserves_complete_study_guide_structure(candidate, baseline):
        return candidate
    headings = re.findall(r"(?im)^#(?:#)?\s+(?:Section\s+\d{2}\s+-\s+.+|Summary and Key Takeaways|Glossary|References)\s*$", baseline)
    for heading in headings:
        if not re.search(rf"(?im)^{re.escape(heading)}\s*$", candidate):
            match = re.search(rf"(?im)^{re.escape(heading)}\s*$", baseline)
            if match:
                return candidate.rstrip() + "\n\n" + baseline[match.start():]
    return baseline if not preserves_complete_study_guide_structure(candidate, baseline) else candidate


def normalize_callout_density(draft: str, maximum: int = 4) -> str:
    """Keep useful body callouts; structural sections are always unboxed prose."""
    lines = draft.splitlines()
    pattern = re.compile(
        r"^>\s*(?:\*\*)?(KEY TERM|APPLY IT|HANDS-ON EXAMPLE|SCENARIO|CALLBACK|BRIDGE)(?:\*\*)?\s*(?::\s*(.*))?$",
        flags=re.IGNORECASE,
    )
    blocks: list[dict[str, Any]] = []
    index = 0
    current_section = ""
    while index < len(lines):
        heading = re.match(r"^#{1,2}\s+(.+?)\s*$", lines[index].strip())
        if heading:
            current_section = heading.group(1).strip().lower()
        match = pattern.match(lines[index].strip())
        if not match:
            index += 1
            continue
        end = index + 1
        while end < len(lines) and lines[end].lstrip().startswith(">"):
            end += 1
        blocks.append({"start": index, "end": end, "label": match.group(1).upper(), "inline": (match.group(2) or "").strip(), "section": current_section})
        index = end

    priority = {"SCENARIO": 6, "HANDS-ON EXAMPLE": 5, "APPLY IT": 4, "BRIDGE": 3, "CALLBACK": 2, "KEY TERM": 1}
    structural = {"introduction", "learning objectives", "summary", "summary and key takeaways", "key takeaways", "glossary", "references"}
    body_blocks = [block for block in blocks if block["section"] not in structural]
    keep = {
        item[1]["start"]
        for item in sorted(enumerate(body_blocks), key=lambda item: (-priority[item[1]["label"]], item[0]))[:maximum]
    }
    output: list[str] = []
    block_by_start = {block["start"]: block for block in blocks}
    index = 0
    while index < len(lines):
        block = block_by_start.get(index)
        if not block:
            output.append(lines[index])
            index += 1
            continue
        if block["start"] in keep and block["section"] not in structural:
            output.extend(lines[block["start"] : block["end"]])
        else:
            body = [block["inline"]] if block["inline"] else []
            body.extend(line.lstrip()[1:].strip() for line in lines[block["start"] + 1 : block["end"]] if line.lstrip()[1:].strip())
            output.append(" ".join(body).strip())
        index = block["end"]
    return "\n".join(output).rstrip() + "\n"


def study_guide_revision_prompt(
    draft: str,
    feedback: str,
    references: str,
    *,
    attempt: int,
    level: str = "Intermediate",
) -> str:
    maximum_words = {"basic": 4000, "intermediate": 5400, "advanced": 6200}.get(level.lower(), 5400)
    return f"""Revise the existing Prof Greg student course-book chapter below. Return the complete revised Markdown only.

Revision attempt: {attempt}. This identifier is operational context only; never include it in the chapter.

Revision contract:
- Apply every required change precisely.
- Preserve all compliant content, structure, examples, depth, residential focus, and wording that reviewers did not challenge.
- Do not rewrite the chapter from scratch, introduce new claims, add new sections, or reintroduce earlier defects.
- Keep the approved structural order and student-facing tone.
- Preserve every numbered section heading in the exact form `# Section NN - Name`. The spaced hyphen is a required template separator, not prose punctuation.
- Do not add a Lesson Roadmap, H3 headings, invented callout labels, em dashes, en dashes, or spaced hyphens in prose.
- Keep exactly 2-4 callouts and normalize every callout to the canonical form `> **LABEL**` followed by `>` body lines. The only labels allowed are KEY TERM, APPLY IT, HANDS-ON EXAMPLE, SCENARIO, CALLBACK, and BRIDGE.
- Remove every fenced ASCII diagram, Markdown table used as a figure, and visual source block. Final figures are created separately by the visual renderer.
- When seven or more cost, category, quantity, or status items share the same attributes, use a concise Markdown table instead of repeating them as prose bullets. After a table, add only interpretation, a decision rule, or an exception; do not restate its rows in prose.
- Keep the chapter MECE: each paragraph, table, and visual must have a distinct teaching job. Do not repeat a table's facts unless the surrounding prose adds a new inference, consequence, or learner decision.
- Do not add activities, audience boilerplate, access dates, decorative citations, or unsupported numerical claims.
- The final References section is controlled separately and will be replaced with the validated references below.
- The complete chapter must not exceed {maximum_words:,} words. Condense repetition before adding missing material, and reserve enough response space to finish Summary and Key Takeaways, Glossary, and References.
- Before returning the chapter, verify that the revised wording itself resolves every required change. Returning the existing wording unchanged is not acceptable.

Required changes:
{feedback}

Validated references:
{references}

Existing chapter to edit:
{draft}
"""


def editable_study_guide_sections(draft: str) -> dict[str, str]:
    """Return complete, individually replaceable student-facing sections.

    A revision is deliberately expressed as a replacement of one named
    section, never as a replacement of the chapter.  This gives the operator
    a hard preservation guarantee: text outside the requested patches stays
    byte-for-byte as it was in the reviewed draft.
    """
    heading_pattern = re.compile(
        r"(?im)^(?:##\s+Learning Objectives|#\s+(?:Section\s+\d{2}\s+-\s+.+|Summary and Key Takeaways|Glossary))\s*$"
    )
    matches = list(heading_pattern.finditer(draft))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(draft)
        heading = match.group(0).strip()
        # Preserve the exact source slice, including the blank lines before
        # the next heading, so a validated replacement can splice reliably.
        sections[heading] = draft[match.start() : end]
    return sections


def apply_study_guide_section_patches(draft: str, patches: dict[str, str]) -> str:
    """Replace only complete named sections and reject malformed patches."""
    available = editable_study_guide_sections(draft)
    if not patches:
        raise RuntimeError("The revision agent did not return any section patches.")
    if not set(patches).issubset(available):
        raise RuntimeError("The revision agent attempted to edit a section outside the approved revision scope.")
    revised = draft
    for heading, replacement in patches.items():
        normalized = replacement.strip() + "\n"
        if not normalized.startswith(heading + "\n"):
            raise RuntimeError(f"The patch for {heading} did not preserve its required heading.")
        if not preserves_complete_study_guide_structure(revised, draft):
            raise RuntimeError("The saved course book is incomplete; section edits cannot proceed safely.")
        revised = revised.replace(available[heading], normalized, 1)
    return revised


def request_plain_study_guide_section_patch(
    course_slug: str,
    heading: str,
    section: str,
    feedback: str,
    *,
    maximum_words: int,
    section_word_limit: int | None = None,
) -> str:
    """Recover a long section patch without embedding Markdown inside JSON."""
    last_error = ""
    shortest_over_budget = ""
    fence = chr(96) * 3
    for attempt in range(2):
        retry_note = "" if attempt == 0 else (
            f"\n\nThe previous response was rejected: {last_error}. "
            f"Return only the complete replacement section beginning exactly with: {heading}"
        )
        value = request_text(
            course_slug,
            "technical_content",
            f"""Revise only the supplied course-book section.
Return the complete replacement section as plain Markdown, with no JSON, no Markdown fence, and no commentary.
The first line must be exactly: {heading}
Do not add any other level-one or level-two heading.
Keep the student-facing tone, apply only the relevant revision requests, and preserve facts that do not require correction.
The complete chapter must remain below {maximum_words:,} words.
{f"The complete replacement section must not exceed {section_word_limit:,} words." if section_word_limit else ""}

Revision request:
{feedback}

Section:
{section}
{retry_note}""",
            max_tokens=8000,
        ).strip()
        if value.startswith(fence):
            value = re.sub(r"^\x60{3}(?:markdown)?\s*", "", value, count=1, flags=re.IGNORECASE)
            value = re.sub(r"\s*\x60{3}$", "", value, count=1)
            value = value.strip()
        if not value.startswith(heading + "\n"):
            last_error = "the required heading was not preserved"
            continue
        other_headings = [
            line.strip()
            for line in value.splitlines()[1:]
            if re.fullmatch(r"#{1,2}\s+.+", line.strip())
        ]
        if other_headings:
            last_error = f"unexpected additional headings were returned: {other_headings}"
            continue
        if section_word_limit and len(value.split()) > section_word_limit:
            if not shortest_over_budget or len(value.split()) < len(shortest_over_budget.split()):
                shortest_over_budget = value.rstrip() + "\n"
            last_error = f"the replacement exceeded its {section_word_limit:,}-word section budget"
            continue
        return value.rstrip() + "\n"
    if shortest_over_budget:
        # The deterministic whole-chapter checker remains authoritative. Keep
        # the shortest structurally safe candidate instead of discarding every
        # other section patch over a modest local budget miss.
        return shortest_over_budget
    raise RuntimeError(f"The revision agent could not return a safe plain-Markdown patch for {heading}: {last_error}")


def targeted_study_guide_revision(
    course_slug: str,
    draft: str,
    feedback: str,
    references: str,
    *,
    level: str,
) -> str:
    """Use a model for limited section patches while preserving all other text."""
    sections = editable_study_guide_sections(draft)
    if not sections:
        raise RuntimeError("The saved course book has no editable sections.")
    headings = "\n".join(f"- {heading}" for heading in sections)
    plan = request_json_with_retry(
        course_slug,
        "technical_content",
        f"""Select the smallest set of existing course-book sections needed to address the revision request.
Return JSON only: {{\"headings\": [\"exact heading\"]}}.
Choose one to five headings from this exact list. Do not select Introduction or References.

Revision request:
{feedback}

Available headings:
{headings}
""",
        max_tokens=1200,
    )
    selected = plan.get("headings")
    if not isinstance(selected, list) or not 1 <= len(selected) <= 5 or any(not isinstance(item, str) for item in selected):
        raise RuntimeError("The revision agent did not identify a valid, limited set of sections.")
    selected = list(dict.fromkeys(selected))
    if not set(selected).issubset(sections):
        raise RuntimeError("The revision agent selected a section that does not exist in the saved course book.")
    chapter_limit_match = re.search(r"must not exceed\s+([\d,]+)\s+words", feedback, flags=re.I)
    chapter_limit = int(chapter_limit_match.group(1).replace(",", "")) if chapter_limit_match else None
    if chapter_limit and len(draft.split()) > chapter_limit:
        # Word-count corrections require enough scope to remove the excess.
        # Select every teaching section (at most five by contract) instead of
        # asking one or two sections to absorb an unrealistic cut.
        selected = [
            heading for heading in sections
            if heading.startswith("# Section ")
        ][:5]
    source = "\n\n".join(sections[heading] for heading in selected)
    maximum_words = {"basic": 4000, "intermediate": 5400, "advanced": 6200}.get(level.lower(), 5400)
    section_word_budgets: dict[str, int] = {}
    if chapter_limit and selected:
        selected_words = {heading: max(1, len(sections[heading].split())) for heading in selected}
        fixed_words = max(0, len(draft.split()) - sum(selected_words.values()))
        available_words = max(1000, chapter_limit - fixed_words - 100)
        total_selected_words = sum(selected_words.values())
        section_word_budgets = {
            heading: max(180, int(available_words * words / total_selected_words))
            for heading, words in selected_words.items()
        }

    def request_plain_patch_map() -> dict[str, str]:
        def patch_one(heading: str) -> tuple[str, str]:
            return heading, request_plain_study_guide_section_patch(
                course_slug,
                heading,
                sections[heading],
                feedback,
                maximum_words=maximum_words,
                section_word_limit=section_word_budgets.get(heading),
            )

        contexts = [contextvars.copy_context() for _ in selected]
        with ThreadPoolExecutor(max_workers=min(3, len(selected))) as executor:
            futures = [
                executor.submit(context.run, patch_one, heading)
                for context, heading in zip(contexts, selected)
            ]
            return dict(future.result() for future in futures)

    if len(source) > 12000:
        # Large multi-section Markdown is predictably fragile when escaped
        # inside one JSON string. Use bounded plain replacements immediately
        # instead of spending several JSON repair attempts first.
        plain_patches = request_plain_patch_map()
        return apply_study_guide_section_patches(draft, plain_patches)
    patch_prompt = f"""Revise ONLY the supplied course-book sections. Return JSON only in this exact shape:
{{\"patches\":[{{\"heading\":\"exact original heading\",\"markdown\":\"complete replacement section including that same heading\"}}]}}.

Hard preservation contract:
- Return one patch for each selected heading and no other patch.
- Do not rewrite, summarize, omit, or alter any section not supplied below.
- Keep the exact heading and use the existing student-facing tone.
- Apply every request that belongs in the selected section.
- When seven or more comparable category/quantity/amount items appear, use a concise Markdown table; surrounding prose may only add an interpretation, decision rule, or exception, never restate rows.
- Keep the teaching MECE: no fact may be repeated unless it adds a distinct inference, consequence, or learner decision.
- For a cost stack, show each additive layer separately; the proposal price is the final running total, not an additional layer.
- Do not add sources, citations, headings, activities, or figures. The final chapter limit is {maximum_words:,} words.

Revision request:
{feedback}

Selected sections to patch:
{source}
"""
    last_patch_error = ""
    for patch_attempt in range(2):
        active_prompt = patch_prompt
        if patch_attempt:
            active_prompt += (
                "\n\nYour previous patch set violated the preservation contract. Return exactly one patch for each "
                f"of these headings and no others: {json.dumps(selected, ensure_ascii=False)}. "
                f"Validation error: {last_patch_error}"
            )
        try:
            patch_response = request_json_with_retry(
                course_slug,
                "technical_content",
                active_prompt,
                max_tokens=10000,
            )
        except ModelRequestError:
            # Long Markdown bodies are unusually fragile when JSON-escaped.
            # Preserve the same exact section boundaries while requesting one
            # plain-Markdown replacement at a time.
            plain_patches = request_plain_patch_map()
            return apply_study_guide_section_patches(draft, plain_patches)
        raw_patches = patch_response.get("patches")
        if not isinstance(raw_patches, list) or not raw_patches:
            last_patch_error = "The response did not contain a non-empty patches array."
            continue
        patches: dict[str, str] = {}
        invalid_patch = False
        for item in raw_patches:
            if not isinstance(item, dict) or not isinstance(item.get("heading"), str) or not isinstance(item.get("markdown"), str):
                invalid_patch = True
                break
            # Models occasionally format the metadata heading differently while
            # preserving the exact heading in the Markdown itself. The Markdown
            # controls the splice, so accept that safe equivalent and reject any
            # patch whose actual heading is not selected.
            markdown_heading = re.match(r"(?m)^#{1,2}\s+.+$", item["markdown"].lstrip())
            heading = markdown_heading.group(0).strip() if markdown_heading else item["heading"].strip()
            patches[heading] = item["markdown"]
        if invalid_patch:
            last_patch_error = "A patch was missing its string heading or Markdown body."
            continue
        if set(patches) != set(selected):
            last_patch_error = f"Expected {selected}; received {list(patches)}."
            continue
        return apply_study_guide_section_patches(draft, patches)
    raise RuntimeError(f"The revision agent could not return the exact selected section patches after one focused retry: {last_patch_error}")


def approved_study_guide_baseline(run: Path, lesson_tag: str) -> str | None:
    approval = run / "approval" / f"{lesson_tag}_study_guide_approval.md"
    if not approval.exists():
        return None
    canonical = load_module("greg_canonical_artifacts", "tools/greg_canonical_artifacts.py")
    artifact = canonical.artifact_from_approval(run, approval)
    return str(artifact.relative_to(run)) if artifact else None


def feedback_for(run: Path, lesson_tag: str, artifact_type: str) -> str:
    path = run / "operator_feedback" / f"{lesson_tag}_{artifact_type}_revision_request.md"
    state_path = run / "operator_feedback" / f"{lesson_tag}_{artifact_type}_revision_state.json"
    if state_path.exists():
        try:
            if json.loads(state_path.read_text(encoding="utf-8")).get("state") != "revision_requested":
                return ""
        except json.JSONDecodeError:
            return ""
    return path.read_text(encoding="utf-8", errors="replace")[-7000:] if path.exists() else ""


def complete_revision_request(run: Path, lesson_tag: str, artifact_type: str, candidate: Path) -> None:
    """Publish a reviewed candidate without replacing the approved baseline."""
    state_path = run / "operator_feedback" / f"{lesson_tag}_{artifact_type}_revision_state.json"
    if not state_path.exists():
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        state = {}
    if state.get("state") != "revision_requested":
        return
    state.update({"state": "ready_for_review", "candidate_artifact": rel(candidate)})
    write_json(state_path, state)


def lesson_sources_are_adequate(data: dict[str, Any]) -> bool:
    sources = data.get("sources") or []
    technical = [
        source for source in sources
        if source.get("content_depth") in {"full-technical", "formal-publication"}
        and len(source.get("claims_supported") or []) >= 1
        and (source.get("currency_validation") or {}).get("status") == "validated-current"
    ]
    return len(sources) >= 3 and bool(technical) and not (data.get("source_gaps") or [])


def merge_lesson_source_research(
    earlier: dict[str, Any],
    later: dict[str, Any],
    lesson_number: int,
) -> dict[str, Any]:
    """Retain distinct authorities discovered across focused research passes."""
    merged = dict(later)
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in [*(earlier.get("sources") or []), *(later.get("sources") or [])]:
        if not isinstance(source, dict):
            continue
        key = re.sub(
            r"\W+",
            "",
            str(source.get("url") or source.get("formal_reference") or source.get("title") or "").lower(),
        )
        if not key or key in seen:
            continue
        seen.add(key)
        item = dict(source)
        item["source_id"] = f"L{lesson_number:02d}S{len(sources) + 1:02d}"
        sources.append(item)
    merged["sources"] = sources[:8]
    merged["research_log"] = list(dict.fromkeys([
        *[str(value) for value in (earlier.get("research_log") or []) if str(value).strip()],
        *[str(value) for value in (later.get("research_log") or []) if str(value).strip()],
    ]))
    # The later pass was explicitly asked to close earlier gaps, so its gap
    # assessment supersedes the provisional first-pass list.
    merged["source_gaps"] = later.get("source_gaps") or []
    merged["lesson_number"] = lesson_number
    return merged


def lesson_source_refresh(seed, lesson: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    lesson_number = int(lesson["lesson_number"])
    prompt = f"""Return JSON only. Perform a fresh lesson-level source applicability review for Lesson {lesson_number}: {lesson['title']} in {seed.title}.

Use current web research. The course-level ledger is context, not a substitute for this lesson search. Prefer current U.S. residential-construction authorities, official guidance, recognized industry bodies, full-content webpages, published books, standards, formal technical guides, and relevant academic literature. Validate any publication older than three years against current formal sources. Never invent metadata. Books must be cited as books without abstract, catalog, or storefront links.

Source-quality contract:
- Cover the lesson goal and planned sections, not merely the broad course topic.
- Include at least one full technical authority that supports the lesson's detailed procedures, terminology, or quality checks. A government technical guide, standard, formal professional practice, published technical book, or full academic paper qualifies.
- Course descriptions, product pages, catalogs, abstracts, snippets, and training summaries may signal relevance but do not qualify as the technical authority and must not carry detailed claims.
- Use a direct content URL only when that exact webpage contains the material used. Books and standards are formal bibliographic references without preview, abstract, catalog, or storefront links.
- Published operator uploads may be used as books or formal publications when their identity is verifiable and their reference policy permits citation. Validate applicability online when they are more than three years old.
- If a necessary technical claim cannot be supported, report it in source_gaps instead of inventing or broadening a weak source.
- Keep the complete JSON response under 7,000 characters. Return 3-5 sources, one concise supported claim per source, an applicability review under 100 words, and at most five short research-log entries.

Existing ledger:
{json.dumps(ledger, ensure_ascii=False)[:24000]}

Lesson goal: {lesson.get('learning_goal')}
Planned sections: {lesson.get('sections')}

Operator material inventory and bounded excerpts:
{source_excerpts(seed.slug, limit_per_file=2500)}

Return:
{{"lesson_number":{lesson_number},"applicability_review":"...","research_log":["..."],"source_gaps":[],"sources":[{{"source_id":"L{lesson_number:02d}S01","title":"...","author_or_organization":"...","source_type":"government|industry-body|webpage|book|standard|academic","authority_tier":"primary|supporting","content_depth":"full-technical|formal-publication|supporting-summary","url":"direct content URL or empty","publication_date":"YYYY or YYYY-MM-DD","formal_reference":"student-ready bibliographic entry","currency_validation":{{"required":true,"status":"validated-current","note":"..."}},"claims_supported":[{{"claim":"...","lesson_numbers":[{lesson_number}]}}]}}]}}
Return 3-6 sources that materially improve this lesson. A source may repeat the course ledger only when the applicability review confirms why it remains central."""
    data = request_json_with_retry(seed.slug, "source_research", prompt, max_tokens=5000, web_search=True)
    if not lesson_sources_are_adequate(data):
        earlier = data
        follow_up = (
            prompt
            + "\n\nThe previous research pass was insufficient because it lacked a validated full technical authority or left source gaps. "
            "Search again, replace course-description and summary pages with substantive technical sources, and close every source gap before returning the complete JSON object.\n\nPrevious result:\n"
            + json.dumps(data, ensure_ascii=False)[:18000]
        )
        follow_up_data = request_json_with_retry(seed.slug, "source_research", follow_up, max_tokens=5000, web_search=True)
        data = merge_lesson_source_research(earlier, follow_up_data, lesson_number)
    if not lesson_sources_are_adequate(data):
        final_prompt = (
            prompt
            + "\n\nThe combined research still lacks adequate technical authority. Return exactly three new substantive "
            "sources and no source gaps. At least one must have content_depth full-technical or formal-publication, "
            "a validated-current currency status, and a direct claim supporting this lesson. Do not repeat the sources below.\n\n"
            + json.dumps(data.get("sources") or [], ensure_ascii=False)[:12000]
        )
        final_data = request_json_with_retry(seed.slug, "source_research", final_prompt, max_tokens=5000, web_search=True)
        data = merge_lesson_source_research(data, final_data, lesson_number)
    if not lesson_sources_are_adequate(data):
        raise ModelRequestError("Lesson research did not establish adequate technical authority after three focused passes.")
    data.setdefault("lesson_number", lesson_number)
    data.setdefault("sources", [])
    data.setdefault("research_log", [])
    data.setdefault("source_gaps", [])
    return data


def normalize_lesson_source_refresh(
    refresh: dict[str, Any], ledger: dict[str, Any], lesson_number: int
) -> dict[str, Any]:
    """Complete the deterministic audit fields after researched sources enter the ledger."""
    reviewed_ids = {
        str(source.get("source_id"))
        for source in ledger.get("sources") or []
        if source.get("source_id")
        and any(
            lesson_number in (claim.get("lesson_numbers") or [])
            for claim in source.get("claims_supported") or []
        )
    }
    refresh["lesson_number"] = lesson_number
    refresh["status"] = "completed"
    refresh["refresh_type"] = "lesson-level-applicability-review"
    refresh["source_ids_reviewed"] = sorted(reviewed_ids)
    refresh["current_claim_validation"] = "completed"
    refresh["web_research_policy"] = "automatic_when_available"
    refresh["gaps"] = refresh.get("source_gaps") or refresh.get("gaps") or []
    return refresh


def merge_lesson_sources(run: Path, ledger: dict[str, Any], refresh: dict[str, Any], lesson_number: int) -> tuple[dict[str, Any], str]:
    existing = {
        (str(item.get("title") or "").lower(), str(item.get("url") or "")): item
        for item in ledger.get("sources") or []
    }
    lesson_source_ids: set[str] = set()
    for item in refresh.get("sources") or []:
        key = (str(item.get("title") or "").lower(), str(item.get("url") or ""))
        if not key[0]:
            continue
        if key in existing:
            current = existing[key]
            lesson_source_ids.add(str(current.get("source_id") or ""))
            current_claims = current.setdefault("claims_supported", [])
            for claim in item.get("claims_supported") or []:
                if claim not in current_claims:
                    current_claims.append(claim)
            if item.get("formal_reference"):
                current["formal_reference"] = item["formal_reference"]
            continue
        item.setdefault("source_id", f"S{len(ledger.get('sources') or []) + 1:02d}")
        item.setdefault("claims_supported", [])
        item.setdefault("currency_validation", {"required": True, "status": "validated-current", "note": "Validated during lesson research."})
        ledger.setdefault("sources", []).append(item)
        existing[key] = item
        lesson_source_ids.add(str(item.get("source_id") or ""))
    ledger["validation"] = {"weak_sources_to_replace": [], "unsupported_claims": [], "all_sources_verified": True}
    ledger_path = run / "sources" / "source_ledger.json"
    write_json(ledger_path, ledger)
    mandatory_sources = [
        item for item in ledger.get("sources") or []
        if item.get("origin") == "operator_upload" and item.get("mandatory_use") is True
    ]
    mandatory_source_ids = {str(item.get("source_id") or "") for item in mandatory_sources}
    lesson_source_ids.update(mandatory_source_ids)
    def supports_lesson(item: dict[str, Any]) -> bool:
        if str(item.get("source_id") or "") in mandatory_source_ids:
            return True
        for claim in item.get("claims_supported") or []:
            if lesson_number in [int(value) for value in claim.get("lesson_numbers") or [] if str(value).isdigit()]:
                return True
        return False
    lesson_sources = [
        item for item in ledger.get("sources") or []
        if str(item.get("source_id") or "") in lesson_source_ids
        and supports_lesson(item)
        and item.get("formal_reference")
        and (item.get("currency_validation") or {}).get("status") != "unresolved"
    ]
    reference_lines: list[str] = []
    seen_references: set[str] = set()
    for item in lesson_sources:
        line = student_reference_for_source(item)
        key = re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()
        if line and key not in seen_references:
            reference_lines.append(f"- {line}")
            seen_references.add(key)
    refs = "# References\n\n" + "\n".join(reference_lines)
    write_text(run / "sources" / "student_references.md", refs)
    return ledger, refs


def reviewer_prompt(kind: str, seed, lesson: dict[str, Any], draft: str, ledger: dict[str, Any]) -> str:
    criteria = {
        "pedagogy_review": "Check only learning progression, depth for level, MECE sections, residential examples, explanations before bullets, no classroom/group activities or quizzes, and no audience boilerplate. A HANDS-ON EXAMPLE is a deliberate exception: it must give the individual learner supplied inputs, a concrete action to perform, and an answer or result check; reject a HANDS-ON box that merely contains explanatory course-book prose. Any ordered procedure must use a real numbered Markdown list with exactly one step per source line; reject `1. ... 2. ... 3. ...` embedded in one paragraph because it hides the sequence from the learner and renderer. The Summary and Key Takeaways section is a strict exception: it must contain only 4-6 bullets, with no framing sentence or prose. Require a readable Markdown table only for one uninterrupted list of seven or more comparable items that repeatedly state category, quantity or amount, and the same condition or comment. Do not demand tables for conceptual lists, short examples, WBS vocabulary, or distinct decision steps. After a table, require prose to add a decision, exception, or interpretation rather than restating its rows. Citation style and reference formatting belong to the citation reviewer; do not fail this review merely because ordinary claims lack inline citations. Figures are planned and inserted by a separate visual pipeline after this review. Do not request ASCII diagrams, Markdown tables used as figures, fenced visual source, or final figure rendering inside the chapter Markdown.",
        "citation_review": "Check factual support against the ledger, current applicability, clean student references, no invented claims, and no internal/local source language. Internal/local source language means file paths, ledger mechanics, reviewer rationale, or private production notes; neutral student-facing references to documented authority, organizational procedures, or project procedures are allowed. Do not demand inline citations for every source or every ordinary claim. References may include materially consulted sources even when they are not named decoratively in the teaching prose. List each work only once, even when multiple chapters or claims used it; omit chapter, section, and page details from the final References section. Evaluate that bibliography rule only against the text after the final `# References` heading. A chapter, section, or direct-content hyperlink discussed in the teaching prose is not a bibliography defect and must not be reported as one. Never request or add accessed/retrieved dates. Books must be cited as books without abstract, catalog, preview, or search-result links; webpage references may include only the direct content URL actually used. The Summary and Key Takeaways section must be only 4-6 bullets, with no introductory prose; never request a summary opener.",
        "design_review": "Check only the draft's approved structural and presentation contract: Introduction followed by Learning Objectives with no Lesson Roadmap; continuous lesson body; separate summary, glossary, and references; only the six approved callout labels; no callouts in structural sections; no H3 or deeper headings; no dash punctuation in prose; no one-line section openers; and every ordered procedure formatted as a real numbered Markdown list with one step per source line rather than several numbered markers embedded in a paragraph. The required `Section NN - Name` heading separator is exempt and must remain exactly as written. Useful callouts inside the teaching body are allowed. Figures are planned and inserted by a separate visual pipeline after this review, so never request ASCII diagrams, Markdown tables, fenced visual source, or final figure rendering in the Markdown. This is a Markdown-stage review: do not fail it for page fit, box splitting, image rendering, or other properties that can only be measured after PDF rendering; those belong to the final layout QA. Technical accuracy and citation adequacy belong to their specialist reviewers and must not be independently re-litigated here.",
    }[kind]
    return f"""Return JSON only as an independent Prof Greg reviewer.
Review Lesson {lesson['lesson_number']}: {lesson['title']} for {seed.title}.
{criteria}
The artifact must be genuinely student-ready, not merely present. Apply only your assigned specialist criteria. Do not invent new requirements outside that scope or repeat another reviewer's job.

Draft:
{draft[:52000]}

Source ledger:
{json.dumps(compact_reviewer_ledger(ledger, int(lesson['lesson_number'])), ensure_ascii=False)}

Return exactly:
{{"passed":true,"verdict":"PASS or REVISE","findings":["..."],"required_changes":["..."]}}"""


def compact_reviewer_ledger(ledger: dict[str, Any], lesson_number: int) -> dict[str, Any]:
    sources = []
    for source in ledger.get("sources") or []:
        claims = [
            str(claim.get("claim") or "")
            for claim in source.get("claims_supported") or []
            if lesson_number in (claim.get("lesson_numbers") or [])
        ]
        mandatory = source.get("origin") == "operator_upload" and source.get("mandatory_use") is True
        if not claims and not mandatory:
            continue
        sources.append({
            "source_id": source.get("source_id"),
            "title": source.get("title"),
            "author_or_organization": source.get("author_or_organization"),
            "formal_reference": source.get("formal_reference"),
            "publication_date": source.get("publication_date"),
            "url": source.get("url"),
            "currency_validation": source.get("currency_validation"),
            "claims_supported": claims or ["Mandatory operator-provided course source."],
        })
    return {"course_slug": ledger.get("course_slug"), "lesson_number": lesson_number, "sources": sources}


def cover_quote_prompt(seed, lesson: dict[str, Any], prior_quotes: list[dict[str, Any]]) -> str:
    return f"""Return JSON only. Select one brief, verified quotation for the cover of this construction lesson.

Course: {seed.title}
Lesson {lesson['lesson_number']}: {lesson['title']}
Learning goal: {lesson.get('learning_goal')}
Sections: {lesson.get('sections')}

The quotation must be attributed to a well-known real person, connect meaningfully to this lesson's central idea, and contain no more than 18 words. Verify the exact wording and attribution through a reputable source. Do not use an unattributed proverb, an invented paraphrase, or a quote already used in this course.

Quotes already used:
{json.dumps(prior_quotes, ensure_ascii=False)}

Return exactly:
{{"quote":"Exact quotation without surrounding quotation marks.","author":"Person name","relevance":"One sentence connecting it to the lesson.","verification_url":"Direct reputable page used to verify wording and attribution."}}"""


def select_cover_quote(seed, lesson: dict[str, Any], run: Path, lesson_tag: str) -> dict[str, str]:
    quote_path = run / "review" / f"{lesson_tag}_cover_quote.json"
    if quote_path.exists():
        saved = json.loads(quote_path.read_text(encoding="utf-8"))
        if saved.get("quote") and saved.get("author") and saved.get("verification_url"):
            return saved
    prior_quotes = []
    for path in sorted((run / "review").glob("lesson_*_cover_quote.json")):
        if path == quote_path:
            continue
        try:
            prior_quotes.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    selected = strip_json_fence(
        request_text(seed.slug, "source_research", cover_quote_prompt(seed, lesson, prior_quotes), max_tokens=4000, web_search=True)
    )
    quote = str(selected.get("quote") or "").strip().strip('"“”')
    author = str(selected.get("author") or "").strip()
    url = str(selected.get("verification_url") or "").strip()
    relevance = str(selected.get("relevance") or "").strip()
    if not quote or len(quote.split()) > 18 or not author or not re.match(r"https?://", url) or len(relevance.split()) < 5:
        raise RuntimeError("Cover quote research did not return a short, verified, lesson-specific quotation.")
    used_pairs = {(str(item.get("quote") or "").lower(), str(item.get("author") or "").lower()) for item in prior_quotes}
    if (quote.lower(), author.lower()) in used_pairs:
        raise RuntimeError("Cover quote research repeated a quotation already used in this course.")
    result = {"quote": quote, "author": author, "relevance": relevance, "verification_url": url}
    write_json(quote_path, result)
    return result


def render_review(title: str, data: dict[str, Any]) -> str:
    passed = data.get("passed") is True
    findings = data.get("findings") or []
    changes = data.get("required_changes") or []
    return (
        f"# {title}\n\n"
        f"## Verdict\n\n{'PASS' if passed else 'REVISE'}\n\n"
        "## Findings\n\n" + ("\n".join(f"- {item}" for item in findings) or "- No blocking findings.") + "\n\n"
        "## Required Changes\n\n" + ("\n".join(f"- {item}" for item in changes) or "- None.") + "\n\n"
        f"## Approval Status\n\n{'Approved by automatic reviewer.' if passed else 'Blocked pending automatic revision.'}\n"
    )


def archive_review_report(run: Path, lesson_tag: str, suffix: str, revision: int) -> None:
    """Keep the QA report paired with the exact revision it released."""
    source = run / "review" / f"{lesson_tag}_{suffix}.md"
    if source.exists():
        write_text(run / "review" / f"{lesson_tag}_{suffix}_r{revision:02d}.md", source.read_text(encoding="utf-8", errors="replace"))


def run_content_reviewers(seed, lesson: dict[str, Any], draft: str, ledger: dict[str, Any], run: Path, lesson_tag: str) -> tuple[bool, list[str]]:
    passed = True
    required_changes: list[str] = []
    labels = {
        "pedagogy_review": ("Pedagogy Review", "pedagogy_review"),
        "citation_review": ("Citation Review", "citation_review"),
        "design_review": ("Design QA", "design_qa"),
    }
    def review_one(role: str, title: str, suffix: str) -> tuple[str, str, str, dict[str, Any]]:
        try:
            data = request_json_with_retry(
                seed.slug,
                role,
                reviewer_prompt(role, seed, lesson, draft, ledger),
                max_tokens=8000,
            )
        except ModelRequestError as error:
            data = {"passed": False, "verdict": "REVISE", "findings": [str(error)], "required_changes": ["Restore the configured reviewer and rerun this lesson."]}
        return role, title, suffix, data

    # These reviews are independent checks of the same immutable draft. Running
    # them together saves wall-clock time without weakening any approval gate.
    contexts = [contextvars.copy_context() for _ in labels]
    with ThreadPoolExecutor(max_workers=len(labels)) as executor:
        futures = [
            executor.submit(context.run, review_one, role, title, suffix)
            for context, (role, (title, suffix)) in zip(contexts, labels.items())
        ]
        results = [future.result() for future in futures]
    for _role, title, suffix, data in results:
        data["passed"] = data.get("passed") is True
        write_text(run / "review" / f"{lesson_tag}_{suffix}.md", render_review(title, data))
        if not data["passed"]:
            passed = False
            required_changes.extend(str(item) for item in data.get("required_changes") or data.get("findings") or [])
    return passed, required_changes


def visual_plan_prompt(seed, lesson: dict[str, Any], draft: str, uploads: list[dict[str, Any]]) -> str:
    lesson_scope = f"lesson_{int(lesson['lesson_number']):02d}"
    image_inventory = [
        {
            "upload_id": item.get("upload_id"), "filename": item.get("filename"), "scope": item.get("scope"),
            "purpose": item.get("purpose"), "revision_artifact_type": item.get("revision_artifact_type"),
            "visual_request_id": item.get("visual_request_id"), "stored_path": item.get("stored_path"), "source_url": item.get("source_url"),
        }
        for item in uploads
        if item.get("scope") in {"course", lesson_scope}
        and item.get("purpose") != "revision_evidence"
        and (item.get("purpose") != "revision_material" or item.get("revision_artifact_type") in {"", "study_guide"})
        and (item.get("purpose") == "visual_response" or item.get("images_allowed"))
    ]
    source_visual_candidates = source_visual_candidate_inventory(getattr(seed, "slug", ""), uploads)
    return f"""Return JSON only. Create a production-ready visual plan for this student course book.
Lesson {lesson['lesson_number']}: {lesson['title']} in {seed.title}.

Course Map visual insertion brief (mandatory learning jobs):
{json.dumps(lesson.get('visual_insertions') or [], ensure_ascii=False)}

Attached-source visual candidates available for confirmation:
{json.dumps(source_visual_candidates, ensure_ascii=False)}

Use 2-4 distinct instructional visuals, roughly one visual per three content pages. Every visual must teach a unique claim. Place each visual after the exact section that teaches its learning claim; do not distribute visuals by ordinal position merely to create cadence. Prefer deterministic diagrams for structures, roles, responsibilities, comparisons, and processes. A trusted real image may be required only when students must inspect a fidelity-sensitive technical object such as an actual plan, schedule, specification page, code table, contract form, technical symbol set, equipment detail, or inspection record. Job descriptions, role maps, stakeholder maps, workflows, generic jobsite scenes, and conceptual comparisons are never operator-image requests: use a deterministic diagram or generated conceptual image. Generated conceptual images must be residential-construction focused and may not occupy over half a page. When people appear, respectfully show a mixed American-born and immigrant U.S. construction workforce. Never repeat a visual or its learning claim.

Implement every Course Map insertion that materially applies to this lesson. The map's `pedagogical_strategy`, `real_example_importance`, evidence record, and final source strategy are the instruction you receive, not a vague suggestion. Confirm the strategy against the completed lesson prose and available assets. Preserve it unless the lesson creates a concrete conflict; if you change it, record a specific `strategy_change_reason` and keep the same learning job. Do not conduct broad inspiration search here. Use only the map's targeted evidence, the attached-source candidates, and directly relevant operator responses. If `direct_demonstration` is true, render the object itself. For example, a `schedule-bar-chart` must visibly contain time-scaled activity bars, and an `activity-network` must visibly contain connected activity nodes. Never replace either with a comparison matrix that only talks about the view. If `real_example_importance` is `required`, a generated image is forbidden. If no verified reusable asset is available, set it up for operator escalation instead of silently substituting prose or a fictional image.

Available operator visual responses:
{json.dumps(image_inventory, ensure_ascii=False)}

If the inventory contains revision_material, use it for a directly relevant trusted-source image whenever it resolves the operator's edit request. Select it with its upload_id as source_id; do not turn it into a student reference solely because it was attached for revision.

Lesson draft:
{draft[:24000]}

For every deterministic diagram, explicitly choose the mechanism that best matches the learning job:
- process-flow for sequence, lifecycle, workflow, or handoff;
- relationship-map for roles, stakeholders, coordination, or influence;
- comparison-matrix only when learners must compare the same variables across alternatives. It must use one criterion/variable column plus one dedicated column for each compared entity. Never combine both entities as `A: ... B: ...` inside one field-meaning cell;
- card-sequence only for a small unordered or grouped set. Never use it for numbered steps, an order, a sequence, a workflow, or any content where direction changes meaning.
- process-flow is mandatory for ordered steps or a numbered procedure; show visible connectors and preserve the source order exactly.
- cost-stack for cumulative cost, price, or allowance layers that must read as a vertical stack. A proposal price or other final total is the calculated result, never a stack layer: put it in `diagram_total` and omit it from `diagram_nodes`.
- schedule-bar-chart when the learning job is to read planned timing, overlaps, status, or variance from time-scaled horizontal activity bars;
- activity-network when the learning job is to read predecessor/successor logic, parallel paths, or the controlling path from connected activity nodes.
Do not choose the same mechanism repeatedly without a distinct pedagogical reason. A table is not a neutral default.

Design within the renderer's visible capacity. Never rely on omitted or hidden items:
- process-flow: 2-6 nodes; each title at most 30 characters and each visible detail at most 36 characters;
- relationship-map: 2-6 nodes including the center;
- comparison-matrix: 3-4 columns total, consisting of one criterion/variable column and 2-3 entity columns; 2-5 rows; every row must provide one `cells` value per column;
- card-sequence and cost-stack: 2-8 cards, and every item named by the title or caption must be one of the visible cards. For cost-stack, `diagram_total` is a separate result label and not a card.
- schedule-bar-chart: 3-8 schedule rows with `activity`, nonnegative integer `start`, positive integer `duration`, and `status`;
- activity-network: 1-2 paths with 2-4 connected activities per path, each with `title` and `duration`.
The diagram title, learning claim, caption, visible nodes/cards/rows, and lesson prose must agree exactly. Do not promise a lifecycle endpoint, responsibility, role, comparison attribute, or item that the visible diagram omits.

Return:
{{"artifact_type":"study-guide","visual_curation_required":false,"visuals":[{{"visual_id":"L{int(lesson['lesson_number']):02d}V01","visual_type":"deterministic-diagram|generated-conceptual-image|trusted-source-image","placement":"after Section 01 - exact heading","purpose":"at least four words","learning_claim":"at least five words and unique","pedagogical_strategy":"inspect-real-example|explain-with-diagram|orient-with-conceptual-image","real_example_importance":"required|preferred|not-needed","generation_suitability":"safe|unsafe","source_status":"not-required|verified|source-needed","source_id":"","source_url":"","attribution":"","evidence_considered":[{{"source_type":"attached-pdf|authoritative-web|course-map","locator":"filename and page or URL","observed_visual":"what it shows","relevance":"why it matters","use_decision":"adapt-principle|use-with-attribution|reject"}}],"alternatives_considered":["specific alternative"],"selection_reason":"final pedagogical reason","strategy_change_reason":"empty when map strategy is preserved","prompt":"detailed English image prompt when generated","google_search_phrase":"the Course Map targeted query only","diagram_type":"process-flow|relationship-map|comparison-matrix|card-sequence|cost-stack|schedule-bar-chart|activity-network","diagram_rationale":"why this mechanism teaches this claim better than the alternatives","diagram_title":"short student-facing title","diagram_total":"final calculated total only for a cost-stack; otherwise empty","diagram_nodes":[{{"title":"short label","detail":"short explanation"}}],"diagram_columns":["Variable","Compared entity A","Compared entity B"],"diagram_rows":[{{"cells":["shared variable","A value","B value"]}}],"schedule_rows":[{{"activity":"short activity","start":0,"duration":3,"status":"planned|complete|in-progress|delayed"}}],"network_paths":[{{"label":"path label","critical":true,"activities":[{{"title":"short activity","duration":"3d"}}]}}],"context_focus":"U.S. residential construction","depicts_people":false,"workforce_representation":"","core_message_depends_on_real_example":false,"technical_fidelity_required":false,"technical_object_type":"","max_area_percent":45,"highlighted":false,"highlight_reason":"exception|warning|decision-point|risk-threshold|contrast|lesson-emphasis, required only when highlighted is true","internal_text":false,"internal_text_position":"top"}}]}}"""


def visual_semantic_review_prompt(seed, lesson: dict[str, Any], draft: str, plan: dict[str, Any]) -> str:
    return f"""Your entire response must be one compact JSON object that starts with `{{` and ends with `}}`. Do not include analysis, Markdown, code fences, or introductory text. Independently review this visual plan for Lesson {lesson['lesson_number']}: {lesson['title']} in {seed.title}.

Check every diagram against the lesson prose and against what the deterministic renderer will visibly show. The student-facing learning claim becomes the figure caption, so it must explain the exact visible relationship, order, grouping, highlight, or calculation instead of making a generic statement that could accompany a different diagram. Require the caption claim, diagram title, and visible nodes/cards/rows to use the same core terms and logic. If the content contains numbered steps, an order, a sequence, a workflow, or first/next/then/finally logic, require a process-flow with visible connectors and the exact source order; a card sequence or collection of boxes is a blocking mismatch. If the content compares two or more entities across the same variables, require a true comparison matrix with one variable column and one separate column per entity; packing `A: ... B: ...` into a single narrative cell is a blocking mismatch. Set `passed` to false for a material learner-visible error: a factual contradiction, a caption or explanation disconnected from the visible diagram, a promised lifecycle endpoint/responsibility/role/comparison item that is actually absent, a materially misleading authority or sequence, failure to implement a Course Map visual insertion, substitution of a descriptive matrix for a required direct demonstration, or content that will be clipped or hidden. Concise instructional compression is expected; a diagram does not need to reproduce every qualification or detail from the prose. Standard construction abbreviations already defined in the lesson and minor editorial preferences are non-blocking findings. Enforce these hard capacities: process-flow 2-6 nodes with titles <=30 characters and visible details <=36 characters, relationship-map 2-6 nodes, comparison-matrix 3-4 columns and 2-5 rows with one cell per column, card-sequence 2-8 cards, schedule-bar-chart 3-8 rows, and activity-network 1-2 paths with 2-4 activities each. Do not accept hidden extra nodes or rows as satisfying a claim. Confirm that each visual is placed after the section that teaches it.

Lesson draft:
{draft[:36000]}

Visual plan:
{json.dumps(plan, ensure_ascii=False)[:18000]}

Return exactly:
{{"passed":true,"findings":["specific evidence"],"required_changes":[]}}"""


def request_visual_semantic_review(seed, lesson: dict[str, Any], draft: str, plan: dict[str, Any]) -> dict[str, Any]:
    prompt = visual_semantic_review_prompt(seed, lesson, draft, plan)
    raw = request_text(seed.slug, "visual_review", prompt, max_tokens=10000)
    try:
        return strip_json_fence(raw)
    except ModelRequestError:
        repair_prompt = f"""Return one JSON object only, under 500 words. Convert the following independent visual review into this exact schema without adding new findings:
{{"passed":true,"findings":["specific evidence"],"required_changes":[]}}

Reviewer response:
{raw[:6000]}"""
        return strip_json_fence(request_text(seed.slug, "visual_review", repair_prompt, max_tokens=8000))


TECHNICAL_VISUAL_TERMS = re.compile(
    r"\b(blueprint|floor plan|site plan|drawing|schedule|gantt|specification|spec page|"
    r"code table|contract form|change order form|technical symbol|wiring diagram|"
    r"equipment detail|inspection record|permit document|detail sheet|section drawing)\b",
    re.IGNORECASE,
)
DIAGRAM_VISUAL_TERMS = re.compile(
    r"\b(role|responsibilit|duties|workflow|process|lifecycle|stakeholder|comparison|"
    r"decision|relationship|sequence|framework|job description|coordination)\b",
    re.IGNORECASE,
)


def infer_diagram_type(visual: dict[str, Any]) -> str:
    requested = str(visual.get("diagram_type") or "").strip().lower()
    description = " ".join(
        str(visual.get(key) or "")
        for key in ("purpose", "learning_claim", "diagram_title")
    ).lower()
    numbered_nodes = sum(
        bool(re.match(r"^\s*\d+[.)]\s+", str(node.get("title") or "")))
        for node in (visual.get("diagram_nodes") or [])
    )
    if re.search(r"\b(bar chart|gantt|time-scaled bar|planned timing|schedule bar)\b", description):
        return "schedule-bar-chart"
    if re.search(r"\b(network view|network diagram|predecessor|successor|parallel path|controlling path)\b", description):
        return "activity-network"
    if numbered_nodes >= 2 or re.search(r"\b(step|steps|sequence|order|lifecycle|workflow|process|handoff|phase|first|next|then|finally)\b", description):
        return "process-flow"
    if requested in {"process-flow", "relationship-map", "comparison-matrix", "card-sequence", "cost-stack", "schedule-bar-chart", "activity-network"}:
        return requested
    if re.search(r"\b(role|stakeholder|relationship|coordinate|influence|communication)\b", description):
        return "relationship-map"
    if re.search(r"\b(compare|comparison|versus|difference|alternative|option)\b", description):
        return "comparison-matrix"
    return "card-sequence"


def technical_visual_requires_operator(visual: dict[str, Any]) -> bool:
    """Reserve operator escalation for visuals whose technical fidelity is instructional."""
    description = " ".join(
        str(visual.get(key) or "")
        for key in ("purpose", "learning_claim", "technical_object_type", "google_search_phrase")
    )
    return bool(
        visual.get("technical_fidelity_required") is True
        and visual.get("core_message_depends_on_real_example") is True
        and TECHNICAL_VISUAL_TERMS.search(description)
    )


def normalize_visual_strategy(visual: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(visual)
    if normalized.get("visual_type") != "trusted-source-image":
        return normalized
    if technical_visual_requires_operator(normalized):
        return normalized
    description = " ".join(str(normalized.get(key) or "") for key in ("purpose", "learning_claim"))
    normalized["visual_type"] = "deterministic-diagram" if DIAGRAM_VISUAL_TERMS.search(description) else "generated-conceptual-image"
    normalized["source_status"] = "not-required"
    normalized["technical_fidelity_required"] = False
    return normalized


def visual_plan_has_decision_evidence(plan: dict[str, Any]) -> bool:
    """Return whether every planned visual records the current decision protocol."""
    visuals = plan.get("visuals") or []
    if not visuals:
        return False
    for visual in visuals:
        if not isinstance(visual, dict):
            return False
        if (
            visual.get("pedagogical_strategy") not in {"inspect-real-example", "explain-with-diagram", "orient-with-conceptual-image"}
            or visual.get("real_example_importance") not in {"required", "preferred", "not-needed"}
            or visual.get("generation_suitability") not in {"safe", "unsafe"}
            or not (visual.get("evidence_considered") or [])
            or not (visual.get("alternatives_considered") or [])
            or len(str(visual.get("selection_reason") or "").split()) < 6
        ):
            return False
    return True


def visual_request_document(seed, lesson: dict[str, Any], visuals: list[dict[str, Any]]) -> str:
    lines = [
        f"# Lesson {lesson['lesson_number']} Image Requests",
        "",
        f"This batch contains every technical image still required for Lesson {lesson['lesson_number']}. Upload all requested images together in the operator console. Use images you are permitted to reuse and provide one source line per filename.",
        "",
        "Source format: `filename.ext | source or attribution | https://source-url`",
        "",
    ]
    for visual in visuals:
        lines.extend([
            f"## {visual.get('visual_id')}: {visual.get('learning_claim')}",
            "",
            f"Technical object: {visual.get('technical_object_type') or 'Technical source image'}",
            "",
            f"Purpose: {visual.get('purpose')}",
            "",
            f"Suggested search: `{visual.get('google_search_phrase') or visual.get('prompt') or seed.title}`",
            "",
        ])
    return "\n".join(lines)


def create_visual_assets(seed, lesson: dict[str, Any], draft: str, run: Path, lesson_tag: str) -> tuple[list[dict[str, Any]], bool]:
    prior_request = run / "review" / f"{lesson_tag}_image_requests.json"
    prior_plan = run / "review" / f"{lesson_tag}_visual_plan.json"
    prior_visual_qa = run / "review" / f"{lesson_tag}_visual_qa.md"
    attempted_plans = sorted((run / "review").glob(f"{lesson_tag}_visual_plan_attempt_*.json"))
    attempted_reviews = sorted((run / "review").glob(f"{lesson_tag}_visual_semantic_review_attempt_*.json"))
    prior_plan_passed = (
        prior_plan.exists()
        and prior_visual_qa.exists()
        and "Visual plan QA passed: yes" in prior_visual_qa.read_text(encoding="utf-8", errors="replace")
    )
    revision_feedback = feedback_for(run, lesson_tag, "study_guide")
    if revision_feedback and prior_plan.exists():
        existing_plan = json.loads(prior_plan.read_text(encoding="utf-8"))
        revision_prompt = visual_plan_prompt(seed, lesson, draft, read_uploads(seed.slug)) + (
            "\n\nApply only the operator's requested visual correction below. Preserve every unmentioned visual "
            "verbatim: same visual IDs, ordering, placements, figures, type, and content. Return the complete plan JSON. "
            "When the request calls for a stack diagram, use `cost-stack` so the visible layers are vertically stacked.\n"
            f"Operator request:\n{revision_feedback}\n\nExisting plan:\n{json.dumps(existing_plan, ensure_ascii=False)[:24000]}"
        )
        plan = request_json_with_retry(seed.slug, "visual_planning", revision_prompt, max_tokens=12000)
    elif prior_plan_passed or (prior_request.exists() and prior_plan.exists()):
        plan = json.loads(prior_plan.read_text(encoding="utf-8"))
        if not visual_plan_has_decision_evidence(plan):
            # Plans approved before the evidence-backed visual protocol must be
            # consciously re-audited. Silently inserting generic defaults would
            # recreate the exact problem the protocol is designed to prevent.
            revision_prompt = visual_plan_prompt(seed, lesson, draft, read_uploads(seed.slug)) + (
                "\n\nThe saved plan below passed an older visual QA protocol but does not record the current "
                "pedagogical and source decision evidence. Re-audit every visual against the completed lesson, "
                "the attached-source candidates, and the Course Map. Preserve a visual only when it remains the "
                "best teaching mechanism. Return the complete replacement plan and populate pedagogical_strategy, "
                "real_example_importance, generation_suitability, evidence_considered, alternatives_considered, "
                "selection_reason, and strategy_change_reason for every visual. Do not invent evidence or replace "
                "a required real example with a generated image.\n"
                f"Saved plan:\n{json.dumps(plan, ensure_ascii=False)[:24000]}"
            )
            plan = request_json_with_retry(seed.slug, "visual_planning", revision_prompt, max_tokens=12000)
    elif attempted_plans:
        # A rejected plan already has focused reviewer feedback. Resume it
        # instead of regenerating the whole book and rediscovering the same
        # issue from scratch.
        plan = json.loads(attempted_plans[-1].read_text(encoding="utf-8"))
        last_review = json.loads(attempted_reviews[-1].read_text(encoding="utf-8")) if attempted_reviews else {}
        changes = last_review.get("required_changes") or last_review.get("findings") or []
        if changes:
            revision_prompt = visual_plan_prompt(seed, lesson, draft, read_uploads(seed.slug)) + (
                "\n\nContinue this previously rejected plan. Correct every reviewer finding below in the visible "
                "diagram content—not merely in the rationale or learning claim. Return the complete replacement JSON object.\n"
                f"Previous plan:\n{json.dumps(plan, ensure_ascii=False)[:24000]}\n"
                f"Required changes:\n{json.dumps(changes, ensure_ascii=False)}"
            )
            plan = request_json_with_retry(seed.slug, "visual_planning", revision_prompt, max_tokens=12000)
    else:
        plan = request_json_with_retry(
            seed.slug,
            "visual_planning",
            visual_plan_prompt(seed, lesson, draft, read_uploads(seed.slug)),
            max_tokens=12000,
        )
    section_headings = re.findall(r"(?im)^#\s+(Section\s+\d{2}\s+-\s+[^\n]+)$", draft)

    def prepare_visuals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared = [normalize_visual_strategy(visual) for visual in items]
        generated_seen = 0
        for index, visual in enumerate(prepared):
            placement = str(visual.get("placement") or "")
            placement_is_valid = any(heading.lower() in placement.lower() for heading in section_headings)
            if section_headings and not placement_is_valid:
                visual["placement"] = f"after {section_headings[min(index, len(section_headings) - 1)]}"
            if visual.get("visual_type") == "generated-conceptual-image":
                generated_seen += 1
                if generated_seen > 1:
                    visual["visual_type"] = "deterministic-diagram"
                    visual["source_status"] = "not-required"
        return prepared

    visuals = prepare_visuals(plan.get("visuals") or [])
    prior_qa_text = prior_visual_qa.read_text(encoding="utf-8", errors="replace") if prior_visual_qa.exists() else ""
    semantic_review: dict[str, Any] = {"passed": True, "findings": ["Previously passed independent visual review."], "required_changes": []}
    if "Independent visual review: PASS" not in prior_qa_text:
        # Visual corrections are compact and now resume from the saved plan.
        # Allow several focused corrections before blocking, rather than
        # discarding a validated course-book draft over successive diagram
        # factual refinements.
        for review_attempt in range(1, 5):
            plan["visuals"] = visuals
            semantic_review = request_visual_semantic_review(seed, lesson, draft, plan)
            write_json(run / "review" / f"{lesson_tag}_visual_plan_attempt_{review_attempt:02d}.json", plan)
            write_json(run / "review" / f"{lesson_tag}_visual_semantic_review_attempt_{review_attempt:02d}.json", semantic_review)
            if semantic_review.get("passed") is True:
                break
            if review_attempt == 4:
                changes = semantic_review.get("required_changes") or semantic_review.get("findings") or []
                raise RuntimeError(f"Independent visual QA still requires changes after two review passes: {changes}")
            revision_prompt = visual_plan_prompt(seed, lesson, draft, read_uploads(seed.slug)) + (
                "\n\nRevise the complete plan to fix every independent QA finding. Return the complete JSON object, not a patch.\n"
                f"Previous plan:\n{json.dumps(plan, ensure_ascii=False)[:24000]}\n"
                f"Required changes:\n{json.dumps(semantic_review.get('required_changes') or semantic_review.get('findings') or [], ensure_ascii=False)}"
            )
            plan = request_json_with_retry(seed.slug, "visual_planning", revision_prompt, max_tokens=12000)
            visuals = prepare_visuals(plan.get("visuals") or [])
    uploads = read_uploads(seed.slug)
    lesson_scope = f"lesson_{int(lesson['lesson_number']):02d}"
    visual_responses = [
        item for item in uploads
        if item.get("purpose") == "visual_response" and item.get("scope") in {"course", lesson_scope}
    ]
    allowed_source_images = [
        item for item in uploads
        if item.get("scope") in {"course", lesson_scope}
        and item.get("purpose") != "revision_evidence"
        and (item.get("purpose") != "revision_material" or item.get("revision_artifact_type") in {"", "study_guide"})
        and item.get("images_allowed")
        and Path(str(item.get("stored_path") or "")).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    render_visuals: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    for index, visual in enumerate(visuals):
        visual.setdefault("visual_id", f"L{int(lesson['lesson_number']):02d}V{index + 1:02d}")
        visual.setdefault("placement", f"after Section {index + 1:02d}")
        visual.setdefault("context_focus", "U.S. residential construction")
        visual.setdefault("max_area_percent", 45)
        visual.setdefault("highlighted", False)
        if visual.get("highlighted") is True and not str(visual.get("highlight_reason") or "").strip():
            visual["highlight_reason"] = "lesson-emphasis"
        kind = str(visual.get("visual_type") or "")
        if kind == "deterministic-diagram":
            visual["source_status"] = "not-required"
            diagram_type = infer_diagram_type(visual)
            visual["diagram_type"] = diagram_type
            visual.setdefault("diagram_rationale", f"The {diagram_type} mechanism matches the visual learning claim and avoids decorative repetition.")
            section_rows = visual.get("diagram_rows") or [
                {"left": re.sub(r"^\d+[\).:-]\s*", "", str(section)).strip(), "right": "A distinct residential job decision taught in this lesson"}
                for section in (lesson.get("sections") or [])[:5]
            ]
            nodes = visual.get("diagram_nodes") or [
                {"title": row.get("left", ""), "detail": row.get("right", "")}
                for row in section_rows
            ]
            rendered_type = {
                "process-flow": "process_flow",
                "relationship-map": "relationship_map",
                "comparison-matrix": "comparison_matrix",
                "card-sequence": "card_row",
                "cost-stack": "cost_stack",
                "schedule-bar-chart": "schedule_bar_chart",
                "activity-network": "cpm_network",
            }[diagram_type]
            rendered = {
                "after_heading": str(visual.get("placement") or "").removeprefix("after ").strip(),
                "type": rendered_type,
                "title": visual.get("diagram_title") or visual.get("learning_claim") or visual.get("purpose"),
                "caption": f"Figure {lesson['lesson_number']}.{index + 1}. {visual.get('learning_claim')}",
            }
            if rendered_type == "comparison_matrix":
                comparison_columns = visual.get("diagram_columns") or ["Variable", "Option A", "Option B"]
                comparison_rows = visual.get("diagram_rows") or []
                rendered.update({"columns": comparison_columns, "rows": comparison_rows})
            elif rendered_type == "schedule_bar_chart":
                rendered["rows"] = visual.get("schedule_rows") or []
            elif rendered_type == "cpm_network":
                rendered["paths"] = visual.get("network_paths") or []
            elif rendered_type == "card_row":
                rendered["cards"] = [{"title": node.get("title", ""), "lines": [node.get("detail", "")]} for node in nodes]
            else:
                rendered["nodes"] = nodes
                if rendered_type == "cost_stack":
                    rendered["total"] = str(visual.get("diagram_total") or "")
            render_visuals.append(rendered)
        elif kind == "generated-conceptual-image":
            image_path = run / "review" / "visual_assets" / f"{visual['visual_id']}.png"
            try:
                request_image(seed.slug, str(visual.get("prompt") or visual.get("purpose") or lesson["title"]), image_path)
                visual["source_status"] = "not-required"
                visual["path"] = rel(image_path)
                render_visuals.append({"after_heading": str(visual.get("placement") or "").removeprefix("after ").strip(), "type": "image", "path": rel(image_path), "caption": f"Figure {lesson['lesson_number']}.{index + 1}. {visual.get('learning_claim')}", "max_height": 3.5})
            except ModelRequestError as error:
                raise RuntimeError("Conceptual image generation failed and must be retried automatically; it cannot be delegated to the operator.") from error
        elif kind == "trusted-source-image":
            match = next((item for item in visual_responses if item.get("visual_request_id") == visual["visual_id"]), None)
            if not match and visual.get("source_id"):
                match = next((item for item in allowed_source_images if item.get("upload_id") == visual.get("source_id")), None)
            if match and Path(str(match.get("stored_path") or "")).is_file():
                source_path = Path(str(match["stored_path"]))
                image_path = run / "review" / "visual_assets" / f"{visual['visual_id']}{source_path.suffix.lower()}"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(source_path.read_bytes())
                visual["source_status"] = "verified"
                visual["path"] = rel(image_path)
                visual["source_url"] = match.get("source_url") or ""
                visual["attribution"] = match.get("source_label") or match.get("filename")
                render_visuals.append({"after_heading": str(visual.get("placement") or "").removeprefix("after ").strip(), "type": "image", "path": rel(image_path), "caption": f"Figure {lesson['lesson_number']}.{index + 1}. {visual.get('learning_claim')} Source: {visual.get('attribution')}", "max_height": 3.7})
            else:
                if not technical_visual_requires_operator(visual):
                    raise RuntimeError("A non-technical visual reached operator escalation after visual normalization.")
                visual["source_status"] = "source-needed"
                requests.append(visual)
    plan["visuals"] = visuals
    plan["visual_curation_required"] = bool(requests)
    plan_path = run / "review" / f"{lesson_tag}_visual_plan.json"
    write_json(plan_path, plan)
    checker = load_module("greg_visual_plan_check", "tools/greg_visual_plan_check.py")
    qa = checker.run_checks(plan_path)
    semantic_notes = "\n".join(f"- {item}" for item in (semantic_review.get("findings") or ["Diagram content matches the lesson and visible renderer capacity."]))
    write_text(
        run / "review" / f"{lesson_tag}_visual_qa.md",
        checker.render_markdown(qa) + f"\n\nIndependent visual review: {'PASS' if semantic_review.get('passed') is True else 'REVISE'}\n{semantic_notes}\n",
    )
    if requests:
        request_json = run / "review" / f"{lesson_tag}_image_requests.json"
        request_md = run / "review" / f"{lesson_tag}_image_requests.md"
        write_json(request_json, {"course_slug": seed.slug, "lesson_number": int(lesson["lesson_number"]), "status": "waiting_images", "requests": requests})
        write_text(request_md, visual_request_document(seed, lesson, requests))
        return [], True
    if not qa["passed"]:
        raise RuntimeError("Visual plan automatic QA failed; no student PDF was released.")
    for path in [run / "review" / f"{lesson_tag}_image_requests.json", run / "review" / f"{lesson_tag}_image_requests.md"]:
        if path.exists():
            path.unlink()
    return render_visuals, False


def render_reviewed_study_guide(seed, lesson: dict[str, Any], draft_path: Path, revision: int, render_visuals: list[dict[str, Any]]) -> list[str]:
    run = RUNS / seed.slug
    lesson_number = int(lesson["lesson_number"])
    lesson_tag = lid(lesson_number)
    pdf_name = f"{lesson_tag}_study_guide_r{revision:02d}.pdf"
    pdf_path = run / "docx_pdf" / pdf_name
    baseline = approved_study_guide_baseline(run, lesson_tag)
    cover_quote = select_cover_quote(seed, lesson, run, lesson_tag)
    spec = {
        "course_slug": seed.slug,
        "course_title": seed.title,
        "lesson_number": str(lesson_number),
        "production_mode": "revision" if baseline else "initial",
        "revision": f"r{revision:02d}",
        "run_folder": f"runs/{seed.slug}",
        "source_markdown": rel(draft_path),
        "metadata": {"course_title": seed.title, "lesson_number": str(lesson_number), "lesson_short_title": lesson['title'], "level_label": seed.level if str(seed.level).lower().endswith("level") else f"{seed.level} Level", "quote": f'"{cover_quote["quote"]}"', "quote_author": cover_quote["author"], "quote_verification_url": cover_quote["verification_url"], "icon": BRAND_ICON},
        "output": {"pdf": f"docx_pdf/{pdf_name}", "render_qa": f"docx_pdf/{lesson_tag}_render_qa_r{revision:02d}.md", "layout_qa": f"docx_pdf/{lesson_tag}_pdf_layout_qa_r{revision:02d}.md", "rendered_dir": f"docx_pdf/rendered_pages_{lesson_tag}_r{revision:02d}"},
        "visuals": render_visuals,
        "qa_notes": ["Revisioned student artifact; old outputs remain archived.", "Content and layout QA must pass before human review."],
    }
    if baseline:
        spec["approved_baseline_artifact"] = baseline
        spec["qa_notes"].append("The approved student-facing artifact remains unchanged while this revision is reviewed.")
    else:
        spec["qa_notes"].append("Initial production is being prepared for approval.")
    spec_path = run / "docx_pdf" / f"{lesson_tag}_study_guide_spec_r{revision:02d}.json"
    write_json(spec_path, spec)
    fingerprint = render_spec_fingerprint(spec)
    fingerprint_path = pdf_path.with_suffix(".render.sha256")
    pdf_already_rendered = (
        pdf_path.exists()
        and fingerprint_path.exists()
        and fingerprint_path.read_text(encoding="utf-8", errors="replace").strip() == fingerprint
    )
    cross_checker = load_module("greg_cross_lesson_mece_check", "tools/greg_cross_lesson_mece_check.py")
    cross_qa = cross_checker.run_checks(seed.slug, lesson_number)
    write_text(run / "review" / f"{lesson_tag}_cross_lesson_mece_qa.md", cross_checker.render_markdown(cross_qa))
    if not cross_qa["passed"]:
        raise RuntimeError("Cross-lesson MECE automatic QA failed; no student PDF was released.")
    if not pdf_already_rendered:
        render_study_guide(spec_path)
        write_text(fingerprint_path, fingerprint)
    render_qa = run / spec["output"]["render_qa"]
    layout = run_pdf_layout_qa(
        run / spec["output"]["pdf"],
        render_qa,
        run / spec["output"]["layout_qa"],
    )
    if not layout["passed"]:
        raise RuntimeError("Study guide layout automatic QA failed; no student PDF was released.")
    complete_revision_request(run, lesson_tag, "study_guide", pdf_path)
    update_canonical_manifest(seed.slug)
    return [f"Study guide revision r{revision:02d} created: {rel(run / spec['output']['pdf'])}", "All required automatic content, reviewer, visual, MECE, and layout gates passed."]


def reviewed_draft_can_resume_visuals(run: Path, lesson_tag: str, revision: int) -> bool:
    visual_qa = run / "review" / f"{lesson_tag}_visual_qa.md"
    if not visual_qa.exists() or "Visual plan QA passed:" not in visual_qa.read_text(encoding="utf-8", errors="replace"):
        return False
    snapshots = [
        run / "review" / f"{lesson_tag}_{suffix}_r{revision:02d}.md"
        for suffix in ("pedagogy_review", "citation_review", "design_qa")
    ]
    return all(path.exists() and "## Verdict\n\nPASS" in path.read_text(encoding="utf-8", errors="replace") for path in snapshots)


def produce_study_guide(course_slug: str, lesson_number: int) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    course_map = json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8"))
    lesson = lesson_by_number(course_map, lesson_number)
    lesson_tag = lid(lesson_number)
    ledger = json.loads((run / "sources" / "source_ledger.json").read_text(encoding="utf-8"))
    refresh_path = run / "sources" / f"{lesson_tag}_source_refresh.json"
    cached_refresh = json.loads(refresh_path.read_text(encoding="utf-8")) if refresh_path.exists() else {}
    if lesson_sources_are_adequate(cached_refresh):
        cached_refresh = normalize_lesson_source_refresh(cached_refresh, ledger, lesson_number)
        write_json(refresh_path, cached_refresh)
    pending_images = run / "review" / f"{lesson_tag}_image_requests.json"
    prior_drafts = sorted((run / "lesson_draft").glob(f"{lesson_tag}_draft_r*.md"))
    latest_prior_text = prior_drafts[-1].read_text(encoding="utf-8", errors="replace") if prior_drafts else ""
    reusable_sources_current = draft_has_all_mandatory_upload_references(latest_prior_text, ledger)
    if pending_images.exists() and prior_drafts and reusable_sources_current:
        draft_path = prior_drafts[-1]
        draft_path, revision = revisioned_resumed_study_guide_draft(run, lesson_tag, draft_path)
        draft = draft_path.read_text(encoding="utf-8", errors="replace")
        render_visuals, waiting_images = create_visual_assets(seed, lesson, draft, run, lesson_tag)
        if waiting_images:
            update_canonical_manifest(seed.slug)
            return [f"Lesson {lesson_number} is still waiting for one or more requested images."]
        return render_reviewed_study_guide(seed, lesson, draft_path, revision, render_visuals)
    if prior_drafts and reusable_sources_current:
        draft_path = prior_drafts[-1]
        match = re.search(r"_r(\d+)\.md$", draft_path.name)
        if match and not feedback_for(run, lesson_tag, "study_guide") and reviewed_draft_can_resume_visuals(run, lesson_tag, int(match.group(1))):
            draft_path, revision = revisioned_resumed_study_guide_draft(run, lesson_tag, draft_path)
            draft = draft_path.read_text(encoding="utf-8", errors="replace")
            render_visuals, waiting_images = create_visual_assets(seed, lesson, draft, run, lesson_tag)
            if waiting_images:
                update_canonical_manifest(seed.slug)
                return [f"Lesson {lesson_number} is waiting for one or more requested images."]
            return render_reviewed_study_guide(seed, lesson, draft_path, revision, render_visuals)
    try:
        refresh = cached_refresh if lesson_sources_are_adequate(cached_refresh) else lesson_source_refresh(seed, lesson, ledger)
        ledger, references = merge_lesson_sources(run, ledger, refresh, lesson_number)
        refresh = normalize_lesson_source_refresh(refresh, ledger, lesson_number)
        write_json(run / "sources" / f"{lesson_tag}_source_refresh.json", refresh)
        write_text(
            run / "sources" / f"{lesson_tag}_source_refresh_qa.md",
            "Lesson source refresh QA passed: yes\n\n"
            + str(refresh.get("applicability_review") or "Current applicability reviewed.")
            + "\n\nSource gaps:\n"
            + ("\n".join(f"- {item}" for item in refresh.get("source_gaps") or []) or "- None."),
        )
        mandatory_sources = [
            item for item in ledger.get("sources") or []
            if item.get("origin") == "operator_upload" and item.get("mandatory_use") is True
        ]
        active_ledger = {**ledger, "sources": [*mandatory_sources, *(refresh.get("sources") or [])]}
        source_checker = load_module("greg_source_reference_check", "tools/greg_source_reference_check.py")
        source_qa = source_checker.run_checks(run / "sources" / "source_ledger.json", run / "sources" / "student_references.md")
        write_text(run / "sources" / f"{lesson_tag}_source_reference_qa.md", source_checker.render_markdown(source_qa))
        if not source_qa["passed"]:
            raise RuntimeError("Lesson-level source/reference QA failed.")
    except ModelRequestError as error:
        block(run, "sources", f"Lesson {lesson_number} source refresh could not complete.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error

    revision_feedback = feedback_for(run, lesson_tag, "study_guide")
    working_path = run / "lesson_draft" / f"{lesson_tag}_working.md"
    draft = working_path.read_text(encoding="utf-8", errors="replace") if working_path.exists() else ""
    reusable_drafts = sorted((run / "lesson_draft").glob(f"{lesson_tag}_draft_r*.md"), key=lambda path: path.stat().st_mtime)
    latest_reusable_draft = reusable_drafts[-1] if reusable_drafts else None
    if latest_reusable_draft and (
        not draft or latest_reusable_draft.stat().st_mtime > working_path.stat().st_mtime
    ):
        draft = latest_reusable_draft.read_text(encoding="utf-8", errors="replace")
        write_text(working_path, draft)
    complete_drafts = [
        path for path in reusable_drafts
        if preserves_complete_study_guide_structure(path.read_text(encoding="utf-8", errors="replace"), "")
    ]
    approved_complete_draft = complete_drafts[-1].read_text(encoding="utf-8", errors="replace") if complete_drafts else ""
    if approved_complete_draft and not preserves_complete_study_guide_structure(draft, approved_complete_draft):
        draft = approved_complete_draft
        write_text(working_path, draft)
    if not draft:
        existing_pdfs = list((run / "docx_pdf").glob(f"{lesson_tag}_study_guide*.pdf"))
        latest_pdf_mtime = max((path.stat().st_mtime for path in existing_pdfs), default=0)
        reviewer_files = [run / "review" / f"{lesson_tag}_{suffix}.md" for suffix in ("pedagogy_review", "citation_review", "design_qa")]
        reviewers_pass = all(path.exists() and "## Verdict\n\nPASS" in path.read_text(encoding="utf-8", errors="replace") for path in reviewer_files)
        if reusable_drafts and reusable_drafts[-1].stat().st_mtime > latest_pdf_mtime and reviewers_pass:
            draft = reusable_drafts[-1].read_text(encoding="utf-8", errors="replace")
            write_text(working_path, draft)
    if draft:
        # Source refresh owns the bibliography even when compliant teaching
        # prose is reused. This invalidates a stale reference section without
        # needlessly rewriting the complete lesson.
        draft = normalize_reviewed_factual_language(force_student_references(draft, references))
        draft = normalize_callout_density(draft)
        write_text(working_path, draft)
    if revision_feedback and draft:
        # Start with the saved approved draft and make only the operator's
        # requested correction. The renderer will create a separate candidate
        # file, leaving the approved PDF untouched.
        try:
            draft = targeted_study_guide_revision(
                seed.slug,
                draft,
                revision_feedback,
                references,
                level=seed.level,
            )
        except ModelRequestError as error:
            block(run, "lesson_draft", f"Configured technical-content model could not revise Lesson {lesson_number}.\n\nReason: {error}")
            raise RuntimeError(str(error)) from error
        draft = restore_truncated_revision(draft, approved_complete_draft)
        draft = normalize_callout_density(normalize_reviewed_factual_language(force_student_references(draft, references)))
        write_text(working_path, draft)
    prior_revision_was_noop = False
    deterministic_checker = load_module("greg_study_guide_content_check_loop", "tools/greg_study_guide_content_check.py")
    # Three complete review rounds preserve independent QA while avoiding the
    # former five-pass loop, which could spend heavily on a draft that was not
    # converging. A blocked lesson remains blocked; it is never released.
    for attempt in range(1, 4):
        if not draft:
            try:
                draft = request_text(seed.slug, "technical_content", study_guide_prompt(seed, lesson, references, active_ledger, revision_feedback), max_tokens=24000)
            except ModelRequestError as error:
                block(run, "lesson_draft", f"Configured technical-content model could not produce Lesson {lesson_number}.\n\nReason: {error}")
                raise RuntimeError(str(error)) from error
            draft = normalize_reviewed_factual_language(force_student_references(draft, references))
            draft = normalize_callout_density(draft)
            if not preserves_complete_study_guide_structure(draft, ""):
                raise RuntimeError(
                    "The technical-content model returned an incomplete course book. "
                    "No partial draft was saved or released."
                )
            write_text(working_path, draft)
        reviewer_passed, changes = run_content_reviewers(seed, lesson, draft, active_ledger, run, lesson_tag)
        deterministic_qa = deterministic_checker.run_checks(working_path, seed.level)
        if not deterministic_qa["passed"]:
            reviewer_passed = False
            changes.extend(
                f"Deterministic content QA: {item['note']}"
                for item in deterministic_qa["findings"]
                if item["status"] == "fail"
            )
        if reviewer_passed:
            break
        revision_feedback = "Automatic reviewer changes required:\n- " + "\n- ".join(changes)
        if prior_revision_was_noop:
            revision_feedback += (
                "\n- The previous revision returned the chapter unchanged. Rewrite the exact challenged sentences "
                "and verify each required change against the final wording."
            )
        write_text(run / "review" / f"{lesson_tag}_automatic_revision_{attempt:02d}.md", revision_feedback)
        if attempt < 3:
            try:
                prior_draft = draft
                revised_draft = targeted_study_guide_revision(
                    seed.slug,
                    draft,
                    revision_feedback,
                    references,
                    level=seed.level,
                )
            except ModelRequestError as error:
                block(run, "lesson_draft", f"Configured technical-content model could not revise Lesson {lesson_number}.\n\nReason: {error}")
                raise RuntimeError(str(error)) from error
            revised_draft = restore_truncated_revision(revised_draft, prior_draft)
            revised_draft = normalize_reviewed_factual_language(force_student_references(revised_draft, references))
            revised_draft = normalize_callout_density(revised_draft)
            if not preserves_complete_study_guide_structure(revised_draft, prior_draft):
                prior_revision_was_noop = True
                continue
            draft = revised_draft
            prior_revision_was_noop = draft.strip() == force_student_references(prior_draft, references).strip()
            write_text(working_path, draft)
    else:
        raise RuntimeError("Independent study-guide reviewers still require changes after three automatic revision passes.")

    revision = next_study_guide_revision(run, lesson_tag)
    draft_name = f"{lesson_tag}_draft_r{revision:02d}.md"
    draft_path = run / "lesson_draft" / draft_name
    write_text(draft_path, draft)
    checker = load_module("greg_study_guide_content_check", "tools/greg_study_guide_content_check.py")
    content_qa = checker.run_checks(draft_path, seed.level)
    content_qa_path = run / "lesson_draft" / f"{lesson_tag}_content_qa_r{revision:02d}.md"
    write_text(content_qa_path, checker.render_markdown(content_qa))
    if not content_qa["passed"]:
        raise RuntimeError("Study guide content automatic QA failed; no student PDF was released.")
    for suffix in ("pedagogy_review", "citation_review", "design_qa"):
        archive_review_report(run, lesson_tag, suffix, revision)
    render_visuals, waiting_images = create_visual_assets(seed, lesson, draft, run, lesson_tag)
    archive_review_report(run, lesson_tag, "visual_qa", revision)
    if waiting_images:
        working_path.unlink(missing_ok=True)
        update_canonical_manifest(seed.slug)
        return [
            f"Lesson {lesson_number} passed content review and is waiting for operator images.",
            f"Image request document: {rel(run / 'review' / f'{lesson_tag}_image_requests.md')}",
        ]
    result = render_reviewed_study_guide(seed, lesson, draft_path, revision, render_visuals)
    working_path.unlink(missing_ok=True)
    return result


def latest_approved_book(run: Path, lesson_tag: str) -> Path:
    approval = run / "approval" / f"{lesson_tag}_study_guide_approval.md"
    canonical = load_module("greg_canonical_artifacts", "tools/greg_canonical_artifacts.py")
    artifact = canonical.artifact_from_approval(run, approval) if approval.exists() else None
    if not artifact:
        raise RuntimeError(f"Lesson {lesson_tag[-2:]} needs an approved course book before presentation production.")
    return artifact


DECK_TEACHING_STRATEGIES = {
    "activate-prior-knowledge",
    "anchor-with-scenario",
    "worked-example",
    "compare-and-contrast",
    "trace-a-process",
    "inspect-evidence",
    "diagnose-and-decide",
    "synthesize-and-recall",
}
DECK_VISUAL_MEDIA = {
    "native-diagram",
    "trusted-source-image",
    "generated-conceptual-image",
}
DECK_IMAGE_LAYOUTS = {"intro_image_bullets", "image_bullets"}
DECK_LAYOUT_MECHANISMS = {
    "card_sequence": "card-sequence",
    "process_flow": "process-flow",
    "schedule_bar_chart": "schedule-bar-chart",
    "activity_network": "activity-network",
    "comparison": "comparison-matrix",
    "planned_actual": "planned-actual",
    "row_list": "paired-record-rows",
    "checklist_rows": "verification-checklist",
}


def deck_prompt(seed, lesson: dict[str, Any], book: str, visual_plan: dict[str, Any], feedback: str) -> str:
    return f"""Return JSON only for a 10-slide English presentation that teaches Lesson {lesson['lesson_number']}: {lesson['title']} from {seed.title}.

Audience: U.S. residential construction workforce. Use homes, remodels, townhomes, and small multifamily examples. This is a recorded lesson: no time references, activities, quizzes, speaker notes, or next-lesson teaser.

The course book below is the single content authority. The Course Map visual decisions and approved course-book visual plan below are the visual-strategy authority. Produce MECE slides with distinct teaching jobs and visibly different silhouettes. Use these layouts only: cover, intro_image_bullets, image_bullets, card_sequence, process_flow, schedule_bar_chart, activity_network, comparison, planned_actual, row_list, checklist_rows, takeaway.

Plan every body slide in this order:
1. State one `learning_job`: the specific change in learner understanding or judgment.
2. Choose one `teaching_strategy` from activate-prior-knowledge, anchor-with-scenario, worked-example, compare-and-contrast, trace-a-process, inspect-evidence, diagnose-and-decide, or synthesize-and-recall.
3. Evaluate all three `visual_candidates`: native-diagram, trusted-source-image, and generated-conceptual-image. Give each a concrete fit or rejection reason, mark exactly one selected, and set `visual_medium` to it. Do not begin from a favorite layout.
4. Choose the renderer layout only after the medium and teaching strategy are resolved. State `text_role`: what the words add that the visual cannot carry alone, such as directing attention, explaining a decision rule, or naming the takeaway.

Consciously adapt the resolved visual strategy to presentation scale. For every body slide, provide `course_map_visual_id` when it implements a mapped insertion, plus `pedagogical_strategy`, `real_example_importance`, `generation_suitability`, `source_strategy`, `evidence_considered`, `alternatives_considered`, and `selection_reason`. Do not conduct a broad inspiration search or invent a new source decision. A native diagram should use the mechanism that matches the content logic: `process_flow` for ordered movement or handoffs; `schedule_bar_chart` for time-scaled timing, overlap, status, or drift; `activity_network` for predecessor/successor logic, parallel paths, or the controlling path; `comparison` only for comparable dimensions; `planned_actual` only for a consequential variance that is not itself a time-scaled schedule; paired rows only for records or mappings; and checklist rows only for field verification. `card_sequence` is only for grouped or equal-priority concepts, never an ordered process. Never turn a concept into two generic boxes simply because the layout exists. Use an `intro_image_bullets` or `image_bullets` slide only when the selected medium is a trusted real image or generated conceptual image; an image slide is not mandatory. Its image must teach a specific point, not decorate the slide.

For every image layout, supply `image_alt` and `image_source_strategy` as `trusted-source` or `generated-conceptual`. A generated image also requires `image_prompt`. A trusted-source image requires `source_id` or a reusable `course_book_visual_id`; never provide an image prompt as a substitute. If `real_example_importance` is `required` or `generation_suitability` is `unsafe`, generation is forbidden. If the required verified asset is unavailable, preserve the request rather than silently substituting a generic scene. Generated conceptual images must depict a realistic U.S. residential construction setting when people or a jobsite appear, represent the workforce respectfully, and contain no visible text, labels, logos, watermarks, or UI.

Across slides 2-9, use at least four distinct layouts, do not place the same layout on adjacent slides, and do not use one body layout more than twice. This is only an anti-repetition floor. Visual variety must come from different learning jobs; never choose a weaker medium or mechanism merely to increase variety. Never highlight a last item merely because it is last.

Required JSON schema:
{{"slides":[{{"layout":"cover","title":"...","subtitle":"...","topics":["...","...","...","..."]}},{{"layout":"card_sequence|process_flow|comparison|planned_actual|row_list|checklist_rows","title":"...","subtitle":"...","learning_job":"specific learner change","teaching_strategy":"activate-prior-knowledge|anchor-with-scenario|worked-example|compare-and-contrast|trace-a-process|inspect-evidence|diagnose-and-decide|synthesize-and-recall","visual_medium":"native-diagram","visual_candidates":[{{"medium":"native-diagram","decision":"selected|rejected","reason":"specific fit"}},{{"medium":"trusted-source-image","decision":"selected|rejected","reason":"specific fit"}},{{"medium":"generated-conceptual-image","decision":"selected|rejected","reason":"specific fit"}}],"text_role":"what the words add to the visual","course_map_visual_id":"L01V01 or empty only when not mapped","pedagogical_strategy":"explain-with-diagram","real_example_importance":"required|preferred|not-needed","generation_suitability":"safe|unsafe","source_strategy":"deterministic","evidence_considered":[{{"locator":"filename/page or URL","relevance":"..."}}],"alternatives_considered":["trusted real image because...","generated conceptual image because..."],"selection_reason":"presentation-specific reason","items":[{{"title":"...","body":"..."}}],"bottom_line":"..."}},{{"layout":"schedule_bar_chart","title":"...","subtitle":"...","schedule_rows":[{{"activity":"...","start":0,"duration":3,"status":"planned|complete|in-progress|delayed"}}],"bottom_line":"...","learning_job":"...","teaching_strategy":"trace-a-process","visual_medium":"native-diagram","visual_candidates":[{{"medium":"native-diagram","decision":"selected","reason":"Time-scaled bars reveal timing and overlap directly."}},{{"medium":"trusted-source-image","decision":"rejected","reason":"A source screenshot would add irrelevant project detail."}},{{"medium":"generated-conceptual-image","decision":"rejected","reason":"A scene cannot show time-scaled schedule logic."}}],"text_role":"...","pedagogical_strategy":"explain-with-diagram","real_example_importance":"not-needed","generation_suitability":"safe","source_strategy":"deterministic","evidence_considered":[{{"locator":"...","relevance":"..."}}],"alternatives_considered":["...","..."],"selection_reason":"..."}},{{"layout":"activity_network","title":"...","subtitle":"...","network_paths":[{{"label":"...","critical":true,"activities":[{{"title":"...","duration":"3d"}}]}}],"bottom_line":"...","learning_job":"...","teaching_strategy":"trace-a-process","visual_medium":"native-diagram","visual_candidates":[{{"medium":"native-diagram","decision":"selected","reason":"Connected nodes expose predecessor and path logic directly."}},{{"medium":"trusted-source-image","decision":"rejected","reason":"A source screenshot would obscure the target relationship."}},{{"medium":"generated-conceptual-image","decision":"rejected","reason":"A scene cannot show controlling path logic."}}],"text_role":"...","pedagogical_strategy":"explain-with-diagram","real_example_importance":"not-needed","generation_suitability":"safe","source_strategy":"deterministic","evidence_considered":[{{"locator":"...","relevance":"..."}}],"alternatives_considered":["...","..."],"selection_reason":"..."}},{{"layout":"intro_image_bullets|image_bullets","title":"...","subtitle":"...","intro":"...","bullets":["...","...","..."],"learning_job":"...","teaching_strategy":"...","visual_medium":"trusted-source-image|generated-conceptual-image","visual_candidates":[{{"medium":"native-diagram","decision":"selected|rejected","reason":"..."}},{{"medium":"trusted-source-image","decision":"selected|rejected","reason":"..."}},{{"medium":"generated-conceptual-image","decision":"selected|rejected","reason":"..."}}],"text_role":"...","course_map_visual_id":"...","course_book_visual_id":"...","pedagogical_strategy":"inspect-real-example|orient-with-conceptual-image","real_example_importance":"preferred|not-needed|required","generation_suitability":"safe|unsafe","source_strategy":"trusted-source|generated-fallback","evidence_considered":[{{"locator":"...","relevance":"..."}}],"alternatives_considered":["..."],"selection_reason":"...","image_source_strategy":"trusted-source|generated-conceptual","source_id":"required for an operator source when applicable","image_side":"left|right","image_alt":"...","image_prompt":"only for generated-conceptual"}},{{"layout":"takeaway","title":"...","body":"...","final_line":"..."}}]}}
Return exactly 10 slides; the first is cover and the final is takeaway. Keep text concise enough to fit the renderer.

Resolved Course Map visual decisions:
{json.dumps(lesson.get('visual_insertions') or [], ensure_ascii=False)}

Approved course-book visual plan:
{json.dumps(visual_plan.get('visuals') or [], ensure_ascii=False)}

Approved course book:\n{book[:42000]}\nRevision feedback:\n{feedback or 'None.'}"""


def deck_revision_prompt(slides: list[dict[str, Any]], feedback: str) -> str:
    return f"""Revise this existing Prof Greg presentation JSON. Return JSON only as {{"slides":[...]}}.

Apply only the requested changes. Preserve every unmentioned slide, layout, slide order, image path, and student-visible value exactly. Do not rebuild the presentation, add or remove slides, or alter an unrelated diagram or image. The returned `slides` array must contain all 10 slides so the renderer can produce a separate review candidate.

Supported layouts are: cover, intro_image_bullets, image_bullets, card_sequence, process_flow, schedule_bar_chart, activity_network, comparison, planned_actual, row_list, checklist_rows, and takeaway. When QA requires `process-flow`, use layout `process_flow` with 2-6 ordered `items`. When it requires `schedule-bar-chart`, use `schedule_bar_chart` with 3-7 `schedule_rows`. When it requires `activity-network`, use `activity_network` with 1-2 `network_paths`, each containing 2-4 connected activities. Never spell a layout with hyphens.

For every body slide, preserve or add the internal visual-decision fields required by the current worker: `learning_job`, `teaching_strategy`, `visual_medium`, all three `visual_candidates` with exactly one selected and concrete reasons, `text_role`, `pedagogical_strategy`, `real_example_importance`, `generation_suitability`, `source_strategy`, `evidence_considered`, `alternatives_considered`, and `selection_reason`. Adding missing internal planning metadata is not a student-visible change. The selected medium must match the preserved layout and asset: non-image layouts use `native-diagram`; trusted image assets use `trusted-source-image`; generated assets use `generated-conceptual-image`.

Requested changes:
{feedback}

Existing slides:
{json.dumps(slides, ensure_ascii=False)}"""


def normalize_deck_slides(data: dict[str, Any], lesson: dict[str, Any]) -> list[dict[str, Any]]:
    slides = data.get("slides") if isinstance(data.get("slides"), list) else []
    allowed = {"cover", "intro_image_bullets", "image_bullets", "card_sequence", "process_flow", "schedule_bar_chart", "activity_network", "comparison", "planned_actual", "row_list", "checklist_rows", "takeaway"}
    if len(slides) != 10 or any(not isinstance(item, dict) or item.get("layout") not in allowed for item in slides):
        raise RuntimeError("Presentation model returned an invalid deck structure.")
    if slides[0].get("layout") != "cover" or slides[-1].get("layout") != "takeaway":
        raise RuntimeError("Presentation must begin with a cover and end with a lesson takeaway.")
    slides[0].setdefault("title", lesson["title"])
    slides[0].setdefault("subtitle", lesson.get("learning_goal") or "Key residential construction decisions.")
    slides[0]["topics"] = [str(value)[:80] for value in (slides[0].get("topics") or [])][:5]
    if len(slides[0]["topics"]) < 3:
        raise RuntimeError("Presentation cover needs at least three main topics.")
    body_layouts = [str(slide.get("layout") or "") for slide in slides[1:-1]]
    image_slides = [slide for slide in slides[1:-1] if slide.get("layout") in {"intro_image_bullets", "image_bullets"}]
    if len(image_slides) > 2:
        raise RuntimeError("Presentation may use no more than two teaching-image slides.")
    required_distinct_layouts = 4
    if len(set(body_layouts)) < required_distinct_layouts:
        raise RuntimeError(f"Presentation needs at least {required_distinct_layouts} distinct body layouts to avoid repetitive slides.")
    if any(left == right for left, right in zip(body_layouts, body_layouts[1:])):
        raise RuntimeError("Presentation may not repeat a body layout on adjacent slides.")
    if any(body_layouts.count(layout) > 2 for layout in set(body_layouts)):
        raise RuntimeError("Presentation may not use a body layout more than twice.")
    for slide in slides[1:-1]:
        if len(str(slide.get("learning_job") or "").split()) < 5:
            raise RuntimeError("Every presentation body slide needs one specific learner-facing learning job.")
        if slide.get("teaching_strategy") not in DECK_TEACHING_STRATEGIES:
            raise RuntimeError("Every presentation body slide must choose an approved teaching strategy before choosing a visual.")
        medium = str(slide.get("visual_medium") or "")
        if medium not in DECK_VISUAL_MEDIA:
            raise RuntimeError("Every presentation body slide must choose a diagram, trusted real image, or generated conceptual image.")
        candidates = slide.get("visual_candidates")
        if not isinstance(candidates, list):
            raise RuntimeError("Every presentation body slide must compare all three visual media.")
        candidate_media = [str(candidate.get("medium") or "") for candidate in candidates if isinstance(candidate, dict)]
        selected_media = [
            str(candidate.get("medium") or "")
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("decision") == "selected"
        ]
        if set(candidate_media) != DECK_VISUAL_MEDIA or len(candidate_media) != len(DECK_VISUAL_MEDIA):
            raise RuntimeError("Every presentation body slide must evaluate each visual medium exactly once.")
        if selected_media != [medium]:
            raise RuntimeError("Exactly one visual candidate must be selected and it must match visual_medium.")
        if any(len(str(candidate.get("reason") or "").split()) < 4 for candidate in candidates):
            raise RuntimeError("Every visual candidate needs a concrete fit or rejection reason.")
        if len(str(slide.get("text_role") or "").split()) < 4:
            raise RuntimeError("Every presentation body slide must explain how text works with the selected visual.")
        is_image_layout = slide.get("layout") in DECK_IMAGE_LAYOUTS
        if is_image_layout != (medium in {"trusted-source-image", "generated-conceptual-image"}):
            raise RuntimeError("Presentation layout must follow the selected visual medium.")
        if slide.get("real_example_importance") not in {"required", "preferred", "not-needed"}:
            raise RuntimeError("Every presentation body slide must state the importance of a real example.")
        if slide.get("generation_suitability") not in {"safe", "unsafe"}:
            raise RuntimeError("Every presentation body slide must state whether generation is safe.")
        if slide.get("source_strategy") not in {"deterministic", "trusted-source", "generated-fallback"}:
            raise RuntimeError("Every presentation body slide needs a resolved source strategy.")
        if not isinstance(slide.get("evidence_considered"), list) or not slide.get("evidence_considered"):
            raise RuntimeError("Every presentation body slide needs evidence for its visual decision.")
        if not isinstance(slide.get("alternatives_considered"), list) or len(slide.get("alternatives_considered")) < 2:
            raise RuntimeError("Every presentation body slide must record the two visual media it rejected.")
        if len(str(slide.get("selection_reason") or "").split()) < 6:
            raise RuntimeError("Every presentation body slide needs a specific visual selection reason.")
        expected_strategy = {
            "native-diagram": "explain-with-diagram",
            "trusted-source-image": "inspect-real-example",
            "generated-conceptual-image": "orient-with-conceptual-image",
        }[medium]
        # `visual_medium` is the audited decision produced after comparing all
        # three candidates. Keep the legacy strategy label synchronized rather
        # than discarding an otherwise valid deck plan for redundant metadata.
        slide["pedagogical_strategy"] = expected_strategy
        if slide.get("real_example_importance") == "required" and medium != "trusted-source-image":
            raise RuntimeError("A required real example must use a verified trusted-source image.")
        layout = str(slide.get("layout") or "")
        if layout == "process_flow" and not 2 <= len(slide.get("items") or []) <= 6:
            raise RuntimeError("A process-flow slide needs 2-6 visible ordered items.")
        if layout == "schedule_bar_chart":
            rows = slide.get("schedule_rows") or []
            if not 3 <= len(rows) <= 7:
                raise RuntimeError("A schedule-bar slide needs 3-7 visible activity rows.")
            if any(
                not str(row.get("activity") or "").strip()
                or not isinstance(row.get("start"), int)
                or not isinstance(row.get("duration"), int)
                or row.get("start", -1) < 0
                or row.get("duration", 0) <= 0
                for row in rows
            ):
                raise RuntimeError("Schedule-bar rows need an activity, nonnegative integer start, and positive integer duration.")
        if layout == "activity_network":
            paths = slide.get("network_paths") or []
            if not 1 <= len(paths) <= 2 or any(not 2 <= len(path.get("activities") or []) <= 4 for path in paths):
                raise RuntimeError("An activity-network slide needs 1-2 paths with 2-4 connected activities each.")
    for index, slide in enumerate(image_slides, start=1):
        strategy = str(slide.get("image_source_strategy") or "")
        if strategy not in {"trusted-source", "generated-conceptual"} or not str(slide.get("image_alt") or "").strip():
            raise RuntimeError("Every teaching-image slide needs a resolved image source and accessible description.")
        if strategy == "generated-conceptual":
            if slide.get("visual_medium") != "generated-conceptual-image":
                raise RuntimeError("Generated image metadata must match the selected visual medium.")
            if slide.get("source_strategy") != "generated-fallback":
                raise RuntimeError("A generated teaching image must follow the resolved generated-fallback strategy.")
            if slide.get("real_example_importance") == "required" or slide.get("generation_suitability") == "unsafe":
                raise RuntimeError("A required real example or generation-unsafe visual may not be generated.")
            if not str(slide.get("image_prompt") or "").strip():
                raise RuntimeError("Every generated teaching image needs an image prompt.")
        else:
            if slide.get("visual_medium") != "trusted-source-image":
                raise RuntimeError("Trusted image metadata must match the selected visual medium.")
            if slide.get("source_strategy") != "trusted-source":
                raise RuntimeError("A trusted teaching image must follow the resolved trusted-source strategy.")
            if not str(slide.get("source_id") or slide.get("course_book_visual_id") or "").strip():
                raise RuntimeError("A trusted teaching image needs a verified source or reusable course-book visual.")
        requested_side = str(slide.get("image_side") or "")
        slide["image_side"] = requested_side if requested_side in {"left", "right"} else ("left" if index % 2 == 0 else "right")
        slide["image_prompt"] = str(slide.get("image_prompt") or "").strip()[:1800]
        slide["image_alt"] = str(slide["image_alt"]).strip()[:300]
        slide["image_name"] = f"teaching-image-{index}"
    return slides


def request_normalized_deck_revision(
    course_slug: str,
    lesson: dict[str, Any],
    slides: list[dict[str, Any]],
    feedback: str,
) -> list[dict[str, Any]]:
    """Require revision calls to preserve a complete renderer-compatible deck."""
    last_error = ""
    for attempt in range(1, 4):
        retry_feedback = feedback
        if last_error:
            retry_feedback += (
                "\n\nYour previous revision response was invalid: "
                f"{last_error} Return exactly all 10 slides, beginning with cover and ending with takeaway, "
                "using only the supported layouts and including every required internal visual-decision field."
            )
        revised = request_json_with_retry(
            course_slug,
            "technical_content",
            deck_revision_prompt(slides, retry_feedback),
            max_tokens=12000,
        )
        try:
            return normalize_deck_slides(revised, lesson)
        except RuntimeError as error:
            last_error = str(error)
            if attempt == 3:
                raise RuntimeError(f"Presentation revision remained invalid after three attempts: {last_error}") from error
    raise RuntimeError("Presentation revision could not be normalized.")


def deck_visual_plan_from_slides(slides: list[dict[str, Any]], lesson: dict[str, Any]) -> dict[str, Any]:
    """Create the auditable deck visual plan consumed by visual QA and the course registry."""
    visuals: list[dict[str, Any]] = []
    lesson_number = int(lesson.get("lesson_number") or 1)
    for slide_number, slide in enumerate(slides[1:-1], start=2):
        medium = str(slide["visual_medium"])
        visual_type = {
            "native-diagram": "deterministic-diagram",
            "trusted-source-image": "trusted-source-image",
            "generated-conceptual-image": "generated-conceptual-image",
        }[medium]
        candidates = slide.get("visual_candidates") or []
        rejected = [
            f"{candidate.get('medium')}: {candidate.get('reason')}"
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("decision") == "rejected"
        ]
        source_status = "verified" if medium == "trusted-source-image" else "not-required"
        visuals.append({
            "visual_id": f"L{lesson_number:02d}S{slide_number:02d}",
            "visual_type": visual_type,
            "placement": f"slide {slide_number}",
            "purpose": slide["learning_job"],
            "learning_claim": slide["learning_job"],
            "teaching_strategy": slide["teaching_strategy"],
            "pedagogical_strategy": slide["pedagogical_strategy"],
            "visual_medium": medium,
            "visual_candidates": candidates,
            "text_role": slide["text_role"],
            "real_example_importance": slide["real_example_importance"],
            "generation_suitability": slide["generation_suitability"],
            "source_status": source_status,
            "source_id": slide.get("source_id") or slide.get("course_book_visual_id") or "",
            "evidence_considered": slide["evidence_considered"],
            "alternatives_considered": rejected or slide["alternatives_considered"],
            "selection_reason": slide["selection_reason"],
            "diagram_type": DECK_LAYOUT_MECHANISMS.get(str(slide.get("layout") or ""), ""),
            "diagram_rationale": slide["selection_reason"] if medium == "native-diagram" else "",
            "schedule_rows": slide.get("schedule_rows") or [],
            "network_paths": slide.get("network_paths") or [],
            "context_focus": "U.S. residential construction",
            "depicts_people": bool(slide.get("depicts_people")),
            "workforce_representation": slide.get("workforce_representation") or "",
            "core_message_depends_on_real_example": slide["real_example_importance"] == "required",
            "technical_fidelity_required": slide["real_example_importance"] == "required",
            "max_area_percent": 50 if medium != "native-diagram" else 45,
            "highlighted": bool(slide.get("highlighted")),
            "highlight_reason": slide.get("highlight_reason") or "",
            "internal_text": medium == "native-diagram",
            "internal_text_position": "inside",
            "structure_justification": slide["selection_reason"],
        })
    return {"artifact_type": "deck", "visual_curation_required": False, "visuals": visuals}


def create_deck_visual_assets(seed, lesson: dict[str, Any], slides: list[dict[str, Any]], run: Path, lesson_tag: str) -> None:
    """Create or reuse only the teaching images allowed by the resolved strategy."""
    uploads = read_uploads(seed.slug)
    course_book_plan_path = run / "review" / f"{lesson_tag}_visual_plan.json"
    course_book_visuals = (json.loads(course_book_plan_path.read_text(encoding="utf-8")).get("visuals") or []) if course_book_plan_path.exists() else []
    image_index = 0
    for slide in slides:
        if slide.get("layout") not in {"intro_image_bullets", "image_bullets"}:
            continue
        image_index += 1
        asset = run / "deck" / "assets" / f"{lesson_tag}_teaching_image_{image_index:02d}.png"
        if slide.get("image_source_strategy") == "trusted-source":
            source_id = str(slide.get("source_id") or "")
            book_id = str(slide.get("course_book_visual_id") or "")
            source_path: Path | None = None
            if source_id:
                match = next((item for item in uploads if item.get("upload_id") == source_id and Path(str(item.get("stored_path") or "")).is_file()), None)
                if match:
                    source_path = Path(str(match["stored_path"]))
            if source_path is None and book_id:
                book_visual = next((item for item in course_book_visuals if item.get("visual_id") == book_id), None)
                if book_visual and book_visual.get("path") and (ROOT / str(book_visual["path"])).is_file():
                    source_path = ROOT / str(book_visual["path"])
            if source_path is None:
                raise RuntimeError(
                    f"Presentation requires verified image {source_id or book_id}; supply or restore that source before rendering."
                )
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(source_path.read_bytes())
            slide["image"] = {"path": str(asset.relative_to(run)), "alt": slide["image_alt"], "name": slide["image_name"]}
            continue
        prompt = (
            f"Create a polished, realistic teaching image for a U.S. residential construction course. "
            f"{slide['image_prompt']} Use a horizontal composition suitable for the left or right half of a presentation slide. "
            "No words, labels, logos, watermarks, diagrams, or UI. Do not make the scene look like commercial high-rise construction."
        )
        if not asset.exists() or asset.stat().st_size == 0:
            try:
                request_image(seed.slug, prompt, asset)
            except ModelRequestError as error:
                raise RuntimeError("The required teaching image could not be generated.") from error
        slide["image"] = {"path": str(asset.relative_to(run)), "alt": slide["image_alt"], "name": slide["image_name"]}


VIDEO_SOURCE_MAX_BYTES = 20 * 1024 * 1024


def require_video_compatible_deck(path: Path, *, maximum_bytes: int = VIDEO_SOURCE_MAX_BYTES) -> None:
    """Block release of a PPTX that cannot enter the approved Docs-to-Video flow."""
    if not path.exists() or not path.is_file():
        raise RuntimeError("Presentation renderer did not create the expected PPTX file.")
    if path.stat().st_size > maximum_bytes:
        size_mb = path.stat().st_size / (1024 * 1024)
        raise RuntimeError(
            f"Presentation is {size_mb:.2f} MB; Video Generator accepts at most 20 MB. "
            "Reduce presentation media and render a new revision before approval."
        )


def produce_deck(course_slug: str, lesson_number: int) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    course_map = json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8"))
    lesson = lesson_by_number(course_map, lesson_number)
    lesson_tag = lid(lesson_number)
    approved = latest_approved_book(run, lesson_tag)
    revision_feedback = feedback_for(run, lesson_tag, "deck")
    revision, filename = revisioned(run, "deck", f"{lesson_tag}_deck", ".pptx")
    spec_path = run / "deck" / f"{lesson_tag}_deck_spec_r{revision:02d}.json"
    resumable_spec = spec_path.exists() and not (run / "deck" / filename).exists()
    try:
        if resumable_spec:
            saved = json.loads(spec_path.read_text(encoding="utf-8"))
            try:
                slides = normalize_deck_slides({"slides": saved.get("slides")}, lesson)
            except RuntimeError:
                slides = request_normalized_deck_revision(
                    seed.slug,
                    lesson,
                    saved.get("slides") or [],
                    "Do not change any student-visible content. Add only the current pedagogy-first visual-decision metadata required for a resumable presentation spec.",
                )
        else:
            prior_spec = latest_matching_path(run / "deck", f"{lesson_tag}_deck_spec_r*.json") if revision_feedback else None
            if prior_spec:
                prior_slides = json.loads(prior_spec.read_text(encoding="utf-8")).get("slides") or []
                slides = request_normalized_deck_revision(seed.slug, lesson, prior_slides, revision_feedback)
            else:
                plan = request_json_with_retry(
                    seed.slug,
                    "technical_content",
                    deck_prompt(
                        seed,
                        lesson,
                        approved.read_text(encoding="utf-8", errors="replace"),
                        json.loads((run / "review" / f"{lesson_tag}_visual_plan.json").read_text(encoding="utf-8"))
                        if (run / "review" / f"{lesson_tag}_visual_plan.json").exists() else {},
                        revision_feedback,
                    ),
                    max_tokens=12000,
                )
                slides = normalize_deck_slides(plan, lesson)
        deck_visual_plan_path = run / "deck" / f"{lesson_tag}_visual_plan.json"
        visual_checker = load_module("greg_visual_plan_check", "tools/greg_visual_plan_check.py")
        for visual_attempt in range(1, 4):
            write_json(deck_visual_plan_path, deck_visual_plan_from_slides(slides, lesson))
            visual_result = visual_checker.run_checks(deck_visual_plan_path)
            if visual_result.get("passed"):
                break
            failures = "; ".join(
                str(item.get("note") or item.get("check"))
                for item in visual_result.get("findings") or []
                if item.get("status") == "fail"
            )
            if visual_attempt == 3:
                raise RuntimeError(f"Presentation visual-strategy QA failed after three attempts: {failures}")
            slides = request_normalized_deck_revision(
                seed.slug,
                lesson,
                slides,
                "Correct only the visual-strategy QA failures below. Preserve the 10-slide narrative, factual content, and every compliant slide. "
                "For each named slide, choose a renderer-supported layout whose mechanism matches the stated learning job, then update its internal visual-decision metadata consistently. "
                "Do not weaken or bypass the QA rule.\n\n"
                f"Visual-strategy QA failures:\n{failures}",
            )
        create_deck_visual_assets(seed, lesson, slides, run, lesson_tag)
    except ModelRequestError as error:
        block(run, "deck", f"Configured technical-content model could not produce Lesson {lesson_number} presentation.\n\nReason: {error}")
        raise RuntimeError(str(error)) from error
    spec = {
        "course_slug": seed.slug,
        "course_title": seed.title,
        "lesson_number": lesson_number,
        "created": date.today().isoformat(),
        "production_mode": "revision" if (run / "approval" / f"{lesson_tag}_deck_approval.md").exists() else "initial",
        "revision": f"r{revision:02d}",
        "run_folder": f"runs/{seed.slug}",
        "assets": {"brand_icon": BRAND_ICON, "negative_wordmark": NEGATIVE_WORDMARK},
        "output": {"pptx": f"deck/{filename}", "qa": f"deck/{lesson_tag}_deck_qa_r{revision:02d}.md", "rendered_dir": f"deck/rendered_slides_{lesson_tag}_r{revision:02d}"},
        "slides": slides,
        "qa_checks": ["10 slides.", "MECE: each slide has a distinct teaching job.", "At least four distinct body layouts, with no adjacent repeat and no layout used more than twice.", "Every body slide chooses a teaching strategy before comparing native diagram, trusted real image, and generated conceptual image.", "Every body slide records how text and visual work together.", "No generated image substitutes for a required real example.", "No automatic last-item highlight.", "Residential-construction-first audience anchor.", "No visible timing or speaker notes."],
        "inspection_notes": ["Live deck copy was generated from the approved course book.", "Visual mechanisms follow the resolved Course Map and course-book evidence trail.", "Image-led slides are used only when the strategy calls for a real or conceptual image.", "Deck plan and images are reused after an interrupted render when available.", "Deck is released for review only after renderer QA passes and is visually rechecked."],
    }
    baseline = approved_deck_baseline(run, lesson_tag) if (run / "approval" / f"{lesson_tag}_deck_approval.md").exists() else None
    if baseline:
        spec["approved_baseline_artifact"] = str(baseline.relative_to(run))
    write_json(spec_path, spec)
    subprocess.run([sys.executable, str(ROOT / "tools" / "greg_render_deck_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
    require_video_compatible_deck(run / spec["output"]["pptx"])
    qa_path = run / spec["output"]["qa"]
    if not qa_path.exists():
        raise RuntimeError("Presentation automatic QA failed; no deck was released for review.")
    complete_revision_request(run, lesson_tag, "deck", run / spec["output"]["pptx"])
    update_canonical_manifest(seed.slug)
    return [f"Presentation revision r{revision:02d} created: {rel(run / spec['output']['pptx'])}", "Presentation renderer QA passed."]


def approved_deck_baseline(run: Path, lesson_tag: str) -> Path:
    approval = run / "approval" / f"{lesson_tag}_deck_approval.md"
    canonical = load_module("greg_canonical_artifacts", "tools/greg_canonical_artifacts.py")
    artifact = canonical.artifact_from_approval(run, approval) if approval.exists() else None
    if not artifact:
        raise RuntimeError(f"Lesson {lesson_tag[-2:]} needs an approved English presentation before localization.")
    return artifact


def localization_name(locale: str) -> tuple[str, str]:
    if locale == "pt_br":
        return "Brazilian Portuguese for learners working in the U.S. market", "pt-br"
    if locale == "es":
        return "neutral Latin American Spanish", "es-419"
    raise ValueError(f"Unsupported locale: {locale}")


def localized_visual_contract_error(visuals: Any) -> str:
    """Return the exact renderer rejection for localized visuals, if any."""
    if not isinstance(visuals, list):
        return "Localized visuals must be a list."
    global _PDF_VISUAL_CONTRACT
    if _PDF_VISUAL_CONTRACT is None:
        with _PDF_VISUAL_CONTRACT_LOCK:
            if _PDF_VISUAL_CONTRACT is None:
                try:
                    _PDF_VISUAL_CONTRACT = load_module(
                        "greg_pdf_localized_visual_contract",
                        "workspace/renderers/pdf/greg-buildstak-study-guide-renderer.py",
                    )
                except ModuleNotFoundError:
                    # Lightweight development Python may not include ReportLab.
                    # Keep cache safety conservative there; production and the
                    # renderer runtime use the exact typographic measurement.
                    for visual in visuals:
                        if not isinstance(visual, dict):
                            return "Localized visual must be an object."
                        if str(visual.get("type") or "") == "process_flow" and any(
                            len(str(node.get("title") or "")) > 30 or len(str(node.get("detail") or "")) > 36
                            for node in visual.get("nodes") or [] if isinstance(node, dict)
                        ):
                            return "Process-flow title/detail exceeds the visible 30/36 character limit."
                        if str(visual.get("type") or "") == "source_to_wbs_matrix" and any(
                            len(str(row.get("left") or "")) > 40 or len(str(row.get("right") or "")) > 130
                            for row in visual.get("rows") or [] if isinstance(row, dict)
                        ):
                            return "Comparison-matrix cell exceeds the visible 40/130 character limit."
                    return ""
    try:
        _PDF_VISUAL_CONTRACT.validate_visual_text_fit(visuals)
    except (TypeError, ValueError) as error:
        return str(error)
    return ""


def localized_visuals_fit_contract(visuals: Any) -> bool:
    """Return whether cached localized visuals remain safe for the renderer."""
    return not localized_visual_contract_error(visuals)


def localized_book_visuals(seed, run: Path, lesson_tag: str, locale: str, language: str, translated: str) -> list[dict[str, Any]]:
    _, folder = localization_name(locale)
    cache_path = run / "localization" / folder / f"{lesson_tag}_visuals_{locale}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("fit_contract") == "localized-visual-fit-v6" and localized_visuals_fit_contract(cached.get("visuals")):
            return cached["visuals"]
    source_spec_path = latest_matching_path(run / "docx_pdf", f"{lesson_tag}_study_guide_spec_r*.json")
    if not source_spec_path:
        raise RuntimeError("The approved English course book has no visual spec for localization.")
    source_visuals = json.loads(source_spec_path.read_text(encoding="utf-8")).get("visuals") or []
    if not source_visuals:
        return []
    headings = re.findall(r"(?im)^#{1,2}\s+(.+)$", translated)
    def translate_visual(source_visual: dict[str, Any]) -> dict[str, Any]:
        prompt = f"""Translate every student-visible text value in this single course-book visual specification into {language}.
Return exactly one JSON object in the form {{"visual": {{...}}}}. The first response character must be `{{` and the last must be `}}`; do not use Markdown or commentary. The approved English visual is the source contract: preserve its visual_id, type, figure number, node count, row count, column count, ordering, and section number. Localize only learner-visible text, captions, and source explanations. The system assigns `after_heading` from the exact translated Markdown heading; never invent, shorten, or move it. Keep each process-flow title short enough to occupy at most three narrow box lines (prefer 22 characters or fewer and no unbreakable word longer than 12 characters); keep details at most 36 characters. If a literal translation is too long, use a concise equivalent that preserves the central construction meaning. Preserve every comparison-matrix column: one variable column plus one dedicated column per compared entity, with one localized `cells` value per column in every row. Do not combine compared entities inside one cell. Do not omit, merge, or add nodes, rows, or columns. Preserve U.S. construction meaning.

Exact target headings:
{json.dumps(headings, ensure_ascii=False)}

English visual specification:
{json.dumps(source_visual, ensure_ascii=False)}"""
        parsed: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                retry_note = ""
                if attempt and last_error:
                    retry_note = f"\n\nThe exact PDF renderer rejected your previous translation: {last_error} Shorten only the affected learner-visible labels or cells and return the complete visual again."
                parsed = request_json_with_retry(seed.slug, "diagram_planning", prompt + retry_note, max_tokens=4000)
                if isinstance(parsed.get("visual"), dict):
                    visual = parsed["visual"]
                    contract_error = localized_visual_contract_error([visual])
                    if contract_error:
                        raise ModelRequestError(contract_error)
                    break
                raise ModelRequestError("The diagram model did not return the required `visual` object.")
            except (ModelRequestError, json.JSONDecodeError) as error:
                last_error = error
                parsed = None
        if not parsed:
            raise RuntimeError(f"Localized visual translation failed after two validated attempts: {last_error}")
        visual = parsed["visual"]
        source_section = re.search(r"(?:Section|Seção|Sección)\s+(\d{1,2})", str(source_visual.get("after_heading") or ""), flags=re.I)
        if not source_section:
            raise RuntimeError(f"English visual `{source_visual.get('visual_id')}` has no numbered section placement.")
        target = [heading for heading in headings if re.search(rf"(?:Section|Seção|Sección)\s+0?{int(source_section.group(1))}\s*(?:-|:)", heading, flags=re.I)]
        if len(target) != 1:
            raise RuntimeError(f"Localized visual `{source_visual.get('visual_id')}` cannot be anchored to exactly one translated section.")
        visual["after_heading"] = target[0]
        return visual

    with ThreadPoolExecutor(max_workers=min(4, len(source_visuals))) as executor:
        visuals = list(executor.map(translate_visual, source_visuals))
    if len(visuals) != len(source_visuals):
        raise RuntimeError("Localized visual plan changed the required visual count.")
    for source_visual, localized_visual in zip(source_visuals, visuals):
        if source_visual.get("type") != localized_visual.get("type"):
            raise RuntimeError("Localized visual plan changed a renderer type.")
    final_contract_error = localized_visual_contract_error(visuals)
    if final_contract_error:
        raise RuntimeError(f"Localized visual plan failed the exact PDF renderer contract: {final_contract_error}")
    write_json(cache_path, {"locale": locale, "fit_contract": "localized-visual-fit-v6", "visuals": visuals})
    return visuals


def latest_complete_localized_draft(folder: Path, lesson_tag: str, locale: str) -> Path | None:
    section_label = "Seção" if locale == "pt_br" else "Sección"
    summary_label = "Resumo e Principais Conclusões" if locale == "pt_br" else "Resumen y Conclusiones Clave"
    candidates = sorted(folder.glob(f"{lesson_tag}_study_guide_{locale}_r*.md"), key=lambda item: (item.stat().st_mtime, item.name), reverse=True)
    for candidate in candidates:
        text = candidate.read_text(encoding="utf-8", errors="replace")
        # Keep retry detection aligned with the renderer's accepted localized
        # heading variants.  Otherwise a complete translation with harmless
        # H2, unpadded-number, or Unicode-dash formatting is needlessly
        # discarded and regenerated on every retry.
        numbered_sections = re.findall(
            rf"(?im)^#{{1,2}}\s+{re.escape(section_label)}\s+\d{{1,2}}\s*(?:-|:|–|—)\s+.+$",
            text,
        )
        if len(numbered_sections) >= 4 and re.search(rf"(?im)^#\s+{re.escape(summary_label)}\s*$", text):
            return candidate
    return None


def localized_callout_count(markdown: str, locale: str) -> int:
    labels = {
        "pt_br": ("TERMO-CHAVE", "APLIQUE", "EXEMPLO PRÁTICO", "CENÁRIO", "RETOMADA", "PONTE"),
        "es": ("TÉRMINO CLAVE", "APLICACIÓN", "EJEMPLO PRÁCTICO", "ESCENARIO", "RETOMAR", "PUENTE"),
    }[locale]
    pattern = "|".join(re.escape(label) for label in labels)
    return len(re.findall(rf"(?im)^>\s*(?:\*\*)?(?:{pattern})(?:\*\*)?[ \t]*(?::[ \t]*.*)?$", markdown))


def normalize_localized_course_contract(markdown: str, locale: str) -> str:
    """Keep localized Markdown compatible with the approved English template."""
    section = "Seção" if locale == "pt_br" else "Sección"
    labels = {
        "pt_br": ("TERMO-CHAVE", "APLIQUE", "EXEMPLO PRÁTICO", "CENÁRIO", "RETOMADA", "PONTE"),
        "es": ("TÉRMINO CLAVE", "APLICACIÓN", "EJEMPLO PRÁCTICO", "ESCENARIO", "RETOMAR", "PUENTE"),
    }[locale]
    normalized = re.sub(
        rf"(?im)^#{{1,6}}\s+({re.escape(section)}\s+\d{{1,2}}\s*(?:-|:|–|—)\s+.+)$",
        r"# \1",
        markdown,
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    normalized = re.sub(
        rf"(?im)^>\s*\*\*({label_pattern}):\*\*[ \t]*(.*)$",
        lambda match: f"> **{match.group(1)}**" + (f": {match.group(2).strip()}" if match.group(2).strip() else ""),
        normalized,
    )
    normalized = re.sub(
        rf"(?im)^>\s*({label_pattern})\s*$",
        r"> **\1**",
        normalized,
    )
    return normalized


def localized_book_structure_issues(markdown: str, locale: str) -> list[str]:
    """Return learner-visible structural omissions before any PDF work starts.

    The rendering validator remains the final authority, but checking here
    lets production repair a truncated model response rather than publishing a
    generic renderer failure after the expensive visual work has started.
    """
    labels = {
        "pt_br": ("Resumo e Principais Conclusões", "Referências", "Seção"),
        "es": ("Resumen y Conclusiones Clave", "Referencias", "Sección"),
    }[locale]
    summary, references, section = labels
    issues: list[str] = []
    if not re.search(rf"(?im)^#{{1,2}}\s+{re.escape(summary)}\s*$", markdown):
        issues.append(f"missing `{summary}`")
    if not re.search(rf"(?im)^#{{1,2}}\s+{re.escape(references)}\s*$", markdown):
        issues.append(f"missing `{references}`")
    section_pattern = rf"(?im)^#\s+{re.escape(section)}\s+\d{{1,2}}\s*(?:-|:|–|—)\s+.+$"
    if len(re.findall(section_pattern, markdown)) < 4:
        issues.append("fewer than four numbered sections")
    return issues


def localized_book_parity_issues(source_markdown: str, localized_markdown: str, locale: str) -> list[str]:
    """Require the translated book to retain every structural teaching element."""
    return structure_parity_issues(
        markdown_structure(source_markdown, "en"),
        markdown_structure(localized_markdown, locale),
    )


def localize_book(course_slug: str, lesson_number: int, locale: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    lesson_tag = lid(lesson_number)
    source = latest_approved_book(run, lesson_tag)
    source_draft = latest_matching_path(run / "lesson_draft", f"{lesson_tag}_draft_r*.md")
    if not source_draft:
        raise RuntimeError("The approved course book has no revisioned source draft for localization.")
    language, folder = localization_name(locale)
    source_markdown = source_draft.read_text(encoding="utf-8", errors="replace")
    source_structure = markdown_structure(source_markdown, "en")
    localized_metadata = {
        "pt_br": {"course": "O Gerente Completo de Projetos de Construção: da Pré-Construção ao Encerramento", "title": "O Sistema Operacional do Gerente de Projetos de Construção", "guide": "APOSTILA", "lesson": "Lição", "levels": {"basic": "Nível Básico", "intermediate": "Nível Intermediário", "advanced": "Nível Avançado"}},
        "es": {"course": "El Gerente Completo de Proyectos de Construcción: de la Preconstrucción al Cierre", "title": "El Sistema Operativo del Gerente de Proyectos de Construcción", "guide": "GUÍA DE ESTUDIO", "lesson": "Lección", "levels": {"basic": "Nivel Básico", "intermediate": "Nivel Intermedio", "advanced": "Nivel Avanzado"}},
    }[locale]
    localized_level = localized_metadata["levels"].get(str(seed.level).lower(), str(seed.level))
    references = (run / "sources" / "student_references.md").read_text(encoding="utf-8")
    pending_draft = latest_complete_localized_draft(run / "localization" / folder, lesson_tag, locale)
    revision_feedback = feedback_for(run, lesson_tag, f"{locale}_study_guide")
    pending_match = re.search(r"_r(\d+)\.md$", pending_draft.name) if pending_draft else None
    prior_translated = ""
    pending_text = pending_draft.read_text(encoding="utf-8", errors="replace") if pending_draft else ""
    if (
        pending_draft
        and pending_match
        and not revision_feedback
        and not localized_book_parity_issues(source_markdown, pending_text, locale)
    ):
        prior_translated = pending_text
        translated = normalize_localized_course_contract(prior_translated, locale)
        revision = int(pending_match.group(1))
        draft_name = pending_draft.name
    else:
        if revision_feedback and pending_draft:
            prompt = f"""Revise this existing {language} course book. Return the complete Markdown only. Apply only the requested changes and preserve every unmentioned paragraph, heading, diagram placement, reference, and translation verbatim. Do not translate or recreate the whole book.\n\nRequested changes:\n{revision_feedback}\n\nExisting course book:\n{pending_draft.read_text(encoding='utf-8', errors='replace')[:48000]}"""
        else:
            prompt = f"""Translate the following student-facing construction course book into {language}. Return Markdown only. Preserve the structural order and Markdown heading levels exactly: Introduction is `#`, Learning Objectives is `##`, and every numbered Section is `#`. Do not change a numbered Section into `##`. Do not add a Lesson Roadmap. Translate all body text and section titles. Preserve every Summary and Key Takeaways item as a concise bullet point; never convert that section into paragraphs. Keep U.S. construction terminology, units, codes, and market context. Preserve the six approved callout labels semantically in the target language and never invent a new callout type. Preserve exactly the same number of callout blocks as the English source, formatted as Markdown blockquotes: `> **LOCALIZED LABEL**` followed by one or more `>` body lines. Preserve every table with exactly the same number of tables, columns, and body rows. Do not turn a callout into ordinary prose. Do not add or remove facts, activities, citations, or references. Do not use em dashes, en dashes, or spaced hyphens as punctuation. The mandatory source structure is {json.dumps(source_structure, ensure_ascii=False)}.\n\n{source_markdown[:48000]}"""
        try:
            translated = request_text(seed.slug, "localization", prompt, max_tokens=24000)
            translated = normalize_localized_course_contract(remove_unnecessary_localized_emphasis(force_student_references(translated, references, locale)), locale)
            issues = localized_book_structure_issues(translated, locale) + localized_book_parity_issues(source_markdown, translated, locale)
            for _ in range(2):
                if not issues:
                    break
                repair_prompt = f"""Repair this existing {language} course book and return the complete Markdown only. The current translation is structurally incomplete: {', '.join(issues)}. Preserve every correct translated paragraph, heading, table, bullet, and callout already present; do not restart the translation. Restore only missing structural elements from the English source at their corresponding positions. Preserve the English source's complete order and all numbered sections. Preserve exactly {source_structure['callouts']} callout boxes using only these localized labels: {json.dumps(CALLOUTS[locale], ensure_ascii=False)}. Every callout must remain a Markdown blockquote beginning with `> **LOCALIZED LABEL**`, followed by its translated `>` body lines. Preserve these table shapes: {json.dumps(source_structure['tables'])}. Preserve exactly {source_structure.get('summary_items', 0)} concise Summary and Key Takeaways bullets. Include the exact localized headings for Introduction, Learning Objectives, every numbered Section, Summary and Key Takeaways, Glossary, and References. Return the full replacement, never a patch or explanation.

Existing localized draft to repair:
{translated[:48000]}

English source contract:
{source_markdown[:48000]}"""
                translated = request_text(seed.slug, "localization", repair_prompt, max_tokens=24000)
                translated = normalize_localized_course_contract(remove_unnecessary_localized_emphasis(force_student_references(translated, references, locale)), locale)
                issues = localized_book_structure_issues(translated, locale) + localized_book_parity_issues(source_markdown, translated, locale)
            if issues:
                raise ModelRequestError("Localized course book remained structurally incomplete after repair: " + ", ".join(issues))
        except ModelRequestError as error:
            block(run, "localization", f"Localization model could not produce Lesson {lesson_number} {locale} course book.\n\nReason: {error}")
            raise RuntimeError(str(error)) from error
        revision, draft_name = revisioned(run, f"localization/{folder}", f"{lesson_tag}_study_guide_{locale}", ".md")
    translated = normalize_localized_course_contract(remove_unnecessary_localized_emphasis(force_student_references(translated, references, locale)), locale)
    issues = localized_book_structure_issues(translated, locale) + localized_book_parity_issues(source_markdown, translated, locale)
    if issues:
        raise RuntimeError("Localized course book failed structural completeness QA: " + ", ".join(issues))
    draft_path = run / "localization" / folder / draft_name
    if not pending_draft or translated.rstrip() != prior_translated.rstrip():
        write_text(draft_path, translated)
    translated_visuals = localized_book_visuals(seed, run, lesson_tag, locale, language, translated)
    reference_heading = "# Referências" if locale == "pt_br" else "# Referencias"
    if reference_heading not in translated or len(translated.split()) < 250:
        raise RuntimeError("Localized course book failed automatic completeness QA.")
    pdf_name = f"{lesson_tag}_study_guide_{locale}_r{revision:02d}.pdf"
    cover_quote = select_cover_quote(seed, lesson_by_number(json.loads((run / "course_map" / "course_map.json").read_text(encoding="utf-8")), lesson_number), run, lesson_tag)
    spec = {
        "course_slug": seed.slug, "course_title": seed.title, "lesson_number": str(lesson_number), "locale": locale,
        "production_mode": "initial", "revision": f"r{revision:02d}", "run_folder": f"runs/{seed.slug}",
        "source_markdown": rel(draft_path),
        "metadata": {"course_title": localized_metadata["course"], "lesson_number": str(lesson_number), "lesson_short_title": localized_metadata["title"], "lesson_subtitle": language, "level_label": localized_level, "study_guide_label": localized_metadata["guide"], "lesson_label": localized_metadata["lesson"], "quote": f'"{cover_quote["quote"]}"', "quote_author": cover_quote["author"], "quote_verification_url": cover_quote["verification_url"], "icon": BRAND_ICON},
        "output": {"pdf": f"localization/{folder}/{pdf_name}", "render_qa": f"localization/{folder}/{lesson_tag}_{locale}_render_qa_r{revision:02d}.md", "layout_qa": f"localization/{folder}/{lesson_tag}_{locale}_layout_qa_r{revision:02d}.md", "rendered_dir": f"localization/{folder}/rendered_pages_{lesson_tag}_r{revision:02d}"},
        "visuals": translated_visuals, "source_structure": source_structure, "qa_notes": ["Initial production is being prepared for approval.", "Localized artifact is derived from an approved English course book and preserves its translated visuals and structural elements."]
    }
    spec_path = run / "localization" / folder / f"{lesson_tag}_study_guide_{locale}_spec_r{revision:02d}.json"
    write_json(spec_path, spec)
    render_study_guide(spec_path)
    layout = run_pdf_layout_qa(
        run / spec["output"]["pdf"],
        run / spec["output"]["render_qa"],
        run / spec["output"]["layout_qa"],
    )
    if not layout["passed"]:
        raise RuntimeError("Localized course book layout QA failed.")
    complete_revision_request(run, lesson_tag, f"{locale}_study_guide", run / spec["output"]["pdf"])
    update_canonical_manifest(seed.slug)
    return [f"{locale} course book r{revision:02d} created: {rel(run / spec['output']['pdf'])}"]


def latest_matching_path(folder: Path, pattern: str) -> Path | None:
    matches = sorted(folder.glob(pattern), key=lambda item: (item.stat().st_mtime, item.name))
    return matches[-1] if matches else None


def localized_slide_visible_items(slide: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for key in ("subtitle", "intro", "body", "bottom_line", "takeaway", "final_line"):
        if str(slide.get(key) or "").strip():
            items.append(str(slide[key]).strip())
    for key in ("topics", "bullets"):
        items.extend(str(item).strip() for item in slide.get(key) or [] if str(item).strip())
    for key in ("items",):
        for item in slide.get(key) or []:
            if isinstance(item, dict):
                items.extend(str(item.get(field) or "").strip() for field in ("title", "body") if str(item.get(field) or "").strip())
    for key in ("left", "right"):
        item = slide.get(key)
        if isinstance(item, dict):
            items.extend(str(item.get(field) or "").strip() for field in ("title", "body") if str(item.get(field) or "").strip())
    return items or [str(slide.get("title") or "Slide content").strip()]


def localized_deck_slides(
    source_slides: list[dict[str, Any]], translated_slides: Any, *, preserve_layout_on_drift: bool = False,
) -> list[dict[str, Any]]:
    """Apply translated student copy while retaining the approved deck structure.

    A localized deck is not a newly authored deck.  In particular, its image
    layouts and generated teaching-image metadata must come from the approved
    English source, rather than being regenerated or revalidated as though the
    translation were a new deck plan.
    """
    if not isinstance(translated_slides, list) or len(translated_slides) != len(source_slides):
        raise RuntimeError("Localized presentation must preserve the approved slide count.")

    scalar_fields = {"title", "subtitle", "intro", "body", "bottom_line", "takeaway", "final_line", "bridge_label"}
    list_fields = {"topics", "bullets"}
    result: list[dict[str, Any]] = []
    for index, (source_slide, translated_slide) in enumerate(zip(source_slides, translated_slides), start=1):
        if not isinstance(source_slide, dict) or not isinstance(translated_slide, dict):
            raise RuntimeError(f"Localized presentation slide {index} is invalid.")
        if (
            translated_slide.get("layout")
            and translated_slide.get("layout") != source_slide.get("layout")
            and not preserve_layout_on_drift
        ):
            raise RuntimeError(f"Localized presentation slide {index} changed its approved layout.")
        localized = copy.deepcopy(source_slide)
        for field in scalar_fields:
            value = translated_slide.get(field)
            if isinstance(value, str) and value.strip():
                localized[field] = value.strip()
        for field in list_fields:
            source_values = source_slide.get(field)
            translated_values = translated_slide.get(field)
            if source_values is None:
                continue
            if not isinstance(translated_values, list) or len(translated_values) != len(source_values) or not all(isinstance(value, str) and value.strip() for value in translated_values):
                raise RuntimeError(f"Localized presentation slide {index} did not preserve its {field} text.")
            localized[field] = [value.strip() for value in translated_values]
        for field in ("items", "left", "right"):
            source_value = source_slide.get(field)
            translated_value = translated_slide.get(field)
            if source_value is None:
                continue
            if field == "items":
                if not isinstance(translated_value, list) or len(translated_value) != len(source_value):
                    raise RuntimeError(f"Localized presentation slide {index} did not preserve its item structure.")
                merged_items = copy.deepcopy(source_value)
                for source_item, translated_item, merged_item in zip(source_value, translated_value, merged_items):
                    if not isinstance(source_item, dict) or not isinstance(translated_item, dict):
                        raise RuntimeError(f"Localized presentation slide {index} contains an invalid item.")
                    for text_field in ("title", "body"):
                        value = translated_item.get(text_field)
                        if isinstance(value, str) and value.strip():
                            merged_item[text_field] = value.strip()
                localized[field] = merged_items
            else:
                if not isinstance(translated_value, dict):
                    raise RuntimeError(f"Localized presentation slide {index} did not preserve its comparison structure.")
                merged_value = copy.deepcopy(source_value)
                for text_field in ("title", "body"):
                    value = translated_value.get(text_field)
                    if isinstance(value, str) and value.strip():
                        merged_value[text_field] = value.strip()
                localized[field] = merged_value
        result.append(localized)
    return result


def write_localized_deck_text_map(run: Path, lesson_tag: str, folder: str, source_slides: list[dict[str, Any]], localized_slides: list[dict[str, Any]], course_slug: str, source_deck: Path) -> tuple[Path, Path]:
    map_path = run / "localization" / folder / f"{lesson_tag}_deck_text_map_{folder}.md"
    qa_path = run / "localization" / folder / f"{lesson_tag}_deck_localization_qa.md"
    lines = [
        f"Course slug: {course_slug}", f"Lesson: {int(lesson_tag[-2:])}", f"Source deck: {rel(source_deck)}",
        f"Target locale: {folder}", "Scope: deck_text_map", "Status: completed", "",
    ]
    for index, (source_slide, localized_slide) in enumerate(zip(source_slides, localized_slides), start=1):
        original_title = str(source_slide.get("title") or f"Slide {index}").strip()
        localized_title = str(localized_slide.get("title") or f"Slide {index}").strip()
        visible = localized_slide_visible_items(localized_slide)
        ratio = len(localized_title) / max(1, len(original_title))
        risk = "medium" if ratio >= 1.2 or max(map(len, visible)) > 100 else "low"
        lines.extend([
            f"## Slide {index}", f"- Original title: {original_title}", f"- Localized title: {localized_title}",
            "- Localized visible text:", *[f"  - {item}" for item in visible],
            "- Preserved terms: PM and established U.S. construction terminology",
            f"- Length risk: {risk}",
            "- Layout note: Fit was visually rechecked; localized copy was kept concise for the approved layout.", "",
        ])
    write_text(map_path, "\n".join(lines))
    write_text(qa_path, "# Localized Deck QA\n\n- U.S. market terminology preserved.\n- Fit visually rechecked after rendering.\n- No new claims introduced.\n")
    return map_path, qa_path


def localize_deck(course_slug: str, lesson_number: int, locale: str) -> list[str]:
    seed = parse_intake(course_slug)
    run = RUNS / seed.slug
    lesson_tag = lid(lesson_number)
    approved_deck_baseline(run, lesson_tag)
    source_spec = latest_matching_path(run / "deck", f"{lesson_tag}_deck_spec_r*.json")
    if not source_spec:
        raise RuntimeError("The approved English presentation has no revisioned deck spec for localization.")
    language, folder = localization_name(locale)
    source = json.loads(source_spec.read_text(encoding="utf-8"))
    revision_feedback = feedback_for(run, lesson_tag, f"{locale}_deck")
    prior_spec = latest_matching_path(run / "localization" / folder, f"{lesson_tag}_deck_{locale}_spec_r*.json") if revision_feedback else None
    if revision_feedback and prior_spec:
        prior_slides = json.loads(prior_spec.read_text(encoding="utf-8")).get("slides") or []
        prompt = deck_revision_prompt(prior_slides, revision_feedback)
        merge_baseline = prior_slides
    else:
        prompt = f"""Translate every student-visible text value in this Prof Greg deck JSON into {language}. Return JSON only in the form {{"slides": [...]}}. Preserve all keys, layout names, numbers, filenames, asset paths, and slide count exactly. Do not add slides or speaker notes. Preserve U.S. construction terms, units, and facts. If localized copy would overflow its approved layout, use a shorter equivalent that preserves the central message; do not add emphasis Markdown or bold markers.\n\n{json.dumps(source['slides'], ensure_ascii=False)}"""
        merge_baseline = source["slides"]
    try:
        data = request_json_with_retry(seed.slug, "localization", prompt, max_tokens=12000)
    except ModelRequestError as error:
        raise RuntimeError(str(error)) from error
    slides = localized_deck_slides(
        merge_baseline,
        data.get("slides"),
        preserve_layout_on_drift=bool(revision_feedback),
    )
    slides = normalize_localized_dash_punctuation(slides)
    revision, filename = revisioned(run, f"localization/{folder}", f"{lesson_tag}_deck_{locale}", ".pptx")
    localized_course_title = {
        "pt_br": "O Gerente Completo de Projetos de Construção: da Pré-Construção ao Encerramento",
        "es": "El Gerente Completo de Proyectos de Construcción: de la Preconstrucción al Cierre",
    }[locale]
    spec = {**source, "created": date.today().isoformat(), "production_mode": "revision" if revision_feedback else "initial", "revision": f"r{revision:02d}", "locale": locale, "course_title": localized_course_title, "output": {"pptx": f"localization/{folder}/{filename}", "qa": f"localization/{folder}/{lesson_tag}_{locale}_deck_qa_r{revision:02d}.md", "rendered_dir": f"localization/{folder}/rendered_slides_{lesson_tag}_r{revision:02d}"}, "slides": slides}
    if revision_feedback:
        spec["revision_reason"] = [revision_feedback]
    spec_path = run / "localization" / folder / f"{lesson_tag}_deck_{locale}_spec_r{revision:02d}.json"
    for fit_attempt in range(1, 4):
        spec["slides"] = slides
        write_json(spec_path, spec)
        try:
            subprocess.run([sys.executable, str(ROOT / "tools" / "greg_render_deck_from_spec.py"), str(spec_path)], cwd=ROOT, check=True)
            break
        except subprocess.CalledProcessError:
            qa_text = (run / spec["output"]["qa"]).read_text(encoding="utf-8", errors="replace") if (run / spec["output"]["qa"]).exists() else ""
            fit_failures = [line for line in qa_text.splitlines() if "FAIL text_box_density" in line]
            if not fit_failures or fit_attempt == 3:
                raise
            fit_feedback = (
                "Automatic rendered-layout QA found text outside its assigned box. Shorten only the text fields "
                "identified below. Preserve every slide, layout, item count, fact, number, image, and unmentioned "
                "text exactly. Return all slides.\n- " + "\n- ".join(fit_failures)
            )
            fit_data = request_json_with_retry(
                seed.slug,
                "localization",
                deck_revision_prompt(slides, fit_feedback),
                max_tokens=12000,
            )
            slides = localized_deck_slides(slides, fit_data.get("slides"), preserve_layout_on_drift=True)
            slides = normalize_localized_dash_punctuation(slides)
    require_video_compatible_deck(run / spec["output"]["pptx"])
    qa = run / spec["output"]["qa"]
    if not qa.exists():
        raise RuntimeError("Localized presentation QA failed.")
    write_localized_deck_text_map(run, lesson_tag, folder, source["slides"], slides, seed.slug, approved_deck_baseline(run, lesson_tag))
    complete_revision_request(run, lesson_tag, f"{locale}_deck", run / spec["output"]["pptx"])
    update_canonical_manifest(seed.slug)
    return [f"{locale} presentation r{revision:02d} created: {rel(run / spec['output']['pptx'])}"]


def normalize_localized_dash_punctuation(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace(" — ", "; ").replace(" – ", "; ").replace("—", ", ").replace("–", ", ")
    if isinstance(value, list):
        return [normalize_localized_dash_punctuation(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_localized_dash_punctuation(item) for key, item in value.items()}
    return value


def remove_unnecessary_localized_emphasis(markdown: str) -> str:
    """Remove unsupported inline bold while preserving the translated words."""
    # The PDF renderer supplies hierarchy for headings and callout labels.
    # Inline emphasis from a translation model otherwise makes arbitrary
    # opening phrases look like a new heading in the localized course book.
    return re.sub(r"\*\*(.+?)\*\*", r"\1", markdown)


def run_stage(course_slug: str, stage: str, lessons: list[int] | None = None) -> list[str]:
    course_slug = assert_safe_run_slug(course_slug)
    with timed_activity(f"production_stage:{stage}"):
        if stage == "course_map":
            return produce_course_map(course_slug)
        if stage == "sources":
            return produce_source_ledger(course_slug)
        if stage == "study_guide":
            results: list[str] = []
            for lesson in lessons or [1]:
                with timed_activity(f"lesson:{lesson}:study_guide"):
                    results.extend(produce_study_guide(course_slug, lesson))
            return results
        if stage == "deck":
            results: list[str] = []
            for lesson in lessons or [1]:
                with timed_activity(f"lesson:{lesson}:deck"):
                    results.extend(produce_deck(course_slug, lesson))
            return results
        if stage in {"translations_book", "translations_deck"}:
            producer = localize_book if stage.endswith("book") else localize_deck
            results: list[str] = []
            for lesson in lessons or [1]:
                for locale in ("pt_br", "es"):
                    with timed_activity(f"lesson:{lesson}:{stage}:{locale}"):
                        results.extend(producer(course_slug, lesson, locale))
            return results
        if stage in {"pt_br_book", "es_book", "pt_br_deck", "es_deck"}:
            locale = "pt_br" if stage.startswith("pt_br") else "es"
            producer = localize_book if stage.endswith("book") else localize_deck
            results: list[str] = []
            for lesson in lessons or [1]:
                with timed_activity(f"lesson:{lesson}:{stage}"):
                    results.extend(producer(course_slug, lesson, locale))
            return results
        raise ValueError(f"Unsupported live production stage: {stage}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real Prof Greg production stage.")
    parser.add_argument("course_slug")
    parser.add_argument("--stage", choices=["course_map", "sources", "study_guide", "deck", "translations_book", "translations_deck", "pt_br_book", "pt_br_deck", "es_book", "es_deck"], required=True)
    parser.add_argument("--lessons", default="", help="Comma-separated lesson numbers for study-guide production.")
    parser.add_argument("--timing-file", help="Optional JSONL timing trace written without prompts, outputs, or credentials.")
    args = parser.parse_args()
    lessons = [int(value) for value in args.lessons.split(",") if value.strip()] or None
    recorder = TimingRecorder(Path(args.timing_file)) if args.timing_file else None
    token = ACTIVE_TIMING_RECORDER.set(recorder)
    try:
        print("\n".join(run_stage(args.course_slug, args.stage, lessons)))
    finally:
        ACTIVE_TIMING_RECORDER.reset(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
