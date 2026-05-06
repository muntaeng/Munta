## Iteration: 1 of 3
## Branch: feature/assessment-2026-05-06-fixes
## Commit: d655b24a0cd7ee4574dace9a11342a37cfc99ed9
## Tests: 282 passed, 1 skipped (engine subset; corpus-retrieval suite excluded — DB-dependent infra, was not running pre-round either)

### Issues addressed (from brief or prior review)
- AC1 (BINDING): generalised regen script renders both new GOLDEN files end-to-end with §10 PASSED. Brewery: errors=0 warnings=0 infos=1. Soft-drinks: errors=0 warnings=1 infos=1 (same warning shape as dairy post-bug-fix per brief).
- AC2 (BINDING): both reports render the canonical 11 sections (§1–§10 + Appendix A/B) — verified by `grep -c "^## §"` returning 10 and the Appendix A/B headings appearing inline.
- AC3 (BINDING): `plan/architecture.md` Frontend row removed, MUNTec reuse table replaced with the verbatim short note from the brief.
- AC4 (BINDING): no engine module touched; engine pytest run = 282 passed, 1 skipped (no regression vs prior round).
- AC5 (ASPIRATIONAL — chose A): generalised `regenerate_site_report.py` taking `--site {dairy_5mw,brewery_8mw,soft_drinks_12mw}`. `regenerate_dairy_report.py` is now a thin wrapper that calls `regenerate("dairy_5mw")` so prior CLAUDE.md / round-protocol references continue to resolve.

### Files modified
- `backend/scripts/regenerate_site_report.py` (NEW) — generalised renderer, takes `--site`, sizes the §4.4 illustrative dispatch stack from the site's gas-boiler capacity instead of dairy's hardcoded 10 MW / 4 MW EB / 8 MWh TES.
- `backend/scripts/regenerate_dairy_report.py` — collapsed to a thin wrapper (preserves the existing entry point).
- `plan/architecture.md` — removed Frontend Stack row; replaced MUNTec reuse table + estimated-reuse paragraph with the brief's verbatim clean-slate note.

### Verification I did myself
- Brewery render: `chars=52,435 sections=11 provenance=42 standards=33 §9_senior_decisions=4 ... validate: passed=True errors=0 warnings=0 infos=1` and §10 prose reads `Overall: PASSED — errors 0, warnings 0, infos 1`.
- Soft-drinks render: `chars=47,625 sections=11 provenance=42 standards=33 §9_senior_decisions=4 ... validate: passed=True errors=0 warnings=1 infos=1` and §10 prose reads `Overall: PASSED — errors 0, warnings 1, infos 1`.
- Dairy regression render: `chars=47,621 sections=11 provenance=42 standards=33 §9_senior_decisions=4 ... validate: passed=True errors=0 warnings=1 infos=1` — identical shape to prior dairy GOLDEN, confirming the wrapper preserves behaviour.
- Section structure: `grep -c "^## §"` returns 10 on both new reports (matches dairy); `## Appendix A — Calculation Provenance` and `## Appendix B — Standards and Sources Cited` both present.
- Engine pytest: `282 passed, 1 skipped, 1 warning in 166.26s` — unchanged from pre-round count for the same exclusion set.

### Open questions for Reviewer

**Dairy-text leakage in non-dairy reports (per brief sub-task 1, items 1; flagged here for Reviewer per brief instruction "do NOT fix in this round, open follow-up note"):**

1. `GOLDEN_BREWERY_8MW_*.md` line 301 and 411 (§8.1 / §8.2-equivalent risk text) — engine-flagged warning text contains the literal `"dairy_5mw"` site-id in the capex sensitivity narrative. Source: `decarb/engine/pathway.py` warning constructor (out of scope this round).
2. `GOLDEN_BREWERY_8MW_*.md` line 449 (§9 senior decision 4) — IETF eligibility decision is parenthesised as `(food_drink / dairy_processing)` even though the site sub-sector is `brewery`. Same pattern in `GOLDEN_SOFTDRINKS_12MW_*.md` line 433.
3. `GOLDEN_BREWERY_8MW_*.md` line 490 and `GOLDEN_SOFTDRINKS_12MW_*.md` line 474 (Appendix A) — `screen_technologies` provenance row references "GMP contamination check (BRC §4.6, FSSC 22000)" which is dairy/F&D-aseptic framing; partially appropriate for any food_drink site but the GMP framing is dairy-canonical. Likely fine as-is, flagging for completeness.

These are template/engine-prose hygiene issues, not numerical or structural. Per brief, they're a separate per-site template-hygiene round (already carved out as `plan/reviews/dairy_template_hygiene/`).

**Filename naming nit (out of scope to fix):** brief expected `GOLDEN_SOFT_DRINKS_12MW_<UTC>.md` (with underscore) but the fixture's `site_id` is `GOLDEN_SOFTDRINKS_12MW` (no underscore), so the rendered filename is `GOLDEN_SOFTDRINKS_12MW_*.md`. Renaming the fixture's site_id is a fixture change, explicitly out of scope.

**Naming sub-question:** the new generalised script is invoked as `PYTHONPATH=. python3 scripts/regenerate_site_report.py --site <id>` (matching how the original dairy script was invoked — there is no `scripts/__init__.py`). If the supervisor expects `python -m scripts.regenerate_site_report`, that needs a one-line `__init__.py` add; flagging because the docstring's `python -m` form is aspirational, not currently runnable as-is.
