# The website: how it is built and how to change it

The site is served by the same process as the MCP server (`fabric_backend/server.py`, `build_app()`). There is
no build step, no bundler and no external resource at runtime. This note is for whoever edits it next.

## Files

| Path | What |
| --- | --- |
| `fabric_backend/pages.py` | the page registry (`PAGES`: path → template, title, description, nav key), the shared shell (header, footer, meta tags), canonical/Open Graph/Twitter tags, JSON-LD for `/`, the small Markdown renderer for `/docs`, `/privacy` and `/lovable`, the Markdown versions of the pages (`/docs.md`, `/start.md`, …), the 404 page, the static-file resolver |
| `fabric_backend/discovery.py` | everything for crawlers and agents: `/sitemap.xml` (`PUBLIC_PAGES`), `/robots.txt`, `/llms.txt`, the MCP Server Card (`/mcp/server-card`) and the AI Catalog (`/.well-known/ai-catalog.json`) |
| `fabric_backend/page_templates/*.html` | one body template per page (`home.html` is `/`: the hero, the row of what the product connects, a short way in to `/demo`; `demo.html` is the guided demo and its graph); `{{VAR}}` placeholders are filled from the environment (`PRODUCT`, `PRODUCT_URL`, `CONTACT`, `MCP_URL`, `CLIENT_ID`, `GITHUB`, …) and HTML-escaped (the Markdown pages escape while rendering); `{{#IF VAR}}…{{/IF}}` keeps a block only when the variable is set; `{{DEMO_*}}` placeholders are filled from the demo plan |
| `fabric_backend/page_templates/DOCS.md`, `PRIVACY.md`, `LOVABLE.md` | the Markdown pages (served as HTML and as `.md`); `{{RULES_TABLE}}` in DOCS.md is generated from `infer.RULES` |
| `fabric_backend/static/site.css` | design tokens (`:root`, dark values under `prefers-color-scheme: dark`), shell, components, the graph, the mascot poses and animations |
| `fabric_backend/static/site.js` | navigation toggle, the graph renderer (`Graph`), and the per-page wiring for `/demo`, `/explore`, `/partners/workspace`, `/mascots`; on `/` it sends the guided demo's old anchors (`#guide`, `#demo`, …) on to the same anchor on `/demo` |
| `fabric_backend/static/chat-demo.js`, `chat-demo.css` | the chat demo (n92, on every ordinary page since n93), loaded on a click on its button or to restore a chat left open; see below |
| `fabric_backend/static/mascots.js` | the three figures as inline SVG (`Mascots.svg`), the off switch, gaze, the follower, the builder sequence |
| `fabric_backend/static/fonts/` | Fredoka and Nunito, variable, subset to Latin, SIL OFL (licence files beside them) |
| `fabric_backend/static/favicon.svg|png`, `og.svg|png` | icon and Open Graph image; the PNGs are rendered from the SVGs with Playwright |
| `fabric_backend/demo.py` | `demo_plan()`: the real `plan()` on `seed.schema()`, served as `/demo/plan.json`; its `suggestions` list is what `suggest_relationships` answers on the synthetic rows for the column no naming rule links (`orders.ship_to_id` → `addresses`, with its data check and the next candidate), not hand-written. `home_guide()`: the guided example on `/demo` in four steps (the question, the suggestion with its check, the visitor's review, the result card), server-rendered so it reads without JavaScript; accepting decides the meaning and never turns into a check |
| `fabric_backend/offering.py` | n177: the four products as data (Krusgraph for Fabric, for Claude, for Lovable, Open Source: `WAYS`, `DECIDE`, `BUILT`, `NOT_PRODUCTS`); one logo, no product logos; renders the product offering diagram (home page and `/choose`), `/choose`'s comparison and decision guide, the short guide on `/start` and the home page, `/choose.md`, and the screenshots and permissions table of the docs' *Krusgraph for Fabric* group. Statuses come from `tool_status`, prices only from what `/pricing` says |
| `fabric_backend/dbt_flow.py` | n177: a dbt project's files as a flow (sources → staging → marts → model), drawn by the `dbt-flow` block of `chat-demo.js` in the chat demo and on the `dbt_schema` card |
| `workload/scripts/screens/` | n177: the docs' screenshots of the Krusgraph Model editor: its own view components rendered with the engine's answers on synthetic data (`README.md` there) |
| `tests/test_site.py`, `tests/test_site_extras.py` | every route, headers, honesty rules, the plan JSON, discovery documents |
| `server.json`, `docs/PUBLISHING.md` | the MCP Registry entry and how to publish it (not published) |
| `tests/test_browser.py` + `tests/browser_check.js` | Playwright checks; skipped when Node + Playwright + Chromium are missing |
| `docs/screenshots/` | the reviewed screenshots (1280 light, 1280 dark, 390 light per page, plus interaction states) |

## The docs' sub-pages (n86a)

`DOCS.md` is the only source of the docs. `pages.docs_pages()` cuts the rendered Markdown into pages when they are served:
the intro and "Why" are `/docs` (the overview, with links to every page), each other `##` section is a group page
(`/docs/get-started`, …: its heading and the lines before its first `###`) and each `###` a page under it
(`/docs/get-started/connect`). The menu's group labels are `DOCS_GROUPS`; everything else in it is the headings, plus
`/start`, `/it` and `/lovable` (`DOCS_MORE`). Layout: menu left, text in the middle, "On this page" right from 1240 px,
breadcrumbs, previous and next; under 960 px the menu is a `<details>` above the text, which works without JavaScript.
`/docs.md` and `/llms-full.txt` are the same text as before; `/llms.txt` and the sitemap list the sub-pages. Old links
such as `/docs#test-status` are sent on by `static/docs.js`, from a map `/docs` carries as JSON (`docs_anchors()`, built
from the headings); without JavaScript they stay on the overview. Links between headings inside the text point to the
page that has the heading. The sub-pages have `/docs`'s headers and policy, the chat button and the Mascots switch.
Checks: `tests/test_docs_pages.py` and `tests/docs_browser.js` (through `tests/test_browser.py`).

## The Concepts pages (n86b)

`## Concepts` in `DOCS.md` (after *Get started*) has five pages: How it works, Ontologies, Data products, How they
connect and Vision. Their examples are not typed by hand: `{{CONCEPT_...}}` placeholders are filled by
`fabric_backend/concepts.py` from the engine run on the synthetic shop schema (`infer.plan`, `ontology`, `domains`,
`semantic_model`) and from `tool_status`, each time the docs are rendered, so `/docs.md` and `/llms-full.txt` carry the
same facts as the HTML. Between `<!-- figure:NAME -->` and `<!-- /figure -->` the HTML page shows a figure instead
(`concepts.figures()`: HTML and inline SVG in the site's colour tokens, so dark mode follows; the domains diagram has a
stacked version under 600 px); the Markdown keeps the same content as text. The vision's text is the maintainer's,
verbatim. The small question mark next to "ontology" and "data products" in the chat demo and on /check is a button
(`window.KGTip` in `site.js`, the two sentences from `concepts.TIPS` as JSON in the page): it opens in place by tap,
click or keyboard, Escape closes it, and it sends nothing. The home page's steps and /check's *Proposed domains* link to
the pages. Checks: `tests/test_n86b_concepts.py`.

*Where it runs* (n117), between *How they connect* and *Vision*, is a table: four places as columns (the browser,
your own computer, your own Azure tenant, hosted) and the tasks as rows (where it is, status, check, draft, create and
review). `concepts.where_cells()` reads every cell from the code when the page renders: tool_status (`phrase`, `mark`,
`task_status`, `FUNCTIONS`, `CLIENTS`, `LOCAL_TOOLS`), the tools' `dry_run` defaults in `server.py` and `mcp_server.py`,
the `/it` page's where-table, /check's own sentence and downloads, and `deploy/`. What the code cannot say
(`WHERE_NOT_IN_CODE`) is written once, with `WHERE_AS_OF`. Under 700 px each row becomes a card with one labelled block
per place; a visually hidden text version comes before the table. The note "calls no language model" rests on
`tests/test_n117_where_it_runs.py`, which fails if a model SDK or model API host appears in the engine.

Three architecture diagrams (also n86b) are drawn by `concepts._bands_svg` as inline SVG in bands, one layer under the
other, with a second drawing for phones (items two to a row, or one) so nothing scrolls sideways at 375 px: the layers
on *How it works*, the sign-in and request flow on *Hosting and permissions*, and plan → check → items on *How they
connect*. Each has a short text version for screen readers (a visually hidden paragraph the drawings point to with
`aria-describedby`) and the same facts as a list in `/docs.md`. The hosting flow's permissions and its "passes through,
not kept" sentences are read from the rendered `/it` page (`concepts.it_facts()`), so they can only say what `/it` says;
the marks on the flow (created live, dry run, draft) come from `tool_status` (`concepts.mark()`), and the pipeline's
from `pipeline.py`'s own description.

## Adding a page

1. Add a body template under `page_templates/` (just the inside of `<main>`; the shell adds header and footer).
2. Register it in `PAGES` in `pages.py` with a title, a meta description and the nav key it belongs to.
3. The route, cache header and CSP come for free from `build_app()`. Add it to `PUBLIC_PAGES` in `discovery.py`
   unless it should stay unlisted (`/mascots` is excluded on purpose), and link a `.md` version from `/llms.txt`
   if agents should read it.
4. Add a test in `tests/test_site.py`; the parametrised route test picks up every entry in `PAGES`.

## Rules the pages keep

- Nothing is claimed that the product does not do: no customer quotes, logos, numbers or "trusted by"; no
  approval, listing or partnership claims; "Microsoft Fabric" only descriptively, with the trademark note in
  the footer. `tests/test_site.py` checks for the obvious phrases.
- The demo is the engine's output, not hand-drawn data. If the engine changes, `/demo/plan.json` changes and the
  tests on it (`test_demo_plan_is_the_real_engine_output`) say so.
- No external resources: fonts, scripts and images are served from `/static`. The CSP on HTML pages enforces it.
- Mascots are decoration with an off switch, never the only carrier of information. Every bubble has the same
  information in plain text next to it. `prefers-reduced-motion` turns every animation off.

## The graph renderer

`new KrusGraph.Graph(container, planJson, options)` draws table cards (coloured table icon, key fields with a key
icon). Wide containers: left to right along `CHAIN` in `site.js` with `ROW2` underneath; narrow containers (< 700
px): one column in `STACK` order, with wires between non-neighbours in side lanes. Wires are bezier curves in the
source table's colour with a dot at each end, the rule on a chip and the cardinality as text; ports on a shared
card side are ordered so wires do not cross. Options: `tables` (subset), `suggest` (dashed wires from the plan's demo
hints for columns the engine left unlinked), `mascots` (figures on top-row wire chips, or `near` a table), `padBottom`, `label`. Events:
`select` and `focus`. Methods: `fit()`, `zoomBy(f)`, `reset()`, `selectTable(name)`, `setAccepted(edge, on)`. Nodes are buttons, wires are focusable SVG groups, so the keyboard
reaches everything; `Esc` clears the selection.
The panel takes the height the graph needs; the zoom buttons make it scroll. Wires and other non-text graphics
use the darker `--*-d` colour tokens. `/explore#table=orders` and `/explore#edge=orders.customer_id>customers` are
deep links.

## Mascots

Each name has one colour and one role (the founder's decision of 7-8 November 2026, round n164):

| Name | Colour | Role | Figure |
| --- | --- | --- | --- |
| Onto | green (`--onto`, the palette's sage) | maps how the data connects (the ontology) and says the numbers | wide and low, like a cushion |
| Thinker | violet (`--thinker`, the palette's lavender) | checks against the rows, finds what does not hold, asks the questions | a round pear, leaning |
| Builder | coral (`--builder`, the palette's coral) | creates the API, model, report or ontology, always with a dry run first | an upright egg, leaning forward |

The mapping lives in one place: `KINDS` in `mascots.js` (name → `colour`, `token`, figure, default label); `site.css`
defines `--onto`, `--thinker`, `--builder` and their `-soft`, `-ink` and `-d` variants from the palette (so dark mode
follows), and the MCP Apps cards read `KINDS` from the same file. `tests/test_n164_mascot_colours.py` fails when a page,
a stylesheet or a card pairs a name with another colour. The mascots are glad (`celebrate`, `heart`) only when every
check passes. The logo's three dots are not the mascots and stay as they are.

`Mascots.svg(kind, {pose, idle, label})` returns the markup for `onto`, `thinker` or `builder`. Poses are set
with `data-pose` and styled in `site.css`: rest, look, listen, point, celebrate, heart, notice, think, explain,
aside, working, failure, calm. `data-idle` (`breathe`, `nod`, `bounce`) adds the one quiet motion a page may
have. `Mascots.follower(area, {text})` makes Onto follow the pointer in a graph area (hover devices only);
`Mascots.build(fig, 'success' | 'failure', {onState})` runs the builder sequence; `Mascots.say(container, el,
text)` shows a bubble. The switch in the footer sets `html[data-mascots=off]` and stores the choice in
`localStorage` under `krusgraph.mascots` (wrapped in try/catch). `/mascots` shows every pose and state.

## The chat demo

Round n92 (Gustav's decision of 4 November 2026) put it on the start page; round n93 (his decision of the same day, after
he tried it live) gave it pictures, a direct way to the set-up guide, a place on every ordinary page and a memory within
the tab. A button with Onto in the bottom right corner, "Try a demo", opens a small chat that walks through the example
shop with buttons: check how the tables connect, decide on the suggested `orders.ship_to_id` link, then a semantic model,
an ontology and data products, in any order. The replay "A replay of a session in Claude" on the start page stays as it
is.

- **Which pages.** Every page with the site's header (`_shell(..., chat=True)`): the pages in `PAGES` (since n154 the start page again,
  and `/check`), `/privacy`, `/docs` and its sub-pages, `/lovable`, `/local`, `/blog` and its
  articles, the admin-consent return page and the 404 page; not `/demo` (`pages.CHAT_OFF`, a redirect to `/check`).
  `/check`'s policy keeps `connect-src 'none'`, so the page carries the plan itself in an inert JSON block
  (`pages.chat_plan_html`, `id="kgcPlan"`) and the chat reads it there instead of fetching; on `/check` the button steps
  aside while it would cover the drop area (`data-kgc-avoid`, `site.js`). `server.py` still takes the button out of any
  other page whose policy says `connect-src 'none'` (`pages.strip_chat`), which today is the start page when a
  request's Host header is one its policy cannot name. No page's policy changed for the chat:
  every other page has `connect-src 'self'`, the start page names `/demo/plan.json`. The preview of the first customer
  demonstration (`sales_demo.py`, only with `KRUSGRAPH_PREVIEW=1`) is not an ordinary page and has no button. The button
  shows Onto, so every page with it also has the footer's Mascots switch (the n36 rule: the switch goes with a mascot).
- **Files.** The button is server-rendered by `pages.chat_launch_html()` after the footer, with the `hidden` attribute,
  so without JavaScript there is no button and the page is as before. `site.js` shows it and gives the footer room
  underneath (`body.has-kgc`), so the button never covers the last line of a page; it hides while the phone menu is open
  (`body.nav-open`). Its styles are the few `.kgc-launch` rules in `site.css`. The chat itself is `static/chat-demo.js`
  and `static/chat-demo.css`, with `ASSET_V` like every other file, and they load on a click on the button or to
  restore a chat left open, never otherwise with the page. No inline script and no external resource.
- **Behaviour.** The chat never opens by itself on a first visit and nothing appears over the page before the click.
  Buttons only: no free text, no AI. The one request it makes is `GET /demo/plan.json`; it sets no cookie, writes
  nothing to `localStorage`, and logs no event (`/demo/plan.json` is not one of the paths `usage.page_view` counts). The
  links (`/check`, `/check?example=sample`, and "Connect to my Fabric" (n158: the n149 labels, `pages.CHECK_LABEL` and `CONNECT_LABEL`, as data attributes on the launch button), labelled "Opens the set-up guide.", to `/start`)
  open in the same tab and close the chat. If the plan cannot be fetched, the chat says so in one sentence and links to
  `/check?example=sample`. If the script cannot load, the click goes on to that page instead.
- **Memory within the tab (n93).** The steps clicked and whether the chat is open are kept in `sessionStorage` under the
  one key `krusgraph.chat`, as `{"open": true|false, "steps": [...]}` with step names from a fixed list (`scan`, `yes`,
  `no`, `model`, `ontology`, `domains`; `chat-demo.js` `STEPS`); never HTML, text or anything from the plan. Read back, anything
  else is ignored: not an object, `open` not a boolean, an unknown or repeated step, more than 400 characters. A step is
  replayed only by running the button it names when that button is on screen; the first that is not ends the replay.
  Every access is in try/catch: without storage the chat works as in n92 and forgets on the next page. `sessionStorage`
  stays in the browser and in that tab; nothing of it is sent anywhere. A chat that was open on the previous page opens
  again on the next one (`site.js` reads the key only for `open`; `KrusgraphChat.restore`), with its steps, in the same
  corner, without animation, without the confetti and without taking the focus from the page; under 560 px, where the
  chat covers the page, it stays closed after a page change until the button is pressed. Close, Esc and a link inside
  the chat store it as closed, and the steps are there at the next open. **Start over** in the chat's footer empties the
  steps and begins again.
- **Pictures (n93).** Each step draws a small picture in its bubble, as inline SVG built in `chat-demo.js` from
  `/demo/plan.json`; no table, column or entity type name and no count is written in the code. Check the tables: the
  tables as boxes, the links as lines, a key on each table with a key and a "no key" tag on `audit_log`. Yes, add the
  link: the same picture with `orders.ship_to_id` → `addresses` added and marked. Semantic model: its tables with the
  active relationships solid and the inactive one dashed. Ontology: the entity types, with a key or "no key", and the
  relationship types. Data products: `customers` and `products` as groups, the interface between them marked, and
  `audit_log` outside. The drafts' lists the pictures need are in the plan's `drafts` part (`demo._drafts`:
  `ontology.entities` and `ontology.links`, `semantic_model.table_names` and `semantic_model.relationships` with
  `active`). The site's graph renderer (`Graph`) was not reused: its layout names the shop's tables in `site.js`, every
  table and wire in it is a focusable control (a row of tab stops inside each bubble), it lays out one column under 700
  px and it has no groups. The placement is deterministic: a grid of two columns, and of all placements the first, in a
  fixed order, with the shortest lines, no line crossing another or running through a table, and each data product's
  tables in a rectangle that holds no other table; every picture uses the same one. The SVG scales to the bubble's width
  (no horizontal scroll at 375 px; names at about 13 px), and **Larger picture** under each one opens it at the chat's
  full width inside the chat, with its description as text, until Back to the chat or Esc. Each picture has a
  description for screen readers (`role="img"`, `aria-label`, built from the plan) and the text beside it stays.
  Colours are the site's tokens, light and dark; no animation; Mascots: off does not touch them.
- **Numbers.** None is typed into the chat. Tables, links, `keyless` and the `orders.ship_to_id` suggestion (15 of 15
  different values are in `addresses`, in 60 of 60 rows, counted in `seed.rows()`) come from `/demo/plan.json`, and so
  do the drafts' counts in its `drafts` part (`demo.demo_drafts()`): `ontology_draft`, `semantic_model_draft`,
  `domain_draft` and `validate_plan` run on the demo plan as it is (`as_is`) and with the suggestion confirmed
  (`with_suggestion`). Today: 7 entity types (5 with a key) and 6 or 7 relationship types; 7 tables, 6 active
  relationships and, with the link, 1 inactive one; 2 data products, `customers` and `products`, with one interface, and
  `audit_log` left out because it has no key. `tests/test_chat_demo.py` fails when one of them changes.
- **What it promises.** Every result says that nothing was created in the demo, and what the agent does in the
  visitor's own Fabric when asked, by `tool_status`: "creates" where `build_word()` of the creating tool says so and its
  permission is asked for (`available` is not `OPERATOR`, `pages.chat_does()`), "drafts" otherwise: data products
  (`domain_draft` creates nothing) add "the draft creates nothing in Fabric", while the semantic model and the ontology,
  whose permission is not asked for today (n94), say only that the agent drafts them and leave the rest to the status. Then, since n93, one
  plain sentence without a tool's name, built by `pages.chat_status()` from `tool_status` and saying no more than it:
  "Created in a live Fabric workspace and reviewed there." (`build_word` and `REVIEWED`), "Creating it needs a permission
  the hosted service does not ask for today." (available when enabled by the operator), "Tested with unit tests, not yet
  against a live Fabric workspace." (a draft that has not run live). "Fix data issues" and "Draft a dbt project" are steps
  like the others since n162 (n154 to n161 links to the docs, before that marked Planned), offered after the three drafts
  and at the end until they have run. Each shows what the engine answered on the example when the plan JSON was built
  (`demo._fix_result`, `demo._dbt_result`, in `drafts.as_is` and `drafts.with_suggestion`): `validate_plan` with
  `fixes=true` (the counts, then per finding its proposed fix, its counts before and after, mechanical or a business
  decision, a decision as its question with the options; on the example the keys and links hold, so 0 mechanical and 2
  questions: the level of `products.list_price` with its two sums, and `audit_log` without a key; the chat answers and
  applies none), and `dbt_schema` with `project=true` and the rows counted (the file tree, the start of one staging model,
  one relationship's tests in the sources file; "Files only; nothing runs."). Their end texts say what the agent does in
  the visitor's Fabric, from `tool_status`: for fixes the status of `validate_plan` (`data-draft-status-fixes`) and of
  `create_silver_notebook`, which applies the accepted ones; for dbt the status of `dbt_schema`. No dates. The chat does not say that its bubbles appear in the agent.
  The sales-word test covers its text.
- **Keyboard, phone, motion, mascots, theme.** Visible focus on every button; the focus goes to Close when the chat
  opens and to the first new choice after each step; Esc (from inside the chat) and Close close it and give the focus
  back to the button. Under 560 px the chat covers the screen but its top 40 px, the page behind does not scroll
  (`html.kgc-lock`) and is `inert`, Tab stays in the chat (`aria-modal`), and `env(safe-area-inset-*)` is respected.
  `prefers-reduced-motion` turns off every animation and transition, and the steps finish at once. Mascots: off hides
  the figures; the button, every word and every picture stay. Colours are the site's tokens, so light and dark follow
  the theme.
- **The start page's content security policy.** Its `connect-src` names exactly three sources on the page's own host:
  `/check`'s engine files (`/static/pyodide/` and `/check/engine.zip`, for the prefetch, n49) and `/demo/plan.json`
  (n92, for the chat). No `'self'`, no other path; `script-src` and the rest are the other pages', and no other page's
  policy changed (`server.py`, `home_headers`; `tests/test_check.py` checks the three sources, `tests/test_chat_demo.py`
  every page's policy).
- **Checks.** `tests/test_chat_demo.py` (the numbers and lists, the pages with and without the button, every page's
  policy, the files a page loads, no other request, the one storage key and how it is read, the Planned choices, the
  status sentence from `tool_status`, the sales words) and `tests/chat_demo_browser.js` through `tests/test_browser.py`,
  under the pages' own policies (at 375 and 1280 px, light and dark: the flow by mouse and by keyboard, the pictures
  inside their bubbles, Larger picture, Connect to `/start`, a page change with the chat open and closed, Start over, a
  corrupt stored value, blocked storage, Mascots: off, reduced motion, no JavaScript, the plan failing to load, the
  button on every page and what it may cover).

## Screenshots and checks

With the server running locally (`PRODUCT_NAME=Krusgraph MCP_PUBLIC_URL=https://krusgraph.com/mcp
ENTRA_CLIENT_ID=x ENTRA_CLIENT_SECRET=x fabric-backend-server --port 8765`):

- `pytest -q` runs everything, including the browser checks when Playwright is installed
  (`npm i -g playwright && npx playwright install chromium`, or set `PLAYWRIGHT_CHROMIUM`).
- The screenshots in `docs/screenshots/` were taken with Playwright at 1280×900 (light and dark) and 390×900
  (light), full page, then quantised to 8-bit PNGs. Re-take them after visual changes and look at every one.
- An axe-core audit (WCAG 2.1 AA + best practices) ran clean on every page in all three variants.
