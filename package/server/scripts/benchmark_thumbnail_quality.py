"""Compare decoded thumbnails against resized originals; no library writes."""
import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config_manager import ImageSettings
from app.service import storage
from benchmark_basic_pipeline import select_files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--baseline-ref', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    source = subprocess.check_output(['git', 'show', f'{args.baseline_ref}:package/server/app/service/storage.py'], cwd=repo)
    baseline = types.ModuleType('baseline_storage')
    exec(compile(source, 'baseline_storage.py', 'exec'), baseline.__dict__)
    config = ImageSettings()
    scores = {name: {'preview': [], 'thumbnail': []} for name in ('before', 'after')}
    with tempfile.TemporaryDirectory(prefix='trailsnap-quality-') as directory:
        for path in select_files(args.root):
            if path.suffix.lower() == '.mp4':
                continue
            with Image.open(path) as original, ImageOps.exif_transpose(original) as upright:
                upright = upright.convert('RGB')
                for name, module in [('before', baseline), ('after', storage)]:
                    with patch.object(module, '_get_storage_root', return_value=directory):
                        output = Path(module._save_thumbnails(original, uuid4(), 'quality', config))
                    for variant, target, size in [('preview', output, config.preview_size),
                                                   ('thumbnail', output.with_name(output.stem + '-thumb.webp'), config.thumbnail_size)]:
                        with upright.copy() as reference, Image.open(target) as actual:
                            reference.thumbnail((size, size))
                            assert reference.size == actual.size
                            delta = np.asarray(reference, dtype=np.float64) - np.asarray(actual.convert('RGB'), dtype=np.float64)
                            mse = float(np.mean(delta ** 2))
                            scores[name][variant].append(10 * math.log10(255 ** 2 / mse) if mse else 100.0)
                upright.close()
    report = {'metric': 'PSNR against upright resized original (dB, higher is better)',
              'image_count': len(scores['before']['preview']), 'baseline_ref': args.baseline_ref,
              'mean': {name: {variant: statistics.mean(values) for variant, values in variants.items()}
                       for name, variants in scores.items()}, 'samples': scores}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['mean']))


if __name__ == '__main__':
    main()
