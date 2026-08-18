"""Tests for batched job scoring (no live LLM)."""

from jobwright.llm_json import LLMJsonError
from jobwright.scoring.scorer import _map_batch_scores, _parse_score_response


def test_parse_score_response_clamps():
    parsed = _parse_score_response({"score": 12, "keywords": "ops", "reasoning": "strong fit"})
    assert parsed["score"] == 10


def test_map_batch_scores_matches_ids():
    jobs = [
        {"url": "https://a.example/1", "title": "Chief of Staff"},
        {"url": "https://a.example/2", "title": "Store Manager"},
    ]
    data = {
        "scores": [
            {"id": 1, "score": 8, "keywords": "ops", "reasoning": "direct CoS match"},
            {"id": 2, "score": 2, "keywords": "retail", "reasoning": "wrong field"},
        ]
    }
    scored, missing = _map_batch_scores(jobs, data)
    assert missing == []
    assert [s["url"] for s in scored] == ["https://a.example/1", "https://a.example/2"]
    assert scored[0]["score"] == 8
    assert scored[1]["score"] == 2


def test_map_batch_scores_missing_id_falls_back():
    jobs = [
        {"url": "https://a.example/1", "title": "A"},
        {"url": "https://a.example/2", "title": "B"},
    ]
    data = {"scores": [{"id": 1, "score": 7, "keywords": "x", "reasoning": "ok"}]}
    scored, missing = _map_batch_scores(jobs, data)
    assert len(scored) == 1
    assert missing == [jobs[1]]


def test_parse_score_response_requires_reasoning():
    try:
        _parse_score_response({"score": 5, "keywords": "x"})
        raise AssertionError("expected LLMJsonError")
    except LLMJsonError:
        pass


def test_score_job_returns_none_on_empty_llm(monkeypatch):
    """Empty LLM response cascade: score_job -> None."""
    from unittest.mock import MagicMock

    from jobwright.scoring import scorer

    client = MagicMock()
    client.chat.side_effect = RuntimeError("Empty LLM response from model after 2 attempts")
    monkeypatch.setattr(scorer, "get_client", lambda: client)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = scorer.score_job(
        "resume text",
        {"title": "Chief of Staff", "site": "indeed", "location": "SF", "full_description": "Do ops"},
    )
    assert result is None


def test_run_scoring_records_errors_on_empty_batch(tmp_path, monkeypatch):
    """Batch empty -> sequential fallback empty -> errors counted."""
    from unittest.mock import MagicMock

    import jobwright.config as config
    from jobwright.database import close_connection, get_connection, init_db
    from jobwright.scoring import scorer

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "missing-profile.json")
    monkeypatch.setattr("jobwright.resume.load_resume_text", lambda: "Jane Doe\nOps leader\n")
    monkeypatch.setenv("SCORE_BATCH_SIZE", "2")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    close_connection(db)
    init_db(db)
    conn = get_connection(db)
    for i in range(2):
        conn.execute(
            """
            INSERT INTO jobs (url, title, site, full_description, discovered_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (f"https://example.com/{i}", f"Role {i}", "indeed", "Do things", "2026-01-01"),
        )
    conn.commit()

    client = MagicMock()
    client.chat.side_effect = RuntimeError("Empty LLM response")
    monkeypatch.setattr(scorer, "get_client", lambda: client)

    out = scorer.run_scoring(limit=2)
    assert out["scored"] == 0
    assert out["errors"] == 2
    close_connection(db)
