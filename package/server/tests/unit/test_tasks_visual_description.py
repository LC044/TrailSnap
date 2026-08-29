"""Unit tests for ``app/service/tasks/visual_description.py``.

The visual description strategy has two surfaces that don't require a real
language model:

* ``encode_image`` -- resizes an image to a target long-edge size and
  base64-encodes a JPEG.
* ``create_client`` -- validates the user's LLM settings before touching
  the network and raises ``ValueError`` for each missing / disabled piece.

Coverage:

* ``encode_image`` shrinks oversized images and emits a non-empty base64
  string.
* ``encode_image`` converts RGBA / palette PNGs to RGB before encoding.
* ``create_client`` raises when the analysis connection is not configured.
* ``create_client`` raises when the configured connection is disabled.
* ``create_client`` raises when the connection is missing an API key.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def test_encode_image_shrinks_oversized_image(tmp_path):
    """An oversized RGBA PNG is downscaled to fit the ``max_size`` bound."""
    from app.service.tasks import visual_description as vd_mod

    src = tmp_path / "big.png"
    # 2000x1500 RGBA PNG (decorative; no need to look like a photo).
    img = Image.new("RGBA", (2000, 1500), (255, 0, 0, 128))
    img.save(src, format="PNG")

    encoded = vd_mod.encode_image(str(src), max_size=672)
    raw = base64.b64decode(encoded)
    out = Image.open(__import__("io").BytesIO(raw))
    assert out.format == "JPEG"
    # Long edge is now within the bound (with a tolerance of one pixel).
    assert max(out.size) <= 672


def test_encode_image_handles_palette_mode(tmp_path):
    """Palette PNGs are flattened to RGB before encoding."""
    from app.service.tasks import visual_description as vd_mod

    src = tmp_path / "pal.png"
    palette_img = Image.new("P", (64, 64))
    palette_img.save(src, format="PNG")

    encoded = vd_mod.encode_image(str(src), max_size=672)
    raw = base64.b64decode(encoded)
    out = Image.open(__import__("io").BytesIO(raw))
    assert out.mode == "RGB"


def test_create_client_raises_when_connection_id_missing():
    """Without an ``analysis_connection_id`` the strategy refuses to build a client."""
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    settings = MagicMock()
    settings.analysis_connection_id = None
    settings.analysis_model_name = "some-model"

    with pytest.raises(ValueError, match="Visual Model not configured"):
        strategy.create_client(settings)


def test_create_client_raises_when_connection_disabled():
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    connection = MagicMock()
    connection.id = "conn-1"
    connection.enable = False
    connection.api_key = "secret"

    settings = MagicMock()
    settings.analysis_connection_id = "conn-1"
    settings.analysis_model_name = "m"
    settings.connections = [connection]

    with pytest.raises(ValueError, match="disabled"):
        strategy.create_client(settings)


def test_create_client_raises_when_connection_missing_api_key():
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    connection = MagicMock()
    connection.id = "conn-1"
    connection.enable = True
    connection.api_key = ""

    settings = MagicMock()
    settings.analysis_connection_id = "conn-1"
    settings.analysis_model_name = "m"
    settings.connections = [connection]

    with pytest.raises(ValueError, match="api_key"):
        strategy.create_client(settings)


def test_create_client_raises_when_connection_not_found():
    """A connection id that doesn``t match any entry in ``connections`` is rejected."""
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    settings = MagicMock()
    settings.analysis_connection_id = "missing-id"
    settings.analysis_model_name = "m"
    settings.connections = []

    with pytest.raises(ValueError, match="not found"):
        strategy.create_client(settings)


def test_create_client_uses_visual_timeout_without_nested_retries():
    """Slow local inference gets five minutes; task retries stay worker-owned."""
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()
    connection = MagicMock(
        id="conn-1",
        enable=True,
        api_key="secret",
        api_base="http://ai:8001/v1",
    )
    settings = MagicMock(
        analysis_connection_id="conn-1",
        analysis_model_name="vision-model",
        connections=[connection],
    )

    with patch.object(vd_mod, "ChatOpenAI") as chat_openai:
        strategy.create_client(settings)

    kwargs = chat_openai.call_args.kwargs
    assert kwargs["timeout"] == 300
    assert kwargs["max_retries"] == 0
    assert strategy.timeout == 360


def test_parse_visual_result_accepts_json_wrapped_in_prose():
    """A valid object can be recovered without another model request."""
    from app.service.tasks import visual_description as vd_mod

    result = vd_mod.parse_visual_result(
        '结果如下：\n{"description":"照片", "tags":[], "memory_score":60, '
        '"beauty_score":70, "reason":"清晰", "narrative":"值得留存"}\n完成'
    )

    assert result["description"] == "照片"
    assert result["beauty_score"] == 70


def test_parse_visual_result_rejects_missing_or_invalid_fields():
    """Syntactically valid JSON still has to satisfy the storage schema."""
    from app.service.tasks import visual_description as vd_mod

    with pytest.raises(vd_mod.VisualDescriptionFormatError, match="缺少字段"):
        vd_mod.parse_visual_result('{"description": "照片"}')

    with pytest.raises(vd_mod.VisualDescriptionFormatError, match="0~100"):
        vd_mod.parse_visual_result(
            '{"description":"照片", "tags":[], "memory_score":101, '
            '"beauty_score":70, "reason":"清晰", "narrative":"值得留存"}'
        )
