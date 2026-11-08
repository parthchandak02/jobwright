"""Per-user secrets for apply: employer account passwords and one-time codes.

``SecretStore`` is the interface; ``FileSecretStore`` keeps a JSON file with
0600 permissions under the user's data dir (``<user dir>/secrets/apply.json``,
directory 0700). Swap in a keychain/KMS store later by implementing the same
three methods.

Secrets never go into an LLM prompt or tool result. The browser tools fill a
password field with ``fill_secret(ref, name)``: the value is looked up here and
typed into the page by our code; the model only sees "filled [secret]".
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets as _stdlib_secrets
import string
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

from jobwright import config


@runtime_checkable
class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def put(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


def employer_secret_name(url_or_host: str) -> str:
    """Stable name for an employer account: ``account:<host>``."""
    host = urlparse(url_or_host).hostname if "://" in url_or_host else url_or_host
    return f"account:{(host or url_or_host).lower().strip()}"


def generate_password(length: int = 20) -> str:
    """Strong random password with at least one of each class most ATSs demand."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        pw = "".join(_stdlib_secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)):
            return pw


class FileSecretStore:
    """JSON file, owner-only, one per user."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else Path(config.APP_DIR) / "secrets" / "apply.json"

    def _ensure_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self._ensure_dir()
        fd, tmp = tempfile.mkstemp(prefix=".secrets.", dir=str(self.path.parent))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _locked(self):
        self._ensure_dir()
        fh = open(self.path.with_suffix(".lock"), "a")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        return fh

    def get(self, name: str) -> str | None:
        entry = self._read().get(name)
        return entry.get("value") if isinstance(entry, dict) else None

    def put(self, name: str, value: str) -> None:
        fh = self._locked()
        try:
            data = self._read()
            data[name] = {"value": value, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self._write(data)
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()

    def delete(self, name: str) -> None:
        fh = self._locked()
        try:
            data = self._read()
            if data.pop(name, None) is not None:
                self._write(data)
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()

    def names(self) -> list[str]:
        return sorted(self._read())


class MemorySecretStore:
    """Process-local store (tests, and one-time codes that must not hit disk)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._data.get(name)

    def put(self, name: str, value: str) -> None:
        self._data[name] = value

    def delete(self, name: str) -> None:
        self._data.pop(name, None)


def default_store() -> SecretStore:
    return FileSecretStore()


def account_password(store: SecretStore, url_or_host: str, create: bool) -> str | None:
    """The saved password for this employer; generate + save one if ``create``."""
    name = employer_secret_name(url_or_host)
    value = store.get(name)
    if value is None and create:
        value = generate_password()
        store.put(name, value)
    return value
