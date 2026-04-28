# Direction

## What we're building

An **AI engineer for the energy sector** — a system that takes an energy-sector technical problem (industrial site decarbonisation, refinery electrification, process heat integration, heat network design, hydrogen/CCS feasibility, nuclear/O&G adjacency analyses) and produces a consultancy-grade technical study at the depth of a fresh-but-rigorous engineering consultant.

The product is a **deep simulation + optimisation engine** (8,760-hour dynamic site sim, multi-stage refrigerant-cycle thermo via CoolProp with full compressor maps, pinch analysis with real heat-exchanger network synthesis, multi-period MILP investment sequencer with stochastic scenario trees, Monte Carlo uncertainty with Sobol sensitivity, regulatory + safety constraint checks) **wrapped in an LLM agent** that orchestrates the engine, retrieves grounded standards/case-study evidence, and writes the consultancy-voice deliverable.

**North star:** the system fully replaces a junior engineer's work, with a senior engineer reviewing in 1 hour instead of 3 months.

## Who buys it

**Primary (year 1):** Senior engineers and group leaders at UK energy-sector consultancies — Frazer Nash, WSP, Arup, ERM, Wood, Ramboll, Mott MacDonald, Atkins, Ricardo, AECOM, Wood Mackenzie, RINA — currently delivering £50–200k+ technical engagements over 2–6 months using IES VE, Aspen Plus, IPSEpro, EBSILON, spreadsheets, and senior-associate hours.

**Secondary (year 2+):** Energy-sector end-clients direct — Shell, BP, EDF, EDF Renewables, Drax, Centrica, Equinor, INEOS, Phillips 66 (refining), large industrial operators (Tata Chemicals, Ineos, Pilkington, Tate & Lyle, Diageo, Unilever) — at £50–200k/yr enterprise contracts.

## Pricing

- Pilot engagement: £15–40k per scoped study
- Seat licence: £40–150k/seat/yr at a consultancy
- Enterprise: £75–300k/yr direct to an industrial / O&G operator

## Why us, specifically

- Imperial Mech Eng, 1st in cohort thermodynamics
- Heat Pump Lead at Frazer Nash, advised 5 heat pump startups professionally
- Fire Technical Lead at FN — 100+ Ansys simulations, fire and explosion engineering
- Risktec O&G safety consulting — Shell, EDF as prior clients; pressure-environment process safety; HAZOP/ALARP-aware
- Neara — UK DNO context (SSEN, ESB, App+ accounts)
- £1M+ commercial revenue closed across career (FN, Risktec, Neara)
- 6,400-line existing MUNTec backend to repurpose

The intersection of these — first-principles thermo + multi-sector energy depth + safety-engineering literacy + commercial nous — is rare. Few people in the UK can build this engine *correctly* and also sell it.

## What we're not building (in v1)

- Heat pump installer SaaS (parked)
- BUS grant automation (parked)
- Direct-to-SME tools (don't buy software like this)
- Anything grid / DNO / TSO operations facing (Neara non-compete: customer-side off-limits)
- Anything frontier-ML (year 3+, after we have data)

## Vertical slice for the 6-week feasibility spike

**Sector-agnostic but decision-specific:** industrial steam-system electrification + heat integration.

In plain words: a process site (food & drink, chemicals, pharma, paper, refining, ceramics — anyone burning gas to make steam) wants to know: should we electrify, with what mix of heat pumps + electrode boilers + thermal storage + waste-heat recovery, on what schedule, with what risk profile?

This decision class:
- Applies to ~5,000 UK industrial sites
- Maps directly to the existing IETF / Industrial Decarbonisation Strategy demand
- Uses heat pump + thermal + safety + financial depth simultaneously (your full stack)
- Doesn't require sector-specific custom modelling — same physics across food & drink, chemicals, pharma, paper, refining
- Has public reference data (IETF case studies, BREF documents, manufacturer datasheets) to ground the corpus
- Is **clearly outside Neara's market** (industrial demand-side, not utility-side)

The three golden test sites stay food & drink (dairy, brewery, soft drinks) because public benchmarking data is densest there — but the engine is sector-agnostic and the company sells into chemicals, pharma, paper, refining, etc. as well.

**Scope discipline rule for the spike:** one decision class (steam-system electrification + heat integration). Don't broaden the decision class until end of week 6 even if buyer interest is broader. The technology engine you build this way generalises naturally to other industrial energy decisions later (cooling-system electrification, on-site hydrogen, CCS pre-combustion, etc.). Build this one well first.

## Constraints

- Solo founder, employed at Neara, ~15 hrs/wk available
- No outreach until employment lawyer clears energy-sector industrial decarb scope
- All work on personal email + personal devices + personal GitHub
- Clean separation from Neara — work log + own-time discipline
- Engineering depth is non-negotiable — every tool the agent calls must produce output a senior FN engineer would sign off on without rebuild

## Quit trigger

> *"I will quit Neara when MRR ≥ £25k sustained for 2 consecutive months AND I have ≥9 months personal runway saved. Not before."*

Signed and dated, kept in a drawer.
