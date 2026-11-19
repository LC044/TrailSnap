"""Nightly 2026-11-18: app/utils/filename.py 时间戳与哈希文件名解析盲区。"""
from datetime import datetime

import pytest

from app.utils.filename import (
    contains_uuid_or_hash,
    is_valid_timestamp,
    is_within_range,
    valid_time,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_is_within_range_inclusive_bounds():
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)
    assert is_within_range(datetime(2020, 6, 1), start, end) is True
    assert is_within_range(start, start, end) is True
    assert is_within_range(end, start, end) is True


def test_is_within_range_outside_bounds():
    start = datetime(2020, 1, 1)
    end = datetime(2020, 12, 31)
    assert is_within_range(datetime(2019, 12, 31), start, end) is False
    assert is_within_range(datetime(2021, 1, 1), start, end) is False


def test_valid_time_accepts_past_and_rejects_future_and_pre_1990():
    assert valid_time(datetime(2021, 6, 1)) == datetime(2021, 6, 1)
    assert valid_time(datetime(1989, 1, 1)) is None
    assert valid_time(datetime.now().replace(year=datetime.now().year + 5)) is None


def test_contains_uuid_or_hash_detects_common_hash_shapes():
    assert contains_uuid_or_hash("photo-550e8400-e29b-41d4-a716-446655440000.jpg") is True
    assert contains_uuid_or_hash("d41d8cd98f00b204e9800998ecf8427e.jpg") is True
    assert contains_uuid_or_hash("a" * 40 + ".jpg") is True
    assert contains_uuid_or_hash("b" * 64 + ".jpg") is True


def test_contains_uuid_or_hash_ignores_plain_names():
    assert contains_uuid_or_hash("IMG_20200101_120000.jpg") is False
    # 14 位以内嵌时间戳不是哈希特征
    assert contains_uuid_or_hash("1700000000000.jpg") is False
    # 15 位以上孤立数字串视为哈希
    assert contains_uuid_or_hash("123456789012345.jpg") is True


def test_is_valid_timestamp_accepts_10_and_13_digit():
    ten = str(int(datetime(2021, 6, 1, 12, 0, 0).timestamp()))
    assert is_valid_timestamp(ten, "x.jpg") == datetime.fromtimestamp(int(ten))
    thirteen = ten + "000"
    assert is_valid_timestamp(thirteen, "x.jpg") == datetime.fromtimestamp(int(thirteen) / 1000)


def test_is_valid_timestamp_rejects_bad_length_and_uuid_files():
    assert is_valid_timestamp("123", "x.jpg") is None
    assert is_valid_timestamp("1700000000", "photo-d41d8cd98f00b204e9800998ecf8427e.jpg") is None


def test_is_valid_timestamp_rejects_out_of_range_and_garbage():
    assert is_valid_timestamp("0", "x.jpg") is None
    assert is_valid_timestamp("not-a-number", "x.jpg") is None
    assert is_valid_timestamp("999999999999999", "x.jpg") is None
