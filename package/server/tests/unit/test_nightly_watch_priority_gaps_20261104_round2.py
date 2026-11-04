"""Nightly watch coverage for the 2026-11-04 backend and AI gap scan.

The selected backend modules were the lowest-coverage API router plus small,
high-value service boundaries identified from ``coverage-backend.xml``.  The
AI module was the lowest-coverage service in ``coverage-ai.xml``.
"""

from datetime import date
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import media
from app.service.agent import memory
from app.service.jobs import moment_caption
from app.service.tasks import similar


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# app/api/media.py -- live-photo companion path guard
# ---------------------------------------------------------------------------

def test_live_photo_video_path_uses_jpg_stem_and_submitted_video_ext():
    path = media._live_photo_video_path(r"C:/photos/IMG_0001.jpg", "IMG_0001.mp4")

    assert path == r"C:/photos/IMG_0001.mp4"


def test_live_photo_video_path_forces_mov_for_heic():
    path = media._live_photo_video_path(r"C:/photos/IMG_0002.heic", "IMG_0002.mov")

    assert path == r"C:/photos/IMG_0002.MOV"


@pytest.mark.parametrize(
    ("image_path", "video_name", "message"),
    [
        (r"C:/photos/photo.png", "photo.mp4", "Unsupported live photo image type"),
        (r"C:/photos/photo.jpg", "photo.avi", "Unsupported live photo video type"),
    ],
)
def test_live_photo_video_path_rejects_unsupported_extensions(image_path, video_name, message):
    with pytest.raises(ValueError, match=message):
        media._live_photo_video_path(image_path, video_name)


# ---------------------------------------------------------------------------
# app/service/tasks/similar.py -- strategy contract and small-input boundary
# ---------------------------------------------------------------------------

def test_similar_photo_strategy_timeout_is_one_hour():
    assert similar.SimilarPhotoClusteringStrategy().timeout == 60 * 60


def test_similar_photo_strategy_skips_singleton_segment_without_cluster_rows():
    task = SimpleNamespace(
        id=str(uuid4()), owner_id=uuid4(), payload={"threshold": 0.9},
        total_items=0, processed_items=0, result=None, status=None,
    )
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(photo_id="only", embedding=[1.0, 0.0, 0.0], photo_time=None)
    ]

    result = asyncio.run(similar.SimilarPhotoClusteringStrategy().process(
        worker=None, task=task, db=db
    ))

    assert result == {"status": "completed", "groups": 0}
    assert task.total_items == 1
    db.add.assert_not_called()


def test_similar_photo_strategy_reraises_worker_failures():
    task = SimpleNamespace(
        id=str(uuid4()), owner_id=uuid4(), payload={}, total_items=0,
        processed_items=0, result=None, status=None,
    )
    db = MagicMock()
    db.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(similar.SimilarPhotoClusteringStrategy().process(worker=None, task=task, db=db))


# ---------------------------------------------------------------------------
# app/service/jobs/moment_caption.py -- missing-caption SQL boundary
# ---------------------------------------------------------------------------

def test_find_days_missing_caption_maps_rows_in_query_order():
    db = MagicMock()
    db.execute.return_value.all.return_value = [(date(2026, 11, 3),), (date(2026, 11, 2),)]
    user_id = uuid4()

    result = moment_caption._find_days_missing_caption(db, user_id)

    assert result == [date(2026, 11, 3), date(2026, 11, 2)]
    db.execute.assert_called_once()
    statement = db.execute.call_args.args[0]
    assert "photo_time" in str(statement).lower()
    assert "moment_day_caption" in str(statement).lower()


# ---------------------------------------------------------------------------
# app/service/agent/memory.py -- memory extraction LLM selection
# ---------------------------------------------------------------------------

def _user_config(connection):
    return SimpleNamespace(
        ai=SimpleNamespace(
            analysis_connection_id="analysis-conn",
            analysis_model_name="qwen-plus",
            connections=[connection],
        )
    )


def _connection(*, enabled=True, api_key="secret-key", api_base="http://llm.local/v1"):
    return SimpleNamespace(
        id="analysis-conn", enable=enabled, api_key=api_key, api_base=api_base
    )


def test_memory_extraction_llm_uses_enabled_analysis_connection():
    from app.core.config_manager import config_manager

    with patch.object(config_manager, "get_user_config", return_value=_user_config(_connection())):
        with patch("langchain_openai.ChatOpenAI") as chat_openai:
            llm, ok = memory._get_extraction_llm(MagicMock(), str(uuid4()))

    assert ok is True
    assert llm is chat_openai.return_value
    kwargs = chat_openai.call_args.kwargs
    assert kwargs["model"] == "qwen-plus"
    assert kwargs["api_key"] == "secret-key"
    assert kwargs["temperature"] == 0.2
    assert kwargs["timeout"] == 30


def test_memory_extraction_llm_requires_analysis_model():
    from app.core.config_manager import config_manager

    config = _user_config(_connection())
    config.ai.analysis_model_name = ""

    with patch.object(config_manager, "get_user_config", return_value=config):
        with patch("langchain_openai.ChatOpenAI") as chat_openai:
            llm, ok = memory._get_extraction_llm(MagicMock(), str(uuid4()))

    assert (llm, ok) == (None, False)
    chat_openai.assert_not_called()


def test_memory_extraction_llm_rejects_disabled_connection():
    from app.core.config_manager import config_manager

    with patch.object(config_manager, "get_user_config", return_value=_user_config(_connection(enabled=False))):
        with patch("langchain_openai.ChatOpenAI") as chat_openai:
            llm, ok = memory._get_extraction_llm(MagicMock(), str(uuid4()))

    assert (llm, ok) == (None, False)
    chat_openai.assert_not_called()

