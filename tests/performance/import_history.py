"""Download the latest default-branch baseline from Actions artifacts, never Git."""
import argparse
import io
import json
import subprocess
import zipfile
from pathlib import Path


def gh(path, binary=False):
    data = subprocess.check_output(["gh", "api", path])
    return data if binary else json.loads(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    branch = gh(f"repos/{args.repository}")["default_branch"]
    # Filter before choosing: PR runs must never become scheduled baselines.
    runs = gh(f"repos/{args.repository}/actions/runs?branch={branch}&status=success&per_page=100")["workflow_runs"]
    for run in runs:
        if run["path"] != ".github/workflows/import-benchmark.yml" or run["event"] not in ("schedule", "workflow_dispatch", "push"):
            continue
        artifacts = gh(f"repos/{args.repository}/actions/runs/{run['id']}/artifacts")["artifacts"]
        for artifact in artifacts:
            if artifact["expired"] or not artifact["name"].startswith("import-benchmark-"):
                continue
            data = gh(f"repos/{args.repository}/actions/artifacts/{artifact['id']}/zip", binary=True)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                # Read only the known file; never extract arbitrary paths.
                (args.output / "result.json").write_bytes(archive.read("result.json"))
            print(f"Baseline: run {run['id']}, artifact {artifact['id']}")
            return
    print("No retained default-branch baseline; this run establishes a baseline.")


if __name__ == "__main__":
    main()
