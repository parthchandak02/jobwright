"""Per-job manual LinkedIn connections (dashboard edits)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobwright import config
from jobwright.network.rank import load_connections_csv

_LINKEDIN_PROFILE_RE = re.compile(
    r"^https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w%-]+/?(?:\?.*)?$",
    re.IGNORECASE,
)


def _path() -> Path:
    path = Path(config.NETWORK_DIR) / "manual_job_connections.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_all() -> dict[str, list[dict[str, Any]]]:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for url, contacts in data.items():
        if isinstance(url, str) and isinstance(contacts, list):
            out[url] = [c for c in contacts if isinstance(c, dict)]
    return out


def _save_all(data: dict[str, list[dict[str, Any]]]) -> None:
    path = _path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def normalize_linkedin_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("LinkedIn URL is required")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    if not _LINKEDIN_PROFILE_RE.match(url):
        raise ValueError("Enter a LinkedIn profile URL (linkedin.com/in/…)")
    return url.rstrip("/")


def contact_display_name(contact: dict[str, Any]) -> str:
    name = (contact.get("name") or "").strip()
    if name:
        return name
    parts = [contact.get("first_name") or "", contact.get("last_name") or ""]
    joined = " ".join(p.strip() for p in parts if p and str(p).strip()).strip()
    return joined or "Contact"


def get_manual_contacts(job_url: str) -> list[dict[str, Any]]:
    return list(_load_all().get(job_url, []))


def add_manual_contact(job_url: str, contact: dict[str, Any]) -> dict[str, Any]:
    url = (contact.get("url") or "").strip()
    if url:
        url = normalize_linkedin_url(url)
    name = contact_display_name(contact)
    if not url and not name:
        raise ValueError("Name or LinkedIn URL is required")

    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "first_name": (contact.get("first_name") or "").strip() or None,
        "last_name": (contact.get("last_name") or "").strip() or None,
        "company": (contact.get("company") or "").strip() or None,
        "position": (contact.get("position") or "").strip() or None,
        "email": (contact.get("email") or "").strip() or None,
        "url": url or None,
        "source": "manual",
        "added_at": datetime.now(timezone.utc).isoformat(),
    }

    data = _load_all()
    contacts = data.setdefault(job_url, [])
    if url and any(c.get("url") == url for c in contacts):
        raise ValueError("This LinkedIn profile is already added")
    contacts.append(entry)
    _save_all(data)
    return entry


def remove_manual_contact(job_url: str, contact_id: str) -> bool:
    data = _load_all()
    contacts = data.get(job_url, [])
    kept = [c for c in contacts if c.get("id") != contact_id]
    if len(kept) == len(contacts):
        return False
    if kept:
        data[job_url] = kept
    else:
        data.pop(job_url, None)
    _save_all(data)
    return True


def search_connections_csv(query: str, *, limit: int = 10) -> list[dict[str, str]]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []
    try:
        contacts = load_connections_csv()
    except FileNotFoundError:
        return []

    results: list[dict[str, str]] = []
    for contact in contacts:
        first = (contact.get("first_name") or "").strip()
        last = (contact.get("last_name") or "").strip()
        full = f"{first} {last}".strip().lower()
        company = (contact.get("company") or "").strip().lower()
        if q not in full and not full.startswith(q) and q not in company:
            continue
        results.append(contact)
        if len(results) >= limit:
            break
    return results
