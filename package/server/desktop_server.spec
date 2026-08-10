# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("railway")
    + collect_submodules("uvicorn")
    + collect_submodules("passlib.handlers")
    + collect_submodules("sqlalchemy.dialects.postgresql")
)

datas = [
    (str(root / "resources"), "resources"),
]
for package in ("fastapi", "pydantic", "passlib", "langchain", "langchain_core", "langgraph"):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

# scipy / numpy / scikit-learn ship native Fortran/BLAS libraries (e.g.
# libgfortran-<hash>.so.5.0.0) inside <pkg>.libs directories. PyInstaller's
# default hooks do not always bundle them, which leaves the frozen sidecar
# referencing a .so that cannot be found later — and when Tauri's linuxdeploy
# walks the ELF dependencies to assemble the AppImage it aborts with
# "Could not find dependency: libgfortran-...so.5.0.0". collect_all pulls the
# submodules, data files AND the .libs binaries for each package.
binaries = []
for package in ("numpy", "scipy", "sklearn"):
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    [str(root / "desktop_entry.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="trailsnap-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # Electron starts the process with windowsHide and redirects both streams.
    # Keeping a console-subsystem executable makes early import failures and
    # PyInstaller multiprocessing diagnostics observable in server.err.log.
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="trailsnap-server",
)
