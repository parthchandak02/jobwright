"""jobwright -> Hermes across users (2026-11-10).

Hermes runs as the system user ``hermes`` and owns ~hermes/.hermes (cron jobs, scripts/, config.yaml,
whatsapp/all_groups.json); only it may reach the WhatsApp bridge on 127.0.0.1:3000 (nft rule). The
dashboard runs as ``apps`` and cannot touch any of that. So every Hermes-facing call that the
dashboard makes goes over a unix socket instead:

    /run/jobwright-hermes.sock  (systemd socket, group jwdata)  ->  jobwright-hermes@.service as hermes
                                                                ->  python -m jobwright.hermes_broker serve

The server is this same module, run from /srv/jobwright (code apps cannot change). It accepts one
JSON request ``{"op": ..., "args": {...}}`` per connection, checks the op against ``OPS`` and every
argument against a strict pattern, runs the normal local function as hermes, and answers JSON.

Client side: set ``JOBWRIGHT_HERMES_BROKER=/run/jobwright-hermes.sock`` (jobwright-api.service does).
Functions decorated with ``@brokered`` then forward their call; without the variable (Hermes' own
cron scripts, Parth's shell) they run locally exactly as before.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import re
import socket
import sys

ENV_SOCK = "JOBWRIGHT_HERMES_BROKER"
ENV_SERVER = "JOBWRIGHT_HERMES_BROKER_SERVER"
TIMEOUT = 90.0
MAX_REQUEST = 64 * 1024


class BrokerError(RuntimeError):
    pass


def remote() -> bool:
    return bool(os.environ.get(ENV_SOCK)) and os.environ.get(ENV_SERVER) != "1"


def call(op: str, **args):
    """Send one request; returns the result or raises the error the server reported."""
    path = os.environ[ENV_SOCK]
    payload = json.dumps({"op": op, "args": args}).encode()
    if len(payload) > MAX_REQUEST:
        raise BrokerError("request too large")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect(path)
            s.sendall(payload + b"\n")
            s.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                b = s.recv(65536)
                if not b:
                    break
                chunks.append(b)
    except OSError as exc:
        raise BrokerError(f"Hermes broker unreachable ({path}): {exc}") from exc
    try:
        reply = json.loads(b"".join(chunks) or b"{}")
    except ValueError as exc:
        raise BrokerError("Hermes broker sent an invalid reply") from exc
    if reply.get("ok"):
        return reply.get("result")
    kind, msg = reply.get("kind") or "error", reply.get("error") or "unknown error"
    if kind == "uncertain":
        from jobwright.notify import SendUncertain

        raise SendUncertain(msg)
    raise BrokerError(msg)


def brokered(op: str):
    """Forward the decorated function to the broker when ``remote()``; run it locally otherwise."""

    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not remote():
                return fn(*a, **kw)
            bound = sig.bind(*a, **kw)
            bound.apply_defaults()
            args = {k: v for k, v in bound.arguments.items() if k not in ("now", "config_path")}
            result = call(op, **args)
            return _wrap(op, result)

        wrapper.__wrapped_local__ = fn
        return wrapper

    return deco


class _RemotePlan(dict):
    """hermes_channels.plan() over the broker: the Plan's as_dict() payload."""

    def as_dict(self) -> dict:
        return dict(self)

    @property
    def changed(self) -> bool:
        return bool(self.get("changed"))


def _wrap(op: str, result):
    return _RemotePlan(result or {}) if op == "channels_plan" else result


# --------------------------------------------------------------------------- server side

_USER = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
_FIELD = r"[0-9*/,A-Za-z-]{1,40}"
_SCHEDULE = re.compile(rf"^{_FIELD}( {_FIELD}){{4}}$")
_TARGET = re.compile(r"^whatsapp:[0-9A-Za-z._-]{3,64}(@(g\.us|s\.whatsapp\.net|lid))?$")
_JID = re.compile(r"^[0-9A-Za-z._-]{3,64}@(g\.us|s\.whatsapp\.net|lid)$")


def _user(v) -> str:
    if not isinstance(v, str) or not _USER.match(v):
        raise ValueError("bad user_id")
    from jobwright.users import get_user

    if get_user(v) is None:
        raise ValueError(f"unknown user {v}")
    return v


def _schedule(v) -> str:
    if not isinstance(v, str) or not _SCHEDULE.match(v.strip()):
        raise ValueError("bad cron schedule")
    return v.strip()


def _bool(v) -> bool:
    if not isinstance(v, bool):
        raise ValueError("expected true/false")
    return v


def _int(lo: int, hi: int):
    def check(v) -> int:
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise ValueError(f"expected an integer {lo}..{hi}")
        return v

    return check


def _target(v) -> str:
    if not isinstance(v, str) or not _TARGET.match(v):
        raise ValueError("bad WhatsApp target")
    return v


def _jid(v) -> str:
    if not isinstance(v, str) or not _JID.match(v):
        raise ValueError("bad WhatsApp jid")
    return v


def _message(v) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > 12000:
        raise ValueError("message must be 1..12000 characters")
    return v


def _empty_dest(v) -> str:
    if v not in ("", None):
        raise ValueError("a custom backup dest is not accepted over the broker")
    return ""


def _local(module: str, name: str):
    mod = __import__(f"jobwright.{module}", fromlist=[name])
    fn = getattr(mod, name)
    return getattr(fn, "__wrapped_local__", fn)


def _cron_list():
    res = _local("hermes_cron", "_run_hermes")(["cron", "list"])
    if res.get("error"):
        raise RuntimeError(res["error"])
    return res.get("stdout", "")


# op -> (callable, {arg: validator}). Nothing else is accepted.
OPS: dict = {
    "cron_list": (_cron_list, {}),
    "ensure_brief_cron": (lambda **k: _local("hermes_cron", "ensure_brief_cron")(**k),
                          {"user_id": _user, "schedule": _schedule}),
    "remove_brief_cron": (lambda **k: _local("hermes_cron", "remove_brief_cron")(**k), {"user_id": _user}),
    "brief_cron_installed": (lambda **k: _local("hermes_cron", "brief_cron_installed")(**k), {"user_id": _user}),
    "pause_legacy_crons": (lambda **k: _local("hermes_cron", "pause_legacy_crons")(k["user_id"]),
                           {"user_id": _user, "listing": lambda v: None}),
    "ensure_backup_cron": (lambda **k: _local("hermes_cron", "ensure_backup_cron")(k["schedule"]),
                           {"schedule": _schedule, "dest": _empty_dest}),
    "ensure_watchdog_cron": (lambda **k: _local("hermes_cron", "ensure_watchdog_cron")(**k), {"schedule": _schedule}),
    "ensure_weekly_eval_cron": (lambda **k: _local("hermes_cron", "ensure_weekly_eval_cron")(**k),
                                {"schedule": _schedule}),
    "ensure_weekly_summary_cron": (lambda **k: _local("hermes_cron", "ensure_weekly_summary_cron")(**k),
                                   {"schedule": _schedule}),
    "apply_pick_schedule": (lambda **k: _local("hermes_cron", "apply_pick_schedule")(**k),
                            {"user_id": _user, "veto_minutes": _int(0, 1440)}),
    "channels_plan": (lambda **k: _local("hermes_channels", "plan")(None, prune=k["prune"]).as_dict(),
                      {"prune": _bool}),
    "channels_apply": (lambda **k: _local("hermes_channels", "apply")(None, prune=k["prune"]), {"prune": _bool}),
    "hermes_targets": (lambda **k: _local("whatsapp", "_load_hermes_targets")(), {}),
    "group_names": (lambda **k: _local("whatsapp", "_cached_group_names")(), {}),
    "bridge_status": (lambda **k: _local("whatsapp", "bridge_status")(), {}),
    "bridge_chat": (lambda **k: _local("whatsapp", "_bridge_chat")(**k), {"jid": _jid}),
    "send": (lambda **k: _local("notify", "send_via_hermes")(**k), {"message": _message, "target": _target}),
}


def handle(req: dict) -> dict:
    op = req.get("op")
    args = req.get("args") or {}
    if op not in OPS or not isinstance(args, dict):
        return {"ok": False, "error": f"op not allowed: {op!r}"}
    fn, spec = OPS[op]
    if set(args) - set(spec):
        return {"ok": False, "error": f"unexpected arguments for {op}: {sorted(set(args) - set(spec))}"}
    try:
        clean = {k: check(args.get(k)) for k, check in spec.items() if k in args}
    except ValueError as exc:
        return {"ok": False, "error": f"{op}: {exc}"}
    try:
        return {"ok": True, "result": fn(**clean)}
    except Exception as exc:  # noqa: BLE001
        from jobwright.notify import SendUncertain

        kind = "uncertain" if isinstance(exc, SendUncertain) else "error"
        return {"ok": False, "kind": kind, "error": f"{type(exc).__name__}: {exc}"}


def serve() -> int:
    os.environ[ENV_SERVER] = "1"
    os.environ.pop(ENV_SOCK, None)
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    op = "?"
    if len(raw) > MAX_REQUEST:
        reply = {"ok": False, "error": "request too large"}
    else:
        try:
            req = json.loads(raw or b"{}")
        except ValueError:
            req = None
        if isinstance(req, dict):
            op = str(req.get("op"))[:40]
            reply = handle(req)
        else:
            reply = {"ok": False, "error": "bad request"}
    sys.stdout.write(json.dumps(reply, default=str))
    sys.stdout.flush()
    print(f"jobwright-hermes: op={op} ok={reply.get('ok')}", file=sys.stderr)
    return 0


if __name__ == "__main__" and sys.argv[1:] == ["serve"]:
    raise SystemExit(serve())
