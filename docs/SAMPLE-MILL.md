# The manufacturing sample ('mill')

A synthetic manufacturing company beside the shop, for demos and tests (round n192). The data is generated from a seed
by `fabric_backend/mill.py` and is the same on every run. The names of its tables and columns are plain English words of
our own. They do not copy or follow any ERP vendor's tables, columns or codes. Company, customer, supplier and item
names are invented.

## The company

**Ystervik Mekaniska (fictional)** is a Swedish workshop that makes conveyor rollers, pump units, gearbox housing sets,
a hydraulic tensioner and a drive station for other manufacturers. It buys steel bar, tube and plate, bearings, castings,
motors, seals, fasteners and paint. It saws, turns, mills and welds its own parts, and assembles, paints, tests and
packs finished goods to order. Its customers are plants and workshops in Sweden, Norway, Finland, Denmark and Germany,
and some of them belong to a group (a parent customer with several sites).

Two years of dates, 1 November 2024 to 31 October 2026. The open work at the end (promised, planned and expected dates)
can lie up to a few weeks after that.

## The tables

Sixteen tables, 5 012 rows with the default seed (7). Each table numbers its rows in a range of its own (customers from
10001, suppliers from 20001, items 100–599, sales orders from 30001, and so on), so an id of one table is never by chance
a value of another.

| Table | Rows | Key (rule) | Points at |
| --- | ---: | --- | --- |
| `customers` | 32 | `customer_id` (K2) | itself: `parent_customer_id` (not linked, see below) |
| `suppliers` | 12 | `supplier_id` (K2) | |
| `items` | 74 | `item_id` (K2) | `suppliers` (R1). 12 finished goods, 26 parts, 36 raw materials, `standard_cost` per item |
| `bill_of_materials` | 137 | `parent_item_id` + `component_item_id` (K4) | `items` twice, as parent and as component (R4, role columns) |
| `work_centers` | 8 | `work_center_code` (K2, a code such as `CNC1`) | |
| `sales_orders` | 200 | `sales_order_id` (K2) | `customers` twice: `bill_to_customer_id` and `ship_to_customer_id` (R4, role columns) |
| `sales_order_lines` | 499 | `sales_order_id` + `line_no` (K5, the composite key) | `sales_orders`, `items` (R1) |
| `purchase_orders` | 120 | `purchase_order_id` (K2) | `suppliers` (R1) |
| `purchase_order_lines` | 203 | `purchase_order_id` + `line_no` (K5) | `purchase_orders`, `items` (R1) |
| `production_orders` | 317 | `production_order_id` (K2) | `items`, `work_centers`, `sales_orders` (R1); planned and actual start and finish |
| `production_operations` | 1 451 | `production_operation_id` (K2) | `production_orders`, `work_centers` (R1); setup and run hours |
| `inventory_transactions` | 1 158 | `inventory_transaction_id` (K2) | `items`, `production_orders`, `purchase_orders` (R1); receipt, issue, adjustment |
| `deliveries` | 496 | `delivery_id` (K2) | `sales_orders` (R1) and `sales_order_lines` by order + line (R3) |
| `item_prices` | 36 | `item_price_id` (K2) | `items` (R1); a list price per finished good, valid from and to |
| `stg_supplier_prices` | 49 | `supplier_price_id` (K2; `stg_` is read as a kind word) | `suppliers`, `items` (R1) |
| `machine_events` | 220 | none (K3): an event log | `work_centers` (R1) |

The plan has 15 keys and 24 relationships. `tests/test_mill.py` holds every one of them with its rule, and fails when the
engine's answer changes.

## The planted problems

Placed at fixed rows, listed in `tests/fixtures/mill/planted_issues.json`. The tests check that the rows hold exactly
these and that /check finds exactly these.

- **Orphans** (references that point at nothing):
  - `sales_order_lines.item_id`: 2 rows (order 30005 line 2, order 30088 line 1) for items 9001 and 9002, which are not
    in `items`;
  - `inventory_transactions.item_id`: 1 row (70900) for item 9001;
  - `production_operations.work_center_code`: 1 row (60040) at work center `LASER`, which was never set up.
- **A key that is not unique** in a staging-like table: `stg_supplier_prices` loaded one row of a supplier's price file
  twice, a day apart (`supplier_price_id` 95012), so the table has 49 rows and 48 distinct ids.
- **Late deliveries**: 12 of the 474 delivered order lines arrived after the date promised to the customer (on-time
  delivery 97.5 %). The engine does not judge dates. This one is for the on-time KPI below and for the tests.
- **A table without a key**: `machine_events`, an event log. Two work centers log at the same hour, so no column is unique.

/check shows these, and also five warnings that `items.standard_cost` would be summed once per row of
`bill_of_materials`, `production_orders`, `purchase_order_lines` and `sales_order_lines`. The warnings are correct: an
item's cost is repeated on every line that points at the item. It is also why the BOM roll-up below multiplies by
quantity and never sums the cost over the lines. The run makes no suggestions.

**A limit, not a problem.** `customers.parent_customer_id` points at `customers` itself (a group and its sites). Every
value is a customer id. The engine's name rules never link a table to itself, so the plan leaves it out. The tests pin
this, so the day the engine learns self-references, the test fails and this paragraph changes.

## How to load it

- **In the browser**: [krusgraph.com/check](https://krusgraph.com/check), **Manufacturing sample**, or
  `/check?example=mill`.
- **In Fabric** (a lakehouse created with *Lakehouse schemas*), in a notebook attached to it:

  ```python
  %pip install git+https://github.com/Krusmaster/fabric-backend
  from fabric_backend.seed import seed
  seed(spark, mill=True)      # the shop in 'shop' as before, and the mill in 'mill'
  ```

  `mill` is off by default, so `seed(spark)` writes the shop alone, as before. On a lakehouse without schemas the mill
  is not written, and a note says why.
- **In Python**: `fabric_backend.mill.rows()` returns the rows, `mill.schema()` the tables without rows, and
  `mill.source()` an in-memory SQLite database that the engine can read.

## The KPIs it enables

Each query below runs on the sample in `tests/test_mill.py`, in SQLite, against the schema `mill`. The same SQL works
in Fabric's SQL analytics endpoint.

**On-time delivery**: the share of delivered order lines whose last delivery came on or before the promised date.

```sql
SELECT COUNT(*) AS delivered_lines,
       SUM(CASE WHEN d.last_delivery <= l.promised_date THEN 1 ELSE 0 END) AS on_time_lines
FROM mill.sales_order_lines AS l
JOIN (SELECT sales_order_id, line_no, MAX(delivery_date) AS last_delivery
      FROM mill.deliveries GROUP BY sales_order_id, line_no) AS d
  ON d.sales_order_id = l.sales_order_id AND d.line_no = l.line_no
```

**Order backlog**: the quantity and value ordered and not yet delivered.

```sql
SELECT COUNT(*) AS open_lines, SUM(l.quantity - COALESCE(d.delivered, 0)) AS open_quantity,
       SUM((l.quantity - COALESCE(d.delivered, 0)) * l.unit_price) AS open_value
FROM mill.sales_order_lines AS l
LEFT JOIN (SELECT sales_order_id, line_no, SUM(delivered_quantity) AS delivered
           FROM mill.deliveries GROUP BY sales_order_id, line_no) AS d
  ON d.sales_order_id = l.sales_order_id AND d.line_no = l.line_no
WHERE l.quantity - COALESCE(d.delivered, 0) > 0
```

**Inventory value**: the stock on hand at standard cost, per kind of item. The quantity is summed over the
transactions and multiplied by the cost once per item.

```sql
SELECT i.item_type, SUM(s.on_hand * i.standard_cost) AS inventory_value
FROM (SELECT item_id, SUM(quantity) AS on_hand FROM mill.inventory_transactions GROUP BY item_id) AS s
JOIN mill.items AS i ON i.item_id = s.item_id
GROUP BY i.item_type
```

**Work center load**: the hours booked per work center and month, against what the center can give (`hours_per_day`).

```sql
SELECT o.work_center_code, SUBSTRING(CAST(o.finished_on AS VARCHAR(10)), 1, 7) AS month,
       SUM(o.setup_hours + o.run_hours) AS booked_hours, MAX(w.hours_per_day) * 21 AS available_hours
FROM mill.production_operations AS o
JOIN mill.work_centers AS w ON w.work_center_code = o.work_center_code
WHERE o.finished_on IS NOT NULL
GROUP BY o.work_center_code, SUBSTRING(CAST(o.finished_on AS VARCHAR(10)), 1, 7)
```

**BOM cost roll-up**: the material cost of each finished good, through parts to raw materials, quantity times cost at
every level.

```sql
WITH bom_paths (top_item_id, component_item_id, quantity) AS (
    SELECT parent_item_id, component_item_id, quantity FROM mill.bill_of_materials
    UNION ALL
    SELECT p.top_item_id, b.component_item_id, p.quantity * b.quantity
    FROM bom_paths AS p JOIN mill.bill_of_materials AS b ON b.parent_item_id = p.component_item_id
)
SELECT p.top_item_id, SUM(p.quantity * i.standard_cost) AS material_cost
FROM bom_paths AS p
JOIN mill.items AS i ON i.item_id = p.component_item_id
JOIN mill.items AS top ON top.item_id = p.top_item_id
WHERE i.item_type = 'raw material' AND top.item_type = 'finished good'
GROUP BY p.top_item_id
```

The orphans change the answers slightly, as they would in a real company. An inner join drops the order lines for
the missing items and the operation at `LASER`. Finding them first is what the check is for.
