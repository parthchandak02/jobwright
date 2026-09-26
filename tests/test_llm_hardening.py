"""LLM client resilience: retries, Retry-After cap, key handling, usage ledger."""

from __future__ import annotations

import httpx
import pytest

from jobwright import llm


def _client(handler, base="https://api.fireworks.ai/inference/v1", model="m"):
    c = llm.LLMClient(base, model, "secret-key")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def _ok(content="hi", usage=None):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": usage or {}})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    llm.usage_snapshot(reset=True)
    return slept


def test_retries_5xx_then_succeeds(_no_sleep):
    calls = iter([httpx.Response(502), httpx.Response(500), _ok("done")])
    c = _client(lambda req: next(calls))
    assert c.chat([{"role": "user", "content": "x"}]) == "done"
    assert len(_no_sleep) == 2


def test_retry_after_is_capped(_no_sleep):
    calls = iter([httpx.Response(429, headers={"Retry-After": "3600"}), _ok()])
    c = _client(lambda req: next(calls))
    c.chat([{"role": "user", "content": "x"}])
    assert _no_sleep == [llm._MAX_RETRY_AFTER]


def test_transport_errors_are_retried(_no_sleep):
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectError("boom", request=req)
        return _ok("back")

    assert _client(handler).chat([{"role": "user", "content": "x"}]) == "back"


def test_4xx_is_not_retried(_no_sleep):
    c = _client(lambda req: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(httpx.HTTPStatusError):
        c.chat([{"role": "user", "content": "x"}])
    assert _no_sleep == []


def test_gemini_native_key_in_header_not_url():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["key"] = req.headers.get("x-goog-api-key")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    c = _client(handler, base=llm._GEMINI_COMPAT_BASE, model="gemini-3.7-flash")
    c.chat([{"role": "user", "content": "x"}], json_mode=True)
    assert "secret-key" not in seen["url"] and seen["key"] == "secret-key"


def test_gemini_json_mode_is_not_sticky():
    paths = []

    def handler(req):
        paths.append(req.url.path)
        if "generateContent" in req.url.path:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
        return _ok("plain")

    c = _client(handler, base=llm._GEMINI_COMPAT_BASE, model="gemini-3.7-flash")
    c.chat([{"role": "user", "content": "x"}], json_mode=True)
    c.chat([{"role": "user", "content": "x"}])
    assert "generateContent" in paths[0] and paths[1].endswith("/chat/completions")


def test_usage_is_recorded_per_purpose():
    c = _client(lambda req: _ok(usage={"prompt_tokens": 100, "completion_tokens": 7}))
    with llm.llm_purpose("score"):
        c.chat([{"role": "user", "content": "x"}])
        c.chat([{"role": "user", "content": "x"}])
    rows = llm.usage_snapshot(reset=True)
    assert rows == [{"purpose": "score", "provider": "fireworks", "model": "m", "prompt_tokens": 200,
                     "completion_tokens": 14, "cached_tokens": 0, "calls": 2}]


def test_structured_falls_back_when_schema_rejected():
    bodies = []

    def handler(req):
        import json

        body = json.loads(req.content)
        bodies.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "unsupported"})
        return _ok('{"score": 5}')

    c = _client(handler)
    schema = {"name": "s", "strict": True, "schema": {"type": "object"}}
    assert c.chat_structured([{"role": "user", "content": "x"}], schema) == '{"score": 5}'
    c.chat_structured([{"role": "user", "content": "x"}], schema)
    assert bodies == ["json_schema", "json_object", "json_object"]


def test_cost_only_when_price_configured(monkeypatch):
    assert llm.estimate_cost("m", 1_000_000, 0) is None
    monkeypatch.setenv("JOBWRIGHT_LLM_PRICES", '{"m": [0.5, 2.0]}')
    assert llm.estimate_cost("m", 1_000_000, 500_000) == 1.5
