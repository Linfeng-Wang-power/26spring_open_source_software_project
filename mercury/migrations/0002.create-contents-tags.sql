-- Migration 0002: reader content and tags
-- depends: 0001.create-feeds-entries

-- Stores all representations produced by reader/pipeline.py ReaderPipelineService.
-- Fields map 1-to-1 to reader/models.py ReaderDocument.
CREATE TABLE contents (
    entry_id           TEXT PRIMARY KEY REFERENCES entries(entry_id) ON DELETE CASCADE,
    title              TEXT NOT NULL DEFAULT '',  -- readability-extracted title
    source_url         TEXT NOT NULL DEFAULT '',
    final_url          TEXT NOT NULL DEFAULT '',
    source_html        TEXT NOT NULL DEFAULT '',
    cleaned_html       TEXT NOT NULL DEFAULT '',
    canonical_markdown TEXT NOT NULL DEFAULT '',
    reader_html        TEXT NOT NULL DEFAULT '',
    fetched_at         TEXT NOT NULL              -- ISO-8601 UTC
);

-- Entry tags (e.g. "RSS", "Atom", custom labels).
-- Many-to-many: one entry can have multiple tags.
CREATE TABLE tags (
    entry_id TEXT NOT NULL REFERENCES entries(entry_id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
);

CREATE INDEX idx_tags_entry_id ON tags(entry_id);
