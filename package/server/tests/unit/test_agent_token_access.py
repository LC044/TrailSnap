import pytest
from fastapi import HTTPException

from app.service.agent_token_access import enforce_agent_token_rest_access, required_rest_scope


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


@pytest.mark.parametrize(
    ("path", "scope"),
    [
        ("/photos", "photos:read"),
        ("/photos/abc", "photos:read"),
        ("/medias/abc/thumbnail", "photos:read"),
        ("/albums/abc", "albums:read"),
        ("/faces/identities", "people:read"),
    ],
)
def test_required_rest_scope_maps_read_domains(path, scope):
    assert required_rest_scope(path) == scope


def test_agent_token_allows_matching_read_scope_and_whoami():
    enforce_agent_token_rest_access("GET", "/photos", ["photos:read"])
    enforce_agent_token_rest_access("GET", "/users/me", [])


def test_agent_token_rejects_missing_scope():
    with pytest.raises(HTTPException) as exc_info:
        enforce_agent_token_rest_access("GET", "/albums", ["photos:read"])
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail.endswith("albums:read")


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_agent_token_rejects_all_rest_writes(method):
    with pytest.raises(HTTPException) as exc_info:
        enforce_agent_token_rest_access(method, "/photos/abc", ["photos:read"])
    assert exc_info.value.status_code == 403
    assert "只读" in exc_info.value.detail


def test_agent_token_denies_unmapped_rest_endpoint():
    with pytest.raises(HTTPException) as exc_info:
        enforce_agent_token_rest_access("GET", "/settings", ["photos:read"])
    assert exc_info.value.status_code == 403
