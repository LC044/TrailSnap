"""Live HTTP fixtures for backend integration tests."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import pytest
import requests
from dotenv import dotenv_values


_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / "tests" / ".env.test"
_REQUEST_TIMEOUT = 10


def _load_shared_env() -> None:
    """Load the shared test environment without overriding runner variables."""
    if not _ENV_FILE.exists():
        return
    for key, value in dotenv_values(_ENV_FILE).items():
        if value is not None:
            os.environ.setdefault(key, value)


_load_shared_env()


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return os.environ.get("TS_API_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def api_request(api_base_url: str) -> Callable[..., requests.Response]:
    def request(method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{api_base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT)
        return requests.request(method, url, **kwargs)

    return request


@pytest.fixture(scope="session", autouse=True)
def server_ready(api_request: Callable[..., requests.Response]) -> None:
    """Fail clearly when the runner did not leave a reachable backend."""
    last_error: Exception | None = None
    for _ in range(10):
        try:
            response = api_request("GET", "/health-check")
            if response.status_code == 200:
                return
            last_error = RuntimeError(
                f"/health-check returned HTTP {response.status_code}: {response.text[:300]}"
            )
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(0.5)

    pytest.fail(
        "Backend is not reachable at TS_API_BASE_URL; run the integration suite "
        f"through run-tests.ps1. Last error: {last_error}"
    )


def _json(response: requests.Response) -> dict[str, Any] | list[Any]:
    try:
        return response.json()
    except ValueError as exc:
        raise AssertionError(
            f"Expected JSON from {response.request.method} {response.url}, "
            f"got HTTP {response.status_code}: {response.text[:500]}"
        ) from exc


def _require_status(response: requests.Response, expected: int = 200) -> dict[str, Any] | list[Any]:
    payload = _json(response)
    assert response.status_code == expected, (
        f"Expected HTTP {expected}, got {response.status_code}: {payload}"
    )
    return payload


def _login(
    api_request: Callable[..., requests.Response], username: str, password: str
) -> tuple[str, dict[str, Any]]:
    response = api_request(
        "POST",
        "/auth/login",
        data={"username": username, "password": password},
    )
    payload = _require_status(response)
    assert isinstance(payload, dict)
    assert payload.get("token_type") == "bearer"
    token = payload.get("access_token")
    assert isinstance(token, str) and token

    me_response = api_request(
        "GET", "/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    me = _require_status(me_response)
    assert isinstance(me, dict)
    return token, me


@pytest.fixture(scope="session")
def admin_session(
    api_request: Callable[..., requests.Response],
) -> dict[str, Any]:
    """Get a superuser and leave registration enabled for downstream CLI tests."""
    status_response = api_request("GET", "/auth/status")
    status_payload = _require_status(status_response)
    assert isinstance(status_payload, dict)

    username: str
    password: str
    auth_status = status_payload
    if not auth_status.get("has_users"):
        username = f"itest_admin_{uuid.uuid4().hex[:8]}"
        password = "IntegrationAdmin123!"
        register_response = api_request(
            "POST",
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": password,
            },
        )
        _require_status(register_response)
    elif auth_status.get("allow_registration"):
        username = f"itest_admin_{uuid.uuid4().hex[:8]}"
        password = "IntegrationAdmin123!"
        register_response = api_request(
            "POST",
            "/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": password,
            },
        )
        _require_status(register_response)
    else:
        username = os.environ.get("TS_TEST_USERNAME", "e2e-admin")
        password = os.environ.get("TS_TEST_PASSWORD", "Passw0rd!123")

    token, user = _login(api_request, username, password)
    assert user.get("is_superuser") is True, (
        "Integration tests need a superuser. Configure TS_TEST_USERNAME and "
        "TS_TEST_PASSWORD for an existing administrator."
    )

    headers = {"Authorization": f"Bearer {token}"}
    if not auth_status.get("allow_registration"):
        config_response = api_request(
            "PUT",
            "/system/config",
            json={"security": {"allow_registration": True}},
            headers=headers,
        )
        _require_status(config_response)

    return {"token": token, "headers": headers, "user": user}


@pytest.fixture
def registered_user(
    api_request: Callable[..., requests.Response],
    admin_session: dict[str, Any],
) -> dict[str, Any]:
    username = f"itest_user_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "IntegrationUser123!"
    register_response = api_request(
        "POST",
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    user = _require_status(register_response)
    assert isinstance(user, dict)

    token, current_user = _login(api_request, email, password)
    user_id = current_user.get("id") or user.get("id")
    assert user_id

    try:
        yield {
            "username": username,
            "email": email,
            "password": password,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
            "user": current_user,
            "id": user_id,
        }
    finally:
        try:
            api_request(
                "DELETE",
                f"/users/{user_id}",
                headers=admin_session["headers"],
            )
        except requests.RequestException:
            pass


@pytest.fixture
def auth_headers(admin_session: dict[str, Any]) -> dict[str, str]:
    return admin_session["headers"]
