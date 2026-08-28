"""Small bounded admission gates for expensive local inference endpoints."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException

from app.config import settings


class AdmissionGate:
    def __init__(self, name: str, concurrency: int):
        self.name = name
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._waiting = 0
        self._counter_lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._counter_lock:
            if self._semaphore.locked() and self._waiting >= settings.AI_ADMISSION_QUEUE:
                raise HTTPException(
                    status_code=429,
                    detail=f"{self.name} service busy; retry later",
                    headers={"Retry-After": "5"},
                )
            self._waiting += 1
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=settings.AI_ADMISSION_WAIT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=429,
                detail=f"{self.name} service busy; retry later",
                headers={"Retry-After": "5"},
            ) from exc
        finally:
            async with self._counter_lock:
                self._waiting = max(0, self._waiting - 1)

    def release(self) -> None:
        self._semaphore.release()

    @asynccontextmanager
    async def slot(self):
        await self.acquire()
        try:
            yield
        finally:
            self.release()


ocr_admission = AdmissionGate("OCR", settings.AI_OCR_CONCURRENCY)
classification_admission = AdmissionGate(
    "classification", settings.AI_CLASSIFICATION_CONCURRENCY
)
face_admission = AdmissionGate("face recognition", settings.AI_FACE_CONCURRENCY)
embedding_admission = AdmissionGate("embedding", settings.AI_EMBEDDING_CONCURRENCY)
tickets_admission = AdmissionGate("ticket recognition", settings.AI_TICKETS_CONCURRENCY)
