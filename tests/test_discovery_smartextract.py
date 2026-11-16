"""Tests for smartextract discovery (HTML cleaning, LLM judging, strategy executors, sites, run)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from jobwright import config
from jobwright.database import close_connection, init_db
from jobwright.discovery import smartextract
from jobwright.discovery.smartextract import extract as extract_mod
from jobwright.discovery.smartextract import fetch as fetch_mod
from jobwright.discovery.smartextract import judge as judge_mod
from jobwright.discovery.smartextract import run as run_mod
from jobwright.discovery.smartextract import sites as sites_mod


def _setup_user_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, min_salary: int = 100000) -> Path:
    db = tmp_path / "jobwright.db"
    searches = tmp_path / "searches.yaml"
    searches.write_text(
        "\n".join(
            [
                "queries:",
                "  - query: Product Manager",
                "  - query: Strategy Lead",
                "locations:",
                "  - location: San Francisco, CA",
                "    label: sf",
                "location:",
                "  accept_patterns:",
                "    - san francisco",
                "  reject_patterns:",
                "    - austin",
                "exclude_titles:",
                "  - intern",
                f"min_salary: {min_salary}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", searches)
    close_connection(db)
    init_db(db)
    return db


# -- Package exports ---------------------------------------------------------


def test_package_reexports_all_public_symbols():
    for name in smartextract.__all__:
        assert hasattr(smartextract, name), f"Missing re-export: {name}"


# -- fetch.py: HTML cleaning and Playwright intelligence ---------------------


def test_clean_card_html_preserves_semantic_attrs_and_strips_utility_noise():
    raw = (
        '<div id="card-1" class="job-card p-4 mt-2 col-6 d-flex text-sm bg-white '
        'rounded-lg w-100 css-abc123 sc-AbCdEf sc-12ab34-0 sr-only align-center '
        'justify-between flex-col salary-badge" style="color:red" onclick="x()" '
        'data-testid="job-card" data-custom="val" aria-label="Role">'
        '<a href="/jobs/42" class="p-2">Product Lead</a>'
        "</div>"
    )
    cleaned = fetch_mod.clean_card_html(raw)
    assert 'id="card-1"' in cleaned
    assert 'data-testid="job-card"' in cleaned
    assert 'data-custom="val"' in cleaned
    assert 'aria-label="Role"' in cleaned
    assert 'href="/jobs/42"' in cleaned
    assert "style=" not in cleaned
    assert "onclick=" not in cleaned
    assert "job-card" in cleaned
    assert "salary-badge" in cleaned
    for noise in ("p-4", "mt-2", "col-6", "d-flex", "css-abc123", "sc-AbCdEf", "sc-12ab34-0", "sr-only"):
        assert noise not in cleaned
    # When all classes on an inner element are utility classes, class attr is dropped.
    assert '<a href="/jobs/42">Product Lead</a>' in cleaned


def test_clean_page_html_prefers_large_main_strips_chrome_and_truncates():
    long_items = "".join(f'<article data-id="{i}"><h2>Role {i}</h2></article>' for i in range(40))
    html = (
        "<html><head><title>Jobs</title></head><body>"
        "<nav><a href='/'>Home</a></nav>"
        f"<main role='main'>{long_items}"
        "<div class='p-4 empty-wrapper'><span>   </span></div>"
        "<div><img src='/logo.png'/></div>"
        "<div><a href='/more'>More</a></div>"
        "<script>window.x=1;</script><style>.a{}</style><svg><path/></svg>"
        "<footer>Copyright</footer>"
        "</main>"
        "</body></html>"
    )
    cleaned = fetch_mod.clean_page_html(html, max_chars=20000)
    assert "Home" not in cleaned
    assert "Copyright" not in cleaned
    assert "window.x=1" not in cleaned
    assert "<svg" not in cleaned
    assert "empty-wrapper" not in cleaned
    assert "logo.png" not in cleaned
    assert 'href="/more"' in cleaned
    assert "Role 0" in cleaned

    # Force > max_chars truncation (min length 20k+ vs small max_chars)
    truncated = fetch_mod.clean_page_html(html, max_chars=120)
    assert truncated.endswith("\n<!-- TRUNCATED -->")
    assert len(truncated) == 120 + len("\n<!-- TRUNCATED -->")


def test_clean_page_html_falls_back_when_main_is_tiny():
    html = (
        "<html><body><main>tiny</main>"
        "<section><article><h3>Senior Strategy Manager</h3></article></section>"
        "</body></html>"
    )
    cleaned = fetch_mod.clean_page_html(html)
    assert "Senior Strategy Manager" in cleaned


def test_collect_page_intelligence_captures_signals_and_nested_api_data(monkeypatch):
    class _FakeElement:
        def __init__(self, text: str):
            self._text = text

        def inner_text(self) -> str:
            return self._text

    class _FakeResponse:
        def __init__(self, url: str, ct: str, status: int, body: str):
            self.url = url
            self.headers = {"content-type": ct}
            self.status = status
            self._body = body

        def text(self) -> str:
            return self._body

    class _FakeBrowser:
        def __init__(self, page):
            self._page = page
            self.closed = False

        def new_page(self, user_agent: str):
            assert user_agent == fetch_mod.UA
            return self._page

        def close(self):
            self.closed = True

    class _FakePage:
        def __init__(self):
            self._handlers = {}

        def on(self, event: str, fn):
            self._handlers[event] = fn

        def goto(self, url: str, timeout: int):
            cb = self._handlers["response"]
            cb(_FakeResponse("https://example.com/static/app.js", "application/javascript", 200, "x"))
            cb(_FakeResponse("https://example.com/static/logo.png", "image/png", 200, "x"))
            cb(_FakeResponse(
                "https://example.com/api/jobs",
                "application/json",
                200,
                json.dumps([{"title": "PM", "salary": "150k"}]),
            ))
            cb(_FakeResponse(
                "https://algolia.example.com/1/indexes",
                "text/plain",
                200,
                json.dumps({
                    "meta": {"total": 2},
                    "results": [
                        {
                            "title": "Lead",
                            "company": {"name": "Example Impact", "size": 50},
                            "tags": [{"label": "remote"}],
                        }
                    ],
                }),
            ))
            cb(_FakeResponse("https://example.com/graphql", "text/plain", 500, "not json"))

        def wait_for_load_state(self, state: str):
            assert state == "networkidle"

        def title(self) -> str:
            return "Example Careers"

        def query_selector_all(self, selector: str):
            assert "ld+json" in selector
            return [
                _FakeElement(json.dumps({"@type": "JobPosting", "title": "PM"})),
                _FakeElement("{bad json"),
            ]

        def query_selector(self, selector: str):
            if "__NEXT_DATA__" in selector:
                return _FakeElement(json.dumps({"buildId": "abc"}))
            return None

        def evaluate(self, script: str):
            if "data-testid" in script:
                return [{"testid": "job-row", "tag": "div", "text": "PM"}]
            if "total_elements" in script:
                return {"total_elements": 42, "links": 5, "headings": 2, "tables": 0, "articles": 1, "has_data_ids": 3}
            return [{"parent_selector": "ul.jobs", "child_selector": "li", "total_children": 4,
                     "with_text": 4, "with_links": 4, "score": 12, "examples": []}]

        def content(self) -> str:
            return "<html><body><main>Jobs</main></body></html>"

    fake_page = _FakePage()
    fake_browser = _FakeBrowser(fake_page)
    launched_flags = []

    class _FakeSyncPlaywright:
        def __enter__(self):
            class _Chromium:
                def launch(self, headless: bool = True):
                    launched_flags.append(headless)
                    return fake_browser

            return SimpleNamespace(chromium=_Chromium())

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(fetch_mod, "sync_playwright", _FakeSyncPlaywright)

    intel = fetch_mod.collect_page_intelligence("https://example.com/careers", headless=False)
    assert launched_flags == [False]
    assert fake_browser.closed is True
    assert intel["page_title"] == "Example Careers"
    assert intel["json_ld"] == [{"@type": "JobPosting", "title": "PM"}]
    assert intel["next_data"] == {"buildId": "abc"}
    assert len(intel["api_responses"]) == 3
    urls = [r["url"] for r in intel["api_responses"]]
    assert not any(u.endswith(".js") or u.endswith(".png") for u in urls)

    arr_resp = intel["api_responses"][0]
    assert arr_resp["type"] == "array[1]"
    assert arr_resp["first_item_keys"] == ["title", "salary"]

    nested_resp = intel["api_responses"][1]
    assert nested_resp["type"] == "object"
    assert "nested_results" in nested_resp
    assert nested_resp["nested_results"]["count"] == 1
    assert nested_resp["nested_results"]["first_item.company"]["type"] == "object"
    assert nested_resp["nested_results"]["first_item.tags"]["count"] == 1

    raw_none_resp = intel["api_responses"][2]
    assert raw_none_resp["_raw_data"] is None


# -- judge.py: JSON extraction, LLM calls, API judge, strategy briefing ------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"strategy": "json_ld"}', {"strategy": "json_ld"}),
        ('<think>step 1\nstep 2</think>\n{"relevant": true, "reason": "jobs"}', {"relevant": True, "reason": "jobs"}),
        ("```json\n{\"a\": 1}\n```", {"a": 1}),
        ("```\n{\"b\": 2}\n```", {"b": 2}),
        ('{"pattern": "foo\\_bar"}', {"pattern": "foo_bar"}),
        ('{"ok": true}}', {"ok": True}),
        ("[1, 2]]", [1, 2]),
    ],
)
def test_extract_json_handles_thinking_fences_escapes_and_extra_closers(raw, expected):
    assert judge_mod.extract_json(raw) == expected


def test_extract_json_raises_on_unrecoverable_text():
    with pytest.raises(json.JSONDecodeError):
        judge_mod.extract_json("not valid json at all")


def test_ask_llm_returns_text_elapsed_and_metadata(monkeypatch):
    calls = []

    class _FakeClient:
        def ask(self, prompt: str, temperature: float = 0.0, max_tokens: int = 4096) -> str:
            calls.append((prompt, temperature, max_tokens))
            return '{"ok": true}'

    monkeypatch.setattr(judge_mod, "get_client", lambda: _FakeClient())
    text, elapsed, meta = judge_mod.ask_llm("choose strategy")
    assert text == '{"ok": true}'
    assert elapsed >= 0.0
    assert meta["finish_reason"] == "stop"
    assert meta["prompt_chars"] == len("choose strategy")
    assert meta["response_chars"] == len('{"ok": true}')
    assert calls == [("choose strategy", 0.0, 4096)]


def test_judge_api_responses_filters_and_falls_back_on_errors(monkeypatch):
    def _no_client():
        raise AssertionError("get_client should not be called for empty input")

    monkeypatch.setattr(judge_mod, "get_client", _no_client)
    assert judge_mod.judge_api_responses([]) == []

    answers = iter([
        '{"relevant": true, "reason": "job listings"}',
        '{"relevant": false, "reason": "analytics"}',
        RuntimeError("rate limit"),
    ])

    class _FakeClient:
        def ask(self, prompt: str, temperature: float = 0.0, max_tokens: int = 1024) -> str:
            nxt = next(answers)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt

    monkeypatch.setattr(judge_mod, "get_client", lambda: _FakeClient())
    resps = [
        {"url": "https://example.com/api/jobs", "status": 200, "size": 500, "type": "array[2]",
         "first_item_keys": ["title"], "first_item_sample": {"title": "PM"}},
        {"url": "https://example.com/api/telemetry", "status": 200, "size": 50, "type": "object",
         "keys": ["ok"], "nested_events": {"count": 1, "first_item_keys": ["id"], "first_item_sample": {"id": 1}}},
        {"url": "https://example.com/api/fallback", "status": 200, "size": 100, "type": "unknown"},
    ]
    kept = judge_mod.judge_api_responses(resps)
    assert [r["url"] for r in kept] == [
        "https://example.com/api/jobs",
        "https://example.com/api/fallback",
    ]


def test_format_strategy_briefing_covers_all_sections():
    intel = {
        "url": "https://example.com/jobs",
        "page_title": "Careers",
        "json_ld": [
            {"@type": "JobPosting", "title": "Chief of Staff"},
            {"@type": "Organization", "name": "Example Org"},
        ],
        "api_responses": [
            {
                "url": "https://example.com/api/search",
                "status": 200,
                "size": 2048,
                "type": "object",
                "keys": ["results"],
                "first_item_keys": ["title"],
                "first_item_sample": {"title": "PM"},
                "nested_results": {
                    "count": 3,
                    "first_item_keys": ["title", "comp", "tags"],
                    "first_item_sample": {"title": "PM"},
                    "first_item.tags": {"count": 2, "first_item_keys": ["name"], "first_item_sample": {"name": "a"}},
                    "first_item.comp": {"keys": ["min"], "sample": {"min": 120000}},
                },
            }
        ],
        "data_testids": [{"testid": f"id-{i}", "tag": "div", "text": "line\ntext"} for i in range(18)],
        "dom_stats": {"total_elements": 100, "links": 20, "headings": 5, "tables": 1, "articles": 3, "has_data_ids": 4},
        "card_candidates": [
            {"parent_selector": "ul.list", "child_selector": "li.card", "total_children": 5,
             "with_text": 5, "with_links": 5}
        ],
    }
    briefing = judge_mod.format_strategy_briefing(intel)
    assert "JSON-LD: 1 JobPosting entries found (usable!)" in briefing
    assert "Other JSON-LD types (NOT job data): ['Organization']" in briefing
    assert "API RESPONSES INTERCEPTED: 1 calls" in briefing
    assert ".results: array of 3 items" in briefing
    assert ".results[0].tags: array of 2 items" in briefing
    assert ".results[0].comp: object with keys ['min']" in briefing
    assert "DATA-TESTID ATTRIBUTES: 18 elements" in briefing
    assert "id-14" in briefing and "id-15" not in briefing
    assert "REPEATING ELEMENTS DETECTED: 1 candidate groups" in briefing

    no_job_ld = {
        "url": "https://example.com/empty",
        "page_title": "Empty",
        "json_ld": [{"@type": "WebSite"}],
        "api_responses": [],
        "data_testids": [],
        "dom_stats": {},
        "card_candidates": [],
    }
    briefing_empty = judge_mod.format_strategy_briefing(no_job_ld)
    assert "JSON-LD: NO JobPosting entries" in briefing_empty
    assert "API RESPONSES: none intercepted" in briefing_empty
    assert "DATA-TESTID: none found" in briefing_empty
    assert "REPEATING ELEMENTS: none detected" in briefing_empty


# -- extract.py: JSON path helpers & strategy executors ----------------------


def test_resolve_json_path_and_raw_variants():
    data = {
        "results": [
            {
                "title": "Program Lead",
                "pay": 155000,
                "org": {"name": "Example Foundation"},
                "badge": {"text": "Hybrid"},
                "meta": {"a": 1, "b": 2},
                "locations": [{"name": "SF"}, {"name": "NYC"}, {"text": "DC"}, {"name": "LA"}],
                "tags": ["impact", "ops", "strategy", "extra"],
                "empty_str": "",
                "none_val": None,
            }
        ]
    }
    assert extract_mod.resolve_json_path_raw(data, "results[0].tags") == ["impact", "ops", "strategy", "extra"]
    assert extract_mod.resolve_json_path_raw(data, "") is None
    assert extract_mod.resolve_json_path_raw(None, "results") is None
    assert extract_mod.resolve_json_path_raw(data, "results[9].title") is None

    assert extract_mod.resolve_json_path(data, "results[0].title") == "Program Lead"
    assert extract_mod.resolve_json_path(data, "results[0].pay") == "155000"
    assert extract_mod.resolve_json_path(data, "results[0].org") == "Example Foundation"
    assert extract_mod.resolve_json_path(data, "results[0].badge") == "Hybrid"
    assert extract_mod.resolve_json_path(data, "results[0].meta") == "{'a': 1, 'b': 2}"
    assert extract_mod.resolve_json_path(data, "results[0].locations") == "SF, NYC, DC"
    assert extract_mod.resolve_json_path(data, "results[0].tags") == "impact, ops, strategy"
    assert extract_mod.resolve_json_path(data, "results[0].empty_str") == ""
    assert extract_mod.resolve_json_path(data, "results[0].none_val") is None
    assert extract_mod.resolve_json_path(data, "results[0].missing.x") is None


def test_execute_json_ld_extracts_only_job_postings():
    intel = {
        "json_ld": [
            "not-a-dict",
            {"@type": "Organization", "name": "Example Corp"},
            {
                "@type": "JobPosting",
                "title": "Impact Director",
                "baseSalary": {"value": {"minValue": 160000}},
                "description": "Lead grants",
                "jobLocation": [{"address": {"addressLocality": "San Francisco"}}],
                "url": "https://example.com/jobs/1",
            },
        ]
    }
    plan = {
        "extraction": {
            "title": "title",
            "salary": "baseSalary.value.minValue",
            "description": "description",
            "location": "jobLocation[0].address.addressLocality",
            "url": "url",
        }
    }
    jobs = extract_mod.execute_json_ld(intel, plan)
    assert jobs == [
        {
            "title": "Impact Director",
            "salary": "160000",
            "description": "Lead grants",
            "location": "San Francisco",
            "url": "https://example.com/jobs/1",
        }
    ]


def test_execute_api_response_extracts_and_handles_missing_paths():
    intel = {
        "api_responses": [
            {
                "url": "https://example.com/api/v2/postings",
                "_raw_data": {
                    "data": {
                        "items": [
                            "bad-item",
                            {
                                "jobTitle": "Chief of Staff",
                                "comp": "180k",
                                "loc": {"name": "Remote"},
                                "link": "https://example.com/jobs/cos",
                            },
                        ]
                    }
                },
            }
        ]
    }
    plan = {
        "extraction": {
            "url_pattern": "/api/v2/postings",
            "items_path": "data.items",
            "title": "jobTitle",
            "salary": "comp",
            "description": "null",
            "location": "loc.name",
            "url": "link",
        }
    }
    assert extract_mod.execute_api_response(intel, plan) == [
        {
            "title": "Chief of Staff",
            "salary": "180k",
            "description": None,
            "location": "Remote",
            "url": "https://example.com/jobs/cos",
        }
    ]
    assert extract_mod.execute_api_response(intel, {"extraction": {"url_pattern": "/missing"}}) == []
    assert extract_mod.execute_api_response(
        intel, {"extraction": {"url_pattern": "/api/v2/postings", "items_path": "data"}}
    ) == []


def test_execute_css_selectors_paths(monkeypatch):
    assert extract_mod.execute_css_selectors({"full_html": ""}) == ({}, [])

    html = (
        "<html><body><main>"
        + "x" * 1100
        + '<article data-testid="job-card"><h2><a href="https://example.com/j1">Partnerships Lead</a></h2>'
        '<span class="loc">San Francisco</span><span class="pay">$150k</span></article>'
        "</main></body></html>"
    )

    # 1. LLM error
    monkeypatch.setattr(extract_mod, "ask_llm", lambda _p: (_ for _ in ()).throw(RuntimeError("down")))
    assert extract_mod.execute_css_selectors({"full_html": html}) == ({}, [])

    # 2. Parse error
    monkeypatch.setattr(extract_mod, "ask_llm", lambda _p: ("not json", 0.1, {"response_chars": 8}))
    assert extract_mod.execute_css_selectors({"full_html": html}) == ({}, [])

    # 3. LLM reports no job listings
    monkeypatch.setattr(
        extract_mod, "ask_llm", lambda _p: ('{"error": "no job listings found"}', 0.1, {"response_chars": 30})
    )
    sel, jobs = extract_mod.execute_css_selectors({"full_html": html})
    assert sel == {"error": "no job listings found"}
    assert jobs == []

    # 4. Invalid card CSS selector
    monkeypatch.setattr(
        extract_mod, "ask_llm", lambda _p: ('{"job_card": "div[invalid=="}', 0.1, {"response_chars": 26})
    )
    sel, jobs = extract_mod.execute_css_selectors({"full_html": html})
    assert sel["job_card"] == "div[invalid=="
    assert jobs == []

    # 5. Valid extraction (with unmatched selector, invalid sub-selector, and null field)
    selectors_json = json.dumps({
        "job_card": '[data-testid="job-card"]',
        "title": "h2 a",
        "salary": "null",
        "description": ".missing-desc",
        "location": "div[bad==",
        "url": "h2 a",
    })
    monkeypatch.setattr(
        extract_mod, "ask_llm", lambda _p: (selectors_json, 0.2, {"response_chars": len(selectors_json)})
    )
    sel, jobs = extract_mod.execute_css_selectors({"full_html": html})
    assert jobs == [
        {
            "title": "Partnerships Lead",
            "salary": None,
            "description": None,
            "location": None,
            "url": "https://example.com/j1",
        }
    ]

    selectors_with_pay = json.dumps({
        "job_card": '[data-testid="job-card"]',
        "title": "h2 a",
        "salary": ".pay",
        "description": "null",
        "location": ".loc",
        "url": "h2 a",
    })
    monkeypatch.setattr(
        extract_mod, "ask_llm", lambda _p: (selectors_with_pay, 0.2, {"response_chars": len(selectors_with_pay)})
    )
    _, jobs_with_pay = extract_mod.execute_css_selectors({"full_html": html})
    assert jobs_with_pay == [
        {
            "title": "Partnerships Lead",
            "salary": "$150k",
            "description": None,
            "location": "San Francisco",
            "url": "https://example.com/j1",
        }
    ]


# -- extract.py: _run_one_site orchestration ---------------------------------


def _intel_stub(full_html: str, **overrides) -> dict:
    base = {
        "url": "https://example.com/jobs",
        "page_title": "Jobs",
        "json_ld": [],
        "api_responses": [],
        "data_testids": [],
        "dom_stats": {"total_elements": 10},
        "card_candidates": [],
        "full_html": full_html,
    }
    base.update(overrides)
    return base


def test_run_one_site_headful_retry_and_captcha_suppression(monkeypatch):
    calls: list[bool] = []
    big_html = "<main>" + ("<p>Job posting details</p>" * 400) + "</main>"

    # Tiny non-captcha page triggers headless=False retry
    def fake_collect(url: str, headless: bool = True):
        calls.append(headless)
        if headless:
            return _intel_stub("<main>loading</main>")
        return _intel_stub(
            big_html,
            json_ld=[{"@type": "JobPosting", "title": "PM", "url": "https://example.com/1"}],
        )

    monkeypatch.setattr(extract_mod, "collect_page_intelligence", fake_collect)
    monkeypatch.setattr(
        extract_mod,
        "ask_llm",
        lambda _p: (
            json.dumps({
                "strategy": "json_ld",
                "reasoning": "usable json-ld",
                "extraction": {"title": "title", "url": "url"},
            }),
            0.1,
            {"response_chars": 80},
        ),
    )

    res = extract_mod._run_one_site("ExampleSite", "https://example.com/jobs")
    assert calls == [True, False]
    assert res["status"] == "PASS"
    assert res["strategy"] == "json_ld"
    assert res["total"] == 1

    # CAPTCHA signal prevents headful retry
    calls.clear()
    monkeypatch.setattr(
        extract_mod,
        "collect_page_intelligence",
        lambda url, headless=True: (calls.append(headless), _intel_stub("<html>Please verify you are human</html>"))[1],
    )
    monkeypatch.setattr(
        extract_mod,
        "ask_llm",
        lambda _p: ('{"strategy": "unknown_strategy", "reasoning": "blocked"}', 0.1, {"response_chars": 50}),
    )
    res_cap = extract_mod._run_one_site("BlockedSite", "https://example.com/jobs")
    assert calls == [True]
    assert res_cap["status"] == "FAIL"


def test_run_one_site_api_judge_css_and_error_states(monkeypatch):
    big_html = "<main>" + ("<p>Role description text</p>" * 400) + "</main>"
    raw_api = [{"url": "https://example.com/api/jobs", "status": 200, "size": 100,
                "_raw_data": {"jobs": [{"t": "Lead", "u": "https://example.com/1"}, {"u": "https://example.com/2"}]}}]

    monkeypatch.setattr(
        extract_mod,
        "collect_page_intelligence",
        lambda url, headless=True: _intel_stub(big_html, api_responses=list(raw_api)),
    )
    judged_calls = []
    monkeypatch.setattr(
        extract_mod,
        "judge_api_responses",
        lambda resps: (judged_calls.append(len(resps)), resps)[1],
    )
    # 1 of 2 jobs has title -> 0.5 < 0.8 -> PARTIAL
    plan_json = json.dumps({
        "strategy": "api_response",
        "reasoning": "api",
        "extraction": {"url_pattern": "/api/jobs", "items_path": "jobs", "title": "t", "url": "u"},
    })
    monkeypatch.setattr(extract_mod, "ask_llm", lambda _p: (plan_json, 0.1, {"response_chars": len(plan_json)}))
    res = extract_mod._run_one_site("ApiSite", "https://example.com/jobs")
    assert judged_calls == [1]
    assert res["status"] == "PARTIAL"
    assert res["total"] == 2
    assert res["titles"] == 1

    # CSS selectors dispatch
    monkeypatch.setattr(
        extract_mod,
        "collect_page_intelligence",
        lambda url, headless=True: _intel_stub(big_html),
    )
    monkeypatch.setattr(
        extract_mod,
        "ask_llm",
        lambda _p: ('{"strategy": "css_selectors", "reasoning": "cards"}', 0.1, {"response_chars": 50}),
    )
    monkeypatch.setattr(
        extract_mod,
        "execute_css_selectors",
        lambda _intel: ({"job_card": "article"}, [{"title": "Director", "url": "https://example.com/d"}]),
    )
    res_css = extract_mod._run_one_site("CssSite", "https://example.com/jobs")
    assert res_css["status"] == "PASS"
    assert res_css["plan"]["extraction"] == {"job_card": "article"}

    # Phase 1 LLM_ERROR
    monkeypatch.setattr(extract_mod, "ask_llm", lambda _p: (_ for _ in ()).throw(RuntimeError("api down")))
    assert extract_mod._run_one_site("ErrSite", "https://example.com")["status"] == "LLM_ERROR"

    # Phase 1 PARSE_ERROR
    monkeypatch.setattr(extract_mod, "ask_llm", lambda _p: ("{{bad", 0.1, {"response_chars": 5}))
    assert extract_mod._run_one_site("ParseSite", "https://example.com")["status"] == "PARSE_ERROR"

    # Step 3 EXEC_ERROR (e.g. missing "extraction" key for json_ld)
    monkeypatch.setattr(
        extract_mod,
        "ask_llm",
        lambda _p: ('{"strategy": "json_ld", "reasoning": "missing extraction"}', 0.1, {"response_chars": 50}),
    )
    assert extract_mod._run_one_site("ExecSite", "https://example.com")["status"] == "EXEC_ERROR"


# -- sites.py: config, target expansion, filtered DB storage -----------------


def test_load_sites_missing_and_present(tmp_path, monkeypatch):
    monkeypatch.setattr(sites_mod, "CONFIG_DIR", tmp_path)
    assert sites_mod.load_sites() == []

    (tmp_path / "sites.yaml").write_text(
        "sites:\n  - name: ImpactBoard\n    url: https://example.com/jobs?q={query_encoded}\n    type: search\n",
        encoding="utf-8",
    )
    loaded = sites_mod.load_sites()
    assert len(loaded) == 1
    assert loaded[0]["name"] == "ImpactBoard"


def test_build_scrape_targets_expands_search_and_static_sites(tmp_path, monkeypatch):
    sites = [
        {
            "name": "BoardSearch",
            "url": "https://example.com/search?q={query_encoded}&alt={query}&loc={location_encoded}",
            "type": "search",
        },
        {
            "name": "StaticBoard",
            "url": "https://static.example.com/jobs?loc={location_encoded}",
            "type": "static",
        },
    ]
    search_cfg = {
        "queries": [{"query": "Chief of Staff"}, {"query": "Policy Lead"}],
        "locations": [{"location": "San Francisco, CA"}],
    }
    targets = sites_mod.build_scrape_targets(sites=sites, search_cfg=search_cfg)
    assert len(targets) == 3
    assert targets[0] == {
        "name": "BoardSearch",
        "url": "https://example.com/search?q=Chief+of+Staff&alt=Chief+of+Staff&loc=San+Francisco%2C+CA",
        "query": "Chief of Staff",
    }
    assert targets[1]["query"] == "Policy Lead"
    assert targets[2] == {
        "name": "StaticBoard",
        "url": "https://static.example.com/jobs?loc=San+Francisco%2C+CA",
        "query": None,
    }

    # Default arguments load from CONFIG_DIR / SEARCH_CONFIG_PATH
    _setup_user_env(tmp_path, monkeypatch)
    monkeypatch.setattr(sites_mod, "CONFIG_DIR", tmp_path)
    (tmp_path / "sites.yaml").write_text(
        "sites:\n  - name: ImpactBoard\n    url: https://example.com/jobs?q={query_encoded}\n    type: search\n",
        encoding="utf-8",
    )
    default_targets = sites_mod.build_scrape_targets()
    assert len(default_targets) == 2
    assert default_targets[0]["query"] == "Product Manager"
    accept, reject = sites_mod._load_location_filter()
    assert "san francisco" in accept and "austin" in reject


def test_store_jobs_filtered_applies_location_discovery_filters_and_dedupe(tmp_path, monkeypatch):
    db = _setup_user_env(tmp_path, monkeypatch, min_salary=110000)
    conn = sqlite3.connect(db)
    try:
        jobs = [
            {"title": "Missing URL", "location": "San Francisco, CA"},
            {"url": "https://example.com/reject-loc", "title": "PM", "location": "Austin, TX"},
            {"url": "https://example.com/reject-title", "title": "Product Intern", "location": "San Francisco, CA"},
            {
                "url": "https://example.com/reject-salary",
                "title": "Product Manager",
                "location": "San Francisco, CA",
                "salary": "$70,000 - $80,000",
            },
            {
                "url": "https://example.com/keep-1",
                "title": "Senior Product Manager",
                "location": "San Francisco, CA",
                "salary": "$140,000",
                "description": "Lead climate product.",
                "employer": "Example Impact",
            },
        ]
        new, existing = sites_mod._store_jobs_filtered(
            conn, jobs, "ExampleBoard", "json_ld", ["san francisco"], ["austin"]
        )
        assert (new, existing) == (1, 0)

        new2, existing2 = sites_mod._store_jobs_filtered(
            conn, [jobs[-1]], "ExampleBoard", "json_ld", ["san francisco"], ["austin"]
        )
        assert (new2, existing2) == (0, 1)

        row = conn.execute(
            "SELECT url, title, company, site, strategy FROM jobs WHERE url = ?",
            ("https://example.com/keep-1",),
        ).fetchone()
        assert row == ("https://example.com/keep-1", "Senior Product Manager", "Example Impact", "ExampleBoard", "json_ld")
    finally:
        conn.close()


# -- run.py: sequential and parallel target orchestration --------------------


def test_run_smart_extract_empty_targets(tmp_path, monkeypatch):
    _setup_user_env(tmp_path, monkeypatch)
    res = run_mod.run_smart_extract(sites=[])
    assert res == {"total_new": 0, "total_existing": 0, "passed": 0, "total": 0}


def test_run_smart_extract_sequential_and_parallel(tmp_path, monkeypatch):
    db = _setup_user_env(tmp_path, monkeypatch)
    monkeypatch.setattr(sites_mod, "CONFIG_DIR", tmp_path)

    sites = [
        {"name": "BoardOne", "url": "https://one.example.com/jobs?q={query_encoded}", "type": "search"},
        {"name": "BoardTwo", "url": "https://two.example.com/jobs", "type": "static"},
    ]

    def fake_run_one(name: str, url: str) -> dict:
        if name == "BoardOne":
            return {
                "name": name,
                "status": "PASS",
                "strategy": "json_ld",
                "total": 2,
                "titles": 2,
                "jobs": [
                    {
                        "url": "https://one.example.com/j1",
                        "title": "Strategy Lead",
                        "location": "San Francisco, CA",
                        "salary": "$150,000",
                        "company": "Example Org",
                    },
                    {
                        "url": "https://one.example.com/j2",
                        "title": "Filtered Out",
                        "location": "Austin, TX",
                    },
                ],
            }
        return {
            "name": name,
            "status": "LLM_ERROR",
            "error": "timeout",
            "jobs": [],
        }

    monkeypatch.setattr(run_mod, "_run_one_site", fake_run_one)

    try:
        # 2 queries on BoardOne + 1 static target on BoardTwo = 3 targets; BoardOne passes twice
        seq = run_mod.run_smart_extract(sites=sites, workers=1)
        assert seq == {"total_new": 1, "total_existing": 1, "passed": 2, "total": 3}

        par = run_mod.run_smart_extract(sites=sites, workers=2)
        assert par == {"total_new": 0, "total_existing": 2, "passed": 2, "total": 3}
    finally:
        close_connection(db)
