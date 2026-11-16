"""2026-11-16 nightly coverage for the CLIP classification service guards.

The 2026-11-16 backend coverage scan reported ``service/clip_classification.py``
at 95.0% and the following helpers were not referenced by any test:

* ``validate_reference_image`` - a rule may only carry a bounded, real
  JPEG snapshot, never a remote URL or an arbitrary file path;
* ``ai_request`` - the AI service is not ready yet must stay resumable,
  so transient failures become a friendly ``RuntimeError`` instead of a
  hard crash of the classification worker;
* ``enqueue_photos`` - the pending task lookup must only touch the owner
  that owns every photo of the batch;
* ``_publish_initialized_presets`` - a savepoint commit is still part of
  the outer transaction, so the preset cache must not be published yet.
"""

from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import requests
from PIL import Image

from app.service import clip_classification as clip_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def _data_url(payload: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(payload).decode("ascii")


def _jpeg_bytes(size=(8, 8)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_validate_reference_image_accepts_a_small_jpeg_snapshot():
    value = _data_url(_jpeg_bytes())
    assert clip_service.validate_reference_image(value) == value


def test_validate_reference_image_rejects_a_remote_url():
    with pytest.raises(ValueError):
        clip_service.validate_reference_image("https://example.com/cat.jpg")


def test_validate_reference_image_rejects_an_oversized_payload():
    with pytest.raises(ValueError):
        clip_service.validate_reference_image("data:image/jpeg;base64," + "A" * 700_001)


def test_validate_reference_image_rejects_a_non_jpeg_payload():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="PNG")
    with pytest.raises(ValueError):
        clip_service.validate_reference_image(_data_url(buffer.getvalue(), "image/png"))


def test_validate_reference_image_rejects_broken_base64():
    with pytest.raises(ValueError):
        clip_service.validate_reference_image("data:image/jpeg;base64,not-base64!")


def test_ai_request_reports_a_connection_failure_as_a_resumable_error():
    def _boom(url, **_kwargs):
        raise requests.ConnectionError("refused")

    with pytest.raises(RuntimeError):
        clip_service.ai_request(_boom, "http://ai/embedding/text")


def test_ai_request_reports_a_not_ready_service_as_a_resumable_error():
    response = MagicMock()
    response.status_code = 503
    response.text = "not ready"

    def _boom(url, **_kwargs):
        raise requests.HTTPError("server error", response=response)

    with pytest.raises(RuntimeError):
        clip_service.ai_request(_boom, "http://ai/embedding/text")


def test_ai_request_reraises_an_unrelated_http_error():
    response = MagicMock()
    response.status_code = 500
    response.text = "boom"

    def _boom(url, **_kwargs):
        raise requests.HTTPError("server error", response=response)

    with pytest.raises(requests.HTTPError):
        clip_service.ai_request(_boom, "http://ai/embedding/text")


def test_ai_request_returns_the_response_on_success():
    response = MagicMock()
    response.raise_for_status.return_value = None
    assert clip_service.ai_request(lambda url, **kwargs: response, "http://ai/x") is response


def test_enqueue_photos_without_photos_creates_no_task():
    assert clip_service.enqueue_photos(MagicMock(), []) == []


def test_enqueue_photos_rejects_a_mixed_owner_batch():
    first = MagicMock()
    first.owner_id = "owner-1"
    second = MagicMock()
    second.owner_id = "owner-2"
    with pytest.raises(ValueError):
        clip_service.enqueue_photos(MagicMock(), [first, second])


def test_enqueue_photos_without_an_enabled_category_creates_no_task():
    db = MagicMock()
    categories = MagicMock()
    categories.__iter__.return_value = iter([])
    categories.filter_by.return_value = categories
    categories.filter.return_value = categories
    db.query.return_value = categories
    photo = MagicMock()
    photo.owner_id = "owner-1"

    with patch.object(clip_service, "ensure_presets", lambda *_args, **_kwargs: None):
        assert clip_service.enqueue_photos(db, [photo]) == []


def test_publish_initialized_presets_waits_for_the_outer_transaction():
    session = MagicMock()
    session.in_nested_transaction.return_value = True
    session.info = {clip_service._PENDING_PRESETS: {("engine", "key")}}

    clip_service._publish_initialized_presets(session)

    # The pending entry is still owned by the outer transaction.
    assert session.info[clip_service._PENDING_PRESETS] == {("engine", "key")}
