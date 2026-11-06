"""Nightly guards for 2026-11-05 AI coverage gaps.

The remaining AI blind spots are concentrated in ticket parser station/seat
fallbacks and face-recognition validation branches.  These tests exercise the
pure helpers without loading ONNX models or OCR fixtures.
"""

import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services import face_service, ticket_parser

pytestmark = pytest.mark.smoke


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0308F", {"carriage": "03", "seat_num": "08F"}),
        ("0307 08F", {"carriage": None, "seat_num": "0307 08F"}),
    ],
)
def test_split_carriage_seat_only_accepts_glued_alphanumeric_form(raw, expected):
    info = {"carriage": None, "seat_num": raw}
    ticket_parser._split_carriage_seat_if_glued(info)
    assert info == expected


def test_post_fix_arrival_station_clears_duplicate_station():
    info = {"departure_station": "北京南", "arrival_station": ""}
    result = ticket_parser._post_fix_arrival_station(
        info, ["上海虹桥站", "北京南站"]
    )
    assert result["departure_station"] == "北京南"
    assert result["arrival_station"] == "上海虹桥"


def test_pick_left_right_station_names_ignores_invalid_and_duplicate_candidates(monkeypatch):
    monkeypatch.setattr(
        ticket_parser, "_is_valid_station_name", lambda name: name in {"上海虹桥", "北京南"}
    )
    dep, arr = ticket_parser._pick_left_right_station_names(
        [
            ("无效站", 0, 0),
            ("上海虹桥", 10, 10),
            ("上海虹桥", 20, 10),
            ("北京南", 100, 10),
        ]
    )
    assert (dep, arr) == ("上海虹桥", "北京南")


def test_face_valid_embedding_accepts_realistic_vector_and_rejects_bad_values():
    good = np.zeros(512, dtype=float)
    good[0] = 1.0
    assert bool(face_service.FaceRecognitionService._valid_embedding(good)) is True

    bad = np.zeros(512, dtype=float)
    assert bool(face_service.FaceRecognitionService._valid_embedding(bad)) is False
    assert face_service.FaceRecognitionService._valid_embedding(good[:511]) is False
    bad[0] = np.nan
    assert bool(face_service.FaceRecognitionService._valid_embedding(bad)) is False


def test_face_ensure_embedding_short_circuits_valid_features():
    service = face_service.FaceRecognitionService()
    face = SimpleNamespace(embedding=np.ones(512))
    app = MagicMock()
    service._ensure_embedding(app, object(), face)
    app.models.get.assert_not_called()


def test_face_ensure_embedding_requires_model_for_invalid_features():
    service = face_service.FaceRecognitionService()
    face = SimpleNamespace(embedding=None)
    app = MagicMock()
    app.models.get.return_value = None
    with pytest.raises(ValueError, match="Face recognition model is missing"):
        service._ensure_embedding(app, object(), face)

