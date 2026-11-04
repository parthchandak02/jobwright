"""Ops reliability: truthful brief reports, discovery source health, alert fallback,
notify retries, backups + restore, run deadlines and stage budgets."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import jobwright.config as cfg
from jobwright import ops
from jobwright.database import close_connection, init_db


@pytest.fixture()
def app_dir(tmp_path):
    cfg.set_app_dir(tmp_path)
    close_connection(tmp_path / "jobwright.db")
    init_db(tmp_path / "jobwright.db")
    (tmp_path / "logs").mkdir(exist_ok=True)
    yield tmp_path
    close_connection(tmp_path / "jobwright.db")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _summary(app_dir: Path, started: datetime, **extra) -> None:
    payload = {"started_at": _iso(started), "errors": {}, "stages": [], **extra}
    (app_dir / "logs" / "last_run.json").write_text(json.dumps(payload))


def _status(app_dir: Path, start: datetime, *lines: str) -> Path:
    path = app_dir / "BRIEF_STATUS_x"
    head = f"brief_started at={start.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ} pid=1 timeout=10800s"
    path.write_text("\n".join([head, *lines]) + "\n")
    return path


# ---------------------------------------------------------------------------
# H1: brief report
# ---------------------------------------------------------------------------

def test_crashed_pipeline_fails_and_ignores_yesterdays_summary(app_dir):
    now = datetime.now(timezone.utc)
    _summary(app_dir, now - timedelta(days=1), errors={"enrich": "error: old problem"})
    status = _status(app_dir, now, "pipeline_rc=1 (notifying on ready jobs anyway)", "notify_sent 2", "done RC=1")
    rep = ops.build_brief_report(status)
    assert rep.level == "fail"
    assert any("pipeline exited with code 1" in line for line in rep.lines)
    assert any("no fresh run summary" in line for line in rep.lines)
    assert not any("old problem" in line for line in rep.lines)


def test_summary_from_a_dashboard_run_is_not_this_briefs(app_dir):
    now = datetime.now(timezone.utc)
    _summary(app_dir, now + timedelta(minutes=1), web_run_id="web-123")
    status = _status(app_dir, now, "notify_sent 1", "done RC=0")
    rep = ops.build_brief_report(status)
    assert rep.level == "warn" and any("no fresh run summary" in line for line in rep.lines)


def test_fresh_clean_run_is_ok(app_dir):
    now = datetime.now(timezone.utc)
    _summary(app_dir, now + timedelta(seconds=3), stages=[
        {"stage": "score", "status": "ok", "detail": {"scored": 5, "errors": 0}}])
    rep = ops.build_brief_report(_status(app_dir, now, "notify_sent 3", "done RC=0"))
    assert rep.level == "ok", rep.lines


def test_locked_run_warns_with_holder(app_dir, monkeypatch):
    now = datetime.now(timezone.utc)
    _summary(app_dir, now - timedelta(hours=3))
    monkeypatch.setattr("jobwright.pipeline.lock_holder", lambda: "pid=4242 started=2026-11-03T06:00:00+00:00")
    rep = ops.build_brief_report(_status(app_dir, now, "pipeline_locked (another run holds this profile's lock)",
                                         "notify_skipped no new matches", "done RC=75"))
    assert rep.level == "warn"
    assert any("another run held" in line and "pid=4242" in line for line in rep.lines)
    assert not any("pipeline exited" in line or "no fresh run summary" in line for line in rep.lines)


def test_zero_scored_and_timeout_and_uncertain_notify(app_dir):
    now = datetime.now(timezone.utc)
    _summary(app_dir, now + timedelta(seconds=1), stages=[
        {"stage": "score", "status": "ok", "detail": {"scored": 0, "errors": 0}}])
    rep = ops.build_brief_report(_status(app_dir, now, "notify_uncertain hermes send timed out", "done RC=0"))
    assert rep.level == "warn"
    assert any("scored 0 jobs" in line for line in rep.lines)
    assert any("release-uncertain" in line for line in rep.lines)
    rep = ops.build_brief_report(_status(app_dir, now, "timeout after 10800s in pipeline", "notify_sent 1",
                                         "done RC=124"))
    assert rep.level == "fail" and any("deadline" in line for line in rep.lines)


def test_lock_holder_reads_live_pid(app_dir):
    from jobwright.pipeline import lock_holder, pipeline_lock

    assert lock_holder() is None
    with pipeline_lock():
        assert f"pid={os.getpid()}" in (lock_holder() or "")
    (app_dir / ".pipeline.lock").write_text("pid=999999 started=x")
    assert lock_holder() is None  # dead pid: lock is free


# ---------------------------------------------------------------------------
# H2: discovery source health
# ---------------------------------------------------------------------------

def test_discover_records_per_source_health(monkeypatch):
    from jobwright import pipeline
    from jobwright.discovery import impactboards, jobspy, workday

    monkeypatch.setattr(jobspy, "run_discovery", lambda workers=1: {
        "new": 0, "errors": 2, "site_errors": {"linkedin": 3, "indeed+zip_recruiter": 1}, "queries": 8,
        "linkedin": {"requests": 40, "throttled": 9, "rate_limited": 4}})
    monkeypatch.setattr(workday, "run_workday_discovery", lambda workers=1: {"new": 5, "errors": 0, "queries": 2})
    monkeypatch.setattr(impactboards, "run_impact_boards", lambda workers=1: {
        "giin": {"new": 2, "error": None}, "skoll": {"new": 0, "error": "HTTPError: 503"}, "_total_new": 2})
    monkeypatch.setattr(pipeline, "_dedupe", lambda: {})
    stats = pipeline._run_discover()
    src = stats["sources"]
    assert src["jobspy"] == {"new": 0, "errors": 6, "rate_limited": 0, "status": "degraded", "queries": 8,
                             "site_errors": {"linkedin": 3, "indeed+zip_recruiter": 1}}
    assert src["linkedin"]["rate_limited"] == 4 and "new" not in src["linkedin"]
    assert src["workday"]["status"] == "ok" and src["workday"]["new"] == 5
    assert src["impact:skoll"]["errors"] == 1 and src["impact:giin"]["new"] == 2
    assert stats["status"] == "partial" and stats["new"] == 7


def test_report_names_broken_sources_with_one_line_breakdown(app_dir):
    now = datetime.now(timezone.utc)
    sources = {
        "jobspy": {"new": 0, "errors": 6, "rate_limited": 0, "status": "degraded"},
        "linkedin": {"errors": 0, "rate_limited": 4, "status": "degraded"},
        "workday": {"new": 0, "errors": 0, "rate_limited": 0, "status": "ok"},
        "impact:giin": {"new": 2, "errors": 0, "rate_limited": 0, "status": "ok"},
        "impact:skoll": {"new": 0, "errors": 1, "rate_limited": 0, "status": "error: HTTPError: 503"},
    }
    _summary(app_dir, now + timedelta(seconds=1), stages=[
        {"stage": "discover", "status": "partial", "detail": {"new": 2, "sources": sources}},
        {"stage": "score", "status": "ok", "detail": {"scored": 2, "errors": 0}}])
    rep = ops.build_brief_report(_status(app_dir, now, "notify_sent 1", "done RC=0"))
    assert rep.level == "warn"
    line = next(x for x in rep.lines if x.startswith("sources: "))
    assert "jobspy +0 (6 errors)" in line and "linkedin (rate-limited 4)" in line
    assert "impact +2 (1/2 boards failed: skoll)" in line
    assert any("source jobspy: 0 new jobs with 6 errors" in x for x in rep.lines)
    assert any("source linkedin: rate-limited" in x for x in rep.lines)
    assert any("source impact:skoll failed" in x for x in rep.lines)
    assert any("discover partial" in x for x in rep.lines)


def test_discover_zero_new_with_errors_warns(app_dir):
    now = datetime.now(timezone.utc)
    sources = {"workday": {"new": 0, "errors": 3, "rate_limited": 0, "status": "degraded"}}
    _summary(app_dir, now + timedelta(seconds=1), stages=[
        {"stage": "discover", "status": "partial", "detail": {"new": 0, "sources": sources}}])
    rep = ops.build_brief_report(_status(app_dir, now, "notify_skipped none", "done RC=0"))
    assert any("discover found 0 new jobs (3 source errors)" in x for x in rep.lines)


def test_linkedin_client_counts_requests_it_gave_up_on():
    from jobwright.discovery import linkedin

    client = linkedin.GuestClient(interval=0, max_retries=1, sleep=lambda s: None,
                                  transport=httpx.MockTransport(lambda req: httpx.Response(429)))
    with pytest.raises(linkedin.RateLimited):
        client.get("https://www.linkedin.com/jobs-guest/x")
    assert client.rate_limited == 2 and client.gave_up == 1


# ---------------------------------------------------------------------------
# H3: alert fallback + notify retry
# ---------------------------------------------------------------------------

def _osascript_log() -> list[str]:
    path = Path(os.environ["JOBWRIGHT_TEST_OSASCRIPT_LOG"])
    return path.read_text().splitlines() if path.exists() else []


def test_fallback_defaults_to_macos_only_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert ops.fallback_channels() == ["macos"]
    monkeypatch.setattr(sys, "platform", "linux")
    assert ops.fallback_channels() == []
    monkeypatch.setenv("JOBWRIGHT_OPS_FALLBACK", "off")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert ops.fallback_channels() == []
    monkeypatch.setenv("JOBWRIGHT_OPS_FALLBACK", "macos, https://ntfy.example.com/ops-topic")
    assert ops.fallback_channels() == ["macos", "https://ntfy.example.com/ops-topic"]


def test_deliver_uses_fallback_when_hermes_fails(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_OPS_TARGET", "whatsapp:14155550100@s.whatsapp.net")
    monkeypatch.setenv("JOBWRIGHT_OPS_FALLBACK", "macos,ntfy:https://ntfy.example.com/ops-topic")

    def _down(*_a):
        raise RuntimeError("bridge down")

    posted = []
    monkeypatch.setattr("jobwright.notify.send_via_hermes", _down)
    monkeypatch.setattr(ops, "_notify_ntfy", lambda url, title, body, level: posted.append((url, title, body)))
    rep = ops.Report("user1", "fail", ['notify failed "quoted" text'])
    out = ops.deliver(rep)
    assert out.startswith("alert delivery failed: bridge down") and "fallback: macos ok, ntfy ok" in out
    assert out.delivered
    assert posted == [("https://ntfy.example.com/ops-topic", "jobwright ops FAIL: user1", 'notify failed "quoted" text')]
    log_lines = _osascript_log()
    assert log_lines and "jobwright ops FAIL: user1" in log_lines[-1]


def test_deliver_ok_report_never_uses_fallback(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_OPS_FALLBACK", "macos")
    out = ops.deliver(ops.Report("user1", "ok", ["fine"]))
    assert out == "ok (no alert)" and not out.delivered and not _osascript_log()


def test_deliver_without_target_still_reaches_fallback(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_OPS_FALLBACK", "macos")
    out = ops.deliver(ops.Report("backup", "fail", ["volume missing"]))
    assert "no ops_target" in out and out.delivered and _osascript_log()


def _brief_user(monkeypatch, uid: str, *status_lines: str) -> Path:
    from jobwright import users as users_mod

    users_mod.add_user(uid, schedule="0 6 * * *")
    monkeypatch.setattr(ops, "_is_set_up", lambda _uid: True)
    path = users_mod.get_user(uid).resolve_data_dir() / f"BRIEF_STATUS_{datetime.now():%Y%m%d}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(status_lines) + "\n")
    return path


def test_notify_needs_retry_rules():
    assert ops.notify_needs_retry(["started", "notify_failed bridge down", "done RC=0"])
    assert ops.notify_needs_retry(["started", "done RC=0"])  # notify never ran
    assert not ops.notify_needs_retry(["started", "notify_failed x"])  # still running
    assert not ops.notify_needs_retry(["started", "notify_uncertain timed out", "done RC=0"])
    assert not ops.notify_needs_retry(["started", "notify_sent 2", "done RC=0"])
    assert not ops.notify_needs_retry(["started", "preflight_failed", "done RC=2"])
    assert not ops.notify_needs_retry(["notify_failed x", "done RC=0", "notify_retry 1/3", "notify_sent 1"])


def test_watchdog_retries_failed_notify_when_bridge_is_back_at_most_n_times(monkeypatch):
    status = _brief_user(monkeypatch, "rt", "started", "notify_failed bridge down", "done RC=0")
    calls = []

    def still_failing(uid, path):
        calls.append(uid)
        with path.open("a") as fh:
            fh.write("notify_failed bridge down\n")
        return 1

    assert ops.retry_failed_notifies(runner=still_failing, healthy=lambda: False) == []
    assert calls == []  # waits for a healthy bridge, records nothing
    reps = [ops.retry_failed_notifies(runner=still_failing, healthy=lambda: True, max_per_day=2)
            for _ in range(3)]
    assert calls == ["rt", "rt"] and reps[2] == []
    assert reps[0][0].level == "warn" and reps[1][0].level == "fail"
    assert "no more automatic retries" in reps[1][0].text()
    text = status.read_text()
    assert "notify_retry 1/2 by watchdog" in text and "notify_retry 2/2 by watchdog" in text
    log = json.loads((status.parent / "logs" / "notify_retries.json").read_text())
    assert len(log["attempts"]) == 2


def test_watchdog_retry_success_stops_further_retries(monkeypatch):
    _brief_user(monkeypatch, "ok1", "started", "done RC=0")

    def sends(uid, path):
        with path.open("a") as fh:
            fh.write("notify_sent 3\n")
        return 0

    (rep,) = ops.retry_failed_notifies(runner=sends, healthy=lambda: True)
    assert rep.level == "ok" and "notify sent 3" in rep.text()
    assert ops.retry_failed_notifies(runner=sends, healthy=lambda: True) == []


def test_watchdog_cli_retries_and_reports(monkeypatch):
    from jobwright.cli import app

    _brief_user(monkeypatch, "cli1", "started", "notify_failed x", "done RC=0")
    monkeypatch.setattr(ops, "install_missing_brief_crons", lambda: [])
    monkeypatch.setattr(ops, "watchdog", lambda grace_minutes=120: [])
    monkeypatch.setattr(ops, "_bridge_healthy", lambda: True)
    ran = []
    monkeypatch.setattr(ops, "_run_notify_subprocess", lambda uid, path: ran.append(uid) or 0)
    res = CliRunner().invoke(app, ["ops", "watchdog"])
    assert res.exit_code == 0 and ran == ["cli1"] and "notify retry 1/3" in res.output


# ---------------------------------------------------------------------------
# M3: watchdog states, stage budgets
# ---------------------------------------------------------------------------

class _Clock(datetime):
    fixed = datetime(2026, 11, 3, 9, 0)  # a Tuesday

    @classmethod
    def now(cls, tz=None):
        return cls.fixed if tz is None else cls.fixed.astimezone(tz)


def test_watchdog_says_still_running_not_never_started(monkeypatch):
    from jobwright import users as users_mod

    monkeypatch.setattr(ops, "datetime", _Clock)
    monkeypatch.setattr(ops, "_is_set_up", lambda uid: True)
    users_mod.add_user("slow", schedule="0 6 * * *")
    users_mod.add_user("gone", schedule="0 6 * * *")
    since = datetime(2026, 11, 2, 6, 0)
    monkeypatch.setattr(ops, "brief_process", lambda d: (321, since) if d.name == "slow" else None)
    gone = users_mod.get_user("gone").resolve_data_dir() / "BRIEF_STATUS_20261103"
    gone.write_text("started user=gone\n")
    early = datetime(2026, 11, 3, 6, 0).timestamp()
    os.utime(gone, (early, early))
    reports = {r.user: r for r in ops.watchdog(grace_minutes=120)}
    assert reports["slow"].key == "still_running" and "still running for 27.0h (pid 321" in reports["slow"].lines[0]
    assert reports["gone"].key == "not_finished" and "process gone" in reports["gone"].lines[0]


def test_watchdog_reports_timed_out_brief(monkeypatch):
    from jobwright import users as users_mod

    monkeypatch.setattr(ops, "datetime", _Clock)
    monkeypatch.setattr(ops, "_is_set_up", lambda uid: True)
    monkeypatch.setattr(ops, "brief_process", lambda d: None)
    users_mod.add_user("to", schedule="0 6 * * *")
    path = users_mod.get_user("to").resolve_data_dir() / "BRIEF_STATUS_20261103"
    path.write_text("started\ntimeout after 10800s in pipeline\nnotify_sent 1\ndone RC=124\n")
    (rep,) = ops.watchdog()
    assert rep.key == "timed_out" and "timed out" in rep.lines[0]


def test_brief_process_ignores_dead_or_foreign_pids(tmp_path):
    (tmp_path / "BRIEF_PID").write_text("999999")
    assert ops.brief_process(tmp_path) is None
    (tmp_path / "BRIEF_PID").write_text(str(os.getpid()))  # alive, but not run_daily_brief
    assert ops.brief_process(tmp_path) is None


def test_cron_day_of_week_is_honoured(monkeypatch):
    monkeypatch.setattr(ops, "datetime", _Clock)  # Tuesday
    assert ops._cron_clock_today("0 6 * * 1") is None
    assert ops._cron_clock_today("0 6 * * mon") is None
    assert ops._cron_clock_today("0 6 * * 1-5") == datetime(2026, 11, 3, 6, 0)
    assert ops._cron_clock_today("0 6 * * 2,4") is not None
    assert ops._cron_clock_today("0 6 * * sat,sun") is None
    assert ops._cron_clock_today("0 6 15 * *") is None
    assert ops._cron_clock_today("0 6 3 * 1") is not None  # day-of-month OR day-of-week
    assert ops._cron_clock_today("0 */3 * * *") is None  # not a fixed daily time


def test_enrich_stops_at_its_soft_budget_without_starting_a_browser(monkeypatch):
    from jobwright import stage_budget
    from jobwright.enrichment import detail

    monkeypatch.setenv("JOBWRIGHT_STAGE_BUDGET_ENRICH", "0.01")
    assert stage_budget.start("enrich") == 0.01
    time.sleep(0.02)

    def _no_browser():
        raise AssertionError("browser started after the budget ran out")

    monkeypatch.setattr(detail, "sync_playwright", _no_browser)
    try:
        stats = detail.scrape_site_batch(sqlite3.connect(":memory:"), "Indeed", [("u1", "t"), ("u2", "t")])
    finally:
        stage_budget.clear()
    assert stats["budget_skipped"] == 2 and stats["processed"] == 0


def test_pipeline_marks_a_stage_over_budget_and_moves_on(monkeypatch):
    from jobwright import pipeline

    monkeypatch.setenv("JOBWRIGHT_STAGE_BUDGET_SCORE", "0.01")
    order = []

    def slow_score():
        time.sleep(0.03)
        order.append("score")
        return {"status": "ok"}

    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "score", slow_score)
    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "portfolio", lambda min_score=7: order.append("portfolio") or {})
    monkeypatch.setattr(pipeline, "flush_active_usage", lambda run_id: None)
    out = pipeline._run_sequential(["score", "portfolio"], 7)
    assert order == ["score", "portfolio"]
    assert out["stages"][0]["detail"]["over_budget"] is True and not out["errors"]


# ---------------------------------------------------------------------------
# H4: backups and restore
# ---------------------------------------------------------------------------

def _profile_with_db(uid: str = "bk") -> Path:
    from jobwright import users as users_mod

    users_mod.add_user(uid)
    data = users_mod.get_user(uid).resolve_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    (data / "profile.json").write_text("{}")
    with sqlite3.connect(data / "jobwright.db") as c:
        c.execute("CREATE TABLE t (x)")
        c.execute("INSERT INTO t VALUES (42)")
    c.close()
    return data


def test_backup_skips_clutter_and_integrity_checks(tmp_path):
    data = _profile_with_db()
    for junk in ("smoke.db", "jobwright.db.bak", "jobwright.db-wal.old-wal", "jobwright.db.bak.2"):
        (data / junk).write_text("junk")
    rep = ops.backup_users(tmp_path / "bk", keep_days=14)
    snap = Path(rep["snapshot"]) / "bk"
    assert not rep["errors"], rep["errors"]
    assert sorted(p.name for p in snap.iterdir() if p.is_file()) == ["jobwright.db", "profile.json"]


def test_backup_reports_corrupt_db_and_keeps_old_snapshots(tmp_path):
    data = _profile_with_db()
    (data / "other.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)  # not a valid DB
    dest = tmp_path / "bk"
    (dest / "2000-01-01_0000").mkdir(parents=True)
    rep = ops.backup_users(dest, keep_days=14)
    assert any("other.db" in e for e in rep["errors"])
    assert (dest / "2000-01-01_0000").exists() and rep["pruned"] == []


def test_backup_to_unmounted_volume_alerts(tmp_path, monkeypatch):
    from jobwright.cli import app

    _profile_with_db()
    missing = tmp_path / "Volumes" / "ExternalSSD" / "Backups" / "jobwright"
    rep = ops.safe_backup(missing)
    assert rep["errors"] and "volume not mounted" in rep["errors"][0]
    assert not (tmp_path / "Volumes").exists()  # never fakes the mount point
    sent = []
    monkeypatch.setattr(ops, "deliver", lambda report, force=False: sent.append(report) or "sent")
    res = CliRunner().invoke(app, ["ops", "backup", "--dest", str(missing)])
    assert res.exit_code == 1 and sent and sent[0].level == "fail"
    assert "backup crashed" in sent[0].lines[0]


def test_backup_then_restore_opens_the_db(tmp_path):
    from jobwright.cli import app

    data = _profile_with_db("rs")
    dest = tmp_path / "bk"
    rep = ops.backup_users(dest)
    assert not rep["errors"]
    target = tmp_path / "restored"
    res = CliRunner().invoke(app, ["ops", "restore", "--snapshot", "latest", "--user", "rs",
                                   "--to", str(target), "--dest", str(dest)])
    assert res.exit_code == 0, res.output
    assert "integrity_check ok" in res.output
    with sqlite3.connect(target / "jobwright.db") as c:
        assert c.execute("SELECT x FROM t").fetchone()[0] == 42
    c.close()
    assert (target / "profile.json").exists()

    # A live profile dir is never overwritten without --force; with it the old dir is moved aside.
    with pytest.raises(FileExistsError):
        ops.restore_snapshot("latest", "rs", data, backup_root=dest)
    out = ops.restore_snapshot(Path(rep["snapshot"]).name, "rs", data, force=True, backup_root=dest)
    assert out["ok"] and Path(out["moved_aside"]).is_dir() and (data / "jobwright.db").exists()
    with pytest.raises(FileNotFoundError):
        ops.restore_snapshot("1999-01-01_0000", "rs", tmp_path / "x", backup_root=dest)


def test_cleanup_old_brief_files(tmp_path):
    from jobwright import users as users_mod

    users_mod.add_user("cl")
    data = users_mod.get_user("cl").resolve_data_dir()
    (data / "logs").mkdir(parents=True, exist_ok=True)
    old = (datetime.now() - timedelta(days=40)).strftime("%Y%m%d")
    new = datetime.now().strftime("%Y%m%d")
    for name in (f"BRIEF_STATUS_{old}", f"BRIEF_PID_{old}", f"BRIEF_STATUS_{new}", "BRIEF_PID"):
        (data / name).write_text("x")
    (data / "logs" / f"brief_{old}.log").write_text("x")
    (data / "logs" / f"brief_{new}.log").write_text("x")
    removed = ops.cleanup_old_brief_files(30)
    assert len(removed) == 3
    assert sorted(p.name for p in data.iterdir() if p.is_file()) == ["BRIEF_PID", f"BRIEF_STATUS_{new}"]
    assert [p.name for p in (data / "logs").iterdir()] == [f"brief_{new}.log"]
