"""Tests for scoring evaluation (run_eval) and scoring v2 pipeline orchestration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

import jobwright.config as cfg
from jobwright.database import close_connection, get_connection, init_db
from jobwright.labels import record_label
from jobwright.scoring import matcher, pipeline_v2
from jobwright.scoring.evaluate import run_eval

CRITERIA = {
    "summary": "Social impact program and strategy roles",
    "dealbreakers": [{"id": "fundraising", "description": "primarily fundraising"}],
    "min_salary": 100000,
}

LONG_DESC = (
    "Lead community impact programs, measure outcomes across partner organizations, "
    "coordinate cross-functional strategy initiatives, and manage stakeholder reporting. "
) * 3


@pytest.fixture()
def db(tmp_path: Path):
    cfg.set_app_dir(tmp_path)
    path = tmp_path / "jobwright.db"
    close_connection(path)
    init_db(path)
    yield get_connection()
    close_connection(path)


def _insert_job(
    conn: sqlite3.Connection,
    url: str,
    *,
    title: str = "Program Manager",
    company: str = "Acme Foundation",
    location: str = "Oakland, CA",
    description: str = LONG_DESC,
    fit_score: int | None = None,
    funnel_stage: str = "backlog",
    board_updated_by: str | None = None,
    outcome: str | None = None,
    salary: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO jobs (url, title, company, location, salary, full_description, fit_score, "
        "funnel_stage, board_updated_by, outcome, discovered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-10-01T00:00:00+00:00')",
        (url, title, company, location, salary, description, fit_score, funnel_stage, board_updated_by, outcome),
    )
    conn.commit()


def _reply(fit: int = 8, deals: tuple[str, ...] = (), loc: bool | None = True, reasoning: str = "solid fit") -> dict:
    return {
        "dealbreakers": list(deals),
        "concerns": [],
        "location_ok": loc,
        "seniority": "match",
        "fit": fit,
        "confidence": 0.9,
        "reasoning": reasoning,
    }


class RecordingClient:
    """Fake structured-output LLM client recording prompts and returning scripted replies."""

    def __init__(self, replies_by_token: dict[str, dict] | None = None, default_reply: dict | None = None, model: str = "cheap-m"):
        self.replies_by_token = replies_by_token or {}
        self.default_reply = default_reply or _reply()
        self.model = model
        self.prompts: list[str] = []

    def chat_structured(self, messages, schema, **kw):  # noqa: ANN001, ANN201
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        for token, reply in self.replies_by_token.items():
            if f"TITLE: {token}\n" in prompt:
                return json.dumps(reply)
        return json.dumps(self.default_reply)


# ---------------------------------------------------------------------------
# evaluate.run_eval
# ---------------------------------------------------------------------------


def test_run_eval_end_to_end_leave_one_out_metrics_history_and_report(db, tmp_path: Path, monkeypatch):
    # Two explicit positives, one explicit negative, one implicit closed_unapplied negative,
    # and one short-description item that must be filtered out (< 200 chars).
    _insert_job(db, "https://j/pos1", title="Director of Impact Programs", company="Org Alpha", fit_score=8)
    _insert_job(db, "https://j/pos2", title="Program Strategy Lead", company="Org Beta", fit_score=7)
    _insert_job(db, "https://j/neg1", title="Annual Giving Fundraiser", company="Org Gamma", fit_score=6)
    _insert_job(
        db,
        "https://j/closed1",
        title="Operations Associate",
        company="Org Delta",
        fit_score=8,
        funnel_stage="closed",
        board_updated_by="human",
        outcome="not_interested",
    )
    _insert_job(db, "https://j/short", title="Too Short Role", company="Org Epsilon", description="short desc", fit_score=9)

    record_label("https://j/pos1", 9, rationale="great mission alignment", conn=db)
    record_label("https://j/pos2", 8, rationale="strong fit", conn=db)
    record_label("https://j/neg1", 2, rationale="fundraising heavy", conn=db)
    record_label("https://j/short", 9, rationale="ignored due to length", conn=db)

    client = RecordingClient(
        replies_by_token={
            "Director of Impact Programs": _reply(fit=9),
            "Program Strategy Lead": _reply(fit=8),
            "Annual Giving Fundraiser": _reply(fit=2, deals=("fundraising",)),
            "Operations Associate": _reply(fit=7),
        }
    )
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "off")

    flushed_active = []
    flushed_runs = []
    monkeypatch.setattr("jobwright.scoring.evaluate.flush_active_usage", lambda: flushed_active.append(True))
    monkeypatch.setattr("jobwright.scoring.evaluate.flush_usage", lambda conn, run_id: flushed_runs.append(run_id))

    report_dir = tmp_path / "eval_reports"
    report = run_eval(
        conn=db,
        resume_text="Impact strategy leader resume text.",
        profile={"match_criteria": CRITERIA},
        escalate=False,
        workers=1,
        report_dir=report_dir,
    )

    assert len(flushed_active) == 1
    assert flushed_runs == [report["run_id"]]
    assert report["config"]["n"] == 4
    assert report["config"]["positives"] == 2
    assert report["errors"] == 0

    # Short description item must be excluded.
    assert {item["url"] for item in report["items"]} == {
        "https://j/pos1",
        "https://j/pos2",
        "https://j/neg1",
        "https://j/closed1",
    }

    # Leave-one-out: the prompt for each job must never include its own rationale/title as a past decision.
    for prompt in client.prompts:
        if "TITLE: Annual Giving Fundraiser" in prompt:
            assert "fundraising heavy" not in prompt
        if "TITLE: Director of Impact Programs" in prompt:
            assert "great mission alignment" not in prompt

    # Metrics at threshold 7: explicit excludes closed_unapplied (100% precision), all includes it (fp=1).
    assert report["metrics_explicit"]["7"]["tp"] == 2
    assert report["metrics_explicit"]["7"]["fp"] == 0
    assert report["metrics_explicit"]["7"]["precision"] == 1.0
    assert report["metrics"]["7"]["fp"] == 1
    assert report["metrics"]["7"]["precision"] == 0.667

    # Baseline reflects stored jobs.fit_score before eval.
    assert report["baseline_explicit"]["6"]["fp"] == 1
    assert report["baseline_explicit"]["7"]["fp"] == 0

    # Sweep + recommended threshold are populated.
    assert len(report["sweep"]) == 7
    assert report["recommended"] is not None

    # score_history rows written with run_kind='eval' and matching run_id.
    hist_rows = db.execute(
        "SELECT job_url, score, run_kind, run_id FROM score_history WHERE run_kind = 'eval'"
    ).fetchall()
    assert len(hist_rows) == 4
    assert {r[3] for r in hist_rows} == {report["run_id"]}

    # Report JSON persisted to report_dir.
    report_path = Path(report["report_path"])
    assert report_path.exists()
    assert report_path.parent == report_dir
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["run_id"] == report["run_id"]
    assert len(saved["items"]) == 4


def test_run_eval_stratified_limit_no_history_and_usage_flush_failure(db, tmp_path: Path, monkeypatch):
    for i in range(4):
        _insert_job(db, f"https://j/p{i}", title=f"Impact Lead {i}", company=f"Co P{i}")
        record_label(f"https://j/p{i}", 8, rationale="yes", conn=db)
    for i in range(4):
        _insert_job(db, f"https://j/n{i}", title=f"Sales Rep {i}", company=f"Co N{i}")
        record_label(f"https://j/n{i}", 2, rationale="no", conn=db)

    client = RecordingClient(default_reply=_reply(fit=7))
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "off")
    monkeypatch.setattr("jobwright.scoring.evaluate.flush_active_usage", lambda: None)

    def broken_flush(conn, run_id):  # noqa: ARG001
        raise RuntimeError("sqlite busy")

    monkeypatch.setattr("jobwright.scoring.evaluate.flush_usage", broken_flush)

    r1 = run_eval(
        conn=db,
        resume_text="resume",
        profile={"match_criteria": CRITERIA},
        limit=4,
        seed=42,
        escalate=False,
        write_history=False,
        use_examples=False,
        workers=1,
        report_dir=tmp_path / "rep1",
    )
    r2 = run_eval(
        conn=db,
        resume_text="resume",
        profile={"match_criteria": CRITERIA},
        limit=4,
        seed=42,
        escalate=False,
        write_history=False,
        use_examples=False,
        workers=1,
        report_dir=tmp_path / "rep2",
    )

    assert r1["config"]["n"] == 4
    assert r1["config"]["positives"] == 2
    assert [it["url"] for it in r1["items"]] == [it["url"] for it in r2["items"]]
    assert db.execute("SELECT COUNT(*) FROM score_history").fetchone()[0] == 0


def test_run_eval_reuse_report_regates_and_runs_borderline_only(db, tmp_path: Path, monkeypatch):
    _insert_job(db, "https://j/re1", title="Program Manager", company="Org 1", location="Remote")
    _insert_job(db, "https://j/re2", title="Strategy Lead", company="Org 2", location="Remote")
    record_label("https://j/re1", 8, rationale="good", conn=db)
    record_label("https://j/re2", 2, rationale="bad", conn=db)

    prior_path = tmp_path / "prior_eval.json"
    prior_path.write_text(
        json.dumps({
            "items": [
                {
                    "url": "https://j/re1",
                    "fit": 6,
                    "dealbreakers": [],
                    "location_ok": True,
                    "seniority": "match",
                    "tier": "t1",
                    "confidence": 0.7,
                    "model": "old-model",
                    "reasoning": "borderline",
                    "concerns": [],
                },
                {
                    "url": "https://j/re2",
                    "fit": 8,
                    "dealbreakers": [],
                    "location_ok": False,
                    "seniority": "match",
                    "tier": "t1",
                    "confidence": 0.9,
                    "model": "old-model",
                    "reasoning": "wrong loc",
                    "concerns": [],
                },
            ]
        }),
        encoding="utf-8",
    )

    # Only re1 (reused score 6) triggers the borderline second opinion; re2 was capped to 3 by location gate.
    second_client = RecordingClient(default_reply=_reply(fit=8, reasoning="second opinion"))
    monkeypatch.setattr(matcher, "get_client", lambda: second_client)
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "off")
    monkeypatch.setattr("jobwright.scoring.evaluate.flush_active_usage", lambda: None)
    monkeypatch.setattr("jobwright.scoring.evaluate.flush_usage", lambda conn, run_id: None)

    report = run_eval(
        conn=db,
        resume_text="resume",
        profile={"match_criteria": CRITERIA},
        escalate=False,
        use_examples=False,
        workers=1,
        borderline=matcher.Borderline(low=5, high=6),
        reuse_report=prior_path,
        report_dir=tmp_path / "reports",
    )

    assert len(second_client.prompts) == 1
    assert "Program Manager" in second_client.prompts[0]
    assert report["config"]["reused_rows"] == 2
    assert report["second_opinions"] == 1
    by_url = {it["url"]: it for it in report["items"]}
    assert by_url["https://j/re1"]["score"] == 8
    assert by_url["https://j/re2"]["score"] == 3
    assert by_url["https://j/re2"]["caps"] == ["location"]


# ---------------------------------------------------------------------------
# pipeline_v2: BillingDead, Jev prefilter, rescore, WEB_RUN_ID
# ---------------------------------------------------------------------------


def test_score_job_list_billing_dead_zero_saved_raises_and_flushes(db, monkeypatch):
    _insert_job(db, "https://j/bill0", title="Impact Manager")
    req = httpx.Request("POST", "https://api.example.com")
    err = httpx.HTTPStatusError("402", request=req, response=httpx.Response(402, request=req))

    class DeadClient:
        model = "cheap-m"

        def chat_structured(self, messages, schema, **kw):  # noqa: ANN001, ANN201
            raise err

    monkeypatch.setattr(matcher, "get_client", lambda: DeadClient())
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "off")

    flushed = []
    monkeypatch.setattr(pipeline_v2, "flush_usage", lambda conn, run_id: flushed.append(run_id))

    rows = [dict(db.execute("SELECT * FROM jobs WHERE url = 'https://j/bill0'").fetchone())]
    with pytest.raises(RuntimeError, match="billing/auth refused"):
        pipeline_v2.score_job_list(rows, conn=db, profile={"match_criteria": CRITERIA}, resume_text="resume")

    assert len(flushed) == 1
    assert db.execute("SELECT fit_score FROM jobs WHERE url = 'https://j/bill0'").fetchone()[0] is None


def test_score_job_list_billing_dead_with_partial_saves_keeps_progress(db, monkeypatch):
    _insert_job(db, "https://j/part1", title="Impact Lead")
    _insert_job(db, "https://j/part2", title="Impact Director")
    monkeypatch.setenv("JOBWRIGHT_WEB_RUN_ID", "web-run-123")

    def fake_score_jobs(ctx, jobs, **kw):  # noqa: ANN001, ANN201
        on_result = kw["on_result"]
        on_result(
            matcher.MatchResult(
                url="https://j/part1",
                score=8,
                fit=8,
                confidence=0.9,
                dealbreakers=[],
                location_ok=True,
                seniority="match",
                reasoning="partial ok",
                model="cheap-m",
                tier="t1",
            )
        )
        raise matcher.BillingDead("402 credits exhausted")

    monkeypatch.setattr(pipeline_v2, "score_jobs", fake_score_jobs)
    monkeypatch.setattr(pipeline_v2, "flush_usage", lambda conn, run_id: None)

    rows = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY url").fetchall()]
    out = pipeline_v2.score_job_list(rows, conn=db, profile={"match_criteria": CRITERIA}, resume_text="resume")

    assert out["scored"] == 1
    assert out["run_id"] == "web-run-123"
    assert db.execute("SELECT fit_score FROM jobs WHERE url = 'https://j/part1'").fetchone()[0] == 8
    assert db.execute("SELECT fit_score FROM jobs WHERE url = 'https://j/part2'").fetchone()[0] is None
    hist = db.execute("SELECT run_id, score FROM score_history WHERE job_url = 'https://j/part1'").fetchone()
    assert tuple(hist) == ("web-run-123", 8)


def test_score_job_list_jev_prefilter_reject_and_shadow_modes(db, monkeypatch):
    from jobwright.scoring import fastpath

    _insert_job(db, "https://j/rej", title="Senior Sales Executive")
    _insert_job(db, "https://j/keep", title="Program Director")

    seen_fastpath_modes = []

    def fake_fastpath(jobs, profile, conn):  # noqa: ANN001, ANN201
        seen_fastpath_modes.append(profile.get("jev_hybrid"))
        return [
            {"url": "https://j/rej", "jev_route": "fast_reject", "jev_score": 0, "jev_confidence": 0.92},
            {"url": "https://j/keep", "jev_route": "escalate", "jev_score": 7, "jev_confidence": 0.7},
        ]

    client = RecordingClient(default_reply=_reply(fit=8))
    monkeypatch.setattr(fastpath, "score_fastpath", fake_fastpath)
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "off")
    monkeypatch.setattr(pipeline_v2, "flush_usage", lambda conn, run_id: None)

    rows = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY url").fetchall()]
    out = pipeline_v2.score_job_list(
        rows,
        conn=db,
        profile={"match_criteria": CRITERIA, "jev_hybrid": "on"},
        resume_text="resume",
    )

    assert seen_fastpath_modes == ["reject"]
    assert out["scored"] == 2
    # Only the non-rejected job went to the LLM.
    assert len(client.prompts) == 1
    assert "Program Director" in client.prompts[0]

    rej_row = db.execute("SELECT fit_score, score_tier, score_model FROM jobs WHERE url = 'https://j/rej'").fetchone()
    assert tuple(rej_row) == (1, "t0", "jev-latest")  # jev_score=0 clamped to min 1

    # Shadow mode sends all jobs to the LLM and logs no t0 scores.
    client.prompts.clear()
    seen_fastpath_modes.clear()
    out_shadow = pipeline_v2.score_job_list(
        rows,
        conn=db,
        profile={"match_criteria": CRITERIA, "jev_hybrid": "shadow"},
        resume_text="resume",
        run_kind="shadow_test",
    )
    assert seen_fastpath_modes == ["shadow"]
    assert out_shadow["scored"] == 2
    assert len(client.prompts) == 2
    assert db.execute("SELECT COUNT(*) FROM score_history WHERE run_kind = 'shadow_test' AND tier = 't0'").fetchone()[0] == 0


def test_run_scoring_v2_empty_and_rescore_with_limit(db, monkeypatch):
    # No pending jobs -> early empty summary.
    empty = pipeline_v2.run_scoring_v2()
    assert empty == {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    # Insert already-scored jobs + one without full_description (must be skipped by rescore).
    _insert_job(db, "https://j/s1", title="Impact PM 1", fit_score=5)
    _insert_job(db, "https://j/s2", title="Impact PM 2", fit_score=6)
    _insert_job(db, "https://j/nodesc", title="No Desc", description=None, fit_score=4)

    client = RecordingClient(default_reply=_reply(fit=9))
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "off")
    monkeypatch.setattr("jobwright.resume.load_resume_text", lambda: "resume text")
    monkeypatch.setattr(pipeline_v2, "load_profile", lambda: {"match_criteria": CRITERIA})
    monkeypatch.setattr(pipeline_v2, "load_search_config", lambda: {})
    monkeypatch.setattr(pipeline_v2, "flush_usage", lambda conn, run_id: (_ for _ in ()).throw(OSError("ignore")))

    out = pipeline_v2.run_scoring_v2(limit=1, rescore=True)
    assert out["scored"] == 1
    assert out["errors"] == 0
    hist = db.execute("SELECT run_kind, score FROM score_history").fetchall()
    assert len(hist) == 1
    assert tuple(hist[0]) == ("rescore", 9)
