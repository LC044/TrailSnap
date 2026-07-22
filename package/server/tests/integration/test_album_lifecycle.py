"""PostgreSQL-backed album CRUD integration tests."""

from typing import Any, Callable
from uuid import UUID, uuid4

import pytest
import requests


pytestmark = [pytest.mark.regression, pytest.mark.module_album, pytest.mark.postgres]


def _assert_success(response: requests.Response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == 0, payload
    assert payload["msg"] == "success", payload
    assert isinstance(payload["data"], dict | list | type(None)), payload
    return payload


def test_user_album_lifecycle(
    api_request: Callable[..., requests.Response],
    auth_headers: dict[str, str],
) -> None:
    album_name = f"itest-album-{uuid4().hex[:8]}"
    create = api_request(
        "POST",
        "/albums",
        headers=auth_headers,
        json={"name": album_name, "type": "user"},
    )
    created_payload = _assert_success(create)
    album = created_payload["data"]
    assert isinstance(album, dict)
    album_id = UUID(str(album["id"]))
    assert album["name"] == album_name
    assert album["type"] == "user"

    try:
        listed = api_request("GET", "/albums", headers=auth_headers)
        listed_payload = _assert_success(listed)
        assert any(item["id"] == str(album_id) for item in listed_payload["data"])

        fetched = api_request(
            "GET", f"/albums/{album_id}", headers=auth_headers
        )
        fetched_payload = _assert_success(fetched)
        assert fetched_payload["data"]["id"] == str(album_id)
        assert fetched_payload["data"]["name"] == album_name

        renamed = f"{album_name}-renamed"
        updated = api_request(
            "PUT",
            f"/albums/{album_id}",
            headers=auth_headers,
            json={"name": renamed},
        )
        updated_payload = _assert_success(updated)
        assert updated_payload["data"]["name"] == renamed

        photos = api_request(
            "GET", f"/albums/{album_id}/photos", headers=auth_headers
        )
        photos_payload = _assert_success(photos)
        assert photos_payload["data"] == []
    finally:
        deleted = api_request(
            "DELETE", f"/albums/{album_id}", headers=auth_headers
        )
        deleted_payload = _assert_success(deleted)
        assert deleted_payload["data"]["id"] == str(album_id)

    missing = api_request("GET", f"/albums/{album_id}", headers=auth_headers)
    assert missing.status_code == 200
    assert missing.json()["code"] == 404
    assert missing.json()["data"] is None


def test_missing_album_returns_base_response_not_found(
    api_request: Callable[..., requests.Response],
    auth_headers: dict[str, str],
) -> None:
    missing = api_request("GET", f"/albums/{uuid4()}", headers=auth_headers)
    assert missing.status_code == 200
    payload = missing.json()
    assert payload["code"] == 404
    assert payload["data"] is None
