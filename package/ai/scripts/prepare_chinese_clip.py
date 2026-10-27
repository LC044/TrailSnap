"""Prepare the ModelScope repository layout from a checkpoint and exported ONNX files.

Run in the export environment (transformers + Pillow), not at app startup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from transformers import BertTokenizerFast, ChineseCLIPProcessor


def prepare(checkpoint: Path, onnx_dir: Path, output: Path, license_file: Path):
    text, image = output / 'text', output / 'image'
    text.mkdir(parents=True, exist_ok=True)
    image.mkdir(parents=True, exist_ok=True)
    tokenizer = BertTokenizerFast(vocab_file=str(checkpoint / 'vocab.txt'), model_max_length=52)
    tokenizer.save_pretrained(text)
    config = json.loads((checkpoint / 'config.json').read_text(encoding='utf-8'))['text_config']
    config['model_type'] = 'bert'
    (text / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    (text / 'embedding_config.json').write_text(json.dumps({'max_length': 52}), encoding='utf-8')
    processor = ChineseCLIPProcessor.from_pretrained(checkpoint, local_files_only=True)
    processor.image_processor.save_pretrained(image)
    shutil.copyfile(onnx_dir / 'candidate-text.onnx', text / 'textual.onnx')
    shutil.copyfile(onnx_dir / 'candidate-image.onnx', image / 'visual.onnx')
    if license_file.resolve() != (output / 'LICENSE').resolve():
        shutil.copyfile(license_file, output / 'LICENSE')
    (output / 'configuration.json').write_text('{}\n', encoding='utf-8')
    (output / 'README.md').write_text('''---
license: mit
tags:
- chinese-clip
- onnx
---
# Chinese-CLIP ViT-B/16 ONNX for TrailSnap

Source: https://huggingface.co/OFA-Sys/chinese-clip-vit-base-patch16
Revision: 36e679e65c2a2fead755ae21162091293ad37834
Upstream: https://github.com/OFA-Sys/Chinese-CLIP (MIT).

FP32, ONNX opset 17, 224px image input, 52-token text limit, 512-dimensional output.
Text inputs: input_ids, attention_mask, token_type_ids (int64).
Image input: pixel_values (float32). L2-normalize both tower outputs.
Upload the contents of this directory to SiYuan044/chinese-clip-vit-b16-onnx,
preserving text/ and image/ directories. No PyTorch weights are required at runtime.
''', encoding='utf-8')
    hashes = {str(p.relative_to(output)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS.json'}
    (output / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(output.resolve())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--onnx-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--license-file', type=Path, required=True, help='Upstream MIT-LICENSE.txt')
    args = parser.parse_args()
    prepare(args.checkpoint, args.onnx_dir, args.output, args.license_file)
