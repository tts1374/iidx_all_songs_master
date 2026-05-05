"""Fixture tests for Textage JS parsing and decoding."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.textage_loader import (
    _charset_from_content_type,
    _decode_textage_response,
    _extract_js_object,
)


@pytest.mark.light
def test_extract_js_object_with_minimal_titletbl():
    """titletbl constants and object parsing work for minimal fixture."""
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
    """datatbl/actbl minimal objects are parsed."""
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
def test_extract_js_object_with_actbl_constant_flag_keeps_positive_value():
    """actbl constants must keep numeric sign (e.g., F=15 -> 15)."""
    js = """
    F=15;
    actbl={
      "k1":[F,0,0,A,7,B]
    };
    """
    parsed = _extract_js_object(js, "actbl")
    assert parsed["k1"][0] == 15
    assert parsed["k1"][3] == "A"
    assert parsed["k1"][5] == "B"


@pytest.mark.light
def test_extract_js_object_raises_for_missing_varname():
    """Missing variable name raises RuntimeError."""
    js = "var a={};"
    with pytest.raises(RuntimeError):
        _extract_js_object(js, "titletbl")


@pytest.mark.light
def test_extract_js_object_handles_eof_line_comment():
    """Trailing line comments without terminal newline are stripped."""
    js = 'datatbl={"k1":[0,1,2]}; // trailing comment without newline'
    parsed = _extract_js_object(js, "datatbl")
    assert parsed["k1"][1] == 1


@pytest.mark.light
def test_extract_js_object_keeps_double_slash_inside_titletbl_strings():
    """`//` inside title/genre strings must not be treated as comments."""
    js = """
    titletbl={
      'screwowo':[27,2748,0,"TWERKCORE // uwu // BEATJUGGLE","かめりあ","SCREW // owo // SCREW"],
      'lightstr':[27,2749,0,"Hi-GAIN ENERGY","BEMANI Sound Team \\"HuΣeR\\"","LIGHTNING STRIKES"],
      'riffrain':[31,3196,0,"THEME SONG","Rainy。","Riff//rain"],
      '_rabbith':[31,3197,0,"J-POP","DECO*27","ラビットホール"]
    };
    """
    parsed = _extract_js_object(js, "titletbl")
    assert parsed["screwowo"][3] == "TWERKCORE // uwu // BEATJUGGLE"
    assert parsed["lightstr"][5] == "LIGHTNING STRIKES"
    assert parsed["riffrain"][5] == "Riff//rain"
    assert parsed["_rabbith"][5] == "ラビットホール"


@pytest.mark.light
def test_extract_js_object_strips_block_comments_outside_strings():
    """Block comments in Textage rows must be stripped without touching strings."""
    js = """
    titletbl={
      "acidvis":[33,3905,1,"DRUM & BASS"/*"LIQUID FUNK"*/,"L.E.D.","ACID VISION"],
      "commentstr":[33,3906,1,"GENRE /* literal */","ARTIST","TITLE"]
    };
    """
    parsed = _extract_js_object(js, "titletbl")
    assert parsed["acidvis"][3] == "DRUM & BASS"
    assert parsed["commentstr"][3] == "GENRE /* literal */"


@pytest.mark.light
def test_extract_js_object_ignores_comment_braces_while_finding_object_end():
    """Comment braces before the real object end must not truncate extraction."""
    js = """
    titletbl={
      "k1":[33,3905,1,"GENRE","ARTIST","TITLE"],
      /* commented-out note with } before the real table end */
      // line comment with }
      "k2":[33,3906,1,"GENRE","ARTIST","TITLE /* literal } */"]
    };
    """
    parsed = _extract_js_object(js, "titletbl")
    assert sorted(parsed) == ["k1", "k2"]
    assert parsed["k2"][5] == "TITLE /* literal } */"


@pytest.mark.light
def test_charset_from_content_type_extracts_charset_token():
    """Content-Type charset token is parsed correctly."""
    value = "application/javascript; charset=Shift_JIS"
    assert _charset_from_content_type(value) == "Shift_JIS"
    assert _charset_from_content_type("application/javascript") is None


@pytest.mark.light
def test_decode_textage_response_prefers_cp932_fallback():
    """Unknown encoding responses fall back to cp932 and keep Japanese text."""
    body = "titletbl={'k':['Raison d\'&ecirc;tre','・樔ｺ､蟾ｮ縺吶ｋ螳ｿ蜻ｽ・・]};".encode("cp932")
    response = SimpleNamespace(content=body, headers={"Content-Type": "application/javascript"})
    response.encoding = None
    decoded = _decode_textage_response(response)
    assert "蟾ｮ縺吶ｋ螳ｿ蜻ｽ" in decoded
