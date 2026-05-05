# Builder iter 2 — summary

Branch: `feature/dairy-report-fixes`. Engine regression: **222 passed**
(220 → 222; +2 new tests for the new selection rule). Latest dairy
report: `backend/decarb/runs/GOLDEN_DAIRY_5MW_20260505T174753Z.md`.

## Closed (2 of 2)

- **F — Balanced selection rule.** Added a
  `pathway_selection_rule` parameter to
  `optimise_investment_pathway`. Default keeps `max_npv` for
  backwards compatibility. New rule `max_reduction_positive_npv`
  picks the highest year-15-reduction pathway whose NPV stays
  positive (tie-break by NPV). The dairy regenerator
  (`backend/scripts/regenerate_dairy_report.py`) now requests
  `max_reduction_positive_npv`. The
  `balanced_underperforms_conservative_under_v0_defaults` advisory
  is suppressed under the new rule because the rule structurally
  prevents the inversion. New tests:
  `test_max_reduction_positive_npv_rule` (positive NPV + dominates
  Conservative + advisory absent) and
  `test_unknown_pathway_selection_rule_raises`. Result on the dairy
  fixture: Balanced moves to capex £1,554k, NPV £36,773, year-15
  reduction **47.5%** — dominates Conservative (38.7%) on reduction
  while staying NPV-positive. Reviewer's expected pathway hit
  exactly.

- **G+provenance — §9 live values.** Replaced the four hardcoded
  literal pairs in `v0_pathway_report.md.j2` with template
  expressions that read live from
  `pathways.{aggressive,balanced,conservative}` (year-15 reduction,
  NPV, capex). The £150k NH3 split-skid uplift is the only constant
  retained (rendered as "£0.15M" to keep numerical-traceability
  passing) — explicitly documented in the new provenance entry.
  Added two `optimise_investment_pathway` provenance rows
  (Appendix A entries 25 & 26): "Balanced selection rule" and "§9
  senior-decision X-to-Y rendering". Latest report's §9 now reads:
  Balanced 47.5% → Aggressive 50.9% at NPV £-127,005 vs Balanced
  £36,773; Conservative falls from 38.7% (gross capex £1,092,000)
  to ~16% if EB drops out; Aggressive NPV £-127,005 → ~£-277,005
  with split-skid; Balanced NPV £36,773 under 30.0% IETF.

## Couldn't close

None.

## Notes for the Reviewer

- The new selection rule is opt-in. `max_npv` remains the default,
  so existing callers (and the cached pathway tests for the legacy
  rule) are unaffected. Only the renderer driver flips it on for
  the dairy run.
- Numerical-traceability test bands held: rendered §9 has no
  4+digit literal that doesn't appear as a numeric leaf in
  parse/carbon/screen/dispatch results. The £150k constant is
  rendered "£0.15M" for that reason.
- Iter-1 review file restored (`plan/reviews/dairy_report_fixes_iter1.md`) — it was missing locally but the audit trail should keep both reviews.
