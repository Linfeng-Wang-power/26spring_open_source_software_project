"""Tests for mercury_storage.py.

Covers: migrations, FeedStore, EntryStore, ContentStore, SettingsStore,
and StorageService public interface.

All tests use a temporary on-disk SQLite file (tmp_path fixture) so they
never touch the real ~/.mercury_pyqt/mercury.db.
"""

from __future__ import annotations


import pytest
from pathlib import Path

from mercury_feed import Article
from mercury_storage import (
    ContentStore,
    EntryStore,
    FeedStore,
    SettingsStore,
    StorageService,
    apply_migrations,
    get_connection,
)
from reader.models import ReaderDocument


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test_mercury.db"
    apply_migrations(path)
    return path


@pytest.fixture()
def conn(db_path: Path):
    c = get_connection(db_path)
    yield c
    c.close()


@pytest.fixture()
def feeds(conn):
    return FeedStore(conn)


@pytest.fixture()
def entries(conn):
    return EntryStore(conn)


@pytest.fixture()
def contents(conn):
    return ContentStore(conn)


@pytest.fixture()
def settings(conn):
    return SettingsStore(conn)


@pytest.fixture()
def svc(db_path: Path) -> StorageService:
    return StorageService(db_path=db_path)


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

def _make_article(
    *,
    url: str = "https://example.com/article-1",
    title: str = "Test Article",
    stable_id: str = "",
    starred: bool = False,
    unread: bool = True,
    tags: tuple[str, ...] = ("Python",),
) -> Article:
    return Article(
        title=title,
        feed_title="Test Feed",
        author="Test Author",
        published="2026-06-01 10:00",
        url=url,
        summary="A test summary.",
        markdown="A test markdown body.",
        stable_id=stable_id,
        tags=tags,
        starred=starred,
        unread=unread,
    )


def _make_reader_doc(url: str = "https://example.com/article-1") -> ReaderDocument:
    return ReaderDocument(
        title="Reader Title",
        source_url=url,
        final_url=url,
        source_html="<html><body><p>hello</p></body></html>",
        cleaned_html="<p>hello</p>",
        canonical_markdown="hello",
        reader_html="<article><p>hello</p></article>",
    )


# ---------------------------------------------------------------------------
# 1. Migration tests
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "feeds", "entries", "contents", "tags",
    "summary_results", "translation_segments",
    "provider_profiles", "agent_runs", "settings",
}


def test_migrations_create_all_business_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    actual = {r["name"] for r in rows}
    assert EXPECTED_TABLES.issubset(actual), (
        f"Missing tables: {EXPECTED_TABLES - actual}"
    )


def test_migrations_are_idempotent(db_path: Path):
    """Running apply_migrations twice must not raise or duplicate tables."""
    apply_migrations(db_path)  # second call
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    conn.close()
    actual = {r["name"] for r in rows}
    assert EXPECTED_TABLES.issubset(actual)


# ---------------------------------------------------------------------------
# 2. FeedStore tests
# ---------------------------------------------------------------------------

def test_feed_store_upsert_returns_id(feeds):
    feed_id = feeds.upsert("My Blog", "https://myblog.com/feed")
    assert isinstance(feed_id, str) and len(feed_id) == 36  # UUID


def test_feed_store_list_all(feeds):
    feeds.upsert("Blog A", "https://a.com/feed")
    feeds.upsert("Blog B", "https://b.com/feed")
    all_feeds = feeds.list_all()
    urls = [f.url for f in all_feeds]
    assert "https://a.com/feed" in urls
    assert "https://b.com/feed" in urls


def test_feed_store_upsert_same_url_updates_title(feeds):
    feed_id_1 = feeds.upsert("Old Title", "https://x.com/feed")
    feed_id_2 = feeds.upsert("New Title", "https://x.com/feed")
    assert feed_id_1 == feed_id_2  # same row
    row = feeds.get_by_url("https://x.com/feed")
    assert row.title == "New Title"


def test_feed_store_get_by_url_returns_none_if_missing(feeds):
    assert feeds.get_by_url("https://notexist.com/feed") is None


def test_feed_store_get_by_title(feeds):
    feeds.upsert("Mercury Blog", "https://mercury.com/feed")
    row = feeds.get_by_title("Mercury Blog")
    assert row is not None
    assert row.url == "https://mercury.com/feed"


def test_feed_store_delete(feeds, conn):
    feed_id = feeds.upsert("To Delete", "https://del.com/feed")
    feeds.delete(feed_id)
    assert feeds.get_by_url("https://del.com/feed") is None


# ---------------------------------------------------------------------------
# 3. EntryStore tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def feed_id(feeds) -> str:
    return feeds.upsert("Test Feed", "https://testfeed.com/rss")


def test_entry_store_upsert_returns_id(entries, feed_id):
    article = _make_article()
    eid = entries.upsert(feed_id, article)
    assert isinstance(eid, str) and len(eid) == 36


def test_entry_store_upsert_same_url_updates_title(entries, feed_id):
    old = _make_article(title="Old Title")
    new = _make_article(title="New Title")
    id1 = entries.upsert(feed_id, old)
    id2 = entries.upsert(feed_id, new)
    assert id1 == id2
    rows = entries.list(feed_id=feed_id)
    assert rows[0].title == "New Title"


def test_entry_store_upsert_prefers_stable_id(entries, feed_id):
    first = _make_article(
        url="https://example.com/old-url",
        title="Old URL",
        stable_id="entry-guid-1",
    )
    moved = _make_article(
        url="https://example.com/new-url",
        title="New URL",
        stable_id="entry-guid-1",
    )

    id1 = entries.upsert(feed_id, first)
    id2 = entries.upsert(feed_id, moved)

    rows = entries.list(feed_id=feed_id)
    assert id1 == id2
    assert len(rows) == 1
    assert rows[0].url == "https://example.com/new-url"
    assert rows[0].stable_id == "entry-guid-1"


def test_entry_store_list_all(entries, feed_id):
    entries.upsert(feed_id, _make_article(url="https://a.com/1"))
    entries.upsert(feed_id, _make_article(url="https://a.com/2"))
    rows = entries.list()
    assert len(rows) == 2


def test_entry_store_filter_by_feed(entries, feeds):
    fid_a = feeds.upsert("Feed A", "https://a.com/rss")
    fid_b = feeds.upsert("Feed B", "https://b.com/rss")
    entries.upsert(fid_a, _make_article(url="https://a.com/1"))
    entries.upsert(fid_b, _make_article(url="https://b.com/1"))
    assert len(entries.list(feed_id=fid_a)) == 1
    assert len(entries.list(feed_id=fid_b)) == 1


def test_entry_store_filter_unread_only(entries, feed_id):
    entries.upsert(feed_id, _make_article(url="https://a.com/1", unread=True))
    entries.upsert(feed_id, _make_article(url="https://a.com/2", unread=False))
    unread = entries.list(unread_only=True)
    assert len(unread) == 1


def test_entry_store_filter_starred_only(entries, feed_id):
    entries.upsert(feed_id, _make_article(url="https://a.com/1", starred=True))
    entries.upsert(feed_id, _make_article(url="https://a.com/2", starred=False))
    starred = entries.list(starred_only=True)
    assert len(starred) == 1


def test_entry_store_mark_read(entries, feed_id):
    eid = entries.upsert(feed_id, _make_article(unread=True))
    entries.mark_read(eid)
    rows = entries.list(unread_only=True)
    assert all(r.entry_id != eid for r in rows)


def test_entry_store_mark_starred(entries, feed_id):
    eid = entries.upsert(feed_id, _make_article(starred=False))
    entries.mark_starred(eid, True)
    rows = entries.list(starred_only=True)
    assert any(r.entry_id == eid for r in rows)


def test_entry_store_count_unread(entries, feed_id):
    entries.upsert(feed_id, _make_article(url="https://a.com/1", unread=True))
    entries.upsert(feed_id, _make_article(url="https://a.com/2", unread=True))
    entries.upsert(feed_id, _make_article(url="https://a.com/3", unread=False))
    assert entries.count_unread() == 2
    assert entries.count_unread(feed_id=feed_id) == 2


def test_entry_store_delete_feed_cascades_entries(entries, feeds, conn):
    fid = feeds.upsert("Temp Feed", "https://temp.com/rss")
    entries.upsert(fid, _make_article(url="https://temp.com/1"))
    feeds.delete(fid)
    conn.commit()
    remaining = entries.list(feed_id=fid)
    assert remaining == []


def test_entry_store_tags(entries, feed_id):
    eid = entries.upsert(feed_id, _make_article(tags=("Python", "RSS")))
    tags = entries.get_tags(eid)
    assert set(tags) == {"Python", "RSS"}


def test_entry_store_tags_updated_on_re_upsert(entries, feed_id):
    url = "https://a.com/1"
    entries.upsert(feed_id, _make_article(url=url, tags=("Old",)))
    eid = entries.upsert(feed_id, _make_article(url=url, tags=("New1", "New2")))
    assert set(entries.get_tags(eid)) == {"New1", "New2"}


# ---------------------------------------------------------------------------
# 4. ContentStore tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def entry_id(entries, feeds) -> str:
    fid = feeds.upsert("Content Test Feed", "https://content.com/rss")
    return entries.upsert(fid, _make_article())


def test_content_store_save_and_get(contents, entry_id):
    doc = _make_reader_doc()
    contents.save(entry_id, doc)
    retrieved = contents.get(entry_id)
    assert retrieved is not None
    assert retrieved.title == doc.title
    assert retrieved.canonical_markdown == doc.canonical_markdown
    assert retrieved.cleaned_html == doc.cleaned_html
    assert retrieved.reader_html == doc.reader_html


def test_content_store_has(contents, entry_id):
    assert not contents.has(entry_id)
    contents.save(entry_id, _make_reader_doc())
    assert contents.has(entry_id)


def test_content_store_get_returns_none_if_missing(contents, entry_id):
    assert contents.get(entry_id) is None


def test_content_store_save_overwrites(contents, entry_id):
    contents.save(entry_id, _make_reader_doc())
    doc2 = ReaderDocument(
        title="Updated",
        source_url="https://example.com/article-1",
        final_url="https://example.com/article-1",
        source_html="<html></html>",
        cleaned_html="<p>updated</p>",
        canonical_markdown="updated",
        reader_html="<p>updated</p>",
    )
    contents.save(entry_id, doc2)
    result = contents.get(entry_id)
    assert result.title == "Updated"
    assert result.canonical_markdown == "updated"


# ---------------------------------------------------------------------------
# 5. SettingsStore tests
# ---------------------------------------------------------------------------

def test_settings_store_default_language(settings):
    assert settings.current_language() == "zh-CN"


def test_settings_store_get_missing_key_returns_default(settings):
    assert settings.get("no.such.key", "fallback") == "fallback"
    assert settings.get("no.such.key") == ""


def test_settings_store_set_and_get(settings):
    settings.set("ui.language", "en")
    assert settings.get("ui.language") == "en"
    assert settings.current_language() == "en"


def test_settings_store_set_overwrites(settings):
    settings.set("ui.theme", "dark")
    settings.set("ui.theme", "light")
    assert settings.get("ui.theme") == "light"


# ---------------------------------------------------------------------------
# 6. StorageService interface tests
# ---------------------------------------------------------------------------

def test_storage_service_initial_feeds(svc):
    feeds = svc.list_feeds()
    titles = [f.title for f in feeds]
    assert "All Feeds" in titles
    assert "Starred" in titles
    assert len(feeds) == 2  # no real feeds yet


def test_storage_service_list_articles_empty(svc):
    assert svc.list_articles() == []
    assert svc.list_articles("All Feeds") == []
    assert svc.list_articles("Starred") == []


def test_storage_service_settings_store_exposed(svc):
    store = svc.settings_store
    assert store.current_language() == "zh-CN"


def test_storage_service_content_store_exposed(svc):
    store = svc.content_store
    assert store is not None


def test_storage_service_returns_entry_id_and_saves_reader_document(svc):
    feed_id = svc._feeds.upsert("Saved Feed", "https://saved.test/rss")
    entry_id = svc._entries.upsert(
        feed_id,
        _make_article(url="https://saved.test/article", stable_id="saved-1"),
    )
    article = svc.list_articles("Saved Feed")[0]
    doc = _make_reader_doc(url=article.url)

    svc.save_reader_document(article.entry_id, doc)
    cached = svc.get_reader_document(entry_id)

    assert article.entry_id == entry_id
    assert article.stable_id == "saved-1"
    assert cached is not None
    assert cached.canonical_markdown == "hello"


def test_storage_service_delete_feed_removes_entries(svc):
    feed_id = svc._feeds.upsert("Delete Me", "https://delete.test/rss")
    svc._entries.upsert(feed_id, _make_article(url="https://delete.test/1"))

    svc.delete_feed("Delete Me")

    assert "Delete Me" not in [feed.title for feed in svc.list_feeds()]
    assert svc.list_articles("Delete Me") == []


def test_storage_service_starred_and_read_state_updates(svc):
    feed_id = svc._feeds.upsert("State Feed", "https://state.test/rss")
    entry_id = svc._entries.upsert(
        feed_id,
        _make_article(url="https://state.test/1", starred=False, unread=True),
    )

    svc.set_article_starred(entry_id, True)
    svc.set_article_unread(entry_id, False)
    article = svc.list_articles("State Feed")[0]

    assert article.starred is True
    assert article.unread is False
    assert svc.list_articles("State Feed", unread_only=True) == []

    svc.set_article_unread(entry_id, True)
    assert len(svc.list_articles("State Feed", unread_only=True)) == 1


def test_storage_service_tag_operations(svc):
    feed_id = svc._feeds.upsert("Tag Feed", "https://tag.test/rss")
    entry_id = svc._entries.upsert(
        feed_id,
        _make_article(url="https://tag.test/1", tags=()),
    )

    svc.add_article_tag(entry_id, "稍后读")
    tagged = svc.list_articles_by_tag("稍后读")
    assert len(tagged) == 1
    assert tagged[0].entry_id == entry_id
    assert ("稍后读", 1) in svc.list_tags()

    svc.mark_tag_read("稍后读")
    assert svc.list_articles_by_tag("稍后读")[0].unread is False

    svc.star_tag_articles("稍后读", True)
    assert svc.list_articles_by_tag("稍后读")[0].starred is True

    svc.remove_article_tag(entry_id, "稍后读")
    assert svc.list_articles_by_tag("稍后读") == []


def test_no_qt_import():
    """mercury_storage must not import any Qt module."""
    import sys
    import importlib
    # Re-check sys.modules after import
    qt_mods = [m for m in sys.modules if "PySide" in m or "PyQt" in m]
    assert qt_mods == [], f"Unexpected Qt modules: {qt_mods}"
