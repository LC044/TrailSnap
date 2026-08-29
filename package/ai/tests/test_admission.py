import asyncio

import pytest
from fastapi import HTTPException

from app.core.admission import AdmissionGate
from app.config import settings


pytestmark = [pytest.mark.smoke]


@pytest.mark.asyncio
async def test_admission_rejects_when_bounded_wait_queue_is_full(monkeypatch):
    monkeypatch.setattr(settings, "AI_ADMISSION_QUEUE", 1)
    monkeypatch.setattr(settings, "AI_ADMISSION_WAIT_SECONDS", 1.0)
    gate = AdmissionGate("test", concurrency=1)

    await gate.acquire()
    waiting = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    with pytest.raises(HTTPException) as exc_info:
        await gate.acquire()
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "5"

    gate.release()
    await waiting
    gate.release()
