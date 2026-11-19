"""2026-11-16 nightly coverage for the desktop staging cleanup.

The 2026-11-16 backend coverage scan reported
``utils/desktop_data_migration.py`` at 93.4% and showed that the read-only
retry helper inside ``remove_staging_directory`` was never exercised:

* a read-only file copied into the staging tree must still be removed
  (Windows refuses to unlink a read-only file, so the helper relaxes the
  attribute and retries);
* a staging path that is a link must be refused before anything is deleted.
"""

from __future__ import annotations

import os
import stat

import pytest

from app.utils import desktop_data_migration as migration


pytestmark = [pytest.mark.smoke, pytest.mark.module_automatic_upgrade]


def test_remove_staging_directory_deletes_a_read_only_file(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    read_only = staging / "locked.txt"
    read_only.write_text("data", encoding="utf-8")
    os.chmod(read_only, stat.S_IREAD)

    migration.remove_staging_directory(staging)

    assert not staging.exists()


def test_remove_staging_directory_refuses_a_link(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("this environment cannot create symlinks")

    with pytest.raises(ValueError):
        migration.remove_staging_directory(link)

    assert target.exists()
