from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _guard():
    spec = importlib.util.spec_from_file_location("check_private_data", ROOT / "scripts" / "check_private_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_guard_flags_real_looking_contact_data():
    g = _guard()
    email = "jane.doe" + "@" + "gmail.com"
    chat = "12036341111" + "2222333" + "@g.us"
    hits = g.findings(f"mail me at {email} or whatsapp:{chat}", "f", [])
    assert len(hits) == 2
    assert g.findings("owner@example.com whatsapp:120363999999999901@g.us 14155550100@s.whatsapp.net", "f", []) == []
    assert g.findings("Hi JANE DOE", "f", ["Jane Doe"])


def test_tracked_files_contain_no_personal_data():
    g = _guard()
    assert g.scan_all(g.local_denylist()) == []
