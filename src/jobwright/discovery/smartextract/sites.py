"""Site list (config/sites.yaml), scrape targets, location filter and filtered storage."""

import logging
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote_plus

import yaml

from jobwright import config
from jobwright.config import CONFIG_DIR
from jobwright.discovery.location import location_ok as _location_ok

# Same logger name as the old single module, so log output is unchanged.
log = logging.getLogger("jobwright.discovery.smartextract")



# -- Location filtering -------------------------------------------------------

def _load_location_filter(search_cfg: dict | None = None):
    """Load location accept/reject lists from search config."""
    if search_cfg is None:
        search_cfg = config.load_search_config()
    return config.load_location_filters(search_cfg)


# -- Site configuration from YAML --------------------------------------------

def load_sites() -> list[dict]:
    """Load scraping target sites from config/sites.yaml."""
    path = CONFIG_DIR / "sites.yaml"
    if not path.exists():
        log.warning("sites.yaml not found at %s", path)
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("sites", [])


def _store_jobs_filtered(
    conn: sqlite3.Connection,
    jobs: list[dict],
    site: str,
    strategy: str,
    accept_locs: list[str],
    reject_locs: list[str],
) -> tuple[int, int]:
    """Store jobs with location + title/salary filtering. Returns (new, existing)."""
    from jobwright.config import load_search_config
    from jobwright.discovery.filters import passes_discovery_filters

    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0
    filtered = 0
    search_cfg = load_search_config()

    for job in jobs:
        url = job.get("url")
        if not url:
            continue
        if not _location_ok(job.get("location"), accept_locs, reject_locs):
            filtered += 1
            continue
        if not passes_discovery_filters(
            title=job.get("title"),
            salary=job.get("salary"),
            description=job.get("description") or job.get("full_description"),
            search_cfg=search_cfg,
        ):
            filtered += 1
            continue
        company = job.get("company") or job.get("employer") or None
        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, company, strategy, discovered_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (url, job.get("title"), job.get("salary"), job.get("description"),
                 job.get("location"), site, company, strategy, now),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    if filtered:
        log.info("Filtered %d jobs (location/title/salary)", filtered)
    conn.commit()
    return new, existing


# -- Target building --------------------------------------------------------

def build_scrape_targets(
    sites: list[dict] | None = None,
    search_cfg: dict | None = None,
) -> list[dict]:
    """Build the full list of (name, url) targets from sites + search config queries.

    - "search" sites get expanded: 1 URL per query from search config
    - "static" sites get scraped once as-is

    Placeholders in URLs:
      {query_encoded} -> URL-encoded search query
      {location_encoded} -> URL-encoded location
      {query} -> raw search query (for simple substitution)
    """
    if sites is None:
        sites = load_sites()
    if search_cfg is None:
        search_cfg = config.load_search_config()

    queries_cfg = search_cfg.get("queries", [])
    queries = [q["query"] for q in queries_cfg]
    locs = search_cfg.get("locations", [])
    default_location = locs[0]["location"] if locs else ""

    targets: list[dict] = []

    for site in sites:
        site_url = site.get("url", "")
        site_name = site.get("name", "Unknown")
        site_type = site.get("type", "static")

        if site_type == "search" and queries:
            for query in queries:
                expanded_url = site_url
                expanded_url = expanded_url.replace("{query_encoded}", quote_plus(query))
                expanded_url = expanded_url.replace("{query}", quote_plus(query))
                expanded_url = expanded_url.replace("{location_encoded}", quote_plus(default_location))
                targets.append({
                    "name": site_name,
                    "url": expanded_url,
                    "query": query,
                })
        else:
            expanded_url = site_url
            expanded_url = expanded_url.replace("{location_encoded}", quote_plus(default_location))
            targets.append({
                "name": site_name,
                "url": expanded_url,
                "query": None,
            })

    return targets
