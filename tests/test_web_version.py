"""GET /api/version: the deployed build, for the dashboard's "new version" notice and Settings footer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobwright.web import version as version_mod


def test_user_facing_changes_filters_noise():
    subjects = [
        "Settings → Claude: guided setup",
        "Merge branch 'main'",
        "docs: update README",
        "Tests for the review queue",
        "chore: bump deps",
        "Settings → Claude: guided setup",
        "Board: fix the toolbar at mid widths",
        "wip",
    ]
    assert version_mod.user_facing_changes(subjects) == [
        "Settings → Claude: guided setup",
        "Board: fix the toolbar at mid widths",
    ]
    assert len(version_mod.user_facing_changes([f"Change number {i}" for i in range(20)])) == 5


def test_web_build_reads_stamp(tmp_path: Path):
    assert version_mod.web_build(tmp_path) is None
    (tmp_path / "version.json").write_text("not json", encoding="utf-8")
    assert version_mod.web_build(tmp_path) is None
    stamp = {"build_id": "abc1234-m1", "sha": "abc1234", "built_at": "2026-11-08T23:12:00Z", "extra": "x"}
    (tmp_path / "version.json").write_text(json.dumps(stamp), encoding="utf-8")
    assert version_mod.web_build(tmp_path) == {k: stamp[k] for k in ("build_id", "sha", "built_at")}


def test_payload_prefers_web_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        version_mod,
        "_server",
        {"sha": "1111111", "committed_at": "2026-11-01T00:00:00Z", "started_at": "2026-11-08T00:00:00+00:00",
         "subject": "Board polish", "changes": ["Board polish"]},
    )
    payload = version_mod.version_payload(tmp_path)
    assert payload["build_id"] is None
    assert payload["version"] == "1111111"
    assert payload["built_at"] == "2026-11-01T00:00:00Z"
    (tmp_path / "version.json").write_text(
        json.dumps({"build_id": "2222222-x", "sha": "2222222", "built_at": "2026-11-08T01:00:00Z"}), encoding="utf-8"
    )
    payload = version_mod.version_payload(tmp_path)
    assert payload["build_id"] == "2222222-x"
    assert payload["version"] == "2222222"
    assert payload["deployed_at"] == "2026-11-08T00:00:00+00:00"
    assert payload["changes"] == ["Board polish"]


def test_server_info_without_git_uses_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(version_mod, "_git", lambda *a: None)
    monkeypatch.setenv("JOBWRIGHT_BUILD_SHA", "abcdef0123")
    monkeypatch.setenv("JOBWRIGHT_BUILD_AT", "2026-11-08T00:00:00Z")
    info = version_mod._compute_server()
    assert info["sha"] == "abcdef0"
    assert info["committed_at"] == "2026-11-08T00:00:00Z"
    assert info["changes"] == []


def test_version_endpoint_needs_no_login(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from jobwright.web.app import app

    # Cloudflare mode would refuse an unauthenticated /api call; /api/version (like /api/health) is open.
    monkeypatch.setenv("JOBWRIGHT_AUTH_MODE", "cloudflare")
    client = TestClient(app)
    res = client.get("/api/version")
    assert res.status_code == 200
    body = res.json()
    assert set(body) >= {"build_id", "version", "built_at", "deployed_at", "changes"}
    assert res.headers["cache-control"] == "no-store"
    assert not any(k for k in body if "token" in k or "secret" in k)


def test_spa_cache_headers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import jobwright.web.app as app_mod

    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc.js").write_text("x", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app_mod, "_static_dir", tmp_path)
    client = TestClient(app_mod.app)
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/jobs/abc").headers["cache-control"] == "no-cache"
    assert client.get("/manifest.webmanifest").headers["cache-control"] == "no-cache"
    assert "immutable" in client.get("/assets/index-abc.js").headers["cache-control"]
