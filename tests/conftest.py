"""Hermetic test defaults: no real API keys, no real users/ registry, no repo .env."""

from __future__ import annotations

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
    "JOBWRIGHT_DASHBOARD_USER",
    "JOBWRIGHT_AUTH_MODE",
    "JOBWRIGHT_CF_TEAM_DOMAIN",
    "JOBWRIGHT_CF_AUD",
    "JOBWRIGHT_DEV_EMAIL",
    "APPLY_DRY_RUN",
)


@pytest.fixture(autouse=True)
def _hermetic(tmp_path_factory, monkeypatch):
    for key in _SECRET_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-fireworks-key")
    sandbox = tmp_path_factory.mktemp("hermetic")
    monkeypatch.setenv("JOBWRIGHT_ENV", str(sandbox / "no-global.env"))
    monkeypatch.setenv("JOBWRIGHT_AUTH_MODE", "dev")
    monkeypatch.setenv("HERMES_CONFIG", str(sandbox / "hermes-config.yaml"))

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
    yield
    llm_mod._instance = None
    for name, value in snapshot.items():
        setattr(state, name, value)
