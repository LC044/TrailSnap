"""Run final Windows binaries: independent instances and interrupted-update recovery."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
import urllib.request
import pytest

pytestmark = [pytest.mark.module_portable_upgrade]


def test_final_portable_binaries_isolate_and_recover_interrupted_update():
    raw = os.getenv("TS_TEST_DESKTOP_PORTABLE_TEMPLATE")
    if os.name != "nt" or not raw:
        pytest.skip("Set the built Windows portable template for binary acceptance")
    template = Path(raw).resolve()
    repo = Path(__file__).resolve().parents[4]
    cache = repo / "tests/.cache/desktop-portable" / ("runtime-" + uuid.uuid4().hex[:10])
    instances = [cache / "家庭图库", cache / "工作图库"]
    from app.utils.windows_paths import filesystem_path
    for root in instances:
        shutil.copytree(filesystem_path(template), filesystem_path(root))
    env = {**os.environ,"TS_DESKTOP_TEST_HEADLESS":"1","TS_DESKTOP_TEST_READONLY":"1",
           "TS_INSTANCE_ROOT":str(cache / "wrong-instance"), "TS_DATA_DIR":str(cache / "wrong-data")}
    processes = []
    handed_off = None
    def launch(root):
        process = subprocess.Popen([str(root / "TrailSnap.exe")],cwd=root,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(process)
        return process
    def ready(root,process):
        deadline = time.monotonic()+180
        while time.monotonic()<deadline:
            marker = root / "maintenance/validated.json"
            if marker.exists():
                assert json.loads(marker.read_text(encoding="utf-8"))["verified"]
                return json.loads((root / "instance.json").read_text(encoding="utf-8"))
            error = root / "maintenance/launcher-error.json"
            if error.exists(): pytest.fail(error.read_text(encoding="utf-8"))
            if process.poll() is not None: pytest.fail("Launcher exited before validation")
            time.sleep(.2)
        logs = list((root / "userdata/logs").glob("*err*"))
        pytest.fail("Binary startup timed out: " + "\n".join(path.read_text(encoding="utf-8",errors="replace")[-4000:] for path in logs))
    def stop(process):
        if process.poll() is None:
            import psutil
            try: children = psutil.Process(process.pid).children(recursive=True)
            except psutil.Error: children = []
            process.terminate()
            process.wait(timeout=15)
            psutil.wait_procs(children,timeout=15)
    try:
        first,second = [launch(root) for root in instances]
        configs = [ready(root,process) for root,process in zip(instances,[first,second])]
        assert configs[0]["instanceId"] != configs[1]["instanceId"]
        assert configs[0]["serverPort"] != configs[1]["serverPort"]
        metadata = [json.loads((root / "userdata/library.json").read_text(encoding="utf-8")) for root in instances]
        assert metadata[0]["libraryId"] != metadata[1]["libraryId"]
        keys = [json.loads((root / "userdata/data/system_config.json").read_text(encoding="utf-8"))["security"]["secret_key"] for root in instances]
        assert keys[0] != keys[1]
        # Update recovery owns the library and restores its snapshot before any
        # normal startup. Seed an interrupted transaction only in this scratch instance.
        stop(first)
        root = instances[0]
        build = configs[0]["activeBuild"]
        backend = root / "app" / build / "server/trailsnap-server.exe"
        data = root / "userdata"
        snapshot = data / "backups/failure-fixture"
        helper = subprocess.run([str(backend),"--snapshot-data",str(data),str(snapshot)],capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        assert helper.returncode == 0, helper.stderr.decode(errors="replace")
        original = (data / "data/system_config.json").read_bytes()
        (data / "data/system_config.json").write_text('{"security":{"secret_key":"broken"}}',encoding="utf-8")
        journal = {"schemaVersion":1,"id":"failure-fixture","phase":"validating","oldBuild":build,"newBuild":build,"version":"0.0.0","nonce":"test","error":None}
        (root / "maintenance/update.json").write_text(json.dumps(journal),encoding="utf-8")
        (root / "maintenance/validated.json").unlink()
        recovering = launch(root)
        ready(root,recovering)
        tx = json.loads((root / "maintenance/update.json").read_text(encoding="utf-8"))
        assert tx["phase"] == "rolled_back"
        assert (data / "data/system_config.json").read_bytes() == original
        assert second.poll() is None
        with urllib.request.urlopen(f'http://127.0.0.1:{configs[1]["serverPort"]}/health-check',timeout=5) as response:
            assert response.status == 200
        # Exercise the complete snapshot -> verifier -> commit flow with the
        # built candidate. Only the current shell exits; its launcher stays alive.
        import psutil
        successful = {**journal, "id":"success-fixture", "phase":"apply_requested", "nonce":"success-fixture"}
        (root / "maintenance/update.json").write_text(json.dumps(successful),encoding="utf-8")
        (root / "maintenance/validated.json").unlink()
        shell = next(child for child in psutil.Process(recovering.pid).children()
                     if child.name().lower() == "trailsnap-desktop.exe")
        shell.terminate()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            status = json.loads((root / "maintenance/update.json").read_text(encoding="utf-8"))
            if status["phase"] == "committed": break
            assert status["phase"] != "rolled_back", status
            assert recovering.poll() is None
            time.sleep(.2)
        else: pytest.fail("Candidate validation did not commit")
        ready(root,recovering)
        assert second.poll() is None
        stop(recovering)
        # A folder rename must preserve its library ID and remain bootable.
        relocated = root.with_name("家庭图库-搬移")
        deadline = time.monotonic() + 15
        while True:
            try:
                root.rename(relocated)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    import psutil
                    holders = []
                    for process in psutil.process_iter(["pid", "name", "cwd"]):
                        try:
                            cwd = process.info["cwd"]
                            if cwd and Path(cwd).is_relative_to(root): holders.append(process.info)
                        except (psutil.Error, OSError): pass
                    pytest.fail(f"Exited instance still prevents folder relocation: {holders}")
                time.sleep(.2)
        (relocated / "maintenance/validated.json").unlink()
        moved = launch(relocated)
        ready(relocated,moved)
        assert json.loads((relocated / "userdata/library.json").read_text(encoding="utf-8"))["libraryId"] == metadata[0]["libraryId"]
        # Native conversion drains the backend while its UI remains open.
        # Keep this WebView alive to prove its locked browser cache is excluded.
        servers = [child for child in psutil.Process(moved.pid).children(recursive=True)
                   if child.name().lower().startswith("trailsnap-server")]
        for server in reversed(servers):
            try: server.terminate()
            except psutil.NoSuchProcess: pass
        psutil.wait_procs(servers,timeout=15)
        assert moved.poll() is None
        clone = cache / "独立副本"
        program = relocated / "app" / build
        conversion = subprocess.run([str(program / "server/trailsnap-server.exe"), "--convert-portable",
                                     str(relocated / "userdata"),str(clone),str(program),str(relocated / "TrailSnap.exe")],
                                    capture_output=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
        assert conversion.returncode == 0, conversion.stderr.decode(errors="replace")
        assert (clone / "app" / build / "portable-launcher.exe").is_file()
        clone_metadata = json.loads((clone / "userdata/library.json").read_text(encoding="utf-8"))
        assert clone_metadata["libraryId"] != metadata[0]["libraryId"]
        copied = launch(clone)
        ready(clone,copied)
        assert moved.poll() is None
        assert second.poll() is None
        stop(copied)
        # Damaged local configuration must fail promptly without opening an
        # empty library, and unattended verification must never show a modal.
        config_file = clone / 'instance.json'
        saved_config = config_file.read_bytes()
        config_file.unlink()
        rejected = subprocess.run([str(clone / 'TrailSnap.exe'), '--validate-only'], env=env,
                                  capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        assert rejected.returncode != 0 and not config_file.exists()
        config_file.write_bytes(saved_config)
        assert 'instance.json' in (clone / 'maintenance/launcher-error.json').read_text(encoding='utf-8')
        (clone / 'maintenance/launcher-error.json').unlink()
        (clone / "maintenance/validated.json").unlink()
        (relocated / "maintenance/handoff.json").write_text(json.dumps({"target":str(clone)}),encoding="utf-8")
        shell = next(child for child in psutil.Process(moved.pid).children()
                     if child.name().lower() == "trailsnap-desktop.exe")
        shell.terminate()
        moved.wait(timeout=30)
        deadline = time.monotonic() + 180
        while not (clone / "maintenance/validated.json").exists():
            assert time.monotonic() < deadline, "New instance was killed with the original Windows Job"
            time.sleep(.2)
        for process in psutil.process_iter(["exe"]):
            if process.info["exe"] and Path(process.info["exe"]).resolve() == (clone / "TrailSnap.exe").resolve():
                handed_off = process
                break
        assert handed_off is not None and handed_off.is_running()
        assert not (cache / "wrong-instance").exists()
        assert not (cache / "wrong-data").exists()
        report={"instancesIsolated":True,"interruptedUpdateRestored":True,"successfulUpdateCommitted":True,"otherInstanceUnaffected":True,"relocationBooted":True,"frozenConverterCloneBooted":True,"testDirectory":str(cache)}
        (cache / "runtime-result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    finally:
        if handed_off is not None:
            handed_off.terminate()
            handed_off.wait(timeout=15)
        for process in processes: stop(process)
