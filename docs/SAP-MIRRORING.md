# Mirrored databases and SAP mirrored through SAP Datasphere

Round n201 (11 November 2026). The Krusgraph Model, the Fabric workload's item, works with data mirrored into Fabric:
a mirrored database (Azure SQL, SQL Server, Snowflake, open mirroring and the rest of Learn's list), SAP data mirrored
through SAP Datasphere among them, as well as a warehouse and a SQL database. Before n201 it read lakehouses only, and
the workload's detail page said "Compatible with: Lakehouse".

This page says what works, how it was tested, what was not tested, and the steps for a customer. Krusgraph holds no
SAP or Microsoft certification and has no partnership with or endorsement from either; it reads what Fabric has
mirrored, with the signed-in person's own Fabric permissions.

## What Microsoft Learn says (read 11 November 2026)

- [Microsoft Fabric mirrored databases from SAP](https://learn.microsoft.com/fabric/mirroring/sap) (ms.date 26 February
  2026): "Mirroring creates a mirrored database and a SQL analytics endpoint in your Fabric workspace. The mirrored
  database manages replication of data into OneLake and conversion to Parquet". The endpoint "provides a read-only
  analytical experience on top of the Delta tables created by the mirroring process". Via SAP Datasphere a replication
  flow "extracts data (initial snapshot and changed records) from your SAP source system and lands it in an Azure Data
  Lake Storage (ADLS) Gen2 container", and the mirroring engine "continuously merges the data with the mirrored
  database tables in OneLake". Sources: SAP S/4HANA, SAP ECC, SAP BW/4HANA, SAP BW and SAP Datasphere itself. "SAP
  Datasphere Premium Outbound Integration pricing applies when mirroring SAP data via SAP Datasphere."
- [Limitations](https://learn.microsoft.com/fabric/mirroring/sap-limitations) (26 February 2026): target settings
  Group Delta None and File Type Parquet; load type "Initial and Delta" or "Initial Only".
- [Tutorial: SAP via SAP Datasphere](https://learn.microsoft.com/fabric/mirroring/sap-datasphere-tutorial) (26 February
  2026): prerequisites are a Fabric capacity and "An SAP Datasphere environment with Premium Outbound Integration"; the
  mirrored database is "a read-only, continuously replicated copy of your SAP data in OneLake".
- [Get Mirrored Database](https://learn.microsoft.com/rest/api/fabric/mirroreddatabase/items/get-mirrored-database)
  (page updated 6 November 2026): `properties.oneLakeTablesPath`, "OneLake path to the mirrored database tables
  directory", `sqlEndpointProperties` (connection string, id, provisioning status) and `defaultSchema`.
- [How do I connect to OneLake?](https://learn.microsoft.com/fabric/onelake/onelake-access-api) (18 May 2026): items can
  be addressed by workspace and item GUIDs, and the ABFS form is `abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<item>/<path>`.
- [Explore data in your mirrored database with notebooks](https://learn.microsoft.com/fabric/mirroring/explore-onelake-shortcut)
  (19 November 2024): the other documented route, a OneLake shortcut in a lakehouse to the mirrored tables.
- [Mirroring overview](https://learn.microsoft.com/fabric/mirroring/overview) (28 August 2026): database, metadata and
  open mirroring; the list of sources.

## What works

1. **Source.** The item's source picker offers lakehouses, warehouses, SQL databases and mirrored databases (the same
   item types `list_sources` lists). Review, Check against the rows and the plan read the item's SQL analytics endpoint,
   read-only, exactly as for a lakehouse; nothing is written to the source. The review says that the source is
   read-only and, for a mirrored database, what mirroring delivers.
2. **Target.** A mirrored database is read-only, so the silver notebook, the gold views and the pipeline (with its
   check notebook) write to a lakehouse the person picks under **Target lakehouse**: by default the first lakehouse of
   the same workspace by name, and the dry run says which one and that it is the default. A workspace with no
   lakehouse gets a plain refusal and nothing is written. The semantic model, the API for GraphQL, the ontology and the
   data agent read the mirrored tables, as they read a lakehouse's.
3. **How the silver notebook reads the mirror.** At the documented path: `oneLakeTablesPath` from Get Mirrored
   Database, in the ABFS form of the OneLake URI page, read by Spark in Fabric. No data is copied outside Fabric and no
   shortcut is created, so there is nothing extra to consent to. Learn does not document how the folders under
   `Tables` are laid out per schema, so the notebook reads `Tables/<schema>/<table>` when that folder holds a Delta log
   and `Tables/<table>` otherwise (**Unverified** against a real mirror).
4. **SAP.** When the tables are SAP's (two or more tables the SAP pack describes, such as VBAK, VBAP, KNA1, MARA, EKKO,
   EKPO), the review offers the SAP pack's keys (with the client column MANDT where the pack says so) and its links,
   each marked "from the SAP pack" with the pack's public source, beside the keys and links the name rules found. The
   person accepts or rejects each as any other item, and Check against the rows counts them. Nothing is guessed beyond
   the pack (`docs/SAP.md`, `fabric_backend/packs/sap/`). The review also shows what mirroring delivers (Initial and
   Delta loads, Parquet, per Learn) and that SAP Datasphere Premium Outbound Integration is the customer's licence
   matter with SAP; Krusgraph needs no SAP licence and does not check one.
5. **The detail page.** Both workload packages (`Org.Krusgraph` and `Krusgraph.Modeler`) list Lakehouse,
   MirroredDatabase, Warehouse and SQLDatabase as compatible item types, and the detail page's text says "Works with
   data mirrored into Fabric". Learn shows `compatibleItemTypes` with Fabric item type names and gives no list of
   accepted values, so how Fabric renders the three new names is **Unverified** until the founder uploads the package.

## Other routes for SAP data into Fabric

- **Open mirroring.** Learn's open mirroring partner page lists SAP extraction tools that write change data into a
  mirrored database through open mirroring (for example dab Nexus, Simplement Roundhouse, SNP Glue, Theobald Xtract
  Universal, ASAPIO, AecorSoft). What they create is a mirrored database, so items 1 to 4 above cover it. This page
  names them only as routes a customer may use; Krusgraph has no relation to any of them.
- **The "SAP mirroring" workload in the Workload Hub.** The founder saw a workload of that name in Fabric's Workload
  Hub. Its public pages could not be identified from this session (the Fabric community site was not reachable and no
  Learn page names it), so what item it creates is **Unverified**. If it lands data as a mirrored database or as
  lakehouse tables, Krusgraph reads it today through items 1 to 4. If it creates its own item type with a SQL endpoint,
  reading it would need: the item type's REST route and a Get call that returns `sqlEndpointProperties` (as
  `deploy.ENDPOINT_ITEM_ROUTES` holds for the mirrored catalog types), its type name in the editor's picker and in
  `compatibleItemTypes`, and a OneLake path for the silver notebook. That is left out of this round.

## What was tested, and how

- `tests/test_n201_mirrored.py`: a fake mirrored database (Get Mirrored Database's answer as Learn's REST page shows it,
  and a SQL analytics endpoint on SQLite that refuses every write) with SAP-named tables built only from the SAP pack's
  public table and column names and made-up values (`sap_demo.tables()` plus EKKO, EKPO and LFA1); the review with the
  pack's keys with MANDT and its links, each marked "from the SAP pack" with a source URL; accepting and rejecting pack
  items; the check; the dry run that names the default target lakehouse; a chosen target, an unknown one and a
  workspace without a lakehouse; Create of the silver notebook on the target lakehouse; the notebook's setup run with
  stand-ins for Spark and `notebookutils`, which reads `Tables/dbo/VBAK` or `Tables/EKKO` under the mirror's OneLake
  path. A second fake mirror built from the mill sample (no SAP names) plans as a normal source.
- `tests/test_n201_manifest.py`: both packages build and validate with the new compatible item types, the film first,
  the attestation link, and refuse a slide Fabric would not show.
- `workload/Workload/app/items/ModelItem/sourceWords.test.ts`: the editor's words for sources, the target and the SAP
  marks.

## What was not tested

- **No SAP Datasphere was available to us.** Nothing here has run against SAP data mirrored through SAP Datasphere, or
  against any real SAP system. The SAP-named tables in the tests are synthetic.
- No mirrored database in Fabric has been read by the workload yet: not Azure SQL, not Snowflake, not open mirroring.
  The engine's read of a mirrored database's SQL analytics endpoint is the same code the MCP tools use (`list_sources`,
  `resolve_source`), which has not been run against a mirror either.
- The silver notebook has not run in Fabric against a mirror; the folder layout under `Tables` and Spark's read of a
  Delta table by its OneLake path (`delta.` followed by the path in backquotes) are Unverified there.
- The source picker's item type names for a mirrored database and a SQL database are not documented for the workload
  client; the editor asks for several candidates and takes the real type from the engine's answer (**Unverified** until
  tried in Fabric).

## Steps for a customer

1. Mirror the source into Fabric with Fabric's own tools. For SAP via SAP Datasphere, follow Learn's tutorial: a
   replication flow to ADLS Gen2 (Group Delta None, File Type Parquet, load type Initial and Delta or Initial Only), a
   lakehouse shortcut to the container, then New item → Mirrored SAP. SAP Datasphere with Premium Outbound
   Integration is needed; that licence is between you and SAP.
2. Wait until the mirrored database shows rows replicated and its SQL analytics endpoint lists the tables.
3. Make sure the workspace has a lakehouse for what Krusgraph builds (with Lakehouse schemas if you want the gold views).
4. + New item → Krusgraph Model → Choose a source → the mirrored database, and its schema (usually `dbo`).
5. Choose **Target lakehouse**, or leave the default (the first lakehouse of the workspace; the dry run names it).
6. Find keys and relationships. For SAP tables, the pack's keys and links are marked "from the SAP pack" with their
   source; accept or reject each, then Check against the rows.
7. Choose the outputs, read the dry run (it names the target lakehouse and how the mirror is read), then Create.

## Trying it without SAP

An Azure SQL mirror of the mill sample (`docs/SAMPLE-MILL.md`, sixteen synthetic tables) needs no SAP: load the mill
tables into an Azure SQL Database, mirror it into Fabric (Learn: Tutorial: Azure SQL Database), add a lakehouse to the
same workspace, and run the steps above from step 4. The review plans it like any other source, with no SAP pack.
