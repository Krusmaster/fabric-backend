# The website: how it is built and how to change it

The site is served by the same process as the MCP server (`fabric_backend/server.py`, `build_app()`). There is
no build step, no bundler and no external resource at runtime. This note is for whoever edits it next.

## Files

| Path | What |
| --- | --- |
| `fabric_backend/pages.py` | the page registry (`PAGES`: path → template, title, description, nav key), the shared shell (header, footer, meta tags), canonical/Open Graph/Twitter tags, JSON-LD for `/`, the small Markdown renderer for `/docs`, `/privacy` and `/lovable`, the Markdown versions of the pages (`/docs.md`, `/start.md`, …), the 404 page, the static-file resolver |
| `fabric_backend/discovery.py` | everything for crawlers and agents: `/sitemap.xml` (`PUBLIC_PAGES`), `/robots.txt`, `/llms.txt`, the MCP Server Card (`/mcp/server-card`) and the AI Catalog (`/.well-known/ai-catalog.json`) |
| `fabric_backend/page_templates/*.html` | one body template per page; `{{VAR}}` placeholders are filled from the environment (`PRODUCT`, `PRODUCT_URL`, `CONTACT`, `MCP_URL`, `CLIENT_ID`, `GITHUB`, …) and HTML-escaped (the Markdown pages escape while rendering); `{{#IF VAR}}…{{/IF}}` keeps a block only when the variable is set; `{{DEMO_*}}` placeholders are filled from the demo plan |
| `fabric_backend/page_templates/DOCS.md`, `PRIVACY.md`, `LOVABLE.md` | the Markdown pages (served as HTML and as `.md`); `{{RULES_TABLE}}` in DOCS.md is generated from `infer.RULES` |
| `fabric_backend/static/site.css` | design tokens (`:root`, dark values under `prefers-color-scheme: dark`), shell, components, the graph, the mascot poses and animations |
| `fabric_backend/static/site.js` | navigation toggle, the graph renderer (`Graph`), and the per-page wiring for `/`, `/explore`, `/partners/workspace`, `/mascots` |
| `fabric_backend/static/mascots.js` | the three figures as inline SVG (`Mascots.svg`), the off switch, gaze, the follower, the builder sequence |
| `fabric_backend/static/fonts/` | Fredoka and Nunito, variable, subset to Latin, SIL OFL (licence files beside them) |
| `fabric_backend/static/favicon.svg|png`, `og.svg|png` | icon and Open Graph image; the PNGs are rendered from the SVGs with Playwright |
| `fabric_backend/demo.py` | `demo_plan()`: the real `plan()` on `seed.schema()`, served as `/demo/plan.json`; its `suggestions` list is the one hand-written demo hint (for the unlinked `orders.ship_to_id`) and is labelled "demo hint, not inferred" wherever it is shown |
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

## Screenshots and checks

With the server running locally (`PRODUCT_NAME=Krusgraph MCP_PUBLIC_URL=https://krusgraph.com/mcp
ENTRA_CLIENT_ID=x ENTRA_CLIENT_SECRET=x fabric-backend-server --port 8765`):

- `pytest -q` runs everything, including the browser checks when Playwright is installed
  (`npm i -g playwright && npx playwright install chromium`, or set `PLAYWRIGHT_CHROMIUM`).
- The screenshots in `docs/screenshots/` were taken with Playwright at 1280×900 (light and dark) and 390×900
  (light), full page, then quantised to 8-bit PNGs. Re-take them after visual changes and look at every one.
- An axe-core audit (WCAG 2.1 AA + best practices) ran clean on every page in all three variants.
