# Claude Code Handoff

You're switching from Cowork to Claude Code for the engine implementation phase. This file is your orientation.

---

## Quick start

In your local terminal, in the repo root:

```bash
cd /path/to/MuntaSpec
claude
```

Then paste the **First prompt** below as your first message.

---

## What's already built

Don't let Claude Code re-do this — it's there:

```
plan/                                       (read these first)
├── direction.md                            committed direction
├── architecture.md                         technical architecture
└── spike/
    ├── README.md                           6-week plan
    ├── SETUP.md                            dev env setup
    ├── week1_corpus.md                     ~80 reference docs to load
    ├── week1_system_prompt.md              orchestrator prompt design notes
    └── week2_engine_modules.md             engine specs §1–§11

backend/
├── requirements.txt                        anthropic, CoolProp, ortools, pgvector, etc.
└── decarb/
    ├── agent.py                            Anthropic tool-use loop (works)
    ├── tools.py                            Anthropic-facing wrappers
    ├── prompts/orchestrator_v0_1.txt       system prompt
    ├── corpus/init.sql                     pgvector schema
    ├── tests/sites/
    │   ├── dairy_5mw.json                  golden test #1 (with _golden_truth)
    │   ├── brewery_8mw.json                golden test #2
    │   └── soft_drinks_12mw.json           golden test #3
    └── engine/
        ├── emission_factors.py             ✅ DEFRA 2026 + grid intensity + Scope 1/2/3
        ├── load_profiles.py                ✅ 11 shape templates + metrics
        ├── parse.py                        ✅ §1 parse_energy_profile
        ├── carbon.py                       ✅ §2 compute_baseline_carbon
        ├── hp_cycle.py                     ✅ §4 calculate_hp_cycle (single-stage)
        └── tests/
            ├── conftest.py                 fixtures
            ├── test_emission_factors.py    ✅
            ├── test_load_profiles.py       ✅
            ├── test_parse.py               ✅
            ├── test_carbon.py              ✅
            └── test_hp_cycle.py            ✅
```

**Status check:**

```bash
cd backend && source .venv/bin/activate && pytest decarb/engine/tests -v
```

Should be green before doing anything else. If not, that's the first thing to fix.

---

## What's left to build (in order)

| # | Module | File | Spec | Est. lines |
|---|---|---|---|---|
| 1 | `simulate_site_dispatch` | `decarb/engine/dispatch.py` | week2 §3 | ~600 |
| 2 | `screen_technologies` | `decarb/engine/screen.py` | week2 §5 | ~300 |
| 3 | `optimise_investment_pathway` | `decarb/engine/pathway.py` | week2 §6 | ~500 |
| 4 | `monte_carlo_uncertainty` | `decarb/engine/uncertainty.py` | week2 §7 | ~250 |
| 5 | `compute_pinch_analysis` | `decarb/engine/pinch.py` | week2 §8 | ~400 (week 3) |
| 6 | `compute_safety_constraints` | `decarb/engine/safety.py` | week2 §9 | ~250 (week 3) |
| 7 | `assess_grid_connection` | `decarb/engine/grid.py` | week2 §10 | ~200 (week 3) |
| 8 | `compute_reliability_availability` | `decarb/engine/reliability.py` | week2 §11 | ~250 (week 3) |
| 9 | RAG corpus ingest + retrieve | `decarb/corpus/ingest.py`, `retrieve.py` | week1_corpus.md | ~200 |

Each gets a corresponding `decarb/engine/tests/test_X.py` against the three golden sites.

---

## First prompt (paste this into Claude Code as message #1)

```
Read CLAUDE.md, then plan/direction.md, plan/architecture.md, plan/spike/README.md, and plan/spike/week2_engine_modules.md.

Confirm pytest is green:
  cd backend && source .venv/bin/activate && pytest decarb/engine/tests -v

Then implement simulate_site_dispatch as backend/decarb/engine/dispatch.py per the §3 spec in plan/spike/week2_engine_modules.md.

Hard rules:
1. The LLM never does arithmetic — every numeric output traces to a deterministic function in this module or a sub-call to another engine module
2. Energy balance must close to <0.5% (assert in code, not just in tests)
3. Use calculate_hp_cycle from decarb.engine.hp_cycle for all HP COP — never approximate Carnot
4. Half-hourly resolution where electricity prices or grid intensity matter; hourly is acceptable for v0 if half-hourly adds material complexity
5. Every output dict includes a `provenance` field listing the calculations and `standards_cited` listing the BS EN / CIBSE / NESO / DEFRA references

Reuse from existing MUNTec backend (don't reinvent):
- backend/simulation.py has the bones of an 8,760-hour dispatch loop — adapt for industrial process heat, multi-pressure steam headers, and refrigerant cycle integration
- backend/calculator.py has thermal models that map onto industrial loads
- backend/weather.py has weather + grid intensity wiring

Then write backend/decarb/engine/tests/test_dispatch.py:
- For dairy_5mw.json with stack [2 MW NH3 HP at 75°C sink + 4 MW electrode boiler + 8 MWh thermal storage + retained gas backup]:
  - Annual gas displacement 60–75%
  - HP runtime > 6,000 hr/yr
  - Electrode boiler dispatched predominantly during off-peak windows (modelled TOU tariff)
  - Energy balance closes to <0.3%
- For brewery_8mw.json and soft_drinks_12mw.json: structural assertions only (output shape, energy balance closure, no NaNs)

Then update backend/decarb/tools.py:
- Replace the simulate_site_dispatch stub with the real import
- Update the tool schema to reflect the real signature

Finally:
- Run pytest decarb/engine/tests -v — all tests must pass
- git add + git commit with message describing what + why
- Stop. Report back.

Constraint: do not implement screen_technologies, pathway, MC, pinch, or any other module in this session. Stay focused on dispatch.
```

---

## Subsequent prompts

Once dispatch is green, the same pattern works for each:

```
Implement screen_technologies as backend/decarb/engine/screen.py per §5 of plan/spike/week2_engine_modules.md. Tests in test_screen.py against the three golden sites — must produce shortlists matching _golden_truth.expected_shortlist_must_include and exclude what _golden_truth.expected_shortlist_must_exclude_with_reason says, with the cited reasons. Wire into tools.py. pytest green. Commit. Stop.
```

```
Implement optimise_investment_pathway as backend/decarb/engine/pathway.py per §6. Week-2 implementation: brute-force scenario enumeration (~50 candidate pathways simulated via simulate_site_dispatch, ranked by NPV). Skip MILP this week — that's a week-3 upgrade. Reuse phased_retrofit.py and calculations.py from existing backend. Tests against dairy_5mw balanced pathway target metrics. pytest green. Commit. Stop.
```

```
Implement monte_carlo_uncertainty as backend/decarb/engine/uncertainty.py per §7. SciPy + SALib. Latin hypercube, 1,000 trials default. Correlated gas/electricity prices. Sobol sensitivity. CVaR_95 + VaR_95. Tests against dairy: P_npv_positive > 0.7, top-2 Sobol inputs are electricity_price + IETF_grant. pytest green. Commit. Stop.
```

```
Implement the RAG corpus pipeline:
- backend/decarb/corpus/ingest.py: read PDFs from corpus/raw/ via pymupdf4llm, chunk to 500–1000 tokens with 100-token overlap, embed via OpenAI text-embedding-3-large (DECARB_EMBEDDING_DIM env var = 3072), insert into the corpus_chunks table
- backend/decarb/corpus/retrieve.py: vector-search top_k chunks given a query, with optional source_type filter
- Wire retrieve_reference_docs in tools.py to call retrieve
- Sanity test: query "DEFRA 2026 emission factor for natural gas" should return a chunk that quotes the right value

Don't run the full corpus ingestion yet — that needs ~80 paywalled PDFs. Validate with 3–5 freely-available test docs (NESO FES summary, IETF Phase 2 case study, a manufacturer datasheet PDF). Commit. Stop.
```

After each module: `pytest decarb/engine/tests -v` to confirm nothing else broke. Refactor existing modules only if the new module's needs forced it; resist creep.

---

## Working pattern Claude Code should follow

For every module:

1. Read the relevant `§N` spec in `week2_engine_modules.md` carefully
2. Look at how the existing engine modules (`hp_cycle.py`, `parse.py`, `carbon.py`) handle: input validation, dataclasses, provenance dict, standards citation, warnings list
3. Match that style exactly — consistency is part of the consultancy-grade feel
4. Write the module
5. Write the test file
6. Run `pytest decarb/engine/tests -v` until green
7. Wire into `tools.py` (replace the stub, update the schema)
8. Run `python -m decarb.agent --site-brief decarb/tests/sites/dairy_5mw.json` as a smoke test — agent should be able to call the new tool without crashing
9. Commit with `git add -A && git commit -m "..."` — message should be one sentence what + one sentence why
10. Stop and report

Discipline rules CC should respect:

- **No multi-module sessions.** One module at a time. Resist scope creep.
- **No silent approximation.** If a sub-calculation can't be done exactly, return a warning + documented assumption.
- **Standards cited inline.** Every output dict has a `standards_cited` list.
- **Provenance everywhere.** Every numeric output traces to its computation or sub-call.
- **Engineering depth.** If a senior FN engineer would scoff at the depth, deepen before claiming done.
- **No commits during failing tests.** Green pytest is a hard gate.

---

## When to come back to Cowork

After engine modules are done:

- **Methodology PDF** for consultancy buyers — 10-page document, dry rigorous voice, used as a sales asset and load-bearing in procurement conversations. Cowork does this well; CC less so.
- **Sales / pitch one-pager** — a single-page handout for FN/WSP/Arup conversations
- **Strategic decisions** — "should we extend the slice to refining?", "is the deep engine still the right architecture?"
- **Cross-cutting refactors** — fresh perspective when CC has been head-down in a module for too long
- **Decks / case studies** — anything where the deliverable is a polished document
- **Code review** — Cowork can read CC's commits and give a different angle on what was built

The split is: CC for code, Cowork for docs and strategy. They're complementary, not competing.

---

## One thing to watch

If CC starts producing test files where it sets the assertions to match its own output (instead of to the `_golden_truth` blocks in the test fixtures), stop and re-prompt. The whole point of golden tests is they're calibrated against your hand-checked engineering judgement, not the agent's first-pass output. Tests that always pass are worse than no tests.
