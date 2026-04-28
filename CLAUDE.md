# CLAUDE.md

## Project

Munta -- AI engineer for energy-sector decarbonisation. LLM agent wrapping a thermodynamic simulation + optimisation engine.

## Stack

- Python backend (FastAPI)
- PostgreSQL + pgvector for corpus retrieval
- Docker Compose for local dev
- Anthropic Claude API for the agent layer

## Key paths

- `backend/decarb/` -- main package (agent, simulation, corpus ingestion)
- `corpus/` -- technical reference corpus (standards, case studies, datasheets)
- `plan/` -- architecture and planning docs
- `docs/methodology/` -- methodology writeup

## Running the agent

```bash
python -m decarb.agent
```

## Conventions

- Engineering depth is non-negotiable -- every tool the agent calls must produce output a senior engineer would sign off on
- Keep all work on personal email/devices/GitHub (separation from employer)
