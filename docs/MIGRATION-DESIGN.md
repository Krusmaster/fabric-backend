# Migrations, coached: existing platforms, ERP moves, Qlik Sense and Tableau (design, W7)

Round W7. A design text, with one small proof in code (part 6). Written 15 November 2026 by a scheduled Claude session
with no live user, from the founder's note of 11 November 2026: many customers already have a platform with notebooks
and data products; others move from one ERP to another, or from SAP ECC into SAP S/4HANA; many move from Qlik Sense
or Tableau to Power BI and Rayfin. Krusgraph should suggest data products, validate truths, and coach the customer
through the move, partly with the mascots and partly with people (Kruse Consulting).

W7 was claimed on 12 November 2026 and not written that day. W10 (`MIGRATION-PLATFORMS-DESIGN.md`, 12 November) was
written against W7's claim line. This text is now the base W10 asked for. Who owns what:

| Subject | Where it is designed |
|---|---|
| The journey a customer sees (seven phases), the chat path, the mascots' sentences, where a person steps in | here, parts 0 and 5 |
| A platform that is already in Fabric (part 1); ERP to ERP and ECC to S/4HANA (part 2); Tableau (part 4) | here |
| The reader for a Qlik load script and a Tableau workbook | here, part 6, and `fabric_backend/migration_read.py` |
| Databricks and Snowflake into Fabric; the truths file; the ten difference rules D1 to D10; the two-sided check | W10, sections 1 to 4. Used here, not repeated |
| What is done with the Qlik reader's output: the four synthetic key cases, set analysis to DAX, section access | W10, part B. Part 3 here adds the chat path and what the reader returns |

It also builds on `CONNECT-DESIGN.md` (how a source gets into OneLake), `LIFECYCLE-DESIGN.md` and `product_life.py`
(the data product page, retire), `PROMOTE-DESIGN.md`, `DOMAINS-DESIGN.md` (owner, contract, services),
`WORKLOAD-UX-DESIGN.md` (the item's six steps), `SAP.md` and `SCOPES.md`. None of them is edited.

Rules for this text:

- **No AI in Krusgraph for Fabric** (`offering.py`). Every step is a rule, a count or a table lookup. Where a
  translation is not certain it is a *suggestion* that names its rule, and a person decides. The chat's own model
  (Claude, in the customer's client) reads Krusgraph's answers; it is not part of Krusgraph.
- **No speed or compliance claims.** Nothing here says a migration gets faster, cheaper or compliant.
- **Independent.** Krusgraph is not affiliated with Microsoft, SAP, Qlik or Tableau (Salesforce). Nothing here is
  SAP-certified or tested by SAP, and the text never says "compatible". Every SAP mapping in part 2 is marked
  **proposed, not tested on a customer**.
- **Verified** means the public page was opened on 15 November 2026 and says it; the page is in Sources with the
  date the page itself shows. **Unverified** means the page could not be opened. This session's network reached
  `learn.microsoft.com` and `raw.githubusercontent.com` only. `help.qlik.com`, `qlik.dev`, `help.tableau.com` and
  `help.sap.com` were blocked. **Every Qlik and SAP fact here is therefore Unverified**, and every Tableau fact
  except the file layout read in Tableau's own public repository. They are written from public knowledge of those
  vendors' documentation and must be read on the page before anything public rests on them.
- **Today** names the file or tool that does it now. **New** is work for a later round. A round is one claim and one
  release of the usual size.

---

## 0. One journey, seven phases, one way to walk it in the chat

### The phases

The same seven phases for every kind of move. The customer sees these words and no others.

| # | Phase | The question it answers | Reads or writes | Who decides |
|---|---|---|---|---|
| 1 | **Inventory** | What do we have, and what uses it? | reads | a person confirms the scope |
| 2 | **Map** | What does each old thing become? | reads | a person accepts or rejects each proposal |
| 3 | **Check** | Do the keys and links hold in the rows? | reads (counts only) | nobody; it is a count |
| 4 | **Build** | The Fabric side: silver, gold, model, report, ontology, app | writes, after a dry run and a confirmation | a person confirms each item by name |
| 5 | **Reconcile** | Does each agreed number match the old one, or do we know why not? | reads | the owner of each number signs |
| 6 | **Switch over** | Are we ready to stop looking at the old one? | reads | the platform owner sets the date |
| 7 | **Retire the old** | What is switched off, in which order? | Krusgraph writes nothing on the old side, ever | the platform owner |

How this lines up with W10's nine steps for a platform source: Inventory is its step 1; Map and Check are steps 2
and 4; landing the data (step 3) is Fabric's own work between Map and Check; Build is steps 6 to 8; Reconcile is
step 5; Switch over and Retire are step 9. Learn's own migration series has five stages (requirements, planning,
proof of concept, create and validate, deploy) and names two things this design keeps: the new report's data must
match the old "Or—if there's a difference—be able to explain why", and the old and new run in parallel for a time
that is "commonly 30-90 days" (Verified [L1] [L2] [L3]).

### The chat path: buttons first, numbers as the fallback

One new tool, **`migrate`**, built the way `start` is (`start_flow.py`, n219): a stepper that reads nothing and calls
nothing itself. Its answer says where the customer is, what was chosen, and the next steps as calls of existing
tools. It is stateless: what was chosen travels in the arguments.

- **With MCP Apps on** (`KRUSGRAPH_MCP_APPS`, n119 and n218): each next step is a button on the card. A click runs
  the tool through the host; where the host cannot, the button puts its exact sentence (`say`) in the chat
  (`mcp_apps_next.py`). None of the buttons writes; a creating tool is offered only as its dry run.
- **In a text-only client**: the same steps as a numbered list, each with its sentence, ending "Reply with the
  number." The number is the fallback, never the only way: the sentence beside it can be typed or pasted.
- **Every answer** says which phase it is, whether the step reads or writes, and what was not read.

The first card, for every kind of move:

```
Migrate with Krusgraph. Phase 1 of 7: Inventory. This step only reads.
What are you moving?
1. We already have a platform in Fabric          -> "Take inventory of workspace <name>"
2. We are moving ERP (one ERP to another, or SAP ECC to SAP S/4HANA)
                                                  -> "Compare the old and the new ERP schema"
3. We are moving from Qlik Sense                  -> "Read this Qlik load script"
4. We are moving from Tableau                     -> "Read this Tableau workbook"
5. Show me the journey on the synthetic shop      -> "Show the migration on the sample"
Reply with the number.
```

Option 5 is the same path on synthetic data (`demo.py`, `seed.py`, and the two files in `tests/fixtures/w7/`), so a
customer can see every phase without connecting anything.

---

## 1. An existing platform in Fabric

### The user's job

A data lead who already runs lakehouses, notebooks, pipelines and a semantic model in Fabric: "Tell me whether what
we built holds together, list it as a data product with an owner, and do not rebuild or touch any of it. Then tell
me what you would improve."

### The chat path

| # | Phase | Button (and the numbered fallback's sentence) | Tool | Today or new |
|---|---|---|---|---|
| 1 | Inventory | "Take inventory of workspace Sales" | `platform_inventory` | **New.** `list_workspaces`, `list_sources`, `list_tables` today |
| 2 | Inventory | "Show what builds on these tables" | `lineage` | Today for GraphQL APIs, semantic models, views and data agents; notebooks and pipelines **new** |
| 3 | Map | "Show the keys and links of schema gold" | `plan_backend` | Today |
| 4 | Check | "Check them against the rows" | `validate_plan` (with `profile`, `sql_sums`) | Today |
| 5 | Check | "Compare the semantic model Sales with the plan" | `compare_semantic_model` (with `check_data`) | Today |
| 6 | Map | "Keep what I decided as a file" | `review_plan` | Today |
| 7 | Build | "Register these items as a data product" (a dry run first: the list, and "nothing in Fabric changes") | the Data product page's new **Register** | **New** |
| 8 | Build | "Show what could be improved" | `platform_inventory` with `improve` | **New**; every line points at a tool that exists |
| 9 | Reconcile | "Compare these numbers before and after the change" | W10's truths file | New in W10 (B3); only needed when an improvement is applied |

Phases 6 and 7 do not apply: nothing is switched over and nothing is retired.

### Existing tools reused, as the code has them

- **`validate_plan`** (`server.py`): keys unique and non-null, references without a target, as counts with an
  evidence state per item; `tables=` scopes it; past the time budget it returns "not checked (time)" and a
  `resume_from`. Never row values.
- **`compare_semantic_model`**: an existing model against the plan: missing, contradicted and extra relationships,
  cardinality, direction, active, stale columns, suggested measures. It reads the model's TMDL through Get Semantic
  Model Definition, **or takes the TMDL files as input (`tmdl`), which needs no permission at all**. That second
  door is the pattern for every reader in this design.
- **`lineage`**: which objects build on a table, tables nothing uses, and with `runs=` a pipeline's or notebook's
  latest runs (`run_results.py`).
- **`review_plan`**: the decisions as a file the customer keeps.
- **`notebook.py`**: `parse()` already reads Fabric's notebook source format into cells.
- **`product_life.py`**: `status` (built, missing, changed outside, pending), `leftovers`, `adopt`, `retire`.
  **Adopt today takes only an item whose description carries Krusgraph's own plan marker for the same plan.** It
  cannot take an item someone else built. That is the gap.

### What is new

1. **`platform_inventory` (read-only).** One row per item in the workspace (List Items), with its type and, where a
   definition can be read, what it reads and writes:
   - *Notebook*: the definition in `fabricGitSource` format, never `ipynb`: an `ipynb` file can carry cell outputs,
     and outputs can hold row values. Table names are found by fixed patterns (`saveAsTable`, `spark.read.table`,
     `spark.table`, `FROM` and `INTO` in `spark.sql` and `%%sql` cells, the default lakehouse in the metadata). Each
     edge is marked **named in the code**, the wording `lineage.py` already uses for data agents; it is not "certain".
     A notebook where no pattern matched is listed as such and counted.
   - *Pipeline*: the definition's activities: which notebook each runs, a copy activity's source and destination.
   - *Semantic model, GraphQL API, view, data agent*: as `lineage.py` reads them today.
   - *Schedules and last runs*: List Item Schedules and List Item Job Instances.
   Where a definition cannot be read (no write permission, an encrypted sensitivity label), the item is listed with
   "definition not read" and the reason. The same files may be given as input instead, from the workspace's Git
   repository, as `tmdl` is today.
2. **Register: an existing item listed in a data product without being rebuilt.** A new list `registered[]` in the
   Model item's `outputs.json`, beside `created[]`: the item's id, type, name, a role (source, transform, model,
   report), when and by whom. The rules, each with a test:
   - **Krusgraph never updates, renames, schedules, runs or deletes a registered item.** `retire` and `DELETABLE`
     apply to `created[]` only.
   - **Krusgraph writes nothing to the item.** No marker in its description, no tag. Registering changes one file:
     the Model item's own `outputs.json`.
   - **A Create never takes a registered item's name.** n207's rule already refuses an item someone else made
     (`workload_api._adoptable`, `_ownership`): a registered name is refused the same way, and the person picks a
     new name. Nothing is overwritten.
   - `status` reports a registered item as present, missing or changed outside, as it does for built items.
   - One item may be registered in one data product per workspace; a second registration is refused with the name of
     the product that has it.
3. **Improvements, as a fixed list.** Each is a condition with a count, and each points at a draft. Nothing is
   applied.

   | Condition | From | The draft it points at |
   |---|---|---|
   | A model relationship the rows contradict | `compare_semantic_model(check_data=true)` | the corrected relationship, as TMDL text |
   | A key that is not unique, or NULL | `validate_plan` | `silver_notebook_draft` (one row per key, quarantine) |
   | A total that doubles through a join in a view | `validate_plan(sql_sums=true)`, `amounts.py` | the view's line, and the measure at the right level (`level_measures.py`) |
   | A table nothing reads | `lineage` | none; a question for the owner |
   | A table a notebook writes and nothing checks | `platform_inventory` | `create_drift_monitor`'s dry run |
   | A pipeline with no schedule, or failing runs | List Item Schedules, `run_results.py` | Fabric's error text and the next step `run_results.py` already gives |
   | A stale column in the model, a missing measure | `compare_semantic_model` | `semantic_model_draft` |
   | References without a target above a share the owner sets | `validate_plan` | `validate_plan(fixes=true)`'s proposal |

### Learn APIs and scopes (all opened 15 November 2026)

| Operation | What for | Delegated scope | Permission on the item | Does the hosted app have it? | Page (updated) |
|---|---|---|---|---|---|
| Core, List Items | the inventory's rows | `Workspace.Read.All` or `Workspace.ReadWrite.All` | "viewer workspace role" | yes | [L4] (12 Nov 2026) |
| Core, Get Item Definition | any definition | `Item.ReadWrite.All` or `<itemType>.ReadWrite.All` | "read and write permissions for the item" | yes (`Item.ReadWrite.All`) | [L5] (10 Nov 2026) |
| Notebook, Get Notebook Definition | notebook cells; "Supported format: ipynb and fabricGitSource. If no format is provided, fabricGitSource is used" | `Notebook.ReadWrite.All` or `Item.ReadWrite.All` | read and write on the notebook | yes | [L6] (19 Oct 2026) |
| Data Pipeline, Get Data Pipeline Definition | activities | `DataPipeline.ReadWrite.All` or `Item.ReadWrite.All` | read and write on the pipeline | yes | [L7] (19 Oct 2026) |
| Semantic Model, Get Semantic Model Definition | TMDL | `SemanticModel.ReadWrite.All` or `Item.ReadWrite.All` | read and write on the model | yes; used today | [L8] (19 Oct 2026) |
| Report, Get Report Definition | which model a report reads | `Report.ReadWrite.All` or `Item.ReadWrite.All` | read and write on the report | yes | [L9] (19 Oct 2026) |
| Job Scheduler, List Item Schedules | is it scheduled | `Item.Read.All` or `Item.ReadWrite.All` (or the specific type) | not stated on the page | yes | [L10] (10 Nov 2026) |
| Job Scheduler, List Item Job Instances | last runs; "a limit of 100 recently completed" | as above | not stated on the page | yes; used by `lineage(runs=)` | [L11] (15 Sep 2026) |
| Lakehouse, List Tables | table names without SQL | `Lakehouse.Read.All` or `Lakehouse.ReadWrite.All` | not stated | **no, and not needed**: tables are read on the SQL analytics endpoint | [L12] (15 Sep 2026) |
| OneLake Shortcuts, List Shortcuts | which tables are shortcuts to elsewhere | `OneLake.Read.All` or `OneLake.ReadWrite.All` | "read permissions for the item" | **no.** Left out of the first build; a shortcut shows as a table | [L13] (10 Nov 2026) |
| Admin, List Items | a tenant-wide inventory | `Tenant.Read.All`; "must be a Fabric administrator" | | **no, and not asked for** | [L14] (12 Nov 2026) |

**The catch, said to the customer before the first read:** Fabric has no read-only way to read a definition. Get
Definition takes a ReadWrite scope and the caller needs write permission on the item, although the call changes
nothing [L5]. A person with the Viewer role gets the list of items and no definitions. The other door is the files.
A definition under an encrypted sensitivity label needs the right to remove the label [L5]; Krusgraph does not ask
for that and lists the item as not read. **No new scope is needed for part 1.**

### What stays manual

Deciding which items belong to the product, and who owns it. Anything about what a notebook's code *means*: the
inventory finds table names by pattern and nothing else. Fixing a notebook, a pipeline or a report someone else
built. Permissions. Deleting anything that is not Krusgraph's own.

### Risks

| Risk | What we do |
|---|---|
| A table name built at run time is not found by a pattern | The edge wording is "named in the code"; notebooks with no match are counted and listed; nothing is called complete |
| A read needs write permission, which reads as "Krusgraph wants to change my notebooks" | Said before the first call, with the Learn sentence; the files-as-input door needs no permission |
| An item registered and later rebuilt by accident | The never-overwrite rule above, with a test per item type |
| A registered item is renamed or deleted by its owner | `status` says changed outside or missing; Krusgraph does nothing about it |
| A large workspace | One time budget per call (`budget.py`), "not read (time)" with a resume point, as `validate_plan` has; the platform limit is 500 calls a minute [L5] |
| Notebook code may hold a secret or a name | Only table names and the cell count leave the reader; cell text is never returned |

### Estimate

| Build | Rounds |
|---|---|
| P1 `platform_inventory`: List Items, the notebook and pipeline readers, schedules; fake Fabric in tests | 1.5 |
| P2 Register on the Data product page: engine rules, editor, tests for never-overwrite | 1 |
| P3 The improvement list | 1 |
| P4 `migrate` stepper and card (shared by all parts) | 1 |
| One live run on synthetic data, by the founder | 0.5 |

---

## 2. ERP to ERP, and SAP ECC to SAP S/4HANA

**Everything in this part is proposed, not tested on a customer.** No SAP system was read. The SAP facts are public
knowledge of SAP's documentation and are Unverified: `help.sap.com` could not be opened.

### The user's job

A head of controlling and a data lead, with a go-live date: "Our reports must show the same numbers the week after
cutover as the week before. Which old table became which new one, and where do the totals differ?"

Krusgraph does not migrate the ERP. The ERP project moves the data with the vendor's own tools. Krusgraph works on
the **analytics side**: the copies of the old and the new system in OneLake.

### The chat path

| # | Phase | Button | Tool | Today or new |
|---|---|---|---|---|
| 1 | Inventory | "Show which SAP tables the old schema has" / "...the new schema has" | `sap_pack_draft` once per schema | Today: recognised tables, keys with the client, the variant hint (`ecc` or `s4hana`), missing tables, traps |
| 2 | Map | "Compare the old and the new ERP schema" | `erp_map` | **New**: the mapping table below against both schemas |
| 3 | Check | "Check the keys and links of the old schema" / "...of the new schema" | `validate_plan` on each | Today |
| 4 | Reconcile | "Count both sides" | W10's two-sided check (B1) with the reconciliation rows below | New in W10; the rows are **new** here |
| 5 | Reconcile | "Compare the agreed totals before and after" | W10's truths file (B3) | New in W10 |
| 6 | Build | "Build the data product on the new schema" | the existing path (`start`, steps 4 to 9) | Today |
| 7 | Switch over | "Show the cutover sheet" | W10's cutover sheet (B5) | New in W10 |
| 8 | Retire | "Show what still reads the old schema" | `lineage` on the old source | Today |

### The mapping, public facts only: proposed, not tested on a customer

| Old (ECC) | New (S/4HANA) | What Krusgraph can count on both sides | In the SAP pack today? |
|---|---|---|---|
| Customer `KNA1`, supplier `LFA1` as the leading master data | **Business Partner**: `BUT000` leads; `KNA1` and `LFA1` remain and are linked through `CVI_CUST_LINK` and `CVI_VEND_LINK` | customers and suppliers per client; customers without a partner link; partners with two customers | yes: `business_partner.json` has `BUT000` and both link tables |
| FI line items `BSEG`; index tables `BSIS`, `BSAS`, `BSID`, `BSAD`, `BSIK`, `BSAK`; totals `GLT0`, `FAGLFLEXT`; CO line items `COEP` | **`ACDOCA`**, the universal journal, with header `BKPF` | documents per company code and fiscal year; the sum per account, period and currency | yes: `BSEG` marked `ecc`, `ACDOCA` marked `s4hana` |
| Unsigned amounts with a debit/credit indicator (`SHKZG`) | signed amounts in `ACDOCA` | the sum with the sign applied on the old side | yes: the pack's note and trap (`SAP.md`) |
| One row per posting | one row per posting **per ledger** (`RLDNR`) | the sum filtered to one ledger | yes: the pack's note on `ACDOCA` |
| Material documents `MKPF`, `MSEG` | `MATDOC` | documents per year; quantity per material and plant | **no**: inventory is not in the pack |
| Pricing conditions `KONV` | `PRCD_ELEMENTS` | condition lines per document | yes: `pricing.json` |
| Sales document status in `VBUK`, `VBUP` | status fields on the document tables | none; a mapping note | no; `SAP.md` lists it as a known open point |
| Material number, 18 characters | up to 40 characters | values longer than 18; keys with leading zeros that stop matching (W10's rule D8) | no |

Whether an old table is still readable in a given S/4HANA release as a compatibility view is **not asserted**, as
`SAP.md` already says. For an ERP without a public data model, or a move between two different ERPs, the mapping
table is the customer's own file in the same shape (old table and key, new table and key, the count to compare);
`CONNECT-DESIGN.md` section 3.3 is the base. Krusgraph ships a mapping only where public sources allow.

### Reconcile: counts and totals, before and after cutover

Three runs of the same sheet: before cutover on the old system, after cutover on the new one, and the old against
the new for the migrated periods.

| Row | Old side | New side | Equal means |
|---|---|---|---|
| Master data rows | customers, suppliers, materials, G/L accounts per client and company code | the same | every record arrived |
| Open items at the cutover date | open customer and supplier items: count and sum per company code and currency | the same | the opening position is the old closing position |
| Account balances | sum per company code, account, fiscal year and period, sign applied | the same from `ACDOCA`, one ledger | the ledger balances |
| Documents | accounting, sales and purchasing documents per year | the same, where history was migrated | the scope of history is what was agreed |
| Keys | per key: rows, distinct, NULL; per link: rows without a target (`validate_plan`) | the same | the links still hold |

A row that differs is explained by a named rule only when applying the rule reproduces the number (W10, section
4.2); otherwise it is **open**. Rules that matter here: sign, ledger, the client, a key's length and leading zeros,
currency (a document amount is not a company-code amount), and history that was not migrated on purpose. The last
one is a decision, not a difference: the sheet takes a start date per row.

### Learn pages (opened 15 November 2026)

| What | Says | Page (updated) |
|---|---|---|
| Mirroring SAP | "supports all types of SAP sources offered by SAP Datasphere, including SAP S/4HANA, SAP ECC, SAP BW/4HANA, SAP BW, and SAP Datasphere itself"; it runs through SAP Datasphere, and "SAP Datasphere Premium Outbound Integration pricing applies". It names no tables | [L15] (27 Jun 2026) |
| Copy job for SAP via ABAP Add-On | supports "SAP S/4HANA (all versions), SAP ECC 6.0 EhP 8"; "ECC 6.0 EhP 7 or earlier aren't supported"; reads "tables (transparent, pool, cluster), views, and CDS views"; full and watermark incremental; needs an on-premises data gateway and transports imported into the SAP system | [L16] (5 Oct 2026) |
| Business Process Solutions | Microsoft's own prebuilt data models and reports for SAP finance, sales and procurement on Fabric. Named so that nobody is surprised by it; this design does not use it | [L17] (22 Sep 2026) |

No new scope: both schemas are read on their SQL analytics endpoints, as today (`user_impersonation`). No Learn page
was found on reconciling an ECC and an S/4HANA copy; that is an absence of evidence from two searches.

### What stays manual

The ERP migration itself. Getting both systems into OneLake (`CONNECT-DESIGN.md`; the SAP side needs SAP's own
licences and an SAP administrator). The mapping of customer-specific tables and fields (Z tables). The decision how
much history moves. Chart of accounts changes: when account numbers change, the customer's mapping file says which
old account is which new one; Krusgraph does not guess. Sign-off.

### Risks

| Risk | What we do |
|---|---|
| A mapping row is wrong for the customer's release | Every row carries "proposed, not tested on a customer" and its source; a count that does not match is shown, not hidden |
| It reads as SAP-approved | It never says certified, tested by SAP or compatible; a test keeps those words out |
| Totals differ because the business changed during cutover (new chart of accounts, merged company codes) | The customer's mapping file; rows without a mapping are listed as open |
| Both systems must be readable at once | The sheet says which side is missing; a snapshot of the old side's counts can be kept as a file before it is switched off |
| Personal data in master data | Counts only; no names |

### Estimate

| Build | Rounds |
|---|---|
| E1 `erp_map`: the mapping table as a data file with sources, matched against two schemas | 1 |
| E2 The reconciliation rows on W10's two-sided check (waits for B1) | 1 |
| E3 A customer mapping file (accounts, Z tables) and a kept snapshot of the old side | 1 |
| Reading the SAP pages first, with network access | 0.5 |

---

## 3. Qlik Sense to Power BI and Rayfin

W10's part B designs what is done with a load script once it is read: the four cases of a synthetic key, set
analysis to DAX under three labels, the reconciliation per KPI, apps to reports, section access as a note. This
part adds the chat path and what the reader returns. Every Qlik fact is Unverified.

### The user's job

A BI lead with tens of Qlik apps: "Which data products are hiding in these apps? Where will the numbers differ in
Power BI, and why? What do we build first?"

### The chat path

| # | Phase | Button | Tool | Today or new |
|---|---|---|---|---|
| 1 | Inventory | "Read this Qlik load script" (the script is pasted or attached as text) | `qlik_read` | **Proof today** (`migration_read.read_qvs`, part 6); as a tool, new |
| 2 | Inventory | "Show the tables, keys and synthetic keys" | the same answer, as a card | New |
| 3 | Map | "Suggest data products from these apps" | `qlik_products` | New (rule below) |
| 4 | Map | "Resolve the synthetic keys" | W10 B.3: four cases, decided by counts | New (W10 B6) |
| 5 | Check | "Check the keys against the rows in Fabric" | `validate_plan` on the landed tables, with the script's field names as `keys` and `confirmed` | Today, once the tables are in OneLake |
| 6 | Build | "Draft the semantic model" then the dry runs | `semantic_model_draft`, `create_semantic_model`, `create_report`; for Rayfin, `rayfin_connector` and the App output | Today (the App item is in preview, `RAYFIN-APP.md`) |
| 7 | Reconcile | "Compare the app's numbers with the model's" | W10 B.5 and B8 | New |
| 8 | Switch over, Retire | "Show the cutover sheet" | W10 B5 | New |

### What the reader returns (this is what W10's builds B6 to B9 start from)

`read_qvs(text)` gives: the script's tabs; every table with its fields, its loads (file, database, resident, inline,
with distinct, where and group by flags) and the joins and concatenations done in script; the fields two or more
tables share (the associations, the **keys**); **synthetic keys** (two tables sharing two or more fields); **circular
references** (a loop of three or more tables through different link fields); **link table candidates** (a table
whose every field is shared with other tables); tables linked to nothing; field names that differ only by case;
calculated fields with their expression and line; variables; mapping tables and section access tables (kept out of
the model); what was dropped; and **every statement it did not read, with its line and the reason**.

Two differences from W10's part B, as W10 asked to be told: a loop is reported only for three or more tables, so a
synthetic key is never also reported as a loop; and a link table is a *candidate by shape*, which W10's counts then
confirm or reject.

### Suggesting data products: a rule, not a guess

1. Group apps whose scripts load the same sources (compared by name): one candidate data product per group.
2. Inside a group, tables linked by keys form one product; a table linked to nothing is listed apart.
3. A table that several groups load (customers, products, calendar) is proposed as a **shared entity**
   (`DOMAINS-DESIGN.md` part 4), not copied into each product.
4. The name is the app's or the central table's; a person renames it.

The suggestion says how many apps and tables it rests on and which statements were not read. A person accepts,
merges or splits.

### Validating truths

As W10 section 4 and B.5: a person exports the measure per grain from the Qlik app; the DAX measure is evaluated
over the same grain; equal, or a reason that reproduces the number, or open. Reasons specific to Qlik (W10 B.3):
filter direction, rows without a match landing on the blank row, case, calendar settings, and a synthetic key
resolved as the wrong one of the four cases.

### Learn APIs and scopes

| Operation | What for | Scope | Have it? | Page |
|---|---|---|---|---|
| Power BI, Datasets, Execute Queries In Group | evaluate a DAX measure per grain for the reconciliation | `Dataset.Read.All` or `Dataset.ReadWrite.All`; "dataset read and build permissions"; the tenant setting "Dataset Execute Queries REST API" must be on | **no.** A new opt-in scope, as `DataPipeline.Execute.All` is today | [L18] (5 Feb 2025) |
| ...its limits | "One query per API call"; "Maximum of 100,000 rows or 1,000,000 values per query"; "120 query requests per minute per user"; "Only DAX queries are supported" | | | [L18] |
| The Qlik side | none: Krusgraph takes the script as text and connects to nothing | none | | |

Until that scope is decided, the Power BI side of a reconciliation is also a file: a table exported from the report.

### What stays manual

Getting the script out of the app. Exporting the numbers. Deciding the grain of each fact. Every expression W10
labels "a person decides". Rebuilding sheets as pages. Section access to row-level security: a note, never applied.

### Risks

| Risk | What we do |
|---|---|
| A real script has statements the reader does not know (loops, subroutines, dollar-sign expansion that builds table names) | Listed under not read with the line; the answer's first line counts them; a script that is mostly control flow is said to be so |
| The reader's rules about Qlik are wrong in a detail | They are Unverified and say so in the code; the pages are read before the tool ships; a real exported script (synthetic data) becomes a test file |
| The script holds connection strings, user names (section access) and inline data | Kept out of the answer: tested (part 6) |
| "Krusgraph converts Qlik apps" | Never said. It reads, lists, proposes and checks |
| Pasted script text passes through the hosted server | A founder decision (question 3). W10's default is that the source side runs in the local server |

### Estimate

W10's B6 to B9 (five rounds) stand. This part adds:

| Build | Rounds |
|---|---|
| Q1 `qlik_read` as a tool on the proof, with the card, after the Qlik pages are read | 1 |
| Q2 `qlik_products`: grouping across several scripts | 1 |

---

## 4. Tableau to Power BI and Rayfin

### The user's job

A BI lead with Tableau workbooks: "What is in these workbooks, which calculations will not carry over as they are,
what does the semantic model look like, and do the numbers match?"

### The chat path

| # | Phase | Button | Tool | Today or new |
|---|---|---|---|---|
| 1 | Inventory | "Read this Tableau workbook" (`.twb` text, or a `.twbx` package) | `tableau_read` | **Proof today** (`read_twb`, `read_twbx`); as a tool, new |
| 2 | Inventory | "Show the data sources, joins and calculated fields" | the same answer, as a card | New |
| 3 | Map | "Map the workbook to a semantic model" | `tableau_map` | New (table below) |
| 4 | Map | "Suggest data products" | the rule of part 3, with data sources in place of scripts | New |
| 5 | Check | "Check the join columns against the rows" | `validate_plan`, with the join and relationship columns as `confirmed` | Today, once the tables are in OneLake |
| 6 | Build | "Draft the semantic model" then the dry runs | as part 3, step 6 | Today |
| 7 | Reconcile | "Compare the workbook's numbers with the model's" | W10's sheet, with a crosstab exported from Tableau as the old side | New |
| 8 | Switch over, Retire | "Show the cutover sheet" | W10 B5 | New |

### What the reader returns

Per data source: the tables with their database names, custom SQL (its length only), **joins** with type and
clauses, **relationships** with their columns, the **keys** (every column a join or relationship uses), whether an
**extract** is on, and the **calculated fields** with formula, data type, role and kind: row level, aggregate,
**level of detail** (FIXED, INCLUDE or EXCLUDE, with its dimensions) or table calculation. Also parameters, the
worksheets with the calculated fields and filters each uses, and **traps** (below).

What was read where: a `.twb` is XML and a `.twbx` is a zip holding it; a field is a `<column>` with caption, data
type and role; a calculated field carries `<calculation formula>`; a data source has `<connection>` and `<relation>`
(Verified in Tableau's own public repository [T1]). The layout of joins, relationships, extracts and worksheet
filters is Unverified: written from public knowledge, to be confirmed on a workbook saved by Tableau.

### The mapping to a semantic model and DAX: three labels

The labels are W10's (B.4): **translated by rule**, **suggested** (a draft that names what may differ), **a person
decides** (no draft).

| Tableau | Power BI semantic model or DAX | Label | Why |
|---|---|---|---|
| A relationship between two logical tables | A model relationship on the same column. Cardinality and direction come from the counts (`validate_plan`), not from the workbook | By rule | A regular one-to-many relationship filters from the one side; rows without a match land on a blank row [L19] |
| A join on several columns | One combined key column on both sides (`combined_keys.py`) | Suggested | A Power BI relationship is on one column |
| A physical join | The tables stay apart, with a relationship on the join column | Suggested | A join repeats the one side's measures per matching row; `amounts.py` and `sql_sums.py` find the doubled total today |
| A many-to-many relationship | A bridging table, or a many-to-many relationship | A person decides | Learn: "This cardinality type is infrequently used"; the guidance is a bridging table [L19] [L20] |
| Data blending (two sources linked in one sheet) | Two models or one, the person's choice | A person decides | It is defined per sheet, not per data source |
| An extract, with or without filters | Nothing is carried over; the tables are read in OneLake. An extract filter is listed as a filter the silver layer must repeat | A person decides | The extract file is not opened |
| Custom SQL | A view or a notebook, written by a person; `sql_sums` can check it once it is a view | A person decides | Read as text only |
| An aggregate: `SUM([x])`, `MIN`, `MAX`, `AVG`, `COUNT` | `SUM(T[x])` and so on, as a measure | By rule | One column, one aggregation |
| `COUNTD([x])` | `DISTINCTCOUNTNOBLANK(T[x])` | By rule | `DISTINCTCOUNT` counts BLANK (W10 [S25]); that COUNTD ignores NULL is Unverified |
| A row-level calculation: `[a] * [b]` | A column in silver or gold, then a measure over it; for simple arithmetic `SUMX(T, T[a] * T[b])` | Suggested | Where the calculation lives is a design choice |
| `{ FIXED [d] : SUM([x]) }` | `CALCULATE(SUM(T[x]), ALLEXCEPT(T, T[d]))` | Suggested | `ALLEXCEPT` "Removes all context filters in the table except filters that have been applied to the specified columns" [L21]. Tableau keeps context, data source and extract filters on a FIXED expression (Unverified); the draft removes them too, and says so per sheet |
| `{ SUM([x]) }` (no keyword) | `CALCULATE(SUM(T[x]), REMOVEFILTERS())` | Suggested | The same caveat [L22] |
| `{ EXCLUDE [d] : SUM([x]) }` | `CALCULATE(SUM(T[x]), REMOVEFILTERS(T[d]))` | Suggested | Equal only in visuals that group by `d` |
| `{ INCLUDE [d] : SUM([x]) }` inside an aggregate | An iterator: `AVERAGEX(VALUES(T[d]), CALCULATE(SUM(T[x])))` | Suggested | Its meaning depends on each sheet's dimensions; one measure may not fit every page |
| A table calculation (`RUNNING_SUM`, `WINDOW_...`, `RANK`, `INDEX`, `LOOKUP`) | none | A person decides | It runs over one view's layout |
| A parameter | A slicer on a table of values, or a field parameter | A person decides | No rule covers how it is used |
| Sets, groups, bins | Columns in silver or gold | Suggested | |
| User filters and functions that name the user | Row-level security, as a design note (W10 B.7) | A person decides; never applied | Krusgraph applies no security |
| Dashboards, actions, stories | An inventory; `report.py` builds pages from the plan, not from the layout | A person designs | Learn: focus on "the business question the report is trying to answer" [L1] |

The DAX in the middle column is a draft from a fixed rule. **None of these translations has been run**: not against
Tableau, not against a model. The share of a customer's calculated fields under each label is counted per workbook
in the assessment; no share is promised.

### Traps the reader names (the Thinker's lines in part 5)

- **A FIXED level of detail with a filter outside context**: the field keeps the unfiltered value while the rest of
  the sheet is filtered. The reader lists the sheet, the field and the filter.
- **INCLUDE and EXCLUDE** depend on the sheet.
- **A table calculation** depends on the view's layout.
- **A physical join** repeats measures.
- **Custom SQL** hides its tables.

### Learn APIs and scopes

The same as part 3: Execute Queries [L18] for the Power BI side, opt-in and not held today. The DAX pages behind the
drafts: `CALCULATE` [L23], `ALLEXCEPT` [L21], `REMOVEFILTERS` [L22]. Model relationships and the blank row [L19].
Many-to-many guidance [L20]. Nothing on the Tableau side: the workbook is a file. Learn's migration series does not
name Tableau and mentions no converter (searched 15 November 2026; an absence of evidence).

### What stays manual

Saving the workbook as a file. Exporting the crosstab per KPI. Every row labelled "a person decides". Rebuilding
dashboards. Published data sources on a Tableau server (the workbook only points at them). Tableau Prep flows.

### Risks

| Risk | What we do |
|---|---|
| The XML layout the reader assumes differs in a real workbook, or between versions | Top-level elements it does not know are listed; a real workbook saved by Tableau (synthetic data) becomes a test file before the tool ships |
| A draft measure is taken for a translation | The label is on the measure; "suggested" drafts carry their caveat as a description in the model |
| A FIXED expression reconciles on one sheet and not on another | The reconciliation is per sheet filter set, and the trap names the sheets |
| The workbook holds server names, user names and custom SQL | Kept out of the answer: tested |
| "Krusgraph converts Tableau workbooks" | Never said |

### Estimate

| Build | Rounds |
|---|---|
| T1 `tableau_read` as a tool on the proof, with the card, after the Tableau pages are read and a real file is tested | 1 |
| T2 `tableau_map`: the "by rule" rows and the "suggested" drafts with their caveats | 2 |
| T3 Reconciliation with an exported crosstab (on W10's B3) | 1 |
| T4 Worksheets to pages inventory, and the user-filter note | 1 |

---

## 5. Coaching: the mascots, and where a person steps in

### How the mascots coach

The rules the cards already follow (`mcp_apps_mascots.py`, n136 and n172) stay:

- Each mascot says **one plain sentence per step**, and that sentence is **in the tool's text answer word for
  word**. A text-only client loses nothing. A mascot with nothing true to say is not shown.
- The sentences are **fixed texts with counts filled in from the answer**. Nothing is generated.
- Nobody celebrates unless a check passed. Mascots can be switched off on the card.
- **Onto** says what the data means and how the old concept maps. **The Thinker** says the check and the trap.
  **The Builder** says what is built, switched over or retired, and whether the step writes.

### The sentences per phase

`{n}`, `{m}` and names in braces are counts and names from the answer. A sentence whose count is zero is not shown.

| Phase | Onto | The Thinker | The Builder |
|---|---|---|---|
| 1 Inventory | "I found {n} tables and {m} items that read them." | "{k} items could not be read; they are listed, not skipped." | "This step only reads. Nothing in Fabric changes." |
| 2 Map | "{n} old tables have a proposed counterpart; {m} have none yet." | "Each proposal names its rule. You accept or reject it." | "Nothing is built until the map is checked against the rows." |
| 3 Check | "A key is the column that tells one row from the next." | "{n} keys hold; {m} do not. The counts are in the list." | "I build only from links that hold or that you confirmed." |
| 4 Build | "The semantic model has one table per entity and one relationship per link." | "This is a dry run. It lists every item by name." | "I create {n} items after you confirm them by name. I never overwrite an item someone else made." |
| 5 Reconcile | "A truth is a number its owner has signed, at a stated grain." | "{n} of {m} numbers match. {k} differ; {j} have a reason that reproduces the number; the rest are open." | "Nothing is switched over while a number is open." |
| 6 Switch over | "Old and new show the same agreed numbers for {n} days." | "{m} people still read the old reports." | "You set the date. I change nothing on the old side." |
| 7 Retire | "The old reports' numbers now live in the data product {name}." | "{n} items still read the old source." | "This is a checklist for a person. I delete nothing on the old side." |

### The Thinker's trap sentences, per kind of move

Shown at Inventory or Map when the reader's count is above zero.

| Move | Sentence | From |
|---|---|---|
| Qlik | "{n} synthetic keys: two tables share more than one field name. Each needs one of four fixes before a model can be built." | `read_qvs`, `synthetic_keys` |
| Qlik | "{n} circular references: Qlik loosens one table in a loop; Power BI allows no loop." | `circular_references` |
| Qlik | "{n} field names differ only by upper and lower case. Qlik does not link them." | `names_that_differ_only_by_case` |
| Qlik | "{n} statements were not read. They are listed with their line." | `not_read` |
| Tableau | "{n} FIXED calculations sit on sheets with a filter outside context. Their totals ignore that filter." | `read_twb`, trap `fixed_lod_with_filter_outside_context` |
| Tableau | "{n} calculations depend on the sheet they are on. One measure may not fit every page." | traps `lod_depends_on_the_view`, `table_calculation` |
| Tableau | "{n} joins are made before the numbers are added up. A header amount can count once per line." | trap `physical_join` |
| SAP | "Amounts in the old line items carry no sign; the new journal's do. Totals are compared with the sign applied." | the SAP pack's trap |
| SAP | "The new journal holds each posting once per ledger. Totals are compared for one ledger." | the pack's note on `ACDOCA` |
| SAP | "Proposed, not tested on a customer." (on every mapping row) | fixed |
| Existing platform | "{n} notebooks name no table I can recognise. Their inputs and outputs are unknown to me." | `platform_inventory` |
| Existing platform | "Reading a definition needs write permission in Fabric, although nothing is changed." | Learn [L5] |

The Qlik and Tableau sentences state those tools' behaviour and are Unverified with the rest; each is read on the
vendor's page before it goes on a card. The two files in `tests/fixtures/w7/` give counts above zero for the first
Qlik sentence, the second, the fourth, and all three Tableau sentences.

### Where a person from Kruse Consulting steps in

**An idea for the founder. Internal, not a public offer, not for the site.** It follows `DOMAINS-DESIGN.md` part 7:
the product names the need from a fixed condition, says what the customer can do alone, mentions help once, sends
nothing to Kruse Consulting, and works the same without it.

| Phase | Fixed condition | What the customer can do alone | Where a person fits |
|---|---|---|---|
| 1 Inventory | More than a set number of apps, workbooks or notebooks | Read them one at a time | **Scoping session**: which to move, which to leave, in what order |
| 2 Map | Proposals labelled "a person decides", or tables with no counterpart | Decide in the review file | **Mapping workshop** with the people who own the old reports; the list of open rows is the agenda |
| 5 Reconcile | No truths list yet | Write one from the existing reports | **Truths workshop**: which numbers, at what grain, owned by whom |
| 5 Reconcile | Numbers open after a set number of days | Look at the differing grains | **Root cause review**: usually in the source or the old report's logic, which no tool reads |
| 5 Reconcile | Every number has a match or a reason | The owner signs in the sheet | **Sign-off meeting**: a person from Kruse Consulting chairs, the customer's owner signs. Kruse Consulting never signs a customer's truth |
| 6 Switch over | A date is set | Follow the cutover sheet | **Cutover rehearsal** |
| 7 Retire | Readers remain on the old side | Ask them | none |

---

## 6. The proof: a reader for a synthetic `.qvs` and `.twb`

`fabric_backend/migration_read.py`, with `tests/test_w7_migration_read.py` (38 tests) and three files in
`tests/fixtures/w7/`. Synthetic data only: the shop schema of `seed.py` written by hand as a Qlik load script and as
a Tableau workbook. No customer name. Neither file was exported from Qlik or saved by Tableau.

| | `read_qvs` on `shop.qvs` | `read_twb` on `shop.twb` |
|---|---|---|
| Tables | 8, with their fields | 6 in 2 data sources, with their database names |
| Keys | 6 linking fields, per table | 6 join and relationship columns |
| Synthetic keys / joins | 1 synthetic key (Orders and Shipments share OrderID and CustomerID); 1 circular reference (Customers, Orders, ShipTo) | 2 joins (inner, left) with their clauses; 1 relationship |
| Calculated fields | 6, with expression and line | 6: 3 level of detail (2 FIXED, 1 INCLUDE), 1 aggregate, 1 table calculation, 1 row level |
| Also | a preceding load, a join, a concatenation, a drop, a mapping table and section access kept out of the model, 3 variables, 5 tabs | 1 parameter, 2 worksheets with filters, 1 extract, custom SQL, 6 traps |
| Not read | 3 statements, each with its line and reason | none in the file; unknown top-level elements are listed |

`listing()` prints the same as plain lines. Tested beyond the two files: one small script per rule (two common
fields are a synthetic key and not a loop; three tables on one field are not a loop; automatic concatenation;
Join, Keep, Qualify, Rename, Drop; comments and quotes), refusals (not text, too long, malformed XML, a DOCTYPE or
entity), a `.twbx` package, and that inline rows, connection strings, server names, custom SQL and secret-looking
variables stay out of the answer.

What the proof is not: it is **not a tool** (nothing in `server.py` calls it, and a test keeps it so); it has not
read a file from a real Qlik or Tableau installation; its rules about both products are Unverified; it runs no
expression and compares no number.

---

## 7. All parts: rounds, and what to build first

| Part | New builds here | Rounds | Waits for |
|---|---|---|---|
| 0, 5 | P4 the `migrate` stepper, card and the mascot sentences | 1 | nothing |
| 1 Existing platform | P1, P2, P3 | 3.5 | nothing |
| 2 ERP | E1, E2, E3 | 3 | W10's B1 for E2; the SAP pages |
| 3 Qlik | Q1, Q2 (plus W10's B6 to B9, 5 rounds) | 2 | the Qlik pages; a real exported script |
| 4 Tableau | T1 to T4 | 5 | the Tableau pages; a real saved workbook; W10's B3 for T3 |
| Live proof | one run per part on synthetic data | 0.5 each | accounts only the founder can open |

About 14.5 rounds here, beside W10's eleven. **First: part 1 (P1, P2), then P4.** Part 1 needs no vendor
documentation and no new scope, every customer who already has Fabric can use it, and Register closes a gap the
Data product page has today. After those three rounds a customer can take inventory, check and register an existing
platform from the chat.

## 8. Not to be said on the site until built and tested

That Krusgraph migrates, converts or translates anything. Any share of expressions translated. Any SAP mapping
without "proposed, not tested on a customer". "SAP-certified", "tested by SAP", "compatible". That the mascots
coach a migration (the sentences exist in this text only). That Kruse Consulting offers the sessions of part 5.
That the Qlik or Tableau reader exists as a feature: it is a proof on two synthetic files.

## 9. Open questions for the founder

1. **Register writes nothing to the item** (no marker, no tag): right default? A tag would let other tools see the
   product, but it is a write and needs Contributor [L24].
2. **A new opt-in scope, `Dataset.Read.All`**, so a reconciliation can evaluate the DAX measure itself [L18]. It also
   needs a tenant setting. Without it both sides of a reconciliation are exported files.
3. **May a load script or workbook be pasted into the hosted server?** It passes through krusgraph.com for the call
   and is not stored. W10's default is local only. Part 1 is not affected.
4. **Network for the build rounds**: `help.qlik.com`, `qlik.dev`, `help.tableau.com`, `help.sap.com`. Without them
   Q1, T1 and E1 cannot move a single fact from Unverified to Verified.
5. **Real test files with synthetic data**: one load script exported from Qlik Sense and one workbook saved by
   Tableau, from trial installations on your laptop. The reader's layout assumptions stand or fall on them.
6. **Which ERP pair after SAP?** The mapping file's shape is general; a shipped mapping needs a public data model.
7. **The Kruse Consulting lines** in part 5: shown in the product (once, dismissable, as W8 proposes) or kept out?
8. **Order**: part 1 first, as section 7 proposes, or Qlik first because W10's sales draft leads with it?

## Sources

All opened 15 November 2026. The date in brackets is the page's own "updated" date.

**Microsoft Learn (Verified)**

- [L1] Power BI migration overview (2 Jan 2026): https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-migration-overview
- [L2] ...create and validate content (18 Sep 2026): https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-migration-create-validate-content
- [L3] ...deploy, support and monitor (24 Feb 2026): https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-migration-deploy-support-monitor
- [L4] Core, Items, List Items (12 Nov 2026): https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items
- [L5] Core, Items, Get Item Definition (10 Nov 2026): https://learn.microsoft.com/en-us/rest/api/fabric/core/items/get-item-definition
- [L6] Notebook, Get Notebook Definition (19 Oct 2026): https://learn.microsoft.com/en-us/rest/api/fabric/notebook/items/get-notebook-definition
- [L7] Data Pipeline, Get Data Pipeline Definition (19 Oct 2026): https://learn.microsoft.com/en-us/rest/api/fabric/datapipeline/items/get-data-pipeline-definition
- [L8] Semantic Model, Get Semantic Model Definition (19 Oct 2026): https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/get-semantic-model-definition
- [L9] Report, Get Report Definition (19 Oct 2026): https://learn.microsoft.com/en-us/rest/api/fabric/report/items/get-report-definition
- [L10] Job Scheduler, List Item Schedules (10 Nov 2026): https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/list-item-schedules
- [L11] Job Scheduler, List Item Job Instances (15 Sep 2026): https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/list-item-job-instances
- [L12] Lakehouse, Tables, List Tables (15 Sep 2026): https://learn.microsoft.com/en-us/rest/api/fabric/lakehouse/tables/list-tables
- [L13] OneLake Shortcuts, List Shortcuts (10 Nov 2026): https://learn.microsoft.com/en-us/rest/api/fabric/core/onelake-shortcuts/list-shortcuts
- [L14] Admin, Items, List Items (12 Nov 2026): https://learn.microsoft.com/en-us/rest/api/fabric/admin/items/list-items
- [L15] Mirroring SAP (27 Jun 2026): https://learn.microsoft.com/en-us/fabric/mirroring/sap
- [L16] Copy job for SAP via ABAP Add-On (5 Oct 2026): https://learn.microsoft.com/en-us/fabric/data-factory/copy-job-tutorial-sap-abap
- [L17] Business Process Solutions (22 Sep 2026): https://learn.microsoft.com/en-us/azure/sap/business-process-solutions/about-business-process-solutions
- [L18] Power BI REST, Datasets, Execute Queries In Group (5 Feb 2025): https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries-in-group
- [L19] Model relationships in Power BI Desktop (7 Oct 2026): https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-relationships-understand
- [L20] Many-to-many relationship guidance (2 Jan 2026): https://learn.microsoft.com/en-us/power-bi/guidance/relationships-many-to-many
- [L21] ALLEXCEPT (22 Jan 2026): https://learn.microsoft.com/en-us/dax/allexcept-function-dax
- [L22] REMOVEFILTERS (17 Aug 2026): https://learn.microsoft.com/en-us/dax/removefilters-function-dax
- [L23] CALCULATE (4 Aug 2026): https://learn.microsoft.com/en-us/dax/calculate-function-dax
- [L24] Core, Tags, Apply Tags (15 Sep 2026): "contributor or higher role on the workspace"; `ItemMetadata.ReadWrite.All` or an item ReadWrite scope: https://learn.microsoft.com/en-us/rest/api/fabric/core/tags/apply-tags
- Scopes for the Fabric REST APIs (2 Jul 2025): https://learn.microsoft.com/en-us/rest/api/fabric/articles/scopes

**Tableau's own public repository (Verified for the file layout named in part 4)**

- [T1] tableau/document-api-python, branch master: `README.md`, `tableaudocumentapi/field.py`, `tableaudocumentapi/xfile.py`, `test/assets/datasource_test.tds`: https://github.com/tableau/document-api-python. Tableau calls the Document API "unsupported". No file from it is copied into this repository.

**Unverified: the page could not be opened; written from public knowledge of the documentation**

- Qlik: associations by field name, synthetic keys, circular references, automatic concatenation, Join and Keep, Qualify, mapping loads, section access, case in field names: `help.qlik.com` (see also W10's list U8 to U11).
- Tableau: joins and relationships in the workbook XML, extracts, filters and context, the order of operations for FIXED, INCLUDE and EXCLUDE, table calculations, COUNTD and NULL: `help.tableau.com`.
- SAP: Business Partner and customer/vendor integration, `ACDOCA` and what it replaces, `MATDOC`, `PRCD_ELEMENTS`, the status tables, the material number's length: `help.sap.com` (see also the source table in `SAP.md`).
- Not found on Learn in two searches each: a guide for Tableau or Qlik to Power BI that names the product, a converter, a page on reconciling SAP ECC against S/4HANA. Absence of evidence only.
