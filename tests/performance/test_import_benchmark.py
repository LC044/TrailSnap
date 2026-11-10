import copy
import unittest

from import_benchmark import CONFIG, REQUIRED_FLAGS, summarize, validate_snapshot


class ImportBenchmarkTests(unittest.TestCase):
    def snapshot(self):
        return {"tasks": [{"type": "SCAN_FOLDER", "status": "completed", "count": 1}],
                "photos": [{"file_type": "image", "processed": dict.fromkeys(REQUIRED_FLAGS, True), "width": 10, "height": 10}]}

    def test_full_completion_requires_scan_and_durable_results(self):
        snapshot = self.snapshot()
        self.assertTrue(validate_snapshot(snapshot, 1))
        snapshot["photos"][0]["processed"]["ocr"] = False
        self.assertFalse(validate_snapshot(snapshot, 1))
        self.assertFalse(validate_snapshot(self.snapshot(), 2))
        snapshot = self.snapshot()
        snapshot["tasks"] = []
        self.assertFalse(validate_snapshot(snapshot, 1))

    def test_delayed_retry_and_unlisted_derived_tasks_block_completion(self):
        snapshot = self.snapshot()
        snapshot["tasks"].append({"type": "ASSOCIATE_JOURNEYS", "status": "pending", "count": 1})
        self.assertFalse(validate_snapshot(snapshot, 1))

    def test_failure_or_cancellation_never_passes(self):
        for status in ("failed", "cancelled"):
            snapshot = self.snapshot()
            snapshot["tasks"].append({"type": "OCR", "status": status, "count": 1})
            with self.assertRaises(RuntimeError):
                validate_snapshot(snapshot, 1)

    def test_only_declared_remote_tasks_are_excluded(self):
        snapshot = self.snapshot()
        snapshot["tasks"].append({"type": "VISUAL_DESCRIPTION", "status": "pending", "count": 1})
        self.assertTrue(validate_snapshot(snapshot, 1))

    def test_video_requires_basic_and_metadata(self):
        snapshot = self.snapshot()
        snapshot["photos"][0].update(file_type="video", processed={"basic": True, "metadata": True})
        self.assertTrue(validate_snapshot(snapshot, 1))

    def test_incompatible_baseline_and_partial_failure(self):
        current = {"comparison_key": "host-a", "samples": [{"profile": "low", "status": "passed", "total_seconds": 120}]}
        baseline = {"comparison_key": "host-b", "samples": [{"profile": "low", "status": "passed", "total_seconds": 100}]}
        self.assertIn("无兼容基线", summarize(current, baseline))
        baseline["comparison_key"] = "host-a"
        self.assertIn("+20.0%", summarize(current, baseline))
        current["samples"].append({"profile": "low", "status": "timeout"})
        self.assertIn("失败", summarize(current, baseline))


if __name__ == "__main__":
    unittest.main()
