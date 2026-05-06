## Iteration: 2 of 3
## Branch: feature/assessment-2026-05-06-fixes
## Commit: <stamped post-commit>
## Tests: 282 passed, 1 skipped, 5 failed in 164.37s

The 5 failures are all in `decarb/tests/test_retrieve_reference_docs.py`
and are pre-existing — they require `OPENAI_API_KEY`, which is unset in
this environment. Identical failure list as iter-1 (matched by test
name). Engine-side count: 282 = 279 (iter-1 baseline) + 3 new gate
tests.

### Issues addressed (from brief or prior review)

- **C5 (BINDING, only outstanding miss from iter-1 review):** Added
  `backend/decarb/tests/test_tools_render_gate.py` — three tests that
  exercise the `render_report` Phase 5 gate directly:
  1. `test_render_report_blocked_when_validate_failed` — seeds
     `_site_context.engine_results.validate_pathway` with `passed=False`
     and a mix of error- and warning-severity failed checks; asserts the
     return is `{"error": "render_report blocked: validate_pathway
     returned passed=false…"}` with the failed `error` check_id and
     message in the body, and the warning check_id NOT surfaced (the
     gate filters severity == "error" only — `tools.py:502`).
  2. `test_render_report_blocked_when_validate_missing` — empty
     `engine_results`; asserts the alternate gate message
     `"render_report blocked: validate_pathway has not been called yet…"`
     fires.
  3. `test_render_report_passes_gate_when_validate_passed` — `passed=True`
     and otherwise empty bundle; asserts the gate clears (no
     `"render_report blocked"` in error) and the downstream
     missing-engine-outputs branch is reached
     (`"render_report cannot run — missing required engine outputs"`).

### Files modified

- `backend/decarb/tests/test_tools_render_gate.py` — NEW, 105 LOC, 3
  tests; autouse fixture saves/restores `tools._site_context` so tests
  don't leak into the rest of the suite.

### Verification I did myself

- `pytest decarb/tests/test_tools_render_gate.py -v` → 3 passed in
  0.69s.
- `pytest decarb -q --ignore=decarb/corpus` → `5 failed, 282 passed,
  1 skipped, 1 warning in 164.37s`. Net change vs iter-1: +3 passing.
  Failure list is identical to iter-1 review (5 retrieval tests, all
  `RuntimeError: OPENAI_API_KEY not set or is a placeholder`).
- Quoted error message asserted by test 1:
  `"render_report blocked: validate_pathway returned passed=false. Address the following failed error-severity checks before re-requesting render_report:\n- carbon_balance_year_15 (error): Year-15 carbon balance off by 3.1pp on balanced"`.
  Matches the exact wording at `backend/decarb/tools.py:504-509`.
- No engine module touched; no template touched; no methodology touched
  — scope strictly the missing test, per Reviewer's iter-1 prescription.

### Open questions for Reviewer

None. Single-issue scope; the gate code path is now covered with both
failure modes (missing + failed) and a happy-path gate-cleared assertion.
