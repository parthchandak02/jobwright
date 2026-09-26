"""Parse Hermes cron list output for the daily brief job."""

from jobwright.hermes_cron import (
    brief_cron_name,
    find_cron_id,
    legacy_cron_names,
)

LISTING = """
  a656ef5ffa51 [active]
    Name:      Daily Briefing
    Schedule:  0 8 * * *

  eabb061396d6 [active]
    Name:      jobwright-brief-richa
    Schedule:  0 6 * * *
    Deliver:   whatsapp:120363999999999902@g.us
    Script:    wrap_jobwright-brief-richa.sh
"""


def test_find_cron_id():
    assert find_cron_id(LISTING, "jobwright-brief-richa") == "eabb061396d6"
    assert find_cron_id(LISTING, "Daily Briefing") == "a656ef5ffa51"
    assert find_cron_id(LISTING, "missing") is None


def test_brief_cron_name():
    assert brief_cron_name("richa") == "jobwright-brief-richa"


def test_legacy_cron_names():
    names = legacy_cron_names("richa")
    assert "jobwright-send-richa" in names
    assert "jobwright-check-richa" in names
    assert "job-apply-morning-richa" in names


def test_ensure_brief_cron_creates_then_edits(tmp_path, monkeypatch):
    from jobwright import hermes_cron
    from jobwright import users as users_mod

    users_mod.add_user("zed", schedule="15 7 * * *")
    monkeypatch.setattr(hermes_cron, "_hermes_scripts_dir", lambda: tmp_path / "scripts")
    calls = []
    listing = {"text": ""}

    def fake(args):
        calls.append(args)
        if args[:2] == ["cron", "list"]:
            return {"stdout": listing["text"]}
        if "create" in args:
            listing["text"] = "  abcdef123456 [active]\n    Name:      jobwright-brief-zed\n"
        return {"stdout": ""}

    monkeypatch.setattr(hermes_cron, "_run_hermes", fake)
    out = hermes_cron.ensure_brief_cron("zed", "15 7 * * *")
    assert out["ok"] and out["cron_id"] == "abcdef123456"
    create = next(c for c in calls if "create" in c)
    assert create[create.index("--deliver") + 1] == "local" and "--no-agent" in create
    wrapper = (tmp_path / "scripts" / "wrap_jobwright-brief-zed.sh").read_text()
    assert 'JOBWRIGHT_USER="zed"' in wrapper and "scripts/jobwright_brief.sh" in wrapper
    out = hermes_cron.ensure_brief_cron("zed", "30 8 * * *")
    edit = calls[-1]
    assert "edit" in edit and "abcdef123456" in edit and "30 8 * * *" in edit


def test_hermes_dry_run_never_touches_hermes(tmp_path, monkeypatch):
    import subprocess

    from jobwright import hermes_cron, notify
    from jobwright import users as users_mod

    monkeypatch.setenv("JOBWRIGHT_HERMES_DRY_RUN", "1")
    monkeypatch.setattr(hermes_cron, "_hermes_scripts_dir", lambda: tmp_path / "scripts")
    calls = []
    real_run = subprocess.run

    def spy(args, *a, **k):
        calls.append(args)
        return real_run(["true"], *a, **{kk: v for kk, v in k.items() if kk in ("capture_output", "text")})

    monkeypatch.setattr(subprocess, "run", spy)
    users_mod.add_user("sandy", schedule="0 7 * * *")
    hermes_cron.ensure_brief_cron("sandy", "0 7 * * *")
    notify.send_via_hermes("hi", "whatsapp:1@s.whatsapp.net")
    assert all(c[:3] == ["hermes", "cron", "list"] for c in calls)
    assert not (tmp_path / "scripts").exists()
