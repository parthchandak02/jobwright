"""Tests for jobwright.pipeline orchestration, stage wrappers, and run policies."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

from jobwright import config, database, pipeline, stage_budget, users


def _seed_user(user_id: str, *, human_gate: bool = False, search_enabled: bool = True) -> None:
    users.add_user(user_id, name="Alex Rivera", human_gate=human_gate)
    if not search_enabled:
        users.update_user(user_id, search_enabled=False)


# ---------------------------------------------------------------------------
# Stage resolution, human gate, and search pause
# ---------------------------------------------------------------------------


def test_resolve_stages_orders_dedupes_and_handles_all():
    assert pipeline._resolve_stages(["all"]) == list(pipeline.STAGE_ORDER)
    assert pipeline._resolve_stages(["docx", "discover", "docx", "score"]) == [
        "discover",
        "score",
        "docx",
    ]


def test_resolve_stages_rejects_unknown_stage():
    with pytest.raises(SystemExit) as exc:
        pipeline._resolve_stages(["discover", "not-a-stage"])
    assert exc.value.code == 1


def test_default_brief_stages_honors_human_gate():
    _seed_user("gated_user", human_gate=True)
    _seed_user("full_user", human_gate=False)

    with config.user_context("gated_user"):
        assert pipeline.default_brief_stages() == list(pipeline.BRIEF_STAGES_HUMAN_GATED)
    with config.user_context("full_user"):
        assert pipeline.default_brief_stages() == list(pipeline.STAGE_ORDER)


def test_run_pipeline_skips_default_brief_when_search_paused(monkeypatch):
    _seed_user("paused_user", search_enabled=False)
    called: list[str] = []
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "score", lambda **_k: called.append("score") or {"status": "ok"})

    with config.user_context("paused_user"):
        assert pipeline.search_paused() is True
        paused_res = pipeline.run_pipeline(stages=None)
        assert paused_res == {"stages": [], "errors": {}, "elapsed": 0.0, "paused": True}
        assert pipeline.read_run_summary() is None
        assert called == []

        explicit_res = pipeline.run_pipeline(stages=["score"])
        assert explicit_res["errors"] == {}
        assert called == ["score"]
        summary = pipeline.read_run_summary()
        assert summary is not None and summary["stages_requested"] == ["score"]


# ---------------------------------------------------------------------------
# Dry run and lock holder
# ---------------------------------------------------------------------------


def test_run_pipeline_dry_run_skips_execution_and_summary(monkeypatch):
    called: list[str] = []
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "score", lambda **_k: called.append("score") or {"status": "ok"})

    res = pipeline.run_pipeline(stages=["score"], dry_run=True)

    assert res == {"stages": [], "errors": {}, "elapsed": 0.0}
    assert called == []
    assert pipeline.read_run_summary() is None


def test_run_pipeline_returns_locked_when_lock_held():
    config.ensure_dirs()
    with pipeline.pipeline_lock():
        holder = pipeline.lock_holder()
        assert holder is not None and f"pid={os.getpid()}" in holder
        res = pipeline.run_pipeline(stages=["score"])

    assert res["locked"] is True
    assert "lock" in res["errors"]
    assert res["stages"] == []
    assert pipeline.read_run_summary() is None


def test_lock_holder_handles_missing_malformed_and_dead_pid(monkeypatch):
    config.ensure_dirs()
    lock_path = Path(config.APP_DIR) / ".pipeline.lock"

    assert pipeline.lock_holder() is None

    lock_path.write_text("started=now", encoding="utf-8")
    assert pipeline.lock_holder() is None

    lock_path.write_text("pid=notanint started=now", encoding="utf-8")
    assert pipeline.lock_holder() is None

    lock_path.write_text("pid=999999 started=now", encoding="utf-8")

    def fake_kill(_pid: int, _sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(pipeline.os, "kill", fake_kill)
    assert pipeline.lock_holder() is None

    def perm_kill(_pid: int, _sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(pipeline.os, "kill", perm_kill)
    assert pipeline.lock_holder() == "pid=999999 started=now"


# ---------------------------------------------------------------------------
# _run_discover and source health
# ---------------------------------------------------------------------------


def _install_fake_discover_modules(
    monkeypatch,
    *,
    jobspy_fn,
    workday_fn=None,
    impact_fn=None,
    smart_fn=None,
) -> None:
    jobspy_mod = types.ModuleType("jobwright.discovery.jobspy")
    jobspy_mod.run_discovery = jobspy_fn
    monkeypatch.setitem(sys.modules, "jobwright.discovery.jobspy", jobspy_mod)

    if workday_fn is not None:
        workday_mod = types.ModuleType("jobwright.discovery.workday")
        workday_mod.run_workday_discovery = workday_fn
        monkeypatch.setitem(sys.modules, "jobwright.discovery.workday", workday_mod)

    impact_mod = types.ModuleType("jobwright.discovery.impactboards")
    impact_mod.run_impact_boards = impact_fn or (lambda workers=1: {})
    monkeypatch.setitem(sys.modules, "jobwright.discovery.impactboards", impact_mod)

    if smart_fn is not None:
        smart_mod = types.ModuleType("jobwright.discovery.smartextract")
        smart_mod.run_smart_extract = smart_fn
        monkeypatch.setitem(sys.modules, "jobwright.discovery.smartextract", smart_mod)


def test_run_discover_fast_mode_and_skipped_circuit_breakers(monkeypatch):
    monkeypatch.setenv("DISCOVER_MODE", "invalid-mode")
    monkeypatch.setenv("DISCOVER_WORKDAY", "0")
    monkeypatch.setattr(pipeline, "_dedupe", lambda: {"removed": 1})

    _install_fake_discover_modules(
        monkeypatch,
        jobspy_fn=lambda workers=1: {
            "new": 5,
            "errors": 0,
            "queries": 4,
            "site_errors": {},
            "site_health": {
                "glassdoor": {"status": "blocked", "skipped": 2, "blocked_responses": 1},
                "zip_recruiter": {"status": "cooldown", "skipped": 1, "until": "2026-11-16T00:00:00Z"},
            },
        },
        impact_fn=lambda workers=1: {"ideal": {"new": 2}},
    )

    stats = pipeline._run_discover(workers=2)

    assert stats["mode"] == "fast"
    assert stats["workday"] == "skipped"
    assert stats["smartextract"] == "skipped"
    assert stats["status"] == "ok"
    assert stats["new"] == 7
    assert stats["sources"]["glassdoor"] == {
        "errors": 0,
        "rate_limited": 0,
        "status": "blocked",
        "skipped": 2,
        "blocked_responses": 1,
    }
    assert stats["sources"]["zip_recruiter"]["until"] == "2026-11-16T00:00:00Z"


def test_run_discover_full_mode_degraded_sources_and_partial_errors(monkeypatch):
    monkeypatch.setenv("DISCOVER_MODE", "full")
    monkeypatch.setenv("DISCOVER_WORKDAY", "1")
    monkeypatch.setattr(pipeline, "_dedupe", lambda: {"removed": 0})

    _install_fake_discover_modules(
        monkeypatch,
        jobspy_fn=lambda workers=1: {
            "new": 3,
            "errors": 0,
            "site_errors": {},
            "linkedin": {"rate_limited": 0, "throttled": 1, "requests": 10},
            "site_health": {
                "linkedin": {"status": "ok", "skipped": 2, "blocked_responses": 1},
                "indeed": {"status": "warning", "skipped": 1, "blocked_responses": 3},
            },
        },
        workday_fn=lambda workers=1: (_ for _ in ()).throw(RuntimeError("workday down")),
        impact_fn=lambda workers=1: {
            "good_board": {"new": 4},
            "bad_board": {"new": 0, "error": "http 503"},
        },
        smart_fn=lambda workers=1: {"total_new": 2, "total": 3, "passed": 2},
    )

    stats = pipeline._run_discover(workers=3)

    assert stats["mode"] == "full"
    assert stats["status"] == "partial"
    assert stats["workday"] == "error: workday down"
    assert stats["smartextract"] == "ok"
    assert stats["impact_boards_failed"] == ["bad_board"]
    assert stats["sources"]["linkedin"]["status"] == "degraded"
    assert stats["sources"]["linkedin"]["skipped"] == 2
    assert "new" not in stats["sources"]["linkedin"]
    assert stats["sources"]["indeed"] == {
        "errors": 0,
        "rate_limited": 3,
        "status": "degraded",
        "skipped": 1,
    }
    assert stats["sources"]["smartextract"]["errors"] == 1
    assert stats["sources"]["smartextract"]["status"] == "degraded"
    assert stats["sources"]["impact:bad_board"]["status"] == "error: http 503"
    assert stats["new"] == 9


def test_run_discover_all_sources_fail(monkeypatch):
    monkeypatch.setenv("DISCOVER_MODE", "full")
    monkeypatch.setenv("DISCOVER_WORKDAY", "1")
    monkeypatch.setattr(pipeline, "_dedupe", lambda: {"removed": 0})

    def boom(**_k):
        raise RuntimeError("boom")

    _install_fake_discover_modules(
        monkeypatch,
        jobspy_fn=boom,
        workday_fn=boom,
        impact_fn=boom,
        smart_fn=boom,
    )

    stats = pipeline._run_discover()

    assert stats["status"] == "error: every discovery source failed"
    assert stats["new"] == 0
    assert stats["sources"]["workday"]["status"] == "error: boom"
    assert stats["sources"]["impact_boards"]["status"] == "error: boom"
    assert stats["sources"]["smartextract"]["status"] == "error: boom"


# ---------------------------------------------------------------------------
# Individual stage wrappers
# ---------------------------------------------------------------------------


def test_run_enrich_status_branches(monkeypatch):
    detail_mod = types.ModuleType("jobwright.enrichment.detail")
    monkeypatch.setitem(sys.modules, "jobwright.enrichment.detail", detail_mod)

    detail_mod.run_enrichment = lambda workers=1: {"processed": 4, "ok": 1, "partial": 0, "error": 3}
    assert pipeline._run_enrich(workers=2)["status"] == "ok"

    detail_mod.run_enrichment = lambda workers=1: {"processed": 3, "ok": 0, "partial": 0, "error": 3}
    assert pipeline._run_enrich()["status"] == "error: all 3 enrichments failed"

    detail_mod.run_enrichment = lambda workers=1: (_ for _ in ()).throw(ValueError("bad html"))
    assert pipeline._run_enrich() == {"status": "error: bad html"}


def test_run_score_branches(monkeypatch):
    database.init_db()
    scorer_mod = types.ModuleType("jobwright.scoring.scorer")
    cleanup_mod = types.ModuleType("jobwright.discovery.cleanup")
    monkeypatch.setitem(sys.modules, "jobwright.scoring.scorer", scorer_mod)
    monkeypatch.setitem(sys.modules, "jobwright.discovery.cleanup", cleanup_mod)

    calls: list[str] = []
    monkeypatch.setattr(pipeline, "_dedupe", lambda: calls.append("dedupe") or {"removed": 0})
    monkeypatch.setattr(pipeline, "_collapse_duplicates", lambda: calls.append("collapse") or {"closed": 2})

    scorer_mod.run_scoring = lambda: {"scored": 5, "errors": 1}
    cleanup_mod.prune_after_score = lambda _conn, dry_run=False: {"pruned": 3}
    res = pipeline._run_score()
    assert res["status"] == "ok"
    assert res["prune"] == {"pruned": 3}
    assert res["collapse"] == {"closed": 2}
    assert calls == ["dedupe", "collapse"]

    cleanup_mod.prune_after_score = lambda _conn, dry_run=False: (_ for _ in ()).throw(RuntimeError("prune err"))
    res_prune_err = pipeline._run_score()
    assert res_prune_err["status"] == "ok"
    assert "prune" not in res_prune_err

    calls.clear()
    scorer_mod.run_scoring = lambda: {"scored": 0, "errors": 4}
    res_all_err = pipeline._run_score()
    assert res_all_err["status"] == "error: 4 scoring failures"
    assert calls == ["dedupe"]

    scorer_mod.run_scoring = lambda: (_ for _ in ()).throw(RuntimeError("llm down"))
    assert pipeline._run_score() == {"status": "error: llm down"}


def test_remaining_stage_wrappers_and_prep_limit(monkeypatch):
    monkeypatch.setenv("APPLY_LIMIT", "3")
    monkeypatch.delenv("APPLY_PREP_LIMIT", raising=False)
    assert pipeline._prep_limit() == 10
    monkeypatch.setenv("APPLY_LIMIT", "8")
    assert pipeline._prep_limit() == 16
    monkeypatch.setenv("APPLY_PREP_LIMIT", "12")
    assert pipeline._prep_limit() == 12

    portfolio_mod = types.ModuleType("jobwright.scoring.portfolio")
    cover_mod = types.ModuleType("jobwright.scoring.cover_letter")
    pdf_mod = types.ModuleType("jobwright.scoring.pdf")
    docx_mod = types.ModuleType("jobwright.scoring.docx_export")
    connect_mod = types.ModuleType("jobwright.network.per_job")
    monkeypatch.setitem(sys.modules, "jobwright.scoring.portfolio", portfolio_mod)
    monkeypatch.setitem(sys.modules, "jobwright.scoring.cover_letter", cover_mod)
    monkeypatch.setitem(sys.modules, "jobwright.scoring.pdf", pdf_mod)
    monkeypatch.setitem(sys.modules, "jobwright.scoring.docx_export", docx_mod)
    monkeypatch.setitem(sys.modules, "jobwright.network.per_job", connect_mod)

    portfolio_mod.run_portfolio_selection = lambda min_score, limit: {"status": "ok", "min_score": min_score, "limit": limit}
    assert pipeline._run_portfolio(min_score=8) == {"status": "ok", "min_score": 8, "limit": 12}
    portfolio_mod.run_portfolio_selection = lambda **_k: (_ for _ in ()).throw(RuntimeError("pf err"))
    assert pipeline._run_portfolio() == {"status": "error: pf err"}

    cover_mod.run_cover_letters = lambda **_k: {"generated": 2, "errors": 0}
    assert pipeline._run_cover()["status"] == "ok"
    cover_mod.run_cover_letters = lambda **_k: {"generated": 0, "errors": 2}
    assert pipeline._run_cover()["status"] == "error: all 2 cover letters failed"
    cover_mod.run_cover_letters = lambda **_k: (_ for _ in ()).throw(RuntimeError("cv err"))
    assert pipeline._run_cover() == {"status": "error: cv err"}

    pdf_mod.batch_convert = lambda: 4
    assert pipeline._run_pdf() == {"status": "ok", "converted": 4}
    pdf_mod.batch_convert = lambda: (_ for _ in ()).throw(RuntimeError("pdf err"))
    assert pipeline._run_pdf() == {"status": "error: pdf err"}

    docx_mod.batch_convert_docx = lambda limit, min_score: {"status": "ok", "limit": limit, "min_score": min_score}
    assert pipeline._run_docx(min_score=6) == {"status": "ok", "limit": 12, "min_score": 6}
    docx_mod.batch_convert_docx = lambda **_k: (_ for _ in ()).throw(RuntimeError("docx err"))
    assert pipeline._run_docx() == {"status": "error: docx err"}

    monkeypatch.setenv("JOBWRIGHT_CONNECT_LIMIT", "7")
    connect_mod.run_per_job_connect = lambda min_score, limit: {"status": "ok", "min_score": min_score, "limit": limit}
    assert pipeline._run_connect(min_score=9) == {"status": "ok", "min_score": 9, "limit": 7}
    connect_mod.run_per_job_connect = lambda **_k: (_ for _ in ()).throw(RuntimeError("conn err"))
    assert pipeline._run_connect() == {"status": "error: conn err"}


# ---------------------------------------------------------------------------
# Sequential runner: kwargs, budget, partial/skipped vs errors, crash recovery
# ---------------------------------------------------------------------------


def test_run_sequential_kwargs_budget_and_crash_isolation(monkeypatch):
    seen_kwargs: dict[str, dict] = {}
    flushed: list[str] = []
    budget_cleared: list[bool] = []

    monkeypatch.setattr(pipeline, "flush_active_usage", lambda run_id: flushed.append(run_id))
    monkeypatch.setattr(stage_budget, "start", lambda name: 60 if name == "enrich" else 0)
    monkeypatch.setattr(stage_budget, "exceeded", lambda: bool(seen_kwargs.get("enrich") and "score" not in seen_kwargs))
    monkeypatch.setattr(stage_budget, "clear", lambda: budget_cleared.append(True))

    def fake_discover(**kw):
        seen_kwargs["discover"] = kw
        return {"status": "partial", "new": 1}

    def fake_enrich(**kw):
        seen_kwargs["enrich"] = kw
        return {"status": "ok"}

    def fake_score(**kw):
        seen_kwargs["score"] = kw
        raise RuntimeError("score blew up")

    def fake_tailor(**kw):
        seen_kwargs["tailor"] = kw
        return {"status": "skipped"}

    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "discover", fake_discover)
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "enrich", fake_enrich)
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "score", fake_score)
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "tailor", fake_tailor)

    res = pipeline._run_sequential(["discover", "enrich", "score", "tailor"], min_score=8, workers=4, validation_mode="strict")

    assert seen_kwargs["discover"] == {"workers": 4}
    assert seen_kwargs["enrich"] == {"workers": 4}
    assert seen_kwargs["score"] == {}
    assert seen_kwargs["tailor"] == {"min_score": 8, "validation_mode": "strict"}

    by_stage = {r["stage"]: r for r in res["stages"]}
    assert by_stage["discover"]["status"] == "partial"
    assert by_stage["enrich"]["detail"].get("over_budget") is True
    assert by_stage["score"]["status"] == "error: score blew up"
    assert by_stage["tailor"]["status"] == "skipped"

    assert res["errors"] == {"score": "error: score blew up"}
    assert len(flushed) == 4 and len(set(flushed)) == 1
    assert len(budget_cleared) == 4


def test_run_pipeline_none_stages_uses_default_brief_stages_and_persists_errors(monkeypatch):
    _seed_user("brief_user", human_gate=True, search_enabled=True)
    ran: list[str] = []

    for name in pipeline.BRIEF_STAGES_HUMAN_GATED:
        if name == "discover":
            monkeypatch.setitem(
                pipeline._STAGE_RUNNERS, name, lambda _n=name, **_k: ran.append(_n) or {"status": "partial"}
            )
        elif name == "score":
            monkeypatch.setitem(
                pipeline._STAGE_RUNNERS, name, lambda _n=name, **_k: ran.append(_n) or {"status": "error: timeout"}
            )
        else:
            monkeypatch.setitem(
                pipeline._STAGE_RUNNERS, name, lambda _n=name, **_k: ran.append(_n) or {"status": "ok"}
            )

    with config.user_context("brief_user"):
        res = pipeline.run_pipeline(stages=None)
        summary = pipeline.read_run_summary()

    assert ran == list(pipeline.BRIEF_STAGES_HUMAN_GATED)
    assert res["errors"] == {"score": "error: timeout"}
    assert summary is not None
    assert summary["ok"] is False
    assert summary["errors"] == {"score": "error: timeout"}
    assert summary["stages_requested"] == list(pipeline.BRIEF_STAGES_HUMAN_GATED)


def test_run_discover_workday_success_and_dedupe_collapse_wrappers(monkeypatch):
    database.init_db()
    monkeypatch.setenv("DISCOVER_WORKDAY", "1")
    monkeypatch.setenv("DISCOVER_MODE", "fast")
    monkeypatch.setattr(pipeline, "_dedupe", lambda: {"removed": 0})

    _install_fake_discover_modules(
        monkeypatch,
        jobspy_fn=lambda workers=1: {"new": 1, "errors": 0, "site_errors": {}},
        workday_fn=lambda workers=1: {"new": 6, "errors": 0, "queries": 3},
        impact_fn=lambda workers=1: {},
    )

    stats = pipeline._run_discover()
    assert stats["workday"] == "ok"
    assert stats["sources"]["workday"] == {
        "new": 6,
        "errors": 0,
        "rate_limited": 0,
        "status": "ok",
        "queries": 3,
    }
    assert stats["new"] == 7


def test_dedupe_and_collapse_duplicates_suppress_errors(monkeypatch):
    database.init_db()
    dedupe_mod = types.ModuleType("jobwright.discovery.dedupe")
    monkeypatch.setitem(sys.modules, "jobwright.discovery.dedupe", dedupe_mod)

    dedupe_mod.dedupe_new_jobs = lambda _conn: {"merged": 2}
    dedupe_mod.collapse_duplicates = lambda _conn, apply=True: {
        "group_count": 1,
        "closed": 1,
        "blocked": ["j1", "j2"],
    }

    assert pipeline._dedupe() == {"merged": 2}
    assert pipeline._collapse_duplicates() == {"group_count": 1, "closed": 1, "blocked": 2}

    dedupe_mod.dedupe_new_jobs = lambda _conn: (_ for _ in ()).throw(RuntimeError("db busy"))
    dedupe_mod.collapse_duplicates = lambda _conn, apply=True: (_ for _ in ()).throw(RuntimeError("db locked"))

    assert pipeline._dedupe() == {"error": "db busy"}
    assert pipeline._collapse_duplicates() == {"error": "db locked"}

