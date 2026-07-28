"""Tests for export filename template expansion and sanitization."""
from datetime import datetime
from types import SimpleNamespace
import pytest
from app.utils.export_formatter import format_export_filename

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]

def test_format_export_filename_expands_time_and_sequences():
    photo = SimpleNamespace(photo_time=datetime(2026, 7, 28, 9, 8, 7), upload_time=None)
    result = format_export_filename("{date}_{time}_{sequence3}_{original}", photo, 4, original_filename="IMG_1.jpg")
    assert result == "2026-07-28_090807_004_IMG_1"

def test_format_export_filename_uses_exif_fallbacks_and_sanitizes_values():
    photo = SimpleNamespace(photo_time=None, upload_time=datetime(2025, 1, 2, 3, 4))
    metadata = SimpleNamespace(city="北/京", address="朝阳:区", make=None, model=None, exif_info='{"Make":"Fuji","Model":"X/T","LensModel":"23*2","ISO":400}')
    result = format_export_filename("{city}_{location}_{camera}_{lens}_{iso}", photo, 1, metadata=metadata)
    assert result == "北_京_朝阳_区_Fuji X_T_23_2_400"

def test_format_export_filename_drops_unknown_placeholders_and_handles_bad_exif():
    photo = SimpleNamespace(photo_time=datetime(2024, 2, 3), upload_time=None)
    metadata = SimpleNamespace(city=None, address=None, make=None, model=None, exif_info="bad-json")
    assert format_export_filename("{unknown}-{camera}-{lens}-{iso}", photo, 1, metadata) == "-未知相机-未知镜头-未知ISO"
