"""2026-11-19 nightly coverage for ``app/schemas/memory.py``.

``validate_cover`` and ``validate_unique_photos`` were never referenced by any
test file.  They keep the memory invariant that a cover is one of its own
photos and that a split never duplicates a photo across two parts.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.memory import MemoryCreate, MemorySplitPart, MemorySplitRequest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


PHOTO_A = "11111111-2222-3333-4444-555555555555"
PHOTO_B = "11111111-2222-3333-4444-666666666666"


def test_a_cover_outside_the_memory_photos_is_rejected():
    with pytest.raises(ValidationError, match="封面必须属于记忆照片"):
        MemoryCreate(title="旅行", photo_ids=[PHOTO_A], cover_photo_id=PHOTO_B)


def test_a_cover_inside_the_memory_photos_is_accepted():
    memory = MemoryCreate(title="旅行", photo_ids=[PHOTO_A], cover_photo_id=PHOTO_A)

    assert str(memory.cover_photo_id) == PHOTO_A


def test_a_memory_without_a_cover_is_accepted():
    assert MemoryCreate(title="旅行", photo_ids=[PHOTO_A]).cover_photo_id is None


def test_a_memory_needs_at_least_one_photo():
    with pytest.raises(ValidationError):
        MemoryCreate(title="旅行", photo_ids=[])


def test_a_split_may_not_repeat_a_photo():
    parts = [
        MemorySplitPart(title="第一段", photo_ids=[PHOTO_A]),
        MemorySplitPart(title="第二段", photo_ids=[PHOTO_A]),
    ]

    with pytest.raises(ValidationError, match="拆分后的照片不能重复"):
        MemorySplitRequest(parts=parts)


def test_a_split_with_disjoint_photos_is_accepted():
    request = MemorySplitRequest(
        parts=[
            MemorySplitPart(title="第一段", photo_ids=[PHOTO_A]),
            MemorySplitPart(title="第二段", photo_ids=[PHOTO_B]),
        ]
    )

    assert len(request.parts) == 2


def test_a_split_needs_at_least_two_parts():
    with pytest.raises(ValidationError):
        MemorySplitRequest(parts=[MemorySplitPart(title="第一段", photo_ids=[PHOTO_A])])

