# iidx_all_songs_master

beatmania IIDX の楽曲データを Textage から取得し、  
大会・エビデンス管理システム等で利用するための  
**曲マスタ SQLite を生成・配布するプロジェクト**です。

---

# 概要

本リポジトリは以下を提供します。

- Textage からの楽曲情報取得
- 正規化済み検索キー付き SQLite 生成
- `chart_id` 永続保証
- バージョン付き SQLite 出力
- `latest.json` メタ生成
- CI による整合性・互換性検証

---

# 出力物

生成される成果物は以下の2つです。

```text
song_master_<version>.sqlite
latest.json
```

## song_master_<version>.sqlite

- バージョン付きファイル名（固定名上書きなし）
- 読み取り専用前提
- 既存キーに対する `chart_id` 永続保証

## latest.json

例:

```json
{
  "file_name": "song_master_2026-02-15.sqlite",
  "schema_version": "33",
  "generated_at": "2026-02-15T12:34:56Z",
  "sha256": "xxxxxxxx",
  "byte_size": 12345678,
  "source_hashes": {
    "titletbl.js": "xxxxxxxx",
    "datatbl.js": "xxxxxxxx",
    "actbl.js": "xxxxxxxx"
  }
}
```

用途:

- クライアントが最新版を検出するためのメタ情報
- Textage ソース更新有無の判定（ハッシュ比較）

---

# データソース

以下を取得して解析します。

- https://textage.cc/score/titletbl.js
- https://textage.cc/score/datatbl.js
- https://textage.cc/score/actbl.js

---

# DBスキーマ概要

## music

| column           | type                 | note |
| ---------------- | -------------------- | ---- |
| music_id         | INTEGER PK           | AUTOINCREMENT |
| textage_id       | TEXT UNIQUE NOT NULL | 曲の一意キー |
| version          | TEXT NOT NULL        | 例: `33`, `SS` |
| title            | TEXT NOT NULL        |      |
| title_search_key | TEXT NOT NULL        | 検索用正規化キー |
| artist           | TEXT NOT NULL        |      |
| genre            | TEXT NOT NULL        |      |
| is_ac_active     | INTEGER NOT NULL     | 0/1 |
| is_inf_active    | INTEGER NOT NULL     | 0/1 |
| last_seen_at     | TEXT NOT NULL        | ISO8601 |
| created_at       | TEXT NOT NULL        | ISO8601 |
| updated_at       | TEXT NOT NULL        | ISO8601 |

制約:

- `UNIQUE(textage_id)`

索引:

- `idx_music_title_search_key ON music(title_search_key)`

### title_search_key

検索用正規化キー。生成仕様（固定順序）:

1. lowercase
2. trim
3. 置換テーブル適用（`ä→a`, `ö→o`, `ü→u`, `ß→ss`, `æ→ae`, `œ→oe`, `ø→o`, `å→a`, `ç→c`, `ñ→n`, `áàâã→a`, `éèêë→e`, `íìîï→i`, `óòôõ→o`, `úùû→u`, `ýÿ→y`）
4. Unicode 分解（NFD）→ 結合文字除去
5. 連続空白圧縮

## chart

| column       | type           | note |
| ------------ | -------------- | ---- |
| chart_id     | INTEGER PK     | AUTOINCREMENT |
| music_id     | INTEGER NOT NULL | `music(music_id)` 参照 |
| play_style   | TEXT NOT NULL  | `SP` / `DP` |
| difficulty   | TEXT NOT NULL  | `BEGINNER` / `NORMAL` / `HYPER` / `ANOTHER` / `LEGGENDARIA` |
| level        | INTEGER NOT NULL |      |
| notes        | INTEGER NOT NULL |      |
| is_active    | INTEGER NOT NULL | 0/1 |
| last_seen_at | TEXT NOT NULL  | ISO8601 |
| created_at   | TEXT NOT NULL  | ISO8601 |
| updated_at   | TEXT NOT NULL  | ISO8601 |

制約:

- `UNIQUE(music_id, play_style, difficulty)`
- `FOREIGN KEY(music_id) REFERENCES music(music_id)`

索引:

- `idx_chart_music_active ON chart(music_id, is_active)`
- `idx_chart_filter ON chart(play_style, difficulty, level, is_active)`
- `idx_chart_notes_active ON chart(is_active, notes)`

## meta

| column           | type           | note |
| ---------------- | -------------- | ---- |
| schema_version   | TEXT NOT NULL  | スキーマバージョン |
| asset_updated_at | TEXT NOT NULL  | 前回成果物時刻等 |
| generated_at     | TEXT NOT NULL  | 生成時刻 |

備考:

- 生成時に `meta` は1レコードに更新されます。

---

# chart_id 永続保証

同一キー:

```text
(textage_id, play_style, difficulty)
```

に対して `chart_id` は将来の生成でも変更されません。

CI で前回リリースとの比較検証を行い、  
不一致があればビルドは失敗します。

---

# スキップ条件（Textage未更新）

前回 `latest.json` の `source_hashes` と、今回取得した  
`titletbl.js` / `datatbl.js` / `actbl.js` の SHA-256 がすべて一致した場合、  
生成処理はスキップされます。

---

# セットアップ

```bash
pip install -r requirements.txt
```

---

# 実行

```bash
python main.py
```

生成後:

- SQLite 出力
- latest.json 出力
- 整合性チェック実行

---

# CIフロー概要

1. 前回リリース成果物取得
2. Textage 取得 + ハッシュ比較
3. SQLite 生成（必要時のみ）
4. スキーマ・整合性チェック
5. 前回リリースとの `chart_id` 比較
6. `latest.json` 生成
7. 成果物公開

---

# 互換性ポリシー

- `chart_id` は既存キーに対して変更しない
- `textage_id` を曲の唯一識別子とする
- スキーマ変更時は `schema_version` を更新する
- `title_search_key` 生成仕様変更は破壊的変更として扱う

---

# 注意事項

- Textage 構造変更時はパーサ修正が必要
- `chart_id` を振り直すような変更は禁止
- 生成物は必ず検証を通してから公開すること

---

# ライセンス

本プロジェクトは個人利用目的です。  
配布データの利用は自己責任で行ってください。

