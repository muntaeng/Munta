## Verdict: ISSUES_FOUND
## Iteration: 3 of 3

Reviewed against `backend/decarb/runs/GOLDEN_DAIRY_5MW_20260505T174753Z.md` and code at `7f63c0a`. Verified independently of `plan/reviews/builder_iter2_summary.md`.

Engine regression: `222 passed in 53.17s` (was 220 — +2 tests for the new selection-rule path). No engine regressions, no new HIGH-severity warnings.

### Iter-2 fixes — what landed cleanly

- **[F] PASS — engine.** `pathway_selection_rule="max_reduction_positive_npv"` is wired in `backend/decarb/engine/pathway.py:795` (default) and dispatched at line 940; `backend/scripts/regenerate_dairy_report.py:103` requests it for the dairy run. Balanced now lands on **capex £1,554,000 / NPV £36,773 / 47.5% reduction** — exactly the §4.2 NPV-frontier rank-3 row. The `balanced_underperforms_conservative_under_v0_defaults` advisory is gone from §4.3 (line 245 ff.) and §8.1 (line 345 ff.); the suppression is conditioned on the new rule at `pathway.py:1139`. Balanced's action sequence is `hp_mid_2000 + eb_2000 + tes_8000` (§4.1 line 183–188).
- **[G] PASS on impact figures.** Re-derived each X/Y in §9 against §4.1 live numbers:

  | Decision | Field | §9 rendered | §4.1 live | OK? |
  |---|---|---|---|---|
  | #1 | Balanced year-15 reduction | 47.5% | 47.5% | ✓ |
  | #1 | Aggressive year-15 reduction | 50.9% | 50.9% | ✓ |
  | #1 | Aggressive NPV | £-127,005 | £-127,005 | ✓ |
  | #1 | Balanced NPV | £36,773 | £36,773 | ✓ |
  | #2 | Conservative reduction | 38.7% | 38.7% | ✓ |
  | #2 | Conservative gross capex | £1,092,000 | £1,092,000 (net of grant — see note) | ✓* |
  | #3 | Aggressive baseline NPV | £-127,005 | £-127,005 | ✓ |
  | #3 | Aggressive NPV after split-skid | £-277,005 | £-127,005 − £150,000 = £-277,005 | ✓ |
  | #4 | Balanced NPV | £36,773 | £36,773 | ✓ |

  All X/Y impact figures live-rendered. The £150k split-skid constant is templated as `_nh3_split_skid_capex_uplift = 150000` at `v0_pathway_report.md.j2:459`.
- **Provenance.** Appendix A grew from 24 → 26 entries. Row 25: `optimise_investment_pathway / Balanced selection rule` documents the rule param. Row 26: `optimise_investment_pathway / §9 senior-decision X-to-Y rendering` documents the live-render mechanism and references the £150k constant.
- Regression: 222/222 tests pass. New tests cover the selection rule and the inversion-advisory suppression.

### Issues newly introduced by the iter-2 fix

The F fix changed Balanced's stack from `hp_mid_1000 + eb_2000 + tes_8000` (iter-1) to `hp_mid_2000 + eb_2000 + tes_8000` (iter-2). Three pieces of surrounding prose were anchored on the old Balanced stack and are now structurally stale:

1. **§9 Decision 1, "1000 kW" is wrong** (report line 383): renders "HP capacity sized to hot-water sub-demand only (**1000 kW**)" but Balanced's action sequence is `hp_mid_2000` (2,000 kW). Root cause: `v0_pathway_report.md.j2:452–457` — Jinja2 loop-scope bug. The `{% set _hp_kw = a.capacity|int %}` inside `{% for a in _bal.actions %}` does not propagate to outer scope, so `_hp_kw` stays at the default `1000`. Verified empirically:
   ```
   $ python3 -c "from jinja2 import Template; print(Template('{% set x=1000 %}{% for a in items %}{% set x=a %}{% endfor %}x={{x}}').render(items=[2000]))"
   x=1000
   ```
   Fix: use `{% set ns = namespace(hp_kw=1000) %}` and `{% set ns.hp_kw = a.capacity|int %}` then render `{{ ns.hp_kw }}`. Also: the rest of decision 1's framing ("If senior insists ... capacity must rise to `hp_mid_2000`... — Aggressive pathway") presumes Balanced has hp_mid_1000. With Balanced already on hp_mid_2000 the entire decision needs reworking, not just a number swap.

2. **§9 Decision 2, hardcoded `eb_2000` is wrong** (report line 384, template line 462): renders "adding `eb_2000` (Conservative) adds 2,000 kW" — but Conservative's §4.1 action sequence carries `eb_4000` (4,000 kW). The "eb_2000" identifier and the "2,000 kW" load number are hardcoded literals in the template that did not get re-templated when Conservative's stack changed (Conservative was eb_2000 in iter-0 but is eb_4000 from iter-1 onward — this defect actually pre-dates iter-2 but was masked by the live-figure work and now stands alone).

3. **§4.1 "HP capacity rationale" paragraph is stale** (report line 147, template line 197): the paragraph defends `hp_mid_1000` as Balanced's choice and frames `hp_mid_2000` as Aggressive-only. Balanced now uses `hp_mid_2000`. Reading §4.1 as a whole, a senior reviewer hits a direct contradiction: the rationale paragraph argues hp_mid_1000 is right for Balanced, then the action-sequence table immediately below assigns hp_mid_2000 to Balanced.

These are narrative-integrity defects, not engine defects — the engine produced the right numbers and the X/Y impact values in §9 are live and correct. But the report contradicts itself in three places, which a senior reviewer will catch on first read.

## Issues remaining (declared as warnings — no iter-4 per protocol)

Per the iter-3 escalation rule ("do NOT keep iterating past N=3"), the three defects above are declared as remaining gaps:

- **WARNING — §9 Decision 1 HP-capacity number stale.** Jinja2 loop-scope bug at `v0_pathway_report.md.j2:452–457`. `_hp_kw` always renders 1000. With Balanced on hp_mid_2000, the decision narrative ("rise to hp_mid_2000... Aggressive pathway") also needs structural rework — Balanced *is* the hp_mid_2000 stack. Suggested fix is one-line (use `namespace`) plus a paragraph rewrite to frame the senior decision as "Balanced is sized at 2,000 kW; if site-survey hot-water steady-state load is materially lower, downsize to hp_mid_1000 (Conservative) — capex £-800k, year-15 reduction X → Y%".
- **WARNING — §9 Decision 2 hardcoded `eb_2000` mismatches Conservative's eb_4000.** Template line 462 has the EB tech ID and load (2,000 kW) hardcoded. Should read from `_cons.actions` and pick the electrode_boiler entry's `tech_id` and `capacity`.
- **WARNING — §4.1 HP capacity rationale paragraph (template line 197) is hardcoded prose anchored on the old (iter-1) Balanced stack.** Either re-template it from `_bal.actions` (rendering whichever HP size Balanced lands on) or rework the paragraph to defend hp_mid_2000 as Balanced's choice and frame hp_mid_1000 as the smaller-capacity alternative.

None of these block the engine's correctness or the report's traceable numbers. They block the report's prose-level coherence. **Recommend:** merge with these three warnings filed against v0.2; do not start iter-4. A senior reader of the merged report should be told upfront that §4.1 rationale and §9 decisions 1–2 contain known stale prose, fix scheduled for v0.2 alongside the renderer-template hardening.

## Issues newly introduced
- See three items above. All in render templates, not engine.
- No regressions in tests (222/222), provenance (26 entries, all live), methodology, or carbon roll-up.

## Recommended next iteration prompt for Builder
None — iter-3 cap reached. Three template-prose defects declared as warnings (above). Merge decision is the user's call.
