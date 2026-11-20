# A guided page for Krusgraph Migrate: draft (Q2)

Round Q2, 16 November 2026, written by a scheduled Claude session with no live user. **A draft in `docs/`, not a page
of the site**: nothing here is linked from krusgraph.com, in the navigation, in the sitemap or in `llms.txt`'s page
list. It becomes `/migrate` only when the founder says so, after the points in section 5. Prices are not on it and
are kept outside this repository.

What it is for: a person who has a Qlik app and wants it as a Power BI semantic model on Fabric follows four steps in
their chat client, with the three tools this round built (`qlik_plan`, `qlik_measures_draft`, `qlik_reconcile_draft`).
The page says what each step gives, what it does not, and where the load script goes.

Rules for the page, as for every page: no word from the sales-word list (`tests/test_site.py`, `SALES`), no claim
that a migration gets faster, cheaper or compliant, no share of anything "converted", nothing presented as tested
that was not, no "partner", "certified" or "endorsed". Qlik is named only to say what is read.

---

## 1. The page, as text

> # Krusgraph Migrate: from Qlik to Power BI
>
> Move a Qlik app to a Power BI semantic model on Microsoft Fabric, one step at a time, and see what each step
> decided and why. Krusgraph reads your load script by fixed rules. It uses no AI model, connects to nothing on the
> Qlik side and runs no Qlik expression.
>
> **Status: experimental.** The three tools are unit-tested on a synthetic app and on public load scripts. They
> have not read a script from a customer's Qlik installation, and the rules about Qlik's behaviour are written from
> public knowledge of its documentation, not checked against a Qlik engine. Read every result as a draft to review.
>
> ## What you need
>
> - The app's **load script** as text: copy it from the data load editor, or export a `.qvs` file.
> - The app's **master measures** (name and expression).
> - For the last step, a few **KPI values exported from the app** with no selections made.
> - A Fabric lakehouse where the app's tables are landed, or will be, from their original sources.
> - Krusgraph connected to your chat client ([Docs](/docs)), or the local server on your own machine (below).
>
> ## Step 1. Read the load script
>
> Paste the script and ask: *"Read this Qlik load script and plan the model."*
>
> You get the tables with a column name each that a lakehouse accepts, the fields that link them, every synthetic
> key and circular reference, and a proposed star schema: facts, dimensions and what is in between. Each statement
> that was not read is listed with its line. Control statements (If, For, Sub) are listed and the loads inside them
> are read as if each ran once; an included file that you did not paste is listed as not given.
>
> **The part that needs you.** Qlik links two tables on every field name they share. A Power BI relationship has
> one column per side and needs a side where the value is unique. So each synthetic key is put in one of five
> cases, and nothing is picked silently:
>
> | Case | What goes into the plan |
> |---|---|
> | One field links | A relationship on that field, and for the other shared fields the number of rows that matched on the link but differed there |
> | A combined key | One relationship on the fields together, carried as one key column |
> | Two facts sharing dimensions | No relationship between the two; each shared field is a dimension both relate to |
> | A person decides | Nothing; the candidates are listed |
> | Not decided | Nothing, until the rows are counted |
>
> ## Step 2. Land the tables and count
>
> Land the tables in a lakehouse under the names from step 1, then ask: *"Count the plan in workspace W, lakehouse
> L."* The one side of every link now comes from counts in the rows, each synthetic key is decided by counts, and
> the answer names the rows that will move numbers: rows without a match (in Qlik they associated with nothing; in
> a Power BI model they land on the blank row), and rows that a synthetic key kept apart.
>
> Before the tables are landed, the one sides come from names, and every such line says "by name, not counted".
>
> ## Step 3. Draft the measures
>
> Paste the measures and ask: *"Draft DAX for these Qlik measures."* Each expression gets one of three labels:
>
> | Label | Meaning | Examples |
> |---|---|---|
> | Translated | Every part has a rule, and nothing depends on where the measure is used | `Sum(LineAmount)`, `Count(DISTINCT CustomerID)`, `Sum(Quantity * UnitPrice)`, `Sum(a) / Sum(b)` |
> | Suggested | A rule gives DAX, and the answer says when it gives another number than Qlik | a set modifier with fixed values, `TOTAL`, `{1}` |
> | Not translated | No rule; the reason is said, and you decide | `Aggr()`, `P()` and `E()`, a search inside a set, an alternate state, a dollar-sign expansion computed when the app runs |
>
> The counts per label are of your expressions. No share is promised in advance, and the DAX has not been run.
>
> ## Step 4. Build the model
>
> With the plan's keys and relationships, Krusgraph's building tools draft and create the semantic model (a dry run
> first, as always). This is the same step as for any plan; see [Docs](/docs).
>
> ## Step 5. Reconcile the numbers
>
> Export each KPI from the Qlik app with no selections, one row per value of what it is grouped by. Ask: *"Compare
> these KPI values with the migrated tables."* You get one T-SQL statement per KPI. Run it on the lakehouse's SQL
> analytics endpoint: it returns the Qlik value, the new value, the difference and a status per row. Give the rows
> back and the comparison is filled in.
>
> A difference is listed as **open**. Krusgraph names no reason by guess: the checks that may explain it are listed
> with the plan's own counts, and a reason counts when a count reproduces the difference.
>
> ## Where your load script goes
>
> **With the hosted connector (the default):** the script, the expressions and the exported values pass through
> krusgraph.com for the call and are not kept after it. The answer leaves out inline rows, connection strings and
> the value of any variable whose name looks like a secret.
>
> **On your own machine only:** install the open-source package and run the same three tools in the local server.
> Nothing is sent to krusgraph.com.
>
> ```
> pip install "fabric-backend[mcp] @ git+https://github.com/Krusmaster/fabric-backend"
> fabric-backend-mcp --help
> ```
>
> Add it to your chat client as a local MCP server ([the local guide](https://github.com/Krusmaster/fabric-backend/blob/main/docs/LOCAL.md)).
> Your chat client's own model still sees what you paste into the chat: that is between you and that client.
>
> ## What it does not do
>
> - It does not open a `.qvf` file, read `.qvd` data files, or connect to Qlik.
> - It does not read sheets, charts or bookmarks, and creates no report from them.
> - It does not run the script: a table whose name or fields are built by dollar-sign expansion is listed with that
>   name, and you say what it is.
> - It does not apply Generic, Hierarchy or IntervalMatch; those loads are listed as not read.
> - It does not rebuild Section Access as row-level security; it says that the script has one.
> - It does not move the data. The rows come from the original sources.
>
> *Qlik, QlikView and Qlik Sense are trademarks of QlikTech International AB. Power BI and Microsoft Fabric are
> trademarks of Microsoft. Krusgraph is made by Kruse Consulting AB and is affiliated with neither.*

---

## 2. One example, from the tests

The synthetic script `tests/fixtures/q1/sales.qvs` (nine tables of an invented shop) with the synthetic rows of
`tests/test_q1_qlik.py`. These are the tools' own words (`kg_card`), from `tests/test_q2_qlik_tools.py`.

**Step 1 and 2, `qlik_plan`, counted in the rows:**

> Read 9 tables and 8 linking fields from the load script; 9 relationships are in the plan. Nothing was created.
> - 3 synthetic keys: 1 two facts sharing dimensions, 1 a combined key, 1 one field links.
> - 1 circular reference: 1 no longer a loop in the plan.
> - Proposed star schema: 4 facts, 3 dimensions, 2 tables in between, 1 new dimension to build.
> - The one sides were counted in the rows.
> - 1 statement was not read.

**Step 3, `qlik_measures_draft`, 24 expressions:**

> 9 of 24 expressions translated by rule, 7 suggested, 8 not translated. Nothing was created and no DAX was run.

| Qlik | Label | DAX, or why not |
|---|---|---|
| `Sum(Quantity * UnitPrice)` | translated | `SUMX('OrderLines', 'OrderLines'[Quantity] * 'OrderLines'[UnitPrice])` |
| `Sum({<Channel={'web'}>} SalesAmount)` | suggested | `CALCULATE(SUM('StoreSales'[SalesAmount]), 'StoreSales'[Channel] IN {"web"})`; equal to Qlik when Channel is not a dimension of the visual |
| `Avg(Aggr(Sum(LineAmount), OrderID))` | not translated | Aggr() builds a virtual table over dimensions; its DAX depends on the model and is a person's decision |

**Step 5, `qlik_reconcile_draft`, nine KPIs with planted differences:**

> Compared 12 rows for 9 KPIs: 9 equal, 3 not.
> - 9 rows equal within 0.005, 1 different, 1 only in Qlik, 1 only on the migrated tables.
> - 3 rows have no result yet.
> - Each difference is open: no reason is named until a count reproduces it.
> - 3 KPIs have no SQL: Share, List value, By month.

The numbers above are of a synthetic app written to hold one of each case. They say nothing about any other app.

## 3. Where the page would sit, when it is a page

| | |
|---|---|
| Path | `/migrate` (the Website area in `CONTRIBUTING.md` was open on 16 November 2026 except `sap.html`; this round did not take it) |
| Template | `fabric_backend/page_templates/migrate.html`, with the status word rendered from `tool_status.py` as on every page |
| Navigation | Not in the top navigation at first; linked from `/docs` beside the three tools' rows, and from the use cases when there is one |
| Machine-readable | A line in `llms.txt`'s page list and a `/migrate.md`, as the other pages have |
| Tests | The sales-word test and the claims tests cover a new template once it is in `pages.py`'s routes |

## 4. The paragraph for the privacy page (draft)

> **Qlik load scripts.** When you use the tools that read a Qlik load script, its measures or exported KPI values
> through the hosted connector, that text passes through the server for the call and is not kept after it. The
> answer leaves out the rows of inline tables, connection strings and the value of variables whose name looks like
> a secret. To keep the text on your own machine, use the local server.

## 5. Before this becomes a page

1. The founder's yes to publishing it, and to the display text "Krusgraph Migrate: from Qlik to Power BI".
2. The privacy paragraph above on `/privacy` in the same deploy.
3. One real load script read (a trial Qlik Sense app with synthetic data), so that "experimental" rests on more
   than public scripts. Until then the status sentence stays as written.
4. A lawyer's reading of the trademark line and of what is read (`QLIK-MIGRATION-PRODUCT.md` 2.1).
5. A screenshot or a film of the four steps in a chat client, made from a real run.

## 6. Not to be said on the page

That Krusgraph migrates, converts or translates a Qlik app, or any share of one. That numbers are reconciled (they
are compared, and differences are listed as open). Anything about speed, cost, effort or compliance. Any customer.
Anything about Qlik's product that is not needed to say what is read.
