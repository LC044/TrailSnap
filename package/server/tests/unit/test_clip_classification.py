"""Editable CLIP classification: scoring, independent tags and continuations."""

import asyncio
from uuid import uuid4
from types import SimpleNamespace
import numpy as np
import pytest
from app.service import clip_classification as svc
from app.db.models import User, Photo
from app.db.models.photo import FileType
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.clip_classification import (
    ClipCategory,
    ClipRuleRevision,
    TagDecision,
)
from app.db.models.task import Task, TaskType
from app.db.models.image_vector import ImageVector
from app.api.clip_classification import RuleInput, save_rule

pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def seed(db):
    user = User(username=str(uuid4()))
    db.add(user)
    db.flush()
    photo = Photo(
        owner_id=user.id,
        filename="test.jpg",
        file_path="test.jpg",
        file_type=FileType.image,
    )
    tag = PhotoTag(owner_id=user.id, tag_name="露营", type="clip")
    db.add_all([photo, tag])
    db.flush()
    cat = ClipCategory(
        owner_id=user.id,
        tag_id=tag.id,
        groups=["活动 / 事件"],
        enabled=True,
        revision=1,
    )
    db.add(cat)
    db.flush()
    db.add(
        ClipRuleRevision(
            category_id=cat.id,
            revision=1,
            descriptions=["露营照片"],
            strictness="standard",
            thresholds={"test": 0.5},
        )
    )
    db.commit()
    return user, photo, tag, cat


def test_prototype_normalizes_each_description_before_average():
    actual = svc.prototype([[100, 0], [0, 1]])
    assert np.allclose(actual, [2**-0.5, 2**-0.5])
    with pytest.raises(ValueError):
        svc.prototype([[0, 0]])


@pytest.mark.parametrize(
    "strictness, adjustment",
    [("relaxed", -0.025), ("standard", 0), ("strict", 0.025)],
)
@pytest.mark.parametrize(
    "thresholds, base",
    [({}, 0.42), ({"other": 0.8}, 0.42), ({"test": 0.0}, 0.0), ({"test": 0.6}, 0.6)],
)
def test_threshold_uses_model_override_or_default(strictness, adjustment, thresholds, base):
    rule = SimpleNamespace(thresholds=thresholds, strictness=strictness)
    assert svc.threshold_for(rule, "test") == pytest.approx(base + adjustment)


def test_catalog_complete_and_single_membership():
    data = svc.load_catalog()
    assert len(data["groups"]) == 11
    assert data["version"] == 2
    assert len(data["categories"]) == 173
    cats = {c["name"]: c for c in data["categories"]}
    assert len(cats) == len(data["categories"])
    assert len({c["key"] for c in cats.values()}) == len(cats)
    assert all(len(c["groups"]) == 1 for c in cats.values())
    assert all(c["groups"][0] in data["groups"] for c in cats.values())
    assert cats["机场"]["groups"] == cats["站台"]["groups"] == ["交通出行"]
    assert "桥梁道路" not in cats and "网络海报" not in cats
    assert "海洋 / 海面" in cats and "雪景" in cats
    assert all(1 <= len(c["descriptions"]) <= 5 for c in cats.values())


def test_clip_rebuild_preserves_independent_yolo_and_manual_decision(face_sqlite_session):
    db = face_sqlite_session
    user, photo, tag, cat = seed(db)
    yolo = PhotoTag(owner_id=user.id, tag_name=tag.tag_name, type="yolo")
    db.add(yolo)
    db.flush()
    db.add(PhotoTagRelation(photo_id=photo.id, tag_id=yolo.id, confidence=0.9))
    db.commit()
    assert svc.apply_results(db, photo, [(cat, 1, 0.8, 0.5)])
    db.commit()
    assert db.query(PhotoTagRelation).count() == 2
    svc.apply_results(db, photo, [(cat, 1, 0.2, 0.5)])
    db.commit()
    assert db.query(PhotoTagRelation).one().tag_id == yolo.id
    svc.decide_tag(db, photo.id, tag.id, False)
    db.commit()
    svc.apply_results(db, photo, [(cat, 1, 0.9, 0.5)])
    db.commit()
    assert db.query(PhotoTagRelation).one().tag_id == yolo.id
    assert db.get(TagDecision, (photo.id, tag.id)).keep is False
    svc.decide_tag(db, photo.id, tag.id, True)
    db.commit()
    svc.apply_results(db, photo, [(cat, 1, 0.2, 0.5)])
    db.commit()
    assert db.query(PhotoTagRelation).filter_by(tag_id=tag.id).one().confidence == 1.0


def test_unmatched_has_no_association_and_stale_revision_cannot_publish(face_sqlite_session):
    db = face_sqlite_session
    _, photo, tag, cat = seed(db)
    assert svc.apply_results(db, photo, [(cat, 1, 0.2, 0.5)]) == 0
    db.commit()
    assert db.query(PhotoTagRelation).count() == 0
    cat.revision = 2
    db.commit()
    assert not svc.apply_results(db, photo, [(cat, 1, 0.9, 0.5)])
    assert db.query(PhotoTagRelation).count() == 0


def test_owner_isolation_and_name_edit_keeps_revision(face_sqlite_session):
    db = face_sqlite_session
    user, _, tag, cat = seed(db)
    with pytest.raises(ValueError):
        svc.owned_category(db, uuid4(), cat.id)
    payload = RuleInput(
        name="户外露营",
        descriptions=["露营照片"],
        groups=cat.groups,
        thresholds={"test": 0.5},
        revision=1,
        enabled=True,
    )
    result = save_rule(db, user, payload, cat.id)
    assert result.code == 0
    assert result.data["revision"] == 1 and result.data["tag_id"] == str(tag.id)
    payload.descriptions = ["草地上的帐篷"]
    assert save_rule(db, user, payload, cat.id).data["revision"] == 2
    assert save_rule(db, user, payload, cat.id).code == 409


def test_missing_vector_defers_without_waiting(face_sqlite_session, monkeypatch):
    from app.service.tasks.clip_classification import ClipClassificationStrategy

    db = face_sqlite_session
    user, photo, _, cat = seed(db)
    monkeypatch.setattr(svc, "ai_url", lambda *args: "test")
    monkeypatch.setattr(svc, "selected_embedding_model", lambda *args: "test")
    task = Task(
        type=TaskType.CLASSIFY_IMAGE_CLIP,
        owner_id=user.id,
        payload={"photo_id": str(photo.id), "revisions": {str(cat.id): 1}, "model": "test"},
    )
    db.add(task)
    db.commit()
    result = asyncio.run(ClipClassificationStrategy().process(None, task, db))
    assert result["status"] == "deferred"
    assert db.query(Task).filter_by(type=TaskType.IMAGE_EMBEDDING).count() == 1


@pytest.mark.parametrize(
    "thresholds, base",
    [({"test": 0.5}, 0.5), ({"other": 0.9}, 0.42), ({}, 0.42), ({"test": 0}, 0)],
)
def test_preview_has_no_writes_and_filters_other_models(
    face_sqlite_session, monkeypatch, thresholds, base
):
    db = face_sqlite_session
    user, photo, _, _ = seed(db)
    db.add(
        ImageVector(photo_id=photo.id, embedding=[1.0] + [0.0] * 511, model_name="old")
    )
    db.commit()
    monkeypatch.setattr(svc, "ai_url", lambda *args: "test")
    monkeypatch.setattr(svc, "selected_embedding_model", lambda *args: "test")
    monkeypatch.setattr(
        svc, "category_vector", lambda *args: np.array([1.0] + [0.0] * 511)
    )
    result = svc.preview(db, user.id, ["露营照片"], "strict", thresholds)
    assert result["threshold"] == pytest.approx(base + 0.025)
    assert result["checked"] == 0 and result["missing"] == 1
    assert not db.new and not db.dirty


def test_text_response_must_use_requested_model(monkeypatch):
    monkeypatch.setattr(
        svc.requests,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None, headers={}, json=lambda: [[1, 0]]
        ),
    )
    with pytest.raises(ValueError, match="身份"):
        svc.category_vector("test", "model", ["unique"])


def test_batched_publication_preserves_manual_rejection_and_stale_rules(
    face_sqlite_session,
):
    db = face_sqlite_session
    _, photo, tag, cat = seed(db)
    db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=0.9))
    db.commit()
    assert svc.apply_results(db, photo, [(cat, 1, 0.8, 0.5)]) == 1
    db.commit()
    svc.apply_results(db, photo, [(cat, 1, 0.2, 0.5)])
    db.commit()
    assert db.query(PhotoTagRelation).count() == 0
    svc.decide_tag(db, photo.id, tag.id, False)
    db.commit()
    svc.apply_results(db, photo, [(cat, 1, 0.9, 0.5)])
    db.commit()
    assert db.query(PhotoTagRelation).count() == 0
    cat.revision = 2
    db.commit()
    assert svc.apply_results(db, photo, [(cat, 1, 0.9, 0.5)]) == 0
    assert db.query(PhotoTagRelation).count() == 0


def test_bulk_enable_validates_all_owners_before_writing(face_sqlite_session):
    from app.api.clip_classification import EnableInput, enable_categories

    db = face_sqlite_session
    user, _, _, cat = seed(db)
    stranger, _, _, foreign = seed(db)
    result = enable_categories(
        EnableInput(category_ids=[cat.id, foreign.id], enabled=False), db, user
    )
    assert result.code == 400
    db.refresh(cat)
    assert cat.enabled
    result = enable_categories(
        EnableInput(category_ids=[cat.id], enabled=False), db, user
    )
    assert result.code == 0 and not cat.enabled


def test_pending_photo_jobs_merge_latest_rules(face_sqlite_session):
    db = face_sqlite_session
    _, photo, _, cat = seed(db)
    assert svc.enqueue_photo(db, photo)
    db.commit()
    cat.revision = 2
    db.commit()
    assert svc.enqueue_photo(db, photo) is None
    db.commit()
    task = db.query(Task).one()
    assert task.payload["revisions"][str(cat.id)] == 2


def test_existing_embedding_job_is_forced_for_missing_vector(
    face_sqlite_session, monkeypatch
):
    from app.service.tasks.clip_classification import ClipClassificationStrategy

    db = face_sqlite_session
    user, photo, _, cat = seed(db)
    photo.processed_tasks = {"image_embedding": True}
    pending = Task(
        type=TaskType.IMAGE_EMBEDDING,
        owner_id=user.id,
        payload={"photo_id": str(photo.id)},
    )
    db.add(pending)
    db.commit()
    monkeypatch.setattr(svc, "ai_url", lambda *a: "test")
    monkeypatch.setattr(svc, "selected_embedding_model", lambda *a: "test")
    task = SimpleNamespace(
        owner_id=user.id,
        payload={"photo_id": str(photo.id), "revisions": {str(cat.id): 1}, "model": "test"},
    )
    result = asyncio.run(ClipClassificationStrategy().process(None, task, db))
    assert result["status"] == "deferred"
    assert pending.payload["force"] is True and pending.payload["model"] == "test"
    assert db.query(Task).count() == 1


def test_sqlite_migration_round_trip_and_uuid_storage(face_sqlite_session):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text, inspect

    db = face_sqlite_session
    user, photo, _, _ = seed(db)
    user_id, photo_id = user.id, photo.id
    db.close()
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic_sqlite/versions/clip_sqlite_0025_editable_clip_classification.py"
    )
    spec = importlib.util.spec_from_file_location("clip_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with db.bind.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
            migration.upgrade()
            assert "clip_photo_results" not in inspect(conn).get_table_names()
    _, _, _, cat = seed(db)
    stored = db.execute(text("select id from clip_categories")).scalar()
    assert stored == str(cat.id) and len(stored) == 36
    assert db.get(User, user_id) is not None and db.get(Photo, photo_id) is not None


def test_batched_rebuild_removes_unmatched_legacy_clip_relation(face_sqlite_session):
    db = face_sqlite_session
    _, photo, tag, cat = seed(db)
    tag.type = "clip"
    db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=0.8))
    db.commit()
    assert svc.apply_results(db, photo, [(cat, 1, 0.2, 0.5)]) == 0
    db.commit()
    assert db.query(PhotoTagRelation).count() == 0


def test_edited_preset_does_not_claim_original_calibration(face_sqlite_session):
    db = face_sqlite_session
    user, _, _, cat = seed(db)
    preset = svc.load_catalog()["categories"][0]
    cat.preset_key = preset["key"]
    rule = db.get(ClipRuleRevision, (cat.id, 1))
    rule.descriptions = preset["descriptions"]
    rule.thresholds = preset["thresholds"]
    db.commit()
    assert svc.serialize_category(db, cat)["calibration"] == preset["calibration"]
    rule.descriptions = ["another rule"]
    db.commit()
    assert svc.serialize_category(db, cat)["calibration"]["status"] == "custom"


def test_same_name_model_and_custom_tags_have_independent_ids(face_sqlite_session):
    from app.service.tasks.classification import get_tag_id
    from app.crud.tag import add_tag_to_photo

    db = face_sqlite_session
    user, photo, clip, _ = seed(db)
    yolo_id = get_tag_id(db, clip.tag_name, user.id)
    db.commit()
    custom = add_tag_to_photo(db, photo.id, clip.tag_name, owner_id=user.id)
    assert len({str(clip.id), yolo_id, str(custom.id)}) == 3
    assert svc.get_tag(db, user.id, clip.tag_name).id == clip.id
    assert get_tag_id(db, clip.tag_name, user.id) == yolo_id


def test_same_name_id_scopes_browse_remove_cover_and_delete(face_sqlite_session):
    from app.crud import tag as crud
    from app.api.clip_classification import delete_category

    db = face_sqlite_session
    user, photo, clip, cat = seed(db)
    yolo = PhotoTag(owner_id=user.id, tag_name=clip.tag_name, type="yolo")
    db.add(yolo)
    db.flush()
    for tag in (clip, yolo):
        db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=0.9))
    db.commit()
    assert crud.get_photos_by_tag_name(db, user.id, clip.tag_name, tag_id=clip.id) == [photo]
    assert crud.get_photos_by_tag_name(db, uuid4(), clip.tag_name, tag_id=clip.id) == []
    assert crud.set_tag_cover(db, user.id, clip.tag_name, photo.id, tag_id=clip.id)
    assert clip.cover_id == photo.id and yolo.cover_id is None
    assert crud.remove_photos_from_tag(db, user.id, clip.tag_name, [photo.id], tag_id=clip.id) == 1
    assert db.query(PhotoTagRelation).one().tag_id == yolo.id
    svc.decide_tag(db, photo.id, clip.id, True)
    db.commit()
    assert delete_category(cat.id, db, user).code == 0
    assert db.query(PhotoTagRelation).one().tag_id == yolo.id
    assert clip.is_deleted and not yolo.is_deleted
    assert svc.get_tag(db, user.id, clip.tag_name).id != clip.id


def test_clip_name_can_equal_yolo_and_rename_without_affecting_yolo(face_sqlite_session):
    db = face_sqlite_session
    user, _, clip, cat = seed(db)
    yolo = PhotoTag(owner_id=user.id, tag_name="野餐", type="yolo")
    db.add(yolo)
    db.commit()
    result = save_rule(db, user, RuleInput(
        name=yolo.tag_name, descriptions=["露营照片"], groups=cat.groups,
        thresholds={"test": 0.5}, revision=1, enabled=True,
    ), cat.id)
    assert result.code == 0 and clip.id != yolo.id
    assert clip.type == "clip" and yolo.type == "yolo"


def test_yolo_rebuild_only_replaces_its_own_tag_ids(face_sqlite_session):
    from app.service.tasks.classification import ClassifyImageStrategy

    db = face_sqlite_session
    user, photo, clip, cat = seed(db)
    svc.apply_results(db, photo, [(cat, 1, 0.8, 0.5)])
    db.commit()
    task = SimpleNamespace(id=uuid4(), type=TaskType.CLASSIFY_IMAGE)
    strategy = ClassifyImageStrategy()
    prediction = [{"status": "success", "predictions": [{"label": clip.tag_name, "confidence": 0.9}]}]
    asyncio.run(strategy._process_ai_results([task], [photo], prediction, [str(photo.id)], db))
    yolo = db.query(PhotoTag).filter_by(owner_id=user.id, type="yolo").one()
    assert yolo.id != clip.id and db.query(PhotoTagRelation).count() == 2
    asyncio.run(strategy._process_ai_results([task], [photo], [], [str(photo.id)], db))
    assert db.query(PhotoTagRelation).one().tag_id == clip.id
    svc.decide_tag(db, photo.id, yolo.id, False)
    db.commit()
    asyncio.run(strategy._process_ai_results([task], [photo], prediction, [str(photo.id)], db))
    assert db.query(PhotoTagRelation).one().tag_id == clip.id
    svc.decide_tag(db, photo.id, yolo.id, True)
    db.commit()
    asyncio.run(strategy._process_ai_results([task], [photo], [], [str(photo.id)], db))
    assert db.query(PhotoTagRelation).filter_by(tag_id=yolo.id).one().confidence == 1.0


def test_clip_creation_does_not_reuse_same_name_yolo(face_sqlite_session):
    db = face_sqlite_session
    user, _, _, _ = seed(db)
    yolo = PhotoTag(owner_id=user.id, tag_name="机场", type="yolo")
    db.add(yolo)
    db.flush()
    clip = svc.get_tag(db, user.id, yolo.tag_name)
    assert clip.id != yolo.id and clip.type == "clip"


def test_photo_tasks_recompute_and_rule_edits_update_associations(face_sqlite_session, monkeypatch):
    from app.service.tasks.clip_classification import ClipClassificationStrategy

    db = face_sqlite_session
    user, photo, tag, cat = seed(db)
    photo.processed_tasks = {"image_embedding": True}
    db.add(ImageVector(photo_id=photo.id, embedding=[1.0] + [0.0] * 511, model_name="test"))
    db.commit()
    monkeypatch.setattr(svc, "ai_url", lambda *args: "test")
    monkeypatch.setattr(svc, "selected_embedding_model", lambda *args: "test")
    calls = []

    def vectors(*args):
        calls.append(args[-1])
        return [np.array([0.8, 0.6] + [0.0] * 510)]

    monkeypatch.setattr(svc, "category_vectors", vectors)
    monkeypatch.setattr(svc.requests, "get", lambda *args, **kwargs: pytest.fail("photo tasks must not query model identity"))
    task = SimpleNamespace(owner_id=user.id, payload={
        "photo_id": str(photo.id), "revisions": {str(cat.id): 1}, "model": "test",
    })
    strategy = ClipClassificationStrategy()
    for _ in range(2):
        result = asyncio.run(strategy.process(None, task, db))
        assert result["rules_checked"] == result["tags_found"] == 1
        assert db.query(PhotoTagRelation).one().tag_id == tag.id
    assert len(calls) == 2
    draft = RuleInput(name=tag.tag_name, descriptions=["露营照片"], groups=cat.groups,
                      thresholds={"test": 0.9}, revision=1, enabled=True)
    assert save_rule(db, user, draft, cat.id).data["revision"] == 2
    assert asyncio.run(strategy.process(None, task, db))["status"] == "skipped"
    task.payload["revisions"] = {str(cat.id): 2}
    result = asyncio.run(strategy.process(None, task, db))
    assert result["rules_checked"] == 1 and result["tags_found"] == 0
    assert db.query(PhotoTagRelation).count() == 0
    draft.thresholds, draft.revision = {"test": 0.5}, 2
    assert save_rule(db, user, draft, cat.id).data["revision"] == 3
    task.payload["revisions"] = {str(cat.id): 3}
    assert asyncio.run(strategy.process(None, task, db))["tags_found"] == 1
    assert db.query(PhotoTagRelation).count() == 1
    svc.decide_tag(db, photo.id, tag.id, False)
    db.commit()
    assert asyncio.run(strategy.process(None, task, db))["rules_checked"] == 1
    assert db.query(PhotoTagRelation).count() == 0
    assert photo.processed_tasks == {"image_embedding": True}


def test_history_generator_yields_between_pages_and_merges_pending(face_sqlite_session, monkeypatch):
    from app.service.tasks.clip_classification import ClipClassificationStrategy
    from app.db.models.task import TaskStatus, DEFAULT_PRIORITIES

    db = face_sqlite_session
    db.connection().exec_driver_sql('PRAGMA temp_store=MEMORY')
    db.connection().exec_driver_sql('PRAGMA cache_size=-64000')
    user, photo, _, cat = seed(db)
    for _ in range(1024):
        db.add(Photo(owner_id=user.id, filename="test.jpg", file_path="test.jpg", file_type=FileType.image))
    db.commit()
    first_id = db.query(Photo.id).order_by(Photo.id).first().id
    existing = Task(type=TaskType.CLASSIFY_IMAGE_CLIP, owner_id=user.id,
                    payload={"photo_id": str(first_id), "revisions": {str(cat.id): 0}},
                    status=TaskStatus.PENDING)
    db.add(existing)
    db.commit()
    strategy = ClipClassificationStrategy()
    monkeypatch.setattr(svc, "selected_embedding_model", lambda *args: "test")
    result = asyncio.run(strategy.process(None, SimpleNamespace(owner_id=user.id, payload={}), db))
    assert result == {"generated_tasks": 1023, "photos_checked": 1024}
    assert existing.payload["revisions"][str(cat.id)] == 1
    continuation = db.query(Task).filter(Task.photo_id.is_(None)).one()
    assert continuation.priority < DEFAULT_PRIORITIES[TaskType.CLASSIFY_IMAGE_CLIP]
    assert asyncio.run(strategy.process(None, continuation, db))["generated_tasks"] == 1
    assert db.query(Task).filter(Task.photo_id.is_not(None)).count() == 1025


def test_description_cache_is_scoped_by_model_without_identity_requests(monkeypatch):
    calls = []
    def encode(url, json, **kwargs):
        calls.append(json["model"])
        return SimpleNamespace(raise_for_status=lambda: None,
                               headers={"X-Embedding-Model": json["model"]},
                               json=lambda: [[1.0, 0.0]])
    monkeypatch.setattr(svc.requests, "post", encode)
    monkeypatch.setattr(svc.requests, "get", lambda *args, **kwargs: pytest.fail("unexpected model identity request"))
    url = str(uuid4())
    for model in ("first", "first", "second"):
        svc.category_vectors(url, model, [["same description"]])
    assert calls == ["first", "second"]
    from app.service.ai_model_state import DEPENDENCIES
    assert DEPENDENCIES[TaskType.CLASSIFY_IMAGE_CLIP] == ("embedding",)

def test_large_batch_scores_once_and_honors_manual_decisions(face_sqlite_session, monkeypatch):
    from app.service.tasks.clip_classification import ClipClassificationStrategy
    db = face_sqlite_session
    user, photo, tag, cat = seed(db)
    other = Photo(owner_id=user.id, filename='other.jpg', file_path='other.jpg', file_type=FileType.image)
    db.add(other)
    db.flush()
    positive = [1.0] + [0.0] * 511
    for item in (photo, other):
        db.add(ImageVector(photo_id=item.id, model_name='test', embedding=positive))
    db.add(TagDecision(photo_id=photo.id, tag_id=tag.id, keep=False))
    db.commit()
    calls = []
    monkeypatch.setattr(svc, 'ai_url', lambda *a: 'test')
    monkeypatch.setattr(svc, 'category_vectors', lambda *a: calls.append(a) or [np.asarray(positive)])
    tasks = [Task(id=uuid4(), type=TaskType.CLASSIFY_IMAGE_CLIP, owner_id=user.id,
                  payload={'photo_id': str(p.id), 'revisions': {str(cat.id): 1}, 'model': 'test'})
             for p in (photo, other)]
    result = asyncio.run(ClipClassificationStrategy().process_batch(None, tasks, db))
    assert all(r['status'] == 'completed' for r in result), result
    assert len(calls) == 1
    assert db.query(PhotoTagRelation).one().photo_id == other.id
    result = asyncio.run(ClipClassificationStrategy().process_batch(None, tasks, db))
    assert all(r['status'] == 'completed' for r in result), result
    assert db.query(PhotoTagRelation).count() == 1
    monkeypatch.setattr(svc, 'category_vectors', lambda *a: [np.asarray(positive) * 0.75])
    result = asyncio.run(ClipClassificationStrategy().process_batch(None, tasks, db))
    assert all(r['status'] == 'completed' for r in result), result
    db.expire_all()
    assert db.query(PhotoTagRelation).one().confidence == pytest.approx(0.75)
    monkeypatch.setattr(svc, 'category_vectors', lambda *a: [-np.asarray(positive)])
    asyncio.run(ClipClassificationStrategy().process_batch(None, tasks, db))
    assert db.query(PhotoTagRelation).count() == 0


def test_new_enabled_category_automatically_queues_only_it(face_sqlite_session, monkeypatch):
    from app.api import clip_classification as api
    db = face_sqlite_session
    user, _, _, _ = seed(db)
    queued = []
    monkeypatch.setattr(api, 'queue_rebuild', lambda db, user, ids: queued.append(ids) or 'task')
    response = save_rule(db, user, RuleInput(name='new', descriptions=['new photo'],
                         thresholds={'test': 0.5}, enabled=True))
    assert response.code == 0 and response.data['task_id'] == 'task'
    assert [str(c) for c in queued[0]] == [response.data['id']]


def test_classification_task_visible_after_embedding(face_sqlite_session):
    from app.crud.task import get_grouped_status
    from app.service.task_worker import get_chunk_size
    groups = get_grouped_status(face_sqlite_session, set())
    types = [g['category'] for g in groups]
    assert types.index(TaskType.CLASSIFY_IMAGE_CLIP) == types.index(TaskType.IMAGE_EMBEDDING) + 1
    assert get_chunk_size(TaskType.CLASSIFY_IMAGE_CLIP) == 256
