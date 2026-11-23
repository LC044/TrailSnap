"""Nightly watch 2026-11-23 · app/api/ticket_wallet.py 的导入 / 列表路由盲区。

覆盖：
- import_wallet 解析 CSV / JSON 票据文件并转交服务层（happy）
- import_wallet 拒绝非 JSON/CSV 扩展名（error）
- import_wallet 拒绝不支持的 JSON 版本（error）
- import_wallet 拒绝超过 10000 条记录的载荷（error）
- list_wallet 把带时区的输入归一化为 naive UTC（edge）
- list_wallet 在 start >= end 时拒绝查询（error）
- list_wallet 按 skip / limit 切片并返回总数（happy）
"""

import asyncio
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api import ticket_wallet as wallet_api

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def _upload(name: str, payload: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=name)


def _run_import(file: UploadFile, session, user):
    return asyncio.run(wallet_api.import_wallet(file, session, user))


def test_import_wallet_parses_csv_rows(face_sqlite_session, monkeypatch):
    from app.service import ticket_wallet as service

    seen = {}

    def fake_import_records(db, owner_id, records):
        seen["owner_id"] = owner_id
        seen["records"] = records
        return {"imported": len(records)}

    monkeypatch.setattr(service, "import_records", fake_import_records)
    csv_bytes = "type,id\ntrain,train-1\nflight,flight-1\n".encode("utf-8-sig")
    user = _user()

    result = _run_import(_upload("wallet.csv", csv_bytes), face_sqlite_session, user)

    assert result.code == 0
    assert result.data["imported"] == 2
    assert seen["owner_id"] == user.id
    assert seen["records"] == [
        {"type": "train", "id": "train-1"},
        {"type": "flight", "id": "flight-1"},
    ]


def test_import_wallet_parses_a_version_1_json_payload(face_sqlite_session, monkeypatch):
    from app.service import ticket_wallet as service

    seen = {}

    def fake_import_records(db, owner_id, records):
        seen["records"] = records
        return {"imported": len(records)}

    monkeypatch.setattr(service, "import_records", fake_import_records)
    payload = json.dumps({"version": 1, "items": [{"type": "train", "id": "train-9"}]}).encode()

    result = _run_import(_upload("wallet.json", payload), face_sqlite_session, _user())

    assert result.code == 0
    assert seen["records"] == [{"type": "train", "id": "train-9"}]


def test_import_wallet_rejects_an_unsupported_extension(face_sqlite_session):
    with pytest.raises(HTTPException) as failure:
        _run_import(_upload("wallet.txt", b"hello"), face_sqlite_session, _user())
    assert failure.value.status_code == 422


def test_import_wallet_rejects_an_unsupported_json_version(face_sqlite_session):
    payload = json.dumps({"version": 2, "items": []}).encode()

    with pytest.raises(HTTPException) as failure:
        _run_import(_upload("wallet.json", payload), face_sqlite_session, _user())
    assert failure.value.status_code == 422


def test_import_wallet_rejects_more_than_ten_thousand_records(face_sqlite_session):
    records = [{"type": "train", "id": f"train-{index}"} for index in range(10001)]
    payload = json.dumps(records).encode()

    with pytest.raises(HTTPException) as failure:
        _run_import(_upload("wallet.json", payload), face_sqlite_session, _user())
    assert failure.value.status_code == 422


def test_list_wallet_normalizes_timezone_aware_inputs(face_sqlite_session, monkeypatch):
    """带时区的输入按 UTC 归一化后再交给服务层。"""
    from app.service import ticket_wallet as service

    seen = {}

    def fake_list_tickets(db, owner_id, album_id=None, memory_id=None, start=None, end=None):
        seen["start"] = start
        seen["end"] = end
        return []

    monkeypatch.setattr(service, "list_tickets", fake_list_tickets)
    start = datetime(2024, 5, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    end = datetime(2024, 5, 2, 8, 0, tzinfo=timezone(timedelta(hours=8)))

    result = wallet_api.list_wallet(None, None, start, end, 0, 100, face_sqlite_session, _user())

    assert result.code == 0
    assert seen["start"] == datetime(2024, 5, 1, 0, 0)
    assert seen["end"] == datetime(2024, 5, 2, 0, 0)
    assert seen["start"].tzinfo is None


def test_list_wallet_rejects_a_reversed_time_range(face_sqlite_session):
    start = datetime(2024, 5, 2)
    end = datetime(2024, 5, 1)

    with pytest.raises(HTTPException) as failure:
        wallet_api.list_wallet(None, None, start, end, 0, 100, face_sqlite_session, _user())
    assert failure.value.status_code == 422


def test_list_wallet_slices_the_items_and_reports_the_total(face_sqlite_session, monkeypatch):
    from app.service import ticket_wallet as service

    items = [{"key": f"train:{index}"} for index in range(5)]

    monkeypatch.setattr(service, "list_tickets", lambda db, owner_id, **kwargs: items)

    result = wallet_api.list_wallet(None, None, None, None, 1, 2, face_sqlite_session, _user())

    assert result.code == 0
    assert result.data["total"] == 5
    assert result.data["items"] == [{"key": "train:1"}, {"key": "train:2"}]


