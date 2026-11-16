"""2026-11-16 nightly coverage for ``app/crud/metadata_search.py``.

The 2026-11-16 backend coverage scan reported ``crud/metadata_search.py``
at 95.7% with 2 missed lines: the "empty search text" guard (line 48)
and the "unknown search type" fallback (line 64).

Both branches must compile to an always-false predicate so that a photo
search never silently returns the whole library.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import sqlite

from app.crud.metadata_search import apply_metadata_search
from app.db.models.photo import Photo


pytestmark = [pytest.mark.smoke, pytest.mark.module_search]


def _sql(query) -> str:
    return str(query.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))


def test_an_empty_search_text_matches_nothing():
    query = apply_metadata_search(select(Photo), "album", "")
    assert "0 = 1" in _sql(query)


def test_an_unknown_search_type_matches_nothing():
    query = apply_metadata_search(select(Photo), "nonsense", "value")
    assert "0 = 1" in _sql(query)


def test_a_known_search_type_without_a_value_keeps_the_query_open():
    query = apply_metadata_search(select(Photo), "location", "")
    assert "0 = 1" not in _sql(query)


def test_the_album_search_type_filters_by_name():
    query = apply_metadata_search(select(Photo), "album", "旅行")
    sql = _sql(query)
    assert "0 = 1" not in sql
    assert "album" in sql.lower()
