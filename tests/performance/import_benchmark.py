"""Isolated end-to-end import benchmark. Requires Python 3.10+ and Linux Docker."""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from scan_folder_benchmark import HttpApi, TaskEventStream, TaskEventTracker, ensure_admin_session

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads(Path(__file__).with_name("import-v1.json").read_text())
EXCLUDED = set(CONFIG["excluded_task_types"])
REQUIRED_FLAGS = {"basic", "metadata", "face", "ocr", "classification", "image_embedding"}


def command(*args, check=True, timeout=1200):
    result = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{args[0:3]} failed: {result.stderr[-3000:]} {result.stdout[-1000:]}")
    return result.stdout.strip()


def docker(*args, **kwargs):
    return command("docker", *args, **kwargs)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def inspect(name):
    return json.loads(docker("inspect", name))[0]


def wait_http(api, path="/health-check", timeout=600):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            return api.unwrap(api.get(path, timeout=10))
        except Exception as exc:
            error = exc
            time.sleep(2)
    raise TimeoutError(f"Service not ready: {error}")


def prepare_models(api, timeout=1200):
    manifest = api.get("/ai/models")
    selected = {manifest["tasks"][task]["selected"] for task in ("face", "ocr", "embedding", "classification")}
    for model in sorted(selected):
        deadline = time.monotonic() + timeout
        triggered = False
        while time.monotonic() < deadline:
            manifest = api.get("/ai/models")
            state = next(m for m in manifest["models"] if m["id"] == model)
            if state["status"] == "ready":
                break
            if triggered and state["status"] == "failed":
                raise RuntimeError(f"Model download failed: {state}")
            if not triggered:
                api.post(f"/ai/models/{model}/download")
                triggered = True
            time.sleep(3)
        else:
            raise TimeoutError(f"Model files not ready: {model}")
    return {"selected": sorted(selected), "manifest": manifest}


def validate_snapshot(snapshot, expected):
    """Completion requires durable processing flags as well as drained queues."""
    tasks = [t for t in snapshot["tasks"] if t["type"] not in EXCLUDED]
    failures = [t for t in tasks if t["status"] in {"failed", "cancelled"}]
    if failures:
        raise RuntimeError(f"Required tasks failed/cancelled: {failures}")
    pending = [t for t in tasks if t["status"] != "completed"]
    photos = snapshot["photos"]
    complete = len(photos) == expected and all(
        all(p["processed"].get(flag) is True for flag in
            (REQUIRED_FLAGS if p["file_type"] != "video" else {"basic", "metadata"}))
        and (p["width"] or 0) > 0 and (p["height"] or 0) > 0 for p in photos
    )
    scans = [t for t in tasks if t["type"] == "SCAN_FOLDER"]
    return bool(scans) and all(t["status"] == "completed" for t in scans) and not pending and complete


def prepare_dataset(path):
    if not path.exists():
        command("git", "clone", CONFIG["repository"], str(path))
    actual = command("git", "-C", str(path), "rev-parse", "HEAD")
    if actual != CONFIG["commit"]:
        raise RuntimeError(f"Dataset v1 requires {CONFIG['commit']}, found {actual}")
    if command("git", "-C", str(path), "status", "--porcelain"):
        raise RuntimeError("Dataset checkout has local changes")
    for folder in CONFIG["folders"]:
        if not (path / folder).is_dir():
            raise RuntimeError(f"Missing dataset folder: {folder}")
    return path


def run_profile(args, profile, repetition, dataset, output):
    limits = CONFIG["profiles"][profile]
    name = f"tsbench-{uuid.uuid4().hex[:10]}"
    network = name
    containers = []
    tracker = TaskEventTracker()
    stop = threading.Event()
    stream = None
    sample = dict(profile=profile, repetition=repetition, limits=limits, status="error",
                  started_at=datetime.now(timezone.utc).isoformat(), excluded_task_types=sorted(EXCLUDED))
    report = output / f"{profile}-{repetition}"
    report.mkdir(parents=True)
    try:
        docker("network", "create", network)
        for service, image in (("postgres", args.postgres_image), ("ai", args.ai_image), ("server", args.server_image)):
            container = f"{name}-{service}"
            containers.append(container)
            options = ["run", "-d", "--name", container, "--network", network, "--network-alias", service,
                       "--cpus", str(limits["cpus"] if service != "postgres" else 0.5),
                       "--memory", f"{limits['memory_gb_per_service'] if service != 'postgres' else 1}g",
                       "--memory-swap", f"{limits['memory_gb_per_service'] if service != 'postgres' else 1}g"]
            if service == "postgres":
                options += ["-e", "POSTGRES_USER=trailsnap", "-e", "POSTGRES_PASSWORD=trailsnap", "-e", "POSTGRES_DB=trailsnap"]
            elif service == "ai":
                options += ["-p", "127.0.0.1::8001", "-e", "MODEL_PATH=/app/data/models", "-e", "IDLE_TIMEOUT=86400",
                            "-v", f"{args.model_cache.resolve()}:/app/data/models",
                            "-e", "AI_MODEL_CATALOG_PATH=/benchmark-catalog.json",
                            "-v", f"{(output / 'model-catalog.json').resolve()}:/benchmark-catalog.json:ro"]
            else:
                options += ["-p", "127.0.0.1::8000", "-e", "DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap",
                            "-e", "RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap",
                            "-e", "AI_API_URL=http://ai:8001", "-e", "CI=false", "-e", "TZ=UTC",
                            "-v", f"{dataset.resolve()}:/benchmark-source:ro"]
            docker(*options, image)
            if service == "postgres":
                for _ in range(60):
                    if "accepting connections" in docker("exec", container, "pg_isready", "-U", "trailsnap", check=False):
                        break
                    time.sleep(1)
                else:
                    raise TimeoutError("PostgreSQL not ready")
        server = containers[-1]
        ai = containers[-2]
        def api_for(container, port):
            mapping = inspect(container)["NetworkSettings"]["Ports"][f"{port}/tcp"][0]
            return HttpApi(f"http://127.0.0.1:{mapping['HostPort']}")
        api = api_for(server, 8000)
        ai_api = api_for(ai, 8001)
        wait_http(api)
        wait_http(ai_api)
        sample["models"] = prepare_models(ai_api)
        # A fresh process per sample: model initialization is included in import time.
        # Downloaded model files are shared; downloads are reported by the model manifest.
        sample["images"] = {s: inspect(c)["Image"] for s, c in zip(("postgres", "ai", "server"), containers)}
        sample["docker_limits"] = {s: {k: inspect(c)["HostConfig"][k] for k in ("NanoCpus", "Memory", "MemorySwap")}
                                   for s, c in zip(("postgres", "ai", "server"), containers)}
        ensure_admin_session(api, "benchmark-admin", "Benchmark-pass-123!", "benchmark@example.com")
        groups = api.unwrap(api.get("/tasks/grouped-status"))
        if not groups:
            raise RuntimeError("Empty task categories")
        for group in sorted(groups, key=lambda g: g["category"] not in EXCLUDED):
            action = "pause" if group["category"] in EXCLUDED else "resume"
            api.unwrap(api.post(f"/tasks/categories/{group['category']}/{action}"))
        time.sleep(6)
        # Only the E2E smoke/p0 folders enter the measured library.
        docker("exec", server, "mkdir", "-p", "/benchmark-photos")
        for folder in CONFIG["folders"]:
            docker("exec", server, "cp", "-a", f"/benchmark-source/{folder}", "/benchmark-photos/")
        docker("cp", str(Path(__file__).with_name("import_expected.py")), f"{server}:/app/import_expected.py")
        expected_counts = json.loads(docker("exec", server, "python", "/app/import_expected.py"))
        expected = expected_counts["photos"]
        if not expected:
            raise RuntimeError("Dataset contains no media")
        sample["expected_files"] = expected_counts["files"]
        sample["expected_photos"] = expected
        docker("cp", str(Path(__file__).with_name("import_snapshot.py")), f"{server}:/app/import_snapshot.py")
        stream = TaskEventStream(api, tracker, stop)
        stream.start()
        if not stream.connected.wait(15):
            raise RuntimeError("SSE did not connect")
        start = time.monotonic()
        api.unwrap(api.post("/settings/directories", json_body={"path": "/benchmark-photos"}))
        sample["add_directory_seconds"] = time.monotonic() - start
        first_empty = None
        stable = 0
        last_progress = None
        with (report / "progress.jsonl").open("w", encoding="utf-8") as progress_file:
            while time.monotonic() - start < args.timeout:
                snapshot = json.loads(docker("exec", server, "python", "/app/import_snapshot.py", timeout=60))
                elapsed = time.monotonic() - start
                progress_file.write(json.dumps(dict(seconds=elapsed, tasks=snapshot["tasks"], photos=len(snapshot["photos"]))) + "\n")
                progress_file.flush()
                ready = validate_snapshot(snapshot, expected)
                stable = stable + 1 if ready else 0
                first_empty = (first_empty if first_empty is not None else elapsed) if ready else None
                progress = (len(snapshot["photos"]), snapshot["tasks"])
                if progress != last_progress:
                    print(f"[{profile}] {elapsed:.1f}s photos={len(snapshot['photos'])}/{expected} tasks={snapshot['tasks']}", flush=True)
                    last_progress = progress
                if stable >= 3:
                    sample.update(status="passed", total_seconds=round(first_empty, 3), confirmed_seconds=round(elapsed, 3),
                                  files_per_second=round(expected_counts["files"] / first_empty, 3), snapshot=snapshot)
                    break
                for c in containers:
                    state = inspect(c)["State"]
                    if not state["Running"] or state["OOMKilled"]:
                        raise RuntimeError(f"Container stopped/OOM: {c}: {state}")
                time.sleep(2)
            else:
                sample.update(status="timeout", snapshot=snapshot)
        sample["event_diagnostics"] = dict(parse_errors=tracker.parse_errors, stream_error=stream.last_error)
        records = tracker.snapshot()
        sample["task_samples"] = [r.to_sample() for r in records]
        with (report / "tasks.csv").open("w", newline="", encoding="utf-8") as f:
            rows = sample["task_samples"]
            if rows:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    except Exception as exc:
        sample["error"] = str(exc)
        print(f"[{profile}] ERROR {exc}", flush=True)
    finally:
        stop.set()
        for c in containers:
            logs = subprocess.run(["docker", "logs", c], capture_output=True, text=True, timeout=30)
            (report / f"{c.rsplit('-', 1)[-1]}.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
            docker("rm", "-fv", c, check=False)
        docker("network", "rm", network, check=False)
        if stream:
            stream.join(timeout=2)
        write_json(report / "result.json", sample)
    return sample


def summarize(result, baseline=None):
    lines = ["# TrailSnap 导入性能基准", "", f"数据集：{CONFIG['version']} / `{CONFIG['commit']}`", "",
             "范围：基础处理、元数据、人脸、OCR、分类、向量及派生任务；排除远程视觉描述、票据识别。",
             "每轮独立进程和空白库；计入模型加载，模型文件共享缓存。计时终点为首次验证完整完成的轮询，含最多一次采样延迟；三轮确认窗口另列。",
             "资源为每个 server/ai 容器分别限制；PostgreSQL 固定 0.5 CPU / 1 GiB；禁用 swap，不模拟磁盘或 GPU。", "",
             "| 档位 | CPU/服务 | 内存GiB/服务 | 成功/总轮数 | 中位耗时(s) | 基线变化 |", "|---|---:|---:|---:|---:|---:|"]
    for profile in CONFIG["profiles"]:
        samples = [s for s in result["samples"] if s["profile"] == profile]
        if not samples:
            continue
        passed = [s["total_seconds"] for s in samples if s["status"] == "passed"]
        median = statistics.median(passed) if len(passed) == len(samples) else None
        change = "无兼容基线"
        if baseline and baseline.get("comparison_key") == result["comparison_key"] and median:
            old = [s["total_seconds"] for s in baseline["samples"] if s["profile"] == profile and s["status"] == "passed"]
            if old:
                change = f"{(median / statistics.median(old) - 1) * 100:+.1f}%"
        limits = CONFIG["profiles"][profile]
        lines.append(f"| {profile} | {limits['cpus']} | {limits['memory_gb_per_service']} | {len(passed)}/{len(samples)} | {f'{median:.3f}' if median else '失败'} | {change} |")
    lines += ["", "单次测量只作为初始样本，不用于显著性或 P95 判断。结果按主机、数据集、镜像和场景兼容性比较；不兼容时建立新基线。"]
    for sample in result["samples"]:
        if sample.get("error"):
            lines += ["", f"- {sample['profile']}：{sample['error']}"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "tests/.cache/benchmark-photos")
    parser.add_argument("--output", type=Path, default=Path(os.environ["TS_PERF_OUTPUT"]) if os.environ.get("TS_PERF_OUTPUT") else ROOT / "tests/artifacts/import-benchmark" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--model-cache", type=Path, default=Path(os.environ["TS_PERF_MODEL_CACHE"]) if os.environ.get("TS_PERF_MODEL_CACHE") else ROOT / "tests/.cache/benchmark-models")
    parser.add_argument("--server-image", default="trailsnap-import-benchmark:local")
    parser.add_argument("--ai-image", default="siyuan044/trailsnap-ai:master")
    parser.add_argument("--postgres-image", default="siyuan044/pgvector:pg18-trixie")
    parser.add_argument("--profiles", nargs="+", choices=list(CONFIG["profiles"]), default=list(CONFIG["profiles"]))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--baseline", type=Path, default=Path(os.environ["TS_PERF_BASELINE"]) if os.environ.get("TS_PERF_BASELINE") else None)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    args.model_cache.mkdir(parents=True, exist_ok=True)
    result = dict(schema_version=1, dataset=CONFIG, commit=command("git", "rev-parse", "HEAD"),
                  host=dict(platform=platform.platform(), machine=platform.machine(), processor=platform.processor(), cpu_count=os.cpu_count(),
                            docker=json.loads(docker("info", "--format", "{{json .}}"))), samples=[])
    dataset = prepare_dataset(args.dataset)
    for image in (args.server_image, args.ai_image, args.postgres_image):
        if not docker("images", "-q", image):
            docker("pull", image)
    catalog = json.loads(docker("run", "--rm", "--entrypoint", "cat", args.ai_image, "/app/app/model_catalog.json"))
    # Excluded LLM downloads must not consume network/CPU during measured imports.
    for model in catalog["models"]:
        model["autoDownload"] = False
    write_json(args.output / "model-catalog.json", catalog)
    result["comparison_key"] = dict(dataset=CONFIG, host=os.environ.get("TS_PERF_MACHINE_ID", platform.node()),
        cpu=result["host"]["processor"], docker_cpus=result["host"]["docker"]["NCPU"],
        docker_memory=result["host"]["docker"]["MemTotal"], ai_image=json.loads(docker("image", "inspect", args.ai_image))[0]["Id"],
        postgres_image=json.loads(docker("image", "inspect", args.postgres_image))[0]["Id"], scenario="process-cold-model-files-cached-v1")
    baseline = json.loads(args.baseline.read_text()) if args.baseline and args.baseline.exists() else None
    for repetition in range(1, args.repetitions + 1):
        for profile in args.profiles:
            result["samples"].append(run_profile(args, profile, repetition, dataset, args.output))
            write_json(args.output / "result.json", result)
            (args.output / "report.md").write_text(summarize(result, baseline), encoding="utf-8")
    print((args.output / "report.md").read_text(encoding="utf-8"))
    return 0 if all(s["status"] == "passed" for s in result["samples"]) else 1


if __name__ == "__main__":
    sys.exit(main())
