#!/usr/bin/env python3
"""Block personal data from reaching the public repo.

Checks text for real-looking emails, WhatsApp ids (groups, @lid, phone jids)
and, when the local registry exists, every email, name, phone and chat id found
in users/users.yaml and users/*/profile.json (the registry itself is never
committed). Placeholders such as example.com emails and the fake id ranges used
in tests are allowed.

  python3 scripts/check_private_data.py --staged        # pre-commit: added lines
  python3 scripts/check_private_data.py --push A..B     # pre-push: commits in range
  python3 scripts/check_private_data.py --all           # every tracked file (CI)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
NOT_EMAIL_DOMAINS = ("g.us", "s.whatsapp.net", "lid")
ALLOWED_EMAIL_DOMAINS = (
    "example.com", "example.org", "example.net", "users.noreply.github.com", "noreply.github.com",
    "notify.cloudflare.com", "anthropic.com",
)
JID = re.compile(r"\b(\d{8,})(?:-(\d{9,}))?@(g\.us|lid|s\.whatsapp\.net)")
FAKE_ID = re.compile(r"^(1203630{6,}\d*|12036340{6,}\d*|1203639{6,}\d*|555\d*|1555\d*|1415555\d*|10{6,}\d*)$")

SKIP_FILES = {"scripts/check_private_data.py", "uv.lock", "frontend/pnpm-lock.yaml"}
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".lock")


def _users_dir() -> Path:
    """users/ of this checkout, else of the main checkout (git worktrees share its .git)."""
    import os

    env = os.environ.get("JOBWRIGHT_PRIVACY_USERS_DIR")
    if env:
        return Path(env)
    here = ROOT / "users"
    if here.exists():
        return here
    try:
        common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True,
                                text=True, check=True).stdout.strip()
        return (ROOT / common).resolve().parent / "users"
    except (OSError, subprocess.CalledProcessError):
        return here


def local_denylist() -> list[str]:
    """Private values from the local, never-committed user registry."""
    values: set[str] = set()
    users = _users_dir()
    registry = users / "users.yaml"
    if registry.exists():
        try:
            import yaml

            data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            data = {}
        for email in data.get("admins") or []:
            values.add(str(email))
        target = str(data.get("ops_target") or "")
        if target:
            values.add(target.removeprefix("whatsapp:").split("@")[0])
        for user in data.get("users") or []:
            values.update(str(e) for e in user.get("emails") or [])
            name = str(user.get("name") or "")
            if " " in name:
                values.add(name)
            chat = str(user.get("whatsapp_target") or "")
            if chat:
                values.add(chat.removeprefix("whatsapp:").split("@")[0])
    for profile in users.glob("*/profile.json"):
        try:
            personal = json.loads(profile.read_text(encoding="utf-8")).get("personal") or {}
        except (OSError, ValueError):
            continue
        for key in ("email", "full_name", "preferred_name", "linkedin_url", "phone"):
            value = str(personal.get(key) or "").strip()
            if len(value) >= 6:
                values.add(value)
        digits = re.sub(r"\D", "", str(personal.get("phone") or ""))
        if len(digits) >= 10:
            values.add(digits[-10:])
    return sorted(v for v in values if len(v) >= 6)


def findings(text: str, where: str, deny: list[str]) -> list[str]:
    out: list[str] = []
    for m in EMAIL.finditer(text):
        domain = m.group(0).rsplit("@", 1)[1].lower()
        if domain in NOT_EMAIL_DOMAINS:
            continue
        if not any(domain == d or domain.endswith("." + d) for d in ALLOWED_EMAIL_DOMAINS):
            out.append(f"{where}: email address ({domain})")
    for m in JID.finditer(text):
        if not FAKE_ID.match(m.group(1)):
            out.append(f"{where}: WhatsApp id ending …{m.group(1)[-4:]}@{m.group(3)}")
    lowered = text.lower()
    for value in deny:
        if value.lower() in lowered:
            out.append(f"{where}: value from the local user registry (…{value[-4:]})")
    return out


def _skip(path: str) -> bool:
    return path in SKIP_FILES or path.endswith(SKIP_SUFFIXES) or path.startswith("users/")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def scan_diff(diff: str, deny: list[str]) -> list[str]:
    out: list[str] = []
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and current and not _skip(current):
            out.extend(findings(line[1:], current, deny))
    return out


def scan_all(deny: list[str]) -> list[str]:
    out: list[str] = []
    for path in _git("ls-files").splitlines():
        if _skip(path):
            continue
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out.extend(findings(text, path, deny))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--push", metavar="RANGE")
    mode.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    deny = local_denylist()
    if args.staged:
        problems = scan_diff(_git("diff", "--cached", "-U0", "--no-color"), deny)
    elif args.push:
        problems = scan_diff(_git("log", "-p", "-U0", "--no-color", "--format=", args.push), deny)
    else:
        problems = scan_all(deny)
    if problems:
        print("Blocked: personal data must not reach the public repo.", file=sys.stderr)
        for p in sorted(set(problems))[:50]:
            print(f"  {p}", file=sys.stderr)
        print("Use placeholders (user1@example.com, Example Person, fake ids 1203639999…). "
              "See AGENTS.md > Public repository.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
