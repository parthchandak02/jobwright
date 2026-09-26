"""Operator report, watchdog and preflight."""

from __future__ import annotations

import json
from datetime import datetime

import jobwright.config as cfg
from jobwright import ops
from jobwright.database import close_connection, init_db


def _setup(tmp_path):
    cfg.set_app_dir(tmp_path)
    close_connection(tmp_path / "jobwright.db")
    init_db(tmp_path / "jobwright.db")


def test_report_flags_failed_notify_and_stage(tmp_path):
    _setup(tmp_path)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "last_run.json").write_text(json.dumps({
        "errors": {"score": "error: 12 scoring failures"},
        "stages": [{"stage": "score", "status": "error", "detail": {"scored": 0, "errors": 12}}],
    }))
    status = tmp_path / "BRIEF_STATUS_x"
    status.write_text("started\nnotify_failed hermes send timed out\ndone RC=1\n")
    rep = ops.build_brief_report(status)
    assert rep.level == "fail"
    assert any("stage score" in line for line in rep.lines)
    assert any("notify failed" in line for line in rep.lines)
    close_connection(tmp_path / "jobwright.db")


def test_report_ok_and_no_alert_without_target(tmp_path, monkeypatch):
    _setup(tmp_path)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "last_run.json").write_text(json.dumps({"errors": {}, "stages": []}))
    status = tmp_path / "BRIEF_STATUS_x"
    status.write_text("started\nnotify_sent 3\ndone RC=0\n")
    rep = ops.build_brief_report(status)
    assert rep.level == "ok"
    assert ops.deliver(rep) == "ok (no alert)"
    rep.level = "fail"
    assert "no ops_target" in ops.deliver(rep)
    sent = []
    monkeypatch.setattr("jobwright.notify.send_via_hermes", lambda msg, target: sent.append((target, msg)))
    ops.set_ops_target("whatsapp:123@lid")
    assert ops.deliver(rep).startswith("sent to whatsapp:123@lid") and sent
    close_connection(tmp_path / "jobwright.db")


def test_watchdog_detects_missing_and_unfinished_briefs(tmp_path, monkeypatch):
    from jobwright import users as users_mod

    early = datetime.now().replace(hour=0, minute=1)
    sched = f"{early.minute} {early.hour} * * *"
    users_mod.add_user("amy", schedule=sched)
    users_mod.add_user("ben", schedule=sched)
    ben_dir = users_mod.get_user("ben").resolve_data_dir()
    (ben_dir / f"BRIEF_STATUS_{datetime.now():%Y%m%d}").write_text("started user=ben\n")
    if datetime.now() < early.replace(hour=2):
        return  # too early in the day for the grace window; nothing to assert
    reports = {r.user: r for r in ops.watchdog(grace_minutes=60)}
    assert "no brief started" in reports["amy"].lines[0]
    assert "has not finished" in reports["ben"].lines[0]


def test_preflight_reports_missing_inputs(tmp_path, monkeypatch):
    from jobwright import preflight

    cfg.set_app_dir(tmp_path)
    monkeypatch.setattr(preflight, "_playwright_launch", lambda: (True, "ok"))
    monkeypatch.setattr(preflight, "check_whatsapp_bridge", lambda: preflight.Check("whatsapp_bridge", False, False, "x"))
    checks = preflight.run_checks()
    failed = {c.name for c in preflight.blocking_failures(checks)}
    assert "user_inputs" in failed and "whatsapp_bridge" not in failed
