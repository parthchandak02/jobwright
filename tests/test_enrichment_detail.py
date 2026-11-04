"""Offline tests for detail-page enrichment (enrichment/detail.py).

A small fake Playwright page backed by BeautifulSoup serves the fake ATS
layouts in ``tests/fixtures/detail/``; the LLM tier uses a fake client. No
network, no real browser, no real LLM.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

import pytest
from bs4 import BeautifulSoup

from jobwright.enrichment import detail

FIXTURES = Path(__file__).parent / "fixtures" / "detail"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fake Playwright
# ---------------------------------------------------------------------------

class FakeElement:
    def __init__(self, tag, page):
        self.tag = tag
        self.page = page

    def inner_text(self):
        if self.tag.name == "script":
            return self.tag.string or ""
        return self.tag.get_text("\n", strip=True)

    def inner_html(self):
        return self.tag.decode_contents()

    def get_attribute(self, name):
        val = self.tag.get(name)
        if isinstance(val, list):
            return " ".join(val)
        return val

    def evaluate(self, script):
        if "tagName" in script:
            return self.tag.name
        if "parentElement" in script:
            parent = self.tag.parent
            a = parent.find("a", href=True) if parent is not None else None
            return urljoin(self.page.url, a["href"]) if a else None
        raise NotImplementedError(script)


class FakeResponse:
    def __init__(self, status):
        self.status = status


class FakePage:
    """Routes: url -> html | (status, html) | Exception."""

    def __init__(self, routes: dict, *, networkidle_fails: bool = True):
        self.routes = routes
        self.url = ""
        self.soup = BeautifulSoup("", "html.parser")
        self.visited: list[str] = []
        self.networkidle_fails = networkidle_fails

    def goto(self, url, timeout=None):
        self.visited.append(url)
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        status, html = route if isinstance(route, tuple) else (200, route)
        self.url = url
        self.soup = BeautifulSoup(html, "html.parser")
        return FakeResponse(status)

    def wait_for_load_state(self, state, timeout=None):
        if state == "networkidle" and self.networkidle_fails:
            raise TimeoutError("networkidle never reached")

    def title(self):
        return self.soup.title.get_text(strip=True) if self.soup.title else ""

    def query_selector(self, sel):
        tag = self.soup.select_one(sel)
        return FakeElement(tag, self) if tag is not None else None

    def query_selector_all(self, sel):
        return [FakeElement(t, self) for t in self.soup.select(sel)]

    def evaluate(self, script):
        body = self.soup.body
        return body.decode_contents() if body else ""


class FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.closed = False

    def new_context(self, **_kw):
        return self

    def new_page(self, **_kw):
        return self.page

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, page):
        self.chromium = self
        self.browser = FakeBrowser(page)
        self.launch_opts = None

    def launch(self, **kw):
        self.launch_opts = kw
        return self.browser

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeLLM:
    def __init__(self, reply: str | Exception):
        self.reply = reply
        self.prompts: list[str] = []

    def ask(self, prompt, **_kw):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture(autouse=True)
def _no_sponsorship_llm(monkeypatch):
    monkeypatch.setenv("SPONSORSHIP_LLM", "0")


@pytest.fixture()
def llm(monkeypatch):
    client = FakeLLM(
        '{"full_description": "<p>Run monthly close and the annual audit for twelve programs.</p>", '
        '"application_url": "https://example.com/apply/finance-manager"}'
    )
    monkeypatch.setattr(detail, "get_client", lambda: client)
    return client


@pytest.fixture()
def no_llm(monkeypatch):
    def boom():
        raise AssertionError("LLM tier should not run for this page")

    monkeypatch.setattr(detail, "get_client", boom)


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------

def test_resolve_url_rules(monkeypatch):
    monkeypatch.setattr(detail, "_load_base_urls", lambda: {"ExampleBoard": "https://board.example.com/"})
    assert detail.resolve_url("", "x") is None
    assert detail.resolve_url("https://a.example.com/j/1", "x") == "https://a.example.com/j/1"
    assert detail.resolve_url("slug", "WelcomeToTheJungle") is None
    assert detail.resolve_url("12345", "Randstad Canada") == "https://www.randstad.ca/jobs/search/12345"
    assert detail.resolve_url("/jobs", "4DayWeek") is None
    assert detail.resolve_url("/jobs/9;jsessionid=abc", "ExampleBoard") == "https://board.example.com/jobs/9"
    assert detail.resolve_url("/jobs/9", "UnknownBoard") is None


def test_resolve_all_urls_updates_relative_rows(monkeypatch):
    from jobwright.database import init_db

    monkeypatch.setattr(detail, "_load_base_urls", lambda: {"ExampleBoard": "https://board.example.com"})
    conn = init_db()
    conn.executemany(
        "INSERT INTO jobs (url, title, site, application_url) VALUES (?, ?, ?, ?)",
        [
            ("/jobs/1", "Rel", "ExampleBoard", "/apply/1"),
            ("/jobs/2", "Dup of abs", "ExampleBoard", None),
            ("https://board.example.com/jobs/2", "Abs", "ExampleBoard", None),
            ("/jobs/3", "No base", "Unknown", None),
        ],
    )
    conn.commit()
    stats = detail.resolve_all_urls(conn)
    assert stats == {"resolved": 2, "failed": 1, "already_absolute": 1, "app_resolved": 1}
    urls = {r[0] for r in conn.execute("SELECT url FROM jobs")}
    assert urls == {"https://board.example.com/jobs/1", "https://board.example.com/jobs/2", "/jobs/3"}
    app = conn.execute(
        "SELECT application_url FROM jobs WHERE url = 'https://board.example.com/jobs/1'"
    ).fetchone()[0]
    assert app == "https://board.example.com/apply/1"


# ---------------------------------------------------------------------------
# Tier 1 / 2 / 3 extraction per ATS layout
# ---------------------------------------------------------------------------

def test_workday_json_ld_tier1(no_llm):
    url = "https://samplecorp.wd5.myworkdayjobs.com/en-US/Careers/job/Remote/Senior-Analyst_R-1234"
    page = FakePage({url: _html("workday.html")})
    result = detail.scrape_detail_page(page, url)
    assert result["tier_used"] == 1
    assert result["status"] == "ok"
    assert result["application_url"] == url
    desc = result["full_description"]
    assert "Senior Analyst" in desc and "- Build quarterly dashboards" in desc
    assert "<p>" not in desc and "&lt;" not in desc


def test_json_ld_graph_direct_apply_and_contact():
    long = "Responsibilities include running programs and reporting to the board each quarter."
    graph = {"@graph": [{"@type": "Organization"}, {
        "@type": "JobPosting", "description": long, "directApply": True,
        "url": "https://example.com/jobs/1"}]}
    assert detail.extract_from_json_ld({"json_ld": [graph]})["application_url"] == "https://example.com/jobs/1"

    contact = [{"@type": "JobPosting", "description": long,
                "applicationContact": {"url": "https://example.com/apply/1"},
                "url": "https://example.com/jobs/1"}]
    assert detail.extract_from_json_ld({"json_ld": [contact]})["application_url"] == "https://example.com/apply/1"

    too_short = {"@type": "JobPosting", "description": "Short."}
    no_desc = {"@type": "JobPosting"}
    assert detail.extract_from_json_ld({"json_ld": [too_short, no_desc, {"@type": "Thing"}]}) is None


def test_greenhouse_tier2(no_llm):
    url = "https://boards.greenhouse.io/exampleorg/jobs/4001"
    page = FakePage({url: _html("greenhouse.html")})
    result = detail.scrape_detail_page(page, url)
    assert result["tier_used"] == 2
    assert result["status"] == "ok"
    assert "quarterly planning cycle" in result["full_description"]
    assert result["application_url"] == url + "#app"


def test_lever_tier2(no_llm):
    url = "https://jobs.lever.co/example-org/1111-2222"
    page = FakePage({url: _html("lever.html")})
    result = detail.scrape_detail_page(page, url)
    assert result["tier_used"] == 2
    assert "weekly operating review" in result["full_description"]
    assert result["application_url"] == "https://jobs.lever.co/example-org/1111-2222/apply"


def test_ashby_relative_apply_href_is_made_absolute(no_llm):
    url = "https://jobs.ashbyhq.com/sample-labs/9f8e7d"
    page = FakePage({url: _html("ashby.html")})
    result = detail.scrape_detail_page(page, url)
    assert result["tier_used"] == 2
    assert "analytics stack" in result["full_description"]
    assert result["application_url"] == "https://jobs.ashbyhq.com/sample-labs/9f8e7d/application"


def test_generic_article_and_text_apply_link(no_llm):
    url = "https://www.example.coop/careers/community-organizer"
    page = FakePage({url: _html("generic.html")})
    result = detail.scrape_detail_page(page, url)
    assert result["tier_used"] == 2
    assert result["full_description"].startswith("Community Organizer")
    # javascript: links are skipped; the relative href is resolved against the page
    assert result["application_url"] == "https://www.example.coop/careers/community-organizer/form"


def test_llm_fallback_tier3(llm):
    url = "https://www.example.org/jobs/finance-manager"
    page = FakePage({url: _html("llm_only.html")})
    result = detail.scrape_detail_page(page, url)
    assert result["tier_used"] == 3
    assert result["status"] == "ok"
    assert result["application_url"] == "https://example.com/apply/finance-manager"
    assert result["full_description"] == "Run monthly close and the annual audit for twelve programs."
    prompt = llm.prompts[0]
    assert "PAGE URL: https://www.example.org/jobs/finance-manager" in prompt
    assert "Opening: Finance Manager" in prompt
    assert "<style" not in prompt and "<header" not in prompt and "onclick" not in prompt


def test_llm_error_means_no_data(monkeypatch):
    monkeypatch.setattr(detail, "get_client", lambda: FakeLLM(RuntimeError("provider down")))
    url = "https://www.example.org/jobs/finance-manager"
    result = detail.scrape_detail_page(FakePage({url: _html("llm_only.html")}), url)
    assert result["tier_used"] == 3
    assert result["status"] == "error"
    assert result["error"] == "no data extracted"


def test_llm_apply_only_is_partial(monkeypatch):
    monkeypatch.setattr(detail, "get_client",
                        lambda: FakeLLM('{"full_description": null, "application_url": "https://example.com/a"}'))
    url = "https://www.example.org/jobs/finance-manager"
    result = detail.scrape_detail_page(FakePage({url: _html("llm_only.html")}), url)
    assert result["status"] == "partial"
    assert result["application_url"] == "https://example.com/a"


def test_empty_page_skips_llm(no_llm, monkeypatch):
    url = "https://www.example.org/empty"
    page = FakePage({url: "<html><body></body></html>"})
    result = detail.scrape_detail_page(page, url)
    assert result["status"] == "error"
    assert result["error"] == "no data extracted"


def test_http_404_and_navigation_errors(no_llm):
    page = FakePage({
        "https://example.com/gone": (404, "<html>gone</html>"),
        "https://example.com/slow": TimeoutError("Timeout 45000ms exceeded"),
        "https://example.com/dns": RuntimeError("net::ERR_NAME_NOT_RESOLVED"),
    })
    assert detail.scrape_detail_page(page, "https://example.com/gone")["error"] == "HTTP 404"
    assert detail.scrape_detail_page(page, "https://example.com/slow")["error"] == "timeout"
    assert "ERR_NAME_NOT_RESOLVED" in detail.scrape_detail_page(page, "https://example.com/dns")["error"]


def test_clean_description_html_and_plain():
    html = "<h2>Role</h2><p>Line one<br>Line two</p><ul><li>A</li><li>B</li></ul>"
    assert detail.clean_description(html) == "Role\nLine one\nLine two\n- A\n- B"
    assert detail.clean_description("  plain\n\n\n\ntext  ") == "plain\ntext"
    assert detail.clean_description("") == ""
    # entity-escaped HTML (common in JSON-LD) is parsed, not kept literally
    assert detail.clean_description("&lt;p&gt;Fish &amp;amp; chips&lt;/p&gt;&lt;ul&gt;&lt;li&gt;A&lt;/li&gt;&lt;/ul&gt;") == (
        "Fish & chips\n- A"
    )


def test_is_permanent_failure():
    assert detail._is_permanent_failure("HTTP 404")
    assert detail._is_permanent_failure("HTTP 410")
    assert detail._is_permanent_failure("This position is no longer accepting applications")
    assert not detail._is_permanent_failure("timeout")
    assert not detail._is_permanent_failure(None)


# ---------------------------------------------------------------------------
# scrape_site_batch: DB writes, auto-close, detail_error, budget
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    from jobwright.database import init_db

    return init_db()


def _insert(conn, url, title="Role", site="ExampleBoard", **cols):
    keys = ["url", "title", "site", *cols]
    conn.execute(
        f"INSERT INTO jobs ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
        (url, title, site, *cols.values()),
    )
    conn.commit()


def _row(conn, url):
    return dict(conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone())


def _patch_browser(monkeypatch, routes):
    page = FakePage(routes)
    pw = FakePlaywright(page)
    monkeypatch.setattr(detail, "sync_playwright", lambda: pw)
    return pw


def test_scrape_site_batch_writes_results_and_errors(db, monkeypatch, no_llm):
    ok_url = "https://www.example.coop/careers/community-organizer"
    gone = "https://example.com/jobs/gone"
    held = "https://example.com/jobs/held"
    prep = "https://example.com/jobs/in-prepare"
    flaky = "https://example.com/jobs/flaky"
    for u in (ok_url, gone, held, flaky):
        _insert(db, u)
    _insert(db, prep, funnel_stage="prepare")
    db.execute("UPDATE jobs SET board_updated_by = 'human' WHERE url = ?", (held,))
    db.commit()

    pw = _patch_browser(monkeypatch, {
        ok_url: _html("generic.html"),
        gone: (404, ""),
        held: (410, ""),
        prep: (404, ""),
        flaky: RuntimeError("net::ERR_CONNECTION_RESET"),
    })
    jobs = [(ok_url, "Organizer"), (gone, "Gone"), (held, None), (prep, "Prep"), (flaky, "Flaky")]
    stats = detail.scrape_site_batch(db, "ExampleBoard", jobs, delay=0)

    assert stats["processed"] == 5
    assert stats["ok"] == 1 and stats["error"] == 4
    assert stats["tiers"][2] == 1
    assert stats["auto_closed"] == 1
    assert pw.browser.closed

    ok = _row(db, ok_url)
    assert ok["full_description"].startswith("Community Organizer")
    assert ok["application_url"].endswith("/careers/community-organizer/form")
    assert ok["detail_scraped_at"] and ok["detail_error"] is None
    assert ok["sponsorship_status"] == "not_required"

    g = _row(db, gone)
    assert g["detail_error"] == "HTTP 404"
    assert g["funnel_stage"] == "closed" and g["outcome"] == "cancelled"
    assert g["board_updated_by"] == "system"

    h = _row(db, held)  # human-held card: error recorded, never closed
    assert h["detail_error"] == "HTTP 410"
    assert h["funnel_stage"] in (None, "backlog")

    p = _row(db, prep)  # past backlog: not auto-closed
    assert p["funnel_stage"] == "prepare"

    f = _row(db, flaky)  # transient error: recorded, not closed
    assert "ERR_CONNECTION_RESET" in f["detail_error"]
    assert f["funnel_stage"] in (None, "backlog")


def test_auto_close_dead_unknown_url(db):
    assert detail._auto_close_dead(db, "https://example.com/missing", "HTTP 404") is False


def test_scrape_site_batch_budget_and_limits(db, monkeypatch):
    from jobwright import stage_budget

    def no_browser():
        raise AssertionError("no browser when the budget is used up")

    monkeypatch.setattr(detail, "sync_playwright", no_browser)
    monkeypatch.setattr(stage_budget, "exceeded", lambda *a, **k: True)
    stats = detail.scrape_site_batch(db, "X", [("https://e.example.com/1", "A")], delay=0)
    assert stats["budget_skipped"] == 1 and stats["processed"] == 0
    assert detail.scrape_site_batch(db, "X", [], delay=0)["processed"] == 0


def test_scrape_site_batch_budget_runs_out_midway(db, monkeypatch, no_llm):
    from jobwright import stage_budget

    urls = [f"https://example.com/j/{i}" for i in range(3)]
    for u in urls:
        _insert(db, u)
    _patch_browser(monkeypatch, {u: (404, "") for u in urls})
    calls = {"n": 0}

    def exceeded(*_a, **_k):
        calls["n"] += 1
        return calls["n"] > 2  # pre-check + first job pass, then out of time

    monkeypatch.setattr(stage_budget, "exceeded", exceeded)
    stats = detail.scrape_site_batch(db, "X", [(u, "T") for u in urls], delay=0)
    assert stats["processed"] == 1
    assert stats["budget_skipped"] == 2


def test_scrape_site_batch_max_jobs_and_proxy(db, monkeypatch, no_llm):
    urls = [f"https://example.com/p/{i}" for i in range(3)]
    for u in urls:
        _insert(db, u)
    pw = _patch_browser(monkeypatch, {u: (404, "") for u in urls})
    monkeypatch.setattr(detail, "_PROXY_CONFIG", {"playwright": {"server": "http://proxy.example:8080"}})
    stats = detail.scrape_site_batch(db, "X", [(u, "T") for u in urls], delay=0, max_jobs=2)
    assert stats["processed"] == 2
    assert pw.launch_opts["proxy"] == {"server": "http://proxy.example:8080"}


def test_run_detail_scraper_groups_sites_and_skips(db, monkeypatch, no_llm):
    _insert(db, "https://example.com/a1", site="SiteA")
    _insert(db, "https://example.com/a2", site="SiteA")
    _insert(db, "https://example.com/b1", site="SiteB")
    _insert(db, "https://example.com/g1", site="glassdoor")
    _insert(db, "https://example.com/done", site="SiteA", detail_scraped_at="2026-11-01")
    _insert(db, "https://example.com/applied", site="SiteA", funnel_stage="applied")

    seen: list[tuple[str, list]] = []

    def fake_batch(conn, site, jobs, delay=2.0, max_jobs=None):
        seen.append((site, [u for u, _ in jobs]))
        return {"processed": len(jobs), "ok": len(jobs), "partial": 0, "error": 0,
                "tiers": {1: 0, 2: len(jobs), 3: 0}, "budget_skipped": 1}

    monkeypatch.setattr(detail, "scrape_site_batch", fake_batch)
    stats = detail._run_detail_scraper(db)
    assert dict(seen) == {"SiteA": ["https://example.com/a1", "https://example.com/a2"],
                          "SiteB": ["https://example.com/b1"]}
    assert stats["processed"] == 3 and stats["tiers"][2] == 3 and stats["budget_skipped"] == 2

    seen.clear()
    detail._run_detail_scraper(db, sites=["SiteB"])
    assert [s for s, _ in seen] == ["SiteB"]

    seen.clear()
    par = detail._run_detail_scraper(db, workers=2)
    assert sorted(s for s, _ in seen) == ["SiteA", "SiteB"]
    assert par["ok"] == 3


def test_run_detail_scraper_nothing_pending(db):
    assert detail._run_detail_scraper(db) == {"processed": 0, "ok": 0, "partial": 0, "error": 0}


def test_run_enrichment_end_to_end(db, monkeypatch, llm):
    monkeypatch.setattr(detail, "_load_base_urls", lambda: {"ExampleBoard": "https://www.example.org"})
    _insert(db, "/jobs/finance-manager", site="ExampleBoard")
    _patch_browser(monkeypatch, {"https://www.example.org/jobs/finance-manager": _html("llm_only.html")})
    stats = detail.run_enrichment(limit=5)
    assert stats["processed"] == 1 and stats["ok"] == 1 and stats["tiers"][3] == 1

    from jobwright.database import get_connection

    row = _row(get_connection(), "https://www.example.org/jobs/finance-manager")
    assert row["application_url"] == "https://example.com/apply/finance-manager"
    assert row["full_description"].startswith("Run monthly close")
