"""Nightly gap coverage for app/services/ticket_service.py.

The station-line OCR recovery path was uncovered in the nightly scan: when the
card only prints one endpoint, the opposite column is re-read with OCR and a
credible (but not yet confirmed) station name is used to fill the missing side.
"""

from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pytest

from app.services import ticket_parser, ticket_service

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


@contextmanager
def _no_lock():
    yield


def _image():
    return np.zeros((100, 200, 3), dtype=np.uint8)


def _box(x0, x1):
    return [[x0, 0], [x1, 0], [x1, 20], [x0, 20]]


def test_station_line_recovers_missing_endpoint_from_credible_name(monkeypatch):
    monkeypatch.setattr(ticket_parser, "_get_valid_station_names", lambda: {"北京", "上海"})
    monkeypatch.setattr(ticket_parser, "_is_valid_station_name", lambda name: True)
    monkeypatch.setattr(ticket_service, "openvino_infer_lock", _no_lock)
    monkeypatch.setattr(ticket_service, "_ocr_blocks", lambda result: (["杭州"], []))

    info = {"train_code": "G1", "departure_station": "北京", "arrival_station": None}
    ticket_service.recover_station_line(
        info, _image(), ["北京站"], [_box(0, 60)], lambda *args, **kwargs: []
    )

    assert info["arrival_station"] == "杭州"
    assert info["station_source"] == "card-line-ocr"


def test_station_line_keeps_info_untouched_without_a_single_credible_name(monkeypatch):
    monkeypatch.setattr(ticket_parser, "_get_valid_station_names", lambda: {"北京", "上海"})
    monkeypatch.setattr(ticket_parser, "_is_valid_station_name", lambda name: True)
    monkeypatch.setattr(ticket_service, "openvino_infer_lock", _no_lock)
    monkeypatch.setattr(ticket_service, "_ocr_blocks", lambda result: (["杭州", "苏州"], []))

    info = {"train_code": "G1", "departure_station": "北京", "arrival_station": None}
    ticket_service.recover_station_line(
        info, _image(), ["北京站"], [_box(0, 60)], lambda *args, **kwargs: []
    )

    assert info["arrival_station"] is None
    assert "station_source" not in info


def test_station_line_requires_a_train_code(monkeypatch):
    monkeypatch.setattr(ticket_service, "openvino_infer_lock", _no_lock)

    info = {"departure_station": "北京", "arrival_station": None}
    ticket_service.recover_station_line(
        info, _image(), ["北京站"], [_box(0, 60)], lambda *args, **kwargs: []
    )

    assert info["arrival_station"] is None
