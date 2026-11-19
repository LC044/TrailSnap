"""覆盖 app/service/user_storage.py 中此前没有测试引用的路径解析函数。

盲区来源：函数级静态引用扫描命中 _user_key / _configured_path /
_is_legacy_default_path / legacy_storage_base。

这些函数决定「照片存放在哪里」：
- _configured_path 从用户设置里取出自定义存储目录，类型不对时必须返回 None；
- _is_legacy_default_path 识别旧的默认目录（data/uploads），用于迁移到
  按用户隔离的新布局；漏判会让旧目录继续被当作用户目录使用；
- legacy_storage_base 返回迁移前的 uploads/thumbnails 根目录。

既有测试只走 ensure_user_layout 的整体流程，从未直接断言这些判定。
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.service import user_storage

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_user_key_is_the_plain_string_form_of_the_identifier():
    identifier = uuid4()
    assert user_storage._user_key(identifier) == str(identifier)
    assert user_storage._user_key("already-a-string") == "already-a-string"


def test_configured_path_reads_the_photo_storage_setting():
    assert user_storage._configured_path({"storage": {"photo_storage_path": "D:/photos"}}) == "D:/photos"
    # 未配置、缺少 storage 段、类型不对都必须退化为 None。
    assert user_storage._configured_path(None) is None
    assert user_storage._configured_path({}) is None
    assert user_storage._configured_path({"storage": {}}) is None
    assert user_storage._configured_path({"storage": {"photo_storage_path": 5}}) is None
    assert user_storage._configured_path({"storage": None}) is None


def test_legacy_default_path_detection():
    assert user_storage._is_legacy_default_path("data/uploads") is True
    assert user_storage._is_legacy_default_path("./data/uploads") is True
    assert user_storage._is_legacy_default_path("data/uploads/") is True
    # 反斜杠写法在 Windows 上等价于正斜杠写法。
    assert user_storage._is_legacy_default_path("data\\uploads") is True


def test_legacy_default_path_detection_ignores_unrelated_paths():
    assert user_storage._is_legacy_default_path(None) is False
    assert user_storage._is_legacy_default_path("") is False
    assert user_storage._is_legacy_default_path("D:/photos") is False
    assert user_storage._is_legacy_default_path("data/uploads-backup") is False


def test_legacy_storage_base_falls_back_to_the_shared_legacy_root():
    expected = os.path.abspath(os.path.expanduser(user_storage.LEGACY_DEFAULT_STORAGE_BASE))
    assert user_storage.legacy_storage_base(None) == expected
    assert user_storage.legacy_storage_base({}) == expected
    assert user_storage.legacy_storage_base({"storage": {"photo_storage_path": "data/uploads"}}) == expected


def test_legacy_storage_base_keeps_a_custom_directory():
    assert user_storage.legacy_storage_base(
        {"storage": {"photo_storage_path": "D:/custom-photos"}}
    ) == os.path.abspath(os.path.expanduser("D:/custom-photos"))


def test_user_root_is_namespaced_under_the_storage_base():
    identifier = uuid4()
    root = user_storage.get_user_root(identifier, "D:/photos")
    assert root == os.path.join(os.path.abspath("D:/photos"), "users", str(identifier))


def test_storage_base_cache_round_trips_per_user():
    identifier = uuid4()
    try:
        base = user_storage.cache_storage_base(identifier, "D:/photos")
        assert base == os.path.abspath(os.path.expanduser("D:/photos"))
        assert user_storage.get_cached_storage_base(identifier) == base
    finally:
        user_storage._STORAGE_BASE_CACHE.pop(str(identifier), None)
    assert user_storage.get_cached_storage_base(identifier) is None
