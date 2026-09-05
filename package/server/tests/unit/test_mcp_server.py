from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from mcp import Client
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.agent_token import AgentToken
from app.db.models.album import Album
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.service import mcp_server


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


@pytest.fixture()
def mcp_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(mcp_server, "SessionLocal", factory)
    try:
        yield factory
    finally:
        engine.dispose()


def _auth(user_id, scopes):
    return auth_context_var.set(AuthenticatedUser(AccessToken(
        token="ts_test",
        client_id="test-client",
        subject=str(user_id),
        scopes=scopes,
    )))


@pytest.mark.asyncio
async def test_mcp_protocol_lists_tools_and_owner_scopes_results(mcp_db):
    owner, stranger = uuid4(), uuid4()
    owned_photo, foreign_photo = uuid4(), uuid4()
    person = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="旅行伙伴", is_deleted=False, is_hidden=False)
    with mcp_db() as db:
        db.add_all([
            User(id=owner, username="owner", hashed_password="x"),
            User(id=stranger, username="stranger", hashed_password="x"),
            Photo(id=owned_photo, owner_id=owner, filename="west-lake.jpg", file_path="west-lake.jpg", file_type=FileType.image, photo_time=datetime(2025, 5, 2, 10), is_deleted=False),
            Photo(id=foreign_photo, owner_id=stranger, filename="private.jpg", file_path="private.jpg", file_type=FileType.image, photo_time=datetime(2025, 5, 2, 11), is_deleted=False),
            PhotoMetadata(photo_id=owned_photo, city="杭州", address="西湖"),
            PhotoMetadata(photo_id=foreign_photo, city="杭州", address="西湖"),
            Album(id=uuid4(), owner_id=owner, name="杭州旅行", type="user", num_photos=1),
            Album(id=uuid4(), owner_id=stranger, name="他人私密相册", type="user", num_photos=1),
            person,
        ])
        db.flush()
        db.add(Face(photo_id=owned_photo, face_identity_id=person.id, is_deleted=False))
        db.commit()

    context_token = _auth(owner, list(mcp_server.READ_SCOPES))
    try:
        async with Client(mcp_server.mcp) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "search_photos", "list_albums", "list_people",
                "investigate_memory", "get_person_timeline",
            }
            assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools.tools)
            assert all(tool.annotations and tool.annotations.destructive_hint is False for tool in tools.tools)

            search = await client.call_tool("search_photos", {"location": "杭州"})
            assert search.structured_content["total"] == 1
            assert search.structured_content["photos"][0]["photo_id"] == str(owned_photo)

            albums = await client.call_tool("list_albums", {})
            assert [item["name"] for item in albums.structured_content["albums"]] == ["杭州旅行"]

            people = await client.call_tool("list_people", {})
            assert people.structured_content["people"][0]["identity_id"] == str(person.id)
    finally:
        auth_context_var.reset(context_token)


@pytest.mark.asyncio
async def test_mcp_tool_rejects_missing_scope(mcp_db):
    owner = uuid4()
    with mcp_db() as db:
        db.add(User(id=owner, username="owner", hashed_password="x"))
        db.commit()
    context_token = _auth(owner, ["albums:read"])
    try:
        async with Client(mcp_server.mcp) as client:
            result = await client.call_tool("search_photos", {})
            assert result.is_error is True
            assert "photos:read" in result.content[0].text
    finally:
        auth_context_var.reset(context_token)


@pytest.mark.asyncio
async def test_agent_token_verifier_rejects_expired_and_preserves_scopes(mcp_db):
    owner = uuid4()
    with mcp_db() as db:
        db.add(User(id=owner, username="owner", hashed_password="x"))
        db.add_all([
            AgentToken(id=uuid4(), user_id=owner, name="mcp", token="ts_valid", expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1), scopes=["photos:read"], is_deleted=False),
            AgentToken(id=uuid4(), user_id=owner, name="expired", token="ts_expired", expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1), scopes=list(mcp_server.READ_SCOPES), is_deleted=False),
        ])
        db.commit()

    verifier = mcp_server.AgentTokenVerifier()
    access = await verifier.verify_token("ts_valid")
    assert access is not None
    assert access.subject == str(owner)
    assert access.scopes == ["photos:read"]
    assert await verifier.verify_token("ts_expired") is None
    assert await verifier.verify_token("jwt_not_allowed") is None
