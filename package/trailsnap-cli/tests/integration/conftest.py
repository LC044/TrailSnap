import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
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

@pytest.fixture
def test_user_credentials(api_base_url):
    """Register a random test user in the backend or use env vars"""
    # Generate a random test user for CLI tests
    email = f"cli_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    
    # Try to register the user
    req_data = json.dumps({"username": email.split("@")[0], "email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base_url}/auth/register",
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            pass # Registered successfully
    except urllib.error.HTTPError as e:
        # Ignore 400 (already exists) or 403 (registration disabled)
        print(f"Registration HTTPError: {e.code} - {e.read().decode('utf-8')}")
        pass
    except urllib.error.URLError as e:
        print(f"Warning: Failed to connect to server during registration: {e}")
        
    return {"email": email, "password": password}
