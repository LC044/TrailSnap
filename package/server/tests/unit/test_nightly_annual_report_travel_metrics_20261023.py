"""Nightly watch 2026-10-23 — ``app/api/annual_report.py`` 未覆盖分支补测。

2026-10-23 的后端覆盖率扫描显示 ``api/annual_report.py`` 仍有 36 行未覆盖
（整体 76.9%）。已有基线
（``test_nightly_annual_report_api_gaps.py`` /
``test_nightly_annual_report_api_gaps_20260810.py``）只覆盖了
``/summary`` ``/season`` ``/emotion`` ``/easter-egg`` ``/photos`` 这几个
"直接委托给 crud 层" 的入口，真正自己写查询逻辑的几个端点仍然是盲区：

* ``GET /annual-report/travel-behavior`` —— 月度频次 / Top 线路 / Top 目的地 / 工作日周末分布
* ``GET /annual-report/comprehensive``   —— 总里程与每公里成本
* ``GET /annual-report/transport-analysis`` —— 上面两者的组合
* ``GET /annual-report/expenses/details`` —— 车票明细（含 owner 过滤与异常兜底）
* ``get_date_range_filter()``            —— 照片时间窗过滤

这些分支全部依赖真实的 SQL 聚合（``extract`` / ``group_by`` / ``sum``），
MagicMock 只能验证 mock 的形状、验证不了聚合结果，因此这里用真实的
SQLite 会话跑一遍，与 ``tests/conftest.py`` 里 ``face_sqlite_session``
fixture 的做法保持一致。
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.db.models  # noqa: F401  （注册全部 ORM 元数据）
from app.api import annual_report as report_api
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.trip import TrainTicket
from app.db.models.user import User


@pytest.fixture()
def annual_db(tmp_path):
    """真实的 SQLite 会话 + 两个用户（owner / 其它用户）。"""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'annual_report.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    owner = User(username="nightly-owner", email="nightly-owner@example.com", hashed_password="x")
    stranger = User(username="nightly-other", email="nightly-other@example.com", hashed_password="x")
    session.add_all([owner, stranger])
    session.flush()
    try:
        yield session, owner, stranger
    finally:
        session.close()
        engine.dispose()


def _ticket(owner, code, departure, arrival, when, price="100.00", mileage="1000.0", minutes=60):
    return TrainTicket(
        train_code=code,
        departure_station=departure,
        arrival_station=arrival,
        date_time=when,
        carriage="8A",
        seat_num="12F",
        price=Decimal(price),
        seat_type="二等座",
        name="夜间值守",
        total_mileage=Decimal(mileage),
        total_running_time=minutes,
        owner_id=owner.id,
    )


START = datetime(2026, 3, 1, 0, 0, 0)
END = datetime(2026, 3, 31, 23, 59, 59)


def test_travel_behavior_aggregates_month_routes_and_weekday_split(annual_db):
    """月度频次 / Top 线路 / Top 目的地 / 工作日周末分布都要按 owner 聚合。"""
    session, owner, _ = annual_db
    # 2026-03-05 是周四（工作日），2026-03-07 是周六（周末）
    session.add_all([
        _ticket(owner, "G1", "上海", "北京", datetime(2026, 3, 5, 10, 0)),
        _ticket(owner, "G2", "上海", "北京", datetime(2026, 3, 7, 10, 0)),
        _ticket(owner, "G3", "杭州", "北京", datetime(2026, 3, 9, 10, 0)),
    ])
    session.commit()

    metrics = report_api.get_report_travel_behavior(START, END, session, owner)

    assert [(m.month, m.count) for m in metrics.monthlyFrequency] == [("2026-03", 3)]
    assert metrics.topRoutes[0].route == "上海 -> 北京"
    assert metrics.topRoutes[0].count == 2
    assert metrics.topDestinations[0].city == "北京"
    assert metrics.topDestinations[0].count == 3
    # 03-05 周四 + 03-09 周一 = 2 个工作日，03-07 周六 = 1 个周末日
    assert metrics.tripTypeDistribution.workday == 2
    assert metrics.tripTypeDistribution.weekend == 1
    # 节假日需要外部日历数据，接口恒为 0
    assert metrics.tripTypeDistribution.holiday == 0


def test_travel_behavior_without_tickets_returns_empty_payload(annual_db):
    """没有任何车票时返回空集合而不是 None，避免前端拿不到数组。"""
    session, owner, _ = annual_db

    metrics = report_api.get_report_travel_behavior(START, END, session, owner)

    assert metrics.monthlyFrequency == []
    assert metrics.topRoutes == []
    assert metrics.topDestinations == []
    assert metrics.tripTypeDistribution.workday == 0
    assert metrics.tripTypeDistribution.weekend == 0


def test_travel_behavior_ignores_other_owners_tickets(annual_db):
    """别人的车票不能进入当前用户的统计。"""
    session, owner, stranger = annual_db
    session.add_all([
        _ticket(owner, "G1", "上海", "北京", datetime(2026, 3, 5, 10, 0)),
        _ticket(stranger, "G2", "广州", "深圳", datetime(2026, 3, 5, 11, 0)),
    ])
    session.commit()

    metrics = report_api.get_report_travel_behavior(START, END, session, owner)

    assert metrics.monthlyFrequency[0].count == 1
    assert [route.route for route in metrics.topRoutes] == ["上海 -> 北京"]


def test_comprehensive_aggregates_mileage_and_cost_per_km(annual_db):
    """总里程累加，每公里成本 = 总票价 / 总里程，保留两位小数。"""
    session, owner, _ = annual_db
    session.add_all([
        _ticket(owner, "G1", "上海", "北京", datetime(2026, 3, 5, 10, 0), price="100.00", mileage="1000.0"),
        _ticket(owner, "G2", "上海", "南京", datetime(2026, 3, 6, 10, 0), price="200.00", mileage="1000.0"),
    ])
    session.commit()

    metrics = report_api.get_report_comprehensive(START, END, session, owner)

    assert metrics.totalMileage == 2000
    assert metrics.costPerKm == 0.15


def test_comprehensive_without_tickets_is_zero(annual_db):
    """空数据时总里程 0、每公里成本 0.0（不能出现除零）。"""
    session, owner, _ = annual_db

    metrics = report_api.get_report_comprehensive(START, END, session, owner)

    assert metrics.totalMileage == 0
    assert metrics.costPerKm == 0.0


def test_transport_analysis_combines_behavior_and_comprehensive(annual_db):
    """组合端点把行为指标和综合指标一起返回。"""
    session, owner, _ = annual_db
    session.add(_ticket(owner, "G1", "上海", "北京", datetime(2026, 3, 5, 10, 0), price="100.00", mileage="1000.0"))
    session.commit()

    metrics = report_api.get_report_transport_analysis(START, END, session, owner)

    assert metrics.behavior.monthlyFrequency[0].count == 1
    assert metrics.comprehensive.totalMileage == 1000
    assert metrics.comprehensive.costPerKm == 0.1


def test_expense_details_returns_owner_tickets_newest_first(annual_db):
    """明细按发车时间倒序返回，且只包含当前用户、且在时间窗内的车票。"""
    session, owner, stranger = annual_db
    session.add_all([
        _ticket(owner, "G1", "上海", "北京", datetime(2026, 3, 5, 10, 0)),
        _ticket(owner, "G2", "杭州", "南京", datetime(2026, 3, 20, 10, 0)),
        _ticket(stranger, "G3", "广州", "深圳", datetime(2026, 3, 6, 10, 0)),
        _ticket(owner, "G4", "上海", "苏州", datetime(2025, 12, 31, 10, 0)),
    ])
    session.commit()

    details = report_api.get_report_expense_details(START, END, session, owner)

    assert [d.train_code for d in details] == ["G2", "G1"]
    assert details[0].departure_station == "杭州"
    assert details[0].arrival_station == "南京"
    assert details[0].price == 100.0


def test_expense_details_converts_database_error_to_http_500(annual_db, monkeypatch):
    """数据库异常时返回 500，而不是把异常直接抛给调用方。"""
    session, owner, _ = annual_db

    def _boom(*args, **kwargs):
        raise RuntimeError("db is down")

    monkeypatch.setattr(session, "query", _boom)

    with pytest.raises(HTTPException) as excinfo:
        report_api.get_report_expense_details(START, END, session, owner)

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Failed to fetch expense details"


def test_get_date_range_filter_keeps_only_photos_inside_window(annual_db):
    """时间窗过滤只保留落在 [start, end] 区间的照片。"""
    session, owner, _ = annual_db
    session.add_all([
        Photo(filename="inside.jpg", _file_path="inside.jpg", file_type=FileType.image,
              photo_time=datetime(2026, 3, 10, 12, 0), owner_id=owner.id),
        Photo(filename="before.jpg", _file_path="before.jpg", file_type=FileType.image,
              photo_time=datetime(2026, 2, 28, 23, 0), owner_id=owner.id),
        Photo(filename="after.jpg", _file_path="after.jpg", file_type=FileType.image,
              photo_time=datetime(2026, 4, 1, 0, 30), owner_id=owner.id),
    ])
    session.commit()

    query = report_api.get_date_range_filter(session.query(Photo), START, END)
    filenames = sorted(row.filename for row in query.all())

    assert filenames == ["inside.jpg"]
