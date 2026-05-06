# Meta-Summary — multisite_render_and_architecture

**Branch:** `feature/assessment-2026-05-06-fixes`. **Commits:** d655b24 (BUILD iter1), 8c7882f (stamp), 07d8eb1 (REVIEW iter1 CLEAN).
**Final verdict:** CLEAN at iter-1. Cap did not bind.

---

## 1. Outcome

The round was supposed to render brewery + soft-drinks GOLDEN reports through the same pattern as dairy, and prune two stale claims from `plan/architecture.md`, as Phase 6 (final) of the assessment_2026_05_06_fixes feature branch.

| AC | Status | Evidence |
|---|---|---|
| AC1 [BINDING] both new GOLDEN renders end-to-end with §10 PASSED | CLOSED | Brewery `Overall: PASSED — errors 0, warnings 0, infos 1`; Soft-drinks `Overall: PASSED — errors 0, warnings 1, infos 1` (warning is `exec_summary_baseline_consistency`, severity=warning, allowed by brief). |
| AC2 [BINDING] 11 sections + Appendix A/B both reports | CLOSED | `grep ^## §|^## Appendix` returns 12 H2s on each, matching dairy. |
| AC3 [BINDING] architecture.md frontend row + MUNTec reuse table replaced verbatim | CLOSED | Reviewer string-equals against brief at `plan/architecture.md:113`. |
| AC4 [BINDING] 279/279 tests, no regression | CLOSED with note | 282 passed / 1 skipped pre- and post-round (engine subset; corpus-retrieval suite excluded). Brief baseline of 279 was stale — actual baseline at round-start was already 282 from earlier phases. Reviewer noted and accepted. |
| AC5 [ASPIRATIONAL] Option A generalised script | CLOSED | `regenerate_site_report.py --site {dairy_5mw,brewery_8mw,soft_drinks_12mw}`; dairy script reduced to wrapper. |
| AC6 [ASPIRATIONAL] no dairy-specific text leaks | WARNING | 3 leaks/site flagged, not fixed (per brief): `dairy_5mw` literal in capex-sensitivity narrative; `(food_drink / dairy_processing)` IETF parenthetical in §9; GMP/BRC framing in Appendix A. Already carved out as `plan/reviews/dairy_template_hygiene/`. |

## 2. Per-iteration ledger

| Iter | Builder commit (time) | Scope of edit | Reviewer caught | Reviewer missed |
|---|---|---|---|---|
| 1 | d655b24 (19:30) | NEW `regenerate_site_report.py`; `regenerate_dairy_report.py` → wrapper; `architecture.md` 2 minimal edits (frontend row removal, MUNTec note) | Re-derived implied boiler efficiencies live (0.921 / 0.855 / 0.85), independently grepped section counts, string-equality-checked architecture note vs brief, re-ran full pytest, verified §10 PASSED on both reports, re-confirmed Builder's 3 dairy-leak line numbers | Did not flag the soft-drinks 14.5% baseline-y0 disagreement as a *quantitative* concern — accepted it as "warning severity allowed by brief" but the brewery/dairy sites now hit 0.0% on the same anchor, so soft-drinks is a genuine residual signal, not just a permitted warning. Captured in residuals §4 below. |

Cap did not bind; iter-2 not needed.

## 3. Workflow critique

- **Reviewer independence.** Strong. Reviewer re-derived three implied-efficiency values from `_implied_baseline_boiler_efficiency` rather than trusting Builder's ~0.855 figure; re-ran the full pytest exclusion set and got an independent timing (164s vs Builder 166s, same count); read each new report's §10 line directly off-disk; string-equality-checked the architecture.md note against the brief verbatim. No rubber-stamping observed.
- **Builder scope discipline.** Tight. Three files touched, all in-scope. No engine modules, no methodology, no fixtures, no other tests. Builder explicitly refused to fix the 3 dairy-leaks per the brief's instruction and instead routed them to the existing `dairy_template_hygiene` round.
- **N=3 cap.** Did not bind. Round converged in iter-1 because brief was unusually well-scoped (small files-in-scope set, sharp acceptance criteria, anchor patterns already proven on dairy). This is the cleanest round in the assessment_2026_05_06_fixes phase.
- **Audit-trail integrity.** All three iter files (`iter_1_build.md`, `iter_1_review.md`, `actions.md`) present in working tree. SHA d655b24 in `iter_1_build.md` is reachable from HEAD; stamp commit 8c7882f references it correctly. Action log is consistent with both iter files.
- **Anchored-prose hygiene.** No new anchored-prose drift introduced this round. The 3 known dairy leaks per site are pre-existing engine-prose hygiene issues now properly tracked, not regressions.

## 4. Residual risk → v0.2 ticket list

1. Soft-drinks `exec_summary_baseline_consistency` warns 14.5% disagreement (`compute_baseline_carbon=18220.5 t` vs `pathway=15573.4 t`) despite implied efficiency hitting the 0.85 default — points to a non-efficiency baseline-input divergence (fuel-mix split, T&D inclusion, or grid-intensity year alignment) in `decarb/engine/baseline.py` vs `decarb/engine/pathway.py`. Brewery/dairy now 0.0%, so soft-drinks is the lone outlier.
2. Three dairy-text leaks per non-dairy site, already routed to `plan/reviews/dairy_template_hygiene/`: capex-sensitivity narrative carries literal `dairy_5mw` site-id (`decarb/engine/pathway.py` warning constructor); §9 IETF eligibility parenthetical hardcodes `(food_drink / dairy_processing)`; Appendix A `screen_technologies` provenance row carries dairy-canonical GMP/BRC framing.
3. `standards_register_no_dupes` info-FAILs with 3 duplicates on every report (dairy + 2 new) — track for a standards-dedupe round.
4. `python -m scripts.regenerate_site_report` requires `scripts/__init__.py` to work as a module; currently only the `PYTHONPATH=. python3 scripts/...` form runs. Cosmetic; Reviewer accepted.
5. Filename mismatch `GOLDEN_SOFTDRINKS_12MW_*.md` (no underscore) vs the brief's `SOFT_DRINKS` example — caused by fixture's `site_id`. Fixture changes were out of scope; track if the founder cares about the underscore on disk.

## 5. Recommendations for the next round

**Carry over:**
- Brief-writing pattern: tightly-bounded files-in-scope list + binding-vs-aspirational AC tagging + explicit "do NOT fix in this round" routing. Drove iter-1 convergence.
- Reviewer's habit of re-deriving numerical anchors live (implied efficiencies, pytest counts) rather than trusting Builder's report.
- Builder's discipline of routing out-of-scope findings to a sibling round-brief directory instead of expanding scope.

**Change:**
- When the brief states a stale baseline number (here: "279 tests passing" while reality was 282), Reviewer should call it out explicitly in the verdict line, not bury it in the AC4 footnote — founder eyes parse the verdict header first.
- For warning-severity validate failures that are *allowed* by the brief but *quantitatively divergent from the rest of the fleet* (the soft-drinks 14.5% case), Reviewer should flag them above the residual list, not inside it.
- Add a one-line `scripts/__init__.py` either in this branch's tail or in the next round so the docstring's `python -m` invocation actually runs — current state is a small lie in the docstring.

**Merge call:** MERGE NOW. Phase 6 of `assessment_2026_05_06_fixes` is clean, all binding ACs closed, residuals are properly tracked in named follow-up rounds.
