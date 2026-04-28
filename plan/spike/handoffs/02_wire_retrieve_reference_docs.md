# Handoff 02 — Wire `retrieve_reference_docs`

**Goal**: replace the stub `retrieve_reference_docs` tool with a real RAG implementation backed by the corpus that's already loaded into pgvector. Add tests. Update the system prompt with a one-paragraph citation rule.

Almost everything you need already exists — the corpus is loaded into pgvector, the embedding client is in `backend/decarb/corpus/embed.py`, the DB helpers are in `backend/decarb/corpus/db.py`, and the agent loop and tool dispatch are in `backend/decarb/agent.py` and `backend/decarb/tools.py`. Don't restructure anything else.

---

## Read first

- `backend/decarb/tools.py` — note the `retrieve_reference_docs` stub at line 174 and its `TOOL_SCHEMAS` entry at line 388. The pattern for "real" tools is at lines 52–122 (`calculate_hp_cycle`, `compute_baseline_carbon`, `simulate_site_dispatch`). They take `**kwargs`, call into a real engine module, and return a *compact* dict — the LLM only needs the headline numbers; the full audit trail is preserved in `ToolCallRecord`.
- `backend/decarb/corpus/db.py` — `get_conn()` returns a live psycopg connection. `test_retrieval(conn, embedding, limit)` does the cosine search and returns a list of dicts with `doc_id, doc_title, section, page_number, text, token_count, source_type, sector, similarity`.
- `backend/decarb/corpus/embed.py` — `embed_single(query, client=...)` returns a 3072-dim vector for one query string. `get_client()` returns the OpenAI client.
- `backend/decarb/agent.py` lines 244–245 — the agent truncates each tool result's JSON to **800 chars** in the conversation. Anything past that is invisible to the LLM (the full version is still logged in `ToolCallRecord` and persisted to `agent_tool_calls`).
- `backend/decarb/corpus/init.sql` — the `corpus_chunks` schema. Note `source_type` values: `standard, regulation, case_study, datasheet, textbook`.
- `backend/decarb/corpus/tests/test_retrieval.py` — the three quality-bar queries already passing against the corpus. They must continue to pass.

---

## What to build

### 1. Real `retrieve_reference_docs` in `backend/decarb/tools.py`

Replace the stub. The function:

- Embeds the query using `embed_single()` (text-embedding-3-large, 3072-dim).
- Runs cosine search with optional WHERE filters on `source_type` and `sector`. Add a new `db.search_chunks(conn, embedding, *, limit, source_type=None, sector=None)` and call it from here. Keep the SQL in `db.py`, not in `tools.py`. Don't change the existing `db.test_retrieval` — the quality-bar tests use it.
- Returns a compact dict shaped to survive the 800-char truncation:

```python
{
  "n": 4,
  "hits": [
    {
      "doc_id": "01-defra-2025-factors-full",
      "doc_title": "DEFRA 2025 Government GHG Conversion Factors ...",
      "section": "Energy > Stationary combustion > Natural gas",
      "page_number": 47,
      "similarity": 0.812,
      "snippet": "Natural gas (kWh net CV) 0.18293 kgCO2e/kWh ...",
      "source_url": "https://www.gov.uk/government/publications/...",
      "source_type": "regulation",
      "sector": null
    }
  ]
}
```

Order each hit's keys so the citation-critical ones (`doc_id`, `section`, `similarity`, `snippet`) come first — that way truncation at 800 chars still leaves a usable citation trail. Trim `snippet` to the first **180 characters** of the chunk text, single-spaced (collapse internal whitespace, strip newlines). Round `similarity` to **3 d.p.**

Add a small in-process LRU cache for query embeddings (use `functools.lru_cache` on a thin wrapper that takes the query string and returns a tuple of floats; max **128 entries**). The agent often re-asks similar queries during a single run — this cuts both latency and cost.

If the DB has zero chunks (fresh dev environment), return `{"n": 0, "hits": [], "error": "corpus_chunks is empty — run ingestion"}` so the failure mode is loud but the tool doesn't crash the agent loop.

### 2. Update the tool schema in `TOOL_SCHEMAS`

Find the `retrieve_reference_docs` entry around line 388. Then:

- Drop the `"STUB Week 1 RAG."` prefix. Replace the description with:

  > Vector search over the reference corpus (DEFRA factors, UK regulation, CIBSE/EHPA standards, IETF case studies, manufacturer datasheets, textbooks). Use to ground numerical claims in cited sources before asserting them. Returns top-K matching chunks with doc_id, section, page, similarity score, snippet, and source URL. Prefer narrow, technically-specific queries (e.g. "DEFRA 2025 natural gas combustion factor", not "emission factors"). Multiple narrow queries beat one broad one.

- Add an optional `sector` filter alongside `source_type_filter`. The values currently in the corpus are `food_and_drink` (and null for the rest). Use `enum: ["food_and_drink"]` so the LLM can't invent values.
- Keep `top_k` default 5. Add `"minimum": 1, "maximum": 10` to its entry.

Don't change any other tool's schema or handler.

### 3. Update the system prompt

In `backend/decarb/prompts/orchestrator_v0_1.txt`, find the section that lists tools and any existing guidance about `retrieve_reference_docs`. Strip any "STUB" language. Add this short guidance block:

> When citing a number, standard, or precedent in the report, you MUST first call `retrieve_reference_docs` to ground the claim. Quote the retrieved snippet inline and reference it by `doc_id` (e.g. `[01-defra-2025-factors-full, p.47]`). If retrieval returns nothing relevant, say so explicitly rather than asserting from prior knowledge.

Don't expand the prompt beyond that. Full citation discipline gets enforced in the Week 4 self-critique pass — for now the only goal is that the tool gets called and the doc_ids show up in outputs.

### 4. Tests

Create `backend/decarb/tests/test_retrieve_reference_docs.py` with:

- `test_dispatch_returns_real_hits` — call `dispatch("retrieve_reference_docs", {"query": "DEFRA 2025 natural gas emission factor"})`. Assert the returned dict has `n >= 1`, no `_stub` key, and the first hit's `doc_id` starts with `01-defra-2025`.
- `test_source_type_filter` — query `"industrial heat pump COP"`, filter `source_type_filter="standard"`, assert all returned hits have `source_type == "standard"`.
- `test_sector_filter` — query `"case study"`, filter `sector="food_and_drink"`, assert all returned hits have `sector == "food_and_drink"`.
- `test_truncation_safety` — take a real tool result, JSON-serialise it, truncate to 800 chars, and assert at least one full doc_id string still appears in the truncated output (the LLM must be able to cite even from a truncated payload).
- `test_lru_cache_hits` — call the tool twice with the same query, assert the second call's underlying `embed_single` invocation count didn't increase. Mock or count via a wrapper.

Don't add a smoke test that runs the full agent loop here — that's a separate file.

Also create `backend/decarb/tests/test_agent_smoke.py` (if not present), with **one** end-to-end integration test marked:

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="integration only")
```

It loads `backend/decarb/tests/sites/dairy_5mw.json`, runs the agent, and asserts that at least one tool call in the run record has `tool_name == "retrieve_reference_docs"` and `outputs["n"] >= 1`. Skipped by default — you don't need to run it; just verify the test exists and is structured correctly so default CI doesn't burn API tokens.

The three existing `corpus/tests/test_retrieval.py` quality-bar tests must continue to pass — don't break them.

---

## Constraints

- Don't modify `corpus/init.sql`, `corpus/db.py`'s **existing** functions (you may add new ones, but don't change `test_retrieval` or `upsert_chunks`), `corpus/embed.py`, the manifest, or any other tool's handler / schema.
- Don't switch embedding providers. Stay on text-embedding-3-large at 3072 dims.
- Don't add the HNSW/IVFFlat vector index. The 3072-dim ceiling is documented in `init.sql`; sequential scan at this scale is fine.
- Don't introduce new dependencies. `psycopg`, `openai`, `python-dotenv` are already in the project.
- Don't print full chunk text to stdout in the tool — the verbose agent output already truncates inputs to 400 chars; the tool should keep its own prints similarly tight (or silent).
- Don't expose connection pooling work as part of this task. One `get_conn()` per tool call is fine for the spike. If you observe slow performance, leave a TODO comment, don't pre-optimise.
- Don't rewrite the test_retrieval.py quality-bar suite. It's the external check on your changes.

---

## Done criterion

- The `retrieve_reference_docs` stub is gone; the tool returns real hits.
- All five new tests in `test_retrieve_reference_docs.py` pass.
- The three quality-bar tests in `corpus/tests/test_retrieval.py` still pass.
- `backend/decarb/tests/test_agent_smoke.py` exists with one `@pytest.mark.integration` test asserting at least one `retrieve_reference_docs` call with `n >= 1`. Skipped by default.
- A short `corpus/retrieval_wired.md` notes what was changed: which files, the new schema fields, and any non-trivial decisions (e.g. cache size, snippet length).
