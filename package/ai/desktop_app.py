"""CPU-only desktop AI application exposing the complete AI service API."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.core.logger import setup_logging
from app.routers import (
    ai_config,
    embedding,
    emotion,
    face,
    image_classification,
    llm,
    object_detection,
    ocr,
    tickets,
)
from app.services.llm_manager import llm_manager
from app.services.unified_model_manager import ai_model_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    listener = setup_logging("desktop-ai")
    if os.environ.get("TS_AI_SKIP_AUTO_DOWNLOAD") != "1":
        ai_model_manager.start_selected_downloads()
    llm_idle_task = asyncio.create_task(llm_manager.idle_checker())
    try:
        yield
    finally:
        llm_idle_task.cancel()
        try:
            await llm_idle_task
        except asyncio.CancelledError:
            pass
        await llm_manager.stop()
        listener.stop()


app = FastAPI(
    title="TrailSnap Desktop AI Extension",
    version="0.11.0",
    description="Optional CPU extension providing the complete TrailSnap AI service.",
    lifespan=lifespan,
)

app.include_router(face.router, prefix="/face", tags=["Face Recognition"])
app.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
app.include_router(object_detection.router, prefix="/object-detection", tags=["Object Detection"])
app.include_router(tickets.router, prefix="/tickets", tags=["Ticket Recognition"])
app.include_router(image_classification.router, prefix="/classification", tags=["Image Classification"])
app.include_router(embedding.router, prefix="/embedding", tags=["Embedding"])
app.include_router(llm.router, prefix="/v1", tags=["OpenAI LLM"])
app.include_router(ai_config.router, prefix="/ai", tags=["AI Configuration"])
app.include_router(emotion.router, prefix="/emotion", tags=["Emotion Color"])


@app.get("/health-check", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "TrailSnap Desktop AI Extension",
        "capabilities": [
            "face",
            "ocr",
            "object_detection",
            "tickets",
            "classification",
            "embedding",
            "llm",
            "emotion",
        ],
    }


@app.get("/version", tags=["System"])
def version():
    return {"version": settings.APP_VERSION}
