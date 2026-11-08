"""Safe automatic apply: answer bank, agent tools, human-in-the-loop, evidence, safety rails.

Every browser test drives a real headless Chromium against a local fake ATS
(tests/apply_fakes.py) with a scripted fake Claude client. No network, no
model calls, no hermes.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apply_fakes import FakeATS, ScriptedClient, fill_form_steps, provide_when_open

from jobwright import config
from jobwright import users as users_mod
from jobwright.apply import answers as answers_mod
from jobwright.apply import auto, evidence, hitl, safety
from jobwright.apply.agent import AnthropicApplyAgent
from jobwright.apply.runner import apply_job
from jobwright.database import close_connection, get_connection, init_db, job_id_for_url

GROUP = "whatsapp:120363999999999901@g.us"
FULL_ANSWERS = {
    "work_authorized": "Yes", "requires_sponsorship": "No", "criminal_record": None, "background_check": "Yes",
    "age_18_plus": "Yes", "certify": "Yes", "salary_expectation": "Open to discussing",
    "start_date": "Two weeks after an offer", "relocation": "No", "onsite": "Yes", "previously_worked_here": "No",
    "eeo_gender": "Decline to self-identify", "eeo_race": "Decline to self-identify",
    "eeo_hispanic": "Decline to self-identify", "eeo_veteran": "I am not a protected veteran",
    "eeo_disability": "I do not want to answer", "phone": "+1 415 555 0100", "city": "Oakland",
    "state": "CA", "country": "United States", "education_highest": "BA Economics, Example University, 2019",
    "how_heard": "Company website",
}


@pytest.fixture
def env(monkeypatch):
    users_mod.add_user("alex", name="Alex Rivera", apply_enabled=True, whatsapp_target=GROUP)
    # These tests drive the server-side runner; the default is the person's own Claude (connector).
    users_mod.update_user("alex", apply_via="server")
    data = config.set_active_user("alex")
    close_connection()
    init_db()
    (data / "profile.json").write_text(json.dumps({"personal": {
        "full_name": "Alex Rivera", "email": "user1@example.com", "phone": "+1 415 555 0100",
        "city": "Oakland", "password": "never-use-this"}}), encoding="utf-8")
    tailored = data / "tailored_resumes"
    tailored.mkdir(exist_ok=True)
    (tailored / "resume.md").write_text("# Alex Rivera\nData analyst. SQL, Python, dashboards.\n", encoding="utf-8")
    (tailored / "resume.docx").write_bytes(b"PK fake docx")
    answers_mod.set_answers({k: v for k, v in FULL_ANSWERS.items() if v is not None}, source="cli")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr("jobwright.notify.send_via_hermes", lambda text, target: sent.append((target, text)))
    monkeypatch.setenv("JOBWRIGHT_PUBLIC_BASE_URL", "https://dash.example.com")
    monkeypatch.setenv("JOBWRIGHT_APPLY_FALLBACKS", "on")
    monkeypatch.setenv("JOBWRIGHT_APPLY_FILLERS", "off")
    yield {"dir": data, "sent": sent}
    close_connection()


def add_job(url: str, *, company: str = "Example Co", title: str = "Data Analyst", score: int = 9,
            application_url: str | None = None, site: str = "greenhouse", dedupe_key: str | None = None,
            stage: str = "backlog", materials: bool = True) -> dict:
    data = Path(config.APP_DIR) / "tailored_resumes"
    conn = get_connection()
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, application_url, fit_score, tailored_resume_path, "
        "tailored_resume_docx_path, cover_letter_path, dedupe_key, job_id, funnel_stage, discovered_at, "
        "full_description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Analyse data.')",
        (url, title, company, site, application_url or url, score,
         str(data / "resume.md") if materials else None, str(data / "resume.docx") if materials else None,
         str(data / "resume.md") if materials else None, dedupe_key or f"{company}|{title}|{url[-6:]}",
         job_id_for_url(url), stage, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone())


def run(job: dict, script, *, dry_run: bool, **kw):
    client = ScriptedClient(script)
    agent = AnthropicApplyAgent(client=client)
    res = apply_job(job, dry_run=dry_run, user_id="alex", agent=agent, headless=True, poll_s=0.05, **kw)
    return res, client


def job_row(url: str) -> dict:
    return dict(get_connection().execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone())


def transcript_text(res) -> str:
    sub = get_connection().execute("SELECT transcript_path FROM submissions WHERE id = ?",
                                   (res.submission_id,)).fetchone()
    return Path(sub[0]).read_text(encoding="utf-8")


SUBMIT_AND_FINISH = [
    ("click", {"ref": "@Submit application"}),
    ("snapshot", {}),
    ("finish", {"status": "submitted", "summary": "sent", "questions": []}),
]


# ---------------------------------------------------------------------------
# Answer bank
# ---------------------------------------------------------------------------


def test_answer_bank_round_trip_and_classifier(env):
    bank = answers_mod.load_answers()
    assert bank.get("work_authorized") == "Yes"
    assert bank.entry("phone")["source"] == "cli" and bank.entry("phone")["updated_at"]
    assert "criminal_record" in [s.key for s in bank.missing()]
    profile = json.loads((env["dir"] / "profile.json").read_text())
    assert profile["personal"]["full_name"] == "Alex Rivera"  # other keys kept
    assert stat.S_IMODE(os.stat(env["dir"] / "profile.json").st_mode) == 0o600
    cases = {
        "Will you now or in the future require sponsorship for employment visa status?": "requires_sponsorship",
        "Are you legally authorized to work in the United States?": "work_authorized",
        "Have you ever been convicted of a felony?": "criminal_record",
        "Do you consent to a background check?": "background_check",
        "What is your gender?": "eeo_gender",
        "Are you Hispanic or Latino?": "eeo_hispanic",
        "Are you at least 18 years of age?": "age_18_plus",
        "I certify that the information provided is true and complete": "certify",
        "What are your salary expectations?": "salary_expectation",
        "When can you start?": "start_date",
        "Are you willing to relocate?": "relocation",
        "Have you previously worked for this company?": "previously_worked_here",
    }
    for question, key in cases.items():
        assert answers_mod.is_attestation(question), question
        assert answers_mod.key_for_question(question) == key, question
    assert not answers_mod.is_attestation("Why do you want to work here?")
    assert answers_mod.is_attestation("Anything", model_category="eeo")
    assert answers_mod.key_for_question("Mobile phone number") == "phone"
    with pytest.raises(ValueError):
        answers_mod.set_answers({"not_a_key": "x"})
    filler = bank.as_filler_dict()
    assert filler["work_authorized"] == "Yes" and filler["questions"] == {}


def test_answers_cli_show_set_missing(env, monkeypatch):
    from typer.testing import CliRunner

    from jobwright import cli

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    r = CliRunner()
    assert r.invoke(cli.app, ["answers", "set", "criminal_record", "No"]).exit_code == 0
    out = r.invoke(cli.app, ["answers", "show"]).output
    assert "criminal_record" in out and "No" in out
    assert "All answers saved" in r.invoke(cli.app, ["answers", "missing"]).output
    assert r.invoke(cli.app, ["answers", "set", "bogus", "x"]).exit_code == 1


# ---------------------------------------------------------------------------
# Browser runs against the fake ATS
# ---------------------------------------------------------------------------


def test_live_apply_fills_from_answers_and_verifies(env):
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        res, client = run(job, [("snapshot", {}), *fill_form_steps(), *SUBMIT_AND_FINISH], dry_run=False)
        assert res.outcome == "applied", res.reasons
        assert res.verification_confidence in ("high", "medium")
        assert ats.post_paths() == ["/submit/std"]
        body = ats.posts[0][1].decode(errors="replace")
        assert "+1 415 555 0100" in body and "Alex Rivera" in body
    row = job_row(job["url"])
    assert row["applied_at"] and row["apply_status"] == "applied" and row["funnel_stage"] == "applied"
    sub = evidence.get_submission(res.submission_id)
    assert sub["outcome"] == "applied" and not sub["dry_run"]
    assert {"filled", "review", "confirmation"} <= set(sub["screenshots"])
    sources = {f["label"]: f["source"] for f in sub["fields"]}
    assert sources["Phone"] == "answer_bank"
    assert sources["Are you legally authorized to work in the United States?"] == "answer_bank"
    assert sources["Why do you want to work here?"] == "resume_ai"
    assert sources["Resume"] == "materials"
    assert sub["cost_usd"] > 0 and sub["steps"] >= 10
    # The usage ledger got the apply calls.
    rows = get_connection().execute("SELECT purpose, provider FROM llm_usage").fetchall()
    assert ("apply", "anthropic") in [tuple(r) for r in rows]
    # The prompt carries the answers but never the profile password.
    assert "never-use-this" not in client.all_text()
    assert "Decline to self-identify" in client.all_text()
    req = client.requests[0]
    assert req["model"] == "claude-sonnet-5-5" and req["output_config"] == {"effort": "medium"}
    assert req["fallbacks"] == "default"


def test_unknown_attestation_stops_and_asks(env):
    with FakeATS() as ats:
        job = add_job(ats.url("felony"))
        script = [("snapshot", {}), *fill_form_steps(),
                  ("select", {"ref": "@convicted", "option": "No", "source": "resume_ai", "category": None}),
                  ("click", {"ref": "@Submit application"}),
                  ("ask_human", {"kind": "answer", "prompt": "Have you ever been convicted of a felony?"}),
                  ("finish", {"status": "needs_answer", "summary": "",
                              "questions": ["Have you ever been convicted of a felony?"]})]
        res, client = run(job, script, dry_run=False)
        assert ats.posts == []  # never submitted
    assert res.outcome == "needs_answer"
    assert res.questions == ["Have you ever been convicted of a felony?"]
    assert any("NEEDS_ANSWER" in r for r in client.results)
    assert any("REFUSED: unanswered attestation" in r for r in client.results)
    assert job_row(job["url"])["apply_status"] == "needs_answer"
    pending = [p for p in hitl.list_pending() if p["kind"] == "answer"]
    assert len(pending) == 1 and "felony" in pending[0]["prompt"]
    assert any("I need your answer" in t and pending[0]["id"] in t for _, t in env["sent"])
    # The person's reply saves the answer for that question and re-opens the job.
    hitl.provide(pending[0]["id"], "No", by="whatsapp")
    assert answers_mod.load_answers().custom("Have you ever been convicted of a felony?") == "No"
    assert job_row(job["url"])["apply_status"] is None


def test_attestation_value_must_match_saved_answer(env):
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        script = [("snapshot", {}),
                  ("select", {"ref": "@legally authorized", "option": "No", "source": "answer_bank",
                              "category": None}),
                  ("finish", {"status": "failed", "summary": "stop", "questions": []})]
        _res, client = run(job, script, dry_run=True)
    assert any("REFUSED: the saved answer" in r and "'Yes'" in r for r in client.results)


def test_dry_run_never_submits(env):
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        script = [("snapshot", {}), *fill_form_steps(), ("click", {"ref": "@Submit application"}),
                  ("finish", {"status": "dry_run_ready", "summary": "ready", "questions": []})]
        res, client = run(job, script, dry_run=True)
        assert ats.posts == []
    assert any("DRY RUN: final submit is blocked" in r for r in client.results)
    assert res.outcome == "dry_run"
    sub = evidence.get_submission(res.submission_id)
    assert sub["dry_run"] and {"filled", "review"} <= set(sub["screenshots"])
    assert len(sub["fields"]) >= 7
    row = job_row(job["url"])
    assert row["applied_at"] is None and row["apply_status"] is None


def test_dry_run_blocks_a_misread_submit_at_the_network(env):
    """Even a submit button the tools do not recognise cannot send anything in a dry run."""
    with FakeATS() as ats:
        job = add_job(ats.url("go"))
        script = [("snapshot", {}), ("click", {"ref": "@Go"}),
                  ("finish", {"status": "dry_run_ready", "summary": "", "questions": []})]
        res, _client = run(job, script, dry_run=True)
        assert ats.posts == []
    assert res.outcome == "dry_run"
    assert "dry-run POST" in transcript_text(res)


def test_dry_run_never_creates_accounts(env):
    with FakeATS() as ats:
        job = add_job(ats.url("acct"))
        script = [("snapshot", {}),
                  ("fill", {"ref": "@Email", "value": "user1@example.com", "source": "profile", "category": None}),
                  ("fill_secret", {"ref": "@Password", "name": "account_password"}),
                  ("click", {"ref": "@Create account"}),
                  ("finish", {"status": "dry_run_ready", "summary": "", "questions": []})]
        res, client = run(job, script, dry_run=True)
        assert ats.posts == []
    assert sum("DRY RUN" in r for r in client.results) >= 2
    assert not (env["dir"] / "secrets" / "apply.json").exists()
    assert res.outcome == "dry_run"


def test_live_account_password_is_typed_but_never_shown(env):
    with FakeATS() as ats:
        job = add_job(ats.url("acct"))
        script = [("snapshot", {}),
                  ("fill", {"ref": "@Email", "value": "user1@example.com", "source": "profile", "category": None}),
                  ("fill_secret", {"ref": "@Password", "name": "account_password"}),
                  ("click", {"ref": "@Create account"}),
                  ("snapshot", {}), *fill_form_steps(), *SUBMIT_AND_FINISH]
        res, client = run(job, script, dry_run=False)
        posted = dict(ats.posts)
    assert res.outcome == "applied"
    store_path = env["dir"] / "secrets" / "apply.json"
    assert stat.S_IMODE(os.stat(store_path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(store_path.parent).st_mode) == 0o700
    password = next(iter(json.loads(store_path.read_text()).values()))["value"]
    assert len(password) >= 16
    from urllib.parse import parse_qs

    assert parse_qs(posted["/account"].decode())["password"] == [password]
    assert password not in client.all_text()
    assert password not in transcript_text(res)
    sub = evidence.get_submission(res.submission_id)
    assert {"label": "Password", "value": "[secret]"}.items() <= next(
        f for f in sub["fields"] if f["label"] == "Password").items()


def test_captcha_pauses_and_resumes_after_provide(env):
    with FakeATS() as ats:
        job = add_job(ats.url("captcha"))
        script = [("snapshot", {}),
                  ("ask_human", {"kind": "captcha", "prompt": "CAPTCHA on the form"}),
                  ("snapshot", {}), *fill_form_steps(), *SUBMIT_AND_FINISH]
        provide_when_open("captcha", "", by="dashboard")
        res, client = run(job, script, dry_run=False, wait_s=20)
    assert any("CAPTCHA_DETECTED" in r for r in client.results)
    assert any("CAPTCHA is done" in r for r in client.results)
    assert res.outcome == "applied"
    rows = hitl.list_pending(None)
    cap = [r for r in rows if r["kind"] == "captcha"][0]
    assert cap["status"] == "resolved" and cap["resolved_by"] == "dashboard" and cap["resolved_value"] is None
    assert hitl.live_screenshot_path(cap["id"]).is_file()
    assert any(f"https://dash.example.com/apply/pending/{cap['id']}" in t for _, t in env["sent"])


def test_captcha_times_out_when_nobody_answers(env):
    with FakeATS() as ats:
        job = add_job(ats.url("captcha"))
        script = [("snapshot", {}), ("ask_human", {"kind": "captcha", "prompt": "CAPTCHA"}),
                  ("finish", {"status": "captcha_timeout", "summary": "no human", "questions": []})]
        res, _client = run(job, script, dry_run=False, wait_s=0.3)
        assert ats.posts == []
    assert res.outcome == "captcha_timeout"
    assert [r["status"] for r in hitl.list_pending(None)] == ["expired"]
    assert job_row(job["url"])["apply_status"] == "captcha_timeout"


def test_email_code_is_asked_in_the_group_and_never_reaches_the_model(env):
    with FakeATS() as ats:
        job = add_job(ats.url("code"))
        script = [("snapshot", {}), *fill_form_steps(), ("click", {"ref": "@Submit application"}),
                  ("snapshot", {}),
                  ("ask_human", {"kind": "email_code", "prompt": "Please paste the code from Example Co"}),
                  ("fill_secret", {"ref": "@Verification code", "name": "email_code"}),
                  ("click", {"ref": "@Verify"}),
                  ("snapshot", {}),
                  ("finish", {"status": "submitted", "summary": "verified", "questions": []})]
        provide_when_open("email_code", "123456")
        res, client = run(job, script, dry_run=False, wait_s=20)
        assert "/verify/code" in ats.post_paths()
    assert res.outcome == "applied", res.reasons
    assert "123456" not in client.all_text()
    assert "123456" not in transcript_text(res)
    row = [r for r in hitl.list_pending(None) if r["kind"] == "email_code"][0]
    assert row["resolved_value"] is None and row["status"] == "resolved"
    raw = get_connection().execute("SELECT resolved_value, value_hash FROM pending_inputs WHERE id = ?",
                                   (row["id"],)).fetchone()
    assert raw["resolved_value"] is None and len(raw["value_hash"]) == 64
    assert not list(hitl.inbox_dir().glob(row["id"]))  # handoff file removed
    assert any("paste the code from Example Co" in t for target, t in env["sent"] if target == GROUP)


def test_unconfirmed_submit_is_unverified_not_applied(env):
    with FakeATS() as ats:
        job = add_job(ats.url("bad"))
        res, _client = run(job, [("snapshot", {}), *fill_form_steps(), *SUBMIT_AND_FINISH], dry_run=False)
    assert res.outcome == "unverified"
    row = job_row(job["url"])
    assert row["applied_at"] is None and row["apply_status"] == "unverified"
    assert row["funnel_stage"] == "backlog"
    sub = evidence.get_submission(res.submission_id)
    assert sub["verification_confidence"] in ("none", "low")


def test_agent_claiming_submit_without_clicking_is_a_failure(env):
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        res, _ = run(job, [("snapshot", {}), ("finish", {"status": "submitted", "summary": "", "questions": []})],
                     dry_run=False)
        assert ats.posts == []
    assert res.outcome == "failed" and job_row(job["url"])["applied_at"] is None


def test_navigate_outside_allowlist_is_blocked(env):
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        script = [("navigate", {"url": "https://mail.example.org/inbox"}),
                  ("finish", {"status": "failed", "summary": "", "questions": []})]
        _res, client = run(job, script, dry_run=True)
    assert any(r.startswith("BLOCKED") for r in client.results)


def test_step_limit_stops_the_agent(env, monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_APPLY_MAX_STEPS", "3")
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        res, _ = run(job, [("snapshot", {})] * 10, dry_run=True)
    assert res.outcome == "failed"
    assert "step_limit" in (evidence.get_submission(res.submission_id)["error"] or "") or res.reasons


# ---------------------------------------------------------------------------
# Deterministic filler first, agent fallback
# ---------------------------------------------------------------------------


class _FakeFiller:
    ats = "fake"

    def __init__(self, result):
        self.result = result
        self.submitted = False

    def fill(self, page, job, answers, materials):
        assert answers["work_authorized"] == "Yes" and materials["profile"]["full_name"] == "Alex Rivera"
        page.fill("#name", "Alex Rivera")
        page.fill("#email", "user1@example.com")
        return self.result

    def submit(self, page):
        self.submitted = True
        page.click("button[type=submit]")
        return True

    def verify(self, page):
        return True, "high", "fake"


def _with_filler(monkeypatch, filler):
    monkeypatch.setattr("jobwright.apply.runner.get_filler", lambda url, cb=None: filler)


def test_filler_dry_run_stops_before_submit(env, monkeypatch):
    from jobwright.apply.fill import FieldRecord, FillResult

    filler = _FakeFiller(FillResult(fields=[FieldRecord("Full name", "Alex Rivera", "resume", True)],
                                    ready_to_submit=True))
    _with_filler(monkeypatch, filler)
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        res, client = run(job, [], dry_run=True)
        assert ats.posts == [] and not filler.submitted
    assert res.outcome == "dry_run" and client.requests == []
    assert evidence.get_submission(res.submission_id)["provider"] == "filler:fake"


def test_filler_live_submits_and_verifies(env, monkeypatch):
    from jobwright.apply.fill import FieldRecord, FillResult

    filler = _FakeFiller(FillResult(fields=[FieldRecord("Full name", "Alex Rivera", "resume", True)],
                                    ready_to_submit=True))
    _with_filler(monkeypatch, filler)
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        res, _ = run(job, [], dry_run=False)
        assert ats.post_paths() == ["/submit/std"] and filler.submitted
    assert res.outcome == "applied"


def test_filler_attestation_from_ai_is_refused(env, monkeypatch):
    from jobwright.apply.fill import FieldRecord, FillResult

    filler = _FakeFiller(FillResult(fields=[
        FieldRecord("Are you legally authorized to work in the United States?", "Yes", "ai", True)],
        ready_to_submit=True))
    _with_filler(monkeypatch, filler)
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        res, _ = run(job, [], dry_run=False)
        assert ats.posts == [] and not filler.submitted
    assert res.outcome == "needs_answer"


def test_filler_needs_answer_skips_job(env, monkeypatch):
    from jobwright.apply.fill import FillResult, Need

    filler = _FakeFiller(FillResult(needs=[Need("answer", "criminal_record: Have you ever been convicted?")]))
    _with_filler(monkeypatch, filler)
    with FakeATS() as ats:
        res, client = run(add_job(ats.url("std")), [], dry_run=False)
    assert res.outcome == "needs_answer" and res.questions == ["Have you ever been convicted?"]
    assert client.requests == []


def test_filler_trouble_falls_back_to_agent(env, monkeypatch):
    from jobwright.apply.fill import FillResult, Need

    filler = _FakeFiller(FillResult(needs=[Need("answer", "form: could not read the fake form")]))
    _with_filler(monkeypatch, filler)
    with FakeATS() as ats:
        job = add_job(ats.url("std"))
        res, client = run(job, [("snapshot", {}), ("finish", {"status": "dry_run_ready", "summary": "",
                                                               "questions": []})], dry_run=True)
    assert client.requests and res.outcome == "dry_run"


# ---------------------------------------------------------------------------
# Safety rails
# ---------------------------------------------------------------------------


def _fake_submission(job: dict, outcome: str = "applied", dry_run: bool = False, days_ago: int = 0) -> None:
    sid = evidence.start_submission(job, evidence.new_run_id(), ats=None, provider="test", model=None,
                                    dry_run=dry_run)
    evidence.finish_submission(sid, outcome=outcome, fields=[], needs=[], screenshots={}, transcript_path=None)
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = get_connection()
    conn.execute("UPDATE submissions SET started_at = ? WHERE id = ?", (when, sid))
    conn.commit()


def test_kill_switch_stops_everything(env, monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_APPLY_KILL", "1")
    job = add_job("https://jobs.example.com/a/1")
    res = apply_job(job, dry_run=True, user_id="alex", agent=object())
    assert res.outcome == "skipped" and any("kill switch" in r for r in res.reasons)
    assert evidence.list_submissions() == []
    monkeypatch.setenv("JOBWRIGHT_APPLY_KILL", "0")
    assert not safety.kill_switch_on()


def test_live_needs_apply_enabled_but_dry_run_does_not(env):
    users_mod.update_user("alex", apply_enabled=False)
    assert "apply_enabled is false" in safety.check_profile("alex", live=True).reasons
    assert safety.check_profile("alex", live=False).ok


def test_daily_cap_and_auto_pause(env):
    job = add_job("https://jobs.example.com/a/1")
    _fake_submission(job, "applied")
    _fake_submission(job, "applied")
    assert any("daily cap" in r for r in safety.check_profile("alex", live=True).reasons)
    _fake_submission(job, "applied", dry_run=True)  # dry runs never count
    assert safety.live_submissions_today() == 2
    _fake_submission(job, "failed")
    _fake_submission(job, "unverified")
    assert safety.consecutive_failures() == 2
    assert safety.maybe_auto_pause("alex")
    user = users_mod.get_user("alex")
    assert user.apply_paused and "in a row" in user.apply_paused_reason


def test_dedupe_employer_cap_score_and_linkedin(env):
    a = add_job("https://jobs.example.com/a/1", company="Example Co, Inc.", dedupe_key="example co|analyst|sf")
    b = add_job("https://jobs.example.com/a/2", company="Example Co", dedupe_key="example co|analyst|sf")
    c = add_job("https://jobs.example.com/a/3", company="Example Co", title="Engineer", dedupe_key="example co|eng|sf")
    low = add_job("https://jobs.example.com/a/4", company="Other Co", score=7)
    li = add_job("https://www.linkedin.com/jobs/view/1234567890", company="Third Co", site="linkedin",
                 application_url="https://www.linkedin.com/jobs/view/1234567890")
    resolved = add_job("https://www.linkedin.com/jobs/view/1234567891", company="Fourth Co", site="linkedin",
                       application_url="https://boards.greenhouse.io/fourthco/jobs/1")
    assert safety.check_job(b, "alex", live=True).ok
    _fake_submission(a, "applied")
    assert any("same company and title" in r for r in safety.check_job(b, "alex", live=True).reasons)
    assert any("last 30 days" in r for r in safety.check_job(c, "alex", live=True).reasons)
    assert any("below 8" in r for r in safety.check_job(low, "alex", live=True).reasons)
    assert any("LinkedIn" in r for r in safety.check_job(li, "alex", live=True).reasons)
    assert safety.check_job(resolved, "alex", live=True).ok
    conn = get_connection()
    conn.execute("UPDATE submissions SET started_at = ?", ((datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),))
    conn.commit()
    assert safety.check_job(c, "alex", live=True).ok


# ---------------------------------------------------------------------------
# Picks with a veto window
# ---------------------------------------------------------------------------


class _Res:
    def __init__(self, outcome, submission_id=None):
        self.outcome, self.submission_id, self.reasons = outcome, submission_id, []


def test_pick_posts_and_veto_window(env):
    a = add_job("https://jobs.example.com/p/1", company="Alpha", score=9)
    b = add_job("https://jobs.example.com/p/2", company="Beta", score=8)
    add_job("https://jobs.example.com/p/3", company="Gamma", score=7)
    add_job("https://jobs.example.com/p/4", company="Alpha", title="Other", score=8)  # same employer
    now = datetime.now(timezone.utc)
    result = auto.pick("alex", now=now)
    picks = result["picks"]
    assert [p["job_url"] for p in picks] == [a["url"], b["url"]]
    assert picks[0]["apply_after"] == (now + timedelta(minutes=180)).isoformat(timespec="seconds")
    msg = env["sent"][-1][1]
    assert "I'll apply to these at" in msg and "skip all" in msg and "1. *Data Analyst* @ Alpha" in msg
    assert auto.pick("alex", now=now)["reasons"] == ["today's picks are already made"]
    vetoed = auto.veto(2, number=True, by="whatsapp", now=now + timedelta(minutes=5))
    assert vetoed[0]["status"] == "vetoed" and vetoed[0]["vetoed_by"] == "whatsapp"
    with pytest.raises(auto.VetoError, match="already vetoed"):
        auto.veto(picks[1]["id"], now=now)
    with pytest.raises(auto.VetoError, match="Too late"):
        auto.veto(picks[0]["id"], now=now + timedelta(minutes=181))

    calls = []
    assert auto.due("alex", now=now + timedelta(minutes=10), apply_fn=lambda *a, **k: _Res("applied")) == []
    done = auto.due("alex", now=now + timedelta(minutes=181),
                    apply_fn=lambda job, **k: calls.append((job["url"], k)) or _Res("applied"))
    assert calls == [(a["url"], {"dry_run": False, "user_id": "alex"})]
    assert [p["status"] for p in done] == ["applied"]
    report = env["sent"][-1][1]
    assert "Applied today" in report and "1 of 1" in report
    # The next day's pick never brings back the vetoed job.
    later = auto.candidates("alex", 5)
    assert b["url"] not in [j["url"] for j in later] and a["url"] not in [j["url"] for j in later]


def test_veto_all_and_after_deadline(env):
    add_job("https://jobs.example.com/v/1", company="Alpha")
    add_job("https://jobs.example.com/v/2", company="Beta")
    now = datetime.now(timezone.utc)
    auto.pick("alex", now=now)
    assert len(auto.veto("all", now=now)) == 2
    with pytest.raises(auto.VetoError, match="Nothing left"):
        auto.veto("all", now=now)
    assert auto.due("alex", now=now + timedelta(days=1), apply_fn=lambda *a, **k: _Res("applied")) == []


def test_auto_mode_applies_right_after_picking(env):
    users_mod.update_user("alex", apply_mode="auto")
    add_job("https://jobs.example.com/m/1", company="Alpha")
    out = auto.run_auto("alex", apply_fn=lambda job, **k: _Res("applied"))
    assert [p["status"] for p in out["applied"]] == ["applied"]
    assert not any("I'll apply to these" in t for _, t in env["sent"])


def test_due_keeps_picks_planned_when_paused(env, monkeypatch):
    add_job("https://jobs.example.com/k/1", company="Alpha")
    now = datetime.now(timezone.utc)
    auto.pick("alex", now=now)
    monkeypatch.setenv("JOBWRIGHT_APPLY_KILL", "1")
    assert auto.due("alex", now=now + timedelta(days=1), apply_fn=lambda *a, **k: _Res("applied")) == []
    assert auto.list_picks()[0]["status"] == "planned"


def test_due_tailors_missing_materials(env):
    job = add_job("https://jobs.example.com/t/1", company="Alpha", materials=False)
    now = datetime.now(timezone.utc)
    users_mod.update_user("alex", apply_veto_minutes=0)
    auto.pick("alex", now=now)
    tailored = []

    def tailor(url):
        tailored.append(url)
        conn = get_connection()
        conn.execute("UPDATE jobs SET tailored_resume_path = 'x.md', cover_letter_path = 'c.md' WHERE url = ?", (url,))
        conn.commit()
        return 0

    done = auto.due("alex", now=now + timedelta(seconds=1), apply_fn=lambda j, **k: _Res("needs_answer"),
                    tailor_fn=tailor)
    assert tailored == [job["url"]] and done[0]["status"] == "skipped"


def test_veto_cli_and_provide_cli(env, monkeypatch):
    from typer.testing import CliRunner

    from jobwright import cli

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    add_job("https://jobs.example.com/c/1", company="Alpha")
    auto.pick("alex")
    r = CliRunner()
    res = r.invoke(cli.app, ["apply", "veto", "1", "--number", "--by", "whatsapp"])
    assert res.exit_code == 0 and "Skipped" in res.output
    res = r.invoke(cli.app, ["apply", "veto", "1", "--number"])
    assert res.exit_code == 1 and "Too late" in res.output
    row = hitl.create_pending("email_code", "Please paste the code from Alpha", job={"company": "Alpha"})
    res = r.invoke(cli.app, ["apply", "provide", row["id"], "654321"])
    assert res.exit_code == 0 and "Code passed on" in res.output
    assert hitl.wait_for(row["id"], timeout_s=1) == "654321"
    assert r.invoke(cli.app, ["apply", "provide", row["id"], "1"]).exit_code == 1  # already resolved


# ---------------------------------------------------------------------------
# API + Hermes prompt
# ---------------------------------------------------------------------------


@pytest.fixture
def api(env, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from jobwright.web import session as session_mod
    from jobwright.web.app import app

    monkeypatch.setenv("JOBWRIGHT_DASHBOARD_USER", "alex")
    session_mod.forget_initialized()
    with TestClient(app) as client:
        client.cookies.set("jobwright_user", "alex")
        # The app parks the process default on an empty dir; tests write as alex.
        config.set_active_user("alex")
        close_connection()
        yield client


def test_answers_api(api):
    got = api.get("/api/answers").json()
    assert got["answers"]["work_authorized"]["value"] == "Yes" and "criminal_record" in got["missing"]
    assert any(f["key"] == "eeo_gender" and f["attestation"] for f in got["fields"])
    res = api.put("/api/answers", json={"answers": {"criminal_record": "No", "pronouns": None}})
    assert res.status_code == 200 and res.json()["answers"]["criminal_record"]["source"] == "settings"
    assert api.put("/api/answers", json={"answers": {"nope": "x"}}).status_code == 400
    status = api.get("/api/apply/status").json()
    assert status["apply_mode"] == "veto" and status["apply_daily_cap"] == 2 and status["apply_min_score"] == 8


def test_pending_and_evidence_api(api):
    row = hitl.create_pending("captcha", "CAPTCHA on Example Co", job={"company": "Example Co"})
    hitl.live_screenshot_path(row["id"]).write_bytes(b"\x89PNG fake")
    assert api.get(f"/api/apply/pending/{row['id']}").json()["has_screenshot"] is True
    assert api.get(f"/api/apply/pending/{row['id']}/screenshot").status_code == 200
    assert api.post(f"/api/apply/pending/{row['id']}/provide", json={}).json()["status"] == "resolved"
    assert api.post(f"/api/apply/pending/{row['id']}/provide", json={}).status_code == 409

    job = add_job("https://jobs.example.com/e/1")
    rid = evidence.new_run_id()
    sid = evidence.start_submission(job, rid, ats="greenhouse", provider="test", model=None, dry_run=True)
    (evidence.run_dir(rid) / "review.png").write_bytes(b"\x89PNG fake")
    evidence.finish_submission(sid, outcome="dry_run", fields=[], needs=[], screenshots={"review": "review.png",
                               "evil": "../../profile.json"}, transcript_path=None)
    sub = api.get(f"/api/apply/submissions/{sid}").json()
    assert sub["outcome"] == "dry_run" and "run_dir" not in sub and "transcript_path" not in sub
    assert api.get(f"/api/apply/submissions/{sid}/screenshots/review").status_code == 200
    assert api.get(f"/api/apply/submissions/{sid}/screenshots/evil").status_code == 404


def test_veto_api(api):
    add_job("https://jobs.example.com/x/1", company="Alpha")
    pick = auto.pick("alex")["picks"][0]
    assert api.post(f"/api/apply/picks/{pick['id']}/veto").json()["picks"][0]["status"] == "vetoed"
    assert api.post(f"/api/apply/picks/{pick['id']}/veto").status_code == 409
    assert api.get(f"/api/apply/picks?job={pick['job_id']}").json()["picks"][0]["status"] == "vetoed"


def test_hermes_group_prompt_knows_veto_and_codes(env):
    from jobwright import hermes_channels as hc

    text = hc.render_system_prompt(users_mod.get_user("alex"))
    assert "jobwright --user alex apply veto --number 2 --by whatsapp" in text
    assert "jobwright --user alex apply veto all" in text
    assert "jobwright --user alex apply provide <ref> <code>" in text
    assert "Never read anyone's email" in text


# ---------------------------------------------------------------------------
# Prompt and legacy path hygiene
# ---------------------------------------------------------------------------


def test_prompt_is_honest_and_carries_no_secrets(env):
    from jobwright.apply.prompt import build_agent_system_prompt, build_prompt

    profile = json.loads((env["dir"] / "profile.json").read_text())
    text = build_agent_system_prompt(job={"url": "https://jobs.example.com/1", "title": "Analyst"}, profile=profile,
                                     answers=answers_mod.load_answers(), resume_text="SQL", dry_run=False,
                                     has_resume_file=True, has_cover_file=False)
    lowered = text.lower()
    for banned in ("whatever it takes", "capsolver", "don't sell short", "never-use-this", "gmail"):
        assert banned not in lowered
    assert "criminal_record [ATTESTATION]" in text and "(NOT SAVED)" in text
    assert "Never claim experience" in text
    legacy = build_prompt({"url": "https://jobs.example.com/1"}, "SQL")
    assert "never-use-this" not in legacy and "RESULT:DRYRUN" in legacy


def test_legacy_path_has_no_gmail_pinned_mcp_and_fresh_profiles(env):
    from jobwright.apply import chrome, launcher

    servers = launcher._make_mcp_config(9222)["mcpServers"]
    assert list(servers) == ["playwright"]
    assert all("@latest" not in a for a in servers["playwright"]["args"])
    profile = chrome.setup_worker_profile(0)
    assert profile.is_relative_to(Path(config.APP_DIR)) and list(profile.iterdir()) == []
    assert launcher.run_job({"title": "x"}, port=9222, dry_run=False)[0] == "failed:legacy_provider_live_disabled"
    assert not hasattr(config, "get_chrome_user_data")
