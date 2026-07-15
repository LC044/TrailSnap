import pytest
import sys
import json
from unittest.mock import patch
from io import StringIO
import os

from trailsnap import cli

pytestmark = [pytest.mark.smoke]

def run_cli(*args):
    """Helper to run CLI and return (exit_code, stdout_str, stderr_str)"""
    test_args = ["trailsnap"] + list(args)
    
    stdout = StringIO()
    stderr = StringIO()
    
    with patch.object(sys, "argv", test_args):
        # Patch stdout/stderr so we don't spam test output and can assert on it
        with patch('sys.stdout', stdout), patch('sys.stderr', stderr):
            try:
                cli.main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code
                
    return exit_code, stdout.getvalue(), stderr.getvalue()

@pytest.fixture
def auth_cli(isolated_cli_env, api_base_url, test_user_credentials):
    """Fixture to ensure CLI is logged in for subsequent tests"""
    # Wait, api_base_url has /api suffix, config login needs the base url without /api or it might handle it
    # Actually, config login's url should be the base URL.
    # trailsnap.utils.make_request does: f"{base_url.rstrip('/')}{endpoint}"
    # So if we pass http://localhost:8000/api, make_request with /auth/login will become http://localhost:8000/api/auth/login. That's correct.
    
    email = test_user_credentials["email"]
    password = test_user_credentials["password"]
    
    code, out, err = run_cli("config", "login", "--email", email, "--password", password, "--url", api_base_url)
    assert code == 0, f"Login failed: {err}"
    
    return True

def test_tasks_list(auth_cli):
    code, out, err = run_cli("--format", "json", "tasks", "list")
    assert code == 0, f"Error: {err}"
    if out.strip():
        data = json.loads(out)
        assert isinstance(data, list)
    else:
        assert "未查询到" in err or "无数据" in err or "未找到" in err

def test_config_test(auth_cli):
    code, out, err = run_cli("config", "test")
    assert code == 0
    assert "连接成功" in out

def test_albums_crud(auth_cli):
    # 1. Create album
    code, out, err = run_cli("--format", "json", "albums", "create", "--name", "CLI Integration Test Album", "--type", "normal")
    assert code == 0, err
    data = json.loads(out)
    album_id = data["id"]
    
    # 2. Get info
    code, out, err = run_cli("--format", "json", "albums", "info", "--id", album_id)
    assert code == 0
    data = json.loads(out)
    assert data["name"] == "CLI Integration Test Album"
    
    # 3. Update album
    code, out, err = run_cli("--format", "json", "albums", "update", "--id", album_id, "--name", "CLI Integration Test Album Updated")
    assert code == 0
    
    # 4. List albums
    code, out, err = run_cli("--format", "json", "albums", "list")
    assert code == 0
    data = json.loads(out)
    assert any(a["id"] == album_id for a in data)
    
    # 5. Delete album
    code, out, err = run_cli("--format", "json", "albums", "delete", "--id", album_id, "--yes")
    assert code == 0

def test_config_whoami(auth_cli):
    code, out, err = run_cli("--format", "json", "config", "whoami")
    assert code == 0, f"Error: {err}"
    assert "当前用户:" in out

def test_tasks_status(auth_cli):
    code, out, err = run_cli("--format", "json", "tasks", "status")
    assert code == 0, f"Error: {err}"
    data = json.loads(out)
    assert isinstance(data, dict)

def test_people_list(auth_cli):
    code, out, err = run_cli("--format", "json", "people", "list")
    assert code == 0, f"Error: {err}"
    if out.strip():
        data = json.loads(out)
        assert isinstance(data, list)
    else:
        assert "未查询到" in err or "无数据" in err

def test_locations_list(auth_cli):
    code, out, err = run_cli("--format", "json", "locations", "list")
    assert code == 0, f"Error: {err}"
    if out.strip():
        data = json.loads(out)
        assert isinstance(data, list)
    else:
        assert "未查询到" in err or "无数据" in err

def test_locations_scenes_list(auth_cli):
    code, out, err = run_cli("--format", "json", "locations", "scenes", "list")
    assert code == 0, f"Error: {err}"
    if out.strip():
        data = json.loads(out)
        assert isinstance(data, list)
    else:
        assert "未查询到" in err or "无数据" in err
    
def test_toolbox_cleanup_list(auth_cli):
    code, out, err = run_cli("--format", "json", "toolbox", "cleanup", "list")
    assert code == 0, f"Error: {err}"
    if out.strip():
        data = json.loads(out)
        assert isinstance(data, list)
    else:
        assert "未查询到" in err or "无数据" in err or "未找到" in err
