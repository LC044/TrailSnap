"""End-to-end HTTP tests for the recycle-bin endpoints.

The other recycle-bin tests call the route functions directly, which skips
everything FastAPI does around them: request validation, `response_model`
serialisation, dependency overrides and status codes. Those are exactly the
places where a wrong schema or an un-JSON-serialisable field shows up, so drive
the real ASGI stack here.

Notably this is what catches:
* `photo_ids: null` surviving Pydantic validation as "purge everything"
* the async purge response actually serialising through `BaseResponse[dict]`
* a purge job id being unreadable by a different user (404, not someone else's data)
"""

import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock, patch

from app.api import photo as photo_api
from app.api.deps import get_current_user
from app.crud import photo as photo_crud
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.dependencies import get_db


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def ctx():
    """A TestClient wired to an isolated SQLite library with FK cascade enabled."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    owner = User(username="api-owner", email="api-owner@e.com", hashed_password="x")
    other = User(username="api-other", email="api-other@e.com", hashed_password="x")
    db.add_all([owner, other])
    db.commit()
    db.refresh(owner)
    db.refresh(other)

    app = FastAPI()
    app.include_router(photo_api.router, prefix="/api/photos")

    current = {"user": owner}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    # Storage is stubbed for the whole module: these tests assert on HTTP and SQL,
    # not on unlink() behaviour.
    stub = patch.multiple(
        photo_crud.storage, delete_file=MagicMock(), delete_thumbnails=MagicMock()
    )
    stub.start()
    smart_albums = patch("app.crud.album.trigger_conditional_albums_update")
    smart_albums.start()

    try:
        yield {
            "client": TestClient(app),
            "db": db,
            "owner": owner,
            "other": other,
            "current": current,
        }
    finally:
        stub.stop()
        smart_albums.stop()
        db.close()
        Base.metadata.drop_all(engine)


_UNSET = object()


def _trash(db, owner, n, deleted_at=_UNSET):
    """Create `n` photos already in `owner`'s recycle bin.

    `deleted_at` defaults to "now", matching every real soft-delete path. Pass
    None explicitly to model a row that lost its timestamp.
    """
    stamp = datetime.now() if deleted_at is _UNSET else deleted_at
    photos = [
        Photo(
            filename=f"t{i}.jpg",
            file_path=f"/tmp/{uuid.uuid4().hex}.jpg",
            file_type=FileType.image,
            size=1,
            owner_id=owner.id,
            is_deleted=True,
            deleted_at=stamp,
        )
        for i in range(n)
    ]
    db.add_all(photos)
    db.commit()
    return [str(p.id) for p in photos]


def test_stats_reports_bin_size(ctx):
    _trash(ctx["db"], ctx["owner"], 7)

    res = ctx["client"].get("/api/photos/recycle-bin/stats")

    assert res.status_code == 200
    body = res.json()["data"]
    assert body["total"] == 7
    assert body["retention_days"] >= 1


def test_stats_is_per_user(ctx):
    _trash(ctx["db"], ctx["owner"], 3)
    _trash(ctx["db"], ctx["other"], 5)

    assert ctx["client"].get("/api/photos/recycle-bin/stats").json()["data"]["total"] == 3

    ctx["current"]["user"] = ctx["other"]
    assert ctx["client"].get("/api/photos/recycle-bin/stats").json()["data"]["total"] == 5


def test_purge_with_null_ids_empties_the_whole_bin(ctx):
    _trash(ctx["db"], ctx["owner"], 12)

    # The client sends no ids at all — this is the "empty recycle bin" contract.
    res = ctx["client"].post("/api/photos/recycle-bin/purge", json={"photo_ids": None})

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["mode"] == "sync"
    assert data["deleted"] == 12
    assert ctx["db"].query(Photo).count() == 0


def test_purge_with_omitted_field_also_means_everything(ctx):
    _trash(ctx["db"], ctx["owner"], 4)

    # `photo_ids` defaults to None, so an empty body must behave like null.
    res = ctx["client"].post("/api/photos/recycle-bin/purge", json={})

    assert res.status_code == 200
    assert res.json()["data"]["deleted"] == 4


def test_purge_never_crosses_users(ctx):
    mine = _trash(ctx["db"], ctx["owner"], 2)
    theirs = _trash(ctx["db"], ctx["other"], 3)

    res = ctx["client"].post(
        "/api/photos/recycle-bin/purge", json={"photo_ids": mine + theirs}
    )

    assert res.status_code == 200
    assert res.json()["data"]["deleted"] == 2
    # The other user's photos must be untouched even though their ids were sent.
    remaining = {str(p.id) for p in ctx["db"].query(Photo).all()}
    assert remaining == set(theirs)


def test_purge_of_empty_bin_is_not_an_error(ctx):
    res = ctx["client"].post("/api/photos/recycle-bin/purge", json={"photo_ids": None})

    assert res.status_code == 200
    assert res.json()["data"]["total"] == 0


def test_purge_rejects_explicit_empty_list(ctx):
    res = ctx["client"].post("/api/photos/recycle-bin/purge", json={"photo_ids": []})

    # An empty array is a client bug; `null` is the documented "everything" signal.
    assert res.status_code == 400


def test_purge_rejects_malformed_uuid(ctx):
    res = ctx["client"].post(
        "/api/photos/recycle-bin/purge", json={"photo_ids": ["not-a-uuid"]}
    )

    assert res.status_code == 422


def test_large_purge_returns_a_pollable_job(ctx):
    from app.service import recycle_bin_purge

    ids = _trash(ctx["db"], ctx["owner"], 3)
    # Force the async path without seeding thousands of rows.
    with patch.object(recycle_bin_purge, "ASYNC_PURGE_THRESHOLD", 1), patch.object(
        recycle_bin_purge, "_run_job"
    ):
        res = ctx["client"].post(
            "/api/photos/recycle-bin/purge", json={"photo_ids": ids}
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["mode"] == "async"
        assert data["total"] == 3
        job_id = data["job_id"]

        # The owner can poll it...
        status = ctx["client"].get(f"/api/photos/recycle-bin/purge/{job_id}")
        assert status.status_code == 200
        assert status.json()["data"]["job_id"] == job_id

        # ...a different user cannot.
        ctx["current"]["user"] = ctx["other"]
        assert ctx["client"].get(f"/api/photos/recycle-bin/purge/{job_id}").status_code == 404


def test_unknown_job_id_is_404(ctx):
    res = ctx["client"].get(f"/api/photos/recycle-bin/purge/{uuid.uuid4()}")
    assert res.status_code == 404


def test_restore_all_empties_the_bin_without_listing_ids(ctx):
    _trash(ctx["db"], ctx["owner"], 6)
    _trash(ctx["db"], ctx["other"], 2)

    res = ctx["client"].post("/api/photos/recycle-bin/restore-all")

    assert res.status_code == 200
    assert res.json()["data"]["restored"] == 6
    # Own photos are back, the other user's stay in their bin.
    assert ctx["db"].query(Photo).filter(Photo.owner_id == ctx["owner"].id, Photo.is_deleted == False).count() == 6
    assert ctx["db"].query(Photo).filter(Photo.owner_id == ctx["other"].id, Photo.is_deleted == True).count() == 2


def test_restore_all_on_empty_bin_is_not_an_error(ctx):
    res = ctx["client"].post("/api/photos/recycle-bin/restore-all")
    assert res.status_code == 200
    assert res.json()["data"]["restored"] == 0


def test_list_endpoint_still_paginates(ctx):
    _trash(ctx["db"], ctx["owner"], 5)

    res = ctx["client"].get("/api/photos/recycle-bin", params={"skip": 0, "limit": 2})

    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 2
    # RecyclePhoto must expose deleted_at (the UI computes days-remaining from it)
    # and must not leak the absolute file path.
    assert "deleted_at" in rows[0]
    assert "file_path" not in rows[0]


def test_listing_survives_a_row_with_no_deleted_at(ctx):
    """One malformed row must not 500 the whole listing.

    deleted_at is nullable in the schema, so a legacy row or a manual SQL fix can
    leave it empty. Before RecyclePhoto.deleted_at was made Optional this
    produced a ResponseValidationError and the entire recycle bin became
    unreachable — with no way for the user to clear the offending row.
    """
    _trash(ctx["db"], ctx["owner"], 2)
    _trash(ctx["db"], ctx["owner"], 1, deleted_at=None)

    res = ctx["client"].get("/api/photos/recycle-bin", params={"skip": 0, "limit": 50})

    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 3
    assert sum(1 for r in rows if r["deleted_at"] is None) == 1


def test_bin_with_missing_timestamp_can_still_be_emptied(ctx):
    """The recovery path: such a row must remain purgeable."""
    _trash(ctx["db"], ctx["owner"], 1, deleted_at=None)

    res = ctx["client"].post("/api/photos/recycle-bin/purge", json={"photo_ids": None})

    assert res.status_code == 200
    assert res.json()["data"]["deleted"] == 1
    assert ctx["db"].query(Photo).count() == 0
