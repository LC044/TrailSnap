import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "TrailSnap AI Service"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = ""
    PORT: int = 8001

    # AI Models Configuration
    MODEL_PATH: str = os.getenv("MODEL_PATH", os.path.expanduser("data/models"))
    LLM_MODEL_PATH: str = os.getenv("LLM_MODEL_PATH", "")
    LLM_SERVER_PORT: int = os.getenv("LLM_SERVER_PORT", 8002)
    LLM_IDLE_TIMEOUT: int = os.getenv("LLM_IDLE_TIMEOUT", 300) # 5 minutes idle timeout for LLM subprocess
    # Memory Management
    IDLE_TIMEOUT: int = 600  # Default 1 hour in seconds
    CHECK_INTERVAL: int = 60  # Check every minute
    AI_ADMISSION_QUEUE: int = int(os.getenv("AI_ADMISSION_QUEUE", "2"))
    AI_ADMISSION_WAIT_SECONDS: float = float(os.getenv("AI_ADMISSION_WAIT_SECONDS", "10"))
    AI_OCR_CONCURRENCY: int = int(os.getenv("AI_OCR_CONCURRENCY", "1"))
    AI_CLASSIFICATION_CONCURRENCY: int = int(os.getenv("AI_CLASSIFICATION_CONCURRENCY", "1"))
    AI_FACE_CONCURRENCY: int = int(os.getenv("AI_FACE_CONCURRENCY", "1"))
    AI_EMBEDDING_CONCURRENCY: int = int(os.getenv("AI_EMBEDDING_CONCURRENCY", "1"))
    AI_TICKETS_CONCURRENCY: int = int(os.getenv("AI_TICKETS_CONCURRENCY", "1"))

    class Config:
        env_file = ".env"

settings = Settings()
