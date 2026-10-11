"""Regression coverage for annual memories backed by desktop SQLite vectors."""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import annual_report
from app.api.deps import get_current_user
from app.crud.annual_report import find_best_match_photo
from app.crud.search_vector import EASTER_EGG_VECTOR, SEASON_VECTORS
from app.db.base import Base
from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType, ImageType, Photo
from app.dependencies import get_db


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def report_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def add_photo(db, owner_id, embedding, **overrides):
    photo = Photo(
        id=uuid4(), owner_id=owner_id, file_path=f"/{uuid4()}.jpg",
        photo_time=datetime(2025, 4, 1), file_type=FileType.image,
        image_type=ImageType.CAMERA, is_deleted=False,
    )
    for key, value in overrides.items():
        setattr(photo, key, value)
    db.add(photo)
    db.add(ImageVector(photo_id=photo.id, embedding=embedding))
    db.commit()
    return photo


def test_sqlite_vector_search_ranks_and_filters_real_orm_rows(report_session):
    db = report_session
    owner_id = uuid4()
    target = [1.0, 0.0] + [0.0] * 510
    add_photo(db, owner_id, [0.0, 1.0] + [0.0] * 510)
    best = add_photo(db, owner_id, [0.9, 0.1] + [0.0] * 510)
    add_photo(db, uuid4(), target)
    add_photo(db, owner_id, target, is_deleted=True)
    add_photo(db, owner_id, target, image_type=ImageType.SCREENSHOT)
    add_photo(db, owner_id, target, photo_time=datetime(2025, 6, 1))
    add_photo(db, owner_id, target, photo_time=datetime(2024, 4, 1))

    result = find_best_match_photo(
        db, datetime(2025, 1, 1), datetime(2025, 12, 31), target,
        months=[3, 4, 5], user_id=owner_id,
    )
    assert result.id == best.id


@pytest.mark.parametrize("endpoint,embedding", [
    ("season", SEASON_VECTORS["春"]),
    ("easter-egg", EASTER_EGG_VECTOR),
])
def test_annual_vector_endpoints_with_sqlite_photos(report_session, endpoint, embedding):
    db = report_session
    owner_id = uuid4()
    photo = add_photo(db, owner_id, embedding)
    app = FastAPI()
    app.include_router(annual_report.router, prefix="/annual-report")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner_id)

    with TestClient(app) as client:
        response = client.get(f"/annual-report/{endpoint}", params={
            "start_time": "2025-01-01T00:00:00",
            "end_time": "2025-12-31T23:59:59",
        })
    assert response.status_code == 200
    data = response.json()
    url = (data["seasonList"][0]["representativePhoto"]
           if endpoint == "season" else data["bestPhotoUrl"])
    assert str(photo.id) in url
