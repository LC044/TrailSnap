"""Keep an existing Agent run leased while a local coding/test command executes.

Uses RP_AGENT_API_URL and RP_AGENT_TOKEN from the environment. The run file is
the JSON response from claim_delivery_task/start_requirement_delivery; it holds
credentials and must remain outside version control. Never logs credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx


class RunLease:
    def __init__(self, client: httpx.Client, run: dict):
        self.client = client
        self.run_id = run["id"]
        self.attempt_id = run["attempt_id"]
        self.lease_token = run["lease_token"]

    def renew(self) -> None:
        """Read the current version, retry one lifecycle race, and fail closed."""
        for _ in range(2):
            response = self.client.get(f"/api/agent-runs/{self.run_id}")
            response.raise_for_status()
            current = response.json()["data"]
            if current["attempt_id"] != self.attempt_id or current["status"] != "running":
                raise RuntimeError("执行已暂停、结束或失效，停止本地命令")
            payload = {"attempt_id": self.attempt_id, "lease_token": self.lease_token,
                       "expected_state_version": current["state_version"]}
            # A transport retry uses exactly the same logical write and key.
            headers = {"Idempotency-Key": str(uuid.uuid4())}
            for attempt in range(2):
                try:
                    response = self.client.post(f"/api/agent-runs/{self.run_id}/heartbeat",
                                                json=payload, headers=headers)
                    break
                except httpx.TransportError:
                    if attempt:
                        raise
            if response.status_code == 409:
                continue
            response.raise_for_status()
            return
        raise RuntimeError("执行状态持续变化，无法续租")


def run_command(lease: RunLease, command: list[str], interval: float = 20) -> int:
    lease.renew()
    process = subprocess.Popen(command, start_new_session=os.name != "nt")
    try:
        next_renewal = time.monotonic() + interval
        while process.poll() is None:
            if time.monotonic() >= next_renewal:
                lease.renew()
                next_renewal = time.monotonic() + interval
            time.sleep(0.2)
        return process.returncode
    finally:
        if process.poll() is None:
            if os.name == "nt":
                # Terminate descendants too: coding commands often launch tools.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-file", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("必须在 -- 后提供编码或测试命令")
    token = os.environ.get("RP_AGENT_TOKEN")
    base_url = os.environ.get("RP_AGENT_API_URL")
    if not token or not base_url:
        parser.error("需要 RP_AGENT_TOKEN 和 RP_AGENT_API_URL 环境变量；使用现有令牌")
    run = json.loads(args.run_file.read_text(encoding="utf-8-sig"))
    with httpx.Client(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {token}"},
                      timeout=10) as client:
        try:
            return run_command(RunLease(client, run), command)
        except (httpx.HTTPError, RuntimeError):
            print("Agent 执行续租失败，本地命令已停止。请通过 get_run 检查状态。", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
