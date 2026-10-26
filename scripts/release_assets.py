"""Shared public Release filenames; runtime platform keys stay unchanged."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

PLATFORMS = {"win32": "windows", "darwin": "macos", "windows": "windows", "macos": "macos", "linux": "linux", "android": "android"}
ARCHITECTURES = {"x86_64": "x64", "amd64": "x64", "x64": "x64", "aarch64": "arm64", "arm64": "arm64", "universal": "universal"}


def asset_name(version: str, component: str, platform: str, arch: str, suffix: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError(f"Invalid release version: {version}")
    if component not in {"desktop", "cli", "ai-core", "mobile"}:
        raise ValueError(f"Unsupported component: {component}")
    return f"TrailSnap-{version}-{component}-{PLATFORMS[platform]}-{ARCHITECTURES[arch]}{suffix}"


def ai_asset_name(version: str, platform_key: str) -> str:
    platform, arch = platform_key.split("-", 1)
    return asset_name(version, "ai-core", platform, arch, ".tar.gz")


def normalize_desktop(root: Path, version: str, platform: str, arch: str) -> None:
    patterns = {
        "windows": [("nsis/*.exe", "-setup.exe")],
        "macos": [("dmg/*.dmg", ".dmg"), ("macos/*.app.tar.gz", "-update.app.tar.gz")],
        "linux": [("appimage/*.AppImage", ".AppImage"), ("deb/*.deb", ".deb")],
    }
    for pattern, suffix in patterns[PLATFORMS[platform]]:
        files = list(root.glob(pattern))
        if len(files) != 1:
            raise ValueError(f"Expected one desktop artifact for {pattern}, found {len(files)}")
        source = files[0]
        destination = source.with_name(asset_name(version, "desktop", platform, arch, suffix))
        if source == destination:
            continue
        if destination.exists():
            raise ValueError(f"Duplicate artifact: {destination}")
        source.rename(destination)
        signature = source.with_name(source.name + ".sig")
        if signature.exists():
            signature.rename(destination.with_name(destination.name + ".sig"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", required=True, choices=PLATFORMS)
    parser.add_argument("--arch", required=True, choices=ARCHITECTURES)
    parser.add_argument("--component", default="desktop")
    parser.add_argument("--suffix", default="")
    parser.add_argument("--bundle-root", type=Path)
    args = parser.parse_args()
    if args.bundle_root:
        normalize_desktop(args.bundle_root, args.version, args.platform, args.arch)
    else:
        print(asset_name(args.version, args.component, args.platform, args.arch, args.suffix))


if __name__ == "__main__":
    main()
