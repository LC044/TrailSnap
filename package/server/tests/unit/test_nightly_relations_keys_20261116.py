"""2026-11-16 nightly coverage for the relation key helpers.

The 2026-11-16 backend coverage scan reported ``service/relations.py`` at
94.8% with 16 missed lines.  The uncovered part is the *pure* key
grammar in ``parse_key`` / ``canonical_key`` / ``region_conditions``:

* the "key too long" guard (line 83) and the unknown region level guard
  (line 87);
* the unknown relation kind guard (line 108);
* the unresolved-place branch of ``canonical_key`` (line 120);
* the "not a standard region place" guard of ``region_conditions``
  (line 139).

These helpers are the entry point of the whole relations API, so every
malformed key must be rejected with a 400 instead of reaching SQL.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException

from app.service.relations import (
    REGION_FIELDS,
    canonical_key,
    parse_key,
    region_conditions,
    region_key,
    uuid_key,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_parse_key_rejects_oversized_keys():
    with pytest.raises(HTTPException) as excinfo:
        parse_key("person:" + "0" * 2001)
    assert excinfo.value.status_code == 400


def test_parse_key_rejects_unknown_region_level():
    with pytest.raises(HTTPException) as excinfo:
        parse_key("place:region:planet:3:xxx")
    assert excinfo.value.status_code == 400


def test_parse_key_rejects_unknown_relation_kind():
    with pytest.raises(HTTPException) as excinfo:
        parse_key("album:123")
    assert excinfo.value.status_code == 400


def test_canonical_key_keeps_unresolved_place_number():
    key = "place:unresolved:7"
    kind, raw = parse_key(key)
    assert kind == "place"
    assert raw == 7
    assert canonical_key(key) == "place:unresolved:7"


def test_canonical_key_round_trips_region_and_uuid_keys():
    region = region_key("city", ["北京市", "北京市", "海淀区"])
    assert parse_key(region) == ("place", ("city", ["北京市", "北京市", "海淀区"]))
    assert canonical_key(region) == region

    raw = UUID("11111111-2222-3333-4444-555555555555")
    assert canonical_key(uuid_key("person", raw)) == uuid_key("person", raw)


def test_region_conditions_requires_a_region_key():
    with pytest.raises(HTTPException) as excinfo:
        region_conditions("person:" + "0" * 32)
    assert excinfo.value.status_code == 400


def test_region_conditions_builds_one_predicate_per_level():
    conditions = region_conditions(region_key("city", ["北京市", "北京市", "海淀区"]))
    assert len(conditions) == REGION_FIELDS.index("city") + 1

