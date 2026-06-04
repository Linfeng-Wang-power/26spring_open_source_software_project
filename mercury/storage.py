"""Mercury local-storage layer.

Provides SQLite persistence for feeds, entries, reader content, and stubs for
future AI-result tables.  Implements the same public interface as
``mercury_feed.LocalFeedService`` so the GUI can swap the two with a one-line
change.

Swap in mercury_gui.py (~line 1211):
    Before:  feed_service=LocalFeedService()
    After:   feed_service=StorageService()

No GUI imports anywhere in this file.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from yoyo import get_backend, read_migrations

from mercury.feed import (
    Article,
    Feed,
    FeedParseError,
    discover_feed_url,
    parse_feed_xml,
    parse_opml,
)
from mercury.reader.models import ReaderDocument

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_DIR = Path.home() / ".mercury_pyqt"
DB_PATH = APP_DIR / "mercury.db"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _validate_feed_url(url: str) -> str:
    normalized = url.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入有效的 http(s) Feed URL。")
    return normalized


# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------

def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign-key enforcement."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_migrations(db_path: Path = DB_PATH) -> None:
    """Run all pending Yoyo migrations against *db_path*.

    Already-applied migrations are skipped automatically.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backend = get_backend(f"sqlite:///{db_path}")
    migrations = read_migrations(str(MIGRATIONS_DIR))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))


# ---------------------------------------------------------------------------
# Row dataclasses  (internal; not exposed to GUI)
# ---------------------------------------------------------------------------

@dataclass
class FeedRow:
    feed_id: str
    title: str
    url: str
    added_at: str


@dataclass
class EntryRow:
    entry_id: str
    feed_id: str
    stable_id: str
    title: str
    author: str
    url: str
    published: str
    summary: str
    is_starred: int = 0
    is_unread: int = 1


@dataclass
class ContentRow:
    entry_id: str
    title: str
    source_url: str
    final_url: str
    source_html: str
    cleaned_html: str
    canonical_markdown: str
    reader_html: str
    fetched_at: str


# ---------------------------------------------------------------------------
# FeedStore
# ---------------------------------------------------------------------------

class FeedStore:
    """CRUD for the ``feeds`` table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, title: str, url: str) -> str:
        """Insert or update a feed by URL; return its feed_id."""
        existing = self._conn.execute(
            "SELECT feed_id FROM feeds WHERE url = ?", (url,)
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE feeds SET title = ? WHERE feed_id = ?",
                (title, existing["feed_id"]),
            )
            return existing["feed_id"]
        feed_id = _new_id()
        self._conn.execute(
            "INSERT INTO feeds (feed_id, title, url, added_at) VALUES (?, ?, ?, ?)",
            (feed_id, title, url, _now()),
        )
        return feed_id

    def list_all(self) -> list[FeedRow]:
        rows = self._conn.execute(
            "SELECT feed_id, title, url, added_at FROM feeds ORDER BY added_at"
        ).fetchall()
        return [FeedRow(**dict(row)) for row in rows]

    def get_by_url(self, url: str) -> FeedRow | None:
        row = self._conn.execute(
            "SELECT feed_id, title, url, added_at FROM feeds WHERE url = ?", (url,)
        ).fetchone()
        return FeedRow(**dict(row)) if row else None

    def get_by_title(self, title: str) -> FeedRow | None:
        row = self._conn.execute(
            "SELECT feed_id, title, url, added_at FROM feeds WHERE title = ?", (title,)
        ).fetchone()
        return FeedRow(**dict(row)) if row else None

    def delete(self, feed_id: str) -> None:
        """Delete a feed and cascade-delete its entries."""
        self._conn.execute("DELETE FROM feeds WHERE feed_id = ?", (feed_id,))


# ---------------------------------------------------------------------------
# EntryStore
# ---------------------------------------------------------------------------

class EntryStore:
    """CRUD for the ``entries`` and ``tags`` tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, feed_id: str, article: Article) -> str:
        """Insert or update an entry by stable ID first, then feed-scoped URL."""
        stable_id = getattr(article, "stable_id", "") or ""
        existing = None
        if stable_id:
            existing = self._conn.execute(
                "SELECT entry_id FROM entries WHERE feed_id = ? AND stable_id = ?",
                (feed_id, stable_id),
            ).fetchone()
        if existing is None:
            existing = self._conn.execute(
                "SELECT entry_id FROM entries WHERE feed_id = ? AND url = ?",
                (feed_id, article.url),
            ).fetchone()

        if existing:
            entry_id = existing["entry_id"]
            self._conn.execute(
                """UPDATE entries
                   SET stable_id = ?, title = ?, author = ?, url = ?,
                       published = ?, summary = ?
                   WHERE entry_id = ?""",
                (stable_id, article.title, article.author, article.url,
                 article.published, article.summary, entry_id),
            )
        else:
            entry_id = _new_id()
            self._conn.execute(
                """INSERT INTO entries
                   (entry_id, feed_id, stable_id, title, author, url, published,
                    summary, is_starred, is_unread)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, feed_id, stable_id, article.title, article.author,
                 article.url, article.published, article.summary,
                 1 if article.starred else 0,
                 1 if article.unread else 0),
            )

        # Sync tags: delete then re-insert so renames are handled cleanly.
        self._conn.execute("DELETE FROM tags WHERE entry_id = ?", (entry_id,))
        for tag in article.tags:
            self._conn.execute(
                "INSERT OR IGNORE INTO tags (entry_id, tag) VALUES (?, ?)",
                (entry_id, tag),
            )
        return entry_id

    def list(
        self,
        feed_id: str | None = None,
        unread_only: bool = False,
        starred_only: bool = False,
    ) -> list[EntryRow]:
        clauses: list[str] = []
        params: list[object] = []

        if feed_id is not None:
            clauses.append("feed_id = ?")
            params.append(feed_id)
        if unread_only:
            clauses.append("is_unread = 1")
        if starred_only:
            clauses.append("is_starred = 1")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"""SELECT entry_id, feed_id, stable_id, title, author, url,
                       published, summary, is_starred, is_unread
                FROM entries {where}
                ORDER BY published DESC, entry_id""",
            params,
        ).fetchall()
        return [EntryRow(**dict(row)) for row in rows]

    def mark_read(self, entry_id: str) -> None:
        self._conn.execute(
            "UPDATE entries SET is_unread = 0 WHERE entry_id = ?", (entry_id,)
        )

    def set_unread(self, entry_id: str, unread: bool) -> None:
        self._conn.execute(
            "UPDATE entries SET is_unread = ? WHERE entry_id = ?",
            (1 if unread else 0, entry_id),
        )

    def mark_starred(self, entry_id: str, starred: bool) -> None:
        self._conn.execute(
            "UPDATE entries SET is_starred = ? WHERE entry_id = ?",
            (1 if starred else 0, entry_id),
        )

    def count_unread(self, feed_id: str | None = None) -> int:
        if feed_id is not None:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM entries WHERE feed_id = ? AND is_unread = 1",
                (feed_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM entries WHERE is_unread = 1"
            ).fetchone()
        return row[0] if row else 0

    def get_tags(self, entry_id: str) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT tag FROM tags WHERE entry_id = ?", (entry_id,)
        ).fetchall()
        return tuple(row[0] for row in rows)

    def list_tags(self) -> list[tuple[str, int]]:
        rows = self._conn.execute(
            """SELECT tag, COUNT(*) AS count
               FROM tags
               GROUP BY tag
               ORDER BY LOWER(tag)"""
        ).fetchall()
        return [(row["tag"], row["count"]) for row in rows]

    def list_by_tag(self, tag: str, unread_only: bool = False) -> list[EntryRow]:
        clauses = ["tags.tag = ?"]
        params: list[object] = [tag]
        if unread_only:
            clauses.append("entries.is_unread = 1")

        rows = self._conn.execute(
            f"""SELECT entries.entry_id, entries.feed_id, entries.stable_id,
                       entries.title, entries.author, entries.url,
                       entries.published, entries.summary,
                       entries.is_starred, entries.is_unread
                FROM entries
                JOIN tags ON tags.entry_id = entries.entry_id
                WHERE {' AND '.join(clauses)}
                ORDER BY entries.published DESC, entries.entry_id""",
            params,
        ).fetchall()
        return [EntryRow(**dict(row)) for row in rows]

    def add_tag(self, entry_id: str, tag: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO tags (entry_id, tag) VALUES (?, ?)",
            (entry_id, tag),
        )

    def remove_tag(self, entry_id: str, tag: str) -> None:
        self._conn.execute(
            "DELETE FROM tags WHERE entry_id = ? AND tag = ?",
            (entry_id, tag),
        )


# ---------------------------------------------------------------------------
# ContentStore
# ---------------------------------------------------------------------------

class ContentStore:
    """Persist and retrieve ``ReaderDocument`` objects from the ``contents`` table.

    Called by reader/pipeline.py after a document has been processed.
    The GUI's Reader panel calls ``get()`` to load cached content
    instead of re-fetching from the network.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, entry_id: str, doc: ReaderDocument) -> None:
        """Persist all representations of a processed article."""
        self._conn.execute(
            """INSERT OR REPLACE INTO contents
               (entry_id, title, source_url, final_url, source_html,
                cleaned_html, canonical_markdown, reader_html, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry_id, doc.title, doc.source_url, doc.final_url,
             doc.source_html, doc.cleaned_html, doc.canonical_markdown,
             doc.reader_html, _now()),
        )

    def get(self, entry_id: str) -> ReaderDocument | None:
        """Return the cached ReaderDocument, or None if not yet fetched."""
        row = self._conn.execute(
            """SELECT title, source_url, final_url, source_html,
                      cleaned_html, canonical_markdown, reader_html
               FROM contents WHERE entry_id = ?""",
            (entry_id,),
        ).fetchone()
        if row is None:
            return None
        return ReaderDocument(
            title=row["title"],
            source_url=row["source_url"],
            final_url=row["final_url"],
            source_html=row["source_html"],
            cleaned_html=row["cleaned_html"],
            canonical_markdown=row["canonical_markdown"],
            reader_html=row["reader_html"],
        )

    def has(self, entry_id: str) -> bool:
        """Return True if cleaned content is already stored for this entry."""
        row = self._conn.execute(
            "SELECT 1 FROM contents WHERE entry_id = ?", (entry_id,)
        ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Stubs for future modules
# ---------------------------------------------------------------------------

class SummaryStore:
    """Storage interface for Summary Agent results.

    Backed by the ``summary_results`` table (migration 0003). Failures must NOT
    overwrite an existing successful result, so ``save_result`` rejects empty
    summary text.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_result(self, entry_id: str, summary_text: str, model_id: str = "") -> None:
        """Persist a successful summary result; overwrites any previous result.

        Empty *summary_text* is rejected so a cancelled or failed run cannot
        wipe an earlier success.
        """
        if not summary_text or not summary_text.strip():
            raise ValueError("summary_text must not be empty")
        if not entry_id:
            raise ValueError("entry_id must not be empty")
        self._conn.execute(
            """INSERT OR REPLACE INTO summary_results
               (entry_id, summary_text, model_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (entry_id, summary_text, model_id, _now()),
        )
        self._conn.commit()

    def get(self, entry_id: str) -> str | None:
        """Return the cached summary text, or None if not yet generated."""
        if not entry_id:
            return None
        row = self._conn.execute(
            "SELECT summary_text FROM summary_results WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()
        if row is None:
            return None
        text = row["summary_text"]
        return text or None

    def get_metadata(self, entry_id: str) -> dict | None:
        """Return ``{summary_text, model_id, created_at}`` or None."""
        if not entry_id:
            return None
        row = self._conn.execute(
            """SELECT summary_text, model_id, created_at
               FROM summary_results WHERE entry_id = ?""",
            (entry_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "summary_text": row["summary_text"],
            "model_id": row["model_id"],
            "created_at": row["created_at"],
        }

    def delete(self, entry_id: str) -> None:
        """Remove a stored summary (used for manual clear)."""
        self._conn.execute(
            "DELETE FROM summary_results WHERE entry_id = ?", (entry_id,)
        )
        self._conn.commit()


class TranslationStore:
    """Storage interface for Translation Agent segment results.

    Schema is live (migration 0003).  Implementation to be filled in by 张睿桐.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_segments(
        self,
        entry_id: str,
        segments: list[dict],
        target_lang: str = "zh-CN",
    ) -> None:
        """Persist translated segments for an entry.

        Each dict in *segments* must have keys:
        ``source_hash``, ``source_text``, ``trans_text``, ``position``.
        """
        raise NotImplementedError

    def get_segments(
        self, entry_id: str, target_lang: str = "zh-CN"
    ) -> list[dict]:
        """Return translated segments ordered by position, or [] if not cached."""
        raise NotImplementedError


class ProviderStore:
    """Storage interface for LLM provider profiles.

    Schema is live (migration 0004).  Implementation to be filled in by 张睿桐.
    API keys must NOT be stored in SQLite; use ``keyring`` instead.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, name: str, base_url: str) -> str:
        """Persist a provider profile; return its provider_id."""
        raise NotImplementedError

    def list(self) -> list[dict]:
        """Return all saved provider profiles (without API keys)."""
        raise NotImplementedError

    def get_api_key(self, provider_id: str) -> str | None:
        """Look up the API key from keyring for this provider."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# SettingsStore
# ---------------------------------------------------------------------------

class SettingsStore:
    """Key-value store for UI preferences and lightweight app config.

    Implements the ``SettingsStore`` protocol from ``mercury_gui.py``.
    Backed by the ``settings`` table (migration 0005).

    Business-level provider config lives in ``ProviderStore``.
    Ephemeral window geometry can go in ``QSettings`` — this store is for
    anything that should survive a fresh OS install but travel with the DB.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str, default: str = "") -> str:
        """Return the value for *key*, or *default* if not set."""
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        """Upsert a key-value pair."""
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    # -- SettingsStore protocol (mercury_gui.py) -----------------------------

    def current_language(self) -> str:
        """Return the active UI language tag, e.g. ``'zh-CN'`` or ``'en'``."""
        return self.get("ui.language", "zh-CN")


# ---------------------------------------------------------------------------
# StorageService  — drop-in replacement for LocalFeedService
# ---------------------------------------------------------------------------

class StorageService:
    """SQLite-backed feed service.

    Implements the ``FeedService`` protocol from ``mercury_gui.py``.
    Feed parsing is still delegated to ``mercury_feed.py``; only the
    persistence layer changes from JSON to SQLite.
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.last_error: str | None = None
        self._db_path = db_path
        apply_migrations(db_path)
        self._conn = get_connection(db_path)
        self._feeds = FeedStore(self._conn)
        self._entries = EntryStore(self._conn)

    def create_worker_copy(self) -> "StorageService":
        """Create a same-database service with a thread-local SQLite connection."""
        return StorageService(db_path=self._db_path)

    # -- FeedService protocol ------------------------------------------------

    def list_feeds(self) -> list[Feed]:
        """Return Feed DTOs for the GUI sidebar."""
        feeds: list[Feed] = [
            Feed("All Feeds", "internal://all", self._entries.count_unread()),
            Feed(
                "Starred",
                "internal://starred",
                len(self._entries.list(starred_only=True)),
            ),
        ]
        for feed_row in self._feeds.list_all():
            unread = self._entries.count_unread(feed_row.feed_id)
            feeds.append(Feed(feed_row.title, feed_row.url, unread))
        return feeds

    def list_articles(self, feed_title: str | None = None, unread_only: bool = False) -> list[Article]:
        """Return Article DTOs for the GUI article list."""
        if feed_title in (None, "All Feeds"):
            rows = self._entries.list(unread_only=unread_only)
        elif feed_title == "Starred":
            rows = self._entries.list(unread_only=unread_only, starred_only=True)
        else:
            feed_row = self._feeds.get_by_title(feed_title)
            rows = self._entries.list(feed_id=feed_row.feed_id, unread_only=unread_only) if feed_row else []
        return [self._to_article(row) for row in rows]

    def list_articles_by_tag(self, tag: str, unread_only: bool = False) -> list[Article]:
        """Return Article DTOs having a specific tag."""
        rows = self._entries.list_by_tag(tag, unread_only=unread_only)
        return [self._to_article(row) for row in rows]

    def list_tags(self) -> list[tuple[str, int]]:
        """Return all tags and their article counts."""
        return self._entries.list_tags()

    def add_feed(self, url: str) -> None:
        normalized = _validate_feed_url(url)
        if self._feeds.get_by_url(normalized):
            return
        feed_title, articles = self._fetch_and_parse(normalized)
        self._conn.execute("BEGIN")
        try:
            feed_id = self._feeds.upsert(feed_title, normalized)
            for article in articles:
                self._entries.upsert(feed_id, article)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def import_opml(self, path: str) -> None:
        subscriptions = parse_opml(Path(path).read_text(encoding="utf-8"))
        self._conn.execute("BEGIN")
        try:
            for sub in subscriptions:
                if not self._feeds.get_by_url(sub.url):
                    self._feeds.upsert(sub.title, sub.url)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def refresh_all(self) -> None:
        self.last_error = None
        errors: list[str] = []
        for feed_row in self._feeds.list_all():
            try:
                title, articles = self._fetch_and_parse(feed_row.url)
                self._conn.execute("BEGIN")
                feed_id = self._feeds.upsert(title, feed_row.url)
                for article in articles:
                    self._entries.upsert(feed_id, article)
                self._conn.commit()
            except Exception as exc:
                self._conn.rollback()
                errors.append(f"{feed_row.url}: {exc}")
        self.last_error = "\n".join(errors) if errors else None

    def delete_feed(self, feed_title: str) -> None:
        """Delete a user feed by title and cascade its entries/content."""
        if feed_title in {"All Feeds", "Starred"}:
            raise ValueError("内置视图不能删除。")
        feed_row = self._feeds.get_by_title(feed_title)
        if feed_row is None:
            raise ValueError("未找到要删除的订阅。")
        self._feeds.delete(feed_row.feed_id)
        self._conn.commit()

    def delete_feeds(self, feed_titles: list[str]) -> None:
        """Delete multiple user feeds in one transaction."""
        real_titles = [title for title in feed_titles if title not in {"All Feeds", "Starred"}]
        if not real_titles:
            raise ValueError("请选择至少一个真实订阅。")
        self._conn.execute("BEGIN")
        try:
            for title in real_titles:
                feed_row = self._feeds.get_by_title(title)
                if feed_row is not None:
                    self._feeds.delete(feed_row.feed_id)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def set_article_starred(self, entry_id: str, starred: bool) -> None:
        """Update favorite state for one entry."""
        if not entry_id:
            raise ValueError("当前文章缺少 entry_id，无法收藏。")
        self._entries.mark_starred(entry_id, starred)
        self._conn.commit()

    def set_article_unread(self, entry_id: str, unread: bool) -> None:
        """Update read state for one entry."""
        if not entry_id:
            raise ValueError("当前文章缺少 entry_id，无法设置已读状态。")
        self._entries.set_unread(entry_id, unread)
        self._conn.commit()

    def add_article_tag(self, entry_id: str, tag: str) -> None:
        """Add a custom tag to one article."""
        normalized = tag.strip()
        if not entry_id:
            raise ValueError("当前文章缺少 entry_id，无法添加标签。")
        if not normalized:
            raise ValueError("标签不能为空。")
        self._entries.add_tag(entry_id, normalized)
        self._conn.commit()

    def remove_article_tag(self, entry_id: str, tag: str) -> None:
        """Remove one tag from one article."""
        normalized = tag.strip()
        if not entry_id:
            raise ValueError("当前文章缺少 entry_id，无法移除标签。")
        if not normalized:
            raise ValueError("标签不能为空。")
        self._entries.remove_tag(entry_id, normalized)
        self._conn.commit()

    def mark_tag_read(self, tag: str) -> None:
        """Mark all entries under a tag as read."""
        for row in self._entries.list_by_tag(tag):
            self._entries.set_unread(row.entry_id, False)
        self._conn.commit()

    def star_tag_articles(self, tag: str, starred: bool = True) -> None:
        """Favorite or unfavorite all entries under a tag."""
        for row in self._entries.list_by_tag(tag):
            self._entries.mark_starred(row.entry_id, starred)
        self._conn.commit()

    # -- Store accessors (for other modules to use) --------------------------

    @property
    def content_store(self) -> ContentStore:
        """Expose ContentStore so reader/pipeline.py can persist documents."""
        return ContentStore(self._conn)

    def get_reader_document(self, entry_id: str) -> ReaderDocument | None:
        """Return cached reader content for a GUI entry."""
        return self.content_store.get(entry_id)

    def save_reader_document(self, entry_id: str, document: ReaderDocument) -> None:
        """Persist cleaned reader content and commit it as one GUI action."""
        self.content_store.save(entry_id, document)
        self._conn.commit()

    @property
    def summary_store(self) -> SummaryStore:
        """Expose SummaryStore for 陆骏凯's SummaryAgent."""
        return SummaryStore(self._conn)

    @property
    def translation_store(self) -> TranslationStore:
        """Expose TranslationStore for 张睿桐's TranslationAgent."""
        return TranslationStore(self._conn)

    @property
    def provider_store(self) -> ProviderStore:
        """Expose ProviderStore for 张睿桐's LLMProvider."""
        return ProviderStore(self._conn)

    @property
    def settings_store(self) -> SettingsStore:
        """Expose SettingsStore for UI preferences and language config."""
        return SettingsStore(self._conn)

    # -- Internal helpers ----------------------------------------------------

    def _fetch_and_parse(self, url: str) -> tuple[str, list[Article]]:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=12.0,
            headers={"User-Agent": "MercuryPyQt/0.1 (+local-first RSS reader)"},
        )
        response.raise_for_status()
        source_url = str(response.url)
        try:
            return parse_feed_xml(response.text, source_url=source_url)
        except FeedParseError:
            discovered = discover_feed_url(response.text, source_url)
            if not discovered or discovered == source_url:
                raise
            r2 = httpx.get(
                discovered,
                follow_redirects=True,
                timeout=12.0,
                headers={"User-Agent": "MercuryPyQt/0.1 (+local-first RSS reader)"},
            )
            r2.raise_for_status()
            return parse_feed_xml(r2.text, source_url=str(r2.url))

    def _to_article(self, row: EntryRow) -> Article:
        feed_row = self._conn.execute(
            "SELECT title FROM feeds WHERE feed_id = ?", (row.feed_id,)
        ).fetchone()
        feed_title = feed_row["title"] if feed_row else ""
        tags = self._entries.get_tags(row.entry_id)
        return Article(
            title=row.title,
            feed_title=feed_title,
            author=row.author,
            published=row.published,
            url=row.url,
            summary=row.summary,
            markdown=row.summary,  # ContentStore.get() upgrades this to real markdown
            stable_id=row.stable_id,
            entry_id=row.entry_id,
            tags=tags,
            starred=bool(row.is_starred),
            unread=bool(row.is_unread),
        )
