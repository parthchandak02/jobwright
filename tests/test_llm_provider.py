"""LLM provider detection tests."""

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from jobwright.llm import (
    LLMClient,
    _detect_provider,
    _gemini_thinking_level,
    _resolve_fireworks_model,
    _GEMINI_COMPAT_BASE,
)


def test_fireworks_takes_priority_over_gemini():
    with patch.dict(
        os.environ,
        {
            "FIREWORKS_API_KEY": "fw-test",
            "GEMINI_API_KEY": "gem-test",
            "LLM_MODEL": "",
            "LLM_URL": "",
        },
        clear=False,
    ):
        base_url, model, api_key = _detect_provider()
    assert base_url == "https://api.fireworks.ai/inference/v1"
    assert model == "accounts/fireworks/models/deepseek-v4-flash-0731"
    assert api_key == "fw-test"


def test_fireworks_ignores_gemini_model_name_without_gemini_key():
    with patch.dict(
        os.environ,
        {
            "FIREWORKS_API_KEY": "fw-test",
            "GEMINI_API_KEY": "",
            "LLM_MODEL": "gemini-2.5-flash",
            "LLM_URL": "",
        },
        clear=False,
    ):
        _, model, _ = _detect_provider()
    assert model == "accounts/fireworks/models/deepseek-v4-flash-0731"


def test_explicit_gemini_model_uses_gemini_when_both_keys():
    with patch.dict(
        os.environ,
        {
            "FIREWORKS_API_KEY": "fw-test",
            "GEMINI_API_KEY": "gem-test",
            "LLM_MODEL": "gemini-2.5-flash",
            "LLM_URL": "",
        },
        clear=False,
    ):
        base_url, model, api_key = _detect_provider()
    assert "generativelanguage.googleapis.com" in base_url
    assert model == "gemini-2.5-flash"
    assert api_key == "gem-test"


def test_resolve_fireworks_short_name():
    assert _resolve_fireworks_model("deepseek-v4-pro-0813") == (
        "accounts/fireworks/models/deepseek-v4-pro-0813"
    )


def test_no_provider_raises():
    with patch.dict(
        os.environ,
        {
            "FIREWORKS_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OPENAI_API_KEY": "",
            "LLM_URL": "",
        },
        clear=False,
    ):
        with pytest.raises(RuntimeError, match="No LLM provider"):
            _detect_provider()


def test_gemini_thinking_level_defaults_to_low():
    with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": ""}, clear=False):
        assert _gemini_thinking_level() == "low"


def test_gemini_thinking_level_invalid_falls_back():
    with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": "ultra"}, clear=False):
        assert _gemini_thinking_level() == "low"


def test_gemini_compat_payload_includes_reasoning_effort_low():
    """Fallback / Gemini 3.x compat path must send reasoning_effort=low by default."""
    captured: dict = {}

    def fake_post(url, json=None, headers=None, **_kwargs):
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
            "usage": {},
        }
        return resp

    client = LLMClient(_GEMINI_COMPAT_BASE, "gemini-3.7-flash", "gem-test")
    client._client.post = fake_post  # type: ignore[method-assign]
    with patch.dict(os.environ, {"GEMINI_THINKING_LEVEL": "low"}, clear=False):
        text = client.chat([{"role": "user", "content": "hi"}], temperature=0.0, json_mode=False)
    assert text == '{"ok": true}'
    assert captured["json"]["reasoning_effort"] == "low"
    # Gemini 3.x: do not force temperature=0.0 into the payload
    assert "temperature" not in captured["json"]


def test_fallback_builds_gemini_37_with_thinking_low():
    """Fireworks empty -> Gemini fallback uses GEMINI_FALLBACK_MODEL + thinking low."""
    primary = LLMClient(
        "https://api.fireworks.ai/inference/v1",
        "accounts/fireworks/models/gpt-oss-120b",
        "fw",
    )
    captured: dict = {}

    def fake_post(url, json=None, headers=None, **_kwargs):
        captured["json"] = json
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "fallback-ok"}, "finish_reason": "stop"}],
            "usage": {},
        }
        return resp

    with patch.dict(
        os.environ,
        {
            "GEMINI_API_KEY": "gem-test",
            "GEMINI_FALLBACK_MODEL": "gemini-3.7-flash",
            "GEMINI_THINKING_LEVEL": "low",
        },
        clear=False,
    ):
        # Pre-install fallback client so we can stub its HTTP before chat runs.
        fb = LLMClient(_GEMINI_COMPAT_BASE, "gemini-3.7-flash", "gem-test")
        fb._is_fallback = True
        fb._client.post = fake_post  # type: ignore[method-assign]
        primary._fallback = fb
        out = primary._try_fallback(
            [{"role": "user", "content": "hi"}], temperature=0.0, max_tokens=64
        )
    assert out == "fallback-ok"
    assert primary._fallback.model == "gemini-3.7-flash"
    assert captured["json"]["reasoning_effort"] == "low"
    primary.close()
