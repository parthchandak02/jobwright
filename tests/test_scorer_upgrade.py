"""Tests for the D2 concurrent single-shot scoring path (no live LLM)."""

from jobwright.llm_json import LLMJsonError
from jobwright.scoring import scorer


class _FakeClient:
    def __init__(self, reply: str = '{"score": 8, "reasoning": "strong fit"}'):
        self.reply = reply
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        for m in messages:
            if m["role"] == "system":
                self.system_prompts.append(m["content"])
            elif m["role"] == "user":
                self.user_prompts.append(m["content"])
        return self.reply


def test_single_prompt_byte_identical_prefix_and_full_desc(monkeypatch):
    """Profile/system prefix is byte-identical across calls; full 6000 desc used."""
    profile = {
        "experience": {"target_role": "Social impact program manager"},
        "job_preferences": {
            "ideal_roles": ["Program officer"],
            "avoid_roles": ["Fundraising"],
        },
    }
    jobs = [
        {
            "url": f"https://example.com/{i}",
            "title": f"Role {i}",
            "company": "Acme",
            "location": "SF",
            "full_description": "X" * 6000,
        }
        for i in range(5)
    ]
    fake = _FakeClient()
    monkeypatch.setattr(scorer, "get_client", lambda: fake)

    results, errors = scorer.score_jobs_single_shot(
        "resume text", jobs, profile=profile, workers=4,
    )
    assert errors == 0
    assert len(results) == 5

    # Every call saw the exact same system string object (prompt-cache friendly).
    first = fake.system_prompts[0]
    assert all(p == first for p in fake.system_prompts)
    expected = scorer._build_score_prompt(profile, "") + scorer.SINGLE_SCORE_TAIL
    assert first == expected

    # Full description is NOT truncated to 800 chars.
    assert all(("X" * 6000) in u for u in fake.user_prompts)
    assert all(("X" * 800) in u and ("X" * 801) in u for u in fake.user_prompts)


def test_single_prompt_default_workers_uses_threadpool(monkeypatch):
    """Worker count defaults from JOBWRIGHT_SCORE_WORKERS (default 20)."""
    monkeypatch.delenv("JOBWRIGHT_SCORE_WORKERS", raising=False)  # hermetic test: clear leaked override
    assert scorer._score_workers() == 20
    monkeypatch.setenv("JOBWRIGHT_SCORE_WORKERS", "0")
    assert scorer._score_workers() == 0
    monkeypatch.setenv("JOBWRIGHT_SCORE_WORKERS", "banana")
    assert scorer._score_workers() == 20


def test_parse_structured_fallback_from_fenced_json(monkeypatch):
    """Prompt+parse fallback: a fenced JSON block still parses through score_job_single."""
    fake = _FakeClient(reply='```json\n{"score": 7, "reasoning": "decent fit"}\n```')
    monkeypatch.setattr(scorer, "get_client", lambda: fake)
    result = scorer.score_job_single(
        "resume text",
        {"title": "Program Manager", "company": "Fdn", "location": "SF",
         "full_description": "manage programs"},
        system_prompt="SYS",
    )
    assert result is not None
    assert result["score"] == 7
    assert result["reasoning"] == "decent fit"


def test_parse_score_clamps(monkeypatch):
    fake = _FakeClient(reply='{"score": 42, "reasoning": "over eager"}')
    monkeypatch.setattr(scorer, "get_client", lambda: fake)
    result = scorer.score_job_single("r", {"title": "T", "full_description": "d"}, system_prompt="S")
    assert result["score"] == 10


def test_single_retries_then_skips_with_warning(monkeypatch):
    """Parse errors retry (2 attempts, no sleep) then return None — never crash."""
    class _BoomClient:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            raise LLMJsonError("not json")

    fake = _BoomClient()
    monkeypatch.setattr(scorer, "get_client", lambda: fake)
    monkeypatch.setattr(scorer, "_backoff_jitter", lambda attempt, rng: 0.0)

    result = scorer.score_job_single(
        "r", {"title": "T", "full_description": "d"}, system_prompt="S",
    )
    assert result is None
    assert fake.calls == scorer.SCORE_SINGLE_ATTEMPTS


def test_single_non_retryable_skips_immediately(monkeypatch):
    """Non-retryable errors (e.g. no provider) skip without retry."""
    class _NoProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            raise RuntimeError("No LLM provider configured")

    fake = _NoProvider()
    monkeypatch.setattr(scorer, "get_client", lambda: fake)
    result = scorer.score_job_single("r", {"title": "T", "full_description": "d"}, system_prompt="S")
    assert result is None
    assert fake.calls == 1  # not retried


def test_json_schema_supported_on_client_posts_schema(monkeypatch):
    """On a real-style LLMClient, _try_schema_chat posts json_schema and parses reply."""
    import json

    sent = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(
                {"score": 9, "reasoning": "perfect"})}}]}

    class _Transport:
        def post(self, url, json=None, headers=None):
            sent["url"] = url
            sent["payload"] = json
            sent["headers"] = headers
            return _Resp()

    class _LLMClient:
        base_url = "https://api.fireworks.ai/inference/v1"
        model = "accounts/fireworks/models/x"
        api_key = "k"
        _is_gemini = False
        _client = _Transport()

    client = _LLMClient()
    raw = scorer._chat_single(client, [{"role": "user", "content": "hi"}])
    assert raw
    assert sent["payload"]["response_format"]["type"] == "json_schema"
    assert "job_fit_score" in sent["payload"]["response_format"]["json_schema"]["name"]


def test_json_schema_rejected_degrades_to_json_object(monkeypatch):
    """400 from provider -> degrade to client.chat json_mode, still succeeds."""
    class _Resp400:
        status_code = 400

        def raise_for_status(self):
            return None

    class _Transport:
        def post(self, url, json=None, headers=None):
            return _Resp400()

    class _LLMClient:
        base_url = "https://api.fireworks.ai/inference/v1"
        model = "m"
        api_key = "k"
        _is_gemini = False
        _client = _Transport()

        def chat(self, messages, **kwargs):
            assert kwargs.get("json_mode") is True
            return '{"score": 6, "reasoning": "so-so"}'

    client = _LLMClient()
    text = scorer._chat_single(client, [{"role": "user", "content": "hi"}])
    assert '"score": 6' in text


def test_json_schema_not_supported_client_falls_back(monkeypatch):
    """Mock/unknown clients (no base_url) skip schema and use json_mode."""

    class _Plain:
        def chat(self, messages, **kwargs):
            assert kwargs.get("json_mode") is True
            return '{"score": 5, "reasoning": "mid"}'

    assert scorer._chat_single(_Plain(), [{"role": "user", "content": "x"}]) == (
        '{"score": 5, "reasoning": "mid"}'
    )


def test_run_scoring_on_mode_routes_fastpath_and_escalates(tmp_path, monkeypatch):
    """jev_hybrid='on': fast-accept skips deepseek; escalate still gets scored."""
    from jobwright import config
    from jobwright.database import close_connection, get_connection, init_db
    from jobwright.scoring import fastpath, scorer

    url_accept = "https://example.com/accept"
    url_escalate = "https://example.com/escalate"

    db = tmp_path / "on.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "p.json")
    monkeypatch.setattr("jobwright.resume.load_resume_text", lambda: "resume")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    close_connection(db)
    init_db(db)
    conn = get_connection(db)
    for url in (url_accept, url_escalate):
        conn.execute(
            "INSERT INTO jobs (url, title, site, full_description, discovered_at) "
            "VALUES (?, ?, 'indeed', 'desc', '2026-01-01')",
            (url, "Role"),
        )
    conn.commit()

    # Profile enables 'on'.
    monkeypatch.setattr(scorer, "load_profile", lambda: {"jev_hybrid": "on"})
    # Jev fastpath: accept -> skip deepseek; escalate -> deepseek.
    monkeypatch.setattr(
        fastpath,
        "score_fastpath",
        lambda jobs, cfg, conn: [
            {"url": url_accept, "jev_score": 9, "jev_confidence": 0.9, "jev_route": "fast_accept"},
            {"url": url_escalate, "jev_score": 6, "jev_confidence": 0.8, "jev_route": "escalate"},
        ],
    )

    class _Fake:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, **kw):
            self.calls += 1
            return '{"score": 7, "reasoning": "deepseek-escalate"}'

    fake = _Fake()
    monkeypatch.setattr(scorer, "get_client", lambda: fake)

    out = scorer.run_scoring(limit=2)
    assert out["scored"] == 2
    assert fake.calls == 1  # deepseek scored ONLY the escalated job

    row = conn.execute("SELECT fit_score FROM jobs WHERE url=?", (url_accept,)).fetchone()
    assert row["fit_score"] == 9  # jev verdict recorded, deepseek skipped
    row = conn.execute("SELECT fit_score, score_reasoning FROM jobs WHERE url=?", (url_escalate,)).fetchone()
    assert row["fit_score"] == 7  # deepseek
    assert "deepseek-escalate" in row["score_reasoning"]
    close_connection(db)