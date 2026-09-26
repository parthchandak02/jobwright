"""Job identity helpers shared by scoring, materials, network and the web layer."""

from __future__ import annotations

import re

from jobwright.database import job_id_for_url

JOB_BOARDS = frozenset(
    {"linkedin", "indeed", "glassdoor", "google", "ziprecruiter", "zip_recruiter", "manual", "workday", "jobspy"}
)


def resolve_company(job: dict) -> str:
    """Employer name: the DB company, never a job board name like 'indeed'."""
    company = (job.get("company") or "").strip()
    if company:
        return company
    site = (job.get("site") or "").strip()
    if site and site.lower() not in JOB_BOARDS:
        return site  # Workday / smart-extract store the employer in site
    title = (job.get("title") or "").strip()
    m = re.search(r"\bat\s+([A-Z][\w&.' -]{1,60})$", title)
    if m:
        return m.group(1).strip()
    return ""


def _slug(text: str, limit: int) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text or "").strip()
    return re.sub(r"\s+", "_", cleaned)[:limit].strip("_")


def material_prefix(job: dict) -> str:
    """Unique, readable file stem for a job's generated materials.

    Company + title keep downloads recognizable; the job_id suffix makes two
    postings with the same title never overwrite each other's files.
    """
    company = _slug(resolve_company(job), 30) or "company"
    title = _slug(job.get("title") or "untitled", 50) or "untitled"
    return f"{company}_{title}_{job_id_for_url(job['url'])}"
