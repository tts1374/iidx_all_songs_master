"""Release decisions against the latest published SQLite."""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from src.build_validation import should_create_release

pytestmark = [pytest.mark.light, pytest.mark.full]


@pytest.fixture
def databases(tmp_path):
    published = tmp_path / "published.sqlite"
    generated = tmp_path / "generated.sqlite"
    with sqlite3.connect(published) as conn:
        conn.executescript(
            """
            CREATE TABLE music (
                music_id INTEGER PRIMARY KEY,
                textage_id TEXT UNIQUE,
                title TEXT,
                is_ac_active INTEGER,
                is_inf_active INTEGER,
                updated_at TEXT
            );
            CREATE TABLE chart (
                chart_id INTEGER PRIMARY KEY,
                music_id INTEGER,
                play_style TEXT,
                difficulty TEXT,
                is_ac_active INTEGER,
                is_inf_active INTEGER
            );
            CREATE TABLE music_title_alias (alias TEXT);
            INSERT INTO music VALUES (1, 'alpha', 'Old title', 1, 1, 'old');
            INSERT INTO chart VALUES (10, 1, 'SP', 'NORMAL', 1, 1);
            INSERT INTO music_title_alias VALUES ('old alias');
            """
        )
    shutil.copyfile(published, generated)
    return published, generated


def change(path, sql):
    with sqlite3.connect(path) as conn:
        conn.executescript(sql)


def test_music_addition_requires_release(databases):
    published, generated = databases
    change(generated, "INSERT INTO music VALUES (2, 'beta', 'New', 0, 0, 'new');")
    assert should_create_release(str(published), str(generated))


@pytest.mark.parametrize("column", ["is_ac_active", "is_inf_active"])
@pytest.mark.parametrize("old,new", [(0, 1), (1, 0)])
def test_music_activity_change_requires_release(databases, column, old, new):
    published, generated = databases
    change(published, f"UPDATE music SET {column} = {old};")
    change(generated, f"UPDATE music SET {column} = {new};")
    assert should_create_release(str(published), str(generated))


def test_chart_addition_requires_release(databases):
    published, generated = databases
    change(generated, "INSERT INTO chart VALUES (11, 1, 'DP', 'NORMAL', 0, 0);")
    assert should_create_release(str(published), str(generated))


@pytest.mark.parametrize("column", ["is_ac_active", "is_inf_active"])
@pytest.mark.parametrize("old,new", [(0, 1), (1, 0)])
def test_chart_activity_change_requires_release(databases, column, old, new):
    published, generated = databases
    change(published, f"UPDATE chart SET {column} = {old};")
    change(generated, f"UPDATE chart SET {column} = {new};")
    assert should_create_release(str(published), str(generated))


def test_title_only_change_does_not_require_release(databases):
    published, generated = databases
    change(generated, "UPDATE music SET title = 'Corrected title';")
    assert not should_create_release(str(published), str(generated))


def test_timestamp_and_alias_only_changes_do_not_require_release(databases):
    published, generated = databases
    change(
        generated,
        """
        UPDATE music SET updated_at = 'new';
        DELETE FROM music_title_alias;
        INSERT INTO music_title_alias VALUES ('regenerated alias');
        """,
    )
    assert not should_create_release(str(published), str(generated))


def test_internal_ids_are_not_release_keys(databases):
    published, generated = databases
    change(generated, "UPDATE music SET music_id = 7; UPDATE chart SET music_id = 7, chart_id = 20;")
    assert not should_create_release(str(published), str(generated))


def test_missing_music_is_an_error(databases):
    published, generated = databases
    change(generated, "DELETE FROM chart; DELETE FROM music;")
    with pytest.raises(RuntimeError, match="missing music rows"):
        should_create_release(str(published), str(generated))


def test_missing_chart_is_an_error_even_with_addition(databases):
    published, generated = databases
    change(
        generated,
        "DELETE FROM chart; INSERT INTO chart VALUES (11, 1, 'DP', 'NORMAL', 1, 1);",
    )
    with pytest.raises(RuntimeError, match="missing chart rows"):
        should_create_release(str(published), str(generated))


def test_no_comparable_published_sqlite_requires_release(databases):
    _, generated = databases
    assert should_create_release(None, str(generated))


def test_skipped_changes_accumulate_until_release_worthy_change(databases):
    published, generated = databases
    change(generated, "UPDATE music SET title = 'Corrected title';")
    assert not should_create_release(str(published), str(generated))

    change(generated, "UPDATE music SET updated_at = 'new';")
    assert not should_create_release(str(published), str(generated))

    change(generated, "INSERT INTO chart VALUES (11, 1, 'DP', 'NORMAL', 0, 0);")
    assert should_create_release(str(published), str(generated))
    with sqlite3.connect(generated) as conn:
        assert conn.execute("SELECT title, updated_at FROM music").fetchone() == (
            "Corrected title", "new"
        )
