"""Tests for JobSpy discovery, filtering, retry, storage, and crawl orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest

from jobwright import config
from jobwright.database import close_connection, get_connection, init_db
from jobwright.discovery import jobspy, linkedin
from jobwright.discovery.site_breaker import SiteBreaker


def _setup_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "jobs.db"
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "LOG_DIR", log_dir)
    close_connection(db)
    init_db(db)
    return db


def _base_cfg(**overrides) -> dict:
    cfg = {
        "queries": [
            {"query": "Product Manager", "tier": 1},
            {"query": "Strategy Lead", "tier": 2},
        ],
        "locations": [
            {"location": "San Francisco, CA", "label": "sf", "remote": False},
        ],
        "location": {"accept_patterns": ["san francisco"], "reject_patterns": ["texas"]},
        "exclude_companies": ["", "BadCorp"],
        "exclude_titles": ["intern"],
        "min_salary": 120000,
        "defaults": {"results_per_site": 25, "hours_old": 48, "country_indeed": "usa"},
    }
    cfg.update(overrides)
    return cfg


def _df_row(**overrides) -> dict:
    row = {
        "job_url": "https://example.com/jobs/1",
        "title": "Product Manager",
        "company": "Acme Impact",
        "location": "San Francisco, CA",
        "description": "Lead product strategy for climate programs.",
        "site": "indeed",
        "is_remote": False,
        "min_amount": 140000,
        "max_amount": 180000,
        "interval": "yearly",
        "currency": "USD",
        "job_url_direct": "https://boards.greenhouse.io/acme/jobs/1",
        "date_posted": "2026-11-10",
    }
    row.update(overrides)
    return row


# -- Proxy and env helpers ---------------------------------------------------


def test_parse_proxy_formats_and_errors():
    full = jobspy.parse_proxy("127.0.0.1:8080:user1:secret")
    assert full["jobspy"] == "user1:secret@127.0.0.1:8080"
    assert full["playwright"] == {
        "server": "http://127.0.0.1:8080",
        "username": "user1",
        "password": "secret",
    }

    no_auth = jobspy.parse_proxy("127.0.0.1:8080")
    assert no_auth["jobspy"] == "127.0.0.1:8080"
    assert no_auth["user"] is None
    assert no_auth["pass"] is None
    assert no_auth["playwright"] == {"server": "http://127.0.0.1:8080"}

    with pytest.raises(ValueError, match="Proxy format not recognized"):
        jobspy.parse_proxy("invalid-proxy")


def test_env_number_valid_and_invalid(monkeypatch, caplog):
    monkeypatch.delenv("JOBWRIGHT_TEST_NUM", raising=False)
    assert jobspy._env_number("JOBWRIGHT_TEST_NUM", 5) == 5

    monkeypatch.setenv("JOBWRIGHT_TEST_NUM", "12")
    assert jobspy._env_number("JOBWRIGHT_TEST_NUM", 5) == 12

    monkeypatch.setenv("JOBWRIGHT_TEST_NUM", "not-a-number")
    with caplog.at_level(logging.WARNING):
        assert jobspy._env_number("JOBWRIGHT_TEST_NUM", 5) == 5
    assert "JOBWRIGHT_TEST_NUM" in caplog.text


# -- Retry wrapper and breaker helpers ---------------------------------------


def test_scrape_with_retry_transient_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    attempts = {"n": 0}

    def fake_scrape(**_kw):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("HTTP 429 rate limited")
        return "ok-df"

    monkeypatch.setattr(jobspy, "scrape_jobs", fake_scrape)
    monkeypatch.setattr(jobspy.time, "sleep", sleeps.append)

    out = jobspy._scrape_with_retry({"site_name": ["indeed"]}, max_retries=2, backoff=2.0)
    assert out == "ok-df"
    assert attempts["n"] == 3
    assert sleeps == [2.0, 4.0]


def test_scrape_with_retry_non_transient_and_exhausted(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(jobspy.time, "sleep", sleeps.append)

    def fail_permanent(**_kw):
        raise ValueError("bad query syntax")

    monkeypatch.setattr(jobspy, "scrape_jobs", fail_permanent)
    with pytest.raises(ValueError, match="bad query syntax"):
        jobspy._scrape_with_retry({}, max_retries=2, backoff=1.0)
    assert sleeps == []

    calls = {"n": 0}

    def fail_timeout(**_kw):
        calls["n"] += 1
        raise TimeoutError("connection timeout")

    monkeypatch.setattr(jobspy, "scrape_jobs", fail_timeout)
    with pytest.raises(TimeoutError):
        jobspy._scrape_with_retry({}, max_retries=1, backoff=1.5)
    assert calls["n"] == 2
    assert sleeps == [1.5]


def test_note_results_and_note_exception(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "LOG_DIR", log_dir)
    monkeypatch.setenv("JOBWRIGHT_SITE_BLOCK_THRESHOLD", "2")
    breaker = jobspy.site_breaker()
    assert breaker.threshold == 2
    assert breaker.state_path == log_dir / jobspy.SITE_STATE_FILE

    breaker.record_blocked("indeed", "blocked")
    df = pd.DataFrame([{"site": "indeed"}, {"site": "indeed"}])

    jobspy._note_results(None, df, ["indeed"])
    jobspy._note_results(breaker, pd.DataFrame([{"other": 1}]), ["indeed"])
    assert breaker._streak.get("indeed") == 1

    jobspy._note_results(breaker, df, ["indeed", "glassdoor"])
    assert breaker._streak.get("indeed") == 0

    # Multi-site exception should not mark either board as blocked
    jobspy._note_exception(breaker, RuntimeError("403 forbidden"), ["indeed", "glassdoor"])
    assert breaker._streak.get("indeed") == 0

    # Single-site blocked exceptions record rate_limited vs blocked
    jobspy._note_exception(breaker, RuntimeError("HTTP 429 too many requests"), ["glassdoor"])
    jobspy._note_exception(breaker, RuntimeError("403 blocked by WAF"), ["glassdoor"])
    assert breaker.is_open("glassdoor")


# -- URL, salary, and LinkedIn fingerprint helpers ---------------------------


def test_direct_url_and_card_salary_and_fingerprint():
    assert jobspy._direct_url(None) is None
    assert jobspy._direct_url("nan") is None
    assert jobspy._direct_url("ftp://example.com/job") is None
    assert jobspy._direct_url("https://www.linkedin.com/uas/login?next=1") is None
    assert jobspy._direct_url("https://www.linkedin.com/signup/cold-join") is None
    assert jobspy._direct_url("https://example.com/apply") == "https://example.com/apply"

    assert jobspy._card_salary({}) is None
    assert jobspy._card_salary({"min_amount": 130000}) == "USD130,000/yearly"
    assert jobspy._card_salary({"min_amount": 60, "max_amount": 80, "interval": "hourly"}) == "USD60-USD80/hourly"

    cfg = _base_cfg()
    fp1 = jobspy._linkedin_filter_fingerprint(cfg)
    assert fp1 == jobspy._linkedin_filter_fingerprint({**cfg, "unrelated": "value"})
    assert fp1 != jobspy._linkedin_filter_fingerprint({**cfg, "min_salary": 150000})


# -- store_jobspy_results ----------------------------------------------------


def test_store_jobspy_results_filters_promotes_and_deduplicates(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "load_search_config", lambda: _base_cfg())
    conn = get_connection(db)

    long_desc = ("We sponsor H1B visas for qualified engineers. " + ("Impact " * 35)).strip()
    rows = [
        _df_row(job_url="nan"),
        _df_row(job_url="https://example.com/jobs/known"),
        _df_row(job_url="https://example.com/jobs/badco", company="BadCorp Partners"),
        _df_row(job_url="https://example.com/jobs/badtitle", title="Work at BadCorp"),
        _df_row(job_url="https://example.com/jobs/lowpay", min_amount=70000, max_amount=90000),
        _df_row(
            job_url="https://example.com/jobs/good1",
            title="Director of Product",
            min_amount=150000,
            max_amount=None,
            interval="nan",
            is_remote=True,
            description=long_desc,
            site="linkedin",
            job_url_direct="https://jobs.ashbyhq.com/acme/1",
            date_posted="2026-11-12T10:00:00Z",
        ),
        # Within-batch duplicate URL should count as existing, not skipped_known
        _df_row(job_url="https://example.com/jobs/good1"),
        _df_row(
            job_url="https://example.com/jobs/good2",
            location=float("nan"),
            is_remote=True,
            min_amount=None,
            max_amount=None,
            date_posted="not-a-date",
            job_url_direct="https://www.linkedin.com/authwall",
        ),
    ]
    df = pd.DataFrame(rows)

    new, existing, skipped_known = jobspy.store_jobspy_results(
        conn, df, "product manager", known_urls={"https://example.com/jobs/known"},
    )
    assert (new, existing, skipped_known) == (2, 2, 1)

    r1 = conn.execute(
        "SELECT salary, location, full_description, detail_scraped_at, sponsorship_status, "
        "application_url, application_url_source, application_ats, date_posted FROM jobs WHERE url = ?",
        ("https://example.com/jobs/good1",),
    ).fetchone()
    assert r1["salary"] == "USD150,000"
    assert r1["location"] == "San Francisco, CA (Remote)"
    assert r1["full_description"] == long_desc
    assert r1["detail_scraped_at"] is not None
    assert r1["sponsorship_status"] is not None
    assert r1["application_url"] == "https://jobs.ashbyhq.com/acme/1"
    assert r1["application_url_source"] == "linkedin_offsite"
    assert r1["application_ats"] == "ashby"
    assert r1["date_posted"] == "2026-11-12"

    r2 = conn.execute(
        "SELECT location, full_description, detail_scraped_at, application_url, date_posted "
        "FROM jobs WHERE url = ?",
        ("https://example.com/jobs/good2",),
    ).fetchone()
    assert r2["location"] == "Remote"
    assert r2["full_description"] is None
    assert r2["detail_scraped_at"] is None
    assert r2["application_url"] is None
    assert r2["date_posted"] is None

    # IntegrityError backstop when row exists in DB but is omitted from known_urls
    new2, existing2, skipped2 = jobspy.store_jobspy_results(
        conn, pd.DataFrame([_df_row(job_url="https://example.com/jobs/good1")]), "q", known_urls=set(),
    )
    assert (new2, existing2, skipped2) == (0, 1, 0)
    close_connection(db)


# -- LinkedIn card predicate and _run_one_search -----------------------------


def test_linkedin_keep_predicate(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "load_search_config", lambda: _base_cfg())

    rejects = linkedin.RejectMemory(tmp_path / "logs" / "li_rejects.json", "fp1")
    rejects.add("rejected-id")

    keep = jobspy._linkedin_keep(
        accept_locs=["san francisco"],
        reject_locs=["texas"],
        known_urls={"https://example.com/known"},
        remote_any=False,
        rejects=rejects,
    )

    assert not keep({"job_id": "1", "job_url": "https://example.com/known", "title": "PM", "company": "Acme",
                     "location": "San Francisco, CA"})
    assert not keep({"job_id": "rejected-id", "job_url": "https://example.com/r", "title": "PM", "company": "Acme",
                     "location": "San Francisco, CA"})
    assert not keep({"job_id": "2", "job_url": "https://example.com/c", "title": "PM", "company": "BadCorp Inc",
                     "location": "San Francisco, CA"})
    assert not keep({"job_id": "3", "job_url": "https://example.com/t", "title": "BadCorp Liaison", "company": "GoodCo",
                     "location": "San Francisco, CA"})
    assert not keep({"job_id": "4", "job_url": "https://example.com/loc", "title": "PM", "company": "GoodCo",
                     "location": "Austin, Texas"})
    assert not keep({"job_id": "5", "job_url": "https://example.com/sal", "title": "PM", "company": "GoodCo",
                     "location": "San Francisco, CA", "min_amount": 80000})
    assert keep({"job_id": "6", "job_url": "https://example.com/ok", "title": "Product Manager", "company": "GoodCo",
                 "location": "San Francisco, CA", "min_amount": 150000})


def _li_row(**overrides) -> dict:
    row = {
        "job_id": "li-1",
        "job_url": "https://example.com/li/1",
        "title": "Product Manager",
        "company": "Acme",
        "location": "San Francisco, CA",
        "date_posted": "2026-11-10",
        "is_remote": False,
        "description": "Strong impact role.",
        "min_amount": None,
        "max_amount": None,
        "interval": None,
        "job_url_direct": None,
    }
    row.update(overrides)
    return row


def test_run_one_search_linkedin_rejects_and_split_sites(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "load_search_config", lambda: _base_cfg())
    monkeypatch.setattr(linkedin, "use_guest_client", lambda: True)
    monkeypatch.setattr(linkedin, "shared_client", lambda proxy=None: object())

    rejects = linkedin.RejectMemory(tmp_path / "logs" / "li_rejects.json", "fp1")
    rejects.add("old-reject")

    li_rows = [
        # Already rejected and returned without a description: must be pruned before store
        _li_row(job_id="old-reject", job_url="https://example.com/li/old", description=""),
        # Newly fetched description reveals low salary: must be recorded in rejects and excluded
        _li_row(
            job_id="low-sal-desc",
            job_url="https://example.com/li/low",
            description="Compensation: $80,000 - $95,000 base.",
        ),
        # Passing LinkedIn job
        _li_row(
            job_id="good-li",
            job_url="https://example.com/li/good",
            description="Compensation: $150,000 - $180,000 base.",
            min_amount=150000,
            interval="yearly",
        ),
    ]
    monkeypatch.setattr(linkedin, "scrape", lambda *a, **kw: list(li_rows))

    seen_calls: list[dict] = []

    def fake_scrape_jobs(**kwargs):
        seen_calls.append(kwargs)
        if kwargs["site_name"] == ["glassdoor"]:
            return pd.DataFrame([
                _df_row(job_url="https://example.com/gd/ok", site="glassdoor", location="San Francisco, CA"),
                _df_row(job_url="https://example.com/gd/texas", site="glassdoor", location="Austin, Texas"),
            ])
        return pd.DataFrame([
            _df_row(job_url="https://example.com/google/ok", site="google", location="San Francisco, CA"),
        ])

    monkeypatch.setattr(jobspy, "scrape_jobs", fake_scrape_jobs)
    proxy_cfg = jobspy.parse_proxy("127.0.0.1:8080")
    breaker = SiteBreaker(tmp_path / "logs" / "cooldown.json")

    res = jobspy._run_one_search(
        search={"query": "Product Manager", "location": "SF Bay Area", "remote": True, "tier": 1},
        sites=["linkedin", "google", "glassdoor"],
        results_per_site=15,
        hours_old=24,
        proxy_config=proxy_cfg,
        defaults={"country_indeed": "usa"},
        max_retries=0,
        accept_locs=["san francisco"],
        reject_locs=["texas"],
        glassdoor_map={"SF Bay Area": "San Francisco"},
        known_urls=set(),
        li_rejects=rejects,
        breaker=breaker,
    )

    assert "low-sal-desc" in rejects
    assert res["new"] == 3
    assert res["filtered"] == 1  # Texas Glassdoor job filtered by _location_ok
    assert res["errors"] == 0

    google_call = next(c for c in seen_calls if "google" in c["site_name"])
    assert "Product Manager jobs near SF Bay Area" in google_call["google_search_term"]
    assert google_call["is_remote"] is True
    assert google_call["proxies"] == ["127.0.0.1:8080"]

    gd_call = next(c for c in seen_calls if c["site_name"] == ["glassdoor"])
    assert gd_call["location"] == "San Francisco"
    assert gd_call["proxies"] == ["127.0.0.1:8080"]
    close_connection(db)


def test_run_one_search_partial_and_total_failures(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "load_search_config", lambda: _base_cfg())

    # 1) other_sites fails, glassdoor succeeds -> partial error recorded, gd row stored
    def partial_fail(**kwargs):
        if kwargs["site_name"] == ["glassdoor"]:
            return pd.DataFrame([_df_row(job_url="https://example.com/gd/1", site="glassdoor")])
        raise RuntimeError("indeed 500 error")

    monkeypatch.setattr(jobspy, "scrape_jobs", partial_fail)
    res_partial = jobspy._run_one_search(
        search={"query": "Product Manager", "location": "San Francisco, CA"},
        sites=["indeed", "glassdoor"],
        results_per_site=10,
        hours_old=24,
        proxy_config=None,
        defaults={},
        max_retries=0,
        accept_locs=["san francisco"],
        reject_locs=[],
        glassdoor_map={},
    )
    assert res_partial["new"] == 1
    assert res_partial["errors"] == 0
    assert res_partial["site_errors"] == {"indeed": 1}

    # 2) All sites raise -> errors == 1
    def all_fail(**_kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(jobspy, "scrape_jobs", all_fail)
    res_all_fail = jobspy._run_one_search(
        search={"query": "Product Manager", "location": "San Francisco, CA"},
        sites=["indeed", "glassdoor"],
        results_per_site=10,
        hours_old=24,
        proxy_config=None,
        defaults={},
        max_retries=0,
        accept_locs=[],
        reject_locs=[],
        glassdoor_map={},
    )
    assert res_all_fail["errors"] == 1
    assert res_all_fail["site_errors"] == {"indeed": 1, "glassdoor": 1}

    # 3) Empty DataFrame -> zero counts and no error
    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **_kw: pd.DataFrame())
    res_empty = jobspy._run_one_search(
        search={"query": "Product Manager", "location": "San Francisco, CA"},
        sites=["indeed"],
        results_per_site=10,
        hours_old=24,
        proxy_config=None,
        defaults={},
        max_retries=0,
        accept_locs=[],
        reject_locs=[],
        glassdoor_map={},
    )
    assert res_empty["new"] == 0 and res_empty["errors"] == 0

    # 4) LinkedIn via JobSpy (when guest client is off) passes linkedin_fetch_description=True
    seen_kw: dict = {}
    monkeypatch.setattr(linkedin, "use_guest_client", lambda: False)
    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **kw: seen_kw.update(kw) or pd.DataFrame())
    jobspy._run_one_search(
        search={"query": "Product Manager", "location": "San Francisco, CA"},
        sites=["linkedin"],
        results_per_site=10,
        hours_old=24,
        proxy_config=None,
        defaults={},
        max_retries=0,
        accept_locs=[],
        reject_locs=[],
        glassdoor_map={},
    )
    assert seen_kw["linkedin_fetch_description"] is True
    close_connection(db)


# -- search_jobs -------------------------------------------------------------


def test_search_jobs_error_empty_and_persists(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "load_search_config", lambda: _base_cfg())

    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **_kw: (_ for _ in ()).throw(RuntimeError("network")))
    err = jobspy.search_jobs("PM", "San Francisco, CA")
    assert err == {"error": "network", "total": 0, "new": 0, "existing": 0}

    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **_kw: pd.DataFrame())
    empty = jobspy.search_jobs("PM", "San Francisco, CA")
    assert empty == {"total": 0, "new": 0, "existing": 0}

    seen: dict = {}

    def ok_scrape(**kwargs):
        seen.update(kwargs)
        return pd.DataFrame([_df_row(job_url="https://example.com/search/1", site="linkedin")])

    monkeypatch.setattr(jobspy, "scrape_jobs", ok_scrape)
    out = jobspy.search_jobs(
        "Product Manager",
        "San Francisco, CA",
        remote_only=True,
        proxy="127.0.0.1:8080",
    )
    assert out == {"total": 1, "new": 1, "existing": 0}
    assert seen["site_name"] == list(jobspy.DEFAULT_SITES)
    assert seen["is_remote"] is True
    assert seen["proxies"] == ["127.0.0.1:8080"]
    assert seen["linkedin_fetch_description"] is True
    close_connection(db)


# -- run_discovery and _full_crawl -------------------------------------------


def test_run_discovery_empty_config_and_env_overrides(tmp_path, monkeypatch):
    _setup_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "load_search_config", lambda: {})
    assert jobspy.run_discovery() == {"new": 0, "existing": 0, "errors": 0, "db_total": 0, "queries": 0}

    captured: dict = {}
    monkeypatch.setattr(jobspy, "_full_crawl", lambda **kw: captured.update(kw) or {"new": 0})
    monkeypatch.setenv("DISCOVER_MODE", "fast")
    monkeypatch.setenv("JOBWRIGHT_DISCOVER_LOCATIONS", "sf | nyc")
    monkeypatch.setenv("JOBWRIGHT_RESULTS_PER_SITE", "40")
    monkeypatch.setenv("JOBWRIGHT_HOURS_OLD", "bad-int")
    monkeypatch.setenv("JOBWRIGHT_DISCOVER_BOARDS", "indeed|zip_recruiter")

    cfg = _base_cfg()
    jobspy.run_discovery(cfg=cfg, workers=3)
    assert captured["tiers"] == [1]
    assert captured["locations"] == ["sf", "nyc"]
    assert captured["results_per_site"] == 40
    assert captured["hours_old"] == 48
    assert captured["sites"] == ["indeed", "zip_recruiter"]
    assert captured["workers"] == 3

    monkeypatch.setenv("JOBWRIGHT_HOURS_OLD", "96")
    monkeypatch.setenv("DISCOVER_MODE", "full")
    jobspy.run_discovery(cfg=cfg, workers=1)
    assert captured["tiers"] is None
    assert captured["hours_old"] == 96


def test_full_crawl_filters_target_companies_and_parallel_workers(tmp_path, monkeypatch):
    db = _setup_db(tmp_path, monkeypatch)
    cfg = _base_cfg(
        locations=[
            {"location": "San Francisco, CA", "label": "sf", "remote": False},
            {"location": "Remote", "label": "remote", "remote": True, "remote_scope": "any"},
        ],
        target_companies=[{"name": f"Co{i}"} for i in range(10)] + ["   "],
        location={"accept_patterns": ["san francisco"], "reject_patterns": []},
    )
    monkeypatch.setattr(config, "load_search_config", lambda: cfg)
    monkeypatch.setattr(linkedin, "use_guest_client", lambda: True)
    fake_client = type("Client", (), {"requests": 2, "descriptions_fetched": 1, "rate_limited": 1, "gave_up": 0})()
    monkeypatch.setattr(linkedin, "shared_client", lambda proxy=None: fake_client)

    seen_remote_any: list[bool] = []

    def fake_scrape(query, *_a, **kw):
        seen_remote_any.append(kw.get("remote_any"))
        return [
            _li_row(
                job_id=f"li-{query}",
                job_url=f"https://example.com/li/{query.replace(' ', '-')}",
                company=query,
                min_amount=150000,
                interval="yearly",
            )
        ]

    monkeypatch.setattr(linkedin, "scrape", fake_scrape)
    monkeypatch.setenv("JOBWRIGHT_DISCOVER_MAX_QUERIES", "1")
    monkeypatch.setenv("JOBWRIGHT_DISCOVER_WORKERS", "invalid")

    breaker = SiteBreaker(tmp_path / "logs" / "cooldown.json")
    out = jobspy._full_crawl(
        search_cfg=cfg,
        tiers=[1],
        locations=["sf"],
        sites=["linkedin"],
        workers=10,
        breaker=breaker,
    )

    # 1 capped tier-1 query + 8 capped target companies, across 1 matching location ("sf") = 9 searches
    assert out["queries"] == 9
    assert out["workers"] == jobspy._DEFAULT_DISCOVER_WORKER_CAP
    assert out["new"] == 9
    assert out["db_total"] == 9
    assert out["errors"] == 0
    assert seen_remote_any == [True] * 9
    assert out["linkedin"] == {"requests": 0, "throttled": 0, "rate_limited": 0}
    assert (tmp_path / "logs" / "linkedin_rejects.json").exists()

    # Sequential execution + skipped-by-breaker board + default sites
    breaker.record_blocked("linkedin", "blocked")
    breaker.record_blocked("linkedin", "blocked")
    breaker.record_blocked("linkedin", "blocked")
    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **_kw: (_ for _ in ()).throw(RuntimeError("indeed fail")))
    seq_out = jobspy._full_crawl(
        search_cfg=cfg,
        tiers=[1],
        locations=["sf"],
        sites=None,
        workers=1,
        breaker=breaker,
    )
    assert seq_out["workers"] == 1
    assert seq_out["site_errors"] == {"indeed": 9}
    close_connection(db)
