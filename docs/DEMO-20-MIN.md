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
| only a columns list | `fabric-backend demo --columns columns.csv --schema dbo` (plan and map only; no counts, no questions) |
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

## If something goes wrong

- The browser shows "The demo server did not answer": the terminal window was closed; start it again.
- `pyodbc is not installed`: `pip install pyodbc` and the ODBC driver; or fall back to an export.
- A certificate error at connect: add `TrustServerCertificate=yes` for the visit and tell them to fix the certificate.
- `schema 'dbo' has no tables for this sign-in`: ask for `db_datareader`, or the right schema name.
- The page is slow on a large schema: the health check runs two counting queries per table and relationship over the
  whole tables; on a hundred tables that is a few hundred queries. Point it at one schema, or export the tables that
  matter.

## What the demo does not do, on purpose

No account, no sign-in, no telemetry, no call to any service. It does not write to the source. It does not create
anything in Fabric; that is the hosted connector's job, with the customer's own sign-in.
