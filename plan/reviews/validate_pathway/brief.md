# Task: validate_pathway

Carved out of `plan/reviews/assessment_2026_05_06_fixes/brief.md`
Phase 5 (S1) for supervisor execution. The other phases of that
larger task have already shipped to
`feature/assessment-2026-05-06-fixes` (Phases 1, 2, 3, 4 — commits
652fcca, 2a30a69, 6fceff3, 1f609b1). This round implements Phase 5
on the same branch via the Builder/Reviewer/Meta-reviewer protocol.

## Branch

Working branch: `feature/assessment-2026-05-06-fixes`. The supervisor
launches Builder/Reviewer/Meta on this branch (do not switch). The
final merge of all six phases into `main` happens after this round
plus Phase 6 (handled separately, inline).

## Files in scope

- `backend/decarb/engine/validate.py` — NEW module
- `backend/decarb/engine/tests/test_validate.py` — NEW tests
- `backend/decarb/tools.py` — replace the `validate_pathway` stub
  (line ~419) with a live wrapper; update `TOOL_SCHEMAS` entry
- `backend/decarb/agent.py` — gate `render_report` on
  `validate_pathway` having returned `passed=true`
- `backend/decarb/prompts/orchestrator_v0_1.txt` — add the tool
  ordering instruction
- `backend/decarb/render/__init__.py` — accept a new
  `validate_result` kwarg and pass it to the template
- `backend/decarb/render/templates/v0_pathway_report.md.j2` — add a
  new `## §10 Validation Report` section before the appendices
- `backend/scripts/regenerate_dairy_report.py` — call
  `validate_pathway` after MC and before render; pass result through
- `docs/methodology/methodology.md` — flip §4.4 status badge
  `ROADMAP v0.2` → `IMPLEMENTED v0` and rewrite the §4.4 paragraph;
  bump version to 0.4 and add a revision-history row.

Files NOT in scope: any other engine module, any other test, the MC
module, any other tool's stub, methodology sections other than §4.4
+ document control (and incidental wording adjusting to match the
new badge — keep §1 status preamble consistent with the new state).

## Read first

- `plan/assessment_2026-05-06.md` §S1 for the original framing
- `docs/methodology/methodology.md` §4.4 (and §1 status preamble that
  references it)
- The pathway record schema in `backend/decarb/engine/pathway.py`
  return statement (around line 690)
- The MC record schema in `backend/decarb/engine/uncertainty.py`
- The render bundle pattern in `backend/decarb/render/__init__.py`
- The tool registration pattern in `backend/decarb/tools.py`
  (look at how `monte_carlo_uncertainty` was wired — that's the
  template for this work)

Engine baseline at start of this round: **268 tests passing.**

## Architecture

`validate.py` exposes one public function:

```python
def validate_pathway(
    *,
    site_brief: dict,
    energy_profile: dict,
    screening: dict,
    baseline_carbon: dict,
    dispatch: dict,
    pathway: dict,
    monte_carlo: dict | None = None,
) -> dict:
    """Run cross-module consistency and arithmetic checks on the full
    engine bundle before render. Returns:

        {
          "passed": bool,
          "checks": [
            {
              "check_id": str,
              "severity": "error" | "warning" | "info",
              "passed": bool,
              "message": str,
              "details": dict,
            },
            ...
          ],
          "summary": {"errors": int, "warnings": int, "infos": int},
          "standards_cited": [...],
          "provenance": [...],
        }
    """
```

`passed` is True iff zero error-severity checks failed.

## Required checks (v0)

Each is a small function in `validate.py` returning a `check` dict.
The public function aggregates them.

1. `discounted_ge_simple_payback` (severity error). For each named
   pathway in `pathways_with_reinforcement` (and also each of
   `pathways_no_reinforcement` if non-empty / not infeasible), assert
   `discounted_payback_years >= simple_payback_years` (or both None,
   or simple-non-None & discounted-None — the same logic the Phase 2
   tests encode).
2. `screen_pathway_grid_consistency` (severity error). Assert that no
   action in any `pathways_no_reinforcement` named pathway has
   `requires_grid_decision=True`. (Phase 3 invariant — encoded as a
   pre-render gate.)
3. `carbon_balance_year_15` (severity error). For each named pathway,
   assert
   `(baseline_year_0_carbon_t_co2e - year_15_total_carbon_t_co2e)
   / baseline_year_0_carbon_t_co2e ≈ year_15_reduction_pct / 100` to
   within 0.5 percentage points. (Phase 4 fields are now exposed.)
4. `exec_summary_baseline_consistency` (severity warning). The
   baseline-y0 number used by §1 of the report (the pathway record's
   `baseline_year_0_carbon_t_co2e`) and `baseline_carbon.totals.scope_1_2_loc_t_co2e`
   should agree to within 5%. They currently differ by ~7% on dairy
   because of EF/grid-intensity divergence between
   `compute_baseline_carbon` and the pathway dispatch baseline; this
   is the very inconsistency Phase 4's §1 rewrite surfaced. **Wire
   the check; let it fire as a warning**; the underlying engine
   reconciliation is a follow-up ticket, not part of this round.
5. `provenance_arithmetic_self_consistent` (severity error).
   Iterate provenance rows whose `method` string contains a `=` and a
   pattern of the form `<a> p/kWh × <b> kWh = £<c>` or
   `<a> × <b> = <c>`. For each parsed triple, assert
   `|rate × volume - product| < max(1.0, 0.005 × |product|)`. Rows
   that don't parse → `info`, not `error` (we don't penalise
   non-arithmetic provenance text).
6. `mc_pathway_consistency` (severity warning, only if
   `monte_carlo is not None`). Assert
   `monte_carlo.npv_distribution.p50_gbp` is within ±20% of
   `pathway.pathways.balanced.npv_gbp`.
7. `shortlist_in_pathway_or_excluded` (severity error). For every
   action tech_id in any named pathway (both with- and
   no-reinforcement triples), assert it appears in
   `screening.shortlist` OR
   `screening.excluded_pending_grid_decision` (the action knows it
   carries a requires_grid_decision flag).
8. `standards_register_no_dupes` (severity info). Across the union
   of `standards_cited` from every input dict, assert no duplicates
   after normalising whitespace.
9. `methodology_status_matches_engine` (severity warning). Read
   `docs/methodology/methodology.md`. For each `### 3.X module name
   ▍ <BADGE>` line, derive the engine implementation status (presence
   of the corresponding key in the engine bundle, e.g. `pathway`
   non-None and not stub). Mismatch → warning. **Document
   limitation:** v0 implementation can hard-code the §3.X-to-key
   mapping; a future v0.2 enhancement is to derive it from a tool
   registry.

## Tool wiring

In `backend/decarb/tools.py`:

1. Replace the `validate_pathway` stub returning `{"_stub": True}`
   with a live wrapper that:
   - reads `site_brief`, `energy_profile`, `screening`,
     `baseline_carbon`, `dispatch`, `pathway`, `monte_carlo` from
     `_site_context["engine_results"]`
   - calls `decarb.engine.validate.validate_pathway(**bundle)`
   - returns the compact `{passed, summary, standards_cited}` to the
     LLM
   - persists the full result (with checks list) at
     `_site_context["engine_results"]["validate_pathway"]` so the
     renderer can include it in §10
2. In `TOOL_SCHEMAS`, drop "STUB" language. Description:
   > "Cross-module consistency and arithmetic check over the full
   > engine bundle. Call this AFTER all other tool calls and BEFORE
   > render_report. Returns `passed: bool` plus a structured check
   > list. If `passed=false`, fix the underlying engine output; do
   > NOT proceed to render."

## Agent loop integration

In `backend/decarb/agent.py`, gate the `render_report` tool: when the
LLM requests `render_report`, the dispatch wrapper checks
`_site_context["engine_results"].get("validate_pathway", {}).get("passed")`.
If False or missing, return an error message to the LLM so it
investigates the failing checks before re-trying render.

## Render integration

In the renderer, accept a new optional `validate_result` kwarg
(parallel to `pathway_result`, `uncertainty_result`). Pass it
through to the template as `validate`.

In the template, add a new section right before the appendices:

> ## §10 Validation Report  ![status](https://img.shields.io/badge/status-IMPLEMENTED%20v0-green)

Listing each check, its severity, and pass/fail status. Compact
table format. If any error has fired and the report is still being
rendered (unusual — agent loop blocks render in this case, but for
deliberate-debug runs), prefix the report with a giant **DRAFT —
VALIDATION FAILED — DO NOT DISTRIBUTE** banner.

## Methodology doc

After tests pass: in `docs/methodology/methodology.md`:

1. Flip §4.4 status from `*Status: ROADMAP v0.2*` to `*Status:
   IMPLEMENTED v0*`. Rewrite the section paragraph to describe the
   actual check list above.
2. Update the §1 status preamble to reflect the new state: §4.4 self-
   critique loop is now implemented; the "four modules + multi-stage
   + validate_pathway" list shrinks to "four modules + multi-stage".
3. Bump version to 0.4 (header line + document control table); add
   revision-history row.
4. The Phase 1 acceptance criterion was that
   `grep "ROADMAP v0.2"` returned exactly 6 lines. After this Phase,
   it must return exactly **5** lines (§3.4 multi-stage, §3.8, §3.9,
   §3.10, §3.11). This is expected — Reviewer must NOT flag the
   reduction as a regression.

## Acceptance criteria

Each tagged BINDING (failure → ISSUES_FOUND) or ASPIRATIONAL
(failure may be declared as v0.2 follow-up if Builder documents why
it's structurally unreachable in `iter_<N>_build.md`).

1. **[BINDING]** All 9 checks implemented as separate functions in
   `validate.py`, exported via the public `validate_pathway`
   function.
2. **[BINDING]** Fresh dairy GOLDEN report renders §10 Validation
   Report. All `error`-severity checks pass on the dairy fixture
   under the standard regenerate-script invocation
   (ets=£75, grant=0.30, max_reduction_positive_npv).
3. **[BINDING]** Mutation testing: deliberately re-introduce one of
   D1 (drop the y0 early-return revert), D2 (re-include
   requires_grid_decision tech in pathways_no_reinforcement), or D5
   (drop precision in CCL string), run `validate_pathway`, confirm
   `passed=false` with the right check_id in the failure list. Don't
   merge the mutation — Builder demonstrates by running it manually
   in `iter_<N>_build.md` and quoting the output, OR ships a unit
   test that does the same.
4. **[BINDING]** `tools.py:validate_pathway` no longer returns
   `_stub: True`. Live wrapper + schema updated.
5. **[BINDING]** Agent loop gates render_report on
   `validate_pathway.passed`. The gate is exercised by at least one
   test that constructs a fake context with passed=false, requests
   render_report, and asserts the LLM gets the corrective message
   (not the rendered report).
6. **[BINDING]** Methodology §4.4 flipped to `IMPLEMENTED v0`. §1
   preamble adjusted. Version 0.4. Revision-history row added.
   `grep "ROADMAP v0.2" docs/methodology/methodology.md` returns
   exactly 5 lines (§3.4 multi-stage, §3.8, §3.9, §3.10, §3.11).
7. **[BINDING]** `cd backend && PYTHONPATH=. python -m pytest decarb
   -q` — baseline 268 + new tests, 0 regressions.
8. **[ASPIRATIONAL]** Check #4
   (`exec_summary_baseline_consistency`) fires as a `warning` on
   dairy — the underlying baseline-y0 inconsistency between
   `compute_baseline_carbon` and the pathway dispatch baseline is a
   known v0.2 reconciliation ticket, not in scope here. If Builder
   chooses to fix the underlying inconsistency in this round, that's
   a scope expansion that needs explicit justification in
   `iter_<N>_build.md`.
9. **[ASPIRATIONAL]** Mutation-test infrastructure scales — i.e.,
   re-introducing D1/D2/D5 is straightforward as a one-line revert,
   not a multi-file surgery. Builder may add a small `validate.py`
   helper or a parametric test fixture if that helps.

## Iteration discipline

- N=3 cap. If iter-3 Reviewer still ISSUES_FOUND, declare residuals
  as v0.2 warnings and stop. Do not request iter-4. The supervisor
  honours the cap.
- Do not refactor pathway.py, dispatch.py, screen.py, carbon.py,
  uncertainty.py beyond what's strictly needed to expose fields the
  validators consume. The Phase 4 record additions
  (`baseline_year_0_carbon_t_co2e`, `year_15_total_carbon_t_co2e`,
  `ccl_breakdown`) are already in place.
- Do not add new agent tools beyond completing the
  `validate_pathway` registration.
- After landing the engine module, `rg` for any `_stub` references in
  the codebase to confirm none claim validate_pathway is still a
  stub elsewhere (anchored-prose hygiene rule from prior rounds).
- The Reviewer should specifically run the cross-section status
  consistency check (Tier-1 reviewer.md hardening): every module
  flipped to `IMPLEMENTED v0` here must not have prose elsewhere
  claiming it is deferred / stub / roadmap. Rendered report and
  methodology doc are the highest-yield places to grep.
