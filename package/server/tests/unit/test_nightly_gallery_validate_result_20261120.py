"""Gallery validation result payload."""
import os

import pytest

from app.service.gallery_service import _validate_result

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_reports_a_missing_path_as_not_existing():
    result = _validate_result(os.path.join("does", "not", "exist"), valid=True)
    assert result["exists"] is False
    assert result["readable"] is False


def test_reports_an_existing_readable_path(tmp_path):
    target = tmp_path / "gallery"
    target.mkdir()
    result = _validate_result(str(target), valid=True)
    assert result["exists"] is True
    assert result["readable"] is True


def test_empty_path_is_never_existing():
    result = _validate_result("", valid=True)
    assert result["exists"] is False
    assert result["readable"] is False


def test_keeps_the_registration_flag_in_sync_with_the_path():
    assert _validate_result("x", valid=True, registered_path="x")["registered"] is True
    assert _validate_result("x", valid=True)["registered"] is False


def test_defaults_the_warning_list_to_an_empty_list():
    assert _validate_result("x", valid=True)["warnings"] == []


def test_keeps_the_preserved_error_and_conflict_fields():
    result = _validate_result("x", valid=False, error="ERR", msg="boom", conflict_path="/other")
    assert result["valid"] is False
    assert result["error"] == "ERR"
    assert result["msg"] == "boom"
    assert result["conflict"] == "/other"
