"""Nightly watch 2026-11-13: coverage gaps for AI services.

Target modules (from tests/artifacts/nightly/2026-11-13/cov-ai.log):
- app/services/ticket_journey_parser.py (line 127: no elapsed time found)
- app/services/image_classification_service.py (model release path)
- app/services/onnx_providers.py (session option thread overrides)
"""

import pytest

from app.services import image_classification_service, onnx_providers, ticket_journey_parser


pytestmark = pytest.mark.smoke


def _card(*blocks):
    texts, polys = [], []
    for text, x, y in blocks:
        texts.append(text)
        polys.append([[x, y], [x + 60, y], [x + 60, y + 20], [x, y + 20]])
    return texts, polys


# ---------------------------------------------------------------------------
# ticket_journey_parser
# ---------------------------------------------------------------------------


def test_extract_journey_time_returns_empty_when_both_clocks_match():
    texts, polys = _card(
        ("北京南", 20, 300), ("上海虹桥", 360, 300),
        ("08:20", 20, 260), ("08:20", 360, 260),
    )

    assert ticket_journey_parser.extract_journey_time(
        texts, polys, {"departure_station": "北京南", "arrival_station": "上海虹桥"}
    ) == {}


def test_extract_journey_time_returns_empty_without_any_clock_evidence():
    texts, polys = _card(("北京南", 20, 100), ("上海虹桥", 360, 100), ("一等座", 180, 200))

    assert ticket_journey_parser.extract_journey_time(
        texts, polys, {"departure_station": "北京南", "arrival_station": "上海虹桥"}
    ) == {}


def test_extract_journey_time_ignores_single_clock_row():
    texts, polys = _card(("北京南", 20, 100), ("上海虹桥", 360, 100), ("08:20", 20, 70))

    assert ticket_journey_parser.extract_journey_time(
        texts, polys, {"departure_station": "北京南", "arrival_station": "上海虹桥"}
    ) == {}


# ---------------------------------------------------------------------------
# image_classification_service
# ---------------------------------------------------------------------------


def test_release_model_drops_session_and_collects_garbage():
    class _Wrapper:
        model_name = "yolo_photo_cls_general.onnx"

        def __init__(self):
            self.session = object()

    wrapper = _Wrapper()

    image_classification_service.ImageClassificationService._release_model(None, wrapper)

    assert not hasattr(wrapper, "session")


def test_release_model_handles_wrapper_without_session():
    class _Wrapper:
        model_name = "no-session.onnx"

    image_classification_service.ImageClassificationService._release_model(None, _Wrapper())


# ---------------------------------------------------------------------------
# onnx_providers
# ---------------------------------------------------------------------------


def test_session_options_use_explicit_thread_override(monkeypatch):
    monkeypatch.setenv("ORT_INTRA_OP_THREADS", "3")
    onnx_providers.get_session_options.cache_clear()

    options = onnx_providers.get_session_options()

    assert options.intra_op_num_threads == 3
    onnx_providers.get_session_options.cache_clear()


def test_session_options_fall_back_to_runtime_default(monkeypatch):
    monkeypatch.delenv("ORT_INTRA_OP_THREADS", raising=False)
    monkeypatch.setattr(onnx_providers, "_is_apple_silicon", lambda: False)
    onnx_providers.get_session_options.cache_clear()

    options = onnx_providers.get_session_options()

    assert options.inter_op_num_threads == 1
    onnx_providers.get_session_options.cache_clear()
