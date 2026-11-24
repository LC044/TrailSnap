"""Nightly watch 2026-11-24: ``app/service/journey.py``::load_stations 盲区。

2026-11-24 的后端覆盖率报告里 ``service/journey.py`` 为 94.2%，
第 48-49 行（车站历史别名 ``alias_names`` 分支）、第 57 行（缺少省市信息的
车站行被跳过）和第 61 行（把别名并入候选站名）从未被执行过。

这段逻辑决定「火车票的出发地/到达地」能不能映射到城市：别名缺失会让老车站名
匹配不到，地理信息冲突时如果强行推断就会把记忆挂到错误的城市上。

这里用一个假的 railway 站表会话替换真实的车站库（真实库需要 RAILWAY_DB_URL），
直接验证映射规则本身。
"""

from __future__ import annotations

import sys
import types

import pytest
import sqlalchemy

from app.service import journey


pytestmark = [pytest.mark.smoke]


class _Row(tuple):
    """既能被下标访问、又带 station_name/province/city 属性的车站行。"""

    def __new__(cls, station_name, province, city, aliases=None):
        values = (station_name, province, city)
        if aliases is not None:
            values = values + (aliases,)
        return super().__new__(cls, values)

    @property
    def station_name(self):
        return self[0]

    @property
    def province(self):
        return self[1]

    @property
    def city(self):
        return self[2]


class _FakeStation:
    """带历史别名的车站表。"""

    station_name = sqlalchemy.column("station_name")
    province = sqlalchemy.column("province")
    city = sqlalchemy.column("city")
    alias_names = sqlalchemy.column("alias_names")


class _StationWithoutAliases:
    """旧版车站表：没有 alias_names 列。"""

    station_name = sqlalchemy.column("station_name")
    province = sqlalchemy.column("province")
    city = sqlalchemy.column("city")


def _install_railway(monkeypatch, rows, station_class):
    import railway.db.models.models as railway_models

    class _Query:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return list(rows)

    class _Session:
        def query(self, *selected):
            return _Query()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    fake_module = types.ModuleType("railway.db.session")
    fake_module.SessionLocal = lambda: _Session()
    monkeypatch.setitem(sys.modules, "railway.db.session", fake_module)
    monkeypatch.setattr(railway_models, "Station", station_class)


def test_load_stations_maps_a_station_to_its_city(monkeypatch):
    _install_railway(monkeypatch, [_Row("北京南", "北京市", "北京市")], _FakeStation)

    result = journey.load_stations(["北京南"])

    assert result == {"北京南": ("北京市", "北京")}


def test_load_stations_strips_the_station_and_city_suffix(monkeypatch):
    _install_railway(monkeypatch, [_Row("北京站", "北京市", "北京市")], _FakeStation)

    result = journey.load_stations(["北京站"])

    assert result == {"北京": ("北京市", "北京")}


def test_load_stations_resolves_a_historical_alias(monkeypatch):
    rows = [_Row("北京南", "北京市", "北京市", aliases=["磁器口"])]
    _install_railway(monkeypatch, rows, _FakeStation)

    result = journey.load_stations(["磁器口"])

    assert result["磁器口"] == ("北京市", "北京")


def test_load_stations_skips_a_row_without_geography(monkeypatch):
    rows = [_Row("无名站", "", ""), _Row("上海虹桥", "上海市", "上海市")]
    _install_railway(monkeypatch, rows, _FakeStation)

    result = journey.load_stations(["无名站", "上海虹桥"])

    assert "无名站" not in result
    assert result["上海虹桥"] == ("上海市", "上海")


def test_load_stations_drops_a_name_with_conflicting_geography(monkeypatch):
    rows = [_Row("同名站", "北京市", "北京市"), _Row("同名站", "上海市", "上海市")]
    _install_railway(monkeypatch, rows, _FakeStation)

    result = journey.load_stations(["同名站"])

    assert "同名站" not in result, "同名车站地理冲突时不能推断城市"


def test_load_stations_works_without_the_alias_column(monkeypatch):
    rows = [_Row("北京南", "北京市", "北京市")]
    _install_railway(monkeypatch, rows, _StationWithoutAliases)

    result = journey.load_stations(["北京南"])

    assert result == {"北京南": ("北京市", "北京")}
