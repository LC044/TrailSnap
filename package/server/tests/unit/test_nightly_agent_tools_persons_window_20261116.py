"""2026-11-16 nightly coverage for the date window of the Agent person tool.

The 2026-11-16 backend coverage scan reported ``service/agent/tools.py`` at
92.9% with 29 missed lines.  Besides the deliberately unregistered
``get_travel_history_tool`` (dead code, see the run summary), the
reachable gap is the *end date* filter of ``get_photo_persons_tool``
(line 419): the ``start_date`` branch was covered, the ``end_date``
branch was not.

All DB access goes through a monkeypatched ``SessionLocal`` pointing at
an in-memory SQLite database.
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.agent import tools as agent_tools


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]

OWNER = "nightly-persons-owner"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def library(session):
    owner, photos = _build_library(session)
    return {"owner": owner, "photos": photos}


@pytest.fixture
def tools(session, library, monkeypatch):
    monkeypatch.setattr(agent_tools, "SessionLocal", lambda: session)
    return {t.name: t for t in agent_tools.get_agent_tools(str(library["owner"]), "sess-1")}


def _build_library(session):
    owner = uuid4()
    session.add(User(id=owner, username=OWNER, hashed_password="x"))

    identity = FaceIdentity(
        id=uuid4(),
        owner_id=owner,
        identity_name="小李",
        description="朋友",
        tags=["同事"],
        is_deleted=False,
        is_hidden=False,
    )
    session.add(identity)

    photos = []
    for name, when in (
        ("early.jpg", datetime(2025, 3, 1, 10, 0)),
        ("late.jpg", datetime(2025, 8, 1, 10, 0)),
    ):
        photo = Photo(
            id=uuid4(),
            owner_id=owner,
            filename=name,
            file_path=name,
            file_type=FileType.image,
            size=1,
            is_deleted=False,
            photo_time=when,
        )
        session.add(photo)
        session.add(
            Face(
                photo_id=photo.id,
                face_identity_id=identity.id,
                face_rect=None,
                face_confidence=0.9,
                is_deleted=False,
            )
        )
        photos.append(photo)
    session.flush()
    return owner, photos


def test_the_person_tool_applies_the_end_date_filter(tools):

    payload = json.loads(tools["get_photo_persons_tool"].func(start_date="2025-01-01", end_date="2025-05-01"))

    assert [item["name"] for item in payload] == ["小李"]


def test_the_person_tool_returns_every_person_without_a_window(tools):

    payload = json.loads(tools["get_photo_persons_tool"].func())

    assert [item["name"] for item in payload] == ["小李"]


def test_the_person_tool_ignores_an_invalid_end_date(tools):

    payload = json.loads(tools["get_photo_persons_tool"].func(end_date="not-a-date"))

    assert [item["name"] for item in payload] == ["小李"]


def test_the_person_tool_reports_when_nothing_matches(tools):

    result = tools["get_photo_persons_tool"].func(start_date="2030-01-01")

    assert result == "没有找到照片的人物信息。"



