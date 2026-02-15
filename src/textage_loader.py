"""Textage からテーブルJSを取得し、Python辞書へ変換する。"""

from __future__ import annotations

import hashlib
import json
import re

import requests

TITLE_URL = "https://textage.cc/score/titletbl.js"
DATA_URL = "https://textage.cc/score/datatbl.js"
ACT_URL = "https://textage.cc/score/actbl.js"


# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
def _extract_js_object(js_text: str, varname: str) -> dict:
    """
    JSテキスト中の `varname = {...}` を抽出し、辞書に変換する。

    変換時に以下を行う:
    - 定数（例: `SS=35`）を負値へ置換
    - 行コメントの除去
    - `.fontcolor(...)` の除去
    - シングルクォートキーのJSON化
    - actblの裸識別子 `A-F` の文字列化
    """
    match = re.search(rf"{varname}\s*=\s*\{{", js_text)
    if not match:
        raise RuntimeError(f"{varname} が JS 内に見つかりません")

    start = match.start()
    brace_start = js_text.find("{", start)
    if brace_start == -1:
        raise RuntimeError(f"{varname} の開始ブレースが見つかりません")

    index = brace_start
    depth = 0
    in_str = False
    escaped = False
    str_char = ""
    end_index = None
    while index < len(js_text):
        ch = js_text[index]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == str_char:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str = True
                str_char = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_index = index
                    break
        index += 1

    if end_index is None:
        raise RuntimeError(f"{varname} の終了ブレースが見つかりません")

    obj_text = js_text[brace_start : end_index + 1]

    # 定数置換（例: SS=35 -> -35）
    consts = dict(re.findall(r"([A-Z_][A-Z0-9_]*)\s*=\s*([0-9]+)\s*;", js_text))
    for name, val in consts.items():
        obj_text = re.sub(rf"(?<![\"'])\b{name}\b(?![\"'])", f"-{val}", obj_text)

    # JSコメント除去（末尾改行なしにも対応）
    obj_text = re.sub(r"//[^\n]*(?=\n|$)", "", obj_text)

    # 装飾メソッドの除去
    obj_text = re.sub(r"\.fontcolor\([^)]*\)", "", obj_text)

    # シングルクォートキーをJSON準拠へ
    obj_text = re.sub(r"'([^']*?)'(\s*):", r'"\1"\2:', obj_text)

    # actbl の裸識別子 A-F を文字列化
    obj_text = re.sub(r"(?<=,)([A-F])(?=,)", r'"\1"', obj_text)
    obj_text = re.sub(r"(?<=\[)([A-F])(?=,)", r'"\1"', obj_text)
    obj_text = re.sub(r"(?<=,)([A-F])(?=\])", r'"\1"', obj_text)

    def _escape_ctrl(match_obj: re.Match[str]) -> str:
        """文字列リテラル内の制御文字を `\\uXXXX` へ置換する。"""
        src = match_obj.group(1)
        out: list[str] = []
        idx = 0
        while idx < len(src):
            ch = src[idx]
            if ch == "\\" and idx + 1 < len(src):
                out.append(ch)
                idx += 1
                out.append(src[idx])
            else:
                if ord(ch) < 0x20:
                    out.append(f"\\u{ord(ch):04x}")
                else:
                    out.append(ch)
            idx += 1
        return '"' + "".join(out) + '"'

    # titletbl は配列部分だけを個別に拾ってパースする。
    if varname == "titletbl":
        result: dict[str, list] = {}
        entry_re = re.compile(r"['\"]([^'\"]+)['\"]\s*:\s*(\[[^\]]*\])", flags=re.S)
        for key, arr_text in entry_re.findall(obj_text):
            try:
                arr = json.loads(arr_text)
            except json.JSONDecodeError:
                continue

            if isinstance(arr, list) and arr:
                arr[0] = str(arr[0])
            result[key] = arr
        return result

    obj_text = re.sub(r'"((?:\\.|[^"\\\n])*)"', _escape_ctrl, obj_text)
    try:
        return json.loads(obj_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"json parse failed for {varname}: {exc}") from exc


def _sha256_hex(data: bytes) -> str:
    """バイナリデータの SHA-256（16進）を返す。"""
    return hashlib.sha256(data).hexdigest()


def fetch_textage_tables_with_hashes() -> tuple[dict, dict, dict, dict[str, str]]:
    """Textage 3ファイルを取得し、解析結果とソースハッシュを返す。"""
    title_resp = requests.get(TITLE_URL, timeout=30)
    title_resp.raise_for_status()

    data_resp = requests.get(DATA_URL, timeout=30)
    data_resp.raise_for_status()

    act_resp = requests.get(ACT_URL, timeout=30)
    act_resp.raise_for_status()

    titletbl = _extract_js_object(title_resp.text, "titletbl")
    datatbl = _extract_js_object(data_resp.text, "datatbl")
    actbl = _extract_js_object(act_resp.text, "actbl")

    source_hashes = {
        "titletbl.js": _sha256_hex(title_resp.content),
        "datatbl.js": _sha256_hex(data_resp.content),
        "actbl.js": _sha256_hex(act_resp.content),
    }

    return titletbl, datatbl, actbl, source_hashes


def fetch_textage_tables() -> tuple[dict, dict, dict]:
    """Textage 3ファイルを取得し、解析結果のみを返す。"""
    titletbl, datatbl, actbl, _ = fetch_textage_tables_with_hashes()
    return titletbl, datatbl, actbl
