"""Merge per-platform CI asset metadata into the downloadable catalog."""

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("root", type=Path)
parser.add_argument("--version", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

assets = {}
for asset_file in args.root.rglob("*.asset.json"):
    asset = json.loads(asset_file.read_text(encoding="utf-8"))
    if "platform" not in asset:
        continue
    assets[asset.pop("platform")] = asset

if not assets:
    raise SystemExit("No extension asset metadata found")

catalog = {
    "schemaVersion": 1,
    "extensions": [{
        "id": "core-ai",
        "name": "TrailSnap AI 基础扩展",
        "version": args.version,
        "description": "内置 RapidOCR 资源；图片分类和票据模型在运行时从 ModelScope 下载。",
        "capabilities": ["ocr", "tickets", "classification"],
        "requirements": {"memoryMB": 2048, "diskMB": 500, "gpuRequired": False},
        "assets": assets,
    }],
}
args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
