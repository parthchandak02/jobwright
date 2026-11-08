"""Resolve the employer's own application page for jobs that lack one.

Many strong matches have no usable ``application_url``: LinkedIn cards carry
only the LinkedIn job page, and aggregator boards point at their own redirect
host. For jobs scoring >= ``min_score`` this module tries, cheapest and most
certain first:

  a. LinkedIn "Apply on company website": the public guest job page embeds the
     offsite link (``<code id="applyUrl">`` holding
     ``/jobs/view/externalApply/<id>?url=<encoded>``, or the offsite apply
     anchor). Fetched through the shared paced guest client
     (discovery/linkedin.py) and the discovery site breaker, so a
     rate-limiting LinkedIn is left alone for the rest of the run.
     Easy-Apply jobs have no offsite link.
  b. Aggregator / tracking redirects: known redirect parameters are unwrapped
     (``url=``, ``dest=``, ``redirect=``, ...), then redirects are followed by
     hand (GET, no JS, at most ``MAX_REDIRECTS`` hops). A final aggregator page
     is scanned for a meta refresh or a single direct ATS link.
  c. The company's public ATS board: Greenhouse
     (boards-api.greenhouse.io/v1/boards/<slug>/jobs), Lever
     (api.lever.co/v0/postings/<slug>) and Ashby
     (api.ashbyhq.com/posting-api/job-board/<slug>), matched by normalized
     title (location breaks ties; an unbreakable tie is no match). Board
     slugs come from ATS links in the description, then from the company name
     (``exampleorg``, ``example-org``). The company -> board lookup (hits and
     misses) is cached per profile in ``logs/ats_board_cache.json``.

Results land in ``application_url``, ``application_url_source``
(``linkedin_offsite`` | ``redirect`` | ``ats_board``) and ``application_ats``
(apply.ats.detect.ats_family); every attempt stamps
``application_url_checked_at`` so a miss is retried only after
``RECHECK_DAYS``. A LinkedIn URL is never stored as the application URL.

Network use is bounded: ``JOBWRIGHT_APPLY_URL_LIMIT`` jobs per run (default
60), at most one request per host per ``HOST_INTERVAL`` seconds outside
LinkedIn, and the enrich stage budget.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Comment

from jobwright.apply.ats.detect import ats_family, detect_ats

log = logging.getLogger(__name__)

MAX_REDIRECTS = 5
RECHECK_DAYS = 7
HOST_INTERVAL = 1.0
DEFAULT_LIMIT = 60
BOARD_CACHE_FILE = "ats_board_cache.json"
BOARD_HIT_TTL_DAYS = 30
BOARD_MISS_TTL_DAYS = 7

# Aggregators, job boards and link shorteners whose links are not the
# employer's application page. sites.yaml ``aggregator_hosts`` adds more.
DEFAULT_AGGREGATOR_HOSTS = frozenset({
    "adzuna.com", "appcast.io", "builtin.com", "careerjet.com", "careerjet.ca", "dice.com",
    "getwork.com", "glassdoor.com", "himalayas.app", "indeed.com", "jobcase.com",
    "jobgether.com", "jobleads.com", "jobright.ai", "jobs2careers.com", "jooble.org",
    "lensa.com", "monster.com", "remoterocketship.com", "simplyhired.com", "talent.com",
    "ziprecruiter.com", "recruit.net", "learn4good.com", "careerbuilder.com",
    "trabajo.org", "whatjobs.com", "jobilize.com", "teal.com",
})
SHORTENER_HOSTS = frozenset({"lnkd.in", "bit.ly", "t.co", "tinyurl.com", "ow.ly", "grnh.se"})
LINKEDIN_HOSTS = ("linkedin.com",)

# Query parameters that carry the real destination of a redirect/tracking URL.
REDIRECT_PARAMS = (
    "url", "u", "dest", "destination", "redirect", "redirect_url", "redirectUrl", "redirect_uri",
    "target", "to", "link", "apply_url", "applyUrl", "rurl", "jobUrl", "job_url", "out", "goto", "r",
)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


# -- URL helpers --------------------------------------------------------------

def _host(url: str | None) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except ValueError:
        return ""


def _host_in(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def is_linkedin_url(url: str | None) -> bool:
    return _host_in(_host(url), LINKEDIN_HOSTS)


def load_aggregator_hosts() -> frozenset[str]:
    """Default aggregator hosts plus sites.yaml ``aggregator_hosts``."""
    try:
        from jobwright.config import load_sites_config

        extra = load_sites_config().get("aggregator_hosts") or []
    except Exception:  # noqa: BLE001 - config is optional here
        extra = []
    return DEFAULT_AGGREGATOR_HOSTS | {str(h).lower().strip() for h in extra if h}


def is_aggregator_url(url: str | None, hosts: frozenset[str] | None = None) -> bool:
    host = _host(url)
    if not host or detect_ats(url):
        return False
    return _host_in(host, hosts if hosts is not None else load_aggregator_hosts())


def is_employer_url(url: str | None, hosts: frozenset[str] | None = None) -> bool:
    """An http(s) URL that is neither LinkedIn, an aggregator nor a shortener."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    host = _host(url)
    if not host or is_linkedin_url(url) or _host_in(host, SHORTENER_HOSTS - {"grnh.se"}):
        return False
    return not is_aggregator_url(url, hosts)


def _strip_tracking(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k not in ("urlHash", "trk", "refId", "trackingId")]
    return urlunparse(parsed._replace(query=urlencode(kept)))


def unwrap_redirect_params(url: str, max_depth: int = 4) -> str:
    """Peel redirect/tracking wrappers: ``.../redirect?url=https%3A%2F%2F...`` -> inner URL."""
    current = url.strip()
    for _ in range(max_depth):
        try:
            params = parse_qsl(urlparse(current).query, keep_blank_values=True)
        except ValueError:
            break
        lookup = {k: v for k, v in params}
        inner = None
        for name in REDIRECT_PARAMS:
            value = lookup.get(name)
            if not value:
                continue
            for _decode in range(3):
                if value.lower().startswith(("http://", "https://")):
                    break
                value = unquote(value)
            if value.lower().startswith(("http://", "https://")):
                inner = value
                break
        if not inner or inner == current:
            break
        current = inner
    return _strip_tracking(current) if current != url.strip() else current


def linkedin_job_id(url: str | None) -> str | None:
    if not is_linkedin_url(url):
        return None
    m = re.search(r"/jobs/view/(?:[^/?#]*?-)?(\d{6,})", url or "") or re.search(r"currentJobId=(\d+)", url or "")
    return m.group(1) if m else None


def parse_linkedin_offsite(html: str) -> str | None:
    """Offsite apply URL from a LinkedIn guest job page, or None (Easy Apply / none)."""
    soup = BeautifulSoup(html or "", "html.parser")
    raw = None
    code = soup.find("code", id="applyUrl")
    if code is not None:
        comment = code.find(string=lambda s: isinstance(s, Comment))
        raw = (comment or code.get_text() or "").strip().strip('"')
    if not raw:
        for a in soup.select("a[data-tracking-control-name]"):
            if "offsite" in (a.get("data-tracking-control-name") or "") and a.get("href"):
                raw = a["href"]
                break
    if not raw:
        return None
    raw = raw.replace("&amp;", "&")
    if raw.startswith("/"):
        raw = urljoin("https://www.linkedin.com", raw)
    resolved = unwrap_redirect_params(raw)
    return resolved if not is_linkedin_url(resolved) else None


def _html_redirect_target(html: str, base_url: str) -> str | None:
    """Meta refresh, a plain ``location`` assignment, or one distinct direct ATS link."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
    if meta and meta.get("content"):
        m = re.search(r"url\s*=\s*['\"]?([^'\";]+)", meta["content"], re.I)
        if m:
            return urljoin(base_url, m.group(1).strip())
    m = re.search(r"(?:window\.)?location(?:\.href)?\s*=\s*['\"](https?://[^'\"]+)['\"]", html)
    if m:
        return m.group(1)
    ats_links = []
    for a in soup.find_all("a", href=True):
        href = unwrap_redirect_params(urljoin(base_url, a["href"]))
        if detect_ats(href) and href not in ats_links:
            ats_links.append(href)
    return ats_links[0] if len(ats_links) == 1 else None


# -- HTTP ----------------------------------------------------------------------

class HostPacer:
    """At most one request per host per ``interval`` seconds (thread-safe)."""

    def __init__(self, interval: float = HOST_INTERVAL, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.interval = interval
        self._sleep = sleep
        self._clock = clock
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        with self._lock:
            now = self._clock()
            at = max(now, self._next.get(host, 0.0))
            self._next[host] = at + self.interval
        if at > now:
            self._sleep(at - now)


class Http:
    """Small paced httpx wrapper (one client, no cookies kept between hosts)."""

    def __init__(self, client: httpx.Client | None = None, pacer: HostPacer | None = None):
        self.client = client or httpx.Client(
            headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=10.0,
        )
        self.pacer = pacer or HostPacer()
        self.requests = 0

    def get(self, url: str, *, follow: bool = False, **kw) -> httpx.Response | None:
        self.pacer.wait(_host(url))
        self.requests += 1
        try:
            return self.client.get(url, follow_redirects=follow, **kw)
        except (httpx.HTTPError, ValueError) as e:
            log.debug("GET %s failed: %s", url, e)
            return None

    def json(self, url: str, **kw) -> Any | None:
        resp = self.get(url, follow=True, **kw)
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None


def follow_redirects(url: str, http: Http, *, max_redirects: int = MAX_REDIRECTS,
                     aggregators: frozenset[str] | None = None) -> str:
    """Follow redirect hops by hand until the URL leaves aggregator/shortener hosts.

    Never fetches the employer page itself: as soon as a hop lands on an
    employer/ATS URL it is returned. Returns the last URL reached.
    """
    current = unwrap_redirect_params(url)
    for _ in range(max_redirects + 1):
        if is_employer_url(current, aggregators) and not _host_in(_host(current), SHORTENER_HOSTS):
            return current
        resp = http.get(current)
        if resp is None:
            return current
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
            current = unwrap_redirect_params(urljoin(current, resp.headers["location"]))
            continue
        if resp.status_code == 200 and "html" in resp.headers.get("content-type", "html"):
            target = _html_redirect_target(resp.text, current)
            if target and target != current:
                current = unwrap_redirect_params(target)
                continue
        return current
    return current


# -- ATS board search -----------------------------------------------------------

_ABBREV = {"sr": "senior", "jr": "junior", "mgr": "manager", "assoc": "associate", "dir": "director",
           "vp": "vice president", "ii": "2", "iii": "3", "iv": "4", "&": "and", "eng": "engineer",
           "engr": "engineer", "mktg": "marketing", "ops": "operations", "pm": "product manager"}
_NOISE = {"remote", "hybrid", "onsite", "on", "site", "us", "usa", "the", "a", "an", "-", "–"}
_LEGAL = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "plc", "gmbh", "limited",
          "incorporated", "pbc", "sa", "ag", "the"}


def normalize_title(title: str | None, *, loose: bool = False) -> str:
    t = (title or "").lower().replace("&", " and ")
    if loose:
        t = re.sub(r"[(\[].*?[)\]]", " ", t)
        t = re.split(r"\s[-–|,]\s", t)[0]
    words = re.findall(r"[a-z0-9+#]+", t)
    out: list[str] = []
    for w in words:
        out.extend(_ABBREV.get(w, w).split())
    if loose:
        out = [w for w in out if w not in _NOISE]
    return " ".join(out)


def title_score(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    if normalize_title(a) == normalize_title(b):
        return 1.0
    la, lb = normalize_title(a, loose=True), normalize_title(b, loose=True)
    if la and la == lb:
        return 0.95
    sa, sb = set(la.split()), set(lb.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _location_match(job_loc: str | None, posting_loc: str | None) -> bool:
    if not job_loc or not posting_loc:
        return False
    a = set(re.findall(r"[a-z]{3,}", job_loc.lower())) - {"united", "states", "usa"}
    b = set(re.findall(r"[a-z]{3,}", posting_loc.lower())) - {"united", "states", "usa"}
    return bool(a & b)


@dataclass
class Posting:
    family: str
    slug: str
    id: str
    title: str
    location: str | None
    url: str


def company_key(company: str | None) -> str:
    words = re.findall(r"[a-z0-9]+", (company or "").lower())
    return " ".join(w for w in words if w not in _LEGAL)


def slug_candidates(company: str | None) -> list[str]:
    """Board slugs to try from a company name: ``exampleorg``, ``example-org``, full forms."""
    raw = re.findall(r"[a-z0-9]+", (company or "").lower())
    core = [w for w in raw if w not in _LEGAL]
    out: list[str] = []
    for words in (core, raw):
        if not words:
            continue
        for slug in ("".join(words), "-".join(words)):
            if len(slug) >= 2 and slug not in out:
                out.append(slug)
    return out


_HINT_RES = (
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.[a-z]{2})?\.greenhouse\.io/(?:embed/job_board\?for=)?"
                              r"([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs(?:\.eu)?\.lever\.co/([A-Za-z0-9_.-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.I)),
)


def slug_hints(*texts: str | None) -> list[tuple[str, str]]:
    """(family, slug) pairs from ATS links found in a description or URL."""
    out: list[tuple[str, str]] = []
    for text in texts:
        for family, rx in _HINT_RES:
            for m in rx.finditer(text or ""):
                slug = unquote(m.group(1)).strip(".")
                if slug.lower() in ("embed", "jobs", "v1", "api") or (family, slug) in out:
                    continue
                out.append((family, slug))
    return out


def _gh_postings(http: Http, slug: str) -> list[Posting] | None:
    data = http.json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return None
    return [
        Posting("greenhouse", slug, str(j.get("id")), j.get("title") or "",
                (j.get("location") or {}).get("name"),
                f"https://job-boards.greenhouse.io/{slug}/jobs/{j.get('id')}")
        for j in data["jobs"] if j.get("id")
    ]


def _lever_postings(http: Http, slug: str) -> list[Posting] | None:
    data = http.json(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    if not isinstance(data, list):
        return None
    return [
        Posting("lever", slug, str(j.get("id")), j.get("text") or "",
                (j.get("categories") or {}).get("location"),
                j.get("applyUrl") or f"https://jobs.lever.co/{slug}/{j.get('id')}/apply")
        for j in data if isinstance(j, dict) and j.get("id")
    ]


def _ashby_postings(http: Http, slug: str) -> list[Posting] | None:
    data = http.json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return None
    out = []
    for j in data["jobs"]:
        if not j.get("id") or j.get("isListed") is False:
            continue
        url = j.get("applyUrl") or (j.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{j['id']}").rstrip("/")
        if not url.endswith("/application"):
            url = url + "/application"
        out.append(Posting("ashby", slug, str(j["id"]), j.get("title") or "", j.get("location"), url))
    return out


BOARD_FETCHERS: dict[str, Callable[[Http, str], list[Posting] | None]] = {
    "greenhouse": _gh_postings,
    "lever": _lever_postings,
    "ashby": _ashby_postings,
}


def match_posting(postings: list[Posting], title: str | None, location: str | None,
                  min_score: float = 0.85) -> Posting | None:
    scored = [(title_score(title, p.title), _location_match(location, p.location), p) for p in postings]
    scored = [s for s in scored if s[0] >= min_score]
    if not scored:
        return None
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    best = scored[0]
    rivals = [s for s in scored[1:] if (s[0], s[1]) == (best[0], best[1]) and s[2].url != best[2].url]
    if rivals:
        log.info("Ambiguous ATS match for %r (%d postings tie); skipping", title, len(rivals) + 1)
        return None
    return best[2]


class BoardIndex:
    """Find a company's public ATS board and match postings on it.

    ``cache_path`` persists company -> (family, slug) hits for
    ``BOARD_HIT_TTL_DAYS`` and misses for ``BOARD_MISS_TTL_DAYS``; board job
    lists are fetched once per run.
    """

    def __init__(self, http: Http, cache_path: Path | None = None, *,
                 fetchers: dict | None = None, clock: Callable[[], float] = time.time):
        self.http = http
        self.cache_path = Path(cache_path) if cache_path else None
        self.fetchers = fetchers or BOARD_FETCHERS
        self._clock = clock
        self._lock = threading.Lock()
        self._boards: dict[tuple[str, str], list[Posting] | None] = {}
        self._cache: dict[str, dict] = self._load()
        self.lookups = 0

    def _load(self) -> dict[str, dict]:
        if not self.cache_path or not self.cache_path.exists():
            return {}
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data.get("companies", {}) if isinstance(data, dict) else {}

    def save(self) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"companies": self._cache}, indent=1, sort_keys=True), encoding="utf-8")
            tmp.replace(self.cache_path)
        except OSError as e:
            log.warning("Could not save %s: %s", self.cache_path, e)

    def _postings(self, family: str, slug: str) -> list[Posting] | None:
        key = (family, slug.lower())
        if key not in self._boards:
            self.lookups += 1
            self._boards[key] = self.fetchers[family](self.http, slug)
        return self._boards[key]

    def _cached(self, ckey: str) -> dict | None:
        entry = self._cache.get(ckey)
        if not entry:
            return None
        ttl = BOARD_MISS_TTL_DAYS if entry.get("miss") else BOARD_HIT_TTL_DAYS
        if self._clock() - float(entry.get("at", 0)) > ttl * 86400:
            return None
        return entry

    def board_for(self, company: str | None, hints: list[tuple[str, str]] = ()) -> tuple[str, str] | None:
        """(family, slug) of the company's board, or None."""
        ckey = company_key(company)
        with self._lock:
            entry = self._cached(ckey) if ckey else None
        if entry and not entry.get("miss"):
            return entry["family"], entry["slug"]
        tries: list[tuple[str, str]] = list(hints)
        if not entry:  # a cached miss still lets fresh description hints through
            for slug in slug_candidates(company):
                tries.extend((family, slug) for family in self.fetchers)
        found = None
        for family, slug in tries:
            if family not in self.fetchers:
                continue
            if self._postings(family, slug) is not None:
                found = (family, slug)
                break
        if ckey:
            with self._lock:
                if found:
                    self._cache[ckey] = {"family": found[0], "slug": found[1], "at": self._clock()}
                elif not entry:
                    self._cache[ckey] = {"miss": True, "at": self._clock()}
        return found

    def find(self, company: str | None, title: str | None, location: str | None = None,
             hints: list[tuple[str, str]] = ()) -> Posting | None:
        board = self.board_for(company, hints)
        if not board:
            return None
        postings = self._postings(*board) or []
        return match_posting(postings, title, location)


# -- LinkedIn --------------------------------------------------------------------

class LinkedInOffsite:
    """Offsite apply links through the shared guest client + site breaker."""

    def __init__(self, client=None, breaker=None):
        self._client = client
        self.breaker = breaker
        self.fetched = 0

    @property
    def client(self):
        if self._client is None:
            from jobwright.discovery.linkedin import shared_client

            self._client = shared_client()
        return self._client

    def blocked(self) -> bool:
        return self.breaker is not None and self.breaker.is_open("linkedin")

    def offsite_url(self, job_id: str) -> str | None:
        """Offsite URL; None when Easy Apply / not found. Raises RateLimited if throttled."""
        from jobwright.discovery.linkedin import DETAIL_URL, RateLimited

        if self.blocked():
            self.breaker.skip("linkedin")
            raise RateLimited("linkedin breaker open")
        try:
            # The light jobs-guest jobPosting card carries the same <code id="applyUrl">.
            resp = self.client.get(DETAIL_URL.format(job_id), bucket="api")
        except RateLimited:
            if self.breaker is not None:
                self.breaker.record_blocked("linkedin", "rate_limited")
            raise
        self.fetched += 1
        if resp is None:
            return None
        if self.breaker is not None:
            self.breaker.record_ok("linkedin")
        if "/authwall" in str(resp.url) or "/signup" in str(resp.url):
            return None
        return parse_linkedin_offsite(resp.text)


# -- Resolution --------------------------------------------------------------------

@dataclass
class Resolution:
    url: str
    source: str
    ats: str | None


class Resolver:
    def __init__(self, http: Http, boards: BoardIndex, linkedin: LinkedInOffsite | None,
                 aggregators: frozenset[str] | None = None):
        self.http = http
        self.boards = boards
        self.linkedin = linkedin
        self.aggregators = aggregators if aggregators is not None else load_aggregator_hosts()

    def needs_resolution(self, job: dict) -> bool:
        return not is_employer_url(job.get("application_url"), self.aggregators)

    def _final(self, url: str) -> str | None:
        final = follow_redirects(url, self.http, aggregators=self.aggregators)
        return final if is_employer_url(final, self.aggregators) else None

    def resolve(self, job: dict) -> Resolution | None:
        """Employer application URL for ``job``; raises linkedin.RateLimited when LinkedIn throttles."""
        url, app = job.get("url"), job.get("application_url")
        # (a) LinkedIn offsite apply link
        li_id = linkedin_job_id(url) or linkedin_job_id(app)
        if li_id and self.linkedin is not None:
            offsite = self.linkedin.offsite_url(li_id)
            if offsite:
                final = self._final(offsite)
                if final:
                    return Resolution(final, "linkedin_offsite", ats_family(final))
        # (b) aggregator / tracking redirects
        for cand in dict.fromkeys(u for u in (app, url) if u):
            if is_linkedin_url(cand) or is_employer_url(cand, self.aggregators):
                continue
            final = self._final(cand)
            if final:
                return Resolution(final, "redirect", ats_family(final))
        # (c) the company's public ATS board
        hints = slug_hints(job.get("description"), app, url)
        posting = self.boards.find(job.get("company"), job.get("title"), job.get("location"), hints)
        if posting:
            return Resolution(posting.url, "ats_board", posting.family)
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_apply_url_resolution(
    conn: sqlite3.Connection | None = None,
    *,
    min_score: int = 7,
    limit: int | None = None,
    resolver: Resolver | None = None,
    breaker=None,
    exceeded: Callable[[], bool] | None = None,
) -> dict:
    """Resolve application URLs for strong matches that lack one. Returns stats."""
    from jobwright import config, stage_budget
    from jobwright.database import init_db

    own_conn = conn is None
    conn = conn or init_db()
    if limit is None:
        try:
            limit = int(os.environ.get("JOBWRIGHT_APPLY_URL_LIMIT", DEFAULT_LIMIT))
        except ValueError:
            limit = DEFAULT_LIMIT
    exceeded = exceeded or stage_budget.exceeded
    aggregators = resolver.aggregators if resolver is not None else load_aggregator_hosts()
    stats = {"candidates": 0, "resolved": 0, "missed": 0, "rate_limited": 0, "ats_backfilled": 0,
             "by_source": {}}
    if os.environ.get("JOBWRIGHT_APPLY_URLS", "on").strip().lower() in ("0", "off", "false", "no"):
        stats["status"] = "disabled"
        return stats
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECHECK_DAYS)).isoformat()
    own_breaker = False
    boards = None
    try:
        # Cheap pass: ATS family for application URLs that already exist.
        rows = conn.execute(
            "SELECT url, application_url FROM jobs WHERE application_ats IS NULL "
            "AND application_url IS NOT NULL AND application_url != ''"
        ).fetchall()
        for row in rows:
            if is_employer_url(row[1], aggregators):
                conn.execute("UPDATE jobs SET application_ats = ? WHERE url = ?", (ats_family(row[1]), row[0]))
                stats["ats_backfilled"] += 1
        conn.commit()

        rows = conn.execute(
            """
            SELECT url, site, company, title, location, application_url,
                   COALESCE(full_description, description) AS description
            FROM jobs
            WHERE fit_score >= ? AND applied_at IS NULL
              AND COALESCE(funnel_stage, 'backlog') NOT IN ('applied', 'closed')
              AND (application_url_checked_at IS NULL OR application_url_checked_at < ?)
            ORDER BY fit_score DESC, discovered_at DESC
            """,
            (min_score, cutoff),
        ).fetchall()
        todo = [dict(zip(("url", "site", "company", "title", "location", "application_url", "description"), r))
                for r in rows]
        todo = [j for j in todo if not is_employer_url(j["application_url"], aggregators)][: max(0, limit)]
        stats["candidates"] = len(todo)
        if todo and resolver is None:
            if breaker is None:
                from jobwright.discovery.jobspy import site_breaker

                breaker, own_breaker = site_breaker(), True
            http = Http()
            boards = BoardIndex(http, config.LOG_DIR / BOARD_CACHE_FILE)
            resolver = Resolver(http, boards, LinkedInOffsite(breaker=breaker), aggregators)
        from jobwright.discovery.linkedin import RateLimited

        for i, job in enumerate(todo):
            if exceeded():
                stats["budget_skipped"] = len(todo) - i
                log.warning("apply URLs: enrich time budget used up; %d job(s) left for the next run",
                            stats["budget_skipped"])
                break
            try:
                res = resolver.resolve(job)
            except RateLimited:
                stats["rate_limited"] += 1
                res = None
                # LinkedIn never answered: try again next run, unless a board match already worked.
                job_li = dict(job, url=None, application_url=None)
                try:
                    res = resolver.resolve(job_li) if job.get("company") else None
                except RateLimited:
                    res = None
                if res is None:
                    continue
            except Exception as e:  # noqa: BLE001 - one bad job must not stop the stage
                log.warning("apply URL resolution failed for %s: %s", job["url"], e)
                res = None
            now = _now_iso()
            if res:
                conn.execute(
                    "UPDATE jobs SET application_url = ?, application_url_source = ?, application_ats = ?, "
                    "application_url_checked_at = ? WHERE url = ?",
                    (res.url, res.source, res.ats, now, job["url"]),
                )
                stats["resolved"] += 1
                stats["by_source"][res.source] = stats["by_source"].get(res.source, 0) + 1
                log.info("apply URL (%s, %s): %s -> %s", res.source, res.ats, job["url"][:70], res.url[:90])
            else:
                conn.execute("UPDATE jobs SET application_url_checked_at = ? WHERE url = ?", (now, job["url"]))
                stats["missed"] += 1
            conn.commit()
    finally:
        if boards is not None:
            boards.save()
        if own_breaker and breaker is not None:
            breaker.save()
        if own_conn:
            conn.close()
    log.info("apply URLs: %d candidates, %d resolved %s, %d missed, %d rate-limited",
             stats["candidates"], stats["resolved"], stats["by_source"], stats["missed"], stats["rate_limited"])
    return stats
