-- Migration 0001: core feed and entry tables
-- depends:

CREATE TABLE feeds (
    feed_id  TEXT PRIMARY KEY,
    title    TEXT NOT NULL,
    url      TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL          -- ISO-8601 UTC
);

CREATE TABLE entries (
    entry_id   TEXT PRIMARY KEY,
    feed_id    TEXT NOT NULL REFERENCES feeds(feed_id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    author     TEXT NOT NULL DEFAULT '',
    url        TEXT NOT NULL,
    published  TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',
    is_starred INTEGER NOT NULL DEFAULT 0,
    is_unread  INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_entries_feed_id  ON entries(feed_id);
CREATE INDEX idx_entries_unread   ON entries(is_unread);
CREATE INDEX idx_entries_starred  ON entries(is_starred);
CREATE INDEX idx_entries_published ON entries(published DESC);
