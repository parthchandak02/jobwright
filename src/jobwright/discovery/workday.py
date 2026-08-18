"""Workday ATS direct API scraper: searches employer career portals.

Scrapes Workday-powered career sites (TD, RBC, NVIDIA, Salesforce, etc.)
via the undocumented CXS JSON API. Zero LLM, zero browser -- pure HTTP.

Employer registry is loaded from config/employers.yaml instead of being
hardcoded. Supports sequential search + detail fetching with proxy.
"""

import json
import logging
import os
import re
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser

import yaml

from jobwright import config
from jobwright.config import CONFIG_DIR
from jobwright.database import get_connection, init_db
from jobwright.discovery.known_urls import job_url_known, load_known_urls

log = logging.getLogger(__name__)

# Stop paginating an employer+query after this many consecutive known jobs
# (Workday results are typically recency-sorted; a run of known = caught up).
EARLY_STOP_CONSECUTIVE_KNOWN = 10


# -- Employer registry from YAML --------------------------------------------

def load_employers() -> dict:
    """Load Workday employer registry from config/employers.yaml."""
    path = CONFIG_DIR / "employers.yaml"
    if not path.exists():
        log.warning("employers.yaml not found at %s", path)
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("employers", {})


# -- Location filtering from search config -----------------------------------

def _load_location_filter(search_cfg: dict | None = None):
    """Load location accept/reject lists from search config."""
    if search_cfg is None:
        search_cfg = config.load_search_config()
    return config.load_location_filters(search_cfg)


def _location_ok(location: str | None, accept: list[str], reject: list[str]) -> bool:
    """Check if a job location passes the user's location filter."""
    if not location:
        return True

    loc = location.lower()

    for r in reject:
        if r.lower() in loc:
            return False

    if any(r in loc for r in ("remote", "anywhere", "work from home", "wfh", "distributed")):
        return True

    for a in accept:
        if a.lower() in loc:
            return True

    return False


# -- HTML stripper -----------------------------------------------------------

class _HTMLStripper(HTMLParser):
    """Strip HTML tags, keep text content."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        elif tag in ("p", "div", "li", "tr"):
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts)
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def strip_html(html: str) -> str:
    """Convert HTML to plain text."""
    if not html:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


# -- Proxy -------------------------------------------------------------------

_opener = None


def setup_proxy(proxy_str: str | None) -> None:
    """Configure a global urllib opener with proxy support."""
    global _opener
    if not proxy_str:
        _opener = urllib.request.build_opener()
        return

    parts = proxy_str.split(":")
    if len(parts) == 4:
        host, port, user, passwd = parts
        proxy_url = f"http://{user}:{passwd}@{host}:{port}"
    elif len(parts) == 2:
        proxy_url = f"http://{parts[0]}:{parts[1]}"
    else:
        log.warning("Proxy format not recognized: %s (expected host:port:user:pass or host:port)", proxy_str)
        _opener = urllib.request.build_opener()
        return

    proxy_handler = urllib.request.ProxyHandler({
        "http": proxy_url,
        "https": proxy_url,
    })
    _opener = urllib.request.build_opener(proxy_handler)
    log.info("Proxy configured: %s:%s", parts[0], parts[1])


def _urlopen(req, timeout=30):
    """Open a URL using the configured opener (with or without proxy)."""
    if _opener:
        return _opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


# -- Workday API -------------------------------------------------------------

def workday_search(employer: dict, search_text: str, limit: int = 20, offset: int = 0) -> dict:
    """Search jobs via Workday CXS API. Returns JSON with total + jobPostings."""
    url = f"{employer['base_url']}/wday/cxs/{employer['tenant']}/{employer['site_id']}/jobs"
    payload = json.dumps({
        "appliedFacets": {},
        "limit": limit,
        "offset": offset,
        "searchText": search_text,
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    with _urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def workday_detail(employer: dict, external_path: str) -> dict:
    """Fetch full job detail via Workday CXS API."""
    url = f"{employer['base_url']}/wday/cxs/{employer['tenant']}/{employer['site_id']}{external_path}"

    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    with _urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# -- Search + paginate -------------------------------------------------------

def search_employer(
    employer_key: str,
    employer: dict,
    search_text: str,
    location_filter: bool = True,
    max_results: int = 0,
    accept_locs: list[str] | None = None,
    reject_locs: list[str] | None = None,
    known_urls: set[str] | None = None,
    early_stop: int = EARLY_STOP_CONSECUTIVE_KNOWN,
) -> list[dict]:
    """Search an employer, paginate through all results, optionally filter by location.

    When known_urls is set, stop paginating after `early_stop` consecutive known
    postings (recency-sorted results mean we've caught up with prior crawls).
    """
    log.info("%s: searching \"%s\"...", employer["name"], search_text)

    all_jobs: list[dict] = []
    offset = 0
    page_size = 20
    max_pages = 25  # Cap at 500 results
    total = None
    consecutive_known = 0
    known_urls = known_urls or set()

    while True:
        try:
            data = workday_search(employer, search_text, limit=page_size, offset=offset)
        except Exception as e:
            log.error("%s: API error at offset %d: %s", employer["name"], offset, e)
            break

        if total is None:
            total = data.get("total", 0)
            log.info("%s: %d total results", employer["name"], total)

        postings = data.get("jobPostings", [])
        if not postings:
            break

        stop_early = False
        for j in postings:
            loc = j.get("locationsText", "")
            if location_filter and accept_locs is not None and reject_locs is not None:
                if not _location_ok(loc, accept_locs, reject_locs):
                    continue

            external_path = j.get("externalPath", "") or ""
            job = {
                "title": j.get("title", ""),
                "location": loc,
                "posted": j.get("postedOn", ""),
                "external_path": external_path,
                "employer_key": employer_key,
                "employer_name": employer["name"],
            }
            all_jobs.append(job)

            if known_urls and job_url_known(employer, external_path, known_urls):
                consecutive_known += 1
                if early_stop and consecutive_known >= early_stop:
                    log.info(
                        "%s: early-stop after %d consecutive known jobs (offset %d)",
                        employer["name"], consecutive_known, offset,
                    )
                    stop_early = True
                    break
            else:
                consecutive_known = 0

        if stop_early:
            break

        offset += page_size
        page_num = offset // page_size
        if offset >= total:
            break
        if page_num >= max_pages:
            log.info("%s: capped at %d pages (%d results scanned)", employer["name"], max_pages, offset)
            break
        if max_results and len(all_jobs) >= max_results:
            all_jobs = all_jobs[:max_results]
            break

    log.info("%s: %d jobs found%s", employer["name"], len(all_jobs),
             " (filtered)" if location_filter else "")
    return all_jobs


# -- Fetch details -----------------------------------------------------------

def _fetch_one_detail(employer: dict, job: dict) -> dict:
    """Fetch detail for a single job."""
    try:
        detail = workday_detail(employer, job["external_path"])
        info = detail.get("jobPostingInfo", {})

        raw_desc = info.get("jobDescription", "")
        job["full_description"] = strip_html(raw_desc)
        job["apply_url"] = info.get("externalUrl", "")
        job["job_req_id"] = info.get("jobReqId", "")
        job["time_type"] = info.get("timeType", "")
        job["remote_type"] = info.get("remoteType", "")

    except Exception as e:
        job["full_description"] = ""
        job["apply_url"] = ""
        job["detail_error"] = str(e)

    return job


def fetch_details(employer: dict, jobs: list[dict]) -> list[dict]:
    """Fetch full description + apply URL for each job sequentially."""
    log.info("%s: fetching details for %d jobs...", employer["name"], len(jobs))

    completed = 0
    errors = 0
    t0 = time.time()

    for job in jobs:
        _fetch_one_detail(employer, job)
        completed += 1
        if "detail_error" in job:
            errors += 1

        if completed % 20 == 0 or completed == len(jobs):
            elapsed = time.time() - t0
            rate = completed / elapsed if elapsed > 0 else 0
            log.info("%s: %d/%d (%d errors) [%.1f jobs/sec]",
                     employer["name"], completed, len(jobs), errors, rate)

    elapsed = time.time() - t0
    log.info("%s: done in %.1fs (%.1f jobs/sec)", employer["name"], elapsed, len(jobs) / elapsed if elapsed > 0 else 0)
    return jobs


# -- DB storage --------------------------------------------------------------

def store_results(conn: sqlite3.Connection, jobs: list[dict], employers: dict) -> tuple[int, int]:
    """Store corporate jobs in DB. Returns (new, existing)."""
    from jobwright.config import load_search_config
    from jobwright.discovery.filters import passes_discovery_filters

    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0
    search_cfg = load_search_config()

    for job in jobs:
        url = job.get("apply_url", "")
        if not url:
            emp = employers.get(job.get("employer_key", ""), {})
            if emp and job.get("external_path"):
                url = f"{emp['base_url']}/{emp['site_id']}{job['external_path']}"
        if not url:
            continue

        description = job.get("full_description", "")
        short_desc = description[:500] if description else None
        full_description = description if len(description) > 200 else None
        detail_scraped_at = now if full_description else None
        detail_error = job.get("detail_error")

        site = job.get("employer_name", "Corporate")
        company = job.get("employer_name") or None
        strategy = "workday_api"

        if not passes_discovery_filters(
            title=job.get("title"),
            salary=job.get("salary"),
            description=description or short_desc,
            search_cfg=search_cfg,
        ):
            continue

        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, company, strategy, "
                "discovered_at, full_description, application_url, detail_scraped_at, detail_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (url, job.get("title"), None, short_desc, job.get("location"),
                 site, company, strategy, now, full_description, url, detail_scraped_at, detail_error),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    conn.commit()
    return new, existing


def _process_one(
    employer_key: str,
    employers: dict,
    search_text: str,
    location_filter: bool,
    accept_locs: list[str],
    reject_locs: list[str],
    known_urls: set[str] | None = None,
) -> dict:
    """Search one employer, fetch details for unknown jobs only, store results."""
    emp = employers[employer_key]
    known_urls = known_urls or set()

    try:
        jobs = search_employer(
            employer_key, emp, search_text,
            location_filter=location_filter,
            accept_locs=accept_locs,
            reject_locs=reject_locs,
            known_urls=known_urls,
        )
    except Exception as e:
        log.error("%s: ERROR searching '%s': %s", emp["name"], search_text, e)
        return {"employer": emp["name"], "query": search_text,
                "found": 0, "new": 0, "existing": 0, "skipped_known": 0, "error": str(e)}

    if not jobs:
        return {"employer": emp["name"], "query": search_text,
                "found": 0, "new": 0, "existing": 0, "skipped_known": 0}

    to_fetch: list[dict] = []
    skipped_known = 0
    for job in jobs:
        if job_url_known(emp, job.get("external_path", ""), known_urls):
            skipped_known += 1
        else:
            to_fetch.append(job)

    if skipped_known:
        log.info(
            "%s: skipped %d known (no detail fetch) for '%s'",
            emp["name"], skipped_known, search_text,
        )

    if to_fetch:
        try:
            to_fetch = fetch_details(emp, to_fetch)
        except Exception as e:
            log.error("%s: ERROR fetching details for '%s': %s", emp["name"], search_text, e)

    conn = get_connection()
    new, existing = store_results(conn, to_fetch, employers) if to_fetch else (0, 0)
    existing += skipped_known
    log.info(
        "%s: %d new, %d already in DB (%d skipped known)",
        emp["name"], new, existing, skipped_known,
    )

    return {"employer": emp["name"], "query": search_text,
            "found": len(jobs), "new": new, "existing": existing,
            "skipped_known": skipped_known}


# -- Main orchestrator -------------------------------------------------------

def scrape_employers(
    search_text: str,
    employers: dict,
    employer_keys: list[str] | None = None,
    location_filter: bool = True,
    max_results: int = 0,
    accept_locs: list[str] | None = None,
    reject_locs: list[str] | None = None,
    workers: int = 1,
    known_urls: set[str] | None = None,
) -> dict:
    """Run full scrape: search -> filter -> detail -> store.

    Sequential by default. When workers > 1, processes employers in parallel
    using ThreadPoolExecutor.
    """
    if employer_keys is None:
        employer_keys = list(employers.keys())

    if accept_locs is None:
        accept_locs = []
    if reject_locs is None:
        reject_locs = []
    if known_urls is None:
        known_urls = set()

    # Ensure DB schema
    init_db()

    total_new = 0
    total_existing = 0
    total_found = 0
    total_skipped = 0
    errors = 0
    t0 = time.time()

    valid_keys = [k for k in employer_keys if k in employers]

    if workers > 1 and len(valid_keys) > 1:
        # Parallel mode
        completed = 0
        with ThreadPoolExecutor(max_workers=min(workers, len(valid_keys))) as pool:
            futures = {
                pool.submit(
                    _process_one, key, employers, search_text,
                    location_filter, accept_locs, reject_locs, known_urls,
                ): key
                for key in valid_keys
            }
            for future in as_completed(futures):
                result = future.result()
                completed += 1
                total_new += result["new"]
                total_existing += result["existing"]
                total_found += result["found"]
                total_skipped += result.get("skipped_known", 0)
                if "error" in result:
                    errors += 1

                if completed % 10 == 0 or completed == len(valid_keys):
                    elapsed = time.time() - t0
                    log.info(
                        "[%s] Progress: %d/%d employers (%d new, %d dupes, %d skipped known, %d errors) [%.0fs]",
                        search_text, completed, len(valid_keys),
                        total_new, total_existing, total_skipped, errors, elapsed,
                    )
    else:
        # Sequential mode (default)
        completed = 0
        for key in valid_keys:
            result = _process_one(
                key, employers, search_text,
                location_filter, accept_locs, reject_locs, known_urls,
            )
            completed += 1
            total_new += result["new"]
            total_existing += result["existing"]
            total_found += result["found"]
            total_skipped += result.get("skipped_known", 0)
            if "error" in result:
                errors += 1

            if completed % 10 == 0 or completed == len(valid_keys):
                elapsed = time.time() - t0
                log.info(
                    "[%s] Progress: %d/%d employers (%d new, %d dupes, %d skipped known, %d errors) [%.0fs]",
                    search_text, completed, len(valid_keys),
                    total_new, total_existing, total_skipped, errors, elapsed,
                )

    elapsed = time.time() - t0
    log.info(
        "[%s] Done: %d found, %d new, %d dupes (%d skipped known) in %.0fs",
        search_text, total_found, total_new, total_existing, total_skipped, elapsed,
    )

    return {
        "found": total_found,
        "new": total_new,
        "existing": total_existing,
        "skipped_known": total_skipped,
    }


# -- Public entry point ------------------------------------------------------

def run_workday_discovery(employers: dict | None = None, workers: int = 1) -> dict:
    """Main entry point for Workday-based corporate job discovery.

    Loads employer registry from config/employers.yaml (or uses the provided
    dict), then loads search queries from the user's search config to run
    a full crawl across all employers.

    Args:
        employers: Override the employer registry. If None, loads from YAML.
        workers: Number of parallel threads for employer scraping. Default 1 (sequential).

    Returns:
        Dict with stats: found, new, existing, queries.
    """
    if employers is None:
        employers = load_employers()

    if not employers:
        log.warning("No employers configured. Create config/employers.yaml.")
        return {"found": 0, "new": 0, "existing": 0, "queries": 0}

    search_cfg = config.load_search_config()
    queries_cfg = search_cfg.get("queries", [])
    accept_locs, reject_locs = _load_location_filter(search_cfg)

    # DISCOVER_MODE=fast → tier 1 only; full → workday_max_tier (default 2)
    discover_mode = os.environ.get("DISCOVER_MODE", "fast").strip().lower()
    if discover_mode == "fast":
        max_tier = 1
    else:
        max_tier = search_cfg.get("workday_max_tier", 2)
    queries = [q["query"] for q in queries_cfg if q.get("tier", 99) <= max_tier]

    if not queries:
        # Fallback: use all queries
        queries = [q["query"] for q in queries_cfg]

    if not queries:
        log.warning("No search queries configured in searches.yaml.")
        return {"found": 0, "new": 0, "existing": 0, "queries": 0, "skipped_known": 0}

    max_queries = os.environ.get("JOBWRIGHT_DISCOVER_MAX_QUERIES")
    if max_queries:
        queries = queries[: int(max_queries)]
        log.info("Workday: limiting to %d queries (JOBWRIGHT_DISCOVER_MAX_QUERIES)", len(queries))

    proxy = search_cfg.get("proxy")
    if proxy:
        setup_proxy(proxy)

    location_filter = search_cfg.get("workday_location_filter", True)

    # Load known URLs once; skip detail fetches for jobs already in DB
    init_db()
    conn = get_connection()
    known_urls = load_known_urls(conn)
    log.info(
        "Workday crawl: %d queries x %d employers (workers=%d, mode=%s, known_urls=%d)",
        len(queries), len(employers), workers, discover_mode, len(known_urls),
    )

    grand_new = 0
    grand_existing = 0
    grand_found = 0
    grand_skipped = 0

    for i, query in enumerate(queries, 1):
        log.info("Query %d/%d: \"%s\"", i, len(queries), query)
        result = scrape_employers(
            search_text=query,
            employers=employers,
            location_filter=location_filter,
            accept_locs=accept_locs,
            reject_locs=reject_locs,
            workers=workers,
            known_urls=known_urls,
        )
        grand_new += result["new"]
        grand_existing += result["existing"]
        grand_found += result["found"]
        grand_skipped += result.get("skipped_known", 0)

    log.info(
        "Workday crawl done: %d found, %d new, %d existing (%d skipped known) "
        "across %d queries x %d employers",
        grand_found, grand_new, grand_existing, grand_skipped,
        len(queries), len(employers),
    )

    return {
        "found": grand_found,
        "new": grand_new,
        "existing": grand_existing,
        "skipped_known": grand_skipped,
        "queries": len(queries),
    }
