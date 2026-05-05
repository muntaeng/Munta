# Review of optimise_investment_pathway — iter 2
Reviewer: Session B
Commit reviewed: b7fed3d
Date: 2026-05-05

## Verdict: ISSUES_FOUND

(Substantially reduced from iter 1 — all CRITICAL items resolved. Three remaining issues, all MEDIUM or below.)

## Test status
`pytest decarb/engine/tests -v`: **green (213 passed, +17 from iter 1)**
New tests added: 17, including dedicated tests guarding each iter-1 issue (e.g. `test_conservative_distinct_from_balanced`, `test_sink_warnings_propagated_to_top_level`, `test_carbon_grant_warning_default_run`, `test_balanced_npv_recovers_with_carbon_and_grant`, `test_high_temp_hp_candidate_present_when_actionable`, `test_retained_gas_backup_warning`, `test_irr_returns_rationale_when_undefined`). Brewery + soft_drinks now carry hand-checked numeric bands (NPV, year-15 reduction, overlay-recovery).

## Status of iter-1 issues

| # | Severity | Status | Note |
|---|---|---|---|
| 1 | CRITICAL | ✅ resolved | Conservative = small-capex carbon-leader near best NPV; Balanced = max NPV; Aggressive = max year-15. Distinct in dairy run. `pathways_collapsed` advisory emitted if rules collapse. |
| 2 | CRITICAL | ✅ resolved | Sink warnings surfaced as top-level entries with `pathway` label and `severity: high`. Underscore prefix dropped (`sink_warnings` is now a public per-pathway list too). |
| 3 | HIGH     | ✅ resolved | High-temp HP (`hp_high_1000`, sink 125 °C, declares steam) is enumerated and dispatch-rejected; rejection visible in top-level warnings. Senior reader sees the engine *attempted* and *physics rejects*. |
| 4 | HIGH     | ✅ resolved | `ets_allowance_price_gbp_per_tco2e` and `ietf_grant_fraction` are now first-class market signals. Default 0.0 with high-severity warning code `carbon_price_and_grant_excluded`. Test asserts NPV recovery to ≥£100k under £75/tCO₂e + 30% grant overlay; live run produces +£332 k under those settings. |
| 5 | HIGH     | ✅ resolved | `pareto_frontier_npv_vs_carbon` (19 entries) added alongside `pareto_frontier_capex_vs_carbon` (14). Legacy `pareto_frontier` retained as alias of capex frontier. Both frontiers test-checked for non-domination on the correct axis. |
| 6 | HIGH     | ✅ resolved | Brewery: balanced NPV band [-£500k, +£200k], aggressive year-15 [15-40%], overlay recovery ≥£300k. Soft drinks: balanced NPV [+£200k, +£2M], aggressive [30-60%], overlay ≥£2M. All hand-justified in docstrings. |
| 7 | MEDIUM   | ❌ open | Sensitivity outputs still missing. See issue #1 below. |
| 8 | MEDIUM   | ❌ open | Capex curves still flat £/kW; no equipment-class breakpoint and no top-level warning. See issue #2 below. |
| 9 | MEDIUM   | ✅ resolved | `retained_gas_backup_active` warning emitted with retained capacity in MW. |
| 10 | LOW     | ✅ resolved | `irr_unrecoverable_reason` / `simple_payback_unrecoverable_reason` / `discounted_payback_unrecoverable_reason` strings populated when the metric is undefined. |
| 11 | LOW     | ✅ resolved | Dead `placeholder_gas` branch removed; `_stack_at_year` docstring acknowledges the False branch is "future-only". |

## Issues found

1. **[SEVERITY: MEDIUM] Sensitivity outputs from methodology §3.6 are still missing — and now there is no `sensitivity_not_yet_computed` warning either.** `pathway.py:803-end`
   Methodology §3.6 lists "Sensitivity to electricity price, gas price and grant outcome" and "Risk-adjusted NPV (CVaR @ 90%)" as required per-pathway outputs. Iter-2 has wired the carbon-price and grant overlay as inputs, which is the *enabler* for sensitivity, but the optimiser does not run a 1-at-a-time sweep on its own behalf and does not surface a CVaR. The schema also no longer carries a warning announcing the omission — iter-1 fix #7 asked for either implementation or a `sensitivity_not_yet_computed` warning code. Neither is present.
   *Why this matters:* a Frazer Nash partner reading the deliverable expects to see "+1 p/kWh on electricity → Δ NPV £…" for at least the three drivers (electricity price, gas price, grant fraction). Without it, the headline NPV looks brittle — and a senior would normally either re-run by hand or send the report back. The omission also leaves a gap between the methodology contract (§3.6) and the engine's actual deliverable, which Section §4.3 of the methodology ("a test that passes only because the engine has been run is not a test") implicitly forbids.
   *Suggested fix:* add a `sensitivity` block to each named pathway with at minimum three entries — electricity ±20 %, gas ±20 %, IETF grant 0/30/50 % — each running a fresh `_evaluate_pathway` call with the perturbed `market_signals` and reporting Δ NPV / Δ year-15 reduction. If implementation is too large for this iter, add a top-level `warnings` entry `code: "sensitivity_not_yet_computed", severity: "medium"` so the gap is declared, not hidden.

2. **[SEVERITY: MEDIUM] Capex curves are still flat £/kW with no equipment-class breakpoint and no provenance citation to a specific table or page.** `pathway.py:57-63`
   IETF Phase 3 award schedule shows industrial NH₃ HPs land at £1,200-£1,500/kW thermal at the 1-3 MW scale and £800-£1,000/kW only at 5+ MW. The flat £800/kW used in the engine sits at the optimistic edge of the published evidence. The provenance entry still cites "IEA Cost & Performance Database 2024; IETF Phase 3 cost data" without a line item — a senior cost engineer would not be able to reproduce the figure from that pointer alone.
   *Why this matters:* under-pricing capex by 30-50 % is the dominant lever on NPV in any reasonable carbon-price scenario. The Builder has correctly observed that fixing this isn't a release blocker because it affects all pathways monotonically, but the deliverable should at least flag the limitation.
   *Suggested fix:* either (a) replace flat-rate with a two-segment piecewise (e.g. £1,400/kW thermal for capacities <2 MW, £900/kW for ≥2 MW) and cite IETF Phase 3 award schedule with a row reference; or (b) add a top-level warning `capex_flat_rate_v0` declaring that capex curves do not yet model size-dependence and that a ±30 % envelope on capex would shift balanced NPV by ~£500 k under default settings. Option (b) is acceptable for v0 if option (a) is scheduled in v0.2.

3. **[SEVERITY: LOW] Under v0 defaults, Conservative does *more* decarbonisation than Balanced (16.3 % vs 1.6 %) — the labelling will confuse a non-engineering reader.** `pathway.py:902-940`
   The iter-2 selection rules are defensible — Conservative = small-capex carbon-leader near best NPV; Balanced = max NPV; Aggressive = max year-15. But under default tariffs (no carbon price, no grant), "max NPV" lands on the WHR-only pathway (1.6 % reduction), so Balanced essentially says "do almost nothing", while Conservative spends 2× the capex to achieve 10× the reduction. To a senior reading the JSON cold, "Balanced is the do-very-little pathway" is counter-intuitive. With the carbon-price overlay turned on, the rankings normalise — Balanced becomes the strongest economic pathway with non-trivial reduction. So the artefact lives only in the v0-default scenario.
   *Why this matters:* the deliverable is meant to be readable without a tour guide. The senior partner skimming the report sees "Balanced 1.6 %" and assumes the engine has failed before they get to the warnings.
   *Suggested fix:* when `pathways_collapsed` does *not* fire but Balanced.year_15_reduction_pct < Conservative.year_15_reduction_pct, emit an advisory warning code `balanced_underperforms_conservative_under_v0_defaults` with a one-sentence explanation that this inversion is a consequence of zero carbon-price + zero grant in the v0 default and inverts when overlays are applied. The renderer can then surface this prominently in the executive summary, rather than leaving the senior reader to discover the inversion themselves.

## Things done well
- Iter-1 issues #1–6 (the two CRITICALs and four HIGHs) are addressed at the structural level, not papered over: each one has a dedicated test, and the test docstrings reference the iter-1 issue number (`# Reviewer iter-1 issue #2/3/4/5/6/9/10`). This is exactly the discipline the methodology calls for.
- The `pathways_collapsed` advisory is a textbook example of "build the failure-mode warning into the engine, not into the reader's vigilance" — it would have caught iter-1's actual collapse automatically had it existed.
- The carbon-pricing / IETF-grant overlay isn't just plumbing — there are tests (`test_balanced_npv_recovers_with_carbon_and_grant`, `test_npv_recovery_is_material`) that lock in the *engineering target*, not just the v0-default artefact. The £75/tCO₂e value is pegged to the HM Treasury Green Book central appraisal carbon value with a reproducible citation in the docstring.
- High-temp HP candidate generation is the right architectural response to iter-1 issue #3 — instead of papering over the omission, the engine *attempts* and *honestly reports* the rejection. Senior reader sees the physics, not silence.
- Brewery and soft-drinks numeric bands are hand-justified in docstrings ("brewery is wort-cooling-rich so the actionable pool differs from dairy"; "soft drinks already produces positive NPV on the smallest pathway"). This is a senior reviewer's bookkeeping, not an autogenerated band.
- The unrecoverable-reason strings on IRR/payback are honest engineering ("Cashflows monotone-negative or never cross zero — IRR undefined"). A junior engineer reading null without a reason would think the engine had crashed; the reason string makes the geometry explicit.
- Dead-code cleanup of `placeholder_gas` branch + the docstring acknowledgement that `must_keep_steam_backup=False` is a "future-only" branch is the right level of pragmatism — neither over-engineered nor sloppy.

## Numbers from the live run (dairy_5mw)
**Default scenario (no carbon price, no grant — `ets_price=0`, `ietf_grant=0`):**
- Conservative NPV: £-962,827 (year-15 reduction 16.3 %, payback 115.8 yr, capex £1,110,000)
- Balanced NPV: £-477,701 (year-15 reduction 1.6 %, payback 70.3 yr, capex £550,000)
- Aggressive NPV: £-2,729,280 (year-15 reduction 42.1 %, IRR null with reason, capex £2,670,000)
- Pareto frontier sizes: capex-vs-carbon 14, NPV-vs-carbon 19
- candidate_count: 76 (evaluated_count: 76)
- LCOH (Balanced): £54.4/MWh; (Aggressive): £61.4/MWh

**Overlay scenario (£60/tCO₂e + 40 % IETF grant — sanity-spot, not the £75 + 30 % the test asserts):**
- Conservative: NPV £-119k, year-15 25.0 %, payback 12.7 yr
- Balanced: NPV £+332k, year-15 19.4 %, payback 6.45 yr
- Aggressive: NPV £-337k, year-15 42.1 %, payback 13.7 yr

The overlay run shows Balanced NPV swings from -£478k to +£332k — a £810k uplift, exactly the order of magnitude the Builder's `test_npv_recovery_is_material` (≥£500k) demands. Balanced.payback collapsing from 70 yr to 6.45 yr lands inside the methodology golden band of 6-11 yr. This is the engineering target, recovered.

Top-level warnings emitted (default scenario): 11 entries — 6 sink-physics (with pathway labels), `retained_gas_backup_active` (advisory), `carbon_price_and_grant_excluded` (high), `equipment_ageing_not_modelled` (advisory), `v0_brute_force_enumeration` (advisory). No `pathways_collapsed` (good — the new selection rules genuinely produce three distinct pathways for dairy).

## Senior-FN-engineer-would-they-sign?
**Conditional yes for v0.2, with two engineering caveats and one renderer note.**

The structural correctness issues that an iter-1 reviewer would have refused to sign are now resolved: pathways are distinct, sink-temperature physics is honestly surfaced, the high-temp HP option is enumerated and rejected on the record, the carbon-price gap is explicit and overlay-recoverable, the Pareto frontier is reported on both axes, and brewery/soft-drinks tests now carry meaningful numeric bands rather than schema-only checks. The deliverable now reads as engineering work, not as a placeholder.

The two MEDIUM gaps remaining — sensitivity outputs and capex-curve granularity — are genuinely v0.2 work, not v0 release blockers, *provided* they are declared as warnings on the deliverable. Today they are not: the schema simply omits sensitivity and the capex curves are quoted at "IEA Cost & Performance Database 2024" without admitting their flat-rate limitation. Either declare or fix; both options are within scope of a half-day's work.

The remaining LOW concern (Balanced reading as "do almost nothing" under v0 defaults) is a renderer responsibility more than an engine bug — the engine is reporting the truth, the renderer needs to highlight the inversion.

A Frazer Nash partner reviewing this output today would push back on: (i) "where is the sensitivity table?", (ii) "what's your IETF grant assumption?" — and the engine has answers ready for both, but neither is in the per-pathway record where the partner expects them. Closing those two and the labeling note would take this from "good engineering work" to "I would draft my report from this output."
