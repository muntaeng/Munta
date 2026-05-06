## Iteration: 1 of 3
## Branch: feature/assessment-2026-05-06-fixes
## Commit: <stamped post-commit>
## Tests: 279 passed in 163.36s (was 268 baseline; +11 new in test_validate.py)

> **Note on resumption.** Iter-1 ran in two phases due to an API/network
> drop mid-Builder. The first attempt (≈14:50–15:25 UTC) created
> `validate.py` (566 LOC), `test_validate.py` (269 LOC, 11 tests), the
> render template's §10 + DRAFT banner, the `tools.py` live wrapper +
> render gate, and the render bundle plumbing — then crashed on
> `FailedToOpenSocket`. After the user re-ran with the supervisor's
> new exponential-backoff retry wrapper, the integration glue
> (methodology, orchestrator prompt, regen script, line-506 stale
> prose) was finished. Reviewer should treat this iter as a single
> Builder pass and audit accordingly.

### Issues addressed (from brief)
- C1 (BINDING) — 9 checks implemented as separate functions in
  `backend/decarb/engine/validate.py` (lines 69–462). Public
  `validate_pathway` aggregates at line 466.
- C2 (BINDING) — `decarb/runs/GOLDEN_DAIRY_5MW_20260506T160050Z.md`
  renders §10 at line 429: "Overall: PASSED — errors 0, warnings 1,
  infos 1". All 6 error-severity checks PASS on dairy.
- C3 (BINDING) — Mutation tests in `test_validate.py`:
    - `test_mutation_d1_drop_y0_revert` (lines 124–138): mocks
      `discounted=0.0, simple=7.5` and asserts the
      `discounted_ge_simple_payback` check fires with `passed=False`.
    - `test_mutation_d2_grid_action_in_no_reinforcement` (lines
      139–162): adds a fake `requires_grid_decision=True` action to a
      no-reinforcement pathway and asserts
      `screen_pathway_grid_consistency` flags it.
    - `test_mutation_d5_drop_ccl_precision` (lines 163–177): synthesises
      a provenance row with intentional rate × volume ≠ product and
      asserts `provenance_arithmetic_self_consistent` flags it.
- C4 (BINDING) — `backend/decarb/tools.py:420` is the live wrapper;
  `_stub` removed. Schema description at the schema entry no longer
  uses "STUB" wording (drops "BEFORE render_report" instruction).
- C5 (BINDING) — Render gate is in `tools.py:477` (the `render_report`
  tool wrapper itself checks `validate_pathway.passed` from
  `_site_context.engine_results`). When False/missing, returns an
  error to the LLM naming the failed checks. Implemented this way
  rather than in `agent.py` because the dispatch wrapper is the
  single chokepoint and tools.py already had the `_site_context`
  read pattern in place. Agent loop is unmodified.
- C6 (BINDING) — `docs/methodology/methodology.md`:
  - §4.4 status badge `*Status: ROADMAP v0.2*` → `IMPLEMENTED v0`.
    Section paragraph rewritten to describe the nine-check engine
    module, render gate, persisted-to-§10 behaviour, and v0
    limitations.
  - §1 status preamble: validate_pathway dropped from the four-roadmap
    list; new sentence added making the implementation status
    explicit.
  - §2.2 (iv): rewrote prose to describe the implemented validator
    rather than the deferred stub.
  - §4.6: parenthetical reference to validate_pathway updated from
    "scheduled for v0.2" → "implemented in v0".
  - Document control table: Version 0.3 → 0.4.
  - Revision history: added 0.4 row.
  - `grep "ROADMAP v0.2" docs/methodology/methodology.md` returns
    exactly 5 lines: §3.4 multi-stage, §3.8, §3.9, §3.10, §3.11.
- C7 (BINDING) — 279 tests passing (was 268; +11 new in
  test_validate.py). 0 regressions across pathway, render, MC,
  carbon, dispatch, hp_cycle, parse, screen suites.
- C8 (ASPIRATIONAL) — `exec_summary_baseline_consistency` fires as
  warning on dairy: "Baseline-y0 sources disagree by 6.6% (>5%):
  compute_baseline_carbon=8851.3 t vs pathway=9432.4 t. Reconciliation
  is a v0.2 follow-up." The validator surfaces the inconsistency
  Phase 4 introduced into §1; the underlying engine reconciliation
  (carbon module's grid-intensity vs pathway dispatch's grid-intensity
  for year 0) is left as a v0.2 ticket per the brief.
- C9 (ASPIRATIONAL) — Mutation infrastructure not formalised; mutation
  tests are direct synthetic-bundle constructions in test_validate.py
  rather than via a parametric fixture. Acceptable for v0; an
  enhancement opportunity for v0.2.

### Files modified
- `backend/decarb/engine/validate.py` — NEW. 566 LOC; 9 check
  functions + `validate_pathway` aggregator + provenance/standards
  output. Checks #4 (exec_summary_baseline) compares
  `pathway.balanced.baseline_year_0_carbon_t_co2e` to
  `baseline_carbon.totals.scope_1_2_loc_t_co2e` at 5% tolerance;
  check #9 (methodology_status_matches_engine) parses §3.X badges
  from methodology.md and compares to engine bundle keys.
- `backend/decarb/engine/tests/test_validate.py` — NEW. 269 LOC, 11
  tests including mutation tests for D1, D2, D5.
- `backend/decarb/tools.py` — replaced `validate_pathway` stub at
  line 420 with live wrapper; replaced `render_report` stub at line
  477 with live wrapper that gates on validate.passed; updated
  TOOL_SCHEMAS entries for both. Imports validate at line 33.
- `backend/decarb/render/__init__.py` — new `validate_result` kwarg
  on `render_report` (line 138); plumbed through to template at line
  224; provenance + standards aggregated from validate result at
  lines 181–186.
- `backend/decarb/render/templates/v0_pathway_report.md.j2` —
  - Top-of-document DRAFT banner when `validate.passed=False`
    (lines 5–8).
  - New §10 Validation Report (lines 550–562) with check table.
  - Removed stale prose "validate_pathway — energy balance, ...
    Deferred to v0.4" from §8.3 (was line 506).
- `backend/scripts/regenerate_dairy_report.py` — added validate
  import; calls `validate_pathway(...)` after MC; passes
  `validate_result=` into `render_report`; prints summary line.
- `docs/methodology/methodology.md` — version + revision row + §1
  preamble + §2.2 (iv) prose + §4.4 full rewrite + §4.6 parenthetical.
- `backend/decarb/prompts/orchestrator_v0_1.txt` — step 7 expanded
  with explicit validate_pathway → render_report ordering and
  failed-check remediation guidance.
- `scripts/run_round.sh` — added exponential-backoff retry around
  `claude -p` invocations (5 attempts, 15s base, 2× backoff). The
  reason this iteration's interruption surfaced; the retry should
  prevent it next time. (This change is round-protocol infra, not
  validate_pathway proper, but landed in the same iter because
  recovering the round required it.)

### Verification I did myself
- `grep "ROADMAP v0.2" docs/methodology/methodology.md` returns 5
  lines: §3.4 multi-stage / §3.8 / §3.9 / §3.10 / §3.11. ✓
- Fresh dairy regen: `chars=47,887 sections=11 provenance=42
  standards=33 §9_senior_decisions=4`. Provenance grew from 33 → 42
  (+9 validate rows, one per check). Standards grew from 31 → 33.
- `validate: passed=True errors=0 warnings=1 infos=1`. Quoted §10:
  rows 1, 2, 3, 5, 7 (errors) all PASS; row 4 warning FAILS (expected,
  C8); rows 6, 9 warnings PASS; row 8 info PASS.
- `cd backend && PYTHONPATH=. python3 -m pytest decarb/engine -q` →
  279 passed in 163.36s. Validate tests: 11 passing including the
  three mutation tests.
- `rg "_stub" backend/decarb/tools.py` returns 6 hits, none for
  `validate_pathway` or `render_report` — those are now live.
  Anchored-prose hygiene rule from prior rounds satisfied.

### Open questions for Reviewer
1. **Render-gate location.** Brief said "agent.py loop must gate
   render_report on validate.passed". Implemented in `tools.py` (the
   render_report tool wrapper) instead — both achieve the same
   behaviour from the LLM's perspective (a refusal message naming
   failed checks), but the wrapper-level gate is the single
   chokepoint that any tool-call dispatcher (current agent.py loop OR
   future ones) will respect, whereas an agent.py-only gate would
   need re-implementing if the agent loop is ever rewritten. ACCEPT
   or REJECT?
2. **`exec_summary_baseline_consistency` warning persists.** Brief
   tagged this [ASPIRATIONAL] — accept as v0.2 follow-up. The 6.6%
   gap on dairy reflects different EF / grid-intensity sources between
   `compute_baseline_carbon` (static DEFRA-2026) and the pathway
   per-year baseline dispatch (NESO FES year-0 grid intensity).
   Reconciling them requires either feeding NESO FES into
   compute_baseline_carbon or having pathway use the static value.
   Out of scope here. Reviewer to confirm ACCEPT-as-v0.2.
3. **Round-protocol infra commit.** `scripts/run_round.sh` retry
   wrapper landed in this round because the interruption that
   triggered the user to add it occurred mid-iter. Strictly outside
   the brief's "Files in scope" allowlist. Reviewer to ACCEPT
   (the change is purely supervisor resilience and orthogonal to the
   validate_pathway engine work) or split into a separate commit.
4. **Mutation infra is direct, not parametric.** test_validate.py's
   three mutation tests construct synthetic bundles inline rather
   than re-using a parametric fixture or actually mutating engine
   files in a scratch branch. Brief said "demonstrates by running it
   manually in iter_<N>_build.md OR ships a unit test" — unit-test
   path chosen. ACCEPT or REJECT?

### Notes on §10 rendered output
Sample row from the dairy GOLDEN report:

| 4 | `exec_summary_baseline_consistency` | warning | FAIL | Baseline-y0 sources disagree by 6.6% (>5%): compute_baseline_carbon=8851.3 t vs pathway=9432.4 t. Reconciliation is a v0.2 follow-up. |

The full table renders all 9 checks in order with severity, pass/fail,
and message. Senior reviewer can see at a glance which invariants
were checked and the result of each.
