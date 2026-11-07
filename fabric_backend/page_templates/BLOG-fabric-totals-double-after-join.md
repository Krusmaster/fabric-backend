# Why Your Fabric Totals Double When You Join Orders to Order Lines

Your revenue did not grow overnight.

You join orders to order lines in a Fabric lakehouse or warehouse, then sum an order-level column. Every order total is now counted once per line, not once per order. Two lines, double. Three lines, triple. The query raises no error, so the number reaches a report first.

**Quick answer:** a join from orders to order lines is one-to-many. It repeats each order row for every matching line, so summing `order_total` afterwards counts each order several times. Compare `COUNT(*)` with `COUNT(DISTINCT order_id)` across the join to confirm it. Then aggregate the lines to one row per order before you join.

## The symptom: your order total just doubled

Take two small tables in a Fabric lakehouse. The data is synthetic and shown in full below. Every number in this article comes from running these queries on that data in SQLite on 7 November 2026, not in a live Fabric workspace. The queries are plain T-SQL apart from the string concatenation noted below.

`orders` has 4 rows, and its `order_total` column sums to 530:

| order_id | customer_id | order_total |
|---|---|---|
| 1001 | 1 | 120.00 |
| 1002 | 2 | 80.00 |
| 1003 | 1 | 250.00 |
| 1004 | 3 | 80.00 |

`order_lines` has 8 rows: 2 lines for order 1001, 2 for 1002, 3 for 1003 and 1 for 1004. Its `line_amount` column also sums to 530:

| order_id | line_no | line_amount |
|---|---|---|
| 1001 | 1 | 70.00 |
| 1001 | 2 | 50.00 |
| 1002 | 1 | 50.00 |
| 1002 | 2 | 30.00 |
| 1003 | 1 | 100.00 |
| 1003 | 2 | 100.00 |
| 1003 | 3 | 50.00 |
| 1004 | 1 | 80.00 |

Now the obvious query:

```sql
SELECT SUM(o.order_total) AS revenue
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id;
```

It returns 1230. That is 2.3 times the real figure, and nothing in the query looks wrong. The only visible clue is the row count, covered below.

## Why it happens: join grain vs table grain

**Grain** is what one row in a table represents. In `orders`, one row is one order. In `order_lines`, one row is one line. Microsoft's modelling guidance says fact tables should always load data at a consistent grain ([Microsoft Learn, star schema guidance](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema)).

**Join fan-out** is what happens when you join a table to one at a finer grain. The result takes the finer grain. Each order row is copied once per matching line, and `order_total` goes with every copy:

- Order 1001: 120 × 2 lines = 240
- Order 1002: 80 × 2 lines = 160
- Order 1003: 250 × 3 lines = 750
- Order 1004: 80 × 1 line = 80

The sum is 1230. The inflation isn't random: each order is weighted by its own line count.

### How to find the grain of a fact table in Fabric

The grain is the smallest set of columns that is unique per row. For a line table it is usually the header reference plus a line number. Krusgraph, an MCP tool that reads Fabric table metadata, keys a line table on exactly that pair when it infers relationships.

Confirm it with a count. If `COUNT(*)` equals `COUNT(DISTINCT CONCAT(order_id, '-', line_no))`, the pair is the grain. On the example both are 8. (In SQLite the concatenation is written `order_id || '-' || line_no`.)

### Cross join: the same failure, at full size

A **cross join** pairs every row of one table with every row of another. In practice it is rarely written on purpose. It appears when a join condition is missing, or when a key is duplicated in a table you assumed was unique. Two `customers` rows for one `customer_id` double every order for that customer.

## Diagnose it before you trust a total

Run this fan-out check before you trust any total built on a join. It compares rows with distinct order keys, before and after the join:

```sql
SELECT
  COUNT(*)                   AS joined_rows,
  COUNT(DISTINCT o.order_id) AS distinct_orders
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id;
```

On the example data:

| Measure | Before join (`orders`) | After join |
|---|---|---|
| Rows | 4 | 8 |
| Distinct `order_id` | 4 | 4 |
| `SUM(order_total)` | 530 | 1230 |

If `joined_rows` is larger than `distinct_orders`, the join has fanned out. Any order-level sum on top of it is wrong. Equal counts mean one row per order.

To see where the duplication comes from, group by the key:

```sql
SELECT o.order_id, COUNT(*) AS rows_per_order
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
GROUP BY o.order_id
HAVING COUNT(*) > 1;
```

It returns three orders, with 2, 2 and 3 rows. Run the same query on a table you believe has a unique key, such as `customers`. Any row it returns is a duplicate key.

The pattern is not limited to hand-built tables. In SAP data replicated to Fabric, joining VBAK (order header) to VBAP (order items) repeats the header value VBAK.NETWR on every item row. Summing it multiplies the order value once per line.

## Fix it: pre-aggregate before joining

**Pre-aggregation** means reducing the finer-grained table to the other table's grain before the join. Aggregate the lines to one row per order, then join:

```sql
WITH line_totals AS (
  SELECT order_id,
         SUM(line_amount) AS lines_total,
         COUNT(*)         AS line_count
  FROM order_lines
  GROUP BY order_id
)
SELECT COUNT(*)            AS joined_rows,
       SUM(o.order_total)  AS revenue,
       SUM(lt.lines_total) AS revenue_from_lines
FROM orders AS o
JOIN line_totals AS lt ON lt.order_id = o.order_id;
```

Result on the example data: 4 rows, revenue 530, revenue from lines 530. Rows went from 8 back to 4, and the total is back to the true figure. Rerun the fan-out check here and both counts match.

This is the fix to reach for first. It is plain T-SQL, so it runs in a lakehouse SQL analytics endpoint, a warehouse or a view. Line-level measures such as `line_count` stay available in the same result.

## Fix it: COUNT DISTINCT and window-function alternatives

| Fix | What it does | Result on example | Use it when |
|---|---|---|---|
| Pre-aggregation | Groups lines to order grain before the join | 530 | Default choice |
| Window function (`ROW_NUMBER`) | Keeps one joined row per order, then sums | 530 | You need line columns in the same query |
| `COUNT(DISTINCT order_id)` | Counts orders once, however many rows | 4 orders | You need a count, not a sum |
| `SUM(DISTINCT order_total)` | Sums each distinct value once | 450 | Never for totals |

A **window function** computes a value across related rows without collapsing them. Number the joined rows per order and keep the first one. That restores order grain:

```sql
SELECT SUM(order_total) AS revenue
FROM (
  SELECT o.order_total,
         ROW_NUMBER() OVER (PARTITION BY o.order_id ORDER BY l.line_no) AS rn
  FROM orders AS o
  JOIN order_lines AS l ON l.order_id = o.order_id
) AS x
WHERE rn = 1;
```

**COUNT DISTINCT** counts each distinct value once. It fixes counts; it doesn't fix sums.

`SUM(DISTINCT order_total)` looks like the sum version of the same idea. It removes duplicate values, not duplicate orders. Two orders in the example both total 80.00, so one disappears. The result is 450 instead of 530.

That error is quieter than the original, since 450 looks plausible.

## Fix the semantic model too

A corrected query does not protect a Power BI semantic model built on the same tables. Say the model loads a flat table built from the naive join, so `order_total` sits on every line row. A measure that sums it there inflates exactly as the query did.

Microsoft generally does not recommend relating two fact tables with many-to-many cardinality. It recommends a star schema with one-to-many relationships instead ([Microsoft Learn, many-to-many relationship guidance](https://learn.microsoft.com/en-us/power-bi/guidance/relationships-many-to-many)). For this case:

- Keep order-level amounts in a table at order grain, related one-to-many to the lines.
- Sum line-level amounts from the line table.
- Treat a relationship that defaults to many-to-many as a warning that neither column is unique, and run the fan-out check on both tables.

## Catch fan-out before it reaches a report

The fan-out check works when you know which joins need it. In an unfamiliar lakehouse, you often don't.

The free [check on krusgraph.com](https://krusgraph.com/check) reads CSV or Excel files, or a pasted list of columns. It reports keys, relationships and orphan rows, each with the rule behind it.

One built-in example is "A total that doubles". The check needs no account. Files are read in your browser, not uploaded.

With the Krusgraph MCP connector, `validate_plan` counts duplicate keys, NULL keys and references with no matching row. `create_backend` doesn't run it automatically, so you ask for it. The steps are in the guide to [review a check before you create anything from it](https://krusgraph.com/docs/explore-and-check/review-check-then-create).

What a passing check shows, and what it does not:

- **Shows:** the data agrees with the plan today.
- **Does not show:** that the plan means the right thing. A person still confirms each relationship.

## FAQ

### Why does my revenue double when I join two Fabric tables?

One table is at a finer grain than the other. Joining orders to order lines repeats each order once per line. An order-level revenue column is then summed once per line. Aggregate the line table to one row per order before the join.

### Does SELECT DISTINCT fix duplicate rows after a many-to-many join?

`DISTINCT` fixes it only by accident: it removes rows identical in every selected column, hiding fan-out in one query and dropping real rows in the next. Fix the grain instead, by pre-aggregating or adding a bridging table between the two sides. You can also [run a check on exported Fabric tables](https://krusgraph.com/check) to find the keys that are not unique.
