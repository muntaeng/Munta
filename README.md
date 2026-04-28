# Munta

An AI engineer for the energy sector -- a system that takes an energy-sector technical problem (industrial site decarbonisation, refinery electrification, process heat integration, heat network design, hydrogen/CCS feasibility) and produces a consultancy-grade technical study.

## What it does

A **deep simulation + optimisation engine** (8,760-hour dynamic site sim, multi-stage refrigerant-cycle thermo via CoolProp, pinch analysis with real heat-exchanger network synthesis, multi-period MILP investment sequencer, Monte Carlo uncertainty with Sobol sensitivity, regulatory + safety constraint checks) **wrapped in an LLM agent** that orchestrates the engine, retrieves grounded standards/case-study evidence, and writes the consultancy-voice deliverable.

**North star:** the system fully replaces a junior engineer's work, with a senior engineer reviewing in 1 hour instead of 3 months.

## Current focus

**Vertical slice (6-week feasibility spike):** industrial steam-system electrification + heat integration. A process site burning gas to make steam wants to know: should we electrify, with what mix of heat pumps + electrode boilers + thermal storage + waste-heat recovery, on what schedule, with what risk profile?

## Running

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, JWT_SECRET, etc.

docker compose up --build
```

The agent runs via `python -m decarb.agent`.

## Structure

- `backend/decarb/` -- the decarb agent and simulation engine
- `corpus/` -- ingested technical standards, case studies, manufacturer data
- `plan/` -- architecture, direction, and spike planning
- `docs/methodology/` -- methodology documentation
