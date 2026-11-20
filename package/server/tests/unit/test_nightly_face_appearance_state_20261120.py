"""Cluster state keys and the visible-photo predicate."""
from uuid import uuid4

import pytest

from app.service.face_appearance_clusters import _visible_photo, state_key

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def test_state_key_is_scoped_per_owner():
    owner = uuid4()
    assert state_key(owner) == f"face_cluster_state:{owner}"


def test_state_key_differs_between_owners():
    assert state_key(uuid4()) != state_key(uuid4())


def test_visible_photo_predicate_filters_on_the_owner():
    sql = str(_visible_photo(uuid4()))
    assert "owner_id" in sql
    assert "is_deleted" in sql
    assert "photos.id" in sql
