"""Nightly watch 2026-11-25 (part 6): cover the visual description persistence.

``app/service/tasks/visual_description.py`` writes the model reply back onto
the photo.  ``tests/unit/test_nightly_visual_description_gaps_20261124.py``
already covers the skip branches of ``_save_result``.  What was left: the
reply *replacing* an older description, the ``only_if_missing`` path that
finds nothing, and ``_image_content``, which builds the prompt context and
had no test at all.

A real SQLite session is used for the write path; the image encoder and the
storage lookup are replaced so no file is read.
"""
import types
import uuid

import pytest

from app.db.models.image_description import ImageDescription
from app.db.models.photo import Photo, FileType
from app.db.models.user import User
from app.service.tasks import visual_description as visual_module
from app.service.tasks.visual_description import VisualDescriptionStrategy

RESULT = {
    "description": "海边的日落",
    "tags": ["海边", "日落"],
    "memory_score": 88,
    "beauty_score": 91,
    "reason": "光线与构图都很出色",
    "narrative": "那天在海边等到了日落。",
}


def _user(session):
    user = User(username="owner", email="owner@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    return user


def _photo(session, owner, name="photo.jpg"):
    photo = Photo(
        filename=name,
        _file_path=f"C:/photos/{name}",
        file_type=FileType.image,
        owner_id=owner.id,
        processed_tasks={},
    )
    session.add(photo)
    session.commit()
    return photo


def _strategy():
    return VisualDescriptionStrategy()




def test_save_result_replaces_an_existing_description(face_sqlite_session):
    session = face_sqlite_session
    owner = _user(session)
    photo = _photo(session, owner)
    session.add(ImageDescription(
        photo_id=photo.id,
        description="旧描述",
        memory_score=1,
        quality_score=2,
        tags=["旧"],
        reason="旧原因",
        narrative="旧旁白",
    ))
    session.commit()

    outcome = _strategy()._save_result(session, photo.id, RESULT, {"force": True})

    assert outcome["status"] == "completed"
    stored = session.query(ImageDescription).filter_by(photo_id=photo.id).all()
    assert len(stored) == 1
    assert stored[0].description == RESULT["description"]




def test_save_result_stores_the_reply_when_only_if_missing_finds_nothing(face_sqlite_session):
    session = face_sqlite_session
    owner = _user(session)
    photo = _photo(session, owner)

    outcome = _strategy()._save_result(session, photo.id, RESULT, {"only_if_missing": True})

    assert outcome["status"] == "completed"
    assert session.query(ImageDescription).filter_by(photo_id=photo.id).count() == 1


def test_image_content_returns_nothing_when_the_file_is_unavailable(face_sqlite_session, monkeypatch):
    monkeypatch.setattr(visual_module.storage, "get_available_photo_path", lambda *args, **kwargs: None)
    photo = types.SimpleNamespace(owner_id="owner-1", id=uuid.uuid4(), photo_time=None, file_path="C:/photos/a.jpg")

    assert _strategy()._image_content(photo, face_sqlite_session) is None


def test_image_content_adds_the_single_photo_instruction(face_sqlite_session, monkeypatch):
    monkeypatch.setattr(visual_module.storage, "get_available_photo_path", lambda *args, **kwargs: "C:/photos/a.jpg")
    monkeypatch.setattr(visual_module, "encode_image", lambda path: "BASE64")
    monkeypatch.setattr(visual_module, "get_user_roots", lambda *args, **kwargs: [])
    monkeypatch.setattr(visual_module, "compute_browse_path", lambda path, roots: ("相册", "a.jpg"))
    photo = types.SimpleNamespace(owner_id="owner-1", id=uuid.uuid4(), photo_time=None, file_path="C:/photos/a.jpg")

    parts = _strategy()._image_content(photo, face_sqlite_session)

    text = parts[0]["text"]
    assert text.startswith("请结合图像本身分析照片。只输出 JSON。/no_think")
    assert "文件名：a.jpg" in text
    assert "所在文件夹：相册" in text
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,BASE64")


def test_image_content_keeps_the_batch_prompt_short(face_sqlite_session, monkeypatch):
    monkeypatch.setattr(visual_module.storage, "get_available_photo_path", lambda *args, **kwargs: "C:/photos/a.jpg")
    monkeypatch.setattr(visual_module, "encode_image", lambda path: "BASE64")
    monkeypatch.setattr(visual_module, "get_user_roots", lambda *args, **kwargs: [])
    monkeypatch.setattr(visual_module, "compute_browse_path", lambda path, roots: ("", ""))
    photo = types.SimpleNamespace(owner_id="owner-1", id=uuid.uuid4(), photo_time=None, file_path="C:/photos/a.jpg")

    text = _strategy()._image_content(photo, face_sqlite_session, batch=True)[0]["text"]

    assert "只输出 JSON。/no_think" not in text
    assert text.startswith("照片时间：")


def test_image_content_survives_a_failing_path_lookup(face_sqlite_session, monkeypatch):
    monkeypatch.setattr(visual_module.storage, "get_available_photo_path", lambda *args, **kwargs: "C:/photos/a.jpg")
    monkeypatch.setattr(visual_module, "encode_image", lambda path: "BASE64")

    def boom(*args, **kwargs):
        raise RuntimeError("存储根目录不可用")

    monkeypatch.setattr(visual_module, "get_user_roots", boom)
    photo = types.SimpleNamespace(owner_id="owner-1", id=uuid.uuid4(), photo_time=None, file_path="C:/photos/a.jpg")

    text = _strategy()._image_content(photo, face_sqlite_session)[0]["text"]

    assert text.startswith("请结合图像本身分析照片")
    assert "文件名" not in text


