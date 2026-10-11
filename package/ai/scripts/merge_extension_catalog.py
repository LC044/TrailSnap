"""Publish AI assets belonging to this Server's product Release."""
import argparse
import copy
import json
import re
from pathlib import Path

PLATFORMS = {"win32-x64", "linux-x64", "darwin-arm64"}


def merge_catalog(metadata, assets, version):
    if set(assets) != PLATFORMS:
        raise ValueError("Every release requires Windows, Linux and macOS AI assets")
    for platform, asset in assets.items():
        filename = f"TrailSnap-AI-core-{platform}-{version}.tar.gz"
        expected = f"https://github.com/LC044/TrailSnap/releases/download/v{version}/{filename}"
        if asset["url"] != expected or asset.get("filename") != filename:
            raise ValueError("AI asset version must match the Server release version")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", asset["sha256"]):
            raise ValueError("Every asset requires a SHA-256 checksum")
        if asset.get("size", 0) <= 0:
            raise ValueError("AI asset must not be empty")
    catalog = copy.deepcopy(metadata)
    catalog["schemaVersion"] = 1
    extension = next(e for e in catalog["extensions"] if e["id"] == "core-ai")
    extension.update(version=version, assets=copy.deepcopy(assets))
    extension.pop("releases", None)
    extension.pop("rules", None)
    return catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assets = {}
    for asset_file in args.root.rglob("*.asset.json"):
        asset = json.loads(asset_file.read_text(encoding="utf-8"))
        platform = asset.pop("platform")
        if platform in assets:
            raise ValueError(f"Duplicate AI asset for {platform}")
        assets[platform] = asset
    metadata = Path(__file__).resolve().parents[2] / "desktop/src-tauri/resources/ai-extensions.json"
    catalog = merge_catalog(json.loads(metadata.read_text(encoding="utf-8")), assets, args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
