"""Per-job network connections."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter

from jobwright import config

router = APIRouter(prefix="/api", tags=["connections"])


def _load_contacts() -> dict:
    path = Path(config.NETWORK_DIR) / "job_contacts_latest.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict) and "jobs" in data:
        return data["jobs"] if isinstance(data["jobs"], dict) else {}
    return data if isinstance(data, dict) else {}


@router.get("/jobs/{url:path}/connections")
def job_connections(url: str) -> dict:
    url = unquote(url)
    contacts = _load_contacts()
    entry = contacts.get(url) or {}
    return {
        "url": url,
        "title": entry.get("title"),
        "company": entry.get("company"),
        "fit_score": entry.get("fit_score"),
        "csv_contacts": entry.get("csv_contacts") or [],
        "web_contacts": entry.get("web_contacts") or [],
    }
