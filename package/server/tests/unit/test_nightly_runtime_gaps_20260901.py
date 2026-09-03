"""Nightly coverage for small, high-risk runtime and startup modules."""

import json
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.core import system_config
from app.core.logger import JSONFormatter, log_operation
from app.db import init_db
from app.service import discovery
from app.utils import path_validation
from app.utils.path_validation import validate_filename, validate_target_path


pytestmark = pytest.mark.smoke


def test_discovery_build_service_info_normalizes_url(monkeypatch):
    service_info = MagicMock()
    service_info_factory = MagicMock(return_value=service_info)
    monkeypatch.setattr(discovery, "ServiceInfo", service_info_factory)

    monkeypatch.setattr(discovery, "_resolve_addresses", lambda hostname: [__import__("ipaddress").ip_address("127.0.0.1").packed])
    result = discovery.build_service_info("https://TRAILSNAP.example:8443///", "  Family Album ")

    assert result is service_info
    kwargs = service_info_factory.call_args.kwargs
    assert kwargs["addresses"] == [__import__("ipaddress").ip_address("127.0.0.1").packed]
    assert kwargs["port"] == 8443
    assert kwargs["properties"]["url"] == "https://TRAILSNAP.example:8443"
    assert kwargs["properties"]["api_path"] == "/api"


def test_discovery_service_rejects_invalid_public_url(monkeypatch):
    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "https://trailsnap.example/path")
    zeroconf = MagicMock()
    monkeypatch.setattr(discovery, "build_service_info", MagicMock(side_effect=ValueError("invalid URL")))
    monkeypatch.setattr(discovery, "Zeroconf", MagicMock(return_value=zeroconf))

    discovery.DiscoveryService().start()

    zeroconf.register_service.assert_not_called()


def test_discovery_service_registers_and_releases_service(monkeypatch):
    info = MagicMock()
    zeroconf = MagicMock()
    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "https://trailsnap.example")
    monkeypatch.setattr(discovery, "build_service_info", MagicMock(return_value=info))
    monkeypatch.setattr(discovery, "Zeroconf", MagicMock(return_value=zeroconf))

    service = discovery.DiscoveryService()
    service.start()
    service.stop()

    zeroconf.register_service.assert_called_once_with(info, allow_name_change=True)
    zeroconf.unregister_service.assert_called_once_with(info)
    zeroconf.close.assert_called_once_with()


def test_json_formatter_includes_operation_and_exception():
    record = logging.LogRecord("nightly", logging.ERROR, __file__, 1, "operation failed", (), None)
    record.operation = "nightly-test"
    record.params = {"case": "error"}
    record.result = "failed"
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record.exc_info = sys.exc_info()

    payload = json.loads(JSONFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert payload["operation"] == "nightly-test"
    assert payload["params"] == {"case": "error"}
    assert "boom" in payload["stack_trace"]


def test_log_operation_preserves_structured_context(caplog):
    caplog.set_level(logging.INFO, logger="app")

    log_operation(
        "error",
        "nightly failure",
        operation="coverage",
        params={"attempt": 2},
        result="retry",
    )

    record = caplog.records[-1]
    assert record.getMessage() == "nightly failure"
    assert record.operation == "coverage"
    assert record.params == {"attempt": 2}
    assert record.result == "retry"


def test_validate_filename_accepts_normal_name_and_rejects_reserved_name():
    # Cross-platform cases work everywhere.
    validate_filename("family-photo.jpg", "/photos")
    with pytest.raises(ValueError, match="路径分隔符"):
        validate_filename("nested/secret.jpg", "/photos")
    with pytest.raises(ValueError, match="路径分隔符"):
        validate_filename("nested\\secret.jpg", "/photos")
    with pytest.raises(ValueError, match="不能为空"):
        validate_filename("", "/photos")
    with pytest.raises(ValueError, match="不能为空"):
        validate_filename("..", "/photos")
    with pytest.raises(ValueError, match="空字符"):
        validate_filename("bad\x00name.jpg", "/photos")

    # Windows-specific rules need the os.name patch on non-Windows CI runners.
    with patch.object(path_validation.os, "name", "nt"):
        with pytest.raises(ValueError, match="保留名称"):
            validate_filename("CON", "/photos")
        with pytest.raises(ValueError, match="Windows 文件名不能以空格或句点结尾"):
            validate_filename("photo.", "/photos")
        with pytest.raises(ValueError, match="不允许的字符"):
            validate_filename("photo:bad.jpg", "/photos")


def test_validate_target_path_rejects_reserved_name_and_dot_dot():
    # Windows-only behaviours must be exercised under a patched os.name so the
    # tests stay green on Linux CI runners as well as on Windows.
    with patch.object(path_validation.os, "name", "nt"):
        with pytest.raises(ValueError, match="保留名称"):
            validate_target_path("/photos/CON")
        with pytest.raises(ValueError, match="不允许的字符"):
            validate_target_path("/photos/photo:bad.jpg")

    # validate_target_path delegates to validate_filename with the basename,
    # so the cross-platform filename rules still apply on every platform.
    with pytest.raises(ValueError, match="不能为空"):
        validate_target_path("/photos/..")


def test_scan_schedule_to_cron_supports_modes_and_invalid_time():
    assert system_config.ScanScheduleSettings(mode="off").to_cron_expression() is None
    assert system_config.ScanScheduleSettings(mode="interval", interval=15).to_cron_expression() == "*/15 * * * *"
    assert system_config.ScanScheduleSettings(mode="weekly", time="06:30", weekdays=[1, 3]).to_cron_expression() == "30 6 * * 1,3"
    assert system_config.ScanScheduleSettings(mode="weekly", time="bad").to_cron_expression() is None


def test_proactive_schedule_to_cron_supports_interval_and_invalid_time():
    assert system_config.ProactiveMemoryScheduleSettings(mode="interval", interval=1440).to_cron_expression() == "*/1440 * * * *"
    assert system_config.ProactiveMemoryScheduleSettings(mode="weekly", time="bad").to_cron_expression() is None


def test_resolve_concurrency_auto_uses_computed_default(monkeypatch):
    monkeypatch.setattr(system_config, "get_default_concurrency_level", MagicMock(return_value="high"))
    assert system_config.resolve_concurrency_level("auto") == "high"
    assert system_config.resolve_concurrency_level("low") == "low"


def test_init_models_prints_completion(capsys):
    init_db.init_models()
    assert "数据库初始化完成" in capsys.readouterr().out
