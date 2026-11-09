"""Hermetic test defaults: no real API keys, no real users/ registry, no repo .env."""

from __future__ import annotations

import os

import pytest

from jobwright import config
from jobwright import users as users_mod

_SECRET_ENV = (
    "FIREWORKS_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "LLM_URL",
    "LLM_MODEL",
    "JOBWRIGHT_LLM_MODEL",
    "LLM_ESCALATION_MODEL",
    "TYPESAFE_API_KEY",
    "EXA_API_KEY",
    "CURSOR_API_KEY",
    "JOBWRIGHT_HERMES_DRY_RUN",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "JOBWRIGHT_CF_HOSTNAME",
    "JOBWRIGHT_DASHBOARD_USER",
    "JOBWRIGHT_AUTH_MODE",
    "JOBWRIGHT_CF_TEAM_DOMAIN",
    "JOBWRIGHT_CF_AUD",
    "JOBWRIGHT_DEV_EMAIL",
    "APPLY_DRY_RUN",
    "JOBWRIGHT_OPS_FALLBACK",
    "JOBWRIGHT_OPS_NTFY_TOKEN",
    "JOBWRIGHT_OPS_TARGET",
    "JOBWRIGHT_BACKUP_DIR",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "JOBWRIGHT_APPLY_KILL",
    "JOBWRIGHT_APPLY_MODEL",
    "AGENT_PROVIDER",
)


@pytest.fixture(autouse=True)
def _hermetic(tmp_path_factory, monkeypatch):
    for key in _SECRET_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-fireworks-key")
    sandbox = tmp_path_factory.mktemp("hermetic")
    monkeypatch.setenv("JOBWRIGHT_ENV", str(sandbox / "no-global.env"))
    monkeypatch.setenv("JOBWRIGHT_AUTH_MODE", "dev")
    # Never reach real WhatsApp from a test: the hermes CLI exists on the dev Mac, so a harmless stand-in
    # comes first on PATH (tests that check sending patch subprocess / send_via_hermes as before).
    fake_bin = sandbox / "fake-hermes-bin"
    fake_bin.mkdir(exist_ok=True)
    fake = fake_bin / "hermes"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")
    # Starlette's TestClient connects as host "testclient"; treat it as this machine
    # so dev-mode anonymous admin keeps working in tests (real dev needs loopback).
    from jobwright.web import auth as auth_mod

    monkeypatch.setattr(auth_mod, "LOOPBACK_HOSTS", {*auth_mod.LOOPBACK_HOSTS, "testclient"})
    monkeypatch.setenv("HERMES_CONFIG", str(sandbox / "hermes-config.yaml"))
    monkeypatch.setenv("JOBWRIGHT_HERMES_SCRIPTS_DIR", str(sandbox / "hermes-scripts"))
    shim = sandbox / "bin"
    shim.mkdir()
    (shim / "hermes").write_text("#!/bin/sh\necho 'hermes is disabled in tests' >&2\nexit 97\n")
    (shim / "hermes").chmod(0o755)
    # Never show a real macOS notification from tests: osascript only logs its argv.
    monkeypatch.setenv("JOBWRIGHT_TEST_OSASCRIPT_LOG", str(sandbox / "osascript.log"))
    (shim / "osascript").write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$JOBWRIGHT_TEST_OSASCRIPT_LOG"\nexit 0\n')
    (shim / "osascript").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr("jobwright.hermes_cron._run_hermes", lambda args: {"stdout": "", "error": None})
    monkeypatch.setattr("jobwright.welcome.send_welcome_async", lambda user_id: None)

    def _no_network(*_a, **_k):
        raise AssertionError("tests must not POST to ntfy; stub jobwright.ops._notify_ntfy")

    monkeypatch.setattr("jobwright.ops._notify_ntfy", _no_network)

    def _no_anthropic(*_a, **_k):
        raise AssertionError("tests must not call the Anthropic API; pass a fake client")

    monkeypatch.setattr("jobwright.apply.agent.make_client", _no_anthropic)

    users_root = sandbox / "users"
    monkeypatch.setenv("JOBWRIGHT_USERS_ROOT", str(users_root))
    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")

    state = config._DEFAULT_STATE
    snapshot = {name: getattr(state, name) for name in config._PATH_FIELDS}
    state.point_at(sandbox / "app")
    state.ACTIVE_USER_ID = None

    import jobwright.llm as llm_mod

    llm_mod._instance = None
    llm_mod._usage.clear()
    yield
    llm_mod._instance = None
    llm_mod._usage.clear()
    for name, value in snapshot.items():
        setattr(state, name, value)
