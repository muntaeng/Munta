# Project state — brutal review (2026-05-06)

Reviewer: same friend, eight days later. Continues the 2026-04-28 review.
Read it alongside that one — this is the delta and the things the current
trajectory still gets wrong, not a re-litigation of the baseline.

---

## TL;DR

The eight days since 2026-04-28 are **the strongest week of execution in the
repo's history.** Three engine modules that were stubs are now real
(`render_report`, `optimise_investment_pathway`, `monte_carlo_uncertainty`),
each with a reviewer-iterated build and a test suite. Discipline rules from
the 04-28 review have been actioned (personal email on every commit, secrets
removed, frontend deleted from working tree, work log + decision-placeholder
files created, key rotated). The latest dairy report is a 500-line
deliverable with provenance, standards register, an explicit deficit caveat,
four "Senior to confirm" items, an MC envelope and Sobol indices.

So: the engine bar moved up. The bar a senior FN engineer signs against
moved up faster, because *the report itself now reveals more failure modes
than it used to.* You are no longer behind on engine; you are now behind on
**internal consistency, GTM, and discipline-rule durability.** Three
specific facts:

1. **`docs/methodology/methodology.md` is now lying.** §1 status preamble
   and §3.6, §3.7 still declare investment-pathway and Monte-Carlo
   `ROADMAP v0.2`. The renderer template was patched (commit 95d0058),
   but the methodology doc itself wasn't. The procurement / PI artefact
   says less than the engine ships. This is the exact failure mode the
   04-28 review flagged in reverse, and it is the most reputationally
   dangerous file in the repo today.

2. **`Discounted payback (yr) | 0.0` for the Balanced pathway** in the
   latest golden report. Simple payback is 7.54 yr. Discounted payback
   ≥ simple payback by definition; an FN reviewer flags it in 30 seconds.
   Confirmed root cause: `_discounted_payback_years` in
   `backend/decarb/engine/pathway.py` line 240 returns 0.0 when year-0
   cashflow is positive (IETF grant booked y0 before capex), ignoring
   subsequent capex outflow.

3. **The §3 → §4 cross-section logic in the report contradicts itself.**
   §3.3 routes `industrial_heat_pump_high_temp` (1716 kW) and
   `electrode_boiler_steam` (5199 kW) to *pending senior grid decision*
   on the grounds that both exceed 1.5× DNO-quotable headroom. §4 then
   recommends Conservative/Balanced/Aggressive pathways that *all* carry
   `⚠️ requires DNO reinforcement decision`. In other words: the screen
   says "wait for senior grid call before adding these"; the optimiser
   then puts them in the recommendation regardless. The senior will read
   §3 and then §4 and ask: "why is the engine telling me to wait, then
   recommending I install anyway?" That is the kind of inconsistency
   `validate_pathway` is supposed to catch — and it is still a stub.

GTM remains untouched in the repo:
- `plan/work_log.md` has one entry, dated 2026-04-28. Every commit since
  has been a session that should have produced a line. None did.
- No artefact for lawyer outcome (the work log mentions "lawyer letter
  outcome reviewed" — nothing in the repo about what the outcome was).
- No artefact for evaluator confirmation — no calendar block, no email
  thread, no `evaluator.md`.
- No List A or List B (10 ex-FN coffees, 15 industrial sites). 04-28
  said this is end-of-week-2 territory. Today is week 4 of the spike
  by the original schedule, week 1.5 by elapsed working time. Either
  way, zero coffees lined up with a working week left to book five.

If a Frazer Nash partner asked you tomorrow "what would you sell me?",
the honest answer is now: *a defensible engine for one site type, a
methodology doc that under-claims what the engine does, a 500-line
report with two visible defects, no evaluator booked, no buyer
conversation tested.* That is materially further along than 04-28 and
materially still not a sale.

---

## What got better since 04-28

Credit before criticism. These were on the 04-28 priority list and they
landed:

- **Personal-email migration done.** Every commit in `git log --all
  --format='%ae' | sort -u` is now `muntadhar@muntaengineering.com`. No
  history rewrite shrapnel visible.
- **Secrets cleaned.** `docker-compose.yml` API key gone (commit 1965026);
  `.env.save` and the two large transcript .txt files are not in the
  current tree.
- **Frontend deleted from working tree.** `ls frontend` returns "no such
  file." Architecture doc still references it ("Frontend | Next.js
  (existing) | Already there, fine") — that is now stale and should be
  cut, but the focus tax is recovered.
- **`render_report` shipped (commit 7b95b38).** Eleven sections,
  provenance Appendix A with 33 entries, standards Appendix B with 31
  entries, explicit `IMPLEMENTED v0` / `ROADMAP v0.2` badges per section,
  `> Status of this deliverable` preamble, dispatch-deficit blockquote
  caveat, `requires DNO reinforcement` warnings on pathways that need
  one. Eight golden runs in `backend/decarb/runs/` document the
  iteration trail.
- **`optimise_investment_pathway` shipped real (commit 7886468 + three
  reviewer iterations).** Three named pathways, two Pareto frontiers,
  brute-force enumeration, capex-budget filter, NPV/IRR/LCOH/payback
  computed by deterministic functions, Brent's method for IRR, full
  provenance. It calls `simulate_site_dispatch` as the inner loop —
  the architecture's "engine modules call each other, no
  re-implementation" principle is being honoured.
- **`monte_carlo_uncertainty` shipped real (commit 3995256 + two
  reviewer iterations).** LHS + Iman-Conover copula sampling, Sobol
  S1/ST via SALib, Morris elementary effects, VaR_95/CVaR_95,
  `prob_carbon_target_met`, deterministic seed, closed-form
  re-evaluation (declared in warnings — that's the right call for v0
  given runtime budget). The methodology rigour is real: Saltelli,
  Morris, Iman-Conover all cited correctly.
- **Round-protocol Tier-1 hardening** (latest commit, 7ef5876) — the
  build/review/META iteration pattern is producing converging fixes
  rather than churn. Every round closes with a CLEAN review state.
- **Work log + decision file created.** They exist. They are barely
  used (see below), but the commitment device is in place.

That is genuinely strong shipping for ~25 hours of personal time.

---

## Concrete defects in the v0 deliverable a senior FN engineer will flag

Each one I'd expect them to catch in the first 30 minutes of reading
`GOLDEN_DAIRY_5MW_20260506T115156Z.md`. None are existential; all are
fixable in <2 hours. Listed in priority order.

### D1. Discounted payback < simple payback

```
| Simple payback (yr) | 7.54 |
| Discounted payback (yr) | 0.0 |
```

Bug in `_discounted_payback_years` (`backend/decarb/engine/pathway.py:226–242`).
The early-return on year-0 positive cashflow:

```python
if y == 0 and cumulative >= 0:
    return 0.0
```

triggers when the IETF grant is booked y0 before the capex outflow
lands. Verified by running the function with `[+grant, -capex,
+savings...]` shape — returns 0.0. Any time `pathway_selection_rule`
hands the renderer a Balanced cashflow with grant overlay, the report
ships this defect.

Fix: drop the special case entirely; it's wrong by definition.
Cumulative starting at 0 cannot satisfy "discounted payback" before
year-1 net cashflow has been added. The general-case interpolation
two lines below already handles the legitimate "project pays back in
year 1" case correctly. Add a unit test in `test_pathway.py` that
asserts `discounted_payback >= simple_payback` for every named pathway
and every site fixture. That assertion alone would have caught this.

### D2. Section 3 vetoes what Section 4 recommends

§3.3 (Pending senior grid decision):
> `electrode_boiler_steam` … Estimated electrical demand 5199 kW
> exceeds 1.5× available headroom (1000 kW; 519.9% utilisation).
> Beyond the typical envelope a UK DNO will quote without structural
> reinforcement. Pending senior decision on (a) DNO reinforcement
> (£50k–£500k, 12–24 month timeline) versus (b) capacity-staged
> deployment or (c) alternative technology mix.

§4.1 — every named pathway includes an electrode boiler:
- Conservative: `eb_4000` (4 MW)
- Balanced: `eb_…`
- Aggressive: same shape

The engine is internally inconsistent. A senior reads §3 as "wait for
the senior grid call" and §4 as "here's the recommendation that
ignores it." The right v0 behaviour is **either**:

- the optimiser respects `requires_grid_decision` and produces a
  *dual* recommendation set ("with reinforcement" / "without
  reinforcement"); **or**
- the optimiser is upfront in §4 prose: "Every named pathway in this
  release assumes the senior grid decision is resolved in favour of
  reinforcement; a no-reinforcement variant is computed below."

Right now it does neither — it just attaches a `⚠️ requires DNO
reinforcement decision` footnote to every row and moves on. That
footnote is the kind of legal-disclaimer move a partner notices and
loses confidence over. The screen / pathway disagreement is exactly
the cross-section consistency check `validate_pathway` is supposed
to do, which is still a stub (see S1 below).

### D3. The methodology doc and the report disagree on what is shipped

`docs/methodology/methodology.md`:
- Line 36 (status preamble): "**five engine modules are implemented**
  … **Six modules are specified at the depth indicated and are
  scheduled for v0.2 implementation** (§3.6 pathway, §3.7 Monte
  Carlo, §3.8 pinch, §3.9 safety, §3.10 grid, §3.11 reliability)"
- Line 160: `### 3.6 Investment pathway optimisation  ▍ ROADMAP v0.2`
- Line 168: `### 3.7 Monte Carlo uncertainty  ▍ ROADMAP v0.2`

Report:
- §4: `status-IMPLEMENTED v0` (pathway)
- §4.1: `status-IMPLEMENTED v0` (Monte Carlo)
- §4.1 prose: "Investment-pathway sequencing (§4) and Monte-Carlo NPV
  bands with Sobol sensitivity (§4.1) are live in this release."

Commit 95d0058 fixed the renderer template prose; the methodology doc
itself was missed. This is the single highest-priority fix in the
repo today — the methodology doc is the **sales artefact**, the file
the lawyer / FN partner / PI insurer reads. Every day it carries the
old text is a day the company under-sells what's already shipping
*to the people who decide pricing*.

Five-minute fix:
- §1 status preamble: "**seven** modules implemented … **four**
  scheduled for v0.2 (§3.8 pinch, §3.9 safety, §3.10 grid, §3.11
  reliability)" — also note `render_report` and `monte_carlo` are
  live, leaving `validate_pathway` as the remaining process
  controller in roadmap.
- §3.6, §3.7, §3.8 (the section badges) updated accordingly.
- Bump version to 0.3, append a one-line revision-history row.

### D4. The §1 prose still cites pinch as a deferred pillar but understates carbon delta

§1: "achieves a Scope 1 reduction of **6,951 → 4,169 tCO₂e/yr**
(location-based Scope 2 rises from 1,900 to 2,863 tCO₂e/yr as gas
demand transfers to grid electricity); the net total moves from
**8,851 → 7,032 tCO₂e/yr**."

That's 8,851 → 7,032 = **20.5%** reduction. Then §4.1 reports
year-15 reduction of **50.9%** for Balanced. Both can be true (year-1
of a phased deployment reads worse than year-15 with grid
decarbonisation tailwind), but the executive summary leads with the
year-1 number and an unprepared reader compares it against the
year-15 figure in the next section and concludes the engine
disagrees with itself. The 04-28 dairy-template-hygiene round closed
on this kind of issue; this one slipped through.

Five-minute fix in the renderer: lead with the year-15 figure (or
both, with the dispatch-year tagged). The senior cares about the
trajectory, not the year-1 standstill.

### D5. Provenance row 6 (CCL) embeds a calculation in the description

```
calculation=CCL liability;
method=CCA reduced rates (HMRC 2024+):
  elec 0.062 p/kWh × 12.5M kWh = £7,750;
  gas 0.043 p/kWh × 38.0M kWh = £16,218.;
```

The "0.043 × 38.0M = 16,218" — let's check: 0.043p × 38,000,000 kWh
= 0.00043 × 38e6 = £16,340. Off by £122. Either the rate is more
precise than displayed (likely — true CCA reduced gas rate is
something like 0.043 p/kWh × CCA fraction) or the multiplication is
wrong. Whichever it is, the rendered text shows numbers that *do
not multiply to each other.* This is the third-most-cited concern of
04-28 — provenance is the differentiator vs every "GPT for
engineering" demo, and a provenance entry that fails its own arithmetic
is a self-inflicted credibility wound.

Fix: either (a) compute the multiplication in code and render the
result, never quote both factors and product as inline string; or
(b) round the rate displayed to match the product.

---

## Strategic findings — the things 04-28 raised and the trajectory still gets wrong

### S1. `validate_pathway` is still a stub. This is now actively dangerous.

04-28 priority 4 was "implement validate_pathway self-critique loop."
The engine has shipped two more major modules since, neither preceded
by validate_pathway. The system prompt still tells the LLM to
self-critique. The validator that checks the LLM actually did so does
not exist.

Every defect in the D-list above is a cross-module consistency check
that validate_pathway would catch in seconds:

- D1 (`discounted_payback ≥ simple_payback`) — invariant test.
- D2 (`screen.pending_grid_decision ⇒ pathway must split`) — cross-section.
- D3 (methodology.md status badges match render `IMPLEMENTED` flags) —
  doc/code alignment.
- D4 (year-1 carbon delta isn't the headline number) — render rule.
- D5 (factor × kWh = product, to within rendered precision) —
  arithmetic check.

You are now shipping enough engine that *the LLM's report has
inconsistencies the engine itself could find.* Every additional engine
module makes this worse, not better, until validate_pathway exists.
Build it next. ~250 lines, one day, and it converts every D-class
defect from "lands on the senior" to "engine fails the build."

### S2. Validation against three sites is half a claim

`docs/methodology/methodology.md` §2 line 98:
> "*Golden test cases gate every release.* No engine module is
> released until it produces results, against three reference site
> profiles, that fall within tolerance bands set by hand-checked
> engineering judgement. The reference profiles are dairy (5 MW),
> brewery (8 MW) and soft drinks (12 MW)."

Reality:
- Three site fixtures exist (`tests/sites/dairy_5mw.json`,
  `brewery_8mw.json`, `soft_drinks_12mw.json`) — good.
- Tests run against multiple sites — `grep brewery_8mw` returns 56
  matches, `grep dairy_5mw` returns 140 matches. That is roughly
  50:50 brewery/dairy with soft_drinks under-tested. **Eight
  rendered GOLDEN reports in `backend/decarb/runs/` — all dairy.**
- A senior reading the methodology doc concludes "engine is
  multi-site validated", clicks through to the runs folder and sees
  one site rendered eight times.

Either fix the methodology language to match reality ("dairy is the
primary v0 reference; brewery + soft drinks are unit-tested but
report-render coverage lands v0.3") or generate brewery + soft drinks
GOLDEN reports next session. The latter is ~20 minutes of agent
runtime — the gating isn't capability, it's discipline.

### S3. Work log is dead. This is identical to the Apr-28 Neara-email
finding — discipline rule on paper, ignored in practice.

```
$ wc -l plan/work_log.md
14
$ git log --since=2026-04-29 --oneline | wc -l
30
```

Thirty commits since 04-29; one work-log entry, dated 04-28 itself.
The 04-28 review was explicit: "no discipline survives without an
artefact." The artefact was created — and then never written to.

The reason this matters is *not* compliance hygiene. The reason is
that on the day Neara legal asks "what hours did you spend on this
between April and June?", a 30-line work log with dates and
truthful 1-line entries is the difference between a 5-minute
clarification and a 5-week disclosure. The lawyer letter is the
shield; the work log is the audit trail that lets the shield work.

Same fix mechanism as 04-28: *block your own commits if the work log
hasn't moved.* Pre-commit hook or simple personal rule. Don't ship
another commit Friday without an entry covering it.

### S4. GTM is still where it was 8 days ago

The 04-28 review priorities list, weeks 1–4 GTM:
- Lawyer letter — "in hand" implied by work-log mention; no
  artefact in repo, no `plan/lawyer/` folder, no scope opinion to
  reference.
- Evaluator email — "evaluator email sent" per work log; no reply
  recorded, no calendar block.
- List A (10 ex-FN coffees) — does not exist.
- List B (15 industrial decarb sites) — does not exist.
- Five ex-FN coffees by end of week 4 — count today: zero.

The spike's go/no-go at week 7 has *two inputs*: engine quality and
evaluator/buyer reaction. You are 70% of the way on engine and 0% of
the way on evaluator/buyer. That is the most dangerous shape the
project can be in — the half it controls (engine) is in good shape,
making it psychologically easy to keep building; the half that
determines whether the company exists (buyer reaction) is untouched,
and gets harder the longer engine-only work substitutes for it.

This is the founder failure mode the 04-28 review explicitly named:
*"Realisation that the engine is harder than the spike timeline.
Expected. Stick to the timeline."* Translated: don't let engine
satisfaction crowd out GTM blockers. It has.

Hard rule for week 5 (next week): no engine commits until **two**
ex-FN coffees are on the calendar. Not "emails sent" — accepted
invites with a date. Lawyer letter outcome filed in
`plan/legal/scope_opinion_summary.md` (without breaching privilege —
just bullet headlines). List A populated to ten names with
LinkedIn URLs.

### S5. The optimiser's pathway envelope is narrower than a senior reads it

The Balanced pathway recommends `hp_mid_2000` (2,000 kW NH3 single-stage HP)
for the **hot-water sub-demand only**, with steam (175°C) staying on
gas + EB. §9 senior-decision item 1 is explicit about this rationale.
That is engineering-honest.

But the report frames it as "Year-15 Scope 1+2 reduction: 50.9%"
*without* leading with the architectural truth that *the steam header
is not electrified in this pathway*. The 50.9% is achieved by
electrifying hot water and (per Conservative pathway) trimming peak-
demand steam-related electricity via TES + EB time-shifting. A senior
reading "50.9% reduction" and not catching the §9 caveat will
challenge it on first call: "this is a steam site; you said you'd
electrify the steam system; show me the steam path."

Fix is half-line in the executive summary: "Year-15 reduction of
**50.9%** is achieved by electrifying the **hot-water and ancillary**
loads only; the 175°C steam header is retained on gas-fired backup
under v0 single-stage HP envelope and is the principal lever for the
remaining 49% (multi-stage / 175°C HP architectures: §3.4
ROADMAP v0.2)." Honest. Increases trust.

This is also a **product** finding. If the v0 engine cannot
electrify the steam header (the slice's *named* decision), then the
spike's vertical-slice question is half-answered. Multi-stage HP
implementation moves up the priority list because the spike thesis
literally depends on it. It is currently the only `IMPLEMENTED v0
(single-stage) / ROADMAP v0.2 (multi-stage architectures)` module
in the methodology — make it `IMPLEMENTED v0` for at least the
two-stage economiser case, or face a fair "you didn't actually
electrify the steam" challenge in the week-7 review.

### S6. Eight golden reports of the same site in eight days is iteration drift

`ls backend/decarb/runs/` shows eight `GOLDEN_DAIRY_5MW_*` files
spanning 2026-05-05 17:22 → 2026-05-06 11:51. ~18 hours of clock
time, eight render iterations, all dairy. The build/review pattern
is excellent for module quality but there is a meta-question that
nobody is asking: *what is the next failure mode each iteration
buys down, and at what point is the same-site iteration consuming
hours that should be on brewery / soft drinks / multi-stage / GTM?*

The 04-28 review said "the report being good enough that an FN
senior would sign it after 1hr is the only number that matters."
That number is currently estimated by an internal reviewer agent
loop, not a human. The agent loop has converged to CLEAN; that
proves the iteration round closed on its own rubric, not that the
report is FN-grade.

Two things to do:
- Lock dairy at the current state. No more golden iterations until
  brewery + soft drinks are at the same depth.
- Get a human eye on the report this week — not the week-7 evaluator,
  not the LLM reviewer agent. A friendly ex-FN call ("I have a
  draft, can you red-pen the first 15 minutes of it?") is the only
  signal that matters and the cheapest unit of feedback in the
  pipeline.

---

## What the next 14 days should be

If I were holding the whip:

**Today / tomorrow** (2 hrs total):
1. Fix D3 (methodology badges + §1 preamble). Five minutes; the
   sales doc has been wrong for ~24 hrs.
2. Fix D1 (discounted payback bug + invariant unit test).
3. Open `plan/legal/scope_opinion_summary.md` with the lawyer's
   bullet headlines. Open `plan/gtm/list_A_ex_fn.md` with the first
   five names.

**Week starting 2026-05-11** (15 hrs):
4. Build `validate_pathway`. Most leveraged module remaining.
   Implement the cross-checks in S1 plus the "screen ↔ pathway"
   invariant from D2. ~250–400 lines, one focused day. *Block
   render on validation pass in the renderer.*
5. Fix D2 — split the optimiser output into "with reinforcement"
   and "without reinforcement" pathway sets when any
   `requires_grid_decision == True` action is recommended.
6. Two ex-FN coffees in the diary by Wednesday. Non-negotiable. If
   the calendar is empty by Friday lunchtime, drop everything and
   send four cold emails before Friday close.
7. Render brewery_8mw and soft_drinks_12mw GOLDEN reports.
   Run validate_pathway over each. Compare exec-summary numbers
   across sites — do they tell internally consistent stories?

**Week starting 2026-05-18** (15 hrs):
8. Either: implement two-stage economiser HP cycle (the steam-
   header pathway requires it, S5) — or commit to the methodology
   amendment that v0 covers hot-water-and-ancillary electrification
   only, not steam-header. The current half-position is the worst
   one.
9. First ex-FN coffee delivered. Bring the dairy report with the
   D-fixes applied and ask Question 3 from `next_steps.md`. Listen,
   don't pitch. Write the answer up in
   `plan/gtm/coffee_001_<initial>.md` same evening.

**Week 7 (2026-06-08 onwards)** is the same as in `next_steps.md`.
No change. Stick to the decision matrix.

---

## What I'd cut, again

The architecture doc still references the deleted frontend
(`plan/architecture.md` table line "Frontend | Next.js (existing) |
Already there, fine"; and the "Reuse from existing MUNTec backend"
table). Five-minute edit. Stop selling reuse you don't have, and
the doc reads as engineering-honest rather than aspirational. The
old MUNTec backend reuse claim is the same issue as 04-28 said —
the new engine is better than the old, that is fine, but
architecture.md still positions the old as a feature.

---

## Bottom line

**The engine has caught up; the methodology, the validator, the
testing breadth, and the GTM have not.** The asymmetry is dangerous
because the engine work is the easy half — building three more
modules feels like progress. The remaining modules — `validate_pathway`,
multi-stage HP, brewery + soft-drinks render, methodology doc
alignment — are about *closing the gaps the existing engine has
already exposed*, not about adding new capability. They are
finishing-work. Founders avoid finishing-work.

Five conversations with ex-FN seniors, each one critical of one
specific report defect, would be worth more than three more engine
modules right now. Make them happen this week.

The 14-day window holds. Use it.
