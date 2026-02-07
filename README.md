# iidx_all_songs_master


IIDXの楽曲マスターデータ（SQLite）を生成・更新し、GitHub Releases に配布するためのシステムです。

本リポジトリの主目的は「プログラム」そのものではなく、生成物である `song_master.sqlite` を提供することです。  
大会運営・エビデンス管理・リザルト集計など、IIDX楽曲情報を参照するシステムの共通マスタとして利用できます。

---

## 生成物（配布物）

### song_master.sqlite

本システムが生成するSQLiteデータベースです。

- 曲情報（タイトル、アーティスト、ジャンル、収録状況など）
- 譜面情報（SP/DP、難易度、レベル、ノーツ数、譜面有効フラグ）

を含みます。

---

## データソース

Textage の以下ファイルを取得してSQLiteへ反映します。

- `titletbl.js` : 曲情報（タイトル/アーティスト/ジャンル/version/textage_id）
- `datatbl.js`  : ノーツ数
- `actbl.js`    : 譜面レベル / AC収録フラグ / INFINITAS収録フラグ

---

## DB仕様

### music テーブル（曲情報）

| column | type | description |
|--------|------|-------------|
| music_id | INTEGER | 内部ID |
| textage_id | TEXT | Textage恒久ID（ユニーク） |
| version | TEXT | 収録バージョン（例: `33`, `SS`） |
| title | TEXT | 曲名 |
| artist | TEXT | アーティスト |
| genre | TEXT | ジャンル |
| is_ac_active | INTEGER | AC収録フラグ（0/1） |
| is_inf_active | INTEGER | INFINITAS収録フラグ（0/1） |
| last_seen_at | TEXT | Textage取得時に確認された最終日時 |
| created_at | TEXT | 初回登録日時 |
| updated_at | TEXT | 更新日時 |

---

### chart テーブル（譜面情報）

| column | type | description |
|--------|------|-------------|
| chart_id | INTEGER | 内部ID |
| music_id | INTEGER | music参照 |
| play_style | TEXT | `SP` / `DP` |
| difficulty | TEXT | `BEGINNER` / `NORMAL` / `HYPER` / `ANOTHER` / `LEGGENDARIA` |
| level | INTEGER | 譜面レベル |
| notes | INTEGER | ノーツ数 |
| is_active | INTEGER | 譜面有効フラグ（0/1） |
| last_seen_at | TEXT | Textage取得時に確認された最終日時 |
| created_at | TEXT | 初回登録日時 |
| updated_at | TEXT | 更新日時 |

---

## データ更新仕様

本システムは毎回DBを作り直すのではなく、以下の動作で整合性を維持します。

### 1. GitHub Releases の最新SQLiteを取得（存在する場合）

- latest release の asset から `song_master.sqlite` をダウンロード
- 存在しなければローカル新規作成

### 2. 収録フラグを一旦リセット

更新開始時に `music.is_ac_active` / `music.is_inf_active` を一旦 `0` にします。  
その後Textageデータに存在する曲のみフラグを立て直します。

これにより、Textage側から削除された曲は「未収録扱い」として残ります。

### 3. Upsert（存在すれば更新、無ければ追加）

- `music` は `textage_id` をキーに Upsert
- `chart` は `(music_id, play_style, difficulty)` をキーに Upsert

---

## 正規化処理

Textage由来の文字列は、DB保存時に以下を正規化します。

- HTMLタグ除去  
  例: `<br>` や `<span ...>` を除去
- HTML文字実体参照のデコード  
  例: `&#332;` → `Ō`
- 空白の正規化

これにより、DB上での検索・一致判定を安定させます。

---

## GitHub Releases からの取得方法（利用者向け）

### 1. 最新ReleaseのSQLiteをダウンロードする

GitHub API:

GET https://api.github.com/repos/{owner}/{repo}/releases/latest


レスポンスの `assets` から `song_master.sqlite` を探し、
`browser_download_url` から取得してください。

---

### 2. curl例

curl -L -o song_master.sqlite
https://github.com/{owner}/{repo}/releases/latest/download/song_master.sqlite


---

## song_master.sqlite の利用方法（利用者向け）

### Pythonで参照する例

```python
import sqlite3

conn = sqlite3.connect("song_master.sqlite")
cur = conn.cursor()

cur.execute("""
SELECT title, artist, version
FROM music
WHERE is_ac_active = 1
AND title LIKE ?
ORDER BY version DESC
LIMIT 20
""", ("%BEMANI%",))

for row in cur.fetchall():
    print(row)

conn.close()
譜面情報を取得する例
SELECT
    m.title,
    c.play_style,
    c.difficulty,
    c.level,
    c.notes
FROM chart c
JOIN music m ON m.music_id = c.music_id
WHERE m.title LIKE '%Bunny%'
AND c.is_active = 1
ORDER BY c.level DESC;
設定ファイル（settings.yaml）
本リポジトリは settings.yaml を使用して動作を制御します。

例:

version: 33

output_db_path: "song_master.sqlite"

github:
  owner: "tts1374"
  repo: "song_master_builder"
  upload_to_release: true
  asset_name: "song_master.sqlite"
output_db_path
出力するSQLiteファイルパス

github.owner, github.repo
Releases取得・アップロード対象

github.upload_to_release
trueの場合、生成したsqliteを最新Releaseへアップロード

github.asset_name
Release asset名（通常は song_master.sqlite）

実行方法（開発者向け）
依存インストール
pip install -r requirements.txt
実行
python main.py
必要な環境変数
env	required	description
GITHUB_TOKEN	yes	Release取得/更新用トークン
DISCORD_WEBHOOK_URL	no	成功/失敗通知用
GitHub Actions での運用
本システムは以下の用途での自動運用を想定しています。

定期実行（毎日/毎週）

Textage更新検知後の更新

SQLite生成 → Releaseへアップロード

注意事項
Textageデータ構造変更が発生した場合、取得処理が動かなくなる可能性があります。

本DBは大会運営等での利用を想定していますが、公式データではありません。

is_ac_active / is_inf_active はTextageのフラグを元にしており、完全一致を保証するものではありません。

ライセンス
本リポジトリのコードはリポジトリ内のLICENSEに従います。
Textageおよび楽曲情報は各権利者に帰属します。
