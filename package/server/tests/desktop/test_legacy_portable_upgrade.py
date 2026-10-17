"""Opt-in verification against a user's existing library, operating on copies only."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid
import pytest

pytestmark = [pytest.mark.module_portable_upgrade]


def test_existing_library_converts_and_moves_without_changing_original():
    source_raw = os.getenv("TS_TEST_DESKTOP_LEGACY_ROOT")
    program_raw = os.getenv("TS_TEST_DESKTOP_PROGRAM_DIR")
    launcher_raw = os.getenv("TS_TEST_DESKTOP_LAUNCHER")
    if not all((source_raw, program_raw, launcher_raw)):
        pytest.skip("Set the opt-in legacy root, built program and launcher test inputs")
    source, program, launcher = Path(source_raw).resolve(), Path(program_raw).resolve(), Path(launcher_raw).resolve()
    repo = Path(__file__).resolve().parents[4]
    cache = repo / "tests/.cache/desktop-portable"
    target = cache / ("converted-" + uuid.uuid4().hex[:12])
    db_path = source / "data/trailsnap.sqlite"
    def baseline(path):
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro",uri=True)) as db:
            return {"schema":db.execute("SELECT version_num FROM alembic_version").fetchall(),
                    "counts":{table:db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in ("users","photos","albums","tasks")}}
    before = baseline(db_path)
    command = [sys.executable, "desktop_entry.py", "--convert-portable", str(source),str(target),str(program),str(launcher)]
    environment = {**os.environ,"PYTHONIOENCODING":"utf-8"}
    result = subprocess.run(command,cwd=Path(__file__).resolve().parents[2],env=environment,capture_output=True,text=True,encoding="utf-8",timeout=60*30)
    assert result.returncode == 0, result.stderr
    assert baseline(db_path) == before
    assert baseline(target / "userdata/data/trailsnap.sqlite")["counts"] == before["counts"]
    assert (target / "TrailSnap.exe").is_file()
    instance = json.loads((target / "instance.json").read_text(encoding="utf-8"))
    assert instance["dataRoot"] == {"kind":"relative","path":"userdata"}
    moved = target.with_name(target.name + "-搬移")
    target.rename(moved)
    data = moved / "userdata"
    environment.update(TS_DESKTOP="1",TS_DESKTOP_PORTABLE="1",TS_DESKTOP_ROOT=str(data),TS_DATA_DIR=str(data / "data"))
    prepared = subprocess.run([sys.executable,"desktop_entry.py","--prepare-portable",str(data)],cwd=Path(__file__).resolve().parents[2],env=environment,capture_output=True,text=True,encoding="utf-8",timeout=600)
    assert prepared.returncode == 0, prepared.stderr
    with closing(sqlite3.connect(data / "data/trailsnap.sqlite")) as db:
        assert db.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT count(*) FROM photos WHERE storage_root_id IS NOT NULL").fetchone()[0] > 0
        managed = db.execute("SELECT r.location,p.storage_relative_path FROM photos p JOIN storage_roots r ON p.storage_root_id=r.id WHERE r.kind='managed' LIMIT 20").fetchall()
        assert managed
        available = [data / location / relative for location,relative in managed if (data / location / relative).is_file()]
        assert available, "Managed originals were not found after relocating the instance"
    assert baseline(db_path) == before
    report = {"original":str(source),"testInstance":str(moved),"counts":before["counts"],"schemaBefore":before["schema"],"schemaAfter":baseline(data / "data/trailsnap.sqlite")["schema"],"moved":True,"managedSamplesReadable":len(available)}
    cache.mkdir(parents=True,exist_ok=True)
    (cache / "legacy-upgrade-result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")


def test_final_binary_opens_converted_legacy_library():
    raw = os.getenv("TS_TEST_DESKTOP_CONVERTED_INSTANCE")
    template_raw = os.getenv("TS_TEST_DESKTOP_PORTABLE_TEMPLATE")
    if os.name != "nt" or not raw or not template_raw:
        pytest.skip("Set an already verified scratch conversion for final binary startup")
    import shutil
    import time
    import psutil
    from app.utils.windows_paths import filesystem_path
    root, template = Path(raw).resolve(), Path(template_raw).resolve()
    repo_cache = Path(__file__).resolve().parents[4] / "tests/.cache/desktop-portable"
    assert root.is_relative_to(repo_cache), "Only scratch test libraries may be used"
    with closing(sqlite3.connect(root / "userdata/data/trailsnap.sqlite")) as db:
        photo_count = db.execute("SELECT count(*) FROM photos").fetchone()[0]
    build = json.loads((template / "portable.json").read_text(encoding="utf-8"))["activeBuild"]
    program = root / "app" / build
    if not program.exists(): shutil.copytree(filesystem_path(template / "app" / build), filesystem_path(program))
    shutil.copy2(template / "TrailSnap.exe",root / "TrailSnap.exe")
    config = json.loads((root / "instance.json").read_text(encoding="utf-8"))
    config["activeBuild"] = build
    (root / "instance.json").write_text(json.dumps(config),encoding="utf-8")
    marker = root / "maintenance/validated.json"
    marker.unlink(missing_ok=True)
    env = {**os.environ,"TS_DESKTOP_TEST_HEADLESS":"1","TS_DESKTOP_TEST_READONLY":"1"}
    process = subprocess.Popen([str(root / "TrailSnap.exe")],cwd=root,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 180
        while not marker.exists():
            assert process.poll() is None, "Converted legacy binary exited before validation"
            assert time.monotonic() < deadline, "Converted legacy binary startup timed out"
            time.sleep(.2)
        assert json.loads(marker.read_text(encoding="utf-8"))["verified"]
        with closing(sqlite3.connect(root / "userdata/data/trailsnap.sqlite")) as db:
            assert db.execute("SELECT count(*) FROM photos").fetchone()[0] == photo_count
            assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
        (repo_cache / "legacy-binary-result.json").write_text(json.dumps({"verified":True,"build":build,"testInstance":str(root)}),encoding="utf-8")
    finally:
        if process.poll() is None:
            children = psutil.Process(process.pid).children(recursive=True)
            process.terminate()
            process.wait(timeout=15)
            psutil.wait_procs(children,timeout=15)
