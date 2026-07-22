import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request
import json
import uuid

@pytest.fixture(scope="session")
def api_base_url():
    # Use TS_API_BASE_URL if available, else fallback
    url = os.environ.get("TS_API_BASE_URL", "http://localhost:8000")
    return url.rstrip("/")

@pytest.fixture
def isolated_cli_env():
    """Isolate CLI configuration so we don't overwrite user's local config"""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_env_file = Path(tmpdir) / ".env"
        with patch("trailsnap.utils.ENV_FILE", temp_env_file):
            yield temp_env_file


def _can_login(api_base_url, username, password):
    """Return whether the configured account can authenticate."""
    req_data = urllib.parse.urlencode(
        {"username": username, "password": password}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base_url}/auth/login",
        data=req_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError):
        return False


def _register_user(api_base_url, username, email, password):
    req_data = json.dumps(
        {"username": username, "email": email, "password": password}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base_url}/auth/register",
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        print(
            f"Registration HTTPError: {error.code} - "
            f"{error.read().decode('utf-8')}"
        )
        return False
    except urllib.error.URLError as error:
        print(f"Warning: Failed to connect to server during registration: {error}")
        return False


@pytest.fixture
def test_user_credentials(api_base_url):
    """Use the configured test account, or create an isolated CLI user."""
    configured_username = os.environ.get("TS_TEST_USERNAME")
    configured_password = os.environ.get("TS_TEST_PASSWORD")

    if configured_username and configured_password:
        # Reuse an existing account first. This keeps -Layer all from creating
        # an unrelated first user before the E2E suite logs in as this account.
        if _can_login(api_base_url, configured_username, configured_password):
            return {"email": configured_username, "password": configured_password}

        configured_email = (
            configured_username
            if "@" in configured_username
            else f"{configured_username}@example.com"
        )
        _register_user(
            api_base_url,
            configured_username,
            configured_email,
            configured_password,
        )
        if _can_login(api_base_url, configured_username, configured_password):
            return {"email": configured_username, "password": configured_password}

        pytest.fail(
            "无法使用 TS_TEST_USERNAME/TS_TEST_PASSWORD 登录或注册 CLI 测试账号："
            f"{configured_username}"
        )

    # Preserve the isolated-user behavior when no shared test account is configured.
    email = f"cli_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    _register_user(api_base_url, email.split("@")[0], email, password)
    return {"email": email, "password": password}
