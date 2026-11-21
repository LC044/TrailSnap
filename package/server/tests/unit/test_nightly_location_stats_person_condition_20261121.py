"""夜间盲区补测：人物照片 EXISTS 条件的构造。

覆盖 app/crud/location_stats.py 的 ``person_photo_condition``
（此前未被任何单测按名引用）。
"""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.crud import location_stats
from app.db.models.face import Face, FaceIdentity

pytestmark = [pytest.mark.smoke, pytest.mark.regression]


def test_person_photo_condition_builds_exists_clause():
    """必须构造 EXISTS 子查询，并同时过滤人脸与身份的删除/隐藏标记。"""
    chain = MagicMock()
    db = MagicMock()
    db.query.return_value.join.return_value = chain
    chain.filter.return_value.exists.return_value = "EXISTS"

    result = location_stats.person_photo_condition(db, uuid4(), uuid4())

    assert result == "EXISTS"
    assert db.query.call_args.args == (Face.id,)
    join_args = db.query.return_value.join.call_args.args
    assert join_args[0] is FaceIdentity
    clauses = [str(clause) for clause in chain.filter.call_args.args]
    joined = " ".join(clauses)
    assert "face_identities" in joined
    assert "is_hidden" in joined
    assert "is_deleted" in joined
    assert "photos.id" in joined
