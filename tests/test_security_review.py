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


# --- M1: eval / rescore are admin-only --------------------------------------


@pytest.mark.parametrize("path", ["/api/quality/eval", "/api/quality/rescore"])
def test_quality_runs_are_admin_only(api_env, monkeypatch, path):
    client, h, _ = api_env
    spawned = []
    monkeypatch.setattr("jobwright.web.routers.runs.spawn_logged_run",
                        lambda **kw: spawned.append(kw) or {"run_id": "r1"})
    uid = _onboard(client, h, "eve@example.com", "Eve")
    client.cookies.set("jobwright_user", uid)
    assert client.post(path, headers=h("eve@example.com")).status_code == 403
    assert spawned == []
    res = client.post(path, headers=h("boss@example.com"))
    assert res.status_code == 200, res.text
    assert spawned and spawned[0]["user_id"] == uid


# --- M2 / L4: bulk Undo restores exactly what the bulk action changed --------


def _bulk_add(slug: str, stage: str = "backlog") -> str:
    from jobwright.database import get_connection, insert_manual_job, job_id_for_url

    url = f"https://example.com/undo-{slug}"
    insert_manual_job(url, title=f"Role {slug}", company="ExampleCo", funnel_stage=stage)
    conn = get_connection()
    conn.execute("UPDATE jobs SET fit_score = 6, board_updated_by = 'agent' WHERE url = ?", (url,))
    conn.commit()
    return job_id_for_url(url)


def _job_row(job_id: str):
    from jobwright.database import get_connection

    return get_connection().execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()


def _verdicts(job_id: str) -> list[str]:
    from jobwright.database import get_connection

    rows = get_connection().execute("SELECT verdict FROM score_labels WHERE job_id = ? ORDER BY id", (job_id,))
    return [r[0] for r in rows]


def test_bulk_undo_only_clears_the_label_it_was_given(api_client):
    from jobwright.database import get_connection
    from jobwright.labels import record_label

    a = _bulk_add("mine")
    b = _bulk_add("other")
    res = api_client.post("/api/jobs/bulk", json={"job_ids": [a, b], "action": "close", "reasons": ["Pay"]}).json()
    ids = {r["job_id"]: r["label_id"] for r in res["results"]}
    assert all(isinstance(v, int) for v in ids.values())
    # Someone else records a newer dismiss on b before the Undo lands.
    url_b = _job_row(b)["url"]
    record_label(url_b, 2, rationale="later", source="dismiss", conn=get_connection())
    undo = api_client.post(
        "/api/jobs/bulk",
        json={"job_ids": [a, b], "action": "move", "stage": "backlog",
              "restore": {a: {"label_id": ids[a]}, b: {"label_id": ids[b]}}},
    ).json()
    cleared = {r["job_id"]: r["label_cleared"] for r in undo["results"]}
    assert cleared == {a: True, b: False}
    assert _verdicts(a) == ["not_relevant", "cleared"]
    assert _verdicts(b) == ["not_relevant", "not_relevant"]
    # A label id that is not this job's latest is never cleared (old clients sent no ids).
    c = _bulk_add("plain")
    api_client.post("/api/jobs/bulk", json={"job_ids": [c], "action": "close", "reasons": ["x"]})
    out = api_client.post("/api/jobs/bulk", json={"job_ids": [c], "action": "move", "stage": "backlog",
                                                   "restore": {c: {"label_id": ids[a]}}}).json()
    assert out["results"][0]["label_cleared"] is False


def test_bulk_close_undo_keeps_agent_apply_flag(api_client):
    from jobwright.database import get_connection

    jid = _bulk_add("agent", stage="applied")
    conn = get_connection()
    conn.execute("UPDATE jobs SET applied_at = '2026-10-01T00:00:00+00:00', applied_manually = 0 WHERE job_id = ?",
                 (jid,))
    conn.commit()
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "close", "outcome": "rejected"})
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "move", "stage": "applied"})
    row = _job_row(jid)
    assert row["funnel_stage"] == "applied"
    assert row["applied_manually"] == 0 and row["applied_at"] == "2026-10-01T00:00:00+00:00"


def test_bulk_move_undo_restores_apply_stamps(api_client):
    from jobwright.database import get_connection

    jid = _bulk_add("stamps", stage="applied")
    conn = get_connection()
    conn.execute("UPDATE jobs SET applied_at = '2026-10-02T00:00:00+00:00', applied_manually = 0 WHERE job_id = ?",
                 (jid,))
    conn.commit()
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "move", "stage": "backlog"})
    assert _job_row(jid)["applied_at"] is None
    api_client.post("/api/jobs/bulk", json={
        "job_ids": [jid], "action": "move", "stage": "applied",
        "restore": {jid: {"applied_at": "2026-10-02T00:00:00+00:00", "applied_manually": False}},
    })
    row = _job_row(jid)
    assert row["applied_at"] == "2026-10-02T00:00:00+00:00" and row["applied_manually"] == 0


def test_bulk_reopen_clears_close_reason_and_undo_restores_it(api_client):
    jid = _bulk_add("reason")
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "close", "outcome": "rejected",
                                            "note": "Too far"})
    assert _job_row(jid)["close_reason"] == "Too far"
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "move", "stage": "backlog"})
    row = _job_row(jid)
    assert row["close_reason"] is None and row["outcome"] is None
    # Undo of the reopen: closed again with the reason it had, and no new label.
    before = _verdicts(jid)
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "close", "outcome": "rejected",
                                            "restore": {jid: {"close_reason": "Too far"}}})
    row = _job_row(jid)
    assert row["close_reason"] == "Too far" and row["outcome"] == "rejected"
    assert _verdicts(jid) == before


# --- M4 / M5: uploads validate before replacing, off the event loop ----------


def _pdf_bytes(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_upload_handlers_do_not_block_the_event_loop():
    import inspect

    from jobwright.web.routers import settings as settings_mod

    assert not inspect.iscoroutinefunction(settings_mod.put_resume_pdf)
    assert not inspect.iscoroutinefunction(settings_mod.put_cover_letter_example)


def test_corrupt_or_huge_resume_keeps_the_good_one(api_client, tmp_path):
    from jobwright.resume import MAX_PDF_BYTES

    resume_dir = tmp_path / "users" / "testdash" / "resume"
    good = _pdf_bytes("Example Person resume")
    res = api_client.put("/api/settings/resume.pdf", files={"file": ("base.pdf", good, "application/pdf")})
    assert res.status_code == 200, res.text
    md_before = (resume_dir / "base.md").read_text()
    assert "Example Person" in md_before

    res = api_client.put("/api/settings/resume.pdf",
                         files={"file": ("base.pdf", b"%PDF-1.4 garbage" * 10, "application/pdf")})
    assert res.status_code == 400 and "PDF" in res.json()["detail"]
    big = b"%PDF-1.4" + b"0" * MAX_PDF_BYTES
    res = api_client.put("/api/settings/resume.pdf", files={"file": ("base.pdf", big, "application/pdf")})
    assert res.status_code == 413 and "too big" in res.json()["detail"]

    assert (resume_dir / "base.pdf").read_bytes() == good
    assert (resume_dir / "base.md").read_text() == md_before
    assert sorted(p.name for p in resume_dir.iterdir()) == ["base.md", "base.pdf"]


def test_onboarding_draft_with_corrupt_resume_keeps_the_good_one(api_client, tmp_path):
    resume_dir = tmp_path / "users" / "testdash" / "resume"
    good = _pdf_bytes("Example Person resume")
    assert api_client.put("/api/settings/resume.pdf",
                          files={"file": ("base.pdf", good, "application/pdf")}).status_code == 200
    res = api_client.post("/api/onboarding/draft", files={"file": ("r.pdf", b"%PDF-1.4 nope", "application/pdf")})
    assert res.status_code == 400
    assert (resume_dir / "base.pdf").read_bytes() == good
    assert (resume_dir / "base.md").exists()


def test_corrupt_cover_letter_upload_leaves_nothing_behind(api_client, tmp_path):
    examples = tmp_path / "users" / "testdash" / "cover-letter" / "examples"
    res = api_client.put("/api/settings/cover-letters",
                         files={"file": ("Acme.pdf", b"%PDF-1.4 broken", "application/pdf")})
    assert res.status_code == 400
    assert not examples.exists() or list(examples.iterdir()) == []
    res = api_client.put("/api/settings/cover-letters",
                         files={"file": ("Acme.pdf", _pdf_bytes("Dear Acme team"), "application/pdf")})
    assert res.status_code == 200, res.text
    assert sorted(p.name for p in examples.iterdir()) == ["Acme.md", "Acme.pdf"]


# --- QA follow-ups: apply stamps survive Undo; reopen clears close reason;
#     an unreadable resume doesn't break Settings ----------------------------


def _set_applied(job_id: str, at: str, manual: int) -> None:
    from jobwright.database import get_connection

    conn = get_connection()
    conn.execute("UPDATE jobs SET applied_at = ?, applied_manually = ?, apply_status = 'applied' WHERE job_id = ?",
                 (at, manual, job_id))
    conn.commit()


def test_single_move_applied_and_back_keeps_original_stamps(api_client):
    jid = _bulk_add("drag", stage="applied")
    _set_applied(jid, "2026-09-01T00:00:00+00:00", 0)
    assert api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "backlog"}).status_code == 200
    row = _job_row(jid)
    assert row["applied_at"] is None and row["apply_status"] is None
    assert api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "applied"}).status_code == 200
    row = _job_row(jid)
    assert row["applied_at"] == "2026-09-01T00:00:00+00:00" and row["applied_manually"] == 0
    assert row["apply_status"] == "applied"


def test_bulk_undo_of_applied_to_backlog_keeps_original_date(api_client):
    jid = _bulk_add("bulkdrag", stage="applied")
    _set_applied(jid, "2026-09-02T00:00:00+00:00", 1)
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "move", "stage": "backlog"})
    # Undo exactly as an older client would send it (no restore payload).
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "move", "stage": "applied"})
    row = _job_row(jid)
    assert row["applied_at"] == "2026-09-02T00:00:00+00:00" and row["applied_manually"] == 1


def test_later_fresh_apply_gets_a_new_date(api_client):
    jid = _bulk_add("fresh", stage="applied")
    _set_applied(jid, "2026-09-03T00:00:00+00:00", 1)
    api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "backlog"})
    api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "prepare"})
    api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "applied"})
    assert _job_row(jid)["applied_at"] != "2026-09-03T00:00:00+00:00"


def test_reopen_clears_close_reason_so_later_close_is_not_stale(api_client):
    jid = _bulk_add("stale")
    api_client.post("/api/jobs/bulk", json={"job_ids": [jid], "action": "close", "reasons": ["Pay too low"]})
    assert _job_row(jid)["close_reason"] == "Pay too low"
    # Single-move reopen (drawer) and a later close without reasons.
    api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "backlog"})
    assert _job_row(jid)["close_reason"] is None
    api_client.post(f"/api/jobs/{jid}/move", json={"to_stage": "closed", "outcome": "rejected"})
    assert _job_row(jid)["close_reason"] is None


def test_zero_page_resume_does_not_break_settings(api_client, tmp_path):
    resume_dir = tmp_path / "users" / "testdash" / "resume"
    resume_dir.mkdir(parents=True, exist_ok=True)
    (resume_dir / "base.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    res = api_client.get("/api/settings")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["has_resume_pdf"] is True and body["resume_unreadable"] is True
    assert body["resume_markdown"] == ""
    assert api_client.get("/api/settings/materials").status_code == 200


# --- M6: users.yaml read-modify-write is locked ------------------------------


def test_concurrent_registry_writes_are_not_lost():
    import threading

    from jobwright import users as users_mod

    users_mod.add_user("base", name="Base")
    errors: list[BaseException] = []

    def add(i: int) -> None:
        try:
            users_mod.add_user(f"u{i:02d}", name=f"User {i}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def bump(field: str, n: int) -> None:
        try:
            for k in range(n):
                users_mod.update_user("base", **{field: f"{field}-{k}"})
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=add, args=(i,)) for i in range(16)]
    threads += [threading.Thread(target=bump, args=("name", 15)), threading.Thread(target=bump, args=("notes", 15))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == []
    ids = {u.user_id for u in users_mod.list_users()}
    assert {f"u{i:02d}" for i in range(16)} <= ids
    base = users_mod.get_user("base")
    assert base.name == "name-14" and base.notes == "notes-14"


def test_update_user_only_writes_changed_fields(monkeypatch):
    """A stale in-memory copy must never overwrite fields another writer changed."""
    from jobwright import users as users_mod

    users_mod.add_user("solo", name="Solo")
    real_get = users_mod.get_user
    stale = real_get("solo")
    users_mod.update_user("solo", notes="from another process")
    monkeypatch.setattr(users_mod, "get_user", lambda uid: stale if uid == "solo" else real_get(uid))
    users_mod.update_user("solo", name="Renamed")
    monkeypatch.setattr(users_mod, "get_user", real_get)
    fresh = users_mod.get_user("solo")
    assert fresh.name == "Renamed" and fresh.notes == "from another process"


def test_registry_lock_is_reentrant():
    from jobwright import users as users_mod

    with users_mod.registry_lock():
        users_mod.add_user("nested", name="Nested")
        users_mod.update_user("nested", notes="ok")
    assert users_mod.get_user("nested").notes == "ok"


# --- L1: the welcome is sent once even when two saves race ------------------


def test_concurrent_welcome_sends_once(tmp_path, monkeypatch):
    import threading
    import time
    from types import SimpleNamespace

    import jobwright.welcome as welcome

    user = SimpleNamespace(user_id="w", name="Alex Rivera", whatsapp_target="whatsapp:120363999999999901@g.us",
                           schedule="0 7 * * *")
    monkeypatch.setattr("jobwright.users.get_user", lambda uid: user)
    monkeypatch.setattr(welcome, "_marker_path", lambda uid: tmp_path / "logs" / "welcome_sent.json")
    monkeypatch.setattr("jobwright.hermes_cron.hermes_dry_run", lambda: False)
    monkeypatch.setattr("jobwright.ops.ops_target", lambda: "")
    sent = []

    def slow_send(msg, target):
        time.sleep(0.05)
        sent.append(target)

    monkeypatch.setattr("jobwright.notify.send_via_hermes", slow_send)
    threads = [threading.Thread(target=welcome.send_welcome, args=("w",)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert sent == [user.whatsapp_target]
    assert (tmp_path / "logs" / "welcome_sent.json").exists()


# --- L5: a failed usage flush is all-or-nothing ------------------------------


def test_partial_usage_flush_failure_does_not_double_count(tmp_path):
    from jobwright import llm
    from jobwright.database import close_connection, init_db

    db = tmp_path / "usage.db"
    close_connection(db)
    conn = init_db(db)
    llm.usage_snapshot(reset=True, user_id=None)
    with llm.llm_purpose("score"):
        llm.record_usage("fireworks", "m", {"prompt_tokens": 10, "completion_tokens": 1})
    with llm.llm_purpose("tailor"):
        llm.record_usage("fireworks", "m", {"prompt_tokens": 20, "completion_tokens": 2})

    class FailSecondInsert:
        def __init__(self, inner):
            self.inner, self.inserts = inner, 0

        def execute(self, sql, *args):
            if sql.lstrip().upper().startswith("INSERT"):
                self.inserts += 1
                if self.inserts == 2:
                    raise RuntimeError("disk full")
            return self.inner.execute(sql, *args)

        def commit(self):
            return self.inner.commit()

        def rollback(self):
            return self.inner.rollback()

        @property
        def in_transaction(self):
            return self.inner.in_transaction

    with pytest.raises(RuntimeError):
        llm.flush_usage(FailSecondInsert(conn), "r1", user_id=None)
    assert not conn.in_transaction
    assert llm.flush_usage(conn, "r1", user_id=None) == 2
    rows = conn.execute("SELECT purpose, SUM(prompt_tokens) FROM llm_usage GROUP BY purpose ORDER BY purpose")
    assert [tuple(r) for r in rows] == [("score", 10), ("tailor", 20)]


# --- M3: SIGTERM still runs finally blocks and the atexit usage flush --------


def test_sigterm_runs_finally_and_atexit(tmp_path):
    import os
    import subprocess
    import sys

    script = tmp_path / "victim.py"
    script.write_text(
        "import atexit, os, signal, sys, time\n"
        "from jobwright import cli\n"
        "cli._register_usage_flush()\n"
        "atexit.register(lambda: open(sys.argv[1], 'w').write('flushed'))\n"
        "try:\n"
        "    os.kill(os.getpid(), signal.SIGTERM)\n"
        "    time.sleep(10)\n"
        "finally:\n"
        "    open(sys.argv[2], 'w').write('finally')\n",
        encoding="utf-8",
    )
    env = {**os.environ, "JOBWRIGHT_DIR": str(tmp_path / "app"), "JOBWRIGHT_HERMES_DRY_RUN": "1"}
    proc = subprocess.run([sys.executable, str(script), str(tmp_path / "atexit"), str(tmp_path / "finally")],
                          env=env, timeout=60, capture_output=True)
    assert proc.returncode == 143, proc.stderr.decode()
    assert (tmp_path / "finally").read_text() == "finally"
    assert (tmp_path / "atexit").read_text() == "flushed"


# --- L6: the board does not load job descriptions ----------------------------


def test_board_skips_descriptions_but_keeps_sponsorship_fallback(api_client, monkeypatch):
    from jobwright.database import get_connection, insert_manual_job, job_id_for_url
    from jobwright.web.routers import board as board_mod
    from jobwright.web.routers.board import _row_to_card

    stored = "https://example.com/board-stored"
    derived = "https://example.com/board-derived"
    insert_manual_job(stored, title="Stored", description="We do sponsor visas. " + "x" * 5000)
    insert_manual_job(derived, title="Derived", description="Sorry, no visa sponsorship for this role.")
    conn = get_connection()
    conn.execute("UPDATE jobs SET sponsorship_status = 'required' WHERE url = ?", (stored,))
    conn.execute("UPDATE jobs SET sponsorship_status = NULL WHERE url = ?", (derived,))
    conn.commit()

    statements: list[str] = []
    tracing = {"on": True}

    def tracing_connection(*args, **kwargs):
        c = get_connection(*args, **kwargs)  # the handler thread's own connection
        c.set_trace_callback(lambda sql: statements.append(sql) if tracing["on"] else None)
        return c

    monkeypatch.setattr(board_mod, "get_connection", tracing_connection)
    board = api_client.get("/api/board")
    tracing["on"] = False
    assert statements
    assert board.status_code == 200
    cards = {c["job_id"]: c for col in board.json()["columns"].values() for c in col}
    assert cards[job_id_for_url(stored)]["sponsorship_status"] == "required"
    assert cards[job_id_for_url(derived)]["sponsorship_status"] == "not_required"
    # Same card as building it from the full row.
    full = _row_to_card(conn.execute("SELECT * FROM jobs WHERE url = ?", (stored,)).fetchone())
    board_card = dict(cards[job_id_for_url(stored)])
    for key in ("followup_due", "applied_days_ago", "followup_due_at"):
        board_card.pop(key, None)
        full.pop(key, None)
    assert board_card == full
    board_selects = [s for s in statements if "FROM jobs" in s and "funnel_stage" in s and "SELECT *" in s]
    assert board_selects == []
