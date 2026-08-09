"""CPU-only desktop AI application for the phase-2 extension package."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logger import setup_logging
from app.routers import ai_config, image_classification, ocr, system, tickets
from app.services.model_downloader import model_downloader
from app.services.desktop_model_pack import register_desktop_model_pack


register_desktop_model_pack()


@asynccontextmanager
async def lifespan(_: FastAPI):
    listener = setup_logging("desktop-ai")
    try:
        yield
    finally:
        listener.stop()


app = FastAPI(
    title="TrailSnap Desktop AI Extension",
    version="0.9.2",
    description="Optional CPU extension providing OCR, ticket recognition and classification.",
    lifespan=lifespan,
)

app.include_router(system.router, tags=["System"])
app.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
app.include_router(tickets.router, prefix="/tickets", tags=["Ticket Recognition"])
app.include_router(image_classification.router, prefix="/classification", tags=["Image Classification"])
app.include_router(ai_config.router, prefix="/ai", tags=["AI Configuration"])


@app.get("/health-check", tags=["System"])
def health_check():
    return {
        "status": "ok",
        "service": "TrailSnap Desktop AI Extension",
        "capabilities": ["ocr", "tickets", "classification"],
    }
