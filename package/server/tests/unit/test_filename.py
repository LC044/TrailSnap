"""
后端 smoke 单元测试 —— 文件名时间提取（纯函数，无外部服务）。

这组测试用来"打通流程"：证明 tests/.env.test 已加载、pytest marker 体系生效、
纯函数逻辑正确。秒级返回，是回归底线。
"""
import os
from datetime import datetime

import pytest

from app.utils.filename import extract_datetime_from_filename

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_env_loaded_from_shared_file():
    """tests/.env.test 经 conftest 加载后，TS_TEST_ENV 必须可见——四方共享 env 的证明。"""
    assert os.environ.get("TS_TEST_ENV"), "TS_TEST_ENV 未设置——tests/.env.test 未加载"


def test_extract_img_style_filename():
    assert extract_datetime_from_filename("IMG_20231201_120609.jpg") == datetime(2023, 12, 1, 12, 6, 9)


def test_extract_compact_datetime():
    assert extract_datetime_from_filename("20231201120609.jpg") == datetime(2023, 12, 1, 12, 6, 9)


def test_extract_dash_separated():
    assert extract_datetime_from_filename("2023-12-01 120609.jpg") == datetime(2023, 12, 1, 12, 6, 9)


def test_extract_returns_none_when_no_date():
    assert extract_datetime_from_filename("screenshot.png") is None


def test_extract_returns_none_for_uuid_hash_name():
    # 含 MD5/UUID 特征的文件名不应被误判为时间戳
    assert extract_datetime_from_filename("a3f0b1c2d4e5f6a7b8c9d0e1f2a3b4c5.jpg") is None
