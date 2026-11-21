"""Unit coverage for apply gates that decide whether Claude may claim a job.

Locks down score preference, already-applied checks, employer-cap counting of
hand-marked applications, material file stems, answer-bank fact rules that
keep place-specific / invalid writes out of the shared bank, and open-question
callback logging when the model fails mid-form. No browser, no MCP.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

from jobwright import config
from jobwright import users as users_mod
from jobwright.apply import answers as answers_mod
from jobwright.apply import safety
from jobwright.apply.runner import make_open_answer
from jobwright.database import close_connection, get_connection, init_db, job_id_for_url
from jobwright.job_identity import material_prefix, resolve_company


@pytest.fixture
def env():
    users_mod.add_user("alex", name="Alex Rivera", apply_enabled=True)
    users_mod.update_user("alex", apply_via="server")
    data = config.set_active_user("alex")
    close_connection()
    init_db()
    (data / "profile.json").write_text(json.dumps({"personal": {
        "full_name": "Alex Rivera", "email": "user1@example.com", "phone": "+1 415 555 0100",
        "city": "Oakland"}}), encoding="utf-8")
    yield data
    close_connection()


def _job(**kw) -> dict:
    base = {
        "url": "https://jobs.example.com/j/1", "company": "Example Co", "title": "Analyst",
        "site": "greenhouse", "fit_score": 9, "dedupe_key": "example co|analyst|sf",
    }
    base.update(kw)
    return base


def test_effective_score_prefers_the_persons_rating():
    assert safety.effective_score({"fit_score": 9, "user_fit_score": 4}) == 4
    assert safety.effective_score({"fit_score": 9}) == 9
    assert safety.effective_score({}) is None


def test_check_job_uses_user_rating_and_rejects_already_applied(env):
    low = _job(fit_score=9, user_fit_score=5)
    assert any("below 8" in r for r in safety.check_job(low, "alex", live=False).reasons)
    marked = _job(url="https://jobs.example.com/j/2", applied_at="2026-11-01T00:00:00+00:00")
    assert any("already marked applied" in r for r in safety.check_job(marked, "alex", live=False).reasons)


def test_already_applied_same_posting_via_hand_mark_and_submission(env):
    """Same company|title|place must block a second apply even without a submissions row."""
    conn = get_connection()
    when = datetime.now(timezone.utc).isoformat()
    key = "example co|analyst|sf"
    first = "https://jobs.example.com/post/1"
    second = "https://jobs.example.com/post/2"
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, fit_score, job_id, funnel_stage, applied_at, "
        "discovered_at, dedupe_key) VALUES (?, 'Analyst', 'Example Co', 'greenhouse', 9, ?, 'applied', ?, ?, ?)",
        (first, job_id_for_url(first), when, when, key),
    )
    conn.commit()
    sibling = _job(url=second, dedupe_key=key)
    assert safety.already_applied_same_posting(sibling) is True
    assert any("same company and title" in r for r in safety.check_job(sibling, "alex", live=False).reasons)

    other = _job(url="https://jobs.example.com/post/3", dedupe_key="other|eng|sf")
    assert safety.already_applied_same_posting(other) is False
    conn.execute(
        "INSERT INTO submissions (run_id, job_url, company, title, dry_run, outcome, started_at, dedupe_key) "
        "VALUES ('run-test', ?, 'Other Co', 'Eng', 0, 'applied', ?, 'other|eng|sf')",
        (other["url"], when),
    )
    conn.commit()
    assert safety.already_applied_same_posting(other) is True


def test_answer_bank_lookup_custom_wins_and_is_job_specific(env):
    answers_mod.set_answers({"work_authorized": "Yes", "requires_sponsorship": "No"}, source="settings")
    answers_mod.set_custom_answer("Do you hold a CPA license?", "No", source="whatsapp")
    bank = answers_mod.load_answers()

    key, value = bank.lookup("Are you legally authorized to work in the United States?")
    assert key == "work_authorized" and value == "Yes"
    key, value = bank.lookup("Do you hold a CPA license?")
    assert key and key.startswith("custom:") and value == "No"
    assert bank.lookup("Favorite ice cream?") == (None, None)

    assert answers_mod.is_job_specific("Why do you want to work at Example Co?")
    assert answers_mod.is_job_specific("Tell us about a time you led a project")
    assert not answers_mod.is_job_specific("Are you authorized to work in the US?")
    refused = answers_mod.save_facts(
        [{"question": "Why are you interested in this role?", "value": "Mission fit", "source": "told_claude"}],
        person_confirmed=False,
    )
    assert refused[0]["status"] == "not_saved" and "one employer" in refused[0]["reason"]


def test_undo_answer_restores_previous_or_clears(env):
    answers_mod.set_answers({"salary_expectation": "120k"}, source="settings")
    answers_mod.set_answers({"salary_expectation": "150k"}, source="told_claude")
    bank = answers_mod.undo_answer(key="salary_expectation")
    assert bank.get("salary_expectation") == "120k"
    answers_mod.set_answers({"relocation": "Yes"}, source="settings")
    bank = answers_mod.undo_answer(key="relocation")
    assert bank.get("relocation") is None
    with pytest.raises(ValueError, match="key or question"):
        answers_mod.undo_answer()
    with pytest.raises(LookupError):
        answers_mod.undo_answer(key="relocation")


def test_employer_cap_counts_hand_marked_jobs_without_submission(env):
    assert safety.employer_applications("") == 0
    assert safety.employer_applications(None) == 0
    conn = get_connection()
    url = "https://jobs.example.com/hand/1"
    when = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, fit_score, job_id, funnel_stage, applied_at, "
        "discovered_at) VALUES (?, 'Analyst', 'Example Co, Inc.', 'greenhouse', 9, ?, 'applied', ?, ?)",
        (url, job_id_for_url(url), when, when),
    )
    conn.commit()
    assert safety.employer_applications("Example Co") == 1
    other = _job(url="https://jobs.example.com/hand/2", company="Example Co", title="Engineer",
                 dedupe_key="example co|eng|sf")
    assert any("last 30 days" in r for r in safety.check_job(other, "alex", live=True).reasons)


def test_maybe_auto_pause_is_a_no_op_when_already_paused_or_under_limit(env):
    assert safety.maybe_auto_pause(None) is False
    assert safety.maybe_auto_pause("alex") is False
    users_mod.update_user("alex", apply_paused=True, apply_paused_reason="already")
    assert safety.maybe_auto_pause("alex") is False


def test_check_profile_unknown_user_and_paused_reason(env):
    assert "unknown profile" in safety.check_profile("nobody", live=True).reasons
    users_mod.update_user("alex", apply_paused=True, apply_paused_reason="2 failures")
    assert any("2 failures" in r for r in safety.check_profile("alex", live=True).reasons)


def test_resolve_company_never_returns_a_job_board_name():
    assert resolve_company({"company": "Acme", "site": "linkedin"}) == "Acme"
    assert resolve_company({"company": "", "site": "WorkdayTenant"}) == "WorkdayTenant"
    assert resolve_company({"company": "", "site": "linkedin", "title": "Analyst at Bright Labs"}) == "Bright Labs"
    assert resolve_company({"company": "", "site": "indeed", "title": "Analyst"}) == ""


def test_material_prefix_is_stable_and_unique_per_url():
    a = {"url": "https://jobs.example.com/a", "company": "Example Co!", "title": "Sr. Analyst"}
    b = {"url": "https://jobs.example.com/b", "company": "Example Co!", "title": "Sr. Analyst"}
    assert material_prefix(a).startswith("Example_Co_Sr_Analyst_")
    assert material_prefix(a) != material_prefix(b)
    assert material_prefix({"url": "https://jobs.example.com/c", "company": "", "title": ""}) \
        .startswith("company_untitled_")


def test_fact_key_blocks_place_specific_attestations_and_unknown_keys():
    assert answers_mod.fact_key(None, "salary_expectation") == "salary_expectation"
    with pytest.raises(ValueError, match="Unknown"):
        answers_mod.fact_key(None, "not_a_real_key")
    assert answers_mod.fact_key("Are you willing to relocate to Boston?") is None
    assert answers_mod.fact_key("Are you willing to relocate?") == "relocation"


def test_save_facts_validates_before_writing(env):
    with pytest.raises(ValueError, match="source must be"):
        answers_mod.save_facts([{"question": "Desired pay", "value": "100k", "source": "settings"}],
                               person_confirmed=True)
    with pytest.raises(ValueError, match="needs a value"):
        answers_mod.save_facts([{"question": "Desired pay", "value": "  ", "source": "told_claude"}],
                               person_confirmed=True)
    with pytest.raises(ValueError, match="2000"):
        answers_mod.save_facts([{"question": "Notes", "value": "x" * 2001, "source": "told_claude"}],
                               person_confirmed=False)
    with pytest.raises(ValueError, match="form's question"):
        answers_mod.save_facts([{"question": "ab", "value": "yes", "source": "told_claude"}],
                               person_confirmed=False)
    assert answers_mod.load_answers().get("salary_expectation") is None


def test_seed_from_profile_moves_legacy_contact_answers(env):
    path = env / "profile.json"
    profile = json.loads(path.read_text())
    profile["application_answers"] = {
        "version": 1,
        "answers": {"city": {"value": "Berkeley", "source": "cli", "updated_at": "2026-01-01T00:00:00+00:00"}},
        "custom": {},
    }
    profile["personal"].pop("city", None)
    path.write_text(json.dumps(profile), encoding="utf-8")
    moved = answers_mod.seed_from_profile()
    assert moved == {"city": "Berkeley"}
    assert answers_mod.load_answers().get("city") == "Berkeley"
    assert json.loads(path.read_text())["personal"]["city"] == "Berkeley"


def test_make_open_answer_logs_question_and_job_on_failure(caplog):
    """A model/API failure still returns ''; the warning names question, job, and error type."""

    class Boom:
        def answer_open_question(self, question, job, resume_text, cover_text=""):
            raise RuntimeError("provider down")

    answer = make_open_answer(Boom(), "resume text")
    job = {
        "url": "https://jobs.example.com/j/1",
        "title": "Analyst",
        "company": "Example Co",
    }
    with caplog.at_level(logging.WARNING, logger="jobwright.apply.runner"):
        assert answer("How many years of Python experience?", job) == ""
    text = caplog.text
    assert "How many years of Python experience?" in text
    assert "https://jobs.example.com/j/1" in text
    assert "Analyst" in text
    assert "Example Co" in text
    assert "RuntimeError" in text
    assert "provider down" in text


def test_make_open_answer_success_and_attestation_skip():
    class Ok:
        def answer_open_question(self, question, job, resume_text, cover_text=""):
            return f"ans:{question}:{resume_text[:4]}"

    answer = make_open_answer(Ok(), "long resume")
    job = {"url": "https://jobs.example.com/j/2", "title": "Eng", "company": "Acme"}
    assert answer("Favorite stack?", job) == "ans:Favorite stack?:long"
    # Attestations must stay empty so the filler records a Need, never a guessed answer.
    assert answer("Are you authorized to work in the US?", job) == ""
    assert make_open_answer(None, "resume")("Anything?", job) == ""


def test_connector_settings_and_revoke_api(env, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from jobwright.connector import store
    from jobwright.web import session as session_mod
    from jobwright.web.app import app

    monkeypatch.setenv("JOBWRIGHT_DASHBOARD_USER", "alex")
    session_mod.forget_initialized()
    with TestClient(app) as client:
        client.cookies.set("jobwright_user", "alex")
        config.set_active_user("alex")
        close_connection()

        state = client.get("/api/connector")
        assert state.status_code == 200
        sbody = state.json()
        assert sbody["apply_via"] == "server"
        assert sbody["apply_enabled"] is True
        assert sbody["missing_answers"] > 0

        assert client.put("/api/connector/settings", json={}).status_code == 400
        res = client.put("/api/connector/settings", json={"apply_via": "connector", "apply_enabled": False})
        assert res.status_code == 200
        assert res.json()["apply_via"] == "connector"
        assert res.json()["apply_enabled"] is False

        # Non-admin user cannot hand applications to the server runner.
        monkeypatch.setattr(
            "jobwright.web.routers.connector.get_identity",
            lambda _req: type("Ident", (), {"is_admin": False, "email": "user1@example.com"})(),
        )
        assert client.put("/api/connector/settings", json={"apply_via": "server"}).status_code == 403

        assert client.delete("/api/connector/clients/jwg_missing").status_code == 404
        monkeypatch.setattr(store, "revoke_grant", lambda gid, user_id, reason: gid == "jwg_ok" and user_id == "alex")
        assert client.delete("/api/connector/clients/jwg_ok").status_code == 200


def test_auto_render_picks_connector_and_due_missing_job_and_exception(env, monkeypatch):
    from datetime import timedelta

    from jobwright.apply import auto, evidence

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr("jobwright.notify.send_via_hermes", lambda text, target: sent.append((target, text)))
    users_mod.update_user("alex", whatsapp_target="whatsapp:120363999999999901@g.us", apply_via="connector")

    conn = get_connection()
    now = datetime.now(timezone.utc)
    for i, (co, title) in enumerate([("Alpha", "Ops Lead"), ("Beta", "Analyst")], start=1):
        url = f"https://jobs.example.com/auto/{i}"
        conn.execute(
            "INSERT INTO jobs (url, title, company, site, application_url, fit_score, tailored_resume_path, "
            "cover_letter_path, dedupe_key, job_id, funnel_stage, discovered_at) "
            "VALUES (?, ?, ?, 'greenhouse', ?, 9, 'r.md', 'c.md', ?, ?, 'prepare', ?)",
            (url, title, co, url, f"{co}|{title}|sf", job_id_for_url(url), now.isoformat()),
        )
    conn.commit()

    picked = auto.pick("alex", now=now, conn=conn)
    assert len(picked["picks"]) == 2
    assert "Picked for your Claude today" in sent[-1][1]

    # Switch back to server runner for due(); delete the first job from board and make the second raise.
    users_mod.update_user("alex", apply_via="server")
    conn.execute("DELETE FROM jobs WHERE url = 'https://jobs.example.com/auto/1'")
    conn.commit()

    def _boom(_job, **_kw):
        raise RuntimeError("browser crashed")

    done = auto.due("alex", now=now + timedelta(hours=4), apply_fn=_boom, report=True, conn=conn)
    assert len(done) == 2
    by_num = {p["number"]: p for p in done}
    assert by_num[1]["status"] == "skipped" and by_num[1]["note"] == "job no longer on the board"
    assert by_num[2]["status"] == "failed" and by_num[2]["outcome"] == "error"
    assert "browser crashed" in (by_num[2]["note"] or "")
    report_msg = sent[-1][1]
    assert "job no longer on the board" in report_msg
    assert "browser crashed" in report_msg

    # Verify send_report posts text and screenshot media for applied submissions, and render_report formats needs.
    sid = evidence.start_submission(
        {"url": "https://jobs.example.com/auto/2", "company": "Beta", "title": "Analyst"},
        rid := evidence.new_run_id(),
        ats="greenhouse",
        provider="test",
        model=None,
        dry_run=False,
    )
    (evidence.run_dir(rid) / "confirmation.png").write_bytes(b"\x89PNG fake")
    evidence.finish_submission(
        sid,
        outcome="applied",
        fields=[],
        needs=[],
        screenshots={"confirmation": "confirmation.png"},
        transcript_path=None,
    )
    assert auto.send_report(
        "alex",
        [{"number": 1, "title": "Analyst", "company": "Beta", "outcome": "applied", "submission_id": sid}],
        conn=conn,
    )
    assert f"/apply/submissions/{sid}" in sent[-2][1]
    assert "MEDIA:" in sent[-1][1] and "confirmation.png" in sent[-1][1]
