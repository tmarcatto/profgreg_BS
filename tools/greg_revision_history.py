#!/usr/bin/env python3
"""Durable, append-only communication history for operator revisions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def append_interaction(
    path: Path,
    interaction_type: str,
    *,
    message: str = "",
    problems: list[str] | None = None,
    requests: list[dict[str, Any]] | None = None,
    resolutions: list[dict[str, Any]] | None = None,
    at: str = "",
) -> dict[str, Any]:
    """Append one timestamped worker/operator exchange without flattening history."""
    state = read_state(path)
    row: dict[str, Any] = {"type": interaction_type, "at": at or utc_now()}
    if message.strip():
        row["message"] = message.strip()
    if problems:
        row["problems"] = [str(item).strip() for item in problems if str(item).strip()]
    if requests:
        row["requests"] = [
            {"id": str(item.get("id") or ""), "note": str(item.get("note") or "").strip()}
            for item in requests
            if str(item.get("note") or "").strip()
        ]
    if resolutions:
        row["resolutions"] = [
            {
                "request_id": str(item.get("request_id") or ""),
                "slide_number": int(item.get("slide_number") or 0),
                "problem": str(item.get("problem") or "").strip(),
                "change": str(item.get("change") or "").strip(),
            }
            for item in resolutions
        ]
    interactions = list(state.get("interactions") or [])
    if not interactions and state.get("requests"):
        accepted_at = str(state.get("accepted_at") or utc_now())
        migrated_requests = []
        for item in state.get("requests") or []:
            if not isinstance(item, dict):
                continue
            item.setdefault("requested_at", accepted_at)
            migrated_requests.append({
                "id": str(item.get("id") or ""),
                "note": str(item.get("note") or "").strip(),
            })
        interactions.append({"type": "request", "at": accepted_at, "requests": migrated_requests})
    interactions.append(row)
    state["interactions"] = interactions
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return state
