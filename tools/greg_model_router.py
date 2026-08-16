#!/usr/bin/env python3
"""Configured model access for Prof Greg production roles.

The router is deliberately small: provider and model selection stay in the
workspace configuration, secrets stay in the environment, and every request is
logged without prompts or secret values.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from greg_env_check import load_env_file


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "workspace" / "config" / "model-routing.json"


class ModelRequestError(RuntimeError):
    pass


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def binding_for(role: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_config()
    binding = (config.get("bindings") or {}).get(role, {}).get("primary")
    if not binding:
        raise ModelRequestError(f"No primary model binding is configured for role `{role}`.")
    provider_name = str(binding.get("provider") or "")
    provider = (config.get("providers") or {}).get(provider_name)
    if not provider:
        raise ModelRequestError(f"Provider `{provider_name}` for role `{role}` is not configured.")
    return binding, provider


def append_usage(course_slug: str, *, role: str, binding: dict[str, Any], outcome: str, detail: str = "") -> None:
    path = ROOT / "runs" / course_slug / "ops" / "model_usage_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": role,
        "provider": binding.get("provider"),
        "model": binding.get("model"),
        "outcome": outcome,
        "detail": detail[:300],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 120) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise ModelRequestError(f"Model provider returned HTTP {error.code}: {body[:500]}") from error
    except urllib.error.URLError as error:
        raise ModelRequestError(f"Model provider could not be reached: {error.reason}") from error


def anthropic_text(base_url: str, api_key: str, model: str, prompt: str, max_tokens: int) -> str:
    response = post_json(
        f"{base_url.rstrip('/')}/v1/messages",
        {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
    )
    text = "".join(
        str(block.get("text") or "") for block in response.get("content") or [] if block.get("type") == "text"
    ).strip()
    if not text:
        raise ModelRequestError("Anthropic returned no text content.")
    return text


def openai_text(base_url: str, api_key: str, model: str, prompt: str, max_tokens: int, web_search: bool) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_tokens,
    }
    if web_search:
        payload["tools"] = [{"type": "web_search_preview"}]
    response = post_json(
        f"{base_url.rstrip('/')}/v1/responses",
        payload,
        {"Authorization": f"Bearer {api_key}"},
    )
    text = str(response.get("output_text") or "").strip()
    if not text:
        for output in response.get("output") or []:
            for block in output.get("content") or []:
                if block.get("type") in {"output_text", "text"}:
                    text += str(block.get("text") or "")
    if not text.strip():
        raise ModelRequestError("OpenAI returned no text content.")
    return text.strip()


def request_text(course_slug: str, role: str, prompt: str, *, max_tokens: int = 8000, web_search: bool = False) -> str:
    # Local development uses the same protected environment file as the server
    # service. Existing environment values always take precedence.
    load_env_file(ROOT / ".env.local")
    binding, provider = binding_for(role)
    provider_name = str(binding.get("provider"))
    api_key_name = str(provider.get("api_key_env") or "")
    api_key = os.environ.get(api_key_name, "")
    if not api_key:
        append_usage(course_slug, role=role, binding=binding, outcome="blocked", detail=f"Missing {api_key_name}.")
        raise ModelRequestError(f"The configured `{role}` provider is unavailable because {api_key_name} is not set.")
    base_url_name = str(provider.get("base_url_env") or "")
    defaults = {"anthropic": "https://api.anthropic.com", "openai": "https://api.openai.com"}
    base_url = os.environ.get(base_url_name) or defaults.get(provider_name)
    if not base_url:
        raise ModelRequestError(f"Provider `{provider_name}` needs {base_url_name} configured.")
    try:
        if provider_name == "anthropic":
            text = anthropic_text(base_url, api_key, str(binding.get("model")), prompt, max_tokens)
        elif provider_name == "openai":
            text = openai_text(base_url, api_key, str(binding.get("model")), prompt, max_tokens, web_search)
        else:
            raise ModelRequestError(f"Provider `{provider_name}` is not implemented by the production router yet.")
    except ModelRequestError as error:
        append_usage(course_slug, role=role, binding=binding, outcome="failed", detail=str(error))
        raise
    append_usage(course_slug, role=role, binding=binding, outcome="completed")
    return text


def json_from_text(text: str) -> dict[str, Any]:
    fenced = text.strip()
    if fenced.startswith("```"):
        fenced = fenced.split("\n", 1)[1] if "\n" in fenced else ""
        fenced = fenced.rsplit("```", 1)[0]
    start = fenced.find("{")
    end = fenced.rfind("}")
    if start < 0 or end < start:
        raise ModelRequestError("The model did not return the required JSON object.")
    try:
        return json.loads(fenced[start : end + 1])
    except json.JSONDecodeError as error:
        raise ModelRequestError(f"The model returned invalid JSON: {error}") from error
