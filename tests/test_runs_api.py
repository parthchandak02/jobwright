"""Tests for the observable/controllable run API (runs.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from jobwright.database import close_connection, init_db


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("JOBWRIGHT_DASHBOARD_USER", "testdash")
    monkeypatch.setenv("JOBWRIGHT_USERS_ROOT", str(tmp_path / "users"))
    users_root = tmp_path / "users"
    users_root.mkdir()
    (users_root / "users.yaml").write_text(
        "users:\n  - user_id: testdash\n    name: Test\n    apply_enabled: false\n",
        encoding="utf-8",
    )
    data_dir = users_root / "testdash"
    data_dir.mkdir()
    log_dir = data_dir / "logs"
    monkeypatch.setattr("jobwright.config.APP_DIR", data_dir)
    monkeypatch.setattr("jobwright.config.DB_PATH", data_dir / "jobwright.db")
    monkeypatch.setattr("jobwright.config.LOG_DIR", log_dir)

    import jobwright.users as users_mod

    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")

    # Launch a harmless long-lived process instead of the real pipeline so the
    # start/stop lifecycle is fast and hermetic.
    def _fake_cmd(args, user_id):  # noqa: ANN001, ANN202
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    monkeypatch.setattr("jobwright.web.routers.runs._jobwright_cmd", _fake_cmd)

    close_connection(data_dir / "jobwright.db")
    init_db(data_dir / "jobwright.db")

    from jobwright.web.app import app
    from jobwright.web.routers import runs as runs_mod

    with TestClient(app) as client:

        import jobwright.config as _cfg


        _cfg.set_app_dir(data_dir)
        yield client

    # Teardown: never leave background or unreaped processes running.
    for info in list(runs_mod._runs.values()):
        proc = info.get("proc")
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
    runs_mod._runs.clear()
    close_connection(data_dir / "jobwright.db")


def test_run_lifecycle(api_client):
    # Registry-merge path must not crash when web_runs.json is absent.
    res = api_client.get("/api/runs")
    assert res.status_code == 200
    assert res.json()["runs"] == []

    # Start a run.
    res = api_client.post("/api/run", json={"stages": ["score"]})
    assert res.status_code == 200
    body = res.json()
    run_id = body["run_id"]
    assert body["pid"]
    assert body["user"] == "testdash"
    assert body["log_path"]
    assert Path(body["log_path"]).exists()

    # It shows up in the list, newest first.
    res = api_client.get("/api/runs")
    assert res.status_code == 200
    runs = res.json()["runs"]
    assert any(r["run_id"] == run_id for r in runs)
    listed = next(r for r in runs if r["run_id"] == run_id)
    assert listed["pid"] == body["pid"]
    assert listed["running"] is True
    assert listed["user"] == "testdash"

    # Single-run status includes pid.
    res = api_client.get(f"/api/runs/{run_id}")
    assert res.status_code == 200
    status = res.json()
    assert status["pid"] == body["pid"]
    assert status["running"] is True

    # Stop it.
    res = api_client.post(f"/api/runs/{run_id}/stop")
    assert res.status_code == 200
    assert res.json()["stopped"] is True

    # Unknown run -> 404.
    assert api_client.get("/api/runs/deadbeef").status_code == 404
    assert api_client.post("/api/runs/deadbeef/stop").status_code == 404


def test_registry_persists_across_memory_clear(api_client):
    res = api_client.post("/api/run", json={"stages": ["score"]})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    from jobwright.web.routers import runs as runs_mod

    # Simulate an API restart: drop in-memory state, keep the on-disk registry.
    for info in list(runs_mod._runs.values()):
        proc = info.get("proc")
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)  # reap it, or the handle warns when it is collected
    runs_mod._runs.clear()

    res = api_client.get("/api/runs")
    assert res.status_code == 200
    assert any(r["run_id"] == run_id for r in res.json()["runs"])

    res = api_client.get(f"/api/runs/{run_id}")
    assert res.status_code == 200
    assert res.json()["run_id"] == run_id


def test_stop_after_memory_clear_kills_process(api_client):
    """uvicorn --reload drops in-memory Popen handles; Stop must still kill via the registry PID."""
    import os
    import time

    from jobwright.web.routers import runs as runs_mod

    res = api_client.post("/api/run", json={"stages": ["score"]})
    assert res.status_code == 200
    body = res.json()
    run_id = body["run_id"]
    pid = body["pid"]
    os.kill(pid, 0)  # still alive

    # Simulate reload: forget Popen, do not kill the child (it outlives the worker).
    # The handles stay here only so the test can reap what Stop kills.
    spawned = [info["proc"] for info in runs_mod._runs.values() if info.get("proc") is not None]
    runs_mod._runs.clear()

    res = api_client.post(f"/api/runs/{run_id}/stop")
    assert res.status_code == 200
    assert res.json()["stopped"] is True

    still_alive = True
    for _ in range(20):
        try:
            os.kill(pid, 0)
            os.waitpid(pid, os.WNOHANG)
        except OSError:
            still_alive = False
            break
        except ChildProcessError:
            still_alive = False
            break
        time.sleep(0.05)
    assert still_alive is False
    for proc in spawned:
        proc.wait(timeout=5)


def test_stop_kills_spawned_children(api_client, tmp_path, monkeypatch):
    """JobSpy worker threads/children must die with Stop, not just the parent PID."""
    import os
    import time

    marker = tmp_path / "child.pid"
    script = (
        "import pathlib, subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(marker)!r}).write_text(str(p.pid))\n"
        "time.sleep(60)\n"
    )

    monkeypatch.setattr(
        "jobwright.web.routers.runs._jobwright_cmd",
        lambda args, user_id: [sys.executable, "-c", script],
    )

    res = api_client.post("/api/run", json={"stages": ["score"]})
    assert res.status_code == 200
    parent = res.json()["pid"]
    run_id = res.json()["run_id"]

    child = None
    for _ in range(50):
        if marker.exists() and marker.read_text().strip().isdigit():
            child = int(marker.read_text().strip())
            break
        time.sleep(0.05)
    assert child is not None
    os.kill(child, 0)

    res = api_client.post(f"/api/runs/{run_id}/stop")
    assert res.status_code == 200
    assert res.json()["stopped"] is True

    time.sleep(0.2)
    for pid in (parent, child):
        dead = False
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except OSError:
                dead = True
                break
            time.sleep(0.05)
        assert dead, f"pid {pid} still alive after stop"


def test_pid_is_jobwright_fails_safe_when_ps_fails(monkeypatch):
    import subprocess

    from jobwright.web.routers import runs as runs_mod

    def boom(*a, **k):
        raise OSError("ps missing")

    monkeypatch.setattr(runs_mod.subprocess, "run", boom)
    assert runs_mod._pid_is_jobwright(12345) is False

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("ps", 3)

    monkeypatch.setattr(runs_mod.subprocess, "run", timeout)
    assert runs_mod._pid_is_jobwright(12345) is False

    empty = subprocess.CompletedProcess(["ps"], 1, stdout="", stderr="")
    monkeypatch.setattr(runs_mod.subprocess, "run", lambda *a, **k: empty)
    assert runs_mod._pid_is_jobwright(12345) is False


def test_pid_is_jobwright_rejects_reused_pid(monkeypatch):
    import subprocess
    from datetime import datetime, timedelta

    from jobwright.web.routers import runs as runs_mod

    started = datetime.now().astimezone().replace(microsecond=0)

    def fake_ps(start: datetime, command: str):
        line = f"{start.strftime('%a %b %d %H:%M:%S %Y')} {command}\n"
        return lambda *a, **k: subprocess.CompletedProcess(["ps"], 0, stdout=line, stderr="")

    recorded = started.isoformat()
    cmd = "/usr/bin/python3 -m jobwright --user user1 run score"
    monkeypatch.setattr(runs_mod.subprocess, "run", fake_ps(started, cmd))
    assert runs_mod._pid_is_jobwright(12345, recorded) is True
    assert runs_mod._pid_is_jobwright(12345) is True

    # Same PID, but the process began well after the run was recorded: reused.
    monkeypatch.setattr(runs_mod.subprocess, "run", fake_ps(started + timedelta(minutes=5), cmd))
    assert runs_mod._pid_is_jobwright(12345, recorded) is False

    # A non-jobwright process holding the PID is never ours.
    monkeypatch.setattr(runs_mod.subprocess, "run", fake_ps(started, "/usr/sbin/sshd -D"))
    assert runs_mod._pid_is_jobwright(12345, recorded) is False

    # With a recorded command, the live arguments must match it.
    monkeypatch.setattr(runs_mod.subprocess, "run", fake_ps(started, cmd))
    recorded_cmd = ["/other/python", "-m", "jobwright", "--user", "user1", "run", "score"]
    assert runs_mod._pid_is_jobwright(12345, recorded, recorded_cmd) is True
    other_user = ["/other/python", "-m", "jobwright", "--user", "user2", "run", "score"]
    assert runs_mod._pid_is_jobwright(12345, recorded, other_user) is False


def test_pid_is_jobwright_real_process():
    import os

    from jobwright.web.routers import runs as runs_mod

    # The test runner itself is not a jobwright process (unless the path says so).
    info = runs_mod._ps_start_and_command(os.getpid())
    assert info is not None and info[0] is not None


def test_start_run_validates_stages_and_clamps_workers(api_client, monkeypatch):
    bad = api_client.post("/api/run", json={"stages": ["nonexistent_stage"]})
    assert bad.status_code == 400
    assert "No valid stages" in bad.json()["detail"]

    seen_args: list[list[str]] = []

    def _capture(args, user_id):
        seen_args.append(args)
        return [sys.executable, "-c", "pass"]

    monkeypatch.setattr("jobwright.web.routers.runs._jobwright_cmd", _capture)
    res = api_client.post("/api/run", json={"stages": ["score", "bogus"], "min_score": 9, "workers": 12})
    assert res.status_code == 200
    assert res.json()["stages"] == ["score"]
    assert seen_args[0][:6] == ["run", "score", "-w", "4", "--min-score", "9"]

    default_res = api_client.post("/api/run", json={"stages": [], "workers": 0})
    assert default_res.status_code == 200
    assert len(default_res.json()["stages"]) > 0
    assert seen_args[1][:4] == ["run", "-w", "1", "--min-score"]


def test_stream_run_sse_streams_log_and_done_event(api_client, monkeypatch):
    assert api_client.get("/api/stream/unknown").status_code == 404

    monkeypatch.setattr(
        "jobwright.web.routers.runs._jobwright_cmd",
        lambda args, user_id: [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('alpha line\\r\\nbeta tail'); sys.stdout.flush()",
        ],
    )
    started = api_client.post("/api/run", json={"stages": ["score"]})
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    res = api_client.get(f"/api/stream/{run_id}")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    text = res.text
    assert "data: alpha line\n\n" in text
    assert "data: beta tail\n\n" in text
    assert "data: [done RC=0]\n\n" in text
    assert "event: done\ndata: {}\n\n" in text


def test_stream_run_falls_back_to_registry_after_memory_clear(api_client, monkeypatch):
    from jobwright.run_registry import finish_run
    from jobwright.web.routers import runs as runs_mod

    monkeypatch.setattr(
        "jobwright.web.routers.runs._jobwright_cmd",
        lambda args, user_id: [sys.executable, "-c", "print('persisted line')"],
    )
    started = api_client.post("/api/run", json={"stages": ["score"]})
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    proc = runs_mod._runs[run_id]["proc"]
    proc.wait(timeout=5)
    runs_mod._runs.clear()
    finish_run(run_id, 0)

    res = api_client.get(f"/api/stream/{run_id}")
    assert res.status_code == 200
    assert "data: persisted line\n\n" in res.text
    assert "data: [done RC=0]\n\n" in res.text


def test_apply_endpoint_safety_gates_and_flags(api_client, monkeypatch):
    import jobwright.users as users_mod

    captured: list[list[str]] = []

    def _capture(args, user_id):
        captured.append(args)
        return [sys.executable, "-c", "pass"]

    monkeypatch.setattr("jobwright.web.routers.runs._jobwright_cmd", _capture)

    # Dry-run succeeds even with apply_enabled=false and forwards url + limit.
    dry = api_client.post(
        "/api/apply",
        json={"dry_run": True, "limit": 3, "url": "https://example.com/jobs/1"},
    )
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True
    assert dry.json()["kind"] == "apply"
    assert captured[-1] == ["apply", "-w", "1", "--limit", "3", "--dry-run", "--url", "https://example.com/jobs/1"]

    # Live apply refuses without confirm=true, without apply_enabled, and when apply_via != 'server'.
    no_confirm = api_client.post("/api/apply", json={"dry_run": False, "confirm": False})
    assert no_confirm.status_code == 400
    assert "confirm=true" in no_confirm.json()["detail"]

    disabled = api_client.post("/api/apply", json={"dry_run": False, "confirm": True})
    assert disabled.status_code == 403
    assert "apply_enabled is false" in disabled.json()["detail"]

    users_mod.update_user("testdash", apply_enabled=True, apply_via="connector")
    wrong_via = api_client.post("/api/apply", json={"dry_run": False, "confirm": True})
    assert wrong_via.status_code == 403
    assert "apply_via: connector" in wrong_via.json()["detail"]

    # Authorized server-runner live apply spawns with --live.
    users_mod.update_user("testdash", apply_via="server")
    live = api_client.post(
        "/api/apply",
        json={"dry_run": False, "confirm": True, "url": "https://example.com/jobs/2"},
    )
    assert live.status_code == 200
    assert live.json()["dry_run"] is False
    assert captured[-1] == ["apply", "-w", "1", "--limit", "1", "--live", "--url", "https://example.com/jobs/2"]


def test_mark_applied_endpoint_updates_card_and_404s_missing(api_client):
    # Pre-import on main thread so module-level signal.signal in launcher does not run inside worker thread.
    import jobwright.apply.launcher  # noqa: F401
    from jobwright.database import get_connection, job_id_for_url

    assert api_client.post("/api/jobs/missing-id/applied").status_code == 404

    url = "https://example.com/jobs/mark-me"
    jid = job_id_for_url(url)
    conn = get_connection()
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, job_id, funnel_stage, discovered_at) "
        "VALUES (?, 'Data Analyst', 'Example Co', 'greenhouse', ?, 'review', datetime('now'))",
        (url, jid),
    )
    conn.commit()

    res = api_client.post(f"/api/jobs/{jid}/applied")
    assert res.status_code == 200
    card = res.json()
    assert card["funnel_stage"] == "applied"
    assert card["apply_status"] == "applied"
    assert card["applied_at"]


def test_cross_user_run_isolation_blocks_stop_and_stream(api_client, tmp_path):
    import jobwright.users as users_mod
    from jobwright import config

    users_mod.add_user("other", name="Other Person")
    started = api_client.post("/api/run", json={"stages": ["score"]})
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    try:
        api_client.cookies.set("jobwright_user", "other")
        assert api_client.get(f"/api/runs/{run_id}").status_code == 404
        assert api_client.post(f"/api/runs/{run_id}/stop").status_code == 404
        assert api_client.get(f"/api/stream/{run_id}").status_code == 404
    finally:
        api_client.cookies.delete("jobwright_user")
        close_connection(tmp_path / "users" / "other" / "jobwright.db")
        config.set_app_dir(tmp_path / "users" / "testdash")
