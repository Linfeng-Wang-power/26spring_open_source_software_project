-- Migration 0003: AI result tables (stubs for 陆骏凯 and 张睿桐)
-- depends: 0002.create-contents-tags

-- One summary result per entry per model slot.
-- To be populated by SummaryAgent (陆骏凯).
CREATE TABLE summary_results (
    entry_id     TEXT PRIMARY KEY REFERENCES entries(entry_id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL DEFAULT '',
    model_id     TEXT NOT NULL DEFAULT '',   -- which model produced this
    created_at   TEXT NOT NULL               -- ISO-8601 UTC
);

-- One row per translated paragraph/segment.
-- To be populated by TranslationAgent (张睿桐).
CREATE TABLE translation_segments (
    segment_id  TEXT PRIMARY KEY,
    entry_id    TEXT NOT NULL REFERENCES entries(entry_id) ON DELETE CASCADE,
    source_hash TEXT NOT NULL DEFAULT '',    -- hash of source_text for cache invalidation
    source_text TEXT NOT NULL DEFAULT '',
    trans_text  TEXT NOT NULL DEFAULT '',
    target_lang TEXT NOT NULL DEFAULT 'zh-CN',
    position    INTEGER NOT NULL DEFAULT 0,  -- paragraph order
    created_at  TEXT NOT NULL                -- ISO-8601 UTC
);

CREATE INDEX idx_translation_segments_entry ON translation_segments(entry_id, target_lang);
