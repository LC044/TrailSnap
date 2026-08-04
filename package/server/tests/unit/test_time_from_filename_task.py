from types import SimpleNamespace

import pytest

from app.service.tasks.time_from_filename import TimeFromFilenameStrategy


pytestmark = pytest.mark.smoke


def test_task_category_is_io():
    assert TimeFromFilenameStrategy().task_category == "IO"


@pytest.mark.parametrize(
    "metadata_info, expected",
    [
        (None, True),
        (SimpleNamespace(make="", model="Canon"), True),
        (SimpleNamespace(make="Canon", model=" EOS"), False),
    ],
)
def test_has_missing_metadata_detects_blank_make_or_model(metadata_info, expected):
    photo = SimpleNamespace(metadata_info=metadata_info)

    assert TimeFromFilenameStrategy()._has_missing_metadata(photo) is expected


@pytest.mark.asyncio
async def test_process_rejects_missing_target_root_path():
    task = SimpleNamespace(payload={}, owner_id="owner-1")

    with pytest.raises(ValueError, match="target_root_path"):
        await TimeFromFilenameStrategy().process(None, task, None)
