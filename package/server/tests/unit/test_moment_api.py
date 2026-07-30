"""Unit tests for moments day-caption / day-highlights router.

Covers:
* GET /moments/day-captions —— 参数校验 (start > end / 区间过长)
* PUT /moments/day-captions/{day} —— caption 非空
* POST /moments/day-captions/generate —— scope 白名单、ValueError→400
* GET /moments/day-highlights —— 参数校验、参数正确转发到 service
"""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import asyncio

import pytest
from fastapi import HTTPException

from app.api import moment as moment_api
from app.schemas.moment import (
    MomentDayCaptionGenerateRequest,
    MomentDayCaptionUpsert,
)


pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _user():
    return SimpleNamespace(id=uuid4())


# ---------------------------- GET / list ----------------------------


def test_list_day_captions_rejects_reversed_range():
    with pytest.raises(HTTPException) as exc:
        moment_api.list_day_captions(
            start=date(2025, 8, 10), end=date(2025, 8, 1),
            scope_type="all", scope_id=None,
            current_user=_user(), db=MagicMock(),
        )
    assert exc.value.status_code == 400


def test_list_day_captions_rejects_too_long_range():
    with pytest.raises(HTTPException) as exc:
        moment_api.list_day_captions(
            start=date(2000, 1, 1), end=date(2003, 1, 1),
            scope_type="all", scope_id=None,
            current_user=_user(), db=MagicMock(),
        )
    assert exc.value.status_code == 400


def test_list_day_captions_forwards_to_crud():
    user = _user()
    db = MagicMock()
    with patch.object(moment_api.moment_crud, "list_captions", return_value=[]) as m:
        moment_api.list_day_captions(
            start=date(2025, 8, 1), end=date(2025, 8, 31),
            scope_type="all", scope_id=None,
            current_user=user, db=db,
        )
    m.assert_called_once()
    args = m.call_args.args
    assert args[0] is db
    assert args[1] == user.id
    assert args[2] == "all"


# ---------------------------- PUT / upsert ----------------------------


def test_upsert_day_caption_rejects_blank():
    with pytest.raises(HTTPException) as exc:
        moment_api.upsert_day_caption(
            day=date(2025, 8, 5),
            payload=MomentDayCaptionUpsert(caption="   "),
            scope_type="all", scope_id=None,
            current_user=_user(), db=MagicMock(),
        )
    assert exc.value.status_code == 400


def test_upsert_day_caption_persists_manual():
    user = _user()
    db = MagicMock()
    with patch.object(moment_api.moment_crud, "upsert_caption") as m:
        m.return_value = SimpleNamespace(
            id=1, user_id=user.id, scope_type="all", scope_id=None,
            day=date(2025, 8, 5), caption="hello", source="manual",
            model_name=None, photo_count=0,
            created_at=datetime(2025, 8, 5), updated_at=datetime(2025, 8, 5),
        )
        moment_api.upsert_day_caption(
            day=date(2025, 8, 5),
            payload=MomentDayCaptionUpsert(caption="hello"),
            scope_type="all", scope_id=None,
            current_user=user, db=db,
        )
    args = m.call_args
    assert args.kwargs.get("source") == "manual" or "manual" in args.args


# ---------------------------- POST /generate ----------------------------


def test_generate_rejects_non_all_scope():
    request = MomentDayCaptionGenerateRequest(
        day=date(2025, 8, 5), timezone="Asia/Shanghai",
        scope_type="album", scope_id="abc",
    )
    with pytest.raises(HTTPException) as exc:
        _run(moment_api.generate_day_caption(
            request=request, current_user=_user(), db=MagicMock(),
        ))
    assert exc.value.status_code == 400


def test_generate_sync_maps_value_error_to_400():
    request = MomentDayCaptionGenerateRequest(
        day=date(2025, 8, 5), timezone="Asia/Shanghai",
        stream=False,
    )
    with patch.object(moment_api, "generate_caption_sync", new=AsyncMock(side_effect=ValueError("no llm"))):
        with pytest.raises(HTTPException) as exc:
            _run(moment_api.generate_day_caption(
                request=request, current_user=_user(), db=MagicMock(),
            ))
    assert exc.value.status_code == 400
    assert "no llm" in str(exc.value.detail)


def test_generate_sync_returns_service_result():
    request = MomentDayCaptionGenerateRequest(
        day=date(2025, 8, 5), timezone="Asia/Shanghai",
        stream=False,
    )
    fake = {"caption": "写好的文案", "cached": False, "source": "ai"}
    with patch.object(moment_api, "generate_caption_sync", new=AsyncMock(return_value=fake)):
        res = _run(moment_api.generate_day_caption(
            request=request, current_user=_user(), db=MagicMock(),
        ))
    assert res == fake


# ---------------------------- GET /day-highlights ----------------------------


def test_list_day_highlights_rejects_reversed_range():
    with pytest.raises(HTTPException) as exc:
        moment_api.list_day_highlights(
            start=date(2025, 8, 10), end=date(2025, 8, 1), limit=9,
            current_user=_user(), db=MagicMock(),
        )
    assert exc.value.status_code == 400


def test_list_day_highlights_rejects_too_long_range():
    with pytest.raises(HTTPException) as exc:
        moment_api.list_day_highlights(
            start=date(2000, 1, 1), end=date(2003, 1, 1), limit=9,
            current_user=_user(), db=MagicMock(),
        )
    assert exc.value.status_code == 400


def test_list_day_highlights_forwards_to_service():
    user = _user()
    db = MagicMock()
    fake = [{"day": date(2025, 8, 5), "photos": [], "total_candidates": 0}]
    with patch.object(moment_api, "get_range_highlights", return_value=fake) as m:
        res = moment_api.list_day_highlights(
            start=date(2025, 8, 1), end=date(2025, 8, 31), limit=9,
            current_user=user, db=db,
        )
    assert res == fake
    m.assert_called_once()
    args, kwargs = m.call_args.args, m.call_args.kwargs
    assert args[0] is db
    assert args[1] == user.id
    assert args[2] == date(2025, 8, 1)
    assert args[3] == date(2025, 8, 31)
    assert kwargs.get("limit") == 9
