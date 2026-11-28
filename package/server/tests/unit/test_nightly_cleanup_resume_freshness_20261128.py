"""Nightly 2026-11-28: app/service/cleanup_resume.py 预览复用新鲜度盲区。

覆盖 freshness 的状态/过期/缺失状态/哈希缺失/状态一致/状态漂移/哈希失败/
请求非法等分支，以及 digest_rows 的顺序敏感性与 boundary 的上界裁剪。
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.photo import Photo
from app.service import cleanup_resume
from app.service.cleanup_resume import boundary, digest_rows, freshness

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def _request_payload(cleanup_mode="duplicate", scope=None):
    return {
        "scope": scope if scope is not None else {"source": "all"},
        "config": {"kind": "cleanup", "cleanup_mode": cleanup_mode},
    }


def _plan(**overrides):
    payload = {
        "status": "preview",
        "expires_at": datetime.utcnow() + timedelta(hours=1),
        "request": _request_payload(),
        "summary": {"catalog_state": {"scope": "abc", "hashes": "def"}},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_freshness_ignores_non_preview_plans():
    assert freshness(None, None, _plan(status="running")) is None


def test_freshness_ignores_non_resumable_modes():
    plan = _plan(request=_request_payload(cleanup_mode="quality"))
    assert freshness(None, None, plan) is None


def test_freshness_reports_expired_previews():
    plan = _plan(expires_at=datetime.utcnow() - timedelta(minutes=1))
    assert freshness(None, None, plan) == "expired"


def test_freshness_reports_unknown_without_saved_state():
    assert freshness(None, None, _plan(summary={})) == "unknown"


def test_freshness_duplicate_without_hashes_is_unknown(monkeypatch):
    plan = _plan(summary={"catalog_state": {"scope": "abc"}})
    calls = []
    monkeypatch.setattr(cleanup_resume, "catalog_state", lambda *a, **k: calls.append(a) or {})
    assert freshness(None, None, plan) == "unknown"
    assert calls == []


def test_freshness_reports_current_when_state_matches(monkeypatch):
    saved = {"scope": "abc", "hashes": "def"}
    plan = _plan(summary={"catalog_state": saved})
    seen = {}

    def _fake_catalog_state(db, user, request, *, include_hashes=False, **kwargs):
        seen["include_hashes"] = include_hashes
        return dict(saved)

    monkeypatch.setattr(cleanup_resume, "catalog_state", _fake_catalog_state)
    assert freshness(None, None, plan) == "current"
    assert seen["include_hashes"] is True


def test_freshness_reports_changed_when_state_differs(monkeypatch):
    plan = _plan(summary={"catalog_state": {"scope": "abc", "hashes": "def"}})
    monkeypatch.setattr(
        cleanup_resume,
        "catalog_state",
        lambda *a, **k: {"scope": "abc", "hashes": "changed"},
    )
    assert freshness(None, None, plan) == "changed"


def test_freshness_reports_unknown_when_hash_failed(monkeypatch):
    saved = {"scope": "abc", "hashes": "def"}
    plan = _plan(summary={"catalog_state": saved, "hash_failed": True})
    monkeypatch.setattr(cleanup_resume, "catalog_state", lambda *a, **k: dict(saved))
    assert freshness(None, None, plan) == "unknown"


def test_freshness_reports_changed_for_invalid_request():
    plan = _plan(request={"config": {"kind": "cleanup", "cleanup_mode": "duplicate"}})
    assert freshness(None, None, plan) == "changed"


def test_digest_rows_is_stable_and_order_sensitive():
    rows = [(1, "a"), (2, "b")]
    assert digest_rows(rows) == digest_rows(list(rows))
    assert digest_rows(rows) != digest_rows(list(reversed(rows)))


def test_digest_rows_normalizes_row_sequences():
    assert digest_rows([[1, "a"]]) == digest_rows([(1, "a")])


def test_boundary_without_snapshot_keeps_query_untouched():
    query = select(Photo.id)
    assert boundary(query, None, "snapshot_upper") is query


def test_boundary_filters_by_upper_bound():
    upper = uuid4()
    compiled = str(boundary(select(Photo.id), {"snapshot_upper": str(upper)}, "snapshot_upper"))
    assert "photos.id <=" in compiled


def test_boundary_without_upper_bound_disables_rows():
    compiled = str(boundary(select(Photo.id), {"snapshot_upper": None}, "snapshot_upper")).lower()
    assert "false" in compiled or "0 = 1" in compiled
