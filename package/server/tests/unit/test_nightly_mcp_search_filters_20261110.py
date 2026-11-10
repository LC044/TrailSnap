"""覆盖 app/service/mcp_server.py 中 search_photos 的多维筛选分支。

search_photos 是 MCP 只读工具里唯一的照片检索入口，支持日期区间、地点、
OCR 文本、媒体类型、画幅、是否有人脸、质量分与回忆分等 8 个筛选条件。
这些条件此前没有任何单测覆盖，筛选项一旦写错（例如 orientation 反了、
min_quality_score 取反）只会在真实 Agent 调用时静默返回错误结果。

这里用真实的临时 SQLite 会话 + 真实 ORM 模型验证筛选语义，
只把 Agent Token 鉴权与结果渲染替换成桩函数。
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.face import Face
from app.db.models.image_description import ImageDescription
from app.db.models.ocr import OCR
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User


@pytest.fixture
def search_ctx(tmp_path, monkeypatch):
    """构造一个包含各类照片的临时库，并把 MCP 工具接到这个库上。"""
    import app.db.models  # noqa: F401  确保所有模型都已注册
    from app.service import mcp_server

    engine = create_engine(f"sqlite:///{(tmp_path / 'mcp.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    db = Session()

    owner = User(username="nightly", email="nightly@example.com", hashed_password="x")
    db.add(owner)
    db.flush()

    def _photo(**overrides):
        data = dict(
            filename=overrides.pop("filename", "p.jpg"),
            photo_time=datetime(2024, 1, 1, 12, 0, 0),
            _file_path=f"/photos/{overrides.get('filename', 'p.jpg')}",
            file_type=FileType.image,
            owner_id=owner.id,
            width=100,
            height=100,
        )
        data.update(overrides)
        photo = Photo(**data)
        db.add(photo)
        db.flush()
        return photo

    ctx = {"db": db, "owner": owner, "photo": _photo}

    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: Session())
    monkeypatch.setattr(mcp_server, "_principal", lambda scope: owner.id)
    monkeypatch.setattr(
        mcp_server,
        "photo_contexts",
        lambda _db, _uid, ids: [{"id": i} for i in ids],
    )

    try:
        yield ctx
    finally:
        db.close()
        engine.dispose()


def _ids(result):
    return sorted(item["id"] for item in result["photos"])


def test_no_filter_returns_all_photos(search_ctx):
    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    first = search_ctx["photo"](filename="a.jpg", photo_time=datetime(2024, 1, 1, 10, 0))
    second = search_ctx["photo"](filename="b.jpg", photo_time=datetime(2024, 7, 1, 10, 0))
    db.commit()

    result = search_photos()

    assert result["total"] == 2
    assert _ids(result) == sorted([str(first.id), str(second.id)])
    assert result["next_cursor"] is None


def test_date_range_filter(search_ctx):
    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    old = search_ctx["photo"](filename="old.jpg", photo_time=datetime(2024, 1, 1, 10, 0))
    mid = search_ctx["photo"](filename="mid.jpg", photo_time=datetime(2024, 5, 20, 10, 0))
    new = search_ctx["photo"](filename="new.jpg", photo_time=datetime(2024, 9, 9, 10, 0))
    db.commit()

    assert _ids(search_photos(start_date="2024-05-01")) == sorted([str(mid.id), str(new.id)])
    assert _ids(search_photos(end_date="2024-02-01")) == [str(old.id)]
    assert _ids(search_photos(start_date="2024-05-01", end_date="2024-06-01")) == [str(mid.id)]


def test_location_filter_matches_any_metadata_field(search_ctx):
    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    hz = search_ctx["photo"](filename="hz.jpg")
    sh = search_ctx["photo"](filename="sh.jpg")
    db.add(PhotoMetadata(photo_id=hz.id, city="杭州市", country="中国", address="西湖区"))
    db.add(PhotoMetadata(photo_id=sh.id, city="上海市", country="中国", address="浦东新区"))
    db.commit()

    assert _ids(search_photos(location="杭州")) == [str(hz.id)]
    assert _ids(search_photos(location="浦东")) == [str(sh.id)]
    assert search_photos(location="北京")["total"] == 0


def test_ocr_text_and_media_type_filters(search_ctx):
    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    receipt = search_ctx["photo"](filename="receipt.jpg")
    plain = search_ctx["photo"](filename="plain.jpg")
    clip = search_ctx["photo"](filename="clip.mp4", file_type=FileType.video)
    db.add(OCR(photo_id=receipt.id, text="增值税发票"))
    db.add(OCR(photo_id=plain.id, text="风景照"))
    db.commit()

    assert _ids(search_photos(ocr_text="发票")) == [str(receipt.id)]
    assert _ids(search_photos(media_type="video")) == [str(clip.id)]


def test_orientation_filter(search_ctx):
    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    wide = search_ctx["photo"](filename="wide.jpg", width=200, height=100)
    tall = search_ctx["photo"](filename="tall.jpg", width=100, height=200)
    square = search_ctx["photo"](filename="sq.jpg", width=120, height=120)
    db.commit()

    assert _ids(search_photos(orientation="landscape")) == [str(wide.id)]
    assert _ids(search_photos(orientation="portrait")) == [str(tall.id)]
    assert _ids(search_photos(orientation="square")) == [str(square.id)]


def test_has_people_filter(search_ctx):
    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    with_face = search_ctx["photo"](filename="face.jpg")
    without_face = search_ctx["photo"](filename="nface.jpg")
    db.add(Face(photo_id=with_face.id, is_deleted=False))
    db.add(Face(photo_id=without_face.id, is_deleted=True))
    db.commit()

    assert _ids(search_photos(has_people=True)) == [str(with_face.id)]
    assert _ids(search_photos(has_people=False)) == [str(without_face.id)]


def test_score_filters(search_ctx):
    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    good = search_ctx["photo"](filename="good.jpg")
    meh = search_ctx["photo"](filename="meh.jpg")
    db.add(ImageDescription(photo_id=good.id, quality_score=90.0, memory_score=80.0))
    db.add(ImageDescription(photo_id=meh.id, quality_score=20.0, memory_score=30.0))
    db.commit()

    assert _ids(search_photos(min_quality_score=50)) == [str(good.id)]
    assert _ids(search_photos(min_memory_score=50)) == [str(good.id)]
    assert search_photos(min_quality_score=50, min_memory_score=50)["total"] == 1


def test_pagination_and_invalid_arguments(search_ctx):
    from mcp.server.mcpserver.exceptions import ToolError

    from app.service.mcp_server import search_photos

    db = search_ctx["db"]
    for index in range(3):
        search_ctx["photo"](filename=f"p{index}.jpg", photo_time=datetime(2024, 1, index + 1))
    db.commit()

    page = search_photos(cursor=0, limit=2)
    assert page["total"] == 3
    assert page["returned"] == 2
    assert page["next_cursor"] == 2

    with pytest.raises(ToolError):
        search_photos(start_date="2024-05-01", end_date="2024-01-01")
    with pytest.raises(ToolError):
        search_photos(orientation="diagonal")

