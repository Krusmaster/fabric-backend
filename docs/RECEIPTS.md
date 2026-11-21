# Receipts: every number with the query that counted it

21 November 2026, round BL1 (backlog C-36). Code: `fabric_backend/receipt.py` and the `receipt` command in
`fabric_backend/krusgraph_cli.py`. Tests: `tests/test_bl1_receipt.py`. Verified by unit tests on the synthetic shop and
the synthetic SAP demo (SQLite) on 21 November 2026; not yet run against a live Fabric SQL endpoint.

## Why

Krusgraph's claim is that its numbers are counted, not guessed: a key is unique in all 4 rows, a link holds for 6 rows
with 1 orphan, a header has up to 3 line rows. A receipt lets anyone check that claim without us: each number comes
with the exact read-only statement that produced it. An architect, a partner or a reseller in a demo runs that
statement on the same tables and gets the same number back.

## Make one

```bash
krusgraph receipt --sample sap --human > krusgraph-receipt.md      # the synthetic SAP demo, offline
krusgraph receipt --sample shop --json                             # rows as JSON, for an agent or a script
FABRIC_ODBC=... krusgraph receipt --odbc-from-env --schema dbo --human > krusgraph-receipt.md
```

`receipt` runs the same checks as `krusgraph plan` (`validate_plan`), then lists what they counted. The command writes
no file itself (the CLI never does, docs/CLI.md "Safety model"); `--human` prints the Markdown, and the shell writes it.

## What is in it

One row (in JSON) or one section (in Markdown) per number:

| Field | What it is |
| --- | --- |
| `kind` | `key`, `link`, `extended link` (valid on a date, filtered, or on a unique non-key column), `amount level`, `flat amount`, or `not counted` |
| `item` | the id review and validate use: `key:<table>`, `rel:<source>.<cols>><target>`, `amount:<header><<line>` |
| `sentence` | the number as Krusgraph says it ("Key sap_kna1(MANDT, KUNNR): unique in all 4 rows.") |
| `sql` | the statement, built by the same functions validate uses: `evidence.key_sql`, `evidence.relationship_sql`, `evidence.extended_sql`, `amounts.lines_per_header_sql`, `amounts.flat_sql` |
| `counts` | the columns that statement answers, with the values validate got (`n`, `nulls`, `distinct_keys`; `with_value`, `orphans`; ...) |
| `dialect` | `tsql` (Fabric's SQL endpoint, a warehouse, SQL Server), `sqlite` (the local samples and folders), or `databricks` |
| `generated_at` | the UTC time of the receipt; the counts are over the whole tables at that moment |

Where validate counted several links of one table in one combined statement (to read the table once), the receipt
gives each link's own statement. It counts the same numbers; `evidence.combined_relationship_sql` explains why.

Items validate did not count (the time budget ran out, a query failed, beyond `--max-items`) are listed as not counted,
with no number and no statement. A receipt never turns "not counted" into a number.

A receipt holds table names, column names and counts. It holds no row value: a test compares every receipt of the two
samples with every cell value of those samples.

## Re-run one (for a buyer)

1. Open the SQL endpoint of the same lakehouse or warehouse (in Fabric: the SQL query editor, or SSMS / Azure Data
   Studio with your own sign-in). Read access is enough; every statement is a `SELECT` that only counts.
2. Copy the statement from the section's `sql` block and run it.
3. Compare the answer's columns with the section's counts line. `avg_lines` is rounded to two decimals in the receipt.
4. A different number means the rows changed since `generated_at`, or the statement ran on other tables (check the
   schema name in `[schema].[table]`). Run `krusgraph receipt` again to get a new receipt.

On the local samples the statement is already in SQLite's form (`COUNT` instead of `COUNT_BIG`).

## Next step (not in this round)

"Show the query" beside each number in the chat card and in the Model editor, from `receipt.build`. Those files belong
to the smooth chain (SM2-SM7) today; a round after the chain wires it in.
