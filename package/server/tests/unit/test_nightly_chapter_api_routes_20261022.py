"""Unit tests for ``app/api/chapter.py`` route handlers.

The 2026-10-22 coverage scan showed ``app/api/chapter.py`` at 75.0%
(27 missed statements of 108). The gaps were all *route glue*: every
handler that forwards to ``app.service.chapter`` / ``app.service.chapter_days``
/ ``app.service.chapter_diary`` was never executed because the existing
suite only exercised the discovery endpoints and the action whitelist.

This file drives the HTTP layer with the service layer stubbed, so it
verifies the parts a route actually owns:

* which service function is called,
* with which arguments (ownership id, chapter id, paging window),
* and that the response is wrapped in the ``BaseResponse`` envelope.

The service layer itself is covered by the chapter service tests; stubbing
it here keeps the route tests hermetic (no DB, no LLM).
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chapter import router
from app.api.deps import get_current_user
from app.dependencies import get_db


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _build_client():
    """A TestClient whose dependencies are replaced by plain stubs."""
    app = FastAPI()
    app.include_router(router, prefix="/api/chapters")
    owner = SimpleNamespace(id=uuid.uuid4())
    db = MagicMock()
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), owner, db


@pytest.fixture
def chapter_api(monkeypatch):
    """Stub the three service modules the chapter routes delegate to.

    Returns a namespace with the recorded call arguments so each test can
    assert the route forwarded the right values.
    """
    from app.api import chapter as chapter_module

    calls = SimpleNamespace(
        preview={}, cover_options={}, photos={}, events={}, update={},
        split={}, delete={}, merge={}, serialize=[], owned=[],
        list_days={}, generate_day={}, diary_generate={},
        day_scope={}, upsert_caption={},
    )

    service = MagicMock()
    service.preview.side_effect = lambda db, owner_id, start, end, chapter_id: (
        calls.preview.update({"owner_id": owner_id, "start": start, "end": end,
                              "chapter_id": chapter_id})
        or {"items": [], "total": 0}
    )
    service.cover_options.side_effect = lambda db, owner_id, start, end, skip, limit: (
        calls.cover_options.update({"owner_id": owner_id, "start": start, "end": end,
                                    "skip": skip, "limit": limit})
        or {"items": [], "total": 0}
    )
    service.photos.side_effect = lambda db, row, skip, limit, year=None: (
        calls.photos.update({"row": row, "skip": skip, "limit": limit, "year": year})
        or {"items": [], "total": 0}
    )
    service.events.side_effect = lambda db, row, skip, limit, year=None: (
        calls.events.update({"row": row, "skip": skip, "limit": limit, "year": year})
        or {"items": [], "total": 0}
    )
    service.update.side_effect = lambda db, owner_id, chapter_id, payload: (
        calls.update.update({"owner_id": owner_id, "chapter_id": chapter_id,
                             "version": payload.version})
        or SimpleNamespace(id=chapter_id)
    )
    service.split.side_effect = lambda db, owner_id, chapter_id, payload: (
        calls.split.update({"owner_id": owner_id, "chapter_id": chapter_id,
                            "split_date": payload.split_date})
        or [SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())]
    )
    service.delete.side_effect = lambda db, owner_id, chapter_id, version: (
        calls.delete.update({"owner_id": owner_id, "chapter_id": chapter_id,
                             "version": version})
    )
    service.merge.side_effect = lambda db, owner_id, payload: (
        calls.merge.update({"owner_id": owner_id, "chapter_ids": payload.chapter_ids})
        or SimpleNamespace(id=uuid.uuid4())
    )
    service.serialize.side_effect = lambda db, row: calls.serialize.append(row) or {
        "id": str(getattr(row, "id", "")),
    }
    service._owned.side_effect = lambda db, owner_id, chapter_id, manage=False: (
        calls.owned.append({"owner_id": owner_id, "chapter_id": chapter_id,
                            "manage": manage})
        or SimpleNamespace(id=chapter_id)
    )

    monkeypatch.setattr(chapter_module, "service", service)

    chapter_days = MagicMock()
    chapter_days.list_days.side_effect = lambda db, owner_id, chapter_id, skip, limit, year=None, month=None: (
        calls.list_days.update({"owner_id": owner_id, "chapter_id": chapter_id,
                                "skip": skip, "limit": limit, "year": year, "month": month})
        or {"items": [], "total": 0, "skip": skip, "limit": limit}
    )

    async def _generate_day(db, owner_id, chapter_id, day):
        calls.generate_day.update({"owner_id": owner_id, "chapter_id": chapter_id,
                                   "day": day})
        return {"caption": "今天的一天", "source": "manual"}

    chapter_days.generate.side_effect = _generate_day
    chapter_days.day_scope.side_effect = lambda db, owner_id, chapter_id, day: (
        calls.day_scope.update({"owner_id": owner_id, "chapter_id": chapter_id,
                                "day": day})
        or (SimpleNamespace(id=chapter_id), SimpleNamespace(owner_id=owner_id))
    )
    monkeypatch.setattr("app.service.chapter_days", chapter_days, raising=False)

    chapter_diary = MagicMock()

    async def _diary_generate(db, owner_id, chapter_id, request):
        calls.diary_generate.update({"owner_id": owner_id, "chapter_id": chapter_id,
                                     "scope": request.scope, "version": request.version})
        return {"title": "", "body": "日记", "source": "ai", "source_photo_ids": [],
                "source_memory_ids": [], "scope": request.scope, "year": request.year,
                "version": request.version, "photo_count": 3}

    chapter_diary.generate.side_effect = _diary_generate
    monkeypatch.setattr("app.service.chapter_diary", chapter_diary, raising=False)

    moment = MagicMock()
    moment.upsert_caption.side_effect = lambda db, user_id, scope_type, scope_id, day, caption, source: (
        calls.upsert_caption.update({"user_id": user_id, "scope_type": scope_type,
                                     "scope_id": scope_id, "day": day,
                                     "caption": caption, "source": source})
        or SimpleNamespace(caption=caption, source=source)
    )
    monkeypatch.setattr("app.crud.moment", moment, raising=False)

    return SimpleNamespace(calls=calls, service=service, chapter_days=chapter_days,
                           chapter_diary=chapter_diary, moment=moment)


# ---------------------------------------------------------------------------
# preview / cover-options
# ---------------------------------------------------------------------------


def test_preview_forwards_range_to_service(chapter_api):
    client, owner, db = _build_client()
    start = date(2025, 1, 1)

    resp = client.post("/api/chapters/preview", json={"start_date": start.isoformat()})

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"items": [], "total": 0}
    assert chapter_api.calls.preview["owner_id"] == owner.id
    assert chapter_api.calls.preview["start"] == start
    assert chapter_api.calls.preview["end"] is None
    assert chapter_api.calls.preview["chapter_id"] is None


def test_preview_passes_chapter_id_and_end_date(chapter_api):
    client, owner, _ = _build_client()
    start = date(2025, 3, 1)
    end = date(2025, 4, 1)
    chapter_id = str(uuid.uuid4())

    resp = client.post("/api/chapters/preview", json={
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "chapter_id": chapter_id,
    })

    assert resp.status_code == 200
    assert chapter_api.calls.preview["start"] == start
    assert chapter_api.calls.preview["end"] == end
    assert chapter_api.calls.preview["chapter_id"] == uuid.UUID(chapter_id)


def test_cover_options_forwards_paging_window(chapter_api):
    client, owner, _ = _build_client()
    start = date(2025, 5, 1)

    resp = client.post("/api/chapters/cover-options?skip=5&limit=7",
                       json={"start_date": start.isoformat()})

    assert resp.status_code == 200
    assert chapter_api.calls.cover_options["owner_id"] == owner.id
    assert chapter_api.calls.cover_options["skip"] == 5
    assert chapter_api.calls.cover_options["limit"] == 7
    assert chapter_api.calls.cover_options["start"] == start


# ---------------------------------------------------------------------------
# photos / events
# ---------------------------------------------------------------------------


def test_chapter_photos_resolves_owner_then_lists(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.get(f"/api/chapters/{chapter_id}/photos?skip=2&limit=9&year=2024")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"items": [], "total": 0}
    assert chapter_api.calls.owned == [{"owner_id": owner.id, "chapter_id": chapter_id,
                                        "manage": False}]
    assert chapter_api.calls.photos["skip"] == 2
    assert chapter_api.calls.photos["limit"] == 9
    assert chapter_api.calls.photos["year"] == 2024


def test_chapter_photos_honors_manage_flag(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.get(f"/api/chapters/{chapter_id}/photos?manage=true")

    assert resp.status_code == 200
    assert chapter_api.calls.owned[0]["manage"] is True


def test_chapter_events_resolves_owner_then_lists(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.get(f"/api/chapters/{chapter_id}/events?skip=1&limit=4")

    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert chapter_api.calls.owned[0]["chapter_id"] == chapter_id
    assert chapter_api.calls.events["skip"] == 1
    assert chapter_api.calls.events["limit"] == 4
    assert chapter_api.calls.events["year"] is None


# ---------------------------------------------------------------------------
# update / split / delete
# ---------------------------------------------------------------------------


def test_update_forwards_version_and_serializes(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.patch(f"/api/chapters/{chapter_id}", json={
        "title": "新的章节",
        "start_date": "2025-01-01",
        "version": 3,
    })

    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == str(chapter_id)
    assert chapter_api.calls.update["owner_id"] == owner.id
    assert chapter_api.calls.update["chapter_id"] == chapter_id
    assert chapter_api.calls.update["version"] == 3


def test_split_returns_one_serialized_row_per_part(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.post(f"/api/chapters/{chapter_id}/split", json={
        "split_date": "2025-06-15",
        "first_title": "上半年",
        "second_title": "下半年",
        "version": 2,
    })

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert chapter_api.calls.split["owner_id"] == owner.id
    assert chapter_api.calls.split["split_date"] == date(2025, 6, 15)


def test_delete_forwards_version_and_reports_deleted(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.delete(f"/api/chapters/{chapter_id}?version=5")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"deleted": True}
    assert chapter_api.calls.delete == {
        "owner_id": owner.id, "chapter_id": chapter_id, "version": 5,
    }


def test_merge_serializes_merged_chapter(chapter_api):
    client, owner, _ = _build_client()
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]

    resp = client.post("/api/chapters/merge", json={
        "title": "合并后的章节",
        "start_date": "2025-01-01",
        "chapter_ids": ids,
        "versions": {ids[0]: 1, ids[1]: 1},
    })

    assert resp.status_code == 200
    assert resp.json()["data"]["id"]
    assert chapter_api.calls.merge["owner_id"] == owner.id
    assert [str(cid) for cid in chapter_api.calls.merge["chapter_ids"]] == ids


# ---------------------------------------------------------------------------
# diary endpoints
# ---------------------------------------------------------------------------


def test_diary_generate_forwards_scope_and_version(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.post(f"/api/chapters/{chapter_id}/diary/generate", json={
        "scope": "introduction",
        "version": 4,
        "notes": "写点什么",
    })

    assert resp.status_code == 200
    assert resp.json()["data"]["body"] == "日记"
    assert chapter_api.calls.diary_generate["owner_id"] == owner.id
    assert chapter_api.calls.diary_generate["scope"] == "introduction"
    assert chapter_api.calls.diary_generate["version"] == 4


def test_diary_days_forwards_paging_and_filters(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.get(f"/api/chapters/{chapter_id}/diary/days?skip=1&limit=3&year=2025&month=6")

    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0
    assert chapter_api.calls.list_days["owner_id"] == owner.id
    assert chapter_api.calls.list_days["skip"] == 1
    assert chapter_api.calls.list_days["limit"] == 3
    assert chapter_api.calls.list_days["year"] == 2025
    assert chapter_api.calls.list_days["month"] == 6


def test_generate_day_caption_returns_saved_caption(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.post(f"/api/chapters/{chapter_id}/diary/days/2025-07-04/generate")

    assert resp.status_code == 200
    assert resp.json()["data"]["caption"] == "今天的一天"
    assert chapter_api.calls.generate_day["owner_id"] == owner.id
    assert chapter_api.calls.generate_day["day"] == date(2025, 7, 4)


def test_day_photos_scopes_day_before_listing(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.get(f"/api/chapters/{chapter_id}/diary/days/2025-07-04/photos?skip=2&limit=8")

    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert chapter_api.calls.day_scope["owner_id"] == owner.id
    assert chapter_api.calls.day_scope["day"] == date(2025, 7, 4)
    assert chapter_api.calls.photos["skip"] == 2
    assert chapter_api.calls.photos["limit"] == 8


def test_save_day_upserts_manual_caption_for_owner(chapter_api):
    client, owner, _ = _build_client()
    chapter_id = uuid.uuid4()

    resp = client.put(f"/api/chapters/{chapter_id}/diary/days/2025-07-04", json={
        "caption": "  手写的一天  ",
        "source": "manual",
    })

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"caption": "手写的一天", "source": "manual"}
    saved = chapter_api.calls.upsert_caption
    assert saved["user_id"] == owner.id
    assert saved["scope_type"] == "all"
    assert saved["scope_id"] is None
    assert saved["day"] == date(2025, 7, 4)
    assert saved["caption"] == "手写的一天"
    assert saved["source"] == "manual"
