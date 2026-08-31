"""Health and public contract checks against the running backend."""

from typing import Any, Callable

import pytest
import requests


pytestmark = pytest.mark.smoke


def test_public_health_endpoints(
    api_request: Callable[..., requests.Response],
) -> None:
    root = api_request("GET", "/")
    assert root.status_code == 200
    root_payload = root.json()
    assert "Ready" in root_payload["message"]

    health = api_request("GET", "/health-check")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    discovery = api_request("GET", "/discovery")
    assert discovery.status_code == 200
    discovery_payload = discovery.json()
    assert discovery_payload["code"] == 0
    assert discovery_payload["data"]["service"] == "trailsnap"
    assert discovery_payload["data"]["api_path"] == "/api"
    assert discovery_payload["data"]["version"]

    version = api_request("GET", "/system/version")
    assert version.status_code == 200
    assert version.json().get("version")


def test_database_and_task_contracts(
    api_request: Callable[..., requests.Response],
) -> None:
    auth_status = api_request("GET", "/auth/status")
    assert auth_status.status_code == 200
    auth_payload = auth_status.json()
    assert isinstance(auth_payload["has_users"], bool)
    assert isinstance(auth_payload["allow_registration"], bool)

    task_types = api_request("GET", "/tasks/types")
    assert task_types.status_code == 200
    task_payload: dict[str, Any] = task_types.json()
    assert task_payload["code"] == 0
    assert task_payload["msg"] == "success"
    assert isinstance(task_payload["data"], list)
    assert task_payload["data"]
    assert all(
        isinstance(item.get("type"), str)
        and isinstance(item.get("description"), str)
        for item in task_payload["data"]
    )


def test_protected_album_endpoint_requires_auth(
    api_request: Callable[..., requests.Response],
) -> None:
    response = api_request("GET", "/albums")
    assert response.status_code == 401
