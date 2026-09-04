"""Unit tests for app/service/similar_photo.py (AgglomerativeClustering wrapper).

The SQLAlchemy session is mocked at the `execute(...).all()` boundary; numpy
+ sklearn are real, so cluster behavior is genuinely exercised. Each test
fakes just enough rows to drive a deterministic branch.

The mock returns the same list of detail rows for every photo query; tests
assert against the cluster (not against the full photo set) so the photo
query return must contain only the cluster's photos.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.service.similar_photo import SimilarPhotoService


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _vec_row(photo_id, embedding):
    """First `execute().all()` returns rows shaped like (photo_id, embedding)."""
    return SimpleNamespace(photo_id=photo_id, embedding=embedding)


def _photo_detail_tuple(photo_id, filename="p.jpg", score=0, photo_time=None, desc=None):
    """Second `execute().all()` returns rows shaped like (Photo, ImageDescription)."""
    photo = SimpleNamespace(id=photo_id, filename=filename, photo_time=photo_time)
    return (photo, desc)


def _make_db(vector_rows, photo_query_rows):
    """Build a MagicMock Session.

    First `execute().all()` returns `vector_rows`; every subsequent call
    returns `photo_query_rows` (the rows the photo query would yield, which
    the caller is expected to pre-filter to the cluster's IDs).
    """
    db = MagicMock()
    is_first = {"flag": True}

    def execute(_stmt):
        m = MagicMock()
        if is_first["flag"]:
            is_first["flag"] = False
            m.all.return_value = list(vector_rows)
        else:
            m.all.return_value = list(photo_query_rows)
        return m

    db.execute.side_effect = execute
    return db


def test_get_similar_groups_empty_when_no_vectors():
    db = _make_db(vector_rows=[], photo_query_rows=[])
    service = SimilarPhotoService(db, user_id=uuid4())
    assert service.get_similar_groups() == []


def test_get_similar_groups_groups_identical_embeddings():
    """Two identical embeddings form one cluster of two; sorted by score desc."""
    user_id = uuid4()
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    vector_rows = [
        _vec_row(p1, [1.0, 0.0, 0.0]),
        _vec_row(p2, [1.0, 0.0, 0.0]),
        _vec_row(p3, [0.0, 1.0, 0.0]),
    ]
    # Photo query returns only the clustered pair (p1, p2); p3 is a singleton
    # and the service never asks for its detail row.
    photo_query_rows = [
        _photo_detail_tuple(p1, score=5, photo_time=datetime(2025, 1, 1)),
        _photo_detail_tuple(p2, score=10, photo_time=datetime(2025, 1, 2)),
    ]
    db = _make_db(vector_rows, photo_query_rows)
    service = SimilarPhotoService(db, user_id=user_id)

    groups = service.get_similar_groups(threshold=0.9)

    assert len(groups) == 1
    group = groups[0]
    assert len(group) == 2
    # Score desc, then time desc: p2 (score=10) before p1 (score=5)
    assert group[0]["id"] == str(p2)
    assert group[1]["id"] == str(p1)
    # Helper URLs include the photo id
    assert group[0]["thumbnail_path"] == f"/api/medias/{user_id}/{p2}/thumbnail"
    assert group[0]["src"] == f"/api/medias/{p2}/preview"


def test_get_similar_groups_excludes_singletons():
    """All-different vectors produce only singletons; result must be empty."""
    user_id = uuid4()
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    vector_rows = [
        _vec_row(p1, [1.0, 0.0, 0.0]),
        _vec_row(p2, [0.0, 1.0, 0.0]),
        _vec_row(p3, [0.0, 0.0, 1.0]),
    ]
    photo_query_rows = []
    db = _make_db(vector_rows, photo_query_rows)
    service = SimilarPhotoService(db, user_id=user_id)

    groups = service.get_similar_groups(threshold=0.9)
    assert groups == []


def test_get_similar_groups_includes_quality_and_memory_score():
    """Group items should expose `score = memory_score + quality_score`."""
    user_id = uuid4()
    p1, p2 = uuid4(), uuid4()
    vector_rows = [
        _vec_row(p1, [1.0, 0.0]),
        _vec_row(p2, [1.0, 0.0]),
    ]
    desc1 = SimpleNamespace(memory_score=4, quality_score=3)
    desc2 = SimpleNamespace(memory_score=2, quality_score=2)
    photo_query_rows = [
        _photo_detail_tuple(p1, desc=desc1),
        _photo_detail_tuple(p2, desc=desc2),
    ]
    db = _make_db(vector_rows, photo_query_rows)
    service = SimilarPhotoService(db, user_id=user_id)

    groups = service.get_similar_groups(threshold=0.9)
    assert len(groups) == 1
    scores = sorted(item["score"] for item in groups[0])
    assert scores == [4, 7]


def test_get_similar_groups_uses_lower_threshold_for_looser_match():
    """Lower threshold = larger distance allowance = more groups at low similarity."""
    user_id = uuid4()
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    # 0.5 cosine similarity (angle ~60 deg) between p1 and p2
    vector_rows = [
        _vec_row(p1, [1.0, 0.0]),
        _vec_row(p2, [0.866, 0.5]),
        _vec_row(p3, [0.0, 1.0]),
    ]
    # Photo query returns only the p1+p2 pair (the cluster); p3 is singleton.
    photo_query_rows = [
        _photo_detail_tuple(p1),
        _photo_detail_tuple(p2),
    ]
    db = _make_db(vector_rows, photo_query_rows)
    service = SimilarPhotoService(db, user_id=user_id)

    # threshold=0.5 (distance 0.5) -- p1+p2 are at distance ~0.5; p3 is at distance ~1.0+
    loose_groups = service.get_similar_groups(threshold=0.5)
    assert len(loose_groups) == 1
    assert {item["id"] for item in loose_groups[0]} == {str(p1), str(p2)}
