"""Nightly watch 2026-11-23 - app/services/emotion_service.py 的 _ensure_init 盲区。

EmotionService._ensure_init 是 analyze() 的懒初始化钩子：首次调用后把
_initialized 置为 True，之后再调用不应重复初始化。

已有的 tests/test_emotion_service.py 覆盖了 analyze() 的批次 / 错误分支，
因此本文件只补 _ensure_init 这条尚未被任何用例触及的路径。

本文件覆盖：

- _ensure_init 首次调用把 _initialized 置为 True（happy）
- _ensure_init 重复调用保持幂等（edge）
- analyze() 会触发初始化（happy）
"""

import pytest

from app.services.emotion_service import EmotionService

pytestmark = [pytest.mark.smoke]


def test_ensure_init_marks_the_service_as_initialized():
    service = EmotionService()
    assert service._initialized is False

    service._ensure_init()

    assert service._initialized is True


def test_ensure_init_is_idempotent():
    service = EmotionService()
    service._ensure_init()

    service._ensure_init()

    assert service._initialized is True


@pytest.mark.asyncio
async def test_analyze_triggers_initialization():
    service = EmotionService()
    assert service._initialized is False

    await service.analyze([])

    assert service._initialized is True
