-- Initialise pgvector extension and corpus schema
CREATE EXTENSION IF NOT EXISTS vector;

-- Reference document chunks for RAG
CREATE TABLE IF NOT EXISTS corpus_chunks (
    id              SERIAL PRIMARY KEY,
    doc_id          TEXT        NOT NULL,
    doc_title       TEXT        NOT NULL,
    section         TEXT,
    page_number     INTEGER,
    chunk_index     INTEGER     NOT NULL,
    text            TEXT        NOT NULL,
    token_count     INTEGER,
    embedding       vector(3072),  -- OpenAI text-embedding-3-large
    source_url      TEXT,
    source_type     TEXT,           -- 'standard' | 'regulation' | 'case_study' | 'datasheet' | 'textbook'
    sector          TEXT,           -- nullable; tagged where relevant
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- NOTE: vector index deferred — pgvector HNSW/IVFFlat cap at 2000 dims.
-- For 3072-dim embeddings, add index after reducing dims or switch to
-- text-embedding-3-small (1536). Not needed for smoke test.

CREATE INDEX IF NOT EXISTS idx_corpus_chunks_source_type
    ON corpus_chunks (source_type);

CREATE INDEX IF NOT EXISTS idx_corpus_chunks_doc_id
    ON corpus_chunks (doc_id);

-- Agent run provenance — every report run logs the full tool-call trail
CREATE TABLE IF NOT EXISTS agent_runs (
    id              SERIAL PRIMARY KEY,
    run_uuid        TEXT        UNIQUE NOT NULL,
    site_brief      JSONB       NOT NULL,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          TEXT        DEFAULT 'running',  -- 'running' | 'success' | 'failure'
    final_report    TEXT,
    total_tokens    INTEGER,
    total_cost_gbp  NUMERIC(10, 4)
);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id              SERIAL PRIMARY KEY,
    run_uuid        TEXT        NOT NULL REFERENCES agent_runs(run_uuid) ON DELETE CASCADE,
    sequence        INTEGER     NOT NULL,
    tool_name       TEXT        NOT NULL,
    inputs          JSONB       NOT NULL,
    outputs         JSONB,
    duration_ms     INTEGER,
    error           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_run
    ON agent_tool_calls (run_uuid, sequence);
