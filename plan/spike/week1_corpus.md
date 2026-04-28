# Week 1 — Reference Corpus

The agent retrieves from this corpus when it needs to ground a claim, cite a standard, look up a factor, or reason about a regulation. **Quality matters more than quantity** — 60 well-curated docs beats 600 loosely-related ones for retrieval accuracy.

Target: ~80 documents loaded by end of Friday next week.

---

## Acquisition checklist

For each item: download as PDF or HTML → store in `corpus/raw/` → process to chunks (Markdown, 500–1000 tokens each) → embed → store in pgvector with metadata.

### 1. Emission factors and grid intensity (5 docs)

- [ ] **DEFRA 2026 GHG Conversion Factors — full set** (gov.uk, free Excel + PDF). The single most important file in the corpus. Every Scope 1 and Scope 2 number references this.
- [ ] **DEFRA 2026 Methodology Paper** (the explanatory companion to the factors)
- [ ] **National Grid ESO Future Energy Scenarios 2025** (free PDF, contains grid intensity forecasts to 2050)
- [ ] **DESNZ UK Government CCS / Hydrogen / Industrial Decarbonisation Strategy 2021** + any 2024–2026 updates
- [ ] **Energy Systems Catapult — UK power sector pathway model outputs** (publicly released)

### 2. UK regulatory framework (8 docs)

- [ ] **UK ETS rules and price bulletins** (gov.uk — the latest auction prices and forward curves)
- [ ] **UK CBAM technical guidance** (HMT/HMRC publications, applicable to UK industrial exporters)
- [ ] **SECR (Streamlined Energy and Carbon Reporting) guidance** (gov.uk)
- [ ] **Climate Change Agreements (CCAs) — sector targets** (gov.uk)
- [ ] **MEES (Minimum Energy Efficiency Standards) — commercial property** (gov.uk, relevant for owned manufacturing facilities)
- [ ] **EU F-gas Regulation 517/2014 + UK retained version + 2024 phase-down schedule** (refrigerant choice constraints)
- [ ] **Industrial Energy Transformation Fund (IETF) — Phase 3 guidance** (gov.uk)
- [ ] **Hydrogen Production Business Model — eligibility and contract structure** (gov.uk)

### 3. Engineering standards (12 docs)

- [ ] **CIBSE TM54 — Evaluating Operational Energy Performance of Buildings** (paid — buy a copy, ~£100, single-user PDF licence)
- [ ] **CIBSE Guide A — Environmental Design** (relevant chapters: thermal mass, internal temperatures)
- [ ] **CIBSE Guide F — Energy Efficiency in Buildings**
- [ ] **CIBSE AM17 — Heat Pumps** (commercial and industrial)
- [ ] **CIBSE AM15 — Biomass Heating**
- [ ] **CIBSE AM16 — Combined Heat and Power for Buildings**
- [ ] **BS EN 14825 — Heat Pump Seasonal Performance Calculation**
- [ ] **BS EN 14511 — Heat Pump Performance Test Conditions**
- [ ] **BS EN 16247-1 to 5 — Energy Audits (general + industrial parts)**
- [ ] **BS EN ISO 50001 — Energy Management Systems**
- [ ] **GHG Protocol Corporate Standard** (Scope 1/2/3 definitions)
- [ ] **PAS 2060 — Specification for Carbon Neutrality**

*Standards docs are paywalled but a single-user PDF licence is £80–£200 each — budget ~£800 for the BS/CIBSE corpus. Worth it.*

### 4. Heat pump and electrification technology data (15 docs)

Manufacturer datasheets — collect public PDFs and capture into corpus:

**Industrial heat pumps (high-temp / large capacity):**
- [ ] MAN ETES — high-temp heat pump datasheets
- [ ] Mayekawa NewTon, Heatpipes — ammonia HP product data
- [ ] Friotherm Unitop — 90°C+ HPs
- [ ] Johnson Controls Sabroe — industrial NH3 HPs
- [ ] GEA RedAstrum / Grasso — ammonia HPs
- [ ] Danfoss Termax — refrigerant cycle components
- [ ] Hybrid Energy AS — ammonia-water HPs (high-temp, Norway)
- [ ] Olvondo Industries — Stirling-cycle high-temp HPs

**Electrode and resistance boilers:**
- [ ] Parat MEW / IEH — electrode boilers up to 60 MW
- [ ] Vapor Power — electric boilers
- [ ] CleanBoiler / Acme — electric process steam

**Hydrogen-ready boilers:**
- [ ] Bosch Industrial — H2-ready boiler ranges
- [ ] Cleaver-Brooks — hydrogen burner data

**Thermal storage:**
- [ ] Kyoto Heatcube — molten salt thermal battery
- [ ] EnergyNest — thermal battery for industrial heat
- [ ] Rondo Energy — thermal storage

### 5. Worked case studies — public (15 docs)

These are gold for RAG. Real examples teach the agent the shape of consultancy-grade reasoning.

- [ ] **All published IETF Phase 1, 2, 3 case studies** (gov.uk — there are 30+ public ones)
- [ ] **Energy Systems Catapult — industrial decarbonisation case studies**
- [ ] **Carbon Trust — sector decarbonisation reports** (food & drink, dairy, brewing)
- [ ] **DESNZ — Industrial Cluster decarbonisation studies** (HyNet, East Coast Cluster, etc.)
- [ ] **UKERC — industrial heat decarbonisation reports**
- [ ] **EEF / Make UK — manufacturer energy reports**
- [ ] **British Beer & Pub Association — brewery sustainability reports**
- [ ] **Dairy UK + AHDB — dairy sector decarbonisation reports**

### 6. Sector-specific process knowledge (10 docs)

For our food & drink vertical slice:

- [ ] **AHDB / Dairy UK — typical process heat demand profiles for milk processing**
- [ ] **Brewers Association of Europe — typical brewery energy use**
- [ ] **Soft Drinks Industry — process water and heating data**
- [ ] **ETSU / DESNZ — Industrial Energy Use surveys for food & drink**
- [ ] **WRAP — food processing efficiency benchmarks**
- [ ] **BREF (Best Available Techniques Reference Documents) — Food, Drink and Milk Industries** (EU IPPC document — free, comprehensive)
- [ ] **Carbon Trust — food and drink technology guides** (3–4 separate docs)
- [ ] **Mondelez / Nestlé / Unilever — published sustainability reports** (typical operational profiles in their facilities, useful as anchors)

### 7. Pinch analysis and process integration (8 docs)

Textbook material — these teach the agent how to reason about heat integration:

- [ ] **Linnhoff March — Introduction to Pinch Analysis** (free white paper)
- [ ] **Kemp — Pinch Analysis and Process Integration (2nd ed)** — the canonical textbook (chunks of relevant chapters)
- [ ] **IChemE — Process Integration Best Practice Guides**
- [ ] **CHEMCAD / Aspen documentation on heat integration** (public)
- [ ] **DOE Industrial Technologies Program — Heat Integration training material**
- [ ] **PILOT — UK pinch analysis software case studies**
- [ ] **Smith — Chemical Process Design (relevant chapters)** — heat exchanger network synthesis
- [ ] **Carbon Trust — Process Integration guide for industry**

### 8. Techno-economic methodology (5 docs)

- [ ] **HM Treasury Green Book — appraisal methodology** (gov.uk, free)
- [ ] **DESNZ Energy and Emissions Projections — fuel price assumptions** (the official UK assumptions used in policy modelling)
- [ ] **IEA — World Energy Outlook (most recent free public summaries)**
- [ ] **Lazard — Levelized Cost of Energy / Storage** (annual report, free)
- [ ] **NREL Annual Technology Baseline — equipment cost trajectories**

### 9. Reference reports and methodology examples (5 docs)

What good consultancy output looks like:

- [ ] **Atkins / Mott MacDonald / WSP — published industrial decarbonisation feasibility studies** (find via web search of company sites — many publish redacted examples)
- [ ] **AEA Technology — Industrial Sector Decarbonisation Pathways report**
- [ ] **Element Energy — sector decarbonisation pathway reports**
- [ ] **Frazer Nash — any publicly available decarbonisation outputs** (your old firm)
- [ ] **Ricardo — Industrial Decarbonisation Strategy supporting analysis** (gov.uk, public)

---

## Acquisition strategy

This is ~80 docs. Realistic time:

- **Saturday afternoon (3 hrs):** acquire all the gov.uk free materials (sections 1, 2, 5, 6 — about 50 docs)
- **Sunday morning (2 hrs):** scrape manufacturer datasheets (section 4)
- **Monday/Tuesday lunchtime (2 hrs):** purchase + download paid CIBSE/BS standards (section 3)
- **Tuesday/Wednesday evening (2 hrs):** Pinch analysis + techno-econ + reference reports (sections 7–9)

Total: ~9 hours over the first week. Aim for ~70 docs by Wednesday, ~80 by Friday.

## Processing into RAG

Once acquired:

1. Chunk by document section (PDF → markdown via `pymupdf4llm`; HTML → markdown directly)
2. Target chunk size: 500–1000 tokens with 100-token overlap
3. Per chunk store: text, source filename, document title, section heading, page number
4. Embed: OpenAI `text-embedding-3-large` (3072-dim, ~£0.10 for the whole corpus) or Anthropic equivalent
5. Index in pgvector with HNSW
6. Test: ask the agent "what's the DEFRA 2026 emission factor for natural gas combustion?" — it should retrieve the right chunk and quote it correctly.

If retrieval is wrong on basic facts, the corpus is the problem — re-chunk before tuning prompts.

## Quality bar before moving to Week 2

- [ ] All 80 docs in `corpus/raw/`
- [ ] All 80 chunked and embedded in pgvector
- [ ] Test query returns correct DEFRA gas factor
- [ ] Test query returns correct CIBSE TM54 reference
- [ ] Test query returns a relevant IETF dairy case study
- [ ] Total embedding spend < £5

If yes → start Week 2 (engine v0).
