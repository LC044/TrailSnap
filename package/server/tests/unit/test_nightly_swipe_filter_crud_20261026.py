"""Nightly coverage for ``app/crud/swipe_filter.py`` decision bookkeeping (2026-10-26).

The 2026-10-26 backend coverage scan listed ``crud/swipe_filter.py`` at 79.8%
with 17 missed lines.  The existing nightly suite (``test_nightly_task_strategy_
and_swipe_filter_20261019.py``) only exercises the *HTTP* layer with mocked
CRUD objects, so the interesting CRUD branches were never entered:

* recovering a photo that a previous swipe already deleted (keep -> restore)
* rejecting ``keep`` on a photo that reached the recycle bin by another route
* rolling the transaction back when one item of a batch is unknown
* undoing a ``delete`` decision and putting the photo back into its albums

These tests drive the real CRUD functions against a real SQLite session so the
assertions describe what the database ends up holding, not mock call shapes.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def seeded(face_sqlite_session):
    """One owner with three photos; the middle one lives in an album."""
    from app.db.models.album import Album
    from app.db.models.photo import FileType, Photo

    db = face_sqlite_session
    owner_id = uuid.uuid4()

    album = Album(name="Swipe Album", owner_id=owner_id)
    db.add(album)
    db.flush()

    photos = []
    for index, name in enumerate(("a.jpg", "b.jpg", "c.jpg")):
        photo = Photo(
            id=uuid.uuid4(),
            owner_id=owner_id,
            filename=name,
            file_path=f"/photos/{name}",
            photo_time=None,
            file_type=FileType.image,
            size=100 + index,
            width=800,
            height=600,
            duration=0.0,
        )
        db.add(photo)
        photos.append(photo)

    db.flush()
    photos[1].albums.append(album)
    db.commit()

    return SimpleNamespace(db=db, owner_id=owner_id, album=album, photos=photos)


def _item(photo, decision):
    return SimpleNamespace(photo_id=photo.id, decision=decision)


# ---------------------------------------------------------------------------
# save_decisions -- happy path
# ---------------------------------------------------------------------------


def test_save_decisions_delete_marks_the_photo(seeded):
    from app.crud.swipe_filter import get_stats, save_decisions

    photo = seeded.photos[0]
    assert save_decisions(seeded.db, seeded.owner_id, [_item(photo, "delete")]) == 1

    seeded.db.refresh(photo)
    assert photo.is_deleted is True
    assert photo.deleted_at is not None

    stats = get_stats(seeded.db, seeded.owner_id)
    assert stats["deleted"] == 1
    assert stats["kept"] == 0
    assert stats["processed"] == 1
    assert stats["remaining"] == 2


def test_save_decisions_keep_records_the_decision(seeded):
    from app.crud.swipe_filter import get_stats, save_decisions

    photo = seeded.photos[0]
    assert save_decisions(seeded.db, seeded.owner_id, [_item(photo, "keep")]) == 1

    seeded.db.refresh(photo)
    assert photo.is_deleted is False

    stats = get_stats(seeded.db, seeded.owner_id)
    assert stats["kept"] == 1
    assert stats["remaining"] == 2


# ---------------------------------------------------------------------------
# save_decisions -- the keep-after-delete recovery path
# ---------------------------------------------------------------------------


def test_save_decisions_keep_restores_a_previously_swiped_photo(seeded):
    """``delete`` then ``keep`` is the documented, idempotent recovery path."""
    from app.crud.swipe_filter import save_decisions

    photo = seeded.photos[1]
    save_decisions(seeded.db, seeded.owner_id, [_item(photo, "delete")])
    save_decisions(seeded.db, seeded.owner_id, [_item(photo, "keep")])

    seeded.db.refresh(photo)
    assert photo.is_deleted is False
    assert photo.deleted_at is None


def test_save_decisions_keep_on_recycle_bin_photo_is_rejected(seeded):
    """A photo deleted outside the swipe workflow cannot be 'kept'."""
    from app.crud.swipe_filter import save_decisions

    photo = seeded.photos[0]
    photo.is_deleted = True
    seeded.db.commit()

    with pytest.raises(ValueError) as exc_info:
        save_decisions(seeded.db, seeded.owner_id, [_item(photo, "keep")])

    assert "recycle bin" in str(exc_info.value)


# ---------------------------------------------------------------------------
# save_decisions -- error handling
# ---------------------------------------------------------------------------


def test_save_decisions_unknown_photo_raises_lookup_error(seeded):
    from app.crud.swipe_filter import save_decisions

    unknown = SimpleNamespace(photo_id=uuid.uuid4(), decision="keep")

    with pytest.raises(LookupError):
        save_decisions(seeded.db, seeded.owner_id, [unknown])



def test_save_decisions_rolls_back_the_whole_batch(seeded):
    """A bad item aborts the batch and leaves the good photo untouched."""
    from app.crud.swipe_filter import get_stats, save_decisions

    good = seeded.photos[0]
    unknown = SimpleNamespace(photo_id=uuid.uuid4(), decision="keep")

    with pytest.raises(LookupError):
        save_decisions(
            seeded.db,
            seeded.owner_id,
            [_item(good, "delete"), unknown],
        )

    seeded.db.refresh(good)
    assert good.is_deleted is False
    assert get_stats(seeded.db, seeded.owner_id)["processed"] == 0


# ---------------------------------------------------------------------------
# undo_decision
# ---------------------------------------------------------------------------


def test_undo_decision_restores_a_deleted_photo(seeded):
    from app.crud.swipe_filter import save_decisions, undo_decision

    photo = seeded.photos[1]
    save_decisions(seeded.db, seeded.owner_id, [_item(photo, "delete")])

    assert undo_decision(seeded.db, seeded.owner_id, photo.id) is True

    seeded.db.refresh(photo)
    assert photo.is_deleted is False
    assert photo.deleted_at is None


def test_undo_decision_without_a_record_returns_false(seeded):
    from app.crud.swipe_filter import undo_decision

    assert undo_decision(seeded.db, seeded.owner_id, seeded.photos[0].id) is False


def test_undo_decision_of_a_keep_decision_drops_the_record(seeded):
    """Undoing a 'keep' removes the bookkeeping but never touches the photo."""
    from app.crud.swipe_filter import get_stats, save_decisions, undo_decision

    photo = seeded.photos[0]
    save_decisions(seeded.db, seeded.owner_id, [_item(photo, "keep")])

    assert undo_decision(seeded.db, seeded.owner_id, photo.id) is True

    seeded.db.refresh(photo)
    assert photo.is_deleted is False
    assert get_stats(seeded.db, seeded.owner_id)["processed"] == 0


# ---------------------------------------------------------------------------
# get_batch / reset_decisions
# ---------------------------------------------------------------------------


def test_get_batch_skips_already_handled_photos(seeded):
    from app.crud.swipe_filter import get_batch, save_decisions

    save_decisions(seeded.db, seeded.owner_id, [_item(seeded.photos[0], "keep")])

    photos, stats = get_batch(seeded.db, seeded.owner_id, 10)

    assert seeded.photos[0].id not in {photo.id for photo in photos}
    assert stats["kept"] == 1
    assert stats["remaining"] == 2


def test_reset_decisions_clears_every_record(seeded):
    from app.crud.swipe_filter import get_stats, reset_decisions, save_decisions

    save_decisions(
        seeded.db,
        seeded.owner_id,
        [_item(seeded.photos[0], "keep"), _item(seeded.photos[1], "delete")],
    )

    assert reset_decisions(seeded.db, seeded.owner_id) == 2
    assert get_stats(seeded.db, seeded.owner_id)["processed"] == 0
