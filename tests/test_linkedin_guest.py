"""LinkedIn guest-endpoint discovery client (no network: httpx.MockTransport)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from jobwright.discovery import linkedin


def _card(job_id: int, title: str = "Operations Associate", location: str = "Chicago, IL",
          salary: str | None = None) -> str:
    sal = f'<span class="job-search-card__salary-info">{salary}</span>' if salary else ""
    return f"""
    <div class="base-card base-search-card job-search-card">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/ops-at-example-{job_id}?position=1"></a>
      <div class="base-search-card__info">
        <h3 class="base-search-card__title">{title}</h3>
        <h4 class="base-search-card__subtitle"><a href="https://www.linkedin.com/company/example">Example Co</a></h4>
        <div class="base-search-card__metadata">
          {sal}
          <span class="job-search-card__location">{location}</span>
          <time class="job-search-card__listdate" datetime="2026-09-27">1 day ago</time>
        </div>
      </div>
    </div>"""


_DETAIL = """
<section><div class="show-more-less-html__markup relative" data-x="1">
<p>Help run <strong>operations</strong>.</p><ul><li>Remote friendly</li></ul>
</div></section>"""


class FakeLinkedIn:
    """Serves search pages from a list of card ids and records every request."""

    def __init__(self, ids: list[int], page_size: int = 10, throttle_first: int = 0):
        self.ids = ids
        self.page_size = page_size
        self.throttle_first = throttle_first
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.throttle_first:
            self.throttle_first -= 1
            return httpx.Response(429)
        if _is_detail(request.url.path):
            return httpx.Response(200, text=_DETAIL)
        start = int(request.url.params.get("start", 0))
        page = self.ids[start:start + self.page_size]
        return httpx.Response(200, text="".join(_card(i) for i in page))

    def starts(self) -> list[int]:
        return [int(r.url.params["start"]) for r in self.calls if "search" in r.url.path]

    def details(self) -> int:
        return sum(_is_detail(r.url.path) for r in self.calls)


def _is_detail(path: str) -> bool:
    return "/jobs/view/" in path or "/jobPosting/" in path


def _client(fake: FakeLinkedIn, sleeps: list[float] | None = None) -> linkedin.GuestClient:
    rec = sleeps if sleeps is not None else []
    return linkedin.GuestClient(
        interval=0, sleep=rec.append, transport=httpx.MockTransport(fake),
    )


def test_parse_cards_fields_and_salary():
    html = _card(123, salary="$120K/yr - $150K/yr") + _card(456, salary="$40.00/hr - $50.00/hr")
    cards = linkedin.parse_cards(html)
    assert [c["job_id"] for c in cards] == ["123", "456"]
    first = cards[0]
    assert first["job_url"] == "https://www.linkedin.com/jobs/view/123"
    assert first["title"] == "Operations Associate"
    assert first["company"] == "Example Co"
    assert first["location"] == "Chicago, IL"
    assert str(first["date_posted"]) == "2026-09-27"
    assert (first["min_amount"], first["max_amount"], first["interval"]) == (120000, 150000, "yearly")
    assert (cards[1]["min_amount"], cards[1]["interval"]) == (40.0, "hourly")


def test_parse_detail_markdown_without_attributes():
    text = linkedin.parse_detail(_DETAIL)
    assert "**operations**" in text
    assert "Remote friendly" in text
    assert "data-x" not in text
    assert linkedin.parse_detail("<html></html>") is None


@pytest.mark.parametrize(
    ("location", "remote", "remote_any", "expected"),
    [
        ("Remote", True, False, "United States"),
        ("Remote", True, True, "Worldwide"),
        ("Chicago, IL", False, False, "Chicago, IL"),
        ("Chicago, IL", True, False, "Chicago, IL"),
    ],
)
def test_search_location_remote_scope(location, remote, remote_any, expected):
    assert linkedin.search_location(location, remote, remote_any) == expected


def test_scrape_pages_by_ten_and_sends_remote_filter():
    fake = FakeLinkedIn(list(range(1, 36)))
    rows = linkedin.scrape("ops", "Remote", remote=True, hours_old=72,
                           results_wanted=100, client=_client(fake))
    assert len(rows) == 35
    assert fake.starts() == [0, 10, 20, 30]
    params = fake.calls[0].url.params
    assert params["location"] == "United States"
    assert params["f_WT"] == "2"
    assert params["f_TPR"] == "r259200"
    assert params["sortBy"] == "DD"


def test_scrape_fetches_details_only_for_kept_cards():
    fake = FakeLinkedIn(list(range(1, 21)))
    rows = linkedin.scrape("ops", "Chicago, IL", results_wanted=100, client=_client(fake),
                           keep=lambda c: int(c["job_id"]) % 2 == 0)
    assert fake.details() == 10
    described = {r["job_id"] for r in rows if r["description"]}
    assert described == {str(i) for i in range(2, 21, 2)}
    assert all(r["is_remote"] for r in rows if r["description"])


def test_scrape_stops_after_two_pages_of_already_seen_jobs():
    fake = FakeLinkedIn(list(range(1, 101)))
    rows = linkedin.scrape("ops", "Chicago, IL", results_wanted=100, client=_client(fake),
                           keep=lambda c: False, seen_before=lambda c: True)
    assert fake.starts() == [0, 10]
    assert len(rows) == 20
    assert fake.details() == 0


def test_filtered_pages_do_not_stop_the_search():
    fake = FakeLinkedIn(list(range(1, 51)))
    rows = linkedin.scrape("ops", "Chicago, IL", results_wanted=100, client=_client(fake),
                           keep=lambda c: False)
    assert fake.starts() == [0, 10, 20, 30, 40, 50]
    assert len(rows) == 50


def test_malformed_card_does_not_end_pagination():
    broken = '<div class="base-search-card"><a class="base-card__full-link" href="/jobs/view/x"></a></div>'

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("start", 0))
        if start == 0:
            return httpx.Response(200, text="".join(_card(i) for i in range(1, 10)) + broken)
        if start == 10:
            return httpx.Response(200, text="".join(_card(i) for i in range(11, 16)))
        return httpx.Response(200, text="")

    client = linkedin.GuestClient(interval=0, sleep=lambda s: None,
                                  transport=httpx.MockTransport(handler))
    rows = linkedin.scrape("ops", "Chicago, IL", client=client, keep=lambda c: False)
    assert len(rows) == 14


def test_client_never_keeps_cookies():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "cookie" not in request.headers
        return httpx.Response(200, text=_card(1),
                              headers={"Set-Cookie": "bcookie=abc; Domain=.linkedin.com; Path=/"})

    client = linkedin.GuestClient(interval=0, sleep=lambda s: None,
                                  transport=httpx.MockTransport(handler))
    client.get(linkedin.SEARCH_URL)
    client.get(linkedin.SEARCH_URL)
    assert len(client._http.cookies) == 0


def test_status_999_is_treated_as_throttling():
    codes = iter([999, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(codes), text=_card(1))

    client = linkedin.GuestClient(interval=0.5, sleep=lambda s: None,
                                  transport=httpx.MockTransport(handler))
    assert client.get(linkedin.SEARCH_URL) is not None
    assert client.rate_limited == 1


def test_to_dataframe_missing_values_are_nan():
    import math

    df = linkedin.to_dataframe([{
        "job_url": "https://www.linkedin.com/jobs/view/1", "title": "Ops", "company": None,
        "location": None, "date_posted": None, "is_remote": False, "description": None,
        "min_amount": None, "max_amount": None, "interval": None,
    }])
    row = df.iloc[0]
    for col in ("company", "location", "description", "currency", "job_url_direct"):
        assert isinstance(row[col], float) and math.isnan(row[col]), col
    assert str(row["company"]) == "nan"


def test_description_is_cached_per_client():
    fake = FakeLinkedIn([7])
    client = _client(fake)
    linkedin.scrape("a", "Chicago, IL", client=client)
    linkedin.scrape("b", "Chicago, IL", client=client)
    assert fake.details() == 1


def test_429_backs_off_widens_interval_then_recovers():
    fake = FakeLinkedIn(list(range(1, 21)), throttle_first=2)
    sleeps: list[float] = []
    client = linkedin.GuestClient(interval=0.5, sleep=sleeps.append,
                                  transport=httpx.MockTransport(fake))
    rows = linkedin.scrape("ops", "Chicago, IL", client=client, keep=lambda c: False)
    assert len(rows) == 20
    assert client.rate_limited == 2
    assert 2.0 in sleeps and 4.0 in sleeps  # per-request backoff
    api = client.paces["api"]
    assert api.min_interval == 0.5
    assert 0.5 <= api.interval < 0.5 * 1.5 * 1.5  # widened, then narrowed on success
    assert client.paces["page"].interval == 0.5  # the other bucket is untouched


def test_description_uses_job_page_then_falls_back_to_jobposting():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/jobs/view/5":
            return httpx.Response(200, text="<html>no description here</html>")
        return httpx.Response(200, text=_DETAIL)

    client = linkedin.GuestClient(interval=0, sleep=lambda s: None,
                                  transport=httpx.MockTransport(handler))
    assert "**operations**" in client.description("4")
    assert calls == ["/jobs/view/4"]
    assert "**operations**" in client.description("5")
    assert calls[1:] == ["/jobs/view/5", "/jobs-guest/jobs/api/jobPosting/5"]


def test_search_rate_limited_keeps_cards_so_far():
    fake = FakeLinkedIn(list(range(1, 31)))
    client = _client(fake)
    client.max_retries = 1
    real_get = client.get

    def flaky(url, params=None):
        if params and params.get("start") == 10:
            raise linkedin.RateLimited(url)
        return real_get(url, params)

    client.get = flaky
    rows = linkedin.scrape("ops", "Chicago, IL", client=client, keep=lambda c: False)
    assert len(rows) == 10


def test_description_rate_limited_returns_none():
    fake = FakeLinkedIn([1], throttle_first=99)
    client = _client(fake)
    client.max_retries = 1
    assert client.description("1") is None
    with pytest.raises(linkedin.RateLimited):
        client.get(linkedin.SEARCH_URL)


def test_reject_memory_roundtrip_ttl_and_fingerprint(tmp_path: Path):
    import json

    path = tmp_path / "logs" / "linkedin_rejects.json"
    mem = linkedin.RejectMemory(path, "fp1")
    mem.add("111")
    mem.save()
    assert "111" in linkedin.RejectMemory(path, "fp1")
    assert "111" not in linkedin.RejectMemory(path, "fp2")  # filters changed

    data = json.loads(path.read_text())
    data["ids"]["222"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(data))
    fresh = linkedin.RejectMemory(path, "fp1", ttl_days=7)
    assert "111" in fresh
    assert "222" not in fresh  # expired


def test_env_switch_restores_jobspy(monkeypatch):
    monkeypatch.delenv("JOBWRIGHT_LINKEDIN", raising=False)
    assert linkedin.use_guest_client()
    monkeypatch.setenv("JOBWRIGHT_LINKEDIN", "jobspy")
    assert not linkedin.use_guest_client()


def test_run_one_search_uses_guest_client_and_filters_before_detail(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.database import close_connection, get_connection, init_db
    from jobwright.discovery import jobspy

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "load_search_config", lambda: {
        "exclude_companies": [], "exclude_titles": ["intern"], "min_salary": 100000,
    })
    close_connection(db)
    init_db(db)

    ids = list(range(1, 7))
    locations = {1: "Chicago, IL", 2: "London, United Kingdom", 3: "Chicago, IL",
                 4: "Chicago, IL", 5: "Colombo, Western Province, Sri Lanka", 6: "Chicago, IL"}
    titles = {4: "Operations Intern"}
    salaries = {3: "$50,000/yr - $60,000/yr", 6: "$150K/yr - $180K/yr"}

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_detail(request.url.path):
            return httpx.Response(200, text=_DETAIL)
        start = int(request.url.params.get("start", 0))
        page = ids[start:start + 10]
        return httpx.Response(200, text="".join(
            _card(i, title=titles.get(i, "Operations Associate"), location=locations[i],
                  salary=salaries.get(i)) for i in page
        ))

    fake_calls: list[str] = []

    def recording(request):
        fake_calls.append(request.url.path)
        return handler(request)

    client = linkedin.GuestClient(interval=0, sleep=lambda s: None,
                                  transport=httpx.MockTransport(recording))
    monkeypatch.setattr(linkedin, "shared_client", lambda proxy=None: client)
    monkeypatch.setattr(jobspy, "scrape_jobs", lambda **kw: pytest.fail("JobSpy used for LinkedIn"))
    known = {"https://www.linkedin.com/jobs/view/1"}

    result = jobspy._run_one_search(
        {"query": "operations associate", "location": "Chicago, IL", "remote": False},
        ["linkedin"], 100, 72, None, {}, 0, ["Chicago", ", IL"], ["United Kingdom"], {},
        known,
    )

    detail_ids = sorted(p.rsplit("/", 1)[-1] for p in fake_calls if _is_detail(p))
    assert detail_ids == ["6"]  # 1 known, 2/5 location, 3 salary, 4 title
    assert result["skipped_known"] == 1
    assert result["filtered"] == 2
    assert result["errors"] == 0
    assert result["new"] == 1
    row = get_connection(db).execute(
        "SELECT url, site, salary, full_description FROM jobs"
    ).fetchone()
    assert row["url"] == "https://www.linkedin.com/jobs/view/6"
    assert row["site"] == "linkedin"
    assert row["salary"] == "USD150,000-USD180,000/yearly"
    assert row["full_description"] is None  # fixture JD is under the 200-char promote bar
    close_connection(db)


def test_description_rejects_are_remembered_and_skipped(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.database import close_connection, get_connection, init_db
    from jobwright.discovery import jobspy

    db = tmp_path / "jobs.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "load_search_config", lambda: {
        "exclude_companies": [], "exclude_titles": [], "min_salary": 120000,
    })
    close_connection(db)
    init_db(db)

    low_pay = "<div class='show-more-less-html__markup'><p>The range is $65,000 to $80,000.</p></div>"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if _is_detail(request.url.path):
            job_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, text=low_pay if job_id == "1" else _DETAIL)
        if int(request.url.params.get("start", 0)):
            return httpx.Response(200, text="")
        return httpx.Response(200, text=_card(1) + _card(2))

    def run(rejects):
        client = linkedin.GuestClient(interval=0, sleep=lambda s: None,
                                      transport=httpx.MockTransport(handler))
        monkeypatch.setattr(linkedin, "shared_client", lambda proxy=None: client)
        return jobspy._run_one_search(
            {"query": "ops", "location": "Chicago, IL", "remote": False},
            ["linkedin"], 100, 72, None, {}, 0, ["Chicago"], [], {}, set(), rejects,
        )

    path = tmp_path / "linkedin_rejects.json"
    rejects = linkedin.RejectMemory(path, "fp")
    assert run(rejects)["new"] == 1
    assert "1" in rejects and "2" not in rejects
    rejects.save()

    calls.clear()
    run(linkedin.RejectMemory(path, "fp"))
    assert not any(_is_detail(p) and p.endswith("/1") for p in calls)
    assert get_connection(db).execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    close_connection(db)
