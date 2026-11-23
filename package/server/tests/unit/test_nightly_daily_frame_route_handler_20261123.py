"""Nightly watch 2026-11-23 - app/api/daily_frame.py 的 DailyFrameRoute 统一错误包装盲区。

一日一帧的路由用自定义 APIRoute 把两类异常收敛成统一响应体：

- HTTPException -> BaseResponse.fail(code=状态码, msg=异常文案)
- RequestValidationError -> 422 + 固定的中文提示

这两个分支此前只被 E2E 间接覆盖，包装函数本身没有单元测试。本文件用真实
SQLite 会话 + 真实 router 覆盖：

- 素材不存在时返回 404 且响应体是 BaseResponse 结构（happy）
- 依赖注入抛出的 401 同样被包装（error）
- 日期参数非法时返回 422 与固定文案（error）
- 正常响应不受影响，仍是 code=0 的成功结构（happy）
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.daily_frame import router
from app.api.deps import get_current_user
from app.db.models.user import User
from app.dependencies import get_db

pytestmark = [pytest.mark.smoke]


def _user(db):
    user = User(id=uuid4(), username="owner-" + uuid4().hex[:8], hashed_password="x")
    db.add(user)
    db.flush()
    return user


def _client(db, user, *, current_user=None):
    app = FastAPI()
    app.include_router(router, prefix="/daily-frame")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = current_user or (lambda: user)
    return TestClient(app, raise_server_exceptions=False)


def test_missing_asset_is_wrapped_into_a_base_response(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db)
    db.commit()
    client = _client(db, user)

    response = client.get(f"/daily-frame/assets/{uuid4()}")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 404
    assert body["msg"] == "素材不存在"
    assert body["data"] is None


def test_http_exception_raised_by_a_dependency_is_wrapped(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db)
    db.commit()

    def deny():
        raise HTTPException(status_code=401, detail="Invalid token")

    client = _client(db, user, current_user=deny)

    response = client.get("/daily-frame/settings")

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 401
    assert body["msg"] == "Invalid token"


def test_invalid_date_is_wrapped_into_422(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db)
    db.commit()
    client = _client(db, user)

    response = client.get("/daily-frame/calendar?start=not-a-date&end=2026-01-01")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 422
    assert body["msg"] == "请求参数无效，请检查日期和选帧设置"


def test_successful_response_keeps_the_success_shape(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db)
    db.commit()
    client = _client(db, user)

    response = client.get("/daily-frame/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "success"
    assert body["data"]["initialized"] is False
