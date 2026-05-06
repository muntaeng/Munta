# Architecture

## High-level

```
┌──────────────────────────────────────────────────────────────┐
│  USER                                                        │
│  Senior engineer at FN/WSP/Arup uploads site data            │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR AGENT (Claude Sonnet 4.6)                      │
│  - Parses input                                              │
│  - Plans analysis steps                                      │
│  - Decides which tools to call and when                      │
│  - Writes consultancy-voice narrative                        │
│  - Self-critiques output before finalising                   │
│  - NEVER does arithmetic                                     │
└──────────────────────────────────────────────────────────────┘
        │                                        ▲
        ▼ (tool calls)                           │ (results)
┌──────────────────────────────────────────────────────────────┐
│  DEEP ENGINE (Python — the moat)                             │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Site simulator (8,760-hour dynamic)                   │  │
│  │  - Industrial process heat profiles                    │  │
│  │  - Weather-coupled loads                               │  │
│  │  - Production schedule overlay                         │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Refrigerant cycle thermodynamics (CoolProp)           │  │
│  │  - Real cycles, part-load, multi-stage                 │  │
│  │  - Refrigerant choice (NH3, CO2, HFO)                  │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Multi-tech dispatch                                   │  │
│  │  - HP + electrode boiler hybrid                        │  │
│  │  - Waste heat cascading                                │  │
│  │  - Thermal storage charge/discharge                    │  │
│  │  - PV + battery + HP under TOU tariffs                 │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Pinch analysis & heat integration                     │  │
│  │  - Composite curves                                    │  │
│  │  - Min utility targets                                 │  │
│  │  - Heat exchanger network synthesis                    │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Multi-period investment optimisation (MILP)           │  │
│  │  - 15–20 yr horizon                                    │  │
│  │  - When to install what at what capacity               │  │
│  │  - Solver: OR-Tools / Pyomo                            │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Monte Carlo uncertainty                               │  │
│  │  - 5–10 uncertain inputs                               │  │
│  │  - Sobol sensitivity indices                           │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Techno-economic + carbon (reuse from MUNTec)          │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
        │                                        ▲
        ▼                                        │
┌──────────────────────────────────────────────────────────────┐
│  KNOWLEDGE BASE (read-only, RAG)                             │
│  - DEFRA 2026 factors                                        │
│  - UK ETS / CBAM / SECR rules                                │
│  - CIBSE TM54, AM17, BS EN standards                         │
│  - IETF / Energy Systems Catapult case studies               │
│  - Manufacturer datasheets (HP, electrode, biomass)          │
│  - UK grid intensity forecast                                │
│  Stored in pgvector, retrieved via embedding similarity      │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  OUTPUT                                                      │
│  - 15–25 page markdown report → PDF (weasyprint)             │
│  - Calculation provenance table (every number traced)        │
│  - JSON of all simulation runs (for audit)                   │
└──────────────────────────────────────────────────────────────┘
```

## Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | FastAPI (existing) | Already there, fine |
| LLM | Anthropic Claude Sonnet 4.6 | Best tool-use + reasoning combo today |
| LLM client | Anthropic Python SDK | First-party, well-supported |
| Database | PostgreSQL + pgvector | Standard, hosted on Neon or Supabase |
| Embeddings | OpenAI text-embedding-3-large or Anthropic | Either works; OpenAI is cheap and great |
| Thermo lib | CoolProp | Industry-standard refrigerant property tables |
| Optimisation | OR-Tools (Python) | Free, fast, MILP-capable |
| Simulation | Pure Python + NumPy + pandas | Existing pattern from MUNTec |
| Reporting | Markdown → weasyprint → PDF | Simple, controllable |
| Eval harness | pytest + custom golden tests + LLM-as-judge | Standard |
| Hosting (later) | Fly.io or Railway | Trivial, scales for years |

## Non-negotiable design principles

1. **LLM never does arithmetic.** Every number in the output traces to a deterministic tool call.
2. **Calculation provenance in every output.** Auditable by an FN engineer in under 5 minutes.
3. **Engine is independently runnable.** The LLM is a UX layer; the engine must work without it (could be shipped as a Python library on its own).
4. **Self-critique loop.** The agent reviews its own draft for inconsistencies before producing the final report.
5. **Golden test cases gate every release.** No engine module ships without unit tests against a hand-crafted ground truth.

## Reuse from existing MUNTec backend

The decarb engine is a clean-slate implementation. Earlier MUNTec residential heat-pump code was evaluated for reuse and discarded — the industrial scale and thermodynamic depth required first-principles redesign.

## Out of scope for v1

- User auth, billing, multi-tenancy
- Frontend polish
- Mobile
- Production hosting
- Industries other than food & drink processing (vertical slice)
- Technology decisions other than steam-system electrification (vertical slice)
