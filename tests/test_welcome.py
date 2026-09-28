from __future__ import annotations

from types import SimpleNamespace

import jobwright.welcome as welcome


def test_welcome_message_mentions_name_time_and_board():
    text = welcome.welcome_message("Muskaan", "0 7 * * *")
    assert "Hi Muskaan" in text and "7:00 AM" in text and "https://" in text
    assert "✅ Example Person 1 finished setup" in welcome.admin_message("Example Person 1", "30 6 * * *", "G")
    assert "6:30 AM" in welcome.admin_message("M", "30 6 * * *", "G")


def test_send_welcome_once_and_notifies_operator(tmp_path, monkeypatch):
    user = SimpleNamespace(user_id="m", name="Example Person 1", whatsapp_target="whatsapp:1@g.us", schedule="0 7 * * *")
    monkeypatch.setattr("jobwright.users.get_user", lambda uid: user)
    monkeypatch.setattr(welcome, "_marker_path", lambda uid: tmp_path / "logs" / "welcome_sent.json")
    monkeypatch.setattr("jobwright.hermes_cron.hermes_dry_run", lambda: False)
    monkeypatch.setattr("jobwright.ops.ops_target", lambda: "whatsapp:9@lid")
    monkeypatch.setattr("jobwright.whatsapp.chat_name", lambda t: "Muskaan - Job Applications")
    sent = []
    monkeypatch.setattr("jobwright.notify.send_via_hermes", lambda msg, target: sent.append((target, msg)))

    assert welcome.send_welcome("m") == {"sent": True}
    assert [t for t, _ in sent] == ["whatsapp:1@g.us", "whatsapp:9@lid"]
    assert "Muskaan - Job Applications" in sent[1][1]
    assert welcome.send_welcome("m")["reason"] == "already welcomed"
    assert len(sent) == 2


def test_send_welcome_skips_without_chat_or_in_dry_run(tmp_path, monkeypatch):
    user = SimpleNamespace(user_id="s", name="S", whatsapp_target="", schedule="0 7 * * *")
    monkeypatch.setattr("jobwright.users.get_user", lambda uid: user)
    monkeypatch.setattr(welcome, "_marker_path", lambda uid: tmp_path / "w.json")
    assert welcome.send_welcome("s")["reason"] == "no chat"
    user.whatsapp_target = "whatsapp:1@g.us"
    monkeypatch.setattr("jobwright.hermes_cron.hermes_dry_run", lambda: True)
    assert welcome.send_welcome("s")["reason"] == "dry run"
    assert not (tmp_path / "w.json").exists()


def test_failed_send_is_retried_next_time(tmp_path, monkeypatch):
    user = SimpleNamespace(user_id="r", name="R", whatsapp_target="whatsapp:1@g.us", schedule="0 7 * * *")
    monkeypatch.setattr("jobwright.users.get_user", lambda uid: user)
    monkeypatch.setattr(welcome, "_marker_path", lambda uid: tmp_path / "w.json")
    monkeypatch.setattr("jobwright.hermes_cron.hermes_dry_run", lambda: False)
    monkeypatch.setattr("jobwright.ops.ops_target", lambda: "")

    def boom(msg, target):
        raise RuntimeError("bridge down")

    monkeypatch.setattr("jobwright.notify.send_via_hermes", boom)
    assert welcome.send_welcome("r")["sent"] is False
    assert not (tmp_path / "w.json").exists()
