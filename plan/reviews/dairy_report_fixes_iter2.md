## Verdict: ISSUES_FOUND
## Iteration: 2 of 3

Reviewed against `backend/decarb/runs/GOLDEN_DAIRY_5MW_20260505T172254Z.md` and code at `23b353a`. Independently verified all checklist items against report and code; did not rely on `plan/reviews/builder_iter1_summary.md`.

Engine regression: `220 passed in 37.22s` (was 216 — +4 new tests for issues A/B/D/E). No regressions, no new HIGH-severity warnings.

### What passes (8 of 10)

- **[A] PASS.** §1: "Scope 2 rises from 1,900 to 2,467" — verb and number now agree. Re-derived from §4.4: HP_output 6,271 MWh / COP 3.09 + EB_output 3,705 / 0.99 ≈ 5,772 MWh new electricity × 0.135 kgCO₂e/kWh (NESO 2027 — implied by §5.1 row: 1,688 / 12.5 GWh) = +779 tCO₂e. Year-2027 baseline Scope 2 = 1,688 + 779 ≈ 2,467 ✓ matches §5.3. Scope 1 reconciles too: gas displaced ≈ 7.84 GWh (boiler η=0.85) × 0.18293 ≈ 1,434 tCO₂e saved → 6,951 − 1,434 = 5,517 ≈ 5,520 ✓. Total 5,520 + 2,467 = 7,987 ≈ 7,986 ✓. Test `test_dispatch_scope2_increases_with_electrification` added.
- **[B] PASS.** `screen.py` excludes `waste_heat_recovery_chiller_to_HW` on `thermodynamic_feasibility` axis (sink 70°C vs HW 85°C + 5K LMTD) — visible in §3.2. No pathway in §4.1 carries `whr_500`. §4.3 no longer emits the per-pathway `hp_inactive_no_compatible_end_use` warnings for whr_500. Test `test_no_pathway_carries_a_temperature_inactive_tech` added.
- **[C] PASS.** §4.4 retitled "year-1 of the recommended Balanced pathway, calendar 2027"; assets `hp_mid_1000 + eb_2000 + tes_8000` match Balanced's §4.1 action sequence. §1 narrative and §5.3 column header both label Balanced explicitly.
- **[D] PASS.** Balanced now includes `eb_2000` alongside TES, so the original concern is structurally resolved. Test `test_no_tes_without_eb_in_same_stack` added (asserts no named pathway carries `thermal_storage` without `electrode_boiler` in the same stack).
- **[E] PASS.** Recomputed with the engine's actual O&M fractions (visible in `test_pathway.py:475`: thermal_storage = 0.010, not 0.015 as I assumed in iter-1):
  - Conservative: 800k×0.025 + 600k×0.015 + 160k×0.010 = £30,600 ✓ matches.
  - Balanced: 800k×0.025 + 300k×0.015 + 320k×0.010 = £27,700 ✓ matches.
  - Aggressive: 1,600k×0.025 + 600k×0.015 + 320k×0.010 = £52,200 ✓ matches.
  
  Test `test_annual_opex_matches_active_capex_fractions` added with strict `reported >= expected − 1.0` assertion.
- **[H] PASS.** §8.1 now lists 8 warnings (was empty).
- **[I] PASS.** §3.1 reads as prose with single full-stops at the joins; "× dispatch" typo removed at §4 line 134; §1 line 22 now references "longlist of 16".
- **[J] PASS.** §4.1 now carries the "HP capacity rationale" paragraph distinguishing all-end-uses 1,287 kW average from hot-water sub-demand. §9 decision #1 surfaces the up-size question as a senior decision.

### Issues remaining

- **[F] FAIL.** §4.3 line 247 still emits `[advisory/balanced_underperforms_conservative_under_v0_defaults]` AND Balanced (37.2% reduction, NPV £82k) is *not* the highest-reduction-positive-NPV pathway in the §4.2 NPV frontier — rank 3 (NPV £36,773, capex £1,554k, **47.5%** reduction) dominates Balanced on carbon at still-positive NPV. The checklist requires the advisory removed OR the selection rule fixed. The advisory text now reads "the Balanced selection rule is unconditionally max-NPV ... a senior reader should treat Conservative as the higher-ambition pick" — i.e. the Builder is *declaring* the inversion rather than *fixing* it. That is acceptable on iter-3 escalation per the protocol, but on iter-2 the Builder should attempt the fix first.

- **[G+provenance] PARTIAL FAIL.** §9 form is correct (4 decisions, all in "If <alt>, <impact> changes from X to Y" shape). But the X/Y values in three of the four decisions are *hardcoded literals* in `render/templates/v0_pathway_report.md.j2:458–460` that contradict the live §4.1 output:

  | Decision | §9 hardcoded | §4.1 live | Provenance |
  |---|---|---|---|
  | #1 Aggressive year-15 reduction | **42.1%** | **50.9%** | none |
  | #1 Aggressive NPV | £-260k | £-127,005 | none |
  | #2 Conservative year-15 reduction | **25.0%** | **38.7%** | none |
  | #2 Conservative HP-only capex collapse "£950k → £800k" | — | Conservative gross capex is £1,560k not £950k | none |
  | #3 Aggressive baseline NPV | £-260k | £-127,005 | none |

  These are stale numbers from iter-0/iter-1 pathway runs baked into the prose. They violate the report's own claim ("every numeric output above is produced by a deterministic engine module"). Provenance Appendix A has no entry for any of these claims. Decisions #1, #2, #3 must either pull values from live `pathways['aggressive']` / `pathways['conservative']` or be neutered to qualitative language.

### Issues newly introduced
- §9 decisions hardcoded literals (logged under G above). The §9 block shipped iter-1 introduced these — they did not exist in the iter-0 template. Net new defect.

### Recommended next iteration prompt for Builder

Two items, in priority order. If you genuinely cannot land item 1 without re-architecting the Balanced selection rule, declare it as a warning per the iter-3 escalation protocol and move on — but make a real attempt first.

1. **F (try a fix; declare on iter-3 if not landable).** Add a `pathway_selection_rule` parameter to `optimise_investment_pathway`. Default keeps current `max_npv` for backwards compatibility; add a `max_reduction_positive_npv` rule that returns the highest year-15 reduction among NPV>0 candidates. Have the dairy site (and the report renderer) request `max_reduction_positive_npv` for the Balanced slot. Re-run: Balanced should land on the £1,554k / 47.5%-reduction / NPV £36,773 pathway. Drop the `balanced_underperforms_conservative_under_v0_defaults` advisory once the rule is wired. If you hit a blocker (e.g. Balanced flips to a stack that breaks another invariant test), declare the inversion as a warning with explicit text "v0 selection rule is `max_npv` by design; Balanced may underperform Conservative on reduction — confirmed v0 limitation, fix scheduled for v0.2 alongside `pathway_selection_rule` parameterisation".

2. **G+provenance.** In `v0_pathway_report.md.j2:458–460`, replace the hardcoded literals with template expressions reading from `_agg = pathways.aggressive` and `_cons = pathways.conservative` (mirroring `_bal` already in scope at line 449). Specifically:
   - Decision #1: `to **{{ _agg.year_15_reduction_pct }}%** (Aggressive) at NPV £{{ _agg.npv_gbp|fmt_int }} vs Balanced £{{ _bal.npv_gbp|fmt_int }}.`
   - Decision #2: `year-15 reduction falls from **{{ _cons.year_15_reduction_pct }}%** to ~16%` (or compute the HP-only counterfactual properly — but at minimum the from-value must be live).
   - Decision #3: `shifting Aggressive NPV from £{{ _agg.npv_gbp|fmt_int }} to ~£{{ (_agg.npv_gbp - 150_000)|fmt_int }}` (or similar — the £150k interconnect adder is fine to hardcode, the baseline NPV is not).
   - Add a one-line provenance entry `optimise_investment_pathway / §9 senior-decision X-to-Y rendering` so Appendix A covers it.

After both items, regenerate the dairy report (`python -m decarb.runners.golden_dairy_5mw` or `backend/scripts/regenerate_dairy_report.py`) and re-run `pytest decarb/engine/tests` — must remain ≥220 passing.
