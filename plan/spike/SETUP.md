# Dev Environment Setup

Stand up everything you need to run the orchestrator agent against the smoke-test tool. ~30 minutes start to finish.

---

## Prerequisites

- macOS or Linux
- Docker Desktop installed
- Python 3.11+ available
- An Anthropic API key (`muntadhar@[yourdomain]` account, NOT Neara)
- An OpenAI API key (for embeddings — Anthropic embeddings also work)

## 1. Clone branches and create env file

```bash
cd /path/to/MuntaSpec
cp .env.example .env
# Edit .env and paste in:
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...
#   JWT_SECRET=$(openssl rand -hex 32)
```

## 2. Bring up Postgres with pgvector

```bash
docker compose up -d db
docker compose logs -f db   # wait for "database system is ready to accept connections"
# Ctrl-C out of logs once ready
```

Verify the extension and schema loaded:

```bash
docker compose exec db psql -U muntaspec -d muntaspec -c "\dx"
# Should list 'vector' extension
docker compose exec db psql -U muntaspec -d muntaspec -c "\dt"
# Should list corpus_chunks, agent_runs, agent_tool_calls
```

If the schema isn't there, the init.sql may have been mounted after the database was already created. Reset:
```bash
docker compose down -v   # WARNING: deletes pgdata volume
docker compose up -d db
```

## 3. Backend Python env

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Note: `CoolProp` build occasionally fails on Apple Silicon. If so:
```bash
pip install --no-build-isolation CoolProp
```

## 4. Smoke test the agent

```bash
cd backend
source .venv/bin/activate
python -m decarb.agent --site-brief decarb/tests/sites/dairy_5mw.json
```

**Expected behaviour:**
- The agent reads `dairy_5mw.json`
- It will call `parse_energy_profile` first → gets a stub response
- It will call `compute_baseline_carbon` → stub response
- It will call `screen_technologies` → stub response
- It may call `calculate_hp_cycle` for a candidate HP — this is the real tool, returns real CoolProp output
- The agent will eventually stop because the stubs don't give it enough to write a real report

**Success looks like:**
- The agent runs without crashing
- It calls `calculate_hp_cycle` at least once (the real tool)
- The output for `calculate_hp_cycle` shows `cop_heating` between 2.0 and 4.5 (sane range)
- The run completes in < 2 minutes
- Token cost < £0.50 per run

If the smoke test passes → **week 1 dev env is done. Move to corpus loading.**

## 5. Corpus loading (week 1 main work)

Working from `plan/spike/week1_corpus.md`:

1. Acquire ~80 reference docs into `backend/decarb/corpus/raw/`
2. Build a chunking script (or write one with Claude Code) → outputs to `backend/decarb/corpus/chunks/`
3. Build an embedding script → reads chunks, embeds via OpenAI, inserts into `corpus_chunks` table
4. Test: query "what is the DEFRA 2026 emission factor for natural gas?" → should retrieve the right chunk

A complete corpus pipeline is ~150 lines of Python. Will write it as `decarb/corpus/ingest.py` next session if helpful.

## 6. Common problems

**Anthropic API key not loading:** check `.env` is in repo root, not `backend/`. The `load_dotenv()` call walks up.

**`pgvector extension does not exist`:** the postgres image must be `pgvector/pgvector:pg16`, not the default `postgres:16-alpine`. Re-check `docker-compose.yml`.

**`CoolProp` import fails:** macOS Silicon issue — see step 3 fix.

**Agent loops forever:** the stubs return `{"_stub": True}` which the LLM may keep retrying. The MAX_ITERATIONS=30 cap will catch this. Reduce to 10 if you want a faster failure mode.

**Tool call returns error:** check the input schema in `TOOL_SCHEMAS`. The LLM's input must match.

---

## Quick-test commands

```bash
# Smoke test the real HP cycle calc directly
# Uses a realistic low-pressure steam pre-heat case (waste heat → hot water).
# The original test (evap=0°C, cond=80°C) gave COP 2.26 — physically correct
# but past the single-stage screw compressor envelope (pressure ratio 13.5,
# discharge temp 301°C). Not a real engineering use-case for single-stage.
cd backend && python -c "
from decarb.tools import calculate_hp_cycle
import json
result = calculate_hp_cycle(
    refrigerant='Ammonia',
    process_evaporator_temp_c=20,
    process_condenser_temp_c=60,
)
print(json.dumps(result, indent=2))
"
# Should print COP_heating ≈ 3.5–4.5

# Run a single agent iteration with verbose logging
cd backend && python -m decarb.agent --site-brief decarb/tests/sites/dairy_5mw.json
```

---

## Out of band

- **Don't commit `.env`** — it's gitignored, but double-check before any commit.
- **Don't commit anything in `decarb/corpus/raw/`** that's paywalled (CIBSE, BS standards). Keep those local; gitignore the directory.

---

## Phase 0 complete — baseline (2026-04-28)

Smoke test passed on `dairy_5mw.json` with clean `end_turn` termination.

| Metric | Value |
|---|---|
| Total tokens | 112,498 |
| Estimated cost | ~£0.45 |
| Iterations | 8 |
| Tool calls | 27 (9 live, 17 stubs, 1 render) |
| `calculate_hp_cycle` calls | 8 (multiple refrigerants + cycle types) |
| `simulate_site_dispatch` calls | 3 (conservative / balanced / aggressive) |
| Stop reason | `end_turn` (clean) |
| Wall clock | ~5 min (includes rate-limit waits at 30k tok/min tier) |

Key optimisations applied during Phase 0:
- `parse_energy_profile` and `screen_technologies` pre-run in Python, compact summary injected into initial message (removed from TOOL_SCHEMAS)
- Tool outputs trimmed to essential numbers; full results preserved in `tool_call_log` for provenance
- Tool result strings capped at 800 chars in conversation history
- Stub tools return `{_stub: true}` only, not echoed kwargs
- System prompt instructs zero narration between tool calls

This is the baseline against which week 2 engine work will be compared.
