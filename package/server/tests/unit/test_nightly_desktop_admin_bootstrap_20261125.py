"""Nightly watch 2026-11-25 · app/db/bootstrap.py 的桌面管理员引导分支。

覆盖扫描显示 bootstrap.py 只有一行未覆盖：ensure_desktop_admin 在非桌面模式
下的守卫（L26）。这条守卫决定了「非桌面部署不会凭空造出一个超级管理员」，
但现有测试只是 patch 掉 is_desktop_mode 从未真正走过分支，因此补上：

- 非桌面模式直接 RuntimeError，且不落库
- 桌面模式首次启动创建本地管理员（用户名 / 邮箱 / 超级用户标记）
- 桌面模式重复启动复用同一个管理员（幂等）
- 早期桌面版本遗留的 .local 邮箱在启动时被修复成可序列化的官方邮箱
"""

import pytest

from app.db import bootstrap
from app.db.models.user import User

pytestmark = [pytest.mark.regression, pytest.mark.module_system]


def test_desktop_admin_is_refused_outside_desktop_mode(face_sqlite_session, monkeypatch):
    monkeypatch.delenv("TS_DESKTOP", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        bootstrap.ensure_desktop_admin(face_sqlite_session)

    assert "desktop mode" in str(excinfo.value)
    assert face_sqlite_session.query(User).count() == 0


def test_desktop_admin_is_created_once_and_reused(face_sqlite_session, monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")

    created = bootstrap.ensure_desktop_admin(face_sqlite_session)

    assert created.username == bootstrap.DESKTOP_ADMIN_USERNAME
    assert created.email == bootstrap.DESKTOP_ADMIN_EMAIL
    assert created.is_superuser is True
    assert created.is_active is True
    assert created.hashed_password

    reused = bootstrap.ensure_desktop_admin(face_sqlite_session)

    assert reused.id == created.id
    assert face_sqlite_session.query(User).count() == 1


def test_legacy_desktop_email_is_repaired_on_startup(face_sqlite_session, monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    legacy = User(
        username=bootstrap.DESKTOP_ADMIN_USERNAME,
        email=bootstrap.LEGACY_DESKTOP_ADMIN_EMAIL,
        nickname="TrailSnap Desktop",
        hashed_password="legacy-hash",
        is_active=True,
        is_superuser=True,
        settings={},
    )
    face_sqlite_session.add(legacy)
    face_sqlite_session.commit()

    repaired = bootstrap.ensure_desktop_admin(face_sqlite_session)

    assert repaired.email == bootstrap.DESKTOP_ADMIN_EMAIL
    assert repaired.hashed_password == "legacy-hash"
    assert face_sqlite_session.query(User).count() == 1
