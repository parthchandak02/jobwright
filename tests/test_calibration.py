"""Post-setup calibration: which jobs to rate, and GET /api/onboarding/calibration."""

from __future__ import annotations

import pytest

from jobwright.calibration import TARGET, calibration, select_jobs

pytest.importorskip("fastapi")
pytest.importorskip("jwt")

import test_web_multiuser as _multiuser  # noqa: E402

api_env = _multiuser.api_env


def _row(i, score, company=None, title=None, **kw):
    return {
        "url": f"https://ex.com/{i}",
        "title": title or f"Role {i}",
        "company": company or f"Co {i}",
        "site": "indeed",
        "location": "Remote",
        "fit_score": score,
        "score_reasoning": "Good overlap.",
        "score_gates": "{}",
        "dedupe_key": None,
        **kw,
    }


def test_select_mixes_bands_borderline_first():
    rows = [_row(i, s) for i, s in enumerate([10, 9, 9, 8, 8, 7, 6, 6, 5, 5, 4, 3, 2, 1, 1])]
    picked = select_jobs(rows, 8)
    scores = [r["fit_score"] for r in picked]
    assert len(picked) == 8
    assert scores[0] == 6 and scores[1] == 10 and scores[3] == 4
    assert sum(1 for s in scores if 5 <= s <= 7) == 4
    assert sum(1 for s in scores if s >= 8) == 2 and sum(1 for s in scores if s <= 4) == 2


def test_select_dedupes_company_and_title_then_fills():
    rows = [
        _row(1, 6, company="Acme", title="Program Manager"),
        _row(2, 6, company="ACME", title="Grants Lead"),
        _row(3, 9, company="Beta", title="program manager"),
        _row(4, 9, company="Gamma", title="Director"),
        _row(5, 3, company="Acme", title="Program Manager"),
    ]
    picked = select_jobs(rows, 3)
    assert [r["url"][-1] for r in picked] == ["1", "4", "2"]
    everything = select_jobs(rows, 10)
    pairs = [(r["company"].lower(), r["title"].lower()) for r in everything]
    assert len(pairs) == len(set(pairs)) == 4


def _seed(client, h, n=12):
    import sqlite3

    from jobwright import config

    ann = h("ann@example.com")
    client.post("/api/onboarding/profile", json={"name": "Ann"}, headers=ann)
    client.cookies.set("jobwright_user", "ann")
    ids = []
    for i in range(n):
        res = client.post("/api/jobs", json={"url": f"https://ex.com/j{i}", "title": f"Role {i}",
                                             "company": f"Co {i}"}, headers=ann)
        ids.append(res.json()["job_id"])
    with config.user_context("ann"):
        db = config.DB_PATH
    conn = sqlite3.connect(db)
    for i in range(n):
        conn.execute("UPDATE jobs SET fit_score = ?, score_reasoning = ? WHERE url = ?",
                     ((i % 10) + 1, "Strong program background. " * 12, f"https://ex.com/j{i}"))
    conn.commit()
    conn.close()
    return ann, ids


def test_calibration_endpoint_waits_then_serves(api_env):
    client, h, _ = api_env
    ann = h("ann@example.com")
    client.post("/api/onboarding/profile", json={"name": "Ann"}, headers=ann)
    client.cookies.set("jobwright_user", "ann")
    body = client.get("/api/onboarding/calibration", headers=ann).json()
    assert body == {"ready": False, "scored_count": 0, "rated_count": 0, "target": TARGET, "jobs": []}


def test_calibration_endpoint_excludes_rated_and_counts(api_env):
    client, h, _ = api_env
    ann, ids = _seed(client, h)
    body = client.get("/api/onboarding/calibration", headers=ann).json()
    assert body["ready"] is True and body["scored_count"] == 12 and body["rated_count"] == 0
    assert len(body["jobs"]) == TARGET
    job = body["jobs"][0]
    assert set(job) == {"job_id", "url", "title", "company", "location", "fit_score", "reason"}
    assert len(job["reason"]) <= 161

    first = job["job_id"]
    res = client.patch(f"/api/jobs/{first}", json={"user_fit_score": 8, "user_score_reasons": ["Right level"]},
                       headers=ann)
    assert res.status_code == 200, res.text
    body = client.get("/api/onboarding/calibration", headers=ann).json()
    assert body["rated_count"] == 1 and len(body["jobs"]) == TARGET - 1
    assert first not in {j["job_id"] for j in body["jobs"]}

    labels = client.get(f"/api/jobs/{first}/labels", headers=ann).json()["labels"]
    assert labels[-1]["label_score"] == 8 and labels[-1]["source"] == "dashboard"


def test_calibration_done_after_target(api_env):
    client, h, _ = api_env
    ann, ids = _seed(client, h)
    for jid in ids[:TARGET]:
        client.patch(f"/api/jobs/{jid}", json={"user_fit_score": 2, "user_score_reasons": ["Too senior"]},
                     headers=ann)
    body = client.get("/api/onboarding/calibration", headers=ann).json()
    assert body["rated_count"] == TARGET and body["jobs"] == []


def test_calibration_needs_profile(api_env):
    client, h, _ = api_env
    assert client.get("/api/onboarding/calibration", headers=h("nobody@example.com")).status_code == 403


def test_calibration_direct_skips_closed(tmp_path):
    import sqlite3

    from jobwright.database import close_connection, init_db

    db = tmp_path / "jobwright.db"
    init_db(db)
    close_connection(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO jobs (url, title, company, fit_score, funnel_stage) VALUES "
                 "('u1', 'A', 'X', 7, 'closed'), ('u2', 'B', 'Y', 7, 'backlog')")
    conn.commit()
    body = calibration(conn)
    assert [j["url"] for j in body["jobs"]] == ["u2"] and body["scored_count"] == 1
