"""夜间盲区补测：相似人脸的身份归属校验。

覆盖 app/service/similar_faces.py 的 ``_owned_identity``
（此前未被任何单测按名引用）。
"""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.face import FaceIdentity
from app.service import similar_faces

pytestmark = [pytest.mark.smoke, pytest.mark.regression]


def _db_returning(identity):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = identity
    return db


def test_owned_identity_returns_matching_identity():
    """查到身份时应原样返回，供后续相似度计算使用。"""
    identity = FaceIdentity(id=uuid4(), owner_id=uuid4(), identity_name="小明")
    db = _db_returning(identity)

    result = similar_faces._owned_identity(db, identity.id, uuid4())

    assert result is identity
    assert db.query.call_args.args == (FaceIdentity,)


def test_owned_identity_rejects_missing_identity():
    """身份不存在时必须抛 404，不得继续计算相似度。"""
    db = _db_returning(None)

    with pytest.raises(HTTPException) as excinfo:
        similar_faces._owned_identity(db, uuid4(), uuid4())

    assert excinfo.value.status_code == 404
