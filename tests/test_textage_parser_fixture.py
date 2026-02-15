"""Textage JS パーサの最小 fixture テスト。"""

from __future__ import annotations

import pytest

from src.textage_loader import _extract_js_object


@pytest.mark.light
def test_extract_js_object_with_minimal_titletbl():
    """titletbl の定数置換と配列パースができることを確認する。"""
    js = """
    SS=35;
    titletbl={
      "k1":[SS,"T001","","GENRE","ARTIST","TITLE"]
    };
    """
    parsed = _extract_js_object(js, "titletbl")
    assert parsed["k1"][0] == "-35"
    assert parsed["k1"][1] == "T001"


@pytest.mark.light
def test_extract_js_object_with_minimal_datatbl_and_actbl():
    """datatbl/actbl の基本オブジェクトを抽出できることを確認する。"""
    data_js = """
    datatbl={
      "k1":[0,101,102,103,104,105,106,107,108,109,110]
    };
    """
    act_js = """
    actbl={
      "k1":[3,0,5,0,5,0,5,0,5,0,5,0,0,0,5,0,5,0,5,0,5,0]
    };
    """
    datatbl = _extract_js_object(data_js, "datatbl")
    actbl = _extract_js_object(act_js, "actbl")
    assert datatbl["k1"][1] == 101
    assert actbl["k1"][0] == 3


@pytest.mark.light
def test_extract_js_object_raises_for_missing_varname():
    """対象変数が無い場合に RuntimeError を送出することを確認する。"""
    js = "var a={};"
    with pytest.raises(RuntimeError):
        _extract_js_object(js, "titletbl")


@pytest.mark.light
def test_extract_js_object_handles_eof_line_comment():
    """改行なしの行末コメントがあっても抽出できることを確認する。"""
    js = 'datatbl={"k1":[0,1,2]}; // trailing comment without newline'
    parsed = _extract_js_object(js, "datatbl")
    assert parsed["k1"][1] == 1
