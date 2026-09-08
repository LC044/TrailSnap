import os
import tempfile
import atexit
from pathlib import Path


TEST_DIR = tempfile.TemporaryDirectory()
os.environ["RP_DATABASE_URL"] = f"sqlite:///{Path(TEST_DIR.name) / 'requirements.db'}"
os.environ["RP_JWT_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["RP_GITHUB_TOKEN"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from requirement_platform.db import SessionLocal, engine  # noqa: E402
from requirement_platform.main import app  # noqa: E402
from requirement_platform.models import BackgroundJob, TriageReport  # noqa: E402
from requirement_platform.services import analyze_requirement  # noqa: E402


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

        owner = client.post(
            "/api/auth/login", json={"identifier": "owner@example.com", "password": "password123"}
        ).json()["data"]
        reviewed = client.post(
            f"/api/requirements/{created['id']}/review",
            headers=auth(owner["token"]),
            json={"action": "candidate", "reason": "保留私密信息", "priority": "normal", "risk_level": "medium"},
        )
        assert reviewed.status_code == 200
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
