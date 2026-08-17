"""Unit tests for discovery filters and multi-profile registry."""

from __future__ import annotations

from applypilot.discovery.filters import (
    parse_salary_to_annual,
    passes_discovery_filters,
    salary_below_floor,
    title_excluded,
)


def test_parse_salary_range():
    assert parse_salary_to_annual("$120,000-$140,000") == 140000
    assert parse_salary_to_annual("115k") == 115000
    assert parse_salary_to_annual("$55/hour") == 55 * 2080


def test_title_excluded_word_boundary():
    assert title_excluded("Senior Software Engineer", ["software engineer"])
    assert not title_excluded("Chief of Staff", ["software engineer"])
    # "intern" must not match "International"
    assert title_excluded("Summer Intern", ["intern"])
    assert not title_excluded("International Partnerships Manager", ["intern"])
    assert title_excluded("Internship Coordinator", ["internship"])


def test_salary_below_floor():
    assert salary_below_floor("$90,000", 115000)
    assert not salary_below_floor("$130,000", 115000)
    assert not salary_below_floor(None, 115000)  # unknown kept


def test_passes_discovery_filters():
    cfg = {
        "exclude_titles": ["software engineer", "data scientist"],
        "min_salary": 115000,
    }
    assert not passes_discovery_filters(
        title="Backend Software Engineer",
        salary="$200,000",
        description="",
        search_cfg=cfg,
    )
    assert not passes_discovery_filters(
        title="Chief of Staff",
        salary="$90,000",
        description="",
        search_cfg=cfg,
    )
    assert passes_discovery_filters(
        title="Chief of Staff",
        salary="$130,000",
        description="",
        search_cfg=cfg,
    )
    assert passes_discovery_filters(
        title="CSR Manager",
        salary=None,
        description="Great role",
        search_cfg=cfg,
    )


def test_users_registry_roundtrip(tmp_path, monkeypatch):
    import applypilot.users as users

    monkeypatch.setattr(users, "USERS_ROOT", tmp_path)
    monkeypatch.setattr(users, "REGISTRY_PATH", tmp_path / "users.yaml")

    u = users.add_user("richa", name="Richa", whatsapp_target="whatsapp:123", apply_enabled=False)
    assert u.user_id == "richa"
    assert (tmp_path / "richa").is_dir()
    # Default .env is a stub, not a silent copy of secrets
    env_text = (tmp_path / "richa" / ".env").read_text(encoding="utf-8")
    assert "APPLY_DRY_RUN=true" in env_text
    assert "GEMINI_API_KEY=" not in env_text or "Copy GEMINI" in env_text
    assert users.get_user("richa") is not None
    assert users.is_apply_enabled("richa") is False
    users.update_user("richa", apply_enabled=True)
    assert users.is_apply_enabled("richa") is True
    users.remove_user("richa", delete_data=True)
    assert users.get_user("richa") is None


def test_set_active_user_updates_paths(tmp_path, monkeypatch):
    import applypilot.users as users
    import applypilot.config as config

    monkeypatch.setattr(users, "USERS_ROOT", tmp_path)
    monkeypatch.setattr(users, "REGISTRY_PATH", tmp_path / "users.yaml")
    users.add_user("alice", name="Alice", apply_enabled=False)
    path = config.set_active_user("alice")
    assert path == (tmp_path / "alice").resolve()
    assert config.APP_DIR == path
    assert config.DB_PATH == path / "applypilot.db"
    assert config.ACTIVE_USER_ID == "alice"
    assert users.is_apply_enabled(None) is True
