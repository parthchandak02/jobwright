"""Auth + per-request profile isolation for the dashboard API."""

from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path

import pytest

from jobwright.database import close_connection, init_db, insert_manual_job

pytest.importorskip("fastapi")
jwt = pytest.importorskip("jwt")


def _write_registry(users_root: Path) -> None:
    users_root.mkdir(parents=True, exist_ok=True)
    (users_root / "users.yaml").write_text(
        "admins:\n  - boss@example.com\n"
        "users:\n"
        "  - user_id: alice\n    name: Alice\n    emails: [alice@example.com]\n"
        "  - user_id: bob\n    name: Bob\n    emails: [bob@example.com]\n",
        encoding="utf-8",
    )
    for uid in ("alice", "bob"):
        d = users_root / uid
        d.mkdir(exist_ok=True)
        db = d / "jobwright.db"
        close_connection(db)
        init_db(db)
        import jobwright.config as cfg

        cfg.set_app_dir(d)
        insert_manual_job(f"https://example.com/{uid}-job", title=f"{uid} role", company=f"{uid} co")
        close_connection(db)


@pytest.fixture()
def rsa_keys():
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


@pytest.fixture()
def cf_client(tmp_path, monkeypatch, rsa_keys):
    from fastapi.testclient import TestClient

    from jobwright.web import auth as auth_mod

    users_root = tmp_path / "users"
    import jobwright.users as users_mod

    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")
    _write_registry(users_root)

    monkeypatch.setenv("JOBWRIGHT_AUTH_MODE", "cloudflare")
    monkeypatch.setenv("JOBWRIGHT_CF_TEAM_DOMAIN", "team.cloudflareaccess.com")
    monkeypatch.setenv("JOBWRIGHT_CF_AUD", "aud-123")

    _, public = rsa_keys

    class _Key:
        key = public

    class _FakeJwks:
        def get_signing_key_from_jwt(self, token):  # noqa: ANN001
            return _Key()

    monkeypatch.setattr(auth_mod, "_jwks_client", lambda team: _FakeJwks())

    from jobwright.web import session as session_mod
    from jobwright.web.app import app

    session_mod.forget_initialized()
    with TestClient(app) as client:
        yield client


def _token(private, email: str, aud: str = "aud-123", iss: str = "https://team.cloudflareaccess.com") -> str:
    now = int(time.time())
    return jwt.encode({"email": email, "aud": aud, "iss": iss, "iat": now, "exp": now + 600}, private, algorithm="RS256")


def _h(private, email: str, **kw) -> dict:
    return {"Cf-Access-Jwt-Assertion": _token(private, email, **kw)}


def _board_titles(res) -> set[str]:
    assert res.status_code == 200, res.text
    cols = res.json()["columns"]
    return {c["title"] for col in cols.values() for c in col}


def test_missing_token_is_401(cf_client):
    assert cf_client.get("/api/board").status_code == 401
    assert cf_client.get("/api/health").status_code == 200


def test_bad_audience_and_issuer_rejected(cf_client, rsa_keys):
    private, _ = rsa_keys
    assert cf_client.get("/api/board", headers=_h(private, "alice@example.com", aud="other")).status_code == 401
    assert cf_client.get("/api/board", headers=_h(private, "alice@example.com", iss="https://evil")).status_code == 401


def test_user_sees_only_own_profile(cf_client, rsa_keys):
    private, _ = rsa_keys
    titles = _board_titles(cf_client.get("/api/board", headers=_h(private, "alice@example.com")))
    assert titles == {"alice role"}
    me = cf_client.get("/api/me", headers=_h(private, "alice@example.com")).json()
    assert [p["user_id"] for p in me["profiles"]] == ["alice"] and not me["is_admin"]
    # Cookie for someone else's profile is ignored, and switching is refused.
    res = cf_client.get("/api/board", headers=_h(private, "alice@example.com"), cookies={"jobwright_user": "bob"})
    assert _board_titles(res) == {"alice role"}
    res = cf_client.post("/api/session", json={"user_id": "bob"}, headers=_h(private, "alice@example.com"))
    assert res.status_code == 403


def test_unknown_email_has_no_profile(cf_client, rsa_keys):
    private, _ = rsa_keys
    res = cf_client.get("/api/board", headers=_h(private, "stranger@example.com"))
    assert res.status_code == 403 and res.json()["code"] == "no_profile"
    me = cf_client.get("/api/me", headers=_h(private, "stranger@example.com")).json()
    assert me["profiles"] == [] and me["active_user"] is None


def test_admin_can_switch(cf_client, rsa_keys):
    private, _ = rsa_keys
    hdr = _h(private, "boss@example.com")
    me = cf_client.get("/api/me", headers=hdr).json()
    assert me["is_admin"] and {p["user_id"] for p in me["profiles"]} == {"alice", "bob"}
    res = cf_client.get("/api/board", headers=hdr, cookies={"jobwright_user": "bob"})
    assert _board_titles(res) == {"bob role"}


def test_concurrent_requests_never_cross_users(cf_client, rsa_keys):
    private, _ = rsa_keys
    ha, hb = _h(private, "alice@example.com"), _h(private, "bob@example.com")

    def hit(i: int) -> tuple[str, set[str]]:
        who, hdr = ("alice", ha) if i % 2 == 0 else ("bob", hb)
        return who, _board_titles(cf_client.get("/api/board", headers=hdr))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for who, titles in pool.map(hit, range(40)):
            assert titles == {f"{who} role"}


def test_dev_mode_refuses_cloudflare_traffic(tmp_path, monkeypatch):
    from jobwright.web.auth import AuthError, identify

    monkeypatch.setenv("JOBWRIGHT_AUTH_MODE", "dev")
    with pytest.raises(AuthError):
        identify({"cf-ray": "abc"}, {})
    assert identify({}, {}).is_admin


def test_spa_fallback_blocks_traversal(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from jobwright.web import app as app_mod

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (dist / "asset.js").write_text("ok", encoding="utf-8")
    (tmp_path / "secret.env").write_text("KEY=1", encoding="utf-8")
    monkeypatch.setattr(app_mod, "_static_dir", dist)
    with TestClient(app_mod.app) as client:
        assert client.get("/asset.js").text == "ok"
        for probe in ("/%2e%2e/secret.env", "/..%2fsecret.env", "/%2e%2e%2fsecret.env"):
            res = client.get(probe)
            assert "KEY=1" not in res.text
        assert client.get("/api/does-not-exist").status_code in (401, 403, 404)


def test_download_refuses_profile_and_env(tmp_path, monkeypatch):
    from fastapi import HTTPException

    import jobwright.config as cfg
    from jobwright.web.routers.materials import _assert_allowed

    cfg.set_app_dir(tmp_path)
    (tmp_path / ".env").write_text("K=1", encoding="utf-8")
    (tmp_path / "profile.json").write_text("{}", encoding="utf-8")
    tailored = tmp_path / "tailored_resumes"
    tailored.mkdir()
    ok = tailored / "a.docx"
    ok.write_bytes(b"x")
    assert _assert_allowed(ok) == ok.resolve()
    for bad in (tmp_path / ".env", tmp_path / "profile.json", tailored / ".." / "profile.json"):
        with pytest.raises(HTTPException):
            _assert_allowed(bad)
    sibling = tmp_path.parent / (tmp_path.name + "2") / "tailored_resumes"
    sibling.mkdir(parents=True)
    (sibling / "b.pdf").write_bytes(b"x")
    with pytest.raises(HTTPException):
        _assert_allowed(sibling / "b.pdf")
