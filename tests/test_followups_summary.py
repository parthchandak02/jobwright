"""Follow-up reminders (G8) and the weekly WhatsApp summary (G7)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from jobwright import config, followups, notify, summary
from jobwright import users as users_mod
from jobwright.database import close_connection, init_db, job_id_for_url

NOW = datetime(2026, 9, 27, 18, 0, tzinfo=UTC)


def _ago(days: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _add(conn, url, stage="backlog", stage_at=None, **cols):
    row = {"url": url, "title": "Program Manager", "company": "Acme", "location": "Remote", "fit_score": 8,
           "discovered_at": _ago(2), "funnel_stage": stage, "job_id": job_id_for_url(url), **cols}
    conn.execute(f"INSERT INTO jobs ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    if stage_at:
        conn.execute(
            "INSERT INTO stage_history (job_url, from_stage, to_stage, actor, at) VALUES (?, 'prepare', ?, 'human', ?)",
            (url, stage, stage_at),
        )
    conn.commit()


@pytest.fixture()
def profile():
    users_mod.add_user("ann", name="Ann Lee", whatsapp_target="whatsapp:ann@lid")
    with config.user_context("ann"):
        conn = init_db()
        yield conn
        close_connection(config.DB_PATH)


def test_followup_due_after_n_days_and_snooze():
    job = {"funnel_stage": "applied", "applied_at": None}
    applied = (NOW - timedelta(days=12)).isoformat()
    state = followups.followup_state(job, applied, 10, NOW)
    assert state["followup_due"] is True and state["applied_days_ago"] == 12
    assert followups.followup_state(job, (NOW - timedelta(days=9)).isoformat(), 10, NOW)["followup_due"] is False
    assert followups.followup_state({"funnel_stage": "backlog"}, applied, 10, NOW) is None

    snoozed = {**job, "followed_up_at": (NOW - timedelta(days=1)).isoformat(),
               "follow_up_at": (NOW + timedelta(days=9)).isoformat()}
    assert followups.followup_state(snoozed, applied, 10, NOW)["followup_due"] is False
    assert followups.followup_state(snoozed, applied, 10, NOW + timedelta(days=10))["followup_due"] is True


def test_stale_snooze_ignored_after_reapplying():
    job = {"funnel_stage": "applied", "follow_up_at": (NOW - timedelta(days=30)).isoformat()}
    state = followups.followup_state(job, (NOW - timedelta(days=3)).isoformat(), 10, NOW)
    assert state["followup_due"] is False


def test_due_list_actions_and_per_user_days(profile):
    conn = profile
    _add(conn, "https://x.com/old", "applied", _ago(20), title="Old")
    _add(conn, "https://x.com/mid", "applied", _ago(12), title="Mid")
    _add(conn, "https://x.com/new", "applied", _ago(3), title="New")
    _add(conn, "https://x.com/int", "in_progress", _ago(30))
    due = followups.due_followups(conn)
    assert [j["title"] for j in due] == ["Old", "Mid"]
    assert followups.due_followups(conn, limit=1)[0]["title"] == "Old"

    users_mod.update_user("ann", followup_days=2)
    assert len(followups.due_followups(conn)) == 3
    users_mod.update_user("ann", followup_days=10)

    followups.record_followed_up("https://x.com/old", conn=conn)
    row = conn.execute("SELECT followed_up_at, follow_up_at FROM jobs WHERE url = 'https://x.com/old'").fetchone()
    assert row["followed_up_at"] and row["follow_up_at"] > row["followed_up_at"]
    assert [j["title"] for j in followups.due_followups(conn)] == ["Mid"]

    followups.record_no_response("https://x.com/mid", conn=conn)
    row = conn.execute("SELECT funnel_stage, outcome, close_reason FROM jobs WHERE url = 'https://x.com/mid'").fetchone()
    assert (row["funnel_stage"], row["outcome"], row["close_reason"]) == ("closed", "ghosted", "no_response")
    assert followups.due_followups(conn) == []


def test_notify_appends_at_most_three_followups(profile, monkeypatch):
    conn = profile
    monkeypatch.setattr(notify, "_notify_threshold", lambda: 7)
    _add(conn, "https://x.com/fresh", "prepare", title="Fresh Role")
    for i in range(5):
        _add(conn, f"https://x.com/a{i}", "applied", _ago(11 + i), title=f"Applied {i}")
    res = notify.run_notify(dry_run=True)
    msg = res["message"]
    assert res["followups"] == 3
    assert msg.index("Fresh Role") < msg.index("Time to follow up")
    assert "*Applied 4*\n\U0001f3e2 Acme  \u00b7  applied 15 days ago" in msg
    assert "Applied 0" not in msg and "Applied 1" not in msg
    assert f"/jobs/{job_id_for_url('https://x.com/a4')}" in msg


def test_summary_counts_and_message(profile, monkeypatch):
    conn = profile
    monkeypatch.setattr(summary, "_notify_threshold", lambda: 7)
    _add(conn, "https://x.com/top", "backlog", fit_score=9, title="Top Role", whatsapp_notified_at=_ago(1))
    _add(conn, "https://x.com/meh", "backlog", fit_score=5, title="Meh Role")
    _add(conn, "https://x.com/old", "backlog", fit_score=9, title="Stale Role", discovered_at=_ago(60))
    _add(conn, "https://x.com/app", "applied", _ago(2), title="Applied Role", discovered_at=_ago(20))
    _add(conn, "https://x.com/int", "in_progress", _ago(1), discovered_at=_ago(20))
    _add(conn, "https://x.com/fu", "applied", _ago(14), title="Waiting Role", discovered_at=_ago(20))
    _add(conn, "https://x.com/cl", "closed", _ago(1), discovered_at=_ago(20))

    stats = summary.collect(conn, 7)
    assert stats["found"] == 2 and stats["sent"] == 1
    assert stats["applied"] == 1 and stats["in_progress"] == 1 and stats["offer"] == 0 and stats["closed"] == 1
    assert [j["title"] for j in stats["top"]] == ["Top Role"]
    assert [j["title"] for j in stats["followups"]] == ["Waiting Role"]

    msg = summary.build_summary(stats, "https://dash.example/", "Ann Lee")
    assert msg.startswith("\U0001f4ca Hi Ann, here is your *job search week*")
    assert "\U0001f50d 2 new jobs found" in msg and "\U0001f4e8 1 job sent to you" in msg
    assert "1 job moved to interviews" in msg and "offer" not in msg
    assert f"https://dash.example/jobs/{job_id_for_url('https://x.com/top')}" in msg
    assert "*Waiting Role*\n\U0001f3e2 Acme  \u00b7  applied 14 days ago" in msg
    assert msg.rstrip().endswith("Your board: https://dash.example/")


def test_run_summary_mark_then_send_and_rollback(profile, monkeypatch):
    conn = profile
    _add(conn, "https://x.com/top", "backlog", fit_score=9)
    sent = []
    monkeypatch.setattr(summary, "send_via_hermes", lambda msg, target: sent.append(target))
    res = summary.run_summary()
    assert res["sent"] is True and sent == ["whatsapp:ann@lid"]
    state = json.loads((config.LOG_DIR / summary.STATE_FILE).read_text())
    assert state["last_sent_at"]
    again = summary.run_summary()
    assert again["skipped"] and "already sent" in again["reason"] and len(sent) == 1
    assert summary.run_summary(dry_run=True)["dry_run"] is True

    (config.LOG_DIR / summary.STATE_FILE).unlink()

    def _fail(msg, target):
        raise RuntimeError("bridge down")

    monkeypatch.setattr(summary, "send_via_hermes", _fail)
    with pytest.raises(RuntimeError):
        summary.run_summary()
    assert not (config.LOG_DIR / summary.STATE_FILE).exists() or \
        "last_sent_at" not in json.loads((config.LOG_DIR / summary.STATE_FILE).read_text())


def test_run_summary_opt_out_and_empty(profile, monkeypatch):
    monkeypatch.setattr(summary, "send_via_hermes", lambda *a: pytest.fail("should not send"))
    assert summary.run_summary()["reason"] == "nothing to report"
    _add(profile, "https://x.com/top", "backlog", fit_score=9)
    users_mod.update_user("ann", weekly_summary=False)
    assert summary.run_summary()["reason"] == "opted out"


def test_run_summary_all_iterates_profiles(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_HERMES_DRY_RUN", "1")
    users_mod.add_user("ann", name="Ann", whatsapp_target="whatsapp:ann@lid")
    users_mod.add_user("bob", name="Bob", whatsapp_target="whatsapp:bob@lid")
    with config.user_context("ann"):
        _add(init_db(), "https://x.com/top", "backlog", fit_score=9)
    results = {r["user"]: r for r in summary.run_summary_all()}
    assert results["ann"]["sent"] is False and results["ann"]["dry_run"] is True
    with config.user_context("ann"):
        assert not (config.LOG_DIR / summary.STATE_FILE).exists()
    assert results["bob"]["reason"] == "no database yet"
    assert [r["user"] for r in summary.run_summary_all(["bob"])] == ["bob"]


def test_weekly_summary_cron_and_install_crons(monkeypatch):
    from typer.testing import CliRunner

    from jobwright import hermes_cron
    from jobwright.cli import app

    calls = []
    monkeypatch.setenv("JOBWRIGHT_HERMES_DRY_RUN", "1")
    monkeypatch.setattr(hermes_cron, "_run_hermes", lambda args: calls.append(args) or {"stdout": ""})
    assert hermes_cron.ensure_weekly_summary_cron()["ok"] is True
    assert ["cron", "create", "0 18 * * 0", "--name", "jobwright-weekly-summary"] in calls

    res = CliRunner().invoke(app, ["ops", "install-crons"])
    assert res.exit_code == 0, res.output
    assert "jobwright-weekly-summary" in res.output


def test_users_yaml_defaults_and_validation():
    users_mod.add_user("ann")
    u = users_mod.get_user("ann")
    assert u.weekly_summary is True and u.followup_days == 10
    with pytest.raises(ValueError):
        users_mod.update_user("ann", followup_days=0)


def test_board_followup_api(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("JOBWRIGHT_DASHBOARD_USER", "ann")
    users_mod.add_user("ann", name="Ann")
    from jobwright.web.app import app

    with config.user_context("ann"):
        conn = init_db()
        _add(conn, "https://x.com/due", "applied", _ago(12))
        _add(conn, "https://x.com/back", "backlog")
    with TestClient(app) as client:
        board = client.get("/api/board").json()
        card = board["columns"]["applied"][0]
        assert card["followup_due"] is True and card["applied_days_ago"] == 12
        assert board["columns"]["backlog"][0]["followup_due"] is False

        jid = job_id_for_url("https://x.com/due")
        assert client.post(f"/api/jobs/{job_id_for_url('https://x.com/back')}/followup",
                           json={"action": "followed_up"}).status_code == 400
        card = client.post(f"/api/jobs/{jid}/followup", json={"action": "followed_up"}).json()
        assert card["followup_due"] is False and card["followed_up_at"]
        card = client.post(f"/api/jobs/{jid}/followup", json={"action": "no_response"}).json()
        assert card["funnel_stage"] == "closed" and card["close_reason"] == "no_response"
        assert client.post(f"/api/jobs/{jid}/followup", json={"action": "x"}).status_code == 400

        prof = client.put("/api/profile", json={"weekly_summary": False, "followup_days": 14}).json()
        assert prof["weekly_summary"] is False and prof["followup_days"] == 14
        assert client.put("/api/profile", json={"followup_days": 0}).status_code == 400
    with config.user_context("ann"):
        close_connection(config.DB_PATH)


def test_summary_ignores_stage_moves_that_were_undone(tmp_path):
    import sqlite3

    from jobwright.summary import _moved

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE jobs (url TEXT, funnel_stage TEXT)")
    conn.execute("CREATE TABLE stage_history (job_url TEXT, to_stage TEXT, actor TEXT, at TEXT)")
    conn.executemany("INSERT INTO jobs VALUES (?, ?)", [("a", "closed"), ("b", "offer"), ("c", "in_progress")])
    conn.executemany("INSERT INTO stage_history VALUES (?, ?, 'human', '2026-09-22')",
                     [("a", "offer"), ("b", "offer"), ("c", "applied")])
    assert _moved(conn, ("offer",), "2026-09-20") == 1
    assert _moved(conn, ("applied",), "2026-09-20") == 1
