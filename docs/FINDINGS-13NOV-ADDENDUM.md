# Findings of the first-user test: addendum (F1)

A second session of round F1 ran the same test on 15 November 2026 and was cut short before it could report.
[FINDINGS-13NOV.md](FINDINGS-13NOV.md) is the round's report; this file holds only what that report does not have.
Each MCP finding was run again on 16 November 2026 on `main` at `e9b5521`, after n227, n229 and F2 had landed. The
editor findings were reproduced on 15 November 2026 at `15ac3b3`; on 16 November the code lines they name were read
again and are unchanged, but the pages were not rendered a second time.

Nothing here was run against Fabric, nothing says how fast anything is, and every number comes from synthetic data.
Found in the first run and already fixed on `main` since, so left out: the header sum that joined the line table, the
missing word on which NETWR is summed, an amount warning built on a link without a single match, and the Create step
asking the user to confirm a name that is not in the dry run.

## How it was run

- **Hosted MCP server.** The tool functions of `fabric_backend/server.py` called in-process. The SQL analytics endpoint
  was an in-memory SQLite that runs the engine's own T-SQL (`dialects.sqlite_sql`): the synthetic shop in schema
  `shop`, and the synthetic SAP-shaped sample `sap_sd` of `sap_sample.py` in schema `dbo`. Fabric's REST API was a
  double that answers for one lakehouse, with or without Lakehouse schemas, in an otherwise empty workspace.
- **Model editor.** The real `ModelItemEditor` mounted in Chromium the way `index.ui.tsx` mounts it, with a stand-in
  for Fabric's client, calling the real routes of `workload_api.py` over the test suite's own doubles. Widths 375, 768
  and 1280 px; 375 px also with the system in dark mode. The doubles have no routes for a pipeline run, a schedule, a
  data agent or an App item, so a successful run and a successful App were not seen.

Ranked as in the report: **A** blocks a tester, **B** misleads, **C** looks bad. Numbering continues with a prefix so
that nothing collides: `X` for the MCP, `E` for the editor.

## MCP

### XA1. On a lakehouse without schemas, the first button of the dry-run step cannot work

**Where:** `fabric_backend/start_flow.py` (step 8, `would_build`), `server.py` (`create_pipeline`, `gold_views_draft`,
`create_gold_views`).
**Sees:** Step 8 of Start Krusgraph offers five dry runs, the pipeline first, for every source; it reads nothing from
Fabric to decide. On a lakehouse created without Lakehouse schemas, where every table is in `dbo` (the usual place for
tables that landed from SAP), that first button answers `kind: unsupported`: "materialized lake views need a lakehouse
created with schemas; 'sap_lh' has none", and the hint says to create another lakehouse. The second button, the
semantic model, then says it "reads the silver layer (silver_<table>) ... Run that step first", and the step that
would write it there, `create_silver_notebook`, is not among the buttons.
**Fix:** Step 8 reads whether the lakehouse has schemas (the source is already resolved). Without them it offers the
silver notebook in place of the pipeline, says in one sentence why gold views are left out, and keeps the order silver,
model, report.
**Round:** n227 (Start), with n229's gate.

### XA2. In the semantic model of the SAP-shaped sample the order header is cut off from its items and its customer

**Where:** `fabric_backend/graphs.py` (`WEIGHTS`, the active set), seen in `create_semantic_model`,
`semantic_model_draft` and `analyze_schema`.
**Sees:** 10 relationships active, 9 inactive. Inactive: `VBAP -> VBAK` ("it would close a cycle with VBAP - VBRP -
LIPS - LIKP - ZSD_ORDER_EXT - VBAK; the active path has certainty 0.5, this link 0.5") and `VBAK -> KNA1`. Active:
`ZSD_ORDER_EXT -> LIKP`, a guess by rule R3 for which `validate_plan` counts 301 of 301 rows without a match. A report
on that model cannot slice the order value by an item's material or by the customer, and filters travel over a link
that matches nothing. The cause is in the weights: a link from the SAP pack gets the default 0.5, the same as R3 and
below R1's 0.8, and `join_path` shows it ("SAP pack", certainty 0.5).
**Tried:** With the pack's links at 0.7, `VBAP -> VBAK` becomes active and `VBAK -> KNA1` stays inactive, and the R3
link to LIKP stays active. The weight alone is not the fix.
**Fix:** The report's B7 (the counted evidence sets the certainty) plus two rules: a link counted with no match at all
is never active, and a pack's link ranks above R3 and R4. Then a tie is broken in favour of the direct link from a
header to its master data.
**Round:** new (Engine), with n229's gate for the link without a match.

### XB1. One column pair linked to three tables, and nothing is called ambiguous

**Where:** `fabric_backend/infer.py` (R3), `plan_backend`.
**Sees:** `ZSD_ORDER_EXT.MANDT+VBELN` is linked to VBAK, LIKP and VBRK at once (VBELN is the document number in all
three), and `ambiguous` is `[]`. `validate_plan` then shows two of the three with 100.0% of the rows pointing at
nothing, but its next steps name neither; the first one is about 3 of 844 rows. Every dry run still carries all three.
**Fix:** When R3 gives the same columns more than one target, list them under `ambiguous` and keep none until one is
counted or confirmed. `validate_plan`'s first next step for a link without a single match is to reject it.
**Round:** new (Engine); n229 for the next step.

### XB2. A sum across customers says nothing about the currency

**Where:** `fabric_backend/answers.py`.
**Sees:** "total NETWR per customer" on VBAK and KNA1 gives `SUM(t0.[NETWR])` grouped by customer and no assumption.
The SAP pack names WAERK as the currency of VBAK.NETWR (`sap_pack_draft`, `amounts`), and two orders can differ
in it. The sample has one currency, so its numbers are right; the draft would add different currencies together
without a word.
**Fix:** When the pack or a name rule gives an amount a currency column, group by it or say in `assumptions` that the
sum is across currencies.
**Round:** n229.

### XB3. On the shop sample, the one "doubled total" is a list price

**Where:** `fabric_backend/amounts.py`; the shop seed.
**Sees:** `validate_plan` on the shop says `needs_attention: 1`: `products.list_price` summed over the order lines.
A price per unit is not a total anyone sums, and the fix plan's own third option says so ("not summed at all (a price
or a rate)"). The first sample a tester opens shows the product's main point on a column where it does not apply.
**Fix:** A name rule for prices and rates (price, pris, rate, unit) that keeps them out of the amount levels, and an
amount on the order header in the shop seed so that the sample still shows a real one.
**Round:** new (Engine).

## Model editor

### EA1. The way forward is an icon without a word

**Where:** `app/components/ItemEditor/RibbonToolbarAction.tsx` (the label is a tooltip only), the actions in
`ModelItemEditor.tsx`.
**Sees:** The mascot says "When you have decided, choose Next." Nothing on the page says Next. The ribbon is six icons
of 32 px: Next, Back, Create and Data product among them. A phone has no hover, so the names never show. Same at 768
and 1280 px.
**Fix:** The label beside the icon for Next, Back, Create and Data product, or a Next button at the end of the review;
44 px targets.
**Round:** new (Workload).

### EA2. When the pipeline's run does not start, the result never finishes

**Where:** `ModelItemEditor.tsx`, `followRun` (it returns when the run has no id, before the cards that wait for the
run are stopped); `createWords.ts`, the banner.
**Sees:** With Run once chosen and the run refused: "6 of 7 created, 1 waiting." for more than five minutes; the
report's card says it "waits for the pipeline's run"; no Try again and no finish. After reopening the item a green
banner celebrates "Done: 6 of 7 created", and the list of next steps does not mention the report.
**Fix:** When the run has no id or did not start, stop every card that waits for it and say why. The banner is green
and glad only when everything chosen was made.
**Round:** n229 (next steps after Create).

### EA3. On a phone the first form is cut off at the right edge

**Where:** `app/components/ItemEditor/ItemEditor.scss`, `.item-editor-view-empty` (width 100% plus padding: 399 px in
a 375 px window).
**Sees:** With a warehouse or a mirrored database chosen, the sentences end mid-word at the edge and the three buttons
lose their right border. With a lakehouse only the card's border is cut. At 768 px the card is 28 px too wide.
**Fix:** `box-sizing: border-box; max-width: 100%` on the view and on `.krusgraph-empty-form`.
**Round:** new (Workload).

### EA4. With the system in dark mode, the Data product page's state words cannot be read

**Where:** `DataProductView.tsx`, the `prefers-color-scheme: dark` block.
**Sees:** The editor always uses Fabric's light theme, so the background stays light while the page switches its
status colours to the ones meant for a dark background. Measured contrast: "Built" and "Up to date" 1.94:1, "Out of
date" 1.26:1, the delete button 2.03:1. The existing dark test renders the page without Fluent's tokens and passes.
**Fix:** Drop the dark overrides of the four status colours, or take them from Fluent's status tokens.
**Round:** new (Workload).

### EB1. The Data product page counts the silver and gold notebooks twice

**Where:** `buildWords.ts` (`mergeCreated`), `productWords.ts` (`rowsOf`).
**Sees:** After a Create of silver, gold, pipeline, model, API and ontology: "9 built", while the delete dry run on the
same page says 7 items. Two extra rows say of the notebooks that "this item has no id saved for it" and point to Look
for leftovers, which answers "No leftovers".
**Fix:** `rowsOf` matches the last Create's outputs by type and name as well.
**Round:** new (Workload).

### EB2. A model created minutes ago is called out of date

**Where:** `workload_api.py` (`plan_mark`, `same_plan`); cause not found.
**Sees:** After a Create with one link rejected and Run once chosen: "Semantic model demo_lh_model: Out of date: built
from a different plan (schema shop, 5 links; now shop, 6 links)". The other items of the same Create say 6 links.
**Fix:** Find why the model's mark counts one link fewer than the others in the same Create; a test with one rejected
link.
**Round:** n229 (it verifies what was built).

### EB3. Words that contradict the choices made on the same page

**Where:** `buildWords.ts` (lines 38, 246, 282 and 570 at `15ac3b3`).
**Sees:** "It is not run or scheduled." directly above the ticked "Run once after Create" and a daily schedule. "Create
refreshes the model once; nothing else is run or scheduled." beside "Create starts one run". The button says "Create
and update" when Create will only ask. Cards of items that exist say "0 silver table(s)", "0 gold view(s)", "One page
with 0 visuals".
**Fix:** "... unless you tick it below"; drop the second sentence when a job is chosen; count an update only when one
will happen; show the existing item's facts whenever Create will ask.
**Round:** new (Workload).

### EB4. Suggested data products go stale after a decision

**Where:** `ModelItemEditor.tsx` (the suggestion is set from the review and the check, not after a decision).
**Sees:** After rejecting `order_items -> orders`, the outputs page says "customers: 4 tables" with order_items among
them; the next page says customers has three and order_items belongs to products.
**Fix:** Recompute on Next.
**Round:** new (Workload).

### EB5. Failures show the program's own words

**Where:** `ItemCRUDController.ts`, `ModelItemEditor.tsx`, `engineClient.ts`, the `where` text in `workload_api.py`.
**Sees:** "The item could not be opened: Cannot read properties of undefined (reading 'item'). Fabric is busy, try
again in a few minutes.", followed by the first-run form as if the item were new. A rejected sign-in: "invalid token:
DecodeError". Errors name the workspace by its id. Elsewhere: "list_sources shows what the signed-in account can
see" (a tool of the chat), "Leiden-style communities on the key graph, domain_draft's method", "summary.notes",
"README.generated.md", "outputs.json", "Plan plan-dc47808ed933, schema sha256:f9488893c117d8c7".
**Fix:** One sentence per case in the user's words: "Fabric did not return this item. Try again."; on a 401 forget the
token, try once more, then "Your sign-in expired. Reload the item."; the workspace by name; no file, tool or method
names.
**Round:** new (Workload); the report's B11 covers the id.

### EC1. Small things on the phone

- The warning under a rejected link that holds is one line 842 px wide and is cut after "the sema"
  (`ModelItemViews.tsx`, the message bar needs `layout="multiline"`).
- On the App card two sentences run together ("...are in preview.Could not check...") and step 1 says "Download the
  package below" while the link is above it.
- Labels lower-cased into "Name of the api for graphql" and "Create app (rayfin, preview) demo_lh_app".
- Text of 12 px and targets of 32 px outside the three pages n225 tests: the first form's description, Accept and
  Reject, the choice buttons, the ribbon.
- Labels in the data flow end in "…" ("one row per key: key id checke…"); the full text needs a tap.
- "Read the lakehouse again" is the tooltip for a warehouse too.
- With the mascots on, the finish says the same sentence twice, in the bubbles and in the banner.
- The production build warns that the vendors bundle is 613 KiB, most of it icons.

**Round:** new (Workload).

## What came out clean in the editor

No page error, no failed request, no untranslated key and no horizontal scroll bar in any view. Every address in the
editor and the manifest answers from the server (`/docs`, `/support`, `/privacy`, `/terms`, `/workload/attestation`,
`/it`, `/pilot/fabric`). No field the editor reads is one the server never sends. `npm test`, the type check, the
production build and both packages passed.
