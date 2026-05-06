# Task: multisite_render_and_architecture

Carved out of `plan/reviews/assessment_2026_05_06_fixes/brief.md`
Phase 6 for supervisor execution. The first five phases of that
larger task have already shipped to
`feature/assessment-2026-05-06-fixes` (commits 652fcca, 2a30a69,
6fceff3, 1f609b1, c65acb2…cbb66ee, 4514d23, 5074b2a). This is the
final round before the whole feature branch merges to main.

## Branch

Working branch: `feature/assessment-2026-05-06-fixes`. Builder /
Reviewer / Meta commit on this branch via the supervisor's normal
round protocol.

## Files in scope

- `backend/decarb/runs/GOLDEN_BREWERY_8MW_<UTC>.md` (NEW)
- `backend/decarb/runs/GOLDEN_SOFT_DRINKS_12MW_<UTC>.md` (NEW)
- `backend/scripts/regenerate_dairy_report.py` may be generalised
  into a `regenerate_site_report.py` that takes a site-id arg, OR a
  new sibling script per site can be added — Builder's choice. Note
  that `runs/` is in `.gitignore`, so the rendered reports
  themselves do NOT get committed; the script(s) that produce them
  do.
- `plan/architecture.md` — frontend row + MUNTec reuse cleanup

Files NOT in scope: any engine module, any methodology section, any
other site fixture, any other test (unless a new render path needs
its own test, in which case `test_render.py` is OK to extend).

## Read first

- `plan/architecture.md` — current state, find the stale claims to
  remove
- `backend/scripts/regenerate_dairy_report.py` — the canonical
  one-site rendering pattern (calls parse → carbon → screen →
  dispatch → pathway → MC → validate → render in order, with
  £100/38% overlay anchor and `max_reduction_positive_npv` rule)
- `backend/decarb/tests/sites/brewery_8mw.json` and
  `soft_drinks_12mw.json` — read each end-to-end before rendering;
  flag anything that's clearly dairy-specific in the fixture
  (sector / GMP language / refrigerant choice)
- `backend/decarb/runs/GOLDEN_DAIRY_5MW_<latest>.md` — the
  reference rendered report; the brewery and soft_drinks reports
  should mirror its structure

Engine baseline at start of this round: **279 tests passing.** Bug
#1 (baseline-y0 divergence) was fixed in commit 5074b2a. The
`_implied_baseline_boiler_efficiency` helper is the right anchor
for any new baseline-trajectory loops you add (already used in
regenerate_dairy_report.py).

## Sub-task 1: multi-site GOLDEN render

Render `brewery_8mw` and `soft_drinks_12mw` reports via the same
pattern as `regenerate_dairy_report.py`. Two acceptable Builder
choices:

**(A)** Generalise `regenerate_dairy_report.py` into
`backend/scripts/regenerate_site_report.py`, taking a `--site`
argument (`dairy_5mw`, `brewery_8mw`, `soft_drinks_12mw`). Keep
`regenerate_dairy_report.py` as a thin wrapper for backwards
compat. Run it once for each site to produce the new GOLDEN files.

**(B)** Add `regenerate_brewery_report.py` and
`regenerate_soft_drinks_report.py` as siblings, copy-paste with the
site-id swapped. Acceptable but dirtier.

(A) is preferred. Document the choice in `iter_<N>_build.md`.

For each site:

- Use the same overlay anchors as dairy: `ETS=£100/tCO₂e`,
  `IETF grant fraction=0.38`, `pathway_selection_rule="max_reduction_positive_npv"`.
- Use the implied baseline boiler efficiency
  (`_implied_baseline_boiler_efficiency`); do not hardcode 0.85.
  brewery's implied efficiency is ~0.855 (close to default);
  soft_drinks is exactly 0.85.
- Pipe the result through `validate_pathway`; the fresh report
  must render §10 with `Overall: PASSED`.
- The MC fixture currently uses `_build_dairy_mc` which is
  dairy-specific. Generalise it OR construct the MC inputs
  inline in the regen script.

After rendering each report, **read it end-to-end yourself**.
Specifically check for:

1. Cross-section text that reads oddly for the non-dairy site
   (e.g. dairy-specific GMP language appearing in brewery, "Cleaning
   In Place" references in soft_drinks). Most prose is templated and
   should be safe, but the §9 Senior Decisions blocks were drafted
   against dairy and may carry dairy-specific framing.
2. Numbers that are clearly off (e.g. NPV >> capex × 10×, year-15
   reduction > 100%, simple > discounted payback — though that last
   is now structurally guarded).
3. Validate §10: `Overall: PASSED` with all error-severity checks
   passing. Warnings/infos are acceptable.

If any cross-section text reads oddly, **do NOT fix it in this
round**. Open a follow-up note in `iter_<N>_review.md` listing the
specific anomalies (e.g. "brewery §9 Decision 2 references dairy's
EB capacity"). That's a separate per-site template-hygiene round.

## Sub-task 2: architecture.md cleanup

`plan/architecture.md` carries two stale claims:

1. The "Stack" table includes a row:
   `| Frontend | Next.js (existing) | Already there, fine |`
   The frontend was deleted from the working tree on purpose.
   Remove this row entirely.

2. The "Reuse from existing MUNTec backend" section lists module
   mappings (`calculator.py → ...`, `simulation.py → ...`, etc.)
   for code that no longer exists in the repo. Replace the whole
   table + paragraph with a single short note:

   > "The decarb engine is a clean-slate implementation. Earlier
   > MUNTec residential heat-pump code was evaluated for reuse and
   > discarded — the industrial scale and thermodynamic depth
   > required first-principles redesign."

3. Leave the "Out of scope for v1" section's "Frontend polish" line
   alone; that's still accurate.

## Acceptance criteria

Each tagged BINDING (failure → ISSUES_FOUND) or ASPIRATIONAL
(failure may be declared as v0.2 follow-up if Builder documents why
in `iter_<N>_build.md`).

1. **[BINDING]** A `regenerate_site_report.py` script (or
   equivalent) exists that successfully renders
   `GOLDEN_BREWERY_8MW_*.md` and
   `GOLDEN_SOFT_DRINKS_12MW_*.md` end-to-end without raising. Both
   reports include §10 Validation Report with
   `Overall: PASSED` (zero error-severity check failures;
   warnings/infos acceptable).

2. **[BINDING]** Both new reports render the same 11 sections as
   the dairy GOLDEN: §1 Executive Summary, §2 Site Baseline,
   §3 Decarb Options Considered, §4 Pathway Analysis (incl. §4.1a
   no-reinforcement and §4.1b with-reinforcement subsections),
   §5 Carbon Trajectory and Regulatory Compliance, §6 Funding,
   §7 Implementation Roadmap, §8 Risks and Assumptions, §9 Key
   Decisions for Senior Review, §10 Validation Report, plus
   Appendix A and B.

3. **[BINDING]** `plan/architecture.md` no longer references the
   deleted frontend or the MUNTec reuse claim. The replacement
   note for the MUNTec section is in place verbatim per Sub-task 2
   item 2.

4. **[BINDING]** Engine tests still 279/279 passing — Phase 6 must
   not regress any test from prior phases.

5. **[ASPIRATIONAL]** Builder chose Option (A) generalised script
   over Option (B) per-site copies. If (B), document why in
   iter_<N>_build.md.

6. **[ASPIRATIONAL]** No cross-section dairy-specific text leaks
   into the brewery or soft_drinks reports. If any are found,
   list them in `iter_<N>_review.md` as a follow-up; they do not
   block this round.

## Iteration discipline

- N=3 cap. If iter-3 still ISSUES_FOUND, declare residuals as v0.2
  warnings and stop. Do not request iter-4.
- The reports themselves go to `backend/decarb/runs/` which is
  `.gitignore`'d; the test-of-truth is that the regen script runs
  to completion and the latest rendered files (read off-disk by
  Reviewer in their working tree) pass the structural checks.
- Do NOT modify any engine module, any methodology section, or any
  other site fixture in this round. The bug-fix and baseline-eff
  reconciliation work is complete; further engine changes are out
  of scope here.
- After the round closes CLEAN, the founder will merge
  `feature/assessment-2026-05-06-fixes` to main as the final step
  of the assessment_2026_05_06_fixes work.

## Round-protocol reminders

- Reviewer should run cross-section status consistency check on
  both new reports (Tier-1 reviewer.md hardening): every module
  with `IMPLEMENTED v0` badge should not have prose elsewhere
  claiming it's deferred / stub / roadmap.
- Reviewer should also check `validate.mc_pathway_consistency` and
  `validate.standards_register_no_dupes` warnings on the new
  reports — if they fire, note in iter_<N>_review.md as
  consistency-with-dairy follow-ups (those checks fire warning on
  dairy too post-bug-fix; same expected here).
