"""LinkedIn network ranking from exported Connections.csv (no scraping)."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import jobwright.config as config
from jobwright.config import load_profile
from jobwright.llm import get_client
from jobwright.llm_json import LLMJsonError, chat_json_object, get_list_field

log = logging.getLogger(__name__)

# LinkedIn export column name variants
_FIRST = ("First Name", "FirstName", "first_name")
_LAST = ("Last Name", "LastName", "last_name")
_COMPANY = ("Company", "company", "Organization")
_POSITION = ("Position", "Title", "position", "title")
_EMAIL = ("Email Address", "Email", "email")
_CONNECTED = ("Connected On", "Connected", "connected_on")
_URL = ("URL", "Profile URL", "profileUrl", "LinkedIn URL")


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for k in keys:
        if k in row and row[k]:
            return str(row[k]).strip()
    # case-insensitive fallback
    lower = {kk.lower(): vv for kk, vv in row.items()}
    for k in keys:
        if k.lower() in lower and lower[k.lower()]:
            return str(lower[k.lower()]).strip()
    return ""


def load_connections_csv(path: Path | None = None) -> list[dict[str, str]]:
    """Load LinkedIn Connections.csv export.

    LinkedIn exports often have a few preamble rows before the header.
    """
    path = path or config.CONNECTIONS_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Connections CSV not found at {path}.\n"
            "Export from LinkedIn: Settings → Data privacy → Get a copy of your data → Connections.\n"
            f"Place the file at: {path}"
        )

    raw = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    # Find header row
    header_idx = 0
    for i, line in enumerate(raw[:30]):
        if "First Name" in line or "Company" in line and "Position" in line:
            header_idx = i
            break

    reader = csv.DictReader(raw[header_idx:])
    contacts: list[dict[str, str]] = []
    for row in reader:
        if not row:
            continue
        contact = {
            "first_name": _pick(row, _FIRST),
            "last_name": _pick(row, _LAST),
            "company": _pick(row, _COMPANY),
            "position": _pick(row, _POSITION),
            "email": _pick(row, _EMAIL),
            "connected_on": _pick(row, _CONNECTED),
            "url": _pick(row, _URL),
        }
        if not contact["first_name"] and not contact["last_name"] and not contact["company"]:
            continue
        contacts.append(contact)
    return contacts


def _target_guidance(profile: dict) -> str:
    exp = profile.get("experience") or {}
    prefs = profile.get("job_preferences") or {}
    parts = []
    if exp.get("target_role"):
        parts.append(f"Target role: {exp['target_role']}")
    if prefs.get("ideal_roles") or prefs.get("seek"):
        parts.append(f"Seek: {prefs.get('ideal_roles') or prefs.get('seek')}")
    if prefs.get("avoid_roles") or prefs.get("avoid"):
        parts.append(f"Avoid: {prefs.get('avoid_roles') or prefs.get('avoid')}")
    personal = profile.get("personal") or {}
    if personal.get("city") or personal.get("province_state"):
        parts.append(
            f"Location: {personal.get('city', '')}, {personal.get('province_state', '')}"
        )
    return "\n".join(parts) if parts else "Infer from resume themes (strategy, impact, partnerships)."


def _chunk(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def rank_contacts(
    contacts: list[dict[str, str]],
    profile: dict,
    resume_text: str = "",
    top_n: int = 25,
    batch_size: int = 80,
) -> tuple[list[dict], int]:
    """LLM-rank 1st-degree contacts by helpfulness for the user's job search."""
    if not contacts:
        return [], 0

    guidance = _target_guidance(profile)
    client = get_client()
    scored: list[dict] = []
    batch_errors = 0

    system = """You rank LinkedIn contacts for how helpful they would be for a candidate's job search.
Score each contact 1-10 for intro / referral / advice value given the candidate's target roles.
Prefer: people in target industries (startups, impact VC, CSR, foundations), Bay Area, Chief of Staff /
strategy / partnerships / platform roles, hiring managers, founders, operators.
Deprioritize: pure engineers, students, unrelated industries, very junior contacts with no overlap.

Return ONLY a JSON object with this shape:
{"contacts": [{"i": <index>, "score": <1-10>, "why": "<one short sentence>"}]}
Include only contacts scoring 6+. Max 15 per batch."""

    for batch in _chunk(list(enumerate(contacts)), batch_size):
        lines = []
        for idx, c in batch:
            name = f"{c['first_name']} {c['last_name']}".strip()
            lines.append(
                f"{idx}. {name} | {c['position'] or '?'} @ {c['company'] or '?'}"
            )
        user_msg = (
            f"CANDIDATE TARGETS:\n{guidance}\n\n"
            f"RESUME SNIPPET:\n{(resume_text or '')[:2500]}\n\n"
            f"CONTACTS (index | name | title @ company):\n" + "\n".join(lines)
        )
        try:
            data = chat_json_object(
                client,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=8192,
                temperature=0.2,
            )
            items = get_list_field(data, "contacts", "ranked", "results", "items")
        except LLMJsonError as exc:
            batch_errors += 1
            log.error("Network rank batch JSON error: %s", exc)
            continue
        except Exception as e:
            batch_errors += 1
            log.error("LLM network rank error: %s", e)
            continue

        for item in items:
            try:
                i = int(item["i"])
                score = int(item["score"])
            except (KeyError, TypeError, ValueError):
                continue
            if i < 0 or i >= len(contacts):
                continue
            c = contacts[i]
            scored.append({
                "rank_score": score,
                "why": str(item.get("why") or ""),
                "first_name": c["first_name"],
                "last_name": c["last_name"],
                "company": c["company"],
                "position": c["position"],
                "email": c["email"],
                "url": c["url"],
                "connected_on": c["connected_on"],
            })

    # Dedupe by name+company, keep best score
    best: dict[str, dict] = {}
    for s in scored:
        key = f"{s['first_name']}|{s['last_name']}|{s['company']}".lower()
        if key not in best or s["rank_score"] > best[key]["rank_score"]:
            best[key] = s
    ranked = sorted(best.values(), key=lambda x: -x["rank_score"])
    if batch_errors:
        log.warning("Network ranking: %d batch(es) failed JSON parse", batch_errors)
    return ranked[:top_n], batch_errors


def format_network_digest(ranked: list[dict], user_label: str = "", *, batch_errors: int = 0) -> str:
    who = f" ({user_label})" if user_label else ""
    lines = [
        f"=== Network ranking{who} ===",
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "Top 1st-degree contacts to reach out to:",
        "",
    ]
    if not ranked:
        lines.append("No high-value contacts found in this run.")
        lines.append("")
    for i, c in enumerate(ranked, 1):
        name = f"{c['first_name']} {c['last_name']}".strip()
        lines.append(
            f"{i}. *{name}* - {c['position'] or '?'} @ {c['company'] or '?'} "
            f"(score {c['rank_score']})"
        )
        if c.get("why"):
            lines.append(f"   {c['why']}")
        if c.get("url"):
            lines.append(f"   {c['url']}")
        lines.append("")
    if batch_errors:
        lines.append(
            f"Warning: {batch_errors} ranking batch(es) failed to parse. "
            "Results may be incomplete — try again or check logs."
        )
        lines.append("")
    lines.append(
        "Note: 2nd-degree ranking needs manual help - ask top contacts for intros, "
        "or export additional connection lists if they share them. We do not scrape LinkedIn."
    )
    return "\n".join(lines)


def run_network_rank(top_n: int = 25, csv_path: Path | None = None) -> dict:
    """Full network rank pipeline for the active user."""
    profile = load_profile()
    resume = ""
    try:
        from jobwright.resume import load_resume_text

        resume = load_resume_text()
    except FileNotFoundError:
        pass
    contacts = load_connections_csv(csv_path)
    log.info("Loaded %d connections from CSV", len(contacts))
    ranked, batch_errors = rank_contacts(contacts, profile, resume_text=resume, top_n=top_n)

    config.NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    out_json = config.NETWORK_DIR / "ranked_contacts.json"
    out_txt = config.NETWORK_DIR / "ranked_contacts.txt"
    label = (profile.get("personal") or {}).get("preferred_name") or ""
    digest = format_network_digest(ranked, user_label=label, batch_errors=batch_errors)
    out_json.write_text(json.dumps(ranked, indent=2), encoding="utf-8")
    out_txt.write_text(digest, encoding="utf-8")
    return {
        "contacts": len(contacts),
        "ranked": len(ranked),
        "json_path": str(out_json),
        "txt_path": str(out_txt),
        "digest": digest,
    }
