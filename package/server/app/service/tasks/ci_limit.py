"""CI 环境下限制 AI 类任务的处理规模。

GitHub Actions 标准 runner 只有 4 vCPU，OCR / VISUAL_DESCRIPTION 跑全量照片会
严重拖慢 CI（每张都要调 AI 服务）。CI 下这两类任务最多处理 5 张照片：每次处理前
查 DB，已达到上限就直接跳过，避免浪费时间。

CI 信号来源：tests/docker/docker-compose.yml 把 runner 的 CI 环境变量透传进
server 容器（`CI: ${CI:-}`）。本地 dev / 本地 docker 模式下 CI 未设 → 不限制。
"""
import os
from sqlalchemy.orm import Session

# CI 下每类 AI 任务最多处理的去重照片数
CI_TASK_PHOTO_LIMIT = 5


def is_ci() -> bool:
    """是否运行在 CI 环境（GitHub Actions runner 会设 CI=true）。"""
    return os.environ.get('CI', '').strip().lower() in ('1', 'true', 'yes')


def ci_task_limit_reached(db: Session, model) -> bool:
    """CI 下 model 表中去重 photo_id 数已达上限则返回 True；非 CI 永远返回 False。

    model 应是带 photo_id 列的 ORM 模型（OCR / ImageDescription）。
    """
    if not is_ci():
        return False
    count = db.query(model.photo_id).distinct().count()
    return count >= CI_TASK_PHOTO_LIMIT


def ci_remaining_budget(db: Session, model) -> int | None:
    """CI 下返回还能处理几张照片（上限 - 已有）；非 CI 返回 None（不限制）。"""
    if not is_ci():
        return None
    count = db.query(model.photo_id).distinct().count()
    return max(0, CI_TASK_PHOTO_LIMIT - count)
