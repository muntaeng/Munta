# Task: monte_carlo_uncertainty

## Branch and scope

- Working branch: `feature/monte-carlo-uncertainty`. Before iter 1, **rebase
  onto `main`** so this branch carries the merged dairy-report-fixes +
  dairy-template-hygiene work. Resolve trivially or stop and surface the
  conflict in `iter_1_build.md` if it isn't trivial.
- Files in scope:
  - `backend/decarb/engine/uncertainty.py` — new module
  - `backend/decarb/engine/tests/test_uncertainty.py` — new tests
  - `backend/decarb/engine/__init__.py` — export the new function
  - `backend/decarb/tools.py` — replace the `monte_carlo_uncertainty` stub
    at lines ~229–231 with the live wrapper; update its `input_schema`
    and `description` at lines ~519–531 to reflect the real signature
  - `backend/decarb/render/templates/v0_pathway_report.md.j2` — *minimal*
    integration only: a single uncertainty block under §4 (see
    "Acceptance criteria" 6 below). No new top-level section.
  - `backend/scripts/regenerate_dairy_report.py` — call the new tool
    once before render so `_uncertainty` is populated; pass the Balanced
    pathway result.
  - Optional: `requirements.txt` / `pyproject.toml` to add `SALib`
    if not already present.
- Files NOT in scope: any other engine module (`pathway.py`, `dispatch.py`,
  `screen.py`, `hp_cycle.py`, `carbon.py`, `parse.py`); methodology doc;
  any other template; any other tool's stub.
- Engine state must remain at the current passing-test count throughout
  (run `cd backend && pytest decarb/engine/tests -q` to record the
  baseline in iter_1_build.md, then keep ≥ baseline + the new MC tests).

## Background (read before starting)

- `docs/methodology/methodology.md` §3.7 — the contract for what this
  module produces (LHS, correlated inputs via Gaussian copula, Sobol +
  Morris, P10/P50/P90, VaR/CVaR @ 95%).
- `plan/spike/week2_engine_modules.md` §7 — the build spec, including
  the dairy_5mw golden-test acceptance: `P_success > 0.7`, top-2 Sobol
  inputs are electricity price + IETF grant, CVaR_95% NPV is a
  meaningfully-negative number (not zero).
- `backend/decarb/engine/pathway.py` — the deterministic pathway result
  shape this module consumes (Conservative / Balanced / Aggressive
  pathway records, action sequences, NPV, year-by-year carbon).
- `backend/decarb/tests/sites/dairy_5mw.json` — the golden site.
  `_golden_truth.balanced_pathway_target_metrics` is the anchor for
  cardinal numbers; add a `_golden_truth.uncertainty_acceptance` block
  carrying the four targets above (P_success > 0.7, top-2 Sobol set,
  CVaR_95 < 0, all risk metrics present).
- The Methodology no-arithmetic principle (§2.2 (i)) and provenance
  contract (§2.2 (ii)) apply: every Monte Carlo output rendered into the
  report must trace to a deterministic Python function call recorded in
  the run audit trail.

## What the module must do

Implement `monte_carlo_uncertainty(pathway, uncertain_inputs, n_trials=1000,
seed=...) -> dict` in `engine/uncertainty.py`. The function:

1. **Sampling.** Latin hypercube samples each declared uncertain input
   over `n_trials` rows, then re-orders pairs to impose declared
   correlations via a Gaussian copula. Default uncertain inputs (each
   with sensible v0 distributions; document defaults in the docstring):
   - Electricity price 2026–2040 — triangular, calibrated to DESNZ
     central / low / high
   - Gas price 2026–2040 — triangular
   - HP capex multiplier — triangular (manufacturer ranges)
   - Grid carbon intensity 2030 — triangular bounded by NESO FES range
   - IETF grant outcome — Bernoulli on declared probability
   - Demand growth — triangular
   - Gas–electricity correlation default ρ = 0.6 (Gaussian copula).
2. **Inner loop.** For each sampled row, re-evaluate the pathway's NPV
   and year-by-year carbon trajectory. **Do not re-run dispatch
   per-trial**; use a closed-form sensitivity over the deterministic
   pathway outputs (energy×price, capex×multiplier, carbon×intensity,
   grant×outcome). If a closed-form re-evaluation cannot capture a
   declared uncertain input correctly, document it in the docstring as
   a v0.3 enhancement and exclude that input from sampling rather than
   silently approximating it.
3. **Outputs:**
   - NPV distribution: P10 / P50 / P90 / mean / stdev / skew, plus the
     full sample array
   - Carbon trajectory uncertainty cone: P10 / P50 / P90 per year
   - `prob_npv_positive` and `prob_carbon_target_met` (target taken
     from input or default UK Net Zero trajectory)
   - VaR_95 and CVaR_95 on NPV
   - Sobol first-order **and** total-order sensitivity indices for each
     uncertain input on NPV (the spec says first + second; if second-
     order is materially expensive, ship first + total and document
     second-order as v0.3)
   - Morris elementary-effects screening (mean, mean of |EE|, std)
   - `correlation_check`: realised Pearson ρ between gas and electricity
     samples, with assertion that |realised − target| < 0.05
4. **Provenance.** Return a `provenance` block listing function name,
   engine version, input distributions, n_trials, seed, and the
   standards register entries for §3.7. The render integration step
   adds at least one row to Appendix A.
5. **Determinism.** Seed-driven; same `seed` → same output to the bit.

## Acceptance criteria

1. `cd backend && pytest decarb/engine/tests -q` — baseline test count
   from iter_1_build.md plus **at least 8 new tests** covering: schema
   shape, P10/P50/P90 monotonicity, copula-correlation closure,
   Sobol indices sum-bounded, Morris stability, seed determinism,
   target-trajectory probability calculation, and the dairy_5mw golden
   acceptance from week2_engine_modules.md §7.
2. `cd backend && pytest decarb -q` overall: 0 newly skipped, 0 newly
   failing. The dairy_template_hygiene merge pre-existing skips/ignores
   are permitted as long as Reviewer can confirm they pre-date this
   round.
3. `python backend/scripts/regenerate_dairy_report.py` runs end-to-end
   without raising; rendered report includes the §4 uncertainty block
   (criterion 6) populated from the live tool result.
4. Dairy golden test (`dairy_5mw.json` Balanced pathway) passes the
   `_golden_truth.uncertainty_acceptance` block: `prob_npv_positive >
   0.7`, top-2 Sobol total-order inputs are `electricity_price` and
   `ietf_grant_outcome` (in either order), `cvar_95_npv < 0` and not
   close to zero (e.g. < −£10,000 — pick a defensible band and document).
5. Tool registry: `backend/decarb/tools.py` no longer returns
   `{"_stub": True}`. The schema reflects the real signature
   (`pathway`, `uncertain_inputs`, `n_trials`, `seed`,
   `carbon_target_trajectory`).
6. Render integration: a single block under §4 Pathway, after the
   action-sequence table, headed *"Uncertainty (Monte Carlo, N
   trials)"*, listing for the Balanced pathway: NPV P10/P50/P90,
   `prob_npv_positive`, VaR_95, CVaR_95, top-3 Sobol total-order
   inputs by index value. All numbers live-rendered from the tool
   result via the Jinja2 namespace pattern (no hardcoded literals).
   The §4 status badge for this block reads `IMPLEMENTED v0` (not
   ROADMAP).
7. Provenance Appendix A grows by ≥1 row (one row per metric block, or
   one row covering the MC call — Builder's call, but every numeric
   in the rendered uncertainty block must be traceable).
8. Numerical-integrity contract: every numeric literal in the new
   render block traces to the MC tool's `outputs` dict via the
   namespace pattern. No hardcoded numbers, no hardcoded input names
   in the rendered Sobol top-3.

## Iteration discipline

- N=3 cap. If iter-3 Reviewer still ISSUES_FOUND, declare residuals as
  v0.2 warnings and stop. Do not request iter-4. The supervisor honours
  the cap.
- **Post-engine-change provenance sweep** (rule from dairy template
  hygiene round): after the MC function lands, `rg` the rendered dairy
  report for any number in the uncertainty block and confirm it traces
  to the run audit log, not to a template literal.
- Do not refactor pathway.py, dispatch.py, screen.py, or any other
  engine module. If MC requires a change to a consumed module's output
  shape, write `iter_<N>_build.md` saying so and stop without
  committing — Reviewer adjudicates whether the scope expansion is
  warranted.
- Do not add new agent tools beyond completing the
  `monte_carlo_uncertainty` registration. The validate_pathway and
  lookup_grants stubs stay stubs in this round.
- SALib is the preferred Sobol/Morris implementation. If a transitive
  dependency conflict surfaces, fall back to a hand-rolled
  Saltelli-2002 estimator and document the tradeoff in
  `iter_<N>_build.md`.
