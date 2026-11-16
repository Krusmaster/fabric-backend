# The MCP Apps cards after the founder's test in claude.ai (round n227)

The founder tried the cards in claude.ai on the web on 12 November 2026 (deploy `src-37ff21adce4ff691`). What worked:
the Start Krusgraph stepper with clickable buttons, the reads/writes badges, the mascots, and real items created from
the chat (`shop_model_3`, `shop_model_3_report`, `shop_ontology_3`). This page says what was wrong, what changed and
how it is tested, point by point. Code: `fabric_backend/mcp_apps_words.py`, the new `mcp_apps_result.py`,
`mcp_apps.py`, `mcp_apps_build.py`, `mcp_apps_next.py`, `mcp_apps_start.py`, `mcp_apps_review.py`, `start_flow.py`;
in `server.py` the `check` parameter, the `started` answer and the schema choice; `deploy.answer_by`. Tests:
`tests/test_n227_cards.py` with `tests/mcp_apps_n227_browser.js` (Chromium under a fake host at 375 px).

**The key finding.** The answers already carried plain words in `kg_card`, but a button's answer was drawn from the raw
`summary`. Every card now reads `kg_card` first, everywhere, and every tool has one: with `KRUSGRAPH_MCP_APPS=1` every
tool's answer is also returned as `structuredContent` with `kg_card` (`mcp_apps.structured`); the text answer is
unchanged. `kg_card` is `{title, result, lines, notes}`: one line, at most five lines, and notes of one line each with
their list behind Show. An answer without it (an older server) falls back to its own `summary`, lists or numbers.

| # | Before | After |
| --- | --- | --- |
| 1 | The Start card's subtitle and the mascot said the same sentence | Said once: in Onto's bubble; on the card only with "Mascots: off" |
| 2 | "Which workspace? list_workspaces lists the ones your account can open." | "Which workspace shall we start in? I can list the ones your account can open." |
| 2 | "Asked the host to run create_report; it may ask you first." | "Builder: Creating shop_model_3_report in Fabric…" with the seconds counting |
| 2 | Next steps: `Check against the rows validate_plan`, `Draft a semantic model semantic_model_draft`; "Run semantic_model_draft" | "Check against the rows", "Draft a semantic model" |
| 2 | "SAP pack" with no explanation | "SAP pack: Krusgraph's list of known SAP keys.", once per card, the first time the words appear |
| 3 | "Answer: no summary in it; the whole answer is under Show details." | "1 workspace: demo." / "2 sources: demo_lh (Lakehouse) and demo_wh (Warehouse)." |
| 3 | Show details: one JSON block | Readable lines first ("Tables: 7 …"), then "Show the raw answer (JSON)" |
| 4 | "7 relationships R5 counted 1 code or role column(s) in the rows: 1 counting query(ies) …" | "7 tables, 6 with a key." "7 links: 6 by name, 1 found from the values (ship_to_id → addresses)." |
| 4 | "krusgraph (1 tables)", "1 rows, 0 empty", "Total NETWR (sap_vbrk) (sap_vbrk)" | "krusgraph (1 table)", "1 row, 0 empty", "Total NETWR (sap_vbrk)" |
| 11 | Nothing while a tool ran; after `create_backend`: "7 tables, 6 with keys, 7 relationships R5 counted …" | "Builder: Creating shop_api_3 in Fabric…" with the seconds counting, then "✓ Created shop_api_3, an API for GraphQL, in Fabric." with its endpoint |
| 13 | 24 lines "Not expressible: … → …" | "24 links need a combined key column; Krusgraph can add them in a gold view. Show" |

## 1-4, 13. Words

`mcp_apps_words.summary_card` gives a plan, a semantic model draft, an ontology draft, a report and an API the same
form, for a draft, a dry run, a created item and a create Fabric is still working on. `agree()` makes a number agree
with its noun, `undoubled()` drops a bracket said twice, `plain()` replaces a tool's name where an answer's own
sentence has one (`TOOLS_NAMED` is the list of the server's tools; `list_price` is a column, not a tool). The cards'
own sentences name no tool: buttons carry a label, the chat gets the step's `ask` ("Check against the rows for
shop."), and `say`, with the tool and its arguments, stays in the answer for text clients.

## 5, 12. What is offered, and when

- After `plan_backend`: one primary button, **Check against the rows**. No build, and no draft of one.
- After `validate_plan`: the three builds when every key holds. A key that does not hold: no build on the card, with
  the reason ("1 key does not hold in the rows, so no build is offered here …"); a build can still be asked for in the
  chat. Links with orphans: the builds, with a line that says so.
- A name that ends in `_2`, `_3`: "Named shop_model_3 because shop_model and shop_model_2 are already in this
  workspace; nothing that exists is changed."
- The schema choice never lists `krusgraph_quarantine` (also in the text answer), and the card offers no `silver`,
  `gold` or `krusgraph` button while a source schema is there.

## 6. What the client model is asked

The server's instructions (hosted and local) and the lead of every card result ask the model, with the reason, not to
repeat what a card already shows and to add no reason, source or name the answer does not hold; Claude had written
"the keys are from SAP's own documentation" and "SAP calls this link unconditional". The hosted instructions no longer
say the SAP keys "come from public sources"; they say what the SAP pack is. A request, not a threat: a test keeps
"must", "never", "always" and the like out of these sentences.

## 7. Where no card is drawn

The lead of the text answer is a numbered list in plain words ("Next steps: 1. Check against the rows 2. … Reply 1, 2
or 3."); which call each number is stands in a last paragraph for the model. Every browser test runs at 375 px and
fails when a card scrolls sideways.

## 8. Open in Fabric

The item itself, for every kind a card creates (`mcp_apps_build.ITEM_PATHS`):

| Kind | Address after `/groups/{workspace}/` | Source |
| --- | --- | --- |
| Ontology | `ontologies/{id}` | Microsoft Learn, "Use Ontology MCP Server (Preview)", ms.date 14 April 2026, read 15 November 2026 |
| Semantic model | `datasets/{id}/details` | the Power BI path the cards have used since n169 |
| Report | `reports/{id}` | the same |
| API for GraphQL | `graphql/{id}` | **Unverified**: no Learn page found on 15 November 2026 shows it; by the pattern `/groups/{workspace}/<kind>/{item}` (Learn shows it for lakehouses and ontologies) |

Because the API's address is not confirmed, its card also offers "the workspace's list". Each kind has a unit test of
the address; that the address opens the item in the portal is for the founder to try once per kind.

## 9. A create that answers in time

Seen: "Request timed out" in the host, and a second click that updated what the first had made. Now
`create_backend`, `create_semantic_model`, `create_ontology` and `create_report` end their wait for Fabric 40 seconds
after the call began (`server.CREATE_ANSWER_SECONDS`, `deploy.answer_by`) and answer `started` with the operation's id
(the kind stays `timeout`). The card then shows one button, **Check status**: the same tool with `check` set, which
reads the operation's state and whether an item of that name and kind is in the workspace, and creates nothing.
Create is never offered a second time: not after it ran, not when the host stops waiting (the card then says so and
offers Check status), and the server does not send the same definition again while the first one's outcome is unknown
(kept in the process's memory for 10 minutes; a second replica would not know). How long claude.ai waits is not
documented anywhere this round could read; 40 seconds is the server's own bound, not a measurement.

## 10. The ontology after Create

A static SVG drawn by the card (`mcp_apps_result.ontoSvg`): one row per entity type with "key: …", "no key" or "key of
several columns: …" (solid or dashed box), each relationship type as a labelled arrow, the same as a list under it,
and the notes in plain words ("1 entity type has no key, so nothing can point at it …"). 343 px wide, so it fits 375.

## 11. Waiting

`waitView`: who works, on what, an indicator and the seconds this card has waited. The cards have no CSS animation
(n136), so the indicator is three dots stepped by the same one-second timer; with `prefers-reduced-motion` it stands
still and only the seconds change.

## What the tests do not show

That Claude renders the cards, runs a card's `tools/call`, or keeps to the instructions; how long the host waits; that
each address opens its item. Those are tried by hand after a deploy, with `KRUSGRAPH_MCP_APPS=1`.
