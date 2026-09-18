"""Tests for the D3 Jev fast-path hybrid (canned answers, no network)."""

from jobwright.scoring import fastpath


def _answers(**overrides):
    base = {
        "excl_fundraising": {"probabilities": {"true": 0.1}},
        "excl_license": {"probabilities": {"true": 0.05}},
        "role_function_match": {"score": 4, "confidence": 0.8},
        "mission_sector_alignment": {"score": 4, "confidence": 0.7},
        "seniority_fit": {"score": 3, "confidence": 0.6},
    }
    base.update(overrides)
    return base


# --- Composite math ---------------------------------------------------------

def test_composite_math():
    score, conf, gated, _ = fastpath._composite_from_answers(_answers())
    # 1 + 9*(0.5*1 + 0.3*1 + 0.2*0.75) = 1 + 9*0.95 = 9.55 -> 10
    assert score == 10
    assert conf == 0.7  # mean(0.8, 0.7, 0.6)
    assert gated is None


def test_composite_midrange():
    answers = _answers(
        role_function_match={"score": 3, "confidence": 0.6},
        mission_sector_alignment={"score": 3, "confidence": 0.6},
        seniority_fit={"score": 3, "confidence": 0.6},
    )
    score, _conf, gated, _ = fastpath._composite_from_answers(answers)
    # 1 + 9*(1.0 * 0.75) = 7.75 -> 8
    assert score == 8
    assert gated is None


def test_gate_shortcircuits_to_score_1():
    score, _conf, gated, p_yes = fastpath._composite_from_answers(
        _answers(excl_fundraising={"probabilities": {"true": 0.9}})
    )
    assert score == 1
    assert gated == "excl_fundraising"
    assert p_yes > 0.6


def test_gate_threshold_not_exceeded_passes_through():
    # p(yes) = 0.6 is NOT > 0.60, so the gate does not fire.
    score, _conf, gated, _ = fastpath._composite_from_answers(
        _answers(excl_license={"probabilities": {"true": 0.6}})
    )
    assert gated is None
    assert score == 10


# --- Routing ----------------------------------------------------------------

def test_route_decisions_on_mode():
    assert fastpath.jev_route(9, 0.8, "on") == "fast_accept"
    assert fastpath.jev_route(10, 0.6, "on") == "fast_accept"  # conf == 0.6 is >= 0.6
    assert fastpath.jev_route(3, 0.9, "on") == "fast_reject"
    assert fastpath.jev_route(4, 0.6, "on") == "fast_reject"
    assert fastpath.jev_route(6, 0.8, "on") == "escalate"  # 5-7 band
    assert fastpath.jev_route(5, 0.8, "on") == "escalate"
    assert fastpath.jev_route(9, 0.5, "on") == "escalate"  # low confidence
    assert fastpath.jev_route(4, 0.59, "on") == "escalate"


def test_route_never_decides_outside_on():
    assert fastpath.jev_route(9, 0.9, "shadow") == "escalate"
    assert fastpath.jev_route(1, 0.9, "off") == "escalate"
    assert fastpath.jev_route(None, None, "on") == "escalate"


def test_get_jev_hybrid_defaults_off():
    assert fastpath.get_jev_hybrid(None) == "off"
    assert fastpath.get_jev_hybrid({}) == "off"
    assert fastpath.get_jev_hybrid({"jev_hybrid": "bogus"}) == "off"
    assert fastpath.get_jev_hybrid({"jev_hybrid": "on"}) == "on"
    assert fastpath.get_jev_hybrid({"jev_hybrid": "SHADOW"}) == "shadow"


# --- Config / API key -------------------------------------------------------

def test_typesafe_key_from_user_env_not_repo(monkeypatch, tmp_path):
    from jobwright import config

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("TYPESAFE_API_KEY=\"sekret-abc\"\n# other=keep\nFOO=bar\n")
    monkeypatch.setattr(config, "ENV_PATH", env)
    assert fastpath._typesafe_api_key() == "sekret-abc"


def test_typesafe_key_absent_returns_none(monkeypatch, tmp_path):
    from jobwright import config

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "missing.env")
    assert fastpath._typesafe_api_key() is None


# --- score_fastpath (monkeypatched HTTP, no network) ------------------------

def _make_db(tmp_path):
    from jobwright.database import ensure_columns, get_connection

    db = tmp_path / "jobs.db"
    get_connection(db)  # create file
    conn = get_connection(db)
    conn.execute("CREATE TABLE IF NOT EXISTS jobs (url TEXT PRIMARY KEY)")
    conn.commit()
    ensure_columns(conn)  # adds jev columns
    return conn


def test_score_fastpath_on_routes_and_persists(monkeypatch, tmp_path):
    conn = _make_db(tmp_path)
    for url in ("https://a.example/1", "https://a.example/2"):
        conn.execute("INSERT INTO jobs (url) VALUES (?)", (url,))
    conn.commit()

    jobs = [
        {"url": "https://a.example/1", "title": "Program Director",
         "company": "Impact Fdn", "location": "SF", "full_description": "lead programs"},
        {"url": "https://a.example/2", "title": "Store Clerk",
         "company": "Store", "location": "NY", "full_description": "sales floor"},
    ]
    # job 1 -> strong (score 10), job 2 -> reject-level (score 2)
    def _fake_post(payload, api_key):
        idx = 0 if "Program" in payload["state"]["job"]["title"] else 1
        if idx == 0:
            return {"answers": _answers()}
        return {"answers": _answers(
            role_function_match={"score": 1, "confidence": 0.9},
            mission_sector_alignment={"score": 1, "confidence": 0.8},
            seniority_fit={"score": 1, "confidence": 0.7},
        )}

    monkeypatch.setattr(fastpath, "_post_systemone", _fake_post)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    results = fastpath.score_fastpath(
        jobs, {"jev_hybrid": "on", "job_preferences": {"ideal_roles": ["Program officer"]}}, conn,
    )
    by_url = {r["url"]: r for r in results}
    assert by_url["https://a.example/1"]["jev_route"] == "fast_accept"
    assert by_url["https://a.example/1"]["jev_score"] == 10
    assert by_url["https://a.example/2"]["jev_route"] == "fast_reject"

    row = conn.execute("SELECT jev_score, jev_confidence, jev_routed FROM jobs WHERE url=?",
                       ("https://a.example/1",)).fetchone()
    assert row["jev_score"] == 10.0
    assert row["jev_routed"] == "fast_accept"


def test_score_fastpath_shadow_escalates_everything(monkeypatch, tmp_path):
    conn = _make_db(tmp_path)
    url = "https://a.example/1"
    conn.execute("INSERT INTO jobs (url) VALUES (?)", (url,))
    conn.commit()

    def _fake_post(payload, api_key):
        return {"answers": _answers()}

    monkeypatch.setattr(fastpath, "_post_systemone", _fake_post)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    results = fastpath.score_fastpath(
        jobs=[{"url": url, "title": "Program Director", "company": "Fdn",
               "location": "SF", "full_description": "lead"}],
        user_config={"jev_hybrid": "shadow"},
        conn=conn,
    )
    # Shadow stores the score but never routes to a decision.
    assert results[0]["jev_route"] == "escalate"
    assert results[0]["jev_score"] == 10


def test_score_fastpath_off_is_noop(monkeypatch, tmp_path):
    conn = _make_db(tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    results = fastpath.score_fastpath([{"url": "u"}], {"jev_hybrid": "off"}, conn)
    assert results == []


def test_score_fastpath_missing_key_is_noop(monkeypatch, tmp_path):
    conn = _make_db(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    results = fastpath.score_fastpath([{"url": "u"}], {"jev_hybrid": "on"}, conn)
    assert results == []  # downgraded, never blocks


def test_score_fastpath_error_downgrades_job(monkeypatch, tmp_path):
    conn = _make_db(tmp_path)
    url = "https://a.example/1"
    conn.execute("INSERT INTO jobs (url) VALUES (?)", (url,))
    conn.commit()

    def _boom(payload, api_key):
        raise RuntimeError("network down")

    monkeypatch.setattr(fastpath, "_post_systemone", _boom)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    results = fastpath.score_fastpath(
        [{"url": url, "title": "T", "full_description": "d"}],
        {"jev_hybrid": "on"}, conn,
    )
    assert results[0]["jev_route"] == "error"
    assert results[0]["jev_score"] is None


# --- Database migration (additive, idempotent) ------------------------------

def test_ensure_columns_migrates_and_is_idempotent(tmp_path):
    """check-then-add: jev columns appear once, and re-runs add nothing."""
    import sqlite3

    from jobwright.database import ensure_columns, get_connection

    db = tmp_path / "migrate.db"
    raw = sqlite3.connect(db)
    raw.execute("CREATE TABLE jobs (url TEXT PRIMARY KEY, fit_score INTEGER)")
    raw.commit()
    raw.close()

    conn = get_connection(db)
    added = ensure_columns(conn)
    assert {"jev_score", "jev_confidence", "jev_routed"} <= set(added)

    # Second run is a no-op (idempotent).
    assert ensure_columns(conn) == []

    present = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert {"jev_score", "jev_confidence", "jev_routed"} <= present
    # Existing columns preserved.
    assert "fit_score" in present


def test_init_db_creates_jev_columns_fresh(tmp_path, monkeypatch):
    from jobwright import config
    from jobwright.database import close_connection, init_db

    db = tmp_path / "fresh.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    conn = init_db(db)
    present = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert {"jev_score", "jev_confidence", "jev_routed"} <= present
    close_connection(db)