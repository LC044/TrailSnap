import pytest

from app.service.discovery import SERVICE_TYPE, build_service_info


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_build_service_info_uses_public_entry_point():
    info = build_service_info("http://192.168.1.20:8082", "Family Photos")

    assert info.type == SERVICE_TYPE
    assert info.name == f"Family Photos.{SERVICE_TYPE}"
    assert info.port == 8082
    assert info.parsed_addresses() == ["192.168.1.20"]
    assert info.properties[b"url"] == b"http://192.168.1.20:8082"
    assert info.properties[b"api_path"] == b"/api"


@pytest.mark.parametrize(
    "value",
    ["", "ftp://192.168.1.20", "http://192.168.1.20:8082/path"],
)
def test_build_service_info_rejects_invalid_public_url(value):
    with pytest.raises(ValueError):
        build_service_info(value)
