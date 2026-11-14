"""Nightly watch 2026-11-13 (round 3): AI ticket-service gaps.

The 2026-11-13 AI coverage snapshot still reported the "fill a missing
endpoint" branch of ``supplement_train_code`` as uncovered. That branch is the
last step of the full-image fallback: a single ticket card whose OCR pass
resolved the departure station but not the arrival station may import the
arrival station, but only when the two readings do not contradict each other.

The tests patch the OCR entry points of ``app.services.ticket_service`` so the
merge rules can be pinned down without a model.
"""

from __future__ import annotations

import contextlib

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke]


def _patch_ocr(monkeypatch, ticket_service, *, full, codes, code):
    """Replace every OCR entry point used by ``supplement_train_code``."""

    @contextlib.contextmanager
    def fake_lock():
        yield

    monkeypatch.setattr(ticket_service, "openvino_infer_lock", fake_lock)
    monkeypatch.setattr(ticket_service, "_ocr_blocks",
                        lambda result: (["G1 北京南"], [[0, 0, 10, 10]]))
    monkeypatch.setattr(ticket_service, "normalize_ticket_text", lambda text: text)
    monkeypatch.setattr(ticket_service, "resolve_train_code",
                        lambda texts, departure, polys: code)
    monkeypatch.setattr(ticket_service, "candidate_train_codes", lambda texts: set(codes))
    monkeypatch.setattr(ticket_service, "parse_ticket_info", lambda texts, polys: dict(full))


def test_supplement_train_code_imports_the_missing_arrival_station(monkeypatch):
    """A missing endpoint is filled in when the other reading agrees."""
    from app.services import ticket_service

    _patch_ocr(
        monkeypatch,
        ticket_service,
        full={"arrival_station": "上海虹桥"},
        codes={"G1"},
        code="G1",
    )
    info = {"train_code": "G1", "departure_station": "北京南", "arrival_station": None}

    ticket_service.supplement_train_code(info, np.zeros((8, 8, 3), dtype=np.uint8),
                                          lambda *a, **k: None)

    assert info["arrival_station"] == "上海虹桥"


def test_supplement_train_code_keeps_a_conflicting_endpoint(monkeypatch):
    """Two readings that disagree are never merged into one ticket."""
    from app.services import ticket_service

    _patch_ocr(
        monkeypatch,
        ticket_service,
        full={"departure_station": "南京南", "arrival_station": "上海虹桥"},
        codes={"G1"},
        code="G1",
    )
    info = {"train_code": "G1", "departure_station": "北京南", "arrival_station": None}

    ticket_service.supplement_train_code(info, np.zeros((8, 8, 3), dtype=np.uint8),
                                          lambda *a, **k: None)

    assert info["departure_station"] == "北京南"
    assert info.get("arrival_station") is None
