"""Scoring under provider rate limits: structured retries, adaptive concurrency, ledger, report."""

from __future__ import annotations

import json
import threading

import httpx
import pytest

from jobwright import llm
from jobwright.scoring import matcher
from jobwright.scoring.criteria import parse_criteria

SCHEMA = {"name": "s", "strict": True, "schema": {"type": "object"}}
REPLY = {"dealbreakers": [], "concerns": [], "location_ok": True, "seniority": "match",
         "fit": 7, "confidence": 0.9, "reasoning": "fits"}


def _ok(usage=None):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(REPLY)}}],
                                     "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2}})


def _client(handler):
    c = llm.LLMClient("https://api.fireworks.ai/inference/v1", "m", "fake-key")
    c._client = httpx.Client(transport=httpx.MockTransport(handler))
    return c


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    llm.usage_snapshot(reset=True, user_id=None)
    yield slept
    llm.usage_snapshot(reset=True, user_id=None)


def _ctx():
    return matcher.MatchContext(resume_text="resume", criteria=parse_criteria({"summary": "PM roles"}), index=None)


def _jobs(n):
    return [{"url": f"https://example.com/jobs/{i}", "title": "Program Manager", "location": "Remote"}
            for i in range(n)]


def test_structured_retries_429_burst_then_succeeds(_no_sleep):
    calls = iter([httpx.Response(429)] * 4 + [_ok()])
    seen = []
    c = _client(lambda req: next(calls))
    out = c.chat_structured([{"role": "user", "content": "x"}], SCHEMA, on_retry=lambda s, w: seen.append(s))
    assert json.loads(out)["fit"] == 7
    assert seen == [429] * 4 and len(_no_sleep) == 4
    assert all(0 < w <= llm._MAX_RETRY_AFTER for w in _no_sleep)


def test_structured_honors_retry_after_and_caps_it(_no_sleep):
    calls = iter([httpx.Response(429, headers={"Retry-After": "7"}),
                  httpx.Response(429, headers={"Retry-After": "3600"}), _ok()])
    _client(lambda req: next(calls)).chat_structured([{"role": "user", "content": "x"}], SCHEMA)
    assert 7 <= _no_sleep[0] <= 8 and _no_sleep[1] == llm._MAX_RETRY_AFTER


def test_structured_gives_up_after_attempts(monkeypatch, _no_sleep):
    monkeypatch.setenv("JOBWRIGHT_LLM_STRUCTURED_ATTEMPTS", "3")
    n = {"calls": 0}

    def handler(req):
        n["calls"] += 1
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).chat_structured([{"role": "user", "content": "x"}], SCHEMA)
    assert n["calls"] == 3 and len(_no_sleep) == 2


def test_structured_billing_errors_are_not_retried(_no_sleep):
    with pytest.raises(httpx.HTTPStatusError):
        _client(lambda req: httpx.Response(402)).chat_structured([{"role": "user", "content": "x"}], SCHEMA)
    assert _no_sleep == []


def test_rate_limited_attempts_are_not_billed_in_ledger():
    calls = iter([httpx.Response(429), httpx.Response(429), _ok({"prompt_tokens": 100, "completion_tokens": 5})])
    with llm.llm_purpose("score:t1"):
        _client(lambda req: next(calls)).chat_structured([{"role": "user", "content": "x"}], SCHEMA)
    rows = llm.usage_snapshot(reset=True)
    assert len(rows) == 1 and rows[0]["calls"] == 1 and rows[0]["prompt_tokens"] == 100


def test_backoff_wait_is_jittered_exponential_and_capped():
    import random

    rng = random.Random(0)
    for attempt in range(8):
        w = llm.backoff_wait(None, attempt, base=2.0, rng=rng)
        expo = 2.0 * 2 ** attempt
        assert min(expo / 2, 60) <= w <= min(expo, 60)


def test_limiter_halves_once_per_burst_and_recovers():
    now = {"t": 0.0}
    lim = matcher.AdaptiveLimiter(16, recover_after=2, clock=lambda: now["t"])
    lim.throttled()
    lim.throttled()  # same burst
    assert lim.limit == 8 and lim.cuts == 1
    now["t"] = 5.0
    lim.throttled()
    assert lim.limit == 4 and lim.min_limit == 4
    for _ in range(4):
        lim.succeeded()
    assert lim.limit == 6
    for _ in range(100):
        lim.succeeded()
    assert lim.limit == 16


def test_score_jobs_survives_429_burst_and_shrinks_concurrency(monkeypatch):
    """16 workers against a provider that 429s above 4 concurrent requests: nothing is dropped."""
    monkeypatch.setattr(matcher, "LIMITER_WINDOW", 0.0)
    lock = threading.Lock()
    state = {"inflight": 0, "limited": 0}
    pause = threading.Event()

    def handler(req):
        with lock:
            state["inflight"] += 1
            over = state["inflight"] > 4
            if over:
                state["limited"] += 1
        try:
            if over:
                return httpx.Response(429, headers={"Retry-After": "1"})
            pause.wait(0.002)  # real (unpatched) delay so requests overlap
            return _ok()
        finally:
            with lock:
                state["inflight"] -= 1

    client = _client(handler)
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    stats: dict = {}
    results, errors = matcher.score_jobs(_ctx(), _jobs(60), workers=16, escalate=False, stats=stats,
                                         borderline=matcher.Borderline())
    assert errors == 0 and len(results) == 60
    assert stats["rate_limited"] == state["limited"] > 0 and stats["retries"] == stats["rate_limited"]
    assert stats["workers"] == 16 and stats["workers_min"] <= 4
    usage = llm.usage_snapshot(reset=True)
    assert sum(r["calls"] for r in usage) == 60  # 429s are not billed calls in the ledger


def test_score_jobs_workers_from_env(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_SCORE_WORKERS", "3")
    client = _client(lambda req: _ok())
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    stats: dict = {}
    matcher.score_jobs(_ctx(), _jobs(2), escalate=False, stats=stats, borderline=matcher.Borderline())
    assert stats["workers"] == 3
    monkeypatch.setenv("JOBWRIGHT_SCORE_WORKERS", "nope")
    assert matcher.score_workers() == 16


def test_exhausted_rate_limit_is_not_retried_again_by_judge(monkeypatch):
    monkeypatch.setattr(matcher.time, "sleep", lambda s: None)
    req = httpx.Request("POST", "https://example.com")
    err = httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req))

    class Limited:
        model = "m"
        calls = 0

        def chat_structured(self, messages, schema, **kw):
            self.calls += 1
            raise err

    c = Limited()
    assert matcher.judge_job(_ctx(), _jobs(1)[0], c, tier="t1") is None
    assert c.calls == 1


def test_billing_dead_still_stops_with_limiter(monkeypatch):
    client = _client(lambda req: httpx.Response(401))
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    with pytest.raises(matcher.BillingDead):
        matcher.score_jobs(_ctx(), _jobs(6), workers=4, escalate=False, borderline=matcher.Borderline())


def test_brief_report_shows_rate_limit_retries(tmp_path):
    from datetime import datetime, timedelta, timezone

    import jobwright.config as cfg
    from jobwright import ops
    from jobwright.database import close_connection, init_db

    cfg.set_app_dir(tmp_path)
    close_connection(tmp_path / "jobwright.db")
    init_db(tmp_path / "jobwright.db")
    (tmp_path / "logs").mkdir(exist_ok=True)
    try:
        now = datetime.now(timezone.utc)
        score = {"stage": "score", "status": "ok", "detail": {"scored": 900, "errors": 0, "rate_limited": 116}}
        (tmp_path / "logs" / "last_run.json").write_text(json.dumps(
            {"started_at": (now + timedelta(seconds=1)).isoformat(), "errors": {}, "stages": [score]}))
        status = tmp_path / "BRIEF_STATUS_x"
        status.write_text(f"brief_started at={now:%Y-%m-%dT%H:%M:%SZ} pid=1 timeout=10800s\npipeline_rc=0\n")
        rep = ops.build_brief_report(status)
        assert any("scored 900 jobs (0 failed, 116 rate-limit retries)" in line for line in rep.lines)
    finally:
        close_connection(tmp_path / "jobwright.db")
