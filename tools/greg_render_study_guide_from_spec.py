#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

from greg_security import resolve_under_root


ROOT = Path(__file__).resolve().parents[1]
RENDERER_SOURCE = ROOT / "workspace" / "renderers" / "pdf" / "greg-buildstak-study-guide-renderer.py"
BUNDLED_PYTHON = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "bin" / "python3"
SPEC_CHECK_SOURCE = ROOT / "tools" / "greg_artifact_spec_check.py"
CONTENT_CHECK_SOURCE = ROOT / "tools" / "greg_study_guide_content_check.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_spec(spec_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("greg_artifact_spec_check", SPEC_CHECK_SOURCE)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load artifact spec checker: {SPEC_CHECK_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["greg_artifact_spec_check"] = module
    spec.loader.exec_module(module)
    data = module.run_checks(spec_path, "study_guide_pdf")
    if not data["passed"]:
        failures = [item for item in data["findings"] if item["status"] == "fail"]
        raise RuntimeError(f"Study-guide PDF spec failed validation: {failures}")


def validate_source_markdown(spec: dict[str, Any]) -> None:
    """Block rendering unless the student-facing source passes content QA."""
    source = spec.get("source_markdown")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Study-guide PDF spec is missing `source_markdown`.")
    source_path = resolve_under_root(source)
    locale = str(spec.get("locale") or "en")
    if locale in {"pt_br", "es"}:
        validate_localized_source(source_path, locale)
        return
    content_spec = importlib.util.spec_from_file_location("greg_study_guide_content_check_render", CONTENT_CHECK_SOURCE)
    if not content_spec or not content_spec.loader:
        raise RuntimeError(f"Could not load study-guide content checker: {CONTENT_CHECK_SOURCE}")
    checker = importlib.util.module_from_spec(content_spec)
    sys.modules["greg_study_guide_content_check_render"] = checker
    content_spec.loader.exec_module(checker)
    data = checker.run_checks(source_path)
    if not data["passed"]:
        failures = [item["note"] for item in data["findings"] if item["status"] == "fail"]
        raise RuntimeError("Study-guide source failed content validation; PDF was not rendered: " + " | ".join(failures))


def validate_localized_source(source_path: Path, locale: str) -> None:
    text = unicodedata.normalize("NFC", source_path.read_text(encoding="utf-8", errors="replace"))
    rules = {
        "pt_br": {
            "summary": "Resumo e Principais Conclusões", "references": "Referências", "section": "Seção",
            "callouts": {"TERMO-CHAVE", "APLIQUE", "EXEMPLO PRÁTICO", "CENÁRIO", "RETOMADA", "PONTE"},
        },
        "es": {
            "summary": "Resumen y Conclusiones Clave", "references": "Referencias", "section": "Sección",
            "callouts": {"TÉRMINO CLAVE", "APLICACIÓN", "EJEMPLO PRÁCTICO", "ESCENARIO", "RETOMAR", "PUENTE"},
        },
    }[locale]
    summary = re.search(rf"(?ims)^#\s+{re.escape(rules['summary'])}\s*$\n(.*?)(?=^#\s+|\Z)", text)
    if not summary:
        raise RuntimeError(f"Localized source is missing `{rules['summary']}`.")
    summary_lines = [line.strip() for line in summary.group(1).splitlines() if line.strip()]
    if not 4 <= len(summary_lines) <= 6 or not all(re.match(r"^[-*+]\s+\S", line) for line in summary_lines):
        raise RuntimeError("Localized summary must contain only 4 to 6 bullet points.")
    if len(re.findall(rf"(?im)^#\s+{re.escape(rules['section'])}\s+\d{{2}}\s*[:-]\s+.+$", text)) < 4:
        raise RuntimeError("Localized source must contain at least four numbered sections.")
    if not re.search(rf"(?im)^#\s+{re.escape(rules['references'])}\s*$", text):
        raise RuntimeError(f"Localized source is missing `{rules['references']}`.")
    # Localized production removes arbitrary inline bold so translated opening
    # phrases do not look like headings.  Callout labels may therefore arrive
    # as either `> **TERMO-CHAVE**` or the renderer's equally valid plain
    # form, `> TERMO-CHAVE`.  Plain blockquote body lines must not be mistaken
    # for labels, so only the approved vocabulary is accepted without bold.
    labels = re.findall(r"(?im)^>\s*\*\*([^*]+)\*\*\s*$", text)
    plain_pattern = "|".join(re.escape(label) for label in rules["callouts"])
    labels.extend(re.findall(rf"(?im)^>\s*({plain_pattern})[ \t]*$", text))
    if not 2 <= len(labels) <= 4:
        raise RuntimeError("Localized source must contain 2 to 4 callout blocks.")
    invalid = [label for label in labels if label.strip().upper() not in rules["callouts"]]
    if invalid:
        raise RuntimeError(f"Localized source contains unsupported callout labels: {invalid}.")


def run_folder_from_spec(spec: dict[str, Any]) -> Path:
    run_folder = spec.get("run_folder")
    if not run_folder:
        raise ValueError("Study-guide PDF spec is missing `run_folder`.")
    return resolve_under_root(str(run_folder))


def output_pdf_from_spec(spec: dict[str, Any]) -> Path:
    output = spec.get("output", {}).get("pdf")
    if not output:
        raise ValueError("Study-guide PDF spec is missing `output.pdf`.")
    return run_folder_from_spec(spec) / output


def python_path() -> Path:
    if BUNDLED_PYTHON.exists():
        return BUNDLED_PYTHON
    return Path("python3")


def render(spec_path: Path) -> Path:
    spec_path = resolve_under_root(spec_path)
    validate_spec(spec_path)
    spec = read_json(spec_path)
    validate_source_markdown(spec)
    expected = output_pdf_from_spec(spec)
    if not RENDERER_SOURCE.exists():
        raise FileNotFoundError(f"Reusable study-guide PDF renderer not found: {RENDERER_SOURCE}")
    result = subprocess.run(
        [str(python_path()), str(RENDERER_SOURCE), str(spec_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "PDF renderer returned no diagnostic output."
        raise RuntimeError(f"PDF rendering failed: {detail}")
    if not expected.exists():
        raise RuntimeError(f"Renderer did not create expected output: {expected}")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Prof Greg BuildStak study-guide PDF from a JSON spec.")
    parser.add_argument("spec", help="Path to study-guide PDF spec JSON.")
    args = parser.parse_args()
    output = render(Path(args.spec))
    print(f"Rendered study guide PDF: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
