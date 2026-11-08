"""Application-URL resolution (enrichment/apply_url.py). No network: httpx.MockTransport."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from jobwright.discovery import linkedin
from jobwright.enrichment import apply_url as au

GH_URL = "https://boards.greenhouse.io/exampleorg/jobs/4001234?gh_src=abc"
LI_PAGE = """
<html><body>
<div class="top-card-layout">
  <code id="applyUrl" style="display: none"><!--"https://www.linkedin.com/jobs/view/externalApply/3900000001?url={enc}&urlHash=Ab12&refId=x"--></code>
  <a class="apply-button" data-tracking-control-name="public_jobs_apply-link-offsite" href="#">Apply</a>
</div>
<div class="show-more-less-html__markup"><p>Own the quarterly planning process.</p></div>
</body></html>
"""
LI_EASY_APPLY = """
<html><body><button data-tracking-control-name="public_jobs_apply-link-onsite">Easy Apply</button>
<div class="show-more-less-html__markup"><p>Easy apply role.</p></div></body></html>
"""


def _li_page(target: str = GH_URL) -> str:
    return LI_PAGE.replace("{enc}", quote(target, safe=""))


def _http(handler) -> au.Http:
    return au.Http(httpx.Client(transport=httpx.MockTransport(handler)),
                   au.HostPacer(interval=0, sleep=lambda s: None))


# -- parsing / unwrapping -----------------------------------------------------------

def test_parse_linkedin_offsite_decodes_external_apply():
    assert au.parse_linkedin_offsite(_li_page()) == GH_URL
    assert au.parse_linkedin_offsite(LI_EASY_APPLY) is None
    # Offsite anchor with a LinkedIn redirect wrapper.
    html = ('<a data-tracking-control-name="public_jobs_apply-link-offsite_sign-up-modal" '
            'href="https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fjobs.lever.co%2Fexampleorg%2Fabc'
            '&amp;urlhash=1">Apply</a>')
    assert au.parse_linkedin_offsite(html) == "https://jobs.lever.co/exampleorg/abc"


def test_unwrap_redirect_params_nested_and_tracking():
    inner = "https://jobs.ashbyhq.com/exampleorg/1f2e?utm_source=agg&src=x"
    once = "https://click.agg.example.net/r?dest=" + quote(inner, safe="")
    twice = "https://track.example.net/c?u=" + quote(once, safe="")
    assert au.unwrap_redirect_params(twice) == "https://jobs.ashbyhq.com/exampleorg/1f2e?src=x"
    assert au.unwrap_redirect_params("https://example.org/jobs/1") == "https://example.org/jobs/1"


def test_url_classes():
    assert au.is_linkedin_url("https://www.linkedin.com/signup/cold-join?session_redirect=x")
    assert not au.is_employer_url("https://www.linkedin.com/signup/cold-join?session_redirect=x")
    assert not au.is_employer_url("None")
    assert au.is_aggregator_url("https://www.jobright.ai/jobs/info/123")
    assert not au.is_employer_url("https://jobright.ai/jobs/info/123")
    assert au.is_employer_url("https://careers.example.org/jobs/1")
    assert au.is_employer_url("https://jobs.lever.co/exampleorg/1")
    assert au.linkedin_job_id("https://www.linkedin.com/jobs/view/senior-analyst-at-example-org-3900000001") \
        == "3900000001"


# -- LinkedIn ---------------------------------------------------------------------

def test_guest_client_keeps_offsite_url_from_description_fetch():
    def handler(request):
        if "/jobs/view/3900000001" in str(request.url):
            return httpx.Response(200, text=_li_page())
        if "/jobs/view/3900000002" in str(request.url):
            return httpx.Response(200, text=LI_EASY_APPLY)
        return httpx.Response(404)

    client = linkedin.GuestClient(interval=0, sleep=lambda s: None, transport=httpx.MockTransport(handler))
    assert "quarterly planning" in client.description("3900000001")
    assert client.apply_url("3900000001") == GH_URL
    client.description("3900000002")
    assert client.apply_url("3900000002") is None
    assert client.requests == 2  # no extra request for the apply link


def test_linkedin_offsite_uses_breaker_and_guest_detail_card():
    from jobwright.discovery.site_breaker import SiteBreaker

    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=_li_page())

    client = linkedin.GuestClient(interval=0, sleep=lambda s: None, transport=httpx.MockTransport(handler))
    breaker = SiteBreaker(None, threshold=1)
    off = au.LinkedInOffsite(client, breaker)
    assert off.offsite_url("3900000001") == GH_URL
    assert "jobs-guest/jobs/api/jobPosting/3900000001" in seen[0]
    breaker.record_blocked("linkedin", "rate_limited")
    with pytest.raises(linkedin.RateLimited):
        off.offsite_url("3900000001")
    assert len(seen) == 1  # an open breaker sends nothing


def test_linkedin_429_opens_breaker():
    from jobwright.discovery.site_breaker import SiteBreaker

    client = linkedin.GuestClient(interval=0, sleep=lambda s: None, max_retries=0,
                                  transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    breaker = SiteBreaker(None, threshold=1)
    with pytest.raises(linkedin.RateLimited):
        au.LinkedInOffsite(client, breaker).offsite_url("1")
    assert breaker.is_open("linkedin")


# -- redirects ---------------------------------------------------------------------

def test_follow_redirects_stops_at_employer_without_fetching_it():
    fetched = []

    def handler(request):
        url = str(request.url)
        fetched.append(url)
        if url.startswith("https://www.jobright.ai/jobs/info/1"):
            return httpx.Response(302, headers={"location": "https://out.talent.com/go?id=9"})
        if url.startswith("https://out.talent.com/go"):
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text='<meta http-equiv="refresh" content="0; url=https://jobs.lever.co/exampleorg/abc">')
        raise AssertionError("employer page must not be fetched: " + url)

    final = au.follow_redirects("https://www.jobright.ai/jobs/info/1", _http(handler))
    assert final == "https://jobs.lever.co/exampleorg/abc"
    assert len(fetched) == 2


def test_follow_redirects_finds_single_ats_link_and_respects_limit():
    def handler(request):
        if "loop" in str(request.url):
            return httpx.Response(302, headers={"location": "https://www.lensa.com/loop?n=1"})
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text='<a href="https://job-boards.greenhouse.io/exampleorg/jobs/77">Apply</a>'
                                   '<a href="/about">About</a>')

    http = _http(handler)
    assert au.follow_redirects("https://www.lensa.com/job/1", http) == \
        "https://job-boards.greenhouse.io/exampleorg/jobs/77"
    before = http.requests
    assert au.is_aggregator_url(au.follow_redirects("https://www.lensa.com/loop", http))
    assert http.requests - before == au.MAX_REDIRECTS + 1


# -- ATS boards --------------------------------------------------------------------

def _board_handler(calls: list[str]):
    lever = [
        {"id": "aaa-1", "text": "Senior Data Analyst", "categories": {"location": "Austin, TX"},
         "applyUrl": "https://jobs.lever.co/example-org/aaa-1/apply"},
        {"id": "aaa-2", "text": "Senior Data Analyst", "categories": {"location": "Denver, CO"},
         "applyUrl": "https://jobs.lever.co/example-org/aaa-2/apply"},
        {"id": "aaa-3", "text": "Product Designer", "categories": {"location": "Remote"},
         "applyUrl": "https://jobs.lever.co/example-org/aaa-3/apply"},
    ]

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url.startswith("https://api.lever.co/v0/postings/example-org"):
            return httpx.Response(200, json=lever)
        if url.startswith("https://boards-api.greenhouse.io/v1/boards/hintedboard/jobs"):
            return httpx.Response(200, json={"jobs": [
                {"id": 4001, "title": "Strategy & Operations Manager (Remote)", "location": {"name": "Remote"},
                 "absolute_url": "https://www.example.org/careers?gh_jid=4001"}]})
        if url.startswith("https://api.ashbyhq.com/posting-api/job-board/ashbyorg"):
            return httpx.Response(200, json={"jobs": [
                {"id": "1f2e", "title": "Staff Engineer", "location": "Remote",
                 "jobUrl": "https://jobs.ashbyhq.com/ashbyorg/1f2e"}]})
        return httpx.Response(404, json={"error": "not found"})

    return handler


def test_title_normalization():
    assert au.title_score("Sr. Data Analyst", "Senior Data Analyst") == 1.0
    assert au.title_score("Strategy and Operations Manager", "Strategy & Operations Manager (Remote)") >= 0.95
    assert au.title_score("Data Analyst", "Product Designer") < 0.5
    assert au.slug_candidates("Example Org, Inc.") == ["exampleorg", "example-org", "exampleorginc", "example-org-inc"]


def test_board_index_matches_title_and_location_and_caches(tmp_path: Path):
    calls: list[str] = []
    cache = tmp_path / "ats_board_cache.json"
    boards = au.BoardIndex(_http(_board_handler(calls)), cache)
    p = boards.find("Example Org, Inc.", "Sr. Data Analyst", "Denver, Colorado")
    assert p and p.url == "https://jobs.lever.co/example-org/aaa-2/apply" and p.family == "lever"
    # Same title in two cities and no location to break the tie: ambiguous, no match.
    assert boards.find("Example Org, Inc.", "Senior Data Analyst", None) is None
    boards.save()
    assert json.loads(cache.read_text())["companies"]["example org"]["slug"] == "example-org"

    calls.clear()
    again = au.BoardIndex(_http(_board_handler(calls)), cache)
    assert again.find("Example Org", "Product Designer").url.endswith("/aaa-3/apply")
    assert calls == ["https://api.lever.co/v0/postings/example-org?mode=json"]  # straight to the cached board


def test_board_index_uses_description_hints_and_remembers_misses(tmp_path: Path):
    calls: list[str] = []
    boards = au.BoardIndex(_http(_board_handler(calls)), tmp_path / "c.json")
    hints = au.slug_hints("Apply at https://boards.greenhouse.io/hintedboard/jobs/4001 today")
    assert hints == [("greenhouse", "hintedboard")]
    p = boards.find("Unrelated Name Co", "Strategy and Operations Manager", "Remote", hints)
    assert p.url == "https://job-boards.greenhouse.io/hintedboard/jobs/4001"

    assert boards.find("Nowhere Labs", "Analyst") is None
    n = len(calls)
    assert boards.find("Nowhere Labs", "Analyst") is None
    assert len(calls) == n  # cached miss: no new probes

    p = au.BoardIndex(_http(_board_handler([])), None).find("AshbyOrg", "Staff Engineer")
    assert p.url == "https://jobs.ashbyhq.com/ashbyorg/1f2e/application" and p.family == "ashby"


# -- resolver + stage runner -------------------------------------------------------

class FakeLinkedIn:
    def __init__(self, urls: dict[str, str | None], rate_limited: set[str] = frozenset()):
        self.urls = urls
        self.rate_limited = rate_limited

    def offsite_url(self, job_id):
        if job_id in self.rate_limited:
            raise linkedin.RateLimited(job_id)
        return self.urls.get(job_id)


@pytest.fixture()
def db(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.database import close_connection, get_connection, init_db

    path = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    close_connection(path)
    init_db(path)
    conn = get_connection(path)
    yield conn
    close_connection(path)


def _insert(conn, url, *, site, company, title, score, application_url=None, description=None):
    conn.execute(
        "INSERT INTO jobs (url, site, company, title, location, fit_score, application_url, full_description) "
        "VALUES (?, ?, ?, ?, 'Remote', ?, ?, ?)",
        (url, site, company, title, score, application_url, description),
    )
    conn.commit()


def test_run_resolution_end_to_end(db):
    li_offsite = "https://www.linkedin.com/jobs/view/3900000001"
    li_easy = "https://www.linkedin.com/jobs/view/3900000002"
    li_limited = "https://www.linkedin.com/jobs/view/3900000003"
    agg = "https://www.indeed.com/viewjob?jk=abc"
    _insert(db, li_offsite, site="linkedin", company="Example Org", title="Planner", score=8)
    _insert(db, li_easy, site="linkedin", company="Example Org, Inc.", title="Product Designer", score=9,
            application_url="https://www.linkedin.com/signup/cold-join?x=1")
    _insert(db, li_limited, site="linkedin", company="Quiet Co", title="Analyst", score=7)
    _insert(db, agg, site="indeed", company="Sample Works", title="Analyst", score=7,
            application_url="https://www.jobright.ai/jobs/info/1")
    _insert(db, "https://www.linkedin.com/jobs/view/3900000004", site="linkedin", company="Example Org",
            title="Planner", score=5)
    _insert(db, "https://careers.example.org/j/1", site="ExampleBoard", company="Example Org", title="Planner",
            score=8, application_url="https://careers.example.org/j/1/apply")

    def handler(request):
        url = str(request.url)
        if url.startswith("https://www.jobright.ai/"):
            return httpx.Response(301, headers={"location": "https://exampleworks.applytojob.com/apply/x1"})
        return _board_handler([])(request)

    http = _http(handler)
    resolver = au.Resolver(http, au.BoardIndex(http, None),
                           FakeLinkedIn({"3900000001": GH_URL}, rate_limited={"3900000003"}),
                           au.DEFAULT_AGGREGATOR_HOSTS)
    stats = au.run_apply_url_resolution(db, resolver=resolver, exceeded=lambda: False)
    assert stats["candidates"] == 4 and stats["resolved"] == 3 and stats["rate_limited"] == 1
    assert stats["by_source"] == {"linkedin_offsite": 1, "ats_board": 1, "redirect": 1}

    row = lambda u: db.execute(  # noqa: E731
        "SELECT application_url, application_url_source, application_ats, application_url_checked_at "
        "FROM jobs WHERE url = ?", (u,)).fetchone()
    assert tuple(row(li_offsite))[:3] == (GH_URL, "linkedin_offsite", "greenhouse")
    assert tuple(row(li_easy))[:3] == ("https://jobs.lever.co/example-org/aaa-3/apply", "ats_board", "lever")
    assert tuple(row(agg))[:3] == ("https://exampleworks.applytojob.com/apply/x1", "redirect", "applytojob")
    assert row(li_limited)[3] is None  # throttled: retried next run, not stamped as a miss
    assert row("https://www.linkedin.com/jobs/view/3900000004")[0] is None  # below the score bar
    assert tuple(row("https://careers.example.org/j/1"))[:3] == \
        ("https://careers.example.org/j/1/apply", None, "other")  # ATS family backfilled only

    from jobwright.config import is_apply_blocked_job

    assert not is_apply_blocked_job("linkedin", li_offsite, row(li_offsite)[0])
    # Second run: nothing left to do (resolved ones are employer URLs; throttled one is retried).
    stats2 = au.run_apply_url_resolution(db, resolver=resolver, exceeded=lambda: False)
    assert stats2["candidates"] == 1


def test_run_resolution_stamps_misses_and_obeys_budget(db):
    _insert(db, "https://www.linkedin.com/jobs/view/1000001", site="linkedin", company="Nobody Here",
            title="Analyst", score=8)
    _insert(db, "https://www.linkedin.com/jobs/view/1000002", site="linkedin", company="Nobody Here",
            title="Analyst II", score=8)
    http = _http(lambda r: httpx.Response(404))
    resolver = au.Resolver(http, au.BoardIndex(http, None), FakeLinkedIn({}), au.DEFAULT_AGGREGATOR_HOSTS)
    ticks = iter([False, True])
    stats = au.run_apply_url_resolution(db, resolver=resolver, exceeded=lambda: next(ticks))
    assert stats["missed"] == 1 and stats["budget_skipped"] == 1
    checked = [r[0] for r in db.execute("SELECT application_url_checked_at FROM jobs")]
    assert sum(1 for c in checked if c) == 1


def test_jobspy_direct_url_treats_none_strings_as_missing():
    from jobwright.discovery.jobspy import _direct_url

    for junk in (None, float("nan"), "None", "nan", "", "  ", "/relative",
                 "https://www.linkedin.com/signup/cold-join?session_redirect=x"):
        assert _direct_url(junk) is None, junk
    assert _direct_url("https://jobs.lever.co/exampleorg/1") == "https://jobs.lever.co/exampleorg/1"
