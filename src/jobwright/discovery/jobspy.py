"""JobSpy-based job discovery: searches Indeed, LinkedIn, Glassdoor, ZipRecruiter.

Uses python-jobspy to scrape multiple job boards, deduplicates results,
parses salary ranges, and stores everything in the jobwright database.

Search queries, locations, and filtering rules are loaded from the user's
search configuration YAML (searches.yaml) rather than being hardcoded.
"""

import logging
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from jobspy import scrape_jobs

from jobwright import config
from jobwright.config import load_location_filters
from jobwright.database import get_connection, init_db
from jobwright.discovery import linkedin
from jobwright.discovery.filters import passes_discovery_filters
from jobwright.discovery.known_urls import load_known_urls
from jobwright.discovery.location import location_ok as _location_ok
from jobwright.discovery.location import remote_scope

log = logging.getLogger(__name__)

# Cap JobSpy parallelism to avoid LinkedIn/Indeed soft-bans. Override via
# JOBWRIGHT_DISCOVER_WORKERS (still clamped to this default ceiling unless set).
_DEFAULT_DISCOVER_WORKER_CAP = 4


# -- Proxy parsing -----------------------------------------------------------

def parse_proxy(proxy_str: str) -> dict:
    """Parse host:port:user:pass into components."""
    parts = proxy_str.split(":")
    if len(parts) == 4:
        host, port, user, passwd = parts
        return {
            "host": host,
            "port": port,
            "user": user,
            "pass": passwd,
            "jobspy": f"{user}:{passwd}@{host}:{port}",
            "playwright": {
                "server": f"http://{host}:{port}",
                "username": user,
                "password": passwd,
            },
        }
    elif len(parts) == 2:
        host, port = parts
        return {
            "host": host,
            "port": port,
            "user": None,
            "pass": None,
            "jobspy": f"{host}:{port}",
            "playwright": {"server": f"http://{host}:{port}"},
        }
    else:
        raise ValueError(
            f"Proxy format not recognized: {proxy_str}. "
            f"Expected: host:port:user:pass or host:port"
        )


# -- Retry wrapper -----------------------------------------------------------

def _scrape_with_retry(kwargs: dict, max_retries: int = 2, backoff: float = 5.0):
    """Call scrape_jobs with retry on transient failures."""
    for attempt in range(max_retries + 1):
        try:
            return scrape_jobs(**kwargs)
        except Exception as e:
            err = str(e).lower()
            transient = any(k in err for k in ("timeout", "429", "proxy", "connection", "reset", "refused"))
            if transient and attempt < max_retries:
                wait = backoff * (attempt + 1)
                log.warning("Retry %d/%d in %.0fs: %s", attempt + 1, max_retries, wait, e)
                time.sleep(wait)
            else:
                raise


# -- Location filtering ------------------------------------------------------

def _load_location_config(search_cfg: dict) -> tuple[list[str], list[str]]:
    """Extract accept/reject location lists from search config."""
    return load_location_filters(search_cfg)


# -- DB storage (JobSpy DataFrame -> SQLite) ---------------------------------

def store_jobspy_results(
    conn: sqlite3.Connection,
    df,
    source_label: str,
    known_urls: set[str] | None = None,
) -> tuple[int, int, int]:
    """Store JobSpy DataFrame results into the DB.

    Returns (new, existing, skipped_known). ``skipped_known`` counts rows
    short-circuited via the known-URL set before filters / sponsorship work;
    IntegrityError on INSERT still counts toward ``existing`` as a backstop
    for URLs discovered twice within the same run.
    """
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0
    skipped_known = 0
    # Read-only view of the shared known set (safe across threads). Track
    # URLs we insert in this batch locally so within-DataFrame dupes skip
    # filter/sponsorship work without racing on the shared set.
    known = known_urls or set()
    seen_batch: set[str] = set()
    search_cfg = config.load_search_config()

    from jobwright.discovery.filters import passes_discovery_filters
    from jobwright.enrichment.sponsorship import derive_sponsorship_status

    for _, row in df.iterrows():
        url = str(row.get("job_url", ""))
        if not url or url == "nan":
            continue

        if url in known or url in seen_batch:
            existing += 1
            if url in known:
                skipped_known += 1
            continue

        title = str(row.get("title", "")) if str(row.get("title", "")) != "nan" else None
        company = str(row.get("company", "")) if str(row.get("company", "")) != "nan" else None
        location_str = str(row.get("location", "")) if str(row.get("location", "")) != "nan" else None

        excluded = False
        for exc in search_cfg.get("exclude_companies", []):
            if not exc:
                continue
            el = exc.lower()
            if company and el in company.lower():
                excluded = True
                break
            if title and el in title.lower():
                excluded = True
                break
        if excluded:
            continue

        # Build salary string from min/max
        salary = None
        min_amt = row.get("min_amount")
        max_amt = row.get("max_amount")
        interval = str(row.get("interval", "")) if str(row.get("interval", "")) != "nan" else ""
        currency = str(row.get("currency", "")) if str(row.get("currency", "")) != "nan" else ""
        if min_amt and str(min_amt) != "nan":
            if max_amt and str(max_amt) != "nan":
                salary = f"{currency}{int(float(min_amt)):,}-{currency}{int(float(max_amt)):,}"
            else:
                salary = f"{currency}{int(float(min_amt)):,}"
            if interval:
                salary += f"/{interval}"

        description = str(row.get("description", "")) if str(row.get("description", "")) != "nan" else None

        if not passes_discovery_filters(
            title=title,
            salary=salary,
            description=description,
            search_cfg=search_cfg,
        ):
            continue
        site_name = str(row.get("site", source_label))
        is_remote = row.get("is_remote", False)

        site_label = f"{site_name}"
        if is_remote:
            location_str = f"{location_str} (Remote)" if location_str else "Remote"

        strategy = "jobspy"

        # If JobSpy gave us a full description, promote it directly
        full_description = None
        detail_scraped_at = None
        sponsorship_status = None
        if description and len(description) > 200:
            full_description = description
            detail_scraped_at = now
            # Regex-only here: discovery is the hot loop (hundreds of jobs).
            # The LLM tie-breaker runs in the enrichment stage, not inline per
            # discovered job, so discovery never blocks on LLM rate limits.
            sponsorship_status = derive_sponsorship_status(full_description)

        # Extract apply URL if JobSpy provided it
        apply_url = str(row.get("job_url_direct", "")) if str(row.get("job_url_direct", "")) != "nan" else None
        posted = str(row.get("date_posted", ""))[:10]
        date_posted = posted if re.fullmatch(r"\d{4}-\d{2}-\d{2}", posted) else None

        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, company, strategy, discovered_at, "
                "full_description, application_url, detail_scraped_at, sponsorship_status, date_posted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (url, title, salary, description, location_str, site_label, company, strategy, now,
                 full_description, apply_url, detail_scraped_at, sponsorship_status, date_posted),
            )
            new += 1
            seen_batch.add(url)
        except sqlite3.IntegrityError:
            existing += 1
            seen_batch.add(url)

    conn.commit()
    return new, existing, skipped_known


# -- Single search execution -------------------------------------------------

_LINKEDIN_REJECT_VERSION = 2


def _card_salary(card: dict) -> str | None:
    """Card pay in the same string shape store_jobspy_results builds."""
    if not card.get("min_amount"):
        return None
    salary = f"USD{int(card['min_amount']):,}"
    if card.get("max_amount"):
        salary += f"-USD{int(card['max_amount']):,}"
    return salary + f"/{card.get('interval') or 'yearly'}"


def _linkedin_filter_fingerprint(search_cfg: dict) -> str:
    """Changes whenever a setting that decides discovery rejects changes."""
    import hashlib
    import json

    keys = ("exclude_titles", "exclude_companies", "min_salary", "defaults", "location")
    # Bump _LINKEDIN_REJECT_VERSION when the filter code itself changes.
    blob = json.dumps(
        {"v": _LINKEDIN_REJECT_VERSION, **{k: search_cfg.get(k) for k in keys}},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _linkedin_reject_memory(search_cfg: dict) -> "linkedin.RejectMemory":
    return linkedin.RejectMemory(
        config.LOG_DIR / "linkedin_rejects.json", _linkedin_filter_fingerprint(search_cfg),
    )


def _linkedin_keep(
    accept_locs: list[str],
    reject_locs: list[str],
    known_urls: set[str] | None,
    remote_any: bool,
    rejects: "linkedin.RejectMemory | None" = None,
):
    """Card predicate: only cards that would be stored get a description fetch."""
    search_cfg = config.load_search_config()
    excluded = [e.lower() for e in search_cfg.get("exclude_companies") or [] if e]
    known = known_urls or set()

    def keep(card: dict) -> bool:
        if card["job_url"] in known:
            return False
        if rejects is not None and card["job_id"] in rejects:
            return False
        company = (card.get("company") or "").lower()
        title = card.get("title") or ""
        if any(e in company or e in title.lower() for e in excluded):
            return False
        if not _location_ok(card.get("location"), accept_locs, reject_locs, remote_any=remote_any):
            return False
        return passes_discovery_filters(
            title=title, salary=_card_salary(card), description=None, search_cfg=search_cfg,
        )

    return keep


def _run_one_search(
    search: dict,
    sites: list[str],
    results_per_site: int,
    hours_old: int,
    proxy_config: dict | None,
    defaults: dict,
    max_retries: int,
    accept_locs: list[str],
    reject_locs: list[str],
    glassdoor_map: dict,
    known_urls: set[str] | None = None,
    li_rejects: "linkedin.RejectMemory | None" = None,
) -> dict:
    """Run a single search query and store results in DB."""
    s = search
    label = f"\"{s['query']}\" in {s['location']} {'(remote)' if s.get('remote') else ''}"
    if "tier" in s:
        label += f" [tier {s['tier']}]"

    # Split sites: Glassdoor needs simplified location, others use original
    gd_location = glassdoor_map.get(s["location"], s["location"].split(",")[0])
    has_glassdoor = "glassdoor" in sites
    has_linkedin_guest = "linkedin" in sites and linkedin.use_guest_client()
    other_sites = [
        si for si in sites
        if si != "glassdoor" and not (si == "linkedin" and has_linkedin_guest)
    ]

    all_dfs = []

    if has_linkedin_guest:
        try:
            rows = linkedin.scrape(
                s["query"], s["location"],
                remote=bool(s.get("remote")),
                remote_any=bool(s.get("remote_any")),
                hours_old=hours_old,
                results_wanted=results_per_site,
                keep=_linkedin_keep(
                    accept_locs, reject_locs, known_urls, bool(s.get("remote_any")), li_rejects,
                ),
                seen_before=lambda c: c["job_url"] in (known_urls or ())
                or (li_rejects is not None and c["job_id"] in li_rejects),
                client=linkedin.shared_client(proxy_config["jobspy"] if proxy_config else None),
            )
            if li_rejects is not None:
                # Remembered rejects come back without a description; storing
                # them would skip the description salary check.
                rows = [r for r in rows if r["description"] or r["job_id"] not in li_rejects]
                search_cfg = config.load_search_config()
                for row in rows:
                    if row["description"] and not passes_discovery_filters(
                        title=row["title"], salary=_card_salary(row),
                        description=row["description"], search_cfg=search_cfg,
                    ):
                        li_rejects.add(row["job_id"])
            all_dfs.append(linkedin.to_dataframe(rows))
        except Exception as e:
            log.error("[%s] (linkedin): %s", label, e)

    # Run the remaining JobSpy sites with the original location
    if other_sites:
        kwargs = {
            "site_name": other_sites,
            "search_term": s["query"],
            "location": s["location"],
            "results_wanted": results_per_site,
            "hours_old": hours_old,
            "description_format": "markdown",
            "country_indeed": defaults.get("country_indeed", "usa"),
            "verbose": 0,
        }
        if s.get("remote"):
            kwargs["is_remote"] = True
        if proxy_config:
            kwargs["proxies"] = [proxy_config["jobspy"]]
        if "linkedin" in other_sites:
            kwargs["linkedin_fetch_description"] = True
        if "google" in other_sites:
            # JobSpy's Google scraper ignores search_term/location; it needs an
            # explicit natural-language google_search_term or it returns nothing.
            kwargs["google_search_term"] = f"{s['query']} jobs near {s['location']} since yesterday"
        try:
            df = _scrape_with_retry(kwargs, max_retries=max_retries)
            all_dfs.append(df)
        except Exception as e:
            log.error("[%s] (non-gd): %s", label, e)

    # Run Glassdoor separately with simplified location
    if has_glassdoor:
        gd_kwargs = {
            "site_name": ["glassdoor"],
            "search_term": s["query"],
            "location": gd_location,
            "results_wanted": results_per_site,
            "hours_old": hours_old,
            "description_format": "markdown",
            "verbose": 0,
        }
        if s.get("remote"):
            gd_kwargs["is_remote"] = True
        if proxy_config:
            gd_kwargs["proxies"] = [proxy_config["jobspy"]]
        try:
            gd_df = _scrape_with_retry(gd_kwargs, max_retries=max_retries)
            all_dfs.append(gd_df)
        except Exception as e:
            log.error("[%s] (glassdoor): %s", label, e)

    if not all_dfs:
        log.error("[%s]: all sites failed", label)
        return {
            "new": 0, "existing": 0, "skipped_known": 0, "errors": 1,
            "filtered": 0, "total": 0, "label": label,
        }

    import pandas as pd
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        df = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]

    if len(df) == 0:
        log.info("[%s] 0 results", label)
        return {
            "new": 0, "existing": 0, "skipped_known": 0, "errors": 0,
            "filtered": 0, "total": 0, "label": label,
        }

    # Filter by location before storing
    before = len(df)
    df = df[df.apply(lambda row: _location_ok(
        str(row.get("location", "")) if str(row.get("location", "")) != "nan" else None,
        accept_locs, reject_locs, remote_any=bool(s.get("remote_any")),
    ), axis=1)]
    filtered = before - len(df)

    conn = get_connection()
    new, existing, skipped_known = store_jobspy_results(
        conn, df, s["query"], known_urls=known_urls,
    )

    msg = f"[{label}] {before} results -> {new} new, {existing} dupes"
    if skipped_known:
        msg += f" ({skipped_known} skipped known)"
    if filtered:
        msg += f", {filtered} filtered (location)"
    log.info(msg)

    return {
        "new": new,
        "existing": existing,
        "skipped_known": skipped_known,
        "errors": 0,
        "filtered": filtered,
        "total": before,
        "label": label,
    }


# -- Single query search -----------------------------------------------------

def search_jobs(
    query: str,
    location: str,
    sites: list[str] | None = None,
    remote_only: bool = False,
    results_per_site: int = 50,
    hours_old: int = 72,
    proxy: str | None = None,
    country_indeed: str = "usa",
) -> dict:
    """Run a single job search via JobSpy and store results in DB."""
    if sites is None:
        sites = ["indeed", "linkedin", "zip_recruiter"]

    proxy_config = parse_proxy(proxy) if proxy else None

    log.info("Search: \"%s\" in %s | sites=%s | remote=%s", query, location, sites, remote_only)

    kwargs = {
        "site_name": sites,
        "search_term": query,
        "location": location,
        "results_wanted": results_per_site,
        "hours_old": hours_old,
        "description_format": "markdown",
        "country_indeed": country_indeed,
        "verbose": 2,
    }

    if remote_only:
        kwargs["is_remote"] = True

    if proxy_config:
        kwargs["proxies"] = [proxy_config["jobspy"]]

    if "linkedin" in sites:
        kwargs["linkedin_fetch_description"] = True

    try:
        df = scrape_jobs(**kwargs)
    except Exception as e:
        log.error("JobSpy search failed: %s", e)
        return {"error": str(e), "total": 0, "new": 0, "existing": 0}

    total = len(df)
    log.info("JobSpy returned %d results", total)

    if total == 0:
        return {"total": 0, "new": 0, "existing": 0}

    if "site" in df.columns:
        site_counts = df["site"].value_counts()
        for site, count in site_counts.items():
            log.info("  %s: %d", site, count)

    conn = init_db()
    new, existing, skipped_known = store_jobspy_results(conn, df, query)
    log.info("Stored: %d new, %d already in DB (%d skipped known)", new, existing, skipped_known)

    db_total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL").fetchone()[0]
    log.info("DB total: %d jobs, %d pending detail scrape", db_total, pending)

    return {"total": total, "new": new, "existing": existing}


# -- Full crawl (all queries x all locations) --------------------------------

def _full_crawl(
    search_cfg: dict,
    tiers: list[int] | None = None,
    locations: list[str] | None = None,
    sites: list[str] | None = None,
    results_per_site: int = 100,
    hours_old: int = 72,
    proxy: str | None = None,
    max_retries: int = 2,
    workers: int = 1,
) -> dict:
    """Run all search queries from search config across all locations."""
    if sites is None:
        sites = ["indeed", "linkedin", "zip_recruiter"]

    # Build search combinations from config
    queries = search_cfg.get("queries", [])
    locs = search_cfg.get("locations", [])
    defaults = search_cfg.get("defaults", {})
    glassdoor_map = search_cfg.get("glassdoor_location_map", {})
    accept_locs, reject_locs = _load_location_config(search_cfg)

    if tiers:
        queries = [q for q in queries if q.get("tier") in tiers]
    if locations:
        allowed = set(locations)
        locs = [
            loc for loc in locs
            if loc.get("location") in allowed or loc.get("label") in allowed
        ]

    max_queries = os.environ.get("JOBWRIGHT_DISCOVER_MAX_QUERIES")
    if max_queries:
        queries = queries[: int(max_queries)]

    searches = []
    for q in queries:
        for loc in locs:
            searches.append({
                "query": q["query"],
                "location": loc["location"],
                "remote": loc.get("remote", False),
                "tier": q.get("tier", 0),
            })

    extra_companies = []
    for raw in search_cfg.get("target_companies") or []:
        name = raw.get("name") if isinstance(raw, dict) else raw
        name = str(name or "").strip()
        if name:
            extra_companies.append(name)
    extra_companies = extra_companies[:8]
    for name in extra_companies:
        for loc in locs:
            searches.append({
                "query": name,
                "location": loc["location"],
                "remote": loc.get("remote", False),
                "tier": 1,
            })
    if extra_companies:
        log.info("JobSpy: +%d target-company searches", len(extra_companies))
    remote_any = remote_scope(search_cfg) == "any"
    for s in searches:
        s["remote_any"] = remote_any

    proxy_config = parse_proxy(proxy) if proxy else None

    # Cap concurrency to avoid LinkedIn/Indeed soft-bans. Env override lets
    # operators raise the ceiling without a code change.
    worker_cap = _DEFAULT_DISCOVER_WORKER_CAP
    cap_env = os.environ.get("JOBWRIGHT_DISCOVER_WORKERS")
    if cap_env:
        try:
            worker_cap = max(1, int(cap_env))
        except ValueError:
            log.warning("Ignoring non-integer JOBWRIGHT_DISCOVER_WORKERS=%r", cap_env)
    effective_workers = max(1, min(workers, worker_cap))

    log.info("Full crawl: %d search combinations", len(searches))
    log.info(
        "Sites: %s | Results/site: %d | Hours old: %d | Workers: %d",
        ", ".join(sites), results_per_site, hours_old, effective_workers,
    )

    # Ensure DB schema is ready; preload known URLs so store skips redundant
    # filter/sponsorship work for jobs already in the DB.
    init_db()
    known_urls = load_known_urls(get_connection())
    log.info("JobSpy: %d known URLs preloaded for skip", len(known_urls))
    li_rejects = None
    if "linkedin" in sites and linkedin.use_guest_client():
        li_rejects = _linkedin_reject_memory(search_cfg)
        log.info("LinkedIn: %d recently rejected jobs remembered for skip", len(li_rejects))

    total_new = 0
    total_existing = 0
    total_skipped = 0
    total_errors = 0
    completed = 0
    t0 = time.time()

    search_args = (
        sites, results_per_site, hours_old,
        proxy_config, defaults, max_retries,
        accept_locs, reject_locs, glassdoor_map,
    )

    def _accumulate(result: dict) -> None:
        nonlocal total_new, total_existing, total_skipped, total_errors, completed
        completed += 1
        total_new += result["new"]
        total_existing += result["existing"]
        total_skipped += result.get("skipped_known", 0)
        total_errors += result["errors"]

    def _progress() -> None:
        if completed % 5 == 0 or completed == len(searches):
            log.info(
                "Progress: %d/%d queries done (%d new, %d dupes, %d skipped known, %d errors) [%.0fs]",
                completed, len(searches), total_new, total_existing,
                total_skipped, total_errors, time.time() - t0,
            )

    try:
        if effective_workers > 1 and len(searches) > 1:
            with ThreadPoolExecutor(max_workers=min(effective_workers, len(searches))) as pool:
                futures = {
                    pool.submit(_run_one_search, s, *search_args, known_urls, li_rejects): s
                    for s in searches
                }
                for future in as_completed(futures):
                    _accumulate(future.result())
                    _progress()
        else:
            for s in searches:
                _accumulate(_run_one_search(s, *search_args, known_urls, li_rejects))
                _progress()
    finally:
        if li_rejects is not None:
            li_rejects.save()

    # Final stats
    conn = get_connection()
    db_total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    elapsed = time.time() - t0

    log.info(
        "Full crawl complete: %d new | %d dupes (%d skipped known) | %d errors | %d total in DB [%.0fs]",
        total_new, total_existing, total_skipped, total_errors, db_total, elapsed,
    )
    if li_rejects is not None:
        li = linkedin.shared_client()
        log.info(
            "LinkedIn guest client: %d requests (%d descriptions), %d rate-limited (429)",
            li.requests, li.descriptions_fetched, li.rate_limited,
        )

    return {
        "new": total_new,
        "existing": total_existing,
        "skipped_known": total_skipped,
        "errors": total_errors,
        "db_total": db_total,
        "queries": len(searches),
        "workers": effective_workers,
    }


# -- Public entry point ------------------------------------------------------

def run_discovery(cfg: dict | None = None, workers: int = 1) -> dict:
    """Main entry point for JobSpy-based job discovery.

    Loads search queries and locations from the user's search config YAML,
    then runs a full crawl across all configured job boards.

    Args:
        cfg: Override the search configuration dict. If None, loads from
             the user's searches.yaml file.
        workers: Parallel search-combination threads (capped; see
             JOBWRIGHT_DISCOVER_WORKERS). Default 1 = sequential.

    Returns:
        Dict with stats: new, existing, errors, db_total, queries.
    """
    if cfg is None:
        cfg = config.load_search_config()

    if not cfg:
        log.warning("No search configuration found. Run `jobwright init` to create one.")
        return {"new": 0, "existing": 0, "errors": 0, "db_total": 0, "queries": 0}

    proxy = cfg.get("proxy")
    sites = cfg.get("boards") or cfg.get("sites")
    if not sites:
        sites = ["indeed", "linkedin", "zip_recruiter"]
    results_per_site = cfg.get("defaults", {}).get("results_per_site", 100)
    hours_old = cfg.get("defaults", {}).get("hours_old", 72)
    tiers = cfg.get("tiers")
    locations = cfg.get("location_labels")

    # DISCOVER_MODE=fast → tier-1 queries only (unless searches.yaml sets tiers explicitly)
    discover_mode = os.environ.get("DISCOVER_MODE", "fast").strip().lower()
    if tiers is None and discover_mode == "fast":
        tiers = [1]
        log.info("JobSpy: DISCOVER_MODE=fast → tier 1 queries only")

    loc_env = os.environ.get("JOBWRIGHT_DISCOVER_LOCATIONS")
    if loc_env:
        locations = [x.strip() for x in loc_env.split("|") if x.strip()]
        log.info("JobSpy: limiting locations to %s", locations)

    rps_env = os.environ.get("JOBWRIGHT_RESULTS_PER_SITE")
    if rps_env:
        results_per_site = int(rps_env)

    # Widen (or narrow) the freshness window without editing searches.yaml.
    # The default 24h is tight for niche non-tech roles; dedup + known-URL skip
    # make a wider window safe on re-runs.
    hours_env = os.environ.get("JOBWRIGHT_HOURS_OLD")
    if hours_env:
        try:
            hours_old = int(hours_env)
            log.info("JobSpy: hours_old override = %d", hours_old)
        except ValueError:
            log.warning("Ignoring non-integer JOBWRIGHT_HOURS_OLD=%r", hours_env)

    # Restrict boards without editing searches.yaml (e.g. Indeed-only for smoke,
    # since ZipRecruiter/Glassdoor/Google frequently return 0 behind WAFs).
    boards_env = os.environ.get("JOBWRIGHT_DISCOVER_BOARDS")
    if boards_env:
        override = [b.strip() for b in boards_env.replace("|", ",").split(",") if b.strip()]
        if override:
            sites = override
            log.info("JobSpy: board override = %s", sites)

    return _full_crawl(
        search_cfg=cfg,
        tiers=tiers,
        locations=locations,
        sites=sites,
        results_per_site=results_per_site,
        hours_old=hours_old,
        proxy=proxy,
        workers=workers,
    )
