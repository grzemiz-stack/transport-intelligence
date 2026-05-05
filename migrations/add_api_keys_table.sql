-- Migration: Add api_keys table for integration API authentication
-- Run: psql -U transport_intel -d transport_intel -f migrations/add_api_keys_table.sql

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_hash VARCHAR(128) NOT NULL,
    client_name VARCHAR(100) NOT NULL,
    permissions JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    last_used TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS ix_api_keys_is_active ON api_keys(is_active);
