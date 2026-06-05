-- Migration 0006: feed-scoped stable entry identity
-- depends: 0005.create-settings

ALTER TABLE entries ADD COLUMN stable_id TEXT NOT NULL DEFAULT '';

CREATE INDEX idx_entries_feed_stable_id ON entries(feed_id, stable_id);
CREATE INDEX idx_entries_feed_url ON entries(feed_id, url);
