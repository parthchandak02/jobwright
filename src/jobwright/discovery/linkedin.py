"""LinkedIn discovery through the public (logged-out) guest job endpoints.

Replaces JobSpy's LinkedIn scraper, which pages with a growing stride (skips
results), fetches the heavy /jobs/view page for every card before any
filtering, and crashes the whole search on locations in countries it does not
know. Here every request goes through one client with an adaptive pace per
LinkedIn rate-limit bucket, and cards are filtered before any description
fetch.
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Callable

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com"
SEARCH_URL = f"{BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = f"{BASE_URL}/jobs-guest/jobs/api/jobPosting/{{}}"
PAGE_URL = f"{BASE_URL}/jobs/view/{{}}"
PAGE_SIZE = 10
MAX_START = 1000  # the guest search stops returning cards past ~1000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_REMOTE_KEYWORDS = ("remote", "work from home", "wfh")


def use_guest_client() -> bool:
    """False when JOBWRIGHT_LINKEDIN=jobspy asks for the old JobSpy path."""
    return os.environ.get("JOBWRIGHT_LINKEDIN", "guest").strip().lower() != "jobspy"


class RateLimited(Exception):
    """LinkedIn kept answering 429 after every backoff."""


class _Pace:
    """Adaptive spacing for one LinkedIn rate-limit bucket, shared by threads.

    A 429 widens the interval 1.5x; each success narrows it back toward the
    floor. Only the throttled request waits and retries, so one 429 does not
    stall every worker.
    """

    MAX_INTERVAL = 4.0

    def __init__(self, interval: float, sleep: Callable[[float], None]):
        self.min_interval = max(0.0, interval)
        self.interval = self.min_interval
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._widened_at = float("-inf")

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self.interval * random.uniform(0.8, 1.2)
        if wait > 0:
            self._sleep(wait)

    def throttled(self) -> None:
        # Concurrent 429s from one throttling event widen the interval once.
        with self._lock:
            now = time.monotonic()
            if now - self._widened_at < self.interval:
                return
            self._widened_at = now
            self.interval = min(self.MAX_INTERVAL, max(self.interval, 0.2) * 1.5)

    def ok(self) -> None:
        with self._lock:
            self.interval = max(self.min_interval, self.interval * 0.9)


class GuestClient:
    """Thread-safe LinkedIn client: search on the jobs-guest API, descriptions
    from the public job pages, each with its own adaptive pace.

    Cookies are never kept. LinkedIn throttles a session that carries its
    cookies at about one request per second; without them the same IP
    sustained ~1.7 requests per second with almost no 429s.
    """

    def __init__(
        self,
        interval: float | None = None,
        backoff: float = 2.0,
        max_retries: int = 3,
        proxy: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ):
        if interval is None:
            interval = float(os.environ.get("JOBWRIGHT_LINKEDIN_INTERVAL", "0.5"))
        self.paces = {"api": _Pace(interval, sleep), "page": _Pace(interval, sleep)}
        self.backoff = backoff
        self.max_retries = max_retries
        self._sleep = sleep
        self._lock = threading.Lock()
        self._details: dict[str, str | None] = {}
        self.requests = 0
        self.rate_limited = 0
        self.descriptions_fetched = 0
        self._http = httpx.Client(
            headers=_HEADERS, timeout=15.0, follow_redirects=True,
            proxy=f"http://{proxy}" if proxy else None, transport=transport,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        )

    def get(self, url: str, params: dict | None = None, bucket: str = "api") -> httpx.Response | None:
        """GET with pacing. Returns None on a non-429 failure; raises RateLimited."""
        pace = self.paces[bucket]
        for attempt in range(self.max_retries + 1):
            pace.wait()
            with self._lock:
                self.requests += 1
            try:
                resp = self._http.get(url, params=params)
            except httpx.HTTPError as e:
                log.warning("LinkedIn request failed (%s): %s", url, e)
                return None
            if resp.status_code in (429, 999):  # 999: LinkedIn's anti-bot soft block
                with self._lock:
                    self.rate_limited += 1
                pace.throttled()
                if attempt == self.max_retries:
                    raise RateLimited(url)
                self._sleep(self.backoff * (2 ** attempt))
                continue
            if resp.status_code < 400:
                pace.ok()
            else:
                log.warning("LinkedIn HTTP %d for %s", resp.status_code, url)
                return None
            return resp
        return None

    def _fetch_description(self, job_id: str) -> str | None:
        """Job page first; jobs-guest jobPosting only when the page has no description."""
        resp = self.get(PAGE_URL.format(job_id), bucket="page")
        if resp is not None and "/signup" not in str(resp.url) and "/authwall" not in str(resp.url):
            text = parse_detail(resp.text)
            if text:
                return text
        resp = self.get(DETAIL_URL.format(job_id), bucket="api")
        return parse_detail(resp.text) if resp is not None else None

    def description(self, job_id: str) -> str | None:
        """Job description markdown, fetched once per job per client."""
        with self._lock:
            if job_id in self._details:
                return self._details[job_id]
        try:
            text = self._fetch_description(job_id)
        except RateLimited:
            log.warning("LinkedIn kept rate-limiting job %s; storing it without a description", job_id)
            return None
        with self._lock:
            self._details[job_id] = text
            self.descriptions_fetched += 1
        return text


class RejectMemory:
    """LinkedIn job ids whose description failed the discovery filters.

    Rejected jobs are never stored, so without this every daily run would
    fetch their descriptions again. Entries expire after ``ttl_days`` and the
    whole file is dropped when the filter settings (``fingerprint``) change.
    """

    def __init__(self, path, fingerprint: str, ttl_days: int = 7):
        self.path = path
        self.fingerprint = fingerprint
        self._lock = threading.Lock()
        self._ids: dict[str, str] = {}
        cutoff = time.time() - ttl_days * 86400
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if data.get("fingerprint") == fingerprint:
            self._ids = {
                job_id: at for job_id, at in (data.get("ids") or {}).items()
                if _epoch(at) >= cutoff
            }

    def __contains__(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, job_id: str) -> None:
        with self._lock:
            self._ids[job_id] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def save(self) -> None:
        with self._lock:
            payload = {"fingerprint": self.fingerprint, "ids": dict(self._ids)}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as e:
            log.warning("Could not save LinkedIn reject memory %s: %s", self.path, e)


def _epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return 0.0


_shared: GuestClient | None = None
_shared_lock = threading.Lock()


def shared_client(proxy: str | None = None) -> GuestClient:
    """One client per process so parallel discovery workers share the pacing."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = GuestClient(proxy=proxy)
        return _shared


# -- Parsing -----------------------------------------------------------------

def _money(text: str) -> float | None:
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    try:
        amount = float(digits) if digits else None
    except ValueError:
        return None
    if amount is not None and "k" in text.lower():
        amount *= 1000
    return amount


def _interval(text: str) -> str:
    lower = text.lower()
    if "/hr" in lower or "hour" in lower:
        return "hourly"
    if "/mo" in lower or "month" in lower:
        return "monthly"
    return "yearly"


def parse_cards(html: str) -> list[dict]:
    """Parse guest search result cards into plain dicts."""
    return _parse_page(html)[0]


def _parse_page(html: str) -> tuple[list[dict], int]:
    """(parsed cards, raw card count); malformed cards are skipped but counted."""
    soup = BeautifulSoup(html, "html.parser")
    raw = soup.find_all("div", class_="base-search-card")
    cards = []
    for card in raw:
        link = card.find("a", class_="base-card__full-link")
        if not link or not link.get("href"):
            continue
        job_id = link["href"].split("?")[0].rstrip("/").split("-")[-1]
        if not job_id.isdigit():
            continue
        title_tag = card.find("h3", class_="base-search-card__title") or card.find("span", class_="sr-only")
        company_tag = card.find("h4", class_="base-search-card__subtitle")
        loc_tag = card.find("span", class_="job-search-card__location")
        time_tag = card.find("time")
        salary_tag = card.find("span", class_="job-search-card__salary-info")

        min_amount = max_amount = interval = None
        if salary_tag:
            salary_text = salary_tag.get_text(" ", strip=True)
            parts = salary_text.split("-")
            min_amount = _money(parts[0])
            max_amount = _money(parts[1]) if len(parts) > 1 else None
            interval = _interval(salary_text) if min_amount else None

        date_posted = None
        if time_tag and time_tag.get("datetime"):
            try:
                date_posted = datetime.strptime(time_tag["datetime"], "%Y-%m-%d").date()
            except ValueError:
                pass

        cards.append({
            "job_id": job_id,
            "job_url": f"{BASE_URL}/jobs/view/{job_id}",
            "title": title_tag.get_text(strip=True) if title_tag else None,
            "company": company_tag.get_text(strip=True) if company_tag else None,
            "location": loc_tag.get_text(strip=True) if loc_tag else None,
            "date_posted": date_posted,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "interval": interval,
        })
    return cards, len(raw)


def parse_detail(html: str) -> str | None:
    """Return the job description as markdown, or None."""
    from jobspy.util import markdown_converter

    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in c)
    if div is None:
        return None
    for tag in [div, *div.find_all(True)]:
        tag.attrs = {}
    return markdown_converter(div.decode_contents())


# -- Search ------------------------------------------------------------------

def search_location(location: str, remote: bool, remote_any: bool) -> str:
    """Guest search location for a searches.yaml entry.

    location="Remote" makes LinkedIn return remote jobs worldwide; US-scoped
    remote searches ask for United States plus the remote filter instead.
    """
    if remote and location.strip().lower() in ("remote", "anywhere", ""):
        return "Worldwide" if remote_any else "United States"
    return location


def scrape(
    query: str,
    location: str,
    *,
    remote: bool = False,
    remote_any: bool = False,
    hours_old: int | None = 72,
    results_wanted: int = 100,
    keep: Callable[[dict], bool] = lambda card: True,
    seen_before: Callable[[dict], bool] = lambda card: False,
    client: GuestClient | None = None,
) -> list[dict]:
    """Search LinkedIn and return one row per unique card.

    Only cards for which ``keep(card)`` is true get a description fetch; the
    rest are returned without one so callers can still count them as known /
    filtered. Results are newest first, so the search stops once two pages in
    a row hold only jobs ``seen_before`` (known or remembered rejects).
    """
    client = client or shared_client()
    params = {
        "keywords": query,
        "location": search_location(location, remote, remote_any),
        "sortBy": "DD",
    }
    if remote:
        params["f_WT"] = "2"
    if hours_old:
        params["f_TPR"] = f"r{int(hours_old) * 3600}"

    rows: list[dict] = []
    seen: set[str] = set()
    stale_pages = 0
    start = 0
    while len(rows) < results_wanted and start < MAX_START:
        try:
            resp = client.get(SEARCH_URL, {**params, "start": start})
        except RateLimited:
            log.warning("LinkedIn kept rate-limiting %r at start=%d; keeping %d cards",
                        query, start, len(rows))
            break
        if resp is None:
            break
        cards, raw_count = _parse_page(resp.text)
        if not raw_count:
            break
        fresh = 0
        for card in cards:
            if card["job_id"] in seen:
                continue
            seen.add(card["job_id"])
            card["is_remote"] = remote or any(
                k in f"{card['title']} {card['location']}".lower() for k in _REMOTE_KEYWORDS
            )
            card["description"] = None
            if not seen_before(card):
                fresh += 1
            if keep(card):
                card["description"] = client.description(card["job_id"])
                if card["description"] and not card["is_remote"]:
                    card["is_remote"] = any(
                        k in card["description"].lower() for k in _REMOTE_KEYWORDS
                    )
            rows.append(card)
            if len(rows) >= results_wanted:
                break
        stale_pages = 0 if fresh else stale_pages + 1
        if stale_pages >= 2 or raw_count < PAGE_SIZE:
            break
        start += raw_count
    return rows


def to_dataframe(rows: list[dict]):
    """Rows in the JobSpy DataFrame shape store_jobspy_results expects."""
    import pandas as pd

    df = pd.DataFrame([
        {
            "site": "linkedin",
            "job_url": r["job_url"],
            "job_url_direct": None,
            "title": r["title"],
            "company": r["company"],
            "location": r["location"],
            "date_posted": r["date_posted"],
            "is_remote": r["is_remote"],
            "description": r["description"],
            "min_amount": r["min_amount"],
            "max_amount": r["max_amount"],
            "interval": r["interval"],
            "currency": "USD" if r["min_amount"] else None,
        }
        for r in rows
    ])
    # store_jobspy_results treats only NaN as missing; str(None) would be "None".
    return df.astype(object).where(df.notna(), float("nan"))
