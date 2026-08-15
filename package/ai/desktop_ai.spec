# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
hiddenimports = (
    collect_submodules("rapidocr")
    + collect_submodules("uvicorn")
    + collect_submodules("insightface", on_error="ignore")
    + collect_submodules("transformers", on_error="ignore")
    + [
        "modelscope",
        "modelscope.hub",
        "modelscope.hub.api",
        "modelscope.hub.constants",
        "modelscope.hub.errors",
        "modelscope.hub.file_download",
        "modelscope.hub.snapshot_download",
        "modelscope.utils",
        "modelscope.utils.config",
        "modelscope.utils.constant",
        "modelscope.utils.file_utils",
        "modelscope.utils.logger",
    ]
)
datas = [
    (str(root / "app" / "data"), "app/data"),
]
for package in (
    "fastapi", "pydantic", "rapidocr", "onnxruntime", "insightface",
    "modelscope", "transformers", "tokenizers", "huggingface-hub",
):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass
# The desktop runtime uses ONNX Runtime only. Keep RapidOCR's ONNX models and
# dictionaries, but omit the duplicate PyTorch weights.
datas += collect_data_files("rapidocr", excludes=["models/*.pth", "models/**/*.pth"])
for package in ("insightface", "transformers"):
    datas += collect_data_files(package)

a = Analysis(
    [str(root / "desktop_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter", "pytest", "torch", "pandas",
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
    # The Sidecar is controlled by the desktop gateway and writes to files.
    # Building it as a windowed executable prevents any console flash even if
    # Windows process flags are lost during an upgrade or manual launch.
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="trailsnap-ai",
)
