"""ATS detection, hybrid API helpers and deterministic form fillers for stage-6 apply.

Fillers (Greenhouse, Lever, Ashby): ``fillers.filler_for(url, answer_open_question)``;
answer keys and rules: ``forms`` module docstring.
"""

from jobwright.apply.ats.detect import ats_family, detect_ats
from jobwright.apply.ats.greenhouse import (
    fetch_greenhouse_schema,
    parse_greenhouse_url,
    summarize_schema_for_prompt,
    validate_schema_against_profile,
)

__all__ = [
    "ats_family",
    "detect_ats",
    "fetch_greenhouse_schema",
    "parse_greenhouse_url",
    "summarize_schema_for_prompt",
    "validate_schema_against_profile",
]
