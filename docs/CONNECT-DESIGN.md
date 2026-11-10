# Krusgraph Connect: getting a source system into Fabric with Fabric's own tools

Round n193. A design text, docs only, nothing implemented here. Written 10 November 2026 from the founder's note of
9-10 November 2026. It adds the missing first step to the Lifecycle ([LIFECYCLE-DESIGN.md](LIFECYCLE-DESIGN.md)):
before a plan can be checked, the source must be in a lakehouse.

The goal in one line: **a manufacturer with an ERP and no analytics gets its ERP tables into its own Fabric, through
Fabric's own tools, set up step by step in the Krusgraph item.**

The principle:

- **Krusgraph never moves customer data.** Fabric does: mirroring, Copy job, a pipeline, or a notebook, all running in
  the customer's tenant, on the customer's capacity, under the customer's identity.
- **Krusgraph prepares and configures.** It picks the right Fabric tool, checks the prerequisites, shows a dry run of
  what it will create, creates it as the signed-in user, and reads back the status.
- **No AI.** Krusgraph for Fabric keeps its "no AI" default (`offering.py`, `NO_AI`). Every choice in Connect is a rule
  or a table in this text, not a model's guess.

How to read this text (the same rules as the Lifecycle text):

- **Today** names the file that does it now. **New** is work for a later round.
- Effort is **S** (a day or less), **M** (a few days), **L** (a week or more).
- **Verified** means a public page was opened on 10 November 2026 and says it; the page and its date are given.
  Learn pages were read from the public source repository `github.com/MicrosoftDocs/fabric-docs` (branch `main`) or
  from `learn.microsoft.com` itself. Fabric REST scopes were read from `github.com/microsoft/fabric-rest-api-specs`
  (branch `main`, `## Required Delegated Scopes` in each `swagger.json`).
  **Unverified** means we found no public page that says it, or could not open it. Treat it as an open question.
- Only public Microsoft Learn pages, the public Fabric REST specification and the vendors' own public pages are cited.
- Krusgraph is independent. It has no partnership with Microsoft, SAP, Monitor or any other vendor, and this text does
  not imply one. Product names are used only to say what Krusgraph works with.

---

## 0. What exists today and what is new

| Part | Today | File | New in Connect |
|---|---|---|---|
| Reading a SQL Server schema | A plan of one SQL Server schema over ODBC, from your own Python (metadata and counting queries, `db_datareader` is enough) | `sqlserver.py` | The same metadata, but from an export the customer runs and uploads (section 1.5) |
| SAP mirrored through Datasphere | Keys from `_metadata.json`, a drafted source-to-mirror check; nothing connects | `sap_mirror.py`, `docs/SAP.md` | Connect points to Learn's SAP mirroring tutorial as a guided manual step |
| Knowledge packs | `sap` and `younium_salesforce`: tables, keys, links, traps, and per table the `delta` columns a load can watch | `packs/`, `pack_manifest.py`, `docs/PACKS.md` | A pack also says which tables to bring first, in which order, and how to load each (section 3) |
| A manufacturing sample | `mill`: a fictional workshop, 16 tables, planted problems | `mill.py`, `docs/SAMPLE-MILL.md` | Used as the test source for the guided flow |
| A Nordic ERP survey | Business Central verified on Learn; Monitor and others not documented publicly at field level | `docs/NORDIC-PACK-SPIKE.md` | The Monitor pack is built from a customer's schema export, with permission (section 3.3) |
| Pipelines, run once, schedule | Krusgraph creates notebooks and a pipeline as the user and starts or schedules it | `pipeline.py`, `pipeline_jobs.py` | A load step in front of silver, or a Copy job the pipeline waits for |
| Run results | Job instances, Fabric's error text, a small error catalogue | `run_results.py` | The same for Copy job and mirroring status |
| A preflight with plain cards | Rayfin checks the tenant setting first and shows an on, off or "could not check" card | `rayfin_app.py` (`preflight`, `off_card`) | The same pattern for capacity, gateway and connection (section 2.3) |
| Drift and health | Snapshot and drift against the plan; health per run is designed | `drift.py`, `monitor.py`, `LIFECYCLE-DESIGN.md` §1 | Freshness per source table feeds the health table (section 4) |
| On-behalf-of sign-in | Every call runs as the signed-in user; no long-lived tokens | `entra.py` | Unchanged. Connect adds read scopes for connections and gateways (section 2.2) |
| Key Vault | The server's own Entra client secret only | `keyvault.py` | Not used for customer secrets. Customer secrets live in the customer's Key Vault or in a Fabric connection |
| Data processing agreement | A draft template | `docs/DPA-DRAFT.md` | A pilot version that names Connect (section 5) |

What does not exist at all today: a step before Plan, any call to the Fabric connection, gateway, Copy job or
mirrored database APIs, and any template for loading a source.

---

## 1. Source types and the Fabric tool for each

```
                     ┌──────────────── customer's tenant and capacity ────────────────┐
 SQL Server (on-prem) ──gateway──► Mirroring  or  Copy job ──►  Lakehouse / mirrored DB │
 Oracle (on-prem)     ──gateway──► Mirroring  or  Copy job ──►  (Delta tables)          │
 REST API only        ───────────► Notebook (pages, watermark) ──► Lakehouse tables     │
 File exports (CSV)   ───────────► Lakehouse Files ──► load notebook ──► tables         │
 Dynamics 365 / Dataverse ───────► Link to Fabric (set up in Power Apps)                │
                     └────────────────────────────────────────────────────────────────┘
                                         ▲
                Krusgraph item: picks the tool, checks, dry run, creates as the user,
                reads status. Never sees a row.
```

### 1.1 Databases: mirroring where it is supported

Fabric mirroring keeps a replica of a database in OneLake as Delta tables, with a SQL analytics endpoint. Learn's
overview lists three kinds: database mirroring, metadata mirroring and open mirroring.

Sources with mirroring, from Learn's table (include `mirroring/includes/mirrored-sources-table.md`, ms.date
2026-08-28). **Verified.**

| Source | Kind of mirroring |
|---|---|
| Azure Cosmos DB | Database |
| Azure Databricks | Metadata |
| Azure Database for PostgreSQL | Database |
| Azure Database for MySQL (preview) | Database |
| Azure SQL Database | Database |
| Azure SQL Managed Instance | Database |
| Dremio catalog (preview) | Metadata |
| Google BigQuery | Database |
| Oracle | Database |
| SAP (via SAP Datasphere) | Database |
| SharePoint List (preview) | Database and metadata |
| Snowflake | Database and metadata |
| SQL Server | Database |
| Open mirrored databases | Open mirroring |
| Fabric SQL database | Database (configured automatically) |

The two that matter most for on-premises manufacturers:

**SQL Server** (Learn `mirroring/sql-server.md`, ms.date 2025-11-05; `sql-server-limitations.md`, ms.date
2026-05-15; `sql-server-tutorial.md`, ms.date 2026-04-03). **Verified.**

| Version | Supported | How changes are read | Notes |
|---|---|---|---|
| SQL Server 2016-2022 (Windows) | Yes | Change Data Capture (CDC) | Tables need a primary key. A DDL change stops mirroring until CDC is re-enabled for that table |
| SQL Server 2017 on Linux | From CU18 | CDC | |
| SQL Server 2019, 2022 on Linux | Yes | CDC | |
| SQL Server 2025 | On-premises only; not in an Azure VM, not on Linux | Fabric's change feed | Needs Azure Arc with the Azure Extension for SQL Server. Not if CDC is on in the database. A DDL change reseeds the table |

More from the same pages:

- A data gateway (on-premises or virtual network) is needed when the instance is not public.
- At most 1,000 tables per mirrored database.
- Some types cannot be in a primary key or clustered index (computed columns, user-defined types, geometry, geography,
  hierarchyid, sql_variant, timestamp, datetime2(7), datetimeoffset(7), time(7)).
- Row-level security and column permissions in the source are **not** carried to the replica.
- **Mirroring is not read-only on the source.** The login needs `SELECT`, `ALTER ANY EXTERNAL MIRROR`,
  `VIEW DATABASE PERFORMANCE STATE` and `VIEW DATABASE SECURITY STATE`. On 2016-2022, setting up CDC needs `sysadmin`
  (the tutorial adds the login to `sysadmin` for a while if CDC is not on yet). CDC writes change tables and holds the
  transaction log until mirroring has read it.

**Oracle** (Learn `mirroring/oracle.md`, ms.date 2025-08-22). **Verified:** Oracle 10 and above, LogMiner enabled,
archive log mode on, the database in write mode, and an on-premises data gateway.

What this means for an ERP database: the ERP vendor and the customer's database administrator must both agree to CDC
on the ERP's database. Many ERP support terms limit changes to their database (Unverified per vendor; ask each one).
So Connect offers mirroring, but **the default for an ERP database is Copy job with a read-only login**. Mirroring is
the choice when the administrator says yes and wants near real-time data.

### 1.2 Databases: Copy job (or a pipeline Copy activity) through the gateway

Copy job (Learn `data-factory/what-is-copy-job.md`, ms.date 2026-09-17; `copy-job-connectors.md`, ms.date
2026-11-09). **Verified:**

- Modes: full copy, or incremental copy. Incremental is **watermark-based** (a column such as `ROWVERSION`, a datetime,
  date, integer, or a string read as a datetime) or **CDC-based** (inserts, updates and deletes).
- Copy job keeps the state of the last successful run. A failed run resumes from there.
- It runs once or on a schedule.
- It reaches sources behind a firewall through an on-premises or virtual network data gateway.
- CDC sources for Copy job (include `copy-job-cdc-replication-connectors.md`, ms.date 2026-09-15): Azure SQL Database,
  Azure SQL Managed Instance, on-premises SQL Server, Oracle, Google BigQuery, Snowflake, a Fabric Lakehouse table and
  three SAP Datasphere outbound targets.
- The ODBC connector's built-in incremental copy works only for the SQL Server family.

Watermark copy needs only `SELECT`. That is why it is the ERP default: nothing in the ERP database changes.

A pipeline Copy activity is the fallback when a source or a setting is not in Copy job. Krusgraph already writes
pipelines (`pipeline.py`); Connect would add a Copy activity in front of silver. Prefer Copy job: it keeps the
watermark state itself.

### 1.3 Sources with only a REST API: a notebook in the customer's Fabric

Many ERPs (Monitor among them, by the founder's note) offer an API and no supported database access. Then:

- Krusgraph writes a **notebook from a fixed template**, like the silver notebook today: no `%pip`, no import of this
  library, the code in the cell verbatim.
- The notebook pages through each endpoint, writes the pages as Delta tables in the lakehouse (`bronze.<entity>`),
  and records the highest watermark per entity in a small state table `krusgraph.connect_state`.
- The next run asks only for rows changed since that watermark (when the API offers such a filter).
- It runs on a schedule, from the pipeline Krusgraph made, as the customer's identity.
- **Secrets never in code.** The notebook reads the API key at run time with `notebookutils.credentials.getSecret`
  from the customer's Azure Key Vault. Learn says: "Never hardcode secrets or credentials directly in notebook code"
  (`data-engineering/notebookutils/notebookutils-credentials.md`, ms.date 2026-09-23). **Verified.** Learn also says
  `getSecret` "uses your current user credentials", so the identity that runs the schedule needs Get on the secret.
  Whose identity that is for a scheduled run: Unverified, test in the first live run.
- Fabric's REST connector for pipelines and Copy job is the alternative when the API is simple (Learn
  `data-factory/connector-rest-overview`, opened, not read in detail: its pagination support per API shape is
  Unverified here).

What the template must handle: page size and the vendor's paging style, rate limits and retry with back-off, a time
limit per run, and a clear failure that `run_results.py` can classify.

### 1.4 File exports

Some customers can only export files (CSV or Excel from the ERP's report tool).

- The customer uploads to the lakehouse's **Files** area (by hand, OneLake file explorer, or a shared folder through a
  Copy job).
- A **load notebook** from a template reads `Files/connect/<entity>/*.csv`, applies the column types from the pack or
  the export, and writes `bronze.<entity>`. A file already loaded is recorded by name and not loaded twice.
- Freshness is the time of the newest file. Stale is easy to see.

### 1.5 The schema export (all database sources)

Krusgraph needs the source's tables, columns and declared keys to plan. It must not read rows to get them. So the
item shows a **read-only metadata query** (`INFORMATION_SCHEMA` and the key catalog views, the same metadata
`sqlserver.py` reads) that the customer's administrator runs and uploads as a file. It holds names and types only.
It feeds the table picker, the pack match and the plan. After the first load, the lakehouse itself is the schema.

### 1.6 SaaS systems with Microsoft's own link

**Dynamics 365 and Power Apps (Dataverse): Link to Fabric.** Learn `power-apps/maker/data-platform/
azure-synapse-link-view-in-fabric` (ms.date 2026-07-06). **Verified:**

- Made in Power Apps, Link data page, **New link > Fabric link**.
- Adds all non-system tables with **Track changes** on; more can be added later.
- The replica is Delta, kept in Dataverse storage (it consumes Dataverse storage), in the same region.
- Today one environment links to one Fabric workspace.

Krusgraph has found no Fabric REST API that creates this link (Unverified that none exists). So it is a **guided
manual step**: the item shows the steps and the link to the Learn page, then finds the resulting lakehouse.

**Other SaaS systems** (Salesforce, Business Central and others): Copy job or a pipeline with Fabric's connector for
that system, where one exists. Which connectors exist changes often; the item reads the list from
`GET /v1/connections/supportedConnectionTypes` rather than from this text.

### Source type → tool

| Source | Default tool | Alternative | Gateway | Krusgraph creates | Effort |
|---|---|---|---|---|---|
| SQL Server on-prem (ERP database) | Copy job, watermark | Mirroring (with the DBA's yes) | Yes | Copy job; mirrored database | M, then M |
| SQL Server on-prem (not an ERP, or DBA agrees) | Mirroring | Copy job | Yes | Mirrored database | M |
| Oracle on-prem | Copy job | Mirroring (LogMiner, archive log) | Yes | Copy job; mirrored database | M |
| Azure SQL, Snowflake, BigQuery, PostgreSQL | Mirroring | Copy job | No | Mirrored database | S each after the first |
| REST API only | Notebook from template | Copy job with REST connector | No (or yes, for an on-prem API) | Notebook, schedule | M |
| File exports | Lakehouse Files + load notebook | Copy job from a file share | Maybe | Notebook | S |
| Dataverse / Dynamics 365 | Link to Fabric | — | No | Nothing (manual step) | S |
| SAP | Mirroring via SAP Datasphere | Copy job from Datasphere outbound | Depends | Nothing at first (manual, Learn tutorial) | S |

---

## 2. What Krusgraph can create, and what stays manual

### 2.1 Documented Fabric REST APIs

From the Fabric REST specification (`fabric-rest-api-specs`, `platform`, `copyJob`, `mirroredDatabase`). **Verified.**

| Action | API | Scope (delegated) | Connect uses it |
|---|---|---|---|
| List gateways | `GET /v1/gateways` | `Gateway.Read.All` | Pick the customer's gateway |
| Is the gateway online | `POST /v1/gateways/{id}/checkStatus` (also per member) | `Gateway.Read.All` | Preflight |
| Create a gateway | `POST /v1/gateways` | `Gateway.ReadWrite.All` | **No.** Only virtual network gateway types can be created this way; an on-premises gateway is installed on a customer machine |
| List connections | `GET /v1/connections` | `Connection.Read.All` | Pick the connection |
| Test a connection | `POST /v1/connections/{id}/testConnection` | `Connection.Read.All` | Preflight |
| Supported connection types | `GET /v1/connections/supportedConnectionTypes` | `Connection.Read.All` | Which sources this tenant offers |
| Create a connection | `POST /v1/connections` | `Connection.ReadWrite.All` | **Not at first** (see below) |
| Create, run, reset a Copy job | `POST /workspaces/{ws}/copyJobs`, `.../jobs/execute/instances`, `.../resetCopyJob` | `CopyJob.ReadWrite.All` or `Item.ReadWrite.All`; run: `CopyJob.Execute.All` or `Item.Execute.All` | Yes |
| Copy job definition | `getDefinition`, `updateDefinition` | as above | Yes. Format: Learn "CopyJob definition" (ms.date 2025-02-03): `jobMode` Batch or CDC, source and destination with a connection id |
| Create a mirrored database | `POST /workspaces/{ws}/mirroredDatabases` | `MirroredDatabase.ReadWrite.All` or `Item.ReadWrite.All` | Yes. Format: Learn "Mirrored database definition" (ms.date 2024-10-24): source types include `MSSQL` (2016-2022), `SqlServer2025`, `Oracle`, `AzureSqlDatabase`, `SAP`, and a connection id |
| Start, stop mirroring | `startMirroring`, `stopMirroring` | as above | Yes |
| Mirroring status, per table | `getMirroringStatus`, `getTablesMirroringStatus` | `MirroredDatabase.Read.All` or `Item.Read.All` | Freshness (section 4) |
| Capacities | `GET /v1/capacities` | `Capacity.Read.All` | Preflight (optional scope) |
| Notebooks, pipelines, schedules | as today | `Notebook.ReadWrite.All`, `DataPipeline.ReadWrite.All`, `DataPipeline.Execute.All` | As today |

**Why Krusgraph does not create connections at first.** For a connection through an on-premises gateway, the
specification says the credentials are "encrypted serialized" JSON, encrypted with RSA using the gateway's public key.
To do that, someone must hold the database password in clear. If Krusgraph's server did it, the password would pass
through Krusgraph. That breaks the principle. So:

- **Round C1:** the customer creates the connection in Fabric (**Settings > Manage connections and gateways**), ideally
  with an Azure Key Vault reference so the password lives in their vault (Learn
  `data-factory/azure-key-vault-reference-overview`, ms.date 2026-06-15: the vault must be reachable, or private with
  a gateway that can see it; the creator needs at least Key Vault Certificate User). Krusgraph lists the connections,
  the user picks one, Krusgraph tests it.
- **Later, maybe:** the item's browser page encrypts the credentials with the gateway's public key, so the password
  goes from the browser to Fabric and the Krusgraph server only sees ciphertext. That needs a security review first.

**Guided manual steps** (Krusgraph shows the steps, links to Learn, then checks the result):

| Step | Who | Why manual |
|---|---|---|
| Install the on-premises data gateway | The customer's IT, on a Windows machine near the database | Installed software; no create API for this type |
| Create a read-only login in the source | The database administrator | Krusgraph never touches the source. The item shows the T-SQL to run |
| Turn on CDC (mirroring of SQL Server 2016-2022) or Azure Arc (2025) | The database administrator | Needs `sysadmin` on the source |
| Create the connection | A gateway admin or the user | See above |
| Store an API key in Key Vault | The customer's Azure admin | Customer's secret, customer's vault |
| Link Dataverse to Fabric | A Power Platform admin | No Fabric API found |
| SAP Datasphere replication flow | The SAP team | Configured in SAP Datasphere |

### 2.2 Scopes

Scopes Krusgraph has today (`deploy/azure_containerapp.py`, `REQUIRED_SCOPES`): `Workspace.Read.All`, `Item.Read.All`,
`Item.ReadWrite.All`, `Notebook.ReadWrite.All`, `DataPipeline.ReadWrite.All`, GraphQL scopes, and Azure SQL
`user_impersonation`.

| New scope | For | Needed from |
|---|---|---|
| `Gateway.Read.All` | List gateways, check status | C1 |
| `Connection.Read.All` | List, test, supported types | C1 |
| `Item.Execute.All` (or `CopyJob.Execute.All`) | Run a Copy job once | C1 (Unverified whether `Item.ReadWrite.All` alone covers the run; the spec names only the execute scopes) |
| `Capacity.Read.All` | Show the capacity's state in the preflight | Optional |
| `Connection.ReadWrite.All` | Create connections | Only if the browser-encryption option is built |

Copy job and mirrored database creation are covered by `Item.ReadWrite.All`, which Krusgraph already has. Each new
scope goes into `REQUIRED_SCOPES` and `docs/SCOPES.md` in the same change, as `docs/SCOPES.md` asks.

### 2.3 Prerequisite checks first: plain cards

Like the Rayfin preflight (`rayfin_app.preflight`): each check answers **ok**, **stop** (with the fix) or **could not
check** (with the reason), and nothing is created until every stop is cleared.

| Check | How | Card when it fails |
|---|---|---|
| The workspace has a capacity | `GET /v1/workspaces/{id}`, `capacityId` | "This workspace has no Fabric capacity. Assign one in workspace settings." |
| The capacity is running | `GET /v1/capacities` (state), if `Capacity.Read.All` | "The capacity is paused. Resume it in the Azure portal." Without the scope: could not check |
| A gateway exists and is online | `GET /v1/gateways`, `checkStatus` | "No gateway is online. Install the on-premises data gateway on a machine that can reach the database (Learn link)." |
| The gateway version is recent | `version` on the gateway | Advice only. Learn's Oracle page asks for the latest gateway |
| A connection exists and works | `GET /v1/connections`, `testConnection` | "The connection failed: <Fabric's text>. Check the login and the firewall." |
| The source is supported for the chosen tool | The source type and version from the export (1.5) against section 1.1 | "SQL Server 2014 cannot be mirrored. Use Copy job." |
| Tables have keys | The export | "12 tables have no primary key. Mirroring (2016-2022) skips them. Copy job with merge needs a key you choose." |
| A watermark column exists | The export, then the pack | "No change column on `orders`. It will be copied in full each run." |
| The user's workspace role | Create's own answer | "You need Member or Admin to create a mirrored database for SQL Server 2025" (from Learn's tutorial) |

The mascots stay calm on a failed check and are glad only when every check passes (`MASCOTS-RENAME-LOVABLE.md`).

---

## 3. ERP packs

### 3.1 What a pack contains

A pack today (`docs/PACKS.md`) holds tables, keys, links with their sources, amounts and their level, traps, and the
`delta` columns per table. For Connect it grows by a **load** section per table:

| Field | Example (SAP, from the existing pack) | Today |
|---|---|---|
| Tables to bring first | Order-to-cash core: `KNA1`, `MARA`, `VBAK`, `VBAP`, `LIKP`, `LIPS`, `VBRK`, `VBRP` | New: `wave` 1, 2, 3 per table |
| Key and links, with their source | `VBAP` → `VBAK` on `MANDT+VBELN`, source cited | Yes |
| KPIs | Order intake, delivered on time, invoiced amount (at the right level) | Partly (amounts and levels); KPI list new |
| Load order | Masters first, then headers, then items | New: derived from the links (targets before sources) |
| Incremental columns | `VBAK.ERDAT`, `VBAK.AEDAT` | Yes (`delta`) |
| Deletes | Whether the source deletes rows or flags them, and how to see it | New |
| Load mode per table | Full for small masters, watermark for documents, CDC where on | New |
| Personal data | Columns the pack names as personal | Yes (`privacy` traps) |

How a pack plugs in:

```
 Connect a source ──► pack match (table names in the export) ──► wave 1 tables pre-ticked
        │                                                          load order, watermark per table
        ▼
 Copy job / mirroring / notebook created for wave 1 ──► first load ──► Plan uses the same pack
                                                                       for keys, links, KPIs
```

The pack is the bridge: the same file says what to load and how to plan it.

### 3.2 SAP

The SAP pack exists (six modules, `docs/SAP.md`). The route into Fabric is Learn's SAP mirroring via SAP Datasphere
(already read in `sap_mirror.py`). Connect adds only the `wave` and load fields and a guided manual step. Effort S.
Licence question for the customer: SAP Datasphere and the replication flow are SAP products under the customer's own
SAP agreement (Unverified what each customer's licence allows; ask SAP and the customer).

### 3.3 Monitor, and any ERP without a public data model

Monitor's public integrations page (https://www.monitorerp.com/integrations/) says, per the founder's note, that
integrations need the **Full Access API**, **API licences** and a **partner API key**. That page could not be opened
from the session that wrote this text: **Unverified here**, recorded from the founder's note.
`docs/NORDIC-PACK-SPIKE.md` found no public field reference for Monitor.

So a Monitor pack is built **only** from:

1. **Monitor's own documentation**, as far as it is public or given to the customer under their licence and shared
   with their permission.
2. **A pilot customer's schema export** (section 1.5): names, types and declared keys, no rows, given with written
   permission and covered by the pilot's data processing agreement.
3. **Checks on the customer's rows, run in the customer's Fabric** (the existing check notebook): key uniqueness and
   orphans, counts only.

**Never guessed.** A table, key or link without one of these sources is not in the pack. Every claim carries its
source, as in the SAP pack. Each claim is marked `verified` only when a check on real rows confirms it. The pack's
`sharing` must not be `public-synthetic` if any claim rests on a customer's export; that needs a new value (for
example `customer-permission`) and a decision on whether such a pack may be shipped to other customers at all
(Unverified legally; ask the customer and a lawyer).

Two routes for Monitor data, and the questions to ask first:

| Route | Needs | Open questions for the vendor and the customer |
|---|---|---|
| The API, via the notebook template (1.3) | Full Access API, API licences, a partner API key (founder's note) | Is a partner key per integrator or per customer? Does Krusgraph need one if the code runs in the customer's Fabric under the customer's key? What does an API licence cost? Rate limits? |
| The database, via Copy job (1.2) | Read access to the ERP's database, if the customer hosts it | Does the licence or support agreement allow direct reads? Which database engine and version? (Unverified) |

Ask the same for every ERP before a pack: is there a public data model, is direct database reading allowed, what does
API access cost, and is a partner agreement needed. Krusgraph does not claim a partnership with any vendor, and
applying for a partner key is a business decision for the founder.

### 3.4 Effort

| Work | Effort |
|---|---|
| Pack schema: `wave`, load mode, deletes, KPIs; manifest and tests | M |
| SAP load fields | S |
| Monitor pack from one customer's export | L (depends on access) |

---

## 4. Incremental loads and freshness

| Tool | How it loads only changes | Where the state lives | Freshness signal |
|---|---|---|---|
| Mirroring | CDC (SQL Server 2016-2022), change feed (2025), LogMiner (Oracle) | Fabric | `getTablesMirroringStatus`: per table `status`, `processedRows`, `lastSyncDateTime` (Learn `mirroring/mirrored-database-rest-api.md`, ms.date 2026-03-18, Verified) |
| Copy job, watermark | Rows with a watermark above the last run's | Copy job's own state | Job instances (end time, status); the Delta table's last commit |
| Copy job, CDC | Source CDC | Copy job | As above |
| Notebook (API) | The API's "changed since" filter, if any | `krusgraph.connect_state` (entity, watermark, run id, rows) | The state table and the last commit |
| Files | New file names | `krusgraph.connect_state` | The newest file's time |

Choosing the watermark column, in this order: a declared `rowversion`; a pack's `delta` column; a column named like a
change date that the export shows as a datetime. If none, the table is copied in full and the card says so.

Known gaps:

- A watermark sees inserts and updates, not deletes. The pack says how the source deletes. Where it matters, a weekly
  full copy of that table or CDC fixes it.
- A watermark on a creation date (like `ERDAT`) misses later changes. Prefer a change date (`AEDAT`) where the pack
  names one.

How this feeds the Lifecycle (`LIFECYCLE-DESIGN.md` §1.1 and §2):

- The `freshness` check already reads each source table's last Delta commit. With Connect it also knows the load's
  **schedule**, so "stale" means "older than two schedule intervals" without guessing.
- New issue classes for the catalogue (one recogniser each, counts and times only):

| Class | Recognised by | Severity | Fix |
|---|---|---|---|
| `load_failed` | The Copy job or load notebook run failed | red | Re-run once (level 1 safe class); Fabric's text shown |
| `mirroring_stopped` | `getMirroringStatus` not running, or a table in error | red | Show the table and Learn's step (often: re-enable CDC after a DDL change) |
| `gateway_offline` | `checkStatus` fails | red | A person starts the gateway machine |
| `connection_failed` | `testConnection` fails | red | A person fixes the login or password |
| `stale_data` | exists | amber or red | Now names the load and its last success |

---

## 5. Security and privacy

| Rule | How |
|---|---|
| Read-only in the source | Copy job and notebooks use a login with `SELECT` only (or `db_datareader`) on the chosen tables. Mirroring needs more (section 1.1) and is offered only with the database administrator's explicit yes, shown as a separate card |
| Least privilege | One login per source, for analytics only. Not the ERP's own service account. The item shows the exact `GRANT` lines; it never asks for a password |
| Data stays in the customer's tenant | Every load runs in the customer's Fabric, on their capacity. The gateway runs on their machine |
| No row values to Krusgraph | Krusgraph reads names, types, counts, statuses and times. Never rows, never sample values. The schema export is metadata only. This is the same rule as the health table |
| No secrets in Krusgraph | Passwords and API keys live in the customer's Key Vault or a Fabric connection. Krusgraph stores only ids (connection id, gateway id, vault URL and secret name) |
| Personal data | The pack names personal-data columns. Connect can leave them out of the copy (column selection) and says which ones it left out |
| Row-level security is lost | Learn says source RLS and column permissions are not carried to a mirror. The card says so, and that access in Fabric must be set again |
| Audit | Every create and change Connect makes goes into the Lifecycle's audit log (`LIFECYCLE-DESIGN.md` §5.2) |
| Pilots | A data processing agreement before the first pilot connects, based on `docs/DPA-DRAFT.md`, naming Connect, the schema export, and that no rows reach Krusgraph. Read by a lawyer for each side |

---

## 6. The guided flow in the item

A new first step, **Connect a source**, before **Plan**. The mascots guide (roles from `static/mascots.js`):

- **Onto** (green, maps how the data connects) asks what the source is and suggests the tool and the tables.
- **Thinker** (violet, checks and asks) runs the preflight and asks the questions the checks raise.
- **Builder** (coral, creates after a dry run) shows the dry run and creates.

```
 ┌ Connect a source ─────────────────────────────────────────────────────────────┐
 │ 1 Source      Onto: "What do you want to bring in?"                            │
 │               ( ) SQL Server  ( ) Oracle  ( ) An ERP with an API  ( ) Files    │
 │               ( ) Dynamics 365  ( ) SAP  ( ) Other (Fabric's list)            │
 │                                                                               │
 │ 2 Schema      Upload the schema export (query shown, names and types only)    │
 │               Pack found: none / SAP / ...  → wave 1 tables ticked             │
 │                                                                               │
 │ 3 Checks      Thinker:  ✓ capacity  ✓ gateway online  ✕ connection failed      │
 │               "Login failed for user 'krus_read'. Check the password in the   │
 │                connection."   [Open Manage connections]  [Check again]        │
 │                                                                               │
 │ 4 Tables      38 tables · 12 without key · watermark found for 30             │
 │                                                                               │
 │ 5 Dry run     Builder: "This is what I will create in workspace Sales:"       │
 │               + Copy job  krusgraph_load_erp   (watermark, 38 tables)          │
 │                 into lakehouse erp_bronze, every night 02:00                   │
 │               + Schedule on the existing pipeline: after the load              │
 │               Nothing in the source changes. No rows go to Krusgraph.         │
 │               [Create]  [Back]                                                │
 │                                                                               │
 │ 6 First load  Running … 21 of 38 tables · last error: none     → then Plan    │
 └───────────────────────────────────────────────────────────────────────────────┘
```

Rules:

- The dry run lists every item to be created, its name, its workspace, its schedule, and what it will not do.
- Create runs as the signed-in user. Each created item is recorded in `outputs.json` with the plan marker, like the
  other outputs, so the Lifecycle can find it.
- Reopening the item shows the load's status and offers **Update** (dry run first) or **Remove**.
- A manual step shows as a card with numbered steps and a Learn link, and a **Check again** button.

---

## 7. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| The ERP vendor forbids CDC or direct reads | Mirroring or database copy not allowed | Ask first; API route; files |
| API licences and partner keys cost money or take time | Pilot delayed | Ask the vendor early; start with the file route |
| The gateway machine is off or old | Loads fail | Preflight card; `gateway_offline` class |
| A heavy first load slows the ERP | Users complain | Run the first load out of hours; tables in waves |
| Watermark misses deletes | Totals drift | Pack field for deletes; periodic full copy |
| Copy job or mirroring definition formats change | Create fails | Read Learn's definition pages each round; the definition pages are dated 2024 and 2025 |
| Preview features (some mirroring sources, SCD2) | Breaking changes | Use only generally available paths by default; mark preview in the card |
| Capacity cost of loads | Surprise cost | Show the schedule; Learn says mirroring compute and storage are free up to a capacity-based limit |
| A customer's export ends up in a shared pack | Confidentiality breach | `sharing` field, permission in writing, DPA |
| Krusgraph's server sees a password | Breaks the principle | No connection create in C1; browser-side encryption only after review |

---

## 8. Build rounds, in order

1. **C1. The guided flow for SQL Server through a gateway, with Copy job.** The Connect step, the schema export and
   its parser (reusing `sqlserver.py`'s metadata shape), the preflight cards (capacity, gateway online, connection
   test), table picker with watermark choice, dry run, Create Copy job (watermark) into a lakehouse, run once, show
   status. Tested against the `mill` sample on a local SQL Server. New scopes `Gateway.Read.All`,
   `Connection.Read.All`, `Item.Execute.All`. Workload, Engine, Tests, Docs; effort L.
2. **C2. Mirroring.** SQL Server (2016-2022 and 2025) and Azure SQL Database: version checks, the administrator's
   card with the `GRANT` and CDC steps, Create the mirrored database, start it, per-table status. Engine and
   Workload; effort M.
3. **C3. The API notebook template.** Paging, watermark state table, Key Vault through `getSecret`, retry and time
   limit, schedule, error categories in `run_results.py`. The file-export load notebook in the same round. Engine and
   Tests; effort M.
4. **C4. The first ERP pack from a customer's schema.** Pack schema gains load fields; SAP gets them first. Then a
   Monitor pack built from a pilot's export, with written permission and a signed DPA, only after the API licence
   and partner-key questions are answered. SAP pack, Docs, Tests; effort L.
5. **C5. Freshness into the Lifecycle.** `load_failed`, `mirroring_stopped`, `gateway_offline`,
   `connection_failed`, and schedule-aware `stale_data` in the catalogue. Engine and Workload; effort M.
6. **Later.** Dataverse and SAP guided manual steps (S each); browser-side connection encryption (security review
   first).

---

## Sources (opened 10 November 2026)

Microsoft Learn, read from `github.com/MicrosoftDocs/fabric-docs` (`main`) unless a URL is given:

- `fabric/mirroring/overview` (ms.date 2026-08-28) and `mirroring/includes/mirrored-sources-table.md` (2026-08-28).
- `fabric/mirroring/sql-server` (2025-11-05), `sql-server-limitations` (2026-05-15), `sql-server-tutorial`
  (2026-04-03).
- `fabric/mirroring/oracle` (2025-08-22).
- `fabric/mirroring/mirrored-database-rest-api` (2026-03-18).
- `fabric/data-factory/what-is-copy-job` (2026-09-17), `copy-job-connectors` (2026-11-09) and its include
  `copy-job-cdc-replication-connectors` (2026-09-15).
- `fabric/data-factory/how-to-access-on-premises-data` (2026-06-17).
- `fabric/data-engineering/notebook-utilities` (2025-03-31), `notebookutils/notebookutils-credentials` (2026-09-23).
- learn.microsoft.com: `fabric/data-factory/azure-key-vault-reference-overview` (2026-06-15),
  `power-apps/maker/data-platform/azure-synapse-link-view-in-fabric` (2026-07-06),
  `rest/api/fabric/articles/item-management/definitions/mirrored-database-definition` (2024-10-24),
  `rest/api/fabric/articles/item-management/definitions/copyjob-definition` (2025-02-03).

Fabric REST specification, `github.com/microsoft/fabric-rest-api-specs` (`main`): `platform/swagger.json` and
`platform/definitions/connections.json`, `gateways.json` (connections, gateways, capacities, workspaces);
`copyJob/swagger.json`; `mirroredDatabase/swagger.json`.

Not opened or not read in detail (Unverified where used): Monitor's integrations page (from the founder's note only;
not reachable from this session), `fabric/mirroring/sql-server-security` (opened, not read in detail),
`fabric/data-factory/connector-rest-overview` (opened, not read in detail), the capacity `state` values, which
identity `getSecret` uses in a scheduled run, any ERP vendor's licence terms.
