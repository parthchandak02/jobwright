"""Unit coverage for apply HITL: WhatsApp messages, ask/provide, hand-off notify.

Locks down the path where Claude pauses for a person's answer or hands a filled
form back. No browser, no MCP. Placeholders only (example.com JIDs).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import pytest

from jobwright import config
from jobwright import users as users_mod
from jobwright.apply import answers as answers_mod
from jobwright.apply import hitl
from jobwright.database import close_connection, get_connection, init_db, job_id_for_url


@pytest.fixture
def env():
    users_mod.add_user("alex", name="Alex Rivera", apply_enabled=True)
    users_mod.update_user("alex", apply_via="connector")
    data = config.set_active_user("alex")
    close_connection()
    init_db()
    (data / "profile.json").write_text(json.dumps({
        "personal": {
            "full_name": "Alex Rivera",
            "email": "user1@example.com",
            "phone": "+1 415 555 0100",
            "city": "Oakland",
        },
        "application_answers": {},
    }), encoding="utf-8")
    yield data
    close_connection()


def _job(**kw) -> dict:
    url = kw.pop("url", "https://jobs.example.com/j/1")
    base = {
        "url": url,
        "job_id": job_id_for_url(url),
        "company": "Example Co",
        "title": "Analyst",
        "site": "greenhouse",
        "application_url": "https://boards.example.com/jobs/1",
    }
    base.update(kw)
    return base


def test_wait_minutes_clamps_and_ignores_junk(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_APPLY_WAIT_MINUTES", "0")
    assert hitl.wait_minutes() == 1
    monkeypatch.setenv("JOBWRIGHT_APPLY_WAIT_MINUTES", "999")
    assert hitl.wait_minutes() == 120
    monkeypatch.setenv("JOBWRIGHT_APPLY_WAIT_MINUTES", "nope")
    assert hitl.wait_minutes() == hitl.DEFAULT_WAIT_MINUTES


def test_render_message_covers_each_kind(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_PUBLIC_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("JOBWRIGHT_APPLY_WAIT_MINUTES", "15")
    email = hitl.render_message({"id": "abc12345", "kind": "email_code", "company": "Example Co",
                                 "prompt": "code"}, title="Analyst")
    assert "paste the code from Example Co" in email and "Ref abc12345" in email and "15 minutes" in email
    captcha = hitl.render_message({"id": "cap99999", "kind": "captcha", "company": "Example Co",
                                   "prompt": "CAPTCHA"})
    assert "https://app.example.com/apply/pending/cap99999" in captcha
    answer = hitl.render_message({"id": "ans11111", "kind": "answer", "company": "Example Co",
                                  "prompt": "Do you need sponsorship?"})
    assert "Do you need sponsorship?" in answer and "skipped this job" in answer


def test_render_questions_and_handoff_include_links_and_notes(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_PUBLIC_BASE_URL", "https://app.example.com")
    rows = [{
        "id": "q1aaaaaa", "company": "Example Co", "prompt": "Desired pay?",
        "choices": ["100k", "150k"],
    }]
    text = hitl.render_questions(rows, title="Analyst")
    assert "Desired pay?" in text and "100k / 150k" in text
    assert "https://app.example.com/profile?tab=about#application-details" in text
    job = _job()
    handoff = hitl.render_handoff(job, "  Please  click  submit  ", "https://app.example.com/")
    assert "Analyst at Example Co" in handoff
    assert "What's left: Please click submit" in handoff
    assert "Form: https://boards.example.com/jobs/1" in handoff
    assert f"In jobwright: https://app.example.com/jobs/{job['job_id']}" in handoff
    bare = hitl.render_handoff({"title": "", "company": ""}, "", "https://app.example.com")
    assert bare.startswith("📝 A job:") and "What's left" not in bare and "Form:" not in bare


def test_ask_questions_reuses_saved_answers_and_dedupes(env):
    job = _job()
    answers_mod.set_custom_answer("Desired pay?", "150000", source="settings")
    out = hitl.ask_questions([
        {"text": "Desired pay?"},
        {"text": "When can you start?", "choices": ["ASAP", "2 weeks"], "key": "start_date"},
        {"text": "When can you start?"},
    ], job=job)
    assert out[0] == {"question": "Desired pay?", "status": "answered", "value": "150000"}
    assert out[1]["status"] == "asked" and out[1]["id"] and out[1]["choices"] == ["ASAP", "2 weeks"]
    assert out[1]["saves_to"] == "start_date"
    assert out[2]["status"] == "asked" and out[2]["id"] == out[1]["id"]
    with pytest.raises(ValueError, match="word for word"):
        hitl.ask_questions([{"text": "no"}], job=job)
    with pytest.raises(ValueError, match="Unknown answer key"):
        hitl.ask_questions([{"text": "Anything?", "key": "not_a_real_key"}], job=job)


def test_provide_answer_saves_bank_and_clears_needs_answer(env):
    job = _job()
    conn = get_connection()
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, fit_score, job_id, funnel_stage, apply_status, "
        "discovered_at) VALUES (?, 'Analyst', 'Example Co', 'greenhouse', 9, ?, 'prepare', "
        "'needs_answer', ?)",
        (job["url"], job["job_id"], datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    asked = hitl.ask_questions(
        [{"text": "Do you require sponsorship to work in the US?", "key": "requires_sponsorship"}],
        job=job,
    )
    pending_id = asked[0]["id"]
    resolved = hitl.provide(pending_id, "No", by="whatsapp")
    assert resolved["status"] == "resolved"
    bank = answers_mod.load_answers()
    assert bank.custom("Do you require sponsorship to work in the US?") == "No"
    assert bank.get("requires_sponsorship") == "No"
    row = conn.execute("SELECT apply_status FROM jobs WHERE url = ?", (job["url"],)).fetchone()
    assert row["apply_status"] is None
    recent = hitl.answered_questions()
    assert any(r["id"] == pending_id and r["resolved_value"] == "No" for r in recent)


def test_provide_refusals_and_cancel(env):
    row = hitl.create_pending("email_code", "Paste the code", job=_job())
    with pytest.raises(hitl.ProvideError, match="No request"):
        hitl.provide("zzzzzzzz", "123456")
    with pytest.raises(hitl.ProvideError, match="Empty value"):
        hitl.provide(row["id"], "   ")
    with pytest.raises(hitl.ProvideError, match="verification code"):
        hitl.provide(row["id"], "x" * 65)
    hitl.cancel(row["id"])
    with pytest.raises(hitl.ProvideError, match="already cancelled"):
        hitl.provide(row["id"], "123456")
    expired = hitl.create_pending("captcha", "CAPTCHA", job=_job(url="https://jobs.example.com/j/2"))
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
    conn = get_connection()
    conn.execute("UPDATE pending_inputs SET expires_at = ? WHERE id = ?", (past, expired["id"]))
    conn.commit()
    with pytest.raises(hitl.ProvideError, match="expired"):
        hitl.provide(expired["id"], "solved")


def test_notify_paths_stamp_and_skip_without_chat(env, monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_PUBLIC_BASE_URL", "https://app.example.com")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr("jobwright.notify.send_via_hermes", lambda msg, target: sent.append((target, msg)))

    users_mod.update_user("alex", whatsapp_target="")
    row = hitl.create_pending("answer", "Desired pay?", job=_job())
    assert hitl.notify(row, "alex") is False
    assert hitl.notify_questions([row], "alex") is False
    assert hitl.notify_handoff(_job(), "click submit", "alex") is False
    assert not sent

    users_mod.update_user("alex", whatsapp_target="whatsapp:120363999999999901@g.us")
    assert hitl.notify(row, "alex") is True
    assert sent and "Desired pay?" in sent[-1][1]
    stamped = hitl.get_pending(row["id"])
    assert stamped and stamped["notified_at"]
    # Already notified: notify_questions skips those rows.
    assert hitl.notify_questions([stamped], "alex") is False

    other = hitl.create_pending(
        "answer", "When can you start?", job=_job(url="https://jobs.example.com/j/3"),
        choices=["ASAP"],
    )
    assert hitl.notify_questions([other], "alex", title="Analyst") is True
    assert "When can you start?" in sent[-1][1]
    assert hitl.get_pending(other["id"])["notified_at"]

    assert hitl.notify_handoff(_job(), "Need your click", "alex") is True
    assert "Need your click" in sent[-1][1]

    captcha = hitl.create_pending("captcha", "CAPTCHA", job=_job(url="https://jobs.example.com/j/4"))
    monkeypatch.setenv("JOBWRIGHT_OPS_TARGET", "whatsapp:14155550100@s.whatsapp.net")
    before = len(sent)
    assert hitl.notify(captcha, "alex") is True
    targets = [t for t, _ in sent[before:]]
    assert "whatsapp:120363999999999901@g.us" in targets
    assert "whatsapp:14155550100@s.whatsapp.net" in targets


def test_notify_handoff_treats_uncertain_as_sent(env, monkeypatch):
    from jobwright.notify import SendUncertain

    users_mod.update_user("alex", whatsapp_target="whatsapp:120363999999999901@g.us")

    def boom(_msg, _target):
        raise SendUncertain("timeout")

    monkeypatch.setattr("jobwright.notify.send_via_hermes", boom)
    assert hitl.notify_handoff(_job(), "notes", "alex") is True

    def hard(_msg, _target):
        raise RuntimeError("bridge down")

    monkeypatch.setattr("jobwright.notify.send_via_hermes", hard)
    assert hitl.notify_handoff(_job(), "notes", "alex") is False


def test_pending_link_uses_public_base(monkeypatch):
    monkeypatch.setenv("JOBWRIGHT_PUBLIC_BASE_URL", "https://app.example.com/")
    assert hitl.pending_link("abc12345") == "https://app.example.com/apply/pending/abc12345"
