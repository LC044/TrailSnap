"""Nightly watch 2026-11-24 — app/service/tasks/tickets.py 的票据落库分支补测。

覆盖 save_recognition_result 里此前没有测试触及的三条路径：

* 车次候选码归一化：识别结果只给了 train_code_candidates 时，按有序路线的
  唯一候选回填车次号，并记录「修正来源」。
* 行程里程/时长补充失败时只记警告，不影响票据落库。
* 识别结果落库失败、且连「重置处理标记」都失败时，仍要安全返回 failed。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from uuid import uuid4

from app.service.tasks import tickets as tickets_mod


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _photo():
    return SimpleNamespace(
        id=str(uuid4()),
        owner_id="owner-1",
        filename="IMG_0001.jpg",
        photo_time=datetime(2026, 7, 1, 9, 0),
        processed_tasks={},
    )


def _result(**overrides):
    ticket = {
        "type": "train",
        "train_code_candidates": [{"code": "G1"}, {"code": "G2"}],
        "train_code_raw": "G?",
        "departure_station": "北京南",
        "arrival_station": "上海虹桥",
        "datetime": "2026-07-01 10:00",
        "name": "高铁",
    }
    ticket.update(overrides)
    return {"tickets": [ticket]}


def _patch_pipeline(monkeypatch, *, saved=None, extra=None, extra_error=None):
    created = {}

    async def fake_calculate(ticket, evidence=None):
        if extra_error is not None:
            raise extra_error
        return extra

    def fake_create(db, ticket, owner_id=None, commit=False):
        created["ticket"] = ticket
        created["owner_id"] = owner_id
        return saved

    monkeypatch.setattr(tickets_mod, "calculate_ticket_mileage_and_time", fake_calculate)
    monkeypatch.setattr(tickets_mod.crud_train_tickets, "create_train_ticket", fake_create)
    return created


def test_train_code_candidates_are_resolved_and_recorded_as_correction(monkeypatch):
    """只给候选码时按唯一候选回填车次号，并在行程来源里记录修正。"""
    monkeypatch.setattr(
        "app.service.ticket_journey.resolve_code_candidates",
        lambda info, dt, cache: "G1",
    )
    created = _patch_pipeline(
        monkeypatch,
        saved=SimpleNamespace(id="ticket-1"),
        extra={
            "total_mileage": 1318,
            "total_time": 300,
            "stop_stations": [],
            "sources": {
                "distance_source": "gps-haversine-x1.2",
                "duration_source": "estimated-distance-speed",
            },
        },
    )
    db = MagicMock()
    photo = _photo()

    result = asyncio.run(
        tickets_mod.RecognizeTicketStrategy().save_recognition_result(photo, _result(), db)
    )

    assert result["status"] == "success"
    assert result["tickets_added"] == 1
    assert created["ticket"].train_code == "G1"
    # 里程 / 时长是估算出来的，备注里必须写明。
    assert "里程按车站坐标估算" in created["ticket"].comments
    assert "时长按里程及车次类型速度估算" in created["ticket"].comments
    assert photo.processed_tasks["ticket_journey_sources"]["train:ticket-1"]["train_code_correction"]["resolved"] == "G1"


def test_failed_enrichment_does_not_block_the_ticket_from_being_saved(monkeypatch):
    """里程/时长补充失败只记警告，票据仍要落库。"""
    monkeypatch.setattr(
        "app.service.ticket_journey.resolve_code_candidates",
        lambda info, dt, cache: "G1",
    )
    created = _patch_pipeline(
        monkeypatch,
        saved=SimpleNamespace(id="ticket-2"),
        extra_error=RuntimeError("railway cache unavailable"),
    )
    db = MagicMock()
    photo = _photo()

    result = asyncio.run(
        tickets_mod.RecognizeTicketStrategy().save_recognition_result(photo, _result(), db)
    )

    assert result["status"] == "success"
    assert created["ticket"].train_code == "G1"
    assert created["ticket"].total_mileage == 0


def test_failure_to_reset_the_processing_flag_is_contained(monkeypatch, caplog):
    """识别失败且连标记重置都失败时，不能把异常抛给调用方。"""
    monkeypatch.setattr(
        "app.service.ticket_journey.resolve_code_candidates",
        lambda info, dt, cache: "G1",
    )

    def boom(db, ticket, owner_id=None, commit=False):
        raise RuntimeError("写入失败")

    monkeypatch.setattr(tickets_mod.crud_train_tickets, "create_train_ticket", boom)

    db = MagicMock()
    db.commit.side_effect = RuntimeError("提交失败")
    photo = _photo()

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(
            tickets_mod.RecognizeTicketStrategy().save_recognition_result(photo, _result(), db)
        )

    assert result["status"] == "failed"
    assert "写入失败" in result["error"]
    assert db.rollback.called




