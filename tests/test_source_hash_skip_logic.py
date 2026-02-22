"""Tests for build source hash skip decision."""

from __future__ import annotations

import pytest

from main import MANUAL_ALIAS_HASH_KEY, has_same_textage_source_hashes


@pytest.mark.light
def test_has_same_textage_source_hashes_true_when_all_required_hashes_match():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_HASH_KEY: "d",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_HASH_KEY: "d",
    }
    assert has_same_textage_source_hashes(previous, current) is True


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_manual_hash_is_missing_in_previous():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_HASH_KEY: "d",
    }
    assert has_same_textage_source_hashes(previous, current) is False


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_manual_hash_differs():
    previous = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_HASH_KEY: "old",
    }
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_HASH_KEY: "new",
    }
    assert has_same_textage_source_hashes(previous, current) is False


@pytest.mark.light
def test_has_same_textage_source_hashes_false_when_previous_hashes_is_none():
    current = {
        "titletbl.js": "a",
        "datatbl.js": "b",
        "actbl.js": "c",
        MANUAL_ALIAS_HASH_KEY: "d",
    }
    assert has_same_textage_source_hashes(None, current) is False

