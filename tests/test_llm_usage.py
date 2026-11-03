"""LLM usage ledger: per-user keying, purpose tags, flush per stage and per API call."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from jobwright import config, llm
from jobwright.database import close_connection, init_db


def _usage(conn) -> list[tuple]:
    return conn.execute(
        "SELECT purpose, run_id, prompt_tokens, completion_tokens FROM llm_usage ORDER BY purpose"
    ).fetchall()


@pytest.fixture()
def two_users(monkeypatch):
    import jobwright.users as users_mod

    root = users_mod.USERS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    (root / "users.yaml").write_text(
        "admins: [boss@example.com]\n"
        "users:\n"
        "  - user_id: alice\n    name: Alice\n    emails: [alice@example.com]\n"
        "  - user_id: bob\n    name: Bob\n    emails: [bob@example.com]\n",
        encoding="utf-8",
    )
    dbs = {}
    for uid in ("alice", "bob"):
        d = root / uid
        d.mkdir(exist_ok=True)
        db = d / "jobwright.db"
        close_connection(db)
        init_db(db)
        dbs[uid] = db
    llm.usage_snapshot(reset=True, user_id=None)
    yield dbs
    llm.usage_snapshot(reset=True, user_id=None)
    for db in dbs.values():
        close_connection(db)


def _open(db: Path):
    import sqlite3

    return sqlite3.connect(db)


def test_ledger_is_keyed_by_active_user(two_users):
    with config.user_context("alice"), llm.llm_purpose("tailor"):
        llm.record_usage("fireworks", "m", {"prompt_tokens": 10, "completion_tokens": 1})
    with config.user_context("bob"), llm.llm_purpose("cover"):
        llm.record_usage("fireworks", "m", {"prompt_tokens": 20, "completion_tokens": 2})

    with config.user_context("alice"):
        assert [r["purpose"] for r in llm.usage_snapshot()] == ["tailor"]
        from jobwright.database import get_connection

        assert llm.flush_usage(get_connection(), "r1") == 1
    # Bob's spend is untouched by Alice's flush and lands only in Bob's DB.
    everyone = llm.usage_snapshot(user_id=None)
    assert [(r["user_id"], r["purpose"]) for r in everyone] == [("bob", "cover")]
    with config.user_context("bob"):
        assert llm.flush_active_usage("r2") == 1

    a, b = _open(two_users["alice"]), _open(two_users["bob"])
    assert _usage(a) == [("tailor", "r1", 10, 1)]
    assert _usage(b) == [("cover", "r2", 20, 2)]


def test_concurrent_users_flush_to_their_own_db(two_users):
    barrier = threading.Barrier(2)

    def work(uid: str, tokens: int):
        with config.user_context(uid), llm.llm_purpose("onboarding"):
            barrier.wait()
            for _ in range(50):
                llm.record_usage("fireworks", "m", {"prompt_tokens": tokens, "completion_tokens": 0})
            barrier.wait()
            llm.flush_active_usage()

    threads = [threading.Thread(target=work, args=("alice", 1)), threading.Thread(target=work, args=("bob", 3))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _usage(_open(two_users["alice"])) == [("onboarding", None, 50, 0)]
    assert _usage(_open(two_users["bob"])) == [("onboarding", None, 150, 0)]


def test_failed_flush_keeps_rows(two_users):
    class Broken:
        def execute(self, *a, **k):
            raise RuntimeError("disk full")

    with config.user_context("alice"):
        llm.record_usage("fireworks", "m", {"prompt_tokens": 5, "completion_tokens": 1})
        with pytest.raises(RuntimeError):
            llm.flush_usage(Broken())
        assert llm.usage_snapshot()[0]["prompt_tokens"] == 5


def test_llm_purpose_decorator_tags_calls():
    llm.usage_snapshot(reset=True, user_id=None)

    @llm.llm_purpose("portfolio")
    def call():
        llm.record_usage("fireworks", "m", {"prompt_tokens": 1, "completion_tokens": 1})
        return llm.current_purpose()

    assert call() == "portfolio"
    assert llm.current_purpose() == "other"
    assert [r["purpose"] for r in llm.usage_snapshot(reset=True)] == ["portfolio"]


def test_call_sites_are_tagged():
    """Every in-repo LLM entry point carries a purpose (so spend is not 'other')."""
    from jobwright.enrichment import detail, sponsorship
    from jobwright.network import per_job, rank
    from jobwright.scoring import cover_letter, portfolio, tailor
    from jobwright.discovery import smartextract
    from jobwright.targets import build

    for fn in (
        tailor.tailor_resume, tailor.judge_tailored_resume, cover_letter.generate_cover_letter,
        portfolio.select_projects_for_job, per_job.rank_contacts_for_job, rank.rank_contacts,
        sponsorship._classify_llm, detail.extract_with_llm, smartextract.ask_llm,
        smartextract.judge_api_responses, build.build_target_list,
    ):
        assert hasattr(fn, "__wrapped__"), f"{fn.__module__}.{fn.__name__} has no llm_purpose tag"


def test_pipeline_flushes_usage_after_each_stage(monkeypatch):
    from jobwright import pipeline
    from jobwright.database import get_connection

    init_db()
    llm.usage_snapshot(reset=True, user_id=None)

    def fake_tailor(**kwargs):
        llm.record_usage("fireworks", "m", {"prompt_tokens": 7, "completion_tokens": 3})
        return {"status": "ok"}

    def fake_cover(**kwargs):
        with llm.llm_purpose("cover"):
            llm.record_usage("fireworks", "m", {"prompt_tokens": 4, "completion_tokens": 2})
        # Usage from the previous stage must already be in the DB.
        assert get_connection().execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0] == 1
        raise RuntimeError("boom")

    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "tailor", fake_tailor)
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "cover", fake_cover)
    monkeypatch.setenv("JOBWRIGHT_WEB_RUN_ID", "web-run-1")
    result = pipeline._run_sequential(["tailor", "cover"], 7)
    assert "cover" in result["errors"]
    rows = [tuple(r) for r in _usage(get_connection())]
    assert rows == [("cover", "web-run-1", 4, 2), ("tailor", "web-run-1", 7, 3)]
    assert llm.usage_snapshot() == []


def test_criteria_suggest_api_flushes_to_request_user(two_users, monkeypatch):
    from fastapi.testclient import TestClient

    from jobwright.scoring.criteria import parse_criteria
    from jobwright.web import session as session_mod
    from jobwright.web.app import app

    monkeypatch.setenv("JOBWRIGHT_DEV_EMAIL", "alice@example.com")
    monkeypatch.setattr("jobwright.resume.load_resume_text", lambda *a, **k: "resume")

    def fake_suggest(**kwargs):
        with llm.llm_purpose("criteria"):
            llm.record_usage("fireworks", "m", {"prompt_tokens": 11, "completion_tokens": 5})
        return parse_criteria({"summary": "x"})

    monkeypatch.setattr("jobwright.scoring.criteria_miner.suggest_criteria", fake_suggest)
    session_mod.forget_initialized()
    with TestClient(app) as client:
        res = client.post("/api/criteria/suggest")
    assert res.status_code == 200, res.text
    assert _usage(_open(two_users["alice"])) == [("criteria", None, 11, 5)]
    assert _usage(_open(two_users["bob"])) == []
    assert llm.usage_snapshot(user_id=None) == []


def test_banned_model_family_is_never_routed(monkeypatch):
    assert "gpt-oss-120b" not in llm._FIREWORKS_SHORT_MODELS
    assert not any("gpt-oss" in v for v in llm._FIREWORKS_SHORT_MODELS.values())
    monkeypatch.setenv("LLM_MODEL", "accounts/fireworks/models/gpt-oss-120b")
    _, model, _ = llm._detect_provider()
    assert model == llm._FIREWORKS_DEFAULT_MODEL
    _, model, _ = llm._detect_provider("gpt-oss-20b")
    assert model == llm._FIREWORKS_DEFAULT_MODEL


def test_onboarding_draft_api_flushes_to_request_user(two_users, monkeypatch):
    from fastapi.testclient import TestClient

    from jobwright.web import session as session_mod
    from jobwright.web.app import app

    monkeypatch.setenv("JOBWRIGHT_DEV_EMAIL", "bob@example.com")
    monkeypatch.setattr("jobwright.resume.load_resume_text", lambda *a, **k: "resume")

    def fake_draft(resume_text, hints=None, client=None):
        with llm.llm_purpose("onboarding"):
            llm.record_usage("fireworks", "m", {"prompt_tokens": 9, "completion_tokens": 4})
        return {"profile": {}}

    monkeypatch.setattr("jobwright.onboarding.draft_from_resume", fake_draft)
    session_mod.forget_initialized()
    with TestClient(app) as client:
        res = client.post("/api/onboarding/draft", data={"target_roles": "x"})
    assert res.status_code == 200, res.text
    assert _usage(_open(two_users["bob"])) == [("onboarding", None, 9, 4)]
    assert _usage(_open(two_users["alice"])) == []
