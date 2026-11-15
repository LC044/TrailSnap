"""Reference snapshots use the same normalized prototype in previews and workers."""
import asyncio
import base64
import importlib.util
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from app.api.clip_classification import RuleInput, save_rule, categories
from app.db.models import User, Photo
from app.db.models.clip_classification import ClipRuleRevision
from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType
from app.db.models.tag import PhotoTagRelation
from app.db.models.task import Task, TaskType
from app.service import clip_classification as svc
from app.service.tasks.clip_classification import ClipClassificationStrategy

pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def snapshot(color="red", size=(12, 8)):
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()


def test_rule_accepts_images_only_and_rejects_invalid_snapshots():
    image = snapshot()
    assert RuleInput(name="测试", reference_images=[image], thresholds={"test": .5}).descriptions == []
    invalid = [[], ["https://example.com/image.jpg"], ["data:image/jpeg;base64,invalid"],
               [snapshot(size=(1025, 1))], [image] * 6,
               ["data:image/jpeg;base64," + "A" * 700_000]]
    for images in invalid:
        with pytest.raises(ValidationError):
            RuleInput(name="测试", reference_images=images, thresholds={"test": .5})
    with pytest.raises(ValidationError):
        RuleInput(name="测试", descriptions=[" "], reference_images=[image], thresholds={"test": .5})


def mock_encoder(monkeypatch, dimension=2):
    calls = []
    def post(url, json, **kwargs):
        calls.append((url, json))
        axis = 0 if url.endswith("/text") else 1
        vectors = []
        for _ in json.get("texts", json.get("images", [])):
            v = [0.] * dimension
            v[axis] = 100. if axis == 0 else 1.
            vectors.append(v)
        return SimpleNamespace(raise_for_status=lambda: None,
                               headers={"X-Embedding-Model": json["model"]}, json=lambda: vectors)
    monkeypatch.setattr(svc.requests, "post", post)
    return calls


def test_every_text_and_image_has_equal_weight_and_cache_is_model_and_image_scoped(monkeypatch):
    calls = mock_encoder(monkeypatch)
    url = str(uuid4())
    image = snapshot()
    vector = svc.category_vector(url, "test", ["one", "two"], [image])
    assert np.allclose(vector, np.array([2., 1.]) / np.sqrt(5))
    assert len(calls) == 2
    assert calls[1][1]["images"] == [image.split(",", 1)[1]]
    vector[0] = 0
    assert svc.category_vector(url, "test", ["one", "two"], [image])[0] > .8
    assert len(calls) == 2
    svc.category_vector(url, "other", ["one", "two"], [image])
    svc.category_vector(url, "test", ["one", "two"], [snapshot("blue")])
    assert len(calls) == 6
    assert np.allclose(svc.category_vector(url, "test", [], [image, snapshot("blue")]), [0, 1])


@pytest.mark.parametrize("headers, vectors", [({}, [[0, 1]]), ({"X-Embedding-Model": "wrong"}, [[0, 1]]),
                                                  ({"X-Embedding-Model": "test"}, []),
                                                  ({"X-Embedding-Model": "test"}, [[float("nan"), 1]])])
def test_image_encoding_rejects_unverified_model_or_invalid_vectors(monkeypatch, headers, vectors):
    monkeypatch.setattr(svc.requests, "post", lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, headers=headers, json=lambda: vectors))
    with pytest.raises(ValueError):
        svc.category_vector(str(uuid4()), "test", [], [snapshot()])


def test_images_and_new_groups_persist_with_revision_and_owner_isolation(face_sqlite_session):
    db = face_sqlite_session
    owner, other = User(username=str(uuid4())), User(username=str(uuid4()))
    db.add_all([owner, other]); db.commit()
    image = snapshot()
    draft = RuleInput(name="参考分类", reference_images=[image], groups=["新建分组"], thresholds={"test": .5})
    result = save_rule(db, owner, draft)
    assert result.code == 0
    category_id = result.data["id"]
    assert result.data["reference_images"] == [image]
    from uuid import UUID
    draft.revision = 1
    draft.reference_images = [snapshot("blue")]
    updated = save_rule(db, owner, draft, UUID(category_id))
    assert updated.data["revision"] == 2
    assert db.get(ClipRuleRevision, (UUID(category_id), 1)).reference_images == [image]
    assert "新建分组" in categories(db, owner).data["groups"]
    assert "新建分组" not in categories(db, other).data["groups"]
    assert save_rule(db, other, draft, UUID(category_id)).code != 0


@pytest.mark.parametrize("texts", [[], ["one", "two"]])
def test_preview_and_single_and_batch_workers_share_image_prototype(face_sqlite_session, monkeypatch, texts):
    db = face_sqlite_session
    owner = User(username=str(uuid4())); db.add(owner); db.commit()
    image = snapshot()
    draft = RuleInput(name="参考分类", descriptions=texts, reference_images=[image], thresholds={"test": .3})
    result = save_rule(db, owner, draft)
    from uuid import UUID
    cid, tag_id = UUID(result.data["id"]), UUID(result.data["tag_id"])
    # Enable directly to avoid scheduling background work in this isolated test.
    svc.owned_category(db, owner.id, cid).enabled = True
    photo = Photo(owner_id=owner.id, filename="test.jpg", file_path="test.jpg", file_type=FileType.image)
    db.add(photo); db.flush()
    db.add(ImageVector(photo_id=photo.id, embedding=[0., 1.] + [0.] * 510, model_name="test")); db.commit()
    mock_encoder(monkeypatch, 512)
    monkeypatch.setattr(svc, "ai_url", lambda *a: str(owner.id))
    monkeypatch.setattr(svc, "selected_embedding_model", lambda *a: "test")
    preview = svc.preview(db, owner.id, texts, "standard", draft.thresholds, reference_images=[image])
    expected = 1. / np.sqrt(len(texts)**2 + 1)
    assert preview["matches"][0]["score"] == pytest.approx(expected)
    task = Task(id=uuid4(), type=TaskType.CLASSIFY_IMAGE_CLIP, owner_id=owner.id,
                payload={"photo_id": str(photo.id), "revisions": {str(cid): 1}, "model": "test"})
    strategy = ClipClassificationStrategy()
    assert asyncio.run(strategy.process(None, task, db))["tags_found"] == 1
    assert db.query(PhotoTagRelation).filter_by(tag_id=tag_id).one().confidence == pytest.approx(expected)
    batch = asyncio.run(strategy.process_batch(None, [task], db))
    assert batch[0]["status"] == "completed"
    assert db.query(PhotoTagRelation).filter_by(tag_id=tag_id).one().confidence == pytest.approx(expected)


def migration(folder, revision):
    path = Path(__file__).resolve().parents[2] / folder / "versions" / f"{revision}_clip_reference_images.py"
    spec = importlib.util.spec_from_file_location(revision, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_reference_image_migration_preserves_old_sqlite_rules_and_downgrades():
    engine = create_engine("sqlite://")
    module = migration("alembic_sqlite", "clip_sqlite_0026")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE clip_rule_revisions (category_id TEXT, revision INTEGER, descriptions JSON)")
        connection.exec_driver_sql("INSERT INTO clip_rule_revisions VALUES ('old', 1, '[\"text\"]')")
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert connection.exec_driver_sql("SELECT reference_images FROM clip_rule_revisions").scalar() == "[]"
        module.downgrade()
        assert connection.exec_driver_sql("SELECT descriptions FROM clip_rule_revisions").scalar() == '["text"]'
    engine.dispose()


def test_postgres_reference_migration_compiles_without_database_access():
    output = StringIO()
    module = migration("alembic", "clip_pg_0026")
    module.op = Operations(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}))
    module.upgrade(); module.downgrade()
    assert "ADD COLUMN reference_images JSON DEFAULT '[]' NOT NULL" in output.getvalue()
    assert "DROP COLUMN reference_images" in output.getvalue()
