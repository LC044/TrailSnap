"""Scene visibility and visual-similarity helpers for time comparison."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models
from app.db.base import Base
from app.db.models import User
from app.db.models.scene import Scene
from app.crud import location as location_crud

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'scenes.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def test_visible_scene_returns_a_scene_owned_by_the_requesting_user(db):
    owner = User(id=uuid4(), username="owner", hashed_password="unused")
    db.add(owner)
    db.commit()
    scene = Scene(id=uuid4(), name="mine", owner_id=owner.id)
    db.add(scene)
    db.commit()
    assert location_crud._visible_scene(db, owner.id, scene.id) is scene


def test_visible_scene_hides_another_users_scene(db):
    owner = User(id=uuid4(), username="owner", hashed_password="unused")
    other = User(id=uuid4(), username="other", hashed_password="unused")
    db.add_all([owner, other])
    db.commit()
    scene = Scene(id=uuid4(), name="theirs", owner_id=other.id)
    db.add(scene)
    db.commit()
    assert location_crud._visible_scene(db, owner.id, scene.id) is None


def test_visible_scene_exposes_the_global_scene(db):
    scene = Scene(id=uuid4(), name="global", owner_id=None)
    db.add(scene)
    db.commit()
    assert location_crud._visible_scene(db, uuid4(), scene.id) is scene


def test_pair_visual_similarity_needs_both_photos():
    assert location_crud._pair_visual_similarity(None, None, SimpleNamespace(id=1)) is None
    assert location_crud._pair_visual_similarity(None, SimpleNamespace(id=1), None) is None


def test_pair_visual_similarity_returns_the_cosine_of_the_embeddings(monkeypatch):
    monkeypatch.setattr(
        location_crud, "_embedding_map",
        lambda db, ids: {ids[0]: [1.0, 0.0], ids[1]: [1.0, 0.0]},
    )
    left = SimpleNamespace(id=1)
    right = SimpleNamespace(id=2)
    assert location_crud._pair_visual_similarity(None, left, right) == pytest.approx(1.0)


def test_pair_visual_similarity_returns_none_without_embeddings(monkeypatch):
    monkeypatch.setattr(location_crud, "_embedding_map", lambda db, ids: {})
    assert location_crud._pair_visual_similarity(None, SimpleNamespace(id=1), SimpleNamespace(id=2)) is None
