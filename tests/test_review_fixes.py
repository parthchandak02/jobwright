"""Post-review hardening tests: fixes for adversarial-review findings.

1. _jev_verdict must route through apply_fit_score_guards (no bypass).
2. human_gate notify must select high-scoring backlog jobs (not just prepare).
3. score_jobs_single_shot builds the LLM client once (no per-thread singleton races).
"""
import sqlite3

import pytest

from jobwright import users as users_mod
from jobwright.scoring import scorer


def _job(title="Chief Partnerships Officer", url="https://x/job/1"):
    return {"url": url, "title": title, "company": "C", "location": "SF", "full_description": "d" * 100}


def test_jev_verdict_respects_fit_score_guards():
    """A Jev fast-accept on an excluded title must be capped by the guards."""
    job = _job(title="Director of Philanthropy")  # excluded-category title
    jev = {"jev_score": 9, "jev_confidence": 0.9}
    verdict = scorer._jev_verdict(job, jev, "accept", search_cfg={"exclude_titles": ["philanthropy"]})
    assert verdict["score"] <= 4, "guards must cap excluded titles even on Jev fast-accept"


def test_jev_verdict_none_jev_defaults_low():
    verdict = scorer._jev_verdict(_job(), None, "accept", search_cfg=None)
    assert verdict["score"] == 1


def test_gated_notify_pulls_backlog_jobs(tmp_path, monkeypatch):
    """With human_gate on, notify selects scored>=7 backlog jobs, not just prepare."""
    from jobwright import notify as notify_mod

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE jobs (url TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,"
        " fit_score INTEGER, funnel_stage TEXT, whatsapp_notified_at REAL, user_fit_score INTEGER,"
        " discovered_at TEXT, job_id TEXT, full_description TEXT)"
    )
    conn.execute(
        "INSERT INTO jobs VALUES ('u1','T1','C','SF',8,'backlog',NULL,NULL,'2026-09-17','j1','d')"
    )
    conn.commit()
    rows = notify_mod.get_unnotified_gated_jobs(conn)
    assert [r["url"] for r in rows] == ["u1"]


def test_single_shot_builds_client_once(monkeypatch):
    """get_client must be called exactly once per batch, not once per job."""
    calls = {"n": 0}
    real = scorer.get_client

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(scorer, "get_client", counting)
    monkeypatch.setattr(
        scorer, "score_job_single",
        lambda resume, job, *, system_prompt, search_cfg=None, client=None: {"score": 5, "keywords": "", "reasoning": "x"},
        raising=True,
    )
    jobs = [_job(url=f"https://x/{i}") for i in range(6)]
    results, errors = scorer.score_jobs_single_shot("resume", jobs, profile=None, workers=4)
    assert errors == 0 and len(results) == 6
    assert calls["n"] == 1, "client must be built once in the parent thread"
