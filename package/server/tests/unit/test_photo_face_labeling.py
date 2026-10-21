"""Real database regressions for explicit face selection and ownership."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import Photo, FileType
from app.db.models.user import User
from app.service.photo_faces import assign_photo_face, list_photo_faces

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


@pytest.fixture
def library(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", lambda *args: None)
    owner = User(id=uuid4(), username="face-owner", hashed_password="x")
    other = User(id=uuid4(), username="face-other", hashed_password="x")
    alice = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="Alice")
    bob = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="Bob")
    foreign = FaceIdentity(id=uuid4(), owner_id=other.id, identity_name="Private")
    photo = Photo(id=uuid4(), owner_id=owner.id, filename="group.jpg", file_path="/group.jpg", file_type=FileType.image)
    db.add_all([owner, other, alice, bob, foreign, photo])
    db.flush()
    first = Face(photo_id=photo.id, face_identity_id=alice.id, face_rect=[.1, .1, .3, .4])
    second = Face(photo_id=photo.id, face_rect=[.5, .1, .7, .4])
    db.add_all([first, second])
    db.flush()
    alice.default_face_id = first.id
    db.commit()
    return db, owner, other, alice, bob, foreign, photo, first, second


def test_labels_include_unassigned_and_only_selected_face_changes(library):
    db, owner, _, alice, bob, _, photo, first, second = library
    faces = list_photo_faces(db, photo.id, owner.id)
    assert [(f.id, f.identity_name) for f in faces] == [(first.id, "Alice"), (second.id, None)]
    assign_photo_face(db, photo.id, second.id, bob.id, owner.id)
    assert first.face_identity_id == alice.id
    assert second.face_identity_id == bob.id
    assert float(second.recognize_confidence) == 1
    assert bob.default_face_id == second.id
    assign_photo_face(db, photo.id, first.id, bob.id, owner.id)
    assert alice.default_face_id is None
    assert bob.default_face_id == second.id
    assign_photo_face(db, photo.id, second.id, None, owner.id)
    assert second.face_identity_id is None
    assert second.recognize_confidence is None
    assert bob.default_face_id == first.id


@pytest.mark.parametrize("case", ["foreign-photo", "foreign-person", "wrong-photo-face", "deleted-photo", "deleted-face", "deleted-person", "hidden-person"])
def test_invalid_access_does_not_modify_assignment(library, case):
    db, owner, other, alice, bob, foreign, photo, first, second = library
    user_id, face_id, identity_id = owner.id, second.id, bob.id
    if case == "foreign-photo": user_id = other.id
    if case == "foreign-person": identity_id = foreign.id
    if case == "wrong-photo-face": face_id = 999999
    if case == "deleted-photo": photo.is_deleted = True
    if case == "deleted-face": second.is_deleted = True
    if case == "deleted-person": bob.is_deleted = True
    if case == "hidden-person": bob.is_hidden = True
    db.commit()
    with pytest.raises(HTTPException) as exc:
        assign_photo_face(db, photo.id, face_id, identity_id, user_id)
    assert exc.value.status_code == 404
    assert second.face_identity_id is None
    assert first.face_identity_id == alice.id


def test_face_list_hides_private_or_deleted_identities(library):
    db, owner, other, alice, bob, foreign, photo, first, second = library
    with pytest.raises(HTTPException):
        list_photo_faces(db, photo.id, other.id)
    first.face_identity_id = foreign.id
    second.is_deleted = True
    db.commit()
    faces = list_photo_faces(db, photo.id, owner.id)
    assert len(faces) == 1
    assert faces[0].identity_id is None
    assert faces[0].identity_name is None


def test_hover_read_does_not_select_embedding_columns(library):
    from sqlalchemy import event
    db, owner, _, _, _, _, photo, _, _ = library
    statements = []
    def capture(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        assert len(list_photo_faces(db, photo.id, owner.id)) == 2
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    face_queries = [sql for sql in statements if "FROM faces" in sql]
    assert len(face_queries) == 1
    assert "face_feature" not in face_queries[0]


def test_named_people_with_one_or_two_photos_remain_visible_below_clustering_threshold(library, monkeypatch):
    from app.api.face import list_identities
    from app.crud.face import get_identities_with_details
    from types import SimpleNamespace
    db, owner, other, alice, bob, foreign, photo, first, second = library
    photo.size = 1000
    second.face_identity_id = bob.id
    another = Photo(id=uuid4(), owner_id=owner.id, filename="second.jpg", file_path="/second.jpg", file_type=FileType.image)
    unnamed = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="未命名")
    deleted = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="Deleted", is_deleted=True)
    db.add_all([another, unnamed, deleted])
    db.flush()
    db.add_all([Face(photo_id=another.id, face_identity_id=bob.id), Face(photo_id=photo.id, face_identity_id=unnamed.id)])
    db.commit()
    monkeypatch.setattr("app.api.face.config_manager.get_user_config", lambda *args: SimpleNamespace(ai=SimpleNamespace(face_recognition_min_photos=5)))
    result = list_identities(skip=0, limit=100, types=["named", "unnamed"], min_photos=None, db=db, current_user=owner)
    assert {person.id for person in result.data} == {alice.id, bob.id}
    assert {person.id: person.face_count for person in result.data} == {alice.id: 1, bob.id: 2}
    explicit = list_identities(skip=0, limit=100, types=["named", "unnamed"], min_photos=2, db=db, current_user=owner)
    assert {person.id for person in explicit.data} == {bob.id}
    assert get_identities_with_details(db, min_photos=5, owner_id=owner.id) == []
