"""Blocked job boards: per-run circuit breaker, cooldown file, defaults, source health.

Offline only: JobSpy's scrape_jobs and the LinkedIn transport are faked, and
every state file lives under tmp_path.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

import jobwright.config as cfg
from jobwright.database import close_connection, init_db
from jobwright.discovery import jobspy, linkedin
from jobwright.discovery.site_breaker import JobSpyBlockHandler, SiteBreaker, watch_jobspy_logs

ZIP_403 = 'ZipRecruiter response status code 403 with response: {"error": "forbidden"}'


class Clock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_breaker_trips_after_consecutive_blocks_and_success_resets():
    b = SiteBreaker(threshold=3)
    assert not b.record_blocked("zip_recruiter")
    assert not b.record_blocked("zip_recruiter")
    b.record_ok("zip_recruiter")
    assert not b.record_blocked("zip_recruiter") and not b.record_blocked("zip_recruiter")
    assert not b.is_open("zip_recruiter")
    assert b.record_blocked("zip_recruiter")
    assert b.is_open("zip_recruiter") and not b.is_open("indeed")
    b.skip("zip_recruiter")
    health = b.summary()["zip_recruiter"]
    assert health["status"] == "blocked" and health["blocked_responses"] == 5 and health["skipped"] == 1
    assert "until" not in health  # it worked once this run: no cooldown


def test_fully_blocked_site_cools_down_then_gets_one_probe(tmp_path: Path):
    path = tmp_path / "logs" / "site_cooldown.json"
    clock = Clock()
    b = SiteBreaker(path, threshold=3, cooldown_days=3, clock=clock)
    for _ in range(3):
        b.record_blocked("zip_recruiter")
    b.save()
    saved = json.loads(path.read_text())["sites"]["zip_recruiter"]
    assert saved["until"] == pytest.approx(clock.t + 3 * 86400)

    clock.t += 86400  # next day: skipped outright
    b2 = SiteBreaker(path, threshold=3, clock=clock)
    assert b2.in_cooldown("zip_recruiter") and b2.is_open("zip_recruiter")
    b2.skip("zip_recruiter")
    assert b2.summary()["zip_recruiter"]["status"] == "cooldown"
    b2.save()
    assert path.exists()

    clock.t += 3 * 86400  # cooldown over: one blocked probe renews it
    b3 = SiteBreaker(path, threshold=3, clock=clock)
    assert not b3.is_open("zip_recruiter")
    assert b3.record_blocked("zip_recruiter")  # threshold 1 while probing
    b3.save()
    assert json.loads(path.read_text())["sites"]["zip_recruiter"]["until"] > clock.t

    clock.t += 4 * 86400  # probe works: cooldown cleared
    b4 = SiteBreaker(path, threshold=3, clock=clock)
    b4.record_ok("zip_recruiter")
    b4.save()
    assert not path.exists()


def test_rate_limited_trip_gets_no_cooldown(tmp_path: Path):
    path = tmp_path / "site_cooldown.json"
    b = SiteBreaker(path, threshold=2)
    b.record_blocked("linkedin", "rate_limited")
    assert b.record_blocked("linkedin", "rate_limited")
    b.save()
    assert not path.exists()
    assert b.summary()["linkedin"]["status"] == "rate_limited"


def test_corrupt_state_file_is_ignored(tmp_path: Path):
    path = tmp_path / "site_cooldown.json"
    path.write_text("{not json")
    assert not SiteBreaker(path).is_open("zip_recruiter")


def test_jobspy_log_lines_count_as_blocked():
    b = SiteBreaker(threshold=2)
    log = logging.getLogger("JobSpy:ZipRecruiter")
    with watch_jobspy_logs(b) as handler:
        assert isinstance(handler, JobSpyBlockHandler)
        log.error(ZIP_403)
        log.error("429 Response - Blocked by ZipRecruiter for too many requests")
        logging.getLogger("JobSpy:Indeed").error("Indeed: location not parsed")
    log.error(ZIP_403)  # handler removed: not counted
    health = b.summary()
    assert health["zip_recruiter"]["blocked_responses"] == 2 and "indeed" not in health


# ---------------------------------------------------------------------------
# Full crawl with a fake JobSpy
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_dir(tmp_path, monkeypatch):
    cfg.set_app_dir(tmp_path)
    close_connection(tmp_path / "jobwright.db")
    init_db(tmp_path / "jobwright.db")
    (tmp_path / "logs").mkdir(exist_ok=True)
    monkeypatch.setattr(cfg, "load_search_config", lambda: {})
    monkeypatch.setenv("JOBWRIGHT_LINKEDIN", "guest")
    yield tmp_path
    close_connection(tmp_path / "jobwright.db")


def _fake_jobspy(calls: list[list[str]]):
    import pandas as pd

    def scrape_jobs(**kw):
        sites = list(kw["site_name"])
        calls.append(sites)
        if "zip_recruiter" in sites:
            logging.getLogger("JobSpy:ZipRecruiter").error(ZIP_403)
        rows = []
        if "indeed" in sites:
            n = len(calls)
            rows.append({"job_url": f"https://example.com/jobs/{n}", "title": "Program Manager",
                         "company": "Example Org", "location": "Remote", "site": "indeed",
                         "description": "Lead programs."})
        return pd.DataFrame(rows, columns=["job_url", "title", "company", "location", "site", "description"])

    return scrape_jobs


def _search_cfg(n_queries: int) -> dict:
    return {"queries": [{"query": f"program manager {i}", "tier": 1} for i in range(n_queries)],
            "locations": [{"location": "Remote", "remote": True}]}


def test_full_crawl_skips_zip_recruiter_after_three_403s_then_cools_down(app_dir, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(jobspy, "scrape_jobs", _fake_jobspy(calls))
    res = jobspy._full_crawl(_search_cfg(6), sites=["indeed", "zip_recruiter"], max_retries=0)
    assert sum("zip_recruiter" in c for c in calls) == 3 and len(calls) == 6
    zip_health = res["site_health"]["zip_recruiter"]
    assert zip_health["status"] == "blocked" and zip_health["skipped"] == 3 and zip_health["until"]
    assert res["new"] == 6  # Indeed kept working
    state = json.loads((app_dir / "logs" / "site_cooldown.json").read_text())
    assert "zip_recruiter" in state["sites"]

    calls.clear()
    res = jobspy._full_crawl(_search_cfg(4), sites=["indeed", "zip_recruiter"], max_retries=0)
    assert not any("zip_recruiter" in c for c in calls)
    assert res["site_health"]["zip_recruiter"]["status"] == "cooldown"
    assert res["site_health"]["zip_recruiter"]["skipped"] == 4


def test_default_boards_leave_out_zip_recruiter_but_explicit_list_keeps_it(monkeypatch):
    seen = {}
    monkeypatch.setattr(jobspy, "_full_crawl", lambda **kw: seen.setdefault("sites", kw["sites"]) and {})
    jobspy.run_discovery({"queries": [], "locations": []})
    assert seen.pop("sites") == ["indeed", "linkedin"]
    jobspy.run_discovery({"queries": [], "locations": [], "boards": ["indeed", "zip_recruiter"]})
    assert seen["sites"] == ["indeed", "zip_recruiter"]


def test_linkedin_rate_limit_give_ups_trip_the_breaker():
    client = linkedin.GuestClient(interval=0, sleep=lambda s: None, max_retries=1,
                                  transport=httpx.MockTransport(lambda req: httpx.Response(429)))
    b = SiteBreaker(threshold=2)
    linkedin.scrape("ops", "Chicago, IL", client=client, breaker=b)
    assert not b.is_open("linkedin")
    linkedin.scrape("ops 2", "Chicago, IL", client=client, breaker=b)
    assert b.is_open("linkedin") and b.summary()["linkedin"]["status"] == "rate_limited"


def test_run_one_search_skips_open_boards(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(jobspy, "scrape_jobs", _fake_jobspy(calls))
    monkeypatch.setattr(linkedin, "scrape", lambda *a, **k: pytest.fail("LinkedIn should be skipped"))
    b = SiteBreaker(threshold=1)
    b.record_blocked("linkedin", "rate_limited")
    b.record_blocked("zip_recruiter")
    res = jobspy._run_one_search(
        {"query": "ops", "location": "Remote", "remote": True},
        ["linkedin", "zip_recruiter"], 10, 72, None, {}, 0, [], [], {}, set(), None, breaker=b,
    )
    assert calls == [] and res["errors"] == 0
    assert b.summary()["linkedin"]["skipped"] == 1 and b.summary()["zip_recruiter"]["skipped"] == 1


# ---------------------------------------------------------------------------
# Source health in discover + brief-report
# ---------------------------------------------------------------------------

def test_discover_reports_blocked_board_as_skipped_not_errors(monkeypatch):
    from jobwright import ops, pipeline
    from jobwright.discovery import impactboards, workday

    monkeypatch.setattr(jobspy, "run_discovery", lambda workers=1: {
        "new": 9, "errors": 0, "site_errors": {}, "queries": 32,
        "linkedin": {"requests": 40, "throttled": 0, "rate_limited": 0},
        "site_health": {"zip_recruiter": {"status": "blocked", "blocked_responses": 3, "skipped": 29,
                                          "until": "2026-11-07T08:00:00+00:00"}}})
    monkeypatch.setattr(workday, "run_workday_discovery", lambda workers=1: {"new": 1, "errors": 0, "queries": 2})
    monkeypatch.setattr(impactboards, "run_impact_boards", lambda workers=1: {"giin": {"new": 0, "error": None}})
    monkeypatch.setattr(pipeline, "_dedupe", lambda: {})
    stats = pipeline._run_discover()
    src = stats["sources"]
    assert src["zip_recruiter"]["status"] == "blocked" and src["zip_recruiter"]["errors"] == 0
    assert src["jobspy"]["errors"] == 0
    assert stats["status"] == "ok"
    line = ops._source_line(src)
    assert "zip_recruiter: blocked, skipped until 2026-11-07" in line
    assert not any("zip_recruiter" in w for w in ops._source_warnings(src))


def test_cooldown_board_and_skipped_linkedin_render(monkeypatch):
    from jobwright import ops, pipeline

    sources = {"jobspy": {"new": 3, "errors": 0, "rate_limited": 0, "status": "ok"},
               "linkedin": {"errors": 0, "rate_limited": 3, "status": "degraded"}}
    pipeline._add_site_health(sources, {
        "zip_recruiter": {"status": "cooldown", "skipped": 32, "until": "2026-11-07T08:00:00+00:00"},
        "linkedin": {"status": "rate_limited", "blocked_responses": 3, "skipped": 12},
    })
    line = ops._source_line(sources)
    assert "zip_recruiter: blocked, skipped" in line and "skipped 12 queries" in line
