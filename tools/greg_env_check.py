#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]
ESSENTIAL_KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
OPTIONAL_KEYS = [
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "OPENALEX_API_KEY",
    "AISTUDIOS_APP_ID",
    "AISTUDIOS_USER_KEY",
]
BASE_URL_KEYS = ["OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "GOOGLE_BASE_URL", "XAI_BASE_URL", "DEEPSEEK_BASE_URL", "OPENALEX_BASE_URL", "CROSSREF_BASE_URL", "SEMANTIC_SCHOLAR_BASE_URL"]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class EnvKeyStatus:
    key: str
    status: str
    length: int
    required: bool


def status_for_key(key: str, *, required: bool) -> EnvKeyStatus:
    value = os.environ.get(key, "")
    return EnvKeyStatus(key=key, status="set" if value else "missing", length=len(value), required=required)


def run_checks() -> dict[str, Any]:
    load_env_file(ROOT / ".env.local")
    statuses = [status_for_key(key, required=True) for key in ESSENTIAL_KEYS]
    statuses.extend(status_for_key(key, required=False) for key in OPTIONAL_KEYS)
    statuses.extend(status_for_key(key, required=False) for key in BASE_URL_KEYS)
    missing_required = [item.key for item in statuses if item.required and item.status != "set"]
    return {
        "passed": not missing_required,
        "missing_required": missing_required,
        "keys": [asdict(item) for item in statuses],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Prof Greg environment QA passed: {'yes' if data['passed'] else 'no'}",
        f"Missing required keys: {len(data['missing_required'])}",
        "",
        "Keys:",
    ]
    for item in data["keys"]:
        required = "required" if item["required"] else "optional"
        lines.append(f"- {item['key']}: {item['status']} length={item['length']} ({required})")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Prof Greg runtime environment without printing secret values.")
    parser.add_argument("--output", help="Optional Markdown output path.")
    args = parser.parse_args()

    data = run_checks()
    report = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
