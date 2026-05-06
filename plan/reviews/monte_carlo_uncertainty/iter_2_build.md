## Iteration: 2 of 3
## Branch: feature/monte-carlo-uncertainty
## Commit: 5bee06c
## Tests: 237 passed in 92.94s (engine-tests baseline 222 + 15 MC tests = 237). Full backend `pytest decarb -q --ignore=decarb/corpus/tests --ignore=decarb/tests/test_retrieve_reference_docs.py` → 237 passed, 1 skipped, 1 warning. Same as iter-1.

### Issues addressed (from iter-1 Reviewer ISSUES_FOUND)

- **C4 (criterion-4 spec_targets — anchor move).** The reviewer's "good-faith
  attempt" path: retune the deterministic anchor in
  `regenerate_dairy_report.py` within defensible empirical bounds.
  - `ets_allowance_price_gbp_per_tco2e`: **75.0 → 100.0** —
    DESNZ Energy and Emissions Projections 2024 central trajectory
    at 2030 (mid-decade, mid-horizon for the 2026-2040 plan).
  - `ietf_grant_fraction`: **0.30 → 0.38** — median IETF Phase 3
    award rate per DESNZ Phase 3 award schedule 2024.
  - `pathway_selection_rule` left at `max_reduction_positive_npv`
    (Reviewer iter-1 OQ#1 path (1)+(2) tried first).

  After the anchor move, observed dairy_5mw Balanced MC (seed=42, n=1000):
  - prob_npv_positive = **0.803** (was 0.510). **Clears spec target >0.70.** ✓
  - CVaR_95 = **£918,088 loss** (magnitude ≫ £10k floor). ✓
  - VaR_95 = **£659,836 loss**.
  - Sobol total-order: gas_price 0.369, electricity_price 0.339,
    ietf_grant_outcome 0.181, grid_carbon_intensity 0.061,
    hp_capex_multiplier 0.021, demand_growth 0.016. **Top-2 =
    {gas_price, electricity_price} — fails spec set
    {electricity_price, ietf_grant_outcome}.**

  **2/3 spec_targets met. Third (Sobol top-2 set) is structurally
  unattainable in v0** without distorting empirical input
  distributions. Root cause documented:

  - The closed-form re-evaluation perturbs gas_price across (a) the
    gas-only counterfactual baseline cost (~£1.4M/yr × 15-yr horizon
    discounted) and (b) the gas portion of the pathway dispatch cost
    (~£1.0M/yr first-full-stack). Both terms scale fully with the
    DESNZ wholesale gas envelope (triangular ±20%). That envelope is
    the empirically right input — narrowing it to push gas below
    ietf_grant_outcome would distort the v0 input distribution.
  - ietf_grant_outcome is Bernoulli(0.7) and shifts only capex by
    `grant_fraction × total_capex` ≈ £540k. Variance contribution is
    bounded above by p(1-p) × (£540k)² regardless of n_trials.
  - Sweep run iter-2 (see actions.md) confirmed: across
    (ETS, grant) ∈ {(75,0.30), (100,0.30), (100,0.38), (100,0.40),
    (110,0.40), (120,0.35), (125,0.30), (125,0.35), (125,0.40),
    (150,0.40)}, gas_price holds the top Sobol total-order index in
    every case. Switching `pathway_selection_rule` to `max_npv`
    likewise leaves gas_price at the top.

  Per Reviewer iter-1 OQ#1 fallback clause: I retain
  `honest_observed_v0_bands` in `dairy_5mw.json._golden_truth.uncertainty_acceptance`
  but tighten them to reflect the new anchor — `prob_npv_positive_min`
  raised 0.40 → **0.70** (now matches spec_target), max raised
  0.65 → **0.90**. The `sobol_top2_total_order_allowed_set` remains
  `{electricity_price, gas_price, ietf_grant_outcome}` (gas allowed,
  per the structural reasoning). The detailed `_note` documents the
  iter-2 anchor citations and the v0.2 follow-up: replace closed-form
  re-evaluation with a per-trial dispatch loop so gas-price uncertainty
  propagates through HP/EB switching rather than the static gas-only
  counterfactual — that should drop gas_price's Sobol dominance.

### Files modified

- `backend/scripts/regenerate_dairy_report.py:97-105` — ETS 75→100,
  grant 0.30→0.38, with citations in inline comment.
- `backend/decarb/engine/tests/test_uncertainty.py:279-280` — matching
  ETS=100, grant=0.38 in `_build_dairy_mc` so the dairy golden test
  asserts against the same anchor as the regenerate script.
- `backend/decarb/tests/sites/dairy_5mw.json:99-117` — updated
  uncertainty_acceptance `_note` (citations + structural reasoning),
  tightened honest_observed_v0_bands `prob_npv_positive_min` to 0.70
  and `_max` to 0.90.

### Files NOT modified (deliberately, brief allowlist + iteration discipline)

- `backend/decarb/engine/uncertainty.py` — unchanged. The MC math is
  correct as iter-1 left it; this iter is anchor-only.
- `backend/decarb/tools.py` — unchanged. Schema and live wrapper from
  iter-1 already pass C5.
- `backend/decarb/render/templates/v0_pathway_report.md.j2` — unchanged.
  All numerals re-rendered from the new tool result.
- `backend/decarb/render/__init__.py` — unchanged.
- `backend/decarb/engine/__init__.py` — unchanged.

### Verification I did myself

- Param sweep (10 (ETS, grant) combinations × {max_reduction_positive_npv,
  max_npv}) — full table in actions.md. Confirms gas_price holds Sobol
  top spot across the entire defensible empirical envelope.
- `python3 scripts/regenerate_dairy_report.py` (with PYTHONPATH=backend)
  → wrote `decarb/runs/GOLDEN_DAIRY_5MW_20260506T100014Z.md`,
  chars=42,997 sections=11 provenance=33 standards=31 §9
  senior_decisions=4. §4.1 *Uncertainty (Monte Carlo, 1000 trials)*
  block renders the new numbers verbatim:
  - "NPV P10 | £-367,247" (live)
  - "NPV P50 (median) | £682,129"
  - "NPV P90 | £1,537,634"
  - "Probability NPV > 0 | 80.3%"
  - "VaR 95% (loss, £) | £659,836"
  - "CVaR 95% (loss, £) | £918,088"
  - Sobol top-3: gas_price 0.369, electricity_price 0.339,
    ietf_grant_outcome 0.181.
- **Provenance sweep** (rule from dairy template hygiene round):
  `grep -E "367,247|682,129|1,537,634|918,088|659,836|0\.369|0\.339|0\.181|80\.3"
  decarb/render/templates/*.j2 decarb/render/*.py` → no matches.
  Every numeral in the rendered §4.1 uncertainty block traces to
  the live MC tool result via the Jinja2 namespace pattern. C8 holds.
- `cd backend && pytest decarb/engine/tests -q` → 237 passed in 92.94s.
- `cd backend && pytest decarb -q --ignore=decarb/corpus/tests
  --ignore=decarb/tests/test_retrieve_reference_docs.py` → 237 passed,
  1 skipped, 1 warning. No new failures, no new skips.
- `dairy_5mw.json._golden_truth.uncertainty_acceptance.honest_observed_v0_bands`
  range checks against observed:
  - `prob_npv_positive_min` 0.70 ≤ 0.803 ≤ `_max` 0.90 ✓
  - `cvar_95_npv_loss_min_gbp` 500_000 ≤ 918_088 ✓
  - `var_95_npv_loss_min_gbp` 400_000 ≤ 659_836 ✓
  - top-2 Sobol set {gas_price, electricity_price} ⊆
    `sobol_top2_total_order_allowed_set` {electricity_price,
    gas_price, ietf_grant_outcome} ✓

### Open questions for Reviewer

1. **Spec_target 4.b (Sobol top-2 = {electricity_price, ietf_grant_outcome})
   declared v0.2 follow-up.** Per Reviewer iter-1 OQ#1 fallback ("If after
   one good-faith attempt all three spec_targets cannot be met without
   distorting empirical input distributions, document the attempted
   parameter sweep [...] retain `honest_observed_v0_bands`"), I have
   completed the good-faith attempt (10-row parameter sweep above,
   structural variance argument), retained honest bands, and tightened
   them to spec strength on the 2/3 metrics that move. Builder's call:
   the third metric is structurally bounded by the closed-form
   re-evaluation choice, not by anchor parameter choice — the v0.3
   per-trial dispatch loop is the right place to fix it. Please
   adjudicate: ACCEPT this as iter-2 closure (declare CLEAN with the
   `mc_sobol_top2_v02_followup` warning), or REJECT and direct iter-3
   to attempt a different mechanism (e.g. narrow the gas_price triangular
   envelope below DESNZ central low/high spread, or override the
   gas-only counterfactual to one that doesn't scale fully with gas
   tariff).

2. **Honest bands `prob_npv_positive_min` raised 0.40 → 0.70.** This
   is now numerically equal to `spec_targets.prob_npv_positive_min`,
   so passing honest bands is equivalent to passing spec_target on
   that one metric. Acceptable consolidation? (My read: yes — the
   honest_observed table is the assertion target, and tightening it
   to spec strength wherever feasible is the right discipline.)

3. **Deterministic Balanced NPV is now £694k**, still below the
   aspirational `_golden_truth.balanced_pathway_target_metrics.lifetime_npv_gbp_min`
   = £1.2M. No test asserts on those bounds (greenfield aspirational
   metric — searched all .py for `lifetime_npv_gbp_min`, zero matches),
   so no test failure. Flagging only because the gap could be relevant
   to a future dairy-pathway-anchor round. Out of scope for this round.
