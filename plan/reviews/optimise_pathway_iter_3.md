# Review of optimise_investment_pathway — iter 3
Reviewer: Session B
Commit reviewed: b27887f
Date: 2026-05-05

## Verdict: CLEAN

## Test status
`pytest decarb/engine/tests -v`: **green (216 passed, +3 from iter 2)**
New tests added: 3 — `test_sensitivity_warning_declared`, `test_capex_flat_rate_warning_declared`, `test_balanced_underperforms_warning_under_defaults`. Each test guards a top-level warning code that maps directly to one of the three open iter-2 issues.

## Status of iter-2 issues

| # (iter-2) | Severity | Status | Note |
|---|---|---|---|
| 1 (sensitivity) | MEDIUM | ✅ resolved | `sensitivity_not_yet_computed` (severity: medium) emitted; cites methodology §3.6 explicitly; tells the senior reader how to overlay sensitivities manually until v0.2. |
| 2 (capex flat-rate) | MEDIUM | ✅ resolved | `capex_flat_rate_v0` (severity: medium) emitted; quantifies the impact ("±30% capex envelope shifts balanced NPV by ~£500k under default tariffs at dairy_5mw"); names the v0.2 fix (two-segment piecewise £1,400/kW <2 MW, £900/kW ≥2 MW). |
| 3 (Balanced/Conservative inversion) | LOW | ✅ resolved | `balanced_underperforms_conservative_under_v0_defaults` (advisory) emitted *only when the inversion actually occurs* — guarded by a numeric check on `year_15_reduction_pct`. Renderer now has a flag to surface in the executive summary. |

The Builder took the option I explicitly accepted in iter-2 ("Either declare or fix; both options are within scope of a half-day's work"). The declarations are quantitative, name the v0.2 deliverable that closes them, and are test-locked so no future regression can silently drop the disclosure.

## Issues found
None.

## Things done well
- Every warning carries (severity, code, message) where the message is a complete English sentence with a specific quantitative claim and a v0.2 schedule. A senior reader can read the warnings list as a standalone disclosure document.
- The `balanced_underperforms_conservative_under_v0_defaults` warning is emitted *conditionally* — only when the inversion happens. Once a real carbon price + grant overlay is applied and the inversion reverts, the warning disappears. This is the right behaviour: warnings should describe the *current* deliverable, not all hypothetically possible failure modes.
- The test guarding `balanced_underperforms_conservative_under_v0_defaults` mirrors the same conditional logic, so the test only fires the assertion when the inversion is in effect — it doesn't hardwire the pathological case as the expected output.
- Commit message references the Reviewer iter-2 verdict and quotes the fix path I authorised. Provenance of the design decision is auditable via git history, not just code comments.

## Numbers from the live run (dairy_5mw, default scenario)
Numerical outputs unchanged from iter 2 (NPV / payback / reduction / Pareto sizes / candidate counts). The iter-3 changes are disclosure-only — they do not alter any cashflow, candidate, or evaluation. The v0 schema now ships with **14 top-level warnings** comprising:

- 6 sink-physics warnings with pathway labels (per iter-1 issue #2)
- `retained_gas_backup_active` (advisory, per iter-1 issue #9)
- `carbon_price_and_grant_excluded` (high, per iter-1 issue #4)
- `balanced_underperforms_conservative_under_v0_defaults` (advisory, **new**)
- `sensitivity_not_yet_computed` (medium, **new**)
- `capex_flat_rate_v0` (medium, **new**)
- `equipment_ageing_not_modelled` (advisory)
- `v0_brute_force_enumeration` (advisory)

Every single declared methodology-§3.6 deliverable that the engine does *not* currently compute is now disclosed as a top-level warning with named v0.2 successor work. There is nothing left silently absent.

## Senior-FN-engineer-would-they-sign?
**Yes, with the v0 caveats on the record.**

The optimiser produces three distinct named pathways with honest sink-temperature physics, an explicit carbon-price + IETF-grant overlay knob, dual capex/NPV Pareto frontiers, hand-checked numeric bands across all three reference sites, and — as of iter 3 — a complete declaration of every methodology-§3.6 deliverable that is not yet implemented. A Frazer Nash partner reading the dairy report would still want the v0.2 sensitivity table and the size-dependent capex curve before writing it up under their PI cover, but the engine no longer surprises them: every gap is on the deliverable, quantified, and schedule-bound. That is the methodology contract.

The two MEDIUM gaps (sensitivity sweep + size-dependent capex) and the LOW gap (Conservative/Balanced labelling under v0 defaults) are now on the v0.2 backlog with explicit acceptance criteria. The Builder can ship v0.

**No further reviewer iterations needed. Stopping per the protocol.**
