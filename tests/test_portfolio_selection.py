"""Portfolio stage: which projects are chosen, and which jobs get those ids.

The model is a fake. Expected ranks are counted by hand from the description,
not by calling the scorer.
"""

from __future__ import annotations

import json

import pytest

from jobwright import config
from jobwright.llm_json import LLMJsonError
from jobwright.scoring import portfolio

# "Grant Tracker" is in the text, and so are "Excel" and "budgeting".
DESCRIPTION = "We need a Grant Tracker and Excel budgeting partner."

# Overlap with DESCRIPTION, counted by hand:
# grant: name "Grant Tracker" (+3), stack Excel (+2), bullet word "tracker" (+1) = 6
# budget: bullet word "budgeting" (+1) = 1
# quiet: no shared name, stack token, or bullet word = 0
PROJECTS = [
    {
        "id": "grant",
        "name": "Grant Tracker",
        "stack": ["Excel"],
        "bullets": ["Shipped a tracker for grants"],
    },
    {
        "id": "budget",
        "name": "Budget Board",
        "stack": ["Figma"],
        "bullets": ["Mapped the budgeting calendar"],
    },
    {
        "id": "quiet",
        "name": "Quiet Notes",
        "stack": ["Notion"],
        "bullets": ["Wrote weekly notes for the team"],
    },
]
KEYWORD_ORDER = ["grant", "budget", "quiet"]


def _forbid_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no(*_a, **_k):
        raise AssertionError("the model should not be called")

    monkeypatch.setattr(portfolio, "get_client", _no)
    monkeypatch.setattr(portfolio, "chat_json_object", _no)


def _stub_model(monkeypatch: pytest.MonkeyPatch, reply):
    monkeypatch.setattr(portfolio, "get_client", lambda: object())

    def _chat(_client, messages, **_kwargs):
        if callable(reply):
            return reply(messages)
        return reply

    monkeypatch.setattr(portfolio, "chat_json_object", _chat)


def test_no_portfolio_selects_nothing(monkeypatch):
    _forbid_llm(monkeypatch)
    assert portfolio.select_projects_for_job({}, {"full_description": DESCRIPTION}) == []
    assert portfolio.select_projects_for_job({"portfolio": []}, {"full_description": DESCRIPTION}) == []


def test_missing_description_keeps_the_first_five_ids_and_skips_the_model(monkeypatch):
    _forbid_llm(monkeypatch)
    projects = [{"id": f"p{i}", "name": f"Project {i}"} for i in range(6)]
    chosen = portfolio.select_projects_for_job({"portfolio": projects}, {"title": "Program Manager"})
    assert chosen == ["p0", "p1", "p2", "p3", "p4"]


def test_model_picks_keep_its_order_drop_unknown_ids_and_stop_at_five(monkeypatch):
    projects = [{"id": f"p{i}", "name": f"Project {i}"} for i in range(7)]
    _stub_model(
        monkeypatch,
        {"selected_ids": ["p6", "missing", "p0", "p1", "p2", "p3", "p4"]},
    )
    chosen = portfolio.select_projects_for_job(
        {"portfolio": projects},
        {"full_description": "A role with a description."},
    )
    assert chosen == ["p6", "p0", "p1", "p2", "p3"]


def test_short_description_field_still_asks_the_model(monkeypatch):
    _stub_model(monkeypatch, {"selected_ids": ["quiet"]})
    chosen = portfolio.select_projects_for_job(
        {"portfolio": PROJECTS},
        {"description": DESCRIPTION},
    )
    assert chosen == ["quiet"]


@pytest.mark.parametrize("reply", ["json-error", "runtime-error", "null-ids"])
def test_unusable_model_reply_falls_back_to_keyword_overlap(reply, monkeypatch):
    def _reply(_messages):
        if reply == "json-error":
            raise LLMJsonError("not json")
        if reply == "runtime-error":
            raise RuntimeError("model down")
        return {"selected_ids": None}

    _stub_model(monkeypatch, _reply)
    chosen = portfolio.select_projects_for_job(
        {"portfolio": PROJECTS},
        {"url": "https://example.com/jobs/1", "full_description": DESCRIPTION},
    )
    assert chosen == KEYWORD_ORDER


def test_an_explicit_empty_pick_is_kept_and_does_not_fall_back(monkeypatch):
    _stub_model(monkeypatch, {"selected_ids": []})
    chosen = portfolio.select_projects_for_job(
        {"portfolio": PROJECTS},
        {"full_description": DESCRIPTION},
    )
    assert chosen == []


def test_model_is_offered_only_the_twelve_closest_projects(monkeypatch):
    # Twelve zero-overlap projects, then the one that matches the description.
    # After ranking, the matching project leads and the last zero-overlap one
    # falls outside the twelve shown to the model.
    filler = [
        {
            "id": f"z{i:02d}",
            "name": f"Zed {i:02d}",
            "stack": ["Obsidian"],
            "bullets": ["Kept private sketches offline"],
        }
        for i in range(1, 13)
    ]
    projects = [*filler, PROJECTS[0]]
    seen: dict[str, str] = {}

    def _reply(messages):
        seen["prompt"] = messages[0]["content"]
        return {"selected_ids": ["z11"]}

    _stub_model(monkeypatch, _reply)
    chosen = portfolio.select_projects_for_job(
        {"portfolio": projects},
        {"title": "Program Manager", "full_description": DESCRIPTION},
    )
    assert chosen == ["z11"]
    prompt = seen["prompt"]
    assert "id=grant" in prompt
    assert "id=z11" in prompt
    assert "id=z12" not in prompt


def test_saved_ids_resolve_to_projects_in_stored_order():
    profile = {
        "portfolio": [
            {"id": "a", "name": "Alpha"},
            {"id": "b", "name": "Beta"},
            {"name": "No id"},
        ]
    }
    job = {"portfolio_project_ids": json.dumps(["b", "missing", "a"])}
    assert portfolio.get_selected_projects(profile, job) == [
        {"id": "b", "name": "Beta"},
        {"id": "a", "name": "Alpha"},
    ]
    assert portfolio.get_selected_projects({}, {"portfolio_project_ids": '["a"]'}) == []
    assert portfolio.get_selected_projects(profile, {}) == []
    assert portfolio.get_selected_projects(profile, {"portfolio_project_ids": "not-json"}) == []
    assert portfolio.get_selected_projects(profile, {"portfolio_project_ids": ["a"]}) == [
        {"id": "a", "name": "Alpha"},
    ]


def _write_profile(projects: list[dict]) -> None:
    config.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.PROFILE_PATH.write_text(json.dumps({"portfolio": projects}), encoding="utf-8")


def _insert_job(conn, url: str, *, title: str, score: int, description: str | None, ids: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO jobs (url, title, company, site, fit_score, full_description, portfolio_project_ids, discovered_at)
        VALUES (?, ?, 'Example Org', 'example', ?, ?, ?, '2026-01-01')
        """,
        (url, title, score, description, ids),
    )


def test_stage_skips_when_the_profile_has_no_portfolio(monkeypatch):
    _forbid_llm(monkeypatch)
    _write_profile([])
    assert portfolio.run_portfolio_selection() == {"status": "skipped", "reason": "no_portfolio"}


def test_stage_writes_ids_only_for_eligible_jobs(monkeypatch):
    from jobwright.database import init_db

    conn = init_db()
    _write_profile(PROJECTS)
    _insert_job(conn, "https://example.com/jobs/high", title="Real Pick", score=9, description="Ops role")
    _insert_job(conn, "https://example.com/jobs/empty", title="Empty Pick", score=8, description="Ops role")
    _insert_job(conn, "https://example.com/jobs/low", title="Low Pick", score=4, description="Ops role")
    _insert_job(
        conn,
        "https://example.com/jobs/kept",
        title="Kept Pick",
        score=8,
        description="Ops role",
        ids=json.dumps(["keep"]),
    )
    _insert_job(conn, "https://example.com/jobs/blank", title="Blank Pick", score=9, description=None)
    conn.commit()

    def _reply(messages):
        text = messages[0]["content"]
        if "Empty Pick" in text:
            return {"selected_ids": []}
        return {"selected_ids": ["quiet", "invented", "grant"]}

    _stub_model(monkeypatch, _reply)
    assert portfolio.run_portfolio_selection(min_score=7) == {"status": "ok", "processed": 1}

    rows = {
        row["url"]: row["portfolio_project_ids"]
        for row in conn.execute("SELECT url, portfolio_project_ids FROM jobs")
    }
    assert json.loads(rows["https://example.com/jobs/high"]) == ["quiet", "grant"]
    assert rows["https://example.com/jobs/empty"] is None
    assert rows["https://example.com/jobs/low"] is None
    assert json.loads(rows["https://example.com/jobs/kept"]) == ["keep"]
    assert rows["https://example.com/jobs/blank"] is None


def test_stage_limit_updates_the_highest_score_only(monkeypatch):
    from jobwright.database import init_db

    conn = init_db()
    _write_profile(PROJECTS)
    _insert_job(conn, "https://example.com/jobs/second", title="Second", score=8, description="Ops role")
    _insert_job(conn, "https://example.com/jobs/first", title="First", score=9, description="Ops role")
    conn.commit()
    _stub_model(monkeypatch, {"selected_ids": ["grant"]})

    assert portfolio.run_portfolio_selection(min_score=7, limit=1) == {"status": "ok", "processed": 1}
    rows = {
        row["url"]: row["portfolio_project_ids"]
        for row in conn.execute("SELECT url, portfolio_project_ids FROM jobs")
    }
    assert json.loads(rows["https://example.com/jobs/first"]) == ["grant"]
    assert rows["https://example.com/jobs/second"] is None
