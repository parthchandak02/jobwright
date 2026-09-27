"""Per-user Hermes WhatsApp group instructions, generated from users.yaml.

Edits only the jobwright-owned entries under `whatsapp:` in ~/.hermes/config.yaml
(channel_overrides, channel_prompts, channel_skill_bindings, group_allow_from),
round-tripping with ruamel.yaml so comments, key order and quoting survive.
"""

from __future__ import annotations

import difflib
import io
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString

from jobwright.users import UserRecord, list_users

MARKER = "# managed by jobwright (hermes_channels)"
SKILLS = ["pp-job-apply", "hermes-cron-jobs", "graphify", "cursor-agent"]
DEFAULT_CONFIG = "~/.hermes/config.yaml"
PARTS = ("override", "prompt", "binding", "allow")


def default_config_path() -> Path:
    return Path(os.environ.get("HERMES_CONFIG") or DEFAULT_CONFIG).expanduser()


def _dashboard_url() -> str:
    from jobwright.notify import DEFAULT_BASE_URL

    return os.environ.get("JOBWRIGHT_PUBLIC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _repo_root() -> Path:
    from jobwright.hermes_cron import _repo_root as root

    return root()


def group_jid(user: UserRecord) -> str | None:
    target = (user.whatsapp_target or "").strip().lower().removeprefix("whatsapp:").strip()
    return target if target.endswith("@g.us") and len(target) > len("@g.us") else None


def render_system_prompt(user: UserRecord) -> str:
    uid = user.user_id
    name = user.name.strip() or uid
    url = _dashboard_url()
    apply_line = "apply_enabled: true (only from the dashboard apply button)" if user.apply_enabled \
        else "apply_enabled: false (find-only until they opt in)"
    lines = [
        f"You are the Hermes operator for jobwright in {name}'s WhatsApp group (user: {uid}).",
        MARKER,
        f"JOBWRIGHT_REPO={_repo_root()}",
        f"Dashboard: {url}",
        apply_line,
        "",
        f"This group belongs ONLY to {name} ({uid}). Never read, change or act on any other profile's data;",
        f"  every command uses --user {uid}.",
        "Every turn: load pp-job-apply; resolve WhatsApp sender -> user before profile commands.",
        "Codebase questions: use graphify skill (query/path/explain on graphify-out/graph.json).",
        f"Daily Brief cron: jobwright-brief-{uid} only (never job-apply-*, jobwright-send-*, jobwright-check-*).",
        "  Scripts: ~/.hermes/scripts/jobwright_*.sh",
        f"job status -> jobwright --user {uid} status",
        f"find jobs now -> JOBWRIGHT_USER={uid} bash ~/.hermes/scripts/jobwright_brief.sh (detached; sends notify when done).",
        f"notify / resend -> jobwright --user {uid} notify (one WhatsApp list with dashboard deep links).",
    ]
    if user.human_gate:
        lines.append(
            f"Human gate ON: the brief sends a review-first list; materials are generated on demand "
            f"(dashboard Auto Tailor or jobwright --user {uid} run tailor cover docx)."
        )
    lines += [
        f"Review, ratings and apply happen in the dashboard ({url}/jobs/<job_id>), not over WhatsApp. Never auto-apply.",
        f"When {name} says a job is or is not a fit, ask them to rate it or tap \"Not for me\" in the dashboard.",
        "Scoring model is configured in the repo .env; never choose or switch models here, and never use gpt-oss.",
        "Never send test messages to this group. Brief problems alert the operator (ops_target), not this chat.",
        "Code/bugs: reproduce with doctor/status/logs; fix via cursor-agent; never commit users/ or .env.",
        "Docs: docs/agents/whatsapp-group-jobwright.md, hermes-operator-guide.md, whatsapp-routing.md",
    ]
    return "\n".join(lines) + "\n"


def render_channel_prompt(user: UserRecord) -> str:
    return (
        f"jobwright group ({user.user_id}). Auto-loaded skills: {', '.join(SKILLS)}. "
        f"See channel_overrides system_prompt and {_repo_root()}/docs/agents/whatsapp-group-jobwright.md."
    )


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 1 << 30
    return y


def _dump(y: YAML, doc: Any) -> str:
    buf = io.StringIO()
    y.dump(doc, buf)
    return buf.getvalue()


def _is_managed(override: Any) -> bool:
    return isinstance(override, dict) and MARKER in str(override.get("system_prompt") or "")


def _child(parent: CommentedMap, key: str, factory):
    if not isinstance(parent.get(key), (dict, list)):
        parent[key] = factory()
    return parent[key]


@dataclass
class Plan:
    config_path: str
    entries: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    diff: str = ""
    new_text: str = ""
    old_text: str = ""

    def ids(self, status: str) -> list[str]:
        return [e["user_id"] for e in self.entries if e["status"] == status]

    @property
    def changed(self) -> bool:
        return self.new_text != self.old_text

    def as_dict(self) -> dict:
        return {
            "config_path": self.config_path,
            "entries": self.entries,
            "add": self.ids("add"),
            "update": self.ids("update"),
            "unchanged": self.ids("unchanged"),
            "skipped": self.skipped,
            "orphans": self.orphans,
            "changed": self.changed,
            "diff": self.diff,
        }


def _sync_user(wa: CommentedMap, user: UserRecord, jid: str) -> list[str]:
    changes: list[str] = []
    overrides = _child(wa, "channel_overrides", CommentedMap)
    prompt = render_system_prompt(user)
    current = overrides.get(jid)
    if not isinstance(current, dict) or str(current.get("system_prompt") or "") != prompt:
        if isinstance(current, dict):
            current["system_prompt"] = LiteralScalarString(prompt)
        else:
            overrides[jid] = CommentedMap(system_prompt=LiteralScalarString(prompt))
        changes.append("override")

    prompts = _child(wa, "channel_prompts", CommentedMap)
    line = render_channel_prompt(user)
    if prompts.get(jid) != line:
        prompts[jid] = line
        changes.append("prompt")

    bindings = _child(wa, "channel_skill_bindings", CommentedSeq)
    binding = next((b for b in bindings if isinstance(b, dict) and str(b.get("id")) == jid), None)
    if binding is None:
        bindings.append(CommentedMap(id=jid, skills=CommentedSeq(SKILLS)))
        changes.append("binding")
    else:
        skills = binding.get("skills")
        if not isinstance(skills, list):
            binding["skills"] = CommentedSeq(SKILLS)
            changes.append("binding")
        elif missing := [s for s in SKILLS if s not in skills]:
            skills.extend(missing)
            changes.append("binding")

    allow = _child(wa, "group_allow_from", CommentedSeq)
    if jid not in [str(a) for a in allow]:
        allow.append(jid)
        changes.append("allow")
    return changes


def _prune(wa: CommentedMap, jid: str) -> None:
    for key in ("channel_overrides", "channel_prompts"):
        if isinstance(wa.get(key), dict):
            wa[key].pop(jid, None)
    for key, match in (("channel_skill_bindings", lambda b: isinstance(b, dict) and str(b.get("id")) == jid),
                       ("group_allow_from", lambda a: str(a) == jid)):
        seq = wa.get(key)
        if isinstance(seq, list):
            for i in reversed([i for i, item in enumerate(seq) if match(item)]):
                del seq[i]


def plan(config_path: str | Path | None = None, prune: bool = False) -> Plan:
    path = Path(config_path).expanduser() if config_path else default_config_path()
    old_text = path.read_text(encoding="utf-8")
    y = _yaml()
    doc = y.load(old_text)
    if doc is None:
        doc = CommentedMap()
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    wa = _child(doc, "whatsapp", CommentedMap)
    if not isinstance(wa, dict):
        raise ValueError(f"{path}: whatsapp is not a mapping")

    result = Plan(config_path=str(path), old_text=old_text)
    owned: dict[str, str] = {}
    for user in list_users():
        jid = group_jid(user)
        if jid is None:
            reason = "no WhatsApp chat set" if not user.whatsapp_target.strip() else "WhatsApp target is not a group"
            result.skipped.append({"user_id": user.user_id, "name": user.name or user.user_id, "reason": reason})
            continue
        if jid in owned:
            result.skipped.append({"user_id": user.user_id, "name": user.name or user.user_id,
                                   "reason": f"group already belongs to {owned[jid]}"})
            continue
        owned[jid] = user.user_id
        existed = isinstance((wa.get("channel_overrides") or {}).get(jid), dict)
        changes = _sync_user(wa, user, jid)
        status = "unchanged" if not changes else ("update" if existed else "add")
        result.entries.append({"user_id": user.user_id, "name": user.name or user.user_id, "jid": jid,
                               "status": status, "changes": changes})

    overrides = wa.get("channel_overrides")
    if isinstance(overrides, dict):
        result.orphans = [str(j) for j, o in overrides.items() if str(j) not in owned and _is_managed(o)]
    if prune:
        for jid in result.orphans:
            _prune(wa, jid)

    touched = any(e["changes"] for e in result.entries) or (prune and result.orphans)
    result.new_text = _dump(y, doc) if touched else old_text
    result.diff = "".join(difflib.unified_diff(
        old_text.splitlines(keepends=True), result.new_text.splitlines(keepends=True),
        fromfile=str(path), tofile=f"{path} (jobwright)",
    ))
    return result


def _atomic_write(path: Path, text: str) -> None:
    mode = path.stat().st_mode & 0o7777
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def apply(config_path: str | Path | None = None, prune: bool = False) -> dict:
    from jobwright.hermes_cron import hermes_dry_run

    result = plan(config_path, prune=prune)
    out = {**result.as_dict(), "backup": None, "written": False, "dry_run": hermes_dry_run()}
    if not result.changed or out["dry_run"]:
        return out
    path = Path(result.config_path)
    _yaml().load(result.new_text)
    backup = path.with_name(f"{path.name}.bak-jobwright-{datetime.now():%Y%m%d-%H%M%S}")
    backup.write_bytes(path.read_bytes())
    os.chmod(backup, path.stat().st_mode & 0o7777)
    _atomic_write(path, result.new_text)
    _yaml().load(path.read_text(encoding="utf-8"))
    out.update(backup=str(backup), written=True)
    return out
