"""Offline tests for the Workday CXS scraper (discovery/workday.py).

``_urlopen`` is replaced with a fake that serves canned CXS JSON, so no
request leaves the machine. Employers and jobs are placeholders.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from jobwright.discovery import workday as wd

EMP = {
    "name": "Sample Corp",
    "base_url": "https://samplecorp.wd5.myworkdayjobs.com",
    "site_id": "en-US/Careers",
    "tenant": "samplecorp",
}
EMPLOYERS = {"samplecorp": EMP}
SEARCH_URL = "https://samplecorp.wd5.myworkdayjobs.com/wday/cxs/samplecorp/en-US/Careers/jobs"


def _posting(i: int, loc: str = "San Francisco, CA", posted: str = "Posted Today") -> dict:
    return {"title": f"Program Manager {i}", "locationsText": loc, "postedOn": posted,
            "externalPath": f"/job/SF/Program-Manager-{i}_R{i}"}


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWorkday:
    """total postings, served in pages; detail per externalPath."""

    def __init__(self, postings: list[dict], fail_detail: set[str] = frozenset(), fail_search=False):
        self.postings = postings
        self.fail_detail = fail_detail
        self.fail_search = fail_search
        self.search_offsets: list[int] = []
        self.detail_paths: list[str] = []

    def __call__(self, req, timeout=30):
        url = req.full_url
        if url == SEARCH_URL:
            if self.fail_search:
                raise OSError("HTTP Error 403: Forbidden")
            body = json.loads(req.data)
            self.search_offsets.append(body["offset"])
            assert req.get_method() == "POST" and body["searchText"]
            page = self.postings[body["offset"]: body["offset"] + body["limit"]]
            return _Resp({"total": len(self.postings), "jobPostings": page})
        path = url.split("/en-US/Careers", 1)[1]
        self.detail_paths.append(path)
        if path in self.fail_detail:
            raise OSError("HTTP Error 500")
        i = path.rsplit("_R", 1)[1]
        return _Resp({"jobPostingInfo": {
            "jobDescription": "<p>Sample Corp needs a program manager.</p>" + "<p>Details.</p>" * 30
                              + "<p>Visa sponsorship is available.</p>",
            "externalUrl": f"https://samplecorp.wd5.myworkdayjobs.com/en-US/Careers/job/SF/pm_R{i}",
            "jobReqId": f"R{i}", "timeType": "Full time", "remoteType": "Hybrid",
        }})


@pytest.fixture()
def fake(monkeypatch):
    def install(*args, **kwargs):
        f = FakeWorkday(*args, **kwargs)
        monkeypatch.setattr(wd, "_urlopen", f)
        return f
    return install


@pytest.fixture()
def search_cfg():
    from jobwright import config

    def write(text: str):
        path = Path(config.SEARCH_CONFIG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    return write


def test_helpers():
    assert wd.strip_html("") == ""
    assert wd.strip_html("<p>One</p><script>x()</script><ul><li>Two</li></ul>") == "One\n\nTwo"
    assert wd.posted_on_date("Posted Today", date(2026, 11, 4)) == "2026-11-04"
    assert wd.posted_on_date("Posted Yesterday", date(2026, 11, 4)) == "2026-11-03"
    assert wd.posted_on_date("Posted 3 Days Ago", date(2026, 11, 4)) == "2026-11-01"
    assert wd.posted_on_date("Posted 30+ Days Ago", date(2026, 11, 4)) is None
    assert wd.posted_on_date(None) is None
    assert wd.employers_without_excludes(EMPLOYERS, ["sample"]) == {}
    assert wd.employers_without_excludes(EMPLOYERS, []) is EMPLOYERS


def test_setup_proxy_formats():
    wd.setup_proxy("proxy.example.com:8080:user:secret")
    assert wd._opener is not None
    wd.setup_proxy("proxy.example.com:8080")
    wd.setup_proxy("garbage")
    wd.setup_proxy(None)
    assert wd._opener is not None


def test_search_employer_paginates_and_filters(fake):
    postings = [_posting(i) for i in range(45)]
    postings[3] = _posting(3, loc="London, UK")
    f = fake(postings)
    jobs = wd.search_employer("samplecorp", EMP, "program manager",
                              accept_locs=["San Francisco"], reject_locs=["London"])
    assert f.search_offsets == [0, 20, 40]
    assert len(jobs) == 44
    assert jobs[0] == {"title": "Program Manager 0", "location": "San Francisco, CA",
                       "posted": "Posted Today", "external_path": "/job/SF/Program-Manager-0_R0",
                       "employer_key": "samplecorp", "employer_name": "Sample Corp"}


def test_search_employer_page_cap_and_max_results(fake):
    f = fake([_posting(i) for i in range(600)])
    jobs = wd.search_employer("samplecorp", EMP, "pm", location_filter=False)
    assert len(f.search_offsets) == 25 and len(jobs) == 500

    f = fake([_posting(i) for i in range(100)])
    jobs = wd.search_employer("samplecorp", EMP, "pm", location_filter=False, max_results=30)
    assert len(jobs) == 30 and f.search_offsets == [0, 20]


def test_search_employer_api_error_returns_what_it_has(fake):
    fake([_posting(1)], fail_search=True)
    assert wd.search_employer("samplecorp", EMP, "pm") == []


def test_fetch_details_success_and_error(fake):
    f = fake([], fail_detail={"/job/SF/Program-Manager-2_R2"})
    jobs = [{"external_path": "/job/SF/Program-Manager-1_R1"}, {"external_path": "/job/SF/Program-Manager-2_R2"}]
    out = wd.fetch_details(EMP, jobs)
    assert out[0]["apply_url"].endswith("/pm_R1") and out[0]["job_req_id"] == "R1"
    assert out[0]["full_description"].startswith("Sample Corp needs a program manager.")
    assert out[0]["remote_type"] == "Hybrid"
    assert out[1]["full_description"] == "" and "HTTP Error 500" in out[1]["detail_error"]
    assert f.detail_paths == ["/job/SF/Program-Manager-1_R1", "/job/SF/Program-Manager-2_R2"]


def test_store_results_rows_filters_and_dupes(search_cfg):
    from jobwright.database import get_connection, init_db

    search_cfg("exclude_companies: ['Blocked Co']\nexclude_titles: ['Internship']\n")
    conn = init_db()
    long_desc = "Sample Corp needs a program manager. " * 10 + "Visa sponsorship is available."
    jobs = [
        {"title": "Program Manager", "employer_key": "samplecorp", "employer_name": "Sample Corp",
         "external_path": "/job/SF/PM_R1", "full_description": long_desc, "posted": "Posted Today",
         "location": "San Francisco, CA"},
        {"title": "Analyst", "employer_key": "samplecorp", "employer_name": "Sample Corp",
         "apply_url": "https://samplecorp.example.com/apply/2", "full_description": "short",
         "detail_error": "HTTP Error 500"},
        {"title": "Program Manager", "employer_name": "Blocked Co", "apply_url": "https://blocked.example.com/1"},
        {"title": "Summer Internship", "employer_name": "Sample Corp", "apply_url": "https://samplecorp.example.com/3"},
        {"title": "No URL", "employer_key": "unknown"},
    ]
    assert wd.store_results(conn, jobs, EMPLOYERS) == (2, 0)
    assert wd.store_results(conn, jobs[:2], EMPLOYERS) == (0, 2)

    rows = {r["url"]: dict(r) for r in get_connection().execute("SELECT * FROM jobs")}
    first = rows["https://samplecorp.wd5.myworkdayjobs.com/en-US/Careers/job/SF/PM_R1"]
    assert first["strategy"] == "workday_api" and first["company"] == "Sample Corp"
    assert first["full_description"] == long_desc and first["detail_scraped_at"]
    assert first["sponsorship_status"] == "required"
    assert first["date_posted"] == date.today().isoformat()
    assert first["application_url"] == first["url"]
    second = rows["https://samplecorp.example.com/apply/2"]
    assert second["full_description"] is None and second["detail_scraped_at"] is None
    assert second["detail_error"] == "HTTP Error 500"


def test_scrape_employers_skips_known_detail_fetch(fake, search_cfg):
    from jobwright.database import get_connection, init_db

    search_cfg("{}\n")
    init_db()
    known_path = "/job/SF/Program-Manager-0_R0"
    f = fake([_posting(0), _posting(1)])
    known = {f"{EMP['base_url']}/{EMP['site_id']}{known_path}", known_path}
    result = wd.scrape_employers("program manager", EMPLOYERS, location_filter=False, known_urls=known)
    assert result == {"found": 2, "new": 1, "existing": 1, "skipped_known": 1, "errors": 0}
    assert f.detail_paths == ["/job/SF/Program-Manager-1_R1"]
    assert get_connection().execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1


def test_scrape_employers_parallel_and_unknown_keys(fake, search_cfg):
    search_cfg("{}\n")
    fake([_posting(0)])
    other = {**EMP, "name": "Sample Corp Two"}
    employers = {"samplecorp": EMP, "two": other}
    result = wd.scrape_employers("pm", employers, employer_keys=["samplecorp", "two", "missing"],
                                 location_filter=False, workers=2)
    # same fake tenant URL for both: second store sees the first one's row
    assert result["found"] == 2 and result["new"] + result["existing"] == 2


def test_run_workday_discovery_queries_and_filters(fake, search_cfg, monkeypatch):
    search_cfg(
        "queries:\n"
        "  - {query: 'program manager', tier: 1}\n"
        "  - {query: 'operations lead', tier: 2}\n"
        "location:\n  accept_patterns: ['San Francisco']\n  reject_patterns: ['Canada']\n"
        "exclude_companies: ['Excluded']\n"
    )
    f = fake([_posting(0)])
    employers = {"samplecorp": EMP, "td": {**EMP, "name": "Canada Bank"},
                 "ex": {**EMP, "name": "Excluded Inc"}}
    monkeypatch.setenv("DISCOVER_MODE", "fast")
    result = wd.run_workday_discovery(employers=employers)
    assert result["queries"] == 1 and result["new"] == 1 and result["errors"] == 0
    assert len(f.search_offsets) == 1  # only the one surviving employer, tier-1 query

    monkeypatch.setenv("DISCOVER_MODE", "full")
    monkeypatch.setenv("JOBWRIGHT_DISCOVER_MAX_QUERIES", "1")
    assert wd.run_workday_discovery(employers={"samplecorp": EMP})["queries"] == 1


def test_run_workday_discovery_nothing_configured(search_cfg):
    assert wd.run_workday_discovery(employers={})["queries"] == 0
    search_cfg("queries: []\n")
    assert wd.run_workday_discovery(employers=EMPLOYERS)["queries"] == 0


def test_load_employers_reads_shipped_yaml():
    employers = wd.load_employers()
    assert isinstance(employers, dict)
    for emp in list(employers.values())[:3]:
        assert {"name", "base_url", "site_id", "tenant"} <= set(emp)
