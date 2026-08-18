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
