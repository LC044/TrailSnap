"""2026-10-29 nightly coverage for the AI service package.

The nightly AI coverage scan reported two modules with a stubborn dark half:

* ``services/fly_ticket_parser.py`` at 94.7% -- the noise guards that keep
  an order header ("订单完成") from being read as the flight time, the
  year inference on the split date/time path, the four-digit-number guard
  on the price fallback, the weekday/airline guard on the city arrow and
  the plain-name fallback.
* ``services/unified_model_manager.py`` at 96.2% -- the model download
  lifecycle: the already-ready short circuit, the failure bookkeeping, the
  unpublished-candidate guards and the path-escape guard.

Both modules make decisions that corrupt data when they are wrong (a flight
booked for the wrong day, a model deleted while it is still downloading), so
the tests pin the behaviour rather than the implementation.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# fly_ticket_parser
# ---------------------------------------------------------------------------


@pytest.fixture()
def parser():
    from app.services.fly_ticket_parser import FlightTicketParser

    return FlightTicketParser()


def test_an_order_header_is_not_read_as_the_flight_datetime(parser):
    """``订单完成`` marks the booking state, not the departure time."""
    result = parser.parse(["2025-09-27 13:25 订单完成", "CA1234"])

    assert result["datetime"] is None
    assert result["flight_code"] == "CA1234"


def test_an_order_header_still_yields_the_datetime_when_it_looks_like_a_flight(parser):
    """The guard keeps the line when it also carries flight wording."""
    result = parser.parse(["2025-09-27 13:25 订单完成 直飞", "CA1234"])

    assert result["datetime"] == "2025-09-27 13:25"


def test_a_split_date_infers_the_current_year(parser):
    """The date and the time sit on different lines, so strategy 2.2 runs."""
    result = parser.parse(["9月27日", "CA1234 13:25"])

    assert result["datetime"] == f"{datetime.now().year}-09-27 13:25"
    assert result.get("year_source") == "inferred_current_year"


def test_a_four_digit_year_is_not_taken_as_the_price(parser):
    """``2025`` looks like a price but is a year."""
    result = parser.parse(["CA1234", "2025"])

    assert result["price"] is None


def test_a_city_arrow_containing_a_departure_word_is_skipped(parser):
    """``北京-出发`` is a label, not a route."""
    result = parser.parse(["北京-出发"])

    assert result["departure_city"] is None
    assert result["arrival_city"] is None


def test_a_plain_two_character_name_is_used_as_the_passenger(parser):
    """Strategy B is the last resort and still has to work."""
    result = parser.parse(["张三"])

    assert result["name"] == "张三"


def test_an_excluded_word_is_not_used_as_the_passenger(parser):
    result = parser.parse(["订单"])

    assert result["name"] is None


# ---------------------------------------------------------------------------
# unified_model_manager
# ---------------------------------------------------------------------------


def _manager(tmp_path, models=None, tasks=None, selections=None, status=None):
    from app.services.unified_model_manager import UnifiedModelManager

    manager = object.__new__(UnifiedModelManager)
    manager.model_root = (tmp_path / "models").resolve()
    manager.model_root.mkdir(parents=True, exist_ok=True)
    manager.config_path = tmp_path / "ai_config.json"
    manager.legacy_config_path = tmp_path / "legacy_ai_config.json"
    manager._lock = threading.RLock()
    manager._download_lock = threading.Lock()
    manager._active_download = None
    manager._status = dict(status or {})
    manager._errors = {}
    manager._pending_selections = {}
    manager._models = dict(models or {})
    manager._catalog = {"models": list((models or {}).values()), "tasks": dict(tasks or {})}
    manager._selections = dict(selections or {})
    return manager


def _spec(model_id, *, tasks=("ocr",), available=True, local_dir=None,
          required_files=("model.onnx",), sources=None):
    return {
        "id": model_id,
        "name": model_id,
        "runtimeName": f"{model_id}-runtime",
        "localDir": local_dir or f"models/{model_id}",
        "requiredFiles": list(required_files),
        "tasks": list(tasks),
        "available": available,
        "repoId": f"owner/{model_id}",
        "sources": sources,
    }


def _make_ready(manager, model_id):
    base = manager.model_root / manager._models[model_id]["localDir"]
    base.mkdir(parents=True, exist_ok=True)
    for item in manager._models[model_id]["requiredFiles"]:
        (base / item).write_bytes(b"x")
    return base


def test_get_model_file_refuses_a_path_outside_the_model_root(tmp_path):
    models = {"a": _spec("a")}
    manager = _manager(
        tmp_path, models=models, tasks={"ocr": {"default": "a"}},
        selections={"ocr": "a"},
    )

    with pytest.raises(ValueError, match="越界"):
        manager.get_model_file("ocr", "../../../outside.bin")


def test_download_short_circuits_when_the_model_is_already_ready(tmp_path):
    models = {"a": _spec("a")}
    manager = _manager(tmp_path, models=models, tasks={"ocr": {"default": "a"}})
    _make_ready(manager, "a")
    manager._activate_pending_selections = lambda model_id: None

    manager._download("a")

    assert manager._status["a"] == "ready"
    assert manager._errors["a"] is None


def test_download_records_the_failure_and_the_error_message(tmp_path):
    models = {"a": _spec("a", sources=[{"repoId": None}])}
    manager = _manager(tmp_path, models=models, tasks={"ocr": {"default": "a"}})

    manager._download("a")

    assert manager._status["a"] == "failed"
    assert "repoId" in (manager._errors["a"] or "")


def test_download_fails_when_a_required_file_is_missing(tmp_path):
    models = {"a": _spec("a", sources=[{"repoId": "owner/a"}])}
    manager = _manager(tmp_path, models=models, tasks={"ocr": {"default": "a"}})
    manager._download_snapshot = lambda repo_id, target, merged: target.mkdir(
        parents=True, exist_ok=True
    )

    manager._download("a")

    assert manager._status["a"] == "failed"
    assert "model.onnx" in (manager._errors["a"] or "")


def test_trigger_download_rejects_an_unpublished_model(tmp_path):
    models = {"a": _spec("a", available=False)}
    manager = _manager(tmp_path, models=models, tasks={"ocr": {"default": "a"}})

    with pytest.raises(ValueError, match="尚未发布"):
        manager.trigger_download("a")


def test_select_model_activates_a_model_that_is_already_ready(tmp_path):
    models = {"a": _spec("a")}
    manager = _manager(tmp_path, models=models, tasks={"ocr": {"default": "a"}})
    _make_ready(manager, "a")
    manager._activate_selection = lambda task, model_id: None
    manager._save_selections = lambda: None

    result = manager.select_model("ocr", "a")

    assert result == {"changed": True, "status": "active"}


def test_ready_replacement_requires_another_downloaded_model(tmp_path):
    models = {"a": _spec("a")}
    manager = _manager(
        tmp_path, models=models,
        tasks={"ocr": {"default": "a", "name": "文字识别"}},
    )

    with pytest.raises(RuntimeError, match="没有其他已下载模型"):
        manager._ready_replacement("ocr", "a")


def test_ready_replacement_prefers_the_task_default(tmp_path):
    models = {
        "a": _spec("a"),
        "b": _spec("b"),
    }
    manager = _manager(
        tmp_path, models=models,
        tasks={"ocr": {"default": "b", "name": "文字识别"}},
    )
    _make_ready(manager, "a")
    _make_ready(manager, "b")

    assert manager._ready_replacement("ocr", "a") == "b"


def test_delete_model_refuses_while_the_model_is_downloading(tmp_path):
    models = {"a": _spec("a")}
    manager = _manager(
        tmp_path, models=models, tasks={"ocr": {"default": "a"}},
        status={"a": "downloading"},
    )

    with pytest.raises(RuntimeError, match="正在下载"):
        manager.delete_model("a")


