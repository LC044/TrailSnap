"""Nightly 2026-11-18: app/schemas/{face,memory}.py 校验器盲区。"""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.face import MergeRequest
from app.schemas.memory import MemoryCreate, MemorySplitRequest

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_merge_request_trims_identity_name():
    request = MergeRequest(source_ids=[uuid4()], target_id=uuid4(), identity_name="  小明  ")
    assert request.identity_name == "小明"


def test_merge_request_keeps_none_identity_name():
    request = MergeRequest(source_ids=[uuid4()], target_id=uuid4())
    assert request.identity_name is None


def test_merge_request_rejects_blank_identity_name():
    with pytest.raises(ValidationError):
        MergeRequest(source_ids=[uuid4()], target_id=uuid4(), identity_name="   ")


def test_memory_create_requires_cover_inside_photos():
    photo_id = uuid4()
    memory = MemoryCreate(title="旅行", photo_ids=[photo_id], cover_photo_id=photo_id)
    assert memory.cover_photo_id == photo_id


def test_memory_create_rejects_cover_outside_photos():
    with pytest.raises(ValidationError):
        MemoryCreate(title="旅行", photo_ids=[uuid4()], cover_photo_id=uuid4())


def test_memory_create_allows_missing_cover():
    memory = MemoryCreate(title="旅行", photo_ids=[uuid4()])
    assert memory.cover_photo_id is None


def test_memory_split_rejects_duplicated_photos():
    shared = uuid4()
    with pytest.raises(ValidationError):
        MemorySplitRequest(parts=[
            {"title": "一", "photo_ids": [shared, uuid4()]},
            {"title": "二", "photo_ids": [shared]},
        ])


def test_memory_split_accepts_disjoint_photos():
    request = MemorySplitRequest(parts=[
        {"title": "一", "photo_ids": [uuid4()]},
        {"title": "二", "photo_ids": [uuid4()]},
    ])
    assert len(request.parts) == 2
