import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("RP_DATABASE_URL", "sqlite:///./data/requirements.db")
    jwt_secret: str = os.getenv("RP_JWT_SECRET", "change-me-before-production")
    jwt_expire_minutes: int = int(os.getenv("RP_JWT_EXPIRE_MINUTES", "10080"))
    allow_registration: bool = _bool("RP_ALLOW_REGISTRATION", True)
    owner_email: str = os.getenv("RP_OWNER_EMAIL", "").strip().lower()
    cors_origins: tuple[str, ...] = tuple(
        value.strip() for value in os.getenv("RP_CORS_ORIGINS", "http://localhost:5177").split(",") if value.strip()
    )
    daily_submission_limit: int = int(os.getenv("RP_DAILY_SUBMISSION_LIMIT", "5"))
    max_open_requirements: int = int(os.getenv("RP_MAX_OPEN_REQUIREMENTS", "20"))
    ai_api_url: str = os.getenv("RP_AI_API_URL", "").rstrip("/")
    ai_api_key: str = os.getenv("RP_AI_API_KEY", "")
    ai_model: str = os.getenv("RP_AI_MODEL", "")
    github_repo: str = os.getenv("RP_GITHUB_REPO", "LC044/TrailSnap")
    github_token: str = os.getenv("RP_GITHUB_TOKEN", "")
    github_app_id: str = os.getenv("RP_GITHUB_APP_ID", "")
    github_installation_id: str = os.getenv("RP_GITHUB_INSTALLATION_ID", "")
    github_private_key: str = os.getenv("RP_GITHUB_PRIVATE_KEY", "").replace("\\n", "\n")
    github_webhook_secret: str = os.getenv("RP_GITHUB_WEBHOOK_SECRET", "")
    github_oauth_client_id: str = os.getenv("RP_GITHUB_OAUTH_CLIENT_ID", "")
    github_oauth_client_secret: str = os.getenv("RP_GITHUB_OAUTH_CLIENT_SECRET", "")
    github_oauth_redirect_uri: str = os.getenv(
        "RP_GITHUB_OAUTH_REDIRECT_URI", "http://127.0.0.1:8011/api/auth/github/callback"
    )
    web_url: str = os.getenv("RP_WEB_URL", "http://127.0.0.1:8011").rstrip("/")
    mcp_public_url: str = os.getenv("RP_MCP_PUBLIC_URL", "http://127.0.0.1:8011/mcp/")
    worker_poll_seconds: float = float(os.getenv("RP_WORKER_POLL_SECONDS", "3"))
    max_job_attempts: int = int(os.getenv("RP_MAX_JOB_ATTEMPTS", "5"))


settings = Settings()
