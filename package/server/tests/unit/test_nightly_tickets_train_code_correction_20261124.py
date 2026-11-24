"""Nightly watch 2026-11-24 · app/service/tasks/tickets.py 的车次纠错与降级分支。

覆盖扫描显示 tickets.py 还有 15 行未覆盖，集中在「识别结果落库」这条路径上：

- L257-L265: OCR 认不出车次号时，用候选车次 + 有序行程消歧（resolve_code_candidates）
- L292:      纠错结果写进 journey_sources.train_code_correction
- L297-L298: 里程/时长来源为估算时，在票据备注里说明
- L301-L302: 铁路富化失败只告警，不影响票据落库
- L336-L338: 识别结果非法且「复位处理标记」也失败时，仍要回滚并返回失败

这些分支决定了「OCR 认错车次号」和「铁路离线库不可用」两种真实故障下的行为。
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.service.tasks import tickets as tickets_task

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _photo():
    return SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        filename="photo.jpg",
        file_path="/tmp/photo.jpg",
        processed_tasks={},
        photo_time=datetime(2026, 5, 1, 10, 0),
    )


class _Db:
    def __init__(self, fail_commit=False):
        self.commits = 0
        self.rollbacks = 0
        self.added = []
        self.fail_commit = fail_commit

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("数据库不可用")

    def rollback(self):
        self.rollbacks += 1


def _ticket_result():
    return {
        "tickets": [
            {
                "type": "train",
                "train_code": None,
                "train_code_raw": "G1",
                "train_code_candidates": ["G1", "G2"],
                "datetime": "2026-05-01 10:00",
                "departure_station": "北京南",
                "arrival_station": "上海虹桥",
                "name": "张三",
                "price": "553.5元",
            }
        ]
    }


@pytest.fixture
def resolved_code(monkeypatch):
    """把候选车次消歧替换成固定结果，避免依赖离线铁路库。"""
    from app.service import ticket_journey
    from railway import history_cache

    monkeypatch.setattr(ticket_journey, "resolve_code_candidates", lambda info, day, cache: "G1")
    monkeypatch.setattr(history_cache, "HistoryCache", lambda: SimpleNamespace(resolve=lambda *a, **k: {}))
    return "G1"


def test_a_resolved_code_is_applied_and_recorded(monkeypatch, resolved_code):
    created = {}

    async def fake_mileage(ticket, evidence=None):
        return {
            "total_mileage": 1318.0,
            "total_time": 300,
            "stop_stations": [],
            "sources": {
                "distance_source": "gps-haversine-x1.2",
                "duration_source": "estimated-distance-speed",
            },
        }

    def fake_create(db, ticket, owner_id, commit=False):
        created["ticket"] = ticket
        created["owner_id"] = owner_id
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(tickets_task, "calculate_ticket_mileage_and_time", fake_mileage)
    monkeypatch.setattr(tickets_task.crud_train_tickets, "create_train_ticket", fake_create)

    photo = _photo()
    db = _Db()
    result = _run(tickets_task.RecognizeTicketStrategy().save_recognition_result(photo, _ticket_result(), db))

    assert result["status"] == "success"
    assert result["tickets_added"] == 1
    assert created["ticket"].train_code == "G1"
    assert str(created["ticket"].price) == "553.5"

    sources = photo.processed_tasks["ticket_journey_sources"]
    correction = sources[f"train:{created['ticket'].id if hasattr(created['ticket'], 'id') else ''}"] if False else None
    assert any(
        value["train_code_correction"]
        == {
            "original": "G1",
            "resolved": "G1",
            "source": "unique-code-candidate-in-ordered-route",
        }
        for value in sources.values()
    )
    assert "里程按车站坐标估算" in created["ticket"].comments
    assert "时长按里程及车次类型速度估算" in created["ticket"].comments


def test_a_failed_railway_enrichment_still_saves_the_ticket(monkeypatch, resolved_code):
    async def boom(ticket, evidence=None):
        raise RuntimeError("离线铁路库不可用")

    def fake_create(db, ticket, owner_id, commit=False):
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(tickets_task, "calculate_ticket_mileage_and_time", boom)
    monkeypatch.setattr(tickets_task.crud_train_tickets, "create_train_ticket", fake_create)

    photo = _photo()
    db = _Db()
    result = _run(tickets_task.RecognizeTicketStrategy().save_recognition_result(photo, _ticket_result(), db))

    assert result["status"] == "success"
    assert result["tickets_added"] == 1
    assert "ticket_journey_sources" not in photo.processed_tasks


def test_an_invalid_result_is_reported_as_failed():
    photo = _photo()
    db = _Db()
    result = _run(
        tickets_task.RecognizeTicketStrategy().save_recognition_result(photo, {"tickets": "not-a-list"}, db)
    )

    assert result["status"] == "failed"
    assert db.rollbacks == 1
    assert photo.processed_tasks["tickets"] is False


def test_a_broken_reset_still_rolls_back_twice():
    photo = _photo()
    db = _Db(fail_commit=True)
    result = _run(
        tickets_task.RecognizeTicketStrategy().save_recognition_result(photo, {"tickets": "not-a-list"}, db)
    )

    assert result["status"] == "failed"
    # 一次是识别失败后的回滚，一次是复位处理标记也失败后的回滚。
    assert db.rollbacks == 2

