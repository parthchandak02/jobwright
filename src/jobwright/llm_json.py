"""Structured JSON parsing for LLM responses.

When callers use json_mode=True, the provider sets response_format / responseMimeType
and the model output must be valid JSON. Parse with json.loads only — no regex.

On failure, raise LLMJsonError so callers retry the LLM call instead of silently
returning empty results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


class LLMJsonError(ValueError):
    """LLM output was not valid JSON matching the expected shape."""


def parse_json_object(text: str, *, json_mode: bool = True) -> dict[str, Any]:
    """Parse a JSON object from an LLM response."""
    stripped = (text or "").strip()
    if not stripped:
        raise LLMJsonError("Empty LLM response")

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        if json_mode:
            raise LLMJsonError(f"json_mode response was not valid JSON: {exc}") from exc
        data = _legacy_parse_object(stripped)

    if not isinstance(data, dict):
        raise LLMJsonError(f"Expected JSON object, got {type(data).__name__}")
    return data


def get_list_field(data: dict[str, Any], *field_names: str) -> list[Any]:
    """Return the first list-valued field from a JSON object."""
    for name in field_names:
        value = data.get(name)
        if isinstance(value, list):
            return value
    raise LLMJsonError(
        f"Expected list under one of {field_names!r}, got keys={list(data.keys())!r}"
    )


def chat_json_object(
    client: Any,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    max_parse_retries: int = 1,
    **chat_kwargs: Any,
) -> dict[str, Any]:
    """Call LLM with json_mode=True and parse the response as a JSON object."""
    last_error: LLMJsonError | None = None
    attempt_messages = messages

    for attempt in range(max_parse_retries + 1):
        raw = client.chat(
            attempt_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
            **chat_kwargs,
        )
        try:
            return parse_json_object(raw, json_mode=True)
        except LLMJsonError as exc:
            last_error = exc
            log.warning("JSON parse failed (attempt %d/%d): %s", attempt + 1, max_parse_retries + 1, exc)
            if attempt < max_parse_retries:
                attempt_messages = messages + [{
                    "role": "user",
                    "content": (
                        "Your previous reply was not valid JSON. "
                        "Return ONLY a valid JSON object matching the requested schema."
                    ),
                }]

    assert last_error is not None
    raise last_error


def _legacy_parse_object(text: str) -> dict[str, Any]:
    """Non-regex fallback for legacy text-mode callers (migration only)."""
    if "```" in text:
        for part in text.split("```")[1::2]:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                data = json.loads(part)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data

    raise LLMJsonError("No valid JSON object found in LLM response")
