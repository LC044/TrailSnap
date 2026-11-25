"""Nightly watch 2026-11-25: ``app/api/panorama.py`` 盲区。

2026-11-24 的后端覆盖率报告里 ``api/panorama.py`` 为 96.5%，两条错误分支从未执行：

- 第 64 行：把图片标记为全景时，发现 EXIF 方向不是 1（未归一化）就拒绝并回滚；
- 第 87-88 行：生成全景预览图失败时返回 400 而不是 500。

这两条是「设置全景」和「浏览全景预览」的用户可见兜底：
方向未归一化的图片若被直接标记为全景，等距柱状投影会被拉伸变形；
预览生成失败若不兜底，前端会拿到 500 白屏。

这里用真实的临时 JPEG（含 EXIF Orientation=6）触发方向校验，
再用打桩的 ``derivative`` 触发预览失败。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import panorama as panorama_api
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner(db):
    user = User(id=uuid4(), username="nightly-panorama-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _rotated_jpeg(path):
    """写一张带 EXIF Orientation=6（旋转 90 度）的最小 JPEG。"""
    from PIL import Image

    image = Image.new("RGB", (32, 16), (10, 20, 30))
    exif = image.getexif()
    exif[274] = 6
    image.save(path, "JPEG", exif=exif)
    return str(path)


def _photo(db, owner, file_path):
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename="nightly-pano.jpg", file_type=FileType.image,
        file_path=file_path, width=32, height=16,
    )
    db.add(photo)
    db.commit()
    return photo


def test_update_panorama_rejects_a_photo_that_is_not_orientation_normalized(db, owner, tmp_path):
    path = _rotated_jpeg(tmp_path / "rotated.jpg")
    photo = _photo(db, owner, path)

    payload = panorama_api.PanoramaUpdate(mode="equirectangular")
    response = panorama_api.update_panorama(photo.id, payload, db=db, user=owner)

    assert response.code != 0
    assert "方向" in response.msg
    db.refresh(photo)
    assert photo.panorama_override is None, "被拒绝的全景设置不能落库"


def test_update_panorama_marks_an_ordinary_photo(db, owner, tmp_path):
    path = _rotated_jpeg(tmp_path / "ordinary.jpg")
    photo = _photo(db, owner, path)

    payload = panorama_api.PanoramaUpdate(mode="ordinary")
    response = panorama_api.update_panorama(photo.id, payload, db=db, user=owner)

    assert response.code == 0
    db.refresh(photo)
    assert photo.panorama_override == "ordinary"
    assert photo.panorama_projection is None


def test_panorama_image_reports_a_failed_preview(db, owner, monkeypatch):
    photo = _photo(db, owner, "nightly-pano.jpg")
    photo.panorama_projection = "equirectangular"
    photo.panorama_metadata = {"fullWidth": 8000, "fullHeight": 4000,
                               "croppedWidth": 8000, "croppedHeight": 4000}
    db.commit()

    def _boom(*args, **kwargs):
        raise OSError("磁盘空间不足")

    monkeypatch.setattr(panorama_api, "derivative", _boom)

    response = panorama_api.panorama_image(photo.id, high=False, db=db, user=owner)

    assert response.code == 400
    assert response.msg == "全景预览生成失败"


def test_panorama_image_requires_a_panorama_photo(db, owner):
    photo = _photo(db, owner, "nightly-pano.jpg")
    db.commit()

    response = panorama_api.panorama_image(photo.id, high=False, db=db, user=owner)

    assert response.code == 404

