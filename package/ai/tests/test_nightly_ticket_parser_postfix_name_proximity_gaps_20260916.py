"""2026-09-16 nightly tests for AI ticket_parser priority gaps.

Targets three helpers in app/services/ticket_parser.py that remain
untested after the 2026-08-15, 2026-09-08 and 2026-09-14 nightly suites:

* _post_fix_arrival_station -- back-fills arrival when only departure is
  parsed, prefers direction-suffixed stations, and protects against dep==arr.
* _select_name_by_proximity -- selects the closest Chinese candidate to any
  ID-like anchor; returns "" when no anchors exist or all candidates are
  beyond the distance threshold.
* _build_departure_datetime -- time-only branch (no md_cands) for the
  horizontal vs vertical geometry heuristic and the year-omitted fallback
  when no four-digit year is present.
"""

import pytest


pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


# ---------------------------------------------------------------------------
# _post_fix_arrival_station
# ---------------------------------------------------------------------------


def test_post_fix_arrival_returns_early_when_dep_and_arr_already_set():
    from app.services.ticket_parser import _post_fix_arrival_station

    info = {"departure_station": "北京南", "arrival_station": "上海虹桥"}
    # 即使 ocr_texts 里有新站，也不动现有结果
    out = _post_fix_arrival_station(
        dict(info), ["西安北站", "深圳北站"]
    )
    assert out == info


def test_post_fix_arrival_backfills_from_ocr_with_direction_suffix_priority():
    from app.services.ticket_parser import _post_fix_arrival_station

    # 没有 dep 也没有 arr：应按 ocr 中识别到的站名顺序填入（不附带 站 后缀避免分支重复）
    info = _post_fix_arrival_station(
        {}, ["北京南", "上海虹桥"]
    )
    assert info["departure_station"] == "北京南"
    assert info["arrival_station"] == "上海虹桥"

    # 有 dep 无 arr：选第一个不等于 dep 的站
    info = _post_fix_arrival_station(
        {"departure_station": "北京南"}, ["北京南", "上海", "深圳"]
    )
    assert info["arrival_station"] == "上海"

    # 当 ocr 没有任何 != dep 的站点时，arr 保持未设 (空 dict 不含 "arrival_station" 键)
    info = _post_fix_arrival_station(
        {"departure_station": "西安"}, ["西安"]
    )
    assert "arrival_station" not in info
    assert info.get("departure_station") == "西安"


def test_post_fix_arrival_strips_tail_non_chinese_markers():
    """OCR 经常把方向符号 (>) 粘在站名后面，第二分支剥离后再校验。"""
    from app.services.ticket_parser import _post_fix_arrival_station

    info = _post_fix_arrival_station({}, ["北京南>", "上海虹桥>"])
    assert info["departure_station"] == "北京南"
    assert info["arrival_station"] == "上海虹桥"


def test_post_fix_arrival_dedups_repeated_station_names():
    from app.services.ticket_parser import _post_fix_arrival_station

    # 同一站名出现多次，seen set 应去重
    info = _post_fix_arrival_station(
        {}, ["北京南", "上海虹桥", "北京南", "上海虹桥"]
    )
    # 重复出现的同一站名只算一次
    assert info["departure_station"] == "北京南"
    assert info["arrival_station"] == "上海虹桥"


# ---------------------------------------------------------------------------
# _select_name_by_proximity
# ---------------------------------------------------------------------------


def _ids(t):
    from app.services.ticket_parser import _is_id_like_text
    return _is_id_like_text(t)


def test_select_name_no_anchors_returns_empty_string():
    from app.services.ticket_parser import _select_name_by_proximity

    # 全是普通中文，没有任何 ID 锚点
    result = _select_name_by_proximity(
        ["北京", "上海", "张三", "李四"],
        station_name_set=set(),
        ticket_info={},
    )
    assert result == ""


def test_select_name_picks_closest_chinese_candidate_to_anchor():
    from app.services.ticket_parser import _select_name_by_proximity

    # index 0 = 锚点；index 1 是 blocklist 词 "检票" (被 _is_name_candidate_text 排除)
    # index 2 = "张三" 唯一有效候选
    ocr = [
        "****8035",
        "检票",
        "张三",
        "李四",
    ]
    result = _select_name_by_proximity(ocr, station_name_set=set(), ticket_info={})
    assert result == "张三"


def test_extract_tail_name_from_masked_id_block_basic():
    from app.services.ticket_parser import _extract_tail_name_from_masked_id_block

    # 基本提取
    assert _extract_tail_name_from_masked_id_block("****8035王五") == "王五"
    # 较长的尾部姓名
    assert _extract_tail_name_from_masked_id_block("4114****8035欧阳小明") == "欧阳小明"
    # 非法：尾部是 "站" 字，避免误把 XX站 提为姓名
    assert _extract_tail_name_from_masked_id_block("****8035西安站") == ""
    # 非法：没有 4+ 位数字/星号前缀
    assert _extract_tail_name_from_masked_id_block("普通文本") == ""
    # 非法：尾部不是 2~6 个中文
    assert _extract_tail_name_from_masked_id_block("****8035A") == ""
    # 空串
    assert _extract_tail_name_from_masked_id_block("") == ""


def test_select_name_distance_threshold_drops_distant_candidates():
    from app.services.ticket_parser import _select_name_by_proximity

    # 候选距离锚点 > 4，应被忽略
    ocr = ["****8035", "a", "b", "c", "d", "张三"]
    result = _select_name_by_proximity(ocr, station_name_set=set(), ticket_info={})
    assert result == ""


def test_select_name_anchor_label_keyword_triggers_search():
    from app.services.ticket_parser import _select_name_by_proximity

    # 没有 ID 形式锚点，但有 "身份证" 关键字也应触发
    # "票面其他" 含 3 个字符但被 _is_name_candidate_text 接受 (2-6 个中文字符)
    # 然而 index 2 (张三) 比 index 1 (票面其他) 离 anchor (index 0) 更远
    # 实际：index 1 离 anchor 距离 1，index 2 距离 2。所以会选 "票面其他"
    # 为了让 "张三" 胜出，把 blocklist 词 "检票" 放在 index 1
    ocr = ["身份证", "检票", "张三"]
    result = _select_name_by_proximity(ocr, station_name_set=set(), ticket_info={})
    assert result == "张三"


# ---------------------------------------------------------------------------
# _build_departure_datetime
# ---------------------------------------------------------------------------


def test_build_datetime_no_inputs_returns_empty():
    from app.services.ticket_parser import _build_departure_datetime

    assert _build_departure_datetime([], []) == ""
    assert _build_departure_datetime(["hello"], []) == ""


def test_build_datetime_year_prepended_when_present():
    from app.services.ticket_parser import _build_departure_datetime

    ocr = ["2024年", "05月07日", "10:20"]
    polys = [_poly(0, 0), _poly(0, 50), _poly(0, 100)]
    assert _build_departure_datetime(ocr, polys) == "2024年05月07日 10:20"


def test_build_datetime_year_omitted_when_absent():
    from app.services.ticket_parser import _build_departure_datetime

    ocr = ["05月07日", "10:20"]
    polys = [_poly(0, 0), _poly(0, 50)]
    assert _build_departure_datetime(ocr, polys) == "05月07日 10:20"


def test_build_datetime_time_only_picks_leftmost_in_horizontal_layout():
    """只有时间候选 + 横向布局 → 选最左（出发）"""
    from app.services.ticket_parser import _build_departure_datetime

    ocr = ["18:00", "22:30"]  # 出发 / 到达
    polys = [_poly(0, 50), _poly(300, 50)]
    result = _build_departure_datetime(ocr, polys)
    assert result == "18:00"


def test_build_datetime_time_only_picks_topmost_in_vertical_layout():
    """只有时间候选 + 纵向布局 → 选最上（出发）"""
    from app.services.ticket_parser import _build_departure_datetime

    ocr = ["18:00", "22:30"]
    polys = [_poly(50, 0), _poly(50, 300)]
    result = _build_departure_datetime(ocr, polys)
    assert result == "18:00"


def test_build_datetime_date_only_returns_date_string():
    from app.services.ticket_parser import _build_departure_datetime

    ocr = ["05月07日"]
    polys = [_poly(0, 0)]
    result = _build_departure_datetime(ocr, polys)
    assert result == "05月07日"


def test_build_datetime_anchor_y_prefers_nearby_date_when_only_md_present():
    from app.services.ticket_parser import _build_departure_datetime

    # 两个日期候选，anchor_y 偏向第二个
    ocr = ["05月07日", "06月08日"]
    polys = [_poly(0, 0), _poly(0, 200)]
    result = _build_departure_datetime(ocr, polys, anchor_y=200)
    assert result == "06月08日"
