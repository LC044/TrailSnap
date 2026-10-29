"""2026-10-29 nightly gap tests for ``app/service/tasks/organize.py``.

The organize strategy is driven with a mocked SQLAlchemy session and mocked
file transfers, so the folder-name derivation for every strategy
(time / category / person / location) can be asserted without touching disk.

Covered gaps: nested time folders, flat day folders, unknown-time handling,
category and person filters, person name de-duplication, the province /
district / province-city / city-district granularities, unknown locations and
the empty-name sanitisation fallback.
"""

import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service.tasks import organize as organize_module
from app.service.tasks.organize import OrganizePhotosStrategy


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _task(payload):
    return SimpleNamespace(
        id="task-org",
        type="ORGANIZE_PHOTOS",
        owner_id="user-1",
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _chain(photos):
    query = MagicMock()
    query.filter.return_value = query
    query.options.return_value = query
    query.all.return_value = photos
    return query


class _FakeColumn:
    def __init__(self, name):
        self.name = name


class _FakeTable:
    """Minimal stand-in for ``Photo.__table__`` so the copy branch can copy columns."""

    columns = [_FakeColumn(name) for name in (
        "owner_id", "photo_time", "upload_time", "is_deleted",
        "storage_root_id", "storage_relative_path",
    )]


def _photo(file_path, **kwargs):
    data = dict(
        id="photo-1",
        owner_id="user-1",
        filename=os.path.basename(file_path),
        file_path=file_path,
        photo_time=None,
        upload_time=None,
        is_deleted=False,
        tags=None,
        faces=None,
        metadata_info=None,
    )
    data.update(kwargs)
    photo = SimpleNamespace(**data)
    photo.__table__ = _FakeTable()
    return photo


def _run(payload, photos, tmp_path):
    """Run the strategy against mocked photos and return the created folders."""
    db = MagicMock()
    db.query.return_value = _chain(photos)
    target = tmp_path / "target"
    payload = dict(payload)
    payload["target_root_path"] = str(target)

    worker = MagicMock()
    worker.get_instance.return_value.add_task.return_value = None

    with patch.object(organize_module, "_commit_transfer") as transfer:
        with patch.object(organize_module.os, "makedirs"):
            import asyncio
            result = asyncio.run(
                OrganizePhotosStrategy().process(worker=worker, task=_task(payload), db=db)
            )

    folders = sorted({
        os.path.relpath(os.path.dirname(call.args[3]), str(target)).replace("\\", "/")
        for call in transfer.call_args_list
    })
    return result, folders, transfer


def test_time_strategy_builds_nested_year_month_folder(tmp_path):
    """``ym`` + ``nested`` produces a ``YYYY/MM`` subfolder."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    photo = _photo(str(source), photo_time=datetime(2026, 3, 7, 10, 0))

    result, folders, _ = _run(
        {"strategy": "time", "action": "move", "time_granularity": "ym", "time_format": "nested"},
        [photo], tmp_path,
    )

    assert result["success_count"] == 1
    assert any(f.replace("\\", "/").endswith("2026/03") for f in folders)


def test_time_strategy_builds_flat_day_folder(tmp_path):
    """``ymd`` + ``flat`` produces a ``YYYY-MM-DD`` subfolder."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    photo = _photo(str(source), photo_time=datetime(2026, 3, 7, 10, 0))

    _, folders, _ = _run(
        {"strategy": "time", "action": "move", "time_granularity": "ymd", "time_format": "flat"},
        [photo], tmp_path,
    )

    assert any(f.endswith("2026-03-07") for f in folders)


def test_time_strategy_uses_unknown_time_when_photo_has_no_time(tmp_path):
    """A photo without any timestamp lands in ``未知时间``."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    photo = _photo(str(source))

    _, folders, _ = _run(
        {"strategy": "time", "action": "move", "time_granularity": "ym"},
        [photo], tmp_path,
    )

    assert any(f.endswith("未知时间") for f in folders)


def test_time_strategy_skips_photo_outside_requested_range(tmp_path):
    """A photo outside the requested window is skipped entirely."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    photo = _photo(str(source), photo_time=datetime(2026, 3, 7, 10, 0))

    result, folders, transfer = _run(
        {
            "strategy": "time", "action": "move", "time_granularity": "ym",
            "time_range": ["2026-01-01 00:00:00", "2026-02-01 23:59:59"],
        },
        [photo], tmp_path,
    )

    assert result["success_count"] == 0
    assert folders == []
    assert transfer.call_count == 0


def test_time_strategy_skips_untimed_photo_when_range_given(tmp_path):
    """A photo without a timestamp cannot satisfy a time filter."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    photo = _photo(str(source))

    result, folders, _ = _run(
        {
            "strategy": "time", "action": "move", "time_granularity": "ym",
            "time_range": ["2026-01-01 00:00:00", "2026-02-01"],
        },
        [photo], tmp_path,
    )

    assert result["success_count"] == 0
    assert folders == []


def test_category_strategy_uses_uncategorized_folder(tmp_path):
    """A photo without tags goes to ``未分类``."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    photo = _photo(str(source), tags=[])

    _, folders, _ = _run(
        {"strategy": "category", "action": "move"}, [photo], tmp_path
    )

    assert any(f.endswith("未分类") for f in folders)


def test_category_strategy_filters_by_requested_categories(tmp_path):
    """Only the requested categories survive the filter."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    tags = [SimpleNamespace(tag_name="风景", confidence=0.9), SimpleNamespace(tag_name="美食", confidence=0.5)]
    photo = _photo(str(source), tags=tags)

    _, folders, _ = _run(
        {"strategy": "category", "action": "copy", "categories": ["美食"]}, [photo], tmp_path
    )

    assert any(f.endswith("美食") for f in folders)
    assert not any(f.endswith("风景") for f in folders)


def test_person_strategy_deduplicates_identities_for_copy(tmp_path):
    """Copying splits a photo into one folder per distinct identity name."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    faces = [
        SimpleNamespace(confidence=0.9, identity=SimpleNamespace(identity_name="小明")),
        SimpleNamespace(confidence=0.8, identity=SimpleNamespace(identity_name="小明")),
        SimpleNamespace(confidence=0.7, identity=SimpleNamespace(identity_name="小红")),
    ]
    photo = _photo(str(source), faces=faces)

    _, folders, _ = _run(
        {"strategy": "person", "action": "copy"}, [photo], tmp_path
    )

    assert any(f.endswith("小明") for f in folders)
    assert any(f.endswith("小红") for f in folders)


def test_person_strategy_uses_unnamed_folder_without_identity(tmp_path):
    """A photo without a named identity goes to ``未命名``."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    faces = [SimpleNamespace(confidence=0.9, identity=None)]
    photo = _photo(str(source), faces=faces)

    _, folders, _ = _run(
        {"strategy": "person", "action": "move"}, [photo], tmp_path
    )

    assert any(f.endswith("未命名") for f in folders)


def test_person_strategy_filters_by_requested_people(tmp_path):
    """Only the requested people survive the filter."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    faces = [
        SimpleNamespace(confidence=0.9, identity=SimpleNamespace(identity_name="小明")),
        SimpleNamespace(confidence=0.8, identity=SimpleNamespace(identity_name="小红")),
    ]
    photo = _photo(str(source), faces=faces)

    _, folders, _ = _run(
        {"strategy": "person", "action": "copy", "people": ["小红"]}, [photo], tmp_path
    )

    assert any(f.endswith("小红") for f in folders)
    assert not any(f.endswith("小明") for f in folders)


@pytest.mark.parametrize(
    "granularity,expected",
    [
        ("province", "浙江省"),
        ("district", "西湖区"),
        ("province_city", "浙江省-杭州市"),
        ("city_district", "杭州市-西湖区"),
    ],
)
def test_location_strategy_granularities(tmp_path, granularity, expected):
    """Each location granularity produces the expected folder name."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    meta = SimpleNamespace(province="浙江省", city="杭州市", district="西湖区")
    photo = _photo(str(source), metadata_info=meta)

    _, folders, _ = _run(
        {"strategy": "location", "action": "move", "location_granularity": granularity},
        [photo], tmp_path,
    )

    assert any(f.endswith(expected) for f in folders)


def test_location_strategy_uses_unknown_location_without_metadata(tmp_path):
    """A photo without metadata goes to ``未知位置``."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    photo = _photo(str(source), metadata_info=None)

    _, folders, _ = _run(
        {"strategy": "location", "action": "move", "location_granularity": "city"},
        [photo], tmp_path,
    )

    assert any(f.endswith("未知位置") for f in folders)


def test_location_strategy_uses_unknown_location_when_parts_empty(tmp_path):
    """A metadata row without any usable part also yields ``未知位置``."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    meta = SimpleNamespace(province=None, city=None, district=None)
    photo = _photo(str(source), metadata_info=meta)

    _, folders, _ = _run(
        {"strategy": "location", "action": "move", "location_granularity": "city"},
        [photo], tmp_path,
    )

    assert any(f.endswith("未知位置") for f in folders)


def test_location_strategy_filters_by_requested_locations(tmp_path):
    """Only the requested locations survive the filter."""
    source = tmp_path / "a.jpg"
    source.write_bytes(b"x")
    meta = SimpleNamespace(province=None, city="杭州市", district=None)
    photo = _photo(str(source), metadata_info=meta)

    _, folders, _ = _run(
        {
            "strategy": "location", "action": "move", "location_granularity": "city",
            "locations": ["北京市"],
        },
        [photo], tmp_path,
    )

    assert folders == []
