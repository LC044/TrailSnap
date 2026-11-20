"""Identifier, timezone and tag normalisation helpers for agent actions."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.service.agent.actions import _as_utc, _normalize_tags, _uuid

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def test_uuid_parses_uuid_strings():
    value = uuid4()
    assert _uuid(str(value)) == value


def test_uuid_rejects_invalid_identifiers():
    with pytest.raises(ValueError):
        _uuid("not-a-uuid")


def test_uuid_rejects_missing_identifiers():
    with pytest.raises(ValueError):
        _uuid(None)


def test_as_utc_treats_naive_values_as_utc():
    naive = datetime(2024, 1, 1, 12, 0, 0)
    assert _as_utc(naive) == naive.replace(tzinfo=timezone.utc)


def test_as_utc_converts_aware_values():
    aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert _as_utc(aware) == aware.astimezone(timezone.utc)


def test_normalize_tags_strips_blanks_and_duplicates():
    assert _normalize_tags([" a ", "a", "", "  ", "b"]) == ["a", "b"]


def test_normalize_tags_stringifies_non_string_values():
    # Tags are coerced with str() before validation, so a None becomes "None".
    assert _normalize_tags([None]) == ["None"]


def test_normalize_tags_accepts_empty_input():
    assert _normalize_tags(None) == []
    assert _normalize_tags([]) == []


def test_normalize_tags_rejects_overlong_tags():
    with pytest.raises(ValueError):
        _normalize_tags(["x" * 51])
