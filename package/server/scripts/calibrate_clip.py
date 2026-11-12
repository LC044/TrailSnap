"""Read-only developer calibration. Keep photos and labels outside the repository.

Run from package/server after loading the development .env, with --output an
external private directory. Generates scoring data and contact sheets; it never
writes database rows or claims that unlabelled thresholds are calibrated.
"""

import argparse
import json
import os
import sys
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv(os.environ.get("CLIP_DEV_ENV", "data/.env"))
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from sqlalchemy import text
from app.db.session import engine
from app.service.clip_catalog import load_catalog


def apply_review(output, label_path, catalog_path):
    """Choose conservative defaults from explicit visual labels, never pseudo-labels."""
    labels = json.loads(label_path.read_text("utf-8"))
    samples = json.loads((output / "boundary-samples.json").read_text("utf-8"))
    catalog = json.loads(catalog_path.read_text("utf-8"))
    by_name = {row["name"]: row for row in samples}
    report = []
    for cat in catalog["categories"]:
        row = by_name[cat["name"]]
        if row.get("key") != cat["key"] or row.get("descriptions") != cat["descriptions"]:
            raise ValueError(f"Descriptions changed since scoring: {cat['name']}")
        verdicts = labels[cat["name"]]
        if len(verdicts) != len(row["samples"]) or set(verdicts) - set("TFU"):
            raise ValueError(f"Invalid explicit labels: {cat['name']}")
        known = [
            (sample["score"], label == "T")
            for sample, label in zip(row["samples"], verdicts)
            if label != "U" and sample.get("split", "train") == "train"
        ]
        positives = [s for s, keep in known if keep]
        negatives = [s for s, keep in known if not keep]
        initial = row["threshold"]
        candidates = np.arange(0.20, max(0.65, row["max_score"] + 0.01), 0.005)
        # F0.5 prioritizes precision while retaining positive matches. Using
        # weighted error alone can select an empty result for common classes.
        def objective(value):
            tp = sum(s >= value for s in positives)
            fp = sum(s >= value for s in negatives)
            fn = len(positives) - tp
            denominator = 1.25 * tp + 0.25 * fn + fp
            f_half = 1.25 * tp / denominator if denominator else 0.0
            return (-f_half, abs(float(value) - initial), -float(value))

        threshold = min(
            candidates,
            key=objective,
        )
        threshold = round(float(threshold), 3)
        if not positives:
            threshold = round(min(1.0, row["max_score"] + 0.005), 3)
        separated = bool(positives) and (
            not negatives or max(negatives) < min(positives)
        )
        validation = [
            (sample["score"], label == "T")
            for sample, label in zip(row["samples"], verdicts)
            if label != "U" and sample.get("split") == "validation"
        ]
        tp = sum(score >= threshold and label for score, label in validation)
        fp = sum(score >= threshold and not label for score, label in validation)
        fn = sum(score < threshold and label for score, label in validation)
        tn = sum(score < threshold and not label for score, label in validation)
        supported = len(positives) >= 2 and bool(negatives) and separated
        status = "reviewed" if supported and tp >= 1 and fp == 0 else "limited"
        cat["thresholds"][row["model"]] = threshold
        cat["calibration"] = {
            "status": status,
            "reviewed": len(verdicts),
            "positive": verdicts.count("T"),
            "negative": verdicts.count("F"),
            "uncertain": verdicts.count("U"),
            "method": "visual-stratified-f0.5-grid0.005-v2",
            "train_samples": sum(s.get("split") == "train" for s in row["samples"]),
            "validation_samples": sum(s.get("split") == "validation" for s in row["samples"]),
            "date": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "model": row["model"],
            "photos_scored": row["photos_scored"],
            "description_sha256": hashlib.sha256(
                json.dumps(cat["descriptions"], ensure_ascii=False).encode()
            ).hexdigest(),
            "train_positive": len(positives),
            "train_negative": len(negatives),
            "training": {
                "tp": sum(s >= threshold for s in positives),
                "fp": sum(s >= threshold for s in negatives),
                "fn": sum(s < threshold for s in positives),
                "tn": sum(s < threshold for s in negatives),
            },
            "validation": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "no_positive_evidence": not bool(positives),
        }
        report.append(
            {"name": cat["name"], "threshold": threshold, **cat["calibration"]}
        )
        for sample, label in zip(row["samples"], verdicts):
            sample["label"] = {"T": True, "F": False, "U": None}[label]
    (output / "reviewed-samples.json").write_text(
        json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "calibration-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pending_catalog = catalog_path.with_suffix(".json.tmp")
    pending_catalog.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pending_catalog.replace(catalog_path)
    print(
        json.dumps(
            {
                "categories": len(report),
                "reviewed": sum(r["status"] == "reviewed" for r in report),
                "limited": sum(r["status"] == "limited" for r in report),
            },
            ensure_ascii=False,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ai-url", default="http://127.0.0.1:8001")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument(
        "--review-labels",
        type=Path,
        help="Explicit T/F/U labels by category; applies reviewed defaults",
    )
    parser.add_argument(
        "--font",
        default="C:/Windows/Fonts/msyh.ttc",
        help="Font file for contact sheets",
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Append six fitting samples near the current thresholds to an existing 12-sample review",
    )
    parser.add_argument(
        "--boundary",
        action="store_true",
        help="Use boundary-prefixed contact sheet filenames (legacy option)",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.review_labels:
        apply_review(
            args.output,
            args.review_labels,
            Path(__file__).resolve().parents[1] / "app/service/clip_catalog.json",
        )
        return
    if args.data_dir is None:
        parser.error("--data-dir is required when generating contact sheets")
    catalog = load_catalog()
    previous = {}
    if args.refine:
        previous = {
            row["key"]: row
            for row in json.loads((args.output / "boundary-samples.json").read_text("utf-8"))
        }
    snapshot = requests.get(args.ai_url + "/ai/models", timeout=30).json()
    selected = snapshot["tasks"]["embedding"]["selected"]
    model = next(m for m in snapshot["models"] if m["id"] == selected)["runtimeName"]
    with engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT p.id, p.owner_id, p.file_path, v.embedding
            FROM image_vectors v JOIN photos p ON p.id=v.photo_id
            WHERE p.is_deleted=false AND p.file_type!='video' AND v.model_name=:model
            ORDER BY p.id"""),
            {"model": model},
        ).all()
    if len(rows) < 12:
        raise ValueError("Calibration requires at least 12 compatible images")
    vectors = np.asarray(
        [
            json.loads(r.embedding) if isinstance(r.embedding, str) else r.embedding
            for r in rows
        ],
        dtype=np.float32,
    )
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    cache = args.output / "text_vectors.json"
    texts = [s for c in catalog["categories"] for s in c["descriptions"]]
    if (
        cache.exists()
        and (cached := json.loads(cache.read_text("utf-8")))["texts"] == texts
        and cached["model"] == model
    ):
        encoded = cached["vectors"]
    else:
        encoded = []
        for start in range(0, len(texts), 32):
            resp = requests.post(
                args.ai_url + "/embedding/text",
                json={"texts": texts[start : start + 32], "model": model, "cache": True},
                timeout=180,
            )
            resp.raise_for_status()
            if resp.headers.get("X-Embedding-Model") != model:
                raise RuntimeError("Text embedding model identity was not confirmed")
            encoded.extend(resp.json())
            print("encoded", len(encoded), flush=True)
        cache.write_text(
            json.dumps({"model": model, "texts": texts, "vectors": encoded}),
            encoding="utf-8",
        )
    if (
        requests.get(args.ai_url + "/ai/config", timeout=30).json()["embedding"][
            "selected"
        ]
        != selected
    ):
        raise RuntimeError("Model changed during calibration")
    font = ImageFont.truetype(args.font, 15)
    small = ImageFont.truetype(args.font, 13)
    offset = 0
    samples = []
    all_scores = []
    for c in catalog["categories"]:
        proto = np.asarray(
            encoded[offset : offset + len(c["descriptions"])], dtype=np.float32
        )
        offset += len(proto)
        proto /= np.maximum(np.linalg.norm(proto, axis=1, keepdims=True), 1e-12)
        proto = proto.mean(0)
        proto /= np.linalg.norm(proto)
        scores = vectors @ proto
        all_scores.append(scores)
        # Top candidates and seeded score-stratified samples. Validation photos
        # are distinct from fitting photos and never participate in threshold search.
        indices = list(np.argsort(-scores)[:2])
        targets = [0.48, 0.44, 0.40, 0.36, 0.32, 0.28, 0.46, 0.42, 0.38, 0.34]
        rng = np.random.default_rng(20261112 + len(samples))
        for target in targets:
            order = np.argsort(np.abs(scores - target))[:100]
            choices = [int(i) for i in order if int(i) not in indices]
            indices.append(int(rng.choice(choices)))
        if args.refine:
            prior = previous[c["key"]]
            if prior["descriptions"] != c["descriptions"] or prior["model"] != model:
                raise ValueError("Refinement requires the same descriptions and model")
            if len(prior["samples"]) != 12:
                raise ValueError("Refinement requires an initial 12-sample review")
            indices = [sample["index"] for sample in prior["samples"]]
            if any(str(rows[s["index"]].id) != s["photo_id"] for s in prior["samples"]):
                raise ValueError("Development photo snapshot changed; regenerate samples")
            threshold = c["thresholds"][model]
            rng = np.random.default_rng(20261113 + len(samples))
            for delta in [-0.025, -0.015, -0.005, 0.005, 0.015, 0.025]:
                order = np.argsort(np.abs(scores - threshold - delta))[:100]
                choices = [int(i) for i in order if int(i) not in indices]
                indices.append(int(rng.choice(choices)))
        samples.append(
            {
                "key": c["key"],
                "name": c["name"],
                "model": model,
                "threshold": c["thresholds"].get(model),
                "max_score": float(scores.max()),
                "photos_scored": len(rows),
                "descriptions": c["descriptions"],
                "samples": [
                    {
                        "photo_id": str(rows[i].id),
                        "score": float(scores[i]),
                        "label": None,
                        "index": int(i),
                        "split": "validation" if 8 <= j < 12 else "train",
                    }
                    for j, i in enumerate(indices)
                ],
            }
        )
    np.savez_compressed(
        args.output / "scores.npz",
        scores=np.stack(all_scores),
        photo_ids=np.array([str(r.id) for r in rows]),
    )
    (
        args.output / "boundary-samples.json"
    ).write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    for gi, group in enumerate(catalog["groups"]):
        members = [
            (c, s)
            for c, s in zip(catalog["categories"], samples)
            if group in c["groups"]
        ]
        # Split to keep every cell legible without huge image rescaling.
        for part, start in enumerate(range(0, len(members), 4)):
            chunk = members[start : start + 4]
            category_height = 150 * ((len(chunk[0][1]["samples"]) + 5) // 6)
            board = Image.new("RGB", (1080, 50 + len(chunk) * category_height), "#eeeeee")
            draw = ImageDraw.Draw(board)
            draw.text(
                (8, 8),
                f"{gi + 1}. {group} / {part + 1}  9～12验证，其余样本拟合",
                font=font,
                fill="black",
            )
            for ri, (c, s) in enumerate(chunk):
                y = 50 + ri * category_height
                draw.text((5, y), c["name"], font=font, fill="black")
                for j, item in enumerate(s["samples"]):
                    x = (j % 6) * 180
                    cell_y = y + (j // 6) * 145
                    row = rows[item["index"]]
                    compact = str(row.id).replace("-", "")
                    candidates = [
                        args.data_dir
                        / "users"
                        / str(row.owner_id)
                        / "thumbnails"
                        / compact[:2]
                        / compact[2:4]
                        / f"{compact}-thumb.webp",
                        Path(row.file_path),
                    ]
                    thumb = next((p for p in candidates if p.exists()), None)
                    if thumb:
                        try:
                            with Image.open(thumb) as im:
                                cell = ImageOps.contain(im.convert("RGB"), (174, 110))
                                board.paste(cell, (x, cell_y + 22))
                        except Exception:
                            pass
                    draw.text(
                        (x + 3, cell_y + 132),
                        f"{j + 1}: {item['score']:.3f}",
                        font=small,
                        fill="black",
                    )
            board.save(
                args.output
                / f"{'boundary' if args.boundary else 'group'}-{gi + 1:02}-{part + 1}.jpg",
                quality=90,
            )
    print(
        json.dumps(
            {
                "model": model,
                "photos": len(rows),
                "categories": len(samples),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
