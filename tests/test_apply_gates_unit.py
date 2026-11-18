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
