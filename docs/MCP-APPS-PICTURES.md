# The chat demo's pictures in the MCP Apps cards, and Try in Claude (round n170)

The founder, 8 November 2026: *"in the chat on krusgraph.com you see the links visually, and proposals for ontology,
relationships and data products. I want to see that in Claude too."* Since n170, with `KRUSGRAPH_MCP_APPS=1`, the cards
in Claude draw the same pictures as the chat demo. Code: `fabric_backend/mcp_apps_pictures.py`; tests:
`tests/test_n170_card_pictures.py` (with `tests/mcp_apps_pictures_browser.js` and `tests/try_claude_browser.js`).

## The three pictures

| Picture | Cards | What it shows, all from the tool's own result |
| --- | --- | --- |
| Map of the tables and links | `plan_backend` (build card), `validate_plan` (Plan check), `review_plan` (Plan review) | each table with its key columns, or "no key"; each relationship as a line with a label: the rule as a pill (R1, R5 ...) and the column pair. After `validate_plan`: passed in green (✓), failed in red with the orphan count (✕ 3 orphans), not checked in grey (dotted). After `review_plan`: also the review status, a rejected link dashed |
| Ontology proposal | `ontology_draft`, `create_ontology`'s dry run (build card) | the entity types (key marked, "no key" tag otherwise, a composite key named under the entity), the relationship types as lines; under the picture the tool's own sentence on why each keyless entity type has no key (a composite key, or no key found under K3) |
| Data products | `domain_draft` (build card, new in n170) | the proposed domains as tinted groups over the map, the interfaces between them, the tables left out; then one card per product with its tables, the reason for its name, "Owner: not chosen yet" and the Builder's two dry-run buttons over that product's tables: **Create an API for GraphQL for …** and **Build a semantic model for …** (each a dry run under a free name, then Create, as in n169) |

"Data products" is what the chat demo calls `domain_draft`'s domains: the chat demo's list comes from
`/demo/plan.json`, `drafts.as_is.domains`, which `fabric_backend/demo.py` builds with the same `domains.draft()` the
tool uses. The card shows only the products the tool returned; owners are not invented (the tool proposes none).

Under each picture is the same content as a list ("The map as a list", folded), reachable by keyboard and read by a
screen reader; focusing or pointing at a line marks its table or link in the picture. The picture itself is an
`<svg role="img">` with a one-sentence description, which is also what Onto says on the card.

Screenshots (Chromium under a fake host, the shop schema, 8 November 2026): `screenshots/n170-map-plan.png` (the plan),
`screenshots/n170-map-check.png` (the Plan check; one check set to fail by the test, to show the red line),
`screenshots/n170-map-review-dark.png`, `screenshots/n170-ontology.png`, `screenshots/n170-data-products-dark.png`,
`screenshots/n170-try-in-claude.png`.

## How the data reaches the card

The text answer does not change: Lovable, VS Code, Cursor and every text-only client read the same text as before. The
picture's data is added to `structuredContent` only, under `map`, `ontology` and `products` (`mcp_apps.call_result`).
The tool hands what it already computed to `mcp_apps_pictures.keep()` while the call runs (the plan, `validate_plan`'s
full check result before the summary, the ontology's bindings); nothing is kept when no card listens, and a picture that
fails to build is left out without touching the answer. Nothing reads Fabric again for a picture. `review_plan`'s map is
built from its own answer (`review.snapshot` and `review.items`).

## The drawing is the chat demo's

The card does not carry its own renderer. `mcp_apps_pictures.picture_js()` cuts the part of
`fabric_backend/static/chat-demo.js` headed "pictures, drawn from the plan" (the placement search: two columns, the
shortest lines, no line crossing another or running through a table, each data product's tables together; and
`picture()`, which draws the tables, the key marks, the "no key" tags, the lines and the groups) when the card is built,
with four marked additions: bigger cells (room for the key columns and the labels), a `data-table` and a `data-id` on
each table and line, and a second line under a table's name. If `chat-demo.js` changes so that the cut or an addition no
longer fits, building the card raises and the tests fail. The labels on the lines are the card's own: the chat demo has
no room for them. Like the chat demo, a plan of more than 9 tables is placed in plan order instead of searched; above 60
tables the picture shows the first 60 and says so (the list and the answer have them all).

## Try in Claude (the home page's "Try it yourself" card, and step 3 of /start)

**The source.** Anthropic's support article "Open Claude Desktop with a link"
(<https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link>, dated 30 June 2026, read on
8 November 2026) documents `claude://claude.ai/new?q=…` for Claude Desktop: "New chat … q: Text to prefill in the
prompt field", values URL-encoded, the prompt cut at about 14,000 characters. No Anthropic page documents a prefilled
prompt for `https://claude.ai/new` in a browser (a search of anthropic.com, claude.com, support.claude.com and the docs
on 8 November 2026 found none; the documented web parameter `prompt` is for `claude.ai/code`, Claude Code on the web).

**So the button** (`pages.try_in_claude_html`, `site.js` `[data-try-claude]`) is a link to `https://claude.ai/new` in a new
tab that also copies the first question, *"List my Fabric workspaces, then map how the tables in the lakehouse I choose
connect, and check the links against the rows."*, and the note under it says so: paste it in the new chat. Next to it,
**Open in Claude Desktop** fills the question in through the documented link. The note starts with "Connect Krusgraph
first", linking to step 3 of `/start`. Without JavaScript the link still opens a new chat, and the note shows the
question. On the home page it sits in the "Try it yourself" card, not in the hero: the hero keeps its two buttons with the
replayed session right under them (n149, n154).

## What the founder checks in Claude

After a deploy with `"mcp_apps": true`:

1. Ask *"Plan the shop schema of the demo lakehouse."* The plan card shows the map: seven tables, key columns under each
   name, audit_log with "no key", seven lines labelled R1/R5 and their columns.
2. Click **Check against the rows**: the Plan check card's map turns green, with a red line and its orphan count where a
   check fails.
3. Ask *"Draft the ontology."* and *"Draft data products."*: the ontology picture with OrderItems and AuditLog marked
   and why; the data products with a card per product and its two dry-run buttons.
4. On the home page, click **Try in Claude**: a new chat opens on claude.ai and the question is on the clipboard.
