"""Employer-account secrets: names, generated passwords, and the on-disk store.

The apply agent never sees these values. ``FileSecretStore`` is the only copy,
so a bad write, a loose mode, or a lost update would leak or lock the person
out of an employer account.
"""

from __future__ import annotations

import fcntl
import json
import os
import stat
import threading
from datetime import datetime, timezone

import pytest

from jobwright import config
from jobwright.apply.secret_store import (
    FileSecretStore,
    MemorySecretStore,
    account_password,
    default_store,
    employer_secret_name,
    generate_password,
)


def _has_password_classes(pw: str) -> bool:
    return (
        any(c.islower() for c in pw)
        and any(c.isupper() for c in pw)
        and any(c.isdigit() for c in pw)
        and any(not c.isalnum() for c in pw)
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Jobs.Lever.co/acme/123", "account:jobs.lever.co"),
        ("https://user:pass@Jobs.Example.com/path?q=1", "account:jobs.example.com"),
        ("https://boards.greenhouse.io:443/acme", "account:boards.greenhouse.io"),
        (" HTTPS://X.COM/y ", "account:x.com"),
        ("  Example.COM  ", "account:example.com"),
        ("jobs.example.com:443", "account:jobs.example.com:443"),
    ],
)
def test_employer_secret_name_uses_the_lowercase_host(raw, expected):
    assert employer_secret_name(raw) == expected


def test_generated_passwords_have_the_classes_ats_forms_require():
    for length in (4, 20):
        for _ in range(30):
            pw = generate_password(length)
            assert len(pw) == length
            assert _has_password_classes(pw)
            assert all(c.isprintable() and not c.isspace() and c not in "\"'\\`" for c in pw)
    assert len({generate_password() for _ in range(20)}) == 20


def test_file_store_round_trip_is_owner_only_and_reloads(tmp_path):
    path = tmp_path / "secrets" / "apply.json"
    store = FileSecretStore(path)
    store.put("account:jobs.example.com", "Keep-This-1!")
    store.put("account:other.example", "Other-Pass-2!")
    store.put("account:jobs.example.com", "Rotated-Pass-3!")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"account:jobs.example.com", "account:other.example"}
    assert raw["account:jobs.example.com"]["value"] == "Rotated-Pass-3!"
    updated = datetime.fromisoformat(raw["account:jobs.example.com"]["updated_at"])
    assert updated.tzinfo == timezone.utc
    assert abs((datetime.now(timezone.utc) - updated).total_seconds()) < 60

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert store.names() == ["account:jobs.example.com", "account:other.example"]
    assert FileSecretStore(path).get("account:jobs.example.com") == "Rotated-Pass-3!"
    assert path.with_suffix(".lock").is_file()


def test_loose_directory_is_tightened_when_a_secret_is_saved(tmp_path):
    directory = tmp_path / "secrets"
    directory.mkdir()
    directory.chmod(0o755)
    store = FileSecretStore(directory / "apply.json")
    store.put("account:jobs.example.com", "Keep-This-1!")
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_corrupt_and_non_object_entries_do_not_yield_a_secret(tmp_path):
    path = tmp_path / "apply.json"
    path.write_text("{not json", encoding="utf-8")
    store = FileSecretStore(path)
    assert store.get("account:jobs.example.com") is None
    assert store.names() == []

    path.write_text(
        json.dumps({
            "account:jobs.example.com": "plain-string",
            "account:other.example": {"updated_at": "2020-01-01T00:00:00+00:00"},
            "account:ok.example": {"value": "Real-Pass-1!", "updated_at": "2020-01-01T00:00:00+00:00"},
        }),
        encoding="utf-8",
    )
    assert store.get("account:jobs.example.com") is None
    assert store.get("account:other.example") is None
    assert store.get("account:ok.example") == "Real-Pass-1!"


def test_delete_drops_one_secret_and_skips_a_missing_file(tmp_path):
    path = tmp_path / "apply.json"
    store = FileSecretStore(path)
    store.delete("account:missing.example")
    assert not path.exists()

    store.put("account:jobs.example.com", "Keep-This-1!")
    store.put("account:other.example", "Other-Pass-2!")
    store.delete("account:jobs.example.com")
    store.delete("account:jobs.example.com")
    assert store.get("account:jobs.example.com") is None
    assert store.get("account:other.example") == "Other-Pass-2!"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"account:other.example"}
    assert raw["account:other.example"]["value"] == "Other-Pass-2!"


def test_failed_replace_keeps_the_saved_secret_and_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "secrets" / "apply.json"
    store = FileSecretStore(path)
    store.put("account:jobs.example.com", "Keep-This-1!")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        store.put("account:other.example", "Other-Pass-2!")

    assert list(path.parent.glob(".secrets.*")) == []
    assert store.get("account:jobs.example.com") == "Keep-This-1!"
    assert store.get("account:other.example") is None


def test_put_waits_while_another_holder_has_the_lock(tmp_path):
    store = FileSecretStore(tmp_path / "apply.json")
    store.put("account:jobs.example.com", "Keep-This-1!")
    finished = threading.Event()

    def writer():
        store.put("account:other.example", "Other-Pass-2!")
        finished.set()

    thread = threading.Thread(target=writer)
    with open(store.path.with_suffix(".lock"), "a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        thread.start()
        still_waiting = not finished.wait(0.2)
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    thread.join(timeout=5)
    assert still_waiting
    assert not thread.is_alive()
    assert finished.is_set()
    assert store.get("account:jobs.example.com") == "Keep-This-1!"
    assert store.get("account:other.example") == "Other-Pass-2!"


def test_memory_store_stays_in_process():
    first = MemorySecretStore()
    second = MemorySecretStore()
    first.put("email_code", "123456")
    assert first.get("email_code") == "123456"
    assert second.get("email_code") is None
    first.delete("email_code")
    first.delete("email_code")
    assert first.get("email_code") is None


def test_account_password_is_stable_per_employer_and_not_created_unless_asked():
    store = MemorySecretStore()
    assert account_password(store, "https://jobs.example.com/apply/1", create=False) is None
    assert store.get("account:jobs.example.com") is None

    created = account_password(store, "https://Jobs.Example.com/apply/1", create=True)
    assert created is not None
    assert _has_password_classes(created)
    assert account_password(store, "jobs.example.com", create=True) == created
    assert account_password(store, "https://jobs.example.com:443/x", create=False) == created

    other = account_password(store, "jobs.example.com:443", create=True)
    assert other != created
    assert store.get("account:jobs.example.com:443") == other

    store.put("account:boards.greenhouse.io", "Saved-Already-1!")
    assert account_password(store, "https://boards.greenhouse.io/acme", create=True) == "Saved-Already-1!"


def test_default_store_follows_the_active_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    store = default_store()
    assert isinstance(store, FileSecretStore)
    assert store.path == tmp_path / "secrets" / "apply.json"
