"""Nightly watch 2026-11-26 · app/service/relations.py 的入参与分页校验盲区。

覆盖率报告里 ``relations.py`` 还有几处 400 分支从未被执行：``evidence()`` 的
「请选择两个不同对象」「无效的依据类型或数量」「无效分页」，以及 ``search()``
的「无效的类型或数量」。这些校验是关系视图的入口防线——一旦被绕过，前端会拿到
越权或错位的关联数据。

本文件把 ``require`` / ``hydrate`` 换成假实现，只驱动校验与分页游标逻辑：

- 同一个对象不能互相作为依据
- 不支持的 kind / 越界的 limit 被拒绝
- 游标被篡改（scope 不匹配）时提示刷新
- 游标里的 last 不是「两个字符串」时提示无效分页
- 合法游标可以正常翻页
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.service.relations import Relations


pytestmark = [pytest.mark.smoke]


def _relations():
    db = MagicMock()
    db.execute.return_value.all.return_value = []
    relations = Relations(db, uuid4())
    relations.require = lambda value: {"id": value}
    relations.hydrate = lambda keys: []
    return relations


def _encode(payload):
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def _decode(cursor):
    padded = cursor + "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def _tampered(relations, context, last):
    """生成一个 scope 正确但 last 内容不合法的游标。"""
    cursor = relations._next(list(last), context)
    payload = _decode(cursor)
    payload["last"] = last
    return _encode(payload)


# --- evidence ---------------------------------------------------------------

def test_evidence_rejects_the_same_object_on_both_sides():
    relations = _relations()

    with pytest.raises(HTTPException) as excinfo:
        relations.evidence("photo:1", "photo:1", kind="memory", limit=20)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "请选择两个不同对象"


def test_evidence_rejects_an_unsupported_kind():
    relations = _relations()

    with pytest.raises(HTTPException) as excinfo:
        relations.evidence("photo:1", "photo:2", kind="person", limit=20)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "无效的依据类型或数量"


@pytest.mark.parametrize("limit", [0, 51])
def test_evidence_rejects_a_limit_outside_the_allowed_range(limit):
    relations = _relations()

    with pytest.raises(HTTPException) as excinfo:
        relations.evidence("photo:1", "photo:2", kind="photo", limit=limit)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "无效的依据类型或数量"


def test_evidence_rejects_a_cursor_taken_from_another_scope():
    relations = _relations()
    cursor = _encode({"scope": "someone-else", "last": ["2024-01-01", "node"]})

    with pytest.raises(HTTPException) as excinfo:
        relations.evidence("photo:1", "photo:2", kind="memory", limit=20, cursor=cursor)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "分页条件已改变，请刷新"


def test_evidence_rejects_a_cursor_whose_last_is_not_a_pair_of_strings():
    relations = _relations()
    context = ["evidence", *sorted(["photo:1", "photo:2"]), "memory", 20]
    cursor = _tampered(relations, context, [2024, 7])

    with pytest.raises(HTTPException) as excinfo:
        relations.evidence("photo:1", "photo:2", kind="memory", limit=20, cursor=cursor)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "无效分页"


def test_evidence_accepts_a_well_formed_cursor():
    relations = _relations()
    context = ["evidence", *sorted(["photo:1", "photo:2"]), "memory", 20]
    cursor = relations._next(["2024-01-01", "node-1"], context)

    result = relations.evidence("photo:1", "photo:2", kind="memory", limit=20, cursor=cursor)

    assert result["items"] == []
    assert result["has_more"] is False
    assert result["next_cursor"] is None


# --- search -----------------------------------------------------------------

def test_search_rejects_an_unknown_kind():
    relations = _relations()

    with pytest.raises(HTTPException) as excinfo:
        relations.search(kind="album", q="", limit=20)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "无效的类型或数量"


@pytest.mark.parametrize("limit", [0, 51])
def test_search_rejects_a_limit_outside_the_allowed_range(limit):
    relations = _relations()

    with pytest.raises(HTTPException) as excinfo:
        relations.search(kind="person", q="", limit=limit)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "无效的类型或数量"


def test_search_rejects_a_cursor_whose_last_is_not_a_single_string():
    relations = _relations()
    context = ["search", "person", "", 20]
    cursor = _tampered(relations, context, [1, 2])

    with pytest.raises(HTTPException) as excinfo:
        relations.search(kind="person", q="", limit=20, cursor=cursor)

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "无效分页"


def test_search_accepts_a_valid_kind_and_returns_an_empty_page():
    relations = _relations()

    result = relations.search(kind="memory", q="旅行", limit=20)

    assert result["items"] == []
    assert result["has_more"] is False
    assert result["next_cursor"] is None
