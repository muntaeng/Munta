# Project state — brutal review (2026-04-28)

Reviewer: a friend who read the whole repo. No editorialising, no softening.

---

## TL;DR

The plan is excellent. The corpus and the deterministic engine modules that exist are genuinely good engineering — better than 90% of "AI for X" pitches I've seen. **But you are not where the spike timeline says you should be**, you have **two serious discipline breaches** that need fixing today, and the gap between "consultancy-grade tool that exists" and "consultancy-grade output a senior FN engineer signs off on" is bigger than the README acknowledges. Specifically: half of the engine is still stubs, the agent has nothing to *optimise* or *Monte-Carlo* or *render*, and the GTM side of the plan (which is actually where the company succeeds or fails) has not been touched.

If a Frazer Nash partner asked you tomorrow "what would you sell me today?", the honest answer is: *a strong corpus, a single calibrated dispatch model, no report renderer, no pathway optimiser, no validation loop, no real-world test, no signed evaluator.* That is week 1–2 territory in the spike plan, and it's currently end of week 1.

---

## Hard problems first — fix this week

### 1. Security: live API keys are in the working tree, and `docker-compose.yml` is staged with the Anthropic key inline

`docker-compose.yml` (tracked file) currently has the diff:

```
+ - ANTHROPIC_API_KEY= af7AAfASm_gh4lfz5nCx5lNBUsN3hC8HjurG3QIw_vcFyvhwIyzs3GC2v2hv6uSAc4ZDplF2uQOdyuEiAmakAg-PzamiQAA
```

That is the same key sitting in `.env`. One `git add docker-compose.yml && git push` and your Anthropic key is on GitHub. Same key also lives in `.env.save` (untracked, but on disk for no reason).

Fix today:
- Revert that diff in `docker-compose.yml`. Use `${ANTHROPIC_API_KEY}` substitution like every other variable.
- Rotate both the Anthropic and OpenAI keys *now*. Treat them as compromised. They sat on a developer machine in two cleartext files; the rotation is cheap insurance.
- Delete `.env.save`. There is no reason for a backup of a secret file to exist next to the secret file.
- `2026-04-28-151128-local-command-caveatcaveat-the-messages-below.txt` (root) and `backend/2026-04-28-131825-...txt` are 63KB and 163KB Claude Code transcripts. They might contain pasted snippets, paths, or thinking that you don't want in version control. Delete or move to `~/notes/` outside the repo.

### 2. Discipline breach: every commit is `muntadhar@neara.com`

```
$ git log --all --format='%ae' | sort -u
muntadhar@neara.com
```

The whole point of `direction.md` "All work on personal email + personal devices + personal GitHub" and the work-log discipline is that on the day someone at Neara legal asks "is this a Neara project?", the answer has to be evidentially no. Right now the entire git history says yes, including the commits adding the decarb engine. This is the single biggest legal risk to the company. The plan calls it out, the code ignores it.

Fix this week:
- `git config user.email muntadhar@muntaengineering.com` (and same in `~/.gitconfig`) on the personal machine. Verify with `git log -1 --format=%ae`.
- The lawyer letter is the right primary mitigation; this is the secondary mitigation that makes the lawyer's job easy. Don't push the spike onto GitHub under your Neara email. Consider rewriting author email on local commits before pushing — `git filter-repo` is the safe tool, but only do this on a personal mirror, not a Neara-touched repo.
- The Neara separation is in `direction.md` as a discipline rule. It's been a discipline rule for 0% of the actual commits. Treat it as a hard gate: nothing pushes until the email is right.

---

## What is actually built — accurate inventory

Plan/spec docs (excellent):
- `plan/direction.md`, `plan/architecture.md`, `plan/spike/README.md`, `plan/next_steps.md`, `plan/spike/SETUP.md`, `plan/spike/week1_corpus.md`, `plan/spike/week1_system_prompt.md`, `plan/spike/week2_engine_modules.md`, `plan/spike/claude_code_handoff.md`. Roughly 15,000 words of strategy + spec. This is genuinely above-average and the depth is the right kind — engineering depth, not LinkedIn depth.
- `docs/methodology/methodology.md` (260 lines) — already in the right voice for the procurement / PI conversation. This is a real asset.

Backend — `backend/decarb/engine/` (the moat):

| Module | Spec | Lines | Reality |
|---|---|---|---|
| `emission_factors.py` | §2 substrate | 381 | Real DEFRA 2026 Scope 1, Scope 2 location + market, Scope 3 WTT/T&D. Solid. |
| `load_profiles.py` | §1 substrate | 280 | 11 shape templates, normalisation good. Synthetic — fine for v0. |
| `parse.py` | §1 | 317 | Reasonable BS EN 16247-3-flavoured energy audit output. |
| `carbon.py` | §2 | 208 | GHG-Protocol-shaped, with regulatory exposure flags + 15-year trajectory under no-action. |
| `hp_cycle.py` | §4 | 542 | Single-stage CoolProp cycle with isentropic + volumetric maps, discharge-temp limits, F-gas / BS EN 378 checks. **Genuinely consultancy-grade for single-stage.** Multi-stage / cascade / transcritical are scaffolds, not implementations. |
| `dispatch.py` | §3 | 1,154 | 8,760-hour merit-order with HP+EB+TES+gas, COP looked up via real CoolProp calls, energy balance asserted < 0.5%, four dispatch policies. **The centrepiece is real.** |
| `screen.py` | §5 | 1,046 | Nine-axis decision tree. Real and substantial. |

Backend — stubs (still returning `{"_stub": true}`):
- `optimise_investment_pathway` (§6) — entire pathway optimiser
- `monte_carlo_uncertainty` (§7)
- `compute_pinch_analysis` (§8)
- `compute_safety_constraints` (§9)
- `assess_grid_connection` (§10)
- `compute_reliability_availability` (§11)
- `lookup_grants`, `lookup_regulations`, `validate_pathway`, `render_report`

So of the 11 modules in week2_engine_modules.md, **5 are real (§1, §2, §3, §4, §5), 6 are stubs**. The agent that calls these tools therefore cannot produce a real pathway, MC distribution, or report. It produces baseline + screening + a few dispatch runs and stops.

Corpus:
- `corpus/manifest.yaml` lists 117 entries; `git grep -c "status: downloaded"` says 98 downloaded, 16 blocked, 3 paid, 0 todo. **84% acquisition is genuinely impressive for one week's work.** Most "AI for X" decks have the corpus as a future bullet; you have it.
- pgvector + ingest pipeline + retrieval are wired, three smoke-test queries pass with real embedding similarity scores, retrieval is a real tool the agent can call. Good.
- The CIBSE / BS-EN paid items are still missing. Without TM54 and AM17 in the corpus, the procurement narrative around "every claim cited" has visible gaps.

Frontend — `frontend/`:
- ~7,800 lines of the **old MUNTec heat-pump-installer SaaS**. NavBar, Dashboard, RetrofitForm, StepBuilding/Energy/Solar/Tech/Upgrades, MCS cert generator, EPC, meter readings, maintenance, portfolios, teams. Auth, login, register pages.
- **Zero of this is for the new direction.** The product spec in `plan/architecture.md` says "frontend out of scope for v1". The frontend you have is for the parked product. It compiles, it has tests, it works — for nothing the company is now selling.
- Decision needed (week 5–6, not now): when consultancy buyers ask for a UI, do you (a) ship a CLI + PDF, (b) build a thin "upload site brief, get report" page on top of the agent, or (c) repurpose the dashboard tabs (Carbon, Engineering, Compliance) into industrial form factor. Don't build any of these in weeks 1–4. The frontend is a sunk asset; pretending it isn't and burning 15 hrs polishing it would be the single worst use of the spike time.

Backend — old MUNTec Python:
- `calculator.py` (1,312 lines), `simulation.py` (300), `solar_simulation.py` (354), `battery_simulation.py` (543), `phased_retrofit.py` (160), `calculations.py` (135), `weather.py` (274), and ~10 routers. Total ~6,400 lines as plan claims.
- `architecture.md` reuse table claims 3,000 of 6,400 lines reusable. Looking at what `dispatch.py` actually borrowed: the 8,760-hour loop pattern. That's tens of lines of inspiration, not thousands of lines lifted. The "reuse 3,000" number is aspirational. `next_steps.md` revising it down to 1,500 is closer; honest answer is probably 200–500 lines of *concept* reuse. Don't worry about it; the new code is better than the old.

---

## Quality of the engine code that *does* exist

Read `dispatch.py` carefully and the engineering literacy is real. Specifically good:

- COP table pre-computed via CoolProp at 1°C resolution and `np.interp`'d per timestep. This is the right pattern — CoolProp per-hour is too slow, Carnot per-hour is wrong, table-and-interp is fast and faithful. The `_method` field literally says "Hard rule: no Carnot approximations." That sentence in audit output is the kind of thing a senior FN engineer notices.
- Energy balance asserted in code at ±0.5%, with the bug-vs-capacity-limit distinction made explicit. The fact that the assertion message says "This indicates a bug in the dispatch accounting" rather than swallowing the failure is the right reflex.
- TES round-trip efficiency split as `sqrt(eta)` per half-cycle, standing losses applied per timestep with a 0.05%/hour rate. This is correct.
- Provenance dict on every output, listing the calculation, formula, source, and audit path. Standards-cited list of 10 items. *This is the differentiator vs every "GPT for engineering" demo.*

Things that are weaker than the spec implies:
- `screen.py` is 1,046 lines but the screening logic is mostly tier-and-band rules, not the real feasibility envelope checking the §5 spec implies. Capacity ranges are correct, footprint is correct, but the BS EN 378 charge-limit check, ATEX zone reasoning, GMP rationale, and grid-headroom check are largely string outputs rather than computed values. It will trip a senior engineer who reads it carefully. Not broken — just shallower than `methodology.md` claims.
- `hp_cycle.py` covers single-stage rigorously. Two-stage economiser, intercooled, cascade, transcritical CO2 are *scaffolded* — the dataclasses and dispatch-by-cycle-type exist, but the bodies are placeholder. The dairy / brewery sites can be analysed honestly with single-stage; the moment a buyer asks about a 90→160°C steam-make-up case (which is the obvious next decision class), there's no implementation behind it.
- `dispatch.py` energy-balance assertion has been observed to fail in lastfailed cache (whole `decarb/engine/tests` cache shows tests as last-failed). I can't run pytest in this environment to verify current state — you must run `cd backend && source .venv/bin/activate && pytest decarb/engine/tests -v` and confirm green before claiming any of this is shipping.
- `screen.py` golden tests assert shortlist *membership* but not the *reasons*. A test that checks "`industrial_heat_pump_high_temp` is in the shortlist" doesn't catch a regression where the rationale string is wrong. The §5 spec says categorical reasons must match `_golden_truth.expected_shortlist_must_exclude_with_reason` — that's not what's being tested.

---

## Strategic assessment — is this a viable business?

### What's working

- **Differentiated wedge.** The combination — first-principles thermo + UK regulatory grip + safety-engineering literacy + commercial nous — is genuine and not common. The plan's "Why us specifically" is honest, not LinkedIn-honest.
- **Right buyer, right product.** Engineering consultancies have the budget (£40–150k/seat is realistic for FN/WSP/Arup if it replaces 3 weeks of senior associate time) and the procurement pattern. Selling consulting hours with a tool behind them at £15k/study is the right wedge for a solo founder. End-clients direct (Shell, EDF) is a year-3+ move and the plan correctly defers it.
- **Methodology document already at the right voice.** `docs/methodology/methodology.md` reads like a procurement document, not a pitch. It will pass a PI insurer's smell test in a way that 99% of AI products won't. That document is more valuable than two months of code.
- **Engine architecture is provable.** "LLM never does arithmetic" is in the system prompt, in the agent loop, and structurally enforced by tools.py (compact summaries returned to the LLM, full results in `tool_call_log`). When a senior engineer asks "where did 7,820 tCO2e come from?", you can show them the function call. That demonstrability is the moat.

### What's not working

- **Spike timeline is slipping silently.** The spike says: week 1 corpus, week 2 engine v0 (all 7 modules including pathway + MC), week 3 agent integration + first end-to-end report, week 4 self-critique + provenance. We are at the end of week 1 with 5/11 engine modules built and the report renderer + pathway optimiser + MC + self-critique unimplemented. The plan correctly says "expected; week 6 is a feasibility checkpoint, not a delivery date" — but that requires honest tracking. There is no work log in the repo. There is no "I did X for 3 hrs on date Y" record. Without it, the only way to know whether you're on track is to do this kind of audit. You won't.
- **The GTM side has been done literally zero of.** `next_steps.md` says: lawyer letter this week, week-6 evaluator locked this week, two GTM lists by week 2, five ex-FN coffees by week 4. None of these have artefacts in the repo. The product without the lawyer letter is unsellable. The product without an evaluator at week 7 is a feasibility spike with no feasibility judgment. Both are 1-hour tasks today. Both are sliding.
- **The output the spike is supposed to produce — a 15-page consultancy report — currently does not exist as a code path.** `render_report` is a stub. There is no end-to-end run that produces a markdown file that you could put in front of someone. Week 3 of the spike depends on this existing. Without it, week 5 ("real-world test against published consultancy report") is impossible. Without that, week 7 ("ex-FN colleague rates output 1–5") is impossible. Everything down-stream of `render_report` blocks on `render_report`.
- **No empirical anchor for the "1-hour senior review" claim.** The whole pitch turns on the report being good enough that an FN senior would sign it after 1hr. There has never been a real test of this. The agent has been smoke-tested for token budget and tool-call count, not for report quality. That is the only number that matters in the year-1 sales conversation. Every week without that test is a week of building on an unverified assumption.
- **Pricing not pressure-tested.** £40–150k/seat/yr at FN/WSP/Arup is a defensible top-end ask if the tool credibly replaces 3 weeks of associate time per study and a typical senior runs 8 studies/yr. £15k/scoped study is a defensible bottom-end. Neither has been validated by actually asking a partner. `next_steps.md` Q3 ("If a tool produced an 80%-quality version of the report in an hour, what would that be worth?") is the only conversation that determines whether this is a £150k-ARR company or a £5M-ARR company. It hasn't happened.

### What the founder should believe but doesn't seem to

- **The corpus + methodology doc are 30% of the company already.** Most "AI for engineering" companies fail because they treat the corpus as a research afterthought. You treated it as the moat in week 1. That decision will keep paying dividends for years.
- **The frontend is a liability of focus, not an asset.** Every minute spent on it is a minute of vertical-slice scope creep. Treat it as deleted in your head until end of week 6.
- **The depth bar in `methodology.md` is going to outrun what you can ship in 6 weeks.** Section 3.10 promises G99 + G5/5 + harmonic-injection screening. Section 3.9 promises ALARP-screening BS EN 378 + ATEX + DSEAR + PSSR + CDM. Section 3.8 promises HEN synthesis with shell counts. None of those are implemented; under the spike scope they don't *need* to be implemented. But the methodology doc is the sales asset; if you send it to FN before the engine matches it, you lose trust on first call. **Either the methodology doc shrinks to v0 scope, or the engine catches up. The doc-shipping-ahead-of-engine gap is the most reputationally dangerous artefact in the repo right now.**
- **Risktec / FN safety credentials are a moat the plan undersells.** Every consultancy AI company will eventually claim they handle BS EN 378 + DSEAR + ATEX. You actually know what those do. That credibility, paired with one of the early conversations being "I led fire technical at FN, here is how the safety-screening module thinks", closes deals that "we're an AI startup" doesn't.

---

## What needs to change to make this a viable business

In priority order. Time estimates in your-15-hrs-a-week reality, not founder-hyperbole.

### This week (lose-the-company risk if not done)

1. **Email the employment lawyer Monday.** Brief is in `next_steps.md`; copy-paste it. £500–1,500. Without the letter, no outreach, no LOIs, no money. Cost of delay is the entire sales motion.
2. **Lock the week-7 evaluator.** Email the most senior, most opinionated ex-FN colleague today. One email. If they say no, find out now while there's time to find a replacement.
3. **Fix the API key in `docker-compose.yml`. Rotate both keys. Delete `.env.save` and the two large transcript .txt files.**
4. **Set git config to personal email on the development machine and verify with `git log -1`. Don't push until verified.**
5. **Start a `plan/work_log.md` file. Date, hours, what.** No discipline survives without an artefact.

### Weeks 2–4 (engine spike priority order)

6. **Implement `render_report` first, before the rest of the engine is finished.** A bad report from real tools is more useful than a perfect engine with no report. It sets the empirical baseline for "is the output good enough." Ship a 5-page version against `dairy_5mw.json` with whatever you have today. Read it as a senior engineer. Note the 10 things wrong with it. *That* list is the work plan, not the spec.
7. **Then `optimise_investment_pathway` (week-2 brute-force version, not MILP).** Without this the report has nothing to recommend. ~500 lines, 1 day if focused.
8. **Then `monte_carlo_uncertainty`.** Without this every number in the report is a single point estimate, which is the easiest thing for a senior to dismiss. ~250 lines, half a day.
9. **Then `validate_pathway` self-critique loop.** This is the highest-leverage step in the agent. The system prompt already tells it to self-critique; without a tool that actually runs the checks, it's lip service.
10. **Skip pinch / safety / grid / reliability for now.** They're in the methodology doc but not on the critical path for the dairy site. Build them in week 5 if there's time, or after the week-7 go/no-go. Don't let scope discipline slip.

### Weeks 4–6 (GTM)

11. **Five ex-FN coffees by end of week 4.** Question 3 — *"if a tool produced an 80%-quality report in an hour, what would that be worth to your partner?"* — is the conversation that determines pricing. If five answers all come back £40k+/seat, you have a £1M-ARR-by-year-2 path. If they come back "interesting but I'd buy it for £10k personal-use", you have a different company.
12. **One paid pilot conversation by week 6.** £15k scoped study, you deliver it personally with the tool behind you. One signed pilot makes the company real. Ten LOIs make it not.
13. **Methodology doc reality-check before sending to anyone.** Either trim to what the engine can actually back, or ship a v0 marked "draft, not for procurement" until the engine catches up.

### Week 7 — the actual go/no-go

14. **Independent ex-FN review of the report against the rubric.** This is the only honest signal. Trust the result.
15. **Decision matrix is in `next_steps.md`. Use it. Don't drift.**

---

## Two specific things I'd cut

- **The `frontend/` directory's continued existence in the working tree.** Move it to a `legacy/` folder or a separate branch. Every time you `cd` into the repo and see Dashboard.tsx + RetrofitForm.tsx + 35 other files for a parked product, you spend a unit of attention you don't have. Out of sight is not deletion; it's focus.
- **Anything in the spike plan after week 6 that hasn't yet been written.** `next_steps.md` already has the post-week-7 decision matrix. Resist the urge to pre-plan weeks 8–12. Whatever you'd write today is going to be wrong; the week-7 result tells you what's true.

---

## One specific thing I'd add

A `plan/spike/decision.md` file, **created today, empty**, with a one-line header: *"To be filled in week 7 with an honest go / amber / no-go decision against the rubric."* The discipline rule that matters most in the next 6 weeks is: write the decision the day the data is in, not three weeks later when sunk-cost has set in. Pre-creating the file is a small commitment device. Costs nothing. Helps a lot.

---

## Bottom line

The engineering work is good. The corpus is ahead of where most companies have it after 6 months. The methodology doc is a real sales asset. The plan is honest about the discipline rules. *The execution against the discipline rules is currently failing* — Neara email on every commit, secrets in tracked files, no work log, GTM untouched, evaluator unlocked, lawyer unlocked. None of those are technical problems. All of them are 1-hour problems if done this week, 1-month problems if not done this week.

If you fix the discipline this week, fix `render_report` next week, get five ex-FN coffees by week 4, and one pilot conversation by week 6 — this is an obvious-yes business. If you don't, you'll be at week 7 with a half-built engine, no buyer feedback, no evaluator booked, and a Neara legal exposure, and the decision will collapse to "don't ship".

The ceiling is high. The next 14 days determine whether you reach it.
