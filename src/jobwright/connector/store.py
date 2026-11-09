"""Connector sign-in state: one small SQLite file shared by every profile.

``<users root>/connector.sqlite`` (``JOBWRIGHT_CONNECTOR_DB`` overrides), mode
0600. Only SHA-256 hashes of codes, tokens, consent nonces and download links
are stored, never the values. A *grant* is one person's approval of one Claude
client for one profile; tokens hang off a grant, so revoking a grant (from the
dashboard, ``/oauth/revoke`` or refresh-token reuse) ends every token at once.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

ACCESS_SECONDS = 3600
REFRESH_SECONDS = 30 * 86_400
CODE_SECONDS = 300
CONSENT_SECONDS = 600
DOWNLOAD_SECONDS = 15 * 60
# A link may be fetched a few times within its lifetime (the page's upload snippet, a retry, the person
# opening it in a tab), never more.
DOWNLOAD_MAX_USES = 5
# A rotated refresh token is kept (hash only) this long so a replay is noticed.
ROTATED_KEEP_SECONDS = REFRESH_SECONDS

SCOPES = ("jobs:read", "jobs:write", "apply")
SCOPE_LABELS = {
    "jobs:read": "See your jobs, scores, picks and saved answers",
    "jobs:write": "Rate and move jobs, save answers and tailored materials, skip picks",
    "apply": "Start applications and record what was sent (in your own browser)",
}
# Accepted in requests (Claude asks for it to get a refresh token) but not a permission.
EXTRA_SCOPES = ("offline_access",)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, redirect_uris TEXT NOT NULL,
    created_at INTEGER NOT NULL, last_used_at INTEGER
);
CREATE TABLE IF NOT EXISTS consents (
    hash TEXT PRIMARY KEY, email TEXT NOT NULL, params TEXT NOT NULL, expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS codes (
    hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_id TEXT NOT NULL, email TEXT NOT NULL,
    redirect_uri TEXT NOT NULL, challenge TEXT NOT NULL, scope TEXT NOT NULL, resource TEXT,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS grants (
    id TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_id TEXT NOT NULL, email TEXT NOT NULL,
    scope TEXT NOT NULL, created_at INTEGER NOT NULL, last_used_at INTEGER,
    revoked_at INTEGER, revoked_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_grants_user ON grants(user_id, revoked_at);
CREATE TABLE IF NOT EXISTS tokens (
    hash TEXT PRIMARY KEY, kind TEXT NOT NULL, grant_id TEXT NOT NULL,
    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, rotated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tokens_grant ON tokens(grant_id);
CREATE TABLE IF NOT EXISTS downloads (
    hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, path TEXT NOT NULL, filename TEXT NOT NULL,
    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
);
"""

_lock = threading.Lock()
_ready: set[str] = set()


class InvalidGrant(Exception):
    """Code / refresh token unknown, expired, used, or for another client."""


def now() -> int:
    return int(time.time())


def digest(value: str) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(digest(a), digest(b))


def new_secret(prefix: str = "") -> str:
    return prefix + secrets.token_urlsafe(32)


def db_path() -> Path:
    override = os.environ.get("JOBWRIGHT_CONNECTOR_DB", "").strip()
    if override:
        return Path(override).expanduser()
    from jobwright import users

    return Path(users.USERS_ROOT) / "connector.sqlite"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    key = str(path)
    if key not in _ready:
        with _lock:
            if key not in _ready:
                path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(key, timeout=10)
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.executescript(_SCHEMA)
                    cols = {r[1] for r in conn.execute("PRAGMA table_info(downloads)").fetchall()}
                    if "uses" not in cols:
                        conn.execute("ALTER TABLE downloads ADD COLUMN uses INTEGER NOT NULL DEFAULT 0")
                    conn.commit()
                finally:
                    conn.close()
                try:
                    path.chmod(0o600)
                except OSError:
                    pass
                _ready.add(key)
    conn = sqlite3.connect(key, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def normalize_scope(raw: str | None) -> str:
    """Requested scope string -> granted permissions (all of them when none asked)."""
    asked = [s for s in (raw or "").split() if s]
    perms = [s for s in asked if s in SCOPES]
    if not perms:
        perms = list(SCOPES)
    return " ".join(s for s in SCOPES if s in perms)


def unknown_scopes(raw: str | None) -> list[str]:
    return [s for s in (raw or "").split() if s and s not in SCOPES and s not in EXTRA_SCOPES]


# ---------------------------------------------------------------------------
# Clients (dynamic registration)
# ---------------------------------------------------------------------------


def register_client(name: str, redirect_uris: list[str]) -> dict:
    client_id = "jwc_" + secrets.token_urlsafe(18)
    with connect() as conn:
        conn.execute("INSERT INTO clients (id, name, redirect_uris, created_at) VALUES (?, ?, ?, ?)",
                     (client_id, name, json.dumps(redirect_uris), now()))
    return {"client_id": client_id, "client_name": name, "redirect_uris": redirect_uris}


def get_client(client_id: str | None) -> dict | None:
    if not client_id:
        return None
    with connect() as conn:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if row is None:
        return None
    return {"client_id": row["id"], "client_name": row["name"],
            "redirect_uris": json.loads(row["redirect_uris"])}


# ---------------------------------------------------------------------------
# Consent nonces (CSRF for the consent form) and authorization codes
# ---------------------------------------------------------------------------


def create_consent(email: str, params: dict) -> str:
    nonce = new_secret()
    with connect() as conn:
        conn.execute("DELETE FROM consents WHERE expires_at < ?", (now(),))
        conn.execute("INSERT INTO consents (hash, email, params, expires_at) VALUES (?, ?, ?, ?)",
                     (digest(nonce), email, json.dumps(params), now() + CONSENT_SECONDS))
    return nonce


def take_consent(nonce: str, email: str) -> dict | None:
    """The authorize request a consent form was shown for (one use, same login only)."""
    key = digest(nonce)
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM consents WHERE hash = ?", (key,)).fetchone()
        conn.execute("DELETE FROM consents WHERE hash = ?", (key,))
        conn.execute("COMMIT")
    if row is None or row["expires_at"] < now() or row["email"] != email:
        return None
    return json.loads(row["params"])


def create_code(*, client_id: str, user_id: str, email: str, redirect_uri: str, challenge: str,
                scope: str, resource: str | None) -> str:
    code = new_secret("jwk_")
    with connect() as conn:
        conn.execute("DELETE FROM codes WHERE expires_at < ?", (now(),))
        conn.execute(
            "INSERT INTO codes (hash, client_id, user_id, email, redirect_uri, challenge, scope, resource, "
            "expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (digest(code), client_id, user_id, email, redirect_uri, challenge, scope, resource,
             now() + CODE_SECONDS),
        )
    return code


def take_code(code: str) -> dict | None:
    """Delete and return a code row: a code works once, even if the exchange then fails."""
    key = digest(code)
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM codes WHERE hash = ?", (key,)).fetchone()
        conn.execute("DELETE FROM codes WHERE hash = ?", (key,))
        conn.execute("COMMIT")
    if row is None or row["expires_at"] < now():
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Grants and tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    """Who a bearer token speaks for: one profile, one login, one client."""

    user_id: str
    email: str
    client_id: str
    client_name: str
    grant_id: str
    scopes: tuple[str, ...]

    def can(self, scope: str) -> bool:
        return scope in self.scopes


def create_grant(*, client_id: str, user_id: str, email: str, scope: str) -> str:
    """New grant; an older live grant for the same client and profile is replaced."""
    grant_id = "jwg_" + secrets.token_urlsafe(12)
    t = now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = [r["id"] for r in conn.execute(
            "SELECT id FROM grants WHERE client_id = ? AND user_id = ? AND revoked_at IS NULL",
            (client_id, user_id)).fetchall()]
        for gid in old:
            _revoke_locked(conn, gid, "replaced by a new sign-in")
        conn.execute("INSERT INTO grants (id, client_id, user_id, email, scope, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (grant_id, client_id, user_id, email, scope, t))
        conn.execute("COMMIT")
    return grant_id


def issue_tokens(grant_id: str) -> dict:
    access = new_secret("jwa_")
    refresh = new_secret("jwr_")
    t = now()
    with connect() as conn:
        grant = conn.execute("SELECT scope FROM grants WHERE id = ?", (grant_id,)).fetchone()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO tokens (hash, kind, grant_id, created_at, expires_at) VALUES (?, 'access', ?, ?, ?)",
                     (digest(access), grant_id, t, t + ACCESS_SECONDS))
        conn.execute("INSERT INTO tokens (hash, kind, grant_id, created_at, expires_at) VALUES (?, 'refresh', ?, ?, ?)",
                     (digest(refresh), grant_id, t, t + REFRESH_SECONDS))
        conn.execute("DELETE FROM tokens WHERE expires_at < ?", (t,))
        conn.execute("COMMIT")
    return {"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_SECONDS,
            "refresh_token": refresh, "scope": grant["scope"] if grant else " ".join(SCOPES)}


def _revoke_locked(conn: sqlite3.Connection, grant_id: str, reason: str) -> None:
    conn.execute("UPDATE grants SET revoked_at = ?, revoked_reason = ? WHERE id = ? AND revoked_at IS NULL",
                 (now(), reason[:200], grant_id))
    conn.execute("DELETE FROM tokens WHERE grant_id = ?", (grant_id,))


def revoke_grant(grant_id: str, *, user_id: str | None = None, reason: str = "revoked") -> bool:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT user_id, revoked_at FROM grants WHERE id = ?", (grant_id,)).fetchone()
        if row is None or (user_id is not None and row["user_id"] != user_id) or row["revoked_at"]:
            conn.execute("ROLLBACK")
            return False
        _revoke_locked(conn, grant_id, reason)
        conn.execute("COMMIT")
    return True


def refresh_tokens(refresh_token: str, client_id: str | None) -> dict:
    """Rotate a refresh token. A replayed (already rotated) one revokes its grant."""
    key = digest(refresh_token)
    t = now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT t.*, g.client_id, g.revoked_at FROM tokens t JOIN grants g ON g.id = t.grant_id "
            "WHERE t.hash = ? AND t.kind = 'refresh'", (key,)).fetchone()
        if row is None or row["revoked_at"] or row["expires_at"] < t or row["client_id"] != client_id:
            conn.execute("COMMIT")
            raise InvalidGrant("unknown or expired refresh token")
        if row["rotated_at"] is not None:
            # Someone kept an old refresh token: assume it leaked, end the whole connection.
            _revoke_locked(conn, row["grant_id"], "refresh token was reused")
            conn.execute("COMMIT")
            raise InvalidGrant("refresh token was already used")
        conn.execute("UPDATE tokens SET rotated_at = ?, expires_at = ? WHERE hash = ?",
                     (t, t + ROTATED_KEEP_SECONDS, key))
        conn.execute("COMMIT")
    return issue_tokens(row["grant_id"])


def revoke_token(token: str) -> None:
    """RFC 7009: revoking either token ends the grant (and every token of it)."""
    with connect() as conn:
        row = conn.execute("SELECT grant_id FROM tokens WHERE hash = ?", (digest(token),)).fetchone()
    if row is not None:
        revoke_grant(row["grant_id"], reason="revoked by the client")


_TOUCH_SECONDS = 60


def verify_access(token: str) -> Principal | None:
    """Principal for a live access token, or None. The profile must still list the login."""
    if not token or not token.startswith("jwa_"):
        return None
    t = now()
    with connect() as conn:
        row = conn.execute(
            "SELECT g.*, c.name AS client_name FROM tokens t JOIN grants g ON g.id = t.grant_id "
            "LEFT JOIN clients c ON c.id = g.client_id "
            "WHERE t.hash = ? AND t.kind = 'access' AND t.expires_at > ? AND g.revoked_at IS NULL",
            (digest(token), t)).fetchone()
        if row is None:
            return None
        if not row["last_used_at"] or t - row["last_used_at"] > _TOUCH_SECONDS:
            conn.execute("UPDATE grants SET last_used_at = ? WHERE id = ?", (t, row["id"]))
            conn.execute("UPDATE clients SET last_used_at = ? WHERE id = ?", (t, row["client_id"]))
    from jobwright.users import email_opens_profile, get_user

    user = get_user(row["user_id"])
    if not email_opens_profile(row["email"], user):
        # The login was removed from the profile (or the profile deleted): access ends with it.
        revoke_grant(row["id"], reason="login no longer opens this profile")
        return None
    return Principal(user_id=row["user_id"], email=row["email"], client_id=row["client_id"],
                     client_name=row["client_name"] or "Claude", grant_id=row["id"],
                     scopes=tuple(row["scope"].split()))


def list_grants(user_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT g.id, g.email, g.scope, g.created_at, g.last_used_at, c.name AS client_name "
            "FROM grants g LEFT JOIN clients c ON c.id = g.client_id "
            "WHERE g.user_id = ? AND g.revoked_at IS NULL ORDER BY g.created_at DESC", (user_id,)).fetchall()
        live = {r["grant_id"] for r in conn.execute(
            "SELECT DISTINCT grant_id FROM tokens WHERE kind = 'refresh' AND rotated_at IS NULL AND expires_at > ?",
            (now(),)).fetchall()}
    return [{"id": r["id"], "client_name": r["client_name"] or "Claude", "email": r["email"],
             "scopes": r["scope"].split(), "created_at": r["created_at"], "last_used_at": r["last_used_at"],
             "active": r["id"] in live} for r in rows]


# ---------------------------------------------------------------------------
# Short-lived signed download links (tailored resume / cover letter)
# ---------------------------------------------------------------------------


def create_download(user_id: str, path: Path, *, seconds: int = DOWNLOAD_SECONDS,
                    filename: str | None = None) -> tuple[str, int]:
    """A random, profile-scoped link token (only its hash is kept) for one generated file."""
    token = new_secret("jwd_")
    t = now()
    with connect() as conn:
        conn.execute("DELETE FROM downloads WHERE expires_at < ?", (t,))
        conn.execute("INSERT INTO downloads (hash, user_id, path, filename, created_at, expires_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)",
                     (digest(token), user_id, str(path), filename or path.name, t, t + seconds))
    return token, t + seconds


def resolve_download(token: str, *, count: bool = True) -> dict | None:
    """The download row for a live token, counting one use (None = unknown, expired or used up)."""
    if not token or not token.startswith("jwd_"):
        return None
    with connect() as conn:
        if count:
            conn.execute("UPDATE downloads SET uses = uses + 1 WHERE hash = ? AND expires_at > ? AND uses < ?",
                         (digest(token), now(), DOWNLOAD_MAX_USES))
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                return None
        row = conn.execute("SELECT * FROM downloads WHERE hash = ?", (digest(token),)).fetchone()
    if row is None or row["expires_at"] <= now():
        return None
    return dict(row)
