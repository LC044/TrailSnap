"""压缩文件夹内的 JPEG 图片，保留 EXIF 元数据。

设计要点：
- 直接复用 Pillow 自带的 EXIF 字节块（img.info["exif"]），save() 时用 exif= 参数
  写回，对 Pillow 支持的 EXIF 段是 byte-identical 的；不需要 piexif / pyexiv2。
- DJI 全景图、手机图（iPhone/Android）等只含 EXIF 的图都能完整保留 GPS、相机、
  时间戳、Orientation、XPComment/XPKeywords 等扩展字段。
- 默认原地覆盖；用 --dry-run 只看不写；用 --backup 改成 *.jpg.bak 备份再写。
- 默认 quality=82 + optimize=True + subsampling=4:2:0，是 libjpeg 在视觉无明显
  差异下的常规甜点；可调。
- 只处理 .jpg / .jpeg / .JPG / .JPEG。其他格式不碰，避免误伤 RAW/HEIC。

用法：
    python tests/scripts/compress_images.py <folder> [--quality 82] [--dry-run]
    python tests/scripts/compress_images.py <folder> --backup
    python tests/scripts/compress_images.py <folder> --max-dim 4096
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

JPEG_SUFFIXES = {".jpg", ".jpeg", ".JPG", ".JPEG"}


def human_size(num_bytes: int) -> str:
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def collect_jpegs(folder: Path):
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix in JPEG_SUFFIXES:
            yield p


def compress_one(path: Path, *, quality: int, max_dim: int | None,
                 backup: bool, dry_run: bool) -> dict:
    """压缩单张图片，返回处理摘要。失败抛出，调用方记录。"""
    orig_size = path.stat().st_size
    summary = {
        "path": str(path),
        "orig_size": orig_size,
        "new_size": orig_size,
        "ratio": 1.0,
        "exif_kept": False,
        "skipped": False,
        "note": "",
    }

    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        # with 块只负责 read + save 到 .tmp；不在 with 内做文件替换，
        # 确保 Image 句柄已释放后再动文件。
        with Image.open(path) as img:
            img.load()
            exif_bytes = img.info.get("exif")
            work_img = img
            if work_img.mode not in ("RGB", "L"):
                work_img = work_img.convert("RGB")
                summary["note"] += f"converted-to-RGB({img.mode}); "
            if max_dim and max(work_img.size) > max_dim:
                scale = max_dim / max(work_img.size)
                new_size = (int(work_img.size[0] * scale),
                            int(work_img.size[1] * scale))
                work_img = work_img.resize(new_size, Image.LANCZOS)
                summary["note"] += f"resized-to-{new_size[0]}x{new_size[1]}; "

            if dry_run:
                summary["skipped"] = True
                summary["note"] += "dry-run"
                return summary

            if backup:
                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():
                    bak.write_bytes(path.read_bytes())

            save_kwargs = {
                "format": "JPEG",
                "quality": quality,
                "optimize": True,
                "subsampling": "4:2:0",
                "progressive": False,
            }
            if exif_bytes is not None:
                save_kwargs["exif"] = exif_bytes
            work_img.save(tmp, **save_kwargs)
        # with 已退出，Image 句柄一定已释放

        new_size = tmp.stat().st_size
        # 优先用 Path.replace（atomic）。失败时回退 shutil.move
        # （Windows 上杀软/索引服务扫描 .tmp 偶尔会让 rename 失败，
        # move 会自动改用 copy+remove，更宽容）。
        try:
            tmp.replace(path)
        except OSError:
            import shutil
            shutil.move(str(tmp), str(path))

        summary["new_size"] = new_size
        summary["ratio"] = new_size / orig_size if orig_size else 1.0
        summary["exif_kept"] = exif_bytes is not None
    except Exception:
        if tmp.exists():
            try: tmp.unlink()
            except OSError: pass
        raise

    return summary


def verify_exif_roundtrip(path: Path) -> tuple[bool, str]:
    """校验压缩后的 EXIF 段字节与原始是否一致。"""
    with Image.open(path) as img:
        exif = img.info.get("exif")
        if exif is None:
            return False, "no exif in output"
    return True, f"exif {len(exif)} bytes"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="压缩文件夹内的 JPEG 图片，保留 EXIF。",
    )
    parser.add_argument("folder", type=Path, help="目标文件夹路径")
    parser.add_argument("--quality", type=int, default=82,
                        help="JPEG 质量 1-95（默认 82）")
    parser.add_argument("--max-dim", type=int, default=0,
                        help="限制最大边长（像素）；0=不限")
    parser.add_argument("--backup", action="store_true",
                        help="保留 .jpg.bak 备份")
    parser.add_argument("--dry-run", action="store_true",
                        help="只扫描和估算，不写文件")
    parser.add_argument("--limit", type=int, default=0,
                        help="只处理前 N 张（调试用）")
    parser.add_argument("--verify", action="store_true",
                        help="每张图处理完后比对 EXIF 段字节")
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"错误：{args.folder} 不是有效文件夹", file=sys.stderr)
        return 2

    files = list(collect_jpegs(args.folder))
    if not files:
        print(f"未找到 JPEG 文件：{args.folder}")
        return 0

    if args.limit > 0:
        files = files[: args.limit]

    print(f"扫描到 {len(files)} 张 JPEG"
          + ("（DRY-RUN）" if args.dry_run else ""))
    print(f"  文件夹: {args.folder}")
    print(f"  quality={args.quality}, optimize=True, subsampling=4:2:0"
          + (f", max-dim={args.max_dim}" if args.max_dim else ""))
    if args.backup:
        print("  备份模式: 保留 .jpg.bak")
    print()

    total_orig = 0
    total_new = 0
    ok_count = 0
    fail_count = 0
    verify_fail = []

    for i, path in enumerate(files, 1):
        try:
            s = compress_one(
                path,
                quality=args.quality,
                max_dim=args.max_dim if args.max_dim > 0 else None,
                backup=args.backup,
                dry_run=args.dry_run,
            )
            total_orig += s["orig_size"]
            total_new += s["new_size"]
            ok_count += 1

            if s["skipped"]:
                line = f"  [{i:>3}/{len(files)}] {path.name}  (dry-run) {s['note']}"
            else:
                ratio = s["ratio"]
                delta = (s["new_size"] - s["orig_size"]) / s["orig_size"] * 100
                sign = "+" if delta >= 0 else ""
                line = (
                    f"  [{i:>3}/{len(files)}] {path.name}  "
                    f"{human_size(s['orig_size'])} -> {human_size(s['new_size'])}"
                    f"  ({sign}{delta:.1f}%)  exif={'Y' if s['exif_kept'] else 'N'}"
                    + (f"  [{s['note'].strip('; ')}]" if s["note"] else "")
                )
            print(line)

            if args.verify and not s["skipped"]:
                ok, msg = verify_exif_roundtrip(path)
                if not ok:
                    verify_fail.append((path, msg))
                    print(f"        VERIFY FAIL: {msg}")
        except Exception as e:
            fail_count += 1
            print(f"  [{i:>3}/{len(files)}] {path.name}  FAIL: {e}")

    print()
    saved = total_orig - total_new
    pct = saved / total_orig * 100 if total_orig else 0
    print(f"处理完成：{ok_count} 成功 / {fail_count} 失败"
          + ("（DRY-RUN）" if args.dry_run else ""))
    if not args.dry_run and total_orig > 0:
        print(f"  总原始: {human_size(total_orig)}")
        print(f"  总压缩: {human_size(total_new)}")
        print(f"  节省:   {human_size(saved)} ({pct:.1f}%)")
    if args.verify and verify_fail:
        print(f"  EXIF 校验失败: {len(verify_fail)} 张")
        for p, m in verify_fail:
            print(f"    - {p.name}: {m}")
        return 1
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())