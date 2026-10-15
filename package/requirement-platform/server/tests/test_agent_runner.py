import subprocess
import sys

import httpx
import pytest

from requirement_platform.agent_runner import RunLease, run_command


def test_lease_retries_state_conflict_and_reuses_key_on_transport_retry():
    posts = []
    gets = []

    def handle(request):
        if request.method == "GET":
            gets.append(request)
            return httpx.Response(200, json={"data": {"attempt_id": "attempt", "status": "running", "state_version": len(gets)}})
        posts.append(request)
        if len(posts) == 1:
            raise httpx.ReadTimeout("transient")
        if len(posts) == 2:
            return httpx.Response(409)
        return httpx.Response(200, json={"data": {}})

    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handle)) as client:
        lease = RunLease(client, {"id": "run", "attempt_id": "attempt", "lease_token": "secret"})
        lease.renew()
    assert len(gets) == 2 and len(posts) == 3
    assert posts[0].headers["Idempotency-Key"] == posts[1].headers["Idempotency-Key"]
    assert posts[1].headers["Idempotency-Key"] != posts[2].headers["Idempotency-Key"]


@pytest.mark.parametrize("status", ["waiting_input", "cancelled", "succeeded", "timed_out"])
def test_lease_refuses_inactive_run(status):
    def handle(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"data": {"attempt_id": "attempt", "status": status}})

    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(RuntimeError):
            RunLease(client, {"id": "run", "attempt_id": "attempt", "lease_token": "secret"}).renew()


def test_runner_stops_command_when_lease_is_lost(monkeypatch):
    children = []
    popen = subprocess.Popen

    def capture(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    class LostLease:
        calls = 0

        def renew(self):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("lost lease")

    monkeypatch.setattr("requirement_platform.agent_runner.subprocess.Popen", capture)
    with pytest.raises(RuntimeError, match="lost lease"):
        run_command(LostLease(), [sys.executable, "-c", "import time; time.sleep(30)"], interval=0)
    assert children[0].poll() is not None


def test_runner_preserves_command_exit_code():
    class Lease:
        def renew(self):
            pass

    assert run_command(Lease(), [sys.executable, "-c", "raise SystemExit(7)"]) == 7
