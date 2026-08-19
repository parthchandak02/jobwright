"""Parse Hermes cron list output for the daily brief job."""

from jobwright.hermes_cron import (
    brief_cron_name,
    find_cron_id,
    legacy_cron_names,
    pause_legacy_crons,
)

LISTING = """
  a656ef5ffa51 [active]
    Name:      Daily Briefing
    Schedule:  0 8 * * *

  eabb061396d6 [active]
    Name:      jobwright-brief-richa
    Schedule:  0 6 * * *
    Deliver:   whatsapp:120363427224277278@g.us
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
