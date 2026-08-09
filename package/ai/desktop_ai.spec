# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
hiddenimports = (
    collect_submodules("rapidocr")
    + collect_submodules("uvicorn")
)
datas = [(str(root / "app" / "data"), "app/data")]
for package in ("fastapi", "pydantic", "rapidocr", "onnxruntime"):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass
datas += collect_data_files("rapidocr")

a = Analysis(
    [str(root / "desktop_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter", "pytest", "insightface", "torch", "transformers",
        "modelscope", "matplotlib", "pandas", "scipy", "skimage", "sklearn",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="trailsnap-ai",
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="trailsnap-ai",
)
