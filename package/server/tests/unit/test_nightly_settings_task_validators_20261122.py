"""Nightly watch 2026-11-22 · 配置与任务模型的输入校验盲区。

三处校验点此前没有任何测试直接引用：

- ``app/core/config_manager.py::AnalysisRequestSettings.validate_integer_option``
  要求分析并发/单请求图片数必须是**真正的 int**（bool 与 str 都要被拒）。
  Literal 限定了取值集合，但只有先挡住类型才能给出可读的错误。
- ``app/schemas/face.py::MergeRequest.trim_identity_name`` 在合并人物前
  去掉首尾空白，避免「 张三 」和「张三」变成两个不同人物。
- ``app/db/models/task.py::Task._associate_photo`` 从 payload 里的 photo_id
  自动关联照片；扫描类任务没有单张照片，必须保持 photo_id 为空。

本文件覆盖 happy / edge / error 三类。
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config_manager import AnalysisRequestSettings
from app.db.models.task import Task, TaskType
from app.schemas.face import MergeRequest

pytestmark = [pytest.mark.smoke]


# --------------------------------------------------------------------------- #
# AnalysisRequestSettings
# --------------------------------------------------------------------------- #

def test_analysis_settings_accept_the_supported_integer_options():
    settings = AnalysisRequestSettings(analysis_concurrency=4, analysis_images_per_request=8)

    assert settings.analysis_concurrency == 4
    assert settings.analysis_images_per_request == 8


def test_analysis_settings_reject_a_stringified_number():
    with pytest.raises(ValidationError):
        AnalysisRequestSettings(analysis_concurrency="4")


def test_analysis_settings_reject_a_boolean_even_though_bool_is_an_int():
    # type(True) is not int -> 必须拒绝，否则 True 会被当成并发数 1
    with pytest.raises(ValidationError):
        AnalysisRequestSettings(analysis_images_per_request=True)


def test_analysis_settings_reject_a_float():
    with pytest.raises(ValidationError):
        AnalysisRequestSettings(analysis_concurrency=2.0)


# --------------------------------------------------------------------------- #
# MergeRequest.trim_identity_name
# --------------------------------------------------------------------------- #

def test_merge_request_trims_the_identity_name():
    request = MergeRequest(source_ids=[uuid4()], target_id=uuid4(), identity_name="  张三  ")

    assert request.identity_name == "张三"


def test_merge_request_keeps_a_none_identity_name():
    request = MergeRequest(source_ids=[uuid4()], target_id=uuid4(), identity_name=None)

    assert request.identity_name is None


def test_merge_request_rejects_a_name_that_is_only_whitespace():
    # strip 之后为空 -> 触发 min_length=1
    with pytest.raises(ValidationError):
        MergeRequest(source_ids=[uuid4()], target_id=uuid4(), identity_name="   ")


# --------------------------------------------------------------------------- #
# Task._associate_photo
# --------------------------------------------------------------------------- #

def test_task_links_the_photo_named_in_its_payload():
    photo_id = uuid4()

    task = Task(type=TaskType.PROCESS_BASIC.value, payload={"photo_id": str(photo_id)})

    assert task.photo_id == photo_id


def test_task_leaves_the_photo_unlinked_for_a_scan_job():
    task = Task(type=TaskType.SCAN_FOLDER.value, payload={"folder": "D:/photos"})

    assert task.photo_id is None


def test_task_leaves_the_photo_unlinked_for_a_non_dict_payload():
    task = Task(type=TaskType.SCAN_FOLDER.value, payload=["not", "a", "dict"])

    assert task.photo_id is None


def test_task_str_reports_the_identity_fields():
    task = Task(type=TaskType.PROCESS_BASIC.value, status="pending", priority=7)

    rendered = str(task)

    assert "Task(id:" in rendered
    assert "PROCESS_BASIC" in rendered
    assert "pending" in rendered
    assert "7" in rendered
