"""AI-powered smart extraction: discovers jobs from arbitrary websites.

Two-phase approach:
  Phase 1: Lightweight intelligence (JSON-LD, API responses, data-testids, DOM stats)
           -> LLM picks the best extraction strategy
  Phase 2: Only for CSS selectors -- Playwright finds repeating card elements,
           extracts 2-3 examples, sends focused HTML to LLM for selector generation.

JSON-LD and API strategies execute directly from stored data -- no LLM needed.

Sites are loaded from config/sites.yaml, with {query_encoded} and {location_encoded}
placeholders replaced from the user's search configuration.

Modules:
  prompts  -- LLM prompt templates
  fetch    -- Playwright page intelligence + HTML cleaning
  judge    -- LLM helpers (ask_llm, extract_json), API-response judge, strategy briefing
  extract  -- JSON path helpers, strategy executors, per-site run (_run_one_site)
  sites    -- sites.yaml, scrape targets, location filter, filtered job storage
  run      -- run over every target (run_smart_extract)

Every public (and previously module-level private) name stays importable from
``jobwright.discovery.smartextract``.
"""

import sys

from jobwright.discovery.smartextract.extract import (
    _run_one_site,
    execute_api_response,
    execute_css_selectors,
    execute_json_ld,
    resolve_json_path,
    resolve_json_path_raw,
)
from jobwright.discovery.smartextract.fetch import (
    _ALLOWED_ATTRS,
    _ALLOWED_PREFIXES,
    _UTILITY_CLASS_RE,
    UA,
    clean_card_html,
    clean_page_html,
    collect_page_intelligence,
)
from jobwright.discovery.smartextract.judge import (
    ask_llm,
    extract_json,
    format_strategy_briefing,
    judge_api_responses,
    log,
)
from jobwright.discovery.smartextract.prompts import FULL_PAGE_SELECTOR_PROMPT, JUDGE_PROMPT, STRATEGY_PROMPT
from jobwright.discovery.smartextract.run import _run_all, run_smart_extract
from jobwright.discovery.smartextract.sites import (
    _load_location_filter,
    _location_ok,
    _store_jobs_filtered,
    build_scrape_targets,
    load_sites,
)

# Fix Windows encoding -- prevents charmap errors on emoji/unicode in job titles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

__all__ = [
    "FULL_PAGE_SELECTOR_PROMPT", "JUDGE_PROMPT", "STRATEGY_PROMPT", "UA",
    "_ALLOWED_ATTRS", "_ALLOWED_PREFIXES", "_UTILITY_CLASS_RE",
    "_load_location_filter", "_location_ok", "_run_all", "_run_one_site", "_store_jobs_filtered",
    "ask_llm", "build_scrape_targets", "clean_card_html", "clean_page_html", "collect_page_intelligence",
    "execute_api_response", "execute_css_selectors", "execute_json_ld", "extract_json",
    "format_strategy_briefing", "judge_api_responses", "load_sites", "log",
    "resolve_json_path", "resolve_json_path_raw", "run_smart_extract",
]
