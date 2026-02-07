"""
アプリケーション固有の例外定義モジュール。

スクレイピング、バリデーション、GitHub Release操作などの処理で発生する例外を
分類して扱うために、基底例外および派生例外を定義する。
"""


class SongMasterError(Exception):
    """曲マスタ作成システム全体の基底例外。"""


class ScrapeError(SongMasterError):
    """スクレイピング処理に起因する例外。"""


class TableNotFoundError(ScrapeError):
    """期待する条件に一致するHTMLテーブルが見つからない場合の例外。"""


class ValidationError(SongMasterError):
    """入力データやパース結果が仕様を満たさない場合の例外。"""


class GithubReleaseError(SongMasterError):
    """GitHub Release作成やAsset操作に失敗した場合の例外。"""
