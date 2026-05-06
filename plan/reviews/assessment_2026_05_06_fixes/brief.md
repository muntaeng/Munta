# Task: assessment_2026_05_06_fixes

Fix every concrete defect and stale-doc issue called out in
`plan/assessment_2026-05-06.md`. This is one task with five tightly-scoped
phases. Do them in the order below. Each phase is its own
build → review → iterate → CLEAN cycle following the round protocol.
Don't bundle phases into one commit — each lands on its own.

## Branch

Start a feature branch off `main`:

```
git checkout main
git pull --ff-only origin main 2>/dev/null || true
git checkout -b feature/assessment-2026-05-06-fixes
```

Each phase commits to this branch with `[BUILD iter N] <phase>: ...`.
Final merge to main only after every phase is CLEAN.

## Read first

- `plan/assessment_2026-05-06.md` — the source review. Defects are labelled
  D1–D5 (rendered/computed) and S1–S6 (strategic). This brief addresses
  D1, D2, D3, D4, D5, S1, S2, and the architecture.md staleness from §11.
  GTM-side items (List A/B, lawyer summary, work log backfill, ex-FN
  coffees) are NOT in scope here — the user does those by hand.
- `plan/reviews/dairy_template_hygiene/brief.md` — the canonical example
  of the round protocol's tightly-scoped brief. Mirror the format of
  iter_1_build.md / iter_1_review.md / META_SUMMARY.md it produced.
- `docs/methodology/methodology.md` — section badges and §1 status
  preamble are out of date; you'll fix in Phase 1.
- `backend/decarb/runs/GOLDEN_DAIRY_5MW_20260506T115156Z.md` — the most
  recent dairy report. Most defects render here; re-render after each
  fix and confirm the defect is gone.

## Engine-state guarantee

Tests must pass at every commit. Run before each commit:

```
cd backend && PYTHONPATH=. python -m pytest decarb/engine -q
```

If any phase causes a regression elsewhere, fix it in the same phase
before committing — don't carry red tests across phases.

---

## Phase 1 — Methodology doc alignment (D3) — 10 min

**Files in scope (only):** `docs/methodology/methodology.md`

The methodology doc says investment-pathway and Monte-Carlo are ROADMAP
v0.2; the engine ships them as IMPLEMENTED v0. Fix:

1. **Line 36 (status preamble):** rewrite to:
   > "**seven engine modules are implemented and golden-test-validated
   > against three reference sites** (§3.1, §3.2, §3.3, §3.4 single-stage,
   > §3.5, §3.6, §3.7), plus the report renderer. **Four modules are
   > scheduled for v0.2** (§3.8 pinch, §3.9 safety, §3.10 grid, §3.11
   > reliability), alongside the multi-stage HP architectures noted in
   > §3.4 and the `validate_pathway` self-critique loop in §4.4."

2. **Line 160:** change `### 3.6 Investment pathway optimisation  ▍ ROADMAP v0.2`
   to `### 3.6 Investment pathway optimisation  ▍ IMPLEMENTED v0`. Update
   the section prose to past-tense / present-tense for the implemented
   parts; keep the explicit deferral of stochastic-MILP to v0.3 as a
   final paragraph (`v0 limitations:`).

3. **Line 168:** change `### 3.7 Monte Carlo uncertainty  ▍ ROADMAP v0.2`
   to `### 3.7 Monte Carlo uncertainty  ▍ IMPLEMENTED v0`. Rewrite the
   section prose to match the actual implementation: LHS + Iman-Conover
   copula, Sobol S1/ST (NOT second-order — declared deferred), Morris
   elementary effects, VaR_95/CVaR_95, `prob_carbon_target_met`,
   closed-form pathway re-evaluation. Cite Saltelli 2010, Morris 1991,
   Iman & Conover 1982, HM Treasury Green Book §A4 — the same standards
   the implementation cites. End the section with `v0 limitations:`
   listing closed-form re-evaluation, no second-order Sobol, HP-only
   capex multiplier on total capex.

4. **Document control table (line 25 region):** bump version to **0.3**,
   append a revision-history row:
   > | 0.3 | May 2026 | Methodology lead | Section badges aligned with
   > shipped engine state: §3.6 pathway and §3.7 MC moved
   > ROADMAP→IMPLEMENTED v0; §1 status preamble rewritten; §3.7 prose
   > rewritten to match shipped LHS + Iman-Conover + SALib
   > implementation. |

5. **Self-critique line 226:** keep the `### 4.4 Self-critique loop  ▍
   *Status: ROADMAP v0.2*` — that one is still genuinely a stub
   (`validate_pathway`). Phase 5 may flip it; if Phase 5 lands in this
   round, update here. If it's deferred, leave as ROADMAP.

**Acceptance criteria:**
- `grep "ROADMAP v0.2" docs/methodology/methodology.md` returns ONLY
  §3.8, §3.9, §3.10, §3.11, §4.4, and the `multi-stage architectures`
  badge in §3.4. (Six lines, no more.)
- §1 status preamble cites the correct count (seven implemented, four
  ROADMAP).
- Doc reads internally consistent — no claim that pathway/MC are
  forthcoming.

**Commit:** `[BUILD iter 1] methodology_doc_alignment: §1 + §3.6 + §3.7
badges synced with shipped engine state`

---

## Phase 2 — Discounted payback bug (D1) — 30 min

**Files in scope:** `backend/decarb/engine/pathway.py`,
`backend/decarb/engine/tests/test_pathway.py`

The bug:

```python
# pathway.py lines 226–242 — _discounted_payback_years
if y == 0 and cumulative >= 0:
    return 0.0
```

returns 0.0 whenever the IETF grant is booked y0 ahead of capex,
producing a Balanced report row of `Discounted payback (yr) | 0.0`
while simple payback is 7.54 — mathematically impossible.

Reproduction (verified):

```python
from decarb.engine.pathway import _discounted_payback_years
cf = [+593_712, -1_562_400] + [250_000] * 14   # grant y0, capex y1
print(_discounted_payback_years(cf, 0.08))     # → 0.0  (wrong)
```

**Fix:**

1. Drop the `if y == 0 and cumulative >= 0: return 0.0` early-return
   entirely. The general-case interpolation immediately above already
   handles the legitimate "project pays back inside year 1" case
   (cumulative crosses zero between y=-1 baseline=0 and y=0 cumulative).
   The early-return was incorrect because it doesn't consider whether
   later cashflows turn it negative again.

2. Decide cashflow-array convention up front. Inspect
   `_evaluate_pathway` to determine where in the array capex outflows
   land vs. grant inflows vs. operational savings. Document the
   convention as a comment at the top of `_discounted_payback_years`:

   ```python
   def _discounted_payback_years(cashflows: list[float], discount_rate: float) -> float | None:
       """Year (interpolated) at which cumulative discounted cashflow first
       turns positive AND remains non-negative through the horizon end.

       cashflows convention: cashflows[0] is the year-0 net (capex - grant
       - opex + savings); cashflows[i] for i>=1 is year-i net (savings -
       opex). Capex outflows ahead of operational savings means
       cashflows[0] is typically negative.
       """
   ```

3. The "remains non-negative through horizon end" wording matters: a
   pathway can cross zero in year 4, dip back below zero in year 8 due
   to mid-life replacement opex (when ageing lands in v0.2), and then
   recover. For v0 with no ageing, first-cross is sufficient — but the
   docstring should reflect the intent so v0.2 doesn't regress.

4. Add unit tests in `test_pathway.py` (new test class
   `TestDiscountedPaybackInvariants`):

   - `test_discounted_ge_simple_for_each_named_pathway`: for each
     site fixture (`dairy_5mw`, `brewery_8mw`, `soft_drinks_12mw`),
     for each named pathway (Conservative, Balanced, Aggressive),
     assert `discounted_payback_years >= simple_payback_years`
     (allowing `None` for pathways that never recover — both must
     be `None` together).
   - `test_grant_year_zero_does_not_short_circuit`: synthetic
     `[+grant, -capex, +savings...]` shape — confirm the function
     returns a value ≥ 1.0 (i.e. recovery happens after y0, not at it).
   - `test_capex_year_zero_typical_case`: standard
     `[-net_capex, +savings...]` shape with a known-good answer
     hand-computed.

5. Re-render the dairy GOLDEN report. Confirm `Discounted payback (yr)`
   for Balanced is now `>=` simple payback (7.54).

**Acceptance criteria:**
- `pytest decarb/engine/tests/test_pathway.py -v -k Discounted` all green.
- Balanced row in fresh `GOLDEN_DAIRY_5MW_*` shows
  `Discounted payback (yr) | <X>` with `X >= 7.54`.
- No other test regresses.

**Commit:** `[BUILD iter 1] pathway_discounted_payback_bug: drop bogus
y0 early-return, add invariant tests across three sites`

---

## Phase 3 — Screen ↔ Pathway grid-headroom consistency (D2) — 2-3 hr

**Files in scope:** `backend/decarb/engine/pathway.py`,
`backend/decarb/render/templates/v0_pathway_report.md.j2`,
`backend/decarb/engine/tests/test_pathway.py`,
`backend/decarb/engine/tests/test_render.py`

The defect: §3.3 of the report routes high-temp HP and electrode-boiler
to "pending senior grid decision" because they exceed 1.5× DNO-quotable
headroom. §4 then recommends pathways that include those technologies
with an inline `⚠️ requires DNO reinforcement decision` warning. The
engine is internally inconsistent: the screen says "wait for senior
call"; the optimiser says "here's the recommendation that ignores it".

**The fix has two acceptable shapes. Pick one and justify in
`iter_1_build.md`:**

### Option A (preferred): split optimiser output into two pathway sets

In `optimise_investment_pathway`:
1. Determine the site's `headroom_kw_quotable_no_reinforcement` (1.0 ×
   declared headroom, NOT 1.5×; that's the no-questions-asked envelope).
2. Run candidate generation twice:
   - **constrained set:** filter out any candidate whose total stack
     electrical demand (HP draw at typical COP + EB nameplate) exceeds
     `headroom_kw_quotable_no_reinforcement`.
   - **reinforced set:** the existing 1.5× envelope filter.
3. Return both as `pathways_no_reinforcement: {...}` and
   `pathways_with_reinforcement: {...}` in the result, each carrying its
   own Conservative / Balanced / Aggressive triple. If the constrained
   set has no Conservative-feasible option, return
   `pathways_no_reinforcement: {"infeasible_reason": "..."}`.
4. Render both in §4 of the template:
   > **§4.1a — Pathways without DNO reinforcement** (deliverable in
   > 6–9 months from notice-to-proceed)
   > **§4.1b — Pathways with DNO reinforcement** (deliverable in
   > 18–30 months from notice-to-proceed; capex includes reinforcement
   > range £50k–£500k as a separate line)

### Option B: optimiser respects the screen and refuses to recommend pending-decision tech

In `_generate_candidates`, drop any action whose `requires_grid_decision`
is True UNLESS the user explicitly opts in via
`site_brief.constraints.assume_dno_reinforced=true`. Then in the report,
§4 leads with: "Every named pathway in this release respects the §3.3
pending-grid-decision verdict — no electrode boiler or high-temp HP is
recommended until DNO reinforcement is confirmed. Senior reviewer
override: set `assume_dno_reinforced=true` in the site brief."

**Choose A unless A's runtime cost is prohibitive.** The dual output
is more useful to a senior reviewer.

**Tests:**
- `test_screen_pathway_consistency`: for each site fixture, assert that
  if any action in any returned pathway has `requires_grid_decision=True`,
  then either (a) the result also exposes a `pathways_no_reinforcement`
  set, or (b) the site brief carries the `assume_dno_reinforced` opt-in.
- `test_render_no_orphan_warnings`: render the dairy report; assert
  that no `⚠️ requires DNO reinforcement` warning appears outside the
  appropriate header (§4.1b in Option A; never in Option B).

**Acceptance criteria:**
- Fresh dairy GOLDEN report renders both pathway sets (Option A) or
  no contradictory recommendations (Option B).
- Tests above pass.
- §3.3 and §4 read as one consistent story, not two.

**Commit:** `[BUILD iter 1] screen_pathway_grid_consistency: <option
chosen>; dual pathway sets in dairy GOLDEN report`

---

## Phase 4 — Renderer hygiene (D4 + D5) — 30 min

**Files in scope:** `backend/decarb/render/templates/v0_pathway_report.md.j2`,
`backend/decarb/engine/carbon.py` OR
`backend/decarb/engine/emission_factors.py` (whichever computes CCL —
search for "CCL" in `engine/`), `backend/decarb/engine/tests/test_render.py`

### D4 — §1 Executive Summary leads with the wrong carbon number

§1 currently leads with the year-1 dispatch carbon delta
(`8,851 → 7,032 tCO₂e/yr`, 20.5% reduction). §4.1 reports year-15
Balanced reduction as 50.9%. Both are true; the executive summary
juxtaposed against §4.1 reads as the engine disagreeing with itself.

Fix: rewrite the §1 paragraph to **lead with the year-15 figure** and
make the year-1 figure subordinate as a "first-year ramp-up" data
point. Live-render both numbers from the pathway record so the prose
can never go stale relative to the optimiser. Suggested shape:

> A 15-year run of the **Balanced** pathway reduces site Scope 1+2
> emissions from **8,851 → 4,348 tCO₂e/yr** (year-15, **50.9%**
> reduction). Year-1 reduction is more modest — **8,851 → 7,032
> tCO₂e/yr** (20.5%) — reflecting phased deployment of HP +
> EB + TES capacity over the first three years and the contribution
> of declining grid carbon intensity (NESO FES 2025) over the horizon.

Pull the year-15 figure from
`pathways.balanced.year_15_total_carbon_t_co2e` (or whatever the
optimiser exposes). If the field doesn't exist, add it; the renderer
should never compute carbon deltas itself.

### D5 — Provenance row 6 (CCL) self-defeating arithmetic

Current rendered text (provenance row 6):

> "elec 0.062 p/kWh × 12.5M kWh = £7,750; gas 0.043 p/kWh × 38.0M
> kWh = £16,218."

`0.043 p/kWh × 38,000,000 kWh = 0.00043 × 38e6 = £16,340`. Off by £122.
Either the rate is more precise than displayed (CCA fraction not
shown), or the multiplication is wrong. Either way the visible numbers
fail the basic check `factor × volume = product`. This is the exact
"LLM never does arithmetic" principle violated by a deterministic
module.

Fix:
1. Find where this string is built. It's almost certainly an f-string
   or `.format()` call inside the engine module that computes CCL.
2. Replace the embedded calculation with a structured-data return:
   the provenance row should expose `electricity_rate_p_per_kwh`,
   `electricity_volume_kwh`, `electricity_ccl_gbp`, `gas_rate_p_per_kwh`,
   `gas_volume_kwh`, `gas_ccl_gbp` as separate fields.
3. The renderer composes the prose from those structured fields, so
   the displayed multiplication is always `displayed_rate * displayed_volume = displayed_product`
   to within rendering precision. If the precision causes
   inconsistency, round consistently.
4. Add a unit test:
   `test_ccl_provenance_arithmetic_consistent`: parse the rendered
   row, extract the three numbers per fuel, assert
   `abs(rate * volume - product) < 1.0` (£1 rounding tolerance).

**Acceptance criteria:**
- Fresh dairy GOLDEN §1 leads with year-15 reduction.
- Provenance row 6 numbers multiply to within £1.
- New tests pass.

**Commit:** `[BUILD iter 1] renderer_hygiene: §1 carbon framing +
CCL provenance arithmetic consistency`

---

## Phase 5 — `validate_pathway` (S1) — 1 day

**Files in scope:** `backend/decarb/engine/validate.py` (NEW),
`backend/decarb/tools.py`, `backend/decarb/agent.py`,
`backend/decarb/prompts/orchestrator_v0_1.txt`,
`backend/decarb/engine/tests/test_validate.py` (NEW),
`docs/methodology/methodology.md` §4.4

This is the most leveraged remaining module. Every D-class defect above
is a cross-module consistency check it would catch. Build it now and
gate render on it.

### Architecture

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
              "check_id": "discounted_ge_simple_payback",
              "severity": "error" | "warning" | "info",
              "passed": bool,
              "message": str,
              "details": {...},
            },
            ...
          ],
          "summary": {"errors": int, "warnings": int, "infos": int},
        }
    """
```

### Checks (v0 — all required)

Implement at least these. Each is a function in `validate.py` that takes
the bundle and returns a `check` dict; the public function aggregates.

1. **`discounted_ge_simple_payback`** (severity error). For each named
   pathway, assert `discounted_payback_years >= simple_payback_years`
   (or both `None`).
2. **`screen_pathway_grid_consistency`** (severity error). Assert that
   no pathway action has `requires_grid_decision=True` unless the
   render path is the dual-pathway "with reinforcement" track. The
   exact rule depends on Phase 3's implementation; whichever option
   was chosen, encode the corresponding invariant here.
3. **`carbon_balance_year_15`** (severity error). Pull
   `baseline_year_0_carbon_t_co2e`, `pathway_year_15_carbon_t_co2e`,
   `year_15_reduction_pct` from the pathway record. Assert
   `(baseline - pathway_year_15) / baseline ≈ year_15_reduction_pct`
   to within 0.5 percentage points.
4. **`exec_summary_uses_horizon_carbon`** (severity warning). If the
   render path leads §1 with year-1 carbon as the headline, fire a
   warning. (After Phase 4 lands, this should pass; the check is here
   so future regressions trip it.)
5. **`provenance_arithmetic_self_consistent`** (severity error).
   Iterate provenance rows whose `method` string contains a `=`
   (e.g. CCL, capex × kW). Try to parse `<a> × <b> = <c>` patterns;
   for each parse, assert `|a*b - c| / max(|c|, 1) < 0.005`.
   This is heuristic — the failure mode is parse-failure, which
   should be `info`-severity not `error` (we're catching genuine
   inconsistencies, not penalising rows we couldn't auto-parse).
6. **`mc_pathway_consistency`** (severity warning, only if
   `monte_carlo` is not None). Assert that
   `monte_carlo.npv_distribution.p50` is within ±20% of
   `pathway.balanced.npv_gbp`. The MC central tendency should track
   the deterministic central case.
7. **`shortlist_in_pathway_or_excluded`** (severity error). Assert
   that every tech_id in any named pathway also appears in
   `screening.shortlist`. No orphan recommendations.
8. **`standards_register_no_dupes`** (severity info). The standards
   register in Appendix B is supposed to be deduplicated; assert no
   string appears twice.
9. **`methodology_status_matches_engine`** (severity warning). Read
   `docs/methodology/methodology.md`. For each `### 3.X module name
   ▍ <BADGE>` line, check whether the engine module is implemented
   (presence of the corresponding key in the engine bundle). Mismatch
   → warning. This is the check that would have caught D3.

### Tool wiring

1. In `tools.py`, replace the `validate_pathway` stub at line ~419 with
   a real wrapper that calls `decarb.engine.validate.validate_pathway`
   on the full `engine_results` bundle stored in `_site_context`.
   Return the compact result (passed/summary) to the LLM; persist the
   full check list in `_site_context["engine_results"]["validate_pathway"]`
   so the renderer can include it.
2. In the `TOOL_SCHEMAS` entry, drop "STUB" language. Description:
   > "Cross-module consistency and arithmetic check over the full
   > engine bundle. Call this AFTER all other tool calls and BEFORE
   > render_report. Returns `passed: bool` plus a structured check
   > list. If `passed=false`, fix the underlying engine output; do
   > NOT proceed to render."

### Agent loop integration

In `agent.py`, before the `render_report` tool call is allowed, the
agent must have called `validate_pathway` and seen `passed=true`. The
simplest enforcement: in `dispatch()` or the tool-call wrapper, when
`render_report` is requested, check
`_site_context["engine_results"].get("validate_pathway", {}).get("passed")`.
If `False` or missing, return an error to the LLM:

> "validate_pathway must pass before render_report is allowed. Current
> state: <summary>. Fix the underlying issues and re-call
> validate_pathway."

### System prompt

In `orchestrator_v0_1.txt`, add to the tool-ordering section:

> "After all engine tools (parse, screen, baseline, dispatch, pathway,
> MC) have been called, you MUST call `validate_pathway` and confirm
> `passed=true` before calling `render_report`. If validation fails,
> investigate the failing checks and address them — typically by
> re-calling the upstream tool with corrected parameters — then re-call
> validate_pathway."

### Methodology doc §4.4

Once Phase 5 is CLEAN, update `docs/methodology/methodology.md` §4.4
status badge from `ROADMAP v0.2` to `IMPLEMENTED v0`. Rewrite the
paragraph to describe the actual check list above. Bump version to
0.4 and add a revision-history row.

### Render integration

In the renderer, add a new section right before the appendices:

> ## §10 Validation Report  ![status](https://img.shields.io/badge/status-IMPLEMENTED%20v0-green)

listing each check, its severity, and pass/fail status. If any error
has fired and the report is still being rendered (e.g. for debugging),
prefix the report with a giant **DRAFT — VALIDATION FAILED — DO NOT
DISTRIBUTE** banner.

### Tests

`test_validate.py` covers:
- Each check in isolation: build a known-bad bundle, assert the check
  fires; build a known-good bundle, assert it passes.
- The full `validate_pathway` against the dairy fixture, expecting
  `passed=true` after Phases 1–4 are merged.
- A regression test: re-introduce the Phase 2 bug behaviourally
  (mock `simple_payback_years` to 7.54 and `discounted_payback_years`
  to 0.0), assert validate_pathway returns `passed=false`.

**Acceptance criteria:**
- Fresh dairy GOLDEN report renders §10 Validation Report with all
  checks green.
- Mutation testing: deliberately reintroduce one of D1/D2/D5 in a
  scratch branch, run `validate_pathway`, confirm `passed=false`
  with the right check name in the failure list. Don't merge the
  mutation — it's just to prove the validator works.
- All previous tests still green.
- Methodology doc §4.4 is now `IMPLEMENTED v0`.

**Commits (one per sub-phase if it grows long):**
- `[BUILD iter 1] validate_pathway: engine module + 9 checks`
- `[BUILD iter 1] validate_pathway: tool wrapper + agent loop gate`
- `[BUILD iter 1] validate_pathway: §10 render integration`
- `[BUILD iter 1] methodology §4.4: ROADMAP→IMPLEMENTED v0`

---

## Phase 6 — Multi-site GOLDEN renders + architecture.md cleanup — 1 hr

**Files in scope:** `backend/decarb/runs/` (new files),
`plan/architecture.md`

### Multi-site

Render `brewery_8mw` and `soft_drinks_12mw` GOLDEN reports under the
same naming convention as the dairy ones:

```
GOLDEN_BREWERY_8MW_<UTC timestamp>.md
GOLDEN_SOFT_DRINKS_12MW_<UTC timestamp>.md
```

Each must pass `validate_pathway` (Phase 5 must be merged first).
Read each end-to-end yourself; if any cross-section text reads
oddly for the non-dairy case (e.g. dairy-specific GMP language
appearing in brewery), open a follow-up note in
`plan/reviews/assessment_2026_05_06_fixes/iter_1_review.md` with
specifics — do NOT fix in this round; that's a separate per-site
template-hygiene task.

### Architecture doc

`plan/architecture.md` currently references a frontend that has been
deleted from the working tree:
- "Frontend | Next.js (existing) | Already there, fine"
- The "Reuse from existing MUNTec backend" table (entire table) lists
  modules that no longer exist in the repo.

Fix:
- Delete the Frontend row from the Stack table.
- Replace the "Reuse from existing MUNTec backend" section with a
  one-paragraph note: "The decarb engine is a clean-slate
  implementation. Earlier MUNTec residential heat-pump code was
  evaluated for reuse and discarded — the industrial scale and
  thermodynamic depth required first-principles redesign."
- "Out of scope for v1" — leave the "Frontend polish" line; that's
  still accurate.

**Acceptance criteria:**
- Two new GOLDEN reports in `backend/decarb/runs/`.
- `plan/architecture.md` no longer references the deleted frontend
  or the MUNTec reuse claim.

**Commit:** `[BUILD iter 1] multisite_render_and_architecture_cleanup:
brewery + soft_drinks GOLDEN reports; architecture.md frontend +
MUNTec-reuse claims removed`

---

## Round-protocol artefacts

Mirror the existing pattern in `plan/reviews/dairy_template_hygiene/`
and `plan/reviews/monte_carlo_uncertainty/`. For this brief, produce:

- `plan/reviews/assessment_2026_05_06_fixes/iter_1_build.md` — what
  you changed per phase, file-by-file. One section per phase.
- `plan/reviews/assessment_2026_05_06_fixes/iter_1_review.md` — your
  own pass through the result, applying the assessment doc's
  acceptance criteria as the rubric. Mark each defect (D1, D2, …, S1)
  CLEAN / PARTIAL / NOT-ADDRESSED.
- `plan/reviews/assessment_2026_05_06_fixes/META_SUMMARY.md` — final
  one-page summary: which phases landed, which iter, total LOC delta,
  test-count delta, list of follow-ups deferred to a next round.

If any phase fails review, iterate (`iter_2_build.md`, `iter_2_review.md`)
until CLEAN before merging the branch into main.

## Final merge

Only after every phase is CLEAN, every test green, and the META_SUMMARY
written:

```
git checkout main
git merge --no-ff feature/assessment-2026-05-06-fixes
```

Don't squash — preserve the per-phase commit history.

## Out of scope (do NOT do)

- GTM artefacts (List A, List B, lawyer summary, ex-FN coffee logs) —
  the user does these by hand.
- Multi-stage HP cycle implementation (S5 in the assessment) — that's
  a separate, larger task; flag it in META_SUMMARY follow-ups.
- Any frontend / UI work — frontend was deleted on purpose.
- Any change to the corpus (don't add/remove documents).
- Bumping any LLM model name; don't touch `MODEL` in agent.py.
- Pre-writing weeks 8+ planning docs.
