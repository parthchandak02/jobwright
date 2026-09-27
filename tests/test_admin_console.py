"""Admin console v2 API: overview, inline patch, per-person test message and run."""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta

import pytest
import yaml

pytest.importorskip("fastapi")
jwt = pytest.importorskip("jwt")

ANN_GROUP = "whatsapp:120363999999999902@g.us"


def _write_registry(root) -> None:
    (root / "users.yaml").write_text(yaml.safe_dump({
        "admins": ["boss@example.com"],
        "users": [
            {"user_id": "ann", "name": "Ann Lee", "emails": ["ann@example.com"], "whatsapp_target": ANN_GROUP,
             "schedule": "0 6 * * *", "human_gate": True, "brief_top_n": 10},
            {"user_id": "bo", "name": "Bo", "emails": ["bo@example.com"], "schedule": "30 7 * * *"},
        ],
    }), encoding="utf-8")


def _set_up_ann(root) -> None:
    from jobwright.database import close_connection, init_db

    ann = root / "ann"
    (ann / "logs").mkdir(parents=True, exist_ok=True)
    (ann / "profile.json").write_text(json.dumps({
        "experience": {"target_role": "Product manager"},
        "job_preferences": {"avoid_roles": ["sales"]},
    }), encoding="utf-8")
    (ann / "logs" / "ops_health.json").write_text(json.dumps({"level": "ok", "lines": ["scored 5 jobs"]}))
    (ann / f"BRIEF_STATUS_{datetime.now():%Y%m%d}").write_text("started\nnotify_sent 8\n", encoding="utf-8")
    (ann / "logs" / "eval_20260901.json").write_text(json.dumps({"recommended": {"threshold": 6}}))
    db = ann / "jobwright.db"
    close_connection(db)
    init_db(db)
    close_connection(db)
    conn = sqlite3.connect(db)
    now = datetime.now(UTC)
    rows = [
        ("u1", (now - timedelta(days=1)).isoformat(), (now - timedelta(days=1)).isoformat(), None, "prepare"),
        ("u2", (now - timedelta(days=2)).isoformat(), None, (now - timedelta(days=30)).isoformat(), "applied"),
        ("u3", (now - timedelta(days=20)).isoformat(), None, None, "closed"),
    ]
    conn.executemany(
        "INSERT INTO jobs (url, discovered_at, whatsapp_notified_at, applied_at, funnel_stage) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("INSERT INTO llm_usage (at, model, prompt_tokens, completion_tokens, cost_usd) VALUES (?, ?, ?, ?, ?)",
                 (now.isoformat(), "other", 100, 50, 0.5))
    conn.commit()
    conn.close()


@pytest.fixture()
def console(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient

    import jobwright.users as users_mod
    from jobwright import config
    from jobwright.web import auth as auth_mod
    from jobwright.web import session as session_mod

    root = tmp_path / "users"
    root.mkdir()
    _write_registry(root)
    monkeypatch.setattr(users_mod, "USERS_ROOT", root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", root / "users.yaml")
    with config.user_context("ann"):
        resume = config.RESUME_PDF_PATH
    assert str(resume).startswith(str((root / "ann").resolve()))
    _set_up_ann(root)
    resume.parent.mkdir(parents=True, exist_ok=True)
    resume.write_bytes(b"%PDF-1.4")
    (root / "bo").mkdir(exist_ok=True)
    (root / "bo" / "profile.json").write_text("{not json", encoding="utf-8")

    monkeypatch.setenv("JOBWRIGHT_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("JOBWRIGHT_CF_TEAM_DOMAIN", "t.cloudflareaccess.com")
    monkeypatch.setenv("JOBWRIGHT_CF_AUD", "aud")
    monkeypatch.setenv("JOBWRIGHT_HERMES_DRY_RUN", "1")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class _K:
        key = private.public_key()

    monkeypatch.setattr(auth_mod, "_jwks_client",
                        lambda team: type("J", (), {"get_signing_key_from_jwt": lambda s, t: _K()})())
    listing = "  abcdef1234 [active]\n    Name: jobwright-brief-ann\n"
    monkeypatch.setattr("jobwright.hermes_cron._run_hermes", lambda args: {"stdout": listing})
    monkeypatch.setattr("jobwright.whatsapp.bridge_status", lambda: "connected")
    monkeypatch.setattr("jobwright.whatsapp.list_chats", lambda **kw: {"chats": [
        {"target": ANN_GROUP, "name": "Ann - Job Applications", "type": "group"}]})
    session_mod.forget_initialized()
    from jobwright.web.app import app

    def headers(email):
        now = int(time.time())
        tok = jwt.encode({"email": email, "aud": "aud", "iss": "https://t.cloudflareaccess.com", "iat": now,
                          "exp": now + 600}, private, algorithm="RS256")
        return {"Cf-Access-Jwt-Assertion": tok}

    with TestClient(app) as client:
        yield client, headers, root


ROUTES = [
    ("get", "/api/admin/overview", None),
    ("patch", "/api/admin/users/ann", {"human_gate": False}),
    ("post", "/api/admin/users/ann/test-message", None),
    ("post", "/api/admin/users/ann/run", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_admin_only(console, method, path, body):
    client, h, _ = console
    kwargs = {"json": body} if body is not None else {}
    res = getattr(client, method)(path, headers=h("ann@example.com"), **kwargs)
    assert res.status_code == 403


def test_overview_shape_with_broken_profile(console):
    client, h, _ = console
    res = client.get("/api/admin/overview", headers=h("boss@example.com"))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["bridge"] == "connected"
    assert data["access"]["configured"] is False
    assert data["hermes"]["error"]
    assert data["settings"]["admins"] == ["boss@example.com"]
    rows = {u["user_id"]: u for u in data["users"]}
    ann, bo = rows["ann"], rows["bo"]
    assert ann["setup_complete"] is True
    assert ann["health"] == {"level": "ok", "lines": ["scored 5 jobs"]}
    assert ann["last_brief"]["notified"] == 8 and ann["last_brief"]["status"] == "ok"
    assert ann["whatsapp"] == {"target": ANN_GROUP, "name": "Ann - Job Applications", "type": "group"}
    assert (ann["hour"], ann["minute"], ann["schedule_label"]) == (6, 0, "Every day at 6:00 AM")
    assert ann["notify_threshold"] == 7 and ann["recommended_threshold"] == 6
    assert ann["counts"] == {"new_7d": 2, "sent_7d": 1, "applied_total": 1, "open": 2, "followups_due": 1}
    assert ann["cost_30d"] == {"tokens": 150, "cost_usd": 0.5}
    assert ann["brief_cron"] is True and ann["error"] is None
    assert bo["health"]["level"] == "fail" and "profile.json" in bo["health"]["lines"][0]
    assert bo["whatsapp"]["target"] is None and bo["brief_cron"] is False
    assert (bo["hour"], bo["minute"]) == (7, 30)


def test_patch_threshold_keeps_derived(console):
    from jobwright import config
    from jobwright.scoring.criteria import load_criteria

    client, h, root = console
    boss = h("boss@example.com")
    assert client.patch("/api/admin/users/ann", json={"notify_threshold": 11}, headers=boss).status_code == 400
    res = client.patch("/api/admin/users/ann", json={"notify_threshold": 6}, headers=boss)
    assert res.status_code == 200, res.text
    assert res.json()["user"]["notify_threshold"] == 6 and res.json()["cron"] is None
    profile = json.loads((root / "ann" / "profile.json").read_text(encoding="utf-8"))
    assert profile["match_criteria"] == {"notify_threshold": 6}
    assert profile["experience"]["target_role"] == "Product manager"
    criteria = load_criteria(profile)
    assert criteria.derived and criteria.notify_threshold == 6
    with config.user_context("ann"):
        assert config.PROFILE_PATH.stat().st_mode & 0o777 == 0o600


def test_patch_registry_fields_and_validation(console):
    from jobwright.users import get_user

    client, h, _ = console
    boss = h("boss@example.com")
    res = client.patch("/api/admin/users/ann", json={"weekly_summary": False, "followup_days": 14,
                                                     "human_gate": False, "brief_top_n": 0}, headers=boss)
    assert res.status_code == 200, res.text
    user = get_user("ann")
    assert (user.weekly_summary, user.followup_days, user.human_gate, user.brief_top_n) == (False, 14, False, 0)
    for bad in ({"followup_days": 0}, {"hour": 7}, {"hour": 25, "minute": 0}, {"brief_top_n": -1},
                {"schedule": "*/5 * * * *"}, {"name": " "}, {}):
        r = client.patch("/api/admin/users/ann", json=bad, headers=boss)
        assert r.status_code == 400, (bad, r.text)
        assert r.json()["detail"]
    assert client.patch("/api/admin/users/nobody", json={"human_gate": True}, headers=boss).status_code == 404


def test_patch_schedule_ensures_cron_only_for_set_up_users(console, monkeypatch):
    from jobwright.users import get_user

    client, h, _ = console
    boss = h("boss@example.com")
    calls = []
    monkeypatch.setattr("jobwright.hermes_cron.ensure_brief_cron",
                        lambda uid, schedule: calls.append((uid, schedule)) or {"ok": True, "cron_id": "x"})
    res = client.patch("/api/admin/users/ann", json={"hour": 8, "minute": 15}, headers=boss)
    assert res.status_code == 200, res.text
    assert calls == [("ann", "15 8 * * *")]
    assert res.json()["cron"] == {"ok": True, "cron_id": "x"}
    assert res.json()["user"]["schedule_label"] == "Every day at 8:15 AM"
    res = client.patch("/api/admin/users/bo", json={"hour": 9, "minute": 0}, headers=boss)
    assert res.status_code == 200, res.text
    assert calls == [("ann", "15 8 * * *")] and res.json()["cron"] is None
    assert get_user("bo").schedule == "0 9 * * *"
    client.patch("/api/admin/users/ann", json={"whatsapp_target": "120363400000000001@g.us"}, headers=boss)
    assert calls[-1] == ("ann", "15 8 * * *")
    assert get_user("ann").whatsapp_target == "whatsapp:120363400000000001@g.us"


def test_test_message(console, monkeypatch):
    client, h, _ = console
    boss = h("boss@example.com")
    sent = []
    monkeypatch.setattr("jobwright.whatsapp.send_test", lambda target, name="": sent.append((target, name)))
    res = client.post("/api/admin/users/bo/test-message", headers=boss)
    assert res.status_code == 400 and "no WhatsApp chat" in res.json()["detail"]
    res = client.post("/api/admin/users/ann/test-message", headers=boss)
    assert res.status_code == 200, res.text
    assert res.json() == {"sent": True, "target": ANN_GROUP}
    assert sent == [(ANN_GROUP, "Ann")]


def test_run_starts_in_user_context(console, monkeypatch):
    from jobwright import config
    from jobwright.pipeline import BRIEF_STAGES_HUMAN_GATED
    from jobwright.run_registry import load_registry
    from jobwright.web.routers import runs as runs_mod

    client, h, root = console
    seen = []

    def fake_cmd(args, user_id):
        seen.append((list(args), user_id, config.get_active_user_id()))
        return [sys.executable, "-c", "pass"]

    monkeypatch.setattr(runs_mod, "_jobwright_cmd", fake_cmd)
    res = client.post("/api/admin/users/ann/run", headers=h("boss@example.com"))
    assert res.status_code == 200, res.text
    handle = res.json()
    try:
        assert seen and seen[0][1] == "ann" and seen[0][2] == "ann" and seen[0][0][0] == "run"
        assert handle["user"] == "ann" and handle["kind"] == "pipeline"
        assert handle["stages"] == list(BRIEF_STAGES_HUMAN_GATED)
        assert handle["log_path"].startswith(str((root / "ann").resolve()))
        with config.user_context("ann"):
            assert handle["run_id"] in {e["run_id"] for e in load_registry()}
        with config.user_context("bo"):
            assert handle["run_id"] not in {e["run_id"] for e in load_registry()}
    finally:
        info = runs_mod._runs.pop(handle["run_id"], None)
        if info:
            info["proc"].wait(timeout=10)
