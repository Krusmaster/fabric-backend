# The 20-minute demo: script for the person running it

You sit with someone at a mid-sized company, on your own laptop. In twenty minutes they see something of value on
their own data, and nothing of theirs leaves the machine. The tool is `fabric-backend demo`: one local page on
`127.0.0.1`, four steps, a time budget per step, the same inference engine as the hosted connector.

Status (26 October 2026): unit-tested on the synthetic shop schema in SQLite and on a folder of CSV and Excel files
(`tests/test_demo_app.py`), walked through in a browser with Playwright (screenshots of every step, no console errors,
no request to any host but 127.0.0.1). Not yet run by us against a customer's SQL Server; the ODBC path is the one the
local MCP server uses (docs/LOCAL.md), which is unit-tested against recorded SQL Server metadata only.

## Before the visit (10 minutes, once)

On the laptop, Windows:

```powershell
pip install "fabric-backend @ git+https://github.com/Krusmaster/fabric-backend"
fabric-backend demo --sample --no-browser
```

Open http://127.0.0.1:8765/ and click through once so the fonts, the figures and the four steps are familiar. For a
SQL Server visit also install Microsoft ODBC Driver 18 for SQL Server and `pip install pyodbc`. Nothing else: no
account, no cloud, no internet needed during the demo (everything the page loads is in the package).

Ask the customer beforehand, in one line: "Can you give me a read-only login to one database, or an export of a few
tables as CSV or Excel?" Either works. If the answer is "we only have Excel", that is fine; see the end.

## Starting it

| The customer has | You run |
| --- | --- |
| a SQL Server you can reach from the laptop | `fabric-backend demo --odbc "Driver={ODBC Driver 18 for SQL Server};Server=sql01;Database=shopdb;Trusted_Connection=yes;TrustServerCertificate=yes" --schema dbo` (or `Uid=...;Pwd=...` for a SQL login; the string never appears on the page) |
| a folder of CSV / Excel files | `fabric-backend demo --folder C:\data\export` |
| only a columns list | `fabric-backend demo --columns columns.csv --schema dbo` (plan and map only; no counts, no questions). The file can be an INFORMATION_SCHEMA export, a sheet with Table/Column (Tabell/Kolumn) or lines like `Kund.Kundnr`; CSV, TXT or XLSX. Or start without a flag and choose *Paste a columns list* on the page |
| nothing yet | `fabric-backend demo`, then step 1 on the page offers the same choices, including "Try without your own data" |

The terminal prints the address; the browser opens on it. Ctrl+C stops it; the loaded files and the decisions are
gone with it (nothing is written to disk unless the customer downloads an export).

## The four steps, what you say and what you do

The clock at the top right shows the time in the current step and the total. The budget is a guide, not a rule.

### 1. Connect (4 min)

Say: "This runs on my laptop. The page is served on 127.0.0.1, your data is read here and stays here. When I close
it, it is gone." Point at the pill in the header that says so.

Do: pick the source, connect. Read the source notes aloud (how many tables, which files became which tables). If a
file could not be read, the note says why; carry on with the rest.

The step ends with one answer, in one of five states, at the top of step 1 and of the map: **Enough to start**, **We
need your knowledge about …** (a column that could point at two tables, a table without a key, tables nothing links),
**Missing material: …** (rows, a second table, an empty export), **Missing access: …** (the sign-in cannot read the
database, or the laptop has no ODBC driver), **Not supported yet: …** (an .xls, an Access file, a PDF, with what to ask
for instead). There is no percentage of how ready the data is, on purpose: say what is there and who can supply the
rest.

### 2. The map (4 min)

Say: "Every wire is a key or a relationship the engine inferred from names and declared constraints, and every one
carries the rule that made it. Nothing here is guessed silently: a column that could point at two tables is reported,
not linked." Click one wire; read the rule in the right panel. Click a table; show its key and its role.

Do: look at the roles (fact, dimension, bridge) and the subject areas below the graph with the customer. They will
correct you ("that one is not a fact table, it is a staging copy"). That is the point: the map starts a conversation
they usually have with nobody.

Then: Review plan.

### 3. Health check (7 min)

Say: "Now the plan is checked against the rows: is every key unique and free of NULLs, does every reference find its
target. And the engine looks for links it did not dare to make." Each finding has four lines: what we saw, what it
means, the next step, the evidence (the exact counting query, open it if they ask).

Do: go through the findings from the top. Problems (a key that is not unique, orphans) are the most valuable minutes
of the visit; read the counts and ask "did you know?". Suggestions have Accept and Skip. Say what the storyboard says:
"A suggestion is a question. Accept means you decided, not that it is proven." Accept one together; the graph redraws
with the wire marked *confirmed*, and the health check counts it. Skip leaves the column alone. Reset decisions
starts over.

What never happens here: nothing is written to their database, and an accepted suggestion is never shown as verified.

### 4. The value (5 min)

Say: "Five questions your data can answer, proposed from the graph, run here, with the SQL." Open one SQL so they see
it is plain T-SQL they could run themselves. "Which X have no Y" is the one that most often finds a surprise.

Do: download the exports and hand them over on a stick or by mail from their own account: `dictionary.md` (the data
dictionary with the rule per key and relationship), `schema.yml` (dbt sources with tests), `lovable-prompt.md` (a
prompt that builds a first app on this model, with mock data until the API exists), `plan.json` and `er.mmd`.

Close: "The same plan, through the hosted connector in Claude, becomes a GraphQL API in your Fabric workspace, a Power
BI semantic model, wide views and a data agent. That part needs a Fabric workspace and a sign-in; this part needed
neither."

## If the customer only has Excel

Export each sheet to its own CSV, or point the demo at the folder with the workbook: every `.xlsx` is read without
Excel, the first row is the header, a workbook with several sheets gives one table per sheet (`book_Sheet`). Semicolon
and comma separated files both work, decimal commas too. Dates are recognised by the cell's number format. What is
not read: merged headers, formulas without a cached value, charts. If a sheet has a title row above the header, ask
them to delete it or save the sheet as CSV from the header row.

Keys and relationships from exports come from names alone (there are no declared constraints in a file), so expect
more suggestions and fewer rules R0; the health check still counts everything.

## If the customer does not know which systems they have

The first meeting may have one Excel export, a columns list from an e-mail, or nothing. That is enough to begin; the
point of the meeting is to leave with the right export.

Questions to ask, in this order:

1. "Which question do you want answered first?" One question, in their words (for example *what did each customer buy
   last quarter* or *which invoices have no order*). It decides which tables matter.
2. "Where do you look today to answer it?" A report, a screen, a spreadsheet someone keeps. The name on that screen
   or report is usually the system (or the module) the data lives in.
3. "Who exports data from it, and what does the export look like?" The person, not the system, is what you need.
4. "Is there a database behind it that someone can give read access to?" If yes, a login with `db_datareader` on a
   SQL Server is the best material: keys are declared there.

What to ask for, depending on the answer:

| They have | Ask for |
| --- | --- |
| a report or screen they use | the export behind it as Excel (.xlsx) or CSV, *with the header row*, and the same for each list the screen links to (customers, articles, orders and their lines) |
| exports already | the main tables of the question as separate files in one folder, a few thousand rows each is enough; one file per table, file name = table name |
| only a system name | the system's own column list (many systems can print one), or a screenshot of the field list typed into lines like `Kund.Kundnr`; paste it on the page |
| a database and an IT contact | a read-only login (`db_datareader`) and the connection string; run with `--odbc` |
| nothing they may share yet | the column names only (no rows): the map and the questions for the next meeting come from names alone |

Run the demo on what they brought, read the five-state answer at the end of step 1 aloud, and write down the
*knowledge* and *material* lines: they are the agenda of the next meeting. Names from common business systems in
Swedish and English are read (`Kundnr`, `Ordernr`, `Artikelnr`, `Leverantorsnr`, `CustomerNo`, a bare `No` as the key),
and a table without a primary key is reported as such, never given a guessed key. English ERP exports where the order
header and its lines share a `DocumentNo` are only partly linked by names today: expect the answer *We need your
knowledge about …* there, and confirm the link with the customer.

## If something goes wrong

- The browser shows "The demo server did not answer": the terminal window was closed; start it again.
- `pyodbc is not installed`: `pip install pyodbc` and the ODBC driver; or fall back to an export.
- A certificate error at connect: add `TrustServerCertificate=yes` for the visit and tell them to fix the certificate.
- `schema 'dbo' has no tables for this sign-in`: ask for `db_datareader`, or the right schema name.
- The page is slow on a large schema: the health check runs two counting queries per table and relationship over the
  whole tables; on a hundred tables that is a few hundred queries. Point it at one schema, or export the tables that
  matter.

## The hosted path, timed

Measured by the maintainer on 28 October 2026, 15:34:03–15:37:07 UTC, with the hosted connector krusgraph.com/mcp in
Claude, workspace `demo`, lakehouse `demo_lh`, schema `shop` (7 synthetic tables). One tool call at a time; the times
are tool plus agent, not a person's reading and approval time.

| Step | Time | Result |
| --- | --- | --- |
| Connect (`list_workspaces`, `list_sources`) | 13 s | |
| `plan_backend` | 10 s | 7 tables, 6 keys, 6 relationships |
| `validate_plan` | 11 s | 6 of 6 keys unique, 7 of 7 relationships without orphan rows |
| **Checked plan** | **34 s** | |
| `create_backend` | 29 s | shop_api updated |
| `create_semantic_model` | 28 s | shop_model created |
| `create_views` | 16 s | 3 views in schema krusgraph |
| `create_data_agent` | 46 s | shop_agent created and published, 10 example questions |
| `create_silver_notebook` | 17 s | silver_shop updated |
| `create_ontology` | 14 s | HTTP 403 FeatureNotAvailable: ontology is turned off in the tenant's settings |
| **Total, first call to last answer** | **3 min 4 s** | |

Not included: running the notebooks, refreshing the model, the portal steps for shop_api, and a person's reading and
approvals. `create_gold_views` and `create_drift_monitor` created their objects earlier the same day but were not part
of the timed run.

So on a small schema the 20-minute budget has room even for the step into Fabric. A larger schema has not been timed.

## What the demo does not do, on purpose

No account, no sign-in, no telemetry, no call to any service. It does not write to the source. It does not create
anything in Fabric; that is the hosted connector's job, with the customer's own sign-in.
