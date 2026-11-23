"""Query guards for the swipe-filter "still available" photo selection."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.crud.swipe_filter import _available_query
from app.db.models.photo import Photo
from app.db.models.photo_declutter_record import PhotoDeclutterRecord

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _db_with_two_queries(handled):
    db = MagicMock()
    record_chain = MagicMock()
    record_chain.filter.return_value = handled
    photo_chain = MagicMock()
    db.query.side_effect = [record_chain, photo_chain]
    return db, photo_chain


def test_available_query_selects_handled_photos_first():
    handled = select(PhotoDeclutterRecord.photo_id)
    db, _ = _db_with_two_queries(handled)
    _available_query(db, uuid4())
    assert db.query.call_args_list[0].args == (PhotoDeclutterRecord.photo_id,)


def test_available_query_excludes_already_handled_photos():
    handled = select(PhotoDeclutterRecord.photo_id)
    db, photo_chain = _db_with_two_queries(handled)
    result = _available_query(db, uuid4())
    assert result is photo_chain.filter.return_value
    assert db.query.call_args_list[1].args == (Photo,)


def test_available_query_injects_handled_ids_subquery_into_filter():
    handled = select(PhotoDeclutterRecord.photo_id)
    db, photo_chain = _db_with_two_queries(handled)
    _available_query(db, uuid4())
    rendered = " ".join(str(arg) for arg in photo_chain.filter.call_args.args)
    assert "SELECT" in rendered.upper()
    assert "NOT" in rendered.upper()


def test_available_query_scopes_rows_to_owner_and_live_photos():
    handled = select(PhotoDeclutterRecord.photo_id)
    db, photo_chain = _db_with_two_queries(handled)
    owner_id = uuid4()
    _available_query(db, owner_id)
    rendered = " ".join(str(arg) for arg in photo_chain.filter.call_args.args)
    assert "owner_id" in rendered
    assert "is_deleted" in rendered

