"""2026-11-18 nightly coverage for ``app/service/media_urls.py``.

No test file referenced ``app/service/media_urls.py``.  The module is the
single source of the canonical public thumbnail URL, so a change in the path
or in the optional size query breaks every client that renders a thumbnail.
"""

from __future__ import annotations

import pytest

from app.service.media_urls import thumbnail_url


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_the_small_thumbnail_has_no_query_string():
    assert thumbnail_url("user-1", "photo-1") == "/api/medias/user-1/photo-1/thumbnail"


def test_the_small_thumbnail_is_explicitly_the_same_as_the_default():
    assert thumbnail_url("user-1", "photo-1", "small") == thumbnail_url("user-1", "photo-1")


def test_another_size_is_passed_as_a_query_parameter():
    assert thumbnail_url("user-1", "photo-1", "large") == "/api/medias/user-1/photo-1/thumbnail?size=large"


def test_a_uuid_is_rendered_as_a_string():
    from uuid import uuid4

    user_id = uuid4()
    photo_id = uuid4()

    url = thumbnail_url(user_id, photo_id)

    assert url == f"/api/medias/{user_id}/{photo_id}/thumbnail"


def test_the_url_keeps_the_owner_and_the_photo_apart():
    url = thumbnail_url("owner", "photo", "medium")

    assert url.startswith("/api/medias/owner/photo/thumbnail")
