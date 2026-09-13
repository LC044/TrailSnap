"""2026-09-13 nightly tests for current high-priority backend coverage gaps.

Targets selected from the Cobertura report:
agent context-model selection, multimodal artifact/tool wrappers, photo
soft-delete/restore and file cleanup, task retry scheduling, settings map/AI
proxy helpers, and train-ticket recognition normalization.
"""
import asyncio
import json
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

pytestmark = [pytest.mark.smoke]


def _ctx(db):
    @contextmanager
    def _cm():
        yield db

    return MagicMock(side_effect=_cm)


def _tool(name, user_id, session_id="session-1"):
    from app.service.agent.tools import get_agent_tools

    for tool in get_agent_tools(user_id, session_id):
        if tool.name == name:
            return tool
    raise AssertionError(f"tool {name} not found")


# ---------------------------------------------------------------------------
# app/service/agent/service.py -- model context-window selection
# ---------------------------------------------------------------------------


def test_model_context_window_prefers_requested_model_and_falls_back():
    from app.service.agent.service import _model_context_window

    model_4k = SimpleNamespace(model_name="qwen-4k", context_window=4096)
    model_128k = SimpleNamespace(model_name="qwen-128k", context_window=131072)
    settings = SimpleNamespace(
        chat_connection_id="chat",
        chat_model_name="qwen-4k",
        analysis_connection_id="analysis",
        analysis_model_name="qwen-128k",
        connections=[
            SimpleNamespace(id="chat", models=[model_4k, model_128k]),
            SimpleNamespace(id="analysis", models=[model_128k]),
        ],
    )

    assert _model_context_window(settings, "chat", "qwen-4k") == 4096
    assert _model_context_window(settings, "analysis", "qwen-128k") == 131072
    assert _model_context_window(settings, "missing", "missing-model") == 128000


# ---------------------------------------------------------------------------
# app/service/agent/tools.py -- multimodal and artifact wrappers
# ---------------------------------------------------------------------------


def test_agent_multimodal_wrappers_limit_and_serialize_photo_payloads():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    contexts = [{
        "photo_id": "p1",
        "thumbnail_url": "/thumb/p1",
        "description": "西湖",
        "quality_score": 0.91,
    }]

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "photo_contexts", return_value=contexts) as contexts_mock,
        patch.object(tools_module, "contact_sheet_content", return_value=[{"image": "sheet"}]) as sheet_mock,
        patch.object(tools_module, "select_representatives", return_value=["p2"]) as representatives_mock,
    ):
        gallery = json.loads(_tool("view_photos", user_id).func(["p1", "p2", "p3"], size="huge"))
        sheet = _tool("create_contact_sheet", user_id).func(["p1", "p2"])
        selected = json.loads(_tool("select_representative_photos", user_id).func(["p1", "p2"], count=1))

    contexts_mock.assert_called_once_with(db, user_id, ["p1", "p2", "p3"])
    sheet_mock.assert_called_once_with(db, user_id, ["p1", "p2"])
    representatives_mock.assert_called_once_with(db, user_id, ["p1", "p2"], 1)
    assert gallery == {
        "mode": "multimodal_gallery",
        "size": "small",
        "photos": contexts,
    }
    assert sheet == [{"image": "sheet"}]
    assert selected == {"selected": ["p2"], "requested": 1, "returned": 1}


def test_agent_artifact_draft_validates_type_and_serializes_result_or_error():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    artifact_id = uuid4()
    row = SimpleNamespace(
        id=artifact_id, artifact_type="travel_story", title="西湖两日",
        status="DRAFT", source_photo_ids=["p1"],
    )

    db = MagicMock()
    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "create_artifact", return_value=row) as create_mock,
    ):
        payload = json.loads(
            _tool("create_artifact_draft", user_id).func(
                "travel_story", "西湖两日", {"summary": "好看"}, ["p1"], ["t1"]
            )
        )

    create_mock.assert_called_once_with(
        db, user_id, "session-1", "travel_story", "西湖两日",
        {"summary": "好看"}, ["p1"], ["t1"],
    )
    assert payload == {
        "artifact": {
            "id": str(artifact_id), "type": "travel_story", "title": "西湖两日",
            "status": "DRAFT", "url": f"/agent/artifacts/{artifact_id}",
            "photo_ids": ["p1"],
        }
    }

    invalid = json.loads(
        _tool("create_artifact_draft", user_id).func("bad_type", "title", {}, [])
    )
    assert invalid == {"error": "unsupported artifact_type"}

    with (
        patch.object(tools_module, "SessionLocal", _ctx(MagicMock())),
        patch.object(tools_module, "create_artifact", side_effect=ValueError("照片不存在")),
    ):
        error = json.loads(
            _tool("create_artifact_draft", user_id).func("nine_grid", "标题", {}, ["missing"])
        )
    assert error == {"error": "照片不存在"}


# ---------------------------------------------------------------------------
# app/crud/photo.py -- soft delete, restore, and physical cleanup helpers
# ---------------------------------------------------------------------------


def test_batch_soft_delete_photos_updates_flags_album_counts_and_triggers():
    from app.crud import photo as photo_crud

    db = MagicMock()
    query = MagicMock()
    query.options.return_value = query
    query.filter.return_value = query
    db.query.return_value = query
    photo_id, album_id = uuid4(), uuid4()
    album = SimpleNamespace(id=album_id)
    photo = SimpleNamespace(id=photo_id, albums=[album], is_deleted=False, deleted_at=None)

    query.all.return_value = [photo]
    with (
        patch.object(photo_crud, "update_album_photo_counts") as update_counts,
        patch("app.crud.album.trigger_conditional_albums_update") as trigger,
    ):
        count = photo_crud.batch_soft_delete_photos(db, [photo_id], user_id=uuid4())

    assert count == 1
    assert photo.is_deleted is True
    assert isinstance(photo.deleted_at, datetime)
    update_counts.assert_called_once_with(db, {album_id})
    trigger.assert_called_once()
    db.commit.assert_called_once()


def test_restore_photos_clears_deleted_flags_and_discard_decisions():
    from app.crud import photo as photo_crud

    db = MagicMock()
    query = MagicMock()
    query.options.return_value = query
    query.filter.return_value = query
    query.all.return_value = []
    query.delete.return_value = None
    db.query.return_value = query

    with (
        patch.object(photo_crud, "update_album_photo_counts") as update_counts,
        patch("app.crud.album.trigger_conditional_albums_update") as trigger,
    ):
        count = photo_crud.restore_photos(db, [uuid4()], user_id=uuid4())

    assert count == 0
    update_counts.assert_called_once_with(db, set())
    trigger.assert_called_once()
    db.commit.assert_called_once()


def test_remove_photo_files_handles_single_and_parallel_targets():
    from app.crud import photo as photo_crud

    user_id = uuid4()
    original = (r"C:\photos\original.jpg", uuid4(), False, True)
    thumbnails = [(r"C:\photos\a.jpg", uuid4(), False, False), (r"C:\photos\b.jpg", uuid4(), True, False)]

    with (
        patch.object(photo_crud.storage, "delete_file") as delete_file,
        patch.object(photo_crud.storage, "delete_thumbnails") as delete_thumbnails,
    ):
        photo_crud._remove_photo_files(user_id, [original])
        photo_crud._remove_photo_files(user_id, thumbnails)

    assert delete_file.call_count == 1
    assert delete_file.call_args.args[0] == user_id
    assert {call.args[1] for call in delete_thumbnails.call_args_list} == {thumbnails[0][1], thumbnails[1][1]}


# ---------------------------------------------------------------------------
# app/service/task_worker.py -- retry admission and backoff
# ---------------------------------------------------------------------------


def test_schedule_retry_distinguishes_model_download_transient_and_exhausted():
    from app.db.models.task import TaskStatus
    from app.service.task_worker import TaskWorker

    worker = TaskWorker.__new__(TaskWorker)
    worker._publish_task_row = MagicMock()
    db = MagicMock()

    model_task = SimpleNamespace(
        id=uuid4(), status=TaskStatus.PROCESSING, attempt_count=0,
        next_retry_at=None, error=None,
    )
    assert worker._schedule_retry(db, model_task, "model_status=downloading", 3) is True
    assert model_task.status == TaskStatus.PENDING
    assert model_task.attempt_count == 0
    assert model_task.error == "AI 大模型正在下载，下载完成后将自动继续"

    transient = SimpleNamespace(
        id=uuid4(), status=TaskStatus.FAILED, attempt_count=0,
        next_retry_at=None, error="old",
    )
    assert worker._schedule_retry(db, transient, "AI service timeout", 3) is True
    assert transient.attempt_count == 1
    assert transient.status == TaskStatus.PENDING
    assert "1/3" in transient.error

    exhausted = SimpleNamespace(
        id=uuid4(), status=TaskStatus.FAILED, attempt_count=2,
        next_retry_at=None, error="old",
    )
    assert worker._schedule_retry(db, exhausted, "connection refused", 3) is False
    assert exhausted.attempt_count == 3
    assert exhausted.status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# app/api/settings.py -- map key and AI model proxy outcomes
# ---------------------------------------------------------------------------


def test_map_key_test_validates_key_and_wraps_provider_failures():
    from app.api import settings as settings_api
    from app.api.settings import MapKeyTestRequest

    with pytest.raises(HTTPException) as empty:
        settings_api.test_map_key(MapKeyTestRequest(api_key="  "), current_user=MagicMock())
    assert empty.value.status_code == 400

    response = SimpleNamespace(ok=True, status_code=200, json=lambda: {
        "status": "0", "result": {"formatted_address": "北京市东城区"}
    })
    with patch.object(settings_api.requests, "get", return_value=response) as get:
        valid = settings_api.test_map_key(MapKeyTestRequest(api_key=" valid "), current_user=MagicMock())
    assert valid.data == {"valid": True}
    assert get.call_args.kwargs["params"]["tk"] == "valid"

    with patch.object(
        settings_api.requests, "get", side_effect=settings_api.requests.ConnectionError("offline")
    ):
        offline = settings_api.test_map_key(MapKeyTestRequest(api_key="key"), current_user=MagicMock())
    assert offline.data == {"valid": False, "reason": "服务端无法访问天地图，请检查网络"}


def test_ai_model_request_maps_http_body_timeout_and_success():
    from app.api import settings as settings_api

    current_user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.test:8001/"))
    response_200 = SimpleNamespace(status_code=200, json=lambda: {"models": ["clip"]}, text="")
    response_500 = SimpleNamespace(status_code=500, json=lambda: {"detail": "模型未安装"}, text="模型未安装")

    with (
        patch.object(settings_api.config_manager, "get_user_config", return_value=config),
        patch.object(settings_api.requests, "request", return_value=response_200) as request,
    ):
        success = settings_api._ai_model_request("GET", "/ai/models", current_user, db)
    assert success.data == {"models": ["clip"]}
    assert request.call_args.args == ("GET", "http://ai.test:8001/ai/models")

    with (
        patch.object(settings_api.config_manager, "get_user_config", return_value=config),
        patch.object(settings_api.requests, "request", return_value=response_500),
    ):
        failed = settings_api._ai_model_request("DELETE", "/ai/models/clip", current_user, db)
    assert failed.code == 500
    assert failed.msg == "模型未安装"

    with (
        patch.object(settings_api.config_manager, "get_user_config", return_value=config),
        patch.object(settings_api.requests, "request", side_effect=settings_api.requests.Timeout("slow")),
    ):
        timeout = settings_api._ai_model_request("POST", "/ai/config/model", current_user, db, json_body={})
    assert timeout.code == 504
    assert timeout.msg == "AI 模型服务响应超时"


# ---------------------------------------------------------------------------
# app/api/train_ticket.py -- recognition result selection and normalization
# ---------------------------------------------------------------------------


class _FakeTicketResponse:
    status = 200

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeTicketSession:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, *_args, **_kwargs):
        return _FakeTicketResponse(self._payload)


@pytest.mark.asyncio
async def test_recognize_ticket_selects_best_candidate_and_normalizes_payload():
    from app.api.train_ticket import recognize_ticket

    payload = {"results": [{"tickets": [
        {"name": "只识别姓名", "price": "100"},
        {
            "train_code": "G1234", "departure_station": "杭州东", "arrival_station": "上海虹桥",
            "datetime": "9月10日 08:05", "seat_type": "二等座", "price": "￥123.50元",
            "name": "测试", "carriage": "07",
        },
    ]}]}
    file = SimpleNamespace(filename="ticket.jpg", read=AsyncMock(return_value=b"image"))
    current_user = SimpleNamespace(id=uuid4())
    config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.test:8001"))

    with (
        patch("app.api.train_ticket.config_manager") as config_manager,
        patch("app.api.train_ticket.aiohttp.ClientSession", return_value=_FakeTicketSession(payload)),
    ):
        config_manager.get_user_config.return_value = config
        result = await recognize_ticket(file=file, db=MagicMock(), current_user=current_user)

    expected_year = datetime.now().year
    assert result.data == {
        "train_code": "G1234", "departure_station": "杭州东", "arrival_station": "上海虹桥",
        "seat_type": "二等座", "berth_type": "无",
        "name": "测试", "carriage": "07",
        "datetime": f"{expected_year}-09-10T08:05", "price": 123.5,
        "discount_type": "全价票",
    }


@pytest.mark.asyncio
async def test_recognize_ticket_rejects_empty_detection():
    from app.api.train_ticket import recognize_ticket

    payload = {"results": [{"tickets": []}]}
    file = SimpleNamespace(filename="ticket.jpg", read=AsyncMock(return_value=b"image"))
    current_user = SimpleNamespace(id=uuid4())
    config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.test:8001"))

    with (
        patch("app.api.train_ticket.config_manager") as config_manager,
        patch("app.api.train_ticket.aiohttp.ClientSession", return_value=_FakeTicketSession(payload)),
    ):
        config_manager.get_user_config.return_value = config
        with pytest.raises(HTTPException) as exc:
            await recognize_ticket(file=file, db=MagicMock(), current_user=current_user)

    assert exc.value.status_code == 400
    assert exc.value.detail == "未能识别出车票信息"
