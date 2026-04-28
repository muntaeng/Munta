# 6-Week Feasibility Spike

## The question we're answering

> Can a current LLM + a deep custom engine + domain scaffolding produce decarbonisation pathway output that an FN senior engineer rates ≥4/5 for technical correctness, on a real worked example, without human editing?

If yes → confidence to build the company.
If no → narrow scope, change architecture, or wait for next-gen models.

## The vertical slice (everything is constrained to this)

- **Sector:** food & drink processing
- **Site:** mid-size dairy or brewery, 5–15 MW thermal demand, mixed steam + hot water
- **Decision:** electrify the steam system — HP / electrode boiler / hybrid + thermal storage + waste heat recovery
- **Output:** 15-page pathway analysis report (techno-economic + carbon + risk + sequencing)

One sector. One site shape. One decision class. Resist all expansion temptation until end of week 6.

## Six-week schedule

| Week | Theme | Hours | Deliverable |
|---|---|---|---|
| 1 | Knowledge scaffolding | 15 | Reference corpus loaded, pgvector + Anthropic SDK working, first system prompt |
| 2 | Engine v0 | 15 | 8,760-hour industrial sim + refrigerant cycle thermo + scenario sweep + carbon trajectory, all unit-tested |
| 3 | Agent integration | 15 | LLM tool-use wired to engine, RAG retrieval working, first end-to-end report on synthetic site |
| 4 | Iterate to credibility | 15 | Top 5 problems fixed, self-critique loop, Monte Carlo uncertainty, calculation provenance |
| 5 | Real-world test | 15 | Run on one anonymised real case (synthesised from public IETF/H&V case study), compare side-by-side with published consultancy report |
| 6 | Independent expert eval | 10 | One former FN colleague rates output on technical correctness / commercial realism / voice / "could this be your draft?" |

## Decision criteria at end of week 6

| Outcome | Action |
|---|---|
| Green — *"could be my draft with 1hr review"* | Validated. Move to full roadmap (POC → pilots → seat licence → exit). |
| Amber — *"impressive but X is wrong"* | 2–4 weeks fixing X. Re-test. Probably converges to green. |
| Red — *"not engineer-quality yet"* | Narrow scope, hybrid more human-in-loop, or wait 6–12 months for next-gen models. |

## Discipline rules

1. No outreach until employment lawyer clears scope (Phase 0, in parallel with weeks 1–2)
2. All work on personal email + GitHub + Workspace (never `@neara.com`)
3. Work log entry every session (date, hours, what)
4. Don't expand the vertical slice. One sector, one decision, one site shape.
5. Discipline ratio: 80% build, 20% reading docs. After week 4: 50% build, 30% talking to ex-FN over coffee with the demo, 20% iterating.

## Files in this folder

- `README.md` (this file) — the plan
- `week1_corpus.md` — list of 50–100 reference docs to load
- `week1_system_prompt.md` — first draft of the orchestrator system prompt
- `week2_engine_modules.md` — engine module specs (added at start of week 2)
- `week5_eval_rubric.md` — the rating sheet for the FN colleague (added at start of week 5)

Each week's docs are written at the start of that week. Don't pre-write weeks 3–6 — they'll change based on what week 1–2 teaches.
