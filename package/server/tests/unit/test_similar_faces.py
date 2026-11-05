"""Real SQLite tests for sample search, reviewed transactions and undo."""
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.schemas.face import AssignSimilarFaces
from app.service.similar_faces import (
    _candidate_query, _sign, assign_similar_faces, search_similar_faces, undo_face_assignment,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def vector(a=1.0, b=0.0):
    return [a, b] + [0.0] * 510


@pytest.fixture
def library(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    updates = []
    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update",
                        lambda db, owner, ids, **kwargs: updates.append(ids))
    owner = User(id=uuid4(), username="similar-owner", hashed_password="x")
    other = User(id=uuid4(), username="similar-other", hashed_password="x")
    alice = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="Alice")
    bob = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="Bob")
    hidden = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="Hidden", is_hidden=True)
    photo = Photo(id=uuid4(), owner_id=owner.id, filename="group.jpg", file_path="/group.jpg",
                  file_type=FileType.image, photo_time=datetime(2025, 6, 1))
    second_photo = Photo(id=uuid4(), owner_id=owner.id, filename="second.jpg",
                         file_path="/second.jpg", file_type=FileType.image)
    private_photo = Photo(id=uuid4(), owner_id=other.id, filename="private.jpg",
                          file_path="/private.jpg", file_type=FileType.image)
    db.add_all([owner, other, alice, bob, hidden, photo, second_photo, private_photo])
    db.flush()
    rect = [.1, .1, .3, .4]
    seed = Face(photo_id=photo.id, face_identity_id=alice.id, face_rect=rect,
                face_feature=vector(), recognize_confidence=.7)
    same_photo = Face(photo_id=photo.id, face_identity_id=alice.id, face_rect=[.5, .1, .7, .4],
                      face_feature=vector(2, .1), recognize_confidence=1)
    unassigned = Face(photo_id=second_photo.id, face_rect=rect, face_feature=vector(1, .1))
    broad = Face(photo_id=second_photo.id, face_rect=rect, face_feature=vector(.5, .866))
    wrong = Face(photo_id=photo.id, face_identity_id=bob.id, face_rect=rect, face_feature=vector(0, 1))
    invisible = Face(photo_id=photo.id, face_identity_id=hidden.id, face_rect=rect, face_feature=vector())
    foreign = Face(photo_id=private_photo.id, face_rect=rect, face_feature=vector())
    zero = Face(photo_id=photo.id, face_rect=rect, face_feature=vector(0, 0))
    invalid_rect = Face(photo_id=photo.id, face_rect=[.5, .5, .1, .1], face_feature=vector())
    db.add_all([seed, same_photo, unassigned, broad, wrong, invisible, foreign, zero, invalid_rect])
    db.flush()
    alice.default_face_id = seed.id
    db.commit()
    return dict(db=db, owner=owner, other=other, alice=alice, bob=bob, hidden=hidden,
                photo=photo, seed=seed, same=same_photo, unassigned=unassigned,
                broad=broad, wrong=wrong, foreign=foreign, zero=zero, updates=updates)


def search(lib, **kwargs):
    return search_similar_faces(lib["db"], lib["photo"].id, lib["seed"].id, lib["owner"].id, **kwargs)


def selection(result, target, ids):
    return AssignSimilarFaces(identity_id=target.id if target else None, selections=[
        {"face_id": item.id, "review_token": item.review_token}
        for item in [result.reference, *result.items] if item.id in ids
    ])


def apply(lib, result, ids):
    return assign_similar_faces(lib["db"], lib["photo"].id, lib["seed"].id, lib["owner"].id,
                                selection(result, lib["bob"], ids))


def test_search_is_face_local_ranked_and_never_returns_private_or_invalid_faces(library):
    lib = library
    result = search(lib)
    assert result.reference.id == lib["seed"].id
    assert [row.id for row in result.items] == [lib["same"].id, lib["unassigned"].id]
    assert result.face_count == 2 and result.photo_count == 2
    assert result.items[0].manually_confirmed is True
    assert result.items[1].identity_id is None
    assert all(row.face_rect and row.review_token for row in result.items)
    assert lib["updates"] == [] and lib["same"].face_identity_id == lib["alice"].id


def test_filters_pagination_and_widening_keep_face_identity_separate(library):
    lib = library
    assert [f.id for f in search(lib, scope="current").items] == [lib["same"].id]
    assert [f.id for f in search(lib, scope="unassigned").items] == [lib["unassigned"].id]
    assert [f.id for f in search(lib, exclude_identity_id=lib["alice"].id).items] == [lib["unassigned"].id]
    first = search(lib, limit=1)
    second = search(lib, skip=1, limit=1)
    assert first.has_more and not second.has_more
    assert first.items[0].id != second.items[0].id
    assert lib["broad"].id in {f.id for f in search(lib, match="broad").items}


def test_other_scope_includes_other_people_and_unassigned_but_excludes_current(library):
    lib = library
    lib["unassigned"].face_identity_id = lib["bob"].id
    lib["broad"].face_feature = vector()
    lib["db"].commit()
    result = search(lib, scope="other")
    assert {f.id for f in result.items} == {lib["unassigned"].id, lib["broad"].id}
    assert result.face_count == 2
    assert result.reference.id == lib["seed"].id
    excluded = search(lib, scope="other", exclude_identity_id=lib["bob"].id)
    assert [f.id for f in excluded.items] == [lib["broad"].id]
    first = search(lib, scope="other", limit=1)
    second = search(lib, scope="other", skip=1, limit=1)
    assert first.has_more and not second.has_more
    assert first.items[0].id != second.items[0].id


def test_other_scope_for_unassigned_sample_returns_only_assigned_faces(library):
    lib = library
    lib["seed"].face_identity_id = None
    lib["db"].commit()
    result = search(lib, scope="other")
    assert [f.id for f in result.items] == [lib["same"].id]
    assert result.reference.identity_id is None


@pytest.mark.parametrize("max_rows", [150000, 1])
def test_current_low_scope_ranks_dissimilar_faces_and_widens_without_including_other_people(library, monkeypatch, max_rows):
    from app.service.face_vector_cache import FaceVectorCache
    monkeypatch.setattr("app.service.similar_faces.face_vector_cache", FaceVectorCache(max_rows=max_rows))
    lib = library
    lib["broad"].face_identity_id = lib["alice"].id
    lib["wrong"].face_identity_id = lib["alice"].id
    lib["zero"].face_identity_id = lib["alice"].id
    moderate = Face(photo_id=lib["photo"].id, face_identity_id=lib["alice"].id,
                    face_rect=[.1, .1, .3, .4], face_feature=vector(.6, .8))
    lib["db"].add(moderate)
    lib["db"].commit()
    strict = search(lib, scope="current_low", match="strict")
    balanced = search(lib, scope="current_low")
    broad = search(lib, scope="current_low", match="broad")
    assert [f.id for f in strict.items] == [lib["wrong"].id]
    assert [f.id for f in balanced.items] == [lib["wrong"].id, lib["broad"].id]
    assert [f.id for f in broad.items] == [lib["wrong"].id, lib["broad"].id, moderate.id]
    assert balanced.face_count == 2 and balanced.photo_count == 2
    assert all(f.identity_id == lib["alice"].id for f in balanced.items)
    assert balanced.items[0].similarity < balanced.items[1].similarity
    assert balanced.reference.id == lib["seed"].id
    first = search(lib, scope="current_low", limit=1)
    second = search(lib, scope="current_low", skip=1, limit=1)
    assert first.has_more and not second.has_more
    assert [first.items[0].id, second.items[0].id] == [lib["wrong"].id, lib["broad"].id]
    assert search(lib, scope="current_low", exclude_identity_id=lib["alice"].id).items == []
    lib["wrong"].face_identity_id = lib["bob"].id
    lib["db"].commit()
    assert [f.id for f in search(lib, scope="current_low").items] == [lib["broad"].id]


def test_current_low_scope_requires_an_assigned_reference(library):
    lib = library
    lib["seed"].face_identity_id = None
    lib["db"].commit()
    with pytest.raises(HTTPException) as exc:
        search(lib, scope="current_low")
    assert exc.value.status_code == 422


@pytest.mark.parametrize("release", [False, True])
def test_low_similarity_faces_can_be_moved_or_released_without_deleting_and_undone(library, release):
    lib = library
    lib["broad"].face_identity_id = lib["alice"].id
    lib["broad"].recognize_confidence = .8
    lib["alice"].default_face_id = lib["broad"].id
    lib["db"].commit()
    preview = search(lib, scope="current_low")
    response = assign_similar_faces(
        lib["db"], lib["photo"].id, lib["seed"].id, lib["owner"].id,
        selection(preview, None if release else lib["bob"], {lib["broad"].id}),
    )
    assert response.face_count == 1 and response.undo_token
    assert lib["broad"].face_identity_id == (None if release else lib["bob"].id)
    assert lib["broad"].recognize_confidence == (None if release else 1.0)
    assert lib["broad"].is_deleted is False
    assert lib["seed"].face_identity_id == lib["alice"].id
    assert lib["same"].face_identity_id == lib["alice"].id
    assert lib["alice"].default_face_id == lib["same"].id
    assert lib["db"].get(Photo, lib["broad"].photo_id).is_deleted is False
    undo_face_assignment(lib["db"], lib["owner"].id, response.undo_token)
    assert lib["broad"].face_identity_id == lib["alice"].id
    assert float(lib["broad"].recognize_confidence) == .8
    assert len(lib["updates"]) == 2


def test_released_faces_undo_does_not_overwrite_later_reassignment(library):
    lib = library
    preview = search(lib)
    response = assign_similar_faces(
        lib["db"], lib["photo"].id, lib["seed"].id, lib["owner"].id,
        selection(preview, None, {lib["same"].id}),
    )
    lib["same"].face_identity_id = lib["bob"].id
    lib["db"].commit()
    with pytest.raises(HTTPException) as exc:
        undo_face_assignment(lib["db"], lib["owner"].id, response.undo_token)
    assert exc.value.status_code == 409
    assert lib["same"].face_identity_id == lib["bob"].id


def test_release_rejects_stale_selection_before_modifying_any_face(library):
    lib = library
    payload = selection(search(lib), None, {lib["seed"].id, lib["same"].id})
    lib["same"].recognize_confidence = .8
    lib["db"].commit()
    with pytest.raises(HTTPException) as exc:
        assign_similar_faces(lib["db"], lib["photo"].id, lib["seed"].id, lib["owner"].id, payload)
    assert exc.value.status_code == 409
    assert lib["seed"].face_identity_id == lib["alice"].id
    assert lib["same"].face_identity_id == lib["alice"].id
    assert lib["updates"] == []


def test_assignment_changes_only_selected_faces_repairs_covers_and_can_be_undone(library):
    lib = library
    selected_ids = {lib["seed"].id, lib["unassigned"].id}
    result = apply(lib, search(lib), selected_ids)
    assert result.face_count == 2 and len(result.photo_ids) == 2
    for key in ["seed", "unassigned"]:
        assert lib[key].face_identity_id == lib["bob"].id
        assert float(lib[key].recognize_confidence) == 1
    assert lib["same"].face_identity_id == lib["alice"].id
    assert lib["wrong"].face_identity_id == lib["bob"].id
    assert lib["alice"].default_face_id == lib["same"].id
    restored = undo_face_assignment(lib["db"], lib["owner"].id, result.undo_token)
    assert restored.face_count == 2
    assert lib["seed"].face_identity_id == lib["alice"].id
    assert float(lib["seed"].recognize_confidence) == .7
    assert lib["unassigned"].face_identity_id is None
    assert lib["unassigned"].recognize_confidence is None
    assert len(lib["updates"]) == 2
    with pytest.raises(HTTPException):
        undo_face_assignment(lib["db"], lib["owner"].id, result.undo_token)


def test_album_update_failure_rolls_back_faces_and_covers(library, monkeypatch):
    lib = library
    preview = search(lib)
    original_cover = lib["alice"].default_face_id

    def fail_update(db, owner, ids, *, commit):
        assert commit is False
        raise RuntimeError("album update failed")

    monkeypatch.setattr("app.crud.album.trigger_conditional_albums_update", fail_update)
    with pytest.raises(RuntimeError, match="album update failed"):
        apply(lib, preview, {lib["seed"].id, lib["unassigned"].id})
    assert lib["seed"].face_identity_id == lib["alice"].id
    assert lib["unassigned"].face_identity_id is None
    assert lib["alice"].default_face_id == original_cover


@pytest.mark.parametrize("change", ["identity", "confidence", "rect", "delete-face", "delete-photo", "hidden-identity"])
def test_stale_selection_rolls_back_entire_batch(library, change):
    lib = library
    preview = search(lib)
    if change == "identity": lib["same"].face_identity_id = lib["bob"].id
    if change == "confidence": lib["same"].recognize_confidence = .8
    if change == "rect": lib["same"].face_rect = [.6, .1, .8, .4]
    if change == "delete-face": lib["same"].is_deleted = True
    if change == "delete-photo": lib["db"].get(Photo, lib["same"].photo_id).is_deleted = True
    if change == "hidden-identity": lib["alice"].is_hidden = True
    lib["db"].commit()
    with pytest.raises(HTTPException) as exc:
        apply(lib, preview, {lib["unassigned"].id, lib["same"].id})
    assert exc.value.status_code in {404, 409}
    assert lib["unassigned"].face_identity_id is None
    assert lib["updates"] == []


def test_tokens_cannot_be_tampered_reused_for_another_face_owner_or_sample(library):
    lib = library
    preview = search(lib)
    for candidate in [
        {"face_id": lib["same"].id, "review_token": preview.items[1].review_token},
        {"face_id": lib["unassigned"].id, "review_token": "invalid"},
    ]:
        with pytest.raises(HTTPException) as exc:
            assign_similar_faces(lib["db"], lib["photo"].id, lib["seed"].id, lib["owner"].id,
                                 AssignSimilarFaces(identity_id=lib["bob"].id, selections=[candidate]))
        assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        search_similar_faces(lib["db"], lib["photo"].id, lib["seed"].id, lib["other"].id)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        assign_similar_faces(lib["db"], lib["photo"].id, lib["same"].id, lib["owner"].id,
                             selection(preview, lib["bob"], {lib["unassigned"].id}))
    assert exc.value.status_code == 409


def test_undo_rejects_later_edits_and_expired_tokens_without_changing_any_face(library):
    lib = library
    result = apply(lib, search(lib), {lib["seed"].id, lib["unassigned"].id})
    lib["unassigned"].face_identity_id = lib["alice"].id
    lib["db"].commit()
    with pytest.raises(HTTPException) as exc:
        undo_face_assignment(lib["db"], lib["owner"].id, result.undo_token)
    assert exc.value.status_code == 409
    assert lib["seed"].face_identity_id == lib["bob"].id
    expired = _sign({"items": []}, lib["owner"].id, "face-undo", -1)
    with pytest.raises(HTTPException):
        undo_face_assignment(lib["db"], lib["owner"].id, expired)
    with pytest.raises(HTTPException):
        undo_face_assignment(lib["db"], lib["other"].id, result.undo_token)


def test_zero_sample_missing_features_and_deleted_reference_are_rejected(library):
    lib = library
    with pytest.raises(HTTPException) as exc:
        search_similar_faces(lib["db"], lib["photo"].id, lib["zero"].id, lib["owner"].id)
    assert exc.value.status_code == 422
    lib["seed"].face_feature = None
    lib["db"].commit()
    with pytest.raises(HTTPException) as exc:
        search(lib)
    assert exc.value.status_code == 422


def test_schema_bounds_batch_size_and_postgres_uses_scalar_distance(library):
    from sqlalchemy.dialects import postgresql
    from sqlalchemy import Float
    with pytest.raises(ValidationError):
        AssignSimilarFaces(identity_id=uuid4(), selections=[])
    with pytest.raises(ValidationError):
        AssignSimilarFaces(selections=[{"face_id": 1, "review_token": "x"}])
    assert AssignSimilarFaces(identity_id=None, selections=[{"face_id": 1, "review_token": "x"}]).identity_id is None
    with pytest.raises(ValidationError):
        AssignSimilarFaces(identity_id=uuid4(), selections=[
            {"face_id": i + 1, "review_token": "x"} for i in range(501)
        ])
    distance = Face.face_feature.cosine_distance(vector())
    assert isinstance(distance.type, Float)
    query = _candidate_query(library["db"], library["owner"].id).add_columns(
        distance.label("distance")).filter(distance <= .45)
    sql = str(query.statement.compile(dialect=postgresql.dialect()))
    assert "<=>" in sql
    assert "face_feature AS" not in sql
