"""Per-person "Keep looking for new jobs" (search_enabled): pipeline, notify, ops, CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from jobwright import config, notify, ops, pipeline
from jobwright import users as users_mod
from jobwright.database import close_connection, init_db, job_id_for_url


def _ago(days: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _add(conn, url, stage="backlog", stage_at=None, **cols):
    row = {"url": url, "title": "Program Manager", "company": "Acme", "location": "Remote", "fit_score": 8,
           "discovered_at": _ago(1), "funnel_stage": stage, "job_id": job_id_for_url(url), **cols}
    conn.execute(f"INSERT INTO jobs ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    if stage_at:
        conn.execute(
            "INSERT INTO stage_history (job_url, from_stage, to_stage, actor, at) VALUES (?, 'prepare', ?, 'human', ?)",
            (url, stage, stage_at),
        )
    conn.commit()


@pytest.fixture()
def profile():
    users_mod.add_user("ann", name="Example Person", whatsapp_target="whatsapp:14155550100@s.whatsapp.net")
    with config.user_context("ann"):
        conn = init_db()
        yield conn
        close_connection(config.DB_PATH)


def test_registry_default_on_and_update():
    users_mod.add_user("amy")
    assert users_mod.get_user("amy").search_enabled is True
    assert users_mod.is_search_enabled("amy") is True
    assert users_mod.is_search_enabled(None) is True and users_mod.is_search_enabled("nobody") is True
    users_mod.update_user("amy", search_enabled=False)
    assert users_mod.is_search_enabled("amy") is False
    raw = users_mod.load_registry()["users"][0]
    assert raw["search_enabled"] is False


def _stub_run(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "_run_sequential",
                        lambda ordered, *a, **k: calls.append(list(ordered)) or {"stages": [], "errors": {},
                                                                                 "elapsed": 0.0})
    monkeypatch.setattr(pipeline, "write_run_summary", lambda *a, **k: None)
    monkeypatch.setattr("jobwright.run_registry.register_pipeline_run", lambda ordered: None)
    return calls


def test_default_brief_skips_every_stage_when_paused(profile, monkeypatch):
    calls = _stub_run(monkeypatch)
    users_mod.update_user("ann", search_enabled=False)
    res = pipeline.run_pipeline(stages=None)
    assert res["paused"] is True and res["stages"] == [] and not res["errors"]
    assert calls == []
    assert not (config.LOG_DIR / "last_run.json").exists()


def test_explicit_stages_beat_the_pause(profile, monkeypatch):
    calls = _stub_run(monkeypatch)
    users_mod.update_user("ann", search_enabled=False)
    res = pipeline.run_pipeline(stages=["discover", "score"])
    assert "paused" not in res
    assert calls == [["discover", "score"]]


def test_default_brief_runs_when_searching(profile, monkeypatch):
    calls = _stub_run(monkeypatch)
    users_mod.update_user("ann", human_gate=True)
    pipeline.run_pipeline(stages=None)
    assert calls == [list(pipeline.BRIEF_STAGES_HUMAN_GATED)]


def test_paused_notify_sends_no_jobs_and_nothing_when_no_followups(profile, monkeypatch):
    conn = profile
    monkeypatch.setattr(notify, "_notify_threshold", lambda: 7)
    monkeypatch.setattr(notify, "send_via_hermes", lambda *a: pytest.fail("should not send"))
    _add(conn, "https://example.com/jobs/fresh", "prepare", title="Fresh Role")
    users_mod.update_user("ann", search_enabled=False)
    res = notify.run_notify()
    assert res["skipped"] is True and res["paused"] is True and "no follow-ups" in res["reason"]
    row = conn.execute("SELECT whatsapp_notified_at FROM jobs WHERE title = 'Fresh Role'").fetchone()
    assert row[0] is None


def test_paused_notify_sends_followups_once(profile, monkeypatch):
    conn = profile
    monkeypatch.setattr(notify, "_notify_threshold", lambda: 7)
    _add(conn, "https://example.com/jobs/fresh", "prepare", title="Fresh Role")
    _add(conn, "https://example.com/jobs/a1", "applied", _ago(12), title="Applied One")
    users_mod.update_user("ann", search_enabled=False)
    sent = []
    monkeypatch.setattr(notify, "send_via_hermes", lambda msg, target: sent.append((target, msg)))

    preview = notify.run_notify(dry_run=True)
    assert preview["dry_run"] and "Applied One" in preview["message"] and not sent

    res = notify.run_notify()
    assert res["paused"] and res["sent"] == 0 and res["followups"] == 1
    assert len(sent) == 1
    msg = sent[0][1]
    assert "Time to follow up" in msg and "Applied One" in msg
    assert "Fresh Role" not in msg and "ready to review" not in msg and "search is paused" in msg
    # Same follow-ups again tomorrow: no repeat message.
    again = notify.run_notify()
    assert again["skipped"] and "already sent" in again["reason"] and len(sent) == 1
    # A newly due follow-up goes out.
    _add(conn, "https://example.com/jobs/a2", "applied", _ago(15), title="Applied Two")
    assert notify.run_notify()["followups"] == 2 and len(sent) == 2


def test_paused_notify_restores_marker_on_failure(profile, monkeypatch):
    conn = profile
    _add(conn, "https://example.com/jobs/a1", "applied", _ago(12), title="Applied One")
    users_mod.update_user("ann", search_enabled=False)

    def _fail(msg, target):
        raise RuntimeError("bridge down")

    monkeypatch.setattr(notify, "send_via_hermes", _fail)
    with pytest.raises(RuntimeError):
        notify.run_notify()
    sent = []
    monkeypatch.setattr(notify, "send_via_hermes", lambda msg, target: sent.append(msg))
    assert notify.run_notify()["followups"] == 1 and len(sent) == 1


def test_explicit_send_ignores_pause(profile, monkeypatch):
    conn = profile
    monkeypatch.setattr(notify, "_notify_threshold", lambda: 7)
    _add(conn, "https://example.com/jobs/fresh", "prepare", title="Fresh Role")
    users_mod.update_user("ann", search_enabled=False)
    res = notify.run_notify(dry_run=True, respect_pause=False)
    assert "Fresh Role" in res["message"] and not res.get("paused")


def test_brief_report_paused_is_ok_and_ignores_stale_run(profile):
    users_mod.update_user("ann", search_enabled=False)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    (config.LOG_DIR / "last_run.json").write_text(json.dumps({
        "errors": {"score": "error: old failure"},
        "stages": [{"stage": "score", "status": "error", "detail": {"scored": 0, "errors": 12}}],
    }))
    status = config.APP_DIR / "BRIEF_STATUS_x"
    status.write_text("started\nnotify_skipped search paused; no follow-ups due\ndone RC=0\n")
    rep = ops.build_brief_report(status)
    assert rep.level == "ok", rep.lines
    assert any("paused" in line for line in rep.lines)
    assert not any("stage score" in line for line in rep.lines)
    (config.LOG_DIR / "last_run.json").unlink()
    assert ops.build_brief_report(status).level == "ok"


def test_watchdog_never_alerts_for_paused_profile(monkeypatch):
    now = datetime(2026, 9, 30, 12, 30)

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(ops, "datetime", _Clock)
    monkeypatch.setattr(ops, "_is_set_up", lambda uid: True)
    users_mod.add_user("cal", schedule="0 7 * * *")
    users_mod.add_user("dee", schedule="0 7 * * *")
    users_mod.update_user("dee", search_enabled=False)
    assert [r.user for r in ops.watchdog(grace_minutes=120)] == ["cal"]


def test_cli_users_set_pause_and_resume():
    from typer.testing import CliRunner

    from jobwright.cli import app

    users_mod.add_user("amy")
    runner = CliRunner()
    res = runner.invoke(app, ["users", "set", "amy", "--pause-search"])
    assert res.exit_code == 0, res.output
    assert users_mod.get_user("amy").search_enabled is False
    res = runner.invoke(app, ["users", "set", "amy", "--search"])
    assert res.exit_code == 0, res.output
    assert users_mod.get_user("amy").search_enabled is True
