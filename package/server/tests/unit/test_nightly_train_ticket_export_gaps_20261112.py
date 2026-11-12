"""Nightly watch 2026-11-12 · app/api/train_ticket.py 导出分支盲区补测。

被测模块：app/api/train_ticket.py
覆盖点（2026-11-12 覆盖率基线中未触达的分支）：
- GET /export：format 不在 json/csv 时返回 400。
- GET /export：csv 且无记录时返回空 body。

DB 访问通过 patch get_all_train_tickets 打桩，不触碰真实 Postgres。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import train_ticket as train_ticket_api

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _user():
    return SimpleNamespace(id=uuid4())


def test_export_rejects_unsupported_format():
    db = MagicMock()
    with patch.object(train_ticket_api, "get_all_train_tickets", return_value=[]):
        with pytest.raises(HTTPException) as excinfo:
            train_ticket_api.export_tickets(format="xml", db=db, current_user=_user())
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "不支持的导出格式，请使用 json 或 csv"


def test_export_csv_without_records_returns_empty_body():
    db = MagicMock()
    with patch.object(train_ticket_api, "get_all_train_tickets", return_value=[]):
        response = train_ticket_api.export_tickets(format="csv", db=db, current_user=_user())
    assert response.body == b""
    assert response.media_type == "text/csv"


def test_export_json_returns_encoded_tickets():
    db = MagicMock()
    tickets = [{"id": "t1", "train_code": "G1", "date_time": "2025-03-01 10:00:00"}]
    with patch.object(train_ticket_api, "get_all_train_tickets", return_value=tickets):
        response = train_ticket_api.export_tickets(format="json", db=db, current_user=_user())
    assert response.media_type == "application/json"
    assert b"G1" in response.body
