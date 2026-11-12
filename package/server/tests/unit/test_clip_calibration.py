"""Calibration uses explicit labels and keeps validation out of threshold search."""

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


@pytest.fixture
def calibration_files(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/calibrate_clip.py"
    spec = importlib.util.spec_from_file_location("clip_calibration_script", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    category = {
        "key": "example", "name": "测试", "descriptions": ["测试图片"],
        "thresholds": {"test-model": 0.42},
    }
    samples = [{
        **category, "model": "test-model", "threshold": 0.42,
        "photos_scored": 123, "max_score": 0.6,
        "samples": [
            {"score": score, "split": "train" if i < 8 else "validation"}
            for i, score in enumerate([0.6, 0.55, 0.48, 0.44, 0.4, 0.36, 0.32, 0.28,
                                       0.46, 0.42, 0.38, 0.34])
        ],
    }]
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"categories": [category]}), encoding="utf-8")
    (tmp_path / "boundary-samples.json").write_text(json.dumps(samples), encoding="utf-8")
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"测试": "TTTTFFFFFFFF"}), encoding="utf-8")
    return module, tmp_path, labels, catalog


def test_validation_labels_do_not_select_threshold(calibration_files):
    module, output, labels, catalog = calibration_files
    module.apply_review(output, labels, catalog)
    first = json.loads(catalog.read_text("utf-8"))["categories"][0]
    labels.write_text(json.dumps({"测试": "TTTTFFFFTTTT"}), encoding="utf-8")
    module.apply_review(output, labels, catalog)
    second = json.loads(catalog.read_text("utf-8"))["categories"][0]
    assert first["thresholds"] == second["thresholds"]
    assert second["calibration"]["photos_scored"] == 123
    assert first["calibration"]["validation"] != second["calibration"]["validation"]


def test_changed_description_rejects_stale_review(calibration_files):
    module, output, labels, catalog = calibration_files
    data = json.loads(catalog.read_text("utf-8"))
    data["categories"][0]["descriptions"] = ["已经修改的描述"]
    catalog.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Descriptions changed"):
        module.apply_review(output, labels, catalog)
    assert json.loads(catalog.read_text("utf-8")) == data


def test_no_positive_evidence_is_limited(calibration_files):
    module, output, labels, catalog = calibration_files
    labels.write_text(json.dumps({"测试": "FFFFFFFFFFFF"}), encoding="utf-8")
    module.apply_review(output, labels, catalog)
    category = json.loads(catalog.read_text("utf-8"))["categories"][0]
    assert category["thresholds"]["test-model"] > 0.6
    assert category["calibration"]["status"] == "limited"
    assert category["calibration"]["no_positive_evidence"] is True


def test_overlapping_scores_keep_supported_positive_matches(calibration_files):
    module, output, labels, catalog = calibration_files
    sample_path = output / "boundary-samples.json"
    rows = json.loads(sample_path.read_text("utf-8"))
    for sample, score in zip(rows[0]["samples"], [0.4] * 4 + [0.5, 0.49, 0.3, 0.28]):
        sample["score"] = score
    sample_path.write_text(json.dumps(rows), encoding="utf-8")
    module.apply_review(output, labels, catalog)
    category = json.loads(catalog.read_text("utf-8"))["categories"][0]
    assert category["calibration"]["training"]["tp"] == 4
    assert category["calibration"]["status"] == "limited"
