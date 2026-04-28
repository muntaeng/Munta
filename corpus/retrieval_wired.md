# Retrieval Wired — Handoff 02 Notes

## What changed

| File | Change |
|------|--------|
| `backend/decarb/tools.py` | Replaced `retrieve_reference_docs` stub with real RAG implementation. Added LRU-cached query embedding, compact hit formatting (key fields first for truncation safety), empty-corpus guard. Updated tool schema: full description, `sector` filter enum, `top_k` min/max. |
| `backend/decarb/corpus/db.py` | Added `search_chunks()` — cosine similarity search with optional `source_type` and `sector` WHERE filters. Existing `test_retrieval()` and `upsert_chunks()` unchanged. |
| `backend/decarb/prompts/orchestrator_v0_1.txt` | Added citation rule: agent MUST call `retrieve_reference_docs` before asserting numbers/standards, cite by `doc_id` and page. |
| `backend/decarb/tests/test_retrieve_reference_docs.py` | 5 tests: real hits, source_type filter, sector filter, truncation safety, LRU cache hit. |
| `backend/decarb/tests/test_agent_smoke.py` | Integration test (skipped by default) asserting agent calls retrieve_reference_docs with n >= 1. |

## Non-trivial decisions

- **LRU cache size 128**: covers a typical agent run (10–30 distinct queries) with room for repeated queries. Cache is per-process; cleared between test runs.
- **Snippet length 180 chars**: leaves room for ~4 hits within the 800-char truncation window. The hit dict key order puts `doc_id`, `section`, `similarity`, `snippet` first so truncation preserves citation-critical fields.
- **One `get_conn()` per tool call**: no connection pooling. Fine at spike scale. TODO if perf becomes an issue.
- **Embedding model**: OpenAI text-embedding-3-large, 3072 dims, per spec. No local fallback.

## Test results

- `test_retrieve_reference_docs.py`: 5/5 pass
- `corpus/tests/test_retrieval.py`: 3/3 quality-bar tests pass
- `test_agent_smoke.py`: skipped by default (needs `RUN_INTEGRATION_TESTS=1`)
