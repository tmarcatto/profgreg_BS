#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]

SERVER_PATHS = [
    "/opt/profgreg/app",
    "/srv/profgreg/uploads",
    "/srv/profgreg/outputs",
    "/var/log/profgreg",
    "/etc/profgreg",
]


@dataclass
class Finding:
    status: str
    check: str
    note: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return result.returncode, output


def git_value(root: Path, args: list[str]) -> str | None:
    code, output = run_command(["git", *args], root)
    return output if code == 0 else None


def path_status(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    return {
        "path": path_text,
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "readable": os.access(path, os.R_OK),
        "writable": os.access(path, os.W_OK),
    }


def qa_report_passed(path: Path) -> bool | None:
    if not path.exists():
        return None
    text = read_text(path).lower()
    if "pre-push qa passed: yes" in text:
        return True
    if "pre-push qa passed: no" in text:
        return False
    return None


def run_checks(root: Path = ROOT, *, mode: str = "auto", expected_branch: str = "main") -> dict[str, Any]:
    findings: list[Finding] = []
    root = root.resolve()
    server_mode = mode == "server" or (mode == "auto" and str(root) == "/opt/profgreg/app")

    if root.exists():
        findings.append(Finding("pass", "checkout_exists", f"Checkout exists at {root}."))
    else:
        findings.append(Finding("fail", "checkout_exists", f"Checkout is missing at {root}."))

    branch = git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"]) if (root / ".git").exists() else None
    commit = git_value(root, ["rev-parse", "--short", "HEAD"]) if (root / ".git").exists() else None
    status = git_value(root, ["status", "--short"]) if (root / ".git").exists() else None

    if commit:
        findings.append(Finding("pass", "git_commit", f"Current commit is {commit}."))
    else:
        findings.append(Finding("fail", "git_commit", "Could not read current Git commit."))

    if branch == expected_branch:
        findings.append(Finding("pass", "git_branch", f"Current branch is {branch}."))
    else:
        findings.append(Finding("warn", "git_branch", f"Current branch is {branch or 'unknown'}; expected {expected_branch}."))

    if status == "":
        findings.append(Finding("pass", "git_clean", "Git checkout is clean."))
    elif status is None:
        findings.append(Finding("fail", "git_clean", "Could not read Git status."))
    else:
        findings.append(Finding("warn", "git_clean", "Git checkout has local changes."))

    required_docs = [
        "workspace/contracts/deployment-environment-contract.md",
        "workspace/contracts/online-agent-security-contract.md",
        "workspace/ops/server-bootstrap-2026-08-13.md",
    ]
    missing_docs = [item for item in required_docs if not (root / item).exists()]
    if missing_docs:
        findings.append(Finding("fail", "server_docs", f"Missing server/deployment docs: {missing_docs}."))
    else:
        findings.append(Finding("pass", "server_docs", "Server/deployment docs exist."))

    deploy_qa = root / "tmp" / "deploy_qa.md"
    deploy_qa_state = qa_report_passed(deploy_qa)
    if deploy_qa_state is True:
        findings.append(Finding("pass", "deploy_qa_report", "Latest deploy-safe QA report says passed."))
    elif deploy_qa_state is False:
        findings.append(Finding("fail", "deploy_qa_report", "Latest deploy-safe QA report says failed."))
    else:
        status_level = "warn" if server_mode else "pass"
        note = "Deploy-safe QA report is missing or unreadable." if server_mode else "Deploy-safe QA report is optional outside the server."
        findings.append(Finding(status_level, "deploy_qa_report", note))

    env_path = Path("/etc/profgreg/profgreg.env") if server_mode else root / ".env.local"
    if env_path.exists():
        findings.append(Finding("pass", "runtime_env_file", f"Runtime env file exists at {env_path}."))
    else:
        findings.append(Finding("warn", "runtime_env_file", f"Runtime env file not found at {env_path}."))

    if server_mode:
        if os.geteuid() == 0:
            findings.append(Finding("warn", "runtime_user", "Server status is running as root; production checks should run as profgreg where possible."))
        else:
            findings.append(Finding("pass", "runtime_user", f"Server status is running as uid {os.geteuid()}."))

        missing_paths = [item for item in SERVER_PATHS if not Path(item).exists()]
        if missing_paths:
            findings.append(Finding("fail", "server_storage_paths", f"Missing expected server paths: {missing_paths}."))
        else:
            findings.append(Finding("pass", "server_storage_paths", "Expected server storage/config paths exist."))
    else:
        findings.append(Finding("pass", "server_storage_paths", "Server storage path check skipped outside server mode."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "mode": "server" if server_mode else "local",
        "root": str(root),
        "commit": commit,
        "branch": branch,
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "server_paths": [path_status(item) for item in SERVER_PATHS] if server_mode else [],
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Prof Greg server status passed: {'yes' if data['passed'] else 'no'}",
        f"Mode: {data['mode']}",
        f"Root: {data['root']}",
        f"Commit: {data.get('commit') or 'unknown'}",
        f"Branch: {data.get('branch') or 'unknown'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    if data.get("server_paths"):
        lines.extend(["", "Server Paths:"])
        for item in data["server_paths"]:
            flags = []
            flags.append("exists" if item["exists"] else "missing")
            flags.append("dir" if item["is_dir"] else "not-dir")
            flags.append("readable" if item["readable"] else "not-readable")
            flags.append("writable" if item["writable"] else "not-writable")
            lines.append(f"- {item['path']}: {', '.join(flags)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Prof Greg local/server deployment status without exposing secrets.")
    parser.add_argument("--root", default=str(ROOT), help="Checkout root. Defaults to this repository.")
    parser.add_argument("--mode", choices=["auto", "local", "server"], default="auto")
    parser.add_argument("--expected-branch", default="main")
    parser.add_argument("--output", help="Optional Markdown output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = run_checks(Path(args.root), mode=args.mode, expected_branch=args.expected_branch)
    report = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else report, end="" if args.json else "")
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
