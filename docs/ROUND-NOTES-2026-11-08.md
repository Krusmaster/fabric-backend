# Round notes, 8 November 2026 (n150, n149, n151, n152)

Four backlog rounds, worked in that order by one scheduled cloud session. Nothing was written to Microsoft Fabric or any
other external service; the rounds changed code, docs and tests only. Every push had the full suite green locally
(`python -m pytest -q`, Python 3.12, Playwright's Chromium present, so the browser tests ran).

## Round 0: n150 status

n150 was finished on 7 November 2026; nothing was left to do. Checked: the commits whose message starts with "n150",
`tests/fixtures/check_cases/` (all six datasets) and `tests/test_check_cases.py`.

| Bug | Commit | Test |
| --- | --- | --- |
| 1. Power BI preview card summed a header amount at line grain (01: showed 3) | `598138f` | `tests/test_check_cases.py` |
| 2. A key that is not unique exported as `isKey`, joined on, chart 700 vs 600 (04) | `23d57e1` | `tests/test_check_cases.py`, `tests/check_cases_browser.js` |
| 3. Accept/Reject did not reach the exported model (06) | `b88cf08` | `tests/test_check_cases.py`, `tests/test_check_decisions.py` |
| 4. Undecided candidates not counted as open questions (06) | `b88cf08` | `tests/test_check_cases.py` |
| 5. Export panel said 1 relationship, model had 0 (05) | `23d57e1` | `tests/test_check_cases.py` |
| 6. Fan-out counted the orphan group as a header (05: 1.25 instead of 1.33) | `ba85922` | `tests/test_check_cases.py`, `tests/test_amounts.py` |
| 7. Accept/Skip missing in the plain CSV view | `b88cf08` | `tests/check_cases_browser.js` |
| Also: leading zeros kept as text (05) | `53eb541` | `tests/test_check_cases.py` |
| Also: course_hours warned like annual_fee (02) | `82b2fa8` | `tests/test_check_cases.py` |

CI: green on `dc724de` (n150 releases), run 693. The full suite was green here before n149 started (2524 passed).

## Round n149: the home page and /check lead with the problem

Commits: `b93a440` (claim), `c72624d` (the round), `f67b05b` (release), `72db6e7` (CI fix).

CI: run 696 (`c72624d`) and 697 (`f67b05b`) failed in `tests/test_browser.py::test_no_console_errors_external_requests_or_overflow`:
the browser check's new step navigated the home page's tab to /start while the page was still prefetching /check's
engine, and the aborted request counted as a failed one (timing-dependent; it passed locally). `72db6e7` opens /start in
its own tab; run 699 (`72db6e7`) is green.

| Item of the brief | What changed |
| --- | --- |
| 1. Hero | "Why is your total twice what finance says?", the subtext as given, the 2 000 → 1 000 before/after from `seed.AMOUNT_DEMO` as a small card under the buttons (links to the example). The n39 promise sentence stays above the four points (README, /docs and llms.txt keep it in step). The replay panel moved down, after the steps. |
| 2. Two ways in | `pages.CHECK_LABEL` "Check my tables" → /check, `pages.CONNECT_LABEL` "Connect to my Fabric" → /start: hero, middle section, closing card, replay links, after a /check result (card, build step, Onto's answers), /pricing, navigation, footer, /use-cases, the consent pages. The "Connect ▾" chooser (Claude, Lovable, VS Code, Cursor) is now step 3 of /start ("Choose your client"); no link points at `#connect`. The floating "Try a demo" is off on the home page (`pages.PILL_OFF`) and /check (as before), kept on deeper pages. One "Try the guided demo" button, after the total that doubles. |
| 3. /check after a result | Card "Run the same check on your live lakehouse" with "Connect to my Fabric →" and one line (Microsoft work account; an admin approves once, linking /it). Footer: "Run it locally" is a text link, the demo button is gone. At 375 px the drop area and the "read in this browser" line come first, the example cards (two columns) below (CSS order, a browser test). |
| 4. /start | "Coming from /check? Go to step 3: Add the connector ↓" at the top; "What you need" folded below it. |
| 5. Status once | The home page's pitch no longer carries status; one line by the tools list (`#status`) gives the preview/experimental status, the live-run date and the creating tools' status from `tool_status`. |
| 6. Self-hosting wording | Already n146's data line on home and /pricing ("keep everything in your tenant" was gone); a test keeps it. |
| 7. Blog | "Blog" in the main navigation (desktop and mobile menu, every page). "Read the full walkthrough →" to `/blog/fabric-totals-double-after-join` from the home page's example section and under /check's example cards. `/join-validation` does not exist (404), so nothing links there. /blog and the article were already in sitemap.xml and llms.txt. |

Tests: `tests/test_n149_lead_with_problem.py` and `tests/n149_browser.js`. Older tests that pinned the n52/n68/n73/n91
hero, the chooser on the home page and the examples above the drop area on a phone were changed to the brief
(`tests/test_site.py`, `test_browser.py`, `test_connect_menu.py`, `test_chat_demo.py`, `test_check.py`,
`test_use_cases.py` and their browser scripts). /check's engine and export were not touched, except that the export
README's two mentions of the old button text now say "Connect to my Fabric" (`browser_build.py`).

Open: none in code. Wording of the status line by the tools list may want Gustav's read.

## Round n151: create_report's default page looks like a report

Commits: `f67b05b` (claim), `7df0098` (the round), `4e4f6ae` (release and these notes). CI: run 698 (`7df0098`) failed only in the n149 browser check above (2585 passed), fixed by `72db6e7`; run 699 green.

| Item of the brief | What changed |
| --- | --- |
| Live runs | docs/LIVE-TEST.md (row 39 and a section "7 November 2026: create_report with visuals"), `tool_status.py` (last tried live 7 November 2026; still open: the n151 look) and README record `shop_report_visuals` on `shop_model` (every figure right) and `shop_report_lovable` (`832e3687-…`). create_report's own note no longer says the page was "not yet created in Fabric". |
| 1. Titles | `report.title_of` / `plain_table`: "Rows in X" (COUNTROWS of X itself) → X in plain words, `order_items` → "Order lines" only when it points at `orders`; SUM of a quantity column → "Units"; every other measure keeps its name. Shop: Orders, Order lines, Units, Units by month, Units by category, Products by units. |
| 2. Cards | Row counts of business tables (an `isKey` column or a relationship; not named like a log), tables others point at first, then Units; at most four; `audit_log` only if nothing else. `not_drawn` says which card or visual was left out and why. |
| 3. Layout | Title row (with slicers), cards, charts, table, footnote fill 1280 × 720 between 16 px margins; without the month chart the category chart takes the full width; the table spans the page with its columns sized to fill it. |
| 4. Whole numbers | `create_semantic_model` writes `#,0` for COUNTROWS and SUM of int64 columns (also level measures). The visual sets `labelPrecision` 0 only for a whole-number measure whose model lacks a whole-number format. See "Left open" for the shop's quantity. |
| 5. Theme, title, footnote | `StaticResources/RegisteredResources/Krusgraph.json` in the site's CSS colours (contrast tested), registered in report.json; text boxes "Overview · <model name>" and "<date>. Created by Krusgraph from the checked plan." Formats from microsoft/json-schemas eecc60d (report 3.1.0 `themeCollection`, `resourcePackages`), the report theme schema (powerbi-desktop-samples e2f326b, reportThemeSchema-2.159.json) and Microsoft's samples (semantic-link-labs b42fc83, Analysis-Services d3ccb50). |
| 6. Date table, slicers | The calendar now spans the whole years from the first to the last date of the related date columns, which create_semantic_model reads read-only (MIN/MAX; `read_from_rows` in its answer; the placeholder 2020–2030 stays when it cannot read), and has `Year Month` (text, 2026-10) so months of different years stay apart. Month and category slicers only when those fields exist. Cross-filtering stays on. |
| 7. Labels, sort, total | Data labels on both charts; bars and table rows largest first; the table has a total row. |

Tests: `tests/test_n151_report_look.py` (24 tests) and `tests/test_create_report.py`, which now validates every PBIR
part against Microsoft's schemas, copied unmodified into `tests/fixtures/pbir_schemas/` (13 files, MIT, licence file
and THIRD_PARTY_NOTICES.md row). Golden answers regenerated for the format and calendar changes (`tests/golden/`;
`local_listing.json` left as committed, its regenerated form here depends on locally installed extras).

Left open:
- **The shop's "59,00".** The seed's `order_items.quantity` is `DOUBLE`, so the brief's rule (whole-number format for
  SUM of *integer* columns) would not change the live figure. create_semantic_model therefore also counts whether a
  decimal quantity column holds whole numbers only, and formats its sum `#,0` when it does (true for the shop). This
  needs a new model (or an update of `shop_model`) to show in Fabric; existing reports were not touched.
- **Not run live:** the n151 page as a whole, and in particular whether Fabric accepts a report definition with a
  `StaticResources` theme part and a custom theme without a base theme (the schema allows it; no sample was found that
  does exactly this). If Fabric refuses it, dropping the theme part is a two-line change in `report.definition_parts`.

## Round n152: create_semantic_model in Import mode — stopped

The brief's first step: confirm from Microsoft Learn that Publish to web does not support Direct Lake models, and stop
if that is not the reason. It could not be confirmed, and what could be read points elsewhere, so the round stopped
before any code change.

- **learn.microsoft.com** is not reachable from this session (DNS refused by the session's network policy), and the
  Power BI docs' source repository (MicrosoftDocs/powerbi-docs) could not be read either. So the Power BI page "Publish
  to web from Power BI" (`/power-bi/collaborate-share/service-publish-to-web`) and its list of unsupported cases were
  not read.
- **What Microsoft's Fabric docs say** (MicrosoftDocs/fabric-docs, commit caec836, read 8 November 2026,
  `docs/fundamentals/direct-lake-overview.md`, ms.date 09/02/2026), in the table "Considerations and limitations":
  *"Publish to web from Power BI using a service principal is only supported when using a fixed identity for the Direct
  Lake semantic model."* — marked as applying to both Direct Lake on OneLake and Direct Lake on SQL. That is a condition
  on Publish to web for Direct Lake, not a statement that Direct Lake is unsupported.
- `docs/fundamentals/direct-lake-security-integration.md` (same commit): by default Direct Lake uses SSO (Microsoft
  Entra ID), the identity of the user querying the model; it can instead be bound to a cloud connection with a fixed
  identity. An anonymous Publish to web viewer has no Entra identity, so an SSO-bound Direct Lake model is a plausible
  cause of "the report is not eligible for use with Publish to web" — but that is an inference, not something these
  pages state.

So the reason for the refusal of `shop_report_visuals` is not established, and building an Import mode on that premise
would be guesswork. What Gustav could do, in the portal, before deciding on n152 (nothing here was tried):

1. Read the Power BI page "Publish to web from Power BI" on learn.microsoft.com and note its date and what it lists as
   unsupported (Direct Lake, SSO-enabled data sources, row-level security, live connections).
2. On `shop_model`, Settings → Data source credentials / gateway and cloud connections: check whether the Direct Lake
   connection uses SSO; bind it to a cloud connection with a fixed identity (OAuth, SSO off), refresh, and try Publish
   to web on `shop_report_visuals` again.
3. If it is still refused and the Power BI page names Direct Lake as unsupported, n152 can go ahead as briefed, citing
   that page and its date. If step 2 works, the round would instead document the fixed-identity step for public
   reports (no Import mode needed).
4. For the brief's live check, should n152 go ahead after deploy: `create_semantic_model` with `storage_mode="import"`
   as `shop_model_import` on `demo_lh` (schema `shop`), set the data source credentials once (Edit credentials, OAuth),
   refresh, `create_report` on it, then Publish to web.

## Claims

n149 released Website (`f67b05b`). n151 claimed Engine, MCP tools and errors, Docs and submission and Tests, and
releases them with these notes.

## CI and deploy

| Run | Commit | Result |
| --- | --- | --- |
| 693 | `dc724de` n150 releases | green |
| 694 | `b93a440` n149 claims | green |
| 696, 697 | `c72624d`, `f67b05b` n149 | red: one browser check (a cut-off prefetch, see n149) |
| 698 | `7df0098` n151 | red: the same browser check only |
| 699 | `72db6e7` the browser-check fix | green (n149 and n151 together) |
| 700 | `4e4f6ae` release and notes | running when this was written (docs and CONTRIBUTING.md only; the suite was green locally) |

Nothing was deployed and nothing was sent to Fabric. Gustav's live checks after deploy: section 6 of docs/LIVE-TEST.md
(7 November 2026, "For the next run") for n151; the four portal steps under n152 above before n152 is taken up again.

Ready to deploy: bash deploy/krusgraph.sh --from-azure --update
