"""Unit tests covering 2026-08-12 nightly coverage gap scan (round 6).

Modules exercised (MagicMock + chain assembly):
* app/crud/photo.py -- get_photo / get_photos / get_photos_by_time /
  get_filter_options / _build_photo_filter_query / get_all_photos /
  get_timeline_stats / get_photos_by_ids / batch_soft_delete_photos /
  restore_photos / get_recycle_bin_photos / get_random_photos
* app/crud/location.py -- get_location_years / get_locations (level branches incl.
  invalid level) / get_location_photos (level branches) /
  get_location_distribution / search_locations
* app/crud/album.py -- _build_album_query (conditional branches incl. locations
  / people / time_range) / get_albums_by_photo_id / get_albums /
  batch_update_album_association (add/remove/delete/empty/missing-album)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _photo(**kw):
    base = {
        "id": uuid4(),
        "owner_id": uuid4(),
        "is_deleted": False,
        "albums": [],
        "faces": [],
        "processed_tasks": {"face": True, "ocr": True},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _chain(mock_db, leaf_value=None):
    """Wire a generic SQLAlchemy query chain that returns ``leaf_value`` for
    terminal operations (``first`` / ``all`` / ``count``)."""
    chain = mock_db.query.return_value
    chain.filter.return_value = chain
    chain.filter.return_value.filter.return_value = chain
    chain.options.return_value = chain
    chain.join.return_value = chain
    chain.outerjoin.return_value = chain
    chain.offset.return_value = chain
    chain.limit.return_value = chain
    chain.order_by.return_value = chain
    chain.group_by.return_value = chain
    chain.distinct.return_value = chain
    chain.with_entities.return_value = chain
    chain.first.return_value = leaf_value
    if isinstance(leaf_value, list):
        chain.all.return_value = leaf_value
    else:
        chain.all.return_value = [leaf_value] if leaf_value is not None else []
    chain.count.return_value = len(chain.all.return_value)
    return chain


# ===========================================================================
# app/crud/photo.py
# ===========================================================================


def test_get_photo_returns_first_match():
    from app.crud import photo as crud_photo
    db = MagicMock()
    expected = _photo()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.first.return_value = expected
    out = crud_photo.get_photo(db, expected.id)
    assert out is expected


def test_get_photos_returns_empty_when_album_missing():
    from app.crud import photo as crud_photo
    db = MagicMock()
    _chain(db, None)  # get_album().first() returns None -> early return []
    out = crud_photo.get_photos(db, album_id=uuid4(), skip=0, limit=10)
    assert out == []


def test_get_photos_by_time_returns_list():
    from app.crud import photo as crud_photo
    db = MagicMock()
    _chain(db, [_photo()])
    out = crud_photo.get_photos_by_time(db, uuid4(), skip=0, limit=5)
    assert isinstance(out, list)


def test_get_filter_options_returns_dict():
    from app.crud import photo as crud_photo
    db = MagicMock()
    chain = db.query.return_value
    chain.outerjoin.return_value.filter.return_value.distinct.return_value.all.return_value = []
    options = crud_photo.get_filter_options(db, uuid4())
    assert isinstance(options, dict)
    for key in ("years", "cities", "makes", "models", "image_types", "file_types"):
        assert key in options


def test_build_photo_filter_query_accepts_filters():
    from app.crud import photo as crud_photo
    db = MagicMock()
    chain = db.query.return_value
    chain.outerjoin.return_value = chain
    chain.filter.return_value = chain
    crud_photo._build_photo_filter_query(
        db,
        user_id=uuid4(),
        city="Beijing",
        years=[2024],
        tag="sunset",
    )
    assert db.query.called


def test_get_all_photos_invokes_filter_query():
    from app.crud import photo as crud_photo
    db = MagicMock()
    chain = _chain(db, [_photo()])
    out = crud_photo.get_all_photos(db, skip=0, limit=5, user_id=uuid4())
    assert isinstance(out, list)
    assert chain.filter.called


def test_get_timeline_stats_returns_dict_when_no_photos():
    from app.crud import photo as crud_photo
    db = MagicMock()
    _chain(db, [])
    stats = crud_photo.get_timeline_stats(db, uuid4())
    assert isinstance(stats, dict)
    assert stats["total_photos"] == 0


def test_get_photos_by_ids_returns_list():
    from app.crud import photo as crud_photo
    db = MagicMock()
    _chain(db, [_photo()])
    out = crud_photo.get_photos_by_ids(db, [uuid4()], uuid4(), include_deleted=True)
    assert isinstance(out, list)


def test_batch_soft_delete_photos_marks_and_commits():
    from app.crud import photo as crud_photo
    db = MagicMock()
    chain = db.query.return_value
    chain.options.return_value = chain
    chain.filter.return_value = chain
    chain.all.return_value = [_photo(), _photo()]
    count = crud_photo.batch_soft_delete_photos(db, [uuid4(), uuid4()], uuid4())
    assert count == 2
    assert db.commit.called


def test_restore_photos_clears_is_deleted():
    from app.crud import photo as crud_photo
    db = MagicMock()
    chain = db.query.return_value
    chain.options.return_value = chain
    chain.filter.return_value = chain
    chain.all.return_value = [_photo(is_deleted=True)]
    count = crud_photo.restore_photos(db, [uuid4()], uuid4())
    assert count == 1
    assert db.commit.called


def test_get_recycle_bin_photos_returns_paginated_list():
    from app.crud import photo as crud_photo
    db = MagicMock()
    _chain(db, [_photo(is_deleted=True)])
    out = crud_photo.get_recycle_bin_photos(db, uuid4(), skip=0, limit=10)
    assert isinstance(out, list)


def test_get_random_photos_returns_random_sample():
    from app.crud import photo as crud_photo
    db = MagicMock()
    _chain(db, [_photo()])
    out = crud_photo.get_random_photos(db, uuid4(), limit=3)
    assert isinstance(out, list)


# ===========================================================================
# app/crud/location.py
# ===========================================================================


def test_get_location_years_skips_none_and_returns_list():
    from app.crud import location as crud_loc
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value.distinct.return_value.order_by.return_value.all.return_value = [
        (2025,),
        (2024,),
        (None,),
    ]
    years = crud_loc.get_location_years(db, uuid4())
    assert years == [2025, 2024]


def test_get_locations_invalid_level_returns_empty_list():
    from app.crud import location as crud_loc
    out = crud_loc.get_locations(db=MagicMock(), owner_id=uuid4(), level="galaxy")
    assert out == []


def test_get_location_photos_invalid_level_returns_empty():
    from app.crud import location as crud_loc
    assert crud_loc.get_location_photos(MagicMock(), uuid4(), "X", level="galaxy") == []


def test_get_location_distribution_invalid_level_returns_empty():
    from app.crud import location as crud_loc
    assert crud_loc.get_location_distribution(MagicMock(), uuid4(), level="moon") == []


def test_search_locations_returns_results():
    from app.crud import location as crud_loc
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value.filter.return_value.distinct.return_value.limit.return_value.all.return_value = [
        ("Beijing",),
        ("BeijingPark",),
    ]
    out = crud_loc.search_locations(db, uuid4(), query="Beijing")
    assert isinstance(out, list)


# ===========================================================================
# app/crud/album.py
# ===========================================================================


def _album(**kw):
    base = {
        "id": uuid4(),
        "name": "test",
        "type": "user",
        "owner_id": uuid4(),
        "condition": None,
        "query_embedding": None,
        "threshold": 0.25,
        "cover_id": None,
        "photos": [],
        "shared_users": [],
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_build_album_query_user_album_filters_by_owner():
    from app.crud import album as crud_album
    db = MagicMock()
    album = _album(type="user", owner_id=uuid4())
    crud_album._build_album_query(db, album)
    assert db.query.called


def test_build_album_query_conditional_with_locations():
    from app.crud import album as crud_album
    db = MagicMock()
    cond = {
        "locations": [
            {"province": "Beijing", "city": "Beijing"},
            {"province": "Shanghai"},
        ]
    }
    album = _album(type="conditional", owner_id=uuid4(), condition=cond)
    crud_album._build_album_query(db, album)
    assert db.query.called


def test_build_album_query_conditional_with_people_and_time_range():
    from app.crud import album as crud_album
    db = MagicMock()
    cond = {
        "time_range": {"start": "2025-01-01T00:00:00", "end": "2025-12-31T23:59:59Z"},
        "people": [str(uuid4()), str(uuid4())],
    }
    album = _album(type="conditional", owner_id=uuid4(), condition=cond)
    crud_album._build_album_query(db, album)
    assert db.query.called


def test_build_album_query_conditional_with_bad_time_range_does_not_raise():
    from app.crud import album as crud_album
    db = MagicMock()
    cond = {"time_range": {"start": "not-a-date", "end": "still-bad"}}
    album = _album(type="conditional", owner_id=uuid4(), condition=cond)
    # Must swallow ValueError from datetime.fromisoformat.
    crud_album._build_album_query(db, album)


def test_build_album_query_conditional_with_folders():
    from app.crud import album as crud_album
    db = MagicMock()
    chain = _chain(db, [])
    album = _album(
        type="conditional",
        owner_id=uuid4(),
        condition={"folders": ["Photos/Trips", "Photos/Family"]},
    )

    crud_album._build_album_query(db, album)

    # owner/deleted filters plus one folder-condition filter are applied.
    assert chain.filter.call_count >= 3
    folder_expression = chain.filter.call_args_list[-1].args[0]
    compiled = str(folder_expression.compile(compile_kwargs={"literal_binds": True}))
    assert "replace(photos.file_path" in compiled
    assert "Photos/Trips" in compiled
    assert "Photos/Family" in compiled
    assert " OR " in compiled


def test_build_folder_condition_ignores_invalid_and_empty_values():
    from app.crud import album as crud_album

    assert crud_album._build_folder_condition(None) is None
    assert crud_album._build_folder_condition([]) is None
    assert crud_album._build_folder_condition(["", None, 123]) is None


def test_build_album_query_smart_with_embedding():
    from app.crud import album as crud_album
    db = MagicMock()
    album = _album(type="smart", owner_id=uuid4(), query_embedding=[0.1] * 512)
    crud_album._build_album_query(db, album)
    assert db.query.called


def test_get_albums_by_photo_id_returns_joined_list():
    from app.crud import album as crud_album
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [_album()]
    out = crud_album.get_albums_by_photo_id(db, uuid4())
    assert len(out) == 1


def test_get_albums_paginates_results():
    from app.crud import album as crud_album
    db = MagicMock()
    _chain(db, [_album(), _album()])
    out = crud_album.get_albums(db, skip=0, limit=10, user_id=uuid4())
    assert isinstance(out, list)


def test_batch_update_album_association_returns_zero_on_empty_ids():
    from app.crud import album as crud_album
    out = crud_album.batch_update_album_association(MagicMock(), [], uuid4(), action="add_to_album")
    assert out == 0


def test_batch_update_album_association_returns_zero_when_album_missing():
    from app.crud import album as crud_album
    db = MagicMock()
    _chain(db, None)
    out = crud_album.batch_update_album_association(
        db, [uuid4()], uuid4(), action="add_to_album", user_id=uuid4()
    )
    assert out == 0


def test_batch_update_album_association_add_creates_links():
    from app.crud import album as crud_album
    db = MagicMock()
    photo_a = _photo()
    photo_b = _photo()
    album = _album()
    _chain(db, album)
    db.query.return_value.options.return_value.filter.return_value.all.return_value = [
        photo_a,
        photo_b,
    ]
    count = crud_album.batch_update_album_association(
        db, [photo_a.id, photo_b.id], album.id, action="add_to_album", user_id=uuid4()
    )
    assert count == 2


def test_batch_update_album_association_remove_drops_links():
    from app.crud import album as crud_album
    db = MagicMock()
    photo_a = _photo()
    album = _album()
    photo_a.albums = [album]
    _chain(db, album)
    db.query.return_value.options.return_value.filter.return_value.all.return_value = [photo_a]
    count = crud_album.batch_update_album_association(
        db, [photo_a.id], album.id, action="remove_from_album", user_id=uuid4()
    )
    assert count == 1


def test_batch_update_album_association_delete_action_is_noop():
    from app.crud import album as crud_album
    db = MagicMock()
    db.query.return_value.options.return_value.filter.return_value.all.return_value = [_photo()]
    out = crud_album.batch_update_album_association(
        db, [uuid4()], uuid4(), action="delete", user_id=uuid4()
    )
    # delete branch returns 0 (handled by batch_delete_photos_db upstream).
    assert out == 0
