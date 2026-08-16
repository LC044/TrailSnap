content = r"""Unit tests covering 2026-08-16 nightly coverage gap scan.

Targets uncovered branches in app.crud.face (previously 36.7% covered, 131 of
207 lines missed). The existing test_nightly_crud_tag_face_gaps_20260812.py
already exercises a handful of helpers (get_face / update_face / create_identity
/ get_identities); this file complements it with the rest of the surface.

All DB interactions are mocked via MagicMock + SimpleNamespace so the tests run
in isolation without a live Postgres.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Query helper: self-referencing chain mock.
# ``_q()`` returns a ``_Chain`` whose terminal methods (``first`` / ``all`` /
# ``get`` / ``one`` / ``one_or_none``) return caller-supplied values and whose
# intermediate chain methods all return the SAME chain. ``subquery`` returns a
# stand-in with ``.c.count`` for SQL ``func.coalesce(...)`` consumption.
# ---------------------------------------------------------------------------

class _Subquery:
    def __init__(self):
        # The query composes ``subq.c.count.desc().nullslast()`` so the
        # stand-in must support those chain methods.
        col = SimpleNamespace()
        col.count = SimpleNamespace(
            desc=lambda: SimpleNamespace(nullslast=lambda: "__ordered_count__"),
        )
        col.face_identity_id = SimpleNamespace(
            isnot=lambda: "__isnot__",
        )
        self.c = col


class _Chain:
    def __init__(self, *, first=None, all=None, get=None, one=None, one_or_none=None):
        self._terminal = {
            "first": first,
            "all": all,
            "get": get,
            "one": one,
            "one_or_none": one_or_none,
        }

    def __getattr__(self, name):
        if name in self._terminal:
            value = self._terminal[name]
            def _terminal(*args, **kwargs):
                return value
            return _terminal
        # Subquery returns a stand-in object, not the chain.
        if name == "subquery":
            def _subq(*args, **kwargs):
                return _Subquery()
            return _subq
        # Any other chain method returns self so the chain is fully composable.
        def _chain(*args, **kwargs):
            return self
        return _chain


def _q(*, subquery=None, **kwargs):
    if subquery is None:
        return _Chain(**kwargs)
    # When subquery is requested, return a chain whose `.subquery()`
    # terminal method returns the supplied subquery stand-in.
    m = _Chain(**kwargs)
    def _subq(*args, **kwargs):
        return subquery
    m.subquery = _subq
    return m


def _fresh_db():
    db = MagicMock(name="db")
    db.commit = MagicMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.refresh = MagicMock()
    db.flush = MagicMock()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q())
    return db


def _face(**overrides):
    base = dict(
        id=1,
        photo_id=uuid4(),
        face_identity_id=None,
        face_rect=[0.1, 0.2, 0.3, 0.4],
        face_confidence=0.99,
        recognize_confidence=0.0,
        face_feature=None,
        is_deleted=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _identity(**overrides):
    base = dict(
        id=uuid4(),
        identity_name="Alice",
        owner_id=uuid4(),
        default_face_id=None,
        is_hidden=False,
        is_deleted=False,
        description=None,
        tags=None,
        create_time=datetime(2026, 1, 1),
        update_time=datetime(2026, 1, 1),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# create_face
# ---------------------------------------------------------------------------


def test_create_face_persists_all_fields():
    from app.crud import face as crud_face
    from app.schemas.face import FaceCreate

    db = _fresh_db()
    photo_id = uuid4()
    identity_id = uuid4()
    obj_in = FaceCreate(
        photo_id=photo_id,
        face_identity_id=identity_id,
        face_rect=[0.0, 0.1, 0.2, 0.3],
        face_confidence=0.85,
        recognize_confidence=0.5,
    )

    result = crud_face.create_face(db, obj_in)

    db.add.assert_called_once_with(result)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(result)
    assert result.photo_id == photo_id
    assert result.face_identity_id == identity_id
    assert result.face_confidence == 0.85
    assert result.recognize_confidence == 0.5


# ---------------------------------------------------------------------------
# get_faces
# ---------------------------------------------------------------------------


def test_get_faces_returns_list():
    from app.crud import face as crud_face

    db = _fresh_db()
    faces = [_face(id=1), _face(id=2)]
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(all=faces))

    result = crud_face.get_faces(db, skip=0, limit=10)

    assert result == faces


def test_get_faces_joins_photo_when_owner_provided():
    from app.crud import face as crud_face

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(all=[]))
    owner = uuid4()

    result = crud_face.get_faces(db, skip=0, limit=5, owner_id=owner)

    assert result == []


# ---------------------------------------------------------------------------
# delete_face / delete_faces + handle_face_deletion_dependency
# ---------------------------------------------------------------------------


def test_delete_face_returns_none_when_face_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=None))

    result = crud_face.delete_face(db, 99, owner_id=uuid4())

    assert result is None
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_delete_face_deletes_and_returns_face():
    from app.crud import face as crud_face

    db = _fresh_db()
    face = _face(id=7)
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=face))

    result = crud_face.delete_face(db, 7)

    db.delete.assert_called_once_with(face)
    db.commit.assert_called_once()
    assert result is face


def test_delete_faces_iterates_each_id():
    from app.crud import face as crud_face

    db = _fresh_db()
    face = _face(id=1)
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=face))

    crud_face.delete_faces(db, [1, 2, 3])

    # delete_face commits once per id.
    assert db.delete.call_count == 3
    assert db.commit.call_count == 3


def test_handle_face_deletion_dependency_repoints_default_to_replacement():
    from app.crud import face as crud_face

    db = _fresh_db()
    current = _face(id=10, face_identity_id=uuid4())
    replacement = _face(id=20, face_identity_id=current.face_identity_id)
    identity = _identity(id=current.face_identity_id, default_face_id=current.id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(get=identity)
        return _q(first=replacement)

    db.query = MagicMock(side_effect=query_factory)

    crud_face.handle_face_deletion_dependency(db, current)

    assert identity.default_face_id == replacement.id
    db.add.assert_called_once_with(identity)
    db.flush.assert_called_once()


def test_handle_face_deletion_dependency_clears_default_when_no_other_face():
    from app.crud import face as crud_face

    db = _fresh_db()
    current = _face(id=10, face_identity_id=uuid4())
    identity = _identity(id=current.face_identity_id, default_face_id=current.id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(get=identity)
        return _q(first=None)

    db.query = MagicMock(side_effect=query_factory)

    crud_face.handle_face_deletion_dependency(db, current)

    assert identity.default_face_id is None
    db.add.assert_called_once_with(identity)


def test_handle_face_deletion_dependency_noop_when_face_unbound():
    from app.crud import face as crud_face

    db = _fresh_db()
    current = _face(id=10, face_identity_id=None)

    crud_face.handle_face_deletion_dependency(db, current)

    db.add.assert_not_called()
    db.flush.assert_not_called()


# ---------------------------------------------------------------------------
# get_identity / update_identity / delete_identity
# ---------------------------------------------------------------------------


def test_get_identity_returns_identity():
    from app.crud import face as crud_face

    db = _fresh_db()
    identity = _identity()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=identity))

    result = crud_face.get_identity(db, identity.id, owner_id=identity.owner_id)

    assert result is identity


def test_update_identity_returns_none_when_missing():
    from app.crud import face as crud_face
    from app.schemas.face import FaceIdentityUpdate

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=None))

    result = crud_face.update_identity(
        db, uuid4(), FaceIdentityUpdate(), owner_id=uuid4(),
    )

    assert result is None
    db.commit.assert_not_called()


def test_update_identity_persists_changes():
    from app.crud import face as crud_face
    from app.schemas.face import FaceIdentityUpdate

    db = _fresh_db()
    identity = _identity(identity_name="Old")
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=identity))

    result = crud_face.update_identity(
        db, identity.id, FaceIdentityUpdate(identity_name="New"), owner_id=identity.owner_id,
    )

    assert result.identity_name == "New"
    db.add.assert_called_once_with(identity)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(identity)


def test_delete_identity_returns_false_when_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=None))

    result = crud_face.delete_identity(db, uuid4(), owner_id=uuid4())

    assert result is False


def test_delete_identity_removes_and_commits():
    from app.crud import face as crud_face

    db = _fresh_db()
    identity = _identity()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=identity))

    result = crud_face.delete_identity(db, identity.id, owner_id=identity.owner_id)

    db.delete.assert_called_once_with(identity)
    db.commit.assert_called_once()
    assert result is True


# ---------------------------------------------------------------------------
# get_identities_with_details
# ---------------------------------------------------------------------------


def _photo_schema(photo_id):
    """Build a Photo schema with the minimum required fields."""
    from app.schemas.photo import Photo as PhotoSchema
    from app.db.models.photo import FileType
    return PhotoSchema(
        id=photo_id,
        file_type=FileType.image,
        size=1024,
        width=100,
        height=100,
        duration=None,
        filename="test.jpg",
        photo_time=datetime(2026, 1, 1),
        file_path="/tmp/test.jpg",
        upload_time=datetime(2026, 1, 1),
    )


def test_get_identities_with_details_builds_cover_for_each_row():
    from app.crud import face as crud_face

    db = _fresh_db()
    identity = _identity()
    default_face = _face(id=1, face_identity_id=identity.id)
    photo = _photo_schema(default_face.photo_id)
    rows = [(identity, 3, default_face, photo)]

    def query_factory(*args, **kwargs):
        if not hasattr(query_factory, "called"):
            query_factory.called = True
            return _q(subquery=_Subquery())
        return _q(all=rows)

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.get_identities_with_details(
        db, skip=0, limit=10, min_photos=0, photo_id=None, visibility_types=None,
        owner_id=identity.owner_id,
    )

    assert len(result) == 1
    schema = result[0]
    assert schema.face_count == 3
    assert schema.cover_photo is not None
    assert schema.cover_photo.photo_id == default_face.photo_id


def test_get_identities_with_details_skips_cover_when_default_face_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    identity = _identity()
    rows = [(identity, 0, None, None)]

    def query_factory(*args, **kwargs):
        if not hasattr(query_factory, "called"):
            query_factory.called = True
            return _q(subquery=_Subquery())
        return _q(all=rows)

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.get_identities_with_details(db)

    assert result[0].cover_photo is None
    assert result[0].cover is None


def test_get_identities_with_details_empty_list_when_no_rows():
    from app.crud import face as crud_face

    db = _fresh_db()

    def query_factory(*args, **kwargs):
        if not hasattr(query_factory, "called"):
            query_factory.called = True
            return _q(subquery=_Subquery())
        return _q(all=[])

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.get_identities_with_details(db)

    assert result == []


# ---------------------------------------------------------------------------
# get_identities_by_photo_id
# ---------------------------------------------------------------------------


def test_get_identities_by_photo_id_returns_empty_when_no_match():
    from app.crud import face as crud_face

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(all=[]))

    result = crud_face.get_identities_by_photo_id(db, uuid4(), owner_id=uuid4())

    assert result == []


def test_get_identities_by_photo_id_aggregates_face_count_per_identity():
    from app.crud import face as crud_face

    db = _fresh_db()
    photo_id = uuid4()
    identity = _identity()
    face = _face(id=11, face_identity_id=identity.id, photo_id=photo_id)
    photo = SimpleNamespace(id=photo_id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(all=[(face, identity, photo)])
        return _q(all=[(identity.id, 4)])

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.get_identities_by_photo_id(db, photo_id, owner_id=identity.owner_id)

    assert len(result) == 1
    assert result[0].face_count == 4
    assert result[0].cover_photo.photo_id == photo_id


# ---------------------------------------------------------------------------
# get_identity_photos
# ---------------------------------------------------------------------------


def test_get_identity_photos_returns_ordered_list():
    from app.crud import face as crud_face

    db = _fresh_db()
    photo = SimpleNamespace(id=uuid4())
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(all=[photo]))

    result = crud_face.get_identity_photos(db, uuid4(), skip=0, limit=20, owner_id=uuid4())

    assert result == [photo]


# ---------------------------------------------------------------------------
# remove_photos_from_identity
# ---------------------------------------------------------------------------


def test_remove_photos_from_identity_returns_zero_when_identity_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=None))

    result = crud_face.remove_photos_from_identity(
        db, uuid4(), [uuid4()], owner_id=uuid4(),
    )

    assert result == 0


def test_remove_photos_from_identity_clears_face_identity_id_and_returns_count():
    from app.crud import face as crud_face

    db = _fresh_db()
    identity_id = uuid4()
    identity = _identity(id=identity_id, default_face_id=None)
    f1 = _face(id=1, face_identity_id=identity_id)
    f2 = _face(id=2, face_identity_id=identity_id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(first=identity)
        return _q(all=[f1, f2])

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.remove_photos_from_identity(
        db, identity_id, [uuid4(), uuid4()], owner_id=identity.owner_id,
    )

    assert result == 2
    assert f1.face_identity_id is None
    assert f2.face_identity_id is None
    db.add.assert_any_call(f1)
    db.add.assert_any_call(f2)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# delete_faces_by_photo
# ---------------------------------------------------------------------------


def test_delete_faces_by_photo_deletes_below_threshold():
    from app.crud import face as crud_face

    db = _fresh_db()
    f1 = _face(id=1, face_confidence=0.4)
    f2 = _face(id=2, face_confidence=0.3)
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(all=[f1, f2]))

    result = crud_face.delete_faces_by_photo(db, uuid4(), confidence_threshold=0.5)

    assert result == 2
    assert db.delete.call_count == 2
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# set_identity_cover
# ---------------------------------------------------------------------------


def test_set_identity_cover_returns_false_when_identity_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=None))

    result = crud_face.set_identity_cover(db, uuid4(), uuid4(), owner_id=uuid4())

    assert result is False


def test_set_identity_cover_returns_false_when_face_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    identity = _identity()
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(first=identity)
        return _q(first=None)

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.set_identity_cover(db, identity.id, uuid4(), owner_id=identity.owner_id)

    assert result is False
    db.commit.assert_not_called()


def test_set_identity_cover_updates_default_face_id():
    from app.crud import face as crud_face

    db = _fresh_db()
    identity = _identity()
    face = _face(id=99, face_identity_id=identity.id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(first=identity)
        return _q(first=face)

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.set_identity_cover(
        db, identity.id, face.photo_id, owner_id=identity.owner_id,
    )

    assert result is True
    assert identity.default_face_id == face.id
    db.add.assert_called_once_with(identity)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# merge_identities
# ---------------------------------------------------------------------------


def test_merge_identities_returns_false_when_target_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    db.query = MagicMock(side_effect=lambda *_a, **_k: _q(first=None))

    result = crud_face.merge_identities(
        db, uuid4(), [uuid4(), uuid4()], owner_id=uuid4(),
    )

    assert result is False


def test_merge_identities_moves_faces_and_soft_deletes_sources():
    from app.crud import face as crud_face

    db = _fresh_db()
    target_id = uuid4()
    source_id = uuid4()
    target = _identity(id=target_id)
    source = _identity(id=source_id, is_deleted=False)
    moved_face = _face(id=1, face_identity_id=source_id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(first=target)
        if calls[0] == 2:
            return _q(first=source)
        return _q(all=[moved_face])

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.merge_identities(
        db, target_id, [source_id], owner_id=target.owner_id,
    )

    assert result is True
    assert moved_face.face_identity_id == target_id
    assert source.is_deleted is True
    db.commit.assert_called_once()


def test_merge_identities_skips_source_equal_to_target():
    from app.crud import face as crud_face

    db = _fresh_db()
    target_id = uuid4()
    target = _identity(id=target_id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(first=target)
        return _q(first=None)

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.merge_identities(
        db, target_id, [target_id, uuid4()], owner_id=target.owner_id,
    )

    assert result is True
    db.commit.assert_called_once()


def test_merge_identities_continues_when_source_missing():
    from app.crud import face as crud_face

    db = _fresh_db()
    target_id = uuid4()
    missing_source_id = uuid4()
    target = _identity(id=target_id)
    calls = [0]

    def query_factory(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return _q(first=target)
        return _q(first=None)

    db.query = MagicMock(side_effect=query_factory)

    result = crud_face.merge_identities(
        db, target_id, [missing_source_id], owner_id=target.owner_id,
    )

    assert result is True
    db.commit.assert_called_once()
