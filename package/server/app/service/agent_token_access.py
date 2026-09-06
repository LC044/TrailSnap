"""REST authorization policy for scoped TrailSnap Agent Tokens."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException, status


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Ordered from more specific to less specific so future nested routes can
# override a broader domain without changing existing behavior.
REST_SCOPE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("/albums", "albums:read"),
    ("/faces", "people:read"),
    ("/photos", "photos:read"),
    ("/medias", "photos:read"),
    ("/search", "photos:read"),
    ("/locations", "photos:read"),
    ("/location-stats", "photos:read"),
    ("/tags", "photos:read"),
    ("/ocr", "photos:read"),
    ("/stats", "photos:read"),
    ("/annual-report", "photos:read"),
    ("/moments", "photos:read"),
    ("/agent/artifacts", "photos:read"),
)


def required_rest_scope(path: str) -> str | None:
    """Return the scope for an Agent-Token REST path, or None if denied."""
    for prefix, scope in REST_SCOPE_PREFIXES:
        if path == prefix or path.startswith(f"{prefix}/"):
            return scope
    return None


def enforce_agent_token_rest_access(method: str, path: str, scopes: Iterable[str]) -> None:
    """Restrict Agent Tokens to explicitly scoped, read-only REST endpoints.

    User JWTs do not call this function and retain the application's normal
    permissions. ``/users/me`` is allowed so CLI ``config whoami`` can verify
    which user owns a token without exposing another domain.
    """
    normalized_method = method.upper()
    if normalized_method not in SAFE_METHODS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent Token 仅允许只读请求",
        )

    if path in {"/users/me", "/health-check", "/discovery"}:
        return

    required_scope = required_rest_scope(path)
    if required_scope is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent Token 无权访问此接口",
        )
    if required_scope not in set(scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent Token 缺少权限: {required_scope}",
        )
