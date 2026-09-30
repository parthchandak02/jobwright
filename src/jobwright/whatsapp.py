"""WhatsApp targets available through Hermes (for the chat picker) and test sends.

Chat ids come from ``hermes send --list whatsapp --json``. Group names are
resolved from the WhatsApp bridge (``GET /chat/<jid>`` returns the subject and
participants), falling back to Hermes' cached group list, then the id.

Privacy: the bot is the operator's WhatsApp account. Admins see every chat;
other users only see chats that include their own phone number, plus a direct
message to that number.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import subprocess
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

BRIDGE_URL = os.environ.get("JOBWRIGHT_WHATSAPP_BRIDGE", "http://127.0.0.1:3000")
_HERMES_HOME = Path(os.path.expanduser("~/.hermes"))


def bold(text: str) -> str:
    """WhatsApp *bold*. `hermes send` passes text through unchanged, so this is native WhatsApp syntax.

    WhatsApp only renders it when the stars hug non-space text, so inner stars are dropped.
    """
    text = " ".join(str(text).replace("*", "").split())
    return f"*{text}*" if text else ""


def italic(text: str) -> str:
    text = " ".join(str(text).replace("_", " ").split())
    return f"_{text}_" if text else ""


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def phone_target(phone: str) -> str | None:
    """whatsapp:<digits>@s.whatsapp.net for a phone number with country code."""
    digits = _digits(phone)
    if len(digits) < 8:
        return None
    return f"whatsapp:{digits}@s.whatsapp.net"


_TARGETS_TTL = 60.0
_targets_cache: tuple[float, list[dict]] | None = None


def _hermes_targets() -> list[dict]:
    """Chat ids Hermes can post to (cached briefly; the CLI takes ~1-2 s)."""
    global _targets_cache
    import time as _time

    if _targets_cache and _time.monotonic() - _targets_cache[0] < _TARGETS_TTL:
        return _targets_cache[1]
    targets = _load_hermes_targets()
    if targets:
        _targets_cache = (_time.monotonic(), targets)
    return targets


def _load_hermes_targets() -> list[dict]:
    try:
        proc = subprocess.run(
            ["hermes", "send", "--list", "whatsapp", "--json"],
            capture_output=True, text=True, timeout=45, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("hermes target list unavailable: %s", exc)
        return []
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError:
        return []
    return list((data.get("platforms") or {}).get("whatsapp") or [])


def _cached_group_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for path in (_HERMES_HOME / "whatsapp" / "all_groups.json",):
        try:
            for g in json.loads(path.read_text(encoding="utf-8")):
                if g.get("id") and g.get("name"):
                    names[g["id"]] = g["name"]
        except (OSError, ValueError, TypeError):
            continue
    return names


def bridge_status() -> str:
    try:
        return str(httpx.get(f"{BRIDGE_URL}/health", timeout=3).json().get("status") or "unknown")
    except Exception:  # noqa: BLE001
        return "unreachable"


_NAME_TTL = 600.0
_name_cache: dict[str, tuple[float, str]] = {}


def _remember_name(jid: str, name: str) -> None:
    import time as _time

    if name and name != jid.split("@")[0]:
        _name_cache[jid] = (_time.monotonic(), name)


def _known_name(jid: str) -> str:
    import time as _time

    hit = _name_cache.get(jid)
    return hit[1] if hit and _time.monotonic() - hit[0] < _NAME_TTL else ""


def _bridge_chat(jid: str) -> dict | None:
    try:
        resp = httpx.get(f"{BRIDGE_URL}/chat/{jid}", timeout=4)
        if resp.status_code == 200:
            info = resp.json()
            _remember_name(jid, str(info.get("name") or ""))
            return info
    except Exception:  # noqa: BLE001
        return None
    return None


def chat_name(target: str | None) -> str:
    """Display name for a whatsapp:<jid> target (bridge, then cached lists, then the id)."""
    jid = (target or "").removeprefix("whatsapp:")
    if not jid:
        return ""
    if jid.endswith("@g.us"):
        known = _known_name(jid)
        if known:
            return known
        info = _bridge_chat(jid) or {}
        name = str(info.get("name") or "")
        if name and name != jid.split("@")[0]:
            return name
        cached = _cached_group_names().get(jid)
        if cached:
            return cached
    for t in (_targets_cache[1] if _targets_cache else []):
        if t.get("id") == jid and t.get("name"):
            return str(t["name"])
    return jid.split("@")[0]


def list_chats(*, for_phone: str | None = None, show_all: bool = False) -> dict:
    """Chats the bot can post to. ``show_all`` for admins, else filtered by ``for_phone``."""
    targets = _hermes_targets()
    cached = _cached_group_names()
    status = bridge_status()
    details: dict[str, dict] = {}
    if status == "connected":
        groups = [t["id"] for t in targets if str(t.get("id", "")).endswith("@g.us")]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for jid, info in zip(groups, pool.map(_bridge_chat, groups)):
                if info:
                    details[jid] = info
    phone = _digits(for_phone)
    chats: list[dict] = []
    for t in targets:
        jid = str(t.get("id") or "")
        if not jid:
            continue
        info = details.get(jid) or {}
        name = str(info.get("name") or "")
        if not name or name == jid.split("@")[0]:
            name = _known_name(jid) or cached.get(jid) or t.get("name") or jid.split("@")[0]
        participants = [str(p) for p in info.get("participants") or []]
        is_member = bool(phone) and any(_digits(p.split("@")[0]).endswith(phone[-10:]) for p in participants)
        if not show_all and not is_member:
            continue
        chats.append({
            "target": f"whatsapp:{jid}",
            "id": jid,
            "name": name,
            "type": "group" if jid.endswith("@g.us") else "dm",
            "participants": len(participants) or None,
            "includes_you": is_member,
        })
    chats.sort(key=lambda c: (not c["includes_you"], c["type"] != "group", c["name"].lower()))
    direct = phone_target(for_phone) if for_phone else None
    return {"bridge": status, "chats": chats, "direct_target": direct, "filtered": not show_all}


def send_test(target: str, name: str = "") -> None:
    from jobwright.notify import send_via_hermes

    hello = f"Hi{(' ' + name) if name else ''}! This chat is now connected to jobwright. " \
            "Your daily list of matching jobs will arrive here."
    send_via_hermes(hello, target)
