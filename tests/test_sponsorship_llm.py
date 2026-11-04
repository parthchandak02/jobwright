"""Sponsorship LLM tie-breaker: fake client, no network."""

from __future__ import annotations

import pytest

from jobwright.enrichment import sponsorship as sp

AMBIGUOUS = (
    "Example Org welcomes applicants. Candidates should describe their work authorization "
    "and visa situation in the application."
)


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def chat(self, messages, **_kw):
        self.messages = messages
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture()
def client(monkeypatch):
    def install(reply):
        c = FakeClient(reply)
        monkeypatch.setattr("jobwright.llm.get_client", lambda: c)
        return c
    return install


def test_llm_enabled_flags(monkeypatch):
    assert sp._llm_enabled() is True  # conftest sets a fake FIREWORKS_API_KEY
    monkeypatch.setenv("SPONSORSHIP_LLM", "off")
    assert sp._llm_enabled() is False
    monkeypatch.delenv("SPONSORSHIP_LLM")
    monkeypatch.delenv("FIREWORKS_API_KEY")
    assert sp._llm_enabled() is False


def test_excerpt_keeps_head_and_tail():
    text = "A" * 5000 + "MIDDLE" + "Z" * 5000
    out = sp._excerpt(text, limit=1000)
    assert out.startswith("A" * 500) and out.endswith("Z" * 500) and "MIDDLE" not in out
    assert sp._excerpt("short") == "short"


@pytest.mark.parametrize("label,expected", [
    ("offers_sponsorship", "required"),
    ("no_sponsorship", "not_required"),
    ("not_mentioned", "not_found"),
])
def test_classify_uses_llm_for_ambiguous_signal(client, label, expected):
    assert sp.derive_sponsorship_status(AMBIGUOUS) == "not_found"
    c = client(f'{{"status": "{label}"}}')
    assert sp.classify_sponsorship(AMBIGUOUS) == expected
    assert "JOB POSTING:" in c.messages[1]["content"]


def test_classify_llm_failure_or_garbage_falls_back(client):
    client(RuntimeError("provider down"))
    assert sp.classify_sponsorship(AMBIGUOUS) == "not_found"
    client('{"status": "maybe"}')
    assert sp.classify_sponsorship(AMBIGUOUS) == "not_found"


def test_classify_regex_decisive_never_calls_llm(monkeypatch):
    def boom():
        raise AssertionError("LLM must not run when the regex decides")

    monkeypatch.setattr("jobwright.llm.get_client", boom)
    assert sp.classify_sponsorship("Visa sponsorship is available for this role.") == "required"
    assert sp.classify_sponsorship(AMBIGUOUS, use_llm=False) == "not_found"
