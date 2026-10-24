"""Impact / social-sector job board discovery — deterministic, no LLM.

Why this module exists
----------------------
``discovery/smartextract.py`` (the ``sites.yaml`` path) only runs when
``DISCOVER_MODE=full`` because it costs one LLM planning call per target plus a
Playwright render. The daily brief runs ``DISCOVER_MODE=fast``, so nothing in
``sites.yaml`` reaches the daily digest.

This module adds the curated impact-sector boards as *deterministic* scrapers:
no LLM calls, one HTTP request per board (a few need a browser), so they are
cheap enough to run on every daily brief.

Board tiers
-----------
* ``http``     — server-rendered listing / RSS / Google Sheet CSV export.
* ``browser``  — JS-rendered or bot-blocked for plain HTTP; needs Playwright.

Every board returns job dicts shaped like smartextract's
(``url, title, company, location, salary, description``) and is stored through
``smartextract._store_jobs_filtered`` so the user's location + title/salary
filters apply identically.

Disable with ``IMPACT_BOARDS=0``; skip browser boards with
``IMPACT_BOARDS_BROWSER=0``.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

TIMEOUT = 30

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

_LOC_HINT = re.compile(
    r"(?P<loc>"
    r"Remote|Anywhere|"
    r"[A-Z][a-zA-Z.\- ]{2,24},\s?(?:CA|NY|WA|DC|MA|IL|TX|CO|GA|OR|VA|MD|PA|MN|NC|AZ|FL)\b|"
    r"(?:San Francisco|Oakland|Berkeley|New York|Washington|Seattle|Boston|Chicago|"
    r"Los Angeles|Portland|Denver|Atlanta|Austin|Remote[- ](?:US|USA|United States))"
    r"[a-zA-Z, ]{0,20}"
    r")"
)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _guess_location(text: str) -> str | None:
    """Best-effort location from card text; None when nothing matches.

    ``location.location_ok`` keeps jobs with an unknown location, so a miss here
    is not a rejection — it just defers the call to the scorer.
    """
    m = _LOC_HINT.search(_clean(text))
    return _clean(m.group("loc")) if m else None


# -- recency + volume caps ---------------------------------------------------
# Stale postings are worse than missing postings: they cost a scoring call and
# pollute the digest. Boards that expose a date get a hard age window; boards
# that do not are small/fresh listing pages and only get a per-board cap.

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d")


def _max_age_days() -> int:
    try:
        return int(os.environ.get("IMPACT_BOARDS_MAX_AGE_DAYS", "14"))
    except ValueError:
        return 14


def _max_per_board() -> int:
    try:
        return int(os.environ.get("IMPACT_BOARDS_MAX_PER_BOARD", "150"))
    except ValueError:
        return 150


def _recent(date_str: str | None, max_age_days: int) -> bool:
    """True when the posting is inside the window (or has no parseable date)."""
    from datetime import datetime, timedelta

    raw = _clean(date_str)
    if not raw:
        return True
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt >= datetime.now() - timedelta(days=max_age_days)
        except ValueError:
            continue
    return True  # unparseable date -- keep, let the scorer judge


def _client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=TIMEOUT,
                        headers={"User-Agent": UA})


def _anchors(html: str, base_url: str, pattern: str) -> list[tuple[str, str, str]]:
    """Return (absolute_url, anchor_text, card_text) for anchors matching pattern."""
    soup = BeautifulSoup(html, "html.parser")
    rx = re.compile(pattern, re.I)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"])
        if not rx.search(url):
            continue
        key = url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        text = _clean(a.get_text(" ", strip=True))
        card = a
        for _ in range(3):
            if card.parent is None:
                break
            card = card.parent
        out.append((key, text, _clean(card.get_text(" ", strip=True))[:600]))
    return out


def _rss_items(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

    def field(item, name: str) -> str:
        el = item.find(name)
        if el is None:
            el = item.find("{http://www.w3.org/2005/Atom}" + name)
        if el is None:
            return ""
        if name == "link" and el.get("href"):
            return el.get("href")
        return _clean(el.text)

    return [
        {"title": field(i, "title"), "link": field(i, "link"),
         "company": field(i, "company"), "location": field(i, "location"),
         "description": field(i, "description"), "date": field(i, "pubDate")}
        for i in items
    ]


def _sheet_rows(sheet_id: str) -> list[dict]:
    """Fetch a public Google Sheet as CSV via the gviz endpoint."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in reader]


# ---------------------------------------------------------------------------
# board fetchers — each returns list[job dict]
# ---------------------------------------------------------------------------

def fetch_impact_job() -> list[dict]:
    """The Impact Job — public RSS, ~100 most recent postings."""
    with _client() as c:
        r = c.get("https://www.theimpactjob.com/rss/jobs?order=relevance")
        r.raise_for_status()
    max_age = _max_age_days()
    jobs = []
    for it in _rss_items(r.content):
        if not it["link"]:
            continue
        if not _recent(it.get("date"), max_age):
            continue
        jobs.append({
            "url": it["link"],
            "title": it["title"],
            "company": it["company"] or None,
            "location": it["location"] or None,
            "description": it["description"] or None,
        })
    return jobs


def fetch_giin() -> list[dict]:
    """GIIN impact-investing jobs board (paginated, /job/<id>/<slug>/)."""
    jobs: list[dict] = []
    with _client() as c:
        for page in range(1, 3):
            url = "https://jobs.thegiin.org/" if page == 1 else f"https://jobs.thegiin.org/?page={page}"
            r = c.get(url)
            if r.status_code != 200:
                break
            found = _anchors(r.text, url, r"jobs\.thegiin\.org/job/\d+/")
            if not found:
                break
            for link, text, card in found:
                jobs.append({"url": link, "title": text or None, "company": None,
                             "location": _guess_location(card), "description": None})
    return jobs


def fetch_rippleworks() -> list[dict]:
    """Rippleworks portfolio + partner job board."""
    url = "https://careers.rippleworks.org/jobs"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    jobs = []
    for link, text, card in _anchors(r.text, url, r"rippleworks\.org/companies/[^/]+/jobs/\d+"):
        m = re.search(r"/companies/([^/]+)/jobs/", link)
        company = m.group(1).replace("-", " ").title() if m else None
        jobs.append({"url": link, "title": text or None, "company": company,
                     "location": _guess_location(card), "description": None})
    return jobs


def fetch_nextbillion() -> list[dict]:
    """NextBillion jobs board."""
    url = "https://nextbillion.net/jobs/"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    jobs = []
    for link, text, card in _anchors(r.text, url, r"nextbillion\.net/jobs/[a-z0-9][a-z0-9\-]*/$"):
        jobs.append({"url": link, "title": text or None, "company": None,
                     "location": _guess_location(card), "description": None})
    return jobs


def fetch_findevgateway() -> list[dict]:
    """FinDev Gateway (IFC/World Bank) jobs board."""
    url = "https://www.findevgateway.org/jobs"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    jobs = []
    for link, text, card in _anchors(r.text, url, r"findevgateway\.org/jobs-internships/[a-z0-9]"):
        jobs.append({"url": link, "title": text or None, "company": None,
                     "location": _guess_location(card), "description": None})
    return jobs


def fetch_wave() -> list[dict]:
    """WAVE (Women in Alternative Investments) member job board."""
    url = "https://members.women-wave.org/jobs/"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    jobs = []
    for link, text, card in _anchors(r.text, url, r"members\.women-wave\.org/jobs/Details/"):
        jobs.append({"url": link, "title": text or None, "company": None,
                     "location": _guess_location(text + " " + card), "description": None})
    return jobs


def fetch_onpurpose() -> list[dict]:
    """On Purpose careers board — cards link out to each employer's ATS."""
    url = "https://www.onpurposecareers.org/jobboard"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        if "apply now" not in _clean(a.get_text(" ", strip=True)).lower():
            continue
        href = urljoin(url, a["href"]).split("?")[0]
        if href in seen or "onpurposecareers.org" in href:
            continue
        seen.add(href)
        card = a
        for _ in range(4):
            if card.parent is None:
                break
            card = card.parent
        card_text = _clean(card.get_text(" ", strip=True)) if card else ""
        heading = card.find(["h1", "h2", "h3", "h4"]) if card else None
        title = _clean(heading.get_text(" ", strip=True)) if heading else None
        jobs.append({"url": href, "title": title, "company": None,
                     "location": _guess_location(card_text), "description": None})
    return jobs


def _sheet_jobs(sheet_id: str, max_age_days: int | None = None) -> list[dict]:
    """Map a job-tracker sheet (Location / Position / Company / Salary / Job Link).

    Rows carry a ``Date Job Posted`` column; those older than ``max_age_days``
    are dropped so a year-long tracker cannot flood scoring with stale roles.
    """
    jobs: list[dict] = []
    for row in _sheet_rows(sheet_id):
        link = ""
        for k, v in row.items():
            if "link" in k.lower() and v.startswith("http"):
                link = v
                break
        if not link:
            continue
        def pick(*names: str) -> str | None:
            for n in names:
                for k, v in row.items():
                    if k.lower() == n and v:
                        return v
            return None
        title = pick("position", "role", "job title", "title")
        if not title:
            continue
        posted = pick("date job posted", "date posted", "date")
        if max_age_days is not None and not _recent(posted, max_age_days):
            continue
        jobs.append({
            "url": link,
            "title": title,
            "company": pick("company / organization", "company", "organization", "employer"),
            "location": pick("location"),
            "salary": pick("salary"),
            "description": None,
        })
    return jobs


def fetch_sis_global() -> list[dict]:
    return _sheet_jobs("1yM5Cd9EOPKGfrPtCM9ak5UFBCbJMkApqrUh9m6m_SxI", _max_age_days())


def fetch_csr_jobs_sheet() -> list[dict]:
    return _sheet_jobs("15UJRVY12dQin55SdpFM0xt3xr7aWnRO9z3_Rgy4RIkE", _max_age_days())


# ---------------------------------------------------------------------------
# browser boards (Playwright) — JS-rendered or 403 to plain HTTP
# ---------------------------------------------------------------------------

def _browser_fetch(targets: list[tuple[str, str, str]]) -> dict[str, list[dict]]:
    """Render each (name, url, link_pattern) target once; return per-board jobs."""
    from playwright.sync_api import sync_playwright

    out: dict[str, list[dict]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        for name, url, pattern in targets:
            jobs: list[dict] = []
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                try:
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(2500)
                except Exception:
                    pass
                html = page.content()
                for link, text, card in _anchors(html, url, pattern):
                    jobs.append({
                        "url": link,
                        "title": _clean(text.split("\n")[0]) or None,
                        "company": None,
                        "location": _guess_location(text + " " + card),
                        "description": None,
                    })
            except Exception as e:  # noqa: BLE001 - one board must not sink the rest
                log.warning("Browser board %s failed: %s", name, e)
            out[name] = jobs
        browser.close()
    return out


BROWSER_BOARDS: list[tuple[str, str, str]] = [
    ("Skoll Foundation", "https://skoll.org/community/jobs/", r"skoll\.org/job/"),
    ("Net Impact", "https://careers.netimpact.org/", r"careers\.netimpact\.org/job/[a-z0-9]"),
]

# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

HTTP_BOARDS: list[tuple[str, Callable[[], list[dict]]]] = [
    ("The Impact Job", fetch_impact_job),
    ("GIIN", fetch_giin),
    ("Rippleworks", fetch_rippleworks),
    ("Next Billion", fetch_nextbillion),
    ("FinDev Gateway", fetch_findevgateway),
    ("WAVE", fetch_wave),
    ("On Purpose", fetch_onpurpose),
    ("SIS Global (sheet)", fetch_sis_global),
    ("CSR Jobs (sheet)", fetch_csr_jobs_sheet),
]


def run_impact_boards(workers: int = 4, include_browser: bool | None = None) -> dict:
    """Scrape every configured impact board and store new jobs.

    Returns a per-board report: ``{board: {"jobs": n, "new": n, "existing": n, "error": str|None}}``.
    """
    if os.environ.get("IMPACT_BOARDS", "1").strip().lower() in ("0", "false", "no"):
        log.info("Impact boards skipped (IMPACT_BOARDS=0)")
        return {"skipped": "IMPACT_BOARDS=0"}

    if include_browser is None:
        include_browser = os.environ.get(
            "IMPACT_BOARDS_BROWSER", "1").strip().lower() not in ("0", "false", "no")

    from jobwright.config import load_location_filters, load_search_config
    from jobwright.database import init_db
    from jobwright.discovery.smartextract import _store_jobs_filtered

    conn = init_db()
    search_cfg = load_search_config()
    accept, reject = load_location_filters(search_cfg)

    fetched: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fn): name for name, fn in HTTP_BOARDS}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                fetched[name] = fut.result()
            except Exception as e:  # noqa: BLE001 - per-board isolation
                errors[name] = f"{type(e).__name__}: {e}"
                log.warning("Impact board %s failed: %s", name, e)

    if include_browser:
        try:
            fetched.update(_browser_fetch(BROWSER_BOARDS))
        except Exception as e:  # noqa: BLE001
            for name, _, _ in BROWSER_BOARDS:
                errors[name] = f"browser: {type(e).__name__}: {e}"

    report: dict[str, Any] = {}
    total_new = 0
    cap = _max_per_board()
    for name in [n for n, _ in HTTP_BOARDS] + [n for n, _, _ in BROWSER_BOARDS]:
        if name in errors:
            report[name] = {"jobs": 0, "new": 0, "existing": 0, "error": errors[name]}
            continue
        jobs = fetched.get(name) or []
        scraped = len(jobs)
        if cap and len(jobs) > cap:
            jobs = jobs[:cap]
        new, existing = _store_jobs_filtered(conn, jobs, name, "impact_board", accept, reject)
        total_new += new
        report[name] = {"jobs": scraped, "kept": len(jobs), "new": new,
                        "existing": existing, "error": None}
        log.info("Impact board %s: %d scraped, +%d new, %d dupes", name, scraped, new, existing)

    report["_total_new"] = total_new
    return report
