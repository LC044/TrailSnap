"""Nightly watch 2026-11-22: ``app/service/relations.py``::Relations._next / _scope 盲区。

关系图的翻页游标不是授权凭证，而是「作用域 + 上一页末尾」的签名串：
游标里带上 owner 与查询上下文（context）的哈希，服务端每页仍然重新套用
实时权限过滤条件。若作用域哈希计算错位，用户就可能拿到别的查询上下文
的游标，或者翻页时漏掉应有的权限收窄。

本文件覆盖：
- 游标是 base64url 且不带 padding，可还原出 last（happy）
- 游标中的 scope 与 _scope 计算结果一致（happy）
- 不同 context 产生不同 scope（edge）
- 不同 owner 产生不同 scope（edge）
"""

from __future__ import annotations

import base64
import json
from uuid import uuid4

import pytest

from app.service.relations import Relations


pytestmark = [pytest.mark.smoke]


def _decode(cursor: str) -> dict:
    padding = "=" * (-len(cursor) % 4)
    return json.loads(base64.urlsafe_b64decode(cursor + padding).decode())


def test_next_returns_a_urlsafe_cursor_without_padding():
    relations = Relations(None, uuid4())

    cursor = relations._next("node-1", "people")

    assert "=" not in cursor
    assert "+" not in cursor and "/" not in cursor


def test_next_cursor_carries_the_last_node_and_the_scope():
    relations = Relations(None, uuid4())

    cursor = relations._next("node-1", "people")
    payload = _decode(cursor)

    assert payload["last"] == "node-1"
    assert payload["scope"] == relations._scope("people")


def test_next_cursor_changes_with_the_query_context():
    relations = Relations(None, uuid4())

    people_cursor = relations._next("node-1", "people")
    photos_cursor = relations._next("node-1", "photos")

    assert people_cursor != photos_cursor
    assert relations._scope("people") != relations._scope("photos")


def test_next_cursor_changes_with_the_owner():
    first = Relations(None, uuid4())
    second = Relations(None, uuid4())

    assert first._next("node-1", "people") != second._next("node-1", "people")
    assert first._scope("people") != second._scope("people")


def test_next_cursor_is_stable_for_the_same_input():
    relations = Relations(None, uuid4())

    assert relations._next("node-1", "people") == relations._next("node-1", "people")
