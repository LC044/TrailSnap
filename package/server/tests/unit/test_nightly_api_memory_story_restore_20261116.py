"""2026-11-16 nightly coverage for ``app/api/memory.py``.

The 2026-11-16 backend coverage scan reported ``api/memory.py`` at 95.6%
with 4 missed lines:

* the story generation endpoint (lines 137-139) -- the AI story is generated
  and the refreshed row is serialized back to the client;
* the restore endpoint refusing a memory whose status cannot be restored
  (line 164).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import memory as memory_api
from app.db.models.memory import MemoryStatus
from app.schemas.memory import MemoryStoryRequest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.mark.asyncio
async def test_generate_memory_story_returns_the_generated_row():
    memory_id = uuid.uuid4()
    owner = MagicMock(id=uuid.uuid4())
    db = MagicMock()
    row = MagicMock(id=memory_id)

    with patch.object(memory_api.memory_service, "get_detail", return_value=row), \
            patch.object(memory_api.memory_service, "generate_story", new=AsyncMock(return_value=row)) as generate, \
            patch.object(memory_api.memory_service, "serialize", return_value={"id": str(memory_id)}) as serialize:
        response = await memory_api.generate_memory_story(
            memory_id, MemoryStoryRequest(tone="温暖"), owner, db,
        )

    generate.assert_awaited_once()
    assert generate.await_args.args[2] == owner.id
    serialize.assert_called_once()
    assert response.data == {"id": str(memory_id)}


def test_restore_memory_refuses_a_status_that_cannot_be_restored():
    row = MagicMock(status=MemoryStatus.CONFIRMED)
    db = MagicMock()
    owner = MagicMock(id=uuid.uuid4())

    with patch.object(memory_api.memory_service, "get_detail", return_value=row):
        with pytest.raises(HTTPException) as excinfo:
            memory_api.restore_memory(uuid.uuid4(), owner, db)

    assert excinfo.value.status_code == 400
    assert "当前状态不能恢复" in excinfo.value.detail
