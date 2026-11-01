"""Nightly watch 2026-10-31 coverage for remaining backend hot spots.

The scan selected four backend modules with the lowest coverage: daily-frame
API delegation, render-race cancellation, face-cluster candidate resolution,
and location trajectory compaction.  All cases are deterministic unit tests;
no service process, FFmpeg run, or external model is required.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.api import daily_frame as daily_frame_api
from app.crud import location as location_crud
from app.schemas.daily_frame import CalendarSettings, FrameVersion
from app.service import daily_frame_render
from app.service.face_cluster import FaceClusterService
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture()
def sqlite_db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_daily_frame_api_routes_delegate_to_service():
    owner = SimpleNamespace(id=uuid4())
    db = MagicMock()
    expected = {"ok": True}
    payload = CalendarSettings(timezone="Asia/Shanghai")

    with patch.object(daily_frame_api.service, "initialize", return_value=expected) as initialize:
        response = daily_frame_api.initialize(payload, user=owner, db=db)

    initialize.assert_called_once_with(db, owner.id, payload)
    assert response.code == 0
    assert response.data == expected


def test_daily_frame_api_remove_and_undo_delegate_version():
    owner = SimpleNamespace(id=uuid4())
    db = MagicMock()
    day = datetime(2026, 10, 31).date()
    payload = FrameVersion(version=3)

    with patch.object(daily_frame_api.service, "remove", return_value={"removed": True}) as remove:
        remove_response = daily_frame_api.remove(day, payload, user=owner, db=db)
    with patch.object(daily_frame_api.service, "undo_remove", return_value={"restored": True}) as undo:
        undo_response = daily_frame_api.undo(day, payload, user=owner, db=db)

    remove.assert_called_once_with(db, owner.id, day, payload.version)
    undo.assert_called_once_with(db, owner.id, day, payload.version)
    assert remove_response.data == {"removed": True}
    assert undo_response.data == {"restored": True}


def test_daily_frame_render_cancels_when_claim_update_loses_race():
    session = MagicMock()
    work = SimpleNamespace(generation=2, task_id=uuid4(), deleted_at=None, status="queued")
    session.get.return_value = work
    session.execute.return_value.rowcount = 0

    with patch("app.db.session.SessionLocal", return_value=session):
        with pytest.raises(daily_frame_render.RenderCancelled):
            daily_frame_render.render_work(uuid4(), 2, work.task_id)

    session.commit.assert_not_called()


def test_face_cluster_resolves_empty_candidate_window_without_querying():
    db = MagicMock()
    service = FaceClusterService(db=db, user_id=None)

    assert service._resolve_assigned_candidates(np.array([], dtype=np.int64), None) == {}
    db.query.assert_not_called()


def test_location_trajectory_compacts_sampled_points_and_keeps_totals(sqlite_db):
    owner = User(id=uuid4(), username="trajectory-owner", hashed_password="x")
    sqlite_db.add(owner)
    sqlite_db.commit()
    first_time = datetime(2026, 1, 1, 8, 0)
    last_time = datetime(2026, 1, 1, 8, 4)

    for index in range(5):
        photo = Photo(
            id=uuid4(),
            owner_id=owner.id,
            filename=f"trajectory-{index}.jpg",
            file_path=f"trajectory-{index}.jpg",
            file_type=FileType.image,
            photo_time=datetime(2026, 1, 1, 8, index),
            is_deleted=False,
            size=1,
            width=10,
            height=10,
        )
        sqlite_db.add(photo)
        sqlite_db.add(PhotoMetadata(
            photo_id=photo.id,
            latitude=30.0 + index * 0.2,
            longitude=114.0 + index * 0.2,
            city="三亚市",
        ))
    sqlite_db.commit()

    response = location_crud.get_trajectory_points(
        sqlite_db, owner.id, "2026-01-01", "2026-01-01", max_points=1
    )

    assert response.sampled is True
    assert response.totalPhotos == 5
    assert len(response.points) == 1
    assert response.points[0].photoCount == 5
    assert response.points[0].capturedAt == first_time
    assert response.points[0].endAt == last_time
    assert response.points[0].locationName == "三亚市"
