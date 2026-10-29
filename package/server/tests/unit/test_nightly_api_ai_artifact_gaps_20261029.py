"""2026-10-29 nightly gap tests for the AI artifact router (app/api/ai_artifact.py).

The router is called directly; ``artifact_crud`` and the thumbnail resolver
are patched so neither a database nor real thumbnails are required.

Covered gaps:
* ``_structured_html`` ignores malformed sections.
* ``_portable_html`` falls back to the ``small`` thumbnail, skips missing
  files, honours the 30 MiB budget, swallows IO errors and wraps documents
  that have no ``<head>``.
* ``export`` / ``share`` / ``revoke`` / ``update`` all answer 404 when the
  artifact does not belong to the caller.
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import ai_artifact as artifact_api
from app.db.models.ai_artifact import AIArtifact
from app.schemas.ai_artifact import AIArtifactUpdate


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _artifact(user_id=None, **overrides):
    user_id = user_id or uuid4()
    data = dict(
        id=uuid4(),
        user_id=user_id,
        artifact_type="travel_story",
        title="九寨沟流水账",
        content_json={"summary": "秋天很美", "sections": [{"heading": "湖", "body": "蓝色的水"}]},
        html_content=None,
        html_config={"style_name": "editorial"},
        source_photo_ids=[],
        source_ticket_ids=[],
        status="draft",
        version=1,
        created_by_session_id=None,
        created_at=datetime(2026, 10, 1, 8, 0, 0),
        updated_at=datetime(2026, 10, 2, 8, 0, 0),
    )
    data.update(overrides)
    return AIArtifact(**data)


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


# ----------------------- _structured_html -----------------------


def test_structured_html_skips_non_dict_sections():
    """Malformed section entries are ignored instead of crashing the export."""
    row = _artifact(content_json={
        "summary": "混排",
        "sections": ["not-a-dict", 42, {"heading": "湖", "body": "蓝色的水"}],
    })

    html = artifact_api._structured_html(row)

    assert "not-a-dict" not in html
    assert "42" not in html
    assert "湖" in html


def test_structured_html_uses_section_fallbacks():
    """``title`` / ``location`` / default heading and ``narrative`` body are supported."""
    row = _artifact(content_json={
        "summary": "",
        "sections": [
            {"title": "备用标题", "narrative": "备用正文"},
            {"location": "备用地点", "story": "另一个正文"},
            {},
        ],
    })

    html = artifact_api._structured_html(row)

    assert "备用标题" in html
    assert "备用正文" in html
    assert "备用地点" in html
    assert "另一个正文" in html
    assert "旅途片段" in html


# ----------------------- _portable_html -----------------------


def test_portable_html_falls_back_to_small_thumbnail(tmp_path):
    """When the medium thumbnail is gone the ``small`` variant is embedded."""
    user_id = uuid4()
    photo_id = uuid4()
    small = tmp_path / "small.jpg"
    small.write_bytes(b"tiny-image")
    row = _artifact(user_id=user_id, source_photo_ids=[str(photo_id)],
                    html_content=f'<html><head></head><body><img src="/api/medias/{user_id}/{photo_id}/thumbnail?size=medium"></body></html>')

    def fake_path(_user_id, _photo_id, _db, size):
        return str(tmp_path / f"{size}.jpg") if size == "small" else str(tmp_path / "missing.jpg")

    with patch.object(artifact_api, "_get_thumbnail_path", side_effect=fake_path):
        html = artifact_api._portable_html(row, MagicMock())

    assert "data:image/jpeg;base64," in html
    assert f"{user_id}/{photo_id}/thumbnail" not in html


def test_portable_html_skips_photo_without_any_thumbnail(tmp_path):
    """A photo without any thumbnail file is simply left as a URL."""
    user_id = uuid4()
    photo_id = uuid4()
    row = _artifact(user_id=user_id, source_photo_ids=[str(photo_id)],
                    html_content=f'<html><head></head><body><img src="/api/medias/{user_id}/{photo_id}/thumbnail"></body></html>')

    with patch.object(artifact_api, "_get_thumbnail_path", return_value=str(tmp_path / "nope.jpg")):
        html = artifact_api._portable_html(row, MagicMock())

    assert f"{user_id}/{photo_id}/thumbnail" in html
    assert "base64," not in html


def test_portable_html_stops_when_budget_exceeded(tmp_path):
    """Embedding stops before the portable document exceeds its size budget."""
    user_id = uuid4()
    photo_ids = [str(uuid4()) for _ in range(2)]
    big = tmp_path / "medium.jpg"
    big.write_bytes(b"x" * 1024)
    row = _artifact(user_id=user_id, source_photo_ids=photo_ids,
                    html_content="<html><head></head><body></body></html>")

    def fake_path(_user_id, _photo_id, _db, _size):
        return str(big)

    with patch.object(artifact_api, "_get_thumbnail_path", side_effect=fake_path):
        with patch.object(artifact_api, "MAX_PORTABLE_HTML_BYTES", 10):
            html = artifact_api._portable_html(row, MagicMock())

    assert "base64," not in html


def test_portable_html_ignores_io_errors(tmp_path):
    """A failing thumbnail read must not break the whole export."""
    user_id = uuid4()
    photo_id = uuid4()
    row = _artifact(user_id=user_id, source_photo_ids=[str(photo_id)],
                    html_content=f'<html><head></head><body><img src="/api/medias/{user_id}/{photo_id}/thumbnail"></body></html>')

    def boom(*_args, **_kwargs):
        raise OSError("disk gone")

    with patch.object(artifact_api, "_get_thumbnail_path", side_effect=boom):
        html = artifact_api._portable_html(row, MagicMock())

    assert "<head>" in html
    assert "Content-Security-Policy" in html


def test_portable_html_wraps_document_without_head(tmp_path):
    """A fragment without ``<head>`` gets a full document shell with the CSP."""
    row = _artifact(html_content="<p>只有一个片段</p>")

    html = artifact_api._portable_html(row, MagicMock())

    assert html.startswith("<!doctype html><html><head>")
    assert "Content-Security-Policy" in html
    assert "<p>只有一个片段</p>" in html


def test_portable_html_injects_policy_into_existing_head(tmp_path):
    """Existing documents get the CSP meta tag injected after ``<head>``."""
    row = _artifact(html_content="<html><head><title>t</title></head><body>b</body></html>")

    html = artifact_api._portable_html(row, MagicMock())

    assert html.index("Content-Security-Policy") < html.index("<title>")


# ----------------------- export / share / revoke / update -----------------------


def test_export_artifact_html_returns_404_when_missing():
    """Exporting an artifact that is not owned by the caller is a 404."""
    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            artifact_api.export_artifact_html(
                artifact_id=str(uuid4()), current_user=_user(), db=MagicMock()
            )

    assert excinfo.value.status_code == 404


def test_export_artifact_html_sets_attachment_headers(tmp_path):
    """The export response carries the download disposition and no-referrer."""
    row = _artifact(title="九寨沟")
    user = _user()

    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=row):
        response = artifact_api.export_artifact_html(
            artifact_id=str(row.id), current_user=user, db=MagicMock()
        )

    assert response.media_type == "text/html; charset=utf-8"
    assert "attachment" in response.headers["Content-Disposition"]
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_share_artifact_returns_404_when_missing():
    """Sharing an unknown artifact is a 404."""
    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            artifact_api.share_artifact(
                artifact_id=str(uuid4()), current_user=_user(), db=MagicMock()
            )

    assert excinfo.value.status_code == 404


def test_share_artifact_stores_token_hash():
    """The share config keeps only the hash of the secret."""
    row = _artifact()
    user = _user()
    db = MagicMock()

    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=row):
        with patch.object(artifact_api.secrets, "token_urlsafe", return_value="s3cret"):
            response = artifact_api.share_artifact(
                artifact_id=str(row.id), current_user=user, db=db
            )

    share = row.html_config["share"]
    assert share["enabled"] is True
    assert share["token_hash"] == artifact_api._share_digest("s3cret")
    assert response.data["share_path"].endswith(f"{row.id}.s3cret")
    db.commit.assert_called()


def test_revoke_artifact_share_returns_404_when_missing():
    """Revoking a share of an unknown artifact is a 404."""
    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            artifact_api.revoke_artifact_share(
                artifact_id=str(uuid4()), current_user=_user(), db=MagicMock()
            )

    assert excinfo.value.status_code == 404


def test_revoke_artifact_share_removes_share_config():
    """Revoking removes the share block but keeps the other config keys."""
    row = _artifact(html_config={"style_name": "editorial", "share": {"enabled": True}})
    db = MagicMock()

    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=row):
        response = artifact_api.revoke_artifact_share(
            artifact_id=str(row.id), current_user=_user(), db=db
        )

    assert response.data == {"revoked": True}
    assert "share" not in row.html_config
    assert row.html_config["style_name"] == "editorial"


def test_update_artifact_returns_404_when_missing():
    """Updating an unknown artifact is a 404."""
    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            artifact_api.update_artifact(
                artifact_id=str(uuid4()),
                payload=AIArtifactUpdate(title="新标题"),
                current_user=_user(),
                db=MagicMock(),
            )

    assert excinfo.value.status_code == 404


def test_update_artifact_returns_serialized_row():
    """The update endpoint returns the serialized artifact."""
    row = _artifact()
    db = MagicMock()

    with patch.object(artifact_api.artifact_crud, "get_owned", return_value=row):
        with patch.object(artifact_api.artifact_crud, "update", return_value=row) as update_call:
            response = artifact_api.update_artifact(
                artifact_id=str(row.id),
                payload=AIArtifactUpdate(title="新标题"),
                current_user=_user(),
                db=db,
            )

    update_call.assert_called_once()
    assert response.code == 0
    assert response.data["title"] == "九寨沟流水账"
    assert response.data["status"] == "draft"


def test_shared_artifact_requires_token_shape():
    """A share token without the ``id.secret`` shape is a 404."""
    with pytest.raises(HTTPException) as excinfo:
        artifact_api.get_shared_artifact(share_token="no-dot-here", db=MagicMock())

    assert excinfo.value.status_code == 404
