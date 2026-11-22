# Pilot scan: what your estate looks like, names and counts only

21 November 2026, round BL23 (backlog S-04, I-35). Code: `fabric_backend/pilot_scan.py`. Tests:
`tests/test_bl23_pilot_scan.py`. Verified by unit tests against a fake Spark catalog holding the synthetic SAP demo and
the synthetic shop on 21 November 2026. **It has not been run in Fabric yet**; running it once in the demo tenant is a
founder step.

Before the first session you can run one notebook in your own workspace, with your own permissions, that lists what
Krusgraph would read: your lakehouses (or a lakehouse's schemas), their tables, each table's column names and types,
and a row count per table. It turns a first call into a plan: which tables to start with, and which of them a
Krusgraph knowledge pack already knows.

## Get the notebook

```bash
python -m fabric_backend.pilot_scan > krusgraph-pilot-scan.ipynb
```

(`--format fabric` prints the same notebook as Fabric's `notebook-content.py`, for a Git-connected workspace.)

## Import and run it

1. In your Fabric workspace choose **Import** > **Notebook** > **From this computer** and pick
   `krusgraph-pilot-scan.ipynb`.
2. Open it and attach the lakehouse(s) you want scanned under **Lakehouses**; the first one is the default lakehouse,
   where the result is written. A mirrored database is read when it is reachable from the attached lakehouse (for
   example through a shortcut); name it in `MIRRORED` so the summary marks it.
3. Change the parameters cell if you want to: `DATABASES` (empty reads every database the Spark catalog lists),
   `MIRRORED`, `COUNT_ROWS` (`False` reads names and types only), `SCOPE_SIZE` (20), `MAX_TABLES` (2000).
4. **Run all.** The last cell prints where it wrote the two files.

## What it reads, and what it does not

| Reads | Never |
| --- | --- |
| `spark.catalog.listDatabases()`, `listTables()`, `listColumns()`: names and types | a row value: the only query is `SELECT COUNT(*) AS n FROM <database>.<table>` |
| one `COUNT(*)` per table (unless `COUNT_ROWS = False`) | `%pip`, an install, or any import outside the Python standard library |
| | a network call, an API call, or a call to an AI model |
| | a table write: it writes two files, nothing else |

A table whose columns or count cannot be read is listed under "Not read" with the kind of error only (for example
`AnalysisException`), never the error's message, so a message that quotes a value does not reach the files.

## What it writes

Two files in `Files/krusgraph/pilot-scan/` of the default lakehouse, named by the run's time in UTC:
`pilot-scan-<YYYYMMDDTHHMMSSZ>.json` and `.md`. You decide whether to share them. The JSON has:

| Key | What |
| --- | --- |
| `krusgraph_pilot_scan` | the format version, 1 |
| `run_at`, `reads` | when, and "names, types and row counts only; no row values" |
| `totals` | databases, tables, columns, rows |
| `databases` | name, whether you marked it mirrored, number of tables |
| `tables` | database, table, type, column count, row count, columns (name and type) |
| `packs` | per knowledge pack, the tables it knows by name and the pack table each one is |
| `links` | links by name: from table, column, to table, and the rule (`name` or `pack <pack>`) |
| `scope` | the suggested tables, most links first |
| `skipped` | tables not read or not counted, and why |

On the synthetic data in the tests (17 SAP demo tables and 7 shop tables) it reads 24 tables, 154 columns and 329
rows, finds the 17 SAP tables with the SAP pack, 44 links by name, and suggests 20 tables led by `sap_vbpa`,
`sap_vbap` and `sap_kna1`.

## The rules

- **Packs, by name.** The notebook cannot import Krusgraph (it is not installed in your workspace, and the scan installs
  nothing), so the setup cell carries the knowledge packs' names as data: each pack table's name and aliases, its key
  columns, and which pack tables a pack relationship links. A table matches when its name, without case, separators and
  a leading landing word (`sap_`, `bronze_`, `stg_`, ...), is a pack table's name or alias, and it has the pack's key
  columns (the client column may be missing). A pack is reported when it knows at least two tables, one of them by a name
  of the system's own. This is `sap_pack.match`'s name rule without its later refinements (names with a system id or
  client such as `P01_VBAK`, key-column suggestions, mirror metadata): the scan names candidates, `plan_backend` decides.
- **Links by name.** A column `<table>_id`, `<table>id`, `<table>_key`, `<table>_no` or `<table>_code` points at that
  table (singular or plural name); a pack relationship links two tables the pack matched.
- **Scope suggestion.** The `SCOPE_SIZE` tables with the most links (in and out), ties by name, as "How to scope to 20
  tables" in `GETTING-STARTED.md` describes. Name them in `tables` when you ask Krusgraph to plan.

None of these is a check: a link by name can be wrong. The first session counts keys and links against the rows
(`validate_plan`) and says which held.

## Not done yet

- Run once in the demo tenant: this notebook has not run in Fabric. The Spark catalog calls are PySpark's, and the
  `/lakehouse/default` mount is the one `connect_files.py`'s notebook uses for Excel files; how a lakehouse with schemas
  lists its schemas in `listDatabases()` is not verified.
- A download of the notebook from the site or the Start card.
