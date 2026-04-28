# Next steps

Working backwards from the quit trigger (£25k MRR sustained 2 months + 9 months runway). 8 weeks to a real go/no-go, then act on the decision instead of momentum.

## This week (Apr 27 – May 3): unblock the blockers

Two things that gate everything downstream. Do them this week or the rest of the plan slips.

**Employment lawyer letter.** Email a UK employment lawyer Monday. Brief: *"Employed at Neara (utility-side grid digital twin software). Building a side product for industrial demand-side decarbonisation pathway analysis. Need a written scope opinion: what's clean, what's contested, what's a no-go."* Pay for the letter, not a call. Cost: £500–1,500. Until the letter is in hand: no outreach, no company registration, no accepting pilot money.

**Lock in week-6 evaluator.** Pick the most senior, most opinionated ex-FN colleague who'll tell you the truth. Email this week: *"6-week feasibility spike, will you spend 4 hours in early June reviewing the output against your standard? Paying day rate."* Get a date in their calendar. If they say no, find out now.

## Weeks 1–2 (Apr 27 – May 10): engine spike + GTM groundwork in parallel

**Engine.** Stick to `spike/README.md` week 1. Corpus + pgvector + system prompt. Don't touch engine code yet — the corpus is the moat, build it properly.

**GTM groundwork.** Build two lists in a spreadsheet, no outreach yet:

- *List A — consultancy contacts.* 10 ex-FN / WSP / Arup / ERM / Wood people you can have a coffee with. Senior engineers, not partners. Purpose: validate the workflow you're replacing.
- *List B — industrial targets.* 15 UK food & drink sites with public IETF involvement or visible decarb roadmaps. Diageo, Tate & Lyle, Britvic, Nestlé UK, Müller, Coca-Cola Europacific, Unilever, Greene King, Heineken UK, Arla, Cranswick, 2 Sisters, Premier Foods, Bakkavor, Warburtons. For each: find the named head of energy / sustainability / engineering on LinkedIn. Hold list until lawyer letter clears.

## Weeks 3–4 (May 11 – May 24): engine v0 + first conversations

**Engine.** Spike weeks 2–3. Honest reality check: assume 1,500 lines of MUNTec reuse, not 3,000. Industrial steam at MW scale is not residential heat pumps. Different physics, different scale, different code.

**Consultancy coffees.** Assuming lawyer cleared scope: 5 ex-FN coffees. Not pitching. Asking three questions:

1. How do you currently do an industrial steam decarb pathway study? Walk me through the last one.
2. What part do you hate most?
3. If a tool produced an 80%-quality version of the report in an hour, what would that be worth — to you, and to the partner who actually approves software spend?

Question 3 is the one that matters and the one the current plan doesn't have an answer to.

## Weeks 5–6 (May 25 – Jun 7): real-world test + GTM validation in parallel

**Engine.** Spike weeks 4–5. Monte Carlo, self-critique, real-world synthesised case from public IETF data.

**Industrial pilot conversations.** Reach out to 3 names from List B. Pitch: *"Building a tool that produces steam-electrification pathway analysis. I'd like to do a £15k scoped study on your site using the tool and a draft report from me, delivered July. Can we talk?"* Selling your own consulting hours with a tool behind them, not software. One signed £15k pilot at week 6 changes the year-1 path completely.

## Week 7 (Jun 8–14): independent eval + go/no-go

**Engine.** Ex-FN colleague reviews using the rubric. Score honestly.

**Decision matrix:**

| Engine score | Industrial pilot signed? | Action |
|---|---|---|
| Green (4+/5) | Yes | Fundraise decision (bootstrap or seed). Move to full roadmap. |
| Green | No | 10 more industrial conversations before committing. Engine works, market is the question. |
| Amber | Yes | 4–6 weeks fixing the engine. Pilot revenue funds it. |
| Amber | No | Pause. Narrow scope or wait 6–12 months for next-gen models. |
| Red | Either | Narrow scope or shelve. Don't sunk-cost it. |

## Week 8 (Jun 15–21): act on the decision

**If green + pilot signed:** register the limited company (personal address, personal email), open business bank account, draft pilot SOW, deliver in August.

**Anything else:** write a 1-page post-mortem in `plan/spike/decision.md` and follow it. Don't drift.

## Standing rules every week regardless

- Work-log entry every session. Date, hours, what. Neara separation evidence if it ever matters.
- One non-code thing per week. Coffee, phone call, piece of writing. The engine doesn't need 100% of 15 hours.
- Sunday evening: 30 minutes reviewing `spike/README.md` against what you actually did. Ask: *am I still in scope, or did I drift?* Scope discipline is the single biggest risk after the GTM question.

## Things that will try to derail you

- Buyer interest broadening the decision class before week 6. Refuse politely.
- A consultancy partner offering a "non-binding LOI." Worth nothing. Only paid pilots count.
- Realisation that the engine is harder than the spike timeline. Expected. Stick to the timeline; week 6 is a feasibility checkpoint, not a delivery date.
- Neara work pulling 50+ hour weeks. Protect the 15 hours. If you can't, log it and slip the spike, don't burn yourself out trying to hit both.
- The temptation to pre-write weeks 3–6 spike docs in detail. Don't. They'll change.
