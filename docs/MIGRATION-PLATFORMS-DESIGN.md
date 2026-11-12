# Migrating into Microsoft Fabric with Krusgraph: Databricks, Snowflake and Qlik Sense (design, W10)

Round W10. A design text, docs only, nothing implemented here. Written 12 November 2026 by a scheduled Claude session
with no live user, from the founder's line of the same day: "we need to be able to sell how to migrate from Databricks
and Snowflake by using Krusgraph; the same with migrating from Qlik to Power BI by using Krusgraph."

The sales side is [`marketing/MIGRATIONS.md`](marketing/MIGRATIONS.md) (W10). This text is what stands behind it.

It builds on, and does not repeat:

- **W7's `docs/MIGRATION-DESIGN.md`** (existing platforms, ERP to S/4HANA, Qlik Sense and Tableau to Power BI, and a
  small reader for a synthetic `.qvs` and `.twb`). **It was claimed but not on `main`** when this was written (checked
  at claim time and again before the last commit, 12 November 2026). Part B below is therefore written from W7's claim
  line only and must be read against W7's text when it lands; where the two disagree, W7's design of the Qlik reader
  wins and part B's builds are adjusted to it.
- `docs/DATABRICKS.md` (n13): the Databricks adapter in the local server, Draft only.
- `docs/CONNECT-DESIGN.md`: how a source gets into OneLake (mirroring, Copy job, shortcuts) and what Krusgraph creates.
- `docs/SCOPE-REVIEW.md` (S1) section 6: evidence state and coverage; count before claiming.
- `docs/INFERENCE.md` (n226): composite keys carried through as one combined key column.
- `docs/LIFECYCLE-DESIGN.md` and `product_life.py` (n198): retire and clean up.

Rules for this text:

- **No AI in Krusgraph for Fabric** (`offering.py`). Every step below is a rule, a count or a table. Where a
  translation is not certain it is a *suggestion* with its rule, and a person decides.
- **No claim that Fabric is cheaper or faster**, and none about the other platforms. Where a Microsoft page states a
  cost fact it is quoted as Microsoft's statement.
- Krusgraph is independent: not affiliated with Microsoft, Databricks, Snowflake or Qlik. No partnership, no
  certification.
- **Verified** means the public page was opened on 12 November 2026 and says it; the page is in Sources (section 9).
  **Unverified** means the page could not be opened from this session, or no page was found. The session's network
  could reach `learn.microsoft.com` only. `docs.snowflake.com`, `docs.databricks.com`, `docs.getdbt.com`,
  `help.qlik.com` and `qlik.dev` were blocked. Azure Databricks facts were read from Microsoft's copy of the
  Databricks documentation under `learn.microsoft.com/azure/databricks`. **Every Snowflake, dbt and Qlik fact in this
  text is therefore Unverified**: it comes from a search summary of the cited page (marked *summary only*) and must be
  read on the page before it is used in anything public.
- **Today** names the file that does it now. **New** is work for a later round. "Rounds" are build rounds of the usual
  size (one claim, one release).

---

## 1. The method, in nine steps

The same nine steps for every source. What differs per source is how step 1 reads and how step 3 lands.

| # | Step | What Krusgraph does (deterministic, counted) | Output | Today or new | Who decides |
|---|---|---|---|---|---|
| 1 | **Inventory**, read-only | Reads the source's own metadata: catalogs or databases, schemas, tables, views, and for a platform also notebooks, jobs and dashboards. Counts each kind. Reads usage where the platform records it | An inventory file: one row per object with kind, size in rows where cheap, last read, what reads it, and a proposed path (mirror, shortcut, copy, rewrite, leave) with the rule | Tables and columns: today for one schema (`schema.py`, `platforms/databricks.py`). The rest: new (B2, B4) | A person confirms the scope and what is left behind |
| 2 | **Keys and links, source side** | The plan (`infer.py`) and the counting queries (`evidence.py`) in the source's dialect: per key rows, distinct and NULLs; per link rows without a match | The plan with evidence state per key and link (`coverage.py`) | Today on Fabric and, Draft only, on Databricks. Snowflake: new (B2) | A person resolves what the counts leave open |
| 3 | **Land in OneLake** | Nothing. This is Fabric's step: mirroring, a shortcut or a Copy job (sections 2 and 3). Krusgraph proposes the path per table from the inventory | The landed tables | Fabric's own; `docs/CONNECT-DESIGN.md` for what Krusgraph may create later | The platform owner |
| 4 | **Keys and links, landed side** | The same counts on the SQL analytics endpoint. Then the two sets of counts side by side: only what changed | A two-sided sheet per table: rows, per key distinct and NULLs, per link orphans, per column NULL share and distinct count (`profile.py`), before and after | The landed half: today (`validate_plan(profile=true)`). The comparison: new (B1) | Nobody; it is a count |
| 5 | **Validate truths** | A short list of KPIs, each with its query on both sides, computed per agreed grain (month, unit). Equal, or a named reason (section 4) | A reconciliation sheet per KPI: both numbers per grain, the difference, the reason or "open" | New (B1, B3) | The KPI owner signs; a person decides which side is right when the definition itself differs |
| 6 | **Rebuild silver and gold** | From the checked plan: the silver notebook (one row per key, references checked, quarantine), the gold views | Notebooks and views in the customer's workspace | Today (`silver.py`, `gold.py`, `pipeline.py`), on a lakehouse | A person reviews the drafts |
| 7 | **Semantic model, report, ontology** | From the same plan: the TMDL model with relationships and suggested measures, a report, the ontology | Items in the workspace | Today (`semantic_model.py`, `report.py`, `ontology.py`); created live on synthetic data 28 October to 7 November 2026 | A person owns the measures |
| 8 | **Data product with an owner** | The built items listed as one data product with its owner and its checks | The Data product page | First slice today (`product_life.py`); the owner field is design (`docs/DOMAINS-DESIGN.md`) | The owner |
| 9 | **Cutover and retire** | Step 5 re-run on a schedule during the parallel run; a read of who still uses the old objects; a retire checklist | A cutover sheet: days green, readers left, what to switch off in which order | New (B5); retire of Krusgraph's own items today (`product_life.py`) | The platform owner sets the date and switches off. Krusgraph never deletes or stops anything on the source |

Three properties hold at every step:

- **Read-only on the source.** Krusgraph issues metadata queries and counting queries. It creates nothing, changes
  nothing and copies no rows out. The counting queries do use the source's compute (section 5, risk 9).
- **Counts, not rows.** As today (`evidence.py`, `profile.py`): no value leaves the database, with one stated
  exception in section 4 (a difference may need the *key* of the rows that differ, shown to the signed-in person only).
- **The source side runs locally.** The hosted server reads Fabric only and stays that way. The source adapters run
  in the local stdio server with the customer's own credentials, on the customer's or the consultant's machine.

---

## 2. Databricks to Fabric

### 2.1 The paths

| Path | What Microsoft's documentation says | Use it for | Evidence |
|---|---|---|---|
| **Mirroring Azure Databricks Unity Catalog** | "There is no data movement or data replication. Only the Azure Databricks catalog structure is mirrored to Fabric and the underlying catalog data is accessed through shortcuts." It creates a Mirrored Azure Databricks item and a read-only SQL analytics endpoint; Direct Lake is supported. Schema, table, materialized view and streaming table additions and deletions follow. **"Views and metric views don't appear"**; non-Delta external tables are not shown. Not supported: tables with row filters or column masks, Lakehouse federated tables, Delta sharing tables, views. No renaming of schemas or tables | The first step and the parallel run: Fabric reads the same Delta files Databricks writes, so steps 4 and 5 can run before anything is rewritten. It is not a migration by itself: Databricks still writes the tables | Verified [S1] [S2] |
| ...its prerequisites | External data access enabled on the metastore; `EXTERNAL USE SCHEMA` on the schema (granted explicitly, not part of `ALL PRIVILEGES`), plus `SELECT`, `USE CATALOG`, `USE SCHEMA`. The workspace's ADLS Gen2 account must be reachable by Fabric; a storage firewall needs trusted workspace access and an F capacity; "Azure Databricks workspace storage behind an Azure Storage firewall isn't supported" | The assessment checks these first: they decide whether path 1 exists at all | Verified [S3] [S4] |
| ...its security | "Unity Catalog policies and permission aren't mirrored in Fabric." The connection's credential is used for all queries. Permissions are mapped by hand with OneLake security roles | A manual design step. A table that had a row filter cannot be mirrored and must be handled on purpose | Verified [S5] |
| **OneLake shortcut to the Delta files** | A shortcut under a lakehouse's `Tables` folder that points at Delta data is recognised as a table. ADLS Gen2, S3 and GCS are supported sources. Limits per item and per path apply | External tables whose storage the customer owns, when the catalog cannot be mirrored | Verified [S6] |
| **Copy job** | Azure Databricks is a source: full copy and watermark incremental; it is **not** a CDC source. Lakehouse tables and Warehouse are destinations with automatic table creation | The actual move of data that will be owned by Fabric afterwards; views' results; tables path 1 cannot show | Verified [S7] [S8] |
| **Rewrite notebooks and jobs** | No Microsoft guide for Databricks notebooks to Fabric was found, and no mapping page from `dbutils` to NotebookUtils. Learn documents a notebook migration for Azure Synapse only. Fabric's Delta support differs by engine: `TIMESTAMP_NTZ` is not supported by the SQL analytics endpoint, Warehouse or Direct Lake; deletion vectors, column mapping, liquid clustering and type widening vary by runtime; "Delta Lake tables produced by third-party services might have incompatible table features" | Manual work by people. Krusgraph counts the notebooks and jobs and checks what they produce (step 4), it does not translate them | Verified that no guide was found [S9]; table features Verified [S10] |
| **dbt project** | Fabric has a dbt job item, stated as generally available, with the adapters `dbt-fabric` and `dbt-fabricspark` among others. The adapter pages on docs.getdbt.com were not opened | Re-point the project to a Fabric adapter and fix the dialect. Krusgraph's `dbt_schema` writes tests from the plan (`dbt.py`) so the same `unique`, `not_null` and `relationships` tests run on both sides | dbt job Verified [S11]; adapters Unverified [U1] |
| **Databricks SQL dashboards (AI/BI) and metric views** | Dashboards can be exported as `.lvdash.json`. Metric views are defined in YAML. Databricks documents publishing a metric view to Power BI as a semantic model as Private Preview. No Microsoft converter from either into a Power BI semantic model or report was found | Rebuilt as a semantic model and report from the plan (step 7). The exported files are *read* for the inventory: which datasets and measures exist. A metric view's measures become entries in the KPI list (step 5) | Verified [S12] [S13]; absence of a converter is absence of evidence |

### 2.2 What Krusgraph reads on the Databricks side

| What | How | Permission | Evidence |
|---|---|---|---|
| Catalogs, schemas, tables, views, columns, declared constraints, row filters and column masks | `system.information_schema` and each catalog's own. Results are filtered to what the principal may see | No explicit `SELECT` grant on the information schema; `USE CATALOG` and `USE SCHEMA` on what is to be seen. `BROWSE` for metadata only: Unverified | Verified [S14]; today for one schema (`platforms/databricks.py`) |
| Keys and links against the rows | The SQL Statement Execution API on a SQL warehouse, in Databricks SQL (`dialects.py`) | `SELECT` on the tables, use of one SQL warehouse | Today, Draft only: mocked, never run against a workspace (`docs/DATABRICKS.md`) |
| That declared keys prove nothing | Primary key, foreign key and unique constraints are "informational only and aren't enforced" | none | Verified [S15]. They are read as K0/R0 and still counted |
| What reads what, and what is used | `system.access.table_lineage` and `column_lineage`: 395 days, a subset of events, entity types include notebook, job, pipeline, dashboard and query | The system schema enabled, and read access to it | Verified [S16]; `databricks_lineage` reads the table lineage today, Draft only |
| Notebooks, jobs, pipelines, dashboards | The Workspace and Jobs REST APIs; dashboards as `.lvdash.json` | Unverified: the API pages and their minimum permissions were not opened [U2] | New (B4) |
| Which tables path 1 cannot show | From the information schema: views, tables with a row filter or column mask, non-Delta, shared | as row 1 | New (B4): a rule table from [S2] |

### 2.3 What stays manual for Databricks

Enabling external data access and granting `EXTERNAL USE SCHEMA`. Networking between Fabric and the storage account.
Creating the mirrored item (until `docs/CONNECT-DESIGN.md`'s build does it). Mapping Unity Catalog permissions to
OneLake security. Rewriting notebooks, jobs, pipelines and user-defined functions. Anything in ML: models, feature
tables, serving, MLflow. Streaming. Rebuilding dashboards as reports. Stopping jobs and deleting anything in Databricks.

---

## 3. Snowflake to Fabric

### 3.1 The paths

| Path | What the documentation says | Use it for | Evidence |
|---|---|---|---|
| **Mirroring Snowflake** | Continuous replication of table data into OneLake as Delta, with a read-only SQL analytics endpoint. Supported: managed tables, Iceberg tables (as metadata through shortcuts), views and materialized views (a view's data "syncs every 12 hours"). Not supported: external, transient, temporary and dynamic tables | Landing the tables and keeping both sides current during the parallel run | Verified [S17] |
| ...its limits | At most 1 000 tables; "Mirror all data" takes the first 1 000 alphabetically. Any DDL change triggers a full reseed, and the page names dbt runs that drop and recreate tables as a cause. Stop and restart re-fetches whole tables. Snowflake row and column policies are not replicated. No Private Link; a gateway is the route | The assessment counts tables against the limit and lists tables that are dropped and recreated nightly, which mirroring would reseed every night | Verified [S18] |
| ...its permissions and cost notes | The Snowflake user needs `CREATE STREAM`, `SELECT`, `SHOW TABLES`, `DESCRIBE TABLES`. Microsoft states that Snowflake warehouse compute is charged when changed data is read, and that "`SELECT *` will wake up the Snowflake warehouse" | Said to the buyer as Microsoft's statement. Note that mirroring needs `CREATE STREAM`: it is not read-only on Snowflake, unlike Krusgraph's assessment | Verified [S17] [S19] |
| **Iceberg tables and OneLake** | OneLake presents an Iceberg table shortcut as a Delta table and the reverse. Snowflake on Azure can write Iceberg tables to OneLake through an external volume. Limits: Parquet only, the shortcut directly under `Tables` of a lakehouse that is **not** schema-enabled, `timestamp_ntz` "isn't fully supported across all Fabric workloads", and a known type-width issue for Snowflake-written INT64, double and decimal columns with precision of 10 or more | Tables already in Iceberg. The type-width issue is exactly a step 4 finding: the assessment lists the columns it would touch | Verified [S20] [S21] |
| **Copy job** | Snowflake is a source and a destination: full copy, watermark incremental, and it is listed as a CDC source | A one-time or scheduled move where mirroring does not fit (more than 1 000 tables, unsupported table kinds) | Verified [S7] [S8] |
| **Rewrite views, procedures, tasks** | Fabric's Migration Assistant for Data Warehouse lists Synapse dedicated SQL pool, SQL Server and Teradata metadata as sources. **Snowflake is not listed.** No Microsoft guide for Snowflake to Fabric was found | Manual work by people. Krusgraph lists the views and what in their SQL the target does not have (B5), and checks the rewritten result against the rows | Verified [S22]; absence of a guide is absence of evidence |
| **dbt project** | As section 2.1. `dbt-snowflake` is also among the dbt job's adapters, so a project can run from Fabric against Snowflake before it is re-pointed | Re-point, fix the dialect, run the same tests on both sides | Verified [S11]; adapters Unverified [U1] |
| **Snowflake semantic views and Cortex Analyst models** | A semantic view can be read as YAML or DDL. No Microsoft converter into a Power BI semantic model was found | Read for the inventory and the KPI list; rebuilt as a semantic model from the plan | Unverified [U3] |

### 3.2 What Krusgraph reads on the Snowflake side

| What | How | Permission | Evidence |
|---|---|---|---|
| Databases, schemas, tables, views, columns | `INFORMATION_SCHEMA` (read today through the CLI and `plan_from(execute=...)`; `schema.py` compares names case-insensitively because unquoted Snowflake names are upper case) | `USAGE` on the database and schema; a privilege on the object for it to be listed | Today for tables and columns, on names; the grants are Unverified [U4] |
| Keys and links against the rows | Counting queries in Snowflake SQL: a new dialect in `dialects.py` and a new adapter | `SELECT` on the tables, `USAGE` on one warehouse | New (B2) |
| That declared keys prove nothing | Primary key, unique and foreign key constraints are not enforced on standard tables | none | Unverified [U5]. `schema.py` already notes Snowflake has no `KEY_COLUMN_USAGE`, so keys come from names and counts |
| What is used, and by whom | `SNOWFLAKE.ACCOUNT_USAGE`: `ACCESS_HISTORY` (Enterprise edition, hours of latency), `QUERY_HISTORY`, `OBJECT_DEPENDENCIES` | The database roles `GOVERNANCE_VIEWER` and `OBJECT_VIEWER`, or imported privileges on the `SNOWFLAKE` database | Unverified [U6] |
| View, procedure and task definitions | `GET_DDL` and the information schema's view definitions | Depends on the object; not read | Unverified [U6] |
| Which tables mirroring cannot take | From the inventory: the table kind, the count against 1 000, tables recreated by DDL | as row 1 | New (B2): a rule table from [S17] [S18] |

### 3.3 What stays manual for Snowflake

Creating the Snowflake user and grants for mirroring (it needs `CREATE STREAM`). Network set-up or a gateway. Creating
the mirrored database. Rewriting views, stored procedures, tasks, streams, user-defined functions and anything that
reads `VARIANT`. Mapping roles, row access policies and masking policies to OneLake security or model security.
Data sharing and marketplace listings. Suspending warehouses and dropping anything in Snowflake.

---

## 4. Validating truths: the same KPI, the same number, or the reason

This is the part nobody else does by rule, and the part the sales text rests on.

### 4.1 The truths file

A small file the customer owns, one entry per KPI:

```yaml
- kpi: net_sales
  owner: head of controlling            # a role; the name stays with the customer
  grain: [month, company_code]
  source: "SELECT ... FROM shop.orders ..."      # runs on the old side, in its dialect
  target: "SELECT ... FROM gold.orders ..."      # runs on the landed side; later the DAX measure
  tolerance: 0                          # exact by default; anything else is the owner's written decision
```

Krusgraph runs both, per grain, and writes the reconciliation sheet. It does not write the queries: the source query
is the customer's definition of the truth (often lifted from the existing report), and saying what a KPI *means* is
not a tool's job. For a first list, Krusgraph proposes candidates from what it can read: the plan's suggested measures
(`level_measures.py`), a metric view's measures, a semantic view's metrics.

### 4.2 How "shows why" works without guessing

Two layers, both counts.

**Layer 1: column fingerprints, both sides.** For every column of every table in scope, the same handful of counts on
source and landed: rows, NULLs, distinct values, and per type the counts in the table below. They are cheap, they
contain no values, and a difference in a fingerprint is a finding before any KPI is looked at.

**Layer 2: the rule reproduces the difference.** When a KPI differs, Krusgraph takes the columns the two queries read
and the fingerprints that differ on them. For each candidate rule it re-computes the *source* number with the target's
behaviour applied (or the reverse). If that reproduces the target number exactly, the difference is **explained by**
that rule, with the count of rows involved. If two rules together are needed, both are named. If nothing reproduces
it, the sheet says **open**, with the grains where it differs and the fingerprints that differ. It never says
"probably".

| Rule | What changes | Fingerprint, both sides | What the documentation says | Evidence |
|---|---|---|---|---|
| **D1 type not carried** | A column is missing or changed type on the landed side | The column list with types | The SQL analytics endpoint shows only listed types: "Types that aren't listed… aren't represented as the table columns". `ARRAY`, `MAP`, `STRUCT`, `VARIANT`, `INTERVAL` and `TIMESTAMP_NTZ` are not listed. Fabric Warehouse has no `datetimeoffset`, `nvarchar`, `tinyint`, `money` or `datetime` | Verified [S23] |
| **D2 time zone** | A timestamp without zone is read as if it had one, or the reverse; a date boundary moves | Rows per calendar date under UTC and under the stated local zone; the count of timestamps within the zone's offset of midnight | `TIMESTAMP_NTZ` is not supported by the SQL analytics endpoint, Warehouse or Direct Lake. A Power BI model converts Date/Time/Timezone to Date/Time and "doesn't adjust the timezone". Snowflake's `TIMESTAMP` defaults to `TIMESTAMP_NTZ`: Unverified | Verified [S10] [S24]; [U7] |
| **D3 NULL and empty** | NULL became `''` or the reverse; a blank is counted | NULLs, empty strings, strings of blanks only | In a Power BI model BLANK stands for NULL; BLANK + 5 = 5; in comparisons BLANK converts to 0, `""` or FALSE; `DISTINCTCOUNT` counts the BLANK value. Whether Snowflake and T-SQL treat `''` and NULL as distinct was not read | Verified [S24] [S25]; [U7] |
| **D4 decimal precision** | A sum differs in the last digits; a large whole number is rounded | Sum as decimal and as float; the count of values with more decimals than the target scale; the count of values above 2^53 | Power BI "Decimal number" is a 64-bit float with 15 digits; "Fixed decimal number" has four decimals; whole numbers are safe in visuals to 2^53-1. Databricks `DECIMAL` has precision 1 to 38. The Iceberg path has a type-width issue for decimals of precision 10 or more. Snowflake `NUMBER` defaults to (38,0): Unverified. Fabric Warehouse's maximum precision is not on the page read | Verified [S24] [S26] [S20]; [U7] |
| **D5 case in values** | `'ABC'` and `'abc'` are one value on one side and two on the other | Distinct count raw and distinct count of `UPPER(value)` | Databricks compares strings as `UTF8_BINARY` by default, so `'A' <> 'a'`. A Fabric warehouse's default collation is `Latin1_General_100_BIN2_UTF8`, case-sensitive, with a case-insensitive option, and "once a warehouse or SQL analytics endpoint is created, the collation cannot be changed". The Power BI engine is case-insensitive and keeps the first casing it meets | Verified [S27] [S28] [S24] |
| **D6 case in names** | A column or table is not found, or found twice | Names that collide when folded to one case | Databricks identifiers are case-insensitive. Snowflake stores unquoted identifiers in upper case: Unverified. The Snowflake mirroring settings treat identifiers as case-sensitive | Verified [S29] [S18]; [U7] |
| **D7 trailing blanks** | Keys that matched no longer match, or the reverse | Distinct count raw and distinct count of the right-trimmed value | The Power BI engine trims trailing spaces but not leading ones, which "can cause duplicate-value relationship errors". Databricks has an opt-in `RTRIM` collation modifier | Verified [S24] [S27] |
| **D8 leading zeros** | `'00123'` became `123`; keys collide or stop matching | The count of string values that are all digits with a leading zero; distinct count as text and as number | Not a platform rule: it happens when a rewrite or a copy infers a number type for a text key. The fingerprint finds it wherever it happened | A design rule; nothing to cite |
| **D9 duplicated or dropped rows** | A total doubles or shrinks | Rows, distinct keys, orphans (step 4) | Mirroring Snowflake reseeds a table on DDL change; a join in a rewritten view repeats a header amount (`amounts.py`, `sql_sums.py` find the latter today) | Verified [S18]; today for the doubled total |
| **D10 not yet arrived** | The landed side is behind | The newest value of the load timestamp or the highest key, both sides | Mirrored Databricks metadata can take seconds to minutes; a mirrored Snowflake view syncs every 12 hours; polling backs off to an hour without changes | Verified [S1] [S17] [S18] |

Two limits, stated on the sheet itself:

- **A rule explains a difference only when it reproduces it exactly.** A fingerprint that differs is a finding, not an
  explanation.
- **The one place a value may be shown:** to resolve an open difference a person may ask for the *keys* of the rows
  that differ in one grain (not the measures), limited in number, shown to the signed-in person and not kept. Off by
  default; a founder decision before B3 (section 8).

### 4.3 After the semantic model exists

The target query of a truth becomes the DAX measure, evaluated per grain. That adds the model's own rules to the
table (D3, D4, D5 and D7 are worded for it already) and one more: a relationship that filters in one direction, or an
unmatched key that lands on the model's blank row, moves an amount between groups without changing the total. The
sheet therefore always compares the total *and* each grain.

---

## 5. Risks, and what Krusgraph must not claim

| # | Risk | What we do about it |
|---|---|---|
| 1 | **"Automatic migration."** A buyer hears that Krusgraph moves the platform | Never said. Krusgraph inventories, counts, compares and rebuilds the Fabric side from a plan. Notebooks, SQL, procedures and dashboards are rewritten by people |
| 2 | **"Every number will match."** | Never said. The promise is that every KPI on the list is compared and every difference is explained by a rule or listed as open |
| 3 | **A green sheet read as proof of everything.** Only what is on the truths list is checked | The sheet carries its coverage, as every plan answer does (`coverage.py`): how many tables and columns the KPIs touch, and how many they do not |
| 4 | **A wrong reason.** A rule named for a difference it did not cause | Layer 2: named only when it reproduces the number exactly. Tested with planted differences, including pairs that look alike (B1's test) |
| 5 | **Preview and moving features.** Mirroring's limits, the dbt job, OneLake security and metric view publishing change | Every fact has a date and a source. The rule tables for "can this table be mirrored" are data files with the page and date, re-read before each engagement |
| 6 | **Unverified vendor facts.** Every Snowflake, dbt and Qlik fact here | Section 9 lists them. None may appear in public text until read on the page |
| 7 | **Never run live.** The Databricks adapter is mocked only; there is no Snowflake adapter; mirrored Snowflake and Databricks items are tested with Fabric mocked | Said in every offer until a live run on synthetic data is written up in `docs/LIVE-TEST.md`. Needs trial accounts only the founder can open |
| 8 | **Security does not travel.** Unity Catalog and Snowflake policies are not mirrored | Listed in the inventory per table (row filter, mask, policy) and handed over as a design task. Krusgraph applies no security |
| 9 | **Cost on the source during the assessment.** Counting queries use the customer's SQL warehouse or Snowflake warehouse | Stated before the first query. One time budget per call (`budget.py`), an estimate of the number of queries up front, and a mode that reads metadata only |
| 10 | **Personal data.** Fingerprints are counts, but usage history names users | Usage is aggregated per object (readers in the period, last read), never per person, unless the customer asks in writing |
| 11 | **Claims about cost or speed** | None, in either direction. Where Microsoft states a cost fact it is quoted as theirs |
| 12 | **Deleting or stopping things on the old side** | Never. The retire checklist is a list for a person |

---

## Part B. Qlik Sense to Power BI

Builds on W7 (not on `main` when this was written; see the top). W7 owns the reader for a `.qvs` load script. This
part says what is done with what the reader returns. Every Qlik fact is Unverified (*summary only*): `help.qlik.com`
and `qlik.dev` could not be opened.

### B.1 The starting point, from Microsoft

Learn's Power BI migration series is written for migration "from a third-party BI tool". Qlik is not named and no
conversion tool is mentioned. It advises focusing on the business question rather than replicating reports exactly,
and its validation stage says the new report's data must match the old "or, if there's a difference, be able to
explain why" (Verified [S30] [S31]). That sentence is this design's step 5.

### B.2 From load script and data model to a checked plan

| Step | What Krusgraph does | Automatic, suggested, or a person |
|---|---|---|
| Read the app | Takes the load script and, when available, the master items, variables and sheet objects as files. How they are obtained is the customer's step: Qlik's own tooling can unbuild an app into its script, dimensions, measures and variables (Unverified [U8]), or the script is copied out by hand | A person hands the files over. Krusgraph does not connect to Qlik in the first builds |
| Tables and fields | From the script: each loaded table, its fields after renames and qualification, its source (a database table, a QVD, a resident load, an inline table), and the joins and concatenations done in script | **Automatic** for the statements W7's reader covers. Everything it does not parse is **listed, not skipped**: the statement, its line, and "not read" |
| Associations | Qlik associates tables on fields with the same name [U9]. So: every pair of tables that share one field name is one association | **Automatic** |
| Synthetic keys | Two tables that share two or more field names get a synthetic key [U9]. Every such pair is listed with the shared fields | **Automatic** detection |
| Circular references | A loop in the association graph; Qlik sets a table as loosely coupled [U9]. Listed with the tables in the loop | **Automatic** detection (`graphs.py` already finds cycles) |
| Check against the rows | The plan's counts on the *source tables the script loads from*, when they are reachable in Fabric or on the source: per candidate key distinct and NULLs, per association rows without a match | **Automatic**, with the existing `evidence.py`. Where the script transforms on the way, the counts are on the landed silver tables instead, and the sheet says so |

### B.3 Synthetic keys and link tables resolved into proper keys

For each synthetic key, the counts decide which of four cases it is. The proposal is a suggestion with its rule and
its counts; a person accepts it.

| Case | The counts show | Proposal | Who |
|---|---|---|---|
| **A real composite key** | The shared fields together are unique on one side, and no single one of them is | One combined key column on both sides and one relationship on it. This is `combined_keys.py` (n226), built for SAP-shaped keys | **Suggested**; automatic once accepted |
| **An accident of naming** | One shared field carries the link (unique on one side, included on the other); the others are fields that happen to share a name (`Date`, `Status`, `Name`) | Keep the one link, rename the others per table | **Suggested**, with the inclusion count per field |
| **Two facts sharing dimensions** | Neither side is unique on the shared fields; each shared field has its own table, or should | No relationship between the two facts. Each shared field becomes a dimension both facts relate to. A Qlik link table built for this purpose is replaced by those dimensions | **Suggested**; a person confirms the grain of each fact |
| **A real many-to-many** | Neither side unique, and the pairs themselves are the information | A bridge table. Microsoft's guidance names a bridging table as the practice for many-to-many between dimensions (Verified [S32]) | **A person decides** |

Why it must be resolved at all: in Power BI "relationships are based on a single unique column in one table", and a
model allows one active relationship between two tables (Verified [S32]). A loop is not allowed either: Power BI
refuses a cross-filter setting that would create ambiguity (Verified [S33]).

Three differences in behaviour that are written into the plan as notes, because they move numbers:

- **Direction.** A Qlik selection reaches every associated table. A Power BI relationship filters in one direction
  by default, and Microsoft recommends keeping bidirectional relationships to a minimum (Verified [S34]). A measure on
  the "one" side that was filtered by a selection on the "many" side in Qlik needs a measure written for it.
- **Unmatched keys.** In Qlik a NULL does not associate [U9]. In a Power BI model, rows without a match land on a
  blank row of the dimension and stay in the total. Same total, different groups.
- **Case.** Qlik field values are case-sensitive [U9]; the Power BI engine is not (Verified [S24]). Distinct counts
  differ; this is rule D5.

### B.4 Set analysis and master measures to DAX measures

Every expression gets exactly one of three labels, and the label is in the output next to the measure.

| Label | Meaning | Which expressions (first version) |
|---|---|---|
| **Translated by rule** | A fixed rule produces the DAX. The same input always gives the same output. Still reconciled (B.5) | A plain aggregation of one field (`Sum`, `Min`, `Max`, `Avg`, `Count`) with no set expression. `Count(DISTINCT f)` becomes `DISTINCTCOUNTNOBLANK`, because `DISTINCTCOUNT` counts BLANK (Verified [S25]). A master measure that only refers to other master measures. A set modifier that sets one field to a list of literal values, `{<Year={2025}>}`, **when that field is not used as a dimension in any object the measure is used in**: `CALCULATE(..., Dim[Year] = 2025)`. A `CALCULATE` filter replaces an existing filter on the same column (Verified [S35]), which is what the modifier does to a selection |
| **Suggested** | A rule produces a DAX draft and names what may differ. A person reads it | The same modifier when the field *is* a chart dimension (Qlik still groups by it, as we read the set analysis pages [U10], to be confirmed on a real app; a DAX filter on the column replaces the group's own filter). Clearing a field, `{<Year=>}`: `REMOVEFILTERS(Dim[Year])`, with the same caveat. The identifier `1` (all records, selections ignored): DAX has no notion of "selections" apart from a visual's own grouping, so the draft removes filters and says what that also removes. `TOTAL` and `TOTAL <fields>`: `REMOVEFILTERS`, `ALLEXCEPT` or `ALLSELECTED`, depending on the visual. `P()` and `E()`: `TREATAS` or `EXCEPT` over the values (Verified for `TREATAS` [S36]). A search inside a set, `{<Customer={"=Sum(Sales)>100"}>}`: a `FILTER` over the field's values. `Aggr()`: an iterator over the grouping fields |
| **A person decides** | No draft. The expression, where it is used, and why | Alternate states and bookmarks as set identifiers. Set operators between sets. `Aggr` with `NODISTINCT`. Dollar-sign expansion whose content is computed at run time. Calculated dimensions. Anything the reader could not parse. Any measure whose name occurs in two apps with different expressions: which one is right is a business decision |

The list of which forms are translated by rule is published with the build and is short on purpose. The share of a
customer's expressions that falls under each label is **counted per app in the assessment**; no share is promised in
advance, and none is known today.

Calendar and number settings travel with the plan as stated facts, not as translations: the script's week settings
(first week day, broken weeks, reference day [U10]) decide what "week 1" is, and a DAX calendar must be built to the
same settings or the weekly KPIs differ.

### B.5 A reconciliation per KPI

The same sheet as section 4, with Qlik as the old side:

- **The Qlik side** is a table a person exports from the app: the measure per grain (month, unit), with no
  selections, as a file. Krusgraph does not evaluate Qlik expressions.
- **The Power BI side** is the DAX measure evaluated over the same grain on the built model.
- **The reasons** are rules D2 to D9 plus the three notes of B.3 (direction, unmatched keys, case) and the calendar
  settings. A reason is named only when applying it reproduces the number.
- **The label of B.4 is on the sheet.** A measure "translated by rule" that does not reconcile is a bug in the rule
  or a finding in the data, and the sheet shows which fingerprint differs.

### B.6 Apps to reports

| | What | Label |
|---|---|---|
| One model for several apps | Apps whose scripts load the same tables are grouped (the script's sources, compared by name). The proposal is one semantic model per group, where Qlik had one data model per app | **Suggested**; a person decides the grouping |
| Sheets to pages | An inventory per app: sheets, objects per sheet, the dimensions and measures each object uses. Each object type gets a proposed Power BI visual from a fixed table (bar chart to bar chart, straight table to table, pivot to matrix, KPI to card, filter pane to slicer) | **Suggested**. No official mapping from either vendor was found; the table is ours and says so |
| What has no counterpart | Alternate states, the associative selection colours, and objects the reader does not know are listed per app | **A person decides** |
| The report itself | `report.py` creates a report with pages and visuals from the plan today. It does not reproduce a Qlik sheet's layout | **A person** designs the pages. Microsoft's advice is to rebuild around the question, not copy the layout (Verified [S30]) |

### B.7 Section access to row-level security: a design note, never applied

Krusgraph reads the section access part of the script and writes a note. It creates no role and no member.

| Qlik section access [U11] | Power BI counterpart | Note in the design |
|---|---|---|
| A row per user (`USERID` or `USER.EMAIL`) with reduction field values | Dynamic RLS: a security table related to the dimension, filtered by `USERPRINCIPALNAME()` (Verified [S37]) | The reduction field must be a column of the model, with the same case rule: Power BI compares strings case-insensitively |
| `GROUP` | Entra security groups as role members. Microsoft 365 groups are not supported as members (Verified [S37]) | The groups must exist in Entra; a mapping table for a person to fill in |
| `ACCESS` = `ADMIN` or `USER` | No counterpart. RLS applies only to users with Viewer permission; workspace Admin, Member and Contributor are not restricted (Verified [S37]) | The classic trap: someone who was restricted in Qlik becomes a workspace Member and sees everything. The note lists every restricted user to check against workspace roles |
| `OMIT` (hide a field per user) | Object-level security: a column or table is hidden as if it did not exist, for Viewers (Verified [S38]). The mapping is ours, not Microsoft's | Qlik advises against OMIT on key fields; OLS on a relationship column needs the same care |
| A user not listed cannot open the app | App and workspace access plus roles | To be tested by a person with a test user per role, before cutover |
| Wildcards in reduction values | Not read on the page | **Open**: the meaning of a wildcard in Qlik section access must be read in Qlik's documentation before a role is designed from it |

Also in the note: role members cannot be set through the Fabric REST API (Verified [S39]), so adding members is a
manual step or a different API; with Direct Lake, model RLS is supported, a fixed identity is recommended, and RLS
defined on the SQL endpoint makes Direct Lake on SQL fall back to DirectQuery (Verified [S40]).

---

## 6. What exists in the repository today

| Part | Exists | Does not exist |
|---|---|---|
| **A, Databricks** | `platforms/databricks.py`, `databricks_drafts.py`, `docs/DATABRICKS.md`: one Unity Catalog schema read, keys and links counted on a SQL warehouse, lineage, drafts. **Draft only, mocked, never run against a workspace.** Mirrored Azure Databricks catalogs are a source type of the Fabric adapter, tested with Fabric mocked | Inventory across catalogs; notebooks, jobs, dashboards; the "can this be mirrored" rules; a live run |
| **A, Snowflake** | `schema.py` reads `INFORMATION_SCHEMA` on Snowflake for a plan on names (CLI, `plan_from`). Mirrored Snowflake databases and Snowflake database items are source types of the Fabric adapter, tested with Fabric mocked | A Snowflake dialect and adapter; counts on Snowflake; usage; a live run |
| **A, both sides** | Counts on one connection: `evidence.py`, `profile.py`, `coverage.py`, `amounts.py`, `sql_sums.py`, one dialect layer (`dialects.py`), the time budget (`budget.py`) | Two connections in one answer; fingerprints beyond NULL share and distinct count; the truths file; the difference rules |
| **A, rebuild** | `silver.py`, `gold.py`, `pipeline.py`, `semantic_model.py`, `report.py`, `ontology.py`, `dbt.py`, `product_life.py`; items created live on synthetic data | Cutover sheet; usage read; owner field |
| **B, Qlik** | W7's reader for a synthetic `.qvs`: **claimed, not on `main`**. `combined_keys.py` for composite keys; `graphs.py` for cycles; `model_compare.py` and `dax_refs.py` read TMDL and DAX references | Everything in part B |
| **C, sales** | `docs/PILOT.md`, `docs/FAQ-COMPETITION.md`, `docs/MISSING-EVIDENCE.md` | See `marketing/MIGRATIONS.md` section 7 |

---

## 7. What to build, the estimate, the first three per part

Nine engine builds. Each is unit-tested on synthetic data first; a live run is a separate line because it needs
accounts only the founder can open.

| # | Build | What it is | Tested on | Rounds |
|---|---|---|---|---|
| **B1** | **The two-sided check** | Two connections in one call (the local server): the plan's key and link counts and the column fingerprints of section 4.2 on both, and a sheet of what differs. Rules D1 to D10 as fingerprints | A synthetic pair: the shop schema (`seed.py`) twice in local databases, the second with one planted difference per rule and two look-alike pairs. Every planted difference found; nothing else reported | 2 |
| **B2** | **Snowflake, read-only** | A Snowflake dialect and adapter beside the Databricks one: inventory of one database with counts per kind, the plan's counts, the "can this be mirrored" rules from [S17] [S18], a metadata-only mode | Snowflake mocked at its SQL API, as Databricks is. The vendor pages read first (they are Unverified today) | 1 |
| **B3** | **The truths file** | The file of section 4.1, both queries run per grain, the reconciliation sheet, and layer 2: a reason named only when it reproduces the number | The synthetic pair with three KPIs and planted differences; a case that must come out "open" | 1 |
| **B4** | **Databricks inventory** | Across catalogs: tables by kind and format, views, row filters and masks, the "can this be mirrored" rules from [S2], lineage per object; notebooks, jobs and dashboards counted | Mocked. The Workspace and Jobs API pages read first [U2] | 1 |
| **B5** | **View SQL report and the cutover sheet** | Per view definition: the constructs the target does not have, from a published list (types of D1, semi-structured access, dialect functions), with the line. Not a translator. And: readers per object from usage history, days green, the retire checklist | Synthetic view definitions; usage rows mocked | 1 |
| **B6** | **Qlik: the checked plan** | On W7's reader: tables, fields, associations, synthetic keys, loops; the four cases of B.3 decided by counts; combined keys through `combined_keys.py` | Synthetic `.qvs` files, one per case, and the shop data behind them | 1 |
| **B7** | **Qlik: measures** | The three labels of B.4; the published list of forms translated by rule; drafts with their caveat for the suggested ones; the count per label per app | A synthetic set of expressions, each with its expected label and DAX. The Qlik pages read first | 2 |
| **B8** | **Qlik: reconciliation per KPI** | The exported Qlik table against the DAX measure per grain, with the reasons of B.5 | Synthetic: an export file and a model built from the same shop data with planted differences | 1 |
| **B9** | **Qlik: app inventory and the section access note** | Sheets and objects per app, the visual proposals, the grouping of apps into models; the note of B.7 | Synthetic app files | 1 |

Eleven rounds for all nine. Live proof on top: one run each against a Databricks workspace, a Snowflake account and a
Qlik Sense environment, synthetic data, about half a round each once the founder has opened the accounts.

**First three builds, per part.**

- **Part A:** B1, then B2, then B3 (four rounds). B1 first because every source, Qlik included, needs it, and because
  it can be proven without any vendor account.
- **Part B:** B6, then the "translated by rule" half of B7, then B8 (about three rounds). They wait for W7's reader.
- **Part C:** S1, S2, S3 in `marketing/MIGRATIONS.md` section 7 (about two and a half rounds). S1 waits for B1.

The order across parts that gets to something showable soonest: **B1, B3, S1**. After those three there is a
before-and-after sheet on synthetic data to put in front of a buyer, for all three sources.

---

## 8. Decisions for the founder

1. **Which source first for the live proof:** Databricks (an adapter exists, mocked), Snowflake (mirroring copies the
   data, which makes the before-and-after story simplest) or Qlik (W7 has started). The engine order above does not
   depend on the answer; the first live run does.
2. **Trial accounts:** a Databricks workspace, a Snowflake account, a Qlik Sense environment, each with synthetic data
   only. Without them rows 3, 5 and 6 of the sales text's proof table stay missing.
3. **May a reconciliation show the keys of differing rows** to the signed-in person (section 4.2)? Default in this
   design: off.
4. **Does the source side stay local-only**, as designed here (the hosted server reads Fabric only)? It keeps the
   customer's Databricks and Snowflake credentials away from krusgraph.com, and it means an assessment is run with
   Kruse Consulting rather than self-served from the chat.
5. **Network access for the sessions that build B2, B4 and B7:** `docs.snowflake.com`, `docs.databricks.com`,
   `docs.getdbt.com`, `help.qlik.com` and `qlik.dev` must be reachable, or the Unverified list cannot shrink.

---

## 9. Sources

All read 12 November 2026.

### Verified: opened on learn.microsoft.com

- [S1] Mirroring Azure Databricks Unity Catalog: https://learn.microsoft.com/en-us/fabric/mirroring/azure-databricks
- [S2] ...limitations: https://learn.microsoft.com/en-us/fabric/mirroring/azure-databricks-limitations
- [S3] ...tutorial: https://learn.microsoft.com/en-us/fabric/mirroring/azure-databricks-tutorial
- [S4] Azure Databricks, external access to Unity Catalog: https://learn.microsoft.com/en-us/azure/databricks/external-access/admin
- [S5] Mirroring Azure Databricks, security: https://learn.microsoft.com/en-us/fabric/mirroring/azure-databricks-security
- [S6] OneLake shortcuts: https://learn.microsoft.com/en-us/fabric/onelake/onelake-shortcuts
- [S7] Copy job: https://learn.microsoft.com/en-us/fabric/data-factory/what-is-copy-job
- [S8] Copy job connectors: https://learn.microsoft.com/en-us/fabric/data-factory/copy-job-connectors
- [S9] Migrate Azure Synapse notebooks to Fabric (the only notebook migration page found): https://learn.microsoft.com/en-us/fabric/data-engineering/migrate-synapse-notebooks
- [S10] Delta Lake table format interoperability: https://learn.microsoft.com/en-us/fabric/fundamentals/delta-lake-interoperability
- [S11] dbt job in Fabric: https://learn.microsoft.com/en-us/fabric/data-factory/dbt-job-overview (a search summary noted that the tenant setting and a how-to page still say preview; those pages were not opened)
- [S12] Azure Databricks, automate dashboards: https://learn.microsoft.com/en-us/azure/databricks/dashboards/automate/
- [S13] Azure Databricks, metric views and BI tools: https://learn.microsoft.com/en-us/azure/databricks/uc-semantics/metric-views/ and https://learn.microsoft.com/en-us/azure/databricks/uc-semantics/metric-views/bi-tools
- [S14] Azure Databricks, information schema: https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/sql-ref-information-schema
- [S15] Azure Databricks, constraints: https://learn.microsoft.com/en-us/azure/databricks/tables/constraints
- [S16] Azure Databricks, lineage system tables: https://learn.microsoft.com/en-us/azure/databricks/admin/system-tables/lineage
- [S17] Mirroring Snowflake: https://learn.microsoft.com/en-us/fabric/mirroring/snowflake
- [S18] ...limitations: https://learn.microsoft.com/en-us/fabric/mirroring/snowflake-limitations
- [S19] ...tutorial: https://learn.microsoft.com/en-us/fabric/mirroring/snowflake-tutorial
- [S20] Iceberg tables in OneLake: https://learn.microsoft.com/en-us/fabric/onelake/onelake-iceberg-tables
- [S21] Snowflake and OneLake with Iceberg: https://learn.microsoft.com/en-us/fabric/onelake/onelake-iceberg-snowflake
- [S22] Migration Assistant for Fabric Data Warehouse: https://learn.microsoft.com/en-us/fabric/data-warehouse/migration-assistant
- [S23] Fabric Data Warehouse data types, and the SQL analytics endpoint's mapping: https://learn.microsoft.com/en-us/fabric/data-warehouse/data-types
- [S24] Power BI data types (case, trailing spaces, number types, date and time, BLANK): https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-data-types
- [S25] DISTINCTCOUNT: https://learn.microsoft.com/en-us/dax/distinctcount-function-dax
- [S26] Azure Databricks, DECIMAL: https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/data-types/decimal-type
- [S27] Azure Databricks, collation: https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/sql-ref-collation
- [S28] Fabric Data Warehouse collation: https://learn.microsoft.com/en-us/fabric/data-warehouse/collation
- [S29] Azure Databricks, identifiers: https://learn.microsoft.com/en-us/azure/databricks/sql/language-manual/sql-ref-identifiers
- [S30] Power BI migration overview: https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-migration-overview
- [S31] ...create and validate content: https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-migration-create-validate-content
- [S32] Star schema guidance: https://learn.microsoft.com/en-us/power-bi/guidance/star-schema
- [S33] Create and manage relationships: https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-create-and-manage-relationships
- [S34] Bidirectional relationship guidance: https://learn.microsoft.com/en-us/power-bi/guidance/relationships-bidirectional-filtering
- [S35] CALCULATE: https://learn.microsoft.com/en-us/dax/calculate-function-dax
- [S36] TREATAS: https://learn.microsoft.com/en-us/dax/treatas-function-dax
- [S37] Row-level security: https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security
- [S38] Object-level security: https://learn.microsoft.com/en-us/fabric/security/service-admin-object-level-security
- [S39] Power BI Desktop projects: https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview
- [S40] Direct Lake overview: https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-overview

### Unverified: the page could not be opened; a search summary only, or not read at all

- [U1] dbt adapters for Fabric: https://docs.getdbt.com/docs/local/connect-data-platform/fabric-setup and https://docs.getdbt.com/docs/local/connect-data-platform/fabricspark-setup
- [U2] Databricks Workspace export and Jobs APIs and their minimum permissions; the `BROWSE` privilege (https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-catalog/access-control/privileges-reference, summary only); Fabric NotebookUtils (https://learn.microsoft.com/en-us/fabric/data-engineering/notebook-utilities, summary only)
- [U3] Snowflake semantic views as YAML or DDL: https://docs.snowflake.com/en/user-guide/views-semantic/sql
- [U4] Snowflake `INFORMATION_SCHEMA` and the grants needed to list objects: not read
- [U5] Snowflake constraints not enforced: https://docs.snowflake.com/en/sql-reference/constraints-overview
- [U6] Snowflake `ACCOUNT_USAGE`, its database roles, editions and latency, and `GET_DDL`: https://docs.snowflake.com/en/sql-reference/account-usage and https://docs.snowflake.com/en/sql-reference/snowflake-db-roles
- [U7] Snowflake identifiers, `NUMBER`, timestamps, `VARIANT`, empty string and NULL: https://docs.snowflake.com/en/sql-reference/identifiers-syntax and https://docs.snowflake.com/en/sql-reference/data-types-numeric. Also not found on the pages read: Fabric Warehouse's maximum decimal precision, a Direct Lake limit on decimals, empty string and NULL in T-SQL
- [U8] Qlik: unbuilding an app into script, dimensions, measures and variables; reading the script through the engine API; exporting an app: https://qlik.dev/toolkits/qlik-cli/app/app-unbuild/
- [U9] Qlik: associations by field name, synthetic keys, circular references and loosely coupled tables, NULL in associations, case sensitivity of values, dual values: https://help.qlik.com/en-US/cloud-services/Subsystems/Hub/Content/Sense_Hub/Scripting/synthetic-keys.htm and the pages beside it
- [U10] Qlik: set analysis (identifiers, operators, modifiers, `P()` and `E()`, `TOTAL`, `Aggr`), master items, week and calendar variables: https://help.qlik.com/en-US/cloud-services/Subsystems/Hub/Content/Sense_Hub/ChartFunctions/SetAnalysis/set-analysis-expressions.htm and the pages beside it
- [U11] Qlik section access: https://help.qlik.com/en-US/cloud-services/Subsystems/Hub/Content/Sense_Hub/Scripting/Security/manage-security-with-section-access.htm
- Not found at all: a Microsoft guide for Databricks to Fabric or Snowflake to Fabric; a Microsoft converter for Databricks dashboards, metric views or Snowflake semantic views into Power BI; an official mapping of Qlik objects to Power BI visuals. Each is an absence of evidence from a few searches, not a documented statement
- Explicit "generally available" wording for the two mirroring features was not on the pages read; they carry no preview label
