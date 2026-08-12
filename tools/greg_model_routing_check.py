#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "workspace" / "config" / "model-routing.json"

REQUIRED_ROLES = [
    "course_architect",
    "source_research",
    "technical_content",
    "pedagogy_review",
    "citation_review",
    "design_review",
    "visual_planning",
    "diagram_planning",
    "diagram_rendering",
    "image_generation",
    "pptx_generation",
    "docx_pdf_generation",
    "localization",
    "localization_review",
]

MODEL_PATTERNS = [
    r"\bgpt-[a-z0-9.\-]+",
    r"\bclaude-[a-z0-9.\-]+",
    r"\bgemini-[a-z0-9.\-]+",
    r"\bgrok-[a-z0-9.\-]+",
    r"\bdeepseek-[a-z0-9.\-]+",
]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9_\-]{16,}",
    r"anthropic-[A-Za-z0-9_\-]{16,}",
    r"AIza[0-9A-Za-z_\-]{20,}",
]


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


def provider_refs(binding: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    primary = binding.get("primary")
    if isinstance(primary, dict) and primary.get("provider"):
        refs.append(primary["provider"])
    for key in ("fallbacks", "cost_optimization_candidates", "metadata_helpers"):
        items = binding.get(key) or []
        if key == "metadata_helpers":
            refs.extend(str(item) for item in items)
            continue
        for item in items:
            if isinstance(item, dict) and item.get("provider"):
                refs.append(item["provider"])
    premium = binding.get("premium_escalation")
    if isinstance(premium, dict) and premium.get("provider"):
        refs.append(premium["provider"])
    return refs


def run_checks(config_path: Path = CONFIG) -> dict[str, Any]:
    findings: list[Finding] = []
    config = load_json(config_path)
    text = read_text(config_path)

    if config_path.exists():
        findings.append(Finding("pass", "config_exists", "Model routing config exists."))
    else:
        findings.append(Finding("fail", "config_exists", "Model routing config is missing."))

    providers = config.get("providers") or {}
    bindings = config.get("bindings") or {}
    policy = config.get("policy") or {}

    if providers:
        findings.append(Finding("pass", "providers_present", f"Providers configured: {len(providers)}."))
    else:
        findings.append(Finding("fail", "providers_present", "No providers configured."))

    missing_roles = [role for role in REQUIRED_ROLES if role not in bindings]
    if missing_roles:
        findings.append(Finding("fail", "required_roles", f"Missing role bindings: {missing_roles}."))
    else:
        findings.append(Finding("pass", "required_roles", "All required role bindings are present."))

    missing_provider_refs = []
    for role, binding in bindings.items():
        for provider in provider_refs(binding):
            if provider not in providers:
                missing_provider_refs.append((role, provider))
    if missing_provider_refs:
        findings.append(Finding("fail", "provider_references", f"Bindings reference unknown providers/helpers: {missing_provider_refs}."))
    else:
        findings.append(Finding("pass", "provider_references", "All binding provider/helper references exist."))

    provider_secret_issues = []
    for name, provider in providers.items():
        if provider.get("kind") != "local_engine" and provider.get("api_key_env") == "":
            provider_secret_issues.append((name, "blank api_key_env"))
        api_value = provider.get("api_key") or provider.get("secret") or provider.get("token")
        if api_value:
            provider_secret_issues.append((name, "secret-like field present"))
    if provider_secret_issues:
        findings.append(Finding("fail", "provider_secret_fields", f"Provider secret issues: {provider_secret_issues}."))
    else:
        findings.append(Finding("pass", "provider_secret_fields", "Providers reference env vars only; no secret fields found."))

    secrets_found = []
    for pattern in SECRET_PATTERNS:
        if re.search(pattern, text):
            secrets_found.append(pattern)
    if secrets_found:
        findings.append(Finding("fail", "secret_literals", f"Secret-like literals found in routing config: {secrets_found}."))
    else:
        findings.append(Finding("pass", "secret_literals", "No secret-like literals found in routing config."))

    if policy.get("no_hardcoded_models_in_skills") is True and policy.get("secrets_location") == "environment_variables_only":
        findings.append(Finding("pass", "policy_flags", "Policy flags require no hardcoded skill models and env-only secrets."))
    else:
        findings.append(Finding("fail", "policy_flags", "Required policy flags are missing or false."))

    skill_hits = []
    for path in sorted((ROOT / "workspace" / "skills").glob("*/SKILL.md")):
        skill_text = read_text(path)
        for pattern in MODEL_PATTERNS:
            if re.search(pattern, skill_text, flags=re.IGNORECASE):
                skill_hits.append(str(path.relative_to(ROOT)))
                break
    if skill_hits:
        findings.append(Finding("fail", "skills_hardcoded_models", f"Skills contain model/provider IDs: {skill_hits}."))
    else:
        findings.append(Finding("pass", "skills_hardcoded_models", "No hardcoded model IDs found in skills."))

    deterministic_roles = ["diagram_rendering", "pptx_generation", "docx_pdf_generation"]
    bad_deterministic = []
    for role in deterministic_roles:
        primary = (bindings.get(role) or {}).get("primary") or {}
        if primary.get("provider") != "local_deterministic":
            bad_deterministic.append(role)
    if bad_deterministic:
        findings.append(Finding("fail", "deterministic_roles", f"Deterministic roles not routed locally: {bad_deterministic}."))
    else:
        findings.append(Finding("pass", "deterministic_roles", "Deterministic rendering roles route to local_deterministic."))

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "config": str(config_path),
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Model routing QA passed: {'yes' if data['passed'] else 'no'}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        f"Config: {data['config']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Prof Greg model/API routing configuration.")
    parser.add_argument("--config", default=str(CONFIG), help="Path to model-routing.json.")
    parser.add_argument("--output", help="Optional path to write Markdown report.")
    parser.add_argument("--json", action="store_true", help="Print JSON.")
    args = parser.parse_args()

    data = run_checks(Path(args.config).expanduser().resolve())
    markdown = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(markdown)
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
