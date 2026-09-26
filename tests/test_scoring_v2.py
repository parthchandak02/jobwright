"""Scoring v2: criteria, example retrieval, gates, tiering, persistence, labels."""

from __future__ import annotations

import json

import httpx
import pytest

import jobwright.config as cfg
from jobwright.database import close_connection, get_connection, init_db
from jobwright.labels import EvalItem, build_eval_set, clear_label, label_history, record_label
from jobwright.scoring import matcher
from jobwright.scoring.criteria import derive_criteria, load_criteria, parse_criteria, render_criteria
from jobwright.scoring.evaluate import metrics
from jobwright.scoring.examples import ExampleIndex, render_examples

CRITERIA = {
    "summary": "Social impact program roles",
    "dealbreakers": [{"id": "fundraising", "description": "mainly fundraising"}, {"label": "License required"}],
    "min_salary": 100000,
}


@pytest.fixture()
def db(tmp_path):
    cfg.set_app_dir(tmp_path)
    path = tmp_path / "jobwright.db"
    close_connection(path)
    init_db(path)
    yield get_connection()
    close_connection(path)


def _job(conn, url, title="Program Manager", company="Acme Foundation", **extra):
    fields = {"url": url, "title": title, "company": company, "location": "Oakland, CA",
              "full_description": "Lead community programs. " * 20, "discovered_at": "2026-09-20", **extra}
    cols = ", ".join(fields)
    conn.execute(f"INSERT INTO jobs ({cols}) VALUES ({', '.join('?' * len(fields))})", list(fields.values()))
    conn.commit()


class FakeClient:
    def __init__(self, reply: dict | Exception, model: str = "cheap-model"):
        self.reply = reply
        self.model = model
        self.calls = 0

    def chat_structured(self, messages, schema, **kw):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return json.dumps(self.reply)


def _reply(fit=8, deals=(), loc=True, seniority="match", conf=0.9):
    return {"dealbreakers": list(deals), "concerns": [], "location_ok": loc, "seniority": seniority,
            "fit": fit, "confidence": conf, "reasoning": "because"}


def test_criteria_parse_and_derive():
    c = parse_criteria(CRITERIA)
    assert c.dealbreaker_ids() == {"fundraising", "license_required"}
    assert "[fundraising]" in render_criteria(c)
    d = derive_criteria({"job_preferences": {"avoid_roles": ["Grant writing"], "ideal_roles": ["PM"]}})
    assert d.derived and d.dealbreakers[0].id == "grant_writing" and d.must_haves == ["PM"]
    assert load_criteria({"match_criteria": CRITERIA}).derived is False


def _ctx(**kw):
    return matcher.MatchContext(resume_text="resume", criteria=parse_criteria(CRITERIA), index=None, **kw)


def test_gates_cap_dealbreakers_location_salary_and_ignore_unknown_ids():
    ctx = _ctx()
    job = {"url": "u", "title": "Program Manager", "salary": "$60,000", "company": "Acme Foundation"}
    score, deals, caps = matcher.apply_gates(_reply(fit=9, deals=["fundraising", "made_up"]), job, ctx)
    assert score == 3 and deals == ["fundraising"]
    score, _, caps = matcher.apply_gates(_reply(fit=9, loc=False), {"url": "u", "title": "PM"}, ctx)
    assert score == 3 and "location" in caps
    score, _, caps = matcher.apply_gates(_reply(fit=9), job, ctx)
    assert score == 4 and "salary below floor" in caps
    score, _, _ = matcher.apply_gates(_reply(fit=9, seniority="too_senior"), {"url": "u", "title": "PM"}, ctx)
    assert score == 9  # seniority informs fit; no hard cap by default


def test_judge_job_retries_then_scores(monkeypatch):
    monkeypatch.setattr(matcher.time, "sleep", lambda s: None)
    replies = iter(["not json", json.dumps(_reply(fit=7))])

    class Flaky(FakeClient):
        def chat_structured(self, messages, schema, **kw):
            self.calls += 1
            return next(replies)

    client = Flaky(None)
    res = matcher.judge_job(_ctx(), {"url": "u", "title": "PM"}, client, tier="t1")
    assert res.score == 7 and client.calls == 2


def test_billing_error_stops_everything(monkeypatch):
    req = httpx.Request("POST", "https://x")
    err = httpx.HTTPStatusError("402", request=req, response=httpx.Response(402, request=req))
    client = FakeClient(err)
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    with pytest.raises(matcher.BillingDead):
        matcher.score_jobs(_ctx(), [{"url": f"u{i}", "title": "PM"} for i in range(5)], workers=2, escalate=False)


def test_escalation_uses_strong_model_for_promising_jobs(monkeypatch):
    cheap, strong = FakeClient(_reply(fit=7), "cheap"), FakeClient(_reply(fit=9), "strong")
    monkeypatch.setattr(matcher, "get_client", lambda: cheap)
    monkeypatch.setattr(matcher, "get_client_for_model", lambda m: strong)
    results, errors = matcher.score_jobs(_ctx(), [{"url": "u1", "title": "PM"}], workers=1, strong_model="strong")
    assert errors == 0 and results[0].score == 9 and results[0].tier == "t2"
    assert results[0].escalated_from["model"] == "cheap"
    cheap.reply = _reply(fit=3, conf=0.95)
    results, _ = matcher.score_jobs(_ctx(), [{"url": "u2", "title": "PM"}], workers=1, strong_model="strong")
    assert results[0].tier == "t1" and strong.calls == 1


def _item(url, title, label, company="Org", rationale=""):
    return EvalItem(url, title, company, "SF", f"{title} description " * 10, "", label, "label", 2 if not label else 8,
                    rationale, None, None)


def test_examples_leave_one_out_and_positive_floor():
    items = [_item(f"n{i}", "Development Director fundraising", 0) for i in range(10)]
    items += [_item("p1", "Program Officer grantmaking", 1), _item("p2", "CSR Program Manager", 1)]
    items.append(_item("self", "Development Director fundraising", 0, company="Same Org"))
    idx = ExampleIndex(items)
    ex = idx.query("Development Director fundraising", "Same Org", "", k=4,
                   exclude_urls={"self"}, exclude_keys={"same org|development director fundraising"}, min_positive=2)
    urls = {e.item.url for e in ex}
    assert "self" not in urls and {"p1", "p2"} <= urls and len(ex) == 4
    assert "REJECTED" in render_examples(ex) and "WANTED" in render_examples(ex)


def test_labels_are_append_only_and_mirror_latest(db):
    _job(db, "https://j/1")
    record_label("https://j/1", 2, rationale="no dev roles", reasons=["fundraising"], conn=db)
    record_label("https://j/1", 8, rationale="changed my mind", conn=db)
    hist = label_history("https://j/1", conn=db)
    assert [h["label_score"] for h in hist] == [2, 8] and hist[0]["reasons"] == ["fundraising"]
    row = db.execute("SELECT user_fit_score, user_score_rationale FROM jobs WHERE url='https://j/1'").fetchone()
    assert tuple(row) == (8, "changed my mind")
    clear_label("https://j/1", conn=db)
    assert db.execute("SELECT user_fit_score FROM jobs WHERE url='https://j/1'").fetchone()[0] is None
    assert build_eval_set(db) == []


def test_label_snapshot_survives_prune(db):
    from jobwright.database import tombstone_jobs

    _job(db, "https://j/2", title="Grants Officer")
    record_label("https://j/2", 1, rationale="no", conn=db)
    db.execute("UPDATE jobs SET board_updated_by = NULL, user_fit_score = NULL WHERE url='https://j/2'")
    tombstone_jobs(db, [("https://j/2", "prune")])
    items = build_eval_set(db)
    assert len(items) == 1 and items[0].title == "Grants Officer" and items[0].label == 0


def test_eval_set_uses_implicit_board_signals(db):
    _job(db, "https://j/a", funnel_stage="applied")
    _job(db, "https://j/c", funnel_stage="closed", board_updated_by="human")
    _job(db, "https://j/b")
    labels = {i.url: (i.label, i.source) for i in build_eval_set(db)}
    assert labels == {"https://j/a": (1, "applied"), "https://j/c": (0, "closed_unapplied")}


def test_metrics_precision_recall():
    m = metrics([(9, 1), (8, 0), (3, 1), (None, 0)], 7)
    assert (m["tp"], m["fp"], m["fn"], m["precision"], m["recall"]) == (1, 1, 1, 0.5, 0.5)


def test_scoring_stage_persists_incrementally_and_records_history(db, monkeypatch, tmp_path):
    from jobwright.scoring import pipeline_v2

    for i in range(45):
        _job(db, f"https://j/{i}", title=f"Program Manager {i}")
    client = FakeClient(_reply(fit=8))
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    monkeypatch.setenv("LLM_ESCALATION_MODEL", "off")
    monkeypatch.setattr("jobwright.resume.load_resume_text", lambda: "resume text")
    out = pipeline_v2.run_scoring_v2()
    assert out["scored"] == 45 and out["errors"] == 0
    assert db.execute("SELECT COUNT(*) FROM jobs WHERE fit_score = 8 AND score_gates IS NOT NULL").fetchone()[0] == 45
    assert db.execute("SELECT COUNT(DISTINCT run_id), COUNT(*) FROM score_history").fetchone()[1] == 45
