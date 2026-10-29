"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/api/toolbox.py）。

被测模块：app/api/toolbox.py 的相似照片任务相关端点。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，此前完全未触达）：
- get_similar_task_result：
  * 无 cluster 时返回空列表；
  * 正常 cluster（>=2 张本人照片）按 memory_score+quality_score 降序、再按 photo_time 降序；
  * 只有 1 张照片的 cluster 被判定为无效并删除；
  * 关联照片全部属于他人时 cluster 被删除；
  * 没有 PhotoCluster 关联的 cluster 被删除；
  * limit 截断与「删除后 offset 前进」的翻页计算（current_skip + processed - deleted）。
- get_similar_task：任务表命中 / 未命中时回退为「已完成」的 TaskResponse。
- get_latest_similar_task：无进行中任务时从 ImageCluster 反查 task_id；
  task_id 不是合法 UUID 时返回 data=None。
- get_similar_photos（deprecated）：延迟导入的 SimilarPhotoService 被正确调用。
- get_organize_preview_options：category 策略的「未分类」与 location 策略的「未知位置」兜底项。

DB 访问走用例内的 SQLite 内存库，不触碰真实 Postgres。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import toolbox as toolbox_api
from app.db.base import Base
from app.db.models.cluster import ImageCluster, PhotoCluster
from app.db.models.image_description import ImageDescription
from app.db.models.photo import Photo, FileType
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def user():
    return SimpleNamespace(id=uuid4())


def _photo(db, owner_id, name, when, score=None):
    photo = Photo(id=uuid4(), owner_id=owner_id, filename=name, file_path=name,
                  file_type=FileType.image, size=1, is_deleted=False, photo_time=when)
    db.add(photo)
    db.flush()
    if score is not None:
        db.add(ImageDescription(photo_id=photo.id, memory_score=score, quality_score=0, narrative=name))
    return photo


def _cluster(db, task_id, photos, cluster_type="SIMILARITY"):
    cluster = ImageCluster(cluster_id=uuid4(), task_id=task_id, cluster_type=cluster_type,
                           count=len(photos), created_at=datetime.now())
    db.add(cluster)
    db.flush()
    for photo in photos:
        db.add(PhotoCluster(photo_id=photo.id, cluster_id=cluster.cluster_id))
    db.flush()
    return cluster


# ---------------------------------------------------------------------------
# GET /toolbox/similar/tasks/{task_id}/result
# ---------------------------------------------------------------------------


def test_get_similar_task_result_returns_empty_list_without_clusters(db, user):
    response = toolbox_api.get_similar_task_result(task_id=uuid.uuid4(), db=db, current_user=user)
    assert response.data == []


def test_get_similar_task_result_groups_and_sorts_by_score(db, user):
    task_id = str(uuid4())
    low = _photo(db, user.id, "low.jpg", datetime(2025, 1, 1), score=10)
    high = _photo(db, user.id, "high.jpg", datetime(2025, 1, 2), score=90)
    _cluster(db, task_id, [low, high])
    db.commit()

    response = toolbox_api.get_similar_task_result(task_id=uuid.UUID(task_id), db=db, current_user=user)
    assert len(response.data) == 1
    group = response.data[0]
    # 评分高的排前面
    assert group[0].filename == "high.jpg"
    assert group[1].filename == "low.jpg"


def test_get_similar_task_result_deletes_cluster_with_single_photo(db, user):
    task_id = str(uuid4())
    only = _photo(db, user.id, "one.jpg", datetime(2025, 1, 1))
    cluster = _cluster(db, task_id, [only])
    db.commit()

    response = toolbox_api.get_similar_task_result(task_id=uuid.UUID(task_id), db=db, current_user=user)
    assert response.data == []
    assert db.query(ImageCluster).filter(ImageCluster.cluster_id == cluster.cluster_id).first() is None


def test_get_similar_task_result_deletes_cluster_owned_by_other_user(db, user):
    other = uuid4()
    task_id = str(uuid4())
    foreign_a = _photo(db, other, "a.jpg", datetime(2025, 1, 1))
    foreign_b = _photo(db, other, "b.jpg", datetime(2025, 1, 2))
    _cluster(db, task_id, [foreign_a, foreign_b])
    db.commit()

    response = toolbox_api.get_similar_task_result(task_id=uuid.UUID(task_id), db=db, current_user=user)
    assert response.data == []
    assert db.query(ImageCluster).count() == 0


def test_get_similar_task_result_deletes_cluster_without_photo_rows(db, user):
    task_id = str(uuid4())
    cluster = ImageCluster(cluster_id=uuid4(), task_id=task_id, cluster_type="SIMILARITY",
                           count=0, created_at=datetime.now())
    db.add(cluster)
    db.commit()

    response = toolbox_api.get_similar_task_result(task_id=uuid.UUID(task_id), db=db, current_user=user)
    assert response.data == []
    assert db.query(ImageCluster).count() == 0


def test_get_similar_task_result_ignores_non_similarity_clusters(db, user):
    a = _photo(db, user.id, "a.jpg", datetime(2025, 1, 1))
    b = _photo(db, user.id, "b.jpg", datetime(2025, 1, 2))
    _cluster(db, str(uuid4()), [a, b], cluster_type="OTHER")
    db.commit()

    response = toolbox_api.get_similar_task_result(task_id=uuid.uuid4(), db=db, current_user=user)
    assert response.data == []
    # 非 SIMILARITY 的 cluster 不该被删除
    assert db.query(ImageCluster).count() == 1


def test_get_similar_task_result_respects_limit(db, user):
    task_id = str(uuid4())
    a = _photo(db, user.id, "a.jpg", datetime(2025, 1, 1))
    b = _photo(db, user.id, "b.jpg", datetime(2025, 1, 2))
    c = _photo(db, user.id, "c.jpg", datetime(2025, 1, 3))
    _cluster(db, task_id, [a, b])
    _cluster(db, task_id, [c, a])
    db.commit()

    response = toolbox_api.get_similar_task_result(task_id=uuid.UUID(task_id), limit=1, db=db, current_user=user)
    assert len(response.data) == 1


def test_get_similar_task_result_advances_offset_past_deleted_clusters(db, user):
    """无效 cluster 被删除后，翻页偏移要按「已处理 - 已删除」推进。"""
    task_id = str(uuid4())
    keeper_a = _photo(db, user.id, "k1.jpg", datetime(2025, 1, 1))
    keeper_b = _photo(db, user.id, "k2.jpg", datetime(2025, 1, 2))
    _cluster(db, task_id, [keeper_a, keeper_b])
    lonely = _photo(db, user.id, "solo.jpg", datetime(2025, 1, 3))
    _cluster(db, task_id, [lonely])
    db.commit()

    response = toolbox_api.get_similar_task_result(task_id=uuid.UUID(task_id), limit=5, db=db, current_user=user)
    assert len(response.data) == 1
    # 无效 cluster 已被清理
    assert db.query(ImageCluster).count() == 1


# ---------------------------------------------------------------------------
# GET /toolbox/similar/tasks/{task_id}
# ---------------------------------------------------------------------------


def test_get_similar_task_returns_task_when_found(db, user):
    task = SimpleNamespace(id=uuid4())
    with patch.object(toolbox_api.crud_task, "get_task_by_id_and_owner", return_value=task):
        response = toolbox_api.get_similar_task(task_id=uuid4(), db=db, current_user=user)
    assert response.data is task


def test_get_similar_task_falls_back_to_completed_response(db, user):
    task_id = uuid4()
    with patch.object(toolbox_api.crud_task, "get_task_by_id_and_owner", return_value=None):
        response = toolbox_api.get_similar_task(task_id=task_id, db=db, current_user=user)
    assert response.data.id == task_id
    assert response.data.status == toolbox_api.TaskStatus.COMPLETED.value
    assert response.data.type == toolbox_api.TaskType.SIMILAR_PHOTO_CLUSTERING


# ---------------------------------------------------------------------------
# GET /toolbox/similar/tasks/latest
# ---------------------------------------------------------------------------


def test_get_latest_similar_task_returns_pending_task(db, user):
    task = SimpleNamespace(id=uuid4())
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=task):
        response = toolbox_api.get_latest_similar_task(db=db, current_user=user)
    assert response.data is task


def test_get_latest_similar_task_falls_back_to_cluster_task_id(db, user):
    task_id = str(uuid4())
    a = _photo(db, user.id, "a.jpg", datetime(2025, 1, 1))
    b = _photo(db, user.id, "b.jpg", datetime(2025, 1, 2))
    _cluster(db, task_id, [a, b])
    db.commit()

    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=None):
        response = toolbox_api.get_latest_similar_task(db=db, current_user=user)
    assert str(response.data.id) == task_id
    assert response.data.status == toolbox_api.TaskStatus.COMPLETED.value


def test_get_latest_similar_task_returns_none_for_invalid_cluster_task_id(db, user):
    a = _photo(db, user.id, "a.jpg", datetime(2025, 1, 1))
    b = _photo(db, user.id, "b.jpg", datetime(2025, 1, 2))
    _cluster(db, "not-a-uuid", [a, b])
    db.commit()

    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=None):
        response = toolbox_api.get_latest_similar_task(db=db, current_user=user)
    assert response.data is None


# ---------------------------------------------------------------------------
# GET /toolbox/similar (deprecated)
# ---------------------------------------------------------------------------


def test_get_similar_photos_delegates_to_similar_photo_service(db, user):
    sentinel = [{"group": 1}]
    with patch("app.service.similar_photo.SimilarPhotoService") as service_cls:
        service_cls.return_value.get_similar_groups.return_value = sentinel
        response = toolbox_api.get_similar_photos(threshold=0.8, db=db, current_user=user)
    service_cls.assert_called_once_with(db, str(user.id))
    service_cls.return_value.get_similar_groups.assert_called_once_with(0.8)
    assert response.data == sentinel


# ---------------------------------------------------------------------------
# POST /toolbox/organize/preview-options
# ---------------------------------------------------------------------------


def test_get_organize_preview_options_includes_untagged_category(db, user):
    photo = _photo(db, user.id, "untagged.jpg", datetime(2025, 1, 1))
    db.commit()
    request = toolbox_api.OrganizePreviewOptionsRequest(strategy="category")
    response = toolbox_api.get_organize_preview_options(req=request, db=db, current_user=user)
    assert "未分类" in response.data.options


def test_get_organize_preview_options_includes_tag_names(db, user):
    photo = _photo(db, user.id, "tagged.jpg", datetime(2025, 1, 1))
    tag = PhotoTag(id=uuid4(), tag_name="风景", owner_id=user.id, is_deleted=False)
    db.add(tag)
    db.flush()
    db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id))
    db.commit()

    request = toolbox_api.OrganizePreviewOptionsRequest(strategy="category")
    response = toolbox_api.get_organize_preview_options(req=request, db=db, current_user=user)
    assert "风景" in response.data.options
    assert "未分类" not in response.data.options


def test_get_organize_preview_options_includes_unknown_location(db, user):
    photo = _photo(db, user.id, "noloc.jpg", datetime(2025, 1, 1))
    db.add(PhotoMetadata(photo_id=photo.id, province=None, city=None, district=None))
    db.commit()

    request = toolbox_api.OrganizePreviewOptionsRequest(strategy="location")
    response = toolbox_api.get_organize_preview_options(req=request, db=db, current_user=user)
    assert "未知位置" in response.data.options




