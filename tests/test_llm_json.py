"""Tests for structured LLM JSON parsing."""

import pytest

from jobwright.llm_json import LLMJsonError, get_list_field, parse_json_object


def test_parse_json_object_direct():
    data = parse_json_object('{"score": 8, "reasoning": "good fit"}', json_mode=True)
    assert data["score"] == 8


def test_parse_json_object_empty_raises():
    with pytest.raises(LLMJsonError, match="Empty"):
        parse_json_object("", json_mode=True)


def test_parse_json_object_invalid_json_mode_raises():
    with pytest.raises(LLMJsonError, match="not valid JSON"):
        parse_json_object("not json at all", json_mode=True)


def test_get_list_field_contacts():
    data = {"contacts": [{"i": 1, "score": 8}]}
    assert len(get_list_field(data, "contacts", "ranked")) == 1


def test_get_list_field_missing_raises():
    with pytest.raises(LLMJsonError):
        get_list_field({"score": 5}, "contacts")
