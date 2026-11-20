# Krusgraph Migrate as a Fabric workload of its own (design, Q2)

Round Q2, 16 November 2026, written by a scheduled Claude session with no live user. A design: no workload code was
written, no package was built, nothing was uploaded, and no name was used in a build. Prices, bundles and sales are
business material and are kept outside this repository.

It follows the founder's decisions of 16 November 2026 (section 1), which replace the recommendation of
`QLIK-MIGRATION-PRODUCT.md` section 1 ("not a second workload"). It builds on `WORKLOAD-UX-DESIGN.md` (the six-step
frame of the Model item), `WORKLOAD-PUBLISH.md` (the runbook and the Entra app), `PUBLISHING-READINESS.md` (W11: where
`Krusgraph.Modeler` stands) and `QLIK-MIGRATION-PRODUCT.md` (what is built: the reader, the plan, and since this round
the three tools).

Rules for this text:

- **No AI in the workload.** Every step is a rule, a count or a table lookup, as in the Model item.
- **No claim** that a migration gets faster, cheaper or compliant, and no share of anything "converted".
- **Independent.** Krusgraph is not affiliated with Microsoft or Qlik. Qlik, QlikView and Qlik Sense are trademarks
  of QlikTech International AB; Power BI and Microsoft Fabric are trademarks of Microsoft.
- **Verified** means a page on `learn.microsoft.com` was opened on 16 November 2026 and says it (the list is at the
  end). Everything about Qlik is Unverified, as in Q1. What Microsoft's pages do not say is listed as a question for
  Microsoft in section 7, not assumed.

## The design in five lines

1. One new workload, proposed name `Krusgraph.Migrate`, with one item type, **Migration**: one item per Qlik app that
   is moved. Shown as "Krusgraph Migrate - from Qlik to Power BI"; "Qlik" is in no registered name.
2. The editor has five steps: **Script** (paste or upload the load script, or a plan made locally) → **Plan** →
   **Measures** → **Build** → **Reconcile**. Each step is one of the three tools that exist today, plus the build.
3. Build does not have its own engine: it calls the same server functions the Model item's Create calls, with the
   plan from step 2, and it can hand the plan over to a `Krusgraph.Modeler` Model item where that workload is installed.
4. One frontend host, one server and (if Microsoft allows it) one Entra app serve both workloads; the package, the
   manifest, the item manifest, the attestation and the Workload Hub request are a second set.
5. A second name cannot be registered before the first is: the blocker of `Krusgraph.Modeler` applies twice. Until
   then the product is the three chat tools and the guided page, which need no registration.

---

## 1. The founder's decisions, 16 November 2026

| # | Decision | What it changes here |
|---|---|---|
| 1 | Migrate becomes **its own Fabric workload** | A second `[Publisher].[Workload]` name, package, attestation and Hub request (sections 5 to 7) |
| 2 | Registered name proposal **`Krusgraph.Migrate`**; "Qlik" is not in the registered name because it is a trademark; the display text may say "Krusgraph Migrate - from Qlik to Power BI" | Names in section 2. The display text names Qlik only to say what is read |
| 3 | **Chat (MCP) tools and a guided page are built first**, because workload name registration at Microsoft is still blocked | Built in this round: `qlik_plan`, `qlik_measures_draft`, `qlik_reconcile_draft`; the page is a draft (`MIGRATE-GUIDED-PAGE-DRAFT.md`) |
| 4 | Customers are meant to use **both Migrate and `Krusgraph.Modeler`**; they complement each other | Section 4: Migrate ends where Modeler begins, and neither repeats the other's screens |
| 5 | Load scripts **may go through the hosted server by default**, with a **local-only path** for sensitive customers | Section 3.1 and 3.6: the hosted editor takes the script; a plan made on the customer's machine is the other way in |

`CONTRIBUTING.md` says that the build makes only `Org.Krusgraph` and `Krusgraph.Modeler` and that "no other
`Krusgraph.*` name is used anywhere (the first upload reserves a name for good)". Decision 2 is a **proposal** for a
name; this text uses it as that. The build still refuses it, and it stays so until the founder says the name is final
and a round changes `build_package.py` on that word.

## 2. Names and item types

| What | Value | Rule it must meet |
|---|---|---|
| Workload name (registered) | `Krusgraph.Migrate` (proposal) | `[Publisher].[Workload]`; the workload part is at most 32 characters (Verified: `manifest-workload`). "Migrate" is 7 |
| Development name | `Org.KrusgraphMigrate` | An `Org.` name stays in the own tenant and can never be listed (Verified: `manifest-workload`, `publishing-overview`) |
| Display name | Krusgraph Migrate | `Product.json`; at most what the Hub shows without cutting, to be checked in Fabric |
| Subtitle | from Qlik to Power BI | Names a third party's product descriptively. A trademark line goes on the product page: "Qlik is a trademark of QlikTech International AB. Krusgraph is not affiliated with Qlik." Whether Microsoft's review accepts another vendor's name in a Hub text is a question (section 7) |
| Item type | `Krusgraph.Migrate.Migration` | Item names are unique within a workload; the file name is alphanumeric or hyphen, at most 32 characters (Verified: `manifest-item`) |
| Item display name | Migration | One word, as "Model" is in Modeler |

**One item type to begin with.** A Migration item is one Qlik app on its way to one semantic model. It holds what a
Model item has no place for: the script's reading, the decisions on synthetic keys, the measure drafts with a
person's decisions, the exported KPI values and the comparison runs. A package may hold up to 10 item files
(Verified: `manifest-overview`, `manifest-workload`), so there is room for more; two candidates, neither designed
here:

- **Inventory** (later): many apps at once, read through Qlik's APIs from the customer's machine, to decide which
  apps to move. It needs the Qlik side that Q1 put under "later, and only from the local server".
- A **Tableau** entry is not a second item type: it is a second source in step 1 of the same Migration item, when
  `migration_read.read_twb` has a plan and measures of its own.

### What a Migration item stores

In the item's definition, in the customer's workspace (OneLake), not on Krusgraph's server:

| Part | Content | Note |
|---|---|---|
| `source.json` | The source kind (`qlik_load_script`), the script's length and SHA-256, the tabs' names, when it was read. **Not the script by default** | The founder decides whether the item may keep the script itself (section 8, question 2). Without it a reopened item asks for the script again to re-read |
| `plan.json` | `qlik_plan`'s answer: tables, keys, relationships, each synthetic key with its case and counts, the star schema proposal, what was not read | The same JSON the chat tool returns |
| `decisions.json` | What a person decided: which field carries a link, which table a shared field belongs to, renamed fields, new dimensions accepted | The form of the Model item's review decisions, so that the hand-over in section 4 is a copy |
| `measures.json` | Each expression, its label, its DAX, and per `suggested` or `not_translated` measure what the person did: accepted, rewrote (their DAX), left out | `qlik_measures_draft`'s answer plus the decisions |
| `truths.json` | The exported KPI values per grain, the tolerance, and per run: the statement, the rows returned, the status per row, who accepted which difference and why | W10's truths file; `qlik_reconcile_draft`'s answer plus the runs |
| `built.json` | The ids of what was created (lakehouse tables or notebooks, the semantic model, a Model item when one was made) | For reopening and for the reconcile step |

## 3. The editor flow

```
1 Script  ->  2 Plan  ->  3 Measures  ->  4 Build  ->  5 Reconcile
```

The frame is the Model item's (`WORKLOAD-UX-DESIGN.md` section 3): a step indicator at the top of the canvas, one
primary action in a bar at the foot, details behind "Show", a reopened item landing on the furthest step it reached,
Fluent UI v9 components, the same accessibility rules. Nothing below needs a component the Model item does not have,
except a text area and a file picker in step 1 and an editable table in steps 3 and 5.

### 3.1 Script

| | |
|---|---|
| The user does | Pastes the load script, or uploads a `.qvs` file; or uploads a plan file made on their own machine |
| Krusgraph does | `qlik.read_script`: tables, fields, loads, joins, mapping tables, QUALIFY, synthetic keys, circular references; every statement counted by type |
| The screen shows | "9 tables, 8 linking fields, 3 synthetic keys, 1 circular reference". Behind Show: statements read, control statements listed and not run, included files that were not given, statements not read with their line |
| Primary action | **Read the script** |
| Stops with a reason when | The text is longer than 2,000,000 characters; nothing in it is a load; a `.qvf` is uploaded (never read: a binary format, `QLIK-MIGRATION-PRODUCT.md` 2.1) |

The hosted editor sends the script to krusgraph.com for the call; the server keeps nothing after it (the same
statement the hosted tools make, and it must be in the privacy page before this ships). **The local-only way in**:
the customer runs `qlik_plan` in the local server or the library on their own machine and uploads its JSON answer
here. The script then never leaves the machine; steps 2 to 5 work from the plan. A statement not read stays listed
either way.

### 3.2 Plan

| | |
|---|---|
| The user does | Picks the lakehouse where the tables are landed (or will be), and decides what the rules could not |
| Krusgraph does | `qlik.map_associations` over the landed tables: a one side per association from counts in the rows; each synthetic key in one of five cases; the star schema proposal (`qlik.star_schema`) |
| The screen shows | The map (facts, dimensions, tables in between), with one card per thing to decide: a synthetic key where a person decides, a shared field with no key side, a one-to-one. Each card says the counts and what moves numbers |
| Primary action | **Count in the rows** when the tables are landed; before that, **Continue with names only**, and every line says "by name, not counted" |
| Stops with a reason when | A landed table is missing (the plan lists which, with the name it expects); the counting reaches its limit of queries (the rest is listed as not counted) |

Landing the tables is not this item's work in the first version: the rows come from the original sources through
the customer's own ingestion, or through Krusgraph's Connect where it applies. The step lists, per table, whether
it is a copy of its source or shaped in the script, with the steps to rebuild.

### 3.3 Measures

| | |
|---|---|
| The user does | Pastes the master measures (name and expression), or uploads the measure list; decides per measure that is not `translated` |
| Krusgraph does | `qlik.measures.draft`: each expression labelled translated, suggested or not translated, with DAX or the reason |
| The screen shows | Three groups with their counts. A `suggested` measure shows when it may differ from Qlik. A `not_translated` measure shows the reason and an empty DAX field for the person |
| Primary action | **Draft the measures** |
| Stops with a reason when | Two measures have the same name; a field is in several tables and no rule says which |

No share is shown before the expressions are read, and none is promised. The counts are of this app's expressions.

### 3.4 Build

| | |
|---|---|
| The user does | Chooses what to build, from a dry run |
| Krusgraph does | The same calls as the Model item's Create (section 4): the silver notebook for the tables that are shaped in the script, the semantic model with the plan's relationships, the combined key columns and the accepted measures. A dry run first, as every creating tool |
| The screen shows | The dry run: what would be created, with names. Then the result per item, and "Open in Krusgraph Modeler" where that workload is installed |
| Primary action | **Create** (after the dry run) |
| Stops with a reason when | The plan has an open decision that the model needs; a measure the person accepted does not parse as DAX in Fabric (Fabric's own error is shown) |

Build creates and updates in place and never deletes, as Modeler does. It does not create reports: Qlik sheets are
not read, and a report is a person's work or Modeler's report step on the new model.

### 3.5 Reconcile

| | |
|---|---|
| The user does | Uploads the KPI values exported from the Qlik app (one table per KPI and grain, no selections) |
| Krusgraph does | `qlik.reconcile.draft`: one T-SQL statement per KPI. In the workload the statement is run on the SQL analytics endpoint with the user's token (read-only), and the comparison is filled in |
| The screen shows | Per KPI: equal, different, only in Qlik, only on the migrated tables. A difference is **open** until a count reproduces it; the candidate checks are listed with the plan's own counts (rows without a match, rows a synthetic key kept apart) |
| Primary action | **Compare** |
| Stops with a reason when | A KPI's expression has no rule (it gets no SQL, and the reason); a grouping field has no path from the KPI's table |

The step can be run again after each fix; every run is kept in `truths.json`. It never writes "probably".

### 3.6 What goes where

| Data | Hosted editor (default) | Local-only path |
|---|---|---|
| The load script | Sent to krusgraph.com for the reading; not kept after the call | Stays on the machine; only the plan JSON is uploaded |
| Measure expressions | Sent for the draft; not kept | Drafted locally (`qlik_measures_draft` in the local server); the JSON is uploaded |
| Exported KPI values | Sent for the statement; not kept | The statement is written locally and run by the customer |
| Rows of the landed tables | Counted in Fabric with the user's token; only counts come back | The same |

## 4. Migrate and Modeler: one engine, two workloads

The founder's decision 4 is that customers use both. The split:

| | Krusgraph Migrate | Krusgraph.Modeler |
|---|---|---|
| Starts from | A Qlik load script, its measures, its exported numbers | Tables in a lakehouse or warehouse |
| Decides | What Qlik's associations become; which measures carry over | Keys, relationships, checks, what to build |
| Builds | The first semantic model of the migrated app, with its measures | The API, the ontology, the data agent, the pipeline, the data product, reports |
| Keeps | The truths and the reconciliation runs | The review, the checks, drift |
| Ends | When the KPIs are reconciled | Never: it is the model's home afterwards |

**How Migrate calls the engine.** Three ways were weighed:

| | (a) The same server functions | (b) Hand over to a Model item | (c) Call the other workload's frontend |
|---|---|---|---|
| How | Migrate's routes (`/workload/migrate/...`) call `qlik.*` and then the functions `workload_api.py` calls for the Model item's build (`semantic_model.draft`, `deploy.create_semantic_model`, the silver notebook), with a plan made by `qlik.to_plan` | Migrate writes a Model item definition (the plan's keys, confirmed links and decisions) and creates a `Krusgraph.Modeler.Model` item in the same workspace; the user opens it | Migrate's editor opens Modeler's editor in a dialog or page |
| Needs Modeler installed | No | Yes | Yes |
| New code | Routes and an editor; no engine code | (a), plus the mapping of decisions and one item creation | Unknown |
| Verified possible | Yes: it is our own server | **Not verified**: that a workload may create an item of another workload's type through the public Items API with the user's token, and what the user must have consented to | **Not verified**: nothing read says a workload can open another workload's item editor |

**Chosen: (a) for the build, and (b) as the hand-over when it is verified.** The engine is one Python package on
one server; a Migration item's Create is the Model item's Create with another way of arriving at the plan. So a
customer with only Migrate still gets a semantic model, and a customer with both gets "Open in Krusgraph Modeler"
on the finished plan, without deciding the same thing twice. (c) is not pursued.

What must be shared, so that the two never drift apart:

- One plan type (`infer.Plan`), one review-decision format, one dry-run format. `qlik.to_plan` already returns the
  first; `decisions.json` takes the second (section 2).
- One entitlement check per feature (`entitlements.py`, dormant today): which plan an organisation has is asked
  once, for both workloads. How the plans are cut is business material.
- One frontend build. The hosted editor already reads the workload name from the item it opens
  (`WORKLOAD-PUBLISH.md`, "What the build does now"); a Migration item type is a second route in the same bundle.

## 5. The package and the manifest

A second package beside the first, from the same script:

| Part | For Krusgraph.Migrate | Source of the rule |
|---|---|---|
| `BE/WorkloadManifest.xml` | `WorkloadName` `Krusgraph.Migrate`, `HostingType` `FERemote`, `AADFEApp > AppId`, one `ServiceEndpoint` named `Frontend` | Verified: `manifest-workload` |
| `BE/Migration.xml` | The item type `Migration` | Verified: `manifest-item`. One `WorkloadManifest.xml` and up to 10 item files per package |
| `FE/Product.json` | Display name, description, publisher "Kruse Consulting AB", the support, terms, privacy, licence and attestation links, learning materials | Verified: `manifest-product`; the same checks as `build_package.py check_publishing` |
| `FE/Migration.json` | Where the item can be created, its display name, description and icons | Verified: `manifest-item` |
| `FE/assets/` | Icons (product, favicon, item, small, active), a banner, slide media, `en-US` texts | W11: at most 15 assets of at most 1.5 MB, PNG or JPEG, names of at most 32 characters |
| Frontend URL | `https://workload.krusgraph.com/...`: the same host as Modeler | Verified: `manifest-workload` ("the domain must be a subdomain of your verified Entra domain") |

Changes to the repository when this is built (none made now):

- `workload/scripts/build_package.py`: a third allowed name, an item list per name, and its own texts and assets.
  Today it refuses every `Krusgraph.*` name but `Krusgraph.Modeler`, on purpose.
- `workload/Workload/Manifest/items/MigrationItem/` and an editor under `workload/Workload/app/items/`.
- `fabric_backend/workload_api.py`: the routes of section 4 (a), behind the same token validation.
- CI's `workload` job: build the third package and check it, without uploading.
- `fabric_backend/page_templates/`: an attestation page for this workload, and the privacy page's lines on the
  script.

## 6. Entra and permissions

| Question | Design | State |
|---|---|---|
| Which Entra app | **The existing workload app** (`853a0cf0-...`), with one more Application ID URI, `https://krusgraph.com/workload/workload/Krusgraph.Migrate`, and the redirect URIs for the new item's routes. The server already accepts a list of URIs (`KRUSGRAPH_WORKLOAD_APP_ID_URI`) | Ours to do, **if** Fabric lets two workloads name the same `AADFEApp > AppId`. Not verified (section 7, question 3) |
| Why one app | A customer who uses both consents once, and the server keeps one client id and one secret (`WORKLOAD-PUBLISH.md`, "Decision: keep the dev app") | |
| If it must be a second app | A second client id and secret on the server (`entra.WorkloadConfig` takes one today), a second publisher verification, a second admin consent per customer | A server change, about one round |
| Scopes the editor asks for | `Fabric.Extend` (static, as every workload); for Plan and Reconcile: reading the SQL analytics endpoint; for Build: what the Model item's Create asks for today (items, notebooks, semantic models; the list is in `WORKLOAD-DEV.md`) | No scope that Modeler does not already ask for |
| What Migrate does not need | Any permission on the Qlik side; any scheduled or background execution; any admin-only Fabric API | |
| Allowed tenants | The same list as Modeler (`KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS`) while both are in selected-tenant publishing | |
| Conditional Access, activity id in logs, monitoring | The same open points as Modeler (W11, 2.3 and 2.4); solved once on the shared server | Gap, shared |

## 7. Registering a second name: the ask-list for Microsoft

What Learn says (Verified, 16 November 2026): a workload name has the form `[Publisher].[Workload]`; the workload
part is at most 32 characters; the name is set in the manifest before the upload and confirmed in a dialog at the
first upload; it is then "permanently reserved in your tenant" and "can't be changed"; after registration the Publish
tab takes up to 20 tenant ids. What our tenant shows: the first name, `Krusgraph.Modeler`, was refused at upload on
10 November 2026 with the name-registration error, and nothing in this repository records an answer to the support
ticket.

No page read says anything about a **second** name. So these are questions, to be sent with or after the open
ticket; none of them is answered by an assumption in this design.

| # | Question for Microsoft | Why it matters |
|---|---|---|
| 1 | Can one publishing tenant register more than one `[Publisher].[Workload]` name with the same publisher part (`Krusgraph.Modeler` and `Krusgraph.Migrate`)? Is there a limit, a cost or an approval per name? | The whole second workload |
| 2 | Is the fix for our name-registration error (the open ticket) per tenant or per name? Once `Krusgraph.Modeler` can be registered, can `Krusgraph.Migrate` be registered the same day? | Whether the blocker is met once or twice |
| 3 | May two workloads use the **same Entra application** (`AADFEApp > AppId`) and the **same frontend host**, with one Application ID URI each? Or does each workload need its own app? | One consent or two per customer; one secret or two on our server |
| 4 | Does each workload need its **own Publishing Request Form, attestation and validator run**, or can a publisher's second workload refer to the first one's attestation where the answers are the same (same server, same data handling)? | The amount of work per stage |
| 5 | Does each workload need its **own Marketplace SaaS offer** (requirement 1.3.1), or may one offer's plans cover two workloads of the same publisher? May a plan be a bundle of both? | The listing and the price model; the business side is in the private repository |
| 6 | May a workload's Hub texts name another vendor's product descriptively ("from Qlik to Power BI") with a trademark line, or must the text avoid third-party names? | The display text of decision 2 |
| 7 | Can a workload **create an item of another workload's type** (a `Krusgraph.Modeler.Model` item from Migrate) through the public Items API with the signed-in user's token, when both workloads are installed? | The hand-over of section 4 (b) |
| 8 | Is a reserved name ever released (a workload withdrawn before it was published to any tenant)? | Whether a wrong name is for good in every case |
| 9 | Is there a recommended way for a publisher with two workloads to share one support, terms and privacy page, or must the links differ per workload? | The pages we host |

Until question 1 and 2 are answered, **no build may use the name**: an upload reserves it.

## 8. Decisions for the founder

1. **Is `Krusgraph.Migrate` final as the registered name?** It is a proposal here. The build changes on your word,
   and not before.
2. **May a Migration item keep the load script** in its definition (in the customer's own workspace), or only its
   hash and the plan? Keeping it lets a reopened item re-read without asking; not keeping it is the smaller promise.
3. **One Entra app or two**, if Microsoft allows one? This design assumes one.
4. **Send the ask-list** (section 7) with the open support ticket, or after it is answered?
5. **Tableau in the same item** (a second source in step 1), or a workload of its own later? This design says the
   same item.
6. **The privacy page**: one paragraph on the load script through the hosted server, before the tools are announced
   anywhere. The draft sentence is in `MIGRATE-GUIDED-PAGE-DRAFT.md`.

## 9. Build order, and what each step is tested on

| # | Build | Tested on | Waits for |
|---|---|---|---|
| M1 | The three chat tools and the guided page | Done in Q2 as tools and a page draft: unit tests on synthetic and public scripts | Nothing |
| M2 | One real script: a load script, its master measures and a KPI export from a trial Qlik Sense app with synthetic data | The reader's and the rules' assumptions about Qlik, which are all Unverified today | The founder (a trial app) |
| M3 | The server routes of section 4 (a), behind the workload's token validation | Unit tests with the REST calls mocked, as the Model item's | Nothing |
| M4 | The Migration item's editor in the development workload (`Org.KrusgraphMigrate`), steps 1 to 3 | The workload's own tests; a manual pass in the company tenant | M3 |
| M5 | Steps 4 and 5: build and reconcile in the editor | The demo workspace with synthetic data | M4 |
| M6 | The package for `Krusgraph.Migrate`, the attestation page, CI | CI's package checks | The founder's word on the name; Microsoft's answers 1 to 3 |
| M7 | Upload, selected tenants, the validator, the Preview request | Fabric | `Krusgraph.Modeler` registered first |

## 10. Not verified, and what could make this design wrong

- Every question in section 7. If a publisher may hold one name only, Migrate becomes a second item type in
  `Krusgraph.Modeler` (Q1's shape (a)); the editor, the routes and the item's parts in this text stay as they are,
  and only sections 5 to 7 fall away.
- That the SQL analytics endpoint runs the reconciliation statement as written: it ran on SQLite in the tests, not
  on Fabric.
- Every rule about Qlik (the reader, set analysis, what an export looks like).
- The page load time of a second item type in the same frontend bundle, and Fabric's limits on the item
  definition's size (the plan of a large app).
- That a customer may send a load script to a hosted service under their own agreement with Qlik and their own
  data policy: their decision, and the reason the local-only path exists. Nothing here is legal advice.

## Sources

Verified, opened on learn.microsoft.com on 16 November 2026 (`/fabric/extensibility-toolkit/...`; ms.date / updated
as the page shows):

- `manifest-workload` (2025-12-15 / 2026-09-29): `WorkloadName` as `[Organization].[WorkloadId]`, at most 32
  characters after the dot; `Org.[WorkloadId]` when not publishing to other tenants; `HostingType` `FERemote`;
  `AADFEApp > AppId`; `ServiceEndpoint`; the production domain "must be a subdomain of your verified Entra domain";
  the BE folder holds one `WorkloadManifest.xml` and up to 10 item files.
- `manifest-overview` (2025-12-15 / 2026-09-29): item manifests define each item type; at most 10 item files.
- `manifest-item` (2025-12-15 / 2026-03-04): two files per item (`{ItemName}.xml`, `{ItemName}.json`); item names
  unique within a workload; file names alphanumeric or hyphen, at most 32 characters.
- `manifest-product` (2025-12-15 / 2026-03-04) and `publishing-requirements-workload` (2026-02-24 / 2026-03-11):
  as W11 read them (`PUBLISHING-READINESS.md`); not read again line by line.
- `publishing-overview` (2026-04-08 / 2026-09-29): the name confirmed at first upload, "permanently reserved in your
  tenant after confirmation and can't be changed"; Publish to selected tenants, up to 20 tenant ids; up to 10
  minutes to show.

Not found on any page read: a second workload name per publisher, a shared Entra app or Marketplace offer for two
workloads, item creation across workloads. Unverified: everything about Qlik.
