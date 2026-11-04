"""Run smart extraction over every target and store the results."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from jobwright import config
from jobwright.database import get_stats, init_db
from jobwright.discovery.smartextract.extract import _run_one_site
from jobwright.discovery.smartextract.sites import (
    _load_location_filter,
    _store_jobs_filtered,
    build_scrape_targets,
    load_sites,
)

# Same logger name as the old single module, so log output is unchanged.
log = logging.getLogger("jobwright.discovery.smartextract")



# -- Run all sites -----------------------------------------------------------

def _run_all(
    targets: list[dict],
    accept_locs: list[str],
    reject_locs: list[str],
    workers: int = 1,
) -> dict:
    """Run smart extract on all targets.

    Sequential by default. When workers > 1, scrapes multiple sites in parallel
    using ThreadPoolExecutor. DB storage is still serialized after each result.
    """
    conn = init_db()
    pre_stats = get_stats(conn)
    log.info("Database: %d jobs already stored, %d pending detail scrape",
             pre_stats["total"], pre_stats["pending_detail"])

    results: list[dict] = []
    total_new = 0
    total_existing = 0

    def _process_result(r: dict, target: dict) -> None:
        nonlocal total_new, total_existing
        jobs = r.get("jobs", [])
        if jobs:
            new, existing = _store_jobs_filtered(conn, jobs, target["name"],
                                                  r.get("strategy", "?"),
                                                  accept_locs, reject_locs)
            total_new += new
            total_existing += existing
            log.info("DB: +%d new, %d already existed", new, existing)

    if workers > 1 and len(targets) > 1:
        # Parallel mode
        with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as pool:
            future_to_target = {
                pool.submit(_run_one_site, target["name"], target["url"]): target
                for target in targets
            }
            for future in as_completed(future_to_target):
                target = future_to_target[future]
                r = future.result()
                results.append(r)
                _process_result(r, target)
    else:
        # Sequential mode (default)
        for i, target in enumerate(targets):
            label = target["name"]
            if target.get("query"):
                label = f"{target['name']} [{target['query']}]"
            log.info("[%d/%d] %s", i + 1, len(targets), label)

            r = _run_one_site(target["name"], target["url"])
            results.append(r)
            _process_result(r, target)

    # Summary
    for r in results:
        strategy = r.get("strategy", "?")
        if r["status"] in ("PASS", "PARTIAL", "FAIL"):
            detail = f"{r['total']} jobs, {r['titles']} titles, strategy={strategy}"
        else:
            detail = r.get("error", "")[:60]
        log.info("%-10s | %-25s | %s", r["status"], r["name"], detail)

    passed = sum(1 for r in results if r["status"] == "PASS")
    log.info("%d/%d PASS", passed, len(results))

    return {"total_new": total_new, "total_existing": total_existing,
            "passed": passed, "total": len(results)}


# -- Public entry point ------------------------------------------------------

def run_smart_extract(
    sites: list[dict] | None = None,
    workers: int = 1,
) -> dict:
    """Main entry point for AI-powered smart extraction.

    Loads sites from config/sites.yaml and search queries from the user's
    search config, then runs the extraction pipeline on all targets.

    Args:
        sites: Override the site list. If None, loads from YAML.
        workers: Number of parallel threads for site scraping. Default 1 (sequential).

    Returns:
        Dict with stats: total_new, total_existing, passed, total.
    """
    search_cfg = config.load_search_config()
    accept_locs, reject_locs = _load_location_filter(search_cfg)

    targets = build_scrape_targets(sites=sites, search_cfg=search_cfg)

    if not targets:
        log.warning("No scrape targets configured. Create config/sites.yaml and searches.yaml.")
        return {"total_new": 0, "total_existing": 0, "passed": 0, "total": 0}

    search_sites = sum(1 for s in (sites or load_sites()) if s.get("type") == "search")
    static_sites = sum(1 for s in (sites or load_sites()) if s.get("type") != "search")
    log.info("Sites: %d searchable, %d static | Total targets: %d (workers=%d)",
             search_sites, static_sites, len(targets), workers)

    return _run_all(targets, accept_locs, reject_locs, workers=workers)
