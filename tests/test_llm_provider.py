"""LLM provider detection tests."""

import os
from unittest.mock import patch

import pytest

from jobwright.llm import _detect_provider, _resolve_fireworks_model


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


def test_fireworks_ignores_gemini_model_name():
    with patch.dict(
        os.environ,
        {"FIREWORKS_API_KEY": "fw-test", "LLM_MODEL": "gemini-2.5-flash", "LLM_URL": ""},
        clear=False,
    ):
        _, model, _ = _detect_provider()
    assert model == "accounts/fireworks/models/deepseek-v4-flash-0731"


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
