"""Unit tests for discovery filters and multi-profile registry."""

from __future__ import annotations

from jobwright.discovery.filters import (
    apply_fit_score_guards,
    fit_score_ceiling,
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


def test_title_excluded_impact_noise_patterns():
    """Keep applied-style impact titles; drop bizops / clinical / major gifts."""
    excludes = [
        "business operations",
        "go-to-market",
        "home health",
        "major gifts",
        "principal gifts",
        "intern",
    ]
    keep = [
        "Sr. Program Manager, Data for Good",
        "Senior Specialist, Social & Community Impact",
        "Market Engagement Lead, Community Impact & Investment",
        "Portfolio Director",
        "Manager, Corporate Social Responsibility",
        "Director, Corporate Purpose & Learning",
        "Lean In Girls, Senior Partnerships Manager",
        "Deputy Director, Catalyze479 Fund",
        "FUSE Fellow, San Francisco",
        "Analyst or Associate, DRK Foundation",
        "CCS Fundraising Consultant",
        "AI for Social Good Program Manager",
        "International Partnerships Manager",
    ]
    for title in keep:
        assert not title_excluded(title, excludes), title
    assert title_excluded("Principal Business Operations and Programs Lead", excludes)
    assert title_excluded("Home Health Agency Director", excludes)
    assert title_excluded("Director of Principal & Major Gifts", excludes)


def test_fit_score_ceiling_caps_generic_ops():
    excludes = ["business operations", "home health"]
    assert fit_score_ceiling(
        "Principal Business Operations and Programs Lead",
        "Adobe",
        "OKRs and headcount planning",
        excludes,
    ) == 4
    assert fit_score_ceiling(
        "Chief of Staff",
        "Thesis Care",
        "Scale an AI-powered clinical care platform and ops cadence.",
        excludes,
    ) == 4
    assert fit_score_ceiling(
        "Business Advisor",
        "Innovation Norway",
        "Investor outreach and startup ecosystem advisory in San Francisco.",
        excludes,
    ) == 4
    assert fit_score_ceiling(
        "Chief of Staff",
        "The OpenAI Foundation",
        "Lead the CEO office and board cadence.",
        excludes,
    ) is None
    assert fit_score_ceiling(
        "Chief of Staff",
        "Thesis Care",
        "Scale foundation models for clinical AI operations.",
        excludes,
    ) == 4
    assert fit_score_ceiling(
        "Chief of Staff",
        "Blue Star Families",
        "Lead community programs at a mission-driven nonprofit serving military families.",
        excludes,
    ) is None
    assert fit_score_ceiling(
        "Sr. Program Manager, Data for Good",
        "Databricks",
        "Build Databricks for Good with nonprofits.",
        excludes,
    ) is None
    # No JD yet: do not cap CoS (enrichment still pending)
    assert fit_score_ceiling("Chief of Staff", "Acme", "", excludes) is None


def test_apply_fit_score_guards_appends_reason():
    parsed = apply_fit_score_guards(
        {
            "title": "Home Health Agency Director",
            "company": "Cardea Health",
            "full_description": "Run a home health agency.",
        },
        {"score": 9, "keywords": "director", "reasoning": "Strong leadership fit."},
        search_cfg={"exclude_titles": ["home health"]},
    )
    assert parsed["score"] == 4
    assert "capped at 4" in parsed["reasoning"]


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


def test_describe_cron_schedule():
    from jobwright.users import describe_cron_schedule

    assert describe_cron_schedule("0 6 * * *") == "Every day at 6:00 AM"
    assert describe_cron_schedule("30 18 * * *") == "Every day at 6:30 PM"
    assert describe_cron_schedule("0 6 * * 1-5") == "Weekdays at 6:00 AM"
    assert describe_cron_schedule("0 */3 * * 1-5") == "0 */3 * * 1-5"


def test_apply_clock_to_cron():
    from jobwright.users import apply_clock_to_cron, validate_brief_schedule

    assert apply_clock_to_cron("0 6 * * *", 7, 30) == "30 7 * * *"
    assert apply_clock_to_cron("0 6 * * 1-5", 8, 0) == "0 8 * * 1-5"
    assert validate_brief_schedule("15 9 * * *") == "15 9 * * *"
    try:
        validate_brief_schedule("0 */3 * * 1-5")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_users_registry_roundtrip(tmp_path, monkeypatch):
    import jobwright.users as users

    monkeypatch.setattr(users, "USERS_ROOT", tmp_path)
    monkeypatch.setattr(users, "REGISTRY_PATH", tmp_path / "users.yaml")

    u = users.add_user("richa", name="Richa", whatsapp_target="whatsapp:123", apply_enabled=False)
    assert u.user_id == "richa"
    assert (tmp_path / "richa").is_dir()
    # No per-user .env: API keys are global; per-user dirs hold only data.
    assert not (tmp_path / "richa" / ".env").exists()
    assert users.get_user("richa") is not None
    assert users.is_apply_enabled("richa") is False
    users.update_user("richa", apply_enabled=True)
    assert users.is_apply_enabled("richa") is True
    users.remove_user("richa", delete_data=True)
    assert users.get_user("richa") is None


def test_find_user_by_whatsapp(tmp_path, monkeypatch):
    import jobwright.users as users

    monkeypatch.setattr(users, "USERS_ROOT", tmp_path)
    monkeypatch.setattr(users, "REGISTRY_PATH", tmp_path / "users.yaml")

    users.add_user("richa", whatsapp_target="whatsapp:120363@g.us")
    assert users.find_user_by_whatsapp("whatsapp:120363@g.us") is not None
    assert users.find_user_by_whatsapp("120363@g.us").user_id == "richa"
    assert users.find_user_by_whatsapp("whatsapp:unknown") is None


def test_set_active_user_updates_paths(tmp_path, monkeypatch):
    import jobwright.users as users
    import jobwright.config as config

    monkeypatch.setattr(users, "USERS_ROOT", tmp_path)
    monkeypatch.setattr(users, "REGISTRY_PATH", tmp_path / "users.yaml")
    users.add_user("alice", name="Alice", apply_enabled=False)
    path = config.set_active_user("alice")
    assert path == (tmp_path / "alice").resolve()
    assert config.APP_DIR == path
    assert config.DB_PATH == path / "jobwright.db"
    assert config.ACTIVE_USER_ID == "alice"
    assert users.is_apply_enabled(None) is True
