"""Tests for SummaryStore (mercury_storage.SummaryStore)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mercury.storage import SummaryStore, apply_migrations, get_connection


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test_summary.db"
    apply_migrations(path)
    return path


@pytest.fixture()
def conn(db_path: Path):
    c = get_connection(db_path)
    # Insert a feed + entry so summary_results FK can resolve.
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
def store(conn) -> SummaryStore:
    return SummaryStore(conn)


def test_get_returns_none_when_missing(store: SummaryStore) -> None:
    assert store.get("e1") is None
    assert store.get_metadata("e1") is None


def test_save_and_get_roundtrip(store: SummaryStore) -> None:
    store.save_result("e1", "this is the summary", model_id="gpt-4o-mini@abc123")
    assert store.get("e1") == "this is the summary"
    meta = store.get_metadata("e1")
    assert meta is not None
    assert meta["summary_text"] == "this is the summary"
    assert meta["model_id"] == "gpt-4o-mini@abc123"
    assert meta["created_at"]  # ISO string, non-empty


def test_save_overwrites_previous(store: SummaryStore) -> None:
    store.save_result("e1", "first", "v1")
    store.save_result("e1", "second", "v2")
    assert store.get("e1") == "second"
    meta = store.get_metadata("e1")
    assert meta["model_id"] == "v2"


def test_empty_text_is_rejected(store: SummaryStore) -> None:
    """Failed/cancelled runs must not wipe a successful summary."""
    store.save_result("e1", "good", "v1")
    with pytest.raises(ValueError):
        store.save_result("e1", "", "v2")
    with pytest.raises(ValueError):
        store.save_result("e1", "   ", "v2")
    assert store.get("e1") == "good"


def test_empty_entry_id_is_rejected(store: SummaryStore) -> None:
    with pytest.raises(ValueError):
        store.save_result("", "summary", "m")


def test_get_with_empty_id_returns_none(store: SummaryStore) -> None:
    assert store.get("") is None
    assert store.get_metadata("") is None


def test_delete_removes_summary(store: SummaryStore) -> None:
    store.save_result("e1", "summary", "v1")
    store.delete("e1")
    assert store.get("e1") is None
