"""Unit tests for the search REST router (app/api/search.py).

Covers the suggestion aggregator and the metadata / vector text-search
paths. The vector path is exercised by patching ``async_get_embedding``
and ``crud_vector.search_similar_vectors`` so no real AI service or
Postgres is required.

Photo stubs satisfy the ``Photo`` schema (``file_type`` / ``size`` /
``id`` / ``file_path`` / ``upload_time``) so the ``SearchResult`` model
validation passes end-to-end.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import search as search_api
from app.db.models.photo import FileType


pytestmark = [pytest.mark.smoke, pytest.mark.module_search]


def _user():
    return SimpleNamespace(id=uuid4())


def _photo(pid=None):
    """Build a SimpleNamespace that validates against the Photo schema."""
    pid = pid or uuid4()
    return SimpleNamespace(
        id=pid,
        file_type=FileType.image,
        size=1024,
        width=800,
        height=600,
        filename="a.jpg",
        photo_time=datetime(2026, 1, 1),
        md5="x",
        file_path="/Photos/a.jpg",
        upload_time=datetime(2026, 1, 1),
        photo_id=pid,
    )


def _build_chain(per_call_values):
    """Self-referencing chain. ``.all()`` returns the next value per call.

    ``per_call_values`` is a list; each ``.all()`` consumes the next entry.
    """
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.join.return_value = chain
    chain.limit.return_value = chain
    chain.offset.return_value = chain
    chain.all.side_effect = per_call_values
    return chain


def _static_chain(return_value):
    """Self-referencing chain whose ``.all()`` always returns ``return_value``."""
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.join.return_value = chain
    chain.limit.return_value = chain
    chain.offset.return_value = chain
    chain.all.return_value = return_value
    return chain


# ------------------------- GET /search/suggestions --------------------


@pytest.mark.asyncio
async def test_suggestions_returns_top_20_across_all_sources():
    user = _user()
    db = MagicMock()
    # Each suggestion source triggers a chain ending with .all(). The
    # router makes 11 such calls in this order.
    db.query.return_value = _build_chain([
        [("Alice",)],                                # 1. persons
        [("Beijing",)],                              # 2. city
        [("China",)],                                # 3. country
        [("Hubei",)],                                # 4. province
        [("Wuhan",)],                                # 5. district
        [("OCR snippet",)],                          # 6. ocr
        [("Vacation 2025",)],                        # 7. album
        [("IMG_0001.jpg",)],                         # 8. filename
        [("D:/Photos/q-folder/IMG_001.jpg",)],       # 9. folder paths
        [("beach",)],                                # 10. tag
        [("mountain",)],                             # 11. scene
    ])

    response = await search_api.get_search_suggestions(q="q", db=db, user=user)

    assert response.code == 200
    types = {s.type for s in response.data}
    expected = {"person", "location", "ocr", "album", "filename", "folder", "tag", "scene"}
    assert expected.issubset(types)
    assert len(response.data) <= 20


@pytest.mark.asyncio
async def test_suggestions_returns_500_on_db_exception():
    user = _user()
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")

    with pytest.raises(HTTPException) as exc_info:
        await search_api.get_search_suggestions(q="q", db=db, user=user)

    assert exc_info.value.status_code == 500
    assert "db down" in str(exc_info.value.detail)


# ------------------------- POST /search/text --------------------------


@pytest.mark.asyncio
async def test_text_search_metadata_type_uses_query_chain_and_score_one():
    user = _user()
    db = MagicMock()
    photos = [_photo(), _photo()]

    db.query.return_value = _static_chain(photos)

    request = search_api.TextSearchRequest(text="abc", type="filename", limit=10, skip=0)

    response = await search_api.search_by_text(request=request, db=db, user=user)

    assert response.code == 200
    assert len(response.data) == 2
    assert all(item.score == 1.0 for item in response.data)


@pytest.mark.asyncio
async def test_text_search_vector_path_applies_threshold_filter():
    user = _user()
    db = MagicMock()
    keep = _photo()
    drop = _photo()
    # threshold=0.5 -> keep 1-0.3=0.7, drop 1-0.9=0.1
    results = [(keep, 0.3), (drop, 0.9)]

    async def _ok_embed(*args, **kwargs):
        return [0.1, 0.2]

    with patch.object(search_api, "async_get_embedding", new=_ok_embed):
        with patch.object(search_api.crud_vector, "search_similar_vectors", return_value=results):
            with patch.object(
                search_api.app.crud.photo,
                "get_photos_by_ids",
                return_value=[keep, drop],
            ):
                request = search_api.TextSearchRequest(text="hello", type=None, threshold=0.5)
                response = await search_api.search_by_text(request=request, db=db, user=user)

    assert response.code == 200
    assert len(response.data) == 1
    assert response.data[0].photo.id == keep.id
    assert response.data[0].score == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_text_search_vector_path_returns_empty_when_below_threshold():
    user = _user()
    db = MagicMock()
    v = _photo()

    async def _ok_embed(*args, **kwargs):
        return [0.0]

    with patch.object(search_api, "async_get_embedding", new=_ok_embed):
        with patch.object(search_api.crud_vector, "search_similar_vectors", return_value=[(v, 0.99)]):
            with patch.object(search_api.app.crud.photo, "get_photos_by_ids", return_value=[v]):
                request = search_api.TextSearchRequest(text="x", threshold=0.5)
                response = await search_api.search_by_text(request=request, db=db, user=user)

    assert response.code == 200
    assert response.data == []


# ------------------------- _build_vector_search_response -------------


def test_build_vector_search_response_drops_missing_photos():
    pid_keep = uuid4()
    pid_drop = uuid4()
    keep = SimpleNamespace(photo_id=pid_keep)
    drop = SimpleNamespace(photo_id=pid_drop)

    with patch.object(
        search_api.app.crud.photo,
        "get_photos_by_ids",
        return_value=[_photo(pid_keep)],
    ):
        results = search_api._build_vector_search_response(
            None, [(keep, 0.0), (drop, 0.0)], threshold=0.0,
        )

    assert len(results) == 1
    assert results[0].photo.id == pid_keep
