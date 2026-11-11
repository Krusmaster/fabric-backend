# Changelog

Dates are the commit dates on `main`. Versions are the `version` in `pyproject.toml`, mirrored in
`fabric_backend/__init__.py` and `server.json` (a test keeps them equal).

## Not yet deployed — after build `src-8d6c473bf26f45f9` (6 November 2026, main up to n111)

Rounds n114, n115, n116 and n120 are listed under 0.8.0 below and are not deployed either. Round n126 was added to
the list after it was written (round n127). `docs/DEPLOY-NEXT.md` is the checklist for the
next deploy.

- Round n216: **one look for the mascots: the glossy 3D figures of the overview film everywhere the products and the
  workload show them**. New `tools/mascot_renders.py` cuts Onto, Thinker and Builder out of the film's closing frame
  (112 x 112 px, transparent ground, own soft shadow so they work on dark pages) into `fabric_backend/static/mascots/`
  and `workload/Workload/app/assets/mascots/`. The four product cards ("Choose how you work", home page and /choose) show
  the 3D figure at 56 px (2x) with the product's prop as a small badge and one alt text per card. The workload's banner,
  Get started card and quick look use the 3D figures (the banner at the render's own 112 px, so it stays sharp); the
  item icon, workload icon and favicon stay the logo mark, which reads at 16-32 px. In the Krusgraph Model editor Onto,
  Thinker and Builder are the 3D figures at 48 px, the pose kept as a small lean, tilt or hop (still under reduced
  motion), the Mascots on/off switch as before. The Claude card no longer says "or another MCP client": with
  /mcp/connect off it says only Claude signs in to the hosted service; with it on it names VS Code and Cursor and
  /mcp/connect, in "Who it is for", "What you need", "How you work" and the VS Code row of the decision guide.
  `docs/MASCOT-ART-NEEDED.md` lists what is still flat and the renders that would replace it (props, poses, 512 px,
  transparent). The manifest images changed, so a new package is needed.
- Round n220: **run and schedule the pipeline from the chat, and a report name already taken**, after the founder's
  chat of 11 November 2026 (Run once answered 403; create_report refused a name the dry run had found free). The hosted
  MCP app may now hold `DataPipeline.Execute.All` as an **opt-in** permission (deploy switch `pipeline_execute`, server
  `KRUSGRAPH_PIPELINE_EXECUTE`; the deploy check then demands it with admin consent), listed with why on /it, in
  `docs/SCOPES.md` and `docs/TRUST-PACK.md` section 5; scope names cited from microsoft/fabric-rest-api-specs
  `dataPipeline/swagger.json` and Learn's Job Scheduler pages (read 11 November 2026). `create_pipeline` runs or schedules
  only after a dry run that shows what runs and when and the person's yes: the dry run's `jobs.confirm` passed back as
  `confirm_jobs` (the Model editor confirms in its own review); the run is read by polling the job instance. A token
  without the permission gets no bare 403: the dry run already says so, Create makes the items without asking Fabric to
  run them, and the answer names the app, the permission, admin consent and reconnecting, with "Run it in the Fabric
  portal". `create_report` with a taken name offers the next free name (checked), the existing report, says whether
  Krusgraph made it on this model and whether the name was free at the dry run, and checks the name again right before
  the create. Every error or refusal now ends with 1 to 3 next steps, on n218's cards too (`mcp_apps_next.error_steps`):
  the answer's own steps first (a dry run under the free name, a link opened with `ui/open-link`, or a sentence sent to
  the chat), else Try again and "Explain this and what to do"; a step never writes, and review_plan's card still opens no
  link. The build card offers "Use <name>_N" as a dry run where the name is taken. `tests/test_n220_run_from_chat.py`.
  Redeploy; the founder adds the permission in Entra (`docs/SCOPES.md`).
- Round n202: **a synthetic, SAP-shaped sample for demos, /check and films, with customer-specific Z tables**. New
  `fabric_backend/sap_sample.py`: `sap_sd` (order to invoice: `T001`, `KNA1`, `MARA`, `MAKT`, `VBAK`, `VBAP`, `LIKP`,
  `LIPS`, `VBRK`, `VBRP`) and `sap_mm` (purchase to pay: `T001`, `LFA1`, `MARA`, `MAKT`, `EKKO`, `EKPO`, `EKBE`), from a
  seed, a few hundred rows per table, two years of dates, every standard table and column a name the SAP pack already has
  (no `MATDOC`: the pack does not describe it; `MAKT` has its key only). Invented Z tables: `ZSD_ORDER_EXT` (MANDT +
  VBELN, one planted orphan), `ZSD_KAM_ASSIGN` (custom names only, `ZZ_KUNDE_NR`), `ZMM_PO_CONF` (confirmed dates for the
  late-delivery KPI). Planted: `VBAK.NETWR` over `VBAP` (the doubled total, with a wrong and a right gold view that
  `sql_sums` tells apart), orphan items, late goods receipts. Measured on Z tables: no key by name (K3); links through the
  standard key fields by R3, the rows confirming `ZSD_ORDER_EXT` -> `VBAK` and `ZMM_PO_CONF` -> `EKKO`/`EKPO` and
  rejecting `ZSD_ORDER_EXT` -> `LIKP`/`VBRK`; nothing found by the row checks alone (R5 and suggest_relationships look
  at single-column keys, SAP keys start with `MANDT`); `ZZ_KUNDE_NR` -> `KNA1` not found. `seed(spark, sap=True)` writes
  both (default off); /check offers "SAP-shaped sample (synthetic)"; `docs/SAMPLE-SAP.md` (tables and pack sources,
  findings, film scripts with the engine's numbers); `/docs` answers "Does Krusgraph work on customised SAP tables (Z
  tables)?"; `tests/test_sap_sample.py`. Synthetic, SAP-shaped, not SAP data. Redeploy for /check and /docs.
- Round n213: **a 30-day trial per organisation, then a Microsoft Marketplace subscription**, off until
  `KRUSGRAPH_TRIAL=1` (`docs/BILLING-MODEL.md`). The first authenticated call from an Entra tenant on the hosted MCP
  server or the Fabric workload starts its trial (one row in the subscriptions' table, no names or e-mail); after 30 days
  without a subscription, writing to Fabric is refused in plain words with the offer link and reading, checks and dry
  runs still run (`fabric_backend/billing.py`, one decision for tools and routes). The publisher's tenant (and a guest in
  it) and the pilot tenants are exempt. Users per organisation are counted as salted hashes only (`/privacy`); over a
  plan's cap the users and the founder are told, nothing is blocked. Founder events with an Azure Monitor alert in
  `docs/OPERATIONS.md`; `POST /workload/v1/access` and one quiet line in the editor; `/pricing` says it is planned;
  `deploy/krusgraph.sh --update --dry-run` lists what is missing. What Microsoft Learn allows for terms and notice, with
  sources, and a recommendation (no monthly plan with a three-month notice exists) are in the doc. No prices.
- Round n212: **standards on `/trust`, an opt-out for AI training crawlers, and a trust page comparison**. `/trust`
  and `docs/TRUST-PACK.md` get a Standards table: one row each for ISO/IEC 27001, NIS2 and the Swedish cybersecurity
  act, GDPR and Microsoft's publisher requirements (publisher verification, the workload attestation), each with what
  Krusgraph has (linked), what it does not have and what would come next. `/robots.txt` keeps search engines and the
  fetchers AI assistants use for a person's question, and asks GPTBot, ClaudeBot, Google-Extended, Applebot-Extended,
  CCBot and Meta-ExternalAgent out of everything (sources and dates in `docs/SITE.md`; only Anthropic's page could be
  opened, the others are marked Unverified); `/trust` says in one sentence that it is a request, not a block. Stale
  lines fixed: "no tool deletes anything" (`/trust`, `/docs`, the trust pack, `docs/TRUST.md`,
  `docs/PILOT-ONBOARDING.md`) now names the data product page's Delete from Fabric (n198); the ISO 27001
  self-assessment knows the incident process and the supplier pack of n211 (5.25 and 5.28 from missing to partly).
  New `docs/TRUST-PAGE-COMPARISON.md` (Modern Requirements' public trust and pricing material, from search snippets
  since the host was blocked, and five improvements for `/trust` and `/pricing`). No claim of certification or
  compliance. Site and docs only; redeploy for `/trust`, `/docs` and `/robots.txt`.
- Round n211: **a supplier security pack for customers under NIS2 and the Swedish cybersecurity act**. New
  `docs/SECURITY-SUPPLIER.md` (what the texts say with sources, Krusgraph's place in a customer's supply chain, roles,
  what is and is not in place, subcontractors, the Article 21 measures against what Krusgraph has) and
  `docs/INCIDENT-RESPONSE.md` (detect, assess, contain, notify, review; the notification time is a proposal for the
  founder). The site serves a vulnerability disclosure policy at `/security` (and `/security.md`), and
  `/.well-known/security.txt` names it as its Policy instead of the file on GitHub. `/trust` and `docs/TRUST-PACK.md`
  get a section linking them; questionnaire row 18 moves from Planned to Today, partly. No claim of compliance,
  certification or approval. Docs and site only; redeploy for the new page and the security.txt Policy line.
- Round n210: **verification of the integrated main before the first guest users** (n197 to n209). Security: Turn off
  (the Data product page's soft retire) used a schedule id from outputs.json unchecked in a DELETE path, so a crafted id
  could become a hard delete of another item while the dry run said "Remove the schedule"; only GUID ids are used now,
  and Delete from Fabric leaves an item recorded in another workspace alone. Guests: "by whom" and **Me** fall back to
  the token's email (and a guest `#EXT#` sign-in name read back), tests with guest-shaped tokens, and
  `docs/GUEST-TRIAL.md` says which tenant id the allowed list needs. The page asks for health with the Model's own
  workspace (it sent the source's, which failed when they differ). `build-package` stops in a shallow clone instead of
  giving a version below the one in Fabric. An end-to-end test of the mill sample read from a mirrored database. Unit
  tests and test doubles only; redeploy for the engine and the editor, the workload manifest did not change.
- Round n209: **the Krusgraph Model ready for the first outside users** (the founder's live tests of 10 November 2026).
  The dry run and Create take one decision (`workload_api.existing_decision`, each card's `decision`): items built from
  this plan, also by another Krusgraph Model item, are "already built from this plan, will be skipped" in both; red only
  for an item someone else made; "would be updated" only where Create writes. Gold views no longer repeat the join keys
  (`orders_order_id` and the like); the orphan rule moved to the view's WHERE with the same rows kept and dropped. The
  review says "This link holds in the rows: 0 of N rows point at nothing." next to Reject and what rejecting such a link
  costs the semantic model, the API and the ontology. An App already built keeps its choices and package link on reopen.
  With Run once ticked the data agent's example queries are checked and the agent published only after the run
  succeeded; a failure to connect is retried once and reads "not checked yet", never "invalid". An end-to-end test of
  review, dry run, Create, the Data product page with health, Update and Retire (n198, n200, n201 together).
  `docs/GUEST-TRIAL.md` (new) and a section on /pilot/fabric: B2B guests in the publisher's tenant before the workload
  name is registered, cited to Microsoft Learn with Unverified where Learn is silent. Not run against a live workspace.
  Redeploy for the engine and the editor; the workload manifest did not change.
- Round n201: **the Krusgraph Model reads mirrored databases**, SAP mirrored through SAP Datasphere among them, and
  warehouses and SQL databases (the founder, 10 November 2026: the detail page said "Compatible with: Lakehouse"
  only). The source picker offers the four item types; review and check read the SQL analytics endpoint, read-only.
  A read-only source's silver notebook, gold views and pipeline (with its check) write to a lakehouse the person picks
  (Target lakehouse; default the first lakehouse of the workspace, said in the dry run), and the silver notebook reads
  the mirrored tables at `oneLakeTablesPath` (Get Mirrored Database on Learn) in OneLake, with no copy outside Fabric
  and no shortcut. For SAP tables the review marks the SAP pack's keys (with MANDT) and links "from the SAP pack" with
  the pack's public sources, and says what mirroring delivers (Initial and Delta, Parquet) and that SAP Datasphere
  Premium Outbound Integration is the customer's licence matter. Both workload packages list MirroredDatabase,
  Warehouse and SQLDatabase as compatible item types, show the founder's overview film first on the detail page, and
  point the "Certification" link at the attestation page, which says "Draft." at the top. New: `fabric_backend/mirroring.py`,
  `docs/SAP-MIRRORING.md`, `tests/test_n201_mirrored.py`, `tests/test_n201_manifest.py`, `sourceWords.ts`. Not run
  against a mirrored database in Fabric, and no SAP Datasphere was available. A new workload package is needed.
- Round n198: **the Data product page** in the Krusgraph Model item (the founder's question of 10 November 2026: how to
  remove items, update ontologies and data products, and look after the workspace after Create). An item with outputs
  opens on it: name, owner (picked from the workspace's people, kept in the item), health (n200's route when present,
  else "not checked yet"), the pipeline's last run, the plan id and every item with its state in words (built, pending,
  failed, changed outside Krusgraph, missing, removed) and Open in Fabric. *Check against the rows again* lists what is
  out of date with the existing Update path (an App only under a new name). *Retire* turns off the schedules Krusgraph
  made, then *Delete from Fabric*: a dry run of exactly what goes, the data product's name typed, Delete Item per item;
  only items in outputs.json, never a lakehouse, a table or a view's data; each removal recorded with when and by whom.
  *Clean up leftovers* finds items with Krusgraph's plan marker that no Krusgraph Model lists (such as demo_lh_model4)
  and offers Adopt or Delete. `fabric_backend/product_life.py`, `POST /workload/v1/product`, `DataProductView.tsx`,
  `productWords.ts`; `docs/PROMOTE-DESIGN.md` (dev → test → prod with Fabric's Git integration and deployment pipelines,
  design only). Not run against a live workspace yet. Redeploy and build a new workload package to see it.
- Round n200: **health over time and alerts** (Lifecycle round 1, `docs/LIFECYCLE-DESIGN.md` section 8;
  `docs/HEALTH.md`). The pipeline's check notebook appends one row per check to `krusgraph.health`
  (`krusgraph_health` without schemas): run id, time, plan id and fingerprint, check, object, rule, status, count and
  the previous run's count of the same plan. Checks: keys, orphans, rows and sums through each gold view's join (pass or
  fail only, never the sums), row counts of every silver table and gold view (warn when one falls by 50 % or more),
  freshness of each source table from Delta's table history (a commit time; warn after 2 schedule intervals, fail after
  3) and quarantine counts per rule. Never a row value. The pipeline's silver notebook starts with a drift step against
  the plan the outputs were built from: a source table or a used column gone stops the run before anything is written,
  with the reason; anything else is recorded. Optional alert: an Adaptive Card to a Teams workflow or Power Automate
  HTTP trigger whose address is an Azure Key Vault secret the owner names on the pipeline (`alert_key_vault`,
  `alert_secret_name`, `alert_on`), never in code; the pipeline card gives the steps for Fabric's free e-mail on a failed
  scheduled run. `POST /workload/v1/health` returns one health word per data product (green, amber, red, not checked
  yet) and the open findings, read as the signed-in user. All notebook code is written into the cells verbatim (no
  `%pip`, no import of this library), tested on SQLite and a local PySpark; not yet run in Fabric.
  Redeploy, then Create again to give an existing pipeline the health step.
- Round n205: **trust, honest labels, a comparison and findability** before the launch of 11 November 2026, after a
  reviewer's report of 10 November ("the biggest obstacle is trust, not technology"). `/trust` ("Security and data",
  Markdown twin `/trust.md`), written from `docs/TRUST-PACK.md`: what passes through, that no table contents are
  stored, the region, sub-processors, delegated permissions, how to revoke, what is and is not in place (no
  certification held, the attestation a draft, no penetration test) and the questionnaire answers; linked from the
  footer, `/pricing` and `/choose`, in the sitemap and llms.txt. Every hosted tool whose status is neither "tested end
  to end" nor "created live" has "(experimental)" at the end of its title (`tool_status.experimental`, applied in
  `_titled_tool`; today `domain_draft`, `sap_pack_draft`, `create_views`, `create_data_agent`,
  `compare_semantic_model`); `create_pipeline`'s short status is "created live" (it created and ran `pipeline_shop` on
  7 November). The README's status block per tool is generated from `tool_status` and tested equal; the README's
  first line says what Krusgraph does and that this is its source, and a Roadmap section lists what is planned.
  `/choose` has "Why not just Microsoft's tools?" (five rows, linked from `/docs`); `/pricing` says what is free today
  and that a Marketplace team plan is planned with no price. `docs/FOUNDER-TODO.md` lists the GitHub settings only the
  founder can change. Two titles were shortened to keep the read-only listing under its 64 500-character cap.
- Round n204: **the Marketplace landing page accepts personal Microsoft accounts as well as work accounts**, as
  Microsoft requires of a SaaS offer sold through Microsoft (Learn, "Plan a SaaS offer", Technical requirements;
  certification policy 1000.3). With `KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID` (deploy key
  `marketplace_signin_client_id`) and its secret (`marketplace_signin_secret_keyvault_uri` or the container-app secret
  `marketplace-signin-secret`) the buyer signs in through `/common` with a new, separate Entra app, *Krusgraph
  Marketplace sign-in* (work or school accounts of any organisation and personal Microsoft accounts), scopes `openid
  profile email`; unset, the page works as before (`/organizations`, the site's app, `openid profile`). The site's main
  app keeps its audience (`AzureADMultipleOrgs`). The ID token's issuer is checked for the consumer tenant
  (`9188040d-6c67-4c5b-b112-36a304b66dad`) and for organisational tenants; a token for another app is refused. A
  personal account resolves, sees and activates the subscription exactly like a work account (the beneficiary tenant
  comes from resolve), and the page says that Fabric needs a work account in the tenant shown, with that tenant's
  admin-consent link. The landing page's cookies are now signed (a hand-made cookie naming another subscription is
  refused), and the access log line of `/marketplace/` drops the query (the purchase token). `docs/MARKETPLACE-SETUP.md`
  section 2a: the founder's Entra steps; `docs/MARKETPLACE-CERTIFICATION-NOTES.md`: the *Notes for certification*
  draft and the listing checklist (policies 100.1–100.7, 1000.x). `tests/test_n204_marketplace_personal_accounts.py`.
  Redeploy to use it: create the app, set the two keys, `bash deploy/krusgraph.sh --update`.
- Round n197: **Create runs in the background, follows the pipeline run and finishes on its own.** Every editor request
  answers at once (202 and an operation id) and the editor reads the operation until it ends: no request is held open
  longer than 30 s, so the 230 s "no answer" and the phone's "Failed to fetch" are gone. Operations live in the client
  registration's store (Table Storage across replicas), so a reload, a closed tab or a phone asleep resumes the same run.
  Throttling (429, PFE_FABRIC_THROTTLED) is "waiting for capacity" and retried; Fabric's long-running operations are
  followed ("still running in Fabric", never failed) and adopted; items are recorded as pending before they are sent.
  With Run once ticked the run is followed on the pipeline's card, then the model is refreshed, the report made, the
  agent's examples checked and the agent published if ticked; a failed run stops them with the reason. Try again on
  every red card, Create the rest on the result; truthful dry run and Next; the App with one Cloud Shell command.
  `docs/WORKLOAD-DEV.md` section 15. Redeploy: `bash deploy/krusgraph.sh --from-azure --update`.
- Round n196: **The film at the top of the home page, under the headline.** The overview film moves from its section
  below the hero to directly under the headline, the sentence and the two buttons, centred, up to 960 px wide on a
  desktop (narrower on a short screen, so the headline, the buttons and at least the top half of the film fit at
  1280 x 720) and the full content width on a phone, where the 4:5 version still plays (n161). It is muted, loops, plays
  inline, preloads only its metadata, and has a visible Pause/Play button with an accessible name; site.js starts it
  unless the visitor prefers reduced motion, when the poster stays and nothing plays until asked. It is on the home page
  once; /docs keeps its own. Three blocks leave the home page: the before/after chip with the three points and the SAP
  line (the sentence and the points now open /docs as "What Krusgraph does", before "Which Krusgraph should I use?"; the
  SAP line stays on /docs and /sap), "Which Krusgraph should I use?" with its rows and the no-AI paragraph (on /docs and
  /choose already), and "What Krusgraph reads" (its two paragraphs and three points are now "Data and access" on the /docs start page).
  The footer on every page says "Krusgraph is a preview service" with links to the test status per tool and to how data
  and access are handled. A customer quote, Swedish with the English translation, anonymous by request and published
  with the person's written permission, on /docs' Get started page only; the docs' Markdown renders "> " as a quiet
  blockquote. No new copy otherwise. Tests: tests/test_n196_home_film.py and tests/n196_browser.js (375, 768, 1280 and
  1440 px, light and dark; reduced motion; the button by keyboard); the tests that pinned the old places moved with the
  blocks. Redeploy to see it live: `bash deploy/krusgraph.sh --from-azure --update`.
- Round n195: **Krusgraph.Modeler ready for Microsoft's publishing review, as far as the repository can make it.**
  The vendor attestation (Section III of Microsoft's template, filled from what the code does: no row values, delegated
  permissions only, Azure Container Apps in Sweden Central, the one read-only admin call, and every open point marked
  "Not yet") is a page at `/workload/attestation` with a Markdown twin, marked **Draft** and `noindex` until the
  founder removes the marker, not linked from the home page or the navigation. The Krusgraph.Modeler package's
  `Product.json` points `productDetail.supportLink.certification.url` (the attestation link Microsoft's review and
  validator read) at it; `Org.Krusgraph`'s package is byte for byte as before. `build_package.py` refuses a
  Krusgraph.Modeler package without what the review reads and we can fill (publisher, en-US texts, https links, icon
  and banner sizes, learning material) and prints the one gap it cannot fill (no Marketplace offer); the CI `workload`
  job builds both packages. `docs/WORKLOAD-PUBLISH.md` is now the founder's runbook: the name-registration blocker and
  a support ticket text, publisher verification, the upload with the name letter by letter, Microsoft's test tenant
  and pilots on the Publish tab, the target tenant's setting and consent, the form's page 2 answers and a TODO list.
  `tests/test_n195_attestation.py`. **To put the page live, redeploy** (`bash deploy/krusgraph.sh --from-azure
  --update`), **then build Krusgraph.Modeler again.**
- Round n192: **a synthetic manufacturing sample, 'mill', beside the shop.** `fabric_backend/mill.py` generates a
  fictional Swedish workshop (Ystervik Mekaniska) from a seed: sixteen tables with names of our own (customers,
  suppliers, items, bill_of_materials, work_centers, sales, purchase and production orders with their lines and
  operations, inventory_transactions, deliveries, item_prices, a staging table and an event log), 5 012 rows, two
  years of dates. It has single keys, two composite keys (order + line), role columns (bill-to and ship-to customer,
  parent and component item), a code key (`work_center_code`), a self-reference the engine does not link, and planted
  problems: four orphan rows, a duplicate id in `stg_supplier_prices`, 12 late deliveries and a keyless event log
  (`tests/fixtures/mill/planted_issues.json`). /check offers it as **Manufacturing sample** (`/check?example=mill`);
  `seed(spark, mill=True)` writes it to a schema `mill` (off by default; the shop stays the default).
  `tests/test_mill.py` pins the plan's 15 keys and 24 relationships with their rules, the exact findings, and runs the
  KPI queries of `docs/SAMPLE-MILL.md` (on-time delivery, order backlog, inventory value, work center load, BOM cost
  roll-up). **To see the button live, redeploy:** `bash deploy/krusgraph.sh --from-azure --update`.
- Round n194: **the home page from before n190 is back.** The founder looked at the live site after n190 and kept the
  previous home page: the film, the session replay, the hub, the FAQ and the developer note are on it again, with
  n188's navigation and the "Connect to my Fabric" label (n190's commits 868e063 and 3c3a9e2 reverted). Kept from
  n190: n190's **What you can build** grid (seven outputs, each with its status chip from `fabric_backend/claims.py`,
  the chip legend and the sentence on dry run, opt-in Run once or Schedule and /check's drafts), unchanged in look, now
  at the top of /docs after *Which Krusgraph should I use?* and the film, and in /docs.md; /choose no longer says Krusgraph for Fabric
  never runs the pipeline. Not kept: the chips on /start, /choose and /pricing and /check's `intent=` landing.
  `docs/WEBSITE_UX_AUDIT.md`, `WEBSITE_COPY_REWRITE.md` and `WEBSITE_IMPLEMENTATION_PLAN.md` stay as reference, marked
  not applied. The tests n190 retired or changed are back as they were; `tests/test_n194_site.py` replaces
  `test_n190_site.py` and `n190_browser.js`. **To see the old home page live, redeploy:**
  `bash deploy/krusgraph.sh --from-azure --update`.
- Round n190: **the home page redesigned after the outside UX review of 9 November 2026.** One promise ("Your data
  already has connections. Krusgraph finds them.") with **Try the free demo** (the guided demo, no account) and
  **Connect Microsoft Fabric** (the label is now that everywhere); four intent tiles (Find broken relationships,
  Understand how my tables connect, Build a Power BI model, Prepare my data for an AI agent) that open /check on the
  sample with `intent=…` and land on the findings, the map, the Power BI draft or the ontology and evidence; the
  engine's map of the sample under the hero; a before and after computed from the engine's run, with each issue in
  plain words and its check and rule on expand; **What you can build** with one status chip per output (Tested live,
  Preview, Experimental) from the new `fabric_backend/claims.py`, derived from `tool_status.py`, and the same chips on
  /start, /choose, /pricing, the docs' *Test status* and the Markdown twins; one sentence on running and scheduling
  (only Krusgraph for Fabric, opt-in, with `DataPipeline.Execute.All`), which resolves the contradiction the review
  found; /choose no longer says Krusgraph for Fabric never runs the pipeline (n185 added Run once and Schedule). The
  navigation is Product, Examples, How it works, Pricing, Docs and **Try free demo**. /check, the blog, the pilot,
  GitHub and the legal pages are in the footer. The session replay, the hub, the film, the FAQ and the developer
  note left the home page (the film stays on /docs). `docs/WEBSITE_UX_AUDIT.md`, `docs/WEBSITE_COPY_REWRITE.md` and
  `docs/WEBSITE_IMPLEMENTATION_PLAN.md`; tests in `tests/test_n190_site.py` and `tests/n190_browser.js` (375, 768
  and 1440 px, light and dark). Redeploy to publish.
- Round n188: the home page's points are three: **Checked against your rows**, **Errors before anyone sees them** and
  **One checked plan, every starting point** (what the Krusgraph Model item creates from the reviewed plan; the silver
  and gold tables fill when the pipeline runs; /check gives drafts). The SAP point moved to its own page, **/sap**: the
  keys with MANDT and the links of VBAK, VBAP and their neighbours from the SAP pack, each with its public source, linked
  from the home page in one line. /check's *Go further with these tables* has four tiles, 2 x 2 from 760 px and stacked
  below: Build a Power BI model, See it as an app, **Build a Fabric IQ ontology** (the RDF/XML download, with its ?) and
  **Hand over the evidence** (the evidence report). The docs start page and the docs menu begin with **Which Krusgraph
  should I use?**. Redeploy to publish.
- Round n185: **Run once and Schedule** for the pipeline the Krusgraph Model creates, both off by default. Run once
  starts one run after Create and shows each step with its duration and a link. Schedule is daily or every N hours, in
  a time zone (default Europe/Stockholm), with the next run time; a Krusgraph schedule is updated, never doubled, and
  others are never touched. Both need `DataPipeline.Execute.All`; without it they are shown disabled with the steps.
  Run and schedule ids are kept in `outputs.json`. The MCP tool `create_pipeline` takes `run_once` and `schedule` with
  the same dry-run wording.
- Round n185: the **data agent reads one layer** (silver, gold or the source, never two copies of a table; the founder
  saw shop and silver ticked together). Its examples' validation is shown, and the card says Fabric shows them as
  *Example queries*, not as the chat's suggestions. **Publish the agent in Fabric** and **Also make it available in
  Microsoft 365 Copilot** are separate ticks, both off. Publishing happens only with one layer and, with Run once, after
  the run succeeded. Copilot has no API and gets a preflight (capacity, tenant settings, licences).
  `docs/DATA-AGENT-PUBLISH.md`, also on the agent's MCP tab. The report's footer line and the last table row have room
  at 1280 x 720. `docs/WORKLOAD-DEV.md` step 14. Needs a redeploy, `DataPipeline.Execute.All` with consent in the Entra
  portal (only for Run once and Schedule), and a new workload package version.
- Round n184: the Krusgraph Model editor's **output cards show the Fabric icon of the item type** each creates (Notebook
  for the silver notebook and the gold views, Pipeline, Semantic model, Report, Ontology, Data agent, App; the generic
  Fabric item icon for the API for GraphQL, which Microsoft's package has no icon for), 20 px left of the title, with
  the item type as alt text, on *Choose what to build* and on the dry-run and Create cards. The icons are Microsoft's,
  unmodified, from the npm package `@fabric-msft/svg-icons@12.0.0` that Microsoft Learn offers for Fabric platform
  extension development; *About and notices* in the editor and `THIRD_PARTY_NOTICES.md` carry the terms and the
  trademark line. **Default names** follow one pattern from the lakehouse (`demo_lh_api`, no longer `demo_api`).
  `docs/WORKLOAD-DEV.md` step 13. Needs a redeploy and a new workload package version.
- Round n184, additions from the founder's live Create: while Create runs, the line counts "4 of 9 created, 1 creating,
  4 waiting"; the data product lists the pipeline's notebooks as notebooks; no card step names a tool ("Run
  demo_lh_silver first"), the report asks for a refresh only when Create's refresh did not happen; the report's visuals
  are counted alike in the dry run and on Create, with what was not drawn and why; a pipeline that did not exist says
  created; the App card says the App item is empty and puts its commands under "Still to do (in a terminal with Node)".
  **Create ends clearly**: a banner ("Done: 9 of 9 created in demo", or "Done with problems" with the reasons), the
  mascots celebrating (mascot switch and reduced motion respected), a green, amber or red mark on each card, *Next* and
  *Keep it up to date*, kept in `outputs.json` and shown again with its date when the item is reopened.
- Round n183: the **product diagram is a data flow**, on the home page and on `/choose`: your tables in Fabric
  (lakehouse, warehouse, mirrored databases) → one Krusgraph engine (keys and links, checked against your rows) → built
  in Fabric (semantic model, report, ontology, API for GraphQL, pipeline and notebooks, data agent, App (Rayfin, preview),
  data product). The four products sit above the engine as the ways to drive it, each with its "Data passes:" line;
  on a phone everything stacks in that order. "The diagram in words" is a collapsed `<details>` under it. Each product
  card has its **mascot hugging a symbol** we draw ourselves (the founder's decision): Onto with a data table for
  Fabric, the Thinker with a speech bubble for Claude, the Builder with an app screen for Lovable, Onto with code
  brackets for Open Source, with "for ..." under it; inline SVG with alt text, hidden by the mascot switch, and no
  partner logo anywhere. The **home page is calmer**: hero, demo, the diagram, the five-row guide ("We code in VS Code or
  Cursor" → Krusgraph for Claude (any MCP client)) and one line, "Krusgraph is a preview service. Test status per
  tool."; the "Build on the relationships you've reviewed" list moved to the docs' *How it works*, the long status
  paragraph to the docs' *Test status*, which now also says what the Krusgraph Model item creates, the App included.
  The **Krusgraph Model item icon** is Fluent-style (a rounded container, a soft gradient, a slight depth, the three
  connected nodes in Krusgraph's colours), sized by Microsoft's item icon guideline, and is the editor's logo at the top
  left. The workload's banner has no text, so the workload page's own text no longer runs into it. Needs a redeploy and
  a new workload package version (new icons and banner): `docs/WORKLOAD-DEV.md`, section 12.
- Round n181: **App (Rayfin, preview)** is one more output of the Krusgraph Model item. Preview first checks the tenant
  setting "Enable Fabric App Items (preview)". When it is off, a plain card names the setting and says where an
  administrator turns it on, and nothing more happens. Fabric's own 403 "The feature is not available" gets the same
  card. The person ticks key figures, list pages and charts; these are rules over the plan, use no AI and are stored in
  outputs.json. The dry run shows the pages and the read-only connector. Its API has queries only and no mutation
  types, and carries every link, R5 ship_to_id included. A package for the `dataapp` template comes with it, with
  `rayfin/tsconfig.json`; CI runs `tsc --noEmit` on it. It also gives the `rayfin login`, `connector add` and
  `rayfin up` commands. Create makes the App item with Microsoft's documented call (Create App Backend,
  Item.ReadWrite.All) and records its id and plan. The pages are published with the package, because no App item
  definition is documented. The MCP tool `rayfin_connector` runs the same preflight first and answers with the admin card
  when App items are off (no new parameter: the tool listing stays under its size cap). Sources: `docs/RAYFIN-APP.md`.
- Round n177, follow-up (the founder, 9 November 2026, evening): **four product names** on `/choose`, in the diagram and
  in the workload docs: Krusgraph for Fabric (the Krusgraph Model item), Krusgraph for Claude (the MCP connector, which
  works in other MCP clients too), Krusgraph for Lovable and Krusgraph Open Source. The docs group is now *Krusgraph for
  Fabric* (`/docs/krusgraph-for-fabric`). There is one Krusgraph logo, the site's own, on the engine: no product icons,
  no mascot per product, and partner names as plain text only. `/choose` says that the chat demo and /check are ways to
  try it, that the drift monitor, the SAP pack and the dbt export are features, and that buying through Microsoft
  Marketplace is planned.
- Round n177: **Which Krusgraph should I use?** A new page, `/choose` (and `/choose.md`), compares the four ways: in
  Claude, in other AI agents over MCP, run it yourself, and the Krusgraph Model item in Fabric. For each it says who it
  is for, what you need, how you work, what it builds, where the data passes, what is free or paid (only what /pricing
  says), its status (from tool_status and LIVE-TEST) and what it lacks today, followed by the founder's four-line decision
  guide. It says plainly that the Fabric item uses no AI model. The **product offering diagram** (one engine in the
  middle, the four ways around it, what is built in Fabric on the right) is on the home page and on `/choose`. It is
  inline HTML and SVG in the site's colours, stacks on a phone, has a list in words under it, and each way is a link
  with a focus ring. All of it is rendered from `fabric_backend/offering.py`. The docs have a new group, **Krusgraph in
  Fabric**: what the item does, with four screenshots of the editor's own components on synthetic data
  (`workload/scripts/screens/`), how to add it (pilot on request, `/pilot/fabric`; Workload Hub listing planned, not
  available), permissions in plain words (from `workload_api.KINDS`), network hosts and troubleshooting. `/start` has
  **Use it in Fabric** next to Claude and the other agents, in the path cards. Fixes from the
  founder (8-9 November):
  - In full screen the film is letterboxed (`object-fit: contain`), and its file follows the orientation: 16:9 in
    landscape, 4:5 upright.
  - The chat demo says "That is the demo" only after the last step.
  - The fixes and dbt steps' status sentences say what LIVE-TEST records: the option is unit-tested, and the tool
    without it ran live (`tool_status.LIVE_OPTIONS`; a test reads LIVE-TEST).
  - On the /check map, linked tables take neighbouring seats. Interface lines read "interface · product_id", and the
    dashed "?" line has hover text.
  - The dbt step in the chat demo and a new `dbt_schema` MCP Apps card draw the project's flow (sources → staging →
    marts → model, boxes folded, a click shows the SQL or YAML; `fabric_backend/dbt_flow.py`). The chat and the card
    share one renderer.
- Round n176: **Krusgraph.Modeler**, the permanent workload name (the founder's decision of 9 November 2026), for up to
  20 selected tenants. `workload/scripts/build-package --name Krusgraph.Modeler` builds it (item type
  `Krusgraph.Modeler.Model`); `Org.Krusgraph` stays the default, and every other `Krusgraph.*`
  name is refused. The name is written once, in the build. The hosted editor reads the workload from the item it opens,
  so one image serves both names; `KRUSGRAPH_WORKLOAD_APP_ID_URI` takes a comma list and tokens for each URI are accepted.
  A user from a tenant outside `KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS` gets a 403 with `kind: tenant_not_allowed` and a plain
  message in the editor, no longer a 401 sign-in answer. `docs/WORKLOAD-PUBLISH.md` (the founder's steps: Entra, server,
  upload with the irreversible name dialog, Selected tenants, next pilot, withdrawing; keep the existing app as the
  production app), `docs/PILOT-ONBOARDING.md` and the page `/pilot/fabric` (the pilot administrator's five steps).
- Round n180: in the Krusgraph Model, "already built" means built from this plan. Every item a Create writes records
  the plan it was built from (plan id, schema fingerprint, exact schema, links) in outputs.json and at the end of its
  Fabric description. On a re-run, an item built from another plan gets the card "built from a different plan (schema
  Shop, 6 links; now shop, 7 links)", and one built before plans were recorded "built by Krusgraph, plan unknown"; nothing
  is written for either, and the card offers Update (where the tool updates in place; a dry run first, whose
  `confirm_update` the engine requires before it writes) or Choose a new name. Cards of existing items show what the item
  holds (notebook cells and views, report pages and visuals, model tables, data agent example questions) or no count,
  never "0 visual(s)" for a report that has them. Addition 4: Create refreshes a semantic model it has just created once
  (Power BI REST Refresh Dataset In Group, `Dataset.ReadWrite.All`), waits up to two minutes and says refreshed,
  refreshing, refresh failed with the reason, or the missing permission with the Entra steps, before the report is
  built; the dry run says so. The report's title names the model, not its id, and its cards and slicers are sized so
  their captions fit at 1280 x 720. Needs a redeploy, a new workload package version and `Dataset.ReadWrite.All` on the
  workload's Entra app.
- Round n179: Create in the Krusgraph Model sends one request per output (the model before its report), each card with
  its own progress and result; a lost answer says "no answer yet, it may still be running in Fabric" on its card instead
  of "Failed to fetch" for the page; the created ids are saved after each output. A re-run (`skip_built`) shows the
  outputs already in the workspace (built by this Model, or with Krusgraph's description from a Create whose answer was
  lost) as already built and writes nothing for them. The report tries a new model's definition again before it says
  why (`source_not_ready`). Every error on `/workload/v1` is JSON with the CORS headers, and the console log has one
  JSON line per output, failure and server start. `POST /workload/v1/schemas` lists the lakehouse's schemas with their
  tables; the editor offers them as a list (the only schema with tables preselected) and the free-text schema field is
  gone unless the list cannot be read. The semantic model's card is in words (it showed "[object Object]"); generated
  gold SQL names the rule without the certainty number; the flow says plainly that the model, API, ontology and agent
  read bronze even when gold views are built, and that building them on gold is a later option; the permissions are
  folded into a Permissions note. Needs a redeploy (`docs/WORKLOAD-DEV.md`, Hosted, step 9).
- Round n175: a schema typed in another case than the source spells it (`Shop` for the lakehouse schema `shop`) is
  read and queried under the metadata's spelling on every path: the MCP tools, the editor's review, check and build,
  R5's counting queries and the creating tools' definitions. Live on 9 November 2026 the check had failed with
  `Invalid object name 'Shop.addresses'` (42S02) and the review had shown 6 links instead of 7. Table and column names
  in `keys` and `confirmed` are spelled as the metadata spells them too. The answer says which name was used
  (`schema_used`: asked, used, note); the editor saves the exact name and shows a notification. Two schemas that differ
  only by case answer `kind: schema_ambiguous` with both names, and nothing is counted. The workload's page in Fabric:
  the Krusgraph logo mark as the workload icon (64 px), favicon (32 px), item icon and a distinct active item icon (48 px) and the New item card's 24 px icon, sizes Microsoft's validator approves, a banner in the
  site's style with the mascots, the getting-started steps, the editor's map as the quick look
  (`workload/scripts/build_manifest_images.py` draws all eight), a description of every output, the data product and the
  data flow, publisher Kruse Consulting AB, and the hosts IT must allow. The editor's loading view shows the Krusgraph
  mark instead of the Fabric logo. The site's /it has **Network: hosts to allow** (`workload.krusgraph.com` and
  `krusgraph.com`, 443, TLS 1.2 or later) with the symptom "Krusgraph Model keeps loading"; the docs' first-time errors
  and `docs/WORKLOAD-DEV.md` have it too. Needs a redeploy and a new package version (`docs/WORKLOAD-DEV.md`, Hosted,
  step 8).
- Round n174: the Krusgraph Model item builds everything the MCP tools build. **Choose what to build** offers the silver
  notebook, the gold views, the pipeline, the semantic model, a report (on that model or an existing one), the API for
  GraphQL, the ontology and the data agent (left unpublished); `POST /workload/v1/build` takes `outputs: [{kind, name}]`
  and calls each output's MCP tool (`create_silver_notebook`, `create_gold_views`, `create_pipeline`,
  `create_semantic_model`, `create_report`, `create_backend`, `create_ontology`, `create_data_agent`) on the plan the
  review left, on-behalf-of the user, dry run first: one card per output, the data flow first, the model before its
  report. It never writes over an item of the same name that this Model did not build (`already_exists`), and a report
  is never updated in place. Each card lists the delegated permissions the output needs; when the user's token lacks
  one the dry run says so and Create refuses that output with `kind: consent`, the permission and the Entra steps for
  the workload app. Nothing is run or scheduled; no Execute permission is used. **Data product**: an optional name over
  the build, with the domains `domain_draft` proposes, an owner nobody has chosen yet and the plan's version, kept in
  `outputs.json` with the created ids; a re-opened item shows it and offers **Update** where the tool updates in place.
  **The data flow, drawn**: bronze tables → silver tables (one row per key, the links each checks) → gold views (which
  silver tables each joins, on which columns, with the rule) → what is built on the source, and the pipeline's steps
  below; dashed where the build does not make it; Builder presents it. A click, Enter or Space on a box unfolds its code,
  exactly the dry run's: the notebook cell, the CREATE MATERIALIZED LAKE VIEW, the pipeline activity, the model's
  relationships and measures (`fabric_backend/data_flow.py`, `FlowView.tsx`). Not added to the Claude cards: the three
  flow tools have no MCP Apps card yet. Phase 1's form (`name` with `["graphql"]`) answers as before. Needs a redeploy,
  new Entra permissions on the workload app and a new package version (`docs/WORKLOAD-DEV.md`, Hosted, step 7).
- Round n173: the Krusgraph Model editor in Fabric (workload.krusgraph.com), from the founder's run on 8 November
  2026. **Check against the rows** in the review (Home ribbon and a button): a new route, `POST /workload/v1/check`
  (same workload audience and on-behalf-of path as `/review`), runs the counting queries on the reviewed plan and
  writes each key's and link's check into `review.json`: passed (green), failed with its orphans, duplicates or empty
  values (red), not checked (grey); the dry run then says what passed instead of "Not checked: validate_plan". The
  review draws the plan as the MCP Apps cards' map (the cards' own code, copied by `workload/scripts/build_card_map.py`
  and checked current by a test) with the review and check states; **List** keeps the rows. Onto, Thinker and Builder
  speak in the editor with the site's figures and colours; Thinker's question about a table without a key comes with
  its choices inline (`/review` takes the person's `keys` and `confirmed`). **Accept all** and **Accept all that passed
  the check**. Plain-English summary and rows; rule codes stay as pills with a tooltip. Needs a redeploy, then a new
  package version in Fabric (`docs/WORKLOAD-DEV.md`, Hosted, step 6). The MCP cards, the site and Marketplace are
  unchanged.
- Round n172: the MCP Apps cards polished for the film (`docs/MCP-APPS-POLISH.md`), from the founder's try in Claude on
  8 November 2026. A read on the SQL analytics endpoint that fails with a transient connection error (SQLSTATE 08S01,
  the TCP Provider's 0x2714 and other socket errors, Azure SQL's transient error numbers) is tried again on a fresh
  connection, at most three tries with 1 s and 3 s between them; the sign-in, syntax errors and timeouts never are.
  When every try fails, `plan_backend` says the count could not run (`proposed[].not_counted: "failed"`, a summary
  line, `counted_in_rows.failed`), the card draws the link grey, "not counted", and the Thinker offers **Count again**.
  The cards: the map's labels sit on their lines and cover no table; Onto says the plan in short sentences once ("7
  tables, 6 with a key. 7 links: 6 by name, 1 found from the values ..."), the Thinker and the Builder speak plain
  English and never show arguments (the buttons carry them; text clients keep each action's `say`); the titles are
  "Plan" and "Plan check"; the Plan check card shows the Builder's three builds with the drafts under **More**; how a
  tool was tested and "certainty" are left out of the cards (still in the text answer), the rule shown instead;
  `create_semantic_model`'s inactive relationships now carry their `rule`. Fixed: in Claude no **Create** appeared under
  a build's dry run (all four builds): the MCP SDK passes every default to the tool, so the Create action carried
  arguments the card had not sent; buttons are now built from the arguments the call changed, and the card compares
  effective arguments.
- Round n171: Krusgraph can be bought through Microsoft Marketplace, all off by default (`KRUSGRAPH_MARKETPLACE`,
  `docs/MARKETPLACE-SETUP.md`). `/marketplace/landing` signs the buyer in (the existing Entra app, `openid profile`
  only), resolves the purchase with the SaaS fulfilment API v2 and activates on the buyer's click (nothing to activate
  with auto activation); `/marketplace/webhook` checks Microsoft's bearer token (issuer and `tid` our tenant, `aud` the
  fulfilment app, `appid`/`azp` the Marketplace SaaS API), confirms each event with Get operation, records it once per
  operation id and acknowledges ChangePlan, ChangeQuantity and Reinstate. One row per beneficiary tenant in the
  entitlements table (subscription id, offer, plan, status, updated_at; no user data). With `KRUSGRAPH_ENTITLEMENTS=1`
  as well, creating calls (`dry_run=false`) in the MCP tools and the Fabric editor's Create (`/workload/v1/build`, HTTP
  402) answer `kind: upgrade` with the offer's link when the tenant has no active subscription; reads and dry runs stay
  free; the card's Create shows the message and a button to the offer. `deploy/krusgraph.sh --update` carries the new
  variables over and lists by name what is still missing. Not tried against a real offer yet.
- Round n170: the chat demo's pictures in the MCP Apps cards (the founder's ask of 8 November 2026,
  `docs/MCP-APPS-PICTURES.md`). With `KRUSGRAPH_MCP_APPS=1`: `plan_backend`, `validate_plan` and `review_plan` draw the
  map of tables and links (key columns, rule and column pair on each link, passed green, failed red with the orphan
  count, not checked grey, rejected dashed); `ontology_draft` and `create_ontology`'s dry run draw the ontology proposal
  with the keyless entity types and why; `domain_draft` (now on the build card) draws the data products, each a card with
  its tables, no owner yet and dry-run buttons for an API for GraphQL and a semantic model over its tables. The drawing
  is cut from `chat-demo.js` when the card is built; the pictures' data is in `structuredContent` only, so the text
  answer is unchanged. "Try in Claude" on the home page and `/start`: copies the first question and opens claude.ai/new
  (claude.ai documents no prefilled chat for the web), with "Open in Claude Desktop", which does
  (`claude://claude.ai/new?q=`), and "connect Krusgraph first" pointing at step 3. Not tried in Claude yet.
- Round n169: the mascots' next steps on the MCP Apps cards are buttons (the founder's ask of 8 November 2026,
  `docs/MCP-APPS-BUTTONS.md`). With `KRUSGRAPH_MCP_APPS=1`, `plan_backend` and the creating tools (`create_semantic_model`,
  `create_ontology`, `create_backend`, `create_report`) get a build card and every card ends with the Thinker's and the
  Builder's buttons, built from the answer's new `actions`: "Check against the rows", "Build a semantic model", "Create
  an ontology", "Create an API for GraphQL", each a dry run under a free name derived from the source (shop_model_2,
  never one the workspace has), then "Create" on the dry run's card only, with the same arguments and `dry_run=false`;
  after a create "Open in Fabric" and, after a semantic model, "Create a report on it". A host without app tool calls
  gets the button's prompt as a chat message (`ui/message`). `plan_backend` without `schema` on a source with several
  schemas asks which (`choose_schema`) instead of planning one. Claude's sign-in: `/start`, `/docs`, the connect
  chooser, `llms.txt` and `/consent/done` give Claude `https://krusgraph.com/mcp/connect` with "Register automatically",
  with one line on why; `/mcp` keeps working for existing connectors. Not tried in Claude yet.
- Round n164: the mascots' names follow their colours differently (the founder's decision of 7-8 November 2026).
  Onto is green (the wide, low figure; maps how the data connects and says the numbers), the Thinker violet (the round
  pear; checks against the rows, finds what does not hold, asks the questions), the Builder coral (the upright egg;
  builds, always after a dry run). Each role stays where it was; `KINDS` in `static/mascots.js` is the one place where a
  name meets its colour and figure, `site.css` has `--onto`, `--thinker` and `--builder` (with `-soft`, `-ink`, `-d`)
  from the palette, and the chat demo's names, the notes on `/demo`, `/mascots`, the MCP Apps cards and the alt texts
  follow. Two placeholders that named a "maker" (no such mascot; they drew Onto) now draw the Builder. The logo is
  unchanged. `docs/MASCOTS-RENAME-LOVABLE.md` has the prompt for the Shop Desk app in Lovable and what to change by hand.
- Round n154: n149 partly undone after the founder's feedback of 8 November 2026. The replay ("A replay of a session in
  Claude") is back in the home page's hero, under the two buttons as before n149 (on a phone directly under them), with
  the small 2 000 → 1 000 card under it; its first round starts with question 1 already sent and answered, and the
  thread starts under the panel's heading, so the panel no longer opens on about 200 px of empty space (same questions,
  answers and note). The chat's "Try a demo" button is back on the home page, now also on /check, and on every page the site
  renders (the blog included); on /check, whose policy still lets the page fetch nothing, the chat reads the same plan
  from the page, and the button steps aside while it would cover the drop area. In the chat, "Fix data issues" and
  "Write dbt tests" (until now "Create a dbt flow", both marked Planned) link the docs of what exists today: the silver
  notebook with its quarantine table (/docs/build-from-a-plan/one-plan-five-fabric-pieces) and dbt_schema's schema.yml
  with tests (/docs/reference/tools); only a whole dbt project is said to be planned. n149's headline, labels, Blog
  link, /check card and /start line stay. `tests/test_n154_replay_and_widget.py` (with tests/n154_browser.js).
- Round n151: create_report's default page reads like a report, after the first live run with visuals on 7 November
  2026 (`shop_report_visuals` on `shop_model`, every figure right; `shop_report_lovable` from Lovable; both recorded in
  docs/LIVE-TEST.md, and create_report's own note no longer says the page was not yet created in Fabric). Plain titles
  from a tested mapping ("Rows in orders" -> "Orders", "Rows in order_items" -> "Order lines" when order_items points at
  orders, a sum of a quantity column -> "Units"; any other measure keeps its name); cards only for business tables (not
  `audit_log`), at most four; a grid that fills 1280 × 720 between even margins, the category chart taking the month
  chart's width when there is none, the table across the page with its columns sized to fill it and a total row; data
  labels; a month and a category slicer when the fields exist; the page title "Overview · <model>", a dated footnote
  "Created by Krusgraph from the checked plan", and a Krusgraph theme in the site's colours (`StaticResources/
  RegisteredResources/Krusgraph.json`, registered in report.json). create_semantic_model formats counts and sums of whole
  numbers as `#,0`, reads (read-only) the first and last date of the related date columns so the calendar spans the
  data's years, and whether a decimal quantity column holds whole numbers only (the shop's `quantity` is DOUBLE), and its
  calendar has `Year Month`. Every PBIR part is validated against Microsoft's schemas, copied from microsoft/json-schemas
  eecc60d into tests/fixtures/pbir_schemas (MIT). Not run live yet. `tests/test_n151_report_look.py`.
- Round n149: the home page and /check lead with the problem (the UX review of 7 November 2026). The home hero asks
  "Why is your total twice what finance says?" and shows the 2 000 → 1 000 before and after as a small card under its
  two buttons; the replay moved down, after the steps. One primary and one secondary way in with the same labels
  everywhere: "Check my tables" (/check) and "Connect to my Fabric" (/start), in the hero, the middle section, the
  closing card, after a /check result, on /pricing, in the navigation and the footer. The client chooser (Claude,
  Lovable, VS Code, Cursor) moved from the hero's "Connect ▾" to step 3 of /start ("Choose your client"); /start opens
  with "Coming from /check?" and a jump to that step, the requirements folded under it. No floating "Try a demo" on the
  home page (nor /check, as before); one "Try the guided demo" button, after the total that doubles. The test status is
  said once, by the tools list. /check: a card after a result leads to /start and says what it needs (a Microsoft work
  account; an admin approves once, linking /it); the footer's "Run it locally" is a text link and its demo button is
  gone; at 375 px the drop area and the privacy line come before the example cards. Blog is in the main navigation; the
  article on the total that doubles is linked from the home page's example and /check's example cards (there is no
  /join-validation page). The data line on the home page and /pricing is n146's. `tests/test_n149_lead_with_problem.py`.

- Round n146: one source for permissions, data flow and test status, after the outside review of 7 November 2026.
  `fabric_backend/access.py` holds the app's delegated permissions (equal to the deploy check's `REQUIRED_SCOPES`, read
  7 November 2026), what each tool uses them for and whether anything runs or is scheduled, the tokens kept per client
  with their lifetimes from the code, and the two data flows (hosted, self-hosted); /start, /it, /privacy, llms.txt and
  docs/SCOPES.md render from it. create_semantic_model, create_ontology, create_data_agent and compare_semantic_model are
  no longer "available when enabled by the operator": the app has had Item.ReadWrite.All since 28 October 2026. Each
  tool now has separate fields (status word, where available, last operation tried live, date, result, still open);
  "Experimental" is kept for tools never tried live, and tools with a dated live run after 27 October 2026 (or a partial
  one that day) are "Tried live", create_pipeline among them. Planning is described with R5's bounded counting queries,
  the checks with what stays unchecked, the analytics line as "no third-party analytics", /start's step anchors work,
  /local separates what was tried on SQL Server 2022 from what was not, and Claude Code gets one connect instruction.
  Text only: no behaviour, scope or storage changed. `tests/test_n146_one_source.py` fails when two pages state
  different permission lists, status words or Claude Code advice; the texts in page_templates/DOCS.md and README.md that
  still contradict it (held by another round) are strict xfails there.
- Round n146, second part (after n145 released README.md, DOCS.md and LIVE-TEST.md): DOCS.md's "What it accesses" shows
  the generated permission table, the planning and checking sentences and the two data flows; "For agents" and "Other MCP
  clients" give Claude Code `{{CLAUDE_CODE_CONNECT}}`; the status definitions add "Tried live" and say no tool needs an
  operator-enabled permission; README's permission list and "not granted" lines follow access.py, and it records the
  pipeline run of 7 November 2026 (also filled in docs/LIVE-TEST.md). The promise line is now "every proposal shows its
  basis, and the checks you run show their results" on the home page, /docs, llms.txt and the README. By Gustav's
  decision of 7 November 2026, `amount_levels`, `plan_sql_server` and the local server's plan_backend, validate_plan,
  data_dictionary, dbt_schema and answer_query_draft are "Tried live" (SQL Server 2022 in a container, 28 Oct 2026;
  not run from Windows/Claude Desktop yet); the other local tools stay Experimental. The consistency test has no xfails.
- Round n143: lineage with runs=<pipeline or notebook> reads the item's latest runs (Fabric's job-instance list), each
  Notebook activity's status (its notebook's own run in the pipeline run's time window, a heuristic), the error text as
  Fabric returns it, and a category with a next step from a catalog of Spark/Fabric errors (import, table not found,
  permission, capacity paused or throttled, timeout), marked as a heuristic. Only GETs and getDefinition; Item.Read.All,
  which the hosted app has. Unit-tested only (docs/RUN-RESULTS.md). The catalog's layout follows FreelexHo/power-bi-mcp
  8d2e873 (MIT). create_pipeline's status now says pipeline_shop ran live on 7 November 2026 (run 9de8bc49, all three
  steps succeeded).
- Round n140: create_pipeline's check notebook is self-contained. Seen live on 7 November 2026: pipeline_shop's
  silver_shop and gold_shop succeeded, pipeline_shop_check failed with "ImportError: cannot import name 'pipeline' from
  'fabric_backend'", because its %pip installed the published release, which is older than main and has no pipeline
  module. The check (keys unique and never NULL, orphans, gold rows and sums against the silver fact table) is now plain
  PySpark and Python in the notebook (`pipeline.CHECK_CODE`), with no %pip and no import of the library; it still raises
  on a failed check, so the pipeline run fails, and prints a summary when the check holds. The check activity no
  longer sets _inlineInstallationEnabled. The drift monitor's notebook still installs the library (docs/LIVE-TEST.md).
- Round n139: dbt_schema project=true writes valid staging SQL. Seen live on 7 November 2026 on the shop schema: a
  column the draft keeps as the source has it (varchar without a length in the endpoint's metadata) carried a trailing
  comment, and the separating comma came after it, inside the comment, so the next select item followed without one
  (stg_shop__addresses, audit_log, categories, customers, products). `dbt._select_list` now writes the comma before
  the comment, and comment text is kept on one line. Only the staging models of the dbt project draft had the problem;
  the marts, the T-SQL views, gold views, join paths, evidence queries, data agent examples, answer drafts and fixes put
  their comments on lines of their own. `tests/test_n139_sql_parses.py` parses every SQL file and SQL draft for the shop
  schema (as the seed and as a SQL endpoint reports it), n138's synthetic 15-table fixture and every schema fixture
  (4 to 71 tables) with sqlglot's T-SQL parser (gold's Spark SQL with its spark dialect), 1 968 pieces, so a dropped
  comma or bracket fails CI.
- Round n138: MCP Apps card polish after the first live run (Claude desktop app, 6 November 2026, demo_lh/shop), still
  only with `KRUSGRAPH_MCP_APPS=1`. review_plan's ER diagram drew orders.customer_id → customers through the audit_log
  box and put labels on top of each other; it is now a layered layout (`mcp_apps_review.LAYOUT_JS`, inline SVG, no
  loads): referenced tables above the tables that refer to them, edges at right angles through the gaps between tables
  and rows, each label on its own edge on a track of its own. validate_plan's card with nothing to attend to says
  "Nothing needs attention." under Needs attention and the result sentence once, in the summary line. The buttons
  ("Run <tool>", "Record decision") send the specification's `tools/call` request only to a host whose
  `ui/initialize` answer has `hostCapabilities.serverTools`; a host without it, a JSON-RPC error, a result with
  `isError` and a host that does not answer within 20 s each give a sentence on the card (`mcp_apps.CALL_JS`). What a
  button's tool answers is no longer one large JSON block (seen live with semantic_model_draft and ontology_draft): a
  short summary read from names and counts only, never a row value (`mcp_apps.RESULT_JS`): semantic_model_draft its
  tables by role, relationships, measures and notes; ontology_draft its entity types with their keys, relationship
  types, and its notes as questions to the user; any other tool its `summary`; the whole answer behind a collapsed
  "Show details". The same on the review card for an answer without a review file. Tool
  count and listing cap unchanged. `tests/test_n138_card_polish.py` (Chromium) checks the diagram geometrically for
  the shop and a synthetic 15-table fixture, wide and light and narrow and dark, plus the empty-attention line and the
  request shape in each host mode, and the summaries with the live shapes of both draft answers.
- Round n137: the MCP Apps cards read the tool result. Seen live in Claude on the web and in the Claude desktop app on
  6 November 2026: validate_plan's card listed the whole answer as one JSON string under "Needs attention" (no
  mascots, no next-step buttons) and review_plan's card said it held no review file. Cause: the tools return `str`, so
  the SDK derives the output schema `{"result": string}` and sends `structuredContent: {"result": "<JSON text>"}`; the
  cards parsed only the text content and listed the wrapper's `result` as an attention line. Both cards now read the
  result in every form a host may deliver (`mcp_apps.READ_JS`): `structuredContent` when it holds the answer, else the
  text content as JSON, unwrapping `{"result": "<JSON text>"}` in either place; what cannot be read gives one short
  sentence, never a JSON dump, and a mascot never says a JSON text. validate_plan's card shows an all-passed answer's
  `result` sentence under the counts instead of under "Needs attention". With `KRUSGRAPH_MCP_APPS=1`, validate_plan and
  review_plan also return the answer as `structuredContent` (text content unchanged) and are listed without the derived
  output schema; with the flag off nothing changes. Tool count unchanged. Browser tests
  (`tests/test_n137_card_reads_result.py`, Chromium) feed both cards each payload shape with the live shop answers.
- Round n136: the site's mascots on both MCP Apps cards (`fabric_backend/mcp_apps_mascots.py`), still only with
  `KRUSGRAPH_MCP_APPS=1`. Onto says the counts (the answer's `summary`), the Thinker the first thing that needs
  attention, the Builder the next step (validate_plan's first next step; review_plan's `note`, now also shown under
  "Next steps"). Each sentence is a string of the text answer and is also on the card; a figure with nothing to say is
  not shown. Glad (celebrate, heart) only when every check passed and nothing needs attention; never on a failed or
  stale check, an error or a cancelled call. A visible "Mascots: on/off" button on each card hides them; no storage.
  The figures are inline SVG built from the shapes in `static/mascots.js` inside the package (flat colours, no `url()`
  references, no animation); nothing outside `fabric_backend/` is read. Text answers, tool count and listing size are
  unchanged. Unit and browser tests (`tests/test_n136_card_mascots.py`, Chromium at 340 and 480 px, light and dark,
  under the specification's default CSP); not yet tried in a real MCP Apps host.
- Round n126: column-level usage in semantic models (LANDSCAPE idea 5, `fabric_backend/dax_refs.py`). A small DAX
  reference scanner reads the measures and calculated columns of a model's TMDL: `Table[Column]`, `[Measure]`, quoted
  names and measures over measures, followed to the end with the path; strings and comments are skipped. A name it
  cannot settle (several candidates, unknown, SELECTEDMEASURE and other dynamic references, unsupported syntax) is
  listed as could not be read, never guessed, and so is every expression that depends on one. `plan_drift` adds
  `column_usage` when a removed column or lost table reaches a semantic model (the model's definition is read again);
  `compare_semantic_model` adds it for each model column whose source column is gone. No new tool; still the same
  count. Calculation groups, calculated tables, format string expressions, roles, sortByColumn and hierarchies are
  not read. Unit-tested on a TMDL fixture over the shop schema and on the shop model draft; not run against a model
  in Fabric.
- Round n122: `dbt_schema` takes `quality` (`"gx"`, `"soda"` or `"both"`) and writes the plan's key and relationship
  checks as a Great Expectations suite per table and as SodaCL checks, each with its rule and counts, as drafts.
  `profile=true` adds a dbt-fabric `profiles.yml` beside the n114 project, with placeholders and no secret. No new tool.
  Unit-tested; not run against GX, Soda or a Warehouse, not deployed.
- Round n125: `lineage` takes `format="openlineage"` and then returns its graph as OpenLineage run events instead of
  its own graph (the default, `format="graph"`, is unchanged). Tables become datasets with their column names and types,
  each object Krusgraph found or created becomes a job, and a Krusgraph facet carries the edges and each checked
  relationship's rule and counts. No row values. Tested against the OpenLineage 2-0-2 schema in unit tests; not deployed.
- Round n124: a second MCP Apps card, for `review_plan`: its answer drawn as an ER diagram (tables, keys, relationships
  with their rule and counts, failed or stale checks and open items highlighted), with one button per undecided item
  that asks the client to call `review_plan` with that decision. Off unless the operator sets `KRUSGRAPH_MCP_APPS=1`;
  the text answer is the same either way. Unit-tested and checked in Chromium; not deployed.
- Round n123: two server-wide operator settings, both off by default. `KRUSGRAPH_READ_ONLY=1` leaves out every tool
  that creates or changes something in Fabric. `KRUSGRAPH_NO_ROW_VALUES=1` leaves out `sample_rows` and takes row values
  out of the other answers, keeping names and counts. `/healthz` gains a `mode` field, and the server's instructions,
  `/llms.txt` and the Hosting and permissions section of `/docs` name the two settings. With both off the tools are as
  before. Unit-tested on the hosted and the local server; not deployed.
- Round n121: `docs/SEGMENTATION.md`, an internal note with candidate customer segments, where each would run, what
  exists and what is missing. Prices, customers and demand are unknown and the note says so. No change to the service.
- Round n119: the first MCP Apps card: `validate_plan`'s summary as a card in clients that show MCP Apps (counts per kind
  of check, what needs attention, next steps as buttons for read and draft tools only). Off unless the operator sets
  `KRUSGRAPH_MCP_APPS=1`; the text answer and the tool count are the same either way. Unit-tested and checked in
  Chromium; not deployed.
- Round n118: `docs/LANDSCAPE.md`, an internal scan of 33 MCP servers and frameworks near Krusgraph, with licences as
  read from their LICENSE files and five ranked ideas (idea 3 became round n123). No change to the service.
- Round n117: a new page in the docs' Concepts group, Where it runs (`/docs/concepts/where-it-runs`): what can be
  checked, drafted, created and reviewed in the browser, on your own computer, in your own Azure tenant and on the
  hosted service, each cell read from the code. Unit-tested; not deployed.
- Round n113: `docs/COMPARISON-MYRIADE.md`, an internal note on how Myriade infers relationships beside Krusgraph on
  the shop data, from public sources only. No change to the service.
- Round n86b: a Concepts group in `/docs` with pages on how it works, ontologies, data products, how they connect and
  the vision (`/docs/concepts/...`), with examples rendered from the engine on the shop schema, three architecture
  diagrams (layers, sign-in and request flow, plan to Fabric items) and a small explanation that opens next to
  "ontology" and "data products" in the chat demo and on `/check`. Every old docs anchor still leads to the same text.
  Unit-tested; not deployed.

## 0.8.0 — 2026-10-28

- Round n120: `create_pipeline` creates the pipeline of the n110 draft (a new tool; 39). It creates or updates in place
  the silver and gold notebooks the existing tools create, the check notebook, and a data pipeline that runs them in
  that order, each step only after the one before succeeded, so a failed check fails the run. `dry_run=true` (the
  default) makes no write call and returns the definitions and the REST calls; `dry_run=false` sends the same
  definitions with the notebook ids in place of their placeholders. It never runs or schedules the pipeline and says
  so. It uses the notebook and data pipeline create/updateDefinition calls the code already makes and needs
  `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` (or `Item.ReadWrite.All`), which the hosted app has.
  Unit-tested with a test double for Fabric's REST API; not created or run in Fabric, not deployed.
- Round n116: a OneLake catalog draft (`fabric_backend/catalog.py`). `export_item_definitions(items=["catalog"])` lists
  each Fabric item the plan touches with the description and tags it would get, and the exact REST calls for them. The
  items are the source lakehouse or warehouse and the API, model, notebooks and pipelines the creating tools would
  make. The calls are `PATCH /v1/workspaces/{id}/items/{id}` (Update Item, description at most 256 characters) and
  `POST .../items/{id}/applyTags`, which takes tag ids that `GET /v1/tags` finds. Tags that do not exist yet need
  `POST /v1/admin/tags/bulkCreateTags`, which only a Fabric administrator can call. A description holds table and
  entity names, roles, key and relationship rules, validate_plan's counts with `check_rows=true`, and the proposed
  domains. It never holds a column name or a row value. The tags are "Krusgraph" plus one per proposed domain.
  `catalog` alone answers without files; with other items the files stay. Nothing is set on lakehouse tables, T-SQL
  views, the SQL analytics endpoint or endorsement, because no public operation covers them. Sources:
  fabric-rest-api-specs 6f817cb, fabric-docs 28d4ff3 and microsoft/mcp 42c66a2, all read on 6 Nov 2026. No tool sends
  the calls; still 38 tools. Writing would also need `Tag.Read.All`. Unit-tested on the shop; not sent to Fabric.
- Round n115: a fix suggestion for each of validate_plan's findings (`fabric_backend/fixes.py`), as drafts. Each row of
  the evidence report's checklist carries `fix`, and the report has a "Fix suggestions" section. A fix is a mechanical
  step with a stated rule: rows with a NULL key and exact copies go to quarantine, one row per key stays, and an amount
  a flat table repeats on every row of a header value moves to `<table>_per_<header>` in silver. A choice is two such
  steps with none chosen: an orphan row goes to quarantine, or stays with its reference set to NULL. A question is a
  business decision with no default: which of two differing rows with one key wins, whether an orphan's target exists
  elsewhere, which table an amount belongs to. Counts before and after come from the check's own counts and its query.
  `silver.apply_fixes` puts the steps into the silver notebook draft: the decisions are None in its parameters cell,
  and the run stops before writing anything while one the data needs is None. Only the silver tables and
  `krusgraph_quarantine` are written, never a source table, and nothing here runs. n106's flat-table amounts are a
  checklist finding of their own. No tool added (38). Unit-tested on the synthetic shop and flat-table rows, and the
  draft ran on a local PySpark 4.0.1 with the counts it states; not run in Fabric, not deployed.
- Round n114: `dbt_schema` writes a whole dbt project draft with `project=true` (no new tool; still 38). The files are
  dbt_project.yml, the sources file with its tests from the plan's keys and relationships, one staging view per table
  (cast to Fabric Data Warehouse types where the metadata says enough, de-duplicated on the key) and marts in one folder
  per proposed domain. The marts join only over relationships whose target key `check_rows=true` counted unique, and
  child tables are summed to the fact's key before the join, so a header amount is never summed over its lines.
  Written for dbt-fabric 1.12.0 on dbt-core 1.12, T-SQL without CTEs. Untemplated parts (a table without a key, a type
  without an equivalent) and the customer's TODOs (business rules, which duplicate to keep) are listed. It creates and
  runs nothing. `dbt parse` passed on the shop project with dbt-core 1.12.6 and dbt-fabric 1.12.0 on 6 November 2026;
  not run against a Warehouse. Unit-tested; not deployed.
- Round n111: `create_backend` has a dry run, `dry_run` with the default of the other creating tools (`true`), in the
  hosted and the local server. It answers whether an item of that name exists and would be updated or created, the
  definition and what changes in it, and the checks that passed, reading only. A call that should create or update
  now passes `dry_run=false`; what a real create writes is unchanged. `tool_status.NO_DRY_RUN` is empty and the texts
  that said create_backend has no dry run say otherwise. Unit-tested with the Fabric test double; not deployed.
- Round n90: Claude's connectors page moved to Customize. The Connect button opens
  `https://claude.ai/customize/connectors` instead of `https://claude.ai/settings/connectors`, which now only says that
  Connectors moved; the instructions say Customize → Connectors → Add → Add custom connector, and for a new sign-in
  Customize → Connectors → Yours → Reconnect. Tried in Claude on the web on 2 November 2026; instructions for other
  clients unchanged. Unit-tested; not deployed.
- Round n89: `amount_levels` writes a factor only when it is true. The counting query also returns `min_lines`; where
  every referenced header has the same number of lines (`min_lines` = `max_lines` > 1) the sum "comes out n times too
  large", exactly; otherwise no factor, because the average number of lines is not the ratio of the sums (the SAP
  example said "about 1.5 times" beside 1 950 against 750). `/check` shows the ratio from the two counted sums;
  `validate_plan` still sums nothing. Unit-tested on synthetic data; not deployed.
- Round n88: a negation such as "customers who have not placed any orders" or "haven't placed an order" gives an
  anti-join (NOT EXISTS), and a "not", "n't", "never", "inte", "ej" or "aldrig" no marker ties to a table gives no query
  and says so; `amount_levels` says no row is repeated today where every header has one line; lineage's note names
  the live run of 2 November 2026; `/privacy` says that the tools that build on the plan run rule R5's counting queries
  (at most 20 per call, only counts, nothing kept between calls); `docs/LIVE-TEST.md` rows 4, 6 and 25 expect 7
  relationships, with the results of 2 November 2026 after round n87. Unit-tested on synthetic data; not deployed.
- Round n87: the ten findings of the live review of 2 November 2026 (negation, R5 in every plan-based tool, the
  counting query SQL Server refused, per X, value columns, silent replacements, personal data, contradicting notes,
  small errors, the operation result in lineage). Unit-tested on synthetic data and fake answers.
- Round n85: the evidence report downloaded on `/check` carries the decisions taken on the page (the guided demo's
  Accept and Reject): what, the decision, the browser's time and "by: not recorded", the latest choice when it changes,
  as of each download. They stay in the browser (nothing is sent or saved) and a new run starts without them. An
  accepted relationship is "accepted, not checked in the rows": it is not added to the relationships or the checks.
  Without a decision the report is the same as before. The four example buttons' descriptions fit on two lines at
  375 px, 1000 px (where the four sit in one row) and 1280 px; "Subscription billing" reads "Younium + Salesforce
  invoices". Browser tests in `tests/test_check_decisions.py`. `docs/LIVE-TEST.md` records the run of 2 November 2026
  (build `src-69aa8afa445e6c97`): `validate_plan`, `lineage`, and `create_ontology` creating and updating
  `shop_ontology_n81`, round n81's path against real Fabric without throttling; `Retry-After` and 429 tried only
  against fake answers.
- Round n84 (Deployment): the Dependabot PRs of November merged one at a time on green CI, `main` checked after each:
  actions/checkout v5 → v7 (its breaking change, no checkout of a fork's PR under `pull_request_target` or
  `workflow_run`, does not apply to these workflows), and opentelemetry-api 1.45.2, pydantic 2.14.2 and pydantic-core
  2.50.2 in `deploy/constraints.txt` (the image), with `THIRD_PARTY_NOTICES.md` regenerated (#16; #15, the same three
  pins from the `/deploy` entry of `dependabot.yml`, closed as a duplicate). A new CI job, `notices`,
  runs `tools/third_party_notices.py --check --from-installed`: a stale `THIRD_PARTY_NOTICES.md` or an AGPL/SSPL
  dependency, now in the extras too, stops the build; `--from-installed` names a package's home page the way PyPI does,
  so both modes write the same file.
- Round n83: a 60-second overlap window on the refresh-token rotation at `/mcp/connect` (`Layer._refresh`, the
  proposal of `docs/REFRESH-ROTATION.md`): the refresh token just replaced, from the same client id, gets the same
  answer again (no Entra call, no new rotation, `refresh_replayed` in the log), so a client's retry after a lost answer
  no longer signs the user out; after the window, reuse ends the line as before. An ETag conflict, and a final Entra
  refusal on a line another request has just renewed, answer with that request's answer instead of signing out or
  deleting the line. The answer is kept encrypted in the line (with the server's key and a key derived from the
  replaced token) and never opened after the window. The consequence, said in /privacy, `docs/CLIENT-REGISTRATION.md`,
  `docs/TRUST.md`, `docs/RISK-REGISTER.md` (R9) and `docs/REFRESH-ROTATION.md`: a stolen old refresh token used within
  60 seconds is not detected, and an encrypted access token now sits in the row after every refresh. Claude's path
  through `/mcp` is unchanged. Tested against a mocked Entra and store only; not deployed.
- Round n82: by Gustav's decision of 2 November 2026 VS Code and Cursor (verified by him) and Lovable (its flow ran live
  on 30 October 2026, `docs/LOVABLE-END-TO-END.md`) are **Tested end to end** in `tool_status.CLIENTS`, with the date in
  their notes; the Connect menu, the hub, /docs, /start, /lovable and the llms files follow, and "Experimental:" is gone
  from the three menu items. Claude Code and Glama are unchanged. Gustav opened an RDF/XML file from `/check` in
  Microsoft's Ontology Playground the same day, with a good result (`docs/LIVE-TEST.md`; one sentence at the download);
  the file stays Draft. `docs/REFRESH-ROTATION.md` with `tests/test_refresh_rotation.py`: an investigation of Glama's
  sign-out (a refresh token sent twice ends the whole line; what a deployment does to the lines and the key; the causes
  ranked; an overlap window proposed, not implemented). `tests/test_pack_label.py` freezes the evidence report's clock.
- Round n80: a simpler Connect menu (Claude first and open with one large button, Copy URL and a first question to copy
  that only reads; Lovable under it; VS Code and Cursor folded under *Other clients*; the admin line last with a note to
  copy for the admin: the consent link, what is approved, `/it`). No address is printed; each copy button holds its
  client's. `/consent/done` gives one next step, Connect and the question. At `/mcp/connect`, a sign-in Entra stops for
  want of admin consent shows a page that says so, with the same note, instead of an unexplained error in the client.
  Gustav verified on 2 November 2026 that the *Add to VS Code* and *Add to Cursor* buttons work in their clients
  (`tool_status.CLIENTS`, `docs/LIVE-TEST.md`). `/check` says "app starter for Lovable" without the word Supabase (the
  zip is unchanged). `ontology.ontology_rdfxml`: the plan as RDF/XML for Microsoft's Ontology Playground, which reads
  RDF/XML and not Turtle, written after its RDF/XML subset at commit 7bf7acb (MIT), with its validation rules ported to
  `tests/playground_rdf.py` and one official catalogue file as a fixture; a Draft download on `/check`, opened in the
  Playground with a file import; no new MCP tool. Not tried in the Playground app itself.
- Round n79: the pack's own name where a person reads the rule (Subscription billing on `/check`, the data dictionary,
  the Power BI README, the contracts, the Rayfin comments say *Younium + Salesforce pack*; the `rule` fields of the
  answers keep `SAP pack`, and the SAP texts are unchanged). Masking goes through the pack the engine reads, so the
  Younium + Salesforce pack's personal columns (Contact's and the accounts' names, e-mail and telephone numbers) are
  masked like SAP's; the account names were added to the pack. The evidence report
  (`fabric_backend/evidence_report.py`), a pilot's hand-over as JSON and Markdown from the plan and validate_plan's
  counts, with "not checked" for whatever was not counted and no row values: a Draft download on `/check` and
  `evidence-report.md`/`.json` from `fabric-backend demo`; no new MCP tool.
- Round n78: the engine reads the Younium + Salesforce pack. `infer._pack` calls `sap_pack.match_any`, so a schema the
  pack recognises gets its keys and applied relationships with the rule `SAP pack` (one rule for every pack) and the
  pack's name and source on each note, and `plan.pack` carries its tables, amounts and traps. The pack's ordinary table
  names (accounts, invoices, Contact and the like) are marked `common_name`, and a pack is taken only when one table it
  recognises has a name of the system's own, so the shop, SAP, crm and traps plans are the ones before (tested against
  the SAP-only engine). The benchmark's younium row: recall from 0/18 to 15/18 at precision 15/15, orphans 1/1 and
  doubled totals 2/2; the other rows unchanged. `/check` has a fourth example, *Subscription billing* (Younium +
  Salesforce, synthetic data). The pack is still written from sources that could not be opened, and the demo rows from
  the pack.
- Round n77: one manifest per knowledge pack, `fabric_backend/packs/<pack>/manifest.yaml` (`sap`, `younium_salesforce`), in one
  shape for every pack and checked by `packs/manifest.schema.json`: id, version, title, source systems, scope, sharing
  (public-synthetic), sources with `accessed` and `verified` (false wherever the pack's files say the page was not read),
  entities with their key candidates and sources, candidate relationships with the rule, the sources and which of
  `validate_plan`'s checks can confirm them (referential integrity, cardinality, amount level), traps with the check that
  shows them, the fixture module and the benchmark facit, and `review_status` with `reviewed_by`/`reviewed_at` empty until
  the maintainer has reviewed it. The loader `fabric_backend/pack_manifest.py` derives the four claim sections from the
  module files and `tests/test_pack_manifest.py` checks that every rule in the files has a row in the manifest and the
  other way round, that the fixtures build and the pack recognises every fixture table, and that the facit of
  `examples/benchmark` and the manifest's candidate relationships agree (the three links by number of the younium set
  are candidates listed as not applied). `sap_pack_draft` answers with a `pack_manifest` field (id, version, review
  status), read without a YAML library; nothing else in a tool's answer changes. `docs/PACKS.md` describes the format,
  how a pack is added (public sources, synthetic fixtures, never customer data), the review step, and what a pack is
  beside a connector and a finished analysis. The benchmark table is unchanged.
- Round n75: the sales path's last P1 items and the coverage lines. The home page offers two paths after the demo card:
  "Try it yourself" (`/check` and the Connect chooser) and "Get help with one number" (`/partners`), one sentence each and
  no new promise. `/partners` separates the first assessment (you describe one question, one data area and what the
  number is compared with; the answer is one of five words: ready to start, a business question must be decided, material
  missing, access missing, not supported) from the pilot ("Bring one number your team cannot agree on": the plan, the
  checks, the explanation of the number, a reviewed model, the contract and the hand-over; accepted when the number is
  explained with evidence, every relationship has a rule or a decision and the model opens in Power BI Desktop and
  refreshes in Fabric; the customer's part is one data owner with read access; "Quoted after a 30-minute scoping call;
  invoiced.", no amounts), and shows an illustrative delivery on synthetic data whose figures are the engine's own run
  of `seed.AMOUNT_DEMO` (`amounts.demo`), not typed into the page; `/pricing` carries the same price sentence. Coverage:
  every finding card on `/check` says how much of the rows its check read, from the result itself ("Checked on all 60
  rows of orders: 60 with a value", "Counted on all rows of products and order_items: …", "Not counted: a list of columns
  has no rows"), a line under the state says whether every key and relationship of the plan was counted, and the docs'
  `plan_backend` and `validate_plan` sentences carry R5's sample and query budget and `validate_plan`'s default
  `max_items` read from `server.py`. The Fabric IQ FAQ n73 put on `/docs` was checked and left as it is.
- Round n76: trust, risk and licences, as documents. `docs/RISK-REGISTER.md` (internal): eight risk hypotheses with
  cause, event, consequence, area, the existing controls with their file or function in the repository, action, owner
  and next review; probability and impact "not assessed" wherever the repository holds nothing to carry a value; product
  risks apart from business obstacles. `docs/TRUST.md`: the material for a public /trust page, every statement with its
  source in the repository and Microsoft's attestations marked as Microsoft's; the line "Krusgraph is not ISO 27001 or
  SOC 2 certified; here is what we do instead"; the subprocessor list (Microsoft Azure; the AI client is the customer's
  own vendor). `docs/ISO27001-SELF-ASSESSMENT.md`: the 93 Annex A controls, each in place, partly, missing or not
  applicable with its file, and no score. `docs/DPA-DRAFT.md`: a data processing agreement template as a draft, not legal
  advice. `THIRD_PARTY_NOTICES.md` generated from `deploy/constraints.txt` and the extras by `tools/third_party_notices.py`
  (`--check` for CI; the workflow step is left for the Deployment area), with the vendored Pyodide and fonts and the
  image's components; a "Reusing external code" section in `CONTRIBUTING.md` (verified licence file at a pinned commit,
  notices kept, no AGPL or SSPL, nothing from a repository whose licence cannot be verified). `docs/ECOSYSTEM-WATCHLIST.md`:
  the related MCP servers (Microsoft's Fabric MCP Server, Fabric IQ MCP, the Power BI modeling server, the warehouse
  and Real-Time Intelligence servers; datumnova/ms-fabric-mcp and Jasuni69/ms-core-mcp with no licence file found,
  mkoziel2000/mcp-fabric-api under the AGPL) with licence as observed or not verified, what is worth referring to, what
  is not copied, and the date. `docs/COMPANION-MCP.md`: Krusgraph beside Microsoft's servers in the same client, a
  complement with no server-to-server connection, cited from fabric-docs because Learn could not be opened.
- Round n73: the polish from the external review, on the site. `/check` shows the finding first: after a run the state
  line ("Enough to start · 4 things to check"), the most important finding and the folded list come right under the
  status line and before the map, and the engine's steps are a closed `<details>` under the map ("How the engine got
  here"), in the three examples and for the visitor's own files; a browser test reads the finding at 1280 px without
  scrolling. One order runs through "A total that doubles": the engine reads one header row per amount finding from the
  rows (its key, its amount, how many line rows point at it, what a join counts it as: `order_id 1`, 1 000, twice,
  2 000) and the finding's text, Onto's "Why does this total come out twice?", the Power BI preview and the domain's
  ODCS contract (a top-level `customProperties` entry, `amountLevel.<table>.<column>`) all repeat that row; the preview no
  longer shows a second total of its own. Every download button on `/check` says what the file holds and its status
  word from `tool_status` (the Power BI project, the app starter, the contract). `/lovable` is rewritten after the path
  that ran on 30 October 2026: Krusgraph as a custom MCP connector in Lovable at `/mcp/connect` (plan, check, create),
  the three portal steps (an app registration with a secret, Contributor on the workspace, introspection on the item:
  the one with no API), then Lovable's Microsoft Fabric connector; its status words come from Lovable's two rows in
  `tool_status.CLIENTS`. "Connect to Claude" is "Connect" everywhere (the footer, the session links, the closing card,
  `/check`'s answer, `/use-cases`, the consent pages), pointing at the n68 chooser (`/#connect`, which opens it and
  focuses its button); `/start` is "the set-up guide". Docs: the admin consent link on `/docs` carries
  `redirect_uri=https://krusgraph.com/consent/done` like `/start`, and the Fabric IQ section answers "Why not just Fabric
  IQ / the Fabric ontology?" with what Microsoft Learn says about filling an ontology item (by hand, from a semantic
  model, with the ontology agent; links to Learn) and the one angle of `docs/FAQ-COMPETITION.md`: Krusgraph creates the
  ontology item; the evidence step comes before it. `domains.draft` and `domains.contract` take an optional `extra`
  (more top-level custom properties) for `/check`. `docs/SCOPES.md` was not touched: Docs and submission is n72's.
- Round n72: a second knowledge pack, `younium_salesforce` (`fabric_backend/packs/younium_salesforce/`, modules `younium` and
  `salesforce`): Younium's API v2 objects (accounts, products with charge plans and charges, subscriptions with versions
  and charges, sales orders, invoices with lines, payments) beside the Salesforce standard objects the Younium connector
  meets (Account, Contact, Opportunity, OpportunityLineItem, Product2, PricebookEntry, Order, OrderItem, Contract), 20
  tables, 33 relationships (the Younium account to its Salesforce Account through External CRM Id; the links an invoice
  line carries by number are listed, not applied) and 13 traps (versions, amounts on lines, MRR/ARR as measures, one
  currency per account, usage charges, 15- against 18-character Salesforce ids, one customer as two account rows).
  Every source is marked unverified with the date: developer.younium.com, support.younium.com and
  developer.salesforce.com could not be opened from the session that wrote it (`docs/YOUNIUM-SALESFORCE.md` has the
  list and the questions for someone who runs the integration). The loader reads a system prefix (`younium_`, `sf_`,
  `salesforce_`, `crm_`) past like `sap_`, compares columns without case or underscores (`externalCrmId` and
  `external_crm_id` alike), and gains `match_any` (the pack that recognises most of a schema) and `plan_with` (a plan with
  a pack's keys and relationships as the caller's); the engine still calls `match` for the SAP pack alone, so the new
  pack is not applied by `plan_backend` or `/check` yet. The pack schema gets an optional `area` per table, which the
  domain proposal uses for a domain's name (billing, customers and sales), an optional Swedish name, and the level
  `version`. A synthetic demo, `fabric_backend/younium_demo.py` (14 tables, 58 rows, no real party), with a planted
  15-character id and an invoice total over three lines; the benchmark gains it as a fifth set, the four rows from
  before unchanged.
- Round n71: the amount that is not there. A line table with a quantity (`order_items.quantity`) and no amount of its own,
  pointing at a table that carries the price (`products.list_price`), gets the measure `Order amount` =
  `SUMX('order_items', 'order_items'[quantity] * RELATED('products'[list_price]))` in `semantic_model_draft` and
  `create_semantic_model`, with a note on where the price comes from (a list price as it stands at query time, not
  necessarily the price paid); the price column is not summed on its own (`summarizeBy: none`), and `data_dictionary`
  and the ODCS contracts name the measure (`customProperties`). Names: quantity/qty/menge/antal and
  price/list_price/unit_price/netpr (`fabric_backend/amounts.py`). A line that carries an amount (`net_amount`, SAP's
  `VBAP.NETWR`) keeps it and gets no product; a price per unit no longer counts as a measure when a table's role is
  decided, so a products table with a list price stays a dimension. The synthetic shop's products have a `list_price`
  (the live shop's model had shown only a total quantity). The hosted `plan_backend` runs rule R5 over its open
  connection, bounded: the first 200 distinct values of a candidate column, one counting query per candidate target,
  at most 20 per call (on 30 October 2026 it had not found `orders.ship_to_id → addresses`, because R5 needed rows only
  `validate_plan` read); the answer gains `counted_in_rows` and, for candidates it could not confirm or count,
  `proposed` with the reason and the next step. Name, title and annotations of the tool are unchanged; the other tools
  plan by names as before. The benchmark table is unchanged.
- Round n69: the status words after the live runs of 30 October 2026, text only (no tool's name, title, annotations
  or behaviour changed). `create_report` is "Experimental; created live on 30 October 2026 (shop_report_live,
  shop_report), opened and reviewed in the Fabric portal by Gustav the same day" and, next to the offer, "created live;
  reviewed in Fabric" (`LATER_LIVE`, `REVIEWED`). `create_backend`'s long form adds that `shop_api` was updated in
  place again from Lovable and is consumed live by a Lovable app on 30 October 2026; `create_semantic_model`'s that
  `shop_model` was updated in place from Lovable the same day. Lovable has a second row in `tool_status.CLIENTS`: via
  MCP (/mcp/connect), Experimental, signed in with Entra through Krusgraph's OAuth (dynamic client registration) and ran
  plan, check and creates on 30 October 2026; the /mcp/connect sentence names it with its date. The server's test
  status sentence names the tools that have created items live since the run of 27 October instead of saying creating is
  unit-tested only, and `semantic_model_draft`'s note no longer says the item is not yet created live. Docs: a 30 October
  section in docs/LIVE-TEST.md (and a `create_report` row and a Lovable client row), `create_report` in docs/SCOPES.md,
  the README's tool list and status, deploy/SUBMISSION.md row 5, and step 1 of docs/LOVABLE-END-TO-END.md no longer
  blocks. The Fabric REST API was not called in this round.
- Round n67: the TMDL writer never writes a document that holds only comments. On 30 October 2026 Power BI
  Desktop 2.151 opened the shop project from /check but refused the SAP one with "InvalidLineType ... Document:
  ./relationships, line 1": with no expressible relationship, `relationships.tmdl` had been one comment line. The file
  is now left out when there is nothing to put in it, the rule (`has_object`) is applied to every part of the draft, and
  `README.generated.md` says why. Composite keys (SAP's MANDT+VBELN) are listed in the summary as `not_expressible`
  with the reason: one column per side, no calculated columns in Direct Lake, so the lakehouse needs a combined key
  column (a gold view, `create_gold_views`) before the relationship can exist; the old "or a calculated column" advice
  is gone. The zip's README and the model's README say to extract the whole zip before opening the `.pbip` (opening it
  from inside the zip gives "definition.pbism is missing"). Tests: a TMDL document check over every generated document
  for the shop, the SAP demo and Salesforce + ERP, and the zip from /check holds `.pbip`, `definition.pbism`, both
  `.platform` files and the report folder for all three. The Fabric REST API was not called in this round; the SAP
  draft after the change has not been opened in Power BI Desktop yet.
- Round n66: three contradictions in the trust texts, found by an external review of the live site on 30 October
  2026, text only. "Your data stays in your tenant" (home, /it, /pricing) is replaced by the same sentence on all
  three pages: Krusgraph stores no table contents; names, counts and requested sample rows pass through in memory and
  reach the AI client; EU hosting, or your own Azure to keep everything in your tenant ("stays in your tenant" is
  now a banned phrase in tests). /it and /docs say about tokens exactly what /privacy says: Claude's in memory only;
  other MCP clients' sign-ins encrypted in Table Storage for the times /privacy gives, linked. The dry-run sentence
  on /terms, home, /it and /docs renders from `tool_status.NO_DRY_RUN` (create_backend has none), and a test holds it
  to the signatures in server.py. `build_word` and `short` count a tool created live after the run (`LATER_LIVE`)
  as created, so the hub and the docs no longer say "draft" beside "created live" for the ontology and the
  silver notebooks; the docs' hand-written statuses render from tool_status. The Power BI project from /check was
  opened in Power BI Desktop on 30 October 2026, and /check and its README say so. Anchor links in the docs
  Markdown render as links.
- Round n65: `deploy/krusgraph.sh --doctor` prints one table of the service's state (server and build, the
  certificate's expiry, the Entra client secret's expiry as dates only, replicas, domain binding, Log Analytics,
  budget), reads only; `--budget` creates a cost budget on the resource group with e-mail from two new keys,
  `budget_amount` and `budget_email` (empty = nothing); `--backup` exports the registration table's consent records
  to a git-ignored file, with the restore in `docs/OPERATIONS.md` section 8, and section 9 is the continuity
  checklist. Unit-tested against a faked `az`, not run against Azure. `docs/NORDIC-PACK-SPIKE.md` writes down the
  spike of 30 October 2026 on a Nordic ERP pack (Business Central first).
- Round n60: `SECURITY.md` at the repository root (report to gustav@krusgraph.com, as in security.txt; only the latest
  version supported; no customer data stored; no fixed response time, no certification). Dependabot for pip and
  GitHub Actions. `.github/workflows/sbom.yml` builds a CycloneDX SBOM of `deploy/constraints.txt` on every push to
  `main` and on a tag `vX.Y.Z`, kept as an artifact; on a tag it checks the version against `pyproject.toml` and puts
  the CHANGELOG section in the run summary. How to tag: `docs/OPERATIONS.md` section 7. No tag created yet.
- The start page's row under the hero is a hub (the brief of 27 October 2026): "Your data in Fabric" (Lakehouse,
  Warehouse, SQL database) and "What Krusgraph builds in Fabric" (GraphQL API, Power BI semantic model, Fabric IQ
  ontology, views, data agent, silver notebooks) on the left, Krusgraph in the middle ("one plan, the rule behind every
  relationship"), "Where you build" on the right, joined by lines as in the graph and stacked with Krusgraph in the
  middle on a phone. Every status comes from `tool_status.py` (`SOURCES`, `BUILDS`, `build_word()`): "creates" only for
  what has been created live on the hosted service (the GraphQL API), "draft" for the rest; the warehouse and the SQL
  database are marked experimental. Text names only, a text version for screen readers, and the "Independent
  product…" line, which names Anysphere when Cursor is shown. Checked in a browser at 375, 768, 1280 and 1440 px.
- Client registration is on at krusgraph.com since 27 October 2026, and the maintainer's live test that day signed in
  from Glama (client ID metadata document), VS Code and Cursor at `/mcp/connect`. With client registration on, the
  site names them: the hub lists Claude, VS Code and Cursor via MCP (`tool_status.CLIENTS_TESTED`,
  `clients_working()`), `/start`, `/docs` (a new section, *Other MCP clients*) and `llms.txt` send them to
  `/mcp/connect` with the date of the test, and the home page says Krusgraph connects Claude, VS Code and Cursor. With
  it off, the pages say what they said before. The run's findings are in `docs/CLIENT-REGISTRATION.md` and
  `docs/LIVE-TEST.md`; the README, `docs/OPERATIONS.md` and `docs/SECURITY.md` follow.

- Round n17: the guided demo ("Where should each order be delivered?") moved from the start page to a page of its own,
  `/demo`, unchanged in what it does: the four steps, the graph with its mascots, the details, the relationship list
  and the "Demo · synthetic data" pill, with its own title, description, canonical link and sitemap row, and links on to
  `/explore` and `/start`. The start page keeps a short way in (the heading, one sentence, "Try the guided demo"), and
  the hero's button goes to `/demo`; at 1280 px the start page is 3,132 px tall instead of 4,582. Old links into the
  demo on the start page (`/#guide`, `/#demo`, a step's or the graph's id) go on to the same anchor on `/demo`. The
  step headings are `h2` now, under the page's `h1`. `/demo` is not in the menu: it made the open menu at 375 px longer
  and wrapped the header at 768 px; the footer, `/docs`, `llms.txt` and the README link it.
- Under the start page's hero, a row of what Krusgraph connects: Microsoft Fabric (your tables), Power BI (model drafts)
  and Fabric IQ (ontology drafts) on one side, Claude (MCP) and Lovable (via the GraphQL API) on the other, as text
  names on tiles joined by a line, with no third-party logos or icons, a text version for screen readers and the line
  "Independent product. Not affiliated with or endorsed by Microsoft, Anthropic or Lovable." Claude is the only client
  named: the one MCP client tested against the hosted service; Lovable uses the API Krusgraph creates, not Krusgraph.

- Round n16: sign-in for MCP clients other than Claude, behind `KRUSGRAPH_CLIENT_REGISTRATION` (off by default;
  `docs/CLIENT-REGISTRATION.md`, turning it on in `docs/OPERATIONS.md` section 6). The clients use
  `https://<domain>/mcp/connect`, whose metadata names Krusgraph's own authorization server at `/oauth` in front of the
  one Entra app: Client ID Metadata Documents (VS Code, Claude Code, ChatGPT), strict dynamic registration with its own
  flag (Cursor, Glama), redirect addresses https or loopback only, Krusgraph's consent page per client before Entra
  (remembered per user and client for https addresses, shown every time for a program on the user's computer), no
  redirect to a client before it is approved, PKCE S256, single-use state and codes, rotating refresh tokens of its
  own, `iss` in every answer, and the same token validation as `/mcp`. An independent security review found eight
  problems before release, all fixed with tests (the list is in `docs/CLIENT-REGISTRATION.md`). Records in Azure Table Storage (`registration_store.py`).
  Claude's `/mcp`, its metadata and its 401 are the same in both modes (tests lock them). `/privacy` describes the
  records when the flag is on. `deploy/krusgraph.sh --client-registration` prints the commands (one web redirect
  address on the Entra app, the table, the key, the settings) and runs nothing. The earlier facade (`KRUSGRAPH_DCR`,
  `fabric_backend/dcr.py`, `docs/AUTH-DCR.md`) is removed: it handed out the Entra app's client id without a consent of
  its own and changed Claude's metadata when switched on. Unit-tested against a mocked Entra; not deployed.

## 0.7.0 — 2026-10-27

- Home page, round 1 of the brief of 27 October 2026: a shorter lede and a guided example in four steps that follows
  one order to its delivery address. The suggestion for `orders.ship_to_id` is now the engine's own
  (`suggest_relationships` on the synthetic sample, `demo.demo_suggestions()`), with its data check (all 60 orders have
  a `ship_to_id` in addresses, 15 different addresses) and the next candidate that does not hold (customers, 35 of 60).
  The visitor's review is a separate step from the check: accepting decides what the column means in the demo only,
  never "checked", and the graph below follows the same decision. The last step is a result card (what was reviewed,
  what the data shows, the decision, what is still open, next tools with their status) with a summary to copy. Every
  step is in the HTML, so the page reads without JavaScript. The headline and the mascots are unchanged.
- Finding 8 of 27 October 2026: the Glama catalog lists Krusgraph and asks the owner to confirm it with a file.
  `GET /.well-known/glama.json` serves the maintainer's claim (`$schema` and `claim`, a token made to be public) as
  `application/json`, without sign-in and outside the 401 in front of `/mcp`, only when the public host from
  `MCP_PUBLIC_URL` is krusgraph.com; any other host, or none, gets a 404, so a self-hosted copy claims nothing.
- Finding 7 of the live test of 27 October 2026, after a live `create_backend` the maintainer approved: an update of
  `shop_api` with the ship-to relationship confirmed stopped with `would_remove`, because the plan named the reverse
  field `orders_as_ship_to` where the API has `orders`, and `keep_with_confirmed` was empty. `create_backend` and
  `plan_drift` now keep an existing API's field names for the same relationship (the same columns in the same
  direction) unless `confirmed` names them otherwise (`names_kept_from_api` says which), and every `keep_with_confirmed`
  entry carries `field_name` and `reverse_name`. `/docs` and the README document both names in `confirmed`.
  `create_backend` is **Tested end to end (27 October 2026: update in place of shop_api with confirmed)**; creating a
  new API has not run live, and the pages that offer it say both (`tool_status.create_api_status()`).
- Round n15, the live test of 27 October 2026 (Claude through the hosted build `src-df29c45febaec4b0`, main 5adace8,
  against demo / demo_lh / shop; 30 tools read-only, as drafts or as dry runs, no creating call). Status words from
  `tool_status.py`: the tools that ran are **Tested end to end**, the drafts **Tested end to end (a draft; creates
  nothing)**, `create_views`, `create_semantic_model` and `create_data_agent` *tested end to end as a dry run* with
  creating as before; `create_backend` stays Experimental. The notes in the tools' answers now come from
  `tool_status.answer_note()`, so they follow the status instead of saying "not yet run against a live workspace";
  the docs' test status, `llms.txt`, the use cases, the home page's test line and the server's instructions render
  from the same fields. Fixes for what the run found, each reproduced in a test first: `lineage` reads a definition
  once more when Fabric's first answer could change and keeps Fabric's message in a skipped item (`error`, `reason`,
  `hint`); `create_data_agent`'s instructions and examples follow the privacy rules (the key in place of
  `customers.name`; `show_personal_data`); `data_dictionary` with `tables` takes roles and subject areas from the whole
  plan; the drift monitor's notebook installs the tag of the server's version (`v0.6.0`) by default, `main` only when
  asked (the tag is made with each release, docs/PUBLISHING.md).
- Round n13, the Databricks adapter (Draft only: unit-tested with Databricks mocked at its REST API, not yet run against
  a workspace; local stdio server only, `KRUSGRAPH_PLATFORM=databricks`; docs/DATABRICKS.md). Reads a Unity Catalog
  schema through `information_schema`: informational PRIMARY KEY / FOREIGN KEY constraints become K0 / R0 as on a Fabric
  warehouse, column tags feed the personal-data rules (`class.email_address` → P2; a bare `pii` tag → `tag`). Runs the
  checks in Databricks SQL on a SQL warehouse through the Statement Execution API, signed in with Databricks' own
  unified authentication (`databricks-sdk`, `pip install "fabric-backend[databricks]"`). Seven new local tools:
  `databricks_constraints_draft` and `create_databricks_constraints` (RELY only where validate_plan's counts hold; only
  ADD, never DROP; dry run by default), `databricks_pipeline_draft` and `create_databricks_pipeline` (a Lakeflow
  pipeline with the silver and gold rules of the Fabric notebooks as expectations and a quarantine; creates or updates
  the pipeline in place, starts nothing; dry run by default), `databricks_metric_view_draft`, `export_databricks_bundle`
  and `databricks_lineage` (system.access.table_lineage). `create_views` writes Databricks views there. The tools that
  build Fabric items answer `unsupported` on Databricks with the tool that does. The pipeline's SQL ran on SQLite in the
  tests with the same quarantine, per table and rule, as the Fabric silver notebook. One line about it in the hosted
  server's instructions and a section on /docs; nothing else on the site changes before a live run.
- CI runs Python 3.12, which keeps docstring indentation; the golden tool listings compare descriptions after
  `inspect.cleandoc`, so they hold on 3.12 and 3.13 alike.
- Round n13, platform adapters (no answer changed). The engine (inference, validation as counting queries, join paths,
  the graph, drift, dictionary, dbt, the silver logic) is separated from what is platform-specific: reading a source's
  schema, running SQL and building objects now sit behind `fabric_backend/platforms/` (`base.py` the interface,
  `fabric.py` the first adapter, moved out of `server.py`; `local.py` the ODBC string, SQLite, file and columns-list
  sources of the stdio server and the demo, moved out of `mcp_server.py` and `demo_app.py`). The counting, sample and join
  SQL is written through `dialects.py` in the dialect of the connection (T-SQL by default). `docs/ARCHITECTURE.md` says
  what a new adapter implements; `tests/test_architecture.py` checks that the engine imports no I/O library and no
  adapter. `tests/golden/` holds every answer of the engine, of all hosted and local tools, the listings, the
  instructions, the demo and the CLI, committed before the move and unchanged by it.
- Round n12, the layer on top of Microsoft's own Fabric MCP servers (unit-tested; nothing of it has run in Fabric).
  `compare_semantic_model` (read-only): an existing Power BI semantic model against the plan — relationships the model
  lacks, ones a rule or the data contradicts (with the rule or the count), other cardinality, both-way filters, active
  against the plan's spanning forest, links the plan lacks with a `confirmed` entry, columns summed against the
  `summarizeBy` rule, and the suggested measures it lacks; read from the model's TMDL through getDefinition
  (`SemanticModel.ReadWrite.All` or `Item.ReadWrite.All`; the read-only executeQueries is documented as not supporting
  the INFO functions, docs/SCOPES.md) or from `tmdl` files, which need no permission. `semantic_model_draft` suggests
  measures with their reason (row count per fact table, sums only where `summarizeBy` sums) and a `Calendar` table marked
  as the date table, related to `date` columns of fact tables. `gold_views_draft` and `create_gold_views` (dry run by
  default): materialized lake views over the silver tables, one wide view per fact table over the safest many-to-one
  paths, with `CONSTRAINT … CHECK … ON MISMATCH DROP` per key and relationship, each commented with its rule, never over
  a source, silver or foreign table; syntax and status from fabric-docs a2de7f9 (generally available since September
  2026); the SQL ran on SQLite and a local PySpark 4.0.1. `export_item_definitions` (read-only): what the creating tools
  would create, as folders in Fabric's Git format, `create_views`' SQL as a script beside them. Personal data
  (`fabric_backend/privacy.py`): one rule per name pattern (P1–P6), masked in `sample_rows` (hosted and local), left out
  of drafted queries and gold views, masked in the silver quarantine, named in `validate_plan`;
  `show_personal_data=true` shows them; the source's sensitivity label id is named. `deploy/krusgraph.sh
  --client-redirects` prints the az commands for Claude Code, VS Code and Cursor (docs/OPERATIONS.md section 5), runs
  nothing. `docs/LIVE-TEST.md`: the checklist for the next live run. /docs: a section on using Krusgraph beside
  Microsoft's Fabric MCP servers, and what is read about personal data and labels. Thirty-four tools.
- /use-cases no longer calls the GraphQL API and the SQL views "tested end to end": creating the API is Experimental
  (`create_backend` has not been run live; querying an existing API with `describe_backend` and `query_graphql` is tested
  end to end) and the views were tested as a dry run only. The README's note of 25 October and docs/LOVABLE-END-TO-END.md
  said the same of `create_backend`; a test now scans the site, its Markdown and llms texts, the README, docs/ and the
  server instructions for either claim.
- Fixes from an independent review of round n12's code, each with a test: a question grouped by a personal column of a
  table without a key no longer groups by it (one total, and the reason); a mixed-case `gold_schema` is one lower-case
  name for the notebook's guard and its CREATE statements, and the notebook's SQL is a plain string with backslashes and
  triple quotes escaped; the calendar never adds a second active path (a line table whose header already relates to it
  stays inactive); the privacy rules read numbered and qualified names (`phone_no`, `email1`, `address2`, `birth_dt`) and a
  person named in another table (`orders.customer_name`); a suggested measure is matched by its column, so `Amount (EUR)`
  is not re-suggested; `--client-redirects` changes nothing when the app's list cannot be read; `export_item_definitions`
  keeps the gold views to the exported `tables` and refuses two items in one folder; gold views name a personal key they
  keep for a join.
- The status words follow the 26 October protocol (14 steps, no creating call): 16 tools are Tested end to end,
  `create_views` as a dry run; `create_backend` and `list_tables` are Experimental; texts that said the 22 tools of that day
  were tested, or that `create_views` created a schema and a view, are corrected. /local says exactly what leaves the
  machine. The menu says "Pilot projects" (/partners unchanged); the home page's JSON-LD has no price line.

- Drift monitor: the last saved plan is the one with the highest run number for the source (a new `run` column in
  `krusgraph.plans`), then the latest `taken_at`, now kept to the microsecond. Two runs in the same second (the run time
  was cut to whole seconds) could make the next run compare with the older plan and report the same changes again;
  CI's `notebooks` job failed on it once. A plans table from before the column gets it added on the next save.
- A column linked by a `confirmed` entry is settled: it is no longer also inferred to another table or listed in
  `plan.ambiguous`, and a confirmed header link counts for the line key (K5) as the inferred one did (confirming
  `order_items.order_id -> orders` moved the key to `product_id, line_no`). Confirmed entries take the schema's own
  spelling of table and column names, as `check_input` already accepted any case.
- Fixes from an independent review of this round's code, each with a test: the silver notebook can be generated again
  after its first run on a lakehouse without schemas (its own `silver_*` tables are no longer read as sources); its
  ownership mark names the source (`krusgraph.silver = <lakehouse id>/<schema>`), so two notebooks never overwrite each
  other's tables; a table that points at itself is checked until no more rows drop out. The drift monitor never shows
  the webhook address in an error, survives a failed listing of the workspace's items, does not retry (no double
  message), and refuses a `library_ref` that is not a plain ref. Only `--key-vault` switches the app to Key Vault (a
  `key_vault` in the config alone changed the app on `--update`); the full run keeps what `--key-vault` set. Rate limits:
  a zero window is refused at startup, `retry_after` is the slowest bucket's, idle ids are dropped about an hour after
  the last call (as `/privacy` says). Key Vault: a failed re-read after the hour keeps the secret held. Links built
  from `MCP_PUBLIC_URL` (docs, pricing) are parsed instead of split on "/mcp", which broke on a host like
  `mcp.example.com`. The paid-plan check counts `create_drift_monitor`'s dry run as the paid feature it gives away.
  `answer_query_draft` reads markers as whole words ("beräkna" is not "räkna"), takes top N only with a ranking word,
  prefers a column for "per order date", knows "order lines" means the table holding the lines, never groups a table by
  itself, counts per group when no aggregate is named, and lists every number or condition it did not apply.
- `Schema.from_spark` uses `listColumns` with one quoted name (the two-argument form is deprecated since Spark 3.4).
- The local stdio server has `answer_query_draft` (T-SQL only; GraphQL needs an API in Fabric) and, for a lakehouse,
  `silver_notebook_draft` (the notebook without a default lakehouse, since the item ids are not known locally; a schema
  other than `dbo` implies a lakehouse with schemas when `FABRIC_SCHEMAS_ENABLED` is not set). CI has a `notebooks` job
  that installs PySpark 4.0.1 with Java 17 and runs the generated silver notebook and the drift monitor on a local Spark
  (`tests/test_spark_notebooks.py`), so they no longer run only in a sandbox.
- From understanding to building ([docs/NOTEBOOKS.md](docs/NOTEBOOKS.md)); thirty tools. `silver_notebook_draft` and
  `create_silver_notebook` (dry run by default): a Fabric PySpark notebook generated from the plan that writes silver
  tables in a schema of their own, de-duplicated on each key (the latest row by `order_by` or a column named like
  `updated_at` wins), every relationship checked with the rows whose reference is missing in `krusgraph_quarantine`
  with the rule and the reason, each step commented with its rule, idempotent, and guarded twice against writing over a
  source table or a table it did not write. `drift_monitor_draft` and `create_drift_monitor` (dry run by default): a
  notebook and a pipeline with a daily schedule that compare the plan with the last saved one, save it in
  `krusgraph.plans`, and send what changed and which APIs, models and views it reaches to a webhook set as a pipeline
  parameter in Fabric (no secret in the code); the comparison is `plan_drift`'s and `lineage`'s logic as a library
  (`fabric_backend/monitor.py`). `answer_query_draft`: a question in Swedish or English about some tables as T-SQL over
  the safest join path with the rule per step, and as GraphQL for an existing API (or why GraphQL cannot answer it);
  `query_graphql` takes `question`/`tables`/`source` and runs the suggested query. Created through the notebook and data
  pipeline REST APIs (fabric-rest-api-specs a96c37a); without `Notebook.ReadWrite.All` / `DataPipeline.*` the creates
  answer `kind: consent` with the exact scope (docs/SCOPES.md). Unit-tested; the generated silver notebook and the drift
  monitor (two nights) also ran on a local PySpark 4.0.1 against the shop seed; nothing has run in Fabric yet.
- `lineage` (and `plan_drift`'s impact) now finds a GraphQL API over a lakehouse: the API names the lakehouse's SQL
  analytics endpoint as its source item, and the comparison used only the lakehouse's id. Reading the workspace's items
  moved to `lineage.py` (`workspace_edges`, `rest_*`), so the drift monitor uses the same code.
- `create_views` describes its header views (`vw_orders`) in the tool description, the docs page and the README; the
  hosted `sample_rows` passes the column types to the sampling SQL, as the local server does (binary as its size, CLR
  types as text). The plugin skill names the new tools and when to ask; `docs/PUBLISHING.md` notes the open question
  about `argument-hint` in plugin commands on claude.ai.
- Operations before real customers (unit-tested; nothing deployed or run against Azure). Fair-use limits per signed-in
  user (`oid`) and per organisation (`tid`): token buckets, 30/minute and 600/hour per user, 120/minute and 3000/hour per
  organisation by default, configurable or off (`KRUSGRAPH_RATE_*`); a refused call runs nothing and answers
  `kind: rate_limited` with `retry_after`, and only tool calls count, so `initialize`, `tools/list` and Claude's 401
  sign-in challenge are untouched. Anonymous usage statistics (`fabric_backend/usage.py`): one JSON line per tool call
  with tool, outcome kind, duration and dry run, optionally a salted organisation hash, nothing about users or data;
  `/metrics` in the Prometheus format, a 404 unless a token is configured. `/health` for uptime checks, without sign-in
  and without anything about the server. The Entra client secret can be read from Azure Key Vault with the container
  app's managed identity (`fabric_backend/keyvault.py`; as before when not configured), and
  `deploy/krusgraph.sh --key-vault` sets that up. `/privacy` lists exactly what is counted and says whether console
  logs are kept, from the deployment's own settings. `docs/OPERATIONS.md` has the commands, in order, for Key Vault,
  Log Analytics, the 5xx alert and the availability alert; `docs/SECURITY.md` says what is closed and what is open.
- A dormant paid-plan check (`fabric_backend/entitlements.py`, off unless `KRUSGRAPH_ENTITLEMENTS=1`): per organisation,
  from an environment variable or Azure Table Storage; paid features answer `kind: upgrade` with a link to a pricing
  page that does not exist yet, dry runs stay free. With the flag off nothing changes, and a test locks that.
  `docs/PRICING-NOTES.md` says how to switch it on.

- A faster first time: `/start` follows the design sketch (the three steps beside the current step, one at a time
  with JavaScript and all three without it; the real actions are the admin-consent link and the connector URL, no
  sign-in on the site) and its "What will Krusgraph access?" names every scope with the tools that use it, including
  the one the app does not ask for. The first-time error kinds (`sign_in`, `consent`, `no_access`, `capacity`,
  `schema_not_found`, `sql_sign_in`) carry a link to the new docs section "First-time errors", which gives the exact
  clicks per kind. Five first questions for an undocumented lakehouse in the server instructions and on the docs page.
- Fewer tokens per answer (before/after per tool in `docs/INFERENCE.md`): `analyze_schema` no longer repeats the
  constant rule weights and the three per-table centrality maps (the ten most central tables keep their numbers, every
  role its own); `plan_backend` leaves empty notes out and takes `mermaid=false`; `semantic_model_draft`,
  `data_dictionary` and `dbt_schema` take `tables` as names or patterns and are bounded at 60 000 characters (the
  document is cut on a line and the answer says so) instead of answering with a megabyte on 300 tables.
- Naming from the real world (`fabric_backend/infer.py`): a documented synonym table (abbreviations such as `cust`,
  `prod`, `ord`, `emp`; Swedish and German business words in singular and plural), transliteration of `å ä ö ü ß`,
  irregular English plurals (`People` → `person`), the table-kind prefixes `dim_`/`fact_`/`tbl_`/`stg_`/`vw_`, the
  `_sk`/`_bk` key suffixes, Swedish and German line words for K5, a suffix tie-break between two tables that answer to
  the same name, and a suffix guard for the weakest rule. Synonym matches count as R4, carry a `note` on the
  relationship and are listed under `plan.synonyms`; the five public benchmark schemas are unchanged to the number.
  Benchmark: WideWorldImporters (OLTP, 33 tables) and WideWorldImportersDW (star schema, 14 tables) from Microsoft's
  samples, plus four synthetic naming fixtures; before/after per schema in `docs/INFERENCE.md`.
- Compact answers for large schemas (`fabric_backend/compact.py`): `list_tables`, `plan_backend` and `analyze_schema`
  (remote and stdio) take `tables` (names or fnmatch patterns) and `detail` (`auto` = full up to 60 tables and a
  summary above, `full`, `summary`); every answer is bounded at 60 000 characters, a plan that is too large loses its
  diagram first, and the cut says to narrow with `tables`. Measured on 300 and 1 000 synthetic tables in
  `docs/INFERENCE.md` (plan_backend 443 kB → 44 kB, analyze_schema 747 kB → 21 kB at 300 tables).
- `create_ontology` is a regular tool now, dry run by default, no environment flag: it creates the Fabric IQ ontology
  (preview) item from the plan or updates the one of that name (`POST /workspaces/{id}/ontologies`, `updateDefinition`;
  delegated scope `Item.ReadWrite.All`, Contributor on the workspace, a Fabric capacity; checked in
  microsoft/fabric-rest-api-specs `ontology/swagger.json` on 26 October 2026, where the item is marked preview and the
  generation-2 example has the same part layout as the draft). Without the permission it answers `consent` naming the
  scope. The instructions and the docs page tell the one-plan story: API for GraphQL, Power BI semantic model, Fabric IQ
  ontology, wide views and data agent from the same plan, each with a dry run first. Twenty-five tools.
- `suggest_relationships` ranks before the data check: the 26 October live run gave every candidate for
  `orders.ship_to_id` the same score. Role words judged against the target's name and key column (`ship_to` names an
  address), weighted triangular closure (the certainty product of the two links that close the triangle, including a
  shared parent: orders → customers ← addresses), and penalties from the plan (a line table already joins the two, the
  target is a fact table, the source already refers to it). On shop without data: addresses 3.94, the rest 1.5 or less.
  After the check, `final_score` adds the inclusion damped below ten distinct values to the name score.
- `create_views` adds one view per header table: the table a fact table holds the lines of, with its own dimensions
  (`vw_orders` with the customer and, once confirmed, the ship-to address). Found in every benchmark schema: Orders,
  Invoice, ORDERS, SalesOrderHeader and PurchaseOrderHeader.
- TMDL drafts no longer sum CamelCase ids (`PersonID`, `TerritoryID`, `SalesPersonID` in AdventureWorks), codes or label
  numbers (`Status`, `RevisionNumber`, `TaxType`, `ExpYear`); no key, relationship column or id is summed in any
  benchmark schema. A reference with no id word that no rule links is summed until confirmed (pinned by a test).
- The local server's `sample_rows` reads SQL Server's hierarchyid, geography, geometry and sql_variant as text and binary
  columns as their size, so pyodbc's unsupported-type error does not fail the call. SQL text unit-tested only.
- Plugin: `supportUrl` is the issue tracker; the plugin passes `claude plugin validate --strict` (Claude Code 2.1.295,
  26 October 2026).
- `fabric-backend demo`: the 20-minute demo on a laptop (`fabric_backend/demo_app.py`, `docs/DEMO-20-MIN.md`). One local
  page on 127.0.0.1 in the graph explorer's design, four steps with a time budget: connect (a SQL Server over ODBC, a
  folder of CSV / Excel files loaded into SQLite in memory with a standard-library .xlsx reader, a columns list, or the
  synthetic shop schema), the map (plan, roles, subject areas), the health check (validate_plan and
  suggest_relationships as findings with what we saw / what it means / next step / evidence, Accept and Skip, the plan
  updating at once), the value (five questions proposed from the graph and run locally with the SQL, exports:
  dictionary, dbt, a Lovable prompt, the plan, the ER diagram). No account, no cloud, no external script; the figures
  follow the motion brief and prefers-reduced-motion. The site's graph gained a layered layout for any schema. Tests on
  the shop seed and on a CSV / Excel folder; a test that the server binds to 127.0.0.1 only.
- Site: `/local` (the local server over ODBC: SQL Server with Windows sign-in or a Fabric SQL endpoint, what it needs,
  the Claude Desktop configuration, what works locally, the CSV path), the MCP Registry listing named on the home page,
  the docs page and llms.txt, the Claude plugin mentioned as coming soon. `docs/PRICING-NOTES.md` (internal): what a
  free and a paid tier could contain, what would have to be measured per user, what it requires; nothing built.
- `lineage` (read-only, new): which GraphQL APIs, semantic models, views and data agents in the workspace build on a
  source's tables, from each object's own definition (`fabric_backend/lineage.py`), with what a change to one table
  reaches; `plan_drift` adds `impact` for the tables and columns a re-run would drop. `docs/MULTI-SOURCE.md` is the
  design note for a graph over several sources (not built).
- Local server against SQL Server on-prem: the constraint query joins INFORMATION_SCHEMA on the constraint schema too
  (two schemas may share constraint names) and leaves out foreign keys into another schema; `FABRIC_SOURCE_KIND=SQLServer`
  makes the Fabric-only drafts (Direct Lake semantic model, Fabric IQ ontology) answer with an explanation instead of
  wrong output. Tested against recorded INFORMATION_SCHEMA rows (spaces in names, composite declared keys, nvarchar(max),
  datetimeoffset, uniqueidentifier, computed columns, views); no SQL Server was available to run live.
- Claude plugin in `plugin/krusgraph/` (connector reference, skill `fabric-graph-backend`, commands plan / document /
  explain-schema, README, tests); not published; `docs/PUBLISHING.md` says how it is submitted as a plugin bundle.
- Lovable on Fabric without getting stuck: `docs/LOVABLE-END-TO-END.md` maps every step of the chain with its owner,
  whether it is automated and what blocks, with sources. New read-only tool `app_readiness` (keyless and unlinked types,
  write access, one introspection probe, "unknown" with the click path for what Fabric's API cannot read). `app_starter`
  adds the backend piece: a Supabase edge function (client credentials, secrets as Supabase secrets, mutations refused),
  the frontend helper, the per-user alternative and a checklist that starts with the app's own Entra registration.
  Dynamic client registration for agents outside Claude behind `KRUSGRAPH_DCR=1` (`fabric_backend/dcr.py`, design and
  alternatives in `docs/AUTH-DCR.md`): RFC 8414 metadata pointing at Entra, an RFC 7591 registration endpoint that
  answers the app's public client id for allow-listed redirect URIs, nothing stored; off by default, Claude's sign-in
  unchanged. Introspection cannot be set through the Fabric REST API (spec read 26 October 2026), so it stays a
  documented click.
- Review fixes in the stdio server and CLI: the CLI's `semantic-model` writes `schemaName` exactly when the lakehouse has
  schemas (it never did for a lakehouse); a Rayfin `metadata.json` source labels every command's output with the schema
  it read, and `plan`/`definition` accept it too; `views` prints `GO` between batches; a missing `FABRIC_ODBC` answers
  `server_config`; the ODBC string is parsed with braces, quotes and the Server/Database synonyms; `FABRIC_SOURCE_KIND`
  is read without case; a string without a database keeps the drafts' placeholders; every stdio tool opens one
  connection and closes it; a bad `views_schema` is `bad_input`; a failing `create_views` keeps the partial log and the
  warehouse hint (remote too); the stdio tools carry titles and read-only/destructive hints; a missing or wrong columns
  file is one line and exit 2 in the CLI.
- Live run of the consultant, graph and creating tools against the demo workspace (26 October 2026): read-only tools and
  dry runs, then `create_views` for real (schema and one view) and the two other creates answering `consent`; the tool answers, the docs page and the README say what has run live and what has not.
  Site texts updated to the current rules (K0–K5, R0–R4) and the twenty-two tools.

## 0.6.0 — 2026-10-26

- The local stdio server (`fabric-backend-mcp`) gets the SQL-only tools of the remote one over the connection in
  `FABRIC_ODBC`: `validate_plan`, `sample_rows`, `semantic_model_draft`, `join_path`, `data_dictionary`, `dbt_schema`,
  `analyze_schema`, `suggest_relationships` and `create_views` (dry run by default; the ODBC connection gained
  `statement` and `close`). The SQL endpoint host and database come from the ODBC string, the item kind from
  `FABRIC_SOURCE_KIND`, the schemas flag from `FABRIC_SCHEMAS_ENABLED`. The tools that need Fabric item ids stay remote.
- CLI commands from a columns CSV, nothing created: `semantic-model`, `join-path`, `dictionary`, `dbt`, `analyze`,
  `views`. Tested on the synthetic shop schema, including the views applied in SQLite.
- `suggest_relationships` treats an inclusion query that answers no rows as no evidence instead of failing.
- Graph theory on the plan (`fabric_backend/graphs.py`, pure Python, deterministic): certainty per rule (R0/confirmed 1.0,
  verified 0.9, R1 0.8, R2 0.6, R3/R4 0.5) and cost 1/certainty; `analyze_schema` (roles with the numbers behind them,
  degree/betweenness/PageRank, subject areas by label propagation, cycles and multi-path pairs, maximum spanning forest
  of active relationships); `suggest_relationships` (candidate columns ranked by name, type and triangular closure,
  checked against the data with an inclusion count in evidence.py; suggestions only). `join_path` adds the safest path
  next to the shortest; `semantic_model_draft` takes its active set and table roles from the graph; `data_dictionary`
  gets a roles/areas/ambiguity section.
- Review pass: the semantic model draft writes `schemaName` for a lakehouse created with schemas (the REST property
  `properties.defaultSchema`, lakehouse/definitions.json) and omits it for one without, instead of guessing from the
  schema name alone; the Direct Lake expression opens the database name the SQL endpoint actually has (a Fabric SQL
  database's `properties.databaseName`), as `_resolve_source` already resolved it.
- Creating tools with a dry run first: `create_semantic_model` (SemanticModel item from the TMDL draft via
  `POST /semanticModels` / `updateDefinition`), `create_views` (`CREATE OR ALTER VIEW` in a schema of its own on the SQL
  analytics endpoint or warehouse: a wide view per fact table, one per hard-to-read relationship; never DROP), and
  `create_data_agent` (a Fabric data agent through the staging REST API: instructions from the plan, the source as data
  source with the tables selected, example question/T-SQL pairs, publish); `app_starter` (read-only) for an app on a
  created API. A 401/403 from a create answers `kind: consent` naming the missing delegated permission; `docs/SCOPES.md`
  lists permissions per tool and the `az` commands. The SQL connection gained a `statement` runner for DDL.
- Five read-only consultant tools from the same plan, nothing created: `semantic_model_draft` (Power BI model in TMDL,
  Direct Lake on the SQL analytics endpoint, active/inactive relationships, README with decisions), `join_path`
  (shortest relationship chain with T-SQL, or the missing link), `data_dictionary` (Markdown hand-over with optional
  counts), `dbt_schema` (sources with unique/not_null/relationships tests), `plan_drift` (plan vs an existing API's
  definition). New modules semantic_model.py, paths.py, dictionary.py, dbt.py, drift.py; server.py has thin wrappers.
- Security review of the sign-in path (`docs/SECURITY.md`, `tests/test_security.py`): issuer tenant ids compare
  without case; an empty `Bearer` answers `invalid_request`; chunked request bodies are capped at 4 MiB like declared
  ones; the on-behalf-of cache evicts expired entries first and then the oldest half instead of emptying; a token
  endpoint answer without `access_token` is a `TokenError`. Tests cover wrong audience/issuer/tenant/scope, expired and
  immature tokens, `alg: none` and key confusion, altered signatures, path variants around `/mcp`, oversized headers
  and bodies, cache isolation between users, and that no token or secret reaches logs or output.
- Engine: an inference benchmark on Northwind, Chinook, TPC-H, AdventureWorks and Sakila (official DDL as ground
  truth, `tests/fixtures/schemas/`, numbers in `docs/INFERENCE.md`) and the rules it led to: table-wide column
  prefixes (`N_NATIONKEY`), `_code` suffixes, `<X>Header` names, abbreviations of four letters or more, a role before
  the target's name (`manager_staff_id` → staff, rule R4), junction keys (K4) and header-plus-line keys (K5). The shop
  schema's `order_items` now gets `order_id + line_no` by rule K5 without an override. GraphQL field names for
  previously matched columns are unchanged. `plan_backend` suggests `reference + start_date` keys for history tables.

## 0.5.0 — 2026-10-25

- Fabric IQ: `ontology_draft` writes the plan as an ontology (preview) draft: entity types with a key and properties,
  relationship types, data bindings, in the item's generation-2 definition (TMDL parts for `POST /ontologies` or Git),
  plus a Turtle file for the portal's Import ontology and a binding checklist with the rule behind every key and link.
  `create_ontology` exists behind `KRUSGRAPH_ONTOLOGY_WRITE=1` (needs `Item.ReadWrite.All`). CLI `ontology` command and
  `fabric_backend.ontology_files`. Deploy config `ontology_write` turns the create tool on; a large schema's draft keeps
  summary and bindings and says what it left out. Checked against recorded definitions, not live yet.
- Site: robots.txt names the AI crawlers, `/llms-full.txt` serves every Markdown page in one file, llms.txt has a
  Connect section, pages link their Markdown twin with `rel=alternate`, the home page declares the WebSite; the hero
  names the sources it works with and the home graph scrolls inside its card on phones.
- Snowflake and Databricks: Snowflake database items, mirrored Azure Databricks catalogs and mirrored catalogs (preview) are
  source item types next to mirrored databases, each read through its SQL analytics endpoint as Microsoft's REST
  specification documents it; the schema reader's schema match is case-insensitive on every dialect and a missing
  `KEY_COLUMN_USAGE` view (Snowflake) means "no declared keys", so the library, CLI and stdio server plan Snowflake
  and Unity Catalog schemas directly. Docs describe the two routes.
- `list_workspaces`: the workspaces the signed-in account can see, with id and capacity; every other tool now takes
  the workspace by name as well as by id (a duplicate name is reported with the ids to choose from).
- HSTS and `X-Content-Type-Options: nosniff` on every response, the MCP endpoint and the 401 challenge included.
- A request that announces a body over 4 MB is refused with 413 before anything reads it.
- The local stdio server (`fabric-backend-mcp`) answers failures with the same `error`/`kind`/`hint` as the remote
  one and never echoes the ODBC string; the CLI prints an input error as one line and exits 2.
- Input checks: `keys`, `confirmed` and `tables` must name tables and columns that exist (case does not matter);
  a typo is answered as `bad_input` instead of becoming a definition Fabric rejects or an API with missing tables.
  The schema name is escaped inside its SQL literal.
- Engine: the R2 lookup is indexed once instead of rescanning every key per column; a 1 000-table schema plans in
  a tenth of a second instead of ten seconds, with identical output.
- Exact package versions for the server image in `deploy/constraints.txt` (resolved for CPython 3.12 on manylinux,
  audited); the Dockerfile and CI install with it, a weekly workflow audits it, and it is part of the source tag.

## 0.4.0 — 2026-10-25
- Tool errors a user can act on: every MCP tool answers a failure with `error` (plain words), `kind` (a stable code
  such as `not_found`, `no_access`, `capacity`, `sign_in`, `consent`, `schema_not_found`, `table_not_found`,
  `timeout`) and `hint` (what to do next). Fabric's message is quoted only after tokens and secret-bearing headers
  are removed; stack traces never appear. The server's MCP instructions describe the format.
- Deploy check waits for the build it just deployed: the server echoes `KRUSGRAPH_BUILD` on `/healthz`, the deploy
  script sets it to the image's source tag in the full run and in `--update`, and the check passes only when the
  live server reports that tag. `--status` says whether the live build is the one in the checkout.
- `--update` respects `min_replicas` (0 scales to zero, 1 keeps an instance warm); health probes start after a
  second instead of ten so a cold start takes seconds. Seed works on lakehouses without schemas.
- SQL analytics endpoint: 30 s login timeout, 120 s per metadata query, connection closed after the plan.
- Waiting for Fabric's long-running operation tolerates 429/5xx and reports a lost sign-in at once.
- Large `query_graphql` results come back as valid JSON with lists cut to their first items and a `truncated` note.
- CI: plain `pytest` finds `deploy/` (every run since the deployment tests failed at collection); current action
  majors. Tests for the Fabric plumbing, the four tools end to end on the demo schema, the Python API, deployment
  polling and the deploy script's Python 3.8 compatibility. 202 tests.

## 0.3.0 — 2026-10-25

- The "Little Connections" site served by the same process: `/`, `/explore` (the engine's own plan of a synthetic
  shop schema, with the rule behind every link), `/start`, `/support`, `/partners`, restyled `/docs` and
  `/privacy`, styled 404, `sitemap.xml`, `robots.txt`, `llms.txt`, MCP server card, `/lovable`. Self-hosted fonts,
  dark mode, no external resources, CSP, gzip, accessibility audits and browser tests.
- Deploy: `krusgraph.sh --update` (new image only, no Entra, secrets or domains), `--status`, `--check`,
  `company_orgnr` in the config, deploy check covers the site pages and waits for the new revision.
- Privacy page states the logging setup (`--logs-destination none`) and the data path; `docs/PILOT.md` and
  `docs/FET-PLAN.md`.
- Honest wording about which MCP clients are tested today.

## 0.2.0 — 2026-10-21

- Rayfin (Fabric Apps) connector entities from the same plan: entity classes with typed fields, keys and
  `@one`/`@many` relationships, `schema.ts`; CLI, library and MCP tool. Verified with `npx rayfin up`.
- Remote MCP server (Streamable HTTP) with six annotated tools including read-only `query_graphql`; Entra sign-in
  with 401 challenge, protected resource metadata, token validation and on-behalf-of to Fabric and SQL;
  Dockerfile with ODBC Driver 18; Azure Container Apps deploy script.

## 0.1.1 — 2026-10-21

- Fixes from the first live run: by-name lookup skips the SQL analytics endpoint that shares the lakehouse's
  name, create tolerates Fabric's `202` with an empty body, every action spelled out in the definition, SQL
  endpoint accepted as a resolved source.

## 0.1.0 — 2026-10-21

- Tables in a Fabric lakehouse, warehouse or SQL database → an API for GraphQL item with inferred keys and
  relationships (rules K0–K3, R0–R3, ambiguity reported rather than guessed); library, CLI and MCP server.
