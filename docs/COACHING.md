# Coaching: one guided path, said like the home page's demo chat (round CO1)

Gustav, 19 November 2026, after testing Krusgraph in claude.ai on his phone: "vi behöver göra det mer enkelt som
användare. Och jag vill kunna bli coachad precis som i demochatten på hemsidan krusgraph.com" (make it simpler for the
user, and coach me exactly like the demo chat on the home page). This round builds on round WB13 (PR #94: the next-step
rules in `next_rules.py`, Accept / Reject / Skip per link, the small map, the folded ontology file) and changes none of
it; it adds a coach on top.

## What makes the demo chat a good coach

The demo chat is `fabric_backend/static/chat-demo.js` (opened by "Try a demo" on every page; buttons only, no free
text and no AI). Read on 19 November 2026, this is what it does:

1. **One step at a time.** Each message is one step: the scan, one question, one result. Nothing comes before you
   ask for it.
2. **A mascot says what happens, in one plain sentence.** Onto points the way ("Shall I check how its tables
   connect?"), the Thinker reads and asks ("Finding the keys", "Counting links against the rows"), the Builder builds
   and is glad when something is done. Each has one voice and one job.
3. **One to three buttons, one of them clearly first.** The first button is the recommended one (`rec`), drawn as the
   primary; the others are quieter, and only the first has a "why" line under it.
4. **It always says why, in a few words.** "For reports in Power BI: tables, links and measures." "The count
   supports it, and you decide."
5. **Short words, nothing technical unless asked.** Tables, links, keys and counts; no rule codes, no file text, no
   tool names on the buttons.
6. **You decide, with the evidence underneath.** The open link is a question with the count beside it ("Yes, add the
   link" / "No, leave it out").
7. **It never leaves you without a next click.** After every result Onto asks "What next?" with the steps not yet
   taken, and at the very end the two ways out (check your own tables, connect to Fabric).
8. **Honest about what it is.** Every result says that nothing was created and what the real tool does in your
   Fabric.

What the demo chat does not have, and the product needed: a visible "where am I" ("Step 3 of 8"), because the real
path is longer and spread over several tool calls and cards.

## What was copied into the product

`fabric_backend/coach.py` (no LLM: templates chosen by fixed rules from the plan state; the same state always gives the
same coach).

- **A single path with eight named stages** the user can see: Choose data → Krusgraph reads the tables → Check the
  links against the rows → You decide the open links → Build silver and gold → Semantic model → Data agent → Done.
- **Every card** shows "Step N of 8: <stage>" right under its title and **one mascot line** in plain words (the site's
  mascots, in their voice: Onto for choosing and for done, the Thinker for reading, checking and deciding, the Builder
  for building). The card's three summary figures are off while the coach speaks, so there is one line, not three; the
  summary sentences are shown as text instead. **Mascots: on/off** still works: off hides the figure, the words stay.
- **One primary button and at most two others** (the card's own primary action, such as Check against the rows on a
  plan or Create on a dry run, stays the primary). The check card's table of every key and link, with its rule codes,
  is under **Details: every key and link**; the map's labels leave the rule code out when the coach is on; the start
  card's nine-step list is under **Every step of the path**.
- **The host model is coached too.** Every tool result's text carries a short, stable Coach block (golden files in
  `tests/golden/coach/`) that tells the assistant what to say in one or two sentences and which single next step to
  offer, so Claude coaches the same way where no card is drawn. It sits before the JSON, which stays last. A creating
  step says "run it only after the user says yes to these names".
- **Start from a plain sentence.** "help me with my SAP data in Fabric" is one of the phrases that start the path
  (server instructions and the start tool's description); the first card asks only for the workspace, as clickable
  choices, then the lakehouse, then the schema.
- **The same words as the demo chat** where the step is the same: `coach.DEMO` holds them, and
  `tests/test_co1_coach.py` fails when one of them is no longer said word for word in `chat-demo.js`, so the site and
  the product cannot drift apart without a test going red.

### The rules, in order (each gives exactly one primary step)

1. An error: the error's own way on (the card's Check status, or n220's steps), else `start` with what is known.
2. No workspace, no source or no schema: Choose data (`start`, which lists the choices as buttons).
3. Data chosen, tables not read: Read the tables (`plan_backend`).
4. Read, not counted against the rows: Check against the rows (`validate_plan`).
5. Counted, and something waits for a person (WB13's `next_rules`: a key that repeats, open links, links that point at
   nothing, doubled amounts): the most useful of those first. If the fix was just asked for, Decide the open links.
6. Counted and nothing open: the build path, a dry run before each creating call, then the call that creates it, only
   on the user's yes: silver and gold (`create_pipeline`) → the semantic model → the data agent → Done.
7. Done: start again on another schema. There is always a next click.

A primary step is never the call just made (same tool and same distinguishing arguments) unless that call failed.

## Before and after (text only, synthetic shop)

The same call, `validate_plan` on the synthetic shop of `fabric_backend/seed.py` (workspace `demo`, lakehouse
`demo_lh`, schema `shop`), as the text a client without cards receives.

**Before** (main after WB13):

```
6 of 6 keys hold. 7 of 7 links hold, with no orphans. 1 header amount repeats on every line, ...

Next steps:
1. Decide the 1 open link
2. Use the line amounts
Reply 1 or 2.

For the assistant, not for the user: 1 = the user asks "Decide the 1 open link: run start with ..."; 2 = ...

The full answer follows as JSON.
```

**After** (the same, plus the Coach block before the JSON):

```
Coach (step 4 of 8: You decide the open links)
Say in one or two short sentences, in plain words: A few links need you: I show the counts. The count supports it, and you decide.
Offer one next step: Decide the 1 open link = start(workspace="demo", source="demo_lh", schema="shop", step="decide").
Only if asked, also: Use the line amounts.
No rule codes, key strings or file text unless the user asks; end with the one next step.
```

On the card (check card, 390 px): before, the title, the summary, three mascot bubbles (Onto with the counts, the
Thinker with what needs attention, the Builder with the next steps), up to four buttons and the full table of keys
and links with rule codes. After: the title, "Step 4 of 8: You decide the open links", the Thinker's one line, the
summary, one primary button (Decide the 1 open link) and one other, and "Details: every key and link (14)" folded.

`plan_backend` on the same shop: before, two next steps ("Show the doubled totals", "Review keys and links") next to the
card's Check button; after, "Step 2 of 8: Krusgraph reads the tables", the Thinker's "Finding the keys and the links
between your tables. I only read; nothing is changed.", and Check against the rows as the one step to offer.

## Verified, and how

On 19 November 2026: unit tests for the stage rules over 23 plan states (`tests/test_co1_coach.py`: exactly one primary
step, never the step just done, never none, at most two others, the expected stage and step), golden files for the
Coach blocks, the hosted server's results on the synthetic shop (the coach in each result, the JSON last), and two
cards (the check card and the start card) in Chromium under a fake host at 390 px in light and dark mode
(`tests/co1_card_browser.js`). The whole suite passed. Not run: claude.ai on a phone; the click-list below is for that.

## Try it on a phone (claude.ai, the Krusgraph connector)

1. Type: help me with my SAP data in Fabric. Expect "Step 1 of 8: Choose data" and your workspaces as buttons.
2. Tap demo, then demo_lh, then sap_silver.
3. On "Step 2 of 8: Krusgraph reads the tables", tap the one primary button (Show the map, then Check against the rows).
4. On the check: "Step 3" or "Step 4 of 8"; the table of keys and links is folded under Details.
5. If links are open: Accept, Reject or Skip each one; then the build dry run ("Step 5 of 8: Build silver and gold").
6. Turn Mascots off: the figure goes, the words stay.

## WB15: one numbering (20 November 2026)

Gustav's second phone test of 19 November showed "Step 1 of 8" next to the start card's "Step 2 of 9". The eight stages
above are kept as the coach's stages, but every card and every Coach block now numbers them on the start path's nine
steps (`coach.step_of`): Choose data is step 1, 2 or 3, the map 4, the check 5, the decisions 6, the doubled totals 7,
the dry runs and builds 8 and done 9; the start card says its own step ("Step 7 of 9: Doubled totals"). The examples
above with "of 8" are from CO1 and kept as history. The start card now draws the mascot at the top of each step itself
(`mcp_apps_start.py`), as the demo chat does: one sentence, two or three buttons, Next, and one Details fold.

