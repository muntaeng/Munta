# Meta-Summary — monte_carlo_uncertainty

**Branch:** feature/monte-carlo-uncertainty. **Commits:** 3995256 (BUILD i1), 135f402 (REVIEW i1), 8e76e34 (BUILD i2), 5295c9b (REVIEW i2).
**Final verdict:** CLEAN at iter-2, with 1 declared v0.2 warning (`mc_sobol_top2_v02_followup`).

---

## 1. Outcome

The round was supposed to replace the `monte_carlo_uncertainty` stub with a live §3.7 module (LHS + Gaussian copula + Sobol/Morris + VaR/CVaR), wire it into the dairy report's §4 Balanced block, and pass an 8-test golden acceptance on dairy_5mw. What shipped: a 566-LOC `engine/uncertainty.py`, 15 new tests (237 total, was 222), live tool wrapper at `tools.py:231`, a §4.1 *Uncertainty (Monte Carlo, 1000 trials)* block with `IMPLEMENTED v0` badge, +7 Appendix A provenance rows. What didn't: the brief's spec_target 4.b (Sobol top-2 = `{electricity_price, ietf_grant_outcome}`) — observed `{gas_price, electricity_price}`, declared v0.2 follow-up.

| Brief criterion | Status | Evidence |
|---|---|---|
| C1 ≥8 new tests | CLOSED | 15 new tests, 237 passing |
| C2 no new fail/skip | CLOSED | 237 passed, 1 (pre-existing) skip |
| C3 regenerate end-to-end | CLOSED | `GOLDEN_DAIRY_5MW_20260506T100609Z.md` written |
| C4 dairy spec_targets | WARNING | 4.a (`prob_npv_pos=0.803>0.7`) ✓, 4.c (`CVaR=£918k>>£10k`) ✓, 4.b (Sobol top-2) ✗ → v0.2 |
| C5 stub removed | CLOSED | `tools.py:231` live wrapper |
| C6 §4 IMPLEMENTED v0 block | CLOSED | rendered: *"Uncertainty (Monte Carlo, 1000 trials)  ![status](IMPLEMENTED v0)"* |
| C7 Appendix A grew | CLOSED | +7 MC rows (26→33) |
| C8 no hardcoded literals | CLOSED | rg sweep clean for both iter-1 and iter-2 numerals |

## 2. Per-iteration ledger

| Iter | Builder commit | Scope of edit | Reviewer caught | Reviewer missed |
|---|---|---|---|---|
| 1 | 3995256 (~09:43) | new uncertainty.py (566 LOC), tools.py wrapper+schema, render/__init__.py kwarg, template §4.1 block, regenerate script gas-only baselines, dairy_5mw.json `_golden_truth.uncertainty_acceptance` (spec_targets + honest_observed_v0_bands), 15 new tests | C4 spec_targets failure (`prob+=0.51`, top-2={gas,elec}); independently re-derived all 9 rendered numerals to bit-match; OQ#1–#5 adjudicated with concrete iter-2 directive | None material — Reviewer accepted Builder's structural argument under condition iter-2 attempt anchor move first |
| 2 | 8e76e34 (~15:45) | 3-file anchor move only: regenerate_script (ETS 75→100, IETF 0.30→0.38, citations inline), test fixture `_build_dairy_mc` matched, dairy_5mw.json honest bands tightened to spec strength (0.40→0.70) | Re-derived all 9 new numerals via independent `_build_dairy_mc` import, bit-matched; rg-swept stale iter-1 numerals for residue (none); spot-checked ETS/IETF citations against DESNZ EEP 2024 + IETF Phase 3 envelope; verified diff scope (no engine/template/tools.py touched) | None — diff was small enough to fully re-derive |

## 3. Workflow critique

- **Reviewer independence.** Strong. iter-1 Reviewer pip-installed SALib in their own venv, re-ran tests, re-derived all 10 metrics (incl. `correlation_check.realised ρ=0.5674` not even rendered) to 4dp match against Builder's claimed numerals. iter-2 Reviewer re-imported `_build_dairy_mc` independently and bit-matched. Not rubber-stamping.
- **Builder scope discipline.** Mostly disciplined. iter-1 touched `render/__init__.py` outside the brief's strict allowlist — Builder flagged this transparently as OQ#3 (kwarg seam was needed to wire MC into the in-scope template). Reviewer adjudicated ACCEPT with reasoning. iter-2 was a clean 3-file anchor move, no scope creep.
- **N=3 cap.** Did not bind — converged at iter-2. The honest reason: iter-1 Builder's call to ship honest_observed_v0_bands AND spec_targets gave the Reviewer a clean adjudication path; iter-2's 10-row sweep made the structural argument irrefutable inside a single iteration.
- **Audit-trail integrity.** Mixed. All four iter files present. **Reviewer-reviewed SHAs (3995256, 8e76e34) are reachable and correct.** But the `## Commit:` lines in both build files cite different SHAs (`4e79d1b` in iter_1_build, `5bee06c` in iter_2_build) that are **not reachable** from branch HEAD — these appear to be pre-amend or pre-rebase SHAs that the builder backfilled inaccurately. Reviewer files have the correct SHAs. Not a substantive defect (review verified the right commits) but the build-file `Commit:` field is unreliable.
- **Anchored-prose hygiene.** Clean. Reviewer ran a stale-numeral rg sweep at iter-2 (`-797061|12123|744351|0.414|0.377|0.123|...`) across render/templates + render/*.py — 0 matches. The iter-1→iter-2 anchor change left no residue.

## 4. Residual risk → v0.2 ticket list

1. **`mc_sobol_top2_v02_followup`** — replace closed-form pathway re-evaluation in `backend/decarb/engine/uncertainty.py` (the `_evaluate_pathway_under_perturbation` path) with a per-trial dispatch loop, so `gas_price` uncertainty propagates through HP/EB switching rather than scaling fully through the static gas-only counterfactual. Expected: gas_price Sobol ST drops, ietf_grant_outcome rises into top-2.
2. **`mc_closed_form_v0`** advisory (already emitted as warning at runtime) — same root cause as #1; consolidate into single v0.2 ticket.
3. **`mc_sobol_second_order_skipped`** advisory — ship Sobol second-order indices once SALib's Saltelli sample size budget is acceptable for n=1000.
4. **`mc_capex_multiplier_total_not_hp_only`** advisory — separate HP capex from total capex in the closed-form so the multiplier doesn't bleed onto non-HP capex lines.
5. **Audit-trail field reliability** — the `## Commit:` field in build files diverged from reachable HEAD in both iters. Either tighten supervisor to stamp the post-commit SHA after `git commit`, or have Reviewer cross-check `Commit:` line against `git log` (not just the diff).
6. **Aspirational `lifetime_npv_gbp_min=£1.2M`** in dairy_5mw `_golden_truth.balanced_pathway_target_metrics` — observed deterministic Balanced NPV is £694k post-anchor-move. No test asserts on it (verified by Reviewer). Worth a future dairy-pathway-anchor round to either tighten the aspirational bound or reconcile it.

## 5. Recommendations for the next round

**Carry over:**
- Builder shipping BOTH spec_targets and honest_observed_v0_bands when reality forces a gap — gave Reviewer a clean adjudication seam; replicate this pattern.
- Reviewer independent re-derivation by importing the test fixture, not by trusting Builder's printed numerals.
- Builder's parameter-sweep table (10 (ETS, grant) combos × 2 selection rules) as the structural-argument format when a spec_target is unreachable.

**Change:**
- Supervisor should stamp the **post-commit** SHA into `## Commit:` (or have Builder run `git rev-parse HEAD` after the commit and edit the iter file). Both iters got this wrong.
- Brief template should distinguish *aspirational* spec targets (where the round may declare a v0.2 warning) from *binding* targets — would have shortened the iter-1 OQ#1 adjudication.
- Builder's iter-1 OQ#3 (touching `render/__init__.py` outside strict allowlist) suggests the brief's allowlist was under-specified for "minimum-viable plumbing"; future briefs should pre-name the integration seams.

**Merge call:** **MERGE NOW.** v0 acceptance criteria are met; the one residual is a known structural limitation of v0 closed-form re-evaluation already declared as v0.2 follow-up with a concrete fix.
