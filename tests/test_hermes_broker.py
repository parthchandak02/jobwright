"""The dashboard -> Hermes unix-socket broker (`hermes_broker`).

This is a privilege boundary: the API runs as ``apps`` and may not touch Hermes' home or the
WhatsApp bridge, so every Hermes-facing call crosses `/run/jobwright-hermes.sock` into a server
running as ``hermes``. Anything the server accepts runs with Hermes' rights, so these tests pin
both halves: the client only forwards what it should, and the server runs nothing that is not in
``OPS`` with every argument matching its pattern.

The fixture stands in for systemd socket activation (``Accept=yes``): one JSON request per
connection, read to EOF, one JSON reply.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from types import SimpleNamespace

import pytest

from jobwright import hermes_broker
from jobwright.hermes_broker import OPS, BrokerError, handle

GROUP = "120363999999999901@g.us"
TARGET = f"whatsapp:{GROUP}"

# op -> (module, attribute) the server is allowed to reach, and whether it is a `@brokered`
# client function (those must be unwrapped so the server never calls back into itself).
OP_TARGETS = {
    "cron_list": ("hermes_cron", "_run_hermes", False),
    "ensure_brief_cron": ("hermes_cron", "ensure_brief_cron", True),
    "remove_brief_cron": ("hermes_cron", "remove_brief_cron", True),
    "brief_cron_installed": ("hermes_cron", "brief_cron_installed", True),
    "pause_legacy_crons": ("hermes_cron", "pause_legacy_crons", True),
    "ensure_backup_cron": ("hermes_cron", "ensure_backup_cron", True),
    "ensure_watchdog_cron": ("hermes_cron", "ensure_watchdog_cron", True),
    "ensure_weekly_eval_cron": ("hermes_cron", "ensure_weekly_eval_cron", True),
    "ensure_weekly_summary_cron": ("hermes_cron", "ensure_weekly_summary_cron", True),
    "apply_pick_schedule": ("hermes_cron", "apply_pick_schedule", True),
    "channels_plan": ("hermes_channels", "plan", True),
    "channels_apply": ("hermes_channels", "apply", True),
    "hermes_targets": ("whatsapp", "_load_hermes_targets", True),
    "group_names": ("whatsapp", "_cached_group_names", True),
    "bridge_status": ("whatsapp", "bridge_status", True),
    "bridge_chat": ("whatsapp", "_bridge_chat", True),
    "send": ("notify", "send_via_hermes", True),
}


@pytest.fixture()
def broker(tmp_path, monkeypatch):
    """A listening broker socket, plus the requests it saw."""
    path = tmp_path / "hermes.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(8)
    server.settimeout(0.1)
    requests: list = []
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                continue
            with conn:
                raw = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                try:
                    req = json.loads(raw or b"{}")
                except ValueError:
                    req = None
                requests.append(req)
                reply = handle(req) if isinstance(req, dict) else {"ok": False, "error": "bad request"}
                conn.sendall(json.dumps(reply, default=str).encode())

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    monkeypatch.setenv(hermes_broker.ENV_SOCK, str(path))
    monkeypatch.setenv(hermes_broker.ENV_SERVER, "")
    try:
        yield SimpleNamespace(path=path, requests=requests)
    finally:
        stop.set()
        thread.join(timeout=5)
        server.close()


def _reply_once(path, raw: bytes) -> threading.Thread:
    """A one-shot server that answers with ``raw`` whatever it is asked."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)

    def once():
        conn, _ = server.accept()
        with conn:
            while conn.recv(65536):
                pass
            conn.sendall(raw)
        server.close()

    thread = threading.Thread(target=once, daemon=True)
    thread.start()
    return thread


def _zed():
    from jobwright import users as users_mod

    users_mod.add_user("zed", schedule="15 7 * * *")


# --------------------------------------------------------------------------- client side


def test_remote_only_with_a_socket_and_never_on_the_server(monkeypatch):
    monkeypatch.delenv(hermes_broker.ENV_SOCK, raising=False)
    assert hermes_broker.remote() is False
    monkeypatch.setenv(hermes_broker.ENV_SOCK, "/run/jobwright-hermes.sock")
    assert hermes_broker.remote() is True
    # The server runs the same code; it must take the local path or it would call itself.
    monkeypatch.setenv(hermes_broker.ENV_SERVER, "1")
    assert hermes_broker.remote() is False


def test_brokered_runs_locally_without_a_socket(monkeypatch, tmp_path):
    from jobwright import hermes_cron

    monkeypatch.delenv(hermes_broker.ENV_SOCK, raising=False)
    monkeypatch.setattr(hermes_cron, "_hermes_scripts_dir", lambda: tmp_path / "scripts")
    assert hermes_cron.brief_cron_installed("zed") is False
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "wrap_jobwright-brief-zed.sh").write_text("#!/bin/sh\n")
    assert hermes_cron.brief_cron_installed("zed") is True


def test_brokered_forwards_the_call_and_returns_the_result(broker, tmp_path, monkeypatch):
    from jobwright import hermes_cron

    _zed()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "wrap_jobwright-brief-zed.sh").write_text("#!/bin/sh\n")
    monkeypatch.setattr(hermes_cron, "_hermes_scripts_dir", lambda: scripts)
    assert hermes_cron.brief_cron_installed("zed") is True
    assert broker.requests == [{"op": "brief_cron_installed", "args": {"user_id": "zed"}}]


def test_local_only_arguments_never_cross_the_broker(broker):
    from datetime import datetime

    from jobwright import hermes_cron

    _zed()
    out = hermes_cron.apply_pick_schedule("zed", 180, now=datetime(2026, 11, 14, 9, 0))
    assert out["scheduled"] is False
    # `now` is a client-side clock and `config_path` a client-side path: neither is forwarded.
    assert broker.requests == [{"op": "apply_pick_schedule", "args": {"user_id": "zed", "veto_minutes": 180}}]


def test_send_crosses_the_broker_and_runs_once_on_the_server(broker, monkeypatch):
    from jobwright import notify

    client_send = notify.send_via_hermes
    sent = []
    monkeypatch.setattr(notify, "send_via_hermes", lambda message, target: sent.append((message, target)))
    assert client_send("one new job", TARGET) is None
    assert sent == [("one new job", TARGET)]
    assert broker.requests == [{"op": "send", "args": {"message": "one new job", "target": TARGET}}]


def test_an_uncertain_send_stays_uncertain_across_the_broker(broker, monkeypatch):
    """notify keeps its claim (never resends) only if SendUncertain survives the round trip."""
    from jobwright import notify

    client_send = notify.send_via_hermes

    def timed_out(message, target):
        raise notify.SendUncertain("hermes send timed out after 300s (may have been delivered)")

    monkeypatch.setattr(notify, "send_via_hermes", timed_out)
    with pytest.raises(notify.SendUncertain, match="may have been delivered"):
        client_send("one new job", TARGET)


def test_a_server_side_failure_becomes_a_broker_error(broker, monkeypatch):
    from jobwright import notify

    client_send = notify.send_via_hermes

    def broken(message, target):
        raise RuntimeError("hermes send failed (exit 97)")

    monkeypatch.setattr(notify, "send_via_hermes", broken)
    with pytest.raises(BrokerError, match="hermes send failed"):
        client_send("one new job", TARGET)


def test_an_unreachable_socket_raises_a_broker_error(tmp_path, monkeypatch):
    monkeypatch.setenv(hermes_broker.ENV_SOCK, str(tmp_path / "missing.sock"))
    with pytest.raises(BrokerError, match="unreachable"):
        hermes_broker.call("cron_list")


def test_a_garbled_reply_raises_a_broker_error(tmp_path, monkeypatch):
    monkeypatch.setenv(hermes_broker.ENV_SOCK, str(tmp_path / "noise.sock"))
    thread = _reply_once(tmp_path / "noise.sock", b"not json")
    with pytest.raises(BrokerError, match="invalid reply"):
        hermes_broker.call("cron_list")
    thread.join(timeout=5)


def test_an_oversized_request_never_reaches_the_socket(broker):
    with pytest.raises(BrokerError, match="too large"):
        hermes_broker.call("send", message="x" * (hermes_broker.MAX_REQUEST + 1), target=TARGET)
    assert broker.requests == []


def test_channels_plan_uses_the_servers_own_config(broker, tmp_path, monkeypatch):
    from jobwright import hermes_channels

    _zed()
    config = tmp_path / "hermes-config.yaml"
    config.write_text("whatsapp:\n  require_mention: true\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_CONFIG", str(config))
    attacker = tmp_path / "elsewhere.yaml"
    attacker.write_text("whatsapp: {}\n", encoding="utf-8")

    plan = hermes_channels.plan(attacker, prune=False)

    assert broker.requests == [{"op": "channels_plan", "args": {"prune": False}}]
    assert plan.as_dict()["config_path"] == str(config)
    assert plan.changed is False  # zed has no WhatsApp chat, so nothing to write


# --------------------------------------------------------------------------- server allowlist


def test_an_op_outside_the_allowlist_is_refused():
    for op in ("cron_delete", "send_via_hermes", "", None, "__import__"):
        reply = handle({"op": op, "args": {}})
        assert reply == {"ok": False, "error": f"op not allowed: {op!r}"}


def test_arbitrary_hermes_commands_cannot_be_smuggled_through_cron_list():
    reply = handle({"op": "cron_list", "args": {"args": ["cron", "delete", "abc"]}})
    assert reply["ok"] is False and "unexpected arguments" in reply["error"]


def test_an_unexpected_argument_is_refused():
    reply = handle({"op": "ensure_brief_cron",
                    "args": {"user_id": "zed", "schedule": "0 6 * * *", "script": "/tmp/evil.sh"}})
    assert reply["ok"] is False and "script" in reply["error"]


def test_a_non_mapping_args_payload_is_refused():
    reply = handle({"op": "cron_list", "args": ["cron", "list"]})
    assert reply["ok"] is False and "op not allowed" in reply["error"]


@pytest.mark.parametrize("user_id", ["../../etc/passwd", "Zed", "", "zed; id", "-zed", "x" * 64, None, 7])
def test_bad_user_ids_are_refused(user_id):
    reply = handle({"op": "brief_cron_installed", "args": {"user_id": user_id}})
    assert reply["ok"] is False and "bad user_id" in reply["error"]


def test_an_unregistered_user_is_refused_but_a_registered_one_passes(tmp_path, monkeypatch):
    from jobwright import hermes_cron

    monkeypatch.setattr(hermes_cron, "_hermes_scripts_dir", lambda: tmp_path / "scripts")
    reply = handle({"op": "brief_cron_installed", "args": {"user_id": "ghost"}})
    assert reply["ok"] is False and "unknown user ghost" in reply["error"]
    _zed()
    assert handle({"op": "brief_cron_installed", "args": {"user_id": "zed"}}) == {"ok": True, "result": False}


@pytest.mark.parametrize("schedule", [
    "0 6 * * *; rm -rf /",
    "0 6 * * $(id)",
    "0 6 * *",
    "0 6 * * * *",
    "0 6 * * * && curl example.com",
    "",
    42,
])
def test_bad_cron_schedules_are_refused(schedule):
    reply = handle({"op": "ensure_watchdog_cron", "args": {"schedule": schedule}})
    assert reply["ok"] is False and "bad cron schedule" in reply["error"]


def test_a_plain_cron_schedule_is_accepted(monkeypatch):
    from jobwright import hermes_cron

    seen = []
    monkeypatch.setattr(hermes_cron, "ensure_watchdog_cron", lambda schedule: seen.append(schedule) or {"ok": True})
    for schedule in ("30 * * * *", "0 6 * * MON-FRI", "*/15 2 1,15 * *"):
        assert handle({"op": "ensure_watchdog_cron", "args": {"schedule": schedule}})["ok"] is True
    assert seen == ["30 * * * *", "0 6 * * MON-FRI", "*/15 2 1,15 * *"]


def test_the_client_cannot_choose_the_backup_destination(monkeypatch):
    from jobwright import hermes_cron

    monkeypatch.setattr(hermes_cron, "ensure_backup_cron", lambda schedule: {"ok": True, "schedule": schedule})
    reply = handle({"op": "ensure_backup_cron", "args": {"schedule": "30 2 * * *", "dest": "/tmp/exfil"}})
    assert reply["ok"] is False and "custom backup dest" in reply["error"]
    assert handle({"op": "ensure_backup_cron", "args": {"schedule": "30 2 * * *", "dest": ""}})["ok"] is True


@pytest.mark.parametrize("veto", [-1, 1441, True, 3.5, "180", None])
def test_veto_minutes_must_be_a_plain_int_in_range(veto):
    _zed()
    reply = handle({"op": "apply_pick_schedule", "args": {"user_id": "zed", "veto_minutes": veto}})
    assert reply["ok"] is False and "integer 0..1440" in reply["error"]


@pytest.mark.parametrize("target", [
    "whatsapp:120363999999999901@evil.example.com",
    f"{GROUP}",
    f"shell:{GROUP}",
    f"whatsapp:{GROUP} && curl example.com",
    "whatsapp:",
    None,
])
def test_bad_whatsapp_targets_are_refused(target):
    reply = handle({"op": "send", "args": {"message": "hi", "target": target}})
    assert reply["ok"] is False and "bad WhatsApp target" in reply["error"]


@pytest.mark.parametrize("message", ["", "   ", "x" * 12001, None, ["hi"]])
def test_bad_messages_are_refused(message):
    reply = handle({"op": "send", "args": {"message": message, "target": TARGET}})
    assert reply["ok"] is False and "1..12000 characters" in reply["error"]


def test_a_send_without_a_target_delivers_nothing(monkeypatch):
    """A missing argument must fail, never fall back to some default chat."""
    from jobwright import notify

    monkeypatch.setattr(notify, "send_via_hermes", lambda message, target: pytest.fail("sent without a target"))
    reply = handle({"op": "send", "args": {"message": "hi"}})
    assert reply["ok"] is False and reply["kind"] == "error" and "TypeError" in reply["error"]


@pytest.mark.parametrize("jid", ["120363999999999901@evil.example.com", "../x@g.us", "a@g.us", TARGET])
def test_bad_bridge_jids_are_refused(jid):
    reply = handle({"op": "bridge_chat", "args": {"jid": jid}})
    assert reply["ok"] is False and "bad WhatsApp jid" in reply["error"]


def test_prune_must_be_a_boolean():
    for value in ("true", 1, None):
        reply = handle({"op": "channels_plan", "args": {"prune": value}})
        assert reply["ok"] is False and "expected true/false" in reply["error"]


# --------------------------------------------------------------------------- wiring guards


def test_every_allowed_op_reaches_an_unwrapped_local_function():
    assert set(OPS) == set(OP_TARGETS)
    for op, (module, name, is_brokered) in OP_TARGETS.items():
        mod = __import__(f"jobwright.{module}", fromlist=[name])
        public = getattr(mod, name)
        local = hermes_broker._local(module, name)
        assert callable(local), op
        if is_brokered:
            # Decorated for the client; the server must get the undecorated function.
            assert local is public.__wrapped_local__, op
        else:
            assert local is public, op


def test_every_brokered_function_has_an_entry_in_ops():
    import re
    from pathlib import Path

    src = Path(hermes_broker.__file__).parent
    declared = {
        m.group(1)
        for path in sorted(src.glob("*.py"))
        if path.name != "hermes_broker.py"
        for m in re.finditer(r"@brokered\(\"([a-z_]+)\"\)", path.read_text(encoding="utf-8"))
    }
    assert declared, "no @brokered functions found; did the decorator move?"
    assert declared <= set(OPS), f"brokered but not allowed by the server: {sorted(declared - set(OPS))}"


# --------------------------------------------------------------------------- serve()


def _serve(monkeypatch, raw: bytes) -> dict:
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(write=out.write, flush=lambda: None))
    assert hermes_broker.serve() == 0
    return json.loads(out.getvalue())


def test_serve_answers_on_stdout_and_never_calls_itself(monkeypatch):
    from jobwright import notify

    monkeypatch.setenv(hermes_broker.ENV_SOCK, "/run/jobwright-hermes.sock")
    monkeypatch.setenv(hermes_broker.ENV_SERVER, "")
    seen = []

    def record(message, target):
        seen.append((message, target, hermes_broker.remote(), os.environ.get(hermes_broker.ENV_SOCK)))

    monkeypatch.setattr(notify, "send_via_hermes", record)
    reply = _serve(monkeypatch, json.dumps({"op": "send", "args": {"message": "hi", "target": TARGET}}).encode())

    assert reply == {"ok": True, "result": None}
    assert seen == [("hi", TARGET, False, None)]
    assert os.environ[hermes_broker.ENV_SERVER] == "1"


@pytest.mark.parametrize("raw, error", [
    (b"", "op not allowed"),
    (b"not json", "bad request"),
    (b"[1, 2]", "bad request"),
    (b'"send"', "bad request"),
    (b"x" * (hermes_broker.MAX_REQUEST + 1), "too large"),
])
def test_serve_refuses_malformed_or_huge_requests(monkeypatch, raw, error):
    monkeypatch.setenv(hermes_broker.ENV_SERVER, "")
    reply = _serve(monkeypatch, raw)
    assert reply["ok"] is False and error in reply["error"]
