"""Nightly watch gap coverage for app/api/agent.py, app/api/moment.py, app/api/nav.py."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import agent as agent_api
from app.api import moment as moment_api
from app.api import nav as nav_api
from app.schemas.nav import NavItemRef, NavItemsResponse, NavItemsUpdate, ResolvedNavItem


pytestmark = [pytest.mark.smoke]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _agent_session(owner_id=None, sid=None):
    return SimpleNamespace(
        id=sid or uuid4(),
        user_id=owner_id or uuid4(),
        title="t",
        is_pinned=False,
    )


def _config(items):
    return SimpleNamespace(nav=SimpleNamespace(items=items))


def _captions():
    return [SimpleNamespace(day=date(2025, 8, 5), caption="hi", source="manual")]


# ===========================================================================
# api/agent.py
# ===========================================================================


def test_agent_chat_streaming_returns_streaming_response():
    user = _user()
    db = MagicMock()
    request = agent_api.ChatRequest(message="hi", session_id=None, stream=True)

    async def fake_stream(*args, **kwargs):
        if False:
            yield b""

    with patch.object(agent_api.agent_crud, "get_session", return_value=None), \
         patch.object(agent_api.agent_crud, "create_session", return_value=_agent_session(owner_id=user.id)), \
         patch.object(agent_api, "stream_chat_with_agent", side_effect=fake_stream):
        response = agent_api.chat_endpoint(request=request, current_user=user, db=db)

    assert response.media_type == "text/event-stream"


def test_agent_list_sessions_forwards_skip_limit_and_returns_list():
    user = _user()
    db = MagicMock()
    sessions = [_agent_session(owner_id=user.id) for _ in range(3)]

    with patch.object(
        agent_api.agent_crud, "get_sessions_by_user", return_value=sessions
    ) as get_sessions:
        result = agent_api.get_sessions(skip=5, limit=25, current_user=user, db=db)

    get_sessions.assert_called_once_with(db, user_id=user.id, skip=5, limit=25)
    assert result is sessions


def test_agent_create_session_returns_session():
    user = _user()
    db = MagicMock()
    session_in = agent_api.AgentSessionCreate(title="x", status="active")

    with patch.object(
        agent_api.agent_crud, "create_session", return_value=_agent_session(owner_id=user.id)
    ) as create:
        result = agent_api.create_session(session_in=session_in, current_user=user, db=db)

    create.assert_called_once_with(db, obj_in=session_in, user_id=user.id)
    assert result is not None


def test_agent_get_messages_returns_404_when_session_missing():
    user = _user()
    db = MagicMock()

    with patch.object(agent_api.agent_crud, "get_session", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.get_session_messages(
                session_id=str(uuid4()), skip=0, limit=10, current_user=user, db=db
            )

    assert exc_info.value.status_code == 404


def test_agent_get_messages_returns_403_for_other_user():
    user = _user()
    db = MagicMock()

    with patch.object(
        agent_api.agent_crud, "get_session", return_value=_agent_session(owner_id=uuid4())
    ):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.get_session_messages(
                session_id=str(uuid4()), skip=0, limit=10, current_user=user, db=db
            )

    assert exc_info.value.status_code == 403


def test_agent_get_messages_returns_messages_for_owner():
    user = _user()
    db = MagicMock()
    messages = [SimpleNamespace(id=1, content="hi")]

    with patch.object(
        agent_api.agent_crud,
        "get_session",
        return_value=_agent_session(owner_id=user.id),
    ), patch.object(
        agent_api.agent_crud, "get_messages_by_session", return_value=messages
    ) as get_messages:
        result = agent_api.get_session_messages(
            session_id=str(uuid4()), skip=2, limit=5, current_user=user, db=db
        )

    get_messages.assert_called_once()
    assert result is messages


def test_agent_delete_messages_returns_404_when_session_missing():
    user = _user()
    db = MagicMock()

    with patch.object(agent_api.agent_crud, "get_session", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.delete_messages(
                session_id=str(uuid4()), message_ids=None, current_user=user, db=db
            )

    assert exc_info.value.status_code == 404


def test_agent_delete_messages_returns_403_for_other_user():
    user = _user()
    db = MagicMock()

    with patch.object(
        agent_api.agent_crud, "get_session", return_value=_agent_session(owner_id=uuid4())
    ):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.delete_messages(
                session_id=str(uuid4()), message_ids=None, current_user=user, db=db
            )

    assert exc_info.value.status_code == 403


def test_agent_delete_messages_with_ids_issues_query_and_commits():
    user = _user()
    db = MagicMock()
    session = _agent_session(owner_id=user.id)
    query = db.query.return_value.filter.return_value
    query.delete.return_value = 1

    with patch.object(
        agent_api.agent_crud, "get_session", return_value=session
    ):
        result = agent_api.delete_messages(
            session_id=str(uuid4()),
            message_ids="1,2,not-a-number,3",
            current_user=user,
            db=db,
        )

    db.query.assert_called_once()
    query.delete.assert_called_once_with(synchronize_session=False)
    db.commit.assert_called_once()
    assert result["message"] == "Messages deleted successfully"


def test_agent_delete_messages_with_only_invalid_ids_runs_no_delete():
    user = _user()
    db = MagicMock()
    session = _agent_session(owner_id=user.id)

    with patch.object(
        agent_api.agent_crud, "get_session", return_value=session
    ), patch.object(
        agent_api.agent_crud, "delete_messages_by_session"
    ) as delete_all:
        result = agent_api.delete_messages(
            session_id=str(session.id),
            message_ids="abc,def",
            current_user=user,
            db=db,
        )

    db.query.assert_not_called()
    delete_all.assert_not_called()
    assert result["message"] == "Messages deleted successfully"


def test_agent_delete_messages_without_ids_clears_whole_session():
    user = _user()
    db = MagicMock()
    session = _agent_session(owner_id=user.id)

    with patch.object(
        agent_api.agent_crud, "get_session", return_value=session
    ), patch.object(
        agent_api.agent_crud, "delete_messages_by_session", return_value=True
    ) as delete_all:
        result = agent_api.delete_messages(
            session_id=str(session.id),
            message_ids=None,
            current_user=user,
            db=db,
        )

    delete_all.assert_called_once_with(db, str(session.id))
    assert result["message"] == "Messages deleted successfully"


# ===========================================================================
# api/moment.py
# ===========================================================================


def test_moment_list_captions_rejects_inverted_range():
    with pytest.raises(HTTPException) as exc_info:
        moment_api.list_day_captions(
            start=date(2025, 8, 10),
            end=date(2025, 8, 1),
            scope_type="all",
            scope_id=None,
            current_user=_user(),
            db=MagicMock(),
        )

    assert exc_info.value.status_code == 400
    assert "start" in str(exc_info.value.detail)


def test_moment_list_captions_rejects_range_over_366_days():
    with pytest.raises(HTTPException) as exc_info:
        moment_api.list_day_captions(
            start=date(2020, 1, 1),
            end=date(2022, 1, 1),
            scope_type="all",
            scope_id=None,
            current_user=_user(),
            db=MagicMock(),
        )

    assert exc_info.value.status_code == 400
    assert "366" in str(exc_info.value.detail)


def test_moment_list_captions_returns_captions_for_owner():
    user = _user()
    db = MagicMock()

    with patch.object(
        moment_api.moment_crud, "list_captions", return_value=_captions()
    ) as list_captions:
        result = moment_api.list_day_captions(
            start=date(2025, 8, 1),
            end=date(2025, 8, 10),
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )

    list_captions.assert_called_once_with(
        db, user.id, "all", None, date(2025, 8, 1), date(2025, 8, 10)
    )
    assert result == _captions()


def test_moment_upsert_caption_rejects_blank_text():
    payload = SimpleNamespace(caption="   ")

    with pytest.raises(HTTPException) as exc_info:
        moment_api.upsert_day_caption(
            day=date(2025, 8, 5),
            payload=payload,
            scope_type="all",
            scope_id=None,
            current_user=_user(),
            db=MagicMock(),
        )

    assert exc_info.value.status_code == 400
    assert "caption" in str(exc_info.value.detail)


def test_moment_upsert_caption_strips_whitespace_and_calls_crud():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(caption="  hello  ")
    upserted = SimpleNamespace(day=date(2025, 8, 5), caption="hello", source="manual")

    with patch.object(
        moment_api.moment_crud, "upsert_caption", return_value=upserted
    ) as upsert:
        result = moment_api.upsert_day_caption(
            day=date(2025, 8, 5),
            payload=payload,
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )

    upsert.assert_called_once_with(
        db, user.id, "all", None, date(2025, 8, 5), "hello", source="manual"
    )
    assert result is upserted


def test_moment_delete_caption_returns_deleted_flag():
    user = _user()
    db = MagicMock()

    with patch.object(
        moment_api.moment_crud, "delete_caption", return_value=False
    ) as delete_caption:
        result = moment_api.delete_day_caption(
            day=date(2025, 8, 5),
            scope_type="all",
            scope_id=None,
            current_user=user,
            db=db,
        )

    delete_caption.assert_called_once_with(db, user.id, "all", None, date(2025, 8, 5))
    assert result == {"deleted": False}


def test_moment_list_day_locations_rejects_inverted_range():
    with pytest.raises(HTTPException) as exc_info:
        moment_api.list_day_locations(
            start=date(2025, 8, 10),
            end=date(2025, 8, 1),
            timezone="UTC",
            top_n=3,
            current_user=_user(),
            db=MagicMock(),
        )

    assert exc_info.value.status_code == 400


def test_moment_list_day_locations_calls_crud_with_day_bounds():
    user = _user()
    db = MagicMock()
    expected = [SimpleNamespace(day=date(2025, 8, 5), locations=[])]

    with patch.object(
        moment_api.moment_crud, "get_day_locations", return_value=expected
    ) as get_locations, patch.object(
        moment_api, "day_bounds_utc", side_effect=lambda d, tz: (d.isoformat(), d.isoformat())
    ):
        result = moment_api.list_day_locations(
            start=date(2025, 8, 5),
            end=date(2025, 8, 5),
            timezone="Asia/Shanghai",
            top_n=3,
            current_user=user,
            db=db,
        )

    get_locations.assert_called_once()
    assert result is expected


def test_moment_list_day_highlights_rejects_inverted_range():
    with pytest.raises(HTTPException) as exc_info:
        moment_api.list_day_highlights(
            start=date(2025, 8, 10),
            end=date(2025, 8, 1),
            limit=9,
            current_user=_user(),
            db=MagicMock(),
        )

    assert exc_info.value.status_code == 400


def test_moment_list_day_highlights_calls_service_with_limit():
    user = _user()
    db = MagicMock()
    expected = [SimpleNamespace(day=date(2025, 8, 5), photo_ids=[1])]

    with patch.object(
        moment_api, "get_range_highlights", return_value=expected
    ) as get_highlights:
        result = moment_api.list_day_highlights(
            start=date(2025, 8, 5),
            end=date(2025, 8, 10),
            limit=9,
            current_user=user,
            db=db,
        )

    get_highlights.assert_called_once_with(
        db, user.id, date(2025, 8, 5), date(2025, 8, 10), limit=9
    )
    assert result is expected


@pytest.mark.asyncio
async def test_moment_generate_caption_rejects_non_all_scope():
    request = SimpleNamespace(scope_type="album", day=date(2025, 8, 5))

    with pytest.raises(HTTPException) as exc_info:
        await moment_api.generate_day_caption(request=request, current_user=_user(), db=MagicMock())

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_moment_generate_caption_sync_returns_result_dict():
    user = _user()
    db = MagicMock()
    request = SimpleNamespace(
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        timezone="UTC",
        style="casual",
        connection_id=None,
        model_name=None,
        stream=False,
        force=False,
    )
    expected = {"caption": "hi", "cached": False, "source": "ai", "model_name": "m"}

    with patch.object(
        moment_api, "generate_caption_sync", AsyncMock(return_value=expected)
    ) as sync_gen:
        result = await moment_api.generate_day_caption(request=request, current_user=user, db=db)

    sync_gen.assert_called_once()
    assert result is expected


@pytest.mark.asyncio
async def test_moment_generate_caption_value_error_maps_to_400():
    request = SimpleNamespace(
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        timezone="UTC",
        style=None,
        connection_id=None,
        model_name=None,
        stream=False,
        force=False,
    )

    with patch.object(
        moment_api, "generate_caption_sync",
        AsyncMock(side_effect=ValueError("no photos")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await moment_api.generate_day_caption(
                request=request, current_user=_user(), db=MagicMock()
            )

    assert exc_info.value.status_code == 400
    assert "no photos" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_moment_generate_caption_unexpected_error_maps_to_500():
    request = SimpleNamespace(
        scope_type="all",
        scope_id=None,
        day=date(2025, 8, 5),
        timezone="UTC",
        style=None,
        connection_id=None,
        model_name=None,
        stream=False,
        force=False,
    )

    with patch.object(
        moment_api, "generate_caption_sync",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await moment_api.generate_day_caption(
                request=request, current_user=_user(), db=MagicMock()
            )

    assert exc_info.value.status_code == 500
    assert "boom" in str(exc_info.value.detail)


# ===========================================================================
# api/nav.py
# ===========================================================================


def test_nav_resolve_album_returns_resolved_item():
    user_id = uuid4()
    album_id = uuid4()
    album = SimpleNamespace(
        id=album_id,
        owner_id=user_id,
        name="Vacation",
        cover_id=uuid4(),
        num_photos=12,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = album

    item = nav_api.resolve_album(str(album_id), user_id, db)

    assert item is not None
    assert item.entity_type == "album"
    assert item.name == "Vacation"
    assert item.photo_count == 12
    assert item.route_path == f"/album/{album_id}"


def test_nav_resolve_album_returns_none_when_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert nav_api.resolve_album(str(uuid4()), uuid4(), db) is None


def test_nav_resolve_classification_returns_none_when_tag_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert nav_api.resolve_classification(str(uuid4()), uuid4(), db) is None


def test_nav_resolve_location_returns_none_when_no_photos():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.scalar.return_value = 0

    assert nav_api.resolve_location("Beijing", uuid4(), db) is None


def test_nav_resolve_single_entity_returns_none_for_unknown_type():
    ref = SimpleNamespace(entity_type="unknown", entity_id="x")
    assert nav_api.resolve_single_entity(ref, uuid4(), MagicMock()) is None


def test_nav_get_items_returns_resolved_items_response():
    user = _user()
    db = MagicMock()
    resolved = [
        ResolvedNavItem(
            entity_type="album",
            entity_id=str(uuid4()),
            name="Vacation",
            cover_photo_id=None,
            route_path="/album/x",
            photo_count=3,
        )
    ]

    with patch.object(nav_api, "resolve_nav_items", return_value=resolved):
        result = nav_api.get_nav_items(current_user=user, db=db)

    assert isinstance(result.data, NavItemsResponse)
    assert result.data.items == resolved


def test_nav_update_items_rejects_invalid_uuid():
    body = NavItemsUpdate(
        items=[NavItemRef(entity_type="album", entity_id="not-a-uuid")]
    )

    with pytest.raises(HTTPException) as exc_info:
        nav_api.update_nav_items(body=body, current_user=_user(), db=MagicMock())

    assert exc_info.value.status_code == 400


def test_nav_update_items_accepts_valid_refs_and_resolves():
    user = _user()
    db = MagicMock()
    album_uuid = str(uuid4())
    body = NavItemsUpdate(
        items=[
            NavItemRef(entity_type="album", entity_id=album_uuid),
            NavItemRef(entity_type="location", entity_id="Beijing"),
        ]
    )

    with patch.object(
        nav_api.config_manager, "update_user_config"
    ) as update_config, patch.object(
        nav_api, "resolve_nav_items", return_value=[]
    ):
        result = nav_api.update_nav_items(body=body, current_user=user, db=db)

    update_config.assert_called_once()
    assert result.data is not None


def test_nav_delete_item_filters_out_target_and_returns_remaining():
    user = _user()
    db = MagicMock()
    keep = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    target = NavItemRef(entity_type="album", entity_id=str(uuid4()))

    with patch.object(
        nav_api.config_manager, "get_user_config", return_value=_config([keep, target])
    ), patch.object(
        nav_api.config_manager, "update_user_config"
    ) as update_config, patch.object(
        nav_api, "resolve_nav_items", return_value=[]
    ):
        result = nav_api.delete_nav_item(
            entity_type="album",
            entity_id=target.entity_id,
            current_user=user,
            db=db,
        )

    update_config.assert_called_once()
    persisted_items = update_config.call_args.args[1]["nav"]["items"]
    assert persisted_items == [keep.model_dump()]
    assert result.data is not None


def test_nav_resolve_nav_items_prunes_dead_references_and_persists():
    user = _user()
    user_id = user.id
    db = MagicMock()

    alive_ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    dead_ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    alive_resolved = ResolvedNavItem(
        entity_type="album",
        entity_id=alive_ref.entity_id,
        name="Alive",
        cover_photo_id=None,
        route_path=f"/album/{alive_ref.entity_id}",
        photo_count=3,
    )

    with patch.object(
        nav_api.config_manager, "get_user_config",
        return_value=_config([alive_ref, dead_ref]),
    ), patch.object(
        nav_api, "resolve_album",
        side_effect=lambda eid, uid, _db: alive_resolved if eid == alive_ref.entity_id else None,
    ), patch.object(
        nav_api.config_manager, "update_user_config"
    ) as update_config:
        items = nav_api.resolve_nav_items(user_id, db)

    assert items == [alive_resolved]
    update_config.assert_called_once()
    assert update_config.call_args.args[1]["nav"]["items"] == [alive_ref.model_dump()]
