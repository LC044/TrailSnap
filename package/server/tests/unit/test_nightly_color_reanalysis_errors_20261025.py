"""Nightly coverage for ``app.service.jobs.color_reanalysis`` failure branches.

The 2026-10-24 backend coverage report ranked
``service/jobs/color_reanalysis.py`` at 83.3% with 10 statements never
executed.  The uncovered region is the *error* half of the batch loop:
a photo whose file vanished, an image the decoder chokes on, and a database
that fails outright.

The upgrade job runs in the background over a whole library, so the
contract under test is "one bad photo must never abort the batch, and a
database failure must roll back instead of leaving a half-applied batch".
"""

from unittest.mock import MagicMock, patch

import pytest

from app.service.jobs import color_reanalysis
from app.utils.color import CURRENT_COLOR_ANALYSIS_VERSION


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _fake_image():
    """A stand-in for ``PIL.Image.open`` used as a context manager."""
    image = MagicMock()
    image.__enter__.return_value = image
    image.__exit__.return_value = False
    return image


def _make_session(rows, *, dialect="postgresql"):
    """Build a fake ``SessionLocal`` context manager returning ``rows``.

    ``rows`` is a list of ``(color_row, photo_row)`` tuples, mirroring the
    ``query(PhotoColor, Photo).join(...)`` shape used by ``_pending_colors``.
    """
    db = MagicMock()
    db.bind.dialect.name = dialect

    limited = MagicMock()
    limited.all.return_value = rows
    limited.with_for_update.return_value = limited

    base = MagicMock()
    base.order_by.return_value.limit.return_value = limited

    session_factory = MagicMock()
    # ``with SessionLocal() as db`` calls __enter__ on the factory result.
    session_factory.__enter__.return_value = db
    session_factory.__exit__.return_value = False
    return session_factory, db, base


@pytest.fixture
def patched_pending(monkeypatch):
    """Capture the object ``_pending_colors`` returned and let tests replace it."""
    captured = {}

    def _factory(db, now):
        return captured["query"]

    monkeypatch.setattr(color_reanalysis, "_pending_colors", _factory)
    return captured


def test_reanalysis_updates_color_row_on_success(patched_pending):
    """A successfully analysed photo gets the new colour payload."""
    color = MagicMock()
    photo = MagicMock(id=7)
    rows = [(color, photo)]

    session, db, base = _make_session(rows)
    patched_pending["query"] = base

    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        with patch.object(
            color_reanalysis.storage, "get_available_photo_path", return_value="D:/p.jpg"
        ):
            with patch.object(color_reanalysis.Image, "open", return_value=_fake_image()):
                with patch.object(
                    color_reanalysis,
                    "extract_color_info",
                    return_value={
                        "dominant_colors": ["#123456"],
                        "brightness": 0.5,
                        "saturation": 0.4,
                        "emotion_hint": "calm",
                    },
                ):
                    result = color_reanalysis.reanalyze_color_batch(batch_size=10)

    assert result == {"processed": 1, "failed": 0}
    assert color.dominant_colors == ["#123456"]
    assert color.brightness == 0.5
    assert color.saturation == 0.4
    assert color.emotion_hint == "calm"
    assert color.analysis_version == CURRENT_COLOR_ANALYSIS_VERSION
    db.commit.assert_called_once()


def test_missing_file_counts_as_failure(patched_pending):
    """A photo whose file disappeared is a failure, not a crash."""
    color = MagicMock()
    photo = MagicMock(id=7)
    rows = [(color, photo)]

    session, db, base = _make_session(rows)
    patched_pending["query"] = base

    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        with patch.object(color_reanalysis.storage, "get_available_photo_path", return_value=None):
            result = color_reanalysis.reanalyze_color_batch(batch_size=10)

    assert result == {"processed": 0, "failed": 1}
    assert color.analysis_version != CURRENT_COLOR_ANALYSIS_VERSION


def test_empty_dominant_colors_counts_as_failure(patched_pending):
    """An image without dominant colours cannot be refreshed."""
    color = MagicMock()
    photo = MagicMock(id=7)
    rows = [(color, photo)]

    session, db, base = _make_session(rows)
    patched_pending["query"] = base

    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        with patch.object(
            color_reanalysis.storage, "get_available_photo_path", return_value="D:/p.jpg"
        ):
            with patch.object(color_reanalysis.Image, "open", return_value=_fake_image()):
                with patch.object(
                    color_reanalysis,
                    "extract_color_info",
                    return_value={
                        "dominant_colors": [],
                        "brightness": 0.0,
                        "saturation": 0.0,
                        "emotion_hint": None,
                    },
                ):
                    result = color_reanalysis.reanalyze_color_batch(batch_size=10)

    assert result == {"processed": 0, "failed": 1}


def test_decoder_failure_counts_as_failure_and_continues(patched_pending):
    """One unreadable image must not abort the rest of the batch."""
    good_color = MagicMock()
    bad_color = MagicMock()
    bad_photo = MagicMock(id=8)
    good_photo = MagicMock(id=9)
    rows = [(bad_color, bad_photo), (good_color, good_photo)]

    session, db, base = _make_session(rows)
    patched_pending["query"] = base

    paths = {"8": "D:/bad.jpg", "9": "D:/good.jpg"}
    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        with patch.object(
            color_reanalysis.storage,
            "get_available_photo_path",
            side_effect=lambda owner, pid, path: paths[str(pid)],
        ):
            with patch.object(
                color_reanalysis.Image,
                "open",
                side_effect=[OSError("truncated file"), _fake_image()],
            ):
                with patch.object(
                    color_reanalysis,
                    "extract_color_info",
                    return_value={
                        "dominant_colors": ["#abcdef"],
                        "brightness": 0.1,
                        "saturation": 0.2,
                        "emotion_hint": "warm",
                    },
                ):
                    result = color_reanalysis.reanalyze_color_batch(batch_size=10)

    assert result == {"processed": 1, "failed": 1}
    assert good_color.analysis_version == CURRENT_COLOR_ANALYSIS_VERSION


def test_database_failure_rolls_back_and_returns_zeroes(patched_pending):
    """A failing query rolls the transaction back and reports zeroes."""
    session, db, base = _make_session([])
    base.order_by.side_effect = RuntimeError("connection lost")
    patched_pending["query"] = base

    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        result = color_reanalysis.reanalyze_color_batch(batch_size=10)

    assert result == {"processed": 0, "failed": 0}
    db.rollback.assert_called_once()


def test_postgres_batch_uses_row_level_lock(patched_pending):
    """On PostgreSQL the batch must take a row lock with SKIP LOCKED."""
    session, db, base = _make_session([], dialect="postgresql")
    patched_pending["query"] = base

    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        color_reanalysis.reanalyze_color_batch(batch_size=5)

    base.order_by.return_value.limit.return_value.with_for_update.assert_called_once()


def test_has_pending_reanalysis_reflects_candidate_rows(monkeypatch):
    """The scheduler hook only fires when an eligible row exists."""
    session, db, _ = _make_session([])

    pending = MagicMock()
    pending.first.return_value = None
    monkeypatch.setattr(color_reanalysis, "_pending_colors", lambda db, now: pending)

    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        assert color_reanalysis.has_pending_color_reanalysis() is False

    pending.first.return_value = MagicMock()
    with patch.object(color_reanalysis, "SessionLocal", return_value=session):
        assert color_reanalysis.has_pending_color_reanalysis() is True


def test_reanalyze_pending_colors_stops_when_batch_is_not_full(monkeypatch):
    """The drain loop exits as soon as a batch comes back short."""
    calls = []

    def _fake_batch(batch_size):
        calls.append(batch_size)
        return {"processed": 0, "failed": 0}

    monkeypatch.setattr(color_reanalysis, "reanalyze_color_batch", _fake_batch)

    color_reanalysis.reanalyze_pending_colors(batch_size=25)

    assert calls == [25]
