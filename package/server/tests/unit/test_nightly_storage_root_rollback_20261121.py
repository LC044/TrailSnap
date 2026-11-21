"""夜间盲区补测：便携图库存储根注册与事务回滚后的缓存清理。

覆盖 app/db/session.py 的 ``_clear_rolled_back_storage_roots`` 与
app/service/storage_paths.py 的 ``register_storage_root``。
"""
import json
from uuid import uuid4

import pytest

from app.db import session as session_mod
from app.service import storage_paths

pytestmark = [pytest.mark.smoke, pytest.mark.regression]


@pytest.fixture()
def storage_db(tmp_path):
    """真实 SQLite 会话：注册存储根需要读写 StorageRoot 表。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.db.models  # noqa: F401
    from app.db.base import Base

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'roots.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def instance_root(tmp_path, monkeypatch):
    """构造一个便携实例根，library.json 提供 libraryId 命名空间。"""
    root = tmp_path / "instance"
    root.mkdir()
    (root / "library.json").write_text(
        json.dumps({"libraryId": str(uuid4())}), encoding="utf-8"
    )
    monkeypatch.setattr(storage_paths, "instance_root", lambda: root)
    return root


def test_rollback_clears_cached_roots_only_in_portable_mode(monkeypatch):
    """便携模式下回滚必须丢弃已缓存的存储根，避免复用被回滚的 FK。"""
    monkeypatch.setattr(storage_paths, "portable_enabled", lambda: True)
    storage_paths._roots["stale"] = {"id": "stale"}

    session_mod._clear_rolled_back_storage_roots(None)

    assert storage_paths._roots == {}


def test_rollback_keeps_cached_roots_when_portable_mode_is_off(monkeypatch):
    """非便携模式没有可回滚的存储根事务，缓存必须原样保留。"""
    monkeypatch.setattr(storage_paths, "portable_enabled", lambda: False)
    storage_paths._roots["keep"] = {"id": "keep"}

    session_mod._clear_rolled_back_storage_roots(None)

    assert storage_paths._roots == {"keep": {"id": "keep"}}


def test_register_storage_root_is_idempotent_for_same_owner_and_location(storage_db, instance_root):
    """同一 owner + 位置重复注册必须复用同一条记录，而不是插入重复行。"""
    from app.db.models.storage_root import StorageRoot

    owner_id = uuid4()
    anchor = instance_root / "albums"

    storage_paths.register_storage_root(storage_db, owner_id, anchor, "外部图库")
    storage_paths.register_storage_root(storage_db, owner_id, anchor, "外部图库")
    storage_db.commit()

    rows = storage_db.query(StorageRoot).filter(StorageRoot.owner_id == owner_id).all()
    assert len(rows) == 1
    assert rows[0].kind == "managed"
    assert rows[0].location == "albums"
    assert rows[0].name == "外部图库"
    assert str(rows[0].id) in storage_paths._roots


def test_register_storage_root_marks_outside_anchor_as_external(storage_db, instance_root, tmp_path):
    """实例根之外的锚点必须记为 external，且保留绝对路径。"""
    from app.db.models.storage_root import StorageRoot

    owner_id = uuid4()
    outside = tmp_path / "external-drive"
    outside.mkdir()

    storage_paths.register_storage_root(storage_db, owner_id, outside, "外部图库")
    storage_db.commit()

    row = storage_db.query(StorageRoot).filter(StorageRoot.owner_id == owner_id).one()
    assert row.kind == "external"
    assert row.location == str(outside.resolve())
