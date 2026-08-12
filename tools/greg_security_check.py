#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_\-]{16,}",
    r"anthropic-[A-Za-z0-9_\-]{16,}",
    r"AIza[0-9A-Za-z_\-]{20,}",
    r"xai-[A-Za-z0-9_\-]{16,}",
]

SCAN_DIRS = ["tools", "workspace"]
SCAN_EXCLUDE_PARTS = {".git", ".cache", "__pycache__"}


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def mode_octal(path: Path) -> str:
    return oct(stat.S_IMODE(path.stat().st_mode))[-3:]


def iter_scanned_files() -> list[Path]:
    files: list[Path] = []
    for dirname in SCAN_DIRS:
        root = ROOT / dirname
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SCAN_EXCLUDE_PARTS for part in path.parts):
                continue
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".pptx", ".pdf", ".docx"}:
                continue
            files.append(path)
    return sorted(files)


def run_checks() -> dict[str, Any]:
    findings: list[Finding] = []

    gitignore = read_text(ROOT / ".gitignore")
    required_gitignore = [".env", ".env.*", "runtime/", "openclaw/", ".npm-cache/", "workspace/.cache/", "runs/**/input/*.pdf"]
    missing_gitignore = [item for item in required_gitignore if item not in gitignore]
    if missing_gitignore:
        findings.append(Finding("fail", "gitignore_sensitive_paths", f"Missing gitignore entries: {missing_gitignore}."))
    else:
        findings.append(Finding("pass", "gitignore_sensitive_paths", "Git ignore covers local secrets, runtime, caches, and uploaded PDFs."))

    env_file = ROOT / ".env.local"
    if env_file.exists():
        mode = mode_octal(env_file)
        if stat.S_IMODE(env_file.stat().st_mode) & (stat.S_IRWXG | stat.S_IRWXO):
            findings.append(Finding("fail", "env_file_permissions", f".env.local is too permissive: {mode}; expected 600."))
        else:
            findings.append(Finding("pass", "env_file_permissions", f".env.local permissions are restricted: {mode}."))
    else:
        findings.append(Finding("pass", "env_file_permissions", ".env.local is absent; no local secret file to protect."))

    shell_true_hits = []
    eval_hits = []
    secret_hits = []
    unguarded_outputs = []
    for path in iter_scanned_files():
        rel = str(path.relative_to(ROOT))
        text = read_text(path)
        if "shell=True" in text and rel not in {"tools/greg_security_check.py", "tools/greg_code_quality_check.py"}:
            shell_true_hits.append(rel)
        if re.search(r"\b(eval|exec)\s*\(", text) and not rel.endswith("greg_security_check.py"):
            eval_hits.append(rel)
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text):
                secret_hits.append(rel)
                break
        if re.search(r"Path\(args\.output\).*\.resolve\(\)", text) and "assert_safe_write_path" not in text:
            unguarded_outputs.append(rel)

    if shell_true_hits:
        findings.append(Finding("fail", "no_shell_true", f"subprocess shell=True found: {shell_true_hits}."))
    else:
        findings.append(Finding("pass", "no_shell_true", "No shell=True usage found in active Greg code."))

    if eval_hits:
        findings.append(Finding("fail", "no_eval_exec", f"eval/exec usage found: {eval_hits}."))
    else:
        findings.append(Finding("pass", "no_eval_exec", "No eval/exec usage found in active Greg code."))

    if secret_hits:
        findings.append(Finding("fail", "no_secret_literals", f"Secret-like literals found: {secret_hits}."))
    else:
        findings.append(Finding("pass", "no_secret_literals", "No secret-like literals found in active Greg code/config."))

    if unguarded_outputs:
        findings.append(Finding("warn", "unguarded_output_paths", f"Output paths should use greg_security.assert_safe_write_path: {unguarded_outputs}."))
    else:
        findings.append(Finding("pass", "unguarded_output_paths", "CLI output paths use the shared safe-write guard."))

    contracts = [
        ROOT / "workspace" / "contracts" / "model-routing-contract.md",
        ROOT / "workspace" / "contracts" / "source-ledger-contract.md",
        ROOT / "workspace" / "contracts" / "stage-execution-contract.md",
    ]
    missing_contracts = [str(path.relative_to(ROOT)) for path in contracts if not path.exists()]
    if missing_contracts:
        findings.append(Finding("fail", "security_relevant_contracts", f"Missing security-relevant contracts: {missing_contracts}."))
    else:
        findings.append(Finding("pass", "security_relevant_contracts", "Security-relevant operating contracts exist."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Prof Greg security QA passed: {'yes' if data['passed'] else 'no'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local security checks before putting Prof Greg online.")
    parser.add_argument("--output", help="Optional Markdown output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = run_checks()
    markdown = render_markdown(data)
    if args.output:
        output = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
