-- Migration 0005: key-value settings table
-- depends: 0004.create-provider-agent-stubs

-- Stores UI preferences and lightweight app config.
-- Heavy provider metadata goes in provider_profiles (migration 0004).
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Seed defaults so reads never return NULL on a fresh install.
INSERT OR IGNORE INTO settings (key, value) VALUES ('ui.language', 'zh-CN');
INSERT OR IGNORE INTO settings (key, value) VALUES ('ui.theme',    'light');
