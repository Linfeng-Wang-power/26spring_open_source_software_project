"""Tests for TranslationStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from mercury.storage import TranslationStore, apply_migrations, get_connection


@pytest.fixture()
def conn(tmp_path: Path):
    path = tmp_path / "test_translation.db"
    apply_migrations(path)
    c = get_connection(path)
    c.execute(
        "INSERT INTO feeds (feed_id, title, url, added_at) VALUES (?,?,?,?)",
        ("f1", "Feed", "https://x", "2025-01-01"),
    )
    c.execute(
        "INSERT INTO entries (entry_id, feed_id, stable_id, title, url, published, summary)"
        " VALUES (?,?,?,?,?,?,?)",
        ("e1", "f1", "s1", "Hello", "https://x/1", "2025-01-01", "rss summary"),
    )
    c.commit()
    yield c
    c.close()


@pytest.fixture()
def store(conn) -> TranslationStore:
    return TranslationStore(conn)


def _segments(prefix: str = "") -> list[dict]:
    return [
        {
            "source_hash": f"{prefix}h1",
            "source_text": "hello",
            "trans_text": "你好",
            "position": 0,
        },
        {
            "source_hash": f"{prefix}h2",
            "source_text": "world",
            "trans_text": "世界",
            "position": 1,
        },
    ]


def test_save_and_get_segments_roundtrip(store: TranslationStore) -> None:
    store.save_segments("e1", _segments(), "zh-CN")

    rows = store.get_segments("e1", "zh-CN")

    assert [row["source_text"] for row in rows] == ["hello", "world"]
    assert [row["trans_text"] for row in rows] == ["你好", "世界"]
    assert [row["position"] for row in rows] == [0, 1]
    assert rows[0]["created_at"]


def test_save_replaces_same_entry_and_language(store: TranslationStore) -> None:
    store.save_segments("e1", _segments(), "zh-CN")
    store.save_segments(
        "e1",
        [
            {
                "source_hash": "h3",
                "source_text": "new",
                "trans_text": "新的",
                "position": 0,
            }
        ],
        "zh-CN",
    )

    rows = store.get_segments("e1", "zh-CN")

    assert len(rows) == 1
    assert rows[0]["source_text"] == "new"


def test_different_target_languages_do_not_overwrite(store: TranslationStore) -> None:
    store.save_segments("e1", _segments("zh"), "zh-CN")
    store.save_segments("e1", _segments("en"), "en")

    assert len(store.get_segments("e1", "zh-CN")) == 2
    assert len(store.get_segments("e1", "en")) == 2


def test_invalid_segments_are_rejected_without_overwrite(store: TranslationStore) -> None:
    store.save_segments("e1", _segments(), "zh-CN")

    with pytest.raises(ValueError):
        store.save_segments("e1", [], "zh-CN")
    with pytest.raises(ValueError):
        store.save_segments("e1", [{"source_text": "x", "trans_text": ""}], "zh-CN")

    assert len(store.get_segments("e1", "zh-CN")) == 2


def test_get_segments_returns_empty_for_missing(store: TranslationStore) -> None:
    assert store.get_segments("missing", "zh-CN") == []
