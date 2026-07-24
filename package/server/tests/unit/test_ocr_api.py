"""Unit tests for the OCR REST router (app/api/ocr.py).

Covers the two endpoints that wrap a thin CRUD layer:

- GET /ocr?photo_id=...     -- returns a BaseResponse with count and the records.
- DELETE /ocr/{photo_id}   -- clears photo.processed_tasks["ocr"] and deletes rows.

We patch ``app.crud.ocr`` and the ``Photo`` model directly so we do not need
a real Postgres / vector store.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import ocr as ocr_api
from app.crud import ocr as ocr_crud


pytestmark = [pytest.mark.smoke, pytest.mark.module_ocr]


def _record(text="hello", score=0.9):
    return SimpleNamespace(text=text, text_score=score, polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])


# ------------------------------- GET /ocr --------------------------------


def test_get_ocr_records_returns_count_and_records():
    photo_id = uuid4()
    db = MagicMock()
    rows = [_record("hello"), _record("world", 0.8)]

    with patch.object(ocr_crud, "get_ocr_by_photo_id", return_value=rows) as get_call:
        response = ocr_api.get_ocr_records(photo_id=photo_id, db=db)

    get_call.assert_called_once_with(db, photo_id)
    assert response.code == 200
    assert response.msg == ""
    assert response.data["count"] == 2
    assert response.data["records"] is rows


def test_get_ocr_records_empty_list_returns_zero_count():
    photo_id = uuid4()
    db = MagicMock()

    with patch.object(ocr_crud, "get_ocr_by_photo_id", return_value=[]):
        response = ocr_api.get_ocr_records(photo_id=photo_id, db=db)

    assert response.code == 200
    assert response.data["count"] == 0
    assert response.data["records"] == []


# ----------------------------- DELETE /ocr -------------------------------


def test_delete_ocr_records_clears_processed_tasks_flag():
    photo_id = uuid4()
    db = MagicMock()

    photo = MagicMock()
    photo.processed_tasks = {"ocr": True, "face": True}
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch.object(ocr_crud, "delete_ocr_by_photo_id", return_value=3) as delete_call:
        response = ocr_api.delete_ocr_records(photo_id=photo_id, db=db)

    delete_call.assert_called_once_with(db, photo_id)
    assert photo.processed_tasks == {"ocr": False, "face": True}
    db.add.assert_called_once_with(photo)
    assert response.code == 200
    assert response.data["deleted_count"] == 3


def test_delete_ocr_records_without_photo_skips_task_update():
    photo_id = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(ocr_crud, "delete_ocr_by_photo_id", return_value=0) as delete_call:
        response = ocr_api.delete_ocr_records(photo_id=photo_id, db=db)

    delete_call.assert_called_once_with(db, photo_id)
    db.add.assert_not_called()
    assert response.data["deleted_count"] == 0


def test_delete_ocr_records_without_processed_tasks_skips_flag_update():
    photo_id = uuid4()
    db = MagicMock()

    photo = MagicMock()
    photo.processed_tasks = None
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch.object(ocr_crud, "delete_ocr_by_photo_id", return_value=1) as delete_call:
        response = ocr_api.delete_ocr_records(photo_id=photo_id, db=db)

    delete_call.assert_called_once_with(db, photo_id)
    # processed_tasks is None - we should not try to mutate it.
    db.add.assert_not_called()
    assert response.data["deleted_count"] == 1


def test_delete_ocr_records_when_ocr_key_missing_leaves_dict_alone():
    photo_id = uuid4()
    db = MagicMock()

    photo = MagicMock()
    photo.processed_tasks = {"face": False}
    db.query.return_value.filter.return_value.first.return_value = photo

    with patch.object(ocr_crud, "delete_ocr_by_photo_id", return_value=2) as delete_call:
        ocr_api.delete_ocr_records(photo_id=photo_id, db=db)

    delete_call.assert_called_once_with(db, photo_id)
    # 'ocr' key absent -> dict stays untouched, no db.add call needed.
    assert photo.processed_tasks == {"face": False}
    db.add.assert_not_called()
