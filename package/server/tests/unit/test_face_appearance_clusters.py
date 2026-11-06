"""Real SQLite coverage of multi-appearance identities and reset recovery."""
from types import SimpleNamespace
from uuid import uuid4
import numpy as np
import pytest

from app.db.models.face import Face, FaceCluster, FaceIdentity
from app.db.models.photo import Photo, FileType
from app.db.models.user import User
from app.service import face_appearance_clusters as clusters
from test_face_cluster_upgrade import legacy_database

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def vector(angle):
    result = np.zeros(512)
    result[:2] = [np.cos(angle), np.sin(angle)]
    return result.tolist()


@pytest.fixture
def library(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = User(id=uuid4(), username="cluster-owner", hashed_password="unused")
    db.add(owner)
    db.commit()
    config = SimpleNamespace(ai=SimpleNamespace(face_cluster_threshold=0.15, face_recognition_min_photos=2))
    monkeypatch.setattr(clusters.config_manager, "get_user_config", lambda *args: config)
    return db, owner


def add_face(db, owner, angle, identity=None):
    photo = Photo(id=uuid4(), owner_id=owner.id, filename=f"{uuid4()}.jpg",
                  file_path=f"/{uuid4()}.jpg", file_type=FileType.image)
    db.add(photo)
    db.flush()
    face = Face(photo_id=photo.id, face_feature=vector(angle), face_identity_id=identity)
    db.add(face)
    db.flush()
    return face


def separate_cluster(db, owner, angles, identity=None):
    group = None
    for angle in angles:
        face = add_face(db, owner, angle, identity)
        group = clusters.attach(db, face, group, clusters.unit(face.face_feature), owner.id, identity)
    db.flush()
    return group


def test_bootstrap_preserves_multiple_appearances_and_names(library):
    db, owner = library
    person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="孩子")
    db.add(person)
    db.flush()
    faces = [add_face(db, owner, angle, person.id) for angle in [0, .02, 1.4, 1.42]]
    person.default_face_id = faces[0].id
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert db.query(FaceCluster).count() == 2
    assert {face.face_identity_id for face in faces} == {person.id}
    assert person.identity_name == "孩子"
    assert person.default_face_id == faces[0].id
    assert all(face.face_cluster_id for face in faces)
    assert clusters.get_state(db, owner.id)["phase"] == "ready"


def test_new_faces_form_clusters_and_inherit_identity(library):
    db, owner = library
    first, second = [add_face(db, owner, angle) for angle in [0, .02]]
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert first.face_identity_id == second.face_identity_id
    assert first.face_identity_id is not None
    third = add_face(db, owner, .03)
    db.commit()
    clusters.process_faces(db, owner.id)
    db.refresh(third)
    assert third.face_cluster_id == first.face_cluster_id
    assert third.face_identity_id == first.face_identity_id
    assert db.get(FaceCluster, first.face_cluster_id).face_count == 3


def test_remove_updates_center_and_retains_no_exclusion(library):
    db, owner = library
    faces = [add_face(db, owner, a) for a in [0, .1, .2]]
    db.commit()
    clusters.process_faces(db, owner.id)
    cluster_id = faces[0].face_cluster_id
    clusters.lock_owner(db, owner.id)
    clusters.set_identity(db, faces[1], None, owner.id)
    db.commit()
    assert faces[1].face_cluster_id is None
    assert faces[1].face_identity_id is None
    cluster = db.get(FaceCluster, cluster_id)
    expected = clusters.unit(clusters.unit(vector(0)) + clusters.unit(vector(.2)))
    assert cluster.face_count == 2
    assert np.allclose(cluster.center, expected)
    clusters.process_faces(db, owner.id)
    db.refresh(faces[1])
    assert faces[1].face_cluster_id == cluster_id


def test_manual_assignment_of_different_appearance_creates_new_cluster(library):
    db, owner = library
    person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="A")
    db.add(person)
    db.flush()
    first = add_face(db, owner, 0, person.id)
    second = add_face(db, owner, 1.5)
    db.commit()
    clusters.process_faces(db, owner.id)
    clusters.lock_owner(db, owner.id)
    clusters.set_identity(db, second, person.id, owner.id)
    db.commit()
    assert first.face_cluster_id != second.face_cluster_id
    assert first.face_identity_id == second.face_identity_id == person.id


def test_reset_clears_names_and_reuses_vectors(library):
    db, owner = library
    person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="旧名字")
    db.add(person)
    db.flush()
    faces = [add_face(db, owner, angle, person.id) for angle in [0, .02]]
    db.commit()
    clusters.process_faces(db, owner.id)
    original = [face.face_feature[:] for face in faces]
    state = clusters.request_reset(db, owner.id)
    assert state["phase"] == "resetting"
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert person.is_deleted
    assert all(face.face_identity_id != person.id for face in faces)
    assert all(face.face_feature == feature for face, feature in zip(faces, original))
    assert db.query(FaceIdentity).filter(FaceIdentity.is_deleted.is_(False)).one().identity_name == "未命名"
    assert clusters.get_state(db, owner.id)["phase"] == "ready"


def test_single_face_defers_ambiguous_match_to_strict_cluster_checks(library):
    db, owner = library
    people = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name=name) for name in ["哥哥", "弟弟"]]
    db.add_all(people)
    db.flush()
    for angle, person in zip([0, .2], people):
        add_face(db, owner, angle, person.id)
    db.commit()
    clusters.process_faces(db, owner.id)
    index = clusters.load_index(db, owner.id)
    assert index.select(clusters.unit(vector(.11)), .15) is None
    face = add_face(db, owner, .11)
    db.commit()
    clusters.process_faces(db, owner.id)
    db.refresh(face)
    assert face.face_identity_id == people[1].id


def test_owner_isolation(library):
    db, owner = library
    other = User(id=uuid4(), username="cluster-other", hashed_password="unused")
    db.add(other)
    db.flush()
    face = add_face(db, other, 0)
    db.commit()
    clusters.process_faces(db, owner.id)
    db.refresh(face)
    assert face.face_cluster_id is None
    assert db.query(FaceCluster).count() == 0


def test_merge_moves_clusters_without_replacing_centers(library, monkeypatch):
    from app.crud.face import merge_identities
    db, owner = library
    people = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name=name) for name in ["A", "B"]]
    db.add_all(people)
    db.flush()
    faces = [add_face(db, owner, angle, person.id) for angle, person in zip([0, 1.5], people)]
    db.commit()
    clusters.process_faces(db, owner.id)
    before = {cluster.id: list(cluster.center) for cluster in db.query(FaceCluster).all()}
    assert merge_identities(db, people[0].id, [people[1].id], owner_id=owner.id)
    db.expire_all()
    assert {cluster.id: list(cluster.center) for cluster in db.query(FaceCluster).all()} == before
    assert {face.face_identity_id for face in faces} == {people[0].id}
    assert {cluster.identity_id for cluster in db.query(FaceCluster).all()} == {people[0].id}


def test_deleted_anchor_is_removed_from_statistics(library):
    db, owner = library
    faces = [add_face(db, owner, angle) for angle in [0, .1]]
    db.commit()
    clusters.process_faces(db, owner.id)
    cluster_id = faces[0].face_cluster_id
    clusters.detach_photo_clusters(db, [faces[0].photo_id])
    db.commit()
    cluster = db.get(FaceCluster, cluster_id)
    assert cluster.face_count == 1
    assert cluster.anchor_face_id == faces[1].id
    assert np.allclose(cluster.center, clusters.unit(faces[1].face_feature))


def test_reset_checkpoint_does_not_clear_results_twice(library, monkeypatch):
    db, owner = library
    faces = [add_face(db, owner, angle) for angle in [0, .02]]
    db.commit()
    clusters.process_faces(db, owner.id)
    clusters.request_reset(db, owner.id)
    original = clusters.attach
    calls = []
    def interrupt(*args, **kwargs):
        calls.append(True)
        raise RuntimeError("simulated interruption after clear")
    monkeypatch.setattr(clusters, "attach", interrupt)
    with pytest.raises(RuntimeError, match="simulated"):
        clusters.process_faces(db, owner.id)
    db.rollback()
    assert clusters.get_state(db, owner.id)["cleared"] is True
    monkeypatch.setattr(clusters, "attach", original)
    monkeypatch.setattr(clusters, "_clear_results", lambda *args: pytest.fail("must resume past completed clear"))
    clusters.process_faces(db, owner.id)
    assert clusters.get_state(db, owner.id)["phase"] == "ready"
    assert db.query(FaceCluster).count() == 1


def test_reset_api_status_and_gate(library, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import face as face_api
    db, owner = library
    monkeypatch.setattr("app.service.task_manager.TaskManager.get_instance",
                        lambda: SimpleNamespace(start_worker_for_pending_tasks=lambda: None))
    app = FastAPI()
    app.include_router(face_api.router, prefix="/api/faces")
    app.dependency_overrides[face_api.get_db] = lambda: db
    app.dependency_overrides[face_api.deps.get_current_user] = lambda: owner
    with TestClient(app) as client:
        result = client.post("/api/faces/clustering/reset")
        assert result.status_code == 200 and result.json()["code"] == 0
        assert client.get("/api/faces/clustering/status").json()["data"]["phase"] == "resetting"
        assert client.get("/api/faces/identities").status_code == 409
        first_generation = result.json()["data"]["generation"]
        assert client.post("/api/faces/clustering/reset").json()["data"]["generation"] == first_generation


def test_native_index_supports_updates_without_new_model():
    rng = np.random.default_rng(42)
    features = rng.normal(size=(1030, 512)).astype(np.float32)
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    rows = [{"id":uuid4(), "identity":uuid4(), "center":feature, "anchor":feature, "revision":1}
            for feature in features]
    index = clusters.ClusterIndex(rows)
    assert index.ann is not None
    assert index.select(features[0], .2)["id"] == rows[0]["id"]
    updated = rng.normal(size=512).astype(np.float32)
    updated /= np.linalg.norm(updated)
    rows[0]["center"] = updated
    rows[0]["anchor"] = updated
    index.upsert(rows[0])
    assert index.select(updated, .2)["id"] == rows[0]["id"]


def test_reset_during_computation_discards_old_generation(library, monkeypatch):
    db, owner = library
    faces = [add_face(db, owner, angle) for angle in [0, .02]]
    db.commit()
    original = clusters.ClusterIndex.select
    reset = []
    def reset_once(index, *args, **kwargs):
        if not reset:
            reset.append(True)
            clusters.request_reset(db, owner.id)
        return original(index, *args, **kwargs)
    monkeypatch.setattr(clusters.ClusterIndex, "select", reset_once)
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert clusters.get_state(db, owner.id)["generation"] == 1
    assert clusters.get_state(db, owner.id)["phase"] == "ready"
    assert all(face.face_cluster_id is not None for face in faces)


def test_reset_request_id_is_idempotent_after_completion(library):
    db, owner = library
    request_id = uuid4()
    first = clusters.request_reset(db, owner.id, request_id)
    clusters.process_faces(db, owner.id)
    repeated = clusters.request_reset(db, owner.id, request_id)
    assert repeated['generation'] == first['generation']
    assert repeated['phase'] == 'ready'


def test_initialization_retry_preserves_existing_people(library):
    db, owner = library
    person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name='保留姓名')
    db.add(person)
    db.flush()
    face = add_face(db, owner, 0, person.id)
    clusters.save_state(db, owner.id, {'phase':'failed', 'generation':0, 'revision':0})
    db.commit()
    clusters.retry_clustering(db, owner.id)
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert not person.is_deleted and person.identity_name == '保留姓名'
    assert face.face_identity_id == person.id and face.face_cluster_id is not None


def test_strict_cross_appearance_link_preserves_two_centers(library):
    db, owner = library
    # Tighten the core groups separately while retaining cross-group support.
    config = SimpleNamespace(ai=SimpleNamespace(face_cluster_threshold=.4, face_recognition_min_photos=2))
    from unittest.mock import patch
    faces = [add_face(db, owner, angle) for angle in [-.3, .1, .7, .45]]
    db.commit()
    with patch.object(clusters.config_manager, 'get_user_config', return_value=config):
        clusters.process_faces(db, owner.id)
    db.expire_all()
    assert db.query(FaceCluster).count() == 2
    assert len({face.face_identity_id for face in faces}) == 1
    assert faces[0].face_cluster_id != faces[2].face_cluster_id


def test_new_cluster_links_when_two_existing_people_are_similar(library):
    db, owner = library
    people = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name=f"同一人的分组{i}") for i in range(2)]
    db.add_all(people)
    db.flush()
    separate_cluster(db, owner, [0, .01], people[0].id)
    nearest = separate_cluster(db, owner, [.05, .06], people[1].id)
    faces = [add_face(db, owner, angle) for angle in [.5, .51]]
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert db.query(FaceIdentity).count() == 2
    assert db.query(FaceCluster).count() == 3
    assert {face.face_identity_id for face in faces} == {people[1].id}
    assert faces[0].face_cluster_id == faces[1].face_cluster_id
    assert faces[0].face_cluster_id != nearest.id


def test_cluster_link_still_requires_bidirectional_member_support(library):
    db, owner = library
    person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="已有的人物")
    db.add(person)
    db.flush()
    separate_cluster(db, owner, [0, .01], person.id)
    pending = separate_cluster(db, owner, [-.7, .7])
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert pending.identity_id is not None and pending.identity_id != person.id
    assert db.query(FaceCluster).count() == 2


def test_native_unsigned_candidate_labels_are_valid_numpy_indices(library, monkeypatch):
    db, owner = library
    faces = [add_face(db, owner, angle) for angle in [0, .02]]
    db.commit()
    original = clusters.ClusterIndex.batch_candidates
    def unsigned(index, *args, **kwargs):
        return [np.asarray(row, dtype=np.uint64) for row in original(index, *args, **kwargs)]
    monkeypatch.setattr(clusters.ClusterIndex, 'batch_candidates', unsigned)
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert faces[0].face_cluster_id == faces[1].face_cluster_id


def test_finalization_reloads_index_after_manual_edit(library, monkeypatch):
    db, owner = library
    original = clusters._unclustered_batch
    reads = []

    def edit_once(session, owner_id, last_id):
        rows = original(session, owner_id, last_id)
        reads.append(True)
        if len(reads) == 1:
            clusters.changed(session, owner_id)
            session.commit()
        return rows

    monkeypatch.setattr(clusters, "_unclustered_batch", edit_once)
    clusters.process_faces(db, owner.id)
    assert len(reads) == 2
    assert clusters.get_state(db, owner.id)["phase"] == "ready"


def test_pending_cluster_members_do_not_mask_new_imports(library):
    from app.service.tasks.face_cluster import count_unassigned_faces

    db, owner = library
    add_face(db, owner, 0)
    db.commit()
    clusters.process_faces(db, owner.id)
    assert count_unassigned_faces(db, owner.id) == 0
    add_face(db, owner, .02)
    db.commit()
    assert count_unassigned_faces(db, owner.id) == 1


def test_deleting_identity_invalidates_cluster_index(library):
    from app.crud.face import delete_identity

    db, owner = library
    first, second = [add_face(db, owner, angle) for angle in [0, .02]]
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    before = clusters.get_state(db, owner.id)["revision"]
    assert delete_identity(db, first.face_identity_id, owner.id)
    db.expire_all()
    cluster = db.get(FaceCluster, first.face_cluster_id)
    assert cluster.identity_id is None and cluster.status == "pending"
    assert first.face_identity_id is None and second.face_identity_id is None
    assert clusters.get_state(db, owner.id)["revision"] > before


def test_compaction_combines_singletons_before_minimum_photo_check(library):
    db, owner = library
    separate_cluster(db, owner, [0])
    separate_cluster(db, owner, [.02])
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    group = db.query(FaceCluster).one()
    assert group.face_count == 2 and group.identity_id is not None
    assert {face.face_cluster_id for face in db.query(Face).all()} == {group.id}
    assert np.allclose(group.vector_sum, np.asarray(vector(0)) + vector(.02))


def test_compaction_keeps_existing_people_separate(library):
    db, owner = library
    people = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name=name) for name in ["哥哥", "弟弟"]]
    db.add_all(people)
    db.flush()
    separate_cluster(db, owner, [0, .01], people[0].id)
    separate_cluster(db, owner, [.02, .03], people[1].id)
    db.commit()
    clusters.process_faces(db, owner.id)
    assert db.query(FaceCluster).count() == 2
    assert {group.identity_id for group in db.query(FaceCluster).all()} == {person.id for person in people}


def test_compaction_accepts_nearest_person_without_relative_margin(library):
    db, owner = library
    people = [FaceIdentity(id=uuid4(), owner_id=owner.id) for _ in range(2)]
    db.add_all(people)
    db.flush()
    separate_cluster(db, owner, [-.1, -.1], people[0].id)
    separate_cluster(db, owner, [.1, .1], people[1].id)
    singleton = separate_cluster(db, owner, [.01])
    singleton_face = db.get(Face, singleton.anchor_face_id)
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert db.query(FaceCluster).count() == 2
    assert singleton_face.face_identity_id == people[1].id


def test_compaction_checks_outlying_members_beyond_centers(library):
    db, owner = library
    separate_cluster(db, owner, [0, .65, -.65])
    separate_cluster(db, owner, [.02])
    db.commit()
    clusters.process_faces(db, owner.id)
    assert db.query(FaceCluster).count() == 2


def test_compaction_can_absorb_singleton_into_existing_person(library):
    db, owner = library
    person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="家人")
    db.add(person)
    db.flush()
    existing = separate_cluster(db, owner, [0], person.id)
    separate_cluster(db, owner, [.02, .03])
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert db.query(FaceCluster).one().id == existing.id
    assert existing.face_count == 3
    assert {face.face_identity_id for face in db.query(Face).all()} == {person.id}


def test_compaction_does_not_turn_nearby_chain_into_one_cluster(library):
    db, owner = library
    for angle in [0, .3, .6, .9]:
        separate_cluster(db, owner, [angle])
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    assert db.query(FaceCluster).count() >= 2
    for group in db.query(FaceCluster).all():
        anchor = clusters.unit(db.get(Face, group.anchor_face_id).face_feature)
        for face in db.query(Face).filter(Face.face_cluster_id == group.id).all():
            assert 1.0 - anchor @ clusters.unit(face.face_feature) < .15


def test_compaction_updates_native_index_with_many_fragment_clusters(library):
    db, owner = library
    for _ in range(260):
        separate_cluster(db, owner, [0])
    db.commit()
    clusters.process_faces(db, owner.id)
    db.expire_all()
    groups = db.query(FaceCluster).all()
    assert len(groups) < 10
    assert sum(group.face_count for group in groups) == 260
    assert all(db.get(FaceCluster, face.face_cluster_id) is not None for face in db.query(Face).all())


def test_compaction_rolls_back_members_and_statistics(library, monkeypatch):
    db, owner = library
    separate_cluster(db, owner, [0])
    separate_cluster(db, owner, [.02])
    db.commit()
    def fail_after_compaction(*args):
        assert db.query(FaceCluster).count() == 1
        raise RuntimeError("interrupted after compaction")
    monkeypatch.setattr(clusters, "_promote_clusters", fail_after_compaction)
    with pytest.raises(RuntimeError, match="interrupted after compaction"):
        clusters.process_faces(db, owner.id)
    db.rollback()
    assert db.query(FaceCluster).count() == 2
    assert all(group.face_count == 1 for group in db.query(FaceCluster).all())
    assert len({face.face_cluster_id for face in db.query(Face).all()}) == 2


def test_compaction_preserves_person_cover_and_different_appearance(legacy_database, monkeypatch):
    from alembic import command
    from sqlalchemy.orm import Session

    engine, config, _ = legacy_database
    command.upgrade(config, "head")
    settings = SimpleNamespace(ai=SimpleNamespace(face_cluster_threshold=.15, face_recognition_min_photos=2))
    monkeypatch.setattr(clusters.config_manager, "get_user_config", lambda *args: settings)
    with Session(engine, autoflush=False) as db:
        owner = User(id=uuid4(), username="compact-clusters", hashed_password="unused")
        db.add(owner)
        db.flush()
        person = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="孩子")
        db.add(person)
        db.flush()
        first = separate_cluster(db, owner, [0], person.id)
        second = separate_cluster(db, owner, [.02, .03], person.id)
        different = separate_cluster(db, owner, [1.2], person.id)
        person.default_face_id = first.anchor_face_id
        cover = person.default_face_id
        db.commit()
        clusters.process_faces(db, owner.id)
        db.expire_all()
        assert db.query(FaceCluster).count() == 2
        assert db.get(FaceCluster, first.id) is None
        assert second.face_count == 3
        assert different.face_count == 1
        assert person.identity_name == "孩子" and person.default_face_id == cover
        assert db.get(Face, cover).face_cluster_id == second.id
        assert np.allclose(second.vector_sum, np.asarray(vector(0)) + vector(.02) + vector(.03), atol=1e-6)


def test_representatives_use_center_support_beyond_first_sixteen_faces(library):
    db, owner = library
    group = separate_cluster(db, owner, [-1, 1] * 8 + [0, .01, .02])
    db.commit()
    samples = clusters._representative_samples(db, owner.id, group.id, group.center, {})
    assert len(samples) == 3
    assert np.all(1.0 - samples @ clusters.unit(vector(0)) < .001)


def test_unnamed_identity_merge_rejects_unsupported_members(library):
    db, owner = library
    people = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="未命名") for _ in range(2)]
    db.add_all(people)
    db.flush()
    separate_cluster(db, owner, [-.7, .7], people[0].id)
    separate_cluster(db, owner, [0, .01], people[1].id)
    db.commit()
    clusters.process_faces(db, owner.id)
    assert db.query(FaceIdentity).filter(FaceIdentity.is_deleted.is_(False)).count() == 2


@pytest.mark.parametrize("disabled_field", ["face_identity_merge_threshold", "face_identity_match_threshold"])
def test_zero_custom_distance_disables_unnamed_identity_merge(library, monkeypatch, disabled_field):
    from app.core.config_manager import AISettings

    db, owner = library
    config = SimpleNamespace(ai=AISettings(**{disabled_field:0}))
    monkeypatch.setattr(clusters.config_manager, "get_user_config", lambda *args: config)
    people = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="未命名") for _ in range(2)]
    db.add_all(people)
    db.flush()
    for person in people:
        separate_cluster(db, owner, [0, 0], person.id)
    db.commit()
    clusters.process_faces(db, owner.id)
    assert db.query(FaceIdentity).filter(FaceIdentity.is_deleted.is_(False)).count() == 2


def test_unnamed_identity_merge_preserves_clusters_and_named_people(legacy_database, monkeypatch):
    from alembic import command
    from sqlalchemy.orm import Session
    from app.core.config_manager import AISettings

    engine, migration, _ = legacy_database
    command.upgrade(migration, "head")
    config = SimpleNamespace(ai=AISettings())
    monkeypatch.setattr(clusters.config_manager, "get_user_config", lambda *args: config)
    with Session(engine, autoflush=False) as db:
        owner = User(id=uuid4(), username="unnamed-merge", hashed_password="unused")
        db.add(owner)
        db.flush()
        people = [FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name=name)
                  for name in ["未命名", "未命名", "用户命名"]]
        db.add_all(people)
        db.flush()
        first = separate_cluster(db, owner, [0, .01, .02], people[0].id)
        second = separate_cluster(db, owner, [.05, .06], people[1].id)
        named = separate_cluster(db, owner, [.03, .04], people[2].id)
        centers = {group.id:list(group.center) for group in [first, second, named]}
        people[0].default_face_id = first.anchor_face_id
        cover = people[0].default_face_id
        db.commit()
        clusters.process_faces(db, owner.id)
        db.expire_all()
        assert people[1].is_deleted
        assert not people[0].is_deleted and not people[2].is_deleted
        assert first.identity_id == second.identity_id == people[0].id
        assert named.identity_id == people[2].id
        assert people[0].default_face_id == cover
        assert db.query(FaceCluster).count() == 3
        for group in db.query(FaceCluster).all():
            assert np.allclose(group.center, centers[group.id])
