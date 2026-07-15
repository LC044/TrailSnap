import pytest
import urllib.request
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch
import json
import sys

from trailsnap.utils import make_request, load_env

pytestmark = [pytest.mark.smoke]

@pytest.fixture
def mock_env(monkeypatch):
    # Mock environment to return fake URL and token
    monkeypatch.setattr("trailsnap.utils.load_env", lambda: {
        "TRAILSNAP_API_URL": "http://localhost:8000/api",
        "TRAILSNAP_API_TOKEN": "fake_token_123"
    })

def test_make_request_success(mock_env, monkeypatch):
    # Mock urlopen
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "code": 0,
        "msg": "success",
        "data": {"foo": "bar"}
    }).encode("utf-8")
    mock_response.headers.get.return_value = "req-123"

    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value = mock_response
    monkeypatch.setattr(urllib.request, "urlopen", lambda req: mock_urlopen)

    res = make_request("/test-endpoint", method="GET")
    assert res == {"foo": "bar"}

def test_make_request_api_error(mock_env, monkeypatch):
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "code": 40001,
        "msg": "some error",
    }).encode("utf-8")
    mock_response.headers.get.return_value = "req-123"

    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value = mock_response
    monkeypatch.setattr(urllib.request, "urlopen", lambda req: mock_urlopen)

    # _print_error_and_exit will call sys.exit(1)
    with pytest.raises(SystemExit) as e:
        make_request("/test-endpoint", method="GET")
    
    assert e.type == SystemExit
    assert e.value.code == 1

def test_make_request_http_error(mock_env, monkeypatch):
    def mock_urlopen_error(req):
        mock_fp = MagicMock()
        mock_fp.read.return_value = b'{"detail": "Not found"}'
        raise HTTPError("http://localhost", 404, "Not Found", {"X-Request-Id": "req-404"}, mock_fp)
    
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_error)

    with pytest.raises(SystemExit) as e:
        make_request("/not-found", method="GET")
    
    assert e.type == SystemExit
    assert e.value.code == 1

def test_make_request_post_json(mock_env, monkeypatch):
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"code": 0, "msg": "ok", "data": True}).encode("utf-8")
    
    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value = mock_response
    
    # Check that request was built with correct body
    def mock_urlopen_wrapper(req):
        assert req.method == "POST"
        assert req.data == b'{"name": "test_album"}'
        assert req.headers["Content-type"] == "application/json"
        assert req.headers["Authorization"] == "Bearer fake_token_123"
        return mock_urlopen

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_wrapper)

    res = make_request("/albums", method="POST", json_data={"name": "test_album"})
    assert res is True
