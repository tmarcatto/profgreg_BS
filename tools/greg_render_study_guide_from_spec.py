#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
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
    subprocess.run([str(python_path()), str(RENDERER_SOURCE), str(spec_path)], cwd=ROOT, check=True)
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
