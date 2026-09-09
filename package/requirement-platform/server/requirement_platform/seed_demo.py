"""灌入演示数据：重置本地 SQLite 并创建用户、需求、AI 分析与版本批次。

用法（在 package/requirement-platform/server 下）：
    uv run python -m requirement_platform.seed_demo
"""

import random

from passlib.context import CryptContext

from .db import SessionLocal, init_db
from .models import (
    ReleaseBatch,
    ReleaseBatchItem,
    Requirement,
    RequirementFollower,
    TriageReport,
    User,
    utcnow,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

random.seed(42)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        db.query(ReleaseBatchItem).delete()
        db.query(ReleaseBatch).delete()
        db.query(RequirementFollower).delete()
        db.query(TriageReport).delete()
        db.query(Requirement).delete()
        db.query(User).delete()
        db.commit()

        users = {
            "owner": User(username="zhouk", email="owner@trailsnap.cn", password_hash=pwd_context.hash("password123"), role="owner"),
            "admin": User(username="chenjing", email="admin@trailsnap.cn", password_hash=pwd_context.hash("password123"), role="admin"),
            "张三": User(username="zhangsan", email="zhangsan@example.com", password_hash=pwd_context.hash("password123"), role="viewer"),
            "李四": User(username="lisi", email="lisi@example.com", password_hash=pwd_context.hash("password123"), role="viewer"),
            "王五": User(username="wangwu", email="wangwu@example.com", password_hash=pwd_context.hash("password123"), role="viewer"),
            "赵六": User(username="zhaoliu", email="zhaoliu@example.com", password_hash=pwd_context.hash("password123"), role="viewer"),
            "陈晨": User(username="chenchen", email="chenchen@example.com", password_hash=pwd_context.hash("password123"), role="viewer"),
            "林娜": User(username="linna", email="linna@example.com", password_hash=pwd_context.hash("password123"), role="viewer"),
        }
        db.add_all(users.values())
        db.flush()

        demo = [
            ("feature", "支持深色模式", "希望增加深色模式，提升夜间使用体验，减少眼睛疲劳。浏览大量照片时白底过于刺眼，希望可以跟随系统自动切换。", "medium", "pending_review", "high", "张三", 12),
            ("improvement", "移动端适配优化", "在手机端的首页页面存在排版问题，希望优化移动端的浏览体验，包括瀑布流间距、底部导航栏和灯箱手势。", "medium", "developing", "normal", "李四", 8),
            ("feature", "导出需求数据为 Excel", "希望支持需求列表导出为 Excel，便于离线整理和汇报。", "low", "pending_review", "normal", "王五", 5),
            ("improvement", "增加需求标签功能", "希望可以通过标签对需求进行分类，方便筛选和管理，例如「性能」「UI」「同步」等内置标签。", "low", "candidate", "low", "赵六", 6),
            ("feature", "支持需求关注与订阅", "希望可以关注其他用户的需求，状态更新时收到通知。", "medium", "scheduled", "normal", "陈晨", 9),
            ("improvement", "优化需求详情页信息结构", "当前需求详情页信息层次欠佳，希望优化布局，提升阅读体验：把操作按钮固定在底部，元信息折叠到侧边。", "high", "developing", "high", "林娜", 15),
            ("feature", "增加版本关联功能", "希望在需求中关联版本计划，便于跟踪需求的落地情况。", "normal", "pending_review", "normal", "李四", 4),
            ("bug", "搜索框输入中文后回车重复触发搜索", "在搜索框使用输入法输入中文，按回车确认候选词时会误触发搜索，导致结果闪烁。", "high", "candidate", "high", "张三", 11),
            ("feature", "支持富文本编辑", "在提交需求时希望支持富文本编辑，包括图片、代码块和列表，便于描述复杂问题。", "low", "released", "low", "王五", 7),
            ("bug", "相册封面在窄屏下溢出容器", "相册封面图在 400px 以下宽度的屏幕上会溢出容器边界，出现横向滚动条。", "medium", "developing", "normal", "陈晨", 6),
            ("improvement", "时间轴按季节分组", "照片时间轴希望支持按季节分组展示，方便回忆旅行季节氛围。", "low", "deferred", "low", "林娜", 3),
            ("feature", "人物照片批量命名建议", "基于已识别人物，对未命名人物给出批量命名建议，减少手动输入。", "medium", "pending_review", "normal", "赵六", 10),
        ]

        from datetime import timedelta

        base = utcnow()
        requirements = []
        for i, (type_, title, desc, severity, status, priority, name, followers) in enumerate(demo):
            row = Requirement(
                public_number=i + 1, type=type_, title=title, description=desc, severity=severity, status=status, priority=priority,
                risk_level="medium", visibility="public", created_by=users[name].id,
                created_at=base - timedelta(days=len(demo) - i, hours=i % 5),
                updated_at=base - timedelta(days=len(demo) - i - 1, hours=(len(demo) - i) % 7),
            )
            db.add(row)
            requirements.append((row, users[name], followers))

        db.flush()
        for row, author, followers in requirements:
            others = [u for u in users.values() if u.id != author.id and u.role == "viewer"]
            follower_names = random.sample(others, k=min(followers, len(others)))
            db.add(RequirementFollower(requirement_id=row.id, user_id=author.id))
            for follower in follower_names:
                db.add(RequirementFollower(requirement_id=row.id, user_id=follower.id))
            if row.status != "pending_review":
                db.add(TriageReport(
                    requirement_id=row.id, requirement_version=1, provider="fallback", model=None,
                    report={"summary": f"该需求与「{row.title}」相关，建议纳入评估。用户价值：中高。", "category": row.type, "user_value": "medium", "recommendation": "进入候选池", "confidence": 0.72},
                    confidence=0.72,
                ))

        db.flush()
        batch = ReleaseBatch(
            name="v0.16 社区反馈批次", version_name="v0.16.0", batch_type="feature",
            goal="集中处理社区反馈的高频需求：深色模式、移动端体验和基础稳定性修复。",
            status="developing", target_date="2026-10-30", max_risk_level="high", created_by=users["owner"].id,
        )
        db.add(batch)
        db.flush()
        snapshot_map = {}
        for row, _author, _f in requirements:
            snapshot_map[row.id] = {
                "id": row.id, "type": row.type, "title": row.title, "description": row.description,
                "current_behavior": row.current_behavior, "expected_behavior": row.expected_behavior,
                "steps_to_reproduce": row.steps_to_reproduce, "severity": row.severity,
                "product_version": row.product_version, "environment": {}, "visibility": row.visibility,
                "status": row.status, "priority": row.priority, "risk_level": row.risk_level, "version": 1,
            }
        planned = [requirements[1][0], requirements[5][0], requirements[7][0], requirements[9][0]]
        for order, row in enumerate(planned):
            db.add(ReleaseBatchItem(
                batch_id=batch.id, requirement_id=row.id, priority_order=order,
                delivery_status=["completed", "developing", "developing", "not_started"][order],
                requirement_snapshot=snapshot_map[row.id],
            ))

        db.commit()
        print(f"seeded: {len(users)} users, {len(requirements)} requirements, 1 release batch")
    finally:
        db.close()


if __name__ == "__main__":
    main()
