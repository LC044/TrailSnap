"""Canonical public media URL builders shared by API response producers."""

from uuid import UUID


def thumbnail_url(user_id: UUID | str, photo_id: UUID | str, size: str = "small") -> str:
    suffix = "" if size == "small" else f"?size={size}"
    return f"/api/medias/{user_id}/{photo_id}/thumbnail{suffix}"
