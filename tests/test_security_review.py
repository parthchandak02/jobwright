"""Regression tests for the security / data-integrity review (H1-H3, M1-M6, L1-L7)."""

from __future__ import annotations

import json

import pytest

from jobwright import config

pytest.importorskip("fastapi")

import test_web_board as _board  # noqa: E402
import test_web_multiuser as _multi  # noqa: E402

api_client = _board.api_client
api_env = _multi.api_env


# --- H1: profile paths cannot reach another profile's folder -----------------


def _onboard(client, h, email: str, name: str) -> str:
    res = client.post("/api/onboarding/profile", json={"name": name}, headers=h(email))
    assert res.status_code == 200, res.text
    return res.json()["user_id"]


def test_onboarding_confirm_drops_path_and_unknown_profile_keys(api_env):
    client, h, root = api_env
    victim = _onboard(client, h, "victim@example.com", "Vic")
    attacker = _onboard(client, h, "attacker@example.com", "Ana")
    victim_dir = root / victim / "cover-letter" / "examples"
    draft = {
        "profile": {
            "personal": {"full_name": "Ana Example", "password": "x"},
            "experience": {"target_role": "Analyst"},
            "cover_letter_examples_dir": str(victim_dir),
            "cover_letter_template": "../" + victim + "/cover-letter/template.pdf",
            "match_criteria": {"summary": "sneaky"},
            "password": "hunter2",
        },
        "searches": {},
    }
    client.cookies.set("jobwright_user", attacker)
    res = client.post("/api/onboarding/confirm", json=draft, headers=h("attacker@example.com"))
    assert res.status_code == 200, res.text
    saved = json.loads((root / attacker / "profile.json").read_text())
    assert "cover_letter_examples_dir" not in saved
    assert "cover_letter_template" not in saved
    assert "password" not in saved and "password" not in saved["personal"]
    assert "match_criteria" not in saved
    assert saved["personal"]["full_name"] == "Ana Example"
    assert saved["experience"]["target_role"] == "Analyst"


def test_profile_paths_confined_to_active_user(tmp_path, monkeypatch):
    app_dir = tmp_path / "users" / "ana"
    other = tmp_path / "users" / "vic" / "cover-letter" / "examples"
    other.mkdir(parents=True)
    (other / "letter.pdf").write_bytes(b"%PDF-1.4 not really")
    app_dir.mkdir(parents=True)
    monkeypatch.setenv("JOBWRIGHT_DIR", str(app_dir))
    config.set_app_dir(app_dir)

    with pytest.raises(ValueError):
        config.user_relative_path(str(other))
    with pytest.raises(ValueError):
        config.user_relative_path("../vic/cover-letter/examples")
    inside = config.user_relative_path("cover-letter/examples")
    assert inside == (app_dir / "cover-letter" / "examples").resolve()
    assert config.user_relative_path(str(app_dir / "x")) == (app_dir / "x").resolve()

    profile = {"cover_letter_examples_dir": str(other), "cover_letter_template": "../vic/cover-letter/examples/letter.pdf"}
    assert config.cover_letter_examples_dir(profile) != other
    assert config.cover_letter_template_path(profile).parent != other
    _template, examples = config.load_cover_letter_materials(profile)
    assert examples == []
    # Nothing was cached into the other profile's folder.
    assert not (other / "letter.md").exists()


# --- H2: a failed write never leaves the cached connection holding the lock ---


def test_duplicate_manual_job_releases_write_lock(api_client):
    import sqlite3

    from jobwright.database import get_connection, insert_manual_job

    url = "https://example.com/dup-lock"
    insert_manual_job(url, title="Role")
    conn = get_connection()
    with pytest.raises(ValueError):
        insert_manual_job(url, title="Again")
    assert not conn.in_transaction
    # A second connection (another process/thread) can write right away.
    other = sqlite3.connect(str(config.DB_PATH), timeout=0.2)
    other.execute("UPDATE jobs SET notes = 'x' WHERE url = ?", (url,))
    other.commit()
    other.close()


def test_request_guard_rolls_back_leftover_transaction(api_client, monkeypatch):
    """Any sync handler that leaves DML uncommitted is rolled back in its own thread."""
    import sqlite3

    from jobwright.web.routers import jobs as jobs_router

    seen = {}

    def leaky(*args, **kwargs):
        from jobwright.database import get_connection

        conn = get_connection()
        conn.execute("UPDATE jobs SET notes = 'leaked'")
        seen["conn"] = conn
        raise ValueError("boom")

    monkeypatch.setattr(jobs_router, "insert_manual_job", leaky)
    res = api_client.post("/api/jobs", json={"url": "https://example.com/leaky"})
    assert res.status_code == 400
    other = sqlite3.connect(str(config.DB_PATH), timeout=0.2)
    other.execute("UPDATE jobs SET notes = 'ok'")
    other.commit()
    assert other.execute("SELECT COUNT(*) FROM jobs WHERE notes = 'leaked'").fetchone()[0] == 0
    other.close()


def test_rollback_open_transactions_only_touches_open_ones(tmp_path):
    from jobwright.database import get_connection, rollback_open_transactions

    conn = get_connection(tmp_path / "a.db")
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    assert rollback_open_transactions() == 0
    conn.execute("INSERT INTO t VALUES (1)")
    assert rollback_open_transactions() == 1
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


# --- H3: deleting a profile drops cached connections + init marks ------------


def test_invalidate_connections_reaches_other_threads(tmp_path):
    import threading

    from jobwright.database import get_connection, invalidate_connections

    db = tmp_path / "x.db"
    got: list = []
    go = threading.Event()
    done = threading.Event()

    def worker():
        got.append(get_connection(db))
        go.wait(5)
        got.append(get_connection(db))
        done.set()

    t = threading.Thread(target=worker)
    t.start()
    while not got:
        pass
    invalidate_connections(db)
    go.set()
    done.wait(5)
    t.join(5)
    assert got[0] is not got[1]


def test_deleted_profile_data_not_served_to_recreated_profile(api_env):
    client, h, root = api_env
    boss = h("boss@example.com")
    uid = client.post("/api/onboarding/profile", json={"name": "Cara", "emails": ["cara@example.com"]},
                      headers=boss).json()["user_id"]
    cara = h("cara@example.com")
    client.cookies.set("jobwright_user", uid)
    assert client.post("/api/jobs", json={"url": "https://example.com/old-secret", "title": "Old"},
                       headers=cara).status_code == 200
    assert client.get("/api/board", headers=cara).json()["total"] == 1
    client.cookies.clear()
    res = client.delete(f"/api/admin/users/{uid}", params={"delete_data": True}, headers=boss)
    assert res.status_code == 200, res.text
    uid2 = client.post("/api/onboarding/profile", json={"name": "Cara", "emails": ["cara@example.com"]},
                       headers=boss).json()["user_id"]
    assert uid2 == uid  # folder is gone, so the id is free again
    client.cookies.set("jobwright_user", uid2)
    board = client.get("/api/board", headers=cara)
    assert board.status_code == 200, board.text
    assert board.json()["total"] == 0


def test_removed_profile_id_with_leftover_data_is_not_reused(api_env):
    client, h, root = api_env
    boss = h("boss@example.com")
    uid = client.post("/api/onboarding/profile", json={"name": "Dee", "emails": ["dee@example.com"]},
                      headers=boss).json()["user_id"]
    (root / uid / "profile.json").write_text("{}", encoding="utf-8")
    assert client.delete(f"/api/admin/users/{uid}", headers=boss).status_code == 200
    again = client.post("/api/onboarding/profile", json={"name": "Dee", "emails": ["dee@example.com"]},
                        headers=boss).json()["user_id"]
    assert again != uid
    res = client.post("/api/onboarding/profile", json={"name": "Dee", "user_id": uid}, headers=h("new@example.com"))
    assert res.status_code == 400


# --- L7: manual job links must be http(s) -----------------------------------


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "file:///etc/passwd", "example.com/x", "https://"])
def test_manual_job_rejects_non_http_urls(api_client, bad):
    assert api_client.post("/api/jobs", json={"url": bad}).status_code == 400
    assert api_client.post(
        "/api/jobs", json={"url": "https://example.com/ok-" + str(len(bad)), "application_url": bad}
    ).status_code == 400


def test_manual_job_accepts_http_url(api_client):
    res = api_client.post("/api/jobs", json={"url": "https://example.com/fine", "title": "Fine"})
    assert res.status_code == 200, res.text
