"""Offline tests for the deterministic impact-board scrapers.

Every HTTP call goes through ``httpx.MockTransport`` serving fake fixtures from
``tests/fixtures/impactboards/``; the Playwright boards use a fake browser. No
network, no LLM, no real browser.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from jobwright.discovery import impactboards as ib

FIXTURES = Path(__file__).parent / "fixtures" / "impactboards"


def _dates() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=2)
    old = now - timedelta(days=400)
    return {
        "{RECENT_RFC822}": format_datetime(recent),
        "{OLD_RFC822}": format_datetime(old),
        "{RECENT_ISO}": recent.strftime("%Y-%m-%d"),
        "{RECENT_MDY}": recent.strftime("%m/%d/%Y"),
        "{OLD_MDY}": old.strftime("%m/%d/%Y"),
    }


def _fixture(name: str) -> str:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    for key, value in _dates().items():
        text = text.replace(key, value)
    return text


SIS_SHEET = "1yM5Cd9EOPKGfrPtCM9ak5UFBCbJMkApqrUh9m6m_SxI"
CSR_SHEET = "15UJRVY12dQin55SdpFM0xt3xr7aWnRO9z3_Rgy4RIkE"


def _default_routes() -> dict[str, tuple[int, str]]:
    """URL (without query unless the board paginates by query) -> (status, body)."""
    return {
        "https://www.theimpactjob.com/rss/jobs": (200, _fixture("impact_job_rss.xml")),
        "https://jobs.thegiin.org/": (200, _fixture("giin_page1.html")),
        "https://jobs.thegiin.org/?page=2": (200, _fixture("giin_page2.html")),
        "https://careers.rippleworks.org/jobs": (200, _fixture("rippleworks.html")),
        "https://nextbillion.net/jobs/": (200, _fixture("nextbillion.html")),
        "https://www.findevgateway.org/jobs": (200, _fixture("findevgateway.html")),
        "https://members.women-wave.org/jobs/": (200, _fixture("wave.html")),
        "https://www.onpurposecareers.org/jobboard": (200, _fixture("onpurpose.html")),
        f"https://docs.google.com/spreadsheets/d/{SIS_SHEET}/gviz/tq": (200, _fixture("sheet_tracker.csv")),
        f"https://docs.google.com/spreadsheets/d/{CSR_SHEET}/gviz/tq": (200, _fixture("sheet_tracker.csv")),
    }


class _Recorder:
    def __init__(self, routes: dict[str, tuple[int, str]]):
        self.routes = routes
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        key = url
        if key not in self.routes:
            key = url.split("?")[0]
        if key not in self.routes:
            return httpx.Response(404, text="not found")
        status, body = self.routes[key]
        return httpx.Response(status, text=body)


@pytest.fixture()
def http(monkeypatch):
    """Route every impact-board HTTP call to the fixtures; returns the recorder."""
    rec = _Recorder(_default_routes())

    def fake_client() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(rec.handler), follow_redirects=True)

    monkeypatch.setattr(ib, "_client", fake_client)
    return rec


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def test_guess_location_and_clean():
    assert ib._clean("  a \n b\t c ") == "a b c"
    assert ib._clean(None) == ""
    assert ib._guess_location("Example Org | Oakland, CA | Full time") == "Oakland, CA"
    assert ib._guess_location("Fully Remote role") == "Remote"
    assert ib._guess_location("Nairobi, Kenya") is None


def test_recent_window_formats():
    now = datetime.now()
    assert ib._recent(None, 14) is True
    assert ib._recent("not a date", 14) is True
    assert ib._recent((now - timedelta(days=3)).strftime("%m/%d/%Y"), 14) is True
    assert ib._recent((now - timedelta(days=30)).strftime("%Y-%m-%d"), 14) is False
    assert ib._recent((now - timedelta(days=30)).strftime("%b %d, %Y"), 14) is False


def test_recent_understands_rss_rfc822_dates():
    """RSS 2.0 pubDate is RFC 822; the age window must apply to it (regression)."""
    now = datetime.now(timezone.utc)
    assert ib._recent(format_datetime(now - timedelta(days=1)), 14) is True
    assert ib._recent(format_datetime(now - timedelta(days=60)), 14) is False


def test_env_caps_fall_back_on_bad_values(monkeypatch):
    monkeypatch.setenv("IMPACT_BOARDS_MAX_AGE_DAYS", "x")
    monkeypatch.setenv("IMPACT_BOARDS_MAX_PER_BOARD", "y")
    assert ib._max_age_days() == 14
    assert ib._max_per_board() == 150
    monkeypatch.setenv("IMPACT_BOARDS_MAX_AGE_DAYS", "3")
    monkeypatch.setenv("IMPACT_BOARDS_MAX_PER_BOARD", "2")
    assert ib._max_age_days() == 3
    assert ib._max_per_board() == 2


def test_rss_items_reads_atom_feeds():
    atom = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Atom Role</title><link href="https://example.com/jobs/atom-1"/></entry>
</feed>"""
    items = ib._rss_items(atom)
    assert items[0]["title"] == "Atom Role"
    assert items[0]["link"] == "https://example.com/jobs/atom-1"


# ---------------------------------------------------------------------------
# per-board parsers
# ---------------------------------------------------------------------------

def test_fetch_impact_job_parses_rss_and_drops_stale(http):
    jobs = ib.fetch_impact_job()
    by_title = {j["title"]: j for j in jobs}
    assert set(by_title) == {"Program Director, Climate Grants", "Partnerships Manager",
                             "Development Associate"}
    pd = by_title["Program Director, Climate Grants"]
    assert pd["url"] == "https://www.theimpactjob.com/jobs/program-director-climate-grants-1001"
    assert pd["company"] == "Example Org"
    assert pd["location"] == "San Francisco, CA"
    assert pd["description"].startswith("Lead a portfolio")
    # empty fields become None, not ""
    da = by_title["Development Associate"]
    assert da["company"] is None and da["location"] is None and da["description"] is None


def test_fetch_giin_paginates_two_pages_and_dedupes(http):
    jobs = ib.fetch_giin()
    urls = [j["url"] for j in jobs]
    assert urls == [
        "https://jobs.thegiin.org/job/101/impact-measurement-analyst/",
        "https://jobs.thegiin.org/job/102/director-of-investments/",
        "https://jobs.thegiin.org/job/201/portfolio-associate/",
    ]
    assert jobs[0]["title"] == "Impact Measurement Analyst"
    # _guess_location is greedy and keeps preceding capitalised words from the
    # card ("Example Impact Fund New York, NY"); filters still match on the city.
    assert jobs[0]["location"].endswith("New York, NY")
    assert jobs[1]["location"] == "Remote"
    # hard page cap: never asks for page 3
    assert not any("page=3" in u for u in http.requests)


def test_fetch_giin_stops_on_error_page(http):
    http.routes["https://jobs.thegiin.org/?page=2"] = (503, "busy")
    jobs = ib.fetch_giin()
    assert len(jobs) == 2


def test_fetch_giin_stops_on_empty_page(http):
    http.routes["https://jobs.thegiin.org/"] = (200, "<html><body>No jobs today</body></html>")
    assert ib.fetch_giin() == []
    assert not any("page=2" in u for u in http.requests)


def test_fetch_rippleworks_derives_company_from_url(http):
    jobs = ib.fetch_rippleworks()
    assert [(j["title"], j["company"]) for j in jobs] == [
        ("Head of Operations", "Example Org"),
        ("Country Director", "Sample Health Co"),
    ]
    assert jobs[0]["url"] == "https://careers.rippleworks.org/companies/example-org/jobs/555001-head-of-operations"
    assert jobs[1]["url"].endswith("555002-country-director")  # query stripped
    assert jobs[0]["location"].endswith("Oakland, CA")
    assert jobs[1]["location"] is None  # Nairobi is not a recognised hint


def test_fetch_nextbillion_only_single_slug_job_pages(http):
    jobs = ib.fetch_nextbillion()
    assert [j["url"] for j in jobs] == [
        "https://nextbillion.net/jobs/senior-program-officer-example-org/",
        "https://nextbillion.net/jobs/research-fellow-sample-institute/",
    ]
    assert jobs[0]["location"] == "Washington, DC"


def test_fetch_findevgateway(http):
    jobs = ib.fetch_findevgateway()
    assert [j["title"] for j in jobs] == ["Financial Inclusion Specialist", "Summer Internship"]
    assert jobs[0]["url"] == "https://www.findevgateway.org/jobs-internships/financial-inclusion-specialist"


def test_fetch_wave_location_from_anchor_or_card(http):
    jobs = ib.fetch_wave()
    assert [j["url"] for j in jobs] == [
        "https://members.women-wave.org/jobs/Details/9001",
        "https://members.women-wave.org/jobs/Details/9002",
    ]
    assert jobs[0]["location"].endswith("New York, NY")
    assert jobs[1]["location"].endswith("Chicago, IL")


def test_fetch_onpurpose_follows_apply_links_to_ats(http):
    jobs = ib.fetch_onpurpose()
    assert [(j["title"], j["url"]) for j in jobs] == [
        ("Chief of Staff", "https://boards.example-ats.com/example-org/jobs/7001"),
        ("Operations Lead", "https://jobs.example-ats.com/sample-foundation/7002"),
    ]
    assert jobs[0]["location"] == "San Francisco, CA"
    assert jobs[1]["location"] == "Remote"


def test_sheet_boards_map_columns_and_drop_old_rows(http):
    jobs = ib.fetch_sis_global()
    assert [j["title"] for j in jobs] == ["Social Impact Manager", "CSR Program Lead"]
    first = jobs[0]
    assert first == {
        "url": "https://jobs.example.com/example-org/social-impact-manager",
        "title": "Social Impact Manager",
        "company": "Example Org",
        "location": "San Francisco, CA",
        "salary": "$120,000 - $140,000",
        "description": None,
    }
    assert jobs[1]["salary"] is None
    assert len(ib.fetch_csr_jobs_sheet()) == 2
    assert any("tqx=out:csv" in u for u in http.requests)


def test_sheet_jobs_without_age_window_keeps_old_rows(http):
    jobs = ib._sheet_jobs(SIS_SHEET, None)
    assert "Old Sustainability Role" in [j["title"] for j in jobs]


def test_http_error_raises_for_single_page_boards(http):
    http.routes["https://careers.rippleworks.org/jobs"] = (500, "boom")
    with pytest.raises(httpx.HTTPStatusError):
        ib.fetch_rippleworks()


# ---------------------------------------------------------------------------
# browser boards (fake Playwright)
# ---------------------------------------------------------------------------

class _FakePage:
    def __init__(self, pages: dict[str, str], fail: set[str]):
        self.pages = pages
        self.fail = fail
        self.current = ""
        self.mouse = self

    def goto(self, url, **_kw):
        if url in self.fail:
            raise RuntimeError("navigation blocked")
        self.current = url

    def wait_for_timeout(self, _ms):
        return None

    def wheel(self, _x, _y):
        raise RuntimeError("no mouse in headless fake")  # exercised: must be swallowed

    def content(self):
        return self.pages[self.current]


class _FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.closed = False

    def new_page(self, **_kw):
        return self.page

    def close(self):
        self.closed = True


class _FakePlaywright:
    def __init__(self, browser):
        self.chromium = self
        self._browser = browser

    def launch(self, **_kw):
        return self._browser

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install_fake_playwright(monkeypatch, pages, fail=()):
    import playwright.sync_api as pw

    browser = _FakeBrowser(_FakePage(pages, set(fail)))
    monkeypatch.setattr(pw, "sync_playwright", lambda: _FakePlaywright(browser))
    return browser


def test_browser_fetch_parses_each_board_and_isolates_failures(monkeypatch):
    browser = _install_fake_playwright(
        monkeypatch,
        {"https://skoll.org/community/jobs/": _fixture("skoll.html"),
         "https://careers.netimpact.org/": _fixture("netimpact.html")},
        fail={"https://careers.netimpact.org/"},
    )
    out = ib._browser_fetch(ib.BROWSER_BOARDS)
    assert out["Net Impact"] == []
    skoll = out["Skoll Foundation"]
    assert len(skoll) == 1
    assert skoll[0]["url"] == "https://skoll.org/job/director-of-learning-example-org/"
    assert skoll[0]["title"].startswith("Director of Learning")
    assert skoll[0]["location"] == "Remote"
    assert browser.closed


def test_browser_fetch_net_impact(monkeypatch):
    _install_fake_playwright(
        monkeypatch,
        {"https://skoll.org/community/jobs/": "<html></html>",
         "https://careers.netimpact.org/": _fixture("netimpact.html")},
    )
    out = ib._browser_fetch(ib.BROWSER_BOARDS)
    assert out["Skoll Foundation"] == []
    assert out["Net Impact"][0]["url"] == "https://careers.netimpact.org/job/sustainability-analyst-sample-corp"
    assert out["Net Impact"][0]["location"].endswith("Seattle, WA")


# ---------------------------------------------------------------------------
# run_impact_boards: isolation, caps, filters, storage
# ---------------------------------------------------------------------------

@pytest.fixture()
def search_cfg():
    """Write a sandbox searches.yaml: accept SF/NY/DC, reject London, drop interns."""
    from jobwright import config

    path = Path(config.SEARCH_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "location:\n"
        "  accept_patterns: ['San Francisco', 'New York', 'Washington', 'Oakland']\n"
        "  reject_patterns: ['London']\n"
        "exclude_titles: ['Internship']\n",
        encoding="utf-8",
    )
    return path


def _db_rows():
    from jobwright.database import get_connection

    conn = get_connection()
    return [dict(r) for r in conn.execute("SELECT url, title, site, strategy, company, location FROM jobs")]


def test_run_impact_boards_skipped_by_env(monkeypatch):
    monkeypatch.setenv("IMPACT_BOARDS", "0")
    assert ib.run_impact_boards() == {"skipped": "IMPACT_BOARDS=0"}


def test_run_impact_boards_isolates_board_failures_and_stores(http, search_cfg, monkeypatch):
    http.routes["https://careers.rippleworks.org/jobs"] = (500, "boom")

    def explode():
        raise RuntimeError("parser bug")

    monkeypatch.setattr(
        ib, "HTTP_BOARDS",
        [(n, explode if n == "WAVE" else fn) for n, fn in ib.HTTP_BOARDS],
    )
    report = ib.run_impact_boards(workers=3, include_browser=False)

    assert report["Rippleworks"]["error"].startswith("HTTPStatusError")
    assert report["Rippleworks"]["new"] == 0
    assert report["WAVE"]["error"] == "RuntimeError: parser bug"

    giin = report["GIIN"]
    # Boston is outside the accept list, so 1 of the 3 GIIN jobs is filtered out
    assert giin == {"jobs": 3, "kept": 3, "new": 2, "existing": 0, "error": None}
    # FinDev: the internship is dropped by exclude_titles
    assert report["FinDev Gateway"]["jobs"] == 2
    assert report["FinDev Gateway"]["new"] == 1
    # both sheets carry the same rows: second one sees them as existing
    sheets = report["SIS Global (sheet)"], report["CSR Jobs (sheet)"]
    assert sorted((s["new"], s["existing"]) for s in sheets) == [(0, 2), (2, 0)]
    # browser boards were not run: present in report, but empty
    assert report["Skoll Foundation"]["jobs"] == 0

    rows = _db_rows()
    assert {r["strategy"] for r in rows} == {"impact_board"}
    urls = {r["url"] for r in rows}
    assert "https://jobs.thegiin.org/job/101/impact-measurement-analyst/" in urls
    assert not any("summer-internship" in u for u in urls)
    assert report["_total_new"] == len(rows)
    giin_row = next(r for r in rows if r["url"].endswith("/job/101/impact-measurement-analyst/"))
    assert giin_row["site"] == "GIIN"


def test_run_impact_boards_location_filter(http, search_cfg, monkeypatch):
    monkeypatch.setattr(
        ib, "fetch_rippleworks",
        lambda: [
            {"url": "https://example.com/j/1", "title": "Ops Lead", "location": "London, UK"},
            {"url": "https://example.com/j/2", "title": "Ops Lead", "location": "Oakland, CA"},
            {"url": "https://example.com/j/3", "title": "Ops Lead", "location": "Denver, CO"},
            {"url": "https://example.com/j/4", "title": "Ops Lead", "location": None},
        ],
    )
    monkeypatch.setattr(ib, "HTTP_BOARDS", [("Rippleworks", ib.fetch_rippleworks)])
    report = ib.run_impact_boards(include_browser=False)
    assert report["Rippleworks"]["new"] == 2
    assert {r["url"] for r in _db_rows()} == {"https://example.com/j/2", "https://example.com/j/4"}


def test_run_impact_boards_per_board_cap(http, search_cfg, monkeypatch):
    monkeypatch.setenv("IMPACT_BOARDS_MAX_PER_BOARD", "2")
    monkeypatch.setattr(ib, "HTTP_BOARDS", [("GIIN", ib.fetch_giin)])
    report = ib.run_impact_boards(include_browser=False)
    assert report["GIIN"]["jobs"] == 3
    assert report["GIIN"]["kept"] == 2
    assert report["GIIN"]["new"] == 2


def test_run_impact_boards_second_run_counts_existing(http, search_cfg, monkeypatch):
    monkeypatch.setattr(ib, "HTTP_BOARDS", [("GIIN", ib.fetch_giin)])
    first = ib.run_impact_boards(include_browser=False)
    second = ib.run_impact_boards(include_browser=False)
    assert first["GIIN"]["new"] == 2  # Boston row is location-filtered
    assert second["GIIN"]["new"] == 0
    assert second["GIIN"]["existing"] == 2
    assert second["_total_new"] == 0


def test_run_impact_boards_browser_results_and_crash(http, search_cfg, monkeypatch):
    monkeypatch.setattr(ib, "HTTP_BOARDS", [])
    monkeypatch.setattr(ib, "_browser_fetch", lambda targets: {
        "Skoll Foundation": [{"url": "https://skoll.org/job/x/", "title": "Director", "location": "Remote"}],
        "Net Impact": [],
    })
    report = ib.run_impact_boards()  # include_browser defaults on
    assert report["Skoll Foundation"]["new"] == 1
    assert report["Net Impact"]["error"] is None

    def crash(_targets):
        raise RuntimeError("chromium missing")

    monkeypatch.setattr(ib, "_browser_fetch", crash)
    report = ib.run_impact_boards()
    assert report["Skoll Foundation"]["error"] == "browser: RuntimeError: chromium missing"
    assert report["Net Impact"]["error"].startswith("browser:")


def test_run_impact_boards_browser_env_off(http, search_cfg, monkeypatch):
    monkeypatch.setenv("IMPACT_BOARDS_BROWSER", "0")
    monkeypatch.setattr(ib, "HTTP_BOARDS", [])

    def must_not_run(_targets):
        raise AssertionError("browser boards should be skipped")

    monkeypatch.setattr(ib, "_browser_fetch", must_not_run)
    report = ib.run_impact_boards()
    assert report["_total_new"] == 0


def test_strip_tracking_keeps_needed_params():
    assert ib._strip_tracking(
        "https://ats.example.com/r.html?cid=1&jobId=9?utm_source=onpurposecareers"
    ) == "https://ats.example.com/r.html?cid=1&jobId=9"
    assert ib._strip_tracking("https://x.example.com/job/1?ref=onpurpose&gh_src=a") == (
        "https://x.example.com/job/1?gh_src=a"
    )
    assert ib._strip_tracking("https://x.example.com/job/2/") == "https://x.example.com/job/2/"


def test_parse_onpurpose_rendered_cards_read_title_and_company():
    html = """<div class="grid">
      <div class="item"><div><h5>Director of Programs</h5><h6>Example Org</h6><p>Remote</p></div>
        <a href="https://apply.example-ats.com/example-org/j/1?utm_source=onpurposecareers">Apply Now</a></div>
      <div class="item"><div><h5>Program Officer</h5><h6>Sample Foundation</h6><p>Oakland, CA</p></div>
        <a href="https://jobs.example.com/rec.html?cid=7&jobId=2?utm_source=onpurposecareers">Apply Now</a></div>
    </div>"""
    jobs = ib.parse_onpurpose(html)
    assert [(j["title"], j["company"]) for j in jobs] == [
        ("Director of Programs", "Example Org"), ("Program Officer", "Sample Foundation"),
    ]
    assert jobs[0]["url"] == "https://apply.example-ats.com/example-org/j/1"
    assert jobs[1]["url"] == "https://jobs.example.com/rec.html?cid=7&jobId=2"


def test_browser_board_with_zero_cards_is_reported_as_error(http, search_cfg, monkeypatch):
    monkeypatch.setattr(ib, "_browser_fetch", lambda targets: {n: [] for n, _, _ in targets})
    monkeypatch.setattr(
        ib, "_browser_fetch_parsed",
        lambda targets: {"__errors__": {"On Purpose": "browser: RuntimeError: rendered page had 0 job cards"}},
    )
    report = ib.run_impact_boards(workers=2, include_browser=True)
    assert "0 job cards" in report["On Purpose"]["error"]
