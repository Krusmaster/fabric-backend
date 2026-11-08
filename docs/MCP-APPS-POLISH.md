# The MCP Apps cards before the film (round n172)

The founder tried the cards in Claude on 8 November 2026 (deployed 20:20 UTC; `demo_lh`, schema `shop`) and found eight
problems, all in screenshots. This page says what changed for each, where, and how it is tested. Code:
`fabric_backend/mcp_apps_words.py` (new), `mcp_apps.py`, `mcp_apps_build.py`, `mcp_apps_pictures.py`,
`mcp_apps_mascots.py`, `errors.py` (`transient`), `platforms/fabric.py` (`connect`), `infer.py` (R5). Tests:
`tests/test_n172_card_polish.py`, with `tests/mcp_apps_n172_browser.js` (Chromium under a fake host at 640 and 720 px).

## 1. A transient SQL error no longer changes the result

Seen: `plan_backend`'s R5 counting query for `orders.ship_to_id -> addresses.address_id` failed with "TCP Provider:
Error code 0x2714"; the plan said 6 relationships and left the link as proposed, while `validate_plan` a moment later
counted 7 of 7.

- **Retry.** `platforms/fabric.connect` tries a read again on a fresh connection when `errors.transient` says the error
  is transient: at most 3 tries, 1 s then 3 s between them (`RETRY_DELAYS`); the login is covered the same way. DDL is
  not tried again. `validate_plan` and every other read on the SQL analytics endpoint get the same.
- **Which errors.** From Microsoft Learn, "Troubleshoot common connection issues to Azure SQL Database and SQL database
  in Fabric" (`azure-sql/database/troubleshoot-common-errors-issues`, updated 19 October 2026, read 8 November 2026),
  "List of transient fault error codes": 615, 926, 4221, 40197, 40501, 40613, 49918, 49919, 49920, and the TCP
  Provider's "forcibly closed" / "transport-level error" messages ("use a fixed number of retry attempts ... before
  considering them permanent failures"); the ODBC SQLSTATE 08S01 (Communication link failure) with the TCP Provider's
  socket codes 0x2714 (the one seen), 0x2746, 0x2745, 0x68, 0x20; and `errors._sql`'s own mapping (08S01 is
  "unreachable"). **Never** tried again: the sign-in (28000, 18456, AADSTS), syntax and permission errors (42000), a
  missing object or column (42S02, 42S22), timeouts (HYT00, HYT01). The page recommends 5 s before a first retry; the
  delays here are shorter because the query runs inside a chat's tool call, and three tries bound the wait to 4 s.
- **When every try fails.** The candidate is "not counted", never "the rows did not support it":
  `proposed[].not_counted: "failed"` with the reason "not counted: the counting query could not run (the connection to
  the SQL endpoint dropped: ...)", `counted_in_rows.failed`, and a summary line ("1 candidate link(s) could not be
  counted because the counting query could not run: orders.ship_to_id -> addresses; not counted, neither confirmed nor
  rejected ..."). The card draws the link grey and dotted with "R5 not counted"; the Thinker says "I couldn't count
  ship_to_id → addresses: the connection to the data dropped. Shall I count it again?" with a **Count again** button
  (`plan_backend`, the same arguments).

## 2. The map's labels

Each label is placed on the drawn segment of its own line (between the two tables' edges): at its middle, else slid
along the line, else with its first line only (rule and state); it never covers a table, another label or the
picture's edge. One that fits nowhere is left out of the picture (the line's id is in `data-unlabelled`) and stays in
"The map as a list". The cells are wider apart (`GX = 210`), so the shop schema's map is 534 px wide and fits Claude's
card at 640-720 px with every label drawn. A plan of more than 9 tables, which the chat demo places in plan order, is
improved by swapping tables between cells while the chat demo's own cost falls (line length, lines through a table,
crossings), bounded to 12 passes. The browser test checks, at 640 and 720 px, for the shop schema and a 12-table plan,
that no label meets a table or another label, no tables meet, and each label's centre lies on its line.

## 3-6. What the card says

The card's words come from the server, in `structuredContent.kg_card` only (the text answer is unchanged):

| | Plan (`plan_backend`) | Plan check (`validate_plan`) |
| --- | --- | --- |
| Title | Plan | Plan check |
| Onto (says the numbers, once) | 7 tables, 6 with a key. 7 links: 6 by name, 1 found from the values (ship_to_id → addresses). audit_log has no key, so nothing can point to it. | 6 of 6 keys hold. 7 of 7 links hold, with no orphans. 1 header amount repeats on every line, so it must not be summed over the lines. 1 thing needs attention. |
| Thinker | Shall I check these links against the rows? | One thing needs your attention, listed below. I would look at it before building. |
| Builder | I can build a semantic model, an ontology or an API from this plan. Each shows a dry run first. | the same |

- The card's own copy of Onto's sentences (the status line; on Plan check also the count tiles) is hidden while Onto's
  bubble shows them and comes back with "Mascots: off": said once, never only by a mascot.
- No bubble shows argument syntax: `mcp_apps_words.WORDS_WITH_ARGUMENTS` (and the same pattern in the card,
  `ARGS_SAID`) keeps out `name=value`, "run <tool> with" and `tool(`. The buttons carry the arguments; text clients keep
  each action's `say` ("Check against the rows: run validate_plan with workspace=...").
- The old summary ("R5 counted 1 code or role column(s) in the rows: 1 counting query(ies) ...") is only under "Show
  details" now.
- Maintainer notes are left out of what a card shows (`customer()` in the card script): sentences about unit tests,
  end-to-end tests, live runs, synthetic data. "the active path has certainty 0.8, this link 0.5" becomes "the other
  path stays active and this R5 link is inactive"; `create_semantic_model`'s `summary.inactive[]` now carries `rule`.
  The tool's text answer keeps the notes (existing tests and the server's instructions use them).

## 7. The Plan check card

The Builder's three buttons (Build a semantic model, Create an ontology, Create an API for GraphQL, each a dry run
first) come right after "Needs attention"; the n103 drafts (`semantic_model_draft`, `answer_query_draft`, ...) are
folded under **More** ("Drafts that only read; nothing is created"). "Next steps (each reads or drafts; nothing is
created)" is gone.

## 9. Create under the dry run (founder, 8 November 2026, 21:45 CET)

Seen: in Claude, **Build a semantic model (shop_model_2)** drew its dry run on the Plan card, with no **Create** under
it, so nothing could be created. Cause: the MCP SDK calls a tool with every parameter, defaults included (`keys`,
`confirmed`, `tables` as null; `create_backend`'s `writable` and `allow_removals` false; `create_report`'s
`empty_page`), where the n169 tests called the tools directly with only the given arguments. The dry run's Create
action therefore carried arguments the card had not sent, and the card, which shows Create only for exactly the dry
run's arguments, left it out, for all four builds.

Fix (`mcp_apps_build.with_actions`, `ACTIONS_JS`): the buttons are built from what the call changed: a null argument,
or one equal to the tool's own default, is left out; the Create action carries the tool's `defaults`, and the card
compares the effective arguments (null or default = not given). The rule stays: Create is shown only for the dry run's
own arguments with `dry_run: false`, and sends exactly the dry run's arguments with `dry_run: false`.

Tests: `test_through_the_sdk_a_dry_runs_create_carries_the_cards_arguments` (the three plan builds, through the SDK's
own client and server) and `test_build_then_create_on_the_plan_card_for_all_four_builds` (Chromium, fake host running
`tools/call` with answers the SDK produced: click the build, the dry run shows, Create is visible, click it, the call
carries `dry_run: false` and the same arguments; then **Create a report on it** under the created model, the same way).
Both fail without the fix.

## 8. Themes

Both themes use the host's colour variables with light/dark fallbacks, as before; the tests run the cards in light and
dark Chromium and check the bubble and label text differ from their backgrounds. A `[hidden]` rule was added to the
three cards: `.counts { display: grid }` had kept the tiles visible when hidden.

Screenshots (Chromium, fake host, 8 November 2026): `screenshots/n172-plan.png`, `screenshots/n172-plan-check-dark.png`,
`screenshots/n172-plan-not-counted.png`, `screenshots/n172-twelve-tables.png`.

## What the founder checks in Claude

1. *"Plan the shop schema of the demo lakehouse."* Title "Plan"; Onto's three sentences; the Thinker's question and
   **Check against the rows**; the Builder's sentence and three builds; every label on its line.
2. **Mascots: off**: the sentences appear as the card's status line; **on** again: only Onto says them.
3. **Check against the rows**: "Plan check", the map green, the Builder's builds, the drafts under **More**.
4. **Build a semantic model** → its dry run: no "Unit-tested" or "certainty" on the card.
