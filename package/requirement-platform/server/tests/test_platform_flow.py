import base64
import json
import os
import tempfile
import atexit
from datetime import datetime, timezone
from pathlib import Path

import pytest


TEST_DIR = tempfile.TemporaryDirectory()
os.environ["RP_DATABASE_URL"] = f"sqlite:///{Path(TEST_DIR.name) / 'requirements.db'}"
os.environ["RP_JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["RP_GITHUB_TOKEN"] = ""
os.environ["RP_UPLOAD_DIR"] = str(Path(TEST_DIR.name) / "uploads")
os.environ["RP_WEB_URL"] = "https://feedback.trailsnap.cn"
os.environ["RP_MCP_PUBLIC_URL"] = "https://feedback.trailsnap.cn/mcp/"

from fastapi.testclient import TestClient  # noqa: E402

from requirement_platform.db import SessionLocal, engine  # noqa: E402
from requirement_platform.main import app  # noqa: E402
from requirement_platform import mcp_server  # noqa: E402
from requirement_platform.mcp_server import mcp_http_app  # noqa: E402
from requirement_platform.models import (  # noqa: E402
    AIConnection, AIModel, AITaskRoute, AgentRun, BackgroundJob, DeliveryTask, GitHubIdentity, IdempotencyRecord, Requirement,
    RequirementFollower, RequirementSpec, TriageReport,
)
from requirement_platform.services import (  # noqa: E402
    GitHubClient, _call_triage_ai, analyze_requirement, closing_issue_numbers, requirement_status_from_github,
)
from requirement_platform.ai_settings import AIModelTarget  # noqa: E402


def cleanup_database_handles():
    engine.dispose()
    TEST_DIR.cleanup()


atexit.register(cleanup_database_handles)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client: TestClient, username: str, email: str):
    response = client.post("/api/auth/register", json={"username": username, "email": email, "password": "password123"})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_complete_manual_requirement_and_batch_flow():
    with TestClient(app) as client:
        owner = register(client, "owner", "owner@example.com")
        viewer = register(client, "viewer", "viewer@example.com")
        assert owner["user"]["role"] == "owner"
        assert viewer["user"]["role"] == "viewer"

        created = client.post(
            "/api/requirements",
            headers=auth(viewer["token"]),
            json={
                "type": "feature",
                "title": "增加相册导出入口",
                "description": "希望能够从相册页面直接导出选中的照片。",
                "expected_behavior": "用户选择照片后可以导出。",
                "severity": "medium",
                "visibility": "public",
            },
        )
        assert created.status_code == 200, created.text
        requirement = created.json()["data"]
        assert requirement["status"] == "submitted"

        db = SessionLocal()
        try:
            report = analyze_requirement(db, requirement["id"])
            assert report.report["summary"]
            assert db.query(TriageReport).count() == 1
        finally:
            db.close()

        reviewed = client.post(
            f"/api/requirements/{requirement['id']}/review",
            headers=auth(owner["token"]),
            json={"action": "candidate", "reason": "符合产品方向", "priority": "high", "risk_level": "low"},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["data"]["status"] == "candidate"

        batch = client.post(
            "/api/versions",
            headers=auth(owner["token"]),
            json={"name": "相册体验改进", "version_name": "v0.15.0", "batch_type": "feature", "goal": "改善相册导出体验"},
        ).json()["data"]
        added = client.post(
            f"/api/versions/{batch['id']}/items",
            headers=auth(owner["token"]),
            json={"requirement_id": requirement["id"], "priority_order": 1},
        )
        assert added.status_code == 200, added.text
        assert len(added.json()["data"]["items"]) == 1

        locked = client.post(f"/api/versions/{batch['id']}/lock", headers=auth(owner["token"]))
        assert locked.status_code == 200, locked.text
        assert locked.json()["data"]["status"] == "scope_locked"

        updated = client.patch(
            f"/api/versions/{batch['id']}/items/{locked.json()['data']['items'][0]['id']}/status",
            headers=auth(owner["token"]),
            json={"status": "developing"},
        )
        assert updated.status_code == 200

        for batch_status, delivery_status in [
            ("developing", "testing"),
            ("testing", "completed"),
            ("release_ready", None),
            ("published", None),
            ("completed", None),
        ]:
            transition = client.patch(
                f"/api/versions/{batch['id']}/status",
                headers=auth(owner["token"]),
                json={"status": batch_status, "reason": "测试人工版本流转"},
            )
            assert transition.status_code == 200, transition.text
            if delivery_status:
                delivery = client.patch(
                    f"/api/versions/{batch['id']}/items/{locked.json()['data']['items'][0]['id']}/status",
                    headers=auth(owner["token"]),
                    json={"status": delivery_status},
                )
                assert delivery.status_code == 200, delivery.text
        assert transition.json()["data"]["status"] == "completed"

        db = SessionLocal()
        try:
            assert db.query(BackgroundJob).filter(BackgroundJob.job_type == "triage").count() == 1
            assert db.query(BackgroundJob).filter(BackgroundJob.job_type == "github_issue").count() == 1
            assert db.query(BackgroundJob).filter(BackgroundJob.job_type == "github_milestone").count() == 1
        finally:
            db.close()


def test_viewer_cannot_review_and_private_requirement_is_hidden():
    with TestClient(app) as client:
        viewer = client.post("/api/auth/login", json={"identifier": "viewer@example.com", "password": "password123"}).json()["data"]
        created = client.post(
            "/api/requirements",
            headers=auth(viewer["token"]),
            json={"type": "bug", "title": "私密问题报告", "description": "包含不应公开的诊断信息内容。", "visibility": "private"},
        ).json()["data"]
        public_rows = client.get("/api/requirements").json()["data"]
        assert created["id"] not in {row["id"] for row in public_rows}
        denied = client.post(
            f"/api/requirements/{created['id']}/review",
            headers=auth(viewer["token"]),
            json={"action": "candidate", "reason": "越权审核"},
        )
        assert denied.status_code == 403
        denied_status = client.patch(
            f"/api/requirements/{created['id']}/status",
            headers=auth(viewer["token"]),
            json={"status": "developing", "reason": "越权修改状态"},
        )
        assert denied_status.status_code == 403

        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        reviewed = client.post(
            f"/api/requirements/{created['id']}/review",
            headers=auth(owner["token"]),
            json={"action": "candidate", "reason": "保留私密信息", "priority": "normal", "risk_level": "medium"},
        )
        assert reviewed.status_code == 200
        developing = client.patch(
            f"/api/requirements/{created['id']}/status",
            headers=auth(owner["token"]),
            json={"status": "developing", "reason": "开始独立开发"},
        )
        assert developing.status_code == 200, developing.text
        assert developing.json()["data"]["status"] == "developing"
        reset_candidate = client.patch(
            f"/api/requirements/{created['id']}/status",
            headers=auth(owner["token"]),
            json={"status": "candidate", "reason": "继续验证版本排期流程"},
        )
        assert reset_candidate.status_code == 200, reset_candidate.text
        batch = client.post(
            "/api/versions",
            headers=auth(owner["token"]),
            json={"name": "私密修复", "version_name": "v0.15.1", "batch_type": "fix", "goal": "修复私密问题"},
        ).json()["data"]
        added = client.post(
            f"/api/versions/{batch['id']}/items",
            headers=auth(owner["token"]),
            json={"requirement_id": created["id"]},
        )
        assert added.status_code == 200
        public_batch = next(row for row in client.get("/api/versions").json()["data"] if row["id"] == batch["id"])
        assert public_batch["items"][0]["requirement_snapshot"]["title"] == "私密需求"

        db = SessionLocal()
        try:
            assert db.query(BackgroundJob).filter(
                BackgroundJob.job_type == "github_issue", BackgroundJob.object_id == created["id"]
            ).count() == 0
        finally:
            db.close()


def test_owner_can_manage_admin_role():
    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        users = client.get("/api/admin/users", headers=auth(owner["token"])).json()["data"]
        viewer = next(row for row in users if row["username"] == "viewer")
        promoted = client.patch(
            f"/api/admin/users/{viewer['id']}/role", headers=auth(owner["token"]), json={"role": "admin"}
        )
        assert promoted.status_code == 200
        assert promoted.json()["data"]["role"] == "admin"


def test_manager_github_soft_delete_agent_token_and_mcp(monkeypatch):
    with TestClient(app) as client:
        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        created = client.post(
            "/api/requirements", headers=auth(owner["token"]),
            json={"type": "feature", "title": "支持 Agent 管理需求", "description": "允许受控 Agent 读取并管理需求。"},
        ).json()["data"]

        monkeypatch.setattr(
            "requirement_platform.main.GitHubClient.get_issue",
            lambda _self, number: {"number": number, "html_url": f"https://github.com/LC044/TrailSnap/issues/{number}", "state": "open"},
        )
        linked = client.post(
            f"/api/requirements/{created['id']}/github/link", headers=auth(owner["token"]), json={"issue_number": 99991}
        )
        assert linked.status_code == 200, linked.text
        assert linked.json()["data"]["github_issue_number"] == 99991

        deleted = client.request(
            "DELETE", f"/api/requirements/{created['id']}", headers=auth(owner["token"]), json={"reason": "测试软删除"}
        )
        assert deleted.status_code == 200
        assert client.get(f"/api/requirements/{created['id']}").status_code == 404
        deleted_rows = client.get("/api/requirements?include_deleted=true", headers=auth(owner["token"])).json()["data"]
        assert created["id"] in {row["id"] for row in deleted_rows}
        assert client.post(f"/api/requirements/{created['id']}/restore", headers=auth(owner["token"])).status_code == 200

        token_response = client.post(
            "/api/admin/agent-tokens", headers=auth(owner["token"]),
            json={"name": "pytest MCP", "scopes": ["requirements:read"], "expires_in_days": 1},
        )
        assert token_response.status_code == 200, token_response.text
        mcp_token = token_response.json()["data"]["token"]

    with TestClient(mcp_http_app) as mcp_client:
        headers = {
            "Authorization": f"Bearer {mcp_token}",
            "Accept": "application/json, text/event-stream",
            "Host": "feedback.trailsnap.cn",
            "Origin": "https://feedback.trailsnap.cn",
        }
        initialized = mcp_client.post("/", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}},
        })
        assert initialized.status_code == 200, initialized.text
        tools = mcp_client.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert tools.status_code == 200, tools.text
        tool_names = {item["name"] for item in tools.json()["result"]["tools"]}
        assert {"list_requirements", "update_requirement_status", "create_version", "upload_requirement_attachment", "get_requirement_records",
                "sync_github_issues", "sync_github_milestone"} <= tool_names
        rejected = mcp_client.post(
            "/",
            headers={**headers, "Host": "attacker.example"},
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
        )
        assert rejected.status_code == 421


def test_mcp_requirement_version_attachment_and_records_flow(monkeypatch):
    """The MCP surface covers the same local requirement/version lifecycle as the REST API."""
    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        actor_id = owner["user"]["id"]
    actor = type("Actor", (), {"id": actor_id, "role": "owner"})()
    monkeypatch.setattr(mcp_server, "_identity", lambda _scope: (None, actor))

    created = mcp_server.create_requirement(**{
            "type": "bug", "title": "MCP 完整字段测试", "description": "验证 MCP 可写入完整需求字段和后续版本流程。",
            "log_text": "trace", "current_behavior": "当前失败", "expected_behavior": "预期成功",
            "steps_to_reproduce": "1. 调用", "product_version": "v0.1", "environment": {"os": "test"},
        })
    requirement_id = created["id"]
    requirement_reference = created["reference"]
    # 同步执行一次分析，让 get_requirement_triage 有数据可查（create 只是把 triage 任务入队）
    triage_db = SessionLocal()
    try:
        analyze_requirement(triage_db, requirement_id)
    finally:
        triage_db.close()
    updated = mcp_server.update_requirement(requirement_reference, title="MCP 公共编号写入测试")
    assert updated["title"] == "MCP 公共编号写入测试"
    mcp_server.upload_requirement_attachment(requirement_id, "trace.log", base64.b64encode(b"trace").decode())
    attachment_id = mcp_server.list_requirement_attachments(requirement_id)[0]["id"]
    assert mcp_server.download_requirement_attachment(requirement_id, attachment_id)["content_base64"] == base64.b64encode(b"trace").decode()
    mcp_server.review_requirement(requirement_reference, "candidate", "可纳入测试版本")
    changed = mcp_server.update_requirement_status(requirement_reference, "developing", "开始独立开发")
    assert changed["status"] == "developing"
    assert changed["review_reason"] == "开始独立开发"
    with pytest.raises(ValueError, match="无效的需求状态"):
        mcp_server.update_requirement_status(requirement_reference, "unknown", "测试未知状态")
    mcp_server.update_requirement_status(requirement_reference, "candidate", "继续验证版本排期流程")
    batch = mcp_server.create_version("MCP 测试版本", "mcp-test-1", "验证版本写入")
    version = mcp_server.add_version_requirement(batch["id"], requirement_id)
    item_id = version["items"][0]["id"]
    mcp_server.lock_version(batch["id"])
    mcp_server.update_version_delivery_status(batch["id"], item_id, "developing")
    mcp_server.update_version_status(batch["id"], "developing", "开始开发")
    assert mcp_server.get_version(batch["id"])["items"][0]["delivery_status"] == "developing"
    records = mcp_server.get_requirement_records(requirement_id)
    assert "history" in records and records["history"]
    # REQ-123 公共编号与 UUID 等价：按编号查询应返回同一份审计历史
    records_by_reference = mcp_server.get_requirement_records(requirement_reference)
    assert [event["id"] for event in records_by_reference["history"]] == [event["id"] for event in records["history"]]
    assert [item["id"] for item in mcp_server.list_requirement_attachments(requirement_reference)] == [item["id"] for item in mcp_server.list_requirement_attachments(requirement_id)]
    assert [report["id"] for report in mcp_server.get_requirement_triage(requirement_reference)] == [
        report["id"] for report in mcp_server.get_requirement_triage(requirement_id)]
    assert mcp_server.list_background_jobs(requirement_reference)
    mcp_server.set_requirement_following(requirement_reference, True)
    with SessionLocal() as follow_db:
        assert follow_db.query(RequirementFollower).filter(
            RequirementFollower.requirement_id == requirement_id).count() >= 1


def test_attachment_limits_and_private_access():
    with TestClient(app) as client:
        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        viewer = client.post(
            "/api/auth/login", json={"identifier": "viewer@example.com", "password": "password123"}
        ).json()["data"]
        created = client.post(
            "/api/requirements", headers=auth(viewer["token"]),
            json={"type": "bug", "title": "上传诊断日志附件", "description": "需要提供截图和日志帮助定位问题。", "log_text": "sanitized log"},
        ).json()["data"]
        uploaded = client.post(
            f"/api/requirements/{created['id']}/attachments", headers=auth(viewer["token"]),
            files={"file": ("error.log", b"stack trace", "text/plain")},
        )
        assert uploaded.status_code == 200, uploaded.text
        attachment_id = uploaded.json()["data"]["id"]
        assert client.get(
            f"/api/requirements/{created['id']}/attachments/{attachment_id}", headers=auth(viewer["token"])
        ).content == b"stack trace"
        assert client.get(
            f"/api/requirements/{created['id']}/attachments/{attachment_id}", headers=auth(owner["token"])
        ).status_code == 200
        assert client.get(f"/api/requirements/{created['id']}/attachments/{attachment_id}").status_code == 401
        too_large = client.post(
            f"/api/requirements/{created['id']}/attachments", headers=auth(viewer["token"]),
            files={"file": ("large.log", b"x" * (5 * 1024 * 1024 + 1), "text/plain")},
        )
        assert too_large.status_code == 413


def test_batch_update_closed_filter_and_dashboard_charts():
    with TestClient(app) as client:
        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        viewer = client.post(
            "/api/auth/login", json={"identifier": "viewer@example.com", "password": "password123"}
        ).json()["data"]

        batch = client.post(
            "/api/versions", headers=auth(owner["token"]),
            json={"name": "编辑前批次", "version_name": "v9.9.8", "batch_type": "feature", "goal": "验证版本编辑"},
        ).json()["data"]
        updated = client.patch(
            f"/api/versions/{batch['id']}", headers=auth(owner["token"]),
            json={"name": "编辑后批次", "target_date": "2026-10-01", "max_risk_level": "medium"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["name"] == "编辑后批次"
        assert updated.json()["data"]["target_date"] == "2026-10-01"
        assert updated.json()["data"]["max_risk_level"] == "medium"
        conflict = client.patch(
            f"/api/versions/{batch['id']}", headers=auth(owner["token"]), json={"version_name": "v0.15.0"}
        )
        assert conflict.status_code == 409
        unauthenticated = client.patch(f"/api/versions/{batch['id']}", json={"name": "未登录"})
        assert unauthenticated.status_code == 401

        closed = client.post(
            "/api/requirements", headers=auth(viewer["token"]),
            json={"type": "bug", "title": "列表关闭筛选验证需求", "description": "关闭后不应出现在默认列表中。"},
        ).json()["data"]
        client.post(f"/api/requirements/{closed['id']}/close", headers=auth(owner["token"]), json={"reason": "已处理完毕"})
        default_rows = client.get("/api/requirements", headers=auth(viewer["token"])).json()["data"]
        assert closed["id"] not in {row["id"] for row in default_rows}
        closed_rows = client.get(
            "/api/requirements?status=closed", headers=auth(viewer["token"])
        ).json()["data"]
        assert closed["id"] in {row["id"] for row in closed_rows}

        dashboard = client.get("/api/admin/dashboard", headers=auth(owner["token"])).json()["data"]
        assert len(dashboard["daily_new_30d"]) == 30
        assert dashboard["contributor_count"] >= 1
        assert isinstance(dashboard["top_contributors"], list)
        assert dashboard["follower_count"] >= 1


def test_manager_imports_github_issues(monkeypatch):
    with TestClient(app) as client:
        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        monkeypatch.setattr("requirement_platform.main.GitHubClient.list_issues", lambda _self: [{
            "number": 99992, "title": "从 GitHub 导入功能建议", "body": "这是从 GitHub Issue 导入的完整需求说明。",
            "html_url": "https://github.com/LC044/TrailSnap/issues/99992", "state": "closed",
            "labels": [{"name": "enhancement"}, {"name": "status: candidate"}],
        }])
        synced = client.post("/api/admin/github/issues/sync", headers=auth(owner["token"]))
        assert synced.status_code == 200, synced.text
        assert synced.json()["data"]["created"] == 1
        rows = client.get("/api/requirements?status=closed", headers=auth(owner["token"])).json()["data"]
        imported = next(row for row in rows if row["github_issue_number"] == 99992)
        assert imported["source"] == "github"
        assert imported["type"] == "feature"


def test_github_status_sync_preserves_unmanaged_labels(monkeypatch):
    requests = []

    def fake_request(_self, method, path, **kwargs):
        requests.append((method, path, kwargs))
        if method == "GET" and path.endswith("/issues/42"):
            return {"number": 42, "state": "open", "labels": [{"name": "bug"}, {"name": "status: submitted"}]}
        if method == "GET" and path.endswith("/labels"):
            return [{"name": "status: testing"}]
        return {"number": 42, "state": "open"}

    monkeypatch.setattr(GitHubClient, "_request", fake_request)
    GitHubClient().sync_status_label(42, "testing")
    patch_request = next(item for item in requests if item[0] == "PATCH")
    assert patch_request[2]["json"]["labels"] == ["bug", "status: testing"]
    assert patch_request[2]["json"]["state"] == "open"


def test_github_full_issue_sync_updates_content_and_preserves_custom_labels(monkeypatch):
    requests = []

    def fake_request(_self, method, path, **kwargs):
        requests.append((method, path, kwargs))
        if method == "GET" and path.endswith("/issues/42"):
            return {"number": 42, "state": "open", "labels": [
                {"name": "documentation"}, {"name": "bug"}, {"name": "status: submitted"},
            ]}
        if method == "GET" and path.endswith("/labels"):
            return [{"name": "status: testing"}]
        return {"number": 42, "state": "open"}

    monkeypatch.setattr(GitHubClient, "_request", fake_request)
    requirement = type("RequirementStub", (), {
        "github_issue_number": 42, "title": "新的标题", "description": "新的描述",
        "current_behavior": None, "expected_behavior": "新的期望", "review_reason": None,
        "type": "feature", "status": "testing", "public_number": 123,
    })()
    GitHubClient().sync_issue(requirement)
    payload = next(item for item in requests if item[0] == "PATCH")[2]["json"]
    assert payload["title"] == "新的标题"
    assert "新的描述" in payload["body"]
    assert payload["labels"] == ["documentation", "enhancement", "status: testing"]
    assert payload["state"] == "open"


def test_github_status_mapping_distinguishes_sync_echo_from_user_transition():
    assert requirement_status_from_github(
        {"state": "closed", "labels": [{"name": "status: released"}]}, "released", action="closed"
    ) == "released"
    assert requirement_status_from_github(
        {"state": "open", "labels": [{"name": "status: candidate"}]}, "candidate", action="reopened"
    ) == "candidate"
    assert requirement_status_from_github(
        {"state": "closed", "labels": [{"name": "status: candidate"}]}, "candidate", action="closed"
    ) == "closed"
    assert requirement_status_from_github(
        {"state": "open", "labels": [{"name": "status: closed"}]}, "closed", action="reopened"
    ) == "pending_review"


def test_github_closing_keyword_parser_ignores_plain_issue_mentions():
    pull_request = {
        "body": "关联需求 REQ-12，详情见 #10。\n\nCloses #42\nFixes LC044/TrailSnap#43\nresolves #44"
    }
    assert closing_issue_numbers(pull_request) == {42, 43, 44}


def test_github_webhook_updates_platform_status_with_actor_and_history(monkeypatch):
    with TestClient(app) as client:
        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        created = client.post(
            "/api/requirements", headers=auth(owner["token"]),
            json={"type": "feature", "title": "Webhook 状态同步测试", "description": "验证 GitHub 状态变化进入平台时间线。"},
        ).json()["data"]
        db = SessionLocal()
        try:
            row = db.query(Requirement).filter(Requirement.id == created["id"]).one()
            row.github_issue_number = 99993
            row.github_issue_url = "https://github.com/LC044/TrailSnap/issues/99993"
            row.github_state = "open"
            db.add(GitHubIdentity(user_id=owner["user"]["id"], github_user_id=123456789, login="octocat"))
            db.commit()
        finally:
            db.close()

        monkeypatch.setattr("requirement_platform.main.verify_webhook", lambda _body, _signature: True)
        headers = {"X-Hub-Signature-256": "sha256=test", "X-GitHub-Event": "issues"}
        closed = client.post("/api/hooks/github", headers={**headers, "X-GitHub-Delivery": "delivery-close"}, json={
            "action": "closed", "issue": {"number": 99993, "state": "closed", "labels": [{"name": "status: candidate"}]},
            "sender": {"id": 123456789, "login": "octocat"},
        })
        assert closed.status_code == 200, closed.text
        detail = client.get(f"/api/requirements/{created['id']}").json()["data"]
        assert detail["status"] == "closed"
        assert detail["github_state"] == "closed"

        reopened = client.post("/api/hooks/github", headers={**headers, "X-GitHub-Delivery": "delivery-reopen"}, json={
            "action": "reopened", "issue": {"number": 99993, "state": "open", "labels": [{"name": "status: closed"}]},
            "sender": {"id": 123456789, "login": "octocat"},
        })
        assert reopened.status_code == 200, reopened.text
        reopened_detail = client.get(f"/api/requirements/{created['id']}").json()["data"]
        assert reopened_detail["status"] == "pending_review"
        assert reopened_detail["github_state"] == "open"

        pull_request_headers = {
            "X-Hub-Signature-256": "sha256=test", "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "delivery-pr-merged",
        }
        merged = client.post("/api/hooks/github", headers=pull_request_headers, json={
            "action": "closed", "number": 321,
            "pull_request": {
                "number": 321, "title": "feat: 完成 Webhook 状态同步", "body": "Closes #99993",
                "html_url": "https://github.com/LC044/TrailSnap/pull/321", "state": "closed",
                "draft": False, "merged": True, "merged_at": "2026-09-10T01:00:00Z",
                "updated_at": "2026-09-10T01:00:00Z",
            },
            "sender": {"id": 123456789, "login": "octocat"},
        })
        assert merged.status_code == 200, merged.text
        detail = client.get(f"/api/requirements/{created['id']}").json()["data"]
        assert detail["status"] == "pending_review"
        assert detail["github_pull_requests"] == [{
            "number": 321, "title": "feat: 完成 Webhook 状态同步",
            "url": "https://github.com/LC044/TrailSnap/pull/321", "state": "merged",
            "draft": False, "merged_at": "2026-09-10T01:00:00Z", "updated_at": "2026-09-10T01:00:00Z",
        }]

        jobs = SessionLocal()
        try:
            assert jobs.query(BackgroundJob).filter(
                BackgroundJob.object_id == created["id"],
                BackgroundJob.idempotency_key == f"github_issue:{created['id']}:pr-merged:delivery-pr-merged",
            ).count() == 0
        finally:
            jobs.close()


def test_anonymous_number_history_dashboard_and_manager_edit():
    with TestClient(app) as client:
        response = client.post("/api/requirements", json={
            "type": "feature", "title": "匿名用户希望增加地图导出",
            "description": "希望可以把相册中的旅行轨迹导出为通用地图文件。",
            "submitter_name": "旅行者", "submitter_contact": "traveler@example.com",
        })
        assert response.status_code == 200, response.text
        created = response.json()["data"]
        assert created["public_number"] > 0
        assert created["created_by"] is None
        assert created["submitter_contact"] is None
        assert created["upload_token"]

        upload = client.post(
            f"/api/requirements/{created['id']}/attachments",
            headers={"X-Requirement-Upload-Token": created["upload_token"]},
            files={"file": ("details.txt", b"anonymous details", "text/plain")},
        )
        assert upload.status_code == 200, upload.text

        public_detail = client.get(f"/api/requirements/number/{created['public_number']}")
        assert public_detail.status_code == 200
        assert public_detail.json()["data"]["created_by_name"] == "旅行者"
        assert public_detail.json()["data"]["submitter_contact"] is None

        history = client.get(f"/api/requirements/{created['id']}/history")
        assert history.status_code == 200
        assert history.json()["data"][0]["action"] == "requirement.created"

        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        edited = client.patch(
            f"/api/requirements/{created['id']}", headers=auth(owner["token"]),
            json={"title": "管理员完善后的地图导出需求", "severity": "high"},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["data"]["submitter_contact"] == "traveler@example.com"

        dashboard = client.get("/api/admin/dashboard", headers=auth(owner["token"]))
        assert dashboard.status_code == 200
        assert dashboard.json()["data"]["anonymous"] >= 1


def test_triage_rerun_does_not_record_noop_status_change():
    """重新分析已处于待审核的需求时，时间线不应出现"由待审核变为待审核"。"""
    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        created = client.post(
            "/api/requirements", headers=auth(owner["token"]),
            json={"type": "bug", "title": "重新分析时间线测试", "description": "更新内容触发重新分析后，状态无变化时不应记录无意义的状态流转。"},
        ).json()["data"]
        requirement_id = created["id"]

        db = SessionLocal()
        try:
            first = analyze_requirement(db, requirement_id)
            assert first.report["summary"]
            rerun = analyze_requirement(db, requirement_id)
            assert rerun.report["summary"]
        finally:
            db.close()

        history = client.get(f"/api/requirements/{requirement_id}/history").json()["data"]
        triage_events = [event for event in history if event["action"] == "triage.completed"]
        assert len(triage_events) == 2
        first_event, second_event = triage_events
        assert (first_event["before"], first_event["after"]) == ("submitted", "needs_information")
        # 第二次分析状态未变化：不携带 before/after，前端不会渲染成"由待审核变为待审核"
        assert second_event["before"] is None
        assert second_event["after"] is None


# ---------------------------------------------------------------------------
# cc-switch 用量导入与统计
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_usage_tables():
    """用量统计是全局聚合，用例之间清空用量表避免相互累加。"""
    from requirement_platform.db import init_db
    from requirement_platform.usage_models import (
        UsageDailyRollup, UsageDevice, UsageImport, UsageProvider, UsageRequestLog,
    )

    init_db()  # 单独运行用例时 lifespan 尚未执行，先确保表存在
    db = SessionLocal()
    try:
        for model in (UsageRequestLog, UsageDailyRollup, UsageProvider, UsageImport, UsageDevice):
            db.query(model).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    yield


def _ccswitch_sql(
    *, rollups="", logs="", providers="('prov-1', 'claude', 'Zhipu GLM', '{}', 'custom')",
    with_semantics: bool = False,
) -> str:
    """构造一份最小 cc-switch 导出 SQL（rollups/logs 为空时省略对应 INSERT）。"""
    semantics_column = ', "input_token_semantics"' if with_semantics else ""
    semantics_schema = "input_token_semantics INTEGER NOT NULL DEFAULT 0," if with_semantics else ""
    rollup_stmt = (
        'INSERT INTO "usage_daily_rollups" ("date", "app_type", "provider_id", "model", "request_model", '
        '"pricing_model", "request_count", "success_count", "input_tokens", "output_tokens", '
        f'"cache_read_tokens", "cache_creation_tokens"{semantics_column}, "total_cost_usd") VALUES ' + rollups + ";"
        if rollups else ""
    )
    log_stmt = (
        'INSERT INTO "proxy_request_logs" ("request_id", "provider_id", "app_type", "model", "request_model", '
        f'"input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"{semantics_column}, "input_cost_usd", '
        '"output_cost_usd", "cache_read_cost_usd", "cache_creation_cost_usd", "total_cost_usd", "latency_ms", '
        '"status_code", "session_id", "data_source", "created_at") VALUES ' + logs + ";"
        if logs else ""
    )
    return f"""-- CC Switch SQLite 导出
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE providers (
    id TEXT NOT NULL, app_type TEXT NOT NULL, name TEXT NOT NULL,
    settings_config TEXT NOT NULL, website_url TEXT, category TEXT,
    PRIMARY KEY (id, app_type)
);
CREATE TABLE proxy_request_logs (
    request_id TEXT PRIMARY KEY, provider_id TEXT NOT NULL, app_type TEXT NOT NULL,
    model TEXT NOT NULL, request_model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0, cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    {semantics_schema}
    input_cost_usd TEXT NOT NULL DEFAULT '0', output_cost_usd TEXT NOT NULL DEFAULT '0',
    cache_read_cost_usd TEXT NOT NULL DEFAULT '0', cache_creation_cost_usd TEXT NOT NULL DEFAULT '0',
    total_cost_usd TEXT NOT NULL DEFAULT '0', latency_ms INTEGER NOT NULL, first_token_ms INTEGER,
    duration_ms INTEGER, status_code INTEGER NOT NULL, error_message TEXT, session_id TEXT,
    provider_type TEXT, is_streaming INTEGER NOT NULL DEFAULT 0,
    cost_multiplier TEXT NOT NULL DEFAULT '1.0', created_at INTEGER NOT NULL,
    data_source TEXT NOT NULL DEFAULT 'proxy'
);
CREATE TABLE usage_daily_rollups (
    date TEXT NOT NULL, app_type TEXT NOT NULL, provider_id TEXT NOT NULL,
    model TEXT NOT NULL, request_model TEXT NOT NULL DEFAULT '',
    pricing_model TEXT NOT NULL DEFAULT '', request_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0, cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0, {semantics_schema} total_cost_usd TEXT NOT NULL DEFAULT '0',
    avg_latency_ms INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, app_type, provider_id, model, request_model, pricing_model)
);
INSERT INTO "providers" ("id", "app_type", "name", "settings_config", "category") VALUES {providers};
{rollup_stmt}
{log_stmt}
COMMIT;
"""


def _rollup(date: str, model: str, count: int, cost: str, tokens_in: int = 1000, tokens_out: int = 200) -> str:
    return f"('{date}', 'claude', 'prov-1', '{model}', '', '', {count}, {count}, {tokens_in}, {tokens_out}, 0, 0, '{cost}')"


def _log(request_id: str, model: str, created_at: int, cost: str = "0.01",
         tokens_in: int = 100, tokens_out: int = 50) -> str:
    return (f"('{request_id}', 'prov-1', 'claude', '{model}', NULL, {tokens_in}, {tokens_out}, 0, 0, "
            f"'0.005', '0.005', '0', '0', '{cost}', 120, 200, 'sess-1', 'proxy', {created_at})")


def _semantic_log(
    request_id: str, app_type: str, created_at: int, *, tokens_in: int,
    tokens_out: int, cache_read: int, cache_creation: int, semantics: int,
) -> str:
    return (
        f"('{request_id}', 'prov-1', '{app_type}', 'test-model', NULL, {tokens_in}, {tokens_out}, "
        f"{cache_read}, {cache_creation}, {semantics}, '0', '0', '0', '0', '0', 120, 200, "
        f"'sess-1', 'proxy', {created_at})"
    )


# 2026-08-14 00:13 上海时间 = 1786637600 epoch（UTC 2026-08-13 16:13）
LOG_EPOCH = 1786637600


def _import_usage(client: TestClient, token: str, label: str, sql: str, filename: str = "export.sql"):
    return client.post(
        "/api/usage/imports",
        headers=auth(token),
        files={"file": (filename, sql.encode("utf-8"), "application/sql")},
        data={"device_label": label},
    )


def _usage_owner(client: TestClient) -> dict:
    """登录 owner；单独运行用例时用户可能尚未注册，注册即可（第一个注册用户自动成为 owner）。"""
    response = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"})
    if response.status_code == 200:
        return response.json()["data"]
    return register(client, "owner", "owner@example.com")


def _usage_viewer(client: TestClient) -> dict:
    response = client.post("/api/auth/login", json={"identifier": "viewer@example.com", "password": "password123"})
    if response.status_code == 200:
        return response.json()["data"]
    return register(client, "viewer", "viewer@example.com")


def _usage_plain_viewer(client: TestClient) -> dict:
    """专用 viewer：不复用 viewer@example.com（它会先被角色管理用例提升为 admin）。"""
    response = client.post("/api/auth/login", json={"identifier": "usage-viewer@example.com", "password": "password123"})
    if response.status_code == 200:
        return response.json()["data"]
    return register(client, "usage-viewer", "usage-viewer@example.com")


def test_usage_import_overview_and_daily(clean_usage_tables):
    sql = _ccswitch_sql(
        rollups=f"{_rollup('2026-04-27', 'glm-5.2', 10, '0.5')},{_rollup('2026-04-28', 'glm-5.2', 20, '1.0')}",
        logs=f"{_log('req-1', 'glm-5.2', LOG_EPOCH)},{_log('req-2', 'gpt-5.6-sol', LOG_EPOCH + 100, cost='0.02')}",
    )
    with TestClient(app) as client:
        owner = _usage_owner(client)
        response = _import_usage(client, owner["token"], "办公本", sql)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["detail_new"] == 2
        assert data["rollup_rows"] == 2
        assert data["date_min"] == "2026-04-27"
        # 明细日期按上海时区归并为 2026-08-14
        assert data["date_max"] == "2026-08-14"

        # 公开接口无需登录
        overview = client.get("/api/usage/overview")
        assert overview.status_code == 200, overview.text
        payload = overview.json()["data"]
        assert payload["device_count"] == 1
        # 总计 = rollup 30 请求 + 明细 2 请求
        assert payload["total"]["requests"] == 32
        # 成本 = 0.5 + 1.0 + 0.01 + 0.02
        assert abs(payload["total"]["total_cost_usd"] - 1.53) < 1e-6
        assert payload["total"]["date_from"] == "2026-04-27"
        models = {item["key"]: item for item in payload["by_model"]}
        assert models["glm-5.2"]["requests"] == 31
        assert models["gpt-5.6-sol"]["requests"] == 1
        providers = {item["key"]: item for item in payload["by_provider"]}
        assert providers["prov-1"]["label"] == "Zhipu GLM"

        daily = client.get("/api/usage/daily").json()["data"]
        by_date = {item["date"]: item for item in daily}
        assert by_date["2026-04-27"]["requests"] == 10
        assert by_date["2026-04-28"]["requests"] == 20
        assert by_date["2026-08-14"]["requests"] == 2
        # 补零：中间日期存在且为 0
        assert by_date["2026-04-29"]["requests"] == 0

        # 筛选：按模型
        filtered = client.get("/api/usage/daily", params={"model": "gpt-5.6-sol"}).json()["data"]
        filtered_total = sum(item["requests"] for item in filtered)
        assert filtered_total == 1
        # 筛选：按日期范围
        ranged = client.get("/api/usage/overview", params={"date_from": "2026-04-28", "date_to": "2026-04-28"}).json()["data"]
        assert ranged["total"]["requests"] == 20
        # 筛选可选值
        filters = client.get("/api/usage/filters").json()["data"]
        assert "glm-5.2" in filters["models"]
        assert "gpt-5.6-sol" in filters["models"]
        assert "claude" in filters["app_types"]


def test_usage_uses_ccswitch_real_token_semantics(clean_usage_tables):
    """真实消耗不重复计算缓存，并兼容 TOTAL/FRESH/LEGACY 三种输入语义。"""
    logs = ",".join([
        # Codex legacy：input 包含 cache read，但不保证包含 cache creation。
        _semantic_log("legacy", "codex", LOG_EPOCH, tokens_in=1000, tokens_out=50,
                      cache_read=600, cache_creation=100, semantics=0),
        # Codex TOTAL：input 包含两类缓存。
        _semantic_log("total", "codex", LOG_EPOCH + 1, tokens_in=1000, tokens_out=50,
                      cache_read=300, cache_creation=200, semantics=1),
        # FRESH：已经是新增输入，不再扣缓存。
        _semantic_log("fresh", "codex", LOG_EPOCH + 2, tokens_in=500, tokens_out=50,
                      cache_read=300, cache_creation=100, semantics=2),
        # Claude 输入天然为 fresh；即使是 legacy，也不扣 cache read。
        _semantic_log("claude", "claude", LOG_EPOCH + 3, tokens_in=200, tokens_out=50,
                      cache_read=5000, cache_creation=0, semantics=0),
    ])
    sql = _ccswitch_sql(logs=logs, with_semantics=True)

    with TestClient(app) as client:
        owner = _usage_owner(client)
        response = _import_usage(client, owner["token"], "语义测试", sql)
        assert response.status_code == 200, response.text

        total = client.get("/api/usage/overview").json()["data"]["total"]
        # fresh input = (1000-600) + (1000-300-200) + 500 + 200
        assert total["input_tokens"] == 1600
        assert total["output_tokens"] == 200
        assert total["cache_read_tokens"] == 6200
        assert total["cache_creation_tokens"] == 400
        assert total["input_total_tokens"] == 8200
        assert total["real_total_tokens"] == 8400
        assert abs(total["cache_hit_rate"] - (6200 / 8200)) < 1e-6

        daily = client.get("/api/usage/daily").json()["data"]
        point = next(item for item in daily if item["date"] == "2026-08-14")
        assert point["input_tokens"] == 1600


def test_usage_import_dedup_and_aging(clean_usage_tables):
    """同一设备二次导入：SHA 重复拒绝、request_id 跳过、rollup 覆盖、过期明细清理。"""
    with TestClient(app) as client:
        owner = _usage_owner(client)

        # 第一次导入：含 8 月明细（req-old-1/2）+ 4 月 rollup
        first_sql = _ccswitch_sql(
            rollups=_rollup("2026-04-27", "glm-5.2", 10, "0.5"),
            logs=f"{_log('req-old-1', 'glm-5.2', LOG_EPOCH)},{_log('req-old-2', 'glm-5.2', LOG_EPOCH + 50)}",
        )
        response = _import_usage(client, owner["token"], "家里台式机", first_sql)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["detail_new"] == 2

        # 同一文件再次导入 → 409
        dup = _import_usage(client, owner["token"], "家里台式机", first_sql)
        assert dup.status_code == 409

        # 第二次导入：rollup 已覆盖到 2026-08-14（旧明细日期），新明细是 8 月 15 日
        second_sql = _ccswitch_sql(
            rollups=f"{_rollup('2026-04-27', 'glm-5.2', 15, '0.7')},{_rollup('2026-08-14', 'glm-5.2', 2, '0.03')}",
            logs=f"{_log('req-old-1', 'glm-5.2', LOG_EPOCH)},{_log('req-new-1', 'glm-5.2', LOG_EPOCH + 86400)}",
        )
        response = _import_usage(client, owner["token"], "家里台式机", second_sql)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        # 旧明细 2 条（req-old-1/req-old-2，日期 2026-08-14 <= rollup 最大日期）被清理
        assert data["detail_aged_out"] == 2
        # 删除后重新插入 2 条（req-old-1 + req-new-1），无重复跳过
        assert data["detail_new"] == 2
        assert data["detail_dup"] == 0

        # rollup：4 月的 15 > 10 覆盖，8 月 14 新增
        assert data["rollup_rows"] == 2
        assert data["rollup_upserted"] == 1

        # 最终统计：请求 = 15 + 2（rollup）+ 2（明细），旧明细已并入 rollup 不双计
        overview = client.get("/api/usage/overview").json()["data"]
        assert overview["total"]["requests"] == 19
        assert abs(overview["total"]["total_cost_usd"] - (0.7 + 0.03 + 0.01 + 0.01)) < 1e-6


def test_usage_cross_device_merge_and_permissions(clean_usage_tables):
    """跨设备 rollup 求和、供应商名称映射、权限控制。"""
    device_a = _ccswitch_sql(
        rollups=_rollup("2026-04-27", "glm-5.2", 10, "0.5"),
        logs="",
    )
    device_b = _ccswitch_sql(
        rollups=_rollup("2026-04-27", "glm-5.2", 30, "1.5"),
        logs="",
        providers="('prov-1', 'claude', 'MiniMax', '{}', 'custom')",
    )
    with TestClient(app) as client:
        owner = _usage_owner(client)
        viewer = _usage_plain_viewer(client)

        first = _import_usage(client, owner["token"], "设备A", device_a)
        assert first.status_code == 200, first.text
        second = _import_usage(client, owner["token"], "设备B", device_b)
        assert second.status_code == 200, second.text

        # 两台设备同一天的 rollup 相加而非覆盖
        overview = client.get("/api/usage/overview").json()["data"]
        assert overview["total"]["requests"] == 40
        assert abs(overview["total"]["total_cost_usd"] - 2.0) < 1e-6
        assert overview["device_count"] == 2
        models = {item["key"]: item for item in overview["by_model"]}
        assert models["glm-5.2"]["requests"] == 40

        # viewer 不能导入、不能看导入列表，但可以看公开统计
        denied = _import_usage(client, viewer["token"], "设备A", device_a)
        assert denied.status_code == 403
        listing = client.get("/api/usage/imports", headers=auth(viewer["token"]))
        assert listing.status_code == 403
        public_overview = client.get("/api/usage/overview")
        assert public_overview.status_code == 200

        # 管理员删除设备 → 数据级联清空
        device_id = second.json()["data"]["device_id"]
        removed = client.delete(f"/api/usage/devices/{device_id}", headers=auth(owner["token"]))
        assert removed.status_code == 200, removed.text
        overview = client.get("/api/usage/overview").json()["data"]
        assert overview["total"]["requests"] == 10
        assert overview["device_count"] == 1


def test_usage_import_rejects_malicious_sql(clean_usage_tables):
    """authorizer 应拒绝 ATTACH 等危险语句。"""
    with TestClient(app) as client:
        owner = _usage_owner(client)
        malicious = _ccswitch_sql() + "\nATTACH DATABASE 'evil.db' AS evil;"
        response = _import_usage(client, owner["token"], "坏设备", malicious)
        assert response.status_code == 400

        # 单独的 ATTACH 也应被拒绝
        attach_only = "ATTACH DATABASE 'evil.db' AS evil;"
        response = _import_usage(client, owner["token"], "坏设备2", attach_only)
        assert response.status_code == 400
def _spec_content():
    return {
        "problem": "筛选变化后旧选择仍然存在，可能误操作不可见照片。",
        "user_scenario": "用户在照片列表选择照片后切换相册筛选。",
        "goal": "切换筛选后安全清理旧选择。",
        "confirmed_facts": ["当前选择状态由前端维护"],
        "references": ["REQ test"],
        "in_scope": ["照片筛选和选择状态"],
        "out_of_scope": ["批量删除语义"],
        "behavior_rules": ["筛选标识变化时清空选择"],
        "acceptance": [{"id": "AC-01", "given": "已选择照片", "when": "切换筛选",
                        "then": "选择数量归零", "required": True, "verification": "e2e"}],
        "test_data_requirements": ["selection-basic@1"],
        "environment_requirements": ["desktop and mobile viewport"],
        "constraints": ["使用统一主题色"], "risks": [], "dependencies": [],
        "release_requirements": [], "rollback_requirements": [], "blocking_questions": [],
        "assumptions": [], "repository": "LC044/TrailSnap", "target_branch": "master",
    }


def test_phase_a_spec_approval_and_phase_b_manual_agent_protocol(monkeypatch):
    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        created = client.post("/api/requirements", headers=auth(owner["token"]), json={
            "type": "improvement", "title": "筛选后清理选择状态",
            "description": "切换筛选条件后不能保留不可见照片的选择状态。",
            "expected_behavior": "切换筛选后选择数量归零。",
        }).json()["data"]
        monkeypatch.setattr("requirement_platform.delivery.GitHubClient.get_branch_sha", lambda _self, branch: "a" * 40)
        spec_response = client.post(f"/api/requirements/{created['id']}/specs",
            headers={**auth(owner["token"]), "Idempotency-Key": "create-spec-1"},
            json={"content": _spec_content(), "expected_requirement_state_version": created["state_version"]})
        assert spec_response.status_code == 200, spec_response.text
        spec = spec_response.json()["data"]
        approved_response = client.post(f"/api/specs/{spec['id']}/approve",
            headers={**auth(owner["token"]), "Idempotency-Key": "approve-spec-1"},
            json={"expected_state_version": spec["state_version"]})
        assert approved_response.status_code == 200, approved_response.text
        approved = approved_response.json()["data"]
        assert approved["status"] == "approved"
        assert approved["content"]["base_sha"] == "a" * 40

        task_response = client.post("/api/delivery-tasks",
            headers={**auth(owner["token"]), "Idempotency-Key": "create-task-1"},
            json={"spec_id": spec["id"], "risk_level": "low", "budget": {"minutes": 60}})
        assert task_response.status_code == 202, task_response.text
        task = task_response.json()["data"]
        assert task["context_bundle"]["content"]["spec"]["hash"] == approved["content_hash"]
        duplicate_task = client.post("/api/delivery-tasks",
            headers={**auth(owner["token"]), "Idempotency-Key": "create-task-1"},
            json={"spec_id": spec["id"], "risk_level": "low", "budget": {"minutes": 60}})
        assert duplicate_task.json()["data"]["id"] == task["id"]

        token_response = client.post("/api/admin/agent-tokens", headers=auth(owner["token"]), json={
            "name": "phase-b-codex", "scopes": ["specs:read", "tasks:claim", "runs:write"],
            "agent_role": "coding", "task_id": task["id"], "expires_in_days": 1,
        })
        assert token_response.status_code == 200, token_response.text
        agent_token = token_response.json()["data"]["token"]
        agent_headers = {"Authorization": f"Bearer {agent_token}", "Idempotency-Key": "claim-1"}
        claim = client.post("/api/agent-runs/claim", headers=agent_headers,
                            json={"runner_name": "local-codex", "provider": "codex", "role": "coding"})
        assert claim.status_code == 200, claim.text
        run = claim.json()["data"]
        repeated_claim = client.post("/api/agent-runs/claim", headers=agent_headers,
                            json={"runner_name": "local-codex", "provider": "codex", "role": "coding"})
        assert repeated_claim.json()["data"]["id"] == run["id"]
        assert repeated_claim.json()["data"]["lease_token"] == run["lease_token"]

        heartbeat_payload = {"attempt_id": run["attempt_id"], "lease_token": run["lease_token"],
                             "expected_state_version": run["state_version"], "session_reference": "codex-session-1"}
        heartbeat_headers = {"Authorization": f"Bearer {agent_token}", "Idempotency-Key": "heartbeat-1"}
        beat = client.post(f"/api/agent-runs/{run['id']}/heartbeat", headers=heartbeat_headers, json=heartbeat_payload)
        assert beat.status_code == 200, beat.text
        repeated_beat = client.post(f"/api/agent-runs/{run['id']}/heartbeat", headers=heartbeat_headers, json=heartbeat_payload)
        assert repeated_beat.json()["data"]["state_version"] == beat.json()["data"]["state_version"]

        plan_payload = {"attempt_id": run["attempt_id"], "lease_token": run["lease_token"],
            "expected_state_version": beat.json()["data"]["state_version"], "goal_summary": "清理过期选择状态",
            "scope_summary": "只修改照片筛选与选择状态", "acceptance_plan": {"AC-01": "新增端到端测试"},
            "affected_modules": ["package/website"], "migrations": [], "ambiguities": [],
            "out_of_scope": ["批量删除语义"]}
        plan = client.post(f"/api/agent-runs/{run['id']}/implementation-plan",
            headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": "plan-1"}, json=plan_payload)
        assert plan.status_code == 200, plan.text

        result_payload = {"attempt_id": run["attempt_id"], "lease_token": run["lease_token"],
            "expected_state_version": plan.json()["data"]["state_version"], "status": "succeeded",
            "summary": "实现完成", "changed_files": ["package/website/src/example.ts"],
            "acceptance_coverage": {"AC-01": "passed"}, "self_test_results": [{"name": "unit", "passed": True}],
            "head_sha": "b" * 40}
        result_headers = {"Authorization": f"Bearer {agent_token}", "Idempotency-Key": "result-1"}
        result = client.post(f"/api/agent-runs/{run['id']}/results", headers=result_headers, json=result_payload)
        assert result.status_code == 200, result.text
        repeated_result = client.post(f"/api/agent-runs/{run['id']}/results", headers=result_headers, json=result_payload)
        assert repeated_result.status_code == 200
        assert repeated_result.json()["data"]["id"] == run["id"]

        task_now = client.get(f"/api/delivery-tasks/{task['id']}", headers=auth(owner["token"])).json()["data"]
        monkeypatch.setattr("requirement_platform.delivery.GitHubClient.get_pull_request", lambda _self, number: {
            "number": number, "html_url": "https://github.com/LC044/TrailSnap/pull/123",
            "head": {"sha": "b" * 40}, "base": {"sha": "a" * 40, "ref": "master",
            "repo": {"full_name": "LC044/TrailSnap"}},
        })
        pr_payload = {"pull_request_number": 123, "url": "https://github.com/LC044/TrailSnap/pull/123",
                      "head_sha": "b" * 40, "base_sha": "a" * 40,
                      "covered_acceptance_ids": ["AC-01"], "expected_state_version": task_now["state_version"]}
        pr_headers = {"Authorization": f"Bearer {agent_token}", "Idempotency-Key": "link-pr-1"}
        linked = client.post(f"/api/delivery-tasks/{task['id']}/pull-requests", headers=pr_headers, json=pr_payload)
        assert linked.status_code == 200, linked.text
        repeated_link = client.post(f"/api/delivery-tasks/{task['id']}/pull-requests", headers=pr_headers, json=pr_payload)
        assert repeated_link.status_code == 200

        db = SessionLocal()
        try:
            assert db.query(RequirementSpec).filter(RequirementSpec.id == spec["id"]).one().status == "approved"
            assert db.query(DeliveryTask).filter(DeliveryTask.id == task["id"]).one().state == "pr_open"
            assert db.query(AgentRun).filter(AgentRun.id == run["id"]).one().status == "succeeded"
            assert db.query(IdempotencyRecord).filter(IdempotencyRecord.idempotency_key == "result-1").count() == 1
            claim_record = db.query(IdempotencyRecord).filter(IdempotencyRecord.idempotency_key == "claim-1").one()
            assert "lease_token" not in claim_record.response
        finally:
            db.close()


def test_requirement_content_change_revokes_approved_delivery_authorization(monkeypatch):
    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        created = client.post("/api/requirements", headers=auth(owner["token"]), json={
            "type": "improvement", "title": "验证规格修订边界",
            "description": "批准规格后修改需求正文时必须撤销旧执行授权。",
        }).json()["data"]
        monkeypatch.setattr("requirement_platform.delivery.GitHubClient.get_branch_sha", lambda _self, branch: "c" * 40)
        spec = client.post(f"/api/requirements/{created['id']}/specs",
            headers={**auth(owner["token"]), "Idempotency-Key": "revision-spec-create"},
            json={"content": _spec_content(), "expected_requirement_state_version": created["state_version"]}).json()["data"]
        approved = client.post(f"/api/specs/{spec['id']}/approve",
            headers={**auth(owner["token"]), "Idempotency-Key": "revision-spec-approve"},
            json={"expected_state_version": spec["state_version"]}).json()["data"]
        task = client.post("/api/delivery-tasks",
            headers={**auth(owner["token"]), "Idempotency-Key": "revision-task-create"},
            json={"spec_id": approved["id"]}).json()["data"]

        changed = client.patch(f"/api/requirements/{created['id']}", headers=auth(owner["token"]),
                               json={"description": "修改后的需求正文，需要重新批准规格。"})
        assert changed.status_code == 200, changed.text
        assert changed.json()["data"]["status"] == "submitted"

        db = SessionLocal()
        try:
            assert db.query(RequirementSpec).filter(RequirementSpec.id == approved["id"]).one().status == "superseded"
            revoked_task = db.query(DeliveryTask).filter(DeliveryTask.id == task["id"]).one()
            assert revoked_task.state == "cancelled"
            assert "旧执行授权已失效" in revoked_task.blocked_reason
        finally:
            db.close()


def test_registered_user_can_answer_structured_clarification():
    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        created = client.post("/api/requirements", headers=auth(owner["token"]), json={
            "type": "bug", "title": "缺少复现步骤的问题", "description": "导入一批照片以后页面没有显示预期结果。",
        }).json()["data"]
        db = SessionLocal()
        try:
            analyze_requirement(db, created["id"])
        finally:
            db.close()
        detail = client.get(f"/api/requirements/{created['id']}", headers=auth(owner["token"])).json()["data"]
        assert detail["status"] == "needs_information"
        assert detail["clarifications"]
        initial_revision = detail["content_revision"]
        answered = None
        for question in detail["clarifications"]:
            answered = client.post(f"/api/requirements/{created['id']}/clarifications/{question['question_id']}/answers",
                headers=auth(owner["token"]), json={"answer": "从相册页点击导入后打开照片列表。",
                                                     "expected_state_version": detail["state_version"]})
            assert answered.status_code == 200, answered.text
            detail = answered.json()["data"]
        assert answered is not None
        assert detail["status"] == "submitted"
        assert detail["content_revision"] == initial_revision + len(detail["clarifications"])


def test_anonymous_preflight_outage_does_not_block_submission():
    with TestClient(app) as client:
        payload = {"type": "feature", "title": "匿名提交仍然可用", "description": "即使分析模型当前不可用也应该能够直接保存需求。"}
        preflight = client.post("/api/requirements/preflight-triage", json=payload)
        assert preflight.status_code == 200
        assert preflight.json()["data"] == {"available": False, "questions": [], "reason": "ai_not_configured"}
        created = client.post("/api/requirements", json=payload)
        assert created.status_code == 200, created.text


def test_admin_can_manage_encrypted_ai_models_and_task_routes(monkeypatch):
    import httpx
    from requirement_platform.ai_settings import decrypt_api_key

    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        headers = auth(owner["token"])
        connection = client.post("/api/admin/ai-connections", headers=headers, json={
            "name": "primary-openai", "api_base": "https://ai-primary.invalid/v1",
            "api_key": "top-secret-api-key", "timeout_seconds": 12,
        })
        assert connection.status_code == 200, connection.text
        connection_data = connection.json()["data"]
        assert connection_data["api_key_hint"] == "••••-key"
        assert "api_key" not in connection_data

        primary = client.post(f"/api/admin/ai-connections/{connection_data['id']}/models", headers=headers,
                              json={"model_name": "primary-model", "display_name": "Primary"}).json()["data"]
        backup = client.post(f"/api/admin/ai-connections/{connection_data['id']}/models", headers=headers,
                             json={"model_name": "backup-model", "display_name": "Backup",
                                   "supports_json_mode": False}).json()["data"]
        route = client.put("/api/admin/ai-task-routes/preflight_triage", headers=headers,
                           json={"enabled": True, "model_ids": [primary["id"], backup["id"]],
                                 "reasoning_effort": "low"})
        assert route.status_code == 200, route.text
        assert route.json()["data"]["model_ids"] == [primary["id"], backup["id"]]
        assert route.json()["data"]["reasoning_effort"] == "low"

        calls = []
        def routed_analysis(payload, duplicates, target):
            calls.append((target.model_name, target.reasoning_effort))
            if target.model_name == "primary-model":
                raise httpx.ConnectError("primary unavailable")
            return {
                "schema_version": 2, "requirement_revision": 1, "context_bundle_id": None,
                "problem_summary": "备用模型分析成功", "summary": "备用模型分析成功", "category": payload["type"],
                "confirmed_facts": [], "hypotheses": [], "evidence_refs": [], "completeness_items": [],
                "blocking_questions": [], "nonblocking_questions": [], "duplicate_candidates": duplicates,
                "value_assessment": {}, "feasibility": "unknown", "affected_components": [], "risks": [],
                "effort_range": "unknown", "recommended_disposition": "pending_review", "acceptance_draft": [],
                "model": target.model_name, "prompt_version": "triage-v2", "knowledge_revision": None,
                "generated_at": datetime.now(timezone.utc).isoformat(), "fallback_reason": None,
            }
        monkeypatch.setattr("requirement_platform.services._call_triage_ai", routed_analysis)
        preflight = client.post("/api/requirements/preflight-triage", json={
            "type": "feature", "title": "验证模型路由切换", "description": "主模型不可用时应自动切换到备用模型。",
        })
        assert preflight.status_code == 200, preflight.text
        assert preflight.json()["data"]["available"] is True
        assert preflight.json()["data"]["model"] == "backup-model"
        assert calls == [("primary-model", "low"), ("backup-model", "low")]

        db = SessionLocal()
        try:
            stored = db.query(AIConnection).filter(AIConnection.id == connection_data["id"]).one()
            assert stored.api_key_encrypted != "top-secret-api-key"
            assert decrypt_api_key(stored.api_key_encrypted) == "top-secret-api-key"
            assert db.query(AIModel).filter(AIModel.connection_id == stored.id).count() == 2
            stored_route = db.query(AITaskRoute).filter(AITaskRoute.task_type == "preflight_triage").one()
            assert stored_route.model_ids == [primary["id"], backup["id"]]
            assert stored_route.reasoning_effort == "low"
        finally:
            db.close()


def test_late_triage_is_superseded_and_does_not_override_human_state(monkeypatch):
    from types import SimpleNamespace
    from requirement_platform import services as service_module

    with TestClient(app) as client:
        owner = client.post("/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}).json()["data"]
        created = client.post("/api/requirements", headers=auth(owner["token"]), json={
            "type": "feature", "title": "验证迟到分诊守卫", "description": "分诊期间发生编辑和人工决策时不能被旧结果覆盖。",
        }).json()["data"]

        target = SimpleNamespace(connection_id="test", provider="openai_compatible", model_name="test")
        monkeypatch.setattr(service_module, "resolve_model_targets", lambda _db, _task_type: [target])

        def delayed_result(payload, duplicates, _target):
            other = SessionLocal()
            try:
                row = other.query(Requirement).filter(Requirement.id == created["id"]).one()
                row.title = "管理员已经修改标题"
                row.content_revision += 1
                row.version += 1
                row.state_version += 1
                row.status = "candidate"
                other.commit()
            finally:
                other.close()
            return {
                "schema_version": 2, "requirement_revision": payload["content_revision"], "context_bundle_id": None,
                "problem_summary": "旧摘要", "summary": "旧摘要", "category": "feature", "confirmed_facts": [],
                "hypotheses": [], "evidence_refs": [], "completeness_items": [], "blocking_questions": [],
                "nonblocking_questions": [], "duplicate_candidates": duplicates, "value_assessment": {},
                "feasibility": "unknown", "affected_components": [], "risks": [], "effort_range": "unknown",
                "recommended_disposition": "pending_review", "acceptance_draft": [], "model": "test",
                "prompt_version": "triage-v2", "knowledge_revision": None,
                "generated_at": datetime.now(timezone.utc).isoformat(), "fallback_reason": None,
            }

        monkeypatch.setattr(service_module, "_call_triage_ai", delayed_result)
        db = SessionLocal()
        try:
            report = analyze_requirement(db, created["id"])
            assert report.status == "superseded"
        finally:
            db.close()
        detail = client.get(f"/api/requirements/{created['id']}", headers=auth(owner["token"])).json()["data"]
        assert detail["status"] == "candidate"
        assert detail["title"] == "管理员已经修改标题"


def _test_ai_target() -> AIModelTarget:
    return AIModelTarget(
        connection_id="test", connection_name="Test", provider="openai_compatible",
        api_base="http://example.test/v1", api_key="", model_id="test-model",
        model_name="test-model", supports_json_mode=True, timeout_seconds=5,
    )


def test_triage_ai_normalizes_common_model_field_names(monkeypatch):
    response = {
        "analysis_steps": ["检查需求目标", "判断信息完整度"],
        "form_updates": {"expected_behavior": "提交时实时展示 AI 输出", "unknown_field": "ignore"},
        "facts": ["用户希望看到分析过程"],
        "assumptions": ["当前界面缺少反馈"],
        "blocking_questions": [], "non_blocking_questions": [],
        "recommended_disposition": "pending_review",
    }
    monkeypatch.setattr("requirement_platform.services.request_chat_completion", lambda *_args, **_kwargs: json.dumps(response, ensure_ascii=False))
    report = _call_triage_ai(
        {"type": "improvement", "title": "展示 AI 分析输出", "description": "提交需求时实时展示模型返回的内容。", "content_revision": 1},
        [], _test_ai_target(),
    )
    assert report["problem_summary"] == "展示 AI 分析输出"
    assert report["category"] == "improvement"
    assert report["confirmed_facts"][0]["statement"] == "用户希望看到分析过程"
    assert report["hypotheses"][0]["statement"] == "当前界面缺少反馈"
    assert report["analysis_steps"] == ["检查需求目标", "判断信息完整度"]
    assert report["form_updates"] == {"expected_behavior": "提交时实时展示 AI 输出"}


def test_triage_ai_retries_after_invalid_output(monkeypatch):
    responses = iter([
        "not-json",
        json.dumps({
            "problem_summary": "提交时展示 AI 的实时分析输出",
            "category": "feature", "blocking_questions": [], "nonblocking_questions": [],
            "recommended_disposition": "pending_review",
        }, ensure_ascii=False),
    ])
    calls = []

    def fake_completion(_target, messages, *, json_mode):
        calls.append(messages.copy())
        return next(responses)

    monkeypatch.setattr("requirement_platform.services.request_chat_completion", fake_completion)
    report = _call_triage_ai(
        {"type": "feature", "title": "流式展示 AI 输出", "description": "用户可以看到模型正在生成的内容。", "content_revision": 1},
        [], _test_ai_target(),
    )
    assert report["problem_summary"] == "提交时展示 AI 的实时分析输出"
    assert len(calls) == 2
    assert "未通过结构校验" in calls[1][-1]["content"]
    assert "所有面向用户的文字必须使用简体中文" in calls[0][0]["content"]
