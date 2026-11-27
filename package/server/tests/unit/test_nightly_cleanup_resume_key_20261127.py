"""Nightly 2026-11-27: app/service/cleanup_resume.py 预览复用请求键盲区。"""
from uuid import uuid4

import pytest

from app.schemas.toolbox import MediaScope, PhotoScopeFilters, PlanRequest, ToolConfig
from app.service.cleanup_resume import request_key

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def _request(scope=None, config=None):
    return PlanRequest(
        scope=scope or MediaScope(source="all"),
        config=config or ToolConfig(kind="cleanup", cleanup_mode="duplicate"),
    )


def test_request_key_ignores_album_order():
    albums = [uuid4(), uuid4(), uuid4()]
    first = _request(MediaScope(source="albums", album_ids=albums))
    second = _request(MediaScope(source="albums", album_ids=list(reversed(albums))))
    assert request_key(first) == request_key(second)


def test_request_key_ignores_unrelated_scope_lists():
    album = uuid4()
    folder = _request(MediaScope(source="albums", album_ids=[album], folders=[str(uuid4())]))
    album_only = _request(MediaScope(source="albums", album_ids=[album]))
    assert request_key(folder) == request_key(album_only)


def test_request_key_distinguishes_cleanup_mode():
    scope = MediaScope(source="all")
    duplicate = _request(scope, ToolConfig(kind="cleanup", cleanup_mode="duplicate"))
    similar = _request(scope, ToolConfig(kind="cleanup", cleanup_mode="similar"))
    assert request_key(duplicate) != request_key(similar)


def test_request_key_distinguishes_similarity_parameters():
    scope = MediaScope(source="all")
    fast = _request(scope, ToolConfig(kind="cleanup", cleanup_mode="similar", scan_mode="fast"))
    complete = _request(scope, ToolConfig(kind="cleanup", cleanup_mode="similar", scan_mode="complete"))
    assert request_key(fast) != request_key(complete)


def test_request_key_ignores_empty_filters():
    plain = _request(MediaScope(source="all"))
    filtered = _request(MediaScope(source="all", filters=PhotoScopeFilters(years=[2024])))
    empty = _request(MediaScope(source="all", filters=PhotoScopeFilters(years=[2024], cities=[])))
    assert request_key(filtered) == request_key(empty)
    assert request_key(plain) != request_key(filtered)


def test_request_key_include_children_only_for_folders():
    folder = str(uuid4())
    without_children = _request(MediaScope(source="folders", folders=[folder], include_children=False))
    with_children = _request(MediaScope(source="folders", folders=[folder], include_children=True))
    assert request_key(without_children) != request_key(with_children)
    unrelated = _request(MediaScope(source="all", include_children=False))
    still_unrelated = _request(MediaScope(source="all", include_children=True))
    assert request_key(unrelated) == request_key(still_unrelated)
