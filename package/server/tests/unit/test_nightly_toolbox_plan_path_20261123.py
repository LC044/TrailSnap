"""Nightly gap coverage: toolbox PlanPath portable-path column type.

`PlanPath` is a `TypeDecorator` that round-trips `source_path` values through
the portable-config encoder.  Both directions are thin wrappers around
`app.utils.portable_config.transform_paths`, so the tests assert the encoder
contract (encode/decode flag + column key) instead of re-implementing it.
"""

import pytest

from app.db.models.toolbox import PlanPath


pytestmark = pytest.mark.smoke


def test_plan_path_bind_param_encodes_source_path(monkeypatch):
    captured = {}

    def fake_transform_paths(value, *, encode, key="", root=None):
        captured.update(value=value, encode=encode, key=key)
        return "encoded-path"

    monkeypatch.setattr("app.utils.portable_config.transform_paths", fake_transform_paths)

    assert PlanPath().process_bind_param("C:/photos/a.jpg", None) == "encoded-path"
    assert captured == {"value": "C:/photos/a.jpg", "encode": True, "key": "source_path"}


def test_plan_path_result_value_decodes_source_path(monkeypatch):
    captured = {}

    def fake_transform_paths(value, *, encode, key="", root=None):
        captured.update(value=value, encode=encode, key=key)
        return "decoded-path"

    monkeypatch.setattr("app.utils.portable_config.transform_paths", fake_transform_paths)

    assert PlanPath().process_result_value("portable:/photos/a.jpg", None) == "decoded-path"
    assert captured == {"value": "portable:/photos/a.jpg", "encode": False, "key": "source_path"}


def test_plan_path_passes_none_through_untouched(monkeypatch):
    """A NULL column must not be rewritten into an empty path."""
    calls = []

    def fake_transform_paths(value, *, encode, key="", root=None):
        calls.append((value, encode, key))
        return value

    monkeypatch.setattr("app.utils.portable_config.transform_paths", fake_transform_paths)

    assert PlanPath().process_bind_param(None, None) is None
    assert calls == [(None, True, "source_path")]
