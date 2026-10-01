"""SQL predicates for legacy absolute and relative photo paths."""

import os

from sqlalchemy import func, or_

from app.db.models.photo import Photo


def normalized_file_path():
    return func.replace(Photo.file_path, "\\", "/")


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def stored_prefixes(directory: str) -> list[str]:
    """Include historical relative uploads as well as absolute scan paths."""
    directory = (directory or "").replace("\\", "/").rstrip("/")
    if not directory:
        return []
    prefixes = {directory}
    try:
        relative = os.path.relpath(directory).replace("\\", "/").rstrip("/")
        if relative and relative != directory:
            prefixes.update((relative, "./" + relative))
    except ValueError:
        pass
    return [prefix + "/" for prefix in sorted(prefixes)]


def under_directory(directory: str):
    patterns = [normalized_file_path().like(escape_like(prefix) + "%", escape="\\")
                for prefix in stored_prefixes(directory)]
    return or_(*patterns) if patterns else False


def under_browse_folder(folder: str):
    folder = folder.strip().replace("\\", "/").strip("/")
    prefix = escape_like(folder) + "/%"
    path = normalized_file_path()
    return or_(path.like(prefix, escape="\\"), path.like("%/" + prefix, escape="\\"))
