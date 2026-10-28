from contextlib import contextmanager
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.user import User
from app.db.models.photo import Photo, FileType
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_vector import ImageVector
from app.service.agent import photo_search
from app.service.agent import search_planner

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


@pytest.fixture
def library():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    owner, other = uuid4(), uuid4()
    db.add_all([User(id=owner, username="search-owner", hashed_password="x"),
                User(id=other, username="search-other", hashed_password="x")])
    people = [FaceIdentity(id=uuid4(), owner_id=owner, identity_name=name,
                           is_deleted=False, is_hidden=False) for name in ("我", "小李")]
    db.add_all(people)
    photos = []
    for index in range(65):
        photo = Photo(id=uuid4(), owner_id=owner, filename=f"{index}.jpg", file_path=f"{index}.jpg",
                      file_type=FileType.image, size=10, is_deleted=False,
                      photo_time=datetime(2025, 12, 31, 23, 59, 59, 900000))
        photos.append(photo)
        db.add(photo)
        db.add(PhotoMetadata(photo_id=photo.id, city="西安市"))
        for person in people:
            db.add(Face(photo_id=photo.id, face_identity_id=person.id, is_deleted=False))
    foreign = Photo(id=uuid4(), owner_id=other, filename="other.jpg", file_path="other.jpg", size=10,
                    file_type=FileType.image, is_deleted=False, photo_time=datetime(2025, 1, 1))
    db.add(foreign)
    db.commit()
    yield db, owner, other, people, photos, foreign
    db.close()
    engine.dispose()


def test_combines_time_location_and_all_people_without_duplicate_photos(library):
    db, owner, _, people, photos, _ = library
    ids = photo_search.search_photo_ids(db, str(owner), start_date="2025-01-01", end_date="2025-12-31",
                                      location="西安", person_ids=[str(p.id) for p in people])
    assert len(ids) == 65 and set(ids) == {str(p.id) for p in photos}
    face = db.query(Face).filter(Face.photo_id == photos[0].id, Face.face_identity_id == people[0].id).one()
    face.is_deleted = True
    db.commit()
    assert len(photo_search.search_photo_ids(db, str(owner), person_ids=[str(p.id) for p in people])) == 64
    assert len(photo_search.search_photo_ids(db, str(owner), person_ids=[str(p.id) for p in people], people_match="any")) == 65
    assert len(photo_search.search_photo_ids(db, str(owner), min_people=2)) == 64
    assert len(photo_search.search_photo_ids(db, str(owner), max_people=1)) == 1
    assert photo_search.search_photo_ids(db, str(owner), location="成都") == []
    assert photo_search.search_photo_ids(db, str(owner), start_date="2026-01-01") == []
    with pytest.raises(ValueError):
        photo_search.search_photo_ids(db, str(owner), start_date="2026-01-01", end_date="2025-01-01")


def test_complete_snapshot_pages_restore_order_and_recheck_permissions(library):
    db, owner, other, _, photos, foreign = library
    ordered = [str(p.id) for p in photos]
    result = photo_search.save_search_result(db, str(owner), None, ordered + [str(foreign.id)], {"location": "西安"})
    first = photo_search.search_result_page(db, str(owner), result["id"], 0, 60)
    second = photo_search.search_result_page(db, str(owner), result["id"], 60, 60)
    assert first["total"] == 65 and first["next_offset"] == 60
    assert [p["id"] for p in first["photos"] + second["photos"]] == ordered
    assert second["next_offset"] is None
    photos[0].is_deleted = True
    db.commit()
    after_deletion = photo_search.search_result_page(db, str(owner), result["id"], first["next_offset"], 60)
    assert [p["id"] for p in after_deletion["photos"]] == ordered[60:]
    restored = photo_search.search_result_page(db, str(owner), result["id"], 0, 100)
    assert restored["total"] == 64
    assert ordered[0] not in [p["id"] for p in restored["photos"]]
    with pytest.raises(ValueError):
        photo_search.search_result_page(db, str(other), result["id"], 0, 60)


def test_tools_publish_only_find_results_and_search_mode_is_read_only(library, monkeypatch):
    db, owner, other, people, _, _ = library
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(photo_search, "SessionLocal", session)
    tools = photo_search.get_photo_search_tools(str(owner))
    assert {t.name for t in tools} == {"lookup_search_people", "search_library_photos"}
    lookup, search = tools
    found = json.loads(lookup.invoke({"query": "小李"}))
    assert found["people"] == [{"id": str(people[1].id), "name": "小李"}]
    monkeypatch.setattr("app.service.agent.album_p0.photo_contexts", lambda *args: [])
    context = json.loads(search.invoke({"purpose": "context", "location": "西安"}))
    assert context["total"] == 65 and "search_result" not in context
    found = json.loads(search.invoke({"purpose": "find", "location": "西安"}))
    assert found["search_result"]["total"] == 65
    empty = json.loads(search.invoke({"purpose": "find", "location": "成都"}))
    assert empty["search_result"]["total"] == 0
    foreign_person = FaceIdentity(id=uuid4(), owner_id=other, identity_name="外人", is_deleted=False, is_hidden=False)
    db.add(foreign_person); db.commit()
    assert "error" in json.loads(search.invoke({"purpose": "find", "person_ids": [str(foreign_person.id)]}))
    search_only = photo_search.get_photo_search_tools(str(owner), search_only=True)[1]
    assert search_only.return_direct is True and search.return_direct is False
    assert "search_result" in json.loads(search_only.invoke({"purpose": "context"}))


def test_sqlite_semantic_search_ranks_only_filtered_candidates(library, monkeypatch):
    db, owner, _, _, photos, foreign = library
    a, b = [1.0, 0.0] + [0.0] * 510, [0.0, 1.0] + [0.0] * 510
    db.add_all([ImageVector(photo_id=photos[0].id, embedding=a),
                ImageVector(photo_id=photos[1].id, embedding=b),
                ImageVector(photo_id=foreign.id, embedding=a)])
    db.commit()
    monkeypatch.setattr(photo_search, "get_embedding", lambda *args: a)
    assert photo_search.search_photo_ids(db, str(owner), location="西安", description="夕阳") == [str(photos[0].id)]
    assert photo_search.search_photo_ids(db, str(owner), location="成都", description="夕阳") == []


def test_exact_city_search_never_requires_optional_fields_or_model(library, monkeypatch):
    db, owner, _, _, photos, _ = library
    db.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photos[0].id).update({PhotoMetadata.city: "上海市"}, synchronize_session=False)
    db.commit()
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(search_planner, "SessionLocal", session)
    model = MagicMock()
    model.bind.side_effect = AssertionError("exact entity must not call model")
    result = search_planner.PhotoSearchExecutor(model, str(owner), None)._search("上海")
    assert result["total"] == 1
    assert result["search_result"]["filters"]["description"] is None
    assert result["search_result"]["filters"]["person_ids"] is None
    model.bind.assert_not_called()


@pytest.mark.parametrize("query,payload,location,description", [
    ("上海日落", {"location": "上海", "description": "日落", "missing_conditions": ["person_ids"]}, "上海", "日落"),
    ("海边日落", {"description": "海边日落"}, None, "海边日落"),
    ("海边日落", {"location": "海边", "description": "日落"}, None, "海边日落"),
    ("室内聚会", {"location": "室内", "description": "聚会"}, None, "室内聚会"),
    ("上海", {"location": "上海", "people": None, "unsupported": ["person_ids", "description"]}, "上海", None),
])
def test_structured_extraction_has_no_optional_field_gate(query, payload, location, description):
    model = MagicMock()
    model.bind.return_value.invoke.return_value = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
    plan = search_planner.extract_search_plan(model, query)
    assert plan.location == location and plan.description == description
    assert plan.unsupported == []
    assert model.bind.call_count == 1


def test_scene_search_uses_all_locations_while_city_scene_restricts_candidates(library, monkeypatch):
    db, owner, _, _, photos, _ = library
    db.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photos[0].id).update({PhotoMetadata.city: "上海"}, synchronize_session=False)
    a, b = [1.0, 0.0] + [0.0] * 510, [0.0, 1.0] + [0.0] * 510
    db.add_all([ImageVector(photo_id=photos[0].id, embedding=a), ImageVector(photo_id=photos[1].id, embedding=a), ImageVector(photo_id=photos[2].id, embedding=b)])
    db.commit()
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(search_planner, "SessionLocal", session)
    monkeypatch.setattr(photo_search, "get_embedding", lambda *args: a)
    model = MagicMock()
    model.bind.return_value.invoke.return_value = SimpleNamespace(content='{"location":"海边","description":"日落"}')
    executor = search_planner.PhotoSearchExecutor(model, str(owner), None)
    scene = executor._search("海边日落")
    assert scene["total"] == 2
    assert scene["search_result"]["filters"]["location"] is None
    assert scene["search_result"]["filters"]["description"] == "海边日落"
    model.bind.return_value.invoke.return_value = SimpleNamespace(content='{"location":"上海","description":"日落"}')
    city_scene = executor._search("上海日落")
    assert city_scene["total"] == 1
    # The model can identify the scene while accidentally omitting the city.
    # Resolve the city explicitly named by the user from actual library data.
    model.bind.return_value.invoke.return_value = SimpleNamespace(content='{"description":"日落"}')
    grounded = executor._search("上海日落")
    assert grounded["total"] == 1
    assert grounded["search_result"]["filters"]["location"] == "上海"


def test_parser_accepts_literal_dict_and_blank_unused_optional_fields():
    model = MagicMock()
    model.bind.return_value.invoke.return_value = SimpleNamespace(content="{'location':'海边','description':'日落','people':None,'start_date':'','end_date':'','min_people':'','max_people':'','tags':''}")
    plan = search_planner.extract_search_plan(model, "海边日落")
    assert plan.description == "海边日落" and plan.location is None
    assert plan.start_date is None and plan.people == [] and plan.tags == []
    assert model.bind.call_count == 1


def test_grounding_rejects_invented_place_and_retains_explicit_unknown_place(library):
    db, owner, *_ = library
    plan = search_planner.ground_plan_location(db, str(owner), search_planner.SearchPlan(location="上海", description="海边日落"), "海边日落")
    assert plan.location is None and plan.description == "海边日落"
    absent = search_planner.ground_plan_location(db, str(owner), search_planner.SearchPlan(location="巴黎", description="日落"), "巴黎日落")
    assert absent.location == "巴黎"


def test_planner_resolves_people_server_side_and_asks_only_for_actual_names(library):
    db, owner, _, people, _, _ = library
    filters = search_planner.resolve_plan(db, str(owner), search_planner.SearchPlan(people=["我", "小李"]))
    assert filters["person_ids"] == [str(person.id) for person in people]
    with pytest.raises(ValueError, match="女朋友"):
        search_planner.resolve_plan(db, str(owner), search_planner.SearchPlan(people=["女朋友"]))


def test_plan_retries_invalid_json_once_without_format_requirement():
    model = MagicMock()
    model.bind.return_value.invoke.side_effect = [SimpleNamespace(content="invalid"), SimpleNamespace(content='```json\n{"description":"海边日落"}\n```')]
    plan = search_planner.extract_search_plan(model, "海边日落")
    assert plan.description == "海边日落"
    assert model.bind.call_count == 2
    assert "response_format" not in model.bind.call_args.kwargs
    model.bind.return_value.invoke.side_effect = RuntimeError("provider failed")
    with pytest.raises(ValueError, match="暂时未能理解"):
        search_planner.extract_search_plan(model, "上海日落")


def test_model_stream_wrapper_accepts_empty_provider_frames():
    from app.service.agent.service import FixedChatOpenAI
    instance = FixedChatOpenAI.__new__(FixedChatOpenAI)
    with patch("langchain_openai.ChatOpenAI._convert_chunk_to_generation_chunk", return_value=None):
        assert instance._convert_chunk_to_generation_chunk({"choices": []}, MagicMock(), None) is None


@pytest.mark.asyncio
async def test_planner_executor_preserves_agent_stream_and_sync_result_protocol(monkeypatch):
    from langchain_core.messages import HumanMessage
    ref = {"id": str(uuid4()), "total": 4, "filters": {"description": "海边日落"}}
    executor = search_planner.PhotoSearchExecutor(MagicMock(), str(uuid4()), None)
    monkeypatch.setattr(executor, "_search", lambda query: {"total": 4, "search_result": ref})
    state = {"messages": [HumanMessage(content="海边日落")]}
    chunks = [event async for event in executor.astream(state)]
    call = chunks[0][0].tool_calls[0]
    assert call["name"] == "search_library_photos" and call["args"]["query"] == "海边日落"
    assert chunks[1][0].tool_call_id == call["id"]
    assert json.loads(chunks[1][0].content)["search_result"] == ref
    assert json.loads(executor.invoke(state)["messages"][-1].content)["search_result"] == ref


def test_chat_rejects_another_users_session_before_running_agent():
    from app.api import agent
    user = SimpleNamespace(id=uuid4())
    with patch.object(agent.agent_crud, "get_session", return_value=SimpleNamespace(user_id=uuid4())):
        with patch.object(agent, "_agent_service") as service:
            with pytest.raises(HTTPException) as exc:
                agent.chat_endpoint(agent.ChatRequest(message="找照片", session_id=str(uuid4()), mode="search"), user, MagicMock())
            assert exc.value.status_code == 403
            service.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("publish", [True, False])
async def test_stream_emits_and_persists_complete_result_reference_only_for_find(monkeypatch, publish):
    from langchain_core.messages import AIMessageChunk, HumanMessage, AIMessage
    from app.service.agent import service
    user_id, session_id = str(uuid4()), str(uuid4())
    result_ref = {"id": str(uuid4()), "total": 65, "filters": {"location": "西安"}}
    returned = {"total": 65, "photos": []}
    if publish:
        returned["search_result"] = result_ref
    class Agent:
        async def astream(self, state, **kwargs):
            yield AIMessageChunk(content="", tool_calls=[{"id": "search-1", "name": "search_library_photos", "args": {"purpose": "find" if publish else "context"}}]), {"langgraph_node": "model"}
            # Compatible models can omit ToolMessage.name. Resolve via call ID.
            yield SimpleNamespace(type="tool", name=None, content=json.dumps(returned), tool_call_id="search-1"), {"langgraph_node": "tools"}
            yield AIMessageChunk(content="完成"), {"langgraph_node": "model"}
    saved = []
    monkeypatch.setattr(service, "get_agent_executor", lambda *args: (Agent(), "system"))
    monkeypatch.setattr(service, "get_session_history", lambda *args: [HumanMessage(content="先前问题"), AIMessage(content="先前回复")])
    monkeypatch.setattr(service, "create_message", lambda db, message: saved.append(message))
    monkeypatch.setattr(service.config_manager, "get_user_config", lambda *args: SimpleNamespace(ai=None))
    monkeypatch.setattr(service, "_model_context_window", lambda *args: None)
    monkeypatch.setattr(service, "compress_history_if_needed", lambda messages, *args: messages)
    monkeypatch.setattr("app.service.agent.memory.extract_and_store_memory_task", lambda *args: None)
    chunks = [chunk async for chunk in service.stream_chat_with_agent(user_id, session_id, "找西安照片", MagicMock(), mode="search" if publish else "assistant")]
    events = [json.loads(chunk.removeprefix("data: ").strip()) for chunk in chunks if "[DONE]" not in chunk]
    refs = [event["search_result"] for event in events if event.get("type") == "search_result"]
    assert refs == ([result_ref] if publish else [])
    assert saved[-1].content_ext.get("search_results", []) == refs
    assert saved[-1].content_ext["mode"] == ("search" if publish else "assistant")
    assert any(event.get("tool_name") == "search_library_photos" and event.get("type") == "tool_end" for event in events)


def test_history_keeps_search_conditions_for_follow_up_without_loading_all_ids(monkeypatch):
    from app.service.agent import service
    result = {"id": str(uuid4()), "total": 65, "filters": {"location": "西安"}}
    monkeypatch.setattr(service, "get_messages_by_session", lambda *args, **kwargs: [
        SimpleNamespace(role="assistant", content="找到65张", content_ext={"search_results": [result]})])
    messages = service.get_session_history(MagicMock(), str(uuid4()))
    assert messages[-1].type == "system"
    assert "西安" in messages[-1].content and "purpose=context" in messages[-1].content


@pytest.mark.parametrize("text,expected", [("find", "find"), ("use", "use"), ("other", "other"), ("<think>分类过程</think>find", "find"), ("不确定", "other")])
def test_intent_router_accepts_only_model_enum(text, expected):
    model = MagicMock()
    model.invoke.return_value = SimpleNamespace(content=text)
    assert photo_search.classify_photo_intent(model, "去年西安的合照") == expected


def test_intent_router_failure_preserves_general_assistant():
    model = MagicMock()
    model.invoke.side_effect = RuntimeError("unavailable")
    assert photo_search.classify_photo_intent(model, "用这些照片写游记") == "other"


@pytest.mark.parametrize("mode,intent,search_only", [("search", "use", True), ("assistant", "find", True), ("assistant", "use", False)])
def test_executor_limits_tools_for_search_and_keeps_creative_workflows(monkeypatch, mode, intent, search_only):
    from app.service.agent import service
    connection = SimpleNamespace(id="test", enable=True, api_key="test-key", api_base=None, models=[])
    settings = SimpleNamespace(chat_connection_id="test", chat_model_name="test-model", connections=[connection])
    monkeypatch.setattr(service.config_manager, "get_user_config", lambda *args: SimpleNamespace(ai=settings))
    monkeypatch.setattr(service, "FixedChatOpenAI", lambda **kwargs: MagicMock())
    monkeypatch.setattr(service, "get_session_history", lambda *args: [])
    classify = MagicMock(return_value=intent)
    monkeypatch.setattr(photo_search, "classify_photo_intent", classify)
    general = MagicMock(return_value=["creative-tool"])
    monkeypatch.setattr(service, "get_agent_tools", general)
    monkeypatch.setattr("app.service.agent.memory.build_memory_prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr(service, "create_agent", lambda model, tools: tools)
    agent, prompt = service.get_agent_executor(str(uuid4()), str(uuid4()), MagicMock(), user_input="用户请求", mode=mode)
    if search_only:
        from app.service.agent.search_planner import PhotoSearchExecutor
        assert isinstance(agent, PhotoSearchExecutor)
        general.assert_not_called()
    else:
        assert agent == ["creative-tool"]
    assert classify.call_count == (0 if mode == "search" else 1)
