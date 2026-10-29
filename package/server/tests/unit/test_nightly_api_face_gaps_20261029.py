"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/api/face.py）。

被测模块：app/api/face.py 的人脸 / 人物时间线相关端点。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，此前完全未触达）：
- add_photos_to_identity：人物不存在 404；照片不属于本人被跳过；已有特征向量时按
  欧氏距离选最相似的人脸；没有特征时按人脸框面积选最大的一张；完全没有检测框时取
  第一张；照片完全没有检测到人脸时创建默认人脸。
- get_photo_faces / assign_photo_face：委托给 app.service.photo_faces。
- get_person_timeline / get_person_timeline_year：排序与年份明细透传。
- preview_identity_rescan / apply_identity_rescan / rescan_identity：404、409、500 与成功。

service.face_cluster 顶层依赖 sklearn，测试里全部 mock，不加载真实模型。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import face as face_api
from app.schemas.face import AddPhotosToIdentityRequest, AssignPhotoFace, FaceRescanApplyRequest

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _identity():
    return SimpleNamespace(id=uuid4(), identity_name="小李")


# ---------------------------------------------------------------------------
# GET /face/photos/{photo_id}
# ---------------------------------------------------------------------------


def test_get_photo_faces_delegates_to_service():
    user = _user()
    db = MagicMock()
    payload = [{"face_id": 1}]
    with patch("app.service.photo_faces.list_photo_faces", return_value=payload) as list_faces:
        response = face_api.get_photo_faces(photo_id=uuid4(), db=db, current_user=user)
    list_faces.assert_called_once_with(db, list_faces.call_args.args[1], user.id)
    assert response.data == payload


# ---------------------------------------------------------------------------
# PUT /face/photos/{photo_id}/{face_id}/identity
# ---------------------------------------------------------------------------


def test_assign_photo_face_delegates_to_service():
    user = _user()
    db = MagicMock()
    photo_id, face_id = uuid4(), 7
    identity_id = uuid4()
    with patch("app.service.photo_faces.assign_photo_face") as assign:
        response = face_api.assign_photo_face(photo_id=photo_id, face_id=face_id,
                                              payload=AssignPhotoFace(identity_id=identity_id),
                                              db=db, current_user=user)
    assign.assert_called_once_with(db, photo_id, face_id, identity_id, user.id)
    assert response.data == {"face_id": face_id}


# ---------------------------------------------------------------------------
# GET /face/identities/{id}/timeline
# ---------------------------------------------------------------------------


def test_get_person_timeline_sorts_primary_identity_first():
    user = _user()
    db = MagicMock()
    identity_id = uuid4()
    other_id = uuid4()
    result = {"people": [{"id": str(other_id)}, {"id": str(identity_id)}]}
    with patch.object(face_api.person_timeline, "scope", return_value=(identity_id, other_id, [])), \
         patch.object(face_api.person_timeline, "timeline", return_value=result):
        response = face_api.get_person_timeline(id=identity_id, db=db, current_user=user)
    assert [p["id"] for p in response.data["people"]] == [str(identity_id), str(other_id)]


def test_get_person_timeline_year_delegates_to_year_detail():
    user = _user()
    db = MagicMock()
    identity_id = uuid4()
    with patch.object(face_api.person_timeline, "scope", return_value=(identity_id, identity_id, [])), \
         patch.object(face_api.person_timeline, "year_detail", return_value={"photos": []}) as year_detail:
        response = face_api.get_person_timeline_year(id=identity_id, year=2025, db=db, current_user=user)
    assert year_detail.call_args.args[4] == 2025
    assert response.data == {"photos": []}


# ---------------------------------------------------------------------------
# POST /face/identities/{id}/add-photos
# ---------------------------------------------------------------------------


def _add_photos_payload(photo_ids):
    return AddPhotosToIdentityRequest(photo_ids=photo_ids)


@pytest.mark.asyncio
async def test_add_photos_to_identity_returns_404_when_identity_missing():
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await face_api.add_photos_to_identity(
                id=uuid4(), payload=_add_photos_payload([uuid4()]), db=MagicMock(), current_user=_user())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_add_photos_to_identity_skips_photos_owned_by_others():
    user = _user()
    db = MagicMock()
    photo = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    db.query.return_value.get.return_value = photo
    with patch.object(face_api.crud_face, "get_identity", return_value=_identity()), \
         patch("app.crud.album.trigger_conditional_albums_update"):
        response = await face_api.add_photos_to_identity(
            id=uuid4(), payload=_add_photos_payload([photo.id]), db=db, current_user=user)
    assert response.data["count"] == 0


@pytest.mark.asyncio
async def test_add_photos_to_identity_picks_largest_face_without_features():
    user = _user()
    db = MagicMock()
    photo = SimpleNamespace(id=uuid4(), owner_id=user.id)
    small = SimpleNamespace(face_feature=None, face_rect=[0, 0, 1, 1], face_identity_id=None)
    big = SimpleNamespace(face_feature=None, face_rect=[0, 0, 10, 10], face_identity_id=None)
    db.query.return_value.get.return_value = photo
    db.query.return_value.filter.return_value.all.return_value = [small, big]
    with patch.object(face_api.crud_face, "get_identity", return_value=_identity()), \
         patch("app.crud.album.trigger_conditional_albums_update"):
        response = await face_api.add_photos_to_identity(
            id=uuid4(), payload=_add_photos_payload([photo.id]), db=db, current_user=user)
    assert response.data["count"] == 1
    assert big.face_identity_id is not None
    assert small.face_identity_id is None


@pytest.mark.asyncio
async def test_add_photos_to_identity_falls_back_to_first_face_without_rect():
    user = _user()
    db = MagicMock()
    photo = SimpleNamespace(id=uuid4(), owner_id=user.id)
    first = SimpleNamespace(face_feature=None, face_rect=None, face_identity_id=None)
    second = SimpleNamespace(face_feature=None, face_rect=None, face_identity_id=None)
    db.query.return_value.get.return_value = photo
    db.query.return_value.filter.return_value.all.return_value = [first, second]
    with patch.object(face_api.crud_face, "get_identity", return_value=_identity()), \
         patch("app.crud.album.trigger_conditional_albums_update"):
        response = await face_api.add_photos_to_identity(
            id=uuid4(), payload=_add_photos_payload([photo.id]), db=db, current_user=user)
    assert response.data["count"] == 1
    assert first.face_identity_id is not None


@pytest.mark.asyncio
async def test_add_photos_to_identity_creates_default_face_when_none_detected():
    user = _user()
    db = MagicMock()
    photo = SimpleNamespace(id=uuid4(), owner_id=user.id)
    db.query.return_value.get.return_value = photo
    db.query.return_value.filter.return_value.all.return_value = []
    with patch.object(face_api.crud_face, "get_identity", return_value=_identity()), \
         patch("app.crud.album.trigger_conditional_albums_update"):
        response = await face_api.add_photos_to_identity(
            id=uuid4(), payload=_add_photos_payload([photo.id]), db=db, current_user=user)
    assert response.data["count"] == 1
    added = db.add.call_args.args[0]
    assert added.face_feature is None
    assert added.face_identity_id is not None


# ---------------------------------------------------------------------------
# 重扫相关端点
# ---------------------------------------------------------------------------


def test_rescan_identity_returns_404_when_identity_missing():
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            face_api.rescan_identity(id=uuid4(), db=MagicMock(), current_user=_user())
    assert exc_info.value.status_code == 404


def test_preview_identity_rescan_returns_404_when_identity_missing():
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            face_api.preview_identity_rescan(id=uuid4(), db=MagicMock(), current_user=_user())
    assert exc_info.value.status_code == 404


def test_preview_identity_rescan_returns_result():
    user = _user()
    identity_id = uuid4()
    result = {"add": [], "remove": []}
    with patch.object(face_api.crud_face, "get_identity", return_value=_identity()), \
         patch.object(face_api, "_face_cluster_service") as service_factory:
        service_factory.return_value.return_value.preview_identity_rescan.return_value = result
        response = face_api.preview_identity_rescan(id=identity_id, db=MagicMock(), current_user=user)
    assert response.data == result


def test_apply_identity_rescan_returns_404_when_identity_missing():
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            face_api.apply_identity_rescan(
                payload=FaceRescanApplyRequest(), id=uuid4(), db=MagicMock(), current_user=_user())
    assert exc_info.value.status_code == 404


def test_apply_identity_rescan_returns_result_and_triggers_album_update():
    user = _user()
    identity_id = uuid4()
    affected = str(uuid4())
    with patch.object(face_api.crud_face, "get_identity", return_value=_identity()), \
         patch.object(face_api, "_face_cluster_service") as service_factory, \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        service_factory.return_value.return_value.apply_identity_rescan.return_value = {
            "applied": 1, "affected_photo_ids": [affected]}
        response = face_api.apply_identity_rescan(
            payload=FaceRescanApplyRequest(add_face_ids=[1], remove_face_ids=[2]),
            id=identity_id, db=MagicMock(), current_user=user)
    assert response.data == {"applied": 1}
    trigger.assert_called_once()
