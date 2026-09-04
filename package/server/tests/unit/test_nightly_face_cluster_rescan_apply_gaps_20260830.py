"""Round 2026-08-30 coverage for app/service/face_cluster.py main rescan flow.

Targets the still-uncovered public/private methods that the 2026-08-19
("test_nightly_face_cluster_gaps_20260819.py") and 2026-08-24
("test_nightly_face_cluster_analyze_gaps_20260826.py") rounds did not
exercise:

* preview_identity_rescan -- happy path + exception rollback branch.
* apply_identity_rescan -- happy path + FaceRescanConflictError
  short-circuit when selected IDs are no longer in the analysis.
* rescan_identity -- happy path + FaceRescanError propagation when
  the inner _analyze_identity_rescan raises.
* _apply_rescan_analysis -- add / remove / reassign accounting plus
  _repair_default_faces invocation.
* assign_face_to_identity -- distance > threshold returning None
  without mutating face state, and the SQLite in-memory branch coverage.
* process_unassigned_faces / _cluster_unassigned_faces -- short
  circuit when fewer than DBSCAN_MIN_SAMPLES unassigned faces exist.

Pattern: MagicMock + SimpleNamespace + tmp_path, no DB / no HTTP. Mirrors
the 2026-08-19 / 2026-08-24 / 2026-08-26 nightly rounds.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _service(db, *, user_id=None):
    from app.service.face_cluster import FaceClusterService

    return FaceClusterService(db=db, user_id=user_id)


def _face(id_, feature, *, identity_id=None, photo_id=None, confidence=None):
    return SimpleNamespace(
        id=id_,
        face_feature=feature,
        face_identity_id=identity_id,
        photo_id=photo_id,
        is_deleted=False,
        is_manually_confirmed=False,
        recognize_confidence=confidence,
    )


def _seed_faces(session, *, reference_features, target_feature):
    """Persist one identity with reference faces plus one unassigned target."""
    from app.db.models.face import Face, FaceIdentity
    from app.db.models.photo import FileType, Photo
    from app.db.models.user import User

    user = User(username="rescan-user", email="rescan@example.com", hashed_password="unused")
    session.add(user)
    session.flush()

    identity = FaceIdentity(identity_name="Known", owner_id=user.id)
    session.add(identity)
    session.flush()

    reference_ids = []
    for index, feature in enumerate(reference_features):
        photo = Photo(
            filename=f"ref{index}.jpg",
            file_path=f"/ref{index}.jpg",
            file_type=FileType.image,
            owner_id=user.id,
        )
        session.add(photo)
        session.flush()
        face = Face(photo_id=photo.id, face_identity_id=identity.id, face_feature=feature)
        session.add(face)
        session.flush()
        reference_ids.append(face.id)

    target_photo = Photo(
        filename="target.jpg",
        file_path="/target.jpg",
        file_type=FileType.image,
        owner_id=user.id,
    )
    session.add(target_photo)
    session.flush()
    target = Face(photo_id=target_photo.id, face_feature=target_feature)
    session.add(target)
    session.commit()

    return {
        "owner_id": user.id,
        "identity_id": identity.id,
        "reference_ids": reference_ids,
        "target_id": target.id,
        "target_feature": target_feature,
    }


def _chain_query(all_value):
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value = q
    q.order_by.return_value = q
    q.with_for_update.return_value = q
    q.all.return_value = all_value
    # The unassigned select is streamed, not materialised with .all().
    q.count.return_value = len(all_value)
    q.yield_per.return_value = all_value
    return q


def _analysis(*, identity_id="ident-1", add=None, remove=None, prototypes=None, owner_id=None):
    return {
        "identity_id": identity_id,
        "owner_id": owner_id,
        "reason": None,
        "prototypes": prototypes or [],
        "add_candidates": add or [],
        "remove_candidates": remove or [],
        "removal_threshold": 0.42,
    }


# ---------------------------------------------------------------------------
# preview_identity_rescan
# ---------------------------------------------------------------------------


def test_preview_identity_rescan_returns_serialized_preview_on_success():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    db.query.return_value = _chain_query([])

    preview = {
        "status": "success",
        "reason": None,
        "add_candidates": [],
        "remove_candidates": [],
    }

    svc = _service(db)
    with patch.object(svc, "_analyze_identity_rescan", return_value=_analysis()), \
         patch.object(svc, "_serialize_rescan_preview", return_value=preview) as serialize_spy:
        out = svc.preview_identity_rescan("ident-1", owner_id=None)

    assert out is preview
    assert serialize_spy.call_count == 1


def test_preview_identity_rescan_raises_face_rescan_error_and_rolls_back():
    from app.service.face_cluster import FaceRescanError

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    boom = RuntimeError("simulated analyze failure")
    with patch.object(svc, "_analyze_identity_rescan", side_effect=boom):
        with pytest.raises(FaceRescanError) as exc_info:
            svc.preview_identity_rescan("ident-1", owner_id=None)

    assert exc_info.value.__cause__ is boom
    db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# apply_identity_rescan
# ---------------------------------------------------------------------------


def test_apply_identity_rescan_happy_path_routes_through_apply_helper():
    add_face = _face(11, np.array([1.0, 0.0]), photo_id="p-1")
    remove_face = _face(22, np.array([-1.0, 0.0]), photo_id="p-2")

    analysis = _analysis(
        identity_id="ident-1",
        add=[{"face": add_face, "distance": 0.1}],
        remove=[{"face": remove_face, "distance": 0.5}],
        prototypes=[np.array([1.0, 0.0])],
    )
    expected = {"status": "success", "added_count": 1, "removed_count": 1}

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    with patch.object(svc, "_analyze_identity_rescan", return_value=analysis) as analyze_spy, \
         patch.object(svc, "_apply_rescan_analysis", return_value=expected) as apply_spy:
        out = svc.apply_identity_rescan(
            "ident-1",
            owner_id=None,
            add_face_ids=[11],
            remove_face_ids=[22],
        )

    assert out is expected
    analyze_spy.assert_called_once_with("ident-1", None, lock=True)
    apply_spy.assert_called_once_with(analysis, {11}, {22})
    # No conflict raised -> rollback should not be called.
    db.rollback.assert_not_called()


def test_apply_identity_rescan_raises_conflict_when_selected_face_not_in_analysis():
    from app.service.face_cluster import FaceRescanConflictError

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    analysis = _analysis(
        identity_id="ident-1",
        add=[],
        remove=[],
    )

    svc = _service(db)
    with patch.object(svc, "_analyze_identity_rescan", return_value=analysis):
        with pytest.raises(FaceRescanConflictError):
            svc.apply_identity_rescan(
                "ident-1",
                owner_id=None,
                add_face_ids=[999],  # not in analysis.add_candidates
                remove_face_ids=[],
            )

    db.rollback.assert_called_once()


def test_apply_identity_rescan_wraps_unexpected_errors_as_face_rescan_error():
    from app.service.face_cluster import FaceRescanError

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    boom = RuntimeError("apply blew up")
    with patch.object(svc, "_analyze_identity_rescan", return_value=_analysis()), \
         patch.object(svc, "_apply_rescan_analysis", side_effect=boom):
        with pytest.raises(FaceRescanError):
            svc.apply_identity_rescan(
                "ident-1",
                owner_id=None,
                add_face_ids=[],
                remove_face_ids=[],
            )

    db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# rescan_identity (auto selection)
# ---------------------------------------------------------------------------


def test_rescan_identity_auto_selects_high_confidence_adds_and_all_removals():
    # RESCAN_AUTO_MATCH_THRESHOLD defaults to 0.35, so 0.20 qualifies but 0.40 does not.
    add_face_low = _face(11, np.array([1.0, 0.0]), photo_id="p-1")
    add_face_high = _face(12, np.array([1.0, 0.0]), photo_id="p-2")
    remove_face = _face(22, np.array([-1.0, 0.0]), photo_id="p-3")

    analysis = _analysis(
        identity_id="ident-1",
        add=[
            {"face": add_face_low, "distance": 0.40},  # > auto threshold (0.35)
            {"face": add_face_high, "distance": 0.20},  # <= auto threshold
        ],
        remove=[{"face": remove_face, "distance": 0.6}],
    )
    expected = {"status": "success", "added_count": 1, "removed_count": 1}

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    auto_threshold = svc.RESCAN_AUTO_MATCH_THRESHOLD
    # Both test distances must straddle the threshold so the auto-selection is meaningful.
    assert 0.20 <= auto_threshold < 0.40

    with patch.object(svc, "_analyze_identity_rescan", return_value=analysis), \
         patch.object(svc, "_apply_rescan_analysis", return_value=expected) as apply_spy:
        out = svc.rescan_identity("ident-1", owner_id=None)

    assert out is expected
    apply_spy.assert_called_once_with(analysis, {12}, {22})


def test_rescan_identity_propagates_face_rescan_error_without_double_wrap():
    from app.service.face_cluster import FaceRescanError

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    inner = FaceRescanError("inner")
    with patch.object(svc, "_analyze_identity_rescan", side_effect=inner):
        with pytest.raises(FaceRescanError) as exc_info:
            svc.rescan_identity("ident-1", owner_id=None)

    assert exc_info.value is inner
    db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# _apply_rescan_analysis
# ---------------------------------------------------------------------------


def test_apply_rescan_analysis_adds_remove_and_reassigns_affecting_two_identities():
    add_face_fresh = _face(2, np.array([1.0, 0.0]), photo_id="p-fresh", identity_id=None)
    add_face_reassign = _face(
        3,
        np.array([1.0, 0.0]),
        photo_id="p-reassign",
        identity_id="other-ident",
    )
    remove_face = _face(4, np.array([-1.0, 0.0]), photo_id="p-remove")

    analysis = {
        "identity_id": "ident-1",
        "owner_id": None,
        "prototypes": [np.array([1.0, 0.0])],
        "add_candidates": [
            {"face": add_face_fresh, "distance": 0.10},
            {"face": add_face_reassign, "distance": 0.20},
        ],
        "remove_candidates": [{"face": remove_face, "distance": 0.55}],
        "removal_threshold": 0.42,
    }

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    with patch.object(svc, "_repair_default_faces") as repair_spy:
        result = svc._apply_rescan_analysis(analysis, {2, 3}, {4})

    # add_face_reassign gets reassigned into identity-1 (different prior identity)
    assert add_face_reassign.face_identity_id == "ident-1"
    assert add_face_reassign.recognize_confidence == pytest.approx(0.8)

    # add_face_fresh now attached to identity-1
    assert add_face_fresh.face_identity_id == "ident-1"

    # remove_face cleared
    assert remove_face.face_identity_id is None
    assert remove_face.recognize_confidence is None

    db.flush.assert_called_once()
    repair_spy.assert_called_once()
    assert "ident-1" in repair_spy.call_args.args[0]
    assert "other-ident" in repair_spy.call_args.args[0]

    assert result["added_count"] == 2
    assert result["removed_count"] == 1
    assert result["reassigned_count"] == 1
    assert sorted(result["affected_photo_ids"]) == ["p-fresh", "p-reassign", "p-remove"]


def test_apply_rescan_analysis_no_op_when_no_ids_selected():
    face_a = _face(11, np.array([1.0, 0.0]), photo_id="p-a", identity_id="ident-1")
    face_b = _face(22, np.array([-1.0, 0.0]), photo_id="p-b")

    analysis = {
        "identity_id": "ident-1",
        "owner_id": None,
        "prototypes": [np.array([1.0, 0.0])],
        "add_candidates": [{"face": face_b, "distance": 0.1}],
        "remove_candidates": [{"face": face_a, "distance": 0.6}],
        "removal_threshold": 0.42,
    }

    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    with patch.object(svc, "_repair_default_faces") as repair_spy:
        result = svc._apply_rescan_analysis(analysis, set(), set())

    # Without selection, faces are not mutated.
    assert face_a.face_identity_id == "ident-1"
    assert face_b.face_identity_id is None

    db.flush.assert_called_once()
    repair_spy.assert_called_once_with({"ident-1"})
    assert result["added_count"] == 0
    assert result["removed_count"] == 0
    assert result["reassigned_count"] == 0


# ---------------------------------------------------------------------------
# assign_face_to_identity
# ---------------------------------------------------------------------------


def test_assign_face_to_identity_returns_none_when_distance_above_threshold(face_sqlite_session):
    """An orthogonal reference face is far beyond the threshold -> no assignment."""
    from app.service import face_cluster

    fixture = _seed_faces(
        face_sqlite_session,
        reference_features=[[0.0, 1.0] + [0.0] * 510],
        target_feature=[1.0, 0.0] + [0.0] * 510,
    )

    identity_cfg = MagicMock()
    identity_cfg.ai.face_cluster_threshold = 0.35

    svc = face_cluster.FaceClusterService(db=face_sqlite_session, user_id=None)
    with patch(
        "app.service.face_cluster.config_manager.get_user_config",
        return_value=identity_cfg,
    ), patch("app.service.face_cluster.crud_face.update_face") as update_spy:
        result = svc.assign_face_to_identity(
            face_id=fixture["target_id"],
            embedding=fixture["target_feature"],
            owner_id=fixture["owner_id"],
        )

    assert result is None
    update_spy.assert_not_called()


def test_assign_face_to_identity_sqlite_branch_skips_pgvector_order_by(face_sqlite_session):
    """SQLite must resolve the nearest neighbour without pgvector's <=> operator.

    Running against a real SQLite engine is the assertion: emitting the
    pgvector operator here would raise an OperationalError.
    """
    from app.service import face_cluster

    fixture = _seed_faces(
        face_sqlite_session,
        reference_features=[[1.0, 0.0] + [0.0] * 510],
        target_feature=[1.0, 0.0] + [0.0] * 510,
    )

    identity_cfg = MagicMock()
    identity_cfg.ai.face_cluster_threshold = 0.5

    svc = face_cluster.FaceClusterService(db=face_sqlite_session, user_id=None)
    with patch(
        "app.service.face_cluster.config_manager.get_user_config",
        return_value=identity_cfg,
    ), patch("app.service.face_cluster.crud_face.update_face") as update_spy:
        result = svc.assign_face_to_identity(
            face_id=fixture["target_id"],
            embedding=fixture["target_feature"],
            owner_id=fixture["owner_id"],
        )

    assert result == fixture["identity_id"]
    update_spy.assert_called_once()


# ---------------------------------------------------------------------------
# process_unassigned_faces / _cluster_unassigned_faces
# ---------------------------------------------------------------------------


def test_cluster_unassigned_faces_short_circuits_when_below_min_samples():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    # Return only 2 faces (less than DBSCAN_MIN_SAMPLES=5 default).
    db.query.return_value = _chain_query([
        _face(1, np.array([1.0, 0.0])),
        _face(2, np.array([0.0, 1.0])),
    ])

    svc = _service(db)
    # Should return without invoking DBSCAN (no exception).
    with patch("app.service.face_cluster.DBSCAN") as dbscan_spy:
        result = svc._cluster_unassigned_faces(owner_id=None)

    assert result is None
    dbscan_spy.assert_not_called()


def test_process_unassigned_faces_delegates_to_cluster_helper():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    svc = _service(db)
    with patch.object(svc, "_cluster_unassigned_faces") as cluster_spy:
        svc.process_unassigned_faces(owner_id="owner-1")

    cluster_spy.assert_called_once_with("owner-1")
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import numpy as np
import pytest
