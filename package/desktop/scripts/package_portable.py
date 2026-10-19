"""Package the actual Windows program layout, without any user data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from release_assets import asset_name


def package(program: Path, server: Path, launcher: Path, catalog: Path, output: Path, version: str, arch: str, webview_runtime: Path | None = None):
    for required in (program / "trailsnap-desktop.exe", server / "trailsnap-server.exe", launcher, catalog):
        if not required.is_file(): raise ValueError(f"Missing release input: {required}")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
    from app.utils.desktop_layout import stage_program
    layout = output / "layout" / f"TrailSnap-{version}-{arch}"
    if layout.exists(): raise ValueError("Output layout already exists; use a new output directory")
    build = stage_program(layout, program, server, launcher, catalog, version, arch, webview_runtime)
    app = layout / "app" / build
    output.mkdir(parents=True,exist_ok=True)
    full = output / asset_name(version, "desktop", "windows", arch, "-portable.zip")
    update = output / asset_name(version, "desktop", "windows", arch, "-portable-update.zip")
    for base, target in ((layout,full),(app,update)):
        with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in sorted(base.rglob("*")):
                if path.is_file(): archive.write(path,path.relative_to(base).as_posix())
    with update.open("rb") as stream: sha = hashlib.file_digest(stream,"sha256").hexdigest()
    metadata = {"schemaVersion":1,"platform":f"windows-{arch}","version":version,"filename":update.name,"sha256":sha,"size":update.stat().st_size}
    (output / "portable-metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    return {"layout":str(layout),"full":str(full),"update":str(update),"buildId":build}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--program",type=Path,required=True)
    parser.add_argument("--server",type=Path,required=True)
    parser.add_argument("--launcher",type=Path,required=True)
    parser.add_argument("--catalog",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--version",required=True)
    parser.add_argument("--arch",choices=["x86_64","aarch64"],default="x86_64")
    parser.add_argument("--webview-runtime",type=Path)
    args=parser.parse_args()
    print(json.dumps(package(**vars(args))))


if __name__=="__main__": main()
