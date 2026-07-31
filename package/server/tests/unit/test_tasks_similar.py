"""Unit tests for ``app/service/tasks/similar.py``.

The similar-photo clustering strategy groups embeddings that are within a
cosine distance threshold and writes the resulting groups to the
``image_clusters`` / ``photo_clusters`` tables.

These tests cover two non-trivial paths that the existing test suite
didn't lock down:

1. Empty input -- no embeddings at all -> zero groups, status completed.
2. Two distinct bursts of identical embeddings -- each burst becomes its
   own cluster, ignoring the 5-minute gap (so the test runs fast).
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _build_task(payload=None, owner_id="user-1"):
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        type="SIMILAR_PHOTO_CLUSTERING",
        owner_id=owner_id,
        payload=payload or {"threshold": 0.9},
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _run(coro):
    return asyncio.run(coro)


def test_process_returns_zero_groups_when_no_embeddings():
    """No photos with embeddings -> short-circuit, no clusters persisted."""
    from app.service.tasks import similar as similar_mod

    db = MagicMock()
    db.execute.return_value.all.return_value = []
    task = _build_task()

    result = _run(
        similar_mod.SimilarPhotoClusteringStrategy().process(worker=None, task=task, db=db)
    )

    assert result == {"status": "completed", "count": 0}
    assert task.total_items == 0
    # No cluster rows should have been added.
    db.add.assert_not_called()


def test_process_groups_identical_embeddings_within_a_segment():
    """Identical vectors inside a single time window collapse into one group."""
    from app.service.tasks import similar as similar_mod

    from datetime import datetime

    base = datetime(2026, 7, 31, 12, 0, 0)
    vec = np.array([1.0, 0.0, 0.0])

    db = MagicMock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(photo_id="p1", embedding=vec, photo_time=base),
        SimpleNamespace(photo_id="p2", embedding=vec, photo_time=base),
        SimpleNamespace(photo_id="p3", embedding=vec, photo_time=base),
    ]
    task = _build_task()

    result = _run(
        similar_mod.SimilarPhotoClusteringStrategy().process(worker=None, task=task, db=db)
    )

    assert result["status"] == "completed"
    assert result["groups"] == 1
    # All three photos should have been added to a PhotoCluster.
    add_calls = db.add.call_args_list
    cluster_calls = [c for c in add_calls if isinstance(c.args[0], similar_mod.ImageCluster)]
    photo_cluster_calls = [c for c in add_calls if isinstance(c.args[0], similar_mod.PhotoCluster)]
    assert len(cluster_calls) == 1
    assert len(photo_cluster_calls) == 3


def test_process_splits_segments_when_gap_exceeds_threshold():
    """Two bursts >5min apart with the same embedding must form two groups."""
    from app.service.tasks import similar as similar_mod

    from datetime import datetime, timedelta

    early = datetime(2026, 7, 31, 8, 0, 0)
    late = early + timedelta(minutes=10)  # > 5min gap -> new segment
    vec = np.array([0.0, 1.0, 0.0])

    db = MagicMock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(photo_id="a1", embedding=vec, photo_time=early),
        SimpleNamespace(photo_id="a2", embedding=vec, photo_time=early),
        SimpleNamespace(photo_id="b1", embedding=vec, photo_time=late),
        SimpleNamespace(photo_id="b2", embedding=vec, photo_time=late),
    ]
    task = _build_task()

    result = _run(
        similar_mod.SimilarPhotoClusteringStrategy().process(worker=None, task=task, db=db)
    )

    assert result["groups"] == 2
    cluster_calls = [
        c for c in db.add.call_args_list
        if isinstance(c.args[0], similar_mod.ImageCluster)
    ]
    assert len(cluster_calls) == 2
