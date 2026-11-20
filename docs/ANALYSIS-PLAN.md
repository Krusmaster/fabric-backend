# Analysis plan: which SAP analyses your data supports (round AP2)

Two tools, phase 1 of the analysis pack, in the local stdio server and the hosted server:

- **`analysis_plan`** says which of ten SAP order-to-cash analyses the data in a schema supports, ranked, each with
  "Recommended because …", what is missing, the tables and columns it would use and the next step. Read-only.
- **`analysis_notebook_draft`** writes the Fabric notebook for one of the three phase-1 analyses (A7 forecasting, A8 RFM
  segmentation, A3 ABC/XYZ), wired to the tables `analysis_plan` found. It creates nothing and runs nothing.

Krusgraph complements Fabric Data Science. Fabric has the tools to run analyses (notebooks, ML experiments with MLflow,
AutoML, Data Wrangler, semantic link, PREDICT). Krusgraph knows the SAP tables well enough to say which analysis fits
the data, and it writes the first notebook with the joins, the client column and the grain right. The modelling, the
tracking and the scoring run on Fabric's own features, and the analyst starts them. No partnership with, certification
by or endorsement from Microsoft or SAP is claimed.

## 1. How the choice is made: rules, not AI

The choice is a fixed rule per analysis over things Krusgraph already computes. Nothing is trained, nothing is estimated
by a model, and no AI service is called.

- **Metadata**: which table is which SAP table (the SAP pack's names, `sap_pack.pack_table`; CDS view names such as
  `I_BillingDocumentItem` too), the keys, and the relationships of the plan (item -> header, document -> customer master,
  item -> material master). The columns come from `fabric_backend/analysis/o2c.json`, in a fixed order of preference.
  For example, the date is `FKDAT`, then `ERDAT`, on the billing header.
- **Counts** (with a connection, `profile=true`): per sales dataset (billing documents first, else sales orders) the
  rows, the calendar months with rows and the gaps between the first and the last month, the customers and how many of
  them have 2 or more documents, the first-document months, the customers that count as churned by an example
  definition, the materials and in how many months each sold, the currencies, the return or credit documents, and the
  orphans of the joins the analyses use (validate_plan's own count). One statement each, at most `max_items` (default
  20). **Counts only**, as in `profile.py`: no row value leaves the database. A month is compared inside the query, and
  only the number of months comes back. Personal-data columns (names, streets, telephone numbers, e-mail addresses) are
  never read.

Each rule has **hard inputs**: if one is not there, the analysis is `missing`, and the answer names the table or field
and how to land it. A rule also has **soft inputs**, each scored linearly between a floor (0) and a target (1).

    readiness = mean of the soft parts × quality     (quality 0.8 when a join the analysis needs has orphans)
    score     = value × readiness                    (value 1-5: Krusgraph's own judgement, replaced by `weights`)
    ready     readiness ≥ 0.8 and no soft part below 0.5
    partial   readiness ≥ 0.4, or capped there by one soft part below 0.5 (the weak part is named)
    missing   a hard input missing, a soft input below its floor, or readiness < 0.4 (score 0)

Ties are broken by the catalogue's order, so the same input always gives the same ranking. `rule_version` is
`ap-o2c-1`. The thresholds and values are starting points, not findings: a data scientist should validate them.

## 2. The rules

| # | Analysis | Value | Rule, in one line |
| --- | --- | --- | --- |
| A1 | Margin by customer and product | 5 | R8: revenue and a cost (VBRP.WAVWR, a cost condition in KONV/PRCD_ELEMENTS, or ACDOCA); without a cost, it offers revenue concentration instead |
| A2 | DSO, payment behaviour, aging | 5 | R6: customer open and cleared items (BSID/BSAD or ACDOCA) must be there |
| A3 | ABC / XYZ | 3 | R4: a material column linked to the material master and an amount or quantity; materials 20 → 100; XYZ also needs 12 months, with half the materials selling in 6 or more of them |
| A4 | Cohorts and churn | 3 | R3: a linked customer and at least 12 months; months 12 → 24, first-document months 3 → 6; a churn model only from 50 churned customers |
| A5 | On-time-in-full | 4 | R5: delivery items linked to order items, a requested date (VBEP.EDATU or VBAK.VDATU) and the goods issue date (LIKP.WADAT_IST); otherwise it offers in-full only |
| A6 | Price realisation | 4 | R7: document conditions (KONV or PRCD_ELEMENTS); otherwise it offers unit price dispersion, as a proxy |
| A7 | Forecasting | 4 | R1: a date and an amount or quantity, item joined to header; months 12 → 24, no gap, one currency; per material: intermittent if fewer than half sell in 18 or more months |
| A8 | RFM segmentation | 4 | R2: a customer column linked to the customer master, a date and an amount; customers 50 → 200, share with 2 or more documents 0.3 → 0.6, months 6 → 12; k-means from 200 customers |
| A9 | Credit risk early warning | 4 | R9: A2's payment history and the customer master; a warning list, not a credit rating |
| A10 | Returns and credit memos | 3 | R10: documents of the return or credit types (`document_types`, by default SAP's standard RE, G2); return documents 10 → 30 |

`land_next` turns the gaps around: the tables that would unlock the most value, ranked by the summed value of the
analyses they unlock.

## 3. What it says on the synthetic samples (unit tests, 18-19 November 2026)

All three samples are synthetic and SAP-shaped, not SAP data. `tests/test_ap2_analysis_plan.py` pins each answer in
`tests/golden/ap2_analysis_plan_*.json`.

- **The small SAP demo** (`sap_demo.py`, 17 tables, a few days of October 2026): nothing is ready. A7 is `missing`
  with "Only 1 month(s) of billing documents history; forecasting needs at least 12 and about 24". A8 is `missing`:
  1 billed customer, and RFM needs at least 50. `land_next` starts with BSID + BSAD or ACDOCA (unlocks A2, A9).
- **sap_sd** (`sap_sample.py`, 24 months): A7 ready (4.0); A8 partial, capped by 108 customers (78.7 % with 2 or more
  invoices); A3 ready with ABC only (XYZ not ready: 59 of 149 materials sold in 6 or more months); A4 ready with cohort
  tables only (24 churned customers, below 50). This is the design's worked example.
- **The 36-month demo** (`sap_demo36.py`, below): A7, A8, A3 and A4 are ready. A7 has 36 months without a gap. A8 has
  293 customers, k-means is offered and nearly all of them have 2 or more invoices. A3 has 492 materials sold, with XYZ
  ready. Margin, DSO, OTIF, price and credit risk are missing, each naming its table.

## 4. The notebooks (A7, A8, A3)

`analysis_notebook_draft(analysis="A7" | "A8" | "A3")` returns the steps and `notebook-content.py` (Fabric's Git
format). The library also gives `.ipynb`. Each notebook has these cells:

1. **Why**: the rule's "Recommended because", its caveats and thresholds.
2. **Parameters**: source schema, output schema (default `krusgraph_analysis`), date range, currency, document types,
   the ML experiment's name, the counts at plan time, `TOLERANCE`, an optional semantic model to cross-check.
3. **Read**: item rows joined to their header by the plan's relationship, with the client column in the join. Amounts
   are summed from the items, never from a header repeated over its items. SAP's `YYYYMMDD` text and DATE columns both
   become dates, and SAP's initial date is no date.
4. **Data check**: the plan's counts are counted again. If they differ by more than `TOLERANCE`, the notebook stops
   before any model is fitted. The ML experiment is set here, and semantic link (SemPy) can compare a semantic model's
   row count.
5. **Explore**: the prepared table, to open in Data Wrangler.
6. **Analysis**, every run logged to the ML experiment (MLflow):
   - A7: monthly revenue with a seasonal naive and an ETS baseline, then AutoML (FLAML) in pandas mode, backtested on
     the last months. The baseline stays beside the model.
   - A8: R, F and M quintile scores and named segments, plus k-means (scikit-learn) over k = 3-6 by silhouette when
     there are enough customers.
   - A3: ABC by cumulative revenue share and XYZ by the coefficient of variation of monthly quantity. The cut-offs are
     parameters (they are conventions).
7. **Output**: one table (`forecast_monthly`, `rfm_segments`, `abc_xyz`) with the table property `krusgraph.analysis`.
   A table of that name without the property is never replaced.
8. **Next**, commented out: register a model and score it with PREDICT, or add the table to the semantic model.

A library that is not installed is skipped with a printed line, never silently. On 19 November 2026 the three notebooks
ran every cell on a local PySpark 4.0.1 against the 36-month demo, without MLflow, statsmodels, FLAML or
scikit-learn, so those steps were skipped (`tests/test_spark_notebooks.py`). They have **not yet run in Fabric**. Learn
states no release status for AutoML, PREDICT, Data Wrangler or semantic link, so none is called generally available
here.

## 5. Limits

- Only the order-to-cash catalogue (`area="o2c"`) is built. Notebooks exist for A7, A8 and A3. The other seven are
  recommended or reported missing by their rules, and their notebooks are planned.
- The SAP pack does not yet name due, clearing, requested or goods-issue dates, cost fields or condition types. The
  rules match those by name (marked in the answers), and the pack gaps are planned.
- CDS view names are matched by the pack's names. This has not been tried on a live CDS landing.
- The counting statements are written for the Fabric SQL analytics endpoint and SQL Server (and SQLite in the tests).
  On Databricks the tools answer "not on Databricks".
- The thresholds, values and document-type defaults are starting points. Pass `weights` and `document_types` to use
  your own.
- The answer says nothing about what an analysis will show. It says only that the data is there to run it.

## 6. The larger synthetic demo: `sap_demo36`

`fabric_backend/sap_demo36.py` generates the 17 tables and columns of the small SAP demo, seeded and deterministic:
36 monthly periods (November 2023 to October 2026) with a trend and a yearly season, 300 customers (some start late,
some stop), 500 materials with a skewed value and steady, seasonal or sporadic demand, orders, schedule lines,
deliveries, invoices, document flow (VBFA) and partners (VBPA, with legitimately blank partner fields). It has about
130 000 rows. Planted: one orphan item (order 0000099999), one invoice whose header amount is doubled, three billing
items without a material, two customers without a city and one order without a condition number. Every name is
"Demo …" and every e-mail address is at example.com. `examples/sap_demo36/` holds a small CSV sample (four customers),
and the full data is never committed.

To load it into a lakehouse (nothing in `dbo`, `sap_silver` or `sap_gold` is touched):

1. `python -m fabric_backend.sap_demo36 --ipynb sap_demo36.ipynb` (or `--source notebook-content.py`).
2. In the Fabric workspace, choose **Import → Notebook → From this computer**, select `sap_demo36.ipynb`, open it and
   attach the lakehouse.
3. Run all with `DRY_RUN = True` (the default). It prints the row count of each table and writes nothing.
4. Set `DRY_RUN = False` and run all again. It writes `sap_demo36.sap_t001` … `sap_demo36.sap_adr6` as Delta tables.
   The notebook refuses `dbo` and the silver and gold schemas, and it replaces only tables it wrote itself (table
   property `krusgraph.demo`).
5. Then run `analysis_plan` with `schema="sap_demo36"`, and `analysis_notebook_draft` for A7, A8 or A3.

## 7. In the Fabric item

Round WB4 (20 November 2026) brings the plan into the Krusgraph Model item in Fabric. Under **Next, with other Fabric
workloads** (after a Create, and on the Data product page) the item shows **Recommended analyses**, once a key or link
has passed **Check against the rows**:

- The engine route `POST /workload/v1/analysis` runs `analysis_plan` on the item's reviewed plan (keys and links the
  person rejected are left out) with the row counts. Read-only, counts only, no AI, the same rules and `rule_version`
  as the tool.
- The analyses keep the tool's ranking. Each says its readiness in a word (Ready, Partly ready, Not ready yet, Not
  applicable), one line "Recommended because …", and what is missing. A not-ready analysis says what data would make it
  ready, and the fold names what to land first.
- A **ready** A7, A8 or A3 offers its notebook: **Download notebook (.ipynb)** and **Copy the code**, the same notebook
  `analysis_notebook_draft` writes (section 4). There is no Create in the workspace: no Krusgraph tool creates an
  analysis notebook, so the person imports it (Workspace, Import, Notebook) and runs it. Krusgraph runs nothing.
- The other analyses offer the request to copy into Claude (`analysis_notebook_draft` for a partly ready A7, A8 or A3,
  `analysis_plan` for the rest).

On the 24-month sample `sap_sd` (the e2e engine's `sap` scenario): A7 Ready (with its notebook), A8 Partly ready, A3
Ready (with its notebook; XYZ not yet), A4 Ready (its notebook is planned), six not ready. On a schema without SAP
tables the section says there is nothing SAP to rank. Details for developers: `docs/WORKLOAD-DEV.md`, section
"Recommended analyses". Not yet run in Fabric.
