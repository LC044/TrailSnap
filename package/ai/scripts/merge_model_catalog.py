"""Create the downloadable desktop model catalog from CI asset metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asset_file = next(args.artifacts.rglob("models.asset.json"), None)
    if not asset_file:
        raise SystemExit("models.asset.json not found")
    asset = json.loads(asset_file.read_text(encoding="utf-8"))
    catalog = {
        "schemaVersion": 1,
        "models": [{
            "id": "desktop-core-models",
            "name": "桌面 AI 基础模型",
            "version": args.version,
            "description": "OCR、火车票/机票识别和图片分类所需的 CPU 模型。",
            "capabilities": ["ocr", "tickets", "classification"],
            "requirements": {"diskMB": 600},
            "asset": asset,
        }],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
