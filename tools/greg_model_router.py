#!/usr/bin/env python3
"""Configured model access for Prof Greg production roles.

The router is deliberately small: provider and model selection stay in the
workspace configuration, secrets stay in the environment, and every request is
logged without prompts or secret values.
"""
from __future__ import annotations

import json
import os
import base64
import http.client
import socket
import time
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


def cost_estimate(binding: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """Estimate a request cost from the versioned local rate card.

    Provider responses expose usage, not a billing total. Keeping rates in the
    routing configuration makes the UI auditable and lets operations update a
    price without changing production code. An absent rate is deliberately
    reported as unpriced instead of being treated as a free request.
    """
    provider = str(binding.get("provider") or "")
    model = str(binding.get("model") or "")
    rates = ((load_config().get("cost_tracking") or {}).get("rates") or {}).get(f"{provider}/{model}")
    if not isinstance(rates, dict):
        return {"currency": "USD", "status": "unpriced"}

    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    input_details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    cached_tokens = int(input_details.get("cached_tokens") or 0) if isinstance(input_details, dict) else 0
    anthropic_cache_read = int(usage.get("cache_read_input_tokens") or 0)
    if anthropic_cache_read:
        cached_tokens = anthropic_cache_read
    input_rate = rates.get("input_per_million_usd")
    output_rate = rates.get("output_per_million_usd")
    cached_rate = rates.get("cached_input_per_million_usd", input_rate)
    images = int(usage.get("images") or 0)
    if images and not input_tokens and not output_tokens:
        per_image = rates.get("per_image_usd")
        if isinstance(per_image, (int, float)):
            image_usd = round(images * float(per_image), 8)
            return {"currency": "USD", "status": "estimated", "estimated_usd": image_usd, "components": {"images_usd": image_usd}, "rate_version": str(rates.get("rate_version") or "")}
        return {"currency": "USD", "status": "unpriced"}
    if not all(isinstance(value, (int, float)) for value in (input_rate, output_rate, cached_rate)):
        per_image = rates.get("per_image_usd")
        if images and isinstance(per_image, (int, float)):
            image_usd = round(images * float(per_image), 8)
            return {"currency": "USD", "status": "estimated", "estimated_usd": image_usd, "components": {"images_usd": image_usd}, "rate_version": str(rates.get("rate_version") or "")}
        return {"currency": "USD", "status": "unpriced"}
    # Anthropic reports cache reads separately from input_tokens, while the
    # OpenAI-compatible usage shape includes cached input in input_tokens.
    uncached_tokens = input_tokens if anthropic_cache_read else max(0, input_tokens - cached_tokens)
    input_usd = uncached_tokens * float(input_rate) / 1_000_000
    cached_input_usd = cached_tokens * float(cached_rate) / 1_000_000
    output_usd = output_tokens * float(output_rate) / 1_000_000
    estimated = input_usd + cached_input_usd + output_usd
    result = {
        "currency": "USD",
        "status": "estimated",
        "estimated_usd": round(estimated, 8),
        "components": {
            "input_usd": round(input_usd, 8),
            "cached_input_usd": round(cached_input_usd, 8),
            "output_usd": round(output_usd, 8),
        },
        "rate_version": str(rates.get("rate_version") or ""),
    }
    web_runs = int(usage.get("web_search_runs") or 0)
    web_rate = rates.get("web_search_per_1000_usd")
    if web_runs and isinstance(web_rate, (int, float)):
        web_search_usd = web_runs * float(web_rate) / 1000
        result["components"]["web_search_usd"] = round(web_search_usd, 8)
        result["estimated_usd"] = round(result["estimated_usd"] + web_search_usd, 8)
    return result


def append_usage(
    course_slug: str,
    *,
    role: str,
    binding: dict[str, Any],
    outcome: str,
    detail: str = "",
    usage: dict[str, Any] | None = None,
) -> None:
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
    if usage:
        # Keep the operational log small and private: usage metadata is enough
        # for cost reporting and never includes a prompt or generated content.
        row["usage"] = usage
        row["cost"] = cost_estimate(binding, usage) if outcome == "completed" else {"currency": "USD", "status": "not_chargeable"}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 120,
    attempts: int = 3,
) -> dict[str, Any]:
    encoded_payload = json.dumps(payload).encode("utf-8")
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            data=encoded_payload,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retryable or attempt == attempts:
                raise ModelRequestError(f"Model provider returned HTTP {error.code}: {body[:500]}") from error
        except (urllib.error.URLError, http.client.RemoteDisconnected, socket.timeout, TimeoutError) as error:
            if attempt == attempts:
                reason = getattr(error, "reason", error)
                raise ModelRequestError(f"Model provider could not be reached: {reason}") from error
        time.sleep(2 ** (attempt - 1))
    raise ModelRequestError("Model provider request failed after retries.")


def request_image(course_slug: str, prompt: str, output_path: Path, *, size: str = "1536x1024") -> Path:
    """Generate one image through the centrally configured image role."""
    load_env_file(ROOT / ".env.local")
    role = "image_generation"
    binding, provider = binding_for(role)
    provider_name = str(binding.get("provider"))
    if provider_name != "openai":
        raise ModelRequestError(f"Image provider `{provider_name}` is not implemented yet.")
    api_key_name = str(provider.get("api_key_env") or "")
    api_key = os.environ.get(api_key_name, "")
    if not api_key:
        append_usage(course_slug, role=role, binding=binding, outcome="blocked", detail=f"Missing {api_key_name}.")
        raise ModelRequestError(f"The configured image provider is unavailable because {api_key_name} is not set.")
    base_url_name = str(provider.get("base_url_env") or "")
    base_url = os.environ.get(base_url_name) or "https://api.openai.com"
    payload = {
        "model": str(binding.get("model")),
        "prompt": prompt,
        "size": size,
        "quality": str(binding.get("quality") or "medium"),
        "output_format": "png",
    }
    try:
        response = post_json(
            f"{base_url.rstrip('/')}/v1/images/generations",
            payload,
            {"Authorization": f"Bearer {api_key}"},
            timeout=240,
        )
        item = (response.get("data") or [{}])[0]
        encoded = str(item.get("b64_json") or "")
        if not encoded:
            raise ModelRequestError("OpenAI returned no image bytes.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(encoded, validate=True))
    except (ModelRequestError, ValueError) as error:
        append_usage(course_slug, role=role, binding=binding, outcome="failed", detail=str(error))
        raise ModelRequestError(str(error)) from error
    usage = {**dict(response.get("usage") or {}), "images": 1, "size": size, "quality": payload["quality"]}
    append_usage(
        course_slug,
        role=role,
        binding=binding,
        outcome="completed",
        usage=usage,
    )
    return output_path


def anthropic_text(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    *,
    timeout: int = 600,
    return_usage: bool = False,
) -> str | tuple[str, dict[str, Any]]:
    response = post_json(
        f"{base_url.rstrip('/')}/v1/messages",
        {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout=timeout,
        attempts=2,
    )
    text = "".join(
        str(block.get("text") or "") for block in response.get("content") or [] if block.get("type") == "text"
    ).strip()
    if not text:
        raise ModelRequestError("Anthropic returned no text content.")
    usage = dict(response.get("usage") or {})
    return (text, usage) if return_usage else text


def openai_text(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    web_search: bool,
    *,
    timeout: int = 600,
    return_usage: bool = False,
    reasoning: str = "",
) -> str | tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "max_output_tokens": max_tokens,
    }
    if reasoning:
        payload["reasoning"] = {"effort": reasoning}
    if web_search:
        payload["tools"] = [{"type": "web_search_preview"}]
    response = post_json(
        f"{base_url.rstrip('/')}/v1/responses",
        payload,
        {"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
        attempts=2,
    )
    text = str(response.get("output_text") or "").strip()
    if not text:
        for output in response.get("output") or []:
            for block in output.get("content") or []:
                if block.get("type") in {"output_text", "text"}:
                    text += str(block.get("text") or "")
    if not text.strip():
        # Do not retain model content in logs, but make an empty response
        # diagnosable to the operator. This distinguishes an incomplete
        # response from a provider-side refusal or an unexpected shape.
        output_shapes = [
            {
                "type": item.get("type"),
                "status": item.get("status"),
                "content_types": [block.get("type") for block in item.get("content") or []],
            }
            for item in response.get("output") or []
        ]
        reason = response.get("incomplete_details") or response.get("error") or "no completion detail"
        raise ModelRequestError(
            f"OpenAI returned no text content (status={response.get('status')!r}, "
            f"reason={reason!r}, output={output_shapes!r})."
        )
    usage = dict(response.get("usage") or {})
    web_search_runs = sum(1 for item in response.get("output") or [] if item.get("type") == "web_search_call")
    if web_search_runs:
        usage["web_search_runs"] = web_search_runs
    return (text.strip(), usage) if return_usage else text.strip()


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
            text, usage = anthropic_text(
                base_url,
                api_key,
                str(binding.get("model")),
                prompt,
                max_tokens,
                return_usage=True,
            )
        elif provider_name == "openai":
            reasoning = str(binding.get("reasoning") or "")
            try:
                text, usage = openai_text(
                    base_url,
                    api_key,
                    str(binding.get("model")),
                    prompt,
                    max_tokens,
                    web_search,
                    return_usage=True,
                    reasoning=reasoning,
                )
            except ModelRequestError as error:
                # High reasoning can occasionally consume the response without
                # emitting an answer, including after successful web-search
                # calls. Recover with the same approved model at one lower
                # effort instead of repeating the empty configuration.
                if reasoning not in {"max", "high"} or "no text content" not in str(error):
                    raise
                fallback_reasoning = "high" if reasoning == "max" else "medium"
                text, usage = openai_text(
                    base_url,
                    api_key,
                    str(binding.get("model")),
                    prompt,
                    max_tokens,
                    web_search,
                    return_usage=True,
                    reasoning=fallback_reasoning,
                )
                usage = {**usage, "reasoning_fallback": f"{fallback_reasoning}_after_empty_{reasoning}"}
        else:
            raise ModelRequestError(f"Provider `{provider_name}` is not implemented by the production router yet.")
    except ModelRequestError as error:
        append_usage(course_slug, role=role, binding=binding, outcome="failed", detail=str(error))
        raise
    append_usage(course_slug, role=role, binding=binding, outcome="completed", usage=usage)
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
