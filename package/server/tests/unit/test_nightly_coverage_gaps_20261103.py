"""Nightly coverage additions for the 2026-11-03 gap scan.

The selected modules are the highest-value uncovered backend areas after the
regular unit suite: face clustering, task-worker completion state, agent
memory validation, similar-photo time handling and storage's lazy cv2 loader.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.service import storage as storage_module
from app.service import task_worker
from app.service.agent import memory as agent_memory
from app.service.face_cluster import FaceClusterService
from app.db.models.cluster import ImageCluster, PhotoCluster
from app.service.tasks.similar import SimilarPhotoClusteringStrategy


pytestmark = [pytest.mark.smoke]


def test_face_cluster_diverse_prototypes_stop_when_vectors_are_identical():
    """Identical prototypes provide no new diversity and stop sampling early."""
    service = FaceClusterService(MagicMock())
    embeddings = [np.array([1.0, 0.0, 0.0])] * (
        FaceClusterService.MAX_RESCAN_PROTOTYPES + 1
    )

    prototypes = service._select_diverse_prototypes(embeddings)

    assert len(prototypes) == 1
    np.testing.assert_array_equal(prototypes[0], embeddings[0])


def test_task_worker_completion_context_updates_non_numeric_status():
    """Non-numeric fields are replaced while unrelated worker attrs stay readable."""
    worker = SimpleNamespace(scan_status={"phase": "idle"}, accepting_tasks=True)
    context = task_worker.CompletionContext(worker)

    context.scan_status["phase"] = "running"
    context.apply()

    assert context.accepting_tasks is True
    assert worker.scan_status["phase"] == "running"


def test_agent_memory_anchors_without_photo_ids_do_not_query_database():
    """Anchors lacking photo_id are invalid and must not reach the photo query."""
    db = MagicMock()
    raw = {"version": 1, "anchors": [{"text": "no photo reference"}]}

    with patch.object(agent_memory, "load_raw_memory", return_value=raw):
        result = agent_memory.get_valid_memory_anchors(db, "user-1")

    assert result == []
    db.query.assert_not_called()


def test_similar_photo_clustering_groups_photos_without_photo_time():
    """Photos with missing timestamps still form one time segment for clustering."""
    task = SimpleNamespace(
        id="similar-task",
        owner_id="user-1",
        payload={"threshold": 0.9},
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(photo_id="p1", embedding=np.array([1.0, 0.0]), photo_time=None),
        SimpleNamespace(photo_id="p2", embedding=np.array([1.0, 0.0]), photo_time=None),
    ]

    result = asyncio.run(
        SimilarPhotoClusteringStrategy().process(worker=None, task=task, db=db)
    )

    assert result == {"status": "completed", "groups": 1}
    cluster_calls = [call for call in db.add.call_args_list if isinstance(call.args[0], ImageCluster)]
    photo_calls = [call for call in db.add.call_args_list if isinstance(call.args[0], PhotoCluster)]
    assert len(cluster_calls) == 1
    assert len(photo_calls) == 2


def test_storage_lazy_cv2_loader_returns_imported_module():
    """The helper is lazy, so callers receive whichever cv2 object Python imports."""

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            return MagicMock(__name__="cv2")
        raise AssertionError(f"unexpected import: {name}")

    with patch("builtins.__import__", side_effect=fake_import):
        assert storage_module._load_cv2() is not None

