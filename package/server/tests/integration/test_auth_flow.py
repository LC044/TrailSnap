"""Authentication and user identity integration tests."""

from typing import Any, Callable

import pytest
import requests


pytestmark = [pytest.mark.smoke, pytest.mark.module_user]


def test_register_login_and_current_user(
    api_request: Callable[..., requests.Response],
    registered_user: dict[str, Any],
) -> None:
    user = registered_user["user"]
    assert user["username"] == registered_user["username"]
    assert user["email"] == registered_user["email"]
    assert "password" not in user
    assert "hashed_password" not in user

    duplicate = api_request(
        "POST",
        "/auth/register",
        json={
            "username": registered_user["username"],
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert duplicate.status_code == 400

    wrong_password = api_request(
        "POST",
        "/auth/login",
        data={"username": registered_user["email"], "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401

    login = api_request(
        "POST",
        "/auth/login",
        data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert login.status_code == 200
    login_payload = login.json()
    assert login_payload["token_type"] == "bearer"
    assert login_payload["access_token"]

    current_user = api_request(
        "GET",
        "/users/me",
        headers=registered_user["headers"],
    )
    assert current_user.status_code == 200
    assert current_user.json()["id"] == registered_user["id"]
    assert current_user.json()["email"] == registered_user["email"]


def test_current_user_requires_auth(
    api_request: Callable[..., requests.Response],
) -> None:
    response = api_request("GET", "/users/me")
    assert response.status_code == 401

    invalid_token = api_request(
        "GET",
        "/users/me",
        headers={"Authorization": "Bearer definitely-invalid"},
    )
    assert invalid_token.status_code == 403


def test_admin_can_read_users(
    api_request: Callable[..., requests.Response],
    admin_session: dict[str, Any],
) -> None:
    response = api_request("GET", "/users/", headers=admin_session["headers"])
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert any(user["id"] == admin_session["user"]["id"] for user in users)
