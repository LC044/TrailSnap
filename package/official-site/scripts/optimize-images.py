"""Audit public images; optionally apply pixel-exact PNG/WebP optimizations.

Run with Python + Pillow: python scripts/optimize-images.py --apply
Original PNG URLs remain valid; referenced PNGs also get smaller lossless WebP
variants. JPEGs and existing lossy WebPs are never recompressed with loss.
"""
import argparse
import io
import json
import os
from pathlib import Path

from PIL import Image

root = Path(__file__).resolve().parents[1]
public = root / 'public'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply', action='store_true')
parser.add_argument('--report', type=Path, default=root / '../../output/demo-optimization/image-report.json')
args = parser.parse_args()
texts = {}
for directory, dirs, names in os.walk(root):
    dirs[:] = [d for d in dirs if d not in {'node_modules', 'dist', '.cache', 'cache', 'public', '.git'}]
    for name in names:
        path = Path(directory) / name
        if path.suffix in {'.vue', '.md', '.ts', '.mts', '.js', '.css', '.json', '.html'}:
            texts[path] = path.read_text(encoding='utf-8')

rows = []
for path in sorted(public.rglob('*')):
    if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.avif'}:
        continue
    before = path.stat().st_size
    with Image.open(path) as image:
        row = dict(path=path.relative_to(public).as_posix(), bytes=before, width=image.width, height=image.height, action='unchanged')
        rows.append(row)
        # Preserve animations, orientation and color profiles. No resampling.
        if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
            continue
        original = image.convert('RGBA').tobytes()
        meta = {k: image.info[k] for k in ['icc_profile', 'exif'] if k in image.info}
        output = io.BytesIO()
        image.save(output, format='WEBP', lossless=True, exact=True, method=6, **meta)
        data = output.getvalue()
        with Image.open(io.BytesIO(data)) as candidate:
            assert candidate.size == image.size and candidate.convert('RGBA').tobytes() == original
        url = '/' + row['path']
        refs = [p for p, text in texts.items() if url in text]
        variant = path.with_suffix('.webp')
        if refs and not variant.exists() and len(data) < before * .95:
            row.update(action='lossless-webp-variant', optimized_bytes=len(data), saved_bytes=before-len(data), pixel_exact=True)
            if args.apply:
                variant.write_bytes(data)
                for ref in refs:
                    texts[ref] = texts[ref].replace(url, '/' + variant.relative_to(public).as_posix())
        else:
            output = io.BytesIO()
            png_meta = dict(meta)
            if 'dpi' in image.info:
                png_meta['dpi'] = image.info['dpi']
            # Preserve PNG color metadata and text chunks when optimizing in place.
            from PIL.PngImagePlugin import PngInfo
            chunks = PngInfo()
            if 'srgb' in image.info:
                chunks.add(b'sRGB', bytes([image.info['srgb']]))
            if 'gamma' in image.info:
                import struct
                chunks.add(b'gAMA', struct.pack('>I', round(image.info['gamma'] * 100000)))
            for key, value in image.info.items():
                if isinstance(value, str) and key not in {'exif', 'icc_profile'}:
                    chunks.add_text(key, value)
            image.save(output, format='PNG', optimize=True, pnginfo=chunks, **png_meta)
            data = output.getvalue()
            with Image.open(io.BytesIO(data)) as candidate:
                assert candidate.size == image.size and candidate.convert('RGBA').tobytes() == original
            if len(data) < before * .98:
                row.update(action='lossless-png', optimized_bytes=len(data), saved_bytes=before-len(data), pixel_exact=True)
                if args.apply:
                    path.write_bytes(data)
if args.apply:
    for path, text in texts.items():
        if path.read_text(encoding='utf-8') != text:
            path.write_text(text, encoding='utf-8')
summary = dict(scanned=len(rows), original_bytes=sum(r['bytes'] for r in rows), optimized=sum(r['action'] != 'unchanged' for r in rows), saved_bytes=sum(r.get('saved_bytes', 0) for r in rows), applied=args.apply, images=rows)
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'images'}, ensure_ascii=False))
