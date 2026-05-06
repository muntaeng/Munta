# Industrial Decarbonisation Pathway Analysis

## Calculation Methodology

**Document:** IDPA-MET-001
**Version:** 0.4 (draft for senior-engineer review)
**Date:** May 2026
**Classification:** Restricted — for review by senior engineers and technical assurance reviewers

---

### Document control

| Item | Detail |
|---|---|
| Document title | Industrial Decarbonisation Pathway Analysis — Calculation Methodology |
| Document reference | IDPA-MET-001 |
| Version | 0.4 (draft) |
| Status | For review |
| Owner | Methodology lead |
| Reviewer | Senior chartered engineer (mechanical, thermal, or process) |
| Distribution | Engineering directors, technical assurance, professional indemnity reviewers |
| Next review | On completion of week-7 independent expert evaluation |

### Revision history

| Version | Date | Author | Summary of change |
|---|---|---|---|
| 0.1 | April 2026 | Methodology lead | Initial draft for internal review |
| 0.2 | May 2026 | Methodology lead | Module status badges (implemented v0 vs roadmap v0.2); regulatory framing tightened to three-pillar (ETS / CBAM / SECR) with adjacent levers (CCAs, CCL, MEES) declared separately; provenance disclosure of MEng dissertation lineage added |
| 0.3 | May 2026 | Methodology lead | Section badges aligned with shipped engine state: §3.6 pathway and §3.7 MC moved ROADMAP→IMPLEMENTED v0; §1 status preamble rewritten; §3.7 prose rewritten to match shipped LHS + Iman-Conover + SALib implementation; incidental v0.2 references reworded for clarity |
| 0.4 | May 2026 | Methodology lead | §4.4 self-critique loop moved ROADMAP→IMPLEMENTED v0; §1 status preamble updated to four-modules-roadmap state (validate_pathway no longer in the roadmap list); §4.4 paragraph rewritten to describe the nine-check `validate_pathway` engine module; §2.2 (iv) and §4.6 prose realigned with the now-implemented validator |

---

### Status preamble

This methodology describes the system at its target state on completion of v0.2 (target: July 2026). At the time of this version's issue, **seven engine modules are implemented and golden-test-validated against three reference sites** (§3.1, §3.2, §3.3, §3.4 single-stage, §3.5, §3.6, §3.7), plus the report renderer. **Four modules are scheduled for v0.2** (§3.8 pinch, §3.9 safety, §3.10 grid, §3.11 reliability), alongside the multi-stage HP architectures noted in §3.4. The `validate_pathway` self-critique loop in §4.4 is **implemented in v0** and runs as a render-time gate — see §4.4 for the check list. Each section below carries an explicit status badge so the reader is never uncertain what the engine produces today.

The engineering claims, standards cited, and validation regime described in this document apply equally to implemented and roadmap modules: the spec is the contract, and ROADMAP modules are not to be released until they meet it.

---

## 1. Introduction

### 1.1 Purpose

This document sets out the calculation methodology underpinning the analysis system described herein (referred to throughout as *the Engine*). The Engine produces consultancy-grade decarbonisation pathway studies for industrial sites, focused in the present version on steam-system electrification within the food and drink, chemicals, pharmaceutical, paper and refining sectors.

The methodology is published so that a senior chartered engineer reviewing an Engine output can, within approximately one hour, verify that:

(a) every numeric output traces to a deterministic calculation against a recognised standard or peer-reviewed source;
(b) the assumptions, default values and uncertainty treatments are defensible and documented;
(c) the limitations of the analysis are stated explicitly and have been respected.

### 1.2 Scope of the Engine

The Engine accepts an industrial site brief — sector, sub-sector, energy profile, plant inventory and operational constraints — and produces a multi-year decarbonisation pathway covering technology screening, dispatch simulation, investment sequencing, uncertainty quantification, safety screening, grid connection feasibility and reliability assessment. The output deliverable is a written technical report supported by a complete calculation provenance record.

Heat-pump refrigerant cycle thermodynamics is the engineering core; pathway analysis comparing heat pumps with electrode boilers, thermal storage and retained gas backup is the product. Hydrogen, biomass, full CCUS, and multi-stage HP architectures above 120 °C sink temperature are screened out with cited reasoning in the present version, and reserved for future scope expansion.

The Engine does not generate detailed engineering design (single-line diagrams, P&IDs, control narratives, foundation calculations or hazardous-area drawings). It is a feasibility-and-pathway tool, sized to inform senior-engineer review at the Concept Design and Feasibility stages of a typical RIBA or equivalent design programme.

The methodology and engine architecture build on prior thermodynamics work undertaken at Imperial College London (MEng dissertation, supervised by Prof. P. A. Lindstedt) and the principal author's professional practice as Heat Pump Lead at Frazer Nash and process safety engineer at Risktec.

### 1.3 Intended audience

This document addresses two audiences in parallel.

The first is the **senior consulting engineer** receiving an Engine output as a draft. The methodology gives that engineer the visibility required to challenge any number in the report, reproduce its derivation and decide whether to sign the deliverable in its entirety, in part or with revision.

The second is the **technical assurance reviewer**, including those acting on behalf of professional indemnity insurers. The methodology gives that reviewer the audit trail required to confirm that every calculation in scope is traceable to a recognised standard, that no critical assumption is implicit, and that the boundary between machine-generated content and human professional judgement is unambiguous.

### 1.4 Document structure

Section 2 describes the Engine's architecture and the design principles that govern every module within it. Section 3 sets out the calculation methodology of each module, with inputs, procedure, outputs, standards cited, and an **explicit module status badge** (IMPLEMENTED or ROADMAP). Section 4 describes the provenance, validation and quality-assurance regime. Section 5 declares the limitations of the methodology. Section 6 contains a consolidated register of standards and references.

---

## 2. System architecture

### 2.1 Overall design

The Engine consists of three components: a **deterministic simulation and optimisation engine** written in Python, a **knowledge corpus** of standards, manufacturer datasheets and case-study evidence stored under retrieval, and an **orchestration layer** based on a large language model.

The deterministic engine is the locus of every numerical claim made in the deliverable. It is independently runnable: each module can be invoked from a Python interpreter without the orchestration layer present. The knowledge corpus supplies citations and evidence to support the qualitative narrative of the deliverable; it does not perform calculation. The orchestration layer plans the sequence of analysis steps, invokes the engine modules in the correct order, retrieves supporting evidence from the corpus and writes the narrative around the engine's numerical results. **It does not perform arithmetic, and is structurally constrained against doing so** — no Python interpreter, no calculator tool, no compute primitive within the orchestration loop. Every numeric claim in the output traces to a deterministic Python function logged in the run audit trail.

### 2.2 Non-negotiable design principles

Five principles govern every module of the Engine without exception:

**(i)** *No arithmetic in the orchestration layer.* Every numeric claim in the output, without exception, traces to a deterministic Python function call in the engine. The orchestration layer is permitted to interpret and contextualise numbers, but not to compute them. This constraint is enforced both by tool-call architecture and by self-check at output time.

**(ii)** *Calculation provenance in every output.* Each numeric output is accompanied by a record naming the function that produced it, the input values used, the version of the engine and the standard or reference document underpinning the calculation. The provenance record is part of the output schema; it is not optional.

**(iii)** *The engine is independently runnable.* The Python engine produces the same numbers irrespective of whether the orchestration layer is present. This requirement guards against calculation drift and supports independent re-execution by a reviewer.

**(iv)** *Self-critique loop.* Before producing the final deliverable, the orchestration layer runs the `validate_pathway` engine module (§4.4) — a structured nine-check pass over the full engine bundle covering numerical consistency between sections, payback-invariant compliance, screen↔pathway grid-headroom consistency, carbon-balance closure, provenance arithmetic self-consistency, MC↔pathway central-tendency agreement, shortlist-pathway containment, standards-register integrity, and methodology-status / engine-implementation parity. Render is gated on `passed=true`; failed-error checks block the report, with the failed check IDs returned to the orchestration layer for remediation. *Status: IMPLEMENTED v0.*

**(v)** *Golden test cases gate every release.* No engine module is released until it produces results, against three reference site profiles, that fall within tolerance bands set by hand-checked engineering judgement. The reference profiles are dairy (5 MW), brewery (8 MW) and soft drinks (12 MW).

### 2.3 Data flow

A site brief is parsed into a structured energy profile (Module 3.1) from which a baseline carbon trajectory is computed (3.2). The technology screen (3.5) produces a shortlist of feasible options. For each candidate pathway, the dispatch simulator (3.3) runs an 8,760-hour operational simulation, drawing on refrigerant-cycle thermodynamics (3.4) for any heat pump components. The investment pathway optimiser (3.6) selects the preferred sequencing under techno-economic and carbon objectives. The Monte Carlo module (3.7) propagates uncertainty across price, demand and grant-outcome inputs. Heat integration is assessed via pinch analysis (3.8). Safety, grid connection and reliability constraints (3.9–3.11) are checked against the proposed configuration. The orchestration layer composes the resulting numerical record, with citations from the knowledge corpus, into the deliverable.

---

## 3. Calculation modules

### 3.1 Energy profile parsing  ▍ `IMPLEMENTED v0`

The procedure constructs an hourly energy profile (8,760 timesteps per year; the architecture supports 17,520-step half-hourly mode where customer half-hourly metering is supplied) for each declared end-use — process steam, hot water, space heating, process cooling, motive electricity, lighting and compressed air — broken down by fuel and by production-volume linkage. Where half-hourly metering data is supplied, the profile is constructed directly from it; otherwise, sector-specific shape templates are scaled to the declared annual consumption and overlaid with the supplied production schedule.

The procedure produces a load duration curve per end-use, a base-load / variable-load split, a production-linkage coefficient (kWh per tonne, hectolitre or unit produced) and an asset-by-asset utilisation factor for the existing plant inventory. Identified inefficiencies are flagged against published sector benchmarks (ETSU industrial sector benchmarking; BREF documents).

**Standards cited:** BS EN 16247-1 (general energy audits), BS EN 16247-3 (industrial sites), CIBSE TM54.

### 3.2 Baseline carbon accounting  ▍ `IMPLEMENTED v0`

Baseline emissions are computed in compliance with the GHG Protocol Corporate Standard, using DEFRA UK Government GHG Conversion Factors for the year of analysis. Scope 1 combustion emissions are reported with separate carbon dioxide, methane and nitrous oxide components, in line with SECR reporting expectations. Scope 2 electricity emissions are computed both location-based (using grid carbon intensity from the National Energy System Operator's Future Energy Scenarios dataset) and market-based (where REGOs or PPAs are declared). Scope 3 upstream natural gas emissions, including methane leakage and production-stage emissions, are added explicitly; this term is typically material, in the range 15–20% of Scope 1.

The procedure flags exposure to three primary regulatory cost / visibility regimes:

- **UK ETS** (cost regime) — site is flagged in/out of scope based on combustion threshold and regulated activity list. *Quantitative allowance liability calculation (allowance price × Scope 1 emissions) is scheduled for v0.2.*
- **UK CBAM** (trade regime) — site is flagged exposed/not-exposed based on whether it produces CBAM-listed goods. *Quantitative product-level embedded-carbon assessment is scheduled for v0.2.*
- **SECR** (visibility regime) — site is flagged reportable/not-reportable based on size thresholds. The Scope 1 + 2 + 3 outputs of this module are SECR-disclosure-grade by design.

The procedure additionally flags adjacent levers — Climate Change Agreements (CCAs), the Climate Change Levy (CCL) — where applicable. **MEES (Minimum Energy Efficiency Standards) is a buildings-regulation lever that is tangential to process-heat decarbonisation and is not addressed by this module.**

**Standards cited:** GHG Protocol Corporate Standard and Scope 2 Guidance, DEFRA GHG Conversion Factors (2026, GCV basis) and Methodology Paper, UK ETS Order, CCL rates schedule, UK CBAM draft regulations (April 2026), SECR Reporting Guidance.

### 3.3 Site dispatch simulation  ▍ `IMPLEMENTED v0`

The dispatch simulator advances the site through 8,760 hourly timesteps (with a half-hourly mode available where electricity tariff or grid intensity resolution requires it), allocating heat and electricity demand across the proposed technology stack at each step. **Heat pump coefficient of performance at each timestep is computed by the refrigerant-cycle module (3.4) at the actual source and sink temperatures prevailing at that step**; Carnot or seasonal-average approximations are not used. The implementation pre-computes COP at 1 °C resolution across the operating envelope and interpolates per timestep, preserving full real-fluid accuracy at viable runtime cost.

The simulator supports four dispatch policies: merit-order (cost-minimal at short-run marginal cost), carbon-minimal (lowest emissions per kilowatt-hour delivered), Pareto-weighted (configurable cost / carbon trade-off) and regulatory-constrained (subject to ETS allowance, CCA cap or planning use-class limits). Equipment availability is modelled with MTBF / MTTR exponential failure distributions. *Multi-pressure steam header tracking, equipment ramp-rate constraints, and waste-heat cascading across end-uses are scheduled v0.2 enhancements.*

An energy balance check is enforced at module exit and the routine raises an exception where the closure error exceeds 0.5%.

**Standards cited:** CIBSE AM17 (heat pumps in buildings, adapted for industrial), CIBSE TM54, IChemE process integration good practice, NESO Future Energy Scenarios (grid intensity), DEFRA GHG Conversion Factors.

### 3.4 Refrigerant cycle thermodynamics  ▍ `IMPLEMENTED v0` (single-stage)  /  `ROADMAP v0.2` (multi-stage architectures)

The heat pump cycle is solved against a published equation-of-state via CoolProp, supporting the refrigerants commonly encountered in industrial high-temperature applications: ammonia (R717), carbon dioxide (R744), R1234ze(E), R290 (propane), and R134a (legacy where its use is presently lawful).

For each operating point in single-stage mode, the procedure resolves evaporator and condenser saturation states (with declared subcool and superheat), the compressor isentropic efficiency from a compressor-type-specific map (screw, reciprocating, scroll, centrifugal, turbo), the discharge temperature against refrigerant-specific limits, and the cycle-average coefficient of performance for both heating and cooling duties. The discharge temperature check is enforced; configurations that exceed the safe envelope are returned with a warning rather than a coefficient-of-performance value. Refrigerant safety constraints (BS EN 378 charge limit estimate, F-Gas Reg GWP screen, ATEX / DSEAR flag for hydrocarbons) are evaluated at every call.

**Multi-stage architectures** — two-stage with economiser, two-stage with intercooler, cascade systems with two refrigerants, and transcritical CO₂ — are scaffolded in code and scheduled for v0.2 implementation. In the present version, sites with required temperature lifts above the single-stage envelope (typically sink ≥ 120 °C against ambient or low-temperature waste-heat sources) are flagged for v0.2 follow-up rather than computed.

**Standards cited:** BS EN 14825 (seasonal performance), BS EN 378 (refrigerating systems, all parts), BS EN 14511 (test conditions), F-Gas Regulation 517/2014 (UK retained), DSEAR 2002, CoolProp documentation citing the underlying equations of state.

### 3.5 Technology screening  ▍ `IMPLEMENTED v0`

The screening procedure evaluates each technology in the longlist against nine feasibility axes: thermodynamic compatibility (can the technology deliver the required temperature at a viable coefficient of performance), commercially available capacity range, refrigerant safety (BS EN 378 charge limits at the proposed location, F-Gas eligibility, ATEX zone implications), process compatibility (Good Manufacturing Practice constraints in food and pharmaceutical applications, contamination risk for biomass), grid headroom against existing connection capacity, planning consent and Building Regulations Part L implications, site footprint, compressor envelope and broader regulatory eligibility (UK ETS, CCA).

The output includes a shortlist with feasibility rationale and flagged risks per technology, an excluded list with reasoned exclusions referenced to the failing axis, and notes flagged for senior review where the screen has insufficient information to decide.

*Implementation note:* the v0 screening is at decision-tree depth — capacity and footprint envelopes are computed; safety, ATEX zoning, and grid headroom are categorical assessments with cited rationale rather than fully computed envelopes. Full envelope computation is scheduled for v0.2.

**Standards cited:** BS EN 378, BS EN 14825, F-Gas Regulation 517/2014, DSEAR 2002, BS 7671, Approved Document L, Town and Country Planning (Use Classes) Order 1987.

### 3.6 Investment pathway optimisation  ▍ `IMPLEMENTED v0`

The optimiser sequences capital investment over a 15- to 20-year planning horizon. The procedure operates by enumeration: a candidate set of pathways, each defined by a sequence of technology installations and capacity steps, is simulated end-to-end through the dispatch module (3.3) and ranked by net present value at the declared discount rate, with the Balanced pathway selected by a configurable rule (default `max_reduction_positive_npv` — the maximum-carbon-reduction pathway whose NPV remains non-negative).

The procedure produces three named pathways — Conservative, Balanced and Aggressive — and a Pareto frontier across the cost-versus-carbon trade-off. For each pathway the output includes year-by-year capital expenditure against the declared budget envelope, simple and discounted payback, internal rate of return, levelised cost of heat, and net present value at the declared discount rate. The risk-adjusted central tendency (CVaR_95) is computed in the §3.7 Monte Carlo wrapper rather than within §3.6 directly.

**Standards cited:** HM Treasury Green Book (appraisal methodology), BS EN 16247-1 §6 (techno-economic appraisal), IEA Cost & Performance Database.

**v0 limitations:** the v0 implementation enumerates a fixed candidate set; a future release (v0.3) will replace enumeration with a multi-period stochastic mixed-integer linear programme implemented in Pyomo or OR-Tools, retaining the dispatch simulator as the inner-loop evaluator. Mid-life equipment replacement and component ageing are not modelled in v0; the discounted-payback contract therefore implements the v0 first-cross convention rather than the stricter "remains non-negative through the horizon end" form intended for v0.2.

### 3.7 Monte Carlo uncertainty  ▍ `IMPLEMENTED v0`

Uncertainty is propagated by Latin hypercube sampling, with default 1,000 trials and 10,000 trials available for high-stakes runs. Rank-correlation between sampled inputs is imposed by the Iman-Conover (1982) procedure with a Cholesky factorisation of the target correlation matrix. The default uncertain inputs are electricity and gas price trajectories (triangular distributions calibrated to DESNZ projections), grid carbon intensity in the 2030 horizon (NESO Future Energy Scenarios range), heat pump capital cost (triangular multiplier on manufacturer ranges), grant outcomes (Bernoulli on declared grant probability) and annual demand growth. Gas and electricity prices are sampled with a positive correlation, default 0.6; the realised Pearson correlation is reported and asserted to within 0.05 of the target.

For each sampled trial, the deterministic pathway record is re-evaluated in closed form: annual dispatch cost is multiplicatively perturbed by the sampled gas and electricity price ratios, capex by the sampled HP-capex multiplier, and the IETF grant by the sampled outcome. The annual carbon trajectory is similarly perturbed by the sampled grid-intensity factor.

Outputs include the full distribution of net present value (P10, P50, P90, mean, standard deviation, skew), the carbon trajectory uncertainty cone, the probability that net present value exceeds zero (`prob_npv_positive`), the probability that an annual carbon target is met (`prob_carbon_target_met`, default linear glide from baseline year-0 carbon to zero at horizon end), Value-at-Risk at the 95th percentile (loss convention), and conditional Value-at-Risk at the 95th percentile. Sobol first-order and total-order sensitivity indices are computed via the SALib Saltelli sampler and analysis routine, identifying which inputs drive output variance. Morris elementary effects (μ, μ*, σ) are reported as a screening-level cross-check.

**Standards cited:** Saltelli (2010) *Variance based sensitivity analysis of model output*. Morris (1991) *Factorial sampling plans for preliminary computational experiments*. Iman & Conover (1982) *A distribution-free approach to inducing rank correlation among input variables*. HM Treasury Green Book §A4 (uncertainty). BS EN 16247-3 §6.4 (uncertainty in industrial energy audits).

**v0 limitations:** the v0 inner loop is closed-form pathway re-evaluation rather than per-trial dispatch — gas-price uncertainty therefore propagates through the static gas-only counterfactual rather than through HP/EB switching, biasing the Sobol decomposition toward `gas_price` relative to a per-trial dispatch implementation. Sobol second-order indices are not computed in v0 (sample budget). The HP capex multiplier is applied to total pathway capex rather than HP-only capex, which overstates capex variance for pathways where non-HP technologies dominate the capex stack. All three are scheduled for v0.3.

### 3.8 Pinch analysis and heat integration  ▍ `ROADMAP v0.2`

Pinch analysis is performed in accordance with the Linnhoff March method as described in Kemp (*Pinch Analysis and Process Integration*, second edition) and IChemE process-integration practice. Hot and cold process streams are aggregated into composite curves and the grand composite curve. The pinch temperature, minimum hot utility demand, minimum cold utility demand and minimum heat-exchanger area target are reported at the user's declared minimum approach temperature (default 10 K). The capital-energy trade-off is presented as a curve over a range of approach temperatures.

A heat-exchanger network synthesis routine proposes stream-to-stream matches and provides a shell count and area estimate. Pinch violations and network pockets are flagged. The procedure does not perform detailed thermal-hydraulic design of individual exchangers; that is reserved for the subsequent design stage.

**Standards cited:** Kemp, *Pinch Analysis and Process Integration*, 2nd ed. Linnhoff March, *User Guide on Process Integration*. Smith, *Chemical Process Design and Integration*. IChemE *Process Integration Best Practice Guides*.

### 3.9 Safety constraint screening  ▍ `ROADMAP v0.2`

The safety screen is positioned at the level of an ALARP screening exercise — sufficient to identify the dominant safety considerations, insufficient to substitute for a HAZOP. For each proposed unit, the procedure performs a charge-limit assessment under BS EN 378 against the proposed plant-room volume; identifies refrigerants that trigger ATEX zone classification (with the typical 20–40% capital cost uplift for compliant equipment); assesses refrigerant-specific hazards (ammonia toxicity and leak detection requirements; carbon dioxide asphyxiation in confined space; hydrocarbon flammability); and screens for Pressure Equipment Directive applicability where the operating pressure exceeds 0.5 barg.

Steam-system safety implications under PSSR 2000 are flagged for new electrode boilers. DSEAR-relevant cause-event-consequence pairs are recorded. CDM 2015 construction-phase risks are noted. The output is a structured risk register intended to inform, not replace, the formal HAZOP that will be required at the subsequent design stage.

**Standards cited:** BS EN 378 (parts 1–4), DSEAR Regulations 2002, ATEX Directive 2014/34/EU, F-Gas Regulation (UK retained), Pressure Equipment (Safety) Regulations 2016, PSSR 2000, CDM Regulations 2015.

### 3.10 Grid connection assessment  ▍ `ROADMAP v0.2`

The grid connection screen is positioned at the level of a G99 connection feasibility study, sufficient to identify site-killing connection issues but not to substitute for the Distribution Network Operator's formal connection offer. The procedure compares proposed new electrical loads (heat pumps, electrode boilers, motors) against the declared existing connection capacity. Where the resulting site demand exceeds the existing capacity, the increment requiring DNO reinforcement is reported, with an indicative cost range (£50,000 – £500,000) and an indicative timeline (six to eighteen months) calibrated to the relevant DNO area.

Voltage rise at the point of connection is estimated against BS EN 50160 limits. Harmonic injection from variable-speed drives and electrode boilers is screened against IEEE 519 and Engineering Recommendation G5/5; where indicative harmonic distortion exceeds the tolerance, a formal harmonic study is recommended.

**Standards cited:** Engineering Recommendation G99, Engineering Recommendation G5/5, BS EN 50160, BS 7671, IEEE 519, DNO Long Term Development Statements (latest editions).

### 3.11 Reliability and availability  ▍ `ROADMAP v0.2`

System availability is computed from per-unit Mean Time Between Failures and Mean Time To Repair data, drawn either from vendor documentation or, in its absence, from the Offshore Reliability Data Handbook and Lees' *Loss Prevention in Process Industries*. Single-unit and N+1 / N+2 redundant configurations are evaluated against a user-declared availability target (typically 99.0%, 99.5% or 99.9%). The procedure reports annual expected downtime in hours, annual expected downtime cost at the user's declared cost-per-downtime-hour rate, and the recommended planned-maintenance regime.

A v0.2 implementation assumes exponential failure distributions and time-independent availability; future releases will support Markov modelling for systems with significant maintenance-state structure.

**Standards cited:** BS EN 60300 (dependability management), OREDA (Offshore Reliability Data Handbook), Lees' *Loss Prevention in Process Industries*, IEC 61078 (reliability block diagrams).

---

## 4. Provenance, validation and quality assurance

### 4.1 Calculation provenance

Every numeric output of every module is accompanied by a provenance record naming the engine version, the module function, the input values supplied, and the reference document or standard underpinning the calculation. The provenance record is generated mechanically and is part of the output schema. A reviewer reading any deliverable can, for any number in the report, locate the originating function call and reproduce it.

### 4.2 Standards-cited register

Each module declares a `standards_cited` list as part of its output. The list identifies the standards, codes of practice and reference works underpinning that module's calculations. The deliverable's standards register, presented in Section 6, is the union of these lists across all modules invoked for the analysis.

### 4.3 Golden test case regime

Three reference site profiles — a 5 MW dairy, an 8 MW brewery and a 12 MW soft drinks plant — are maintained as fixtures alongside the engine source. Each fixture carries a *golden truth* block that records hand-checked engineering expectations against which each module's output is validated. The expected ranges, shortlist inclusions and exclusions, regulatory flags and characteristic outputs are calibrated against published sector benchmarks and cross-checked by a senior reviewer; they are not regenerated from engine output. A test that passes only because the engine has been run is not a test, and the regime is constructed to make this distinction explicit.

The numeric tolerance bands applied are ±10% on cardinal results and ±25% on probabilistic ranges (P10 / P90). Categorical results (shortlist membership, regulatory flag presence, warning codes) are checked for exact match.

### 4.4 Self-critique loop  ▍ `IMPLEMENTED v0`

The `validate_pathway` engine module runs after all upstream tool calls and before the renderer, performing nine cross-module consistency and arithmetic checks over the engine bundle (parse, screening, baseline carbon, dispatch, pathway, Monte Carlo). Each check returns a structured record (`check_id`, `severity` ∈ {error, warning, info}, `passed`, `message`, `details`); the public function aggregates them and exposes `passed` (True iff zero error-severity checks failed) plus a `summary` and full `checks` list.

The v0 check set:

1. `discounted_ge_simple_payback` (error). For each named pathway, asserts `discounted_payback_years ≥ simple_payback_years` (or both None, or simple-non-None & discounted-None — discounting can push past the horizon, but never earlier than the undiscounted cumulative cross).
2. `screen_pathway_grid_consistency` (error). Asserts that no action in any `pathways_no_reinforcement` named pathway carries `requires_grid_decision=True` — the §3.3 pending-grid screening verdict must propagate into the no-reinforcement track.
3. `carbon_balance_year_15` (error). For each named pathway, asserts `(baseline_y0 − pathway_y15) / baseline_y0 ≈ year_15_reduction_pct` to within 0.5 percentage points.
4. `exec_summary_baseline_consistency` (warning). The §1 baseline-y0 figure (from the pathway's per-year baseline dispatch) and `compute_baseline_carbon.totals.scope_1_2_loc_t_co2e` must agree within 5%; current EF / grid-intensity divergence between the two routines is flagged for v0.2 reconciliation.
5. `provenance_arithmetic_self_consistent` (error). Iterates provenance rows whose `method` string contains a `<a> × <b> = <c>` pattern; asserts `|a × b − c| < max(£1, 0.5%·|c|)`. Catches CCL-class display-rounding bugs.
6. `mc_pathway_consistency` (warning). When Monte Carlo is wired, asserts `monte_carlo.npv_distribution.p50_gbp` is within ±20% of the deterministic Balanced NPV.
7. `shortlist_in_pathway_or_excluded` (error). Every action `tech_id` in any named pathway must appear in `screening.shortlist` or `screening.excluded_pending_grid_decision`.
8. `standards_register_no_dupes` (info). The Appendix B standards register, formed as the union of every input dict's `standards_cited`, is asserted duplicate-free after whitespace normalisation.
9. `methodology_status_matches_engine` (warning). For each `### 3.X module ▍ <BADGE>` line in this document, the corresponding engine bundle key is checked for non-stub presence; mismatches are warned (the check is the cross-module guard against this document drifting out of sync with the shipped engine).

Render is gated: when the LLM requests `render_report`, the tool dispatcher checks `_site_context.engine_results.validate_pathway.passed`. If False or missing, render returns an error to the orchestration layer naming the failed check IDs; the LLM is instructed to fix the underlying engine output (typically by re-calling an upstream tool with corrected parameters) and re-call `validate_pathway` before re-attempting render. The full check list is also persisted to the engine bundle and rendered as §10 of the deliverable so a senior reviewer can see, at a glance, that every cross-section invariant was checked and the value of `passed`.

**v0 limitations:** the §3.X-to-engine-key mapping in check 9 is hand-coded; a future v0.2 enhancement is to derive it from a tool registry. The §1 baseline-y0 inconsistency surfaced by check 4 is a known v0.2 reconciliation ticket — the validator flags it as a warning rather than blocking render.

**Standards cited:** the validator itself does not introduce new standards; it asserts conformance with the standards already cited by the engine modules it audits. Provenance entries name `decarb.engine.validate.<check_id>` for each failed check.

### 4.5 Boundary of machine-generated content

The deliverable is positioned as a draft for senior-engineer review. The system does not replace the chartered-engineer review and sign-off step. The boundary is explicit: numbers and citations are machine-generated; engineering judgement, sign-off and professional indemnity remain with the human reviewer.

### 4.6 Architectural enforcement of the no-arithmetic principle

The orchestration layer is structurally prevented from performing arithmetic. The agent loop exposes only two interfaces to the language model: text generation and named tool requests. The model has no Python interpreter, no calculator tool, no code execution sandbox, and no path by which it can manufacture a number outside of a deterministic engine output. Numerical claims in the narrative are matched against the run audit log by the `validate_pathway` tool (implemented in v0; see §4.4); discrepancies are flagged before render and the render is blocked when error-severity checks fire. The enforcement therefore rests on three layers — architecture, prompt discipline, and post-draft validation — described in Section 4.4 above and reviewable in the engine source.

---

## 5. Limitations and assumptions

The methodology, in its present version, applies to industrial sites within the food and drink, chemicals, pharmaceutical, paper and refining sectors, with thermal demand in the 1–50 MW range, considering the electrification of steam systems through heat pumps, electrode boilers and thermal storage, with optional photovoltaic, battery and waste-heat recovery integration, at sink temperatures below approximately 120 °C in v0 (extending to approximately 180 °C with multi-stage architectures in v0.2). Sites outside this envelope — thermal demand below 1 MW or above 50 MW, sectors with materially different process characteristics (cement, glass, primary metals), or decisions other than steam-system electrification (cooling-system electrification, on-site hydrogen production, carbon capture) — fall outside the present validation envelope.

Default values, where used, are drawn from UK-specific datasets: DEFRA emission factors for the year of analysis; National Energy System Operator Future Energy Scenarios for grid carbon intensity projection; CIBSE benchmarks for sector load shapes; manufacturer-published data for equipment performance. Where a default is invoked, the provenance record discloses it; default values are visible to the reviewer and may be replaced with site-specific data without re-running the entire analysis.

The methodology does not perform detailed engineering design (line-sized P&IDs, foundation design, control narratives, hazardous-area drawings, single-line diagrams), nor does it conduct a HAZOP, a Quantitative Risk Assessment, a formal harmonic study, or a Distribution Network Operator connection study. Each of these is a downstream design activity for which the present analysis provides input, not substitute. The deliverable identifies, in each case, the activity required at the next design stage.

---

## 6. Standards register

| Reference | Title / scope |
|---|---|
| BS EN 14825 | Air conditioners, liquid chilling packages and heat pumps — testing and rating at part-load conditions |
| BS EN 14511 | Air conditioners, liquid chilling packages and heat pumps for space heating and cooling — performance |
| BS EN 16247-1 | Energy audits — General requirements |
| BS EN 16247-3 | Energy audits — Processes |
| BS EN 378 (1–4) | Refrigerating systems and heat pumps — Safety and environmental requirements |
| BS EN 50160 | Voltage characteristics of electricity supplied by public distribution networks |
| BS EN 60300 | Dependability management |
| BS 7671 | Requirements for electrical installations (IET Wiring Regulations) |
| CIBSE AM17 | Heat pumps in buildings (adapted for industrial application) |
| CIBSE TM54 | Evaluating operational energy performance |
| Approved Document L | Conservation of fuel and power (Building Regulations, England) |
| CDM Regulations 2015 | Construction (Design and Management) Regulations |
| DSEAR 2002 | Dangerous Substances and Explosive Atmospheres Regulations |
| ATEX Directive 2014/34/EU | Equipment for use in potentially explosive atmospheres |
| F-Gas Regulation 517/2014 | Fluorinated greenhouse gases (UK retained) |
| Pressure Equipment (Safety) Regulations 2016 | Implementing PED 2014/68/EU in the UK |
| PSSR 2000 | Pressure Systems Safety Regulations |
| Engineering Recommendation G99 | Connection of generation to DNO networks |
| Engineering Recommendation G5/5 | Harmonic distortion limits at the point of common coupling |
| IEEE 519 | Recommended practice for harmonic control in electric power systems |
| IEC 61078 | Reliability block diagrams |
| GHG Protocol Corporate Standard | Greenhouse gas accounting and reporting |
| GHG Protocol Scope 2 Guidance | Location- and market-based methods |
| DEFRA Conversion Factors | UK Government GHG Conversion Factors (current year) |
| HM Treasury Green Book | Appraisal and evaluation methodology |
| NESO Future Energy Scenarios | UK grid carbon intensity projection (current year) |
| UK ETS Order | UK Emissions Trading Scheme regulatory framework |
| UK CBAM Regulations (draft Apr 2026) | Carbon Border Adjustment Mechanism |
| SECR Reporting Guidance | Streamlined Energy and Carbon Reporting |
| Kemp (2007) | *Pinch Analysis and Process Integration*, 2nd edition |
| Smith (2016) | *Chemical Process Design and Integration*, 2nd edition |
| Saltelli et al. (2008) | *Global Sensitivity Analysis: The Primer* |
| Lees (2012) | *Loss Prevention in the Process Industries*, 4th edition |
| OREDA (2015) | Offshore Reliability Data Handbook, 6th edition |
| IChemE | *Process Integration Best Practice Guides* |

---

*End of document. v0.2 draft for senior-engineer review. Implementation status badges per module reflect engine state at issue date; v0.2 target completion: July 2026.*
