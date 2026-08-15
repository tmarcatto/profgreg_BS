#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from greg_security import resolve_under_root


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_NODE = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node"
SETUP_ARTIFACT_WORKSPACE = (
    Path.home()
    / ".codex"
    / "plugins"
    / "cache"
    / "openai-primary-runtime"
    / "presentations"
    / "26.805.11740"
    / "skills"
    / "presentations"
    / "container_tools"
    / "setup_artifact_tool_workspace.mjs"
)
RENDERER_SOURCE = ROOT / "workspace" / "renderers" / "deck" / "greg-buildstak-deck-renderer.mjs"
SPEC_CHECK_SOURCE = ROOT / "tools" / "greg_artifact_spec_check.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_spec(spec_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("greg_artifact_spec_check", SPEC_CHECK_SOURCE)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load artifact spec checker: {SPEC_CHECK_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["greg_artifact_spec_check"] = module
    spec.loader.exec_module(module)
    data = module.run_checks(spec_path, "deck")
    if not data["passed"]:
        failures = [item for item in data["findings"] if item["status"] == "fail"]
        raise RuntimeError(f"Deck spec failed validation: {failures}")


def run_folder_from_spec(spec: dict[str, Any]) -> Path:
    run_folder = spec.get("run_folder")
    if not run_folder:
        raise ValueError("Deck spec is missing `run_folder`.")
    return resolve_under_root(str(run_folder))


def workspace_for_spec(spec_path: Path, spec: dict[str, Any]) -> Path:
    run_folder = run_folder_from_spec(spec)
    explicit = spec.get("renderer_workspace")
    if explicit:
        return resolve_under_root(str(explicit))
    return run_folder / "deck" / "tmp"


def node_path() -> Path:
    if BUNDLED_NODE.exists():
        return BUNDLED_NODE
    return Path("node")


def setup_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    if SETUP_ARTIFACT_WORKSPACE.exists():
        subprocess.run(
            [str(node_path()), str(SETUP_ARTIFACT_WORKSPACE), "--workspace", str(workspace)],
            cwd=ROOT,
            check=True,
        )
    else:
        (workspace / "package.json").write_text('{"private":true,"type":"module"}\n', encoding="utf-8")
    bundled_node_modules = BUNDLED_NODE.parent.parent / "node_modules"
    workspace_node_modules = workspace / "node_modules"
    if bundled_node_modules.exists() and not workspace_node_modules.exists():
        try:
            workspace_node_modules.symlink_to(bundled_node_modules, target_is_directory=True)
        except OSError:
            pass


def copy_renderer(workspace: Path) -> Path:
    if not RENDERER_SOURCE.exists():
        raise FileNotFoundError(f"Reusable renderer not found: {RENDERER_SOURCE}")
    target = workspace / RENDERER_SOURCE.name
    shutil.copy2(RENDERER_SOURCE, target)
    return target


def render(spec_path: Path, skip_setup: bool = False) -> Path:
    spec_path = resolve_under_root(spec_path)
    validate_spec(spec_path)
    spec = read_json(spec_path)
    workspace = workspace_for_spec(spec_path, spec)
    if not skip_setup:
        setup_workspace(workspace)
    renderer = copy_renderer(workspace)
    subprocess.run(
        [str(node_path()), str(renderer), "--spec", str(spec_path)],
        cwd=ROOT,
        check=True,
    )
    return run_folder_from_spec(spec) / spec["output"]["pptx"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Prof Greg BuildStak deck from a JSON deck spec.")
    parser.add_argument("spec", help="Path to deck spec JSON.")
    parser.add_argument("--skip-setup", action="store_true", help="Skip artifact-tool workspace setup and only copy/run renderer.")
    args = parser.parse_args()

    output = render(Path(args.spec), skip_setup=args.skip_setup)
    print(f"Rendered deck: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
