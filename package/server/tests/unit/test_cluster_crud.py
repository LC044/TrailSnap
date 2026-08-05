from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.crud import cluster


pytestmark = pytest.mark.smoke


def test_remove_photo_from_clusters_is_noop_when_unlinked():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    assert cluster.remove_photo_from_clusters(db, uuid4()) is None
    db.delete.assert_not_called()


def test_remove_photo_deletes_singleton_cluster():
    db = MagicMock()
    photo_cluster = SimpleNamespace(cluster_id="cluster-1")
    image_cluster = SimpleNamespace(count=1)
    db.query.return_value.filter.return_value.all.return_value = [photo_cluster]
    db.query.return_value.filter.return_value.first.return_value = image_cluster

    cluster.remove_photo_from_clusters(db, uuid4())

    assert db.delete.call_args_list == [
        ((photo_cluster,), {}),
        ((image_cluster,), {}),
    ]


def test_remove_photo_decrements_shared_cluster_without_deleting_it():
    db = MagicMock()
    photo_cluster = SimpleNamespace(cluster_id="cluster-2")
    image_cluster = SimpleNamespace(count=3)
    db.query.return_value.filter.return_value.all.return_value = [photo_cluster]
    db.query.return_value.filter.return_value.first.return_value = image_cluster

    cluster.remove_photo_from_clusters(db, uuid4())

    assert image_cluster.count == 2
    db.delete.assert_called_once_with(photo_cluster)
