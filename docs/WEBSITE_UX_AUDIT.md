# Website UX audit (round n190, 10 November 2026)

Input: the outside UX review the founder pasted on 9 November 2026, which compared krusgraph.com with lovable.dev and
strawberrybrowser.com. Its findings: technical credibility is high, but customer value, clarity for a new visitor and
the path to start are weak. Too much competes for attention (MCP, APIs, semantic models, ontologies, notebooks, Power BI,
Rayfin, Fabric IQ, data products), four product entries come before the core product is understood, and the site sells
how the technology works rather than the outcome. It also found a contradiction between what the home page says
Krusgraph creates and what the set-up page says about permissions.

This audit is of `main` at round n190. **The live site is not this code.** `CHANGELOG.md` says nothing has been
deployed since build `src-8d6c473bf26f45f9` (main up to n111). This session could not open krusgraph.com (the proxy
refused the connection), so the deployed wording was not checked against the reviewer's quotes.

## 1. Routes

| Route | Template / source | Role | Changed in n190 |
| --- | --- | --- | --- |
| `/` | `page_templates/home.html`, `pages._home_vars` | Home | Rewritten (section 5) |
| `/check` | `check.html`, `static/check.js` | The engine in the browser on CSV/Excel or a list of columns; no account. `?example=sample&guide=1` is the guided demo | Takes `intent=issues\|map\|model\|agent` |
| `/start` | `start.html` | Set-up guide: admin consent, workspace, connector | Claims line; button label |
| `/choose` | `choose.html`, `offering.py` | Which Krusgraph: the four ways in, the diagram, the comparison | Claims line; Fabric's "lacks" corrected |
| `/use-cases`, `/use-cases/build` | `use_cases.html`, `use_cases.py` | Examples with maps; what each tool returns | Called "Examples" in the nav |
| `/pricing` | `pricing.html` | Free / Pilot / Team | Claims line |
| `/docs`, `/docs/...` | `DOCS.md` split into pages | Docs | Claims table in *Test status* |
| `/lovable`, `/local`, `/docs/krusgraph-for-fabric`, `/pilot/fabric` | product pages | Krusgraph for Lovable, Open Source, for Fabric | none |
| `/sap`, `/it`, `/privacy`, `/terms`, `/support`, `/partners`, `/partners/workspace`, `/blog`, `/blog/...` | various | Secondary | none |
| `/demo`, `/explore` | redirects (`pages.REDIRECTS`) | old addresses | kept |
| `/mascots` | `mascots.html` | Review page, noindex | none |
| `*.md`, `/llms.txt`, `/sitemap.xml` | Markdown twins | Agents and crawlers | `/start.md`, `/choose.md` and `/docs.md` carry the claims |

No route was moved or removed, so no new redirect was needed.

## 2. Components

- Shell (`pages._shell`): header, navigation, footer, theme button, mascot toggle, the chat demo's launch button
  (`chat_launch_html`, a scripted replay of `/demo/plan.json` on every page except `/demo`).
- Home: hero, mini before/after badge (`before_after_mini_html`, "2 000 → 1 000 why"), before/after
  (`before_after_html`), the offering diagram (`offering.diagram_html`, n183), the decision guide (`offering.short_html`).
  Before n190 the home page also had the session replay, the overview film (`film_html`), the hub (`hub_html`), the two
  paths, the steps, the trust list, the developer note and the FAQ.
- Maps: `static/map.js` (MapView), used by /check, /use-cases and, since n190, the home page via `static/use-cases.js`.
- /check: example buttons, drop zone, guided demo (Onto's four steps), verdict, findings, map, *Go further* tiles
  (Power BI model, app, Fabric IQ ontology, evidence), Ask Onto (fixed questions, no text box).
- Status: `tool_status.py` (per tool), `offering.py` (per product), and since n190 `claims.py` (per output, the chips).

## 3. Mascot assets

- `static/mascots.js`: Onto (sage), Thinker (lavender), Builder (coral), drawn as inline SVG. Poses: point, look,
  celebrate, breathe (idle). A toggle in the footer turns them off and is remembered in the browser.
- `offering.PICTURES`: each product card's mascot holding a symbol we draw ourselves (n183). No Microsoft, Anthropic or
  Lovable logo appears anywhere, and none next to a mascot.
- `mcp_apps_mascots.py`: the same three in the MCP App cards.
- `/mascots`: the review page.
- Used on: /check (Onto and Thinker, the guide, Ask Onto), /start (one per step), /use-cases, the before/after (Thinker,
  removed from home in n190) and the chat demo.

## 4. Capability claims and their status

The chips come from `fabric_backend/claims.py` and are derived from `tool_status.py`, which follows
`docs/LIVE-TEST.md`. Nothing in the table below is typed per page.

| Claim | Status | Evidence |
| --- | --- | --- |
| Power BI semantic model | Tested live | `create_semantic_model` created `shop_model_live` on 29 October 2026; refreshed and reviewed in the Fabric portal |
| Power BI report | Tested live | `create_report`, 30 October and 7 November 2026; figures checked in Power BI |
| Fabric IQ ontology | Tested live | `create_ontology`, 28 October and 2 November 2026; needs the tenant setting for Ontology (preview) |
| Notebooks and a pipeline | Tested live | silver and gold notebooks created 28 October 2026; `create_pipeline` created and ran `pipeline_shop` on 7 November 2026 |
| API for GraphQL | Experimental | updating an existing API in place was tested live (27 and 30 October 2026); creating a new one is unit-tested only |
| Data agent | Experimental | creating has no recorded live run |
| SQL views (not on the home grid) | Experimental | `create_views`: creating has no recorded live run |
| App (Rayfin) | Preview | only the Krusgraph Model item builds it; not among the recorded live runs (docs/RAYFIN-APP.md) |
| Krusgraph for Fabric (the Model item) | Preview | a pilot on request; unit tests against test doubles of Fabric; not in docs/LIVE-TEST.md |
| Run once and Schedule (pipeline) | Preview, Krusgraph for Fabric only | n185; needs `DataPipeline.Execute.All` with admin consent. The hosted connector does not request it |
| /check drafts (Power BI project, app preview, RDF/XML, evidence report) | Available now | browser tests (n188 and earlier); nothing created in Fabric |
| Claude as a client | Tested end to end | since 27 October 2026 (`tool_status.CLIENTS`) |
| Lovable over MCP, VS Code, Cursor | per `tool_status.CLIENTS` | shown on /choose and /start from the same data |
| Workload Hub listing, Azure Marketplace | Planned | `offering._status_fabric`, /pricing |

## 5. Contradictions found, and what n190 did

1. **Home: "In Fabric, Krusgraph creates … a data agent, an API for GraphQL and an App (preview)" with no status.**
   Creating a data agent or a new API has no recorded live run, and the App is only in the Model item, which is a pilot.
   *Fixed:* the claim is now the *What you can build* grid, one chip per output from `claims.py`.
2. **Krusgraph for Fabric "does not run or schedule the notebooks or the pipeline it creates" (/choose)** against n185's
   Run once and Schedule on the Model item. *Fixed:* the line now says it runs or schedules only when you tick the
   choice and your admin has granted `DataPipeline.Execute.All`.
3. **The reviewer's quote: creating on the home page against "some create tools lack permissions" on /start.** On
   `main` the hosted app has every permission the creating tools use (`access.GRANTED`), and no tool is
   `OPERATOR`. What /start says is that the hosted service **cannot run or schedule** a notebook or pipeline, because
   `DataPipeline.Execute.All` is not requested, which is true and is about running, not creating. The sentence "Some
   items need a permission the hosted service does not ask for today" is still produced by `hub_status_note` and
   `chat_status` when a tool is `OPERATOR`, so the deployed build may still show it. *Fixed:* one sentence about running
   (`claims.RUNS`) is shown with the chips on home, /start, /choose, /pricing and the docs. A redeploy is needed for the
   live site to match.
4. **/choose.md: "Each builds the same items in Microsoft Fabric"**, while the App is built only by Krusgraph for
   Fabric. *Fixed.*
5. **Three names for one demo:** "Try the guided demo" (home), "Try a demo" (the chat button), "Check my tables" (/check).
   *Fixed for the home page and the nav:* "Try the free demo" / "Try free demo" go to the guided demo, and "Check my
   tables" means your own files. The chat button keeps its label (it is a founder decision of n154; see 6).
6. **Chat-like elements against "no fake AI chat".** The home page's session replay showed chat bubbles with typed
   questions. *Removed from the home page.* The chat demo button on every page replays the real engine's plan
   (`/demo/plan.json`) with fixed choices and no text box, so it is structured selection. It is kept, and flagged
   for the founder to look at against the rule.
7. **Nav had eight entries plus GitHub.** *Fixed:* five entries and one call to action. /check, the blog, Get help, the
   pilot, GitHub and the legal pages are in the footer.
8. **Two vocabularies for status.** The docs use Tested end to end / Tried live / Experimental / Draft only. The chips
   use Tested live / Preview / Experimental. The docs' *Test status* now opens with the chip table and says how the
   chips are derived from the per-tool fields.

## 6. The plan

P0 (done in n190): the hero's single promise, the demo CTA and the intent tiles, the map, the before/after, the build
grid with chips, ways to use it, three steps, security and proof, the final CTA, the navigation, and one status per
claim. P1 and P2 are in `docs/WEBSITE_IMPLEMENTATION_PLAN.md`. The copy is in `docs/WEBSITE_COPY_REWRITE.md`.

## 7. Verification checklist

- [x] Hero: one headline, one supporting line, "Try the free demo" → `/check?example=sample&guide=1`, "Connect Microsoft Fabric" → `/start` (tests/test_n190_site.py)
- [x] Four intent tiles, each to `/check?example=sample&intent=…`; in Chromium each lands on its part of the result (tests/n190_browser.js)
- [x] Before/after renders with numbers computed from the engine's run; each issue in plain words with the check on expand
- [x] Claims: every chip on /, /start, /choose, /pricing and the docs equals `claims.status()`; every output appears on each page
- [x] The contradiction's sentences are gone or consistent (tests/test_n190_site.py)
- [x] Navigation: Product, Examples, How it works, Pricing, Docs + "Try free demo"; every nav and CTA link answers 200
- [x] 375, 768 and 1440 px: no horizontal page scroll, light and dark, screenshots written for review
- [x] Keyboard: visible focus on the tiles and CTAs; axe-core when it is installed (it is not a dependency)
- [x] prefers-reduced-motion: tiles do not move; the map draws without animation (use-cases.js)
- [x] SEO: title, description, canonical, og tags and JSON-LD kept; no route removed
- [ ] Core Web Vitals on the live site: not measured (needs the deployed site). The home page dropped the overview film, the session replay and the hub. It added the map, which loads map.js (shared with /check and /use-cases) and draws one map.
- [ ] The live site matches: needs a redeploy (`bash deploy/krusgraph.sh --update`, by the maintainer)
