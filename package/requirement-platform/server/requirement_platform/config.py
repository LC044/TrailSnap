import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]+$")


def normalize_base_path(raw: str | None) -> str:
    """Return '' for a root deployment, or a canonical '/issues' style prefix.

    The value is used in URLs and nginx regexes, so only unreserved path
    characters are accepted and dot segments are rejected explicitly.
    """
    value = (raw or "").strip()
    if not value or value == "/":
        return ""
    segments = [part for part in value.strip("/").split("/") if part]
    if not segments:
        return ""
    for part in segments:
        if part in {".", ".."} or not _SEGMENT.fullmatch(part):
            raise ValueError(
                f"RP_BASE_PATH must contain only URL-safe path segments (got {value!r})"
            )
    return "/" + "/".join(segments)


def apply_base_path(url: str, base_path: str) -> str:
    """Insert base_path into an absolute URL unless it is already present.

    Idempotent, so restarting with the same configuration cannot stack prefixes.
    Relative or empty values are returned untouched.
    """
    if not base_path or not url or not url.startswith(("http://", "https://")):
        return url
    parts = urlsplit(url)
    path = parts.path
    if not path or path == "/":
        return urlunsplit(parts._replace(path=base_path))
    if path == base_path or path.startswith(base_path + "/"):
        return url
    return urlunsplit(parts._replace(path=base_path.rstrip("/") + path))


def derive_web_url(raw: str, base_path: str) -> str:
    """RP_WEB_URL is the site origin; strip an already-included base prefix."""
    value = (raw or "").strip().rstrip("/")
    if base_path and value.endswith(base_path):
        value = value[: -len(base_path)].rstrip("/")
    return value


_BASE_PATH = normalize_base_path(os.getenv("RP_BASE_PATH"))
_LOCAL_ORIGIN = "http://127.0.0.1:8011"


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
    non_admin_hourly_submission_limit: int = int(os.getenv("RP_NON_ADMIN_HOURLY_SUBMISSION_LIMIT", "20"))
    upload_dir: str = os.getenv("RP_UPLOAD_DIR", "./data/uploads")
    max_attachment_bytes: int = int(os.getenv("RP_MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024)))
    max_attachments_per_requirement: int = int(os.getenv("RP_MAX_ATTACHMENTS_PER_REQUIREMENT", "5"))
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
    base_path: str = _BASE_PATH
    github_oauth_redirect_uri: str = apply_base_path(
        os.getenv("RP_GITHUB_OAUTH_REDIRECT_URI") or f"{_LOCAL_ORIGIN}/api/auth/github/callback",
        _BASE_PATH,
    )
    web_url: str = derive_web_url(os.getenv("RP_WEB_URL", _LOCAL_ORIGIN), _BASE_PATH)
    mcp_public_url: str = apply_base_path(
        os.getenv("RP_MCP_PUBLIC_URL") or f"{_LOCAL_ORIGIN}/mcp/", _BASE_PATH
    )
    worker_poll_seconds: float = float(os.getenv("RP_WORKER_POLL_SECONDS", "3"))
    max_job_attempts: int = int(os.getenv("RP_MAX_JOB_ATTEMPTS", "5"))

    @property
    def public_base_url(self) -> str:
        """External site root including the deployment prefix."""
        return f"{self.web_url}{self.base_path}"

    def public_url(self, path: str = "") -> str:
        """Build an externally visible page URL such as /requirements/REQ-1."""
        suffix = path.lstrip("/")
        return f"{self.public_base_url}/{suffix}" if suffix else self.public_base_url

    def api_path(self, path: str = "") -> str:
        """Build an externally visible API path such as /issues/api/..."""
        suffix = path.lstrip("/")
        return f"{self.base_path}/api/{suffix}" if suffix else f"{self.base_path}/api"


settings = Settings()
