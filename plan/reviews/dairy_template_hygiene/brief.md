# Task: dairy_template_hygiene

## Branch and scope

- Working branch: `feature/dairy-report-fixes` (start from current HEAD, post iter-2)
- Files in scope: `backend/decarb/render/templates/v0_pathway_report.md.j2` ONLY
- Files NOT in scope: any engine code under `backend/decarb/engine/`, any test code, any other template, any methodology doc
- Engine state must remain at 222/222 tests passing throughout

## Background (read before starting)

- `plan/reviews/dairy_report_fixes_iter3.md` — the iter-3 critique that identified these defects
- `backend/decarb/runs/GOLDEN_DAIRY_5MW_20260505T174753Z.md` — the report containing the rendered defects
- `docs/methodology/methodology.md` §2.2 (i) and (ii) — no-arithmetic, calculation provenance principles that these defects violate

The previous build (iter-2, commit `7f63c0a`) changed Balanced's stack from `hp_mid_1000 + eb_2000 + tes_8000` to `hp_mid_2000 + eb_2000 + tes_8000`. Three pieces of surrounding template prose were anchored on the old stack and are now structurally stale. They are not cosmetic — they cause the rendered report to display capacity numbers and tech identifiers that contradict the action sequence in the same report. This is a numerical-integrity defect under methodology §2.2 (every numeric output must trace to the originating deterministic calculation).

## Three defects to fix

### Defect 1 — §9 Decision 1 HP-capacity render

Location: `backend/decarb/render/templates/v0_pathway_report.md.j2`, approx lines 452–457.

Symptom: report renders "HP capacity sized to hot-water sub-demand only (**1000 kW**)" but Balanced's action sequence carries `hp_mid_2000` (2000 kW).

Root cause: Jinja2 loop-scope bug. `{% set _hp_kw = a.capacity|int %}` inside `{% for a in _bal.actions %}` does not propagate to outer scope, so `_hp_kw` stays at its default of 1000.

Fix:
1. Replace the local `set` with a Jinja2 `namespace`:
   ```
   {% set ns = namespace(hp_kw=1000) %}
   {% for a in _bal.actions %}
     {% if a.tech_family == 'heat_pump' %}{% set ns.hp_kw = a.capacity|int %}{% endif %}
   {% endfor %}
   ```
   then render `{{ ns.hp_kw }}` in the prose.
2. Rewrite the senior-decision paragraph that follows. Balanced is now hp_mid_2000; the existing prose ("If senior insists ... capacity must rise to `hp_mid_2000` ... — Aggressive pathway") presumes Balanced is at hp_mid_1000 and is structurally wrong. Reframe as: "Balanced is sized at 2,000 kW; if site-survey hot-water steady-state load is materially lower than the parsed envelope, downsize to hp_mid_1000 (the Conservative HP). Capex impact: X → Y; year-15 reduction: A% → B%." Live-render X/Y/A/B from the Conservative and Balanced pathway records — do not hardcode.

Verify against the Jinja2 namespace pattern empirically before committing.

### Defect 2 — §9 Decision 2 hardcoded `eb_2000`

Location: same template, approx line 462.

Symptom: report renders "adding `eb_2000` (Conservative) adds 2,000 kW" but Conservative's action sequence carries `eb_4000` (4000 kW). The tech_id and the load number are hardcoded literals.

Fix: read the electrode-boiler entry from `_cons.actions` (find the entry where `tech_family == 'electrode_boiler'`), render its `tech_id` and `capacity` dynamically. Use the same `namespace` pattern as Defect 1 to escape the loop scope. If no electrode-boiler entry exists in `_cons.actions`, the surrounding paragraph should not render at all (guard with an `{% if %}`).

### Defect 3 — §4.1 HP-capacity rationale paragraph

Location: same template, approx line 197.

Symptom: paragraph defends `hp_mid_1000` as Balanced's choice and frames `hp_mid_2000` as Aggressive-only. Balanced now uses `hp_mid_2000`. The paragraph contradicts the action-sequence table that follows it in the same section.

Fix (preferred — full re-templating):
- Read Balanced's HP capacity from `_bal.actions` via the namespace pattern.
- Read the smaller alternative from `_cons.actions` for symmetry.
- Render a paragraph that defends whichever HP capacity Balanced lands on, naming the smaller alternative as the Conservative downsize option, with capex/reduction impact rendered live from the relevant pathway records.

Fix (fallback — prose rewrite only): rewrite the paragraph to defend `hp_mid_2000` explicitly and name `hp_mid_1000` as the Conservative downsize. Hardcode only if re-templating from `_bal.actions` is genuinely infeasible; explain why in iter1_build.md.

## Acceptance criteria

1. `cd backend && pytest` — 222 passed, 0 failed, 0 newly skipped.
2. Run the dairy regenerate script (path: `backend/scripts/regenerate_dairy_report.py` on this branch). The fresh report must satisfy:
   - §9 Decision 1: rendered HP capacity reads "2,000 kW" (not 1,000 kW), and the senior-decision framing references hp_mid_1000 as the downsize alternative, not hp_mid_2000 as the upsize.
   - §9 Decision 2: rendered electrode-boiler tech_id reads `eb_4000` and load reads "4,000 kW".
   - §4.1: rationale paragraph defends Balanced's actual HP size (2,000 kW). No contradiction between the rationale paragraph and the §4.1 action-sequence table.
3. No new HIGH-severity warnings in the run log.
4. Numerical-integrity contract: every rendered capacity number and tech_id in §4 and §9 traces to an entry in the relevant pathway record (`_bal.actions`, `_cons.actions`, `_agg.actions`). No hardcoded capacity literals or tech_id literals remain in §4 and §9.
5. Provenance Appendix A entry count is unchanged or higher (no provenance loss).

## Iteration discipline

- N=3 cap. If iter-3 review still says ISSUES_FOUND, declare residuals as warnings against v0.2 and create `triggers/complete`.
- Do not modify engine code under any circumstance. If a defect appears to require an engine change, write iter<N>_build.md saying so and stop without committing. The Reviewer will adjudicate.
- Do not add new template features unrelated to the three defects. Template-hardening (e.g., extracting a shared `find_action_by_family` macro) is permitted only if it is the cleanest way to fix one of the three defects and it is fully exercised by the fix.
