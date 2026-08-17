"""ATS detection and hybrid API helpers for stage-6 apply."""

from jobwright.apply.ats.detect import detect_ats
from jobwright.apply.ats.greenhouse import (
    fetch_greenhouse_schema,
    parse_greenhouse_url,
    summarize_schema_for_prompt,
    validate_schema_against_profile,
)

__all__ = [
    "detect_ats",
    "fetch_greenhouse_schema",
    "parse_greenhouse_url",
    "summarize_schema_for_prompt",
    "validate_schema_against_profile",
]
