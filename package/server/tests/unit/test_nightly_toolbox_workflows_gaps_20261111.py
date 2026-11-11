"""Nightly watch 2026-11-11 · 盲区补测（app/api/toolbox_workflows.py, app/schemas/toolbox.py）。

被测模块：REQ-238 工具箱重构引入的路由与 schema，在本轮覆盖率扫描中几乎未被触达
（app/api/toolbox_workflows.py 64.9%，app/schemas/toolbox.py 90.1%）。

覆盖点：
- app/api/toolbox_workflows.py：folders/resolve、scopes/preview、organize/options、
  plans 的创建/列表/详情/明细/执行/停止/重试/撤销、preferences 读取，
  以及 response_call 把 ValueError 转成 code=400 失败响应的分支。
- app/schemas/toolbox.py：MediaScope / OrganizeRule / ToolConfig / ToolboxPreferences
  的 model_validator 失败分支。

路由层用 MagicMock 替换 service 层，只验证「参数如何传递、响应如何封装」；
schema 层直接构造 Pydantic 模型验证校验信息。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api import toolbox_workflows as workflows
from app.schemas import toolbox as toolbox_schemas


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture
def db():
    session = MagicMock()
    session.query.return_value.filter.return_value = session.query.return_value
    return session


@pytest.fixture
def user():
    return SimpleNamespace(id="user-1", settings=None)


# --------------------------------------------------------------------------- #
# app/api/toolbox_workflows.py
# --------------------------------------------------------------------------- #

def test_resolve_folder_returns_the_resolved_path(db, user):
    with patch.object(workflows, "resolve_browser_folder", return_value="/photos") as resolver:
        result = workflows.resolve_folder(parent="/photos", db=db, user=user)

    resolver.assert_called_once_with(db, user, "/photos")
    assert result.code == 0
    assert result.data == {"path": "/photos"}


def test_scope_preview_forwards_pagination(db, user):
    scope = toolbox_schemas.MediaScope(source="all")
    with patch.object(workflows, "scope_preview", return_value={"total": 3, "items": []}) as preview:
        result = workflows.preview_scope(scope=scope, offset=20, limit=10, db=db, user=user)

    preview.assert_called_once_with(db, user, scope, 20, 10)
    assert result.code == 0
    assert result.data == {"total": 3, "items": []}


def test_organize_options_use_the_first_rule(db, user):
    request = toolbox_schemas.PlanRequest(
        scope=toolbox_schemas.MediaScope(source="all"),
        config=toolbox_schemas.ToolConfig(
            kind="organize", action="copy", target="/target",
            rules=[toolbox_schemas.OrganizeRule(strategy="location", granularity="city")],
        ),
    )
    with patch.object(workflows, "group_options", return_value=[{"id": "c1", "name": "武汉", "count": 2}]) as options:
        result = workflows.options(request=request, db=db, user=user)

    options.assert_called_once_with(db, user, request.scope, request.config.rules[0])
    assert result.code == 0
    assert result.data[0]["name"] == "武汉"


def test_create_plan_returns_the_plan_view(db, user):
    request = toolbox_schemas.PlanRequest(
        scope=toolbox_schemas.MediaScope(source="all"),
        config=toolbox_schemas.ToolConfig(kind="rename", template="IMG_{index}"),
    )
    plan = SimpleNamespace(id="plan-1", kind="rename", status="preview")
    with patch.object(workflows, "create_plan", return_value=plan) as creator, \
            patch.object(workflows, "plan_view", return_value={"id": "plan-1"}) as view:
        result = workflows.preview(request=request, db=db, user=user)

    creator.assert_called_once_with(db, user, request)
    view.assert_called_once_with(plan)
    assert result.data == {"id": "plan-1"}


def test_history_excludes_preview_plans_and_filters_active(db, user):
    rows = [SimpleNamespace(id="plan-1"), SimpleNamespace(id="plan-2")]
    query = db.query.return_value.filter.return_value
    query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = rows

    with patch.object(workflows, "plan_view", side_effect=lambda row: {"id": row.id}):
        result = workflows.history(offset=0, limit=20, active_only=True, db=db, user=user)

    assert result.code == 0
    assert result.data == [{"id": "plan-1"}, {"id": "plan-2"}]
    query.filter.assert_called()


def test_history_without_active_filter_does_not_filter_status(db, user):
    query = db.query.return_value.filter.return_value
    query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

    with patch.object(workflows, "plan_view", side_effect=lambda row: {"id": row.id}):
        result = workflows.history(offset=0, limit=20, active_only=False, db=db, user=user)

    assert result.code == 0
    assert result.data == []


def test_plan_detail_uses_the_owner_scoped_lookup(db, user):
    plan_id = uuid4()
    plan = SimpleNamespace(id=plan_id)
    with patch.object(workflows, "get_plan", return_value=plan) as getter, \
            patch.object(workflows, "plan_view", return_value={"id": str(plan_id)}):
        result = workflows.detail(plan_id=plan_id, db=db, user=user)

    getter.assert_called_once_with(db, user.id, plan_id)
    assert result.data == {"id": str(plan_id)}


def test_plan_items_support_the_status_filter(db, user):
    plan_id = uuid4()
    items = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    query = db.query.return_value.filter.return_value
    query.count.return_value = 2
    query.order_by.return_value.offset.return_value.limit.return_value = items

    with patch.object(workflows, "get_plan") as getter, \
            patch.object(workflows, "item_view", side_effect=lambda row: {"id": row.id}):
        result = workflows.items(plan_id=plan_id, offset=0, limit=40, status="ready", db=db, user=user)

    getter.assert_called_once_with(db, user.id, plan_id)
    assert result.data == {"total": 2, "items": [{"id": 1}, {"id": 2}]}


def test_execute_starts_the_plan_and_wakes_the_worker(db, user):
    plan_id = uuid4()
    request = toolbox_schemas.ExecuteRequest(version=1, confirmed=True)
    plan = SimpleNamespace(id=plan_id, status="queued")
    with patch.object(workflows, "start_plan", return_value=plan) as starter, \
            patch.object(workflows, "plan_view", return_value={"id": str(plan_id)}), \
            patch.object(workflows.TaskManager, "get_instance") as manager:
        result = workflows.execute(plan_id=plan_id, request=request, db=db, user=user)

    starter.assert_called_once_with(db, user, plan_id, request)
    manager.return_value.start_worker_if_needed.assert_called_once()
    assert result.code == 0


def test_stop_marks_a_running_plan(db, user):
    plan_id = uuid4()
    plan = SimpleNamespace(id=plan_id, status="running", stop_requested=False)
    with patch.object(workflows, "get_plan", return_value=plan), \
            patch.object(workflows, "plan_view", return_value={"stop_requested": True}):
        result = workflows.stop(plan_id=plan_id, db=db, user=user)

    assert plan.stop_requested is True
    db.commit.assert_called_once()
    assert result.code == 0


def test_stop_rejects_a_finished_plan(db, user):
    plan_id = uuid4()
    plan = SimpleNamespace(id=plan_id, status="completed", stop_requested=False)
    with patch.object(workflows, "get_plan", return_value=plan), \
            patch.object(workflows, "plan_view", return_value={}):
        result = workflows.stop(plan_id=plan_id, db=db, user=user)

    assert result.code == 400
    assert "此任务已结束" in result.msg
    assert plan.stop_requested is False
    db.rollback.assert_called_once()


def test_retry_and_undo_use_the_recovery_plan(db, user):
    plan_id = uuid4()
    plan = SimpleNamespace(id=plan_id)
    with patch.object(workflows, "get_plan", return_value=plan), \
            patch.object(workflows, "recovery_plan", return_value=plan) as recovery, \
            patch.object(workflows, "plan_view", return_value={"id": str(plan_id)}):
        retry_result = workflows.retry(plan_id=plan_id, db=db, user=user)
        undo_result = workflows.undo(plan_id=plan_id, db=db, user=user)

    assert retry_result.code == 0
    assert undo_result.code == 0
    assert recovery.call_args_list[0].kwargs == {}
    assert recovery.call_args_list[1].kwargs == {"undo": True}


def test_preferences_are_read_from_the_user_settings(db, user):
    user.settings = {"toolbox": {"version": 1, "presets": []}}
    result = workflows.preferences(db=db, user=user)

    assert result.code == 0
    assert result.data["version"] == 1
    assert result.data["presets"] == []


def test_preferences_fall_back_to_defaults_without_settings(db, user):
    result = workflows.preferences(db=db, user=user)

    assert result.code == 0
    assert result.data["presets"] == []
    assert result.data["default_rename_id"] is None


# --------------------------------------------------------------------------- #
# app/schemas/toolbox.py
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"source": "albums"}, "请明确选择处理范围"),
        ({"source": "filter"}, "条件筛选至少需要指定日期"),
        ({"source": "all", "start_date": "2026-05-02", "end_date": "2026-05-01"}, "开始日期不能晚于结束日期"),
    ],
)
def test_media_scope_rejects_incomplete_scopes(kwargs, message):
    with pytest.raises(ValidationError, match=message):
        toolbox_schemas.MediaScope(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"strategy": "location", "granularity": "city", "groups": []}, "指定分组至少需要选择一项"),
        ({"strategy": "time", "granularity": "city"}, "日期粒度无效"),
        ({"strategy": "location", "granularity": "year"}, "地点粒度无效"),
    ],
)
def test_organize_rule_rejects_invalid_combinations(kwargs, message):
    with pytest.raises(ValidationError, match=message):
        toolbox_schemas.OrganizeRule(**kwargs)


def test_tool_config_requires_target_and_action_for_organize():
    with pytest.raises(ValidationError, match="请选择目标目录和移动/复制方式"):
        toolbox_schemas.ToolConfig(kind="organize", action=None, target="")


def test_tool_config_multi_group_all_only_supports_copy():
    with pytest.raises(ValidationError, match="多个分组分别生成文件仅支持复制"):
        toolbox_schemas.ToolConfig(kind="organize", action="move", target="/t", multi_group="all")


def test_tool_config_metadata_none_requires_device_information():
    with pytest.raises(ValidationError, match="请至少设置一项拍摄信息"):
        toolbox_schemas.ToolConfig(kind="metadata", time_mode="none", make="", model="")


def test_tool_config_metadata_custom_requires_a_timestamp():
    with pytest.raises(ValidationError, match="请选择指定时间"):
        toolbox_schemas.ToolConfig(kind="metadata", time_mode="custom", custom_time=None)


@pytest.mark.parametrize(
    ("presets", "message"),
    [
        ([{"id": "p1", "name": "a", "config": {"kind": "rename", "template": "A"}}, {"id": "p1", "name": "b", "config": {"kind": "rename", "template": "B"}}], "模板标识重复"),
        ([{"id": "p1", "name": "a", "config": {"kind": "rename", "template": "A"}}, {"id": "p2", "name": "a", "config": {"kind": "rename", "template": "B"}}], "模板名称重复"),
    ],
)
def test_toolbox_preferences_reject_duplicated_presets(presets, message):
    with pytest.raises(ValidationError, match=message):
        toolbox_schemas.ToolboxPreferences.model_validate({"version": 1, "presets": presets})


def test_toolbox_preferences_reject_an_unknown_default_rename_template():
    with pytest.raises(ValidationError, match="默认命名模板不存在"):
        toolbox_schemas.ToolboxPreferences.model_validate(
            {"version": 1, "presets": [], "default_rename_id": "missing"}
        )



def test_save_preferences_persists_the_toolbox_settings(db, user):
    user.settings = {"toolbox": {"version": 3, "recent": [{"kind": "rename"}]}}
    value = toolbox_schemas.ToolboxPreferences.model_validate(
        {"version": 3, "presets": [{"id": "p1", "name": "旅行", "config": {"kind": "rename", "template": "IMG_{index}"}}]}
    )

    with patch.object(workflows, "validate_template") as validator:
        result = workflows.save_preferences(value=value, db=db, user=user)

    validator.assert_called_once_with("IMG_{index}")
    assert result.code == 0
    assert result.data["version"] == 4
    assert result.data["recent"] == [{"kind": "rename"}]
    assert user.settings["toolbox"]["presets"][0]["name"] == "旅行"
    db.commit.assert_called_once()


def test_save_preferences_rejects_a_stale_version(db, user):
    user.settings = {"toolbox": {"version": 1}}
    value = toolbox_schemas.ToolboxPreferences.model_validate({"version": 5, "presets": []})

    result = workflows.save_preferences(value=value, db=db, user=user)

    assert result.code == 400
    assert "请重新载入" in result.msg
    db.rollback.assert_called_once()
