"""Nightly watch 2026-10-31 coverage gaps for five low-coverage server modules."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.api import daily_frame as daily_frame_api
from app.api import media as media_api
from app.api.deps import get_current_user
from app.dependencies import get_db

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def test_daily_frame_media_user_delegates_bearer_token(monkeypatch):
    request = SimpleNamespace(url=SimpleNamespace(path="/daily-frame/assets/x/file"), query_params={})
    user = SimpleNamespace(id=uuid4(), is_active=True)
    seen = {}

    def fake_current_user(req, db, token):
        seen.update(req=req, db=db, token=token)
        return user

    monkeypatch.setattr(daily_frame_api, "get_current_user", fake_current_user)
    db = MagicMock()

    assert daily_frame_api.media_user(request, token="jwt", authorization="Bearer jwt", db=db) is user
    assert seen == {"req": request, "db": db, "token": "jwt"}


def _fake_process(**overrides):
    process = MagicMock()
    process.poll.return_value = None
    process.returncode = 0
    for key, value in overrides.items():
        setattr(process, key, value)
    return process


def test_daily_frame_run_encoder_kills_process_after_timeout(monkeypatch):
    from app.service import daily_frame_render as render

    process = _fake_process()
    process.wait.side_effect = [render.subprocess.TimeoutExpired("ffmpeg", 5), None]
    monkeypatch.setattr(render.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(render.time, "monotonic", MagicMock(side_effect=[10, 20]))

    with pytest.raises(RuntimeError, match="素材处理超时"):
        render.run_encoder(["-version"], working=MagicMock(), check_cancelled=lambda: None, timeout=1)

    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    assert process.wait.call_count == 2


def test_daily_frame_run_encoder_reports_nonzero_exit(monkeypatch):
    from app.service import daily_frame_render as render

    process = _fake_process()
    process.poll.return_value = 0
    process.returncode = 1
    monkeypatch.setattr(render.subprocess, "Popen", lambda *args, **kwargs: process)

    with pytest.raises(RuntimeError, match="素材无法解码"):
        render.run_encoder(["-version"], working=MagicMock(), check_cancelled=lambda: None)


def _agent_client():
    app = FastAPI(root_path="/api")
    app.include_router(agent_api.router, prefix="/agent")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


def test_agent_search_result_photos_success_and_404():
    client = _agent_client()
    result_id = uuid4()
    page = {"items": [], "total": 0, "offset": 0, "limit": 60}

    with patch("app.service.agent.photo_search.search_result_page", return_value=page) as page_spy:
        response = client.get(f"/agent/search-results/{result_id}/photos")
    assert response.status_code == 200
    assert response.json()["data"] == page
    assert str(page_spy.call_args[0][2]) == str(result_id)

    with patch("app.service.agent.photo_search.search_result_page", side_effect=ValueError("not found")):
        response = client.get(f"/agent/search-results/{result_id}/photos")
    assert response.status_code == 404
    assert response.json()["detail"] == "not found"


def test_agent_proactive_read_success_and_404():
    client = _agent_client()

    with patch.object(agent_api.agent_crud, "mark_proactive_read", return_value=True):
        response = client.post("/agent/proactive/42/read")
    assert response.status_code == 200
    assert response.json()["data"] == {"message_id": 42}

    with patch.object(agent_api.agent_crud, "mark_proactive_read", return_value=False):
        response = client.post("/agent/proactive/999/read")
    assert response.status_code == 200
    assert response.json()["code"] == 404


def test_media_existing_backup_photo_without_key_skips_query():
    db = MagicMock()
    assert media_api._existing_backup_photo(db, uuid4(), None) is None
    db.query.assert_not_called()


def test_media_existing_content_photo_ignores_missing_file(monkeypatch):
    photo = SimpleNamespace(id=uuid4(), file_path="missing.jpg")
    query = MagicMock()
    query.filter.return_value.all.return_value = [photo]
    db = MagicMock()
    db.query.return_value = query
    user_id = uuid4()

    monkeypatch.setattr(media_api.os.path, "isfile", lambda path: False)
    assert media_api._existing_content_photo(db, user_id, "0" * 32) is None


@pytest.mark.parametrize("raw,expected", [
    (" ABCDEF0123456789ABCDEF0123456789 ", "abcdef0123456789abcdef0123456789"),
    ("nope", None),
])
def test_media_normalized_md5_edges(raw, expected):
    if expected is None:
        with pytest.raises(Exception):
            media_api._normalized_md5(raw)
    else:
        assert media_api._normalized_md5(raw) == expected


def test_hash_returns_empty_when_budgeted_open_fails(monkeypatch):
    from app.utils import hash as hash_utils

    monkeypatch.setattr(hash_utils, "budgeted_open", MagicMock(side_effect=OSError("disk unavailable")))
    assert hash_utils.calculate_file_md5("any.jpg") == ""
