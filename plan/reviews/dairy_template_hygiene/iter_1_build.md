## Iteration: 1 of 3
## Branch: feature/dairy-report-fixes
## Commit: 940dead (post-amend; pre-amend sha 4860a73 referenced in commit message body)
## Tests: 222/222 (pytest decarb -q --ignore=decarb/corpus/tests --ignore=decarb/tests/test_retrieve_reference_docs.py; both ignored suites pre-fail at collection on this branch back to 7f63c0a — DB-dependent, not introduced here)
## Report rendered: backend/decarb/runs/GOLDEN_DAIRY_5MW_20260506T072857Z.md

### Issues addressed from iter_3 review (originating brief)

- **Defect 1 — §9 Decision 1 Jinja loop-scope bug + stale framing.** Replaced the `{% set _hp_kw = a.capacity|int %}`-inside-`{% for %}` pattern at template lines 449–457 with a Jinja2 `namespace(...)` block that walks each pathway's `actions` and captures `bal_hp_id`/`bal_hp_kw`, `cons_hp_id`/`cons_hp_kw`, `cons_eb_id`/`cons_eb_kw`, `agg_hp_id`/`agg_hp_kw`. Verified the namespace pattern empirically before editing (`python3 -c "from jinja2 import Template; ..."`). Decision 1 prose rewritten: Balanced is now framed as the senior recommendation at `hp_mid_2000` (2,000 kW) and the senior decision is "downsize to hp_mid_1000 if site-survey hot-water steady-state load is materially lower than parsed envelope" — capex/reduction/NPV impact rendered live from `_bal` and `_cons` pathway records, with the up-size to `hp_mid_2000` framed as a Pareto comparison only when the rendered Aggressive HP is strictly larger than Balanced. Template lines 449–472.

- **Defect 2 — §9 Decision 2 hardcoded eb_2000 / 2,000 kW.** Replaced the two literals with `{{ _cons_eb_id_disp }}` and `{{ _cons_eb_kw_disp|fmt_int }}`, where the `_disp` variables resolve to the namespace-extracted Conservative EB tech_id and capacity, with `'eb_2000'` / `2000` fallbacks for the case where `pathway` is None (no-pathway test fixtures). For the live dairy run, Conservative carries `eb_4000` and the rendered prose now reads "adding `eb_4000` (Conservative) adds 4,000 kW". Template line 473.

- **Defect 3 — §4.1 stale HP-capacity rationale paragraph (full re-templating).** Inserted a `rat_ns = namespace(...)` block at template lines 197–204 that walks `_bal_pw.actions`, `_cons_pw.actions`, `_agg_pw.actions` and extracts each pathway's HP id+capacity. The paragraph is rewritten to defend whichever HP capacity Balanced lands on (`{{ rat_ns.bal_hp_id }}` / `{{ rat_ns.bal_hp_kw }}`), name the smaller HP (Conservative's `{{ rat_ns.cons_hp_id }}`) as the natural downsize alternative, and only mention an Aggressive up-size when the Aggressive HP is strictly larger. Guarded with `{% if rat_ns.bal_hp_kw %}` so the paragraph is skipped if Balanced has no HP entry. Now reads "Balanced lands on `hp_mid_2000` (2,000 kW)" — internally consistent with the action-sequence table directly below.

### Files modified

- `backend/decarb/render/templates/v0_pathway_report.md.j2` — three template-prose fixes per the brief; no engine, test, or methodology files touched. Section §4.1 rationale (lines 197–207) and §9 decision setup + decisions 1, 2 (lines 449–474) re-templated against pathway action records.

### Verification I did myself

Strings in the rendered report `backend/decarb/runs/GOLDEN_DAIRY_5MW_20260506T072857Z.md`:

- §4.1 line 147: "Balanced lands on `hp_mid_2000` (2,000 kW) — sized to cover the hot-water peak ... The smaller `hp_mid_1000` (1,000 kW) sits on the Conservative pathway and is the natural downsize" ✓ — internally consistent with the Balanced action-sequence row at line 186 (`hp_mid_2000`, 2,000 kW thermal) and Conservative row at line 166 (`hp_mid_1000`, 1,000 kW thermal).
- §9 Decision 1 line 383: "Balanced HP sized at `hp_mid_2000` (2,000 kW) ... downsize to `hp_mid_1000` (1,000 kW) ... Capex impact: Balanced £1,554,000 → Conservative £1,092,000 (net of grant); year-15 reduction: **47.5%** → **38.7%**; NPV: £36,773 → £-22,765." ✓ — all four numbers cross-checked against §4.1 named-pathway tables (line 178: Balanced capex £1,554,000, NPV £36,773, reduction 47.5%; line 158: Conservative capex £1,092,000, NPV £-22,765, reduction 38.7%).
- §9 Decision 2 line 384: "2,000 kW HP at COP ~3.1 draws ~645 kW; adding `eb_4000` (Conservative) adds 4,000 kW" ✓ — eb_4000 / 4,000 kW now matches Conservative's action-sequence row at line 167 (`eb_4000`, 4,000 kW thermal). 645 kW is `(2000/3.1)|round(0)|int = 645` ✓.
- §9 senior-decision count gate: "4 primary decisions ✓" — the post-render gate at `decarb/render/__init__.py:220` requires ≥4 "**Senior to confirm:" markers; rendered report contains 4. Tests confirm ✓.
- Provenance Appendix A entry count: 26 (unchanged from iter-2). No provenance loss.
- Test suite: `pytest decarb -q --ignore=decarb/corpus/tests --ignore=decarb/tests/test_retrieve_reference_docs.py` → 222 passed, 1 skipped (pre-existing integration mark). Both ignored suites already fail at collection on commit `7f63c0a` (pre-iter-3) — DB-dependent, not introduced by this iteration.

### Open questions / notes for Reviewer

1. **Brief vs engine-gate conflict on Decision 2 conditional.** The brief (§ "Defect 2 fix") says: *"If no electrode-boiler entry exists in `_cons.actions`, the surrounding paragraph should not render at all (guard with an `{% if %}`)."* I implemented this initially and it broke `test_no_jinja_undefined_leaks[dairy_bundle|brewery_bundle|softdrinks_bundle]` and `test_no_nan_strings[softdrinks_bundle]` — those fixtures (in `decarb/engine/tests/test_render.py:50`) call the renderer **without** `pathway_result`, so `pathway` is None and the EB-conditional renders only 3 senior decisions, which trips the post-render assertion at `decarb/render/__init__.py:220` (`senior_to_confirm_count < 4 → AssertionError`).

   I reverted the unconditional skip and instead made the EB tech_id / capacity dynamic with hardcoded fallbacks (`'eb_2000'` / `2000`) for the no-pathway case. This satisfies the dairy live-render fix (the rendered report shows `eb_4000` / 4,000 kW correctly) and keeps the test suite at 222/222, but the no-EB-in-Conservative edge case the brief flagged is **not** fully suppressed — it would render with the legacy `'eb_2000'` literal. Reviewer to adjudicate: is the right fix here to (a) accept the fallback as an acceptable v0 compromise, (b) make the conditional conditional only on `pathway` being truthy AND no EB in `_cons.actions` (skip cleanly only when the pathway optimiser was run but Conservative lands on a no-EB stack), or (c) loosen the post-render senior-decision-count gate to ≥3 with an EB-conditional decision-2? Option (b) is cleanest in code; option (c) requires touching `decarb/render/__init__.py` which the brief said was out of scope.

2. **Whitespace between decisions 1 and 2.** With `trim_blocks=True` in the Jinja env, the `\n` immediately after the `{% endif %}` that closes the up-sizing clause on decision 1 was stripped, jamming items 1 and 2 onto the same rendered line. Fixed by inserting an explicit blank line between the two source lines. Verified in the rendered report (lines 383, 384 are now distinct list items). No other inter-decision boundary needed the same fix because items 2→3, 3→4 don't end with a `%}` block tag.

3. **`_hw_avg_kw` formatting cosmetic.** The hot-water-average constant `1287` is rendered as "1287 kW" (no thousands separator) in §9 Decision 1. This was the rendered form prior to iter-3 too — same `{{ _hw_avg_kw }}` template expression. Not in the brief's scope. Flagging for awareness only; if the reviewer wants `1,287 kW` for consistency with the rationale paragraph, change the call to `{{ _hw_avg_kw|fmt_int }}` (one-character edit).

4. **Engine code untouched.** No files outside `backend/decarb/render/templates/v0_pathway_report.md.j2` were modified. No changes to engine, tests, or methodology docs.
