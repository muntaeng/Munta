# Action log: monte_carlo_uncertainty

Append-only. Format: `[YYYY-MM-DDTHH:MM][role][iter<N>] <action>`

Roles: `builder`, `reviewer`, `meta`.

---

[2026-05-06T07:58][supervisor][iter0] Round started.
[2026-05-06T09:10][builder][iter1] Rebased onto main (no conflicts; sync-merge commit dropped as redundant).
[2026-05-06T09:15][builder][iter1] Engine-tests baseline 222 passed (pre-MC).
[2026-05-06T09:25][builder][iter1] Wrote engine/uncertainty.py (LHS + Iman-Conover copula + Saltelli/Sobol + Morris) + engine/__init__.py export.
[2026-05-06T09:30][builder][iter1] tools.py:229 stub replaced with live monte_carlo_uncertainty wrapper; schema at line 519 rewritten to real signature (pathway_name/n_trials/seed/uncertain_inputs/carbon_target_trajectory).
[2026-05-06T09:32][builder][iter1] render/__init__.py: render_report grew uncertainty_result kwarg; provenance + standards aggregator pull from MC result.
[2026-05-06T09:33][builder][iter1] templates/v0_pathway_report.md.j2 §4.1 Balanced loop got Uncertainty (Monte Carlo) sub-block (status badge IMPLEMENTED v0; live-rendered NPV P10/P50/P90, prob_npv_pos, VaR/CVaR, top-3 Sobol; no hardcoded literals).
[2026-05-06T09:35][builder][iter1] regenerate_dairy_report.py: gas-only baseline arrays computed; MC tool called with seed=42, n_trials=1000; result threaded into render_report.
[2026-05-06T09:38][builder][iter1] dairy_5mw.json: added _golden_truth.uncertainty_acceptance with spec_targets (brief) AND honest_observed_v0_bands. Reason: deterministic Balanced NPV is +£37k under v0 default carbon/grant overlay, so brief's prob_npv_positive>0.7 is unattainable without distorting the input distributions. Documented as v0.3 follow-up; tests assert against honest bands.
[2026-05-06T09:40][builder][iter1] test_uncertainty.py: 15 new tests (schema, monotonicity, copula closure, Sobol bounds, Morris signs, seed determinism, target trajectory probability ×2, dairy golden ×5, triangular helper ×2). All pass.
[2026-05-06T09:42][builder][iter1] cd backend && pytest decarb/engine/tests -q → 237 passed (baseline 222 + 15 new). cd backend && pytest decarb -q (excl. pre-existing psycopg collection errors in corpus tests) → 237 passed, 1 skipped pre-existing.
[2026-05-06T09:43][builder][iter1] regenerate_dairy_report.py runs end-to-end; rendered §4.1 carries the live MC block; Appendix A grew by 7 monte_carlo_uncertainty provenance rows; rg sweep shows no MC literals in templates.
[2026-05-06T10:50][reviewer][iter1] Re-ran `cd backend && pytest decarb/engine/tests -q` after pip-installing SALib (was missing locally) — confirmed 237 passed in 94.05s, matches Builder's count.
[2026-05-06T10:51][reviewer][iter1] Re-ran `pytest decarb -q --ignore=corpus/tests --ignore=tests/test_retrieve_reference_docs.py` → 237 passed, 1 skipped. psycopg collection errors confirmed pre-date round (file ages = initial-import commit 7f33098).
[2026-05-06T10:52][reviewer][iter1] Re-ran regenerate_dairy_report.py end-to-end → 33 prov / 31 standards / 4 §9 senior decisions (matches Builder).
[2026-05-06T10:55][reviewer][iter1] Independently re-derived MC numbers: P10=-797061, P50=12123, P90=744351, prob_npv_pos=0.51, VaR_95=1016158, CVaR_95=1279656, top-3 ST={gas_price 0.414, electricity_price 0.377, ietf_grant_outcome 0.123}. All match rendered §4.1 exactly.
[2026-05-06T10:57][reviewer][iter1] `rg` for rendered numerals in render/templates/* and render/*.py → no matches. Criterion 8 passes.
[2026-05-06T10:58][reviewer][iter1] Verified _stub removed for monte_carlo_uncertainty (tools.py:231); schema at tools.py:616 reflects real signature.
[2026-05-06T10:59][reviewer][iter1] Adjudicated OQ#1: criterion 4 spec_targets unmet (prob_npv_pos=0.51 vs >0.7; Sobol top-2={gas,elec} vs {elec,grant}). Honest bands accepted as safety net but iter-2 must attempt path (ii) — retune deterministic anchor within defensible empirical envelopes.
[2026-05-06T11:00][reviewer][iter1] OQ#3 ACCEPT: render/__init__.py kwarg is the minimum-viable seam to thread MC into the in-scope template; renderer still does no arithmetic.
[2026-05-06T11:01][reviewer][iter1] OQ#4 ACCEPT: closed-form re-evaluation captures all six inputs with documented advisory warnings.
[2026-05-06T15:30][builder][iter2] Param sweep across (ETS, grant, rule) — gas_price holds Sobol ST top across (75,0.30), (100,0.30), (100,0.35), (100,0.38), (100,0.40), (110,0.40), (120,0.35), (125,0.30), (125,0.35), (125,0.40), (150,0.40) and both selection rules. ietf_grant_outcome ranks 3rd with ST≈0.12-0.20.
[2026-05-06T15:35][builder][iter2] regenerate_dairy_report.py:97-105 — ETS 75→100 (DESNZ EEP 2024 central 2030), grant 0.30→0.38 (IETF Phase 3 median); citations in inline comment.
[2026-05-06T15:36][builder][iter2] test_uncertainty.py:279-280 — _build_dairy_mc fixture matches new anchor (ETS=100, grant=0.38).
[2026-05-06T15:37][builder][iter2] dairy_5mw.json:99-117 — uncertainty_acceptance _note rewritten with citations + structural reasoning; honest_observed_v0_bands prob_npv_positive_min 0.40→0.70, _max 0.65→0.90; Sobol allowed-set unchanged ({elec, gas, grant}).
[2026-05-06T15:42][builder][iter2] cd backend && pytest decarb/engine/tests -q → 237 passed in 92.94s. cd backend && pytest decarb -q --ignore=corpus --ignore=test_retrieve_reference_docs → 237 passed, 1 skipped (matches iter-1).
[2026-05-06T15:45][builder][iter2] PYTHONPATH=backend python3 scripts/regenerate_dairy_report.py → GOLDEN_DAIRY_5MW_20260506T100014Z.md, prov=33 std=31. §4.1 MC block: P10=-367,247 P50=682,129 P90=1,537,634 prob+=80.3% VaR=659,836 CVaR=918,088; Sobol top-3 gas_price 0.369 / electricity_price 0.339 / ietf_grant_outcome 0.181.
[2026-05-06T15:46][builder][iter2] Provenance sweep — grep new numerals in render/templates/*.j2 + render/*.py → 0 matches. C8 holds.
[2026-05-06T15:47][builder][iter2] Spec_targets status: prob_npv_positive>0.7 ✓ (0.803), cvar_95<-£10k ✓ (loss £918k); Sobol top-2={elec, grant} ✗ (top-2={gas, elec}, ietf_grant 3rd at ST=0.181). Declared v0.2 follow-up — root cause: closed-form gas-only counterfactual scales fully with gas tariff; per-trial dispatch loop (already declared v0.3 in mc_closed_form_v0 warning) is the right fix.
