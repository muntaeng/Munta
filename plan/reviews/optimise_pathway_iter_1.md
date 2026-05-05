# Review of optimise_investment_pathway — iter 1
Reviewer: Session B
Commit reviewed: 7886468
Date: 2026-05-05

## Verdict: ISSUES_FOUND

## Test status
`pytest decarb/engine/tests -v`: **green (196 passed)**
New tests added: 23 in `test_pathway.py` (TestDairyPathway, TestBreweryPathway, TestSoftDrinksPathway).

## Issues found

1. **[SEVERITY: CRITICAL] Conservative and Balanced pathways are byte-identical for dairy_5mw.** `pathway.py:760-767`
   The named-pathway selection rules — Conservative = `min(capex with year_15>0)` and Balanced = `max(npv)` — collapse onto the same candidate (WHR-500 + HP-mid 500). Both report NPV £-477,701, year-15 reduction 1.6%, simple payback 70.3 yr, identical actions. The methodology §3.6 promises *three distinct named scenarios*; the deliverable currently gives the senior reader two duplicates and one outlier. This is a degenerate output, not a bug fixable by re-tuning thresholds.
   *Why this matters:* a Frazer Nash partner reading this report sees "Conservative and Balanced both deliver 1.6% decarbonisation by year 15" and concludes the engine has produced no decision. The whole point of the three-pathway frame is to triangulate the decision space.
   *Suggested fix:* Conservative and Balanced must be selected from disjoint subsets. E.g. Conservative = max year-15 reduction subject to NPV ≥ best-NPV − Δ AND capex ≤ 25% of budget; Balanced = max NPV; Aggressive = max year-15 reduction subject to capex ≤ budget. Add a test asserting `actions(conservative) ≠ actions(balanced)` for all three sites.

2. **[SEVERITY: CRITICAL] Sink-temperature warnings are silently demoted to a private field.** `pathway.py:457-498, 598`
   When dispatch returns `hp_sink_too_cold_for_end_use` or `hp_inactive_no_compatible_end_use`, the codes are stashed in `_sink_warning_codes` (leading underscore convention = "internal"). They are *not* propagated to the top-level `warnings` list. The dairy run shows every pathway carries `['hp_inactive_no_compatible_end_use', 'hp_sink_too_cold_for_end_use']` — meaning the HP capacity in those pathways is **physically unable to deliver the duty for which it was provisioned**, but the user-facing JSON does not raise this. The methodology's non-negotiable principle (§2.2.ii) is "every numeric output traces to a function call" and §2.2 (general) is "no silent approximation" — burying the sink-warning under an underscore is precisely the silent approximation pattern the methodology forbids.
   *Why this matters:* a senior engineer skimming the deliverable will not see that "Aggressive: install 1.5 MW HP year 0" is contingent on a physics check that the engine has already failed.
   *Suggested fix:* propagate every distinct `hp_*` warning observed during pathway evaluation into the top-level `warnings` list with `severity: "high"` and the affected pathway name. Drop the underscore prefix on the per-pathway record.

3. **[SEVERITY: HIGH] HP configs are hard-coded to serve `hot_water` only — never steam.** `pathway.py:243-254, 281-295`
   `_hp_config_mid_temp` returns `serves_end_uses=["hot_water"]` with `sink_temp_c=90.0`. The dairy site's dominant load is **steam (≈85% of 38 GWh gas)**; hot_water is a small fraction. Therefore no HP candidate in the enumeration can displace the dominant emissions. Only the electrode boiler can, and it does so at electricity:gas ratio ≈ 4:1, which is why every pathway is NPV-negative. The B0 sink-temperature physics fix is correct as a *guard*, but the *response* in pathway.py is to give up on HP-for-steam entirely — instead of generating a high-temperature HP option (R744 transcritical or NH3 cascade) which the methodology explicitly maps to roadmap v0.2. The screening shortlist for dairy includes `industrial_heat_pump_high_temp` — the optimiser ignores it.
   *Why this matters:* the engine answers "can heat pumps electrify dairy steam" with "no" by virtue of *not generating a candidate that even tries*. A senior reviewing the report cannot tell the difference between "we tried high-temp HP and the physics rejects it" and "we never built a high-temp HP candidate."
   *Suggested fix:* add `_hp_config_high_temp(capacity_kw)` returning `sink_temp_c=125.0`, `serves_end_uses=["steam","hot_water"]`, refrigerant cascade NH3+R744, `requires_grid_decision=True`. Include it in `_generate_candidates` whenever `industrial_heat_pump_high_temp` is in the actionable pool. If the dispatch B0 guard then rejects it (because a 125°C sink can't supply 175°C steam), the warning will surface honestly in the top-level `warnings` per fix #2 above — and the senior engineer will see *why* steam can't be HP-electrified, instead of a silent omission.

4. **[SEVERITY: HIGH] Carbon price, ETS allowance cost, and IETF grant uplift are absent from cashflows.** `pathway.py:510-516`
   Cashflow = `savings - capex - opex`, where savings is energy-cost only. UK ETS allowance liability (mandatory for sites >20 MW combustion, allowance currently ~£40-60/tCO2e), CCL on retained gas use, and IETF grant offset (typically 30-50% of HP capex for award-winning bids) are *all* declared in scope by methodology §3.2 / §3.6. None enter NPV. The Builder's test docstring (`test_pathway.py:6-28`) accepts negative NPV as "honest physics" and relaxes the golden NPV band from £1.2-3.5 M to -£800 k …+£200 k — but the negative NPV is **not** physics; it's the absence of a carbon price. Locking the test band at the artefact rather than the engineering target is a deferred correctness gap dressed up as physical realism.
   *Why this matters:* the senior-FN reader is presented with a recommendation that says "every electrification pathway destroys value" — which is the opposite of what every published IETF case study, every CCC scenario, and every BS EN 16247-1 retrofit appraisal of UK industrial decarbonisation produces. The number is wrong because the model is incomplete, not because reality is bleak.
   *Suggested fix:* (i) add an `ets_allowance_price_gbp_per_tco2e` and `ietf_grant_fraction` to `market_signals`, default both to 0.0 in v0 with a top-level warning code `carbon_price_and_grant_excluded` explaining what the user must overlay manually; (ii) re-tighten `test_balanced_npv_in_honest_band` to assert that **with carbon price ≥ £40/tCO2e** the balanced NPV recovers to the £1.2-3.5 M golden band, so the test guards the engineering target rather than the partial-implementation artefact.

5. **[SEVERITY: HIGH] Pareto frontier is on (capex, abated) not (NPV, abated).** `pathway.py:607-628, test_pathway.py:190-213`
   Methodology §3.6 specifies "Pareto frontier across the cost-versus-carbon trade-off". "Cost" in a 15-year techno-economic appraisal means lifetime cost (NPV or PV-cost), not capex alone. A pathway with low capex but ruinous lifetime opex would dominate one with higher capex but lower opex — i.e. the current frontier ranks by the wrong metric. The dominance test in `test_pareto_frontier_is_non_dominated` enforces the same wrong axis, so the bad ranking is also test-locked.
   *Why this matters:* "capex-Pareto" is the lay client's frontier; "NPV-Pareto" is the senior engineer's frontier. The senior-FN partner expects the latter.
   *Suggested fix:* `_pareto_frontier` should accept a `cost_axis` arg and report **two frontiers** in the output — `pareto_frontier_capex_vs_carbon` and `pareto_frontier_npv_vs_carbon`. Update the dominance test to operate on (NPV, abated). Document the choice in `method_reference`.

6. **[SEVERITY: HIGH] Brewery + soft_drinks tests assert no numeric bounds.** `test_pathway.py:261-302`
   Both `TestBreweryPathway` and `TestSoftDrinksPathway` test only schema-shape, ≥1-Pareto-entry, no-NaN, capex-within-budget. None of the methodology §4.3 golden bands (NPV, payback, year-15 reduction) are checked. A regression that drives brewery NPV from -£500k to -£50M would ship green. The methodology §4.3 explicitly rejects this: "A test that passes only because the engine has been run is not a test."
   *Why this matters:* the methodology promises a three-site golden regime as the primary release gate; one site is gated, two are not.
   *Suggested fix:* author hand-checked numeric bands for brewery_8mw and soft_drinks_12mw (NPV, year-15 reduction, simple payback) and assert them with the same `_DAIRY_GOLDEN_TARGETS`-style decoration explaining the relationship between target and current honest band.

7. **[SEVERITY: MEDIUM] Sensitivity outputs promised by methodology §3.6 are absent.** `pathway.py:803-880`
   §3.6 lists "Sensitivity to electricity price, gas price and grant outcome" as a per-pathway required output. Nothing in the returned schema. Same for CVaR-90% (risk-adjusted NPV).
   *Suggested fix:* either implement a 1-at-a-time sensitivity sweep on three inputs (electricity ±20%, gas ±20%, grant 0/30/50%) per pathway returning Δ NPV, or downgrade the methodology section to "ROADMAP v0.2" with an explicit warning code `sensitivity_not_yet_computed`.

8. **[SEVERITY: MEDIUM] Capex curves use flat £/kW with no equipment-size breakpoint and no learning rate.** `pathway.py:57-63`
   IETF Phase 3 award data shows industrial NH3 HPs land at £1,200-£1,500/kW thermal at the 1-3 MW scale; £800/kW is at the optimistic end and only realistic for 5+ MW units. No source-document line item is given inside the provenance — just "IEA Cost & Performance Database 2024" as a register entry. A senior FN cost engineer would want a single-line citation pointing to the table or page used.
   *Suggested fix:* either replace flat-rate with two-segment piecewise (e.g. £1,400/kW <2 MW, £900/kW ≥2 MW) and cite IETF Phase 3 award schedule, or add a top-level warning `capex_flat_rate_v0` flagging the coarse model.

9. **[SEVERITY: MEDIUM] Retained gas backup constraint isn't disclosed in `warnings`.** `pathway.py:135-142`
   Every pathway carries a `must_keep_steam_backup` retained gas boiler at the site's existing capacity. This is a hard structural cap on year-15 reduction (steam peaks always go through gas) and it dominates the 42% Aggressive ceiling. It is not surfaced in the output's `warnings` list, only implicit in the stack.
   *Suggested fix:* emit `warnings` entry `code: "retained_gas_backup_active"`, `severity: "advisory"`, with the retained capacity in MW.

10. **[SEVERITY: LOW] Aggressive returns IRR=None and simple_payback=None.** `pathway.py:582-587`
    Correct behaviour (Brent's method has no sign change in cashflows that never go positive), but a senior reader skims `"irr": null` as "didn't compute" rather than "no positive-NPV recovery point." A short rationale string would be more honest than `None`.
    *Suggested fix:* return `{"value": null, "reason": "cashflows monotone-negative — IRR undefined"}` for irr and simple_payback when the cashflow geometry forecloses recovery.

11. **[SEVERITY: LOW] `_stack_at_year` `placeholder_gas` branch is unreachable.** `pathway.py:143-152`
    The `elif not stack` branch only fires if `must_keep_steam_backup=False` AND no actions installed AND year 0 — which never co-occurs in any of the three golden sites. Dead code adds review noise.
    *Suggested fix:* delete or assert.

## Things done well
- Honest commit message and module docstring; the v0.1 dispatch artefact is acknowledged in `test_pathway.py:6-28`, not hidden. This is real engineering candour.
- Dispatch caching (`_evaluate_pathway:478-488`, `_stack_signature:459-471`) cuts the run from ~100s to <30s without changing semantics — clean separation of optimisation from re-computation.
- `method_reference` is honest about being brute-force enumeration and names what is deferred to v0.2.
- Provenance list (7 entries) names each calculation, method, and source, including the scipy.brentq call for IRR.
- B0 sink-temperature constraint is enforced in dispatch and respected by pathway (per intent), not bypassed.
- `requires_grid_decision` flag is propagated from screening through pathway, surfaced per pathway. Senior reviewer can see the DNO dependency.
- Capex budget enforced as a hard pre-filter, not a post-rank constraint — correctly excludes infeasible candidates before evaluation.
- LCOH formula is the textbook PV(cost) / PV(thermal) — matches BS EN 16247-1 Annex C.
- Warnings list explicitly flags equipment-ageing-not-modelled and v0-brute-force; honest about the v0.2 commitments.

## Numbers from the live run (dairy_5mw)
- Conservative NPV: £-477,701 (year-15 reduction 1.6 %, payback 70.3 yr)
- Balanced NPV: £-477,701 (identical to Conservative — see issue #1)
- Aggressive NPV: £-2,729,280 (IRR null, payback null)
- Pareto frontier size: 14
- Year-15 reduction (Balanced): 1.6 %
- Year-15 reduction (Aggressive): 42.1 %
- IRR (Balanced): -16.47 %
- LCOH (Balanced): £54.4 /MWh
- LCOH (Aggressive): £61.4 /MWh
- candidate_count: ~30 survivors after capex filter; evaluated_count = same
- All pathways carry warnings `hp_inactive_no_compatible_end_use` + `hp_sink_too_cold_for_end_use` in the buried `_sink_warning_codes` field.

## Senior-FN-engineer-would-they-sign?
**No.** The output reports two of three named pathways as identical and the third with -£2.7M NPV and 42% reduction — i.e. one viable answer dressed as three. Negative NPV across all pathways is a direct consequence of (a) HP candidates restricted to a 5-15% slice of demand because high-temp HPs aren't generated, (b) carbon price / IETF grant absent from cashflow, and (c) electrode boiler bearing the entire steam-electrification load at unfavourable energy-cost arbitrage. Each of these is a known v0 limitation but the engine surfaces none of them in the user-facing `warnings` — the sink-temperature flags are demoted to a private underscore field, and the carbon-price absence is invisible. A senior FN partner would read the dairy report and conclude either (i) electrification of UK dairy is a value-destroying exercise, or (ii) the model is incomplete in ways the methodology forbids the orchestration layer from hiding. They would send it back. The fix path is not academic: surface the warnings, generate a high-temp HP candidate, decouple Conservative from Balanced, add a carbon-price overlay even if defaulted to zero, and re-tighten the dairy golden band against the engineering target rather than the implementation artefact.
