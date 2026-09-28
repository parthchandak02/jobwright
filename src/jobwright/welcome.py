"""One-time welcome after setup: a hello in the person's chat and a heads-up to the operator."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from jobwright import config

log = logging.getLogger(__name__)

MARKER = "welcome_sent.json"


def _clock(schedule: str) -> str:
    from jobwright.users import _cron_clock

    parts = (schedule or "").split()
    return (_cron_clock(parts[0], parts[1]) if len(parts) >= 2 else None) or "your chosen time"


def welcome_message(first_name: str, schedule: str) -> str:
    from jobwright.notify import public_base_url

    hi = f"👋 Hi {first_name}, you're all set up on jobwright!" if first_name else "👋 You're all set up on jobwright!"
    return (
        f"{hi}\n\n"
        f"Every morning at {_clock(schedule)} I'll post your best new job matches here, "
        "each with a link to see the details.\n\n"
        "Tap 👍 or \"Not for me\" on the jobs you see; it learns what you like and gets sharper every day.\n\n"
        f"Your board: {public_base_url()}/"
    )


def admin_message(name: str, schedule: str, chat: str) -> str:
    return f"✅ {name} finished setup. Daily list at {_clock(schedule)} → {chat}."


def _marker_path(user_id: str) -> Path:
    with config.user_context(user_id):
        return Path(config.APP_DIR) / "logs" / MARKER


def already_welcomed(user_id: str) -> bool:
    return _marker_path(user_id).exists()


def send_welcome(user_id: str) -> dict:
    """Send once per profile; later calls are no-ops. Never raises."""
    from jobwright.hermes_cron import hermes_dry_run
    from jobwright.notify import send_via_hermes
    from jobwright.ops import ops_target
    from jobwright.users import get_user
    from jobwright.whatsapp import chat_name

    user = get_user(user_id)
    if user is None or not user.whatsapp_target:
        return {"sent": False, "reason": "no chat"}
    marker = _marker_path(user_id)
    if marker.exists():
        return {"sent": False, "reason": "already welcomed"}
    if hermes_dry_run():
        return {"sent": False, "reason": "dry run"}
    first = (user.name or "").split(" ")[0]
    try:
        send_via_hermes(welcome_message(first, user.schedule), user.whatsapp_target)
    except Exception as exc:  # noqa: BLE001
        log.warning("welcome for %s failed: %s", user_id, exc)
        return {"sent": False, "reason": f"send failed: {exc}"}
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "target": user.whatsapp_target}),
                      encoding="utf-8")
    target = ops_target()
    if target and target != user.whatsapp_target:
        try:
            send_via_hermes(admin_message(user.name or user_id, user.schedule, chat_name(user.whatsapp_target)), target)
        except Exception as exc:  # noqa: BLE001
            log.warning("operator heads-up for %s failed: %s", user_id, exc)
    return {"sent": True}


def send_welcome_async(user_id: str) -> None:
    import threading

    threading.Thread(target=send_welcome, args=(user_id,), daemon=True, name=f"welcome-{user_id}").start()
