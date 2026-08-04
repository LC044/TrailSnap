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

def test_extract_yyyy_mm_dd_hh_mm_ss_pattern():
    assert extract_datetime_from_filename("video_2023-10-15_14-30-00.mp4") == datetime(2023, 10, 15, 14, 30, 0)


def test_extract_compact_yyyymmddhhmmss():
    assert extract_datetime_from_filename("photo_20231015143000.jpeg") == datetime(2023, 10, 15, 14, 30, 0)


def test_extract_unix_seconds_timestamp():
    # 1697365800 -> 2023-10-15 18:30:00 UTC; we only check the parsed datetime is
    # non-None because local timezone offset varies.
    result = extract_datetime_from_filename("data_1697365800.csv")
    assert result is not None
    assert result.year == 2023
    assert result.month == 10
    assert result.day == 15


def test_extract_unix_milliseconds_timestamp():
    result = extract_datetime_from_filename("log_1697365800000.txt")
    assert result is not None
    assert result.year == 2023
    assert result.month == 10
    assert result.day == 15


def test_extract_invalid_oversized_timestamp():
    # 9999999999999 is 13-digit but overflows datetime range; should return None.
    assert extract_datetime_from_filename("invalid_9999999999999.txt") is None


def test_extract_t_pattern():
    # YYYYMMDDTHHMMSS
    assert extract_datetime_from_filename("recording_20231015T143000.avi") == datetime(2023, 10, 15, 14, 30, 0)


def test_extract_returns_none_for_future_date_outside_range():
    # Year 2099 is outside the valid 1990-2045 window so valid_time returns None.
    assert extract_datetime_from_filename("far_future_20990101_120000.jpg") is None
