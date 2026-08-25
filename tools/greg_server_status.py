#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from greg_security import assert_safe_write_path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "workspace/contracts/server-operations-contract.md"
LOGROTATE_SAMPLE = "workspace/ops/logrotate-profgreg.conf"
BACKUP_SERVICE_SAMPLE = "workspace/ops/profgreg-backup.service"
BACKUP_TIMER_SAMPLE = "workspace/ops/profgreg-backup.timer"
WORKER_SERVICE_SAMPLE = "workspace/ops/profgreg-worker.service"
UI_SERVICE_SAMPLE = "workspace/ops/profgreg-ui.service"
SERVER_BACKUP_ROOT = Path("/srv/profgreg/backups")
SERVER_UPLOADS = Path("/srv/profgreg/uploads")
SERVER_OUTPUTS = Path("/srv/profgreg/outputs")
SERVER_LOGS = Path("/var/log/profgreg")
SERVER_SECRETS = Path("/etc/profgreg")
LOCAL_JOB_ROOT = ROOT / "tmp" / "jobs"
SERVER_JOB_ROOT = Path("/srv/profgreg/jobs")

JOB_STATES = {"queued", "running", "needs_approval", "completed", "failed", "cancelled"}
JOB_REQUEST_TYPES = {"course_status", "course_start", "stage_next", "lesson_lifecycle", "production_stage", "backup", "full_flow_v1_test"}
JOB_TRANSITIONS = {
    "queued": {"running", "failed", "cancelled"},
    "running": {"needs_approval", "completed", "failed", "cancelled"},
    "needs_approval": {"running", "completed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}

SERVER_PATHS = [
    "/opt/profgreg/app",
    "/srv/profgreg/uploads",
    "/srv/profgreg/outputs",
    "/srv/profgreg/backups",
    "/srv/profgreg/jobs",
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


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_inventory(root: Path, *, include_patterns: tuple[str, ...] = ("*",)) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if not any(path.match(pattern) for pattern in include_patterns):
            continue
        stat = path.stat()
        items.append(
            {
                "path": str(path.relative_to(root)),
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return items


def qa_report_passed(path: Path) -> bool | None:
    if not path.exists():
        return None
    text = read_text(path).lower()
    if "pre-push qa passed: yes" in text:
        return True
    if "pre-push qa passed: no" in text:
        return False
    return None


def safe_backup_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    allowed_local = (ROOT / "tmp").resolve()
    allowed_server = SERVER_BACKUP_ROOT.resolve()
    if resolved == allowed_local or allowed_local in resolved.parents:
        return resolved
    if resolved == allowed_server or allowed_server in resolved.parents:
        return resolved
    raise ValueError(f"Backup root must stay under {allowed_server} or {allowed_local}: {path}")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug[:64] or "job"


def safe_job_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    local = LOCAL_JOB_ROOT.resolve()
    server = SERVER_JOB_ROOT.resolve()
    if resolved == local or local in resolved.parents:
        return resolved
    if resolved == server or server in resolved.parents:
        return resolved
    raise ValueError(f"Job root must stay under {server} or {local}: {path}")


def safe_job_id(value: str) -> str:
    if not re.fullmatch(r"job_[0-9]{8}T[0-9]{6}Z_[a-z0-9_-]{1,64}", value):
        raise ValueError(f"Unsafe job id: {value}")
    return value


def job_event(job_dir: Path, event_type: str, payload: dict[str, Any]) -> None:
    line = json.dumps({"at": iso_now(), "event": event_type, **payload}, ensure_ascii=False)
    with (job_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_job(job_dir: Path, data: dict[str, Any]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def create_job(
    *,
    job_root: Path = LOCAL_JOB_ROOT,
    request_type: str,
    course_slug: str | None = None,
    lesson: int | None = None,
    requested_by: str = "operator",
    input_summary: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if request_type not in JOB_REQUEST_TYPES:
        raise ValueError(f"Unsupported request_type: {request_type}")
    root = safe_job_root(job_root)
    now = iso_now()
    base_job_id = f"job_{now.replace(':', '').replace('-', '')}_{safe_slug(request_type)}"
    job_id = base_job_id
    suffix = 2
    while (root / job_id).exists():
        job_id = f"{base_job_id}-{suffix}"
        suffix += 1
    job_dir = root / job_id
    data = {
        "job_id": job_id,
        "created_at": now,
        "updated_at": now,
        "state": "queued",
        "request_type": request_type,
        "course_slug": course_slug,
        "lesson": lesson,
        "requested_by": requested_by,
        "input_summary": input_summary[:500],
        "artifacts": [],
        "last_error": None,
        "payload": payload or {},
    }
    write_job(job_dir, data)
    job_event(job_dir, "created", {"state": "queued", "request_type": request_type})
    return data


def list_jobs(job_root: Path = LOCAL_JOB_ROOT) -> list[dict[str, Any]]:
    root = safe_job_root(job_root)
    if not root.exists():
        return []
    jobs = []
    for path in sorted(root.glob("job_*/job.json")):
        data = read_json(path)
        if data:
            jobs.append(data)
    return jobs


def transition_job(job_root: Path, job_id: str, to_state: str, *, note: str = "") -> dict[str, Any]:
    root = safe_job_root(job_root)
    job_id = safe_job_id(job_id)
    if to_state not in JOB_STATES:
        raise ValueError(f"Unsupported target state: {to_state}")
    job_dir = root / job_id
    data = read_json(job_dir / "job.json")
    if not data:
        raise ValueError(f"Job not found: {job_id}")
    from_state = data.get("state")
    if to_state not in JOB_TRANSITIONS.get(from_state, set()):
        raise ValueError(f"Invalid transition: {from_state} -> {to_state}")
    data["state"] = to_state
    data["updated_at"] = iso_now()
    display_note = compact_error_note(note)
    if to_state == "failed" and display_note:
        data["last_error"] = display_note
    write_job(job_dir, data)
    job_event(job_dir, "transition", {"from_state": from_state, "to_state": to_state, "note": display_note})
    return data


def compact_error_note(note: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(note or "")).strip()
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    marker = "RuntimeError:"
    marker_index = tail.find(marker)
    if marker_index >= 0:
        tail = tail[marker_index:]
    return "..." + tail


def summarize_worker_error(error: Exception) -> str:
    return compact_error_note(f"{type(error).__name__}: {error}")


def update_job(job_root: Path, job: dict[str, Any], **updates: Any) -> dict[str, Any]:
    data = dict(job)
    data.update(updates)
    data["updated_at"] = iso_now()
    write_job(job_root / data["job_id"], data)
    return data


def next_queued_job(job_root: Path) -> dict[str, Any] | None:
    for job in list_jobs(job_root):
        if job.get("state") == "queued":
            return job
    return None


def execute_worker_job(job_root: Path, job: dict[str, Any], *, backup_root: Path, dry_run: bool = False) -> dict[str, Any]:
    request_type = job.get("request_type")
    if request_type == "backup":
        result = create_backup(ROOT, backup_root=backup_root, label=job["job_id"], dry_run=dry_run)
        artifacts = [
            {"kind": "backup_archive", "path": result.get("archive"), "created": result.get("backup_created")},
            {"kind": "backup_manifest", "path": result.get("manifest"), "created": result.get("backup_created")},
        ]
        return update_job(job_root, job, artifacts=artifacts, last_error=None)
    if request_type == "course_start":
        course_slug = job.get("course_slug")
        if not course_slug:
            raise ValueError("course_start job requires course_slug")
        if dry_run:
            return update_job(job_root, job, artifacts=[], last_error=None)
        command = ["python3", "tools/greg_live_production.py", str(course_slug), "--stage", "course_map"]
        code, output = run_command(command, ROOT)
        if code != 0:
            raise RuntimeError(output or f"course_start Course Map failed with exit code {code}")
        command[-1] = "sources"
        code, output = run_command(command, ROOT)
        if code != 0:
            raise RuntimeError(output or f"course_start source research failed with exit code {code}")
        artifacts = [{"kind": "course_map", "path": f"runs/{course_slug}/course_map/course_map.md", "created": True}, {"kind": "source_ledger", "path": f"runs/{course_slug}/sources/source_ledger.json", "created": True}]
        return update_job(job_root, job, artifacts=artifacts, last_error=None)
    if request_type == "lesson_lifecycle":
        course_slug = job.get("course_slug")
        lesson = job.get("lesson") or 1
        if not course_slug:
            raise ValueError("lesson_lifecycle job requires course_slug")
        if dry_run:
            artifacts = [{"kind": "operator_report", "path": f"runs/{course_slug}/process_review/lesson_{lesson:02d}_operator_report.md", "created": False}]
            return update_job(job_root, job, artifacts=artifacts, last_error=None)
        code, output = run_command(
            [
                "python3",
                "tools/greg_run_lesson.py",
                course_slug,
                "--lesson",
                str(lesson),
                "--action",
                "lifecycle",
                "--write-report",
            ],
            ROOT,
        )
        if code != 0:
            raise RuntimeError(output or f"lesson_lifecycle failed with exit code {code}")
        artifacts = [{"kind": "operator_report", "path": f"runs/{course_slug}/process_review/lesson_{lesson:02d}_operator_report.md", "created": True}]
        return update_job(job_root, job, artifacts=artifacts, last_error=None)
    if request_type == "stage_next":
        course_slug = job.get("course_slug")
        lesson = job.get("lesson") or 1
        if not course_slug:
            raise ValueError("stage_next job requires course_slug")
        if dry_run:
            artifacts = [{"kind": "operator_report", "path": f"runs/{course_slug}/process_review/lesson_{lesson:02d}_operator_report.md", "created": False}]
            return update_job(job_root, job, artifacts=artifacts, last_error=None)
        code, output = run_command(
            [
                "python3",
                "tools/greg_run_lesson.py",
                course_slug,
                "--lesson",
                str(lesson),
                "--action",
                "next",
                "--write-report",
            ],
            ROOT,
        )
        if code != 0:
            raise RuntimeError(output or f"stage_next failed with exit code {code}")
        artifacts = [{"kind": "operator_report", "path": f"runs/{course_slug}/process_review/lesson_{lesson:02d}_operator_report.md", "created": True}]
        return update_job(job_root, job, artifacts=artifacts, last_error=None)
    if request_type == "production_stage":
        course_slug = job.get("course_slug")
        payload = job.get("payload") or {}
        stage = str(payload.get("stage") or "")
        lessons = [int(value) for value in (payload.get("lessons") or [])]
        if not course_slug or stage not in {"course_map", "sources", "study_guide", "deck", "pt_br_book", "pt_br_deck", "es_book", "es_deck"}:
            raise ValueError("production_stage job requires a course and supported stage.")
        if dry_run:
            return update_job(
                job_root,
                job,
                artifacts=[{"kind": "operator_report", "path": f"runs/{course_slug}/process_review/dry_run_{stage}.md", "created": False}],
                last_error=None,
            )
        command = ["python3", "tools/greg_live_production.py", str(course_slug), "--stage", stage]
        if lessons:
            command.extend(["--lessons", ",".join(str(value) for value in lessons)])
        code, output = run_command(command, ROOT)
        if code != 0:
            raise RuntimeError(output or f"production_stage failed with exit code {code}")
        artifacts = [{"kind": stage, "path": f"runs/{course_slug}", "created": True}]
        return update_job(job_root, job, artifacts=artifacts, last_error=None)
    raise ValueError(f"Worker does not support request_type yet: {request_type}")


def process_one_worker_job(job_root: Path, *, backup_root: Path = SERVER_BACKUP_ROOT, dry_run: bool = False) -> dict[str, Any]:
    root = safe_job_root(job_root)
    backup_root = safe_backup_root(backup_root)
    job = next_queued_job(root)
    if not job:
        return {"processed": False, "job_id": None, "state": None}
    job_id = job["job_id"]
    try:
        running = transition_job(root, job_id, "running", note="worker claimed job")
        executed = execute_worker_job(root, running, backup_root=backup_root, dry_run=dry_run)
        completed = transition_job(root, job_id, "completed", note="worker completed job")
        return {"processed": True, "job_id": job_id, "state": completed["state"], "artifacts": executed.get("artifacts", [])}
    except Exception as error:
        message = summarize_worker_error(error)
        failure_recorded = False
        try:
            current = next((item for item in list_jobs(root) if item.get("job_id") == job_id), job)
            if current.get("state") in {"queued", "running"}:
                transition_job(root, job_id, "failed", note=message)
                failure_recorded = True
        except Exception as state_error:
            state_note = summarize_worker_error(state_error)
            message = compact_error_note(f"{message}; worker could not persist failed state: {state_note}")
        return {
            "processed": True,
            "job_id": job_id,
            "state": "failed",
            "error": message,
            "failure_recorded": failure_recorded,
        }


def run_worker_loop(
    *,
    job_root: Path = SERVER_JOB_ROOT,
    backup_root: Path = SERVER_BACKUP_ROOT,
    once: bool = False,
    max_jobs: int | None = None,
    poll_interval: float = 10.0,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    processed = 0
    while True:
        result = process_one_worker_job(job_root, backup_root=backup_root, dry_run=dry_run)
        results.append(result)
        if result["processed"]:
            processed += 1
        if once or (max_jobs is not None and processed >= max_jobs):
            return results
        time.sleep(poll_interval)


def add_tree_to_archive(archive: tarfile.TarFile, source: Path, arc_prefix: str) -> list[dict[str, Any]]:
    included: list[dict[str, Any]] = []
    if not source.exists():
        return included
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        stat = path.stat()
        arcname = str(Path(arc_prefix) / path.relative_to(source))
        archive.add(path, arcname=arcname, recursive=False)
        included.append({"source": str(path), "archive_path": arcname, "size_bytes": stat.st_size})
    return included


def create_backup(
    root: Path = ROOT,
    *,
    backup_root: Path = SERVER_BACKUP_ROOT,
    label: str = "manual",
    dry_run: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    backup_root = safe_backup_root(backup_root)
    timestamp = iso_now().replace(":", "").replace("-", "")
    stem = f"profgreg-backup-{timestamp}-{label}"
    archive_path = backup_root / f"{stem}.tar.gz"
    manifest_path = backup_root / f"{stem}.manifest.json"
    commit = git_value(root, ["rev-parse", "--short", "HEAD"]) if (root / ".git").exists() else None
    branch = git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"]) if (root / ".git").exists() else None

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at": iso_now(),
        "label": label,
        "dry_run": dry_run,
        "deployed_commit": commit,
        "branch": branch,
        "archive": str(archive_path),
        "archive_sha256": None,
        "archive_size_bytes": 0,
        "included_roots": [str(SERVER_UPLOADS), str(SERVER_OUTPUTS)],
        "excluded_secret_paths": [str(SERVER_SECRETS), str(SERVER_SECRETS / "profgreg.env")],
        "log_inventory_only": str(SERVER_LOGS),
        "log_inventory": file_inventory(SERVER_LOGS, include_patterns=("*.log", "*.log.*")),
        "included_files": [],
        "restore_notes": [
            "Restore uploaded source materials from archive path uploads/ into /srv/profgreg/uploads.",
            "Restore generated outputs from archive path outputs/ into /srv/profgreg/outputs.",
            "Do not restore secrets from this backup; restore /etc/profgreg through the operator-controlled encrypted secret process.",
            "Review deployed_commit before mixing restored artifacts with a newer code checkout.",
        ],
    }

    if dry_run:
        return {
            "passed": True,
            "backup_created": False,
            "archive": str(archive_path),
            "manifest": str(manifest_path),
            "manifest_data": manifest,
        }

    backup_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        manifest["included_files"].extend(add_tree_to_archive(archive, SERVER_UPLOADS, "uploads"))
        manifest["included_files"].extend(add_tree_to_archive(archive, SERVER_OUTPUTS, "outputs"))
        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        info = tarfile.TarInfo("manifest.preview.json")
        info.size = len(manifest_bytes)
        info.mtime = int(datetime.now(timezone.utc).timestamp())
        archive.addfile(info, io.BytesIO(manifest_bytes))
    manifest["archive_sha256"] = sha256_file(archive_path)
    manifest["archive_size_bytes"] = archive_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "passed": True,
        "backup_created": True,
        "archive": str(archive_path),
        "manifest": str(manifest_path),
        "manifest_data": manifest,
    }


def contains_all(text: str, values: list[str]) -> bool:
    lower = text.lower()
    return all(value.lower() in lower for value in values)


def logrotate_policy_ok(text: str) -> bool:
    required_patterns = [
        r"/var/log/profgreg/\*\.log",
        r"\bdaily\b",
        r"\brotate\s+\d+",
        r"\bcompress\b",
        r"\bmissingok\b",
        r"\bnotifempty\b",
    ]
    return all(re.search(pattern, text) for pattern in required_patterns)


def backup_service_policy_ok(text: str) -> bool:
    required = [
        "User=profgreg",
        "WorkingDirectory=/opt/profgreg/app",
        "greg_server_status.py --mode server --create-backup",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ReadWritePaths=/srv/profgreg/backups",
    ]
    return all(item in text for item in required)


def backup_timer_policy_ok(text: str) -> bool:
    required = [
        "OnCalendar=daily",
        "Persistent=true",
        "Unit=profgreg-backup.service",
        "WantedBy=timers.target",
    ]
    return all(item in text for item in required)


def worker_service_policy_ok(text: str) -> bool:
    required = [
        "User=profgreg",
        "EnvironmentFile=/etc/profgreg/profgreg.env",
        "greg_server_status.py --worker --job-root /srv/profgreg/jobs",
        "Restart=on-failure",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ReadWritePaths=/srv/profgreg/jobs /srv/profgreg/backups",
    ]
    return all(item in text for item in required)


def ui_service_policy_ok(text: str) -> bool:
    required = [
        "User=profgreg",
        "EnvironmentFile=/etc/profgreg/profgreg.env",
        "greg_ui_server.py --host 127.0.0.1",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ReadWritePaths=/srv/profgreg/jobs /srv/profgreg/backups /srv/profgreg/uploads",
    ]
    return all(item in text for item in required)


def server_ops_findings(root: Path, *, server_mode: bool) -> tuple[list[Finding], list[dict[str, Any]]]:
    findings: list[Finding] = []
    path_infos: list[dict[str, Any]] = []
    contract_text = read_text(root / CONTRACT)
    if contract_text:
        findings.append(Finding("pass", "ops_contract_exists", "Server operations contract exists."))
    else:
        findings.append(Finding("fail", "ops_contract_exists", "Server operations contract is missing."))

    contract_terms = [
        "/srv/profgreg/uploads",
        "/srv/profgreg/outputs",
        "/srv/profgreg/backups",
        "/var/log/profgreg",
        "must not include",
        "api key values",
        "rotated",
    ]
    if contains_all(contract_text, contract_terms):
        findings.append(Finding("pass", "ops_contract_policy_terms", "Contract records backup, log, and secret-exclusion policy."))
    else:
        findings.append(Finding("fail", "ops_contract_policy_terms", "Contract is missing required backup/log/secret policy terms."))

    sample_text = read_text(root / LOGROTATE_SAMPLE)
    if logrotate_policy_ok(sample_text):
        findings.append(Finding("pass", "logrotate_sample", "Repository logrotate sample has required rotation policy."))
    else:
        findings.append(Finding("fail", "logrotate_sample", "Repository logrotate sample is missing required rotation policy."))

    service_text = read_text(root / BACKUP_SERVICE_SAMPLE)
    if backup_service_policy_ok(service_text):
        findings.append(Finding("pass", "backup_service_sample", "Repository backup service has required least-privilege policy."))
    else:
        findings.append(Finding("fail", "backup_service_sample", "Repository backup service is missing required least-privilege policy."))

    timer_text = read_text(root / BACKUP_TIMER_SAMPLE)
    if backup_timer_policy_ok(timer_text):
        findings.append(Finding("pass", "backup_timer_sample", "Repository backup timer has required schedule policy."))
    else:
        findings.append(Finding("fail", "backup_timer_sample", "Repository backup timer is missing required schedule policy."))

    worker_text = read_text(root / WORKER_SERVICE_SAMPLE)
    if worker_service_policy_ok(worker_text):
        findings.append(Finding("pass", "worker_service_sample", "Repository worker service has required least-privilege policy."))
    else:
        findings.append(Finding("fail", "worker_service_sample", "Repository worker service is missing required least-privilege policy."))

    ui_text = read_text(root / UI_SERVICE_SAMPLE)
    if ui_service_policy_ok(ui_text):
        findings.append(Finding("pass", "ui_service_sample", "Repository private UI service has required least-privilege policy."))
    else:
        findings.append(Finding("fail", "ui_service_sample", "Repository private UI service is missing required least-privilege policy."))

    if not server_mode:
        findings.append(Finding("pass", "server_logrotate", "Server logrotate check skipped outside server mode."))
        findings.append(Finding("pass", "backup_manifest", "Backup manifest check skipped outside server mode."))
        return findings, path_infos

    missing_paths = [item for item in SERVER_PATHS if not Path(item).exists()]
    for item in SERVER_PATHS:
        path_infos.append(path_status(item))
    if missing_paths:
        findings.append(Finding("fail", "ops_server_paths", f"Missing expected server paths: {missing_paths}."))
    else:
        findings.append(Finding("pass", "ops_server_paths", "Expected server operation paths exist."))

    logrotate_text = read_text(Path("/etc/logrotate.d/profgreg"))
    if logrotate_policy_ok(logrotate_text):
        findings.append(Finding("pass", "server_logrotate", "Server logrotate policy is installed."))
    else:
        findings.append(Finding("fail", "server_logrotate", "Server logrotate policy is missing or incomplete at /etc/logrotate.d/profgreg."))

    server_service_text = read_text(Path("/etc/systemd/system/profgreg-backup.service"))
    server_timer_text = read_text(Path("/etc/systemd/system/profgreg-backup.timer"))
    if backup_service_policy_ok(server_service_text):
        findings.append(Finding("pass", "server_backup_service", "Server backup service is installed."))
    else:
        findings.append(Finding("warn", "server_backup_service", "Server backup service is not installed yet."))
    if backup_timer_policy_ok(server_timer_text):
        findings.append(Finding("pass", "server_backup_timer", "Server backup timer is installed."))
    else:
        findings.append(Finding("warn", "server_backup_timer", "Server backup timer is not installed yet."))

    server_worker_text = read_text(Path("/etc/systemd/system/profgreg-worker.service"))
    if worker_service_policy_ok(server_worker_text):
        findings.append(Finding("pass", "server_worker_service", "Server worker service is installed."))
    else:
        findings.append(Finding("warn", "server_worker_service", "Server worker service is not installed yet."))

    server_ui_text = read_text(Path("/etc/systemd/system/profgreg-ui.service"))
    if ui_service_policy_ok(server_ui_text):
        findings.append(Finding("pass", "server_ui_service", "Server private UI service is installed."))
    else:
        findings.append(Finding("warn", "server_ui_service", "Server private UI service is not installed yet."))

    manifests = sorted(SERVER_BACKUP_ROOT.glob("*.manifest.json")) if SERVER_BACKUP_ROOT.exists() else []
    if manifests:
        findings.append(Finding("pass", "backup_manifest", f"Backup manifest exists: {manifests[-1].name}."))
    else:
        findings.append(Finding("warn", "backup_manifest", "No backup manifest exists yet. Run `greg_server_status.py --create-backup` before exposing a persistent interface."))

    return findings, path_infos


def run_job_checks(root: Path = ROOT, *, job_root: Path = LOCAL_JOB_ROOT) -> dict[str, Any]:
    findings: list[Finding] = []
    root = root.resolve()
    job_root = safe_job_root(job_root)
    job_root.mkdir(parents=True, exist_ok=True)
    contract = root / "workspace" / "contracts" / "server-job-contract.md"
    if contract.exists():
        findings.append(Finding("pass", "job_contract", "Server job contract exists."))
    else:
        findings.append(Finding("fail", "job_contract", "Server job contract is missing."))
    findings.append(Finding("pass", "job_root", f"Job root exists: {job_root}."))
    bad_jobs = []
    jobs = list_jobs(job_root)
    for job in jobs:
        if job.get("state") not in JOB_STATES:
            bad_jobs.append(job.get("job_id", "?"))
    if bad_jobs:
        findings.append(Finding("fail", "job_states", f"Jobs with invalid states: {bad_jobs}."))
    else:
        findings.append(Finding("pass", "job_states", "No invalid job states found."))
    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "job_count": len(jobs),
        "findings": [asdict(item) for item in findings],
    }


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

    ops_findings, ops_paths = server_ops_findings(root, server_mode=server_mode)
    findings.extend(ops_findings)

    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "mode": "server" if server_mode else "local",
        "report_type": "status",
        "root": str(root),
        "commit": commit,
        "branch": branch,
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "server_paths": ops_paths if server_mode else [],
        "findings": [asdict(item) for item in findings],
    }


def run_ops_checks(root: Path = ROOT, *, mode: str = "auto") -> dict[str, Any]:
    root = root.resolve()
    server_mode = mode == "server" or (mode == "auto" and str(root) == "/opt/profgreg/app")
    findings, paths = server_ops_findings(root, server_mode=server_mode)
    fail_count = sum(1 for item in findings if item.status == "fail")
    warn_count = sum(1 for item in findings if item.status == "warn")
    return {
        "mode": "server" if server_mode else "local",
        "report_type": "operations",
        "root": str(root),
        "commit": None,
        "branch": None,
        "passed": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "server_paths": paths,
        "findings": [asdict(item) for item in findings],
    }


def render_markdown(data: dict[str, Any]) -> str:
    title = "server operations QA" if data.get("report_type") == "operations" else "server status"
    lines = [
        f"Prof Greg {title} passed: {'yes' if data['passed'] else 'no'}",
        f"Mode: {data['mode']}",
        f"Root: {data['root']}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Findings:",
    ]
    if data.get("report_type") != "operations":
        lines.insert(3, f"Commit: {data.get('commit') or 'unknown'}")
        lines.insert(4, f"Branch: {data.get('branch') or 'unknown'}")
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


def render_backup_markdown(data: dict[str, Any]) -> str:
    manifest = data.get("manifest_data") or {}
    lines = [
        f"Prof Greg backup job passed: {'yes' if data.get('passed') else 'no'}",
        f"Backup created: {'yes' if data.get('backup_created') else 'no'}",
        f"Archive: {data.get('archive')}",
        f"Manifest: {data.get('manifest')}",
        f"Included files: {len(manifest.get('included_files') or [])}",
        f"Log inventory entries: {len(manifest.get('log_inventory') or [])}",
    ]
    if manifest.get("archive_sha256"):
        lines.append(f"Archive SHA256: {manifest['archive_sha256']}")
    lines.extend(["", "Excluded Secrets:"])
    for item in manifest.get("excluded_secret_paths") or []:
        lines.append(f"- {item}")
    lines.extend(["", "Restore Notes:"])
    for item in manifest.get("restore_notes") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def render_job_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"Prof Greg job operator QA passed: {'yes' if data['passed'] else 'no'}",
        f"Jobs: {data.get('job_count', 0)}",
        f"Failures: {data['fail_count']}",
        f"Warnings: {data['warn_count']}",
        "",
        "Findings:",
    ]
    for item in data["findings"]:
        lines.append(f"- {item['status'].upper()} {item['check']}: {item['note']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Prof Greg local/server deployment status without exposing secrets.")
    parser.add_argument("--root", default=str(ROOT), help="Checkout root. Defaults to this repository.")
    parser.add_argument("--mode", choices=["auto", "local", "server"], default="auto")
    parser.add_argument("--expected-branch", default="main")
    parser.add_argument("--ops-only", action="store_true", help="Run only backup/log operations readiness checks.")
    parser.add_argument("--create-backup", action="store_true", help="Create a backup archive and restore manifest.")
    parser.add_argument("--backup-root", default=str(SERVER_BACKUP_ROOT), help="Backup root. Must stay under /srv/profgreg/backups or local tmp/.")
    parser.add_argument("--backup-label", default="manual", help="Short backup label.")
    parser.add_argument("--dry-run", action="store_true", help="Preview backup job without writing archive/manifest.")
    parser.add_argument("--jobs-only", action="store_true", help="Run only server job-operator readiness checks.")
    parser.add_argument("--job-root", default=str(LOCAL_JOB_ROOT))
    parser.add_argument("--create-job", choices=sorted(JOB_REQUEST_TYPES))
    parser.add_argument("--course-slug")
    parser.add_argument("--lesson", type=int)
    parser.add_argument("--requested-by", default="operator")
    parser.add_argument("--summary", default="")
    parser.add_argument("--list-jobs", action="store_true")
    parser.add_argument("--transition-job")
    parser.add_argument("--to", choices=sorted(JOB_STATES))
    parser.add_argument("--note", default="")
    parser.add_argument("--worker", action="store_true", help="Run the conservative server worker.")
    parser.add_argument("--once", action="store_true", help="With --worker, process at most one queued job.")
    parser.add_argument("--max-jobs", type=int, help="With --worker, stop after this many processed jobs.")
    parser.add_argument("--poll-interval", type=float, default=10.0, help="With --worker, seconds between polls.")
    parser.add_argument("--output", help="Optional Markdown output path.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.worker:
        data = run_worker_loop(job_root=Path(args.job_root), backup_root=Path(args.backup_root), once=args.once, max_jobs=args.max_jobs, poll_interval=args.poll_interval, dry_run=args.dry_run)
        report = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    elif args.create_backup:
        data = create_backup(Path(args.root), backup_root=Path(args.backup_root), label=args.backup_label, dry_run=args.dry_run)
        report = render_backup_markdown(data)
    elif args.create_job:
        data = create_job(job_root=Path(args.job_root), request_type=args.create_job, course_slug=args.course_slug, lesson=args.lesson, requested_by=args.requested_by, input_summary=args.summary)
        report = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    elif args.list_jobs:
        data = list_jobs(Path(args.job_root))
        report = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    elif args.transition_job:
        if not args.to:
            raise SystemExit("--to is required with --transition-job")
        data = transition_job(Path(args.job_root), args.transition_job, args.to, note=args.note)
        report = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    elif args.jobs_only:
        data = run_job_checks(Path(args.root), job_root=Path(args.job_root))
        report = render_job_markdown(data)
    else:
        data = run_ops_checks(Path(args.root), mode=args.mode) if args.ops_only else run_checks(Path(args.root), mode=args.mode, expected_branch=args.expected_branch)
        report = render_markdown(data)
    if args.output:
        output = assert_safe_write_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else report, end="" if args.json else "")
    if isinstance(data, dict) and "passed" in data:
        return 0 if data["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
