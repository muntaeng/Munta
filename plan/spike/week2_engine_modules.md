# Week 2 — Engine v0 Module Specs (consultancy-grade depth)

The engine is the moat. Every module in this spec must produce output that a senior engineer at Frazer Nash, WSP, or Arup can read and recognise as engineering work — not as approximation. Where existing tools (IES VE, Aspen Plus, EBSILON, IPSEpro) operate on a particular topic, the depth bar is "at least matches incumbent depth, in some dimension exceeds it."

**General quality rules — applied to every module:**

1. **Approach temperatures, not idealisations.** Every heat exchanger has an LMTD approach. No infinite-area assumptions.
2. **Time resolution: half-hourly minimum** for any dispatch / load / market interaction. Hourly is acceptable for a v0 sprint but the architecture must support 30-min when corpus / customer data does.
3. **Regulatory + safety constraints checked, not ignored.** F-gas, BS EN 378, DSEAR, IED, ATEX, ETS, CCAs, MEES, Climate Change Levy. Each module declares which apply.
4. **Uncertainty quantification per output.** Point values are flagged. Ranges (P10/P50/P90) preferred where possible.
5. **Standards cited inline.** Every output has a `standards_cited` list pointing to the BS EN / CIBSE / IChemE / IEA / ISO / DEFRA documents underpinning the calculation.
6. **Failure modes explicit.** Every module enumerates the conditions under which it returns a warning rather than silently approximating.
7. **Output is provenance-complete.** Every numeric output traces to either a closed-form computation in the module, a cited reference value, or a sub-call to another engine module.

---

## §1 `parse_energy_profile`

**Bar:** match what a real BS EN 16247-3 energy audit produces from half-hourly meter data. Generic shape templates are a fallback when no data is provided, not the primary mode.

**Inputs:**
- Site brief (sector, sub-sector, location)
- Half-hourly metering data (electricity, gas, oil, steam) — optional
- Production schedule (shifts, holidays, planned maintenance days, seasonal volume)
- End-use breakdown (steam, hot water, cooling, motive electricity, lighting, compressed air, process fluids)
- Existing plant inventory (boilers, chillers, compressors, motors — with age + efficiency)

**What it produces:**
- Half-hourly (17,520-step) load profile per end-use, per fuel type, with seasonality
- Diversity factors between end-uses (correlated where appropriate — e.g. lighting + HVAC)
- Peak demand analysis (annual peak, monthly peaks, P95 / P99)
- Load duration curve per end-use
- Identified base load vs variable load split
- Production-volume linkage (kWh per tonne / hl / unit produced)
- Existing plant utilisation analysis (load factor per asset)
- Identified inefficiencies vs sector benchmarks (e.g. ETSU food & drink, BREF)

**Standards cited:** BS EN 16247-1 (general energy audit), BS EN 16247-3 (industrial sites), CIBSE TM54, ETSU industrial sector benchmarks.

**Reuse from MUNTec:** `weather.py` profile shaping logic — extend with shift patterns and production-linkage; `simulation.py` hour-by-hour loop pattern.

**Golden test acceptance:** dairy_5mw.json → reconstructs annual gas (38 GWh) and electricity (12.5 GWh) within 1%; correctly identifies steam demand peak as ~3.5 MW thermal during double-shift hours; assigns ~70% of cooling load to fermentation (mostly constant) vs 30% to product-storage (diurnal).

---

## §2 `compute_baseline_carbon`

**Bar:** GHG Protocol Corporate Standard compliant. Scope 1 + 2 (location AND market based) + Scope 3 upstream methane on natural gas. Half-hourly grid intensity, not annual averages.

**Inputs:**
- Energy profile (half-hourly per fuel)
- Year (DEFRA factors are dated)
- Site location (for grid intensity zone if needed)
- Market-based inputs (REGOs, PPAs) — optional

**What it produces:**
- **Scope 1:** combustion emissions per fuel (kg CO2e + breakdown CH4 + N2O + CO2 separately for accuracy under SECR)
- **Scope 2 location-based:** half-hourly grid factor × half-hourly electricity → annual total + monthly profile
- **Scope 2 market-based:** REGOs / PPA-adjusted (if user provides)
- **Scope 3 upstream natural gas:** methane leakage + production emissions per DEFRA Scope 3 factors (often material — 15–20% on top of Scope 1)
- **Carbon trajectory baseline:** projected emissions if no action taken, against forecast grid intensity (NESO FES) and any forecast fuel changes
- **CCL exposure:** Climate Change Levy paid on electricity / gas
- **UK ETS exposure:** if site is in scope (>20 MW combustion or in regulated activities list)
- **CBAM exposure:** for cement, iron, steel, fertilisers, hydrogen, aluminium, electricity exporters

**Standards cited:** GHG Protocol Corporate Standard + Scope 2 Guidance, DEFRA UK Government GHG Conversion Factors (current year + Methodology Paper), SECR Reporting Guidance, CCL rates (HMRC), UK ETS rules, CBAM Regulation (EU) 2023/956.

**Reuse from MUNTec:** `calculator.py` DEFRA factors → extract to `engine/emission_factors.py`.

**Golden test acceptance:** dairy_5mw.json → 7,820 ± 80 tCO2e/yr Scope 1+2 location-based; Scope 3 upstream gas adds ~1,200 tCO2e; correctly flags as not in UK ETS but SECR-reportable; correctly identifies CCL-payable on electricity portion.

---

## §3 `simulate_site_dispatch`

**Bar:** matches what HOMER Pro, EnergyPRO, or PLEXOS produce for site-level dispatch — but with multi-pressure steam headers, refrigerant cycle integration, and ATEX/safety constraints.

**Inputs:**
- Energy profile (half-hourly per end-use)
- Technology stack proposed (each tech has dispatch policy: priority, cost-min, carbon-min)
- Half-hourly market signals (electricity TOU, grid carbon intensity)
- Equipment characteristics (capacity, COP curve vs ambient, ramp rate, min runtime, MTBF)

**What it produces:**
- Half-hourly dispatch trajectory over 1 year
- Multi-pressure steam header tracking (LP/MP/HP) with proper saturated steam properties
- Heat pump COPs computed per timestep via `calculate_hp_cycle` at the actual hourly source/sink temps
- Electrode boiler dispatch under TOU tariffs (charges thermal store off-peak, discharges to steam header peak)
- Thermal storage charge/discharge with state-of-charge tracking
- Waste heat recovery cascade (chiller waste → low-temp HP → MP heat pump → steam pre-heat)
- Equipment availability simulation (MTBF/MTTR-based downtime)
- Ramp + min-runtime + min-downtime constraints respected
- Annual fuel use and carbon by source
- Energy balance check (must close to <0.5%)

**Dispatch policies supported:**
- `merit_order` (cheapest first by short-run marginal cost)
- `carbon_minimal` (lowest emissions per kWh delivered)
- `pareto_weighted` (configurable cost / carbon weighting)
- `regulatory_constrained` (subject to ETS, CCA cap, planning use-class limits)

**Standards cited:** CIBSE AM17 (heat pumps in buildings — adapted for industrial), CIBSE TM54, IChemE process integration good-practice, NESO Future Energy Scenarios for grid intensity.

**Reuse from MUNTec:** `simulation.py` 8,760-hour dispatch loop is the bones; extend to half-hourly + industrial process heat profiles.

**Golden test acceptance:** dairy_5mw.json with stack [2MW NH3 HP + 4MW electrode boiler + 8MWh thermal store + retained gas backup] → annual gas displacement 65–75%; HP runtime > 6,000 hr/yr; electrode boiler runs predominantly during off-peak windows; energy balance closes to <0.3%.

---

## §4 `calculate_hp_cycle` ✅ (v0.2 implemented)

See `backend/decarb/engine/hp_cycle.py`. Already at consultancy-grade depth for single-stage. Two-stage economiser / intercooled / cascade / transcritical CO2 to land in v0.3 (week 3+).

Validation against published refrigerant cycle textbook results:
- NH3, evap 0°C, cond 80°C, screw, 3K subcool, 5K SH → COP_h 3.4–3.8, discharge ~110°C
- R744 transcritical, evap -10°C, gas cooler 90°C → COP_h 2.3–2.7 (when transcritical implemented)
- R1234ze(E), evap 30°C, cond 90°C, screw → COP_h 4.5–5.5

If outputs deviate >10% from textbook, debug before week 2 dispatch sim depends on it.

---

## §5 `screen_technologies`

**Bar:** decision-tree shortlist with proper feasibility envelope checking for each technology. Goes beyond "include if temperature is in range" — includes safety, planning, refrigerant, grid, capex envelope.

**Inputs:**
- Site brief (sector, sub-sector, location, constraints)
- Energy profile (process heat temperatures + demand profile)
- Existing plant inventory

**Per-technology rules (extending the 15-tech longlist):**

For each technology, check feasibility on these axes:
- **Thermodynamic feasibility:** can it deliver the required temperature with viable COP?
- **Capacity range fit:** is the unit size commercially available?
- **Refrigerant safety (HP only):** F-gas restriction, BS EN 378 charge-limit at site, ATEX zone restrictions
- **Process compatibility:** GMP for food/pharma, contamination risk for biomass, vibration sensitivity
- **Grid connection:** kVA headroom required vs available
- **Planning / Part L:** Building Regulations, planning permission requirements
- **Site space:** plant footprint vs envelope
- **Compressor envelope:** if HP, temperature lift achievable with available compressor types
- **Regulatory:** ETS-allowable, CCA-compatible

**What it produces:**
- Shortlist (each entry: technology id + capacity_range + feasibility rationale + flagged risks)
- Excluded list (each entry: technology id + reason + which feasibility axis failed)
- Notes flagged for senior review (borderline cases the agent shouldn't auto-exclude)

**Standards cited:** BS EN 378, BS EN 14825, F-Gas Reg 517/2014, DSEAR 2002, BS 7671 (electrical), Approved Document L (Part L), Town and Country Planning (Use Classes) Order 1987.

**Golden test acceptance:** All 3 sites produce shortlists matching `_golden_truth.expected_shortlist_must_include`; biomass excluded for dairy + brewery on contamination grounds with citation; hydrogen 100% boiler excluded for dairy on infrastructure grounds; soft drinks excluded H2 + biomass per client constraints (must respect explicit constraints).

---

## §6 `optimise_investment_pathway`

**Bar:** matches what a real techno-economic study uses. Multi-period stochastic MILP with scenario tree. Multi-objective (NPV vs carbon vs risk). Pareto frontier, not just best-case.

**Implementation phasing:**
- Week 2: brute-force scenario enumeration (~50 candidate pathways simulated, ranked by NPV) — get to a working answer
- Week 3+: replace with proper stochastic MILP via Pyomo + GLPK or OR-Tools

**Inputs:**
- Energy profile
- Shortlisted technologies (each with capex curve vs capacity, opex profile, lifetime, learning rate)
- Constraints (capex per period, cumulative budget, planning horizon, must-keeps, regulatory)
- Discount rate
- Scenario tree (electricity prices, gas prices, carbon prices, grant outcomes, demand growth)
- Objective weighting (cost / carbon / risk)

**What it produces:**
- **Three named scenarios:** Conservative (do less, lower risk), Balanced (best NPV), Aggressive (max decarb)
- **Pareto frontier** of cost vs carbon for ~10 alternative pathways
- **For each pathway:**
  - Year-by-year action list (install X at Y MW in year Z)
  - NPV with P10/P50/P90 from MC
  - Cumulative carbon trajectory
  - Capex per year against budget envelope
  - Simple + discounted payback
  - IRR
  - LCOH (levelised cost of heat)
  - Risk-adjusted NPV (CVaR @ 90%)
  - Sensitivity to key inputs (electricity price, IETF grant, gas price)
- **Real options analysis:** value of waiting one period before deciding (when does it pay to delay)
- **Equipment ageing:** end-of-life replacement decisions baked in

**Standards cited:** HM Treasury Green Book (appraisal methodology), BS EN 16247-1 §6 (energy audit techno-economic appraisal), IEA Cost & Performance Database, Lazard Levelized Cost (current year).

**Reuse from MUNTec:** `phased_retrofit.py` and `calculations.py` financial calcs.

**Golden test acceptance:** dairy_5mw.json balanced pathway → NPV £1.2–3.5m, payback 6–11 yr, IRR > 10%, year-15 carbon reduction 85–95%; Pareto front shows aggressive pathway is feasible only with IETF grant.

---

## §7 `monte_carlo_uncertainty`

**Bar:** SciPy + SALib done properly. Latin hypercube sampling, correlated inputs (gas/electricity copula), Sobol global sensitivity, Morris elementary effects for screening, VaR/CVaR risk metrics.

**Inputs:**
- Pathway (deterministic best-estimate)
- Uncertain inputs with distributions:
  - Electricity price 2026–2040 (triangular or empirical from DESNZ)
  - Gas price 2026–2040 (triangular)
  - Gas–electricity price correlation (typical ρ = 0.5–0.7)
  - HP capex (triangular from manufacturer ranges)
  - Grid carbon intensity 2030 (NESO FES range)
  - IETF grant outcome (bernoulli)
  - Demand growth (triangular)
- N trials (default 1,000; up to 10,000 for high-stakes runs)

**What it produces:**
- NPV distribution with P10 / P50 / P90 / mean / stdev / skew / 1,000-sample histogram
- Carbon-2040 distribution
- Carbon trajectory uncertainty cone (P10/P50/P90 each year)
- Probability NPV > 0 (P_success)
- Probability annual carbon target met (per UK Net Zero or client target)
- VaR_95% (loss at 95th percentile)
- CVaR_95% (expected loss given worst 5%)
- Sobol first- + second-order sensitivity indices (which inputs drive output variance)
- Morris elementary effects (which inputs to investigate further)
- Sample-correlated-input quality check

**Standards cited:** Saltelli et al. *Global Sensitivity Analysis: The Primer*, BS EN 16247-3 §6.4 (uncertainty in industrial energy audits), HM Treasury Green Book §5 (uncertainty), Society of Actuaries practice notes on CVaR.

**Golden test acceptance:** dairy_5mw.json balanced pathway → P_success > 0.7; top-2 Sobol inputs are electricity price + IETF grant; CVaR_95% NPV is a meaningful negative number, not zero; output covers all risk metrics in the schema.

---

## §8 `compute_pinch_analysis`

**Bar:** real Linnhoff March pinch analysis — composite curves, grand composite, area targeting, capital-energy trade-off, heat exchanger network synthesis. Not a hand-wave.

(Deferred to week 3 because it's not on the critical path for the dairy/brewery test sites — but documented now so it's not surprised in week 3.)

**Inputs:**
- All hot streams (process needing cooling, with T_in / T_out / mass flow / Cp or directly enthalpy curve)
- All cold streams (process needing heating)
- Minimum approach temperature (ΔTmin, typically 10K)
- Hot utility cost per kW
- Cold utility cost per kW
- HX area cost ($/m²)

**What it produces:**
- Composite curves (hot composite, cold composite)
- Grand composite curve
- Pinch temperature
- Minimum hot utility target (Q_H_min)
- Minimum cold utility target (Q_C_min)
- Heat exchanger area target (m²)
- Capital-energy trade-off curve (varying ΔTmin)
- Suggested HX network (matches between hot and cold streams)
- Stream count + shell count estimates
- Identified pockets / pinch violations

**Standards cited:** Kemp *Pinch Analysis and Process Integration* (2nd ed), Linnhoff March *User Guide on Process Integration*, IChemE *Process Integration Best Practice Guides*, Smith *Chemical Process Design and Integration*.

**Golden test acceptance:** dairy_5mw.json → pinch temperature in 30–60°C range; minimum hot utility 28–40 GWh/yr (vs 38 GWh current); WHR potential 4–8 MW thermal demand reduction.

---

## §9 `compute_safety_constraints` (NEW — week 3)

**Bar:** mirror what a Risktec ALARP demonstration touches at screening level. Not a full HAZOP but enough that no senior engineer can dismiss the output as "ignored safety".

**Inputs:**
- Proposed technology stack (with refrigerants, capacities, locations)
- Site layout (occupied space proximity, plant room characteristics)
- Sector (food/pharma/chemicals/etc.)

**What it produces:**
- BS EN 378 charge-limit assessment per HP unit (charge_kg vs max_charge_per_zone)
- ATEX zone classification implications (zone 0/1/2/22 if hydrocarbon refrigerant; affects equipment cost +20–40%)
- DSEAR risk register (initial cause-event-consequence per refrigerant)
- F-gas tracking (total CO2e of refrigerant inventory; phase-down implications)
- Refrigerant-specific safety call-outs (NH3 toxicity → leak detection + PPE; CO2 → asphyxiation in confined space; hydrocarbons → flammability)
- High-pressure equipment (PED 2014/68/EU): components > 0.5 bar.g need PED CE marking; affects supplier selection
- Steam system safety (HSE PSSR 2000) for new electrode boilers
- Compressed air, electrical (HSE EAW Regs 1989), noise (Control of Noise at Work Regs 2005)
- Construction phase risks (CDM 2015) flagged

**Standards cited:** BS EN 378 (parts 1–4), DSEAR 2002, ATEX Directive 2014/34/EU, F-Gas Reg (UK retained), Pressure Equipment Directive 2014/68/EU, PSSR 2000, CDM 2015.

**Golden test acceptance:** dairy_5mw.json with NH3 HP → flags toxicity + plant-room ventilation + leak detection requirements; flags BS EN 378 charge limit considerations; raises PED applicability for any pressure vessel >0.5 bar.

---

## §10 `assess_grid_connection` (NEW — week 3)

**Bar:** what an Atkins / WSP electrical engineer would write for a G99 connection screening. Not a full DNO study but enough to flag site-killing connection issues.

**Inputs:**
- Existing site grid connection (kVA capacity, voltage level, fault level)
- Proposed new electrical loads (HPs, electrode boilers, motors)
- Proposed new generation (PV, BESS) — if any
- Site location (DNO area)

**What it produces:**
- Required new connection capacity (kVA) post-electrification
- Headroom analysis (existing - new vs maximum)
- G99 application implications (>11 kW or >16 A/phase)
- Voltage rise estimate at point of connection (BS EN 50160 §4.2 limits)
- Harmonic injection assessment (if VSDs / electrode boilers — IEEE 519, Engineering Recommendation G5/5)
- DNO reinforcement risk (new transformer, cable upgrade) → cost range £50k–£500k
- Time-to-connect estimate (DNO area-specific: 6–18 months typical)
- Embedded benefits (TRIAD avoidance — though largely abolished post-T&CR review, residual matters)

**Standards cited:** Engineering Recommendation G99, Engineering Recommendation G5/5, BS EN 50160, BS 7671, IEEE 519, DNO Long Term Development Statements (latest).

**Golden test acceptance:** dairy_5mw.json with 4MW new HP+electrode → flags 1.0 MVA headroom is insufficient (5MW load + existing); flags G99 application required; estimates 12-month DNO timeline; flags harmonic study for electrode boiler.

---

## §11 `compute_reliability_availability` (NEW — week 3)

**Bar:** what a Risktec reliability engineer produces — Mean Time Between Failures, redundancy / N+1 analysis, downtime cost, availability fraction. Not a Markov model in v0 but proper exponential-failure assumptions.

**Inputs:**
- Proposed technology stack with vendor reliability data (or defaults from OREDA / Lees)
- Required system availability (99.0%, 99.5%, 99.9%)
- Downtime cost per hour (typically £5,000–£50,000/hr for industrial process)
- Maintenance windows allowed

**What it produces:**
- MTBF per unit
- MTTR per unit
- System availability (with and without redundancy)
- Required N+1 / N+2 sizing to meet target availability
- Annual expected downtime (hours)
- Annual expected downtime cost (£)
- Sensitivity to vendor reliability data uncertainty
- Recommended maintenance regime (PM intervals, CM strategies)

**Standards cited:** BS EN 60300 (Reliability Management), OREDA (Offshore Reliability Data Handbook), Lees' *Loss Prevention in Process Industries*, IEC 61078 (RBD methods).

**Golden test acceptance:** dairy_5mw.json balanced pathway with single 2MW HP + electrode boiler → flags single HP gives ~99.0% availability; recommends 2 × 1MW HP + electrode for 99.5%+; quantifies downtime cost differential.

---

## Engine module file layout

```
backend/decarb/engine/
├── __init__.py
├── emission_factors.py           # DEFRA constants, NESO grid intensity, methane upstream
├── load_profiles.py              # 8,760-hour shape templates + production-volume linkage
├── parse.py                      # parse_energy_profile (§1)
├── carbon.py                     # compute_baseline_carbon (§2)
├── dispatch.py                   # simulate_site_dispatch (§3) — the centrepiece
├── hp_cycle.py                   # calculate_hp_cycle ✅ (§4)
├── screen.py                     # screen_technologies (§5)
├── pathway.py                    # optimise_investment_pathway (§6)
├── uncertainty.py                # monte_carlo_uncertainty (§7)
├── pinch.py                      # compute_pinch_analysis (§8) — week 3
├── safety.py                     # compute_safety_constraints (§9) — week 3
├── grid.py                       # assess_grid_connection (§10) — week 3
├── reliability.py                # compute_reliability_availability (§11) — week 3
└── tests/
    ├── test_*.py                 # one per module, against the 3 golden sites
```

---

## Eval harness pattern

For each engine module:
1. Pydantic schema validation on every output
2. Numeric tolerance: ±10% against `_golden_truth` for cardinal numbers, ±25% for ranges (P10/P90)
3. Categorical exact match on shortlists, regulatory flags, warnings codes
4. Edge cases: missing inputs trigger documented warnings, not silent wrong answers
5. Standards-cited lists are non-empty and resolve to documents in the corpus

Run: `cd backend && pytest decarb/engine/tests -v`
A green pytest run gates week 3.

---

## What "done" looks like at end of week 2

- [ ] All 7 v0-scope engine modules implemented (§1, §2, §3, §4 ✅, §5, §6, §7)
- [ ] Pinch + safety + grid + reliability stubs scaffolded for week 3
- [ ] All `test_*.py` green against the 3 golden sites
- [ ] `tools.py` real implementations replace stubs for v0-scope modules
- [ ] `python -m decarb.agent --site-brief tests/sites/dairy_5mw.json` produces sensible end-to-end tool calls; output won't be a polished report yet (that's week 3)
- [ ] Engine total runtime < 90 sec per pathway (1,000 MC × 50 pathways)
- [ ] git history has one commit per module with "what + why" messages
- [ ] Work log shows discipline: no more than 18 hours total across the week
- [ ] **Senior-engineer smell test:** print the JSON output of `simulate_site_dispatch` for the dairy site. If you read it as if you were a Frazer Nash senior thermal engineer, would you sign it off? If not, deepen before week 3.

---

## Engineering depth principles (re-read before every module)

1. **No magic constants.** Every coefficient comes from a cited source.
2. **No silent approximation.** If a sub-calculation can't be done exactly, return a warning and a documented assumption.
3. **Approach temperatures in every HX.** No infinite-area assumptions.
4. **Discharge temperature checks on every compressor.** Refrigerant-specific limits.
5. **Pressure ratio limits on every compressor stage.** Compressor-type-specific.
6. **F-gas / DSEAR / BS EN 378 awareness in every refrigerant decision.**
7. **Half-hourly resolution wherever electricity prices or grid intensity matter.**
8. **Multi-objective wherever there's a trade-off.** Not just NPV.
9. **CVaR / VaR alongside expected value wherever there's risk.**
10. **Standards cited inline, every output.**

If a module doesn't satisfy all 10, it's not week-2-done.
