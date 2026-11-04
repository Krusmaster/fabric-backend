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
| `fabric_backend/static/chat-demo.js`, `chat-demo.css` | the chat demo on the start page (n92), loaded on the first click on its button; see below |
| `fabric_backend/static/mascots.js` | the three figures as inline SVG (`Mascots.svg`), the off switch, gaze, the follower, the builder sequence |
| `fabric_backend/static/fonts/` | Fredoka and Nunito, variable, subset to Latin, SIL OFL (licence files beside them) |
| `fabric_backend/static/favicon.svg|png`, `og.svg|png` | icon and Open Graph image; the PNGs are rendered from the SVGs with Playwright |
| `fabric_backend/demo.py` | `demo_plan()`: the real `plan()` on `seed.schema()`, served as `/demo/plan.json`; its `suggestions` list is what `suggest_relationships` answers on the synthetic rows for the column no naming rule links (`orders.ship_to_id` → `addresses`, with its data check and the next candidate), not hand-written. `home_guide()`: the guided example on `/demo` in four steps (the question, the suggestion with its check, the visitor's review, the result card), server-rendered so it reads without JavaScript; accepting decides the meaning and never turns into a check |
| `tests/test_site.py`, `tests/test_site_extras.py` | every route, headers, honesty rules, the plan JSON, discovery documents |
| `server.json`, `docs/PUBLISHING.md` | the MCP Registry entry and how to publish it (not published) |
| `tests/test_browser.py` + `tests/browser_check.js` | Playwright checks; skipped when Node + Playwright + Chromium are missing |
| `docs/screenshots/` | the reviewed screenshots (1280 light, 1280 dark, 390 light per page, plus interaction states) |

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

`Mascots.svg(kind, {pose, idle, label})` returns the markup for `onto`, `thinker` or `builder`. Poses are set
with `data-pose` and styled in `site.css`: rest, look, listen, point, celebrate, heart, notice, think, explain,
aside, working, failure, calm. `data-idle` (`breathe`, `nod`, `bounce`) adds the one quiet motion a page may
have. `Mascots.follower(area, {text})` makes Onto follow the pointer in a graph area (hover devices only);
`Mascots.build(fig, 'success' | 'failure', {onState})` runs the builder sequence; `Mascots.say(container, el,
text)` shows a bubble. The switch in the footer sets `html[data-mascots=off]` and stores the choice in
`localStorage` under `krusgraph.mascots` (wrapped in try/catch). `/mascots` shows every pose and state.

## The chat demo on the start page

Round n92 (Gustav's decision of 4 November 2026). A button with Onto in the bottom right corner of `/`, "Try a demo",
opens a small chat that walks through the example shop with buttons: check how the tables connect, decide on the
suggested `orders.ship_to_id` link, then a semantic model, an ontology and data products, in any order. Only the start
page has it; `/demo`, `/check`, `/it`, `/privacy` and the pricing page do not, and the replay "A replay of a session in
Claude" stays as it is.

- **Files.** The button is server-rendered by `pages.chat_launch_html()` with the `hidden` attribute, so without
  JavaScript there is no button and the page is as before. `site.js` shows it and gives the footer room underneath
  (`body.has-kgc`), so the button never covers the last line of the page. Its styles are the few `.kgc-launch` rules in
  `site.css`. The chat itself is `static/chat-demo.js` and `static/chat-demo.css`, with `ASSET_V` like every other file,
  and they load on the first click, not with the page. No inline script and no external resource.
- **Behaviour.** The chat never opens by itself and nothing appears over the page before the click. Buttons only: no
  free text, no AI. The one request it makes is `GET /demo/plan.json`; it sets no cookie, writes nothing to
  `localStorage` or `sessionStorage`, and logs no event (`/demo/plan.json` is not one of the paths `usage.page_view`
  counts). The links (`/check`, `/check?example=sample`, `/#connect`) open in the same tab. If the plan cannot be
  fetched, the chat says so in one sentence and links to `/check?example=sample`. If the script cannot load, the click
  goes on to that page instead.
- **Numbers.** None is typed into the chat. Tables, links, `keyless` and the `orders.ship_to_id` suggestion (15 of 15
  different values are in `addresses`, in 60 of 60 rows, counted in `seed.rows()`) come from `/demo/plan.json`, and so
  do the drafts' counts in its `drafts` part (`demo.demo_drafts()`): `ontology_draft`, `semantic_model_draft`,
  `domain_draft` and `validate_plan` run on the demo plan as it is (`as_is`) and with the suggestion confirmed
  (`with_suggestion`). Today: 7 entity types (5 with a key) and 6 or 7 relationship types; 7 tables, 6 active
  relationships and, with the link, 1 inactive one; 2 data products, `customers` and `products`, with one interface, and
  `audit_log` left out because it has no key. `tests/test_chat_demo.py` fails when one of them changes.
- **What it promises.** Every result says that nothing was created in the demo, and what the agent does in the
  visitor's own Fabric when asked, by `tool_status`: "creates" where `build_word()` of the creating tool says so (the
  semantic model, the ontology), "drafts" otherwise (data products: `domain_draft` creates nothing), followed by the
  tool's status word (`pages.chat_status()`). "Fix data issues" and "Create a dbt flow" are marked Planned, run nothing,
  and say what exists today; no dates. The chat does not say that its bubbles appear in the agent. The sales-word test
  covers its text.
- **Keyboard, phone, motion, mascots, theme.** Visible focus on every button; the focus goes to Close when the chat
  opens and to the first new choice after each step; Esc and Close close it and give the focus back to the button. Under
  560 px the chat covers the screen but its top 40 px, the page behind does not scroll (`html.kgc-lock`) and is `inert`,
  Tab stays in the chat (`aria-modal`), and `env(safe-area-inset-*)` is respected. `prefers-reduced-motion` turns off
  every animation and transition, and the steps finish at once. Mascots: off hides the figures; the button and every
  word stay. Colours are the site's tokens, so light and dark follow the theme.
- **The start page's content security policy.** Its `connect-src` names only `/check`'s engine files (n49,
  `server.py`, `home_headers`), so a browser that enforces it refuses the chat's `GET /demo/plan.json` and the chat shows
  its fallback. Round n92 did not change the policy (the brief said it stays as it is); adding the one path
  `/demo/plan.json` to the start page's `connect-src` is the maintainer's decision. Until then
  `tests/chat_demo_browser.js` checks the whole flow with the policy bypassed, and checks separately what the start page
  shows under its own policy.
- **Checks.** `tests/test_chat_demo.py` (the numbers, the files the page loads, no other request or storage, the
  Planned choices, the statuses, the sales words) and `tests/chat_demo_browser.js` through `tests/test_browser.py` (at
  375 and 1280 px, light and dark: the flow by mouse and by keyboard, Mascots: off, reduced motion, no JavaScript, the
  plan failing to load).

## Screenshots and checks

With the server running locally (`PRODUCT_NAME=Krusgraph MCP_PUBLIC_URL=https://krusgraph.com/mcp
ENTRA_CLIENT_ID=x ENTRA_CLIENT_SECRET=x fabric-backend-server --port 8765`):

- `pytest -q` runs everything, including the browser checks when Playwright is installed
  (`npm i -g playwright && npx playwright install chromium`, or set `PLAYWRIGHT_CHROMIUM`).
- The screenshots in `docs/screenshots/` were taken with Playwright at 1280×900 (light and dark) and 390×900
  (light), full page, then quantised to 8-bit PNGs. Re-take them after visual changes and look at every one.
- An axe-core audit (WCAG 2.1 AA + best practices) ran clean on every page in all three variants.
