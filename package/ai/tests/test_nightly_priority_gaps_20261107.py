"""Nightly AI priority-gap tests for 2026-11-07.

覆盖扫描选择：services/face_service.py、services/ticket_service.py。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import face_service, ticket_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai]


def test_face_service_rejects_before_model_ready():
    service = face_service.FaceRecognitionService()

    with patch.object(face_service.ai_model_manager, "is_ready", return_value=False):
        with pytest.raises(Exception, match="Face model is not ready"):
            service.process_image(b"not-used")


def test_face_service_rejects_invalid_image_bytes():
    service = face_service.FaceRecognitionService()

    with patch.object(face_service.ai_model_manager, "is_ready", return_value=True), patch.object(
        face_service.model_manager, "get_model", return_value=MagicMock()
    ):
        with pytest.raises(ValueError, match="Invalid image data"):
            service.process_image(b"definitely-not-an-image")


def test_full_image_ticket_accepts_complete_railway_ticket():
    image = SimpleNamespace()
    ocr = MagicMock()
    parsed = {
        "train_code": "G1234",
        "departure_station": "武汉",
        "arrival_station": "北京",
        "datetime": "2026年11月7日",
    }

    with patch.object(ticket_service, "has_railway_evidence", return_value=True), patch.object(
        ticket_service, "parse_ticket_info", return_value=parsed
    ), patch.object(
        ticket_service, "_ocr_blocks", return_value=(["中国铁路 G1234"], [[[1, 1], [1, 2], [2, 2], [2, 1]]])
    ):
        result = ticket_service._full_image_ticket(image, ocr)

    assert result == {**parsed, "type": "train", "detection_id": 0}
    ocr.assert_called_once_with(
        image, use_det=True, use_cls=True, use_rec=True
    )


def test_full_image_ticket_rejects_incomplete_ticket():
    parsed = {"train_code": "G1234", "departure_station": "武汉", "arrival_station": ""}

    with patch.object(ticket_service, "has_railway_evidence", return_value=True), patch.object(
        ticket_service, "parse_ticket_info", return_value=parsed
    ), patch.object(ticket_service, "_ocr_blocks", return_value=(["中国铁路"], [])):
        result = ticket_service._full_image_ticket(SimpleNamespace(), MagicMock())

    assert result is None


def test_full_image_ticket_requires_railway_evidence():
    with patch.object(ticket_service, "has_railway_evidence", return_value=False), patch.object(
        ticket_service, "_ocr_blocks", return_value=(["G1234"], [])
    ):
        result = ticket_service._full_image_ticket(SimpleNamespace(), MagicMock())

    assert result is None
