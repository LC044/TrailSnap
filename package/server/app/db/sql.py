"""Small SQL helpers for expressions that differ between database backends."""

from datetime import date, datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import aliased


def location_summary(db):
    """Keep SQLite geography reads on the narrow covering index.

    Materializing the projection prevents photo_id joins from choosing the
    primary-key index and fetching wide EXIF rows, even before import statistics
    exist. PostgreSQL keeps its normal planner and predicate pushdown.
    """
    from app.db.models.photo_metadata import PhotoMetadata
    if db.get_bind().dialect.name != "sqlite":
        return PhotoMetadata
    columns = ("photo_id", "province", "city", "district", "country",
               "scene_id", "latitude", "longitude")
    source = select(*(getattr(PhotoMetadata, name) for name in columns)).cte(
        "location_metadata_summary"
    ).prefix_with("MATERIALIZED", dialect="sqlite")
    return aliased(PhotoMetadata, source)


def date_only(db, column):
    """Return a day expression without SQLite's broken ``CAST(... AS DATE)``.

    SQLite casts ISO datetime text to its numeric year, while SQLAlchemy's
    ``Date`` result processor expects an ISO date string.  SQLite's ``date``
    function returns the stable ``YYYY-MM-DD`` representation instead.
    """
    if db.get_bind().dialect.name == "sqlite":
        return func.date(column)
    return cast(column, Date)


def as_date(value) -> date:
    """Normalize a backend date result to ``datetime.date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def as_date_string(value) -> str:
    """Normalize a backend date result to an ISO date string."""
    return as_date(value).isoformat()
