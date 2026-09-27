"""Recall work (G4): borderline second opinion, threshold sweep, report reuse, quality API."""

from __future__ import annotations

import json

import pytest

from jobwright.scoring import matcher
from jobwright.scoring.criteria import derive_criteria, parse_criteria, render_criteria
from jobwright.scoring.evaluate import prior_from_report, recommend_threshold, threshold_sweep

CRITERIA = {"summary": "Social impact program roles", "dealbreakers": [{"id": "fundraising", "description": "fundraising"}]}
JOB = {"url": "u1", "title": "PM", "location": "Remote"}


def _reply(fit, loc=True, deals=()):
    return {"dealbreakers": list(deals), "concerns": [], "location_ok": loc, "seniority": "match",
            "fit": fit, "confidence": 0.8, "reasoning": "r"}


class Scripted:
    """Returns fits in order; records the user message of each call."""

    def __init__(self, fits, model="cheap"):
        self.fits = list(fits)
        self.model = model
        self.messages = []

    def chat_structured(self, messages, schema, **kw):
        self.messages.append(messages[-1]["content"])
        fit = self.fits.pop(0)
        return json.dumps(fit if isinstance(fit, dict) else _reply(fit))


def _ctx(**kw):
    return matcher.MatchContext(resume_text="resume", criteria=parse_criteria(CRITERIA), index=None, **kw)


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    for key in ("JOBWRIGHT_BORDERLINE_BAND", "JOBWRIGHT_BORDERLINE_MODEL", "JOBWRIGHT_BORDERLINE_COMBINE"):
        monkeypatch.delenv(key, raising=False)


def test_parse_band_and_env(monkeypatch):
    assert matcher.parse_band("5-6") == (5, 6)
    assert matcher.parse_band("6:5") == (5, 6)
    assert matcher.parse_band("off") == (0, 0)
    assert matcher.parse_band("0-12") == (0, 0)
    assert matcher.parse_band("x") == (0, 0)
    assert not matcher.borderline_from_env().enabled
    monkeypatch.setenv("JOBWRIGHT_BORDERLINE_BAND", "5-6")
    monkeypatch.setenv("JOBWRIGHT_BORDERLINE_COMBINE", "mean")
    b = matcher.borderline_from_env()
    assert b.enabled and (b.low, b.high, b.combine, b.model) == (5, 6, "mean", None)


def test_borderline_off_by_default_makes_one_call(monkeypatch):
    client = Scripted([6])
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    results, _ = matcher.score_jobs(_ctx(), [JOB], workers=1, escalate=False)
    assert results[0].score == 6 and len(client.messages) == 1 and results[0].second_opinion is None


def test_borderline_max_takes_higher_second_opinion(monkeypatch):
    client = Scripted([6, 8])
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    band = matcher.Borderline(low=5, high=6)
    results, _ = matcher.score_jobs(_ctx(), [JOB], workers=1, escalate=False, borderline=band)
    r = results[0]
    assert r.score == 8 and r.second_opinion == {
        "model": "cheap", "first_score": 6, "second_score": 8, "second_fit": 8, "combine": "max",
    }
    assert "second_opinion" in json.loads(r.gates_json())


def test_borderline_mean_and_lower_second_keeps_first(monkeypatch):
    client = Scripted([5, 8, 6, 3])
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    mean = matcher.Borderline(low=5, high=6, combine="mean")
    assert matcher.score_jobs(_ctx(), [JOB], workers=1, escalate=False, borderline=mean)[0][0].score == 7
    maxb = matcher.Borderline(low=5, high=6)
    assert matcher.score_jobs(_ctx(), [JOB], workers=1, escalate=False, borderline=maxb)[0][0].score == 6


def test_borderline_skips_outside_band_and_capped(monkeypatch):
    client = Scripted([8, _reply(9, loc=False)])
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    band = matcher.Borderline(low=3, high=6)
    results, _ = matcher.score_jobs(_ctx(), [JOB, dict(JOB, url="u2")], workers=1, escalate=False, borderline=band)
    assert sorted(r.score for r in results) == [3, 8] and len(client.messages) == 2


def test_borderline_uses_other_model_and_balanced_examples(monkeypatch):
    cheap, strong = Scripted([5], "cheap"), Scripted([7], "strong")
    monkeypatch.setattr(matcher, "get_client", lambda: cheap)
    monkeypatch.setattr(matcher, "get_client_for_model", lambda m: strong)
    seen = {}

    class Index:
        def query(self, *a, min_positive=2, **kw):
            seen.setdefault("min_positive", []).append(min_positive)
            return []

    ctx = _ctx(k_examples=12, min_positive_examples=4)
    ctx.index = Index()
    band = matcher.Borderline(low=5, high=6, model="strong")
    results, _ = matcher.score_jobs(ctx, [JOB], workers=1, escalate=False, borderline=band)
    assert results[0].score == 7 and results[0].model == "strong"
    assert seen["min_positive"] == [4, 6]


def _rows(pairs, source="label"):
    return [{"score": s, "label": y, "source": source} for s, y in pairs]


def test_threshold_sweep_and_recommendation():
    rows = _rows([(9, 1), (8, 1), (7, 1), (6, 1), (6, 0), (5, 1), (5, 0), (5, 0), (3, 0), (2, 1)])
    rows += _rows([(8, 0), (8, 0)], source="closed_unapplied")
    sweep = threshold_sweep(rows)
    by_t = {s["threshold"]: s for s in sweep}
    assert by_t[7]["explicit"]["precision"] == 1.0 and by_t[7]["all"]["precision"] == 0.6
    assert by_t[6]["explicit"]["tp"] == 4 and by_t[6]["explicit"]["fp"] == 1
    rec = recommend_threshold(sweep)
    assert rec["threshold"] == 7 and rec["meets_bar"] and rec["recall"] == 0.5
    rec = recommend_threshold(sweep, min_precision=0.8)
    assert rec["threshold"] == 6 and rec["recall"] == 0.667


def test_recommendation_falls_back_when_bar_unmet():
    sweep = threshold_sweep(_rows([(9, 1), (9, 0), (8, 0), (3, 1)]))
    rec = recommend_threshold(sweep)
    assert rec is not None and rec["meets_bar"] is False
    assert recommend_threshold([]) is None


def test_prior_from_report_regates_with_current_rules(tmp_path):
    report = {"items": [
        {"url": "a", "fit": 8, "dealbreakers": [], "location_ok": False, "seniority": "match", "tier": "t1",
         "confidence": 0.9, "model": "m", "reasoning": "r", "concerns": []},
        {"url": "b", "fit": 7, "dealbreakers": [], "location_ok": True, "seniority": "stretch", "tier": "t1"},
        {"url": "c", "fit": 7, "tier": "t1"},
        {"url": "d", "fit": None, "tier": None, "seniority": None},
    ]}
    path = tmp_path / "eval.json"
    path.write_text(json.dumps(report))
    jobs = [dict(JOB, url=u) for u in "abcd"]
    prior = prior_from_report(path, jobs, _ctx())
    assert set(prior) == {"a", "b"}
    assert prior["a"].score == 3 and prior["a"].caps == ["location"] and prior["b"].score == 7


def test_score_jobs_reuses_prior_and_only_calls_for_second_opinion(monkeypatch):
    client = Scripted([8])
    monkeypatch.setattr(matcher, "get_client", lambda: client)
    first = matcher.MatchResult(url="u1", score=6, fit=6, confidence=0.7, dealbreakers=[], location_ok=True,
                                seniority="match", reasoning="", model="cheap", tier="t1")
    results, _ = matcher.score_jobs(_ctx(), [JOB], workers=1, escalate=False, prior={"u1": first},
                                    borderline=matcher.Borderline(low=5, high=6))
    assert results[0].score == 8 and len(client.messages) == 1


def test_derived_criteria_include_company_types():
    c = derive_criteria({"job_preferences": {"company_types": "Foundations; open to NY/LA and US remote"}})
    assert "open to NY/LA and US remote" in c.nice_to_haves
    assert "open to NY/LA and US remote" in render_criteria(c)


def test_quality_api_reports_recommended_threshold(tmp_path, monkeypatch):
    import jobwright.config as cfg
    from jobwright.database import close_connection, init_db
    from jobwright.web.routers import quality

    cfg.set_app_dir(tmp_path)
    init_db(tmp_path / "jobwright.db")
    cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
    items = _rows([(9, 1), (8, 1), (7, 1), (6, 1), (6, 0), (3, 0)])
    (cfg.LOG_DIR / "eval_20260927_000000_eval-x.json").write_text(json.dumps(
        {"run_id": "eval-x", "at": "2026-09-27T00:00:00+00:00", "config": {"limit": 0}, "items": items}
    ))
    monkeypatch.setattr(quality, "current_user_id", lambda request: "default")
    try:
        body = quality.quality(None)
    finally:
        close_connection(tmp_path / "jobwright.db")
    rec = body["recommended_threshold"]
    assert rec["threshold"] == 7 and rec["meets_bar"] and rec["current"] == 7
