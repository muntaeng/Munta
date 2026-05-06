# Meta-Summary — dairy_template_hygiene round

**Founder's-eyes read.** Branch `feature/dairy-report-fixes`. Round terminated at iter-1 with verdict **CLEAN** — loop converged before the N=3 cap.

| Builder commit | Reviewer commit | Tests | Provenance | Wall-clock |
|---|---|---|---|---|
| `d09d115` (07:42) | `cfa82a3` (08:45) | 222 passed / 1 skipped | 26 entries | ~1h 15min from first edit to CLEAN verdict |

---

## 1. Outcome

**All three iter-3 warnings closed structurally.** No prose-only patches; the renderer now reads tech_id and capacity dynamically from `_bal/_cons/_agg.actions`. Final rendered prose:

| # | Defect | Final rendered prose (verbatim) |
|---|---|---|
| 1 | §9 Decision 1 HP-capacity stale | "*Senior to confirm: Balanced HP sized at `hp_mid_2000` (2,000 kW) against hot-water sub-demand … The senior decision is whether to **downsize** to `hp_mid_1000` (1,000 kW) … Capex impact: Balanced £1,554,000 → Conservative £1,092,000 (net of grant); year-15 reduction: **47.5%** → **38.7%**; NPV: £36,773 → £-22,765.*" Reframed: Balanced is the recommendation, hp_mid_1000 is the downsize. All four X→Y values live-rendered from `_bal`/`_cons`. |
| 2 | §9 Decision 2 hardcoded `eb_2000` | "*2,000 kW HP at COP ~3.1 draws ~645 kW; adding `eb_4000` (Conservative) adds 4,000 kW.*" Tech_id and capacity now resolve through `ns.cons_eb_id` / `ns.cons_eb_kw`. 645 kW computed as 2000/3.1 → matches. |
| 3 | §4.1 HP rationale paragraph | "*Balanced lands on `hp_mid_2000` (2,000 kW) — sized to cover the hot-water peak with the EB / gas backstop catching residual headroom. The smaller `hp_mid_1000` (1,000 kW) sits on the Conservative pathway and is the natural downsize if a site survey shows steady-state hot-water draw is materially below the parsed envelope.*" Internally consistent with the action-sequence table directly below. |

Reviewer cross-checked **14/14** rendered values against §4.1 live data. Numerical-integrity contract holds: every capacity number and tech_id in §4.1 and §9 traces back to a pathway action record.

---

## 2. Per-iteration ledger

| Iter | Role | Action | Files / scope | Outcome |
|---|---|---|---|---|
| 1 | Builder | Verified Jinja2 namespace propagation empirically *before* editing (`python3 -c "from jinja2 import Template; …"`); replaced `{% set _hp_kw = a.capacity %}`-inside-`{% for %}` with a top-of-section `namespace(...)` walked over each pathway's actions. Re-templated §4.1 rationale (lines 197–207) and §9 setup + decisions 1, 2 (lines 449–474). | `v0_pathway_report.md.j2` only — no engine, test, methodology, or other template touched. | 222/222, dairy report regen → `GOLDEN_DAIRY_5MW_20260506T072857Z.md`. |
| 1 | Builder | Surfaced a brief-vs-engine-gate conflict: brief asked for `{% if no_eb_in_cons %}skip Decision 2{% endif %}`, but the post-render gate at `decarb/render/__init__.py:220` requires ≥4 senior decisions, and three bundle fixtures call render without `pathway_result` (only 3 markers → AssertionError). Touching the gate is out of scope. Resolved with a fallback (`'eb_2000'` / `2000` literals only when `pathway` is None); flagged as Open Question 1 for Reviewer adjudication. | n/a | Documented and committed. |
| 1 | Reviewer | Independently re-ran tests (222/1 skip). Re-grepped rendered report against §4.1 action sequences for all three defects. Reproduced the Jinja2 `namespace` vs plain-`set` semantics at the shell. Did the 14-row X→Y re-derivation table from scratch. Adjudicated Builder Open Question 1 as ACCEPT (option a) — fallback compromise is correct given scope constraint. | review only | **CLEAN. .trigger_meta dropped.** |

**Loop converged at iter-1.** N=3 cap did not bind; no iter-2 / iter-3 needed. This is the first round in the project history to converge on the first build.

---

## 3. Workflow critique

- **Builder discipline: STRONG.**
  - Verified Jinja2 namespace pattern empirically before touching the template (the brief explicitly asked for this; Builder did it).
  - Stayed strictly in scope — only `v0_pathway_report.md.j2` modified. No opportunistic engine refactors. No new tests added (correctly — tests for renderer behaviour live in the existing test_render suite and were exercised at 222/222).
  - **Did not hack around the brief-vs-gate conflict.** Could have edited `decarb/render/__init__.py:220` to lower the gate to ≥3 (it would have shipped, no test would catch it). Instead Builder reverted, picked a defensible fallback, and surfaced the conflict honestly with three resolution options for Reviewer. This is the behaviour the protocol is designed to encourage.
- **Reviewer rigour: STRONG.**
  - Independent test execution, independent rendered-report verification, independent Jinja2 semantics reproduction, full 14-row cross-check from scratch — none of these relied on Builder's iter_1_build.md.
  - Adjudicated Builder's open question rather than punting.
  - Flagged the residual v0.2 hardening case (Conservative-with-no-EB → legacy `eb_2000` literal) as theoretical-only with explicit reasoning ("currently unreachable in fixtures").
- **actions.md was used as designed.** Both roles left dated entries per material decision (12 entries across two roles, ~5 minute granularity). Audit trail is now durable in the working tree, not just in commits — fixing the audit-trail fragility called out in the previous round's meta.
- **Brief authoring quality.** The previous round's meta recommended a "post-stack-change literal sweep" for Builder and a "numerical-integrity not just shape" check for Reviewer. The brief here baked both in (acceptance criterion 4: "no hardcoded capacity literals or tech_id literals remain in §4 and §9"; explicit fix recipes for all three defects). Result: one-shot convergence. **The previous round's meta-recommendations measurably worked.**
- **One brief defect.** The brief's Defect 2 fix instruction (`{% if %}` guard skip) conflicted with an engine-side gate the brief itself declared out of scope. A more careful brief author would have spotted this. Cost was small — Builder discovered it in <2 minutes, surfaced it cleanly — but a v0.2 brief-authoring guideline should be: "if a fix touches a templated section, check what post-render assertions sit downstream of it before declaring the engine out of scope".

---

## 4. Residual risk → v0.2 ticket list

1. **Conservative-with-no-EB latent case.** If the pathway optimiser is rerun under settings where Conservative drops the EB entirely, §9 Decision 2 would render the legacy `eb_2000` / `2000` fallback. Theoretical only — unreachable in current fixtures. Fix: either lower the post-render gate to ≥3 with EB-conditional decision-2, or add an alternative decision-2 (different topic) that activates when no EB is present. Engine-side change → out of scope for this round, on v0.2 list.
2. **`1287 kW` lacks thousands separator** in §9 Decision 1 (`{{ _hw_avg_kw }}` should be `{{ _hw_avg_kw|fmt_int }}`). Pre-existing from iter-2 of dairy-report-fixes. One-character fix; not in this round's scope.
3. **Two test suites pre-fail at collection** on this branch back to commit `7f63c0a` — `decarb/corpus/tests` and `decarb/tests/test_retrieve_reference_docs.py`, both DB-dependent. Not introduced by this round, not in scope. Worth a dedicated ticket — both Builder and Reviewer ran with `--ignore` flags. Walking past silent collection failures is a habit the project should not develop.

---

## 5. Recommendations for next round (Monte Carlo + Sobol on `feature/monte-carlo-uncertainty`)

**Carry over (these worked):**
- Brief that explicitly bakes in past meta-findings as acceptance criteria — produced one-shot convergence.
- Required-empirical-verification clause in the brief ("verify against the Jinja2 namespace pattern empirically before committing"). Builder did it; Reviewer reproduced it.
- `actions.md` per-decision dated logging by both roles. Durable working-tree audit trail.
- Reviewer doing the X→Y cross-check from scratch rather than trusting the Builder's verification table.
- Explicit Open-Questions surface from Builder when brief conflicts with reality, with adjudication options spelled out — Reviewer's job to pick.

**Change:**
- **Brief-authoring pre-flight check.** Before publishing a brief, the author should `rg` the codebase for assertions / gates that sit downstream of the templated section being modified. Defect 2 here had a brief-vs-gate conflict that took Builder 2min to find; with brief author's pre-flight it would have been zero.
- **Pre-existing test breakage policy.** A round should not run with `--ignore=` flags hiding collection failures. Either fix the suites, mark them `@pytest.mark.requires_db` and exclude by mark not path, or note in the brief that the suites are knowingly broken with a v0.2 ticket reference. Right now both Builder and Reviewer normalise the breakage.
- **MC + Sobol scope guardrail.** Monte Carlo work risks pulling in optimiser, dispatch, and screen simultaneously. Pre-declare the touched-files allowlist in the brief (as `dairy_template_hygiene/brief.md` did). Reviewer should reject any commit touching files outside it.

**Merge call (one line): MERGE `feature/dairy-report-fixes` to `main` NOW.** Engine clean, all iter-3 warnings closed structurally, 14/14 X→Y verified, audit trail durable. There is no engineering reason to hold.
