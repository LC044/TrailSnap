"""Nightly watch gap coverage for app.api.annual_report.

Targets the five remaining CRUD-delegating handlers not exercised by
``test_annual_report_api.py`` (covers /summary, /photos, /season,
/emotion, /easter-egg). All handlers delegate to crud_annual_report
helpers, so we assert delegation + user scope passthrough.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import annual_report as report_api


pytestmark = [pytest.mark.smoke]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _range_args():
    return {
        "start_time": datetime(2026, 1, 1),
        "end_time": datetime(2026, 12, 31, 23, 59, 59),
    }


# -------------------- /annual-report/photos --------------------


def test_get_annual_report_photos_delegates_to_crud():
    db = MagicMock()
    user = _user()
    fake = {2026: [SimpleNamespace(id=uuid4())]}
    args = _range_args()

    with patch.object(
        report_api.crud_annual_report, "get_annual_report_photos", return_value=fake
    ) as crud_call:
        result = report_api.get_annual_report_photos(
            start_time=args["start_time"],
            end_time=args["end_time"],
            db=db,
            current_user=user,
        )

    crud_call.assert_called_once_with(
        args["start_time"], args["end_time"], db, user_id=user.id
    )
    assert result is fake


# -------------------- /annual-report/summary --------------------


def test_get_report_summary_delegates_to_crud():
    db = MagicMock()
    user = _user()
    fake = SimpleNamespace(user="u", time="t")
    args = _range_args()

    with patch.object(
        report_api.crud_annual_report, "get_report_summary", return_value=fake
    ) as crud_call:
        result = report_api.get_report_summary(
            start_time=args["start_time"],
            end_time=args["end_time"],
            db=db,
            current_user=user,
        )

    crud_call.assert_called_once_with(
        args["start_time"], args["end_time"], db, user_id=user.id
    )
    assert result is fake


# -------------------- /annual-report/season --------------------


def test_get_report_season_delegates_to_crud():
    db = MagicMock()
    user = _user()
    fake = SimpleNamespace(seasonList=[])
    args = _range_args()

    with patch.object(
        report_api.crud_annual_report, "get_report_season", return_value=fake
    ) as crud_call:
        result = report_api.get_report_season(
            start_time=args["start_time"],
            end_time=args["end_time"],
            db=db,
            current_user=user,
        )

    crud_call.assert_called_once_with(
        args["start_time"], args["end_time"], db, user_id=user.id
    )
    assert result is fake


# -------------------- /annual-report/emotion --------------------


def test_get_report_emotion_delegates_to_crud():
    db = MagicMock()
    user = _user()
    fake = SimpleNamespace(livePhotos=0, backupPhotos=0)
    args = _range_args()

    with patch.object(
        report_api.crud_annual_report, "get_report_emotion", return_value=fake
    ) as crud_call:
        result = report_api.get_report_emotion(
            start_time=args["start_time"],
            end_time=args["end_time"],
            db=db,
            current_user=user,
        )

    crud_call.assert_called_once_with(
        args["start_time"], args["end_time"], db, user_id=user.id
    )
    assert result is fake


# -------------------- /annual-report/easter-egg --------------------


def test_get_report_easter_egg_delegates_to_crud():
    db = MagicMock()
    user = _user()
    fake = SimpleNamespace(hasEasterEgg=False)
    args = _range_args()

    with patch.object(
        report_api.crud_annual_report, "get_report_easter_egg", return_value=fake
    ) as crud_call:
        result = report_api.get_report_easter_egg(
            start_time=args["start_time"],
            end_time=args["end_time"],
            db=db,
            current_user=user,
        )

    crud_call.assert_called_once_with(
        args["start_time"], args["end_time"], db, user_id=user.id
    )
    assert result is fake
