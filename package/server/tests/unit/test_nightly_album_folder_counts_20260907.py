"""Nightly gap coverage for album folder filtering and bulk recount logic."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

from app.crud import album as album_crud

pytestmark = pytest.mark.smoke


def test_folder_condition_ignores_empty_and_non_string_values():
    assert album_crud._build_folder_condition(None) is None
    assert album_crud._build_folder_condition([]) is None
    assert album_crud._build_folder_condition([None, 123, "   ", "/"]) is None


def test_folder_condition_normalizes_paths_and_escapes_sql_wildcards():
    condition = album_crud._build_folder_condition(
        ["Photos\\Trips 2026", "Photos/Trips 2026", "Photos/100%_old"]
    )
    assert condition is not None

    sqlite = create_engine("sqlite://")
    sql = str(condition.compile(sqlite, compile_kwargs={"literal_binds": True}))
    assert "replace" in sql.lower()
    assert "like" in sql.lower()
    # LIKE wildcards supplied by users must be escaped.
    assert "100\\%\\_old" in sql


def test_update_album_photo_counts_deduplicates_and_recounts_once():
    db = object.__new__(object)
    albums = [
        SimpleNamespace(id="album-1", num_photos=0),
        SimpleNamespace(id="album-2", num_photos=0),
    ]
    query = SimpleNamespace(all=lambda: albums)
    db = SimpleNamespace(
        query=lambda *_args, **_kwargs: SimpleNamespace(
            filter=lambda *_args, **_kwargs: query
        ),
        add=lambda item: None,
        commit=lambda: None,
    )

    with patch.object(album_crud, "_build_album_query", side_effect=lambda _db, album: SimpleNamespace(count=lambda: 3)) as build_query:
        count = album_crud.update_album_photo_counts(db, ["album-2", "album-1", "album-2"])

    assert count == 2
    assert build_query.call_count == 2
    assert all(album.num_photos == 3 for album in albums)


def test_update_album_photo_counts_returns_zero_for_empty_or_unknown_ids():
    db = SimpleNamespace(
        query=lambda *_args, **_kwargs: SimpleNamespace(
            filter=lambda *_args, **_kwargs: SimpleNamespace(all=lambda: [])
        ),
        add=lambda item: None,
        commit=lambda: None,
    )

    assert album_crud.update_album_photo_counts(db, []) == 0
    assert album_crud.update_album_photo_counts(db, None) == 0
    assert album_crud.update_album_photo_counts(db, ["missing"]) == 0
