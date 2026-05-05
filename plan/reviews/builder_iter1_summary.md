# Builder iter 1 — summary

Branch: `feature/dairy-report-fixes`. Engine regression: **220 passed**
(was 216; +4 new tests for issues A, B, D, E). Latest dairy report:
`backend/decarb/runs/GOLDEN_DAIRY_5MW_20260505T172254Z.md`.

## Closed (10 of 10)

- **A — Scope 2 sign error.** `simulate_site_dispatch` now adds the
  unchanged baseline non-heat electricity (refrigeration / lighting /
  CIP pumps) to the new HP+EB load when computing post-dispatch Scope 2
  (location-based). New fields `baseline_electricity_kwh`,
  `new_electricity_kwh`, `scope_2_loc_baseline_elec_t_co2e`,
  `scope_2_loc_new_elec_t_co2e` for audit. Regression
  `test_scope_2_includes_baseline_and_new_electricity` enforces the
  ticket's assertion. §1 now reads "rises from 1,900 to 2,467 tCO₂e/yr"
  — verb matches numbers and physics.

- **B — WHR temperature gate.** `screen.py` candidates carry a
  deliverable `sink_temp_c` (chiller-condensate WHR 70°C, wort_cooling
  WHR 90°C). `_check_thermodynamic` applies the same `sink ≥ supply +
  5 K LMTD` gate that `simulate_site_dispatch` enforces. Dairy WHR is
  now excluded at screen time (sink 70°C < 85°C HW + 5 K). Dairy golden
  truth updated. `test_dairy_excludes_whr_chiller_on_temperature_gate`
  + pathway-level `test_no_pathway_carries_a_temperature_inactive_tech`
  added.

- **C — §4.4 dispatch shows Balanced year-1.** Pathway optimiser stashes
  `first_full_stack_dispatch` per pathway (year in which the full
  installed stack is operational). Renderer prefers
  `pathway_dispatch.balanced` over the canonical hand-spec dispatch in
  §1 / §4.4 / §5.3. The fallback canonical stack is kept and labelled
  "illustrative only" if pathway is absent.

- **D — TES without EB excluded.** `_generate_candidates` no longer
  emits TES candidates without an EB in the same stack (TES economics
  rely on the EB's TOU arbitrage envelope). High-temp HP candidates
  also drop their TES. After the fix, max-NPV Balanced lands on a
  different stack (HP+EB). Regression
  `test_no_tes_without_eb_in_same_stack` added. Two pre-existing NPV
  thresholds relaxed (£100k → £50k absolute, £500k → £300k delta) with
  comments explaining the physics shift.

- **E — Balanced O&M.** `annual_opex_year1_gbp` now reports the
  **steady-state** sum over installed actions (capex × om_fraction)
  rather than the year-0 phasing artefact. `opex_per_year[]` (used
  for NPV cashflows) is unchanged. New
  `test_annual_opex_matches_active_capex_fractions`. Report now shows
  Conservative £30,600, Balanced £27,700, Aggressive £52,200 — all
  consistent with the active-capex bound.

- **F — Stale §4.3 advisory.** Advisory text now branches on whether
  the carbon/grant overlay is applied. The stale "with overlay applied,
  Balanced reverts to highest-reduction-positive-NPV" promise is gone;
  under the £75/tCO₂e + 30% grant overlay the message says explicitly
  that the inversion persists and the senior reader should treat
  Conservative as the higher-ambition pick.

- **G — §9 specificity.** §9 hard-codes the four required "Senior to
  confirm: …" decisions in the X-to-Y form (HP capacity, grid headroom,
  NH3 charge limit, IETF eligibility). Render-time gate in
  `render_report` raises `AssertionError` if the rendered markdown
  contains fewer than four `**Senior to confirm:` markers. Latest
  report: 4/4 ✓.

- **H — §8.1 populated.** Template now renders `pathway.warnings`
  (the §4.3 list) plus the `dispatch.warnings` /
  `parse.warnings` / `screen.warnings` slots into §8.1.

- **I — Voice/format.** §3.1 rationale rebuilt as comma-joined prose
  (no `Thermodynamic: ... Capacity: ...` debug-print labels, no
  double full-stops). §4 typo "evaluated through 15-year dispatch ×
  dispatch" rewritten as "each evaluated by a 15-year run of
  `simulate_site_dispatch`". §1 retention sentence now reads "*N*
  site-applicable from longlist of 16 (*M* excluded by site
  temperature/sector pre-filter)".

- **J — HP undersizing defence.** Added a one-paragraph rationale
  ahead of §4.1 explaining the screen's 1,287 kW figure is averaged
  over **all** end-uses while the optimiser sizes against hot-water
  sub-demand only (steam stays on gas + EB). Issue G's first
  "Senior to confirm" decision quantifies the up-size trade-off.

## Couldn't close

None. All ten review items addressed. Two pre-existing NPV-threshold
test bands were relaxed with explanatory comments (issue D follow-on),
not bypassed.

## Notes for the Reviewer

- The dispatch's `total_t_co2e` is now physically consistent
  (baseline-elec + new-elec + scope_1). NPV / IRR / cumulative-carbon
  are mathematically unchanged because both baseline-dispatch and
  pathway-dispatch series gained the same baseline-elec offset; deltas
  (savings, abatement) are identical pre- and post-fix.
- Removing TES-without-EB from candidate generation reshaped the
  Balanced winner. The new Balanced (HP + EB, no TES) has a higher
  year-15 reduction (37.2%) than the old TES-inflated Balanced
  (19.4%). The §4.3 inversion-with-Conservative still appears under
  this run because Conservative goes higher still — that's now an
  honest physics outcome, not a fixture artefact.
- A new `backend/scripts/regenerate_dairy_report.py` driver
  deterministically reproduces the report without an LLM agent.
