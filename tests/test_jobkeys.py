"""Deep-link job keys: WhatsApp daily list and /jobs/:id hit the API by 12-hex job_id.

``resolve_job_key`` turns that id into the row's URL (or unquotes a legacy full URL).
No dedicated coverage existed; a wrong 404 or decode would leave her unable to open
a job from the daily list.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi import HTTPException

from jobwright import config
from jobwright import users as users_mod
from jobwright.database import close_connection, get_connection, init_db, job_id_for_url
from jobwright.web.jobkeys import resolve_job_key


@pytest.fixture
def env():
    users_mod.add_user("alex", name="Alex Rivera")
    data = config.set_active_user("alex")
    close_connection()
    init_db()
    yield data
    close_connection()


def _insert(url: str, title: str = "Analyst") -> str:
    jid = job_id_for_url(url)
    conn = get_connection()
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, job_id, funnel_stage, discovered_at) "
        "VALUES (?, ?, 'Example Co', 'greenhouse', ?, 'backlog', datetime('now'))",
        (url, title, jid),
    )
    conn.commit()
    return jid


def test_resolve_job_id_returns_stored_url(env):
    url = "https://boards.greenhouse.io/example/jobs/1"
    jid = _insert(url)
    assert resolve_job_key(jid) == url


def test_unknown_job_id_is_404(env):
    with pytest.raises(HTTPException) as exc:
        resolve_job_key("000000000000")
    assert exc.value.status_code == 404
    assert "not found" in str(exc.value.detail).lower()


def test_full_url_passthrough_and_double_encoding(env):
    raw = "https://example.com/jobs/role?a=1&b=two words"
    assert resolve_job_key(raw) == raw
    # Older clients double-encoded the path segment; unquote once restores it.
    assert resolve_job_key(quote(raw, safe="")) == raw


def test_non_hex_twelve_char_key_is_treated_as_url(env):
    # Exactly 12 chars but not hex: not a job_id, so no DB lookup / 404.
    assert resolve_job_key("notahexjobid") == "notahexjobid"
