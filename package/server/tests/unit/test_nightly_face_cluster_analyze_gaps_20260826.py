"""Round 2026-08-26 coverage for app/service/face_cluster.py analyze_identity_rescan."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


pytestmark = [pytest.mark.smoke]


def _service(db):
    from app.service.face_cluster import FaceClusterService

    return FaceClusterService(db=db, user_id=None)


def _face(id_, feature):
    return SimpleNamespace(
        id=id_,
        face_feature=feature,
        is_deleted=False,
        is_manually_confirmed=False,
        recognize_confidence=None,
    )


def _chain_query(all_value):
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value = q
    q.order_by.return_value = q
    q.with_for_update.return_value = q
    q.all.return_value = all_value
    return q


def test_analyze_identity_rescan_returns_no_reference_faces_summary_when_empty():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    db.query.return_value = _chain_query([])

    svc = _service(db)
    identity_id = "ident-1"
    summary = svc._analyze_identity_rescan(identity_id, owner_id=None, lock=False)

    assert summary["identity_id"] == identity_id
    assert summary["reason"] == "no_reference_faces"
    assert summary["prototypes"] == []
    assert summary["add_candidates"] == []
    assert summary["remove_candidates"] == []
    assert summary["removal_threshold"] == svc.RESCAN_REMOVAL_THRESHOLD


def test_analyze_identity_rescan_no_remove_candidates_when_under_threshold():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    faces = [
        _face(101, np.array([1.0, 0.0, 0.0])),
        _face(102, np.array([1.0, 0.0, 0.0])),
    ]
    db.query.return_value = _chain_query(faces)

    identity = SimpleNamespace(default_face_id=None)

    with patch("app.service.face_cluster.crud_face.get_identity", return_value=identity):
        svc = _service(db)
        out = svc._analyze_identity_rescan("ident-2", owner_id=None, lock=False)

    assert out["remove_candidates"] == []
    assert isinstance(out["prototypes"], list)


def test_analyze_identity_rescan_with_owner_id_adds_extra_filter():
    """owner_id set -> the query gains an extra ``.filter(Photo.owner_id == ...)``."""
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    q = _chain_query([])
    db.query.return_value = q

    svc = _service(db)
    # Baseline: no owner_id -> 1 filter call.
    svc._analyze_identity_rescan("ident-3", owner_id=None, lock=False)
    baseline = q.filter.call_count
    # With owner_id -> the owner branch adds exactly one extra filter.
    svc._analyze_identity_rescan("ident-4", owner_id="owner-xyz", lock=False)
    delta = q.filter.call_count - baseline
    # Filter by owner_id adds at least one extra filter call.
    assert delta >= 1
