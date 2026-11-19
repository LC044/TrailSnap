"""Nightly gap coverage (2026-11-16) - app/api/clip_classification.py.

The 2026-11-16 backend coverage scan reported ``api/clip_classification.py``
at 80.1% - the lowest coverage of any backend module - with 34 uncovered
lines.  The router is brand new (owner scoped, editable zero-shot CLIP
categories) and the nightly scan had never touched it.

The gaps sit in the error and side-effect branches of the router:

* ``53`` / ``68``   - the pydantic validators that reject a blank name and an
  out-of-range threshold.
* ``103``           - enabling categories queues a rebuild task.
* ``111-123``       - ``queue_rebuild`` itself.
* ``167-169``       - a failing preset bootstrap degrades to a 400 answer.
* ``178-203``       - preview: success, a domain error and an unexpected error.
* ``223`` / ``231`` - the two "name already taken" conflicts.
* ``282`` / ``292`` - the create / update entry points.
* ``301-309``       - rebuild, including the not-owned category error.
* ``326-328``       - deleting a category that is not owned.

Everything is stubbed: the database is a ``MagicMock`` and the service layer
is patched, so the file stays a pure router-contract test.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api import clip_classification as clip_api


pytestmark = pytest.mark.smoke


def _user():
    return SimpleNamespace(id=uuid4(), is_superuser=False)


def _rule(**overrides):
    payload = {
        "name": "Seaside",
        "descriptions": ["beach"],
        "reference_images": [],
        "groups": ["Custom"],
        "strictness": "standard",
        "thresholds": {"score": 0.5},
        "enabled": False,
    }
    payload.update(overrides)
    return clip_api.RuleInput(**payload)


# --------------------------------------------------------------------------- #
# Payload validation
# --------------------------------------------------------------------------- #

def test_blank_name_is_rejected():
    """A name that is only whitespace must not reach the service layer."""
    with pytest.raises(ValidationError):
        _rule(name="   ")


def test_threshold_outside_the_allowed_range_is_rejected():
    """Thresholds are cosine-like scores and must stay within -1..1."""
    with pytest.raises(ValidationError):
        _rule(thresholds={"score": 1.5})


def test_a_rule_needs_a_description_or_a_reference_image():
    """A completely empty rule is meaningless."""
    with pytest.raises(ValidationError):
        _rule(descriptions=[], reference_images=[])


# --------------------------------------------------------------------------- #
# queue_rebuild
# --------------------------------------------------------------------------- #

def test_queue_rebuild_creates_a_classify_clip_task():
    """Queuing a rebuild returns the id of the freshly created task."""
    user = _user()
    category_id = uuid4()
    task = SimpleNamespace(id=uuid4())

    with patch(
        "app.service.task_manager.TaskManager.get_instance"
    ) as get_instance:
        get_instance.return_value.add_task.return_value = task
        result = clip_api.queue_rebuild(MagicMock(), user, [category_id])

    assert result == str(task.id)
    kwargs = get_instance.return_value.add_task.call_args.kwargs
    assert kwargs["owner_id"] == user.id
    assert kwargs["payload"] == {"category_ids": [str(category_id)]}


def test_queue_rebuild_without_categories_keeps_the_payload_empty():
    """A full rebuild does not restrict the category list."""
    user = _user()
    task = SimpleNamespace(id=uuid4())

    with patch(
        "app.service.task_manager.TaskManager.get_instance"
    ) as get_instance:
        get_instance.return_value.add_task.return_value = task
        clip_api.queue_rebuild(MagicMock(), user, None)

    kwargs = get_instance.return_value.add_task.call_args.kwargs
    assert kwargs["payload"] == {"category_ids": None}


# --------------------------------------------------------------------------- #
# enable
# --------------------------------------------------------------------------- #

def test_enabling_a_disabled_category_queues_a_rebuild():
    """Switching a category on has to re-run the classification."""
    user = _user()
    category = SimpleNamespace(id=uuid4(), enabled=False)

    with patch.object(
        clip_api.svc, "owned_category", return_value=category
    ), patch.object(clip_api, "queue_rebuild", return_value="task-1") as queue:
        result = clip_api.enable_categories(
            payload=clip_api.EnableInput(category_ids=[category.id], enabled=True),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 0
    assert result.data == {"updated": 1, "task_id": "task-1"}
    queue.assert_called_once()


def test_enabling_an_already_enabled_category_does_not_queue_a_rebuild():
    """Nothing changed -> no rebuild task."""
    user = _user()
    category = SimpleNamespace(id=uuid4(), enabled=True)

    with patch.object(
        clip_api.svc, "owned_category", return_value=category
    ), patch.object(clip_api, "queue_rebuild") as queue:
        result = clip_api.enable_categories(
            payload=clip_api.EnableInput(category_ids=[category.id], enabled=True),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 0
    assert result.data == {"updated": 1}
    queue.assert_not_called()


def test_enabling_a_foreign_category_fails_with_400():
    """A category owned by somebody else must be rejected."""
    user = _user()

    with patch.object(
        clip_api.svc, "owned_category", side_effect=ValueError("not owned")
    ):
        result = clip_api.enable_categories(
            payload=clip_api.EnableInput(category_ids=[uuid4()], enabled=True),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 400
    assert result.msg == "not owned"


# --------------------------------------------------------------------------- #
# categories
# --------------------------------------------------------------------------- #

def test_categories_reports_a_broken_preset_bootstrap_as_400():
    """A failing preset bootstrap must not blow up the whole listing."""
    user = _user()

    with patch.object(
        clip_api.svc, "ensure_presets", side_effect=ValueError("catalog broken")
    ):
        result = clip_api.categories(db=MagicMock(), user=user)

    assert result.code == 400
    assert result.msg == "catalog broken"


# --------------------------------------------------------------------------- #
# preview
# --------------------------------------------------------------------------- #

class _FakePhotoSchema:
    """Stand-in for ``app.schemas.photo.Photo``."""

    @staticmethod
    def model_validate(value):
        return SimpleNamespace(model_dump=lambda mode=None: {"id": str(value["id"])})


def test_preview_returns_the_matched_photos():
    """The preview payload is enriched with the serialised photo."""
    user = _user()
    photo_id = uuid4()
    previewed = {
        "matches": [{"photo": {"id": photo_id}, "score": 0.9}],
        "boundary": [{"photo": {"id": photo_id}, "score": 0.5}],
        "matched_count": 1,
    }

    with patch.object(clip_api.svc, "preview", return_value=previewed), patch.object(
        clip_api, "PhotoSchema", _FakePhotoSchema
    ):
        result = clip_api.preview(
            payload=clip_api.PreviewInput(
                name="Seaside",
                descriptions=["beach"],
                groups=["Custom"],
                thresholds={"score": 0.5},
            ),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 0
    assert result.data["matched_count"] == 1
    assert result.data["matches"][0]["photo"] == {"id": str(photo_id)}
    assert result.data["boundary"][0]["photo"] == {"id": str(photo_id)}


def test_preview_reports_a_domain_error_as_400():
    """An invalid reference image is a client error."""
    user = _user()

    with patch.object(clip_api.svc, "preview", side_effect=ValueError("bad image")):
        result = clip_api.preview(
            payload=clip_api.PreviewInput(
                name="Seaside",
                descriptions=["beach"],
                groups=["Custom"],
                thresholds={"score": 0.5},
            ),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 400
    assert result.msg == "bad image"


def test_preview_reports_an_unexpected_error_as_503():
    """An internal failure is a service error, not a client error."""
    user = _user()

    with patch.object(clip_api.svc, "preview", side_effect=RuntimeError("boom")):
        result = clip_api.preview(
            payload=clip_api.PreviewInput(
                name="Seaside",
                descriptions=["beach"],
                groups=["Custom"],
                thresholds={"score": 0.5},
            ),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 503
    assert "boom" in result.msg


# --------------------------------------------------------------------------- #
# save_rule (create / update)
# --------------------------------------------------------------------------- #

def _query_mocks(existing=None, other=None):
    """Two distinct query mocks: one for PhotoTag, one for ClipCategory."""
    photo_tag_query = MagicMock()
    photo_tag_query.filter_by.return_value.first.return_value = existing
    clip_category_query = MagicMock()
    clip_category_query.filter_by.return_value.first.return_value = other
    # ``other.filter(ClipCategory.id != cat.id)`` must not match either.
    clip_category_query.filter_by.return_value.filter.return_value.first.return_value = None
    return photo_tag_query, clip_category_query


def test_create_category_persists_the_rule_and_queues_a_rebuild():
    """A brand new category is stored and - when enabled - rebuilt."""
    user = _user()
    tag = SimpleNamespace(id=uuid4(), tag_name="Seaside")
    photo_tag_query, clip_category_query = _query_mocks()

    db = MagicMock()
    db.query.side_effect = [photo_tag_query, clip_category_query]

    with patch.object(clip_api.svc, "get_tag", return_value=tag), patch.object(
        clip_api.svc, "serialize_category", return_value={"id": "cat-1"}
    ), patch.object(clip_api, "queue_rebuild", return_value="task-2") as queue:
        result = clip_api.create_category(
            payload=_rule(enabled=True), db=db, user=user
        )

    assert result.code == 0
    assert result.data["task_id"] == "task-2"
    queue.assert_called_once()


def test_create_category_rejects_a_name_that_is_already_taken():
    """Two categories may not share the same tag."""
    user = _user()
    tag = SimpleNamespace(id=uuid4(), tag_name="Seaside")
    photo_tag_query, clip_category_query = _query_mocks(other=SimpleNamespace(id=uuid4()))

    db = MagicMock()
    db.query.side_effect = [photo_tag_query, clip_category_query]

    with patch.object(clip_api.svc, "get_tag", return_value=tag):
        result = clip_api.create_category(
            payload=_rule(), db=db, user=user
        )

    assert result.code == 409
    assert result.msg == "\u8be5\u540d\u79f0\u5df2\u6709\u5206\u7c7b"


def test_update_category_rejects_a_stale_revision():
    """The client must reload the rule before it overwrites it."""
    user = _user()
    category = SimpleNamespace(id=uuid4(), revision=7, tag_id=uuid4())

    with patch.object(
        clip_api.svc, "owned_category", return_value=category
    ):
        result = clip_api.update_category(
            category_id=category.id,
            payload=_rule(revision=3),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 409


def test_update_category_rejects_a_name_owned_by_another_tag():
    """Renaming onto an existing tag name is refused."""
    user = _user()
    category = SimpleNamespace(id=uuid4(), revision=1, tag_id=uuid4())
    old_tag = SimpleNamespace(id=category.tag_id, tag_name="Old")
    other_tag = SimpleNamespace(id=uuid4(), tag_name="Seaside")
    photo_tag_query, _ = _query_mocks(existing=other_tag)

    db = MagicMock()
    db.get.return_value = old_tag
    db.query.side_effect = [photo_tag_query]

    with patch.object(clip_api.svc, "owned_category", return_value=category):
        result = clip_api.update_category(
            category_id=category.id,
            payload=_rule(revision=1),
            db=db,
            user=user,
        )

    assert result.code == 409


# --------------------------------------------------------------------------- #
# rebuild
# --------------------------------------------------------------------------- #

def test_rebuild_checks_that_every_category_is_owned():
    """Every requested category must belong to the caller."""
    user = _user()
    category_id = uuid4()

    with patch.object(
        clip_api.svc, "owned_category", return_value=SimpleNamespace(id=category_id)
    ) as owned, patch.object(clip_api, "queue_rebuild", return_value="task-3") as queue:
        result = clip_api.rebuild(
            payload=clip_api.RebuildInput(category_ids=[category_id]),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 0
    assert result.data == {"task_id": "task-3"}
    owned.assert_called_once()
    queue.assert_called_once()


def test_rebuild_rejects_a_foreign_category():
    """A category of somebody else must abort the rebuild."""
    user = _user()

    with patch.object(
        clip_api.svc, "owned_category", side_effect=ValueError("not owned")
    ):
        result = clip_api.rebuild(
            payload=clip_api.RebuildInput(category_ids=[uuid4()]),
            db=MagicMock(),
            user=user,
        )

    assert result.code == 400
    assert result.msg == "not owned"


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #

def test_delete_category_removes_the_tag_and_its_relations():
    """Deleting a category also soft-deletes its tag and relations."""
    user = _user()
    tag = SimpleNamespace(id=uuid4(), is_deleted=False)
    category = SimpleNamespace(id=uuid4(), tag_id=tag.id, is_deleted=False, enabled=True)

    db = MagicMock()
    db.get.return_value = tag

    with patch.object(clip_api.svc, "owned_category", return_value=category):
        result = clip_api.delete_category(
            category_id=category.id, db=db, user=user
        )

    assert result.code == 0
    assert result.data == {"deleted": True}
    assert category.is_deleted is True
    assert category.enabled is False
    assert tag.is_deleted is True


def test_delete_category_rejects_a_foreign_category():
    """A category owned by somebody else must not be deleted."""
    user = _user()

    with patch.object(
        clip_api.svc, "owned_category", side_effect=ValueError("not owned")
    ):
        result = clip_api.delete_category(
            category_id=uuid4(), db=MagicMock(), user=user
        )

    assert result.code == 400
    assert result.msg == "not owned"

def test_blank_description_is_rejected():
    """A description entry may not be an empty string."""
    with pytest.raises(ValidationError):
        _rule(descriptions=["beach", "  "])


def test_overlong_description_is_rejected():
    """A description entry is limited to 100 characters."""
    with pytest.raises(ValidationError):
        _rule(descriptions=["x" * 101])


def test_update_category_bumps_the_revision_when_the_rule_changed():
    """Editing the descriptions of a rule creates a new revision."""
    user = _user()
    category = SimpleNamespace(id=uuid4(), revision=2, tag_id=uuid4(), enabled=True)
    old_rule = SimpleNamespace(
        descriptions=["old"],
        reference_images=[],
        strictness="standard",
        thresholds={"score": 0.5},
    )
    photo_tag_query, clip_category_query = _query_mocks()
    tag = SimpleNamespace(id=category.tag_id, tag_name="Seaside")

    db = MagicMock()
    db.query.side_effect = [photo_tag_query, clip_category_query]
    db.get.side_effect = [tag, old_rule]

    with patch.object(
        clip_api.svc, "owned_category", return_value=category
    ), patch.object(
        clip_api.svc, "serialize_category", return_value={"id": str(category.id)}
    ):
        result = clip_api.update_category(
            category_id=category.id,
            payload=_rule(revision=2, descriptions=["new"]),
            db=db,
            user=user,
        )

    assert result.code == 0
    assert category.revision == 3
    assert category.enabled is False


def test_update_category_of_an_unchanged_rule_keeps_the_revision():
    """An unchanged rule does not create a new revision."""
    user = _user()
    category = SimpleNamespace(id=uuid4(), revision=2, tag_id=uuid4(), enabled=True)
    old_rule = SimpleNamespace(
        descriptions=["beach"],
        reference_images=[],
        strictness="standard",
        thresholds={"score": 0.5},
    )
    photo_tag_query, clip_category_query = _query_mocks()
    tag = SimpleNamespace(id=category.tag_id, tag_name="Seaside")

    db = MagicMock()
    db.query.side_effect = [photo_tag_query, clip_category_query]
    db.get.side_effect = [tag, old_rule]

    with patch.object(
        clip_api.svc, "owned_category", return_value=category
    ), patch.object(
        clip_api.svc, "serialize_category", return_value={"id": str(category.id)}
    ), patch.object(clip_api, "queue_rebuild") as queue:
        result = clip_api.update_category(
            category_id=category.id,
            payload=_rule(revision=2),
            db=db,
            user=user,
        )

    assert result.code == 0
    assert category.revision == 2
    queue.assert_not_called()


def test_save_rule_reports_a_domain_error_as_400():
    """Any ValueError raised while saving is reported as a client error."""
    user = _user()
    photo_tag_query, clip_category_query = _query_mocks()

    db = MagicMock()
    db.query.side_effect = [photo_tag_query, clip_category_query]

    with patch.object(
        clip_api.svc, "get_tag", side_effect=ValueError("bad tag")
    ):
        result = clip_api.create_category(payload=_rule(), db=db, user=user)

    assert result.code == 400
    assert result.msg == "bad tag"