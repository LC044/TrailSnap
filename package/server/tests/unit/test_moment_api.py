"""Focused unit coverage for the moments REST router."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import moment as moment_api
from app.schemas.moment import MomentDayCaptionGenerateRequest, MomentDayCaptionUpsert


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _user():
    return SimpleNamespace(id=uuid4())


def test_upsert_day_caption_trims_text_and_marks_manual_source():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(caption="A clear morning")

    with patch.object(moment_api.moment_crud, "upsert_caption", return_value=expected) as upsert:
        result = moment_api.upsert_day_caption(
            day=date(2026, 7, 29),
            payload=MomentDayCaptionUpsert(caption="  A clear morning  "),
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )

    assert result is expected
    upsert.assert_called_once_with(
        db, user.id, "all", None, date(2026, 7, 29), "A clear morning", source="manual"
    )


def test_list_day_captions_rejects_inverted_date_range():
    with patch.object(moment_api.moment_crud, "list_captions") as list_captions:
        with pytest.raises(HTTPException) as exc_info:
            moment_api.list_day_captions(
                start=date(2026, 7, 30),
                end=date(2026, 7, 29),
                current_user=_user(),
                db=MagicMock(),
            )

    assert exc_info.value.status_code == 400
    assert "start" in exc_info.value.detail
    list_captions.assert_not_called()


@pytest.mark.asyncio
async def test_generate_day_caption_maps_service_value_error_to_http_400():
    request = MomentDayCaptionGenerateRequest(
        day=date(2026, 7, 29),
        stream=False,
    )

    with patch.object(
        moment_api,
        "generate_caption_sync",
        new=AsyncMock(side_effect=ValueError("invalid timezone")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await moment_api.generate_day_caption(
                request=request,
                current_user=_user(),
                db=MagicMock(),
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "invalid timezone"
