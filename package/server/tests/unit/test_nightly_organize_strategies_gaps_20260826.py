"""Round 2026-08-26 coverage gaps for ``app/service/tasks/organize.py``."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _chain(photos):
    query = MagicMock()
    query.filter.return_value = query
    query.options.return_value = query
    query.all.return_value = photos
    return query


def _build_task(payload):
    return SimpleNamespace(
        id="task-org-26",
        type="ORGANIZE_PHOTOS",
        owner_id="user-26",
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _photo(path, **attrs):
    filename = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    defaults = dict(
        file_path=path,
        filename=filename,
        photo_time=None,
        upload_time=None,
        is_deleted=False,
        faces=[],
        tags=[],
        metadata_info=None,
    )
    defaults.update(attrs)
    return SimpleNamespace(**defaults)


def test_time_strategy_ym_flat_builds_year_month_folder(tmp_path):
    """time_format='flat' + time_granularity='ym' -> YYYY-MM."""
    from app.service.tasks import organize

    import datetime
    photo = _photo(
        str(tmp_path / "img.jpg"),
        photo_time=datetime.datetime(2024, 5, 7),
    )
    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "time",
        "action": "move",
        "time_granularity": "ym",
        "time_format": "flat",
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        result = asyncio.run(
            organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db)
        )

    move.assert_called_once()
    called_dst = move.call_args[0][1].replace("\\", "/")
    parts = called_dst.split("/")
    assert "2024-05" in parts
    assert task.processed_items == 1
    assert result["success_count"] == 1


def test_time_strategy_time_range_skips_out_of_window_photo(tmp_path):
    """Photos outside time_range advance processed_items but do not move."""
    from app.service.tasks import organize

    photo = _photo(
        str(tmp_path / "old.jpg"),
        photo_time=SimpleNamespace(strftime=lambda fmt: "2020-01-01 00:00:00"),
    )
    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "time",
        "action": "move",
        "time_range": ["2024-01-01", "2024-12-31"],
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        result = asyncio.run(
            organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db)
        )

    move.assert_not_called()
    assert task.processed_items == 1
    assert result["success_count"] == 0


def test_category_strategy_move_picks_top_confidence_tag(tmp_path):
    """action='move' uses the highest-confidence tag for the subfolder."""
    from app.service.tasks import organize

    photo = _photo(
        str(tmp_path / "p.jpg"),
        tags=[
            SimpleNamespace(tag_name="beach", confidence=0.4),
            SimpleNamespace(tag_name="mountain", confidence=0.9),
            SimpleNamespace(tag_name="city", confidence=0.6),
        ],
    )
    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "category",
        "action": "move",
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        result = asyncio.run(
            organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db)
        )

    move.assert_called_once()
    called_dst = move.call_args[0][1].replace("\\", "/")
    parts = called_dst.split("/")
    assert "mountain" in parts
    assert result["success_count"] == 1


def test_location_strategy_province_city_district_nested_format(tmp_path):
    """province_city_district + nested format builds full path."""
    from app.service.tasks import organize

    photo = _photo(
        str(tmp_path / "p.jpg"),
        metadata_info=SimpleNamespace(
            province="\u6e56\u5317\u7701",
            city="\u6b66\u6c49\u5e02",
            district="\u6b66\u660c\u533a",
        ),
    )
    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "location",
        "action": "move",
        "location_granularity": "province_city_district",
        "location_format": "nested",
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        result = asyncio.run(
            organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db)
        )

    move.assert_called_once()
    called_dst = move.call_args[0][1].replace("\\", "/")
    parts = called_dst.split("/")
    assert "\u6e56\u5317\u7701" in parts
    assert "\u6b66\u6c49\u5e02" in parts
    assert "\u6b66\u660c\u533a" in parts
    assert result["success_count"] == 1


def test_location_strategy_city_only_granularity(tmp_path):
    """location_granularity='city' ignores province/district when building subfolder."""
    from app.service.tasks import organize

    photo = _photo(
        str(tmp_path / "p.jpg"),
        metadata_info=SimpleNamespace(
            province="\u6e56\u5317\u7701",
            city="\u6b66\u6c49\u5e02",
            district="\u6b66\u660c\u533a",
        ),
    )
    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "location",
        "action": "move",
        "location_granularity": "city",
        "location_format": "flat",
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "move") as move:
        import asyncio
        asyncio.run(
            organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db)
        )

    move.assert_called_once()
    called_dst = move.call_args[0][1].replace("\\", "/")
    parts = called_dst.split("/")
    assert "\u6b66\u6c49\u5e02" in parts
    assert "\u6e56\u5317\u7701" not in parts
    assert "\u6b66\u660c\u533a" not in parts


def test_location_strategy_locations_filter_drops_unmatched(tmp_path):
    """locations whitelist restricts which subfolders survive dedup."""
    from app.service.tasks import organize

    photo = _photo(
        str(tmp_path / "p.jpg"),
        metadata_info=SimpleNamespace(province=None, city="\u6b66\u6c49\u5e02", district=None),
    )
    # The copy branch instantiates Photo(...). Provide a stub __table__.columns
    # so the comprehension over photo.__table__.columns does not blow up.
    fake_table_columns = [SimpleNamespace(name=k) for k in ("id", "file_path", "filename")]
    photo.__table__ = SimpleNamespace(columns=fake_table_columns)
    db = MagicMock()
    db.query.return_value = _chain([photo])
    task = _build_task({
        "target_root_path": str(tmp_path / "out"),
        "strategy": "location",
        "action": "copy",
        "location_granularity": "city",
        "locations": ["\u5317\u4eac\u5e02"],  # does not include \u6b66\u6c49\u5e02
    })

    with patch.object(organize.os.path, "exists", return_value=True), \
         patch.object(organize.os, "makedirs"), \
         patch.object(organize.shutil, "copy2") as copy:
        import asyncio
        asyncio.run(
            organize.OrganizePhotosStrategy().process(worker=None, task=task, db=db)
        )

    # locations=['\u5317\u4eac\u5e02'] filters out \u6b66\u6c49\u5e02 -> no copy
    copy.assert_not_called()
