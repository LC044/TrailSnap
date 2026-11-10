"""覆盖 app/crud/photo.py 的 SQLite 智能相册按向量相似度排序分支。

智能相册在 PostgreSQL 上可以直接用 pgvector 的 ``<=>`` 算余弦距离，
但 SQLite 没有 pgvector，只能把向量取回内存用 numpy 算距离再排序。
这条 SQLite 分支此前完全没有覆盖，一旦写错（例如把距离算成相似度），
智能相册在桌面端会返回完全错误的顺序，且不会报错。

这里用真实的临时 SQLite 库 + 真实 ORM 模型验证排序语义。
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import photo as crud_photo
from app.db.base import Base
from app.db.models.album import Album
from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType, Photo
from app.db.models.user import User


def _unit(vec):
    """补齐到 512 维的单位向量。"""
    full = [0.0] * 512
    for index, value in enumerate(vec):
        full[index] = value
    return full


@pytest.fixture
def smart_album(tmp_path):
    import app.db.models  # noqa: F401

    engine = create_engine(f"sqlite:///{(tmp_path / 'crud_photo.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()

    owner = User(username="smart", email="smart@example.com", hashed_password="x")
    db.add(owner)
    db.flush()

    album = Album(
        name="智能相册",
        type="smart",
        owner_id=owner.id,
        query_embedding=_unit([1.0, 0.0]),
        threshold=0.25,
    )
    db.add(album)
    db.flush()

    def _photo(name, embedding):
        photo = Photo(
            filename=name,
            photo_time=datetime(2024, 1, 1, 10, 0),
            _file_path=f"/photos/{name}",
            file_type=FileType.image,
            owner_id=owner.id,
        )
        db.add(photo)
        db.flush()
        if embedding is not None:
            db.add(ImageVector(photo_id=photo.id, embedding=_unit(embedding)))
        db.flush()
        return photo

    exact = _photo("exact.jpg", [1.0, 0.0])
    close = _photo("close.jpg", [0.9, 0.1])
    middle = _photo("middle.jpg", [0.5, 0.866])
    far = _photo("far.jpg", [0.0, 1.0])
    without_vector = _photo("nov.jpg", None)
    db.commit()

    try:
        yield {
            "db": db,
            "album": album,
            "owner": owner,
            "exact": exact,
            "close": close,
            "middle": middle,
            "far": far,
            "without_vector": without_vector,
        }
    finally:
        db.close()
        engine.dispose()


def _ids(photos):
    return [photo.id for photo in photos]


def test_sqlite_smart_album_sorts_by_cosine_distance(smart_album):
    """SQLite 智能相册按余弦距离从小到大返回照片。"""
    db = smart_album["db"]
    album = smart_album["album"]

    ordered = _ids(crud_photo.get_photos(db, album.id, skip=0, limit=0))

    assert ordered.index(smart_album["exact"].id) < ordered.index(smart_album["close"].id)
    assert ordered.index(smart_album["close"].id) < ordered.index(smart_album["middle"].id)


def test_sqlite_smart_album_excludes_photos_beyond_threshold(smart_album):
    """超过相似度阈值的照片不会进入智能相册。"""
    db = smart_album["db"]
    album = smart_album["album"]

    ordered = _ids(crud_photo.get_photos(db, album.id, skip=0, limit=0))

    assert smart_album["far"].id not in ordered


def test_sqlite_smart_album_excludes_photos_without_vector(smart_album):
    """没有向量记录的照片不会进入智能相册。"""
    db = smart_album["db"]
    album = smart_album["album"]

    ordered = _ids(crud_photo.get_photos(db, album.id, skip=0, limit=0))

    assert smart_album["without_vector"].id not in ordered


def test_sqlite_smart_album_respects_limit_and_skip(smart_album):
    """limit/skip 在 SQLite 排序分支同样生效。"""
    db = smart_album["db"]
    album = smart_album["album"]

    everything = _ids(crud_photo.get_photos(db, album.id, skip=0, limit=0))
    first_two = _ids(crud_photo.get_photos(db, album.id, skip=0, limit=2))
    skipped = _ids(crud_photo.get_photos(db, album.id, skip=1, limit=2))

    assert len(everything) == 3
    assert first_two == everything[:2]
    assert skipped == everything[1:3]


def test_sqlite_smart_album_with_zero_target_embedding(smart_album):
    """查询向量全零时不崩溃，按空结果返回。"""
    db = smart_album["db"]
    album = smart_album["album"]
    album.query_embedding = [0.0] * 512
    db.commit()

    photos = crud_photo.get_photos(db, album.id, skip=0, limit=0)

    assert photos == []


def test_sqlite_smart_album_threshold_narrows_results(smart_album):
    """提高相似度阈值后，只剩下最相似的照片。"""
    db = smart_album["db"]
    album = smart_album["album"]
    album.threshold = 0.95
    db.commit()

    ordered = _ids(crud_photo.get_photos(db, album.id, skip=0, limit=0))

    assert smart_album["exact"].id in ordered
    assert smart_album["close"].id in ordered
    assert smart_album["middle"].id not in ordered

