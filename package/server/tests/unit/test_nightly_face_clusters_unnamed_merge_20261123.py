"""Nightly gap coverage: automatic unnamed identity reconciliation.

`_merge_unnamed_identities` groups the automatic "未命名" identities of one
owner and merges the ones that describe the same person.  The cheap guard
(less than two unnamed identities) must short-circuit before any vector work
is done, so it is asserted here with a real SQLite session.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.face import FaceCluster, FaceIdentity
from app.service import face_appearance_clusters as clusters


pytestmark = pytest.mark.smoke


def _config():
    return SimpleNamespace(
        face_cluster_threshold=0.5,
        face_identity_merge_threshold=0.4,
        face_identity_match_threshold=0.85,
    )


def _add_unnamed_cluster(db, owner_id, name="未命名"):
    identity = FaceIdentity(owner_id=owner_id, identity_name=name)
    db.add(identity)
    db.flush()
    vector = [0.0] * 512
    db.add(
        FaceCluster(
            owner_id=owner_id,
            identity_id=identity.id,
            center=vector,
            vector_sum=vector,
            face_count=1,
            status="active",
        )
    )
    db.commit()
    return identity


def test_single_unnamed_identity_is_left_alone(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    _add_unnamed_cluster(db, owner_id)

    assert clusters._merge_unnamed_identities(db, owner_id, _config()) == 0


def test_named_identities_are_not_merged(face_sqlite_session):
    """Only automatic "未命名" identities take part in the reconciliation."""
    db = face_sqlite_session
    owner_id = uuid4()
    _add_unnamed_cluster(db, owner_id, name="张三")
    _add_unnamed_cluster(db, owner_id, name="李四")

    assert clusters._merge_unnamed_identities(db, owner_id, _config()) == 0


def test_unnamed_identities_of_another_owner_are_ignored(face_sqlite_session):
    db = face_sqlite_session
    owner_id = uuid4()
    other_owner = uuid4()
    _add_unnamed_cluster(db, owner_id)
    _add_unnamed_cluster(db, other_owner)

    assert clusters._merge_unnamed_identities(db, owner_id, _config()) == 0
