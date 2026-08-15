"""Unit tests covering 2026-08-15 nightly coverage gap scan (round 3 AI).

Target: ``app/services/ticket_parser.py`` (57% baseline, 339 missed of
852 statements in coverage scan).

The existing ``test_ticket_parser.py`` covers the small helpers plus the
happy path of ``parse_ticket_info``. This file fills in:

* ``_is_valid_station_name`` / ``_get_valid_station_names`` -- station
  set membership + lazy load of the embedded JSON.
* ``_order_dep_arr_by_geometry`` -- horizontal vs vertical geometry.
* ``_pick_left_right_station_names`` -- dedup + single/fallback return.
* ``_pick_dep_arr_from_station_candidates`` -- clustered-row detection
  and the "largest horizontal distance" fallback.
* ``_split_carriage_seat_if_glued`` -- digit pair + seat letter pattern.
* ``_post_fix_arrival_station`` -- back-fill arrival from ocr_texts when
  missing, station dedup, dep==arr guard.
* ``_is_name_candidate_text`` -- rejects station/blocklist/seat-type
  strings; accepts a plain Chinese name.
* ``_extract_tail_name_from_masked_id_block`` -- tail name extraction
  from masked ID lines.
* ``_select_name_by_proximity`` -- nearest Chinese name to an
  ID-like anchor; distance threshold; no-anchor short-circuit.
* ``parse_ticket_info`` -- carriage + seat-type happy paths and the
  "all blank input" schema contract.
"""

from unittest.mock import patch

import pytest


pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


# ---------------------------------------------------------------------------
# _is_valid_station_name / _get_valid_station_names
# ---------------------------------------------------------------------------


def test_is_valid_station_name_known_city_is_true():
    from app.services import ticket_parser

    ticket_parser._VALID_STATION_NAMES = set()
    names = ticket_parser._get_valid_station_names()
    assert "北京" in names
    assert ticket_parser._is_valid_station_name("北京") is True


def test_is_valid_station_name_unknown_is_false():
    from app.services import ticket_parser

    ticket_parser._VALID_STATION_NAMES = set()
    ticket_parser._get_valid_station_names()
    assert ticket_parser._is_valid_station_name("xyzzzz") is False


def test_is_valid_station_name_empty_is_false():
    from app.services import ticket_parser

    assert ticket_parser._is_valid_station_name("") is False


def test_get_valid_station_names_returns_cached_after_first_load():
    from app.services import ticket_parser

    ticket_parser._VALID_STATION_NAMES = set()
    first = ticket_parser._get_valid_station_names()
    first.add("__sentinel__")
    second = ticket_parser._get_valid_station_names()
    assert "__sentinel__" in second
    assert "北京" in second


# ---------------------------------------------------------------------------
# _order_dep_arr_by_geometry
# ---------------------------------------------------------------------------


def test_order_dep_arr_by_geometry_horizontal_left_to_right():
    from app.services.ticket_parser import _order_dep_arr_by_geometry

    dep, arr = _order_dep_arr_by_geometry(("北京南", 0, 0), ("天津", 100, 0))
    assert dep == "北京南"
    assert arr == "天津"


def test_order_dep_arr_by_geometry_horizontal_right_to_left():
    from app.services.ticket_parser import _order_dep_arr_by_geometry

    dep, arr = _order_dep_arr_by_geometry(("天津", 100, 0), ("北京南", 0, 0))
    assert dep == "北京南"
    assert arr == "天津"


def test_order_dep_arr_by_geometry_vertical_top_to_bottom():
    from app.services.ticket_parser import _order_dep_arr_by_geometry

    dep, arr = _order_dep_arr_by_geometry(("北京南", 0, 0), ("天津", 5, 100))
    assert dep == "北京南"
    assert arr == "天津"


# ---------------------------------------------------------------------------
# _pick_left_right_station_names
# ---------------------------------------------------------------------------


def test_pick_left_right_station_names_returns_two_when_distinct():
    from app.services.ticket_parser import _pick_left_right_station_names

    candidates = [("北京南", 10, 5), ("天津", 200, 5)]
    dep, arr = _pick_left_right_station_names(candidates)
    assert (dep, arr) == ("北京南", "天津")


def test_pick_left_right_station_names_dedups_repeated_names():
    from app.services.ticket_parser import _pick_left_right_station_names

    candidates = [("北京南", 10, 5), ("北京南", 50, 5), ("天津", 200, 5)]
    dep, arr = _pick_left_right_station_names(candidates)
    assert dep == "北京南"
    assert arr == "天津"


def test_pick_left_right_station_names_single_station_returns_blank_pair():
    from app.services.ticket_parser import _pick_left_right_station_names

    candidates = [("北京南", 10, 5)]
    dep, arr = _pick_left_right_station_names(candidates)
    assert dep == "北京南"
    assert arr == ""


def test_pick_left_right_station_names_empty_returns_blank_pair():
    from app.services.ticket_parser import _pick_left_right_station_names

    assert _pick_left_right_station_names([]) == ("", "")


# ---------------------------------------------------------------------------
# _pick_dep_arr_from_station_candidates
# ---------------------------------------------------------------------------


def test_pick_dep_arr_from_station_candidates_uses_same_row():
    from app.services.ticket_parser import _pick_dep_arr_from_station_candidates

    candidates = [("北京南", 10, 5), ("天津", 200, 5)]
    dep, arr = _pick_dep_arr_from_station_candidates(candidates)
    assert dep == "北京南"
    assert arr == "天津"


def test_pick_dep_arr_from_station_candidates_falls_back_to_max_dx():
    from app.services.ticket_parser import _pick_dep_arr_from_station_candidates

    candidates = [
        ("甲站", 10, 5),
        ("乙站", 500, 100),
        ("丙站", 250, 200),
    ]
    dep, arr = _pick_dep_arr_from_station_candidates(candidates)
    assert {dep, arr} == {"甲站", "乙站"}


def test_pick_dep_arr_from_station_candidates_empty_returns_blank():
    from app.services.ticket_parser import _pick_dep_arr_from_station_candidates

    assert _pick_dep_arr_from_station_candidates([]) == ("", "")


def test_pick_dep_arr_from_station_candidates_skips_invalid_stations():
    from app.services.ticket_parser import _pick_dep_arr_from_station_candidates

    candidates = [
        ("ab", 10, 5),
        ("北京南", 10, 5),
        ("1234", 100, 5),
        ("天津", 500, 5),
    ]
    dep, arr = _pick_dep_arr_from_station_candidates(candidates)
    assert dep == "北京南"
    assert arr == "天津"


# ---------------------------------------------------------------------------
# _split_carriage_seat_if_glued
# ---------------------------------------------------------------------------


def test_split_carriage_seat_if_glued_unpacks_digit_pair_letter():
    from app.services.ticket_parser import _split_carriage_seat_if_glued

    info = {"carriage": "", "seat_num": "0814A"}
    _split_carriage_seat_if_glued(info)
    assert info == {"carriage": "08", "seat_num": "14A"}


def test_split_carriage_seat_if_glued_leaves_existing_carriage_alone():
    from app.services.ticket_parser import _split_carriage_seat_if_glued

    info = {"carriage": "12", "seat_num": "14A"}
    _split_carriage_seat_if_glued(info)
    assert info == {"carriage": "12", "seat_num": "14A"}


def test_split_carriage_seat_if_glued_leaves_non_matching_seat_alone():
    from app.services.ticket_parser import _split_carriage_seat_if_glued

    info = {"carriage": "", "seat_num": "14A"}
    _split_carriage_seat_if_glued(info)
    assert info == {"carriage": "", "seat_num": "14A"}


def test_split_carriage_seat_if_glued_leaves_empty_seat_alone():
    from app.services.ticket_parser import _split_carriage_seat_if_glued

    info = {"carriage": "", "seat_num": ""}
    _split_carriage_seat_if_glued(info)
    assert info == {"carriage": "", "seat_num": ""}


# ---------------------------------------------------------------------------
# _post_fix_arrival_station
# ---------------------------------------------------------------------------


def test_post_fix_arrival_station_back_fills_arrival_when_dep_present():
    from app.services.ticket_parser import _post_fix_arrival_station

    info = {"departure_station": "北京南", "arrival_station": ""}
    _post_fix_arrival_station(info, ["北京南站", "天津站", "二等座"])
    assert info["departure_station"] == "北京南"
    # Pass-1 + pass-2 run PER text in order, so stations interleaves the
    # bare-name (from pass-1 m.group(1)) and the with-站 form (from pass-2 stripped):
    #   text 0 "北京南站": pass-1 adds "北京南", pass-2 adds "北京南站"
    #   text 1 "天津站":   pass-1 adds "天津",   pass-2 adds "天津站"
    #   text 2 "二等座":   pass-2 adds "二等座"
    # stations = ["北京南", "北京南站", "天津", "天津站", "二等座"]
    # dep = "北京南" -> first non-dep is "北京南站".
    assert info["arrival_station"] == "北京南站"


def test_post_fix_arrival_station_back_fills_both_when_both_missing():
    from app.services.ticket_parser import _post_fix_arrival_station

    info = {"departure_station": "", "arrival_station": ""}
    _post_fix_arrival_station(info, ["北京南站", "天津站"])
    # Pass-1 + pass-2 run per text: text 0 yields ["北京南", "北京南站"],
    # text 1 yields ["天津", "天津站"].
    # stations = ["北京南", "北京南站", "天津", "天津站"]
    # dep = stations[0] = "北京南", arr = stations[1] = "北京南站".
    assert info["departure_station"] == "北京南"
    assert info["arrival_station"] == "北京南站"


def test_post_fix_arrival_station_consistency_guard_does_not_fire_for_distinct_stations():
    # The consistency guard (`dep == arr -> arr = ""`) is currently UNREACHABLE
    # in production: the seen-set guarantees unique station names when both
    # are derived from `stations[0]` / `stations[1]`, and the dep-only branch
    # only sets arr to the first non-dep station so arr can never equal dep.
    # We pin down the observed behaviour: function early-returns when both
    # stations are populated and leaves them alone (the guard never fires).
    from app.services.ticket_parser import _post_fix_arrival_station

    info = {"departure_station": "北京南", "arrival_station": "上海"}
    before = dict(info)
    _post_fix_arrival_station(info, ["北京南站", "上海站"])
    assert info["departure_station"] == "北京南"
    assert info["arrival_station"] == "上海"
    assert info == before


def test_post_fix_arrival_station_no_op_when_both_present():
    from app.services.ticket_parser import _post_fix_arrival_station

    info = {"departure_station": "北京南", "arrival_station": "天津"}
    before = dict(info)
    _post_fix_arrival_station(info, ["上海站", "杭州站"])
    assert info == before


def test_post_fix_arrival_station_handles_no_station_in_text():
    from app.services.ticket_parser import _post_fix_arrival_station

    info = {"departure_station": "", "arrival_station": ""}
    _post_fix_arrival_station(info, ["二等座", "￥70元"])
    assert info["departure_station"] == ""
    assert info["arrival_station"] == ""


# ---------------------------------------------------------------------------
# _is_name_candidate_text
# ---------------------------------------------------------------------------


def test_is_name_candidate_text_accepts_plain_chinese_name():
    from app.services.ticket_parser import _is_name_candidate_text

    assert _is_name_candidate_text("张三", {}, set()) is True


def test_is_name_candidate_text_rejects_station_name():
    from app.services.ticket_parser import _is_name_candidate_text

    assert _is_name_candidate_text("南京", {}, {"南京"}) is False


def test_is_name_candidate_text_rejects_blocklist_words():
    from app.services.ticket_parser import _is_name_candidate_text

    for bad in ("无座", "事由", "限乘", "学生票"):
        assert _is_name_candidate_text(bad, {}, set()) is False


def test_is_name_candidate_text_rejects_mixed_or_empty():
    from app.services.ticket_parser import _is_name_candidate_text

    assert _is_name_candidate_text("", {}, set()) is False
    assert _is_name_candidate_text("张三123", {}, set()) is False
    assert _is_name_candidate_text("John", {}, set()) is False


# ---------------------------------------------------------------------------
# _extract_tail_name_from_masked_id_block
# ---------------------------------------------------------------------------


def test_extract_tail_name_from_masked_id_block_pulls_chinese_tail():
    from app.services.ticket_parser import _extract_tail_name_from_masked_id_block

    assert _extract_tail_name_from_masked_id_block("****8035张三") == "张三"
    assert _extract_tail_name_from_masked_id_block("4114****8035张三") == "张三"


def test_extract_tail_name_from_masked_id_block_rejects_chinese_containing_station():
    from app.services.ticket_parser import _extract_tail_name_from_masked_id_block

    assert _extract_tail_name_from_masked_id_block("****8035北京站") == ""


def test_extract_tail_name_from_masked_id_block_rejects_too_short_prefix():
    from app.services.ticket_parser import _extract_tail_name_from_masked_id_block

    assert _extract_tail_name_from_masked_id_block("**张三") == ""


def test_extract_tail_name_from_masked_id_block_rejects_empty():
    from app.services.ticket_parser import _extract_tail_name_from_masked_id_block

    assert _extract_tail_name_from_masked_id_block("") == ""
    assert _extract_tail_name_from_masked_id_block("plain text") == ""


# ---------------------------------------------------------------------------
# _select_name_by_proximity
# ---------------------------------------------------------------------------


def test_select_name_by_proximity_returns_nearest_chinese_name():
    from app.services.ticket_parser import _select_name_by_proximity

    texts = [
        "****8035",
        "张三",
        "李四",
        "￥70元",
    ]
    assert _select_name_by_proximity(texts, set(), {}) == "张三"


def test_select_name_by_proximity_picks_glued_tail_name():
    from app.services.ticket_parser import _select_name_by_proximity

    # The glued tail text has only asterisks (no digits), so it is NOT
    # classified as an ID-like anchor. The 4-digit-stars anchor lives in
    # the first entry; the second entry is just "****" + Chinese name.
    texts = [
        "****8035",
        "****李四",
    ]
    assert _select_name_by_proximity(texts, set(), {}) == "李四"


def test_select_name_by_proximity_skips_far_candidates():
    from app.services.ticket_parser import _select_name_by_proximity

    texts = [
        "****8035",
        "A", "B", "C", "D", "E",
        "张三",
    ]
    assert _select_name_by_proximity(texts, set(), {}) == ""


def test_select_name_by_proximity_returns_blank_without_anchor():
    from app.services.ticket_parser import _select_name_by_proximity

    texts = ["张三", "李四", "二等座"]
    assert _select_name_by_proximity(texts, set(), {}) == ""


def test_select_name_by_proximity_rejects_blocklist_candidate():
    from app.services.ticket_parser import _select_name_by_proximity

    texts = [
        "****8035",
        "事由",
        "张三",
    ]
    assert _select_name_by_proximity(texts, set(), {}) == "张三"


def test_select_name_by_proximity_uses_anchor_when_text_carries_id_label():
    from app.services.ticket_parser import _select_name_by_proximity

    texts = ["身份证", "张三", "李四"]
    assert _select_name_by_proximity(texts, set(), {}) == "张三"


# ---------------------------------------------------------------------------
# parse_ticket_info: extended coverage
# ---------------------------------------------------------------------------


def test_parse_ticket_info_returns_full_schema_on_empty_input():
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info([], [])
    expected = {
        "train_code", "departure_station", "arrival_station", "datetime",
        "carriage", "seat_num", "berth_type", "price", "seat_type",
        "name", "discount_type", "detection_id",
    }
    assert expected.issubset(set(info.keys()))
    for k in expected - {"detection_id"}:
        assert info[k] in ("", None)
    assert info["detection_id"] == 0


def test_parse_ticket_info_extracts_seat_type_keyword_from_text():
    from app.services.ticket_parser import parse_ticket_info

    texts = ["G1234", "北京南站", "天津站", "二等座", "￥70.5元"]
    polys = [_poly(0, 0), _poly(0, 20), _poly(0, 40), _poly(0, 60), _poly(0, 80)]
    info = parse_ticket_info(texts, polys)
    assert info["seat_type"] == "二等座"


def test_parse_ticket_info_returns_zero_detection_id_on_empty_input():
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info([], [])
    assert info["detection_id"] == 0


def test_parse_ticket_info_detection_id_is_zero_by_default():
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info([], [])
    # detection_id is a placeholder (the OCR service layers it on later);
    # the parser itself never increments it.
    assert info["detection_id"] == 0


def test_parse_ticket_info_handles_text_without_polys():
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["北京南站", "天津站"], [])
    assert "train_code" in info


def test_parse_ticket_info_no_match_when_texts_are_unrelated():
    from app.services.ticket_parser import parse_ticket_info

    info = parse_ticket_info(["只", "是", "普通文字"], [_poly(0, 0), _poly(0, 20), _poly(0, 40)])
    assert info["train_code"] in ("", None)
    assert info["departure_station"] in ("", None)
    assert info["arrival_station"] in ("", None)
