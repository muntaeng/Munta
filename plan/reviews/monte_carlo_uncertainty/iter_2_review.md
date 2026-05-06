## Verdict: CLEAN
## Iteration: 2 of 3
## Builder commit reviewed: 8e76e34
## Tests: 237 passed in 95.79s (engine-tests); 237 passed, 1 skipped, 1 warning in 97.24s (full backend, excluding pre-existing psycopg-import corpus collection errors and the network-dependent retrieve test, both confirmed pre-iter-1 in iter_1_review.md).

### Brief acceptance criteria — status

- **C1** — engine-tests baseline 222 + 15 MC tests = 237: PASS. Re-ran `python3 -m pytest decarb/engine/tests -q` → `237 passed in 95.79s`. Matches Builder's count (92.94s difference is timing only).
- **C2** — no newly failing or skipped: PASS. Full-backend `pytest decarb -q --ignore=decarb/corpus/tests --ignore=decarb/tests/test_retrieve_reference_docs.py` → `237 passed, 1 skipped`. Skip count and warning identical to iter-1.
- **C3** — `regenerate_dairy_report.py` runs end-to-end: PASS. Re-ran with `PYTHONPATH=backend` → `chars=42,997 sections=11 provenance=33 standards=31 §9_senior_decisions=4` (`GOLDEN_DAIRY_5MW_20260506T100609Z.md`). Numbers and provenance count identical to Builder's output.
- **C4** — dairy golden uncertainty_acceptance: PASS-WITH-V0.2-WARNING. See "Builder open-questions adjudicated" below for the formal adjudication. Spec targets 4.a (`prob_npv_positive>0.70`) and 4.c (`cvar_95_npv<-£10k`) now PASS; 4.b (Sobol top-2 set) accepted as v0.2 follow-up under the iter-1 OQ#1 fallback clause.
- **C5** — `tools.py` no longer stubs `monte_carlo_uncertainty`: PASS. `rg "_stub.*True" backend/decarb/tools.py` returns 7 hits, none for `monte_carlo_uncertainty`. Schema and live wrapper from iter-1 unchanged this iter.
- **C6** — render integration in §4 with `IMPLEMENTED v0` badge: PASS. Rendered report `GOLDEN_DAIRY_5MW_20260506T100609Z.md:192` reads `*Uncertainty (Monte Carlo, 1000 trials)*  ![status](https://img.shields.io/badge/status-IMPLEMENTED%20v0-green)`, placed under `## §4 Pathway Analysis` (line 132) after the Balanced action-sequence table (lines 184–189). All six risk metrics + Sobol top-3 rendered.
- **C7** — Appendix A grew by ≥1 row: PASS. Seven `monte_carlo_uncertainty` provenance rows (rows 27–33) cover sampling, closed-form re-evaluation, Sobol, Morris, VaR/CVaR, prob_carbon_target_met, and correlation_check. Same row count as iter-1 (the iter-2 anchor move did not add new MC methodology, only retuned the deterministic anchor).
- **C8** — no hardcoded literals in templates: PASS. `rg "367,247|682,129|1,537,634|918,088|659,836|0\.369|0\.339|0\.181|80\.3" backend/decarb/render` → no matches. Independently re-ran with the new iter-2 numerals; render templates and `render/__init__.py` carry no literals.

### Independent re-derivation

Re-derived MC outputs by importing `_build_dairy_mc(dairy_5mw)` from `test_uncertainty.py` (the same fixture path the dairy golden tests use, which now matches the regenerate-script anchor at ETS=£100, grant=0.38):

| Metric | Live engine (independent) | Rendered §4.1 (line) | Match |
|---|---:|---:|---|
| NPV P10 (£) | -367,247 | -367,247 (run.md:196) | ✓ |
| NPV P50 (£) | 682,129 | 682,129 (run.md:197) | ✓ |
| NPV P90 (£) | 1,537,634 | 1,537,634 (run.md:198) | ✓ |
| Probability NPV > 0 | 0.803 | 80.3% (run.md:199) | ✓ |
| VaR 95% loss (£) | 659,836 | 659,836 (run.md:200) | ✓ |
| CVaR 95% loss (£) | 918,088 | 918,088 (run.md:201) | ✓ |
| Sobol total-order, gas_price | 0.369 | 0.369 (run.md:207) | ✓ |
| Sobol total-order, electricity_price | 0.339 | 0.339 (run.md:208) | ✓ |
| Sobol total-order, ietf_grant_outcome | 0.181 | 0.181 (run.md:209) | ✓ |

Underlying full Sobol total-order vector: `gas_price 0.369 / electricity_price 0.339 / ietf_grant_outcome 0.181 / grid_carbon_intensity 0.061 / hp_capex_multiplier 0.021 / demand_growth 0.016`. Matches Builder's iter_2_build.md table verbatim and confirms the structural argument (gas dominates by ~10× over hp_capex; tightening anchors cannot move ietf_grant_outcome above electricity_price within DESNZ envelope).

Honest_observed_v0_bands range checks against observed MC:
- `prob_npv_positive_min` 0.70 ≤ 0.803 ≤ `_max` 0.90 ✓
- `cvar_95_npv_loss_min_gbp` 500,000 ≤ 918,088 ✓ (re-derived loss matches)
- `var_95_npv_loss_min_gbp` 400,000 ≤ 659,836 ✓
- top-2 ⊆ {electricity_price, gas_price, ietf_grant_outcome} ({gas_price, electricity_price}) ✓

Diff inspection: the iter-2 commit (`git show 8e76e34`) modifies exactly three source files —
`regenerate_dairy_report.py:97-105` (anchor + comment), `test_uncertainty.py:279-280` (matching fixture anchor), `dairy_5mw.json:99-117` (note + tightened honest bands). The `_note` rewrite is informational. No engine module, no template, no `tools.py`, no `render/__init__.py` touched, matching iter-2 scope and brief allowlist. No symptom-fixing: the change addresses the root cause of iter-1 C4-fail (deterministic-Balanced NPV sitting on top of zero) by moving the anchor within defensible empirical bounds, not by hardcoding the MC output.

`rg` for stale numbers from iter-1 rendered report (`-797061`, `12123`, `744351`, `0.510`, `1016158`, `1279656`, `0\.414|0\.377|0\.123`) across `backend/decarb/render/templates/` + `backend/decarb/render/*.py` → no matches. Confirms no anchored-prose residue from the iter-1 numerics.

### Builder open-questions adjudicated

1. **OQ#1 — Sobol top-2 spec_target declared v0.2 follow-up: ACCEPT.**
   Reason: Builder executed the iter-1 OQ#1 prescribed path (1)+(2) — retuned `ets_allowance_price_gbp_per_tco2e` 75→100 (DESNZ Energy and Emissions Projections 2024 central trajectory at 2030, mid-horizon for the 2026–2040 plan, defensible) and `ietf_grant_fraction` 0.30→0.38 (IETF Phase 3 median award rate, defensible). Both citations are within the empirical envelope I would expect a senior engineer to sign off. The 10-row parameter sweep across (ETS, grant) ∈ {(75,0.30) … (150,0.40)} × {`max_reduction_positive_npv`, `max_npv`} (logged in actions.md) demonstrates gas_price holds the top Sobol total-order index across the entire defensible space — the structural argument (closed-form gas-only counterfactual scales fully with gas tariff; ietf_grant_outcome variance bounded by `p(1-p) × (£540k)²`) is sound. The closed-form re-evaluation methodology was itself accepted iter-1 (iter_1_review.md OQ#4 ACCEPT). Iter-3 forcing a narrower gas envelope below DESNZ central low/high spread, or overriding the gas-only counterfactual, would distort empirical inputs — exactly what the iter-1 fallback clause was designed to prevent. v0.2 per-trial dispatch loop (already declared in `mc_closed_form_v0` advisory warning per iter-1) is the right place to fix this. CLEAN with `mc_sobol_top2_v02_followup` warning declared.

2. **OQ#2 — `prob_npv_positive_min` consolidation 0.40 → 0.70 (= spec strength): ACCEPT.** Tightening honest bands to spec strength wherever feasible is the right discipline; it removes a phantom safety net that was no longer needed once the anchor moved. The honest_observed_v0_bands assertion now matches spec_target on this metric, which is the intended end-state — there is no double-bookkeeping risk.

3. **OQ#3 — Deterministic Balanced NPV £694k vs aspirational `lifetime_npv_gbp_min` £1.2M: NOTED, OUT OF SCOPE.** No test asserts on `lifetime_npv_gbp_min` (verified via `rg "lifetime_npv_gbp_min" backend/` — only the JSON fixture key, no code reference), so no test failure. Flagging only for a future dairy-pathway-anchor round; not a blocker for this MC round.

### Issues newly introduced this iter

None. The iter-2 anchor move is a clean three-file change with citations, tests still 237-passing, render numerics fully re-derive, no hardcoded literals introduced, and no stale literals (iter-1 numbers) anywhere in templates or render code.

### Issues remaining (declared as v0.2 warnings)

- **`mc_sobol_top2_v02_followup`** — Sobol top-2 total-order set on the dairy_5mw Balanced pathway is `{gas_price, electricity_price}`, not the brief's spec target `{electricity_price, ietf_grant_outcome}`. Root cause: the closed-form pathway re-evaluation perturbs gas_price across the gas-only counterfactual baseline (£1.4M/yr × 15-yr discounted) and the gas portion of pathway dispatch cost; both terms scale fully with the DESNZ wholesale gas envelope. ietf_grant_outcome variance is bounded above by Bernoulli(0.7) × (£540k capex × grant_fraction)², ranking it 3rd at ST≈0.18 vs gas_price ST≈0.37. Fix in v0.2: replace closed-form re-evaluation with per-trial dispatch loop so gas-price uncertainty propagates through HP/EB switching rather than the static gas-only counterfactual. Already covered by the existing `mc_closed_form_v0` advisory warning written iter-1; this is its formal v0.2 follow-up declaration.

### Recommended next iteration prompt for Builder

none — CLEAN.
