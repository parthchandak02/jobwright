"""Ashby helpers: parse hosted job URLs and fetch a posting's application form.

The public posting API (api.ashbyhq.com/posting-api/job-board/<org>) lists
jobs but not their questions; the hosted job page loads the form from the
same GraphQL endpoint used here (``ApiJobPosting``). ``fetch_ashby_form``
normalizes it to ``[{path, title, type, required, options}]`` for
``fillers.ashby_specs`` (application form first, then the EEO survey).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

import httpx

GRAPHQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
_QUERY = """
query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {
  jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) {
    id
    title
    applicationForm { sections { fieldEntries { ... on FormFieldEntry { id field isRequired } } } }
    surveyForms { sections { fieldEntries { ... on FormFieldEntry { id field isRequired } } } }
  }
}
"""


def parse_ashby_url(url: str) -> tuple[str, str] | None:
    """(org, job_posting_id) from jobs.ashbyhq.com/<org>/<id>[/application]."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if not (parsed.hostname or "").lower().endswith("ashbyhq.com"):
        return None
    parts = [unquote(p) for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[1] != "application":
        return parts[0], parts[1]
    return None


def normalize_form(payload: dict[str, Any]) -> list[dict]:
    posting = ((payload or {}).get("data") or {}).get("jobPosting") or {}
    out: list[dict] = []
    forms = [posting.get("applicationForm") or {}, *(posting.get("surveyForms") or [])]
    for form in forms:
        for section in (form or {}).get("sections") or []:
            for entry in section.get("fieldEntries") or []:
                f = entry.get("field") or {}
                if not f.get("path"):
                    continue
                out.append({
                    "path": f["path"],
                    "title": f.get("title") or f["path"],
                    "type": f.get("type") or "String",
                    "required": bool(entry.get("isRequired")),
                    "options": [v.get("label") for v in f.get("selectableValues") or [] if v.get("label")],
                })
    return out


def fetch_ashby_form(org: str, job_posting_id: str, *, client: httpx.Client | None = None,
                     timeout: float = 10.0) -> list[dict]:
    """The posting's form fields (network call; inject ``client`` in tests)."""
    body = {"operationName": "ApiJobPosting", "query": _QUERY,
            "variables": {"organizationHostedJobsPageName": org, "jobPostingId": job_posting_id}}
    own = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        resp = client.post(GRAPHQL_URL, json=body)
        resp.raise_for_status()
        return normalize_form(resp.json())
    finally:
        if own:
            client.close()
