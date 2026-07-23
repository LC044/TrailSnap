"""Unit tests for the notification REST router (app/api/notification.py).

The router wires four CRUD-style endpoints on top of ``app.crud.notification``
plus a superuser-only ``POST /notifications`` broadcast endpoint.  All
behaviour is tested by patching the CRUD helpers (so we never touch the
database) and asserting the response shape from ``BaseResponse``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import notification as notif_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_notification]


def _user(is_superuser: bool = False):
    return SimpleNamespace(id=uuid4(), is_superuser=is_superuser)


def _notification_stub(**kwargs):
    """Build a Notification-shaped SimpleNamespace.

    ``app.crud.notification._serialize`` reads id / user_id / type / level /
    title / body / ref_type / ref_id / read / created_at / read_at, so any
    stub passed through ``create_notification`` -> ``_serialize`` needs all
    of them.  Defaults match a freshly-created unread notification.
    """
    base = dict(
        id=uuid4(),
        user_id=kwargs.pop("user_id"),
        type="SYSTEM",
        level="INFO",
        title="t",
        body=None,
        ref_type=None,
        ref_id=None,
        read=False,
        created_at=None,
        read_at=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_list_notifications_passes_filters_and_wraps_in_base_response():
    """``list_notifications`` forwards every query param and serialises rows."""
    user = _user()
    db = MagicMock()
    fake_rows = [
        _notification_stub(user_id=user.id, title="t1"),
        _notification_stub(user_id=user.id, title="t2", read=True,
                           body={"k": 1}, type="UPDATE", level="WARN",
                           ref_type="photo", ref_id="p1"),
    ]

    with patch("app.api.notification.crud_notification.list_notifications",
               return_value=fake_rows) as crud_list:
        with patch("app.api.notification.BaseResponse.success",
                   side_effect=lambda data: SimpleNamespace(data=data)) as success:
            notif_api.list_notifications(
                type="SYSTEM",
                unread=True,
                limit=10,
                before_id=None,
                db=db,
                current_user=user,
            )

    crud_list.assert_called_once_with(
        db, user.id, type="SYSTEM", unread=True, limit=10, before_id=None
    )
    success.assert_called_once()
    payload = success.call_args.kwargs["data"]
    assert len(payload) == 2
    assert payload[0]["title"] == "t1"
    assert payload[1]["body"] == {"k": 1}
    assert payload[1]["read"] is True


def test_unread_count_returns_count_wrapped_in_base_response():
    """``unread_count`` must return ``{"count": N}`` via BaseResponse.success."""
    user = _user()
    db = MagicMock()

    with patch("app.api.notification.crud_notification.unread_count",
               return_value=7):
        with patch("app.api.notification.BaseResponse.success",
                   side_effect=lambda data: SimpleNamespace(data=data)) as success:
            notif_api.unread_count(db=db, current_user=user)

    success.assert_called_once_with(data={"count": 7})


def test_mark_read_raises_404_when_crud_returns_false():
    """A miss in the CRUD layer must surface as HTTP 404, not as a silent ok."""
    user = _user()
    db = MagicMock()
    notif_id = uuid4()

    with patch("app.api.notification.crud_notification.mark_read",
               return_value=False):
        with patch("app.api.notification.BaseResponse.success") as success:
            with pytest.raises(HTTPException) as exc_info:
                notif_api.mark_read(notif_id=notif_id, db=db, current_user=user)

    assert exc_info.value.status_code == 404
    success.assert_not_called()


def test_mark_read_returns_remaining_unread_count_on_success():
    """On a successful mark, response carries the new unread count."""
    user = _user()
    db = MagicMock()
    notif_id = uuid4()

    with patch("app.api.notification.crud_notification.mark_read",
               return_value=True):
        with patch("app.api.notification.crud_notification.unread_count",
                   return_value=3):
            with patch("app.api.notification.BaseResponse.success",
                       side_effect=lambda data: SimpleNamespace(data=data)) as success:
                notif_api.mark_read(notif_id=notif_id, db=db, current_user=user)

    success.assert_called_once_with(data={"read": True, "unread_count": 3})


def test_mark_all_read_returns_marked_count():
    """``mark_all_read`` returns the number of rows that were flipped."""
    user = _user()
    db = MagicMock()

    with patch("app.api.notification.crud_notification.mark_all_read",
               return_value=12):
        with patch("app.api.notification.BaseResponse.success",
                   side_effect=lambda data: SimpleNamespace(data=data)) as success:
            notif_api.mark_all_read(db=db, current_user=user)

    success.assert_called_once_with(data={"marked": 12})


def test_create_notification_requires_superuser():
    """Non-admin callers must hit a 403 and no row should be created."""
    user = _user(is_superuser=False)
    db = MagicMock()
    payload = notif_api.NotificationCreate(title="hello")

    with patch("app.api.notification.crud_notification.create_notification") as create:
        with patch("app.api.notification.BaseResponse.success") as success:
            with pytest.raises(HTTPException) as exc_info:
                notif_api.create_notification(payload=payload, db=db,
                                              current_user=user)

    assert exc_info.value.status_code == 403
    create.assert_not_called()
    success.assert_not_called()


def test_create_notification_broadcasts_when_no_user_ids_and_flag_set():
    """Without ``user_ids`` and ``broadcast=True`` we fan out to every user."""
    admin = _user(is_superuser=True)
    db = MagicMock()
    target1, target2 = uuid4(), uuid4()
    fake_users = [SimpleNamespace(id=target1), SimpleNamespace(id=target2)]

    payload = notif_api.NotificationCreate(
        title="system notice",
        body={"msg": "see docs"},
        broadcast=True,
        user_ids=None,
    )

    created_targets = []

    def fake_create(db_, user_id, **kwargs):
        obj = _notification_stub(user_id=user_id, **kwargs)
        created_targets.append(user_id)
        return obj

    fake_manager = MagicMock()

    with patch("app.api.notification.crud_user.get_all_users",
               return_value=fake_users):
        with patch("app.api.notification.crud_notification.create_notification",
                   side_effect=fake_create):
            with patch("app.api.notification.NotificationManager.get_instance",
                       return_value=fake_manager):
                with patch("app.api.notification.BaseResponse.success",
                           side_effect=lambda data: SimpleNamespace(data=data)) as success:
                    notif_api.create_notification(payload=payload, db=db,
                                                  current_user=admin)

    assert created_targets == [target1, target2]
    assert fake_manager.publish_to_user.call_count == 2
    assert success.call_args.kwargs["data"]["count"] == 2


def test_create_notification_targets_specific_user_ids_only():
    """When ``user_ids`` is supplied, broadcast flag is ignored."""
    admin = _user(is_superuser=True)
    db = MagicMock()
    u1, u2 = uuid4(), uuid4()
    payload = notif_api.NotificationCreate(
        title="directed",
        broadcast=True,  # must be ignored
        user_ids=[u1, u2],
    )

    created_targets = []
    fake_manager = MagicMock()

    def fake_create(db_, user_id, **kwargs):
        obj = _notification_stub(user_id=user_id, **kwargs)
        created_targets.append(user_id)
        return obj

    with patch("app.api.notification.crud_user.get_all_users") as get_all_users:
        with patch("app.api.notification.crud_notification.create_notification",
                   side_effect=fake_create):
            with patch("app.api.notification.NotificationManager.get_instance",
                       return_value=fake_manager):
                with patch("app.api.notification.BaseResponse.success",
                           side_effect=lambda data: SimpleNamespace(data=data)) as success:
                    notif_api.create_notification(payload=payload, db=db,
                                                  current_user=admin)

    assert created_targets == [u1, u2]
    get_all_users.assert_not_called()
    assert fake_manager.publish_to_user.call_count == 2
    assert success.call_args.kwargs["data"]["count"] == 2


def test_create_notification_falls_back_to_caller_when_no_broadcast():
    """``broadcast=False`` and no ``user_ids`` means only the admin gets the row."""
    admin = _user(is_superuser=True)
    db = MagicMock()
    payload = notif_api.NotificationCreate(title="self", broadcast=False,
                                            user_ids=None)

    created_targets = []
    fake_manager = MagicMock()

    def fake_create(db_, user_id, **kwargs):
        obj = _notification_stub(user_id=user_id, **kwargs)
        created_targets.append(user_id)
        return obj

    with patch("app.api.notification.crud_user.get_all_users") as get_all_users:
        with patch("app.api.notification.crud_notification.create_notification",
                   side_effect=fake_create):
            with patch("app.api.notification.NotificationManager.get_instance",
                       return_value=fake_manager):
                with patch("app.api.notification.BaseResponse.success",
                           side_effect=lambda data: SimpleNamespace(data=data)) as success:
                    notif_api.create_notification(payload=payload, db=db,
                                                  current_user=admin)

    get_all_users.assert_not_called()
    assert created_targets == [admin.id]
    fake_manager.publish_to_user.assert_called_once()
    assert success.call_args.kwargs["data"]["count"] == 1
