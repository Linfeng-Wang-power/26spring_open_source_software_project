-- Migration 0004: LLM provider and agent-run tables (stubs for 张睿桐 and 陆骏凯)
-- depends: 0003.create-summary-translation-stubs

-- LLM provider configurations (OpenAI-compatible).
-- API keys are NOT stored here; use keyring (张睿桐 负责 ProviderStore).
CREATE TABLE provider_profiles (
    provider_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL              -- ISO-8601 UTC
);

-- Agent task run history for auditing and retry logic.
-- status: pending | running | success | failed | cancelled
CREATE TABLE agent_runs (
    run_id      TEXT PRIMARY KEY,
    entry_id    TEXT REFERENCES entries(entry_id) ON DELETE SET NULL,
    agent_type  TEXT NOT NULL DEFAULT '',  -- "summary" | "translation"
    status      TEXT NOT NULL DEFAULT 'pending',
    started_at  TEXT NOT NULL,             -- ISO-8601 UTC
    finished_at TEXT                       -- NULL while still running
);

CREATE INDEX idx_agent_runs_entry ON agent_runs(entry_id, agent_type);
