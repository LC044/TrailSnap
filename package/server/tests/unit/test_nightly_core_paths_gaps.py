"""Focused unit coverage for ``app.core.paths`` (init_db seed scaffolding).

Tracks the same hot-spots the nightly gap scan keeps surfacing: ``ensure_rg_seed``
writes the default ``CN.csv`` from the bundled seed dir into the writable data
directory on first boot, and remembers that the seed has been applied via a
sentinel file so later deletions don't trigger re-seeding.

We mock the module's ``os`` and ``shutil`` interactions to keep the test
hermetic and to avoid touching the real data directory on the host.
"""
from unittest.mock import patch

import pytest

from app.core import paths as core_paths


pytestmark = [pytest.mark.smoke, pytest.mark.module_core]


def test_ensure_rg_seed_noop_when_sentinel_already_exists(tmp_path):
    """Calling ``ensure_rg_seed`` after the sentinel is present must not retry the copy.

    This is the sticky contract: once seeded, the function returns immediately
    even if the target ``CN.csv`` has been deleted (user reset). Copy is never
    invoked because the sentinel short-circuits everything.
    """
    sentinel = tmp_path / ".seeded.v1"
    sentinel.write_text("", encoding="utf-8")

    rg_data_dir = tmp_path / "rg_data"
    rg_data_dir.mkdir()

    with patch.object(core_paths, "RG_DATA_DIR", str(rg_data_dir)), patch.object(
        core_paths, "_SEED_SENTINEL", str(sentinel)
    ), patch.object(core_paths, "RG_SEED_DIR", str(tmp_path / "seeds")):
        with patch("app.core.paths.shutil.copy2") as copy_mock:
            core_paths.ensure_rg_seed()

    copy_mock.assert_not_called()
    assert sentinel.exists()


def test_ensure_rg_seed_copies_default_cn_csv_atomically(tmp_path):
    """First boot must copy ``CN.csv`` from the bundled seed into the data dir."""
    seeds_dir = tmp_path / "seeds"
    seeds_dir.mkdir()
    seed_csv = seeds_dir / "CN.csv"
    seed_csv.write_text("city,lat,lon\nwuhan,30.59,114.30\n", encoding="utf-8")

    rg_data_dir = tmp_path / "data" / "rg_data"
    rg_data_dir.mkdir(parents=True)
    sentinel = rg_data_dir / ".seeded.v1"
    assert not sentinel.exists()

    captured = {}

    def fake_copy2(src, dst):
        captured["src"] = src
        captured["dst"] = dst
        with open(dst, "w", encoding="utf-8") as f:
            f.write("copied")

    with patch.object(core_paths, "RG_DATA_DIR", str(rg_data_dir)), patch.object(
        core_paths, "_SEED_SENTINEL", str(sentinel)
    ), patch.object(core_paths, "RG_SEED_DIR", str(seeds_dir)), patch(
        "app.core.paths.shutil.copy2", side_effect=fake_copy2
    ) as copy_mock, patch("app.core.paths.os.replace") as replace_mock:
        core_paths.ensure_rg_seed()

    copy_mock.assert_called_once()
    replace_mock.assert_called_once()
    assert captured["src"].endswith("CN.csv")
    assert captured["dst"].endswith("CN.csv.tmp")
    assert sentinel.exists()


def test_ensure_rg_seed_skips_copy_when_seed_cn_missing(tmp_path):
    """If the bundled ``CN.csv`` is missing, log a warning and continue."""
    seeds_dir = tmp_path / "seeds"
    seeds_dir.mkdir()  # intentionally no CN.csv inside

    rg_data_dir = tmp_path / "data" / "rg_data"
    rg_data_dir.mkdir(parents=True)
    sentinel = rg_data_dir / ".seeded.v1"
    assert not sentinel.exists()

    with patch.object(core_paths, "RG_DATA_DIR", str(rg_data_dir)), patch.object(
        core_paths, "_SEED_SENTINEL", str(sentinel)
    ), patch.object(core_paths, "RG_SEED_DIR", str(seeds_dir)), patch(
        "app.core.paths.shutil.copy2"
    ) as copy_mock:
        core_paths.ensure_rg_seed()

    copy_mock.assert_not_called()
    # Sentinel still gets written so we don't retry forever.
    assert sentinel.exists()


def test_ensure_rg_seed_cleans_tmp_on_oserror(tmp_path):
    """``shutil.copy2`` raising OSError must not leave a stray ``.tmp`` file behind."""
    seeds_dir = tmp_path / "seeds"
    seeds_dir.mkdir()
    seed_csv = seeds_dir / "CN.csv"
    seed_csv.write_text("city,lat,lon\n", encoding="utf-8")

    rg_data_dir = tmp_path / "data" / "rg_data"
    rg_data_dir.mkdir(parents=True)
    sentinel = rg_data_dir / ".seeded.v1"
    tmp_file = rg_data_dir / "CN.csv.tmp"

    with patch.object(core_paths, "RG_DATA_DIR", str(rg_data_dir)), patch.object(
        core_paths, "_SEED_SENTINEL", str(sentinel)
    ), patch.object(core_paths, "RG_SEED_DIR", str(seeds_dir)), patch(
        "app.core.paths.shutil.copy2", side_effect=OSError("disk full")
    ) as copy_mock:
        core_paths.ensure_rg_seed()

    copy_mock.assert_called_once()
    assert not tmp_file.exists(), "Failed copy should not leave .tmp around"
    # Sentinel is still written so we don't keep retrying the failed copy each boot.
    assert sentinel.exists()


def test_ensure_rg_seed_creates_data_dir_when_missing(tmp_path):
    """If the writable ``RG_DATA_DIR`` does not exist yet it must be created."""
    seeds_dir = tmp_path / "seeds"
    seeds_dir.mkdir()
    seed_csv = seeds_dir / "CN.csv"
    seed_csv.write_text("city\nwuhan\n", encoding="utf-8")

    rg_data_dir = tmp_path / "data" / "rg_data"
    assert not rg_data_dir.exists()
    sentinel = rg_data_dir / ".seeded.v1"

    with patch.object(core_paths, "RG_DATA_DIR", str(rg_data_dir)), patch.object(
        core_paths, "_SEED_SENTINEL", str(sentinel)
    ), patch.object(core_paths, "RG_SEED_DIR", str(seeds_dir)), patch(
        "app.core.paths.shutil.copy2"
    ) as copy_mock:
        core_paths.ensure_rg_seed()

    assert rg_data_dir.exists() and rg_data_dir.is_dir()
    copy_mock.assert_called_once()
