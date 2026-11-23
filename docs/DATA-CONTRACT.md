# Data contract

Round BL38, 23 November 2026 (backlog P-29). `fabric_backend/data_contract.py` writes a data contract in the
[Open Data Contract Standard](https://github.com/bitol-io/open-data-contract-standard) (ODCS) v3.1.0 for the tables of a
plan, from what `validate_plan` counted. A governance lead can sign off on it, and it can travel with the data product.

## What it holds

- **Per table:** the columns with their logical and physical types, and the primary key (`primaryKey`,
  `primaryKeyPosition`), as the plan has it.
- **Relationships:** each link of the plan as a `foreignKey` from the source column(s) to the target column(s).
- **Quality rules:** one `sql` rule per counted key (no empty or repeated key) and per counted link (no row without its
  target), each with `mustBe: 0`, the read-only Spark SQL that counts it, and the counted value, the date and
  `passed` or `failed` in `customProperties`. A fault is a failing rule with its number, never a passing one.
- **Declared, not counted:** a key or link that was proposed but not counted (not reached, errored, or a conditional
  link) is a `text` rule that says so. It is not a rule that passes.
- **Header amounts:** an amount a join would repeat on every line is a `text` rule that says to sum it per header row.
- **No row values:** names, types, counts, SQL and dates only.
- **Deterministic:** the same plan and counts give the same YAML byte for byte; the date is passed in, no clock is read.

The contracts validate against the ODCS v3.1.0 JSON schema (`tests/fixtures/odcs/`, Apache 2.0),
`tests/test_bl38_data_contract.py`.

## Example (synthetic data)

On the planted-faults shop (`fabric_backend/shop_faults.py`; two of its eight tables shown). The repeated
`customer_id` (fault F1) and the three order lines without an order (F2) are failing rules with their counts.

```python
from fabric_backend import data_contract, shop_faults
from fabric_backend.shop_faults import make_plan
check = shop_faults.check()
contract = data_contract.draft(make_plan(shop_faults.schema()), check["validate"], counted_on="2026-11-23")
print(data_contract.to_yaml(contract))
```

```yaml
apiVersion: "v3.1.0"
kind: "DataContract"
id: "krusgraph_shop_faults"
name: "shop_faults data product"
version: "0.1.0"
status: "draft"
description:
  purpose: "The tables of shop_faults as Krusgraph planned and checked them: keys, links and the rules counted on the rows."
  limitations: "Every rule's counted value is from 2026-11-23. A key or link marked 'declared, not counted' was proposed but not counted and is not a rule. No row values are in this contract."
  usage: "Review with the data product's owner; the SQL rules run on the lakehouse's Spark SQL as written."
schema:
  - name: "customers"
    physicalName: "shop_faults.customers"
    physicalType: "table"
    logicalType: "object"
    properties:
      - name: "customer_id"
        logicalType: "integer"
        physicalType: "int"
        primaryKey: true
        primaryKeyPosition: 1
        required: true
      - name: "name"
        logicalType: "string"
        physicalType: "string"
      - name: "country"
        logicalType: "string"
        physicalType: "string"
    quality:
      - id: "key_customers"
        name: "customers key customer_id is unique and not empty"
        type: "sql"
        dimension: "uniqueness"
        unit: "rows"
        description: "Rows with an empty or repeated customer_id. Counted 1 on 2026-11-23: not unique: 1 duplicate rows (10 distinct values in 11 rows)."
        query: "SELECT n - distinct_keys AS n FROM (SELECT COUNT(*) AS n, SUM(CASE WHEN `customer_id` IS NULL THEN 1 ELSE 0 END) AS nulls, (SELECT COUNT(*) FROM (SELECT DISTINCT `customer_id` FROM `shop_faults`.`customers` WHERE `customer_id` IS NOT NULL) AS d) AS distinct_keys FROM `shop_faults`.`customers`) AS k"
        mustBe: 0
        customProperties:
          - property: "countedValue"
            value: 1
          - property: "countedOn"
            value: "2026-11-23"
          - property: "status"
            value: "failed"
          - property: "rule"
            value: "K2"
  - name: "order_items"
    physicalName: "shop_faults.order_items"
    physicalType: "table"
    logicalType: "object"
    properties:
      - name: "order_id"
        logicalType: "integer"
        physicalType: "int"
        primaryKey: true
        primaryKeyPosition: 1
        required: true
      - name: "line_no"
        logicalType: "integer"
        physicalType: "int"
        primaryKey: true
        primaryKeyPosition: 2
        required: true
      - name: "product_id"
        logicalType: "integer"
        physicalType: "int"
      - name: "quantity"
        logicalType: "number"
        physicalType: "double"
    relationships:
      - type: "foreignKey"
        from: "order_items.order_id"
        to: "orders.order_id"
      - type: "foreignKey"
        from: "order_items.product_id"
        to: "products.product_id"
    quality:
      - id: "key_order_items"
        name: "order_items key order_id+line_no is unique and not empty"
        type: "sql"
        dimension: "uniqueness"
        unit: "rows"
        description: "Rows with an empty or repeated order_id+line_no. Counted 0 on 2026-11-23: unique in all 137 rows."
        query: "SELECT n - distinct_keys AS n FROM (SELECT COUNT(*) AS n, SUM(CASE WHEN `order_id` IS NULL OR `line_no` IS NULL THEN 1 ELSE 0 END) AS nulls, (SELECT COUNT(*) FROM (SELECT DISTINCT `order_id`, `line_no` FROM `shop_faults`.`order_items` WHERE `order_id` IS NOT NULL AND `line_no` IS NOT NULL) AS d) AS distinct_keys FROM `shop_faults`.`order_items`) AS k"
        mustBe: 0
        customProperties:
          - property: "countedValue"
            value: 0
          - property: "countedOn"
            value: "2026-11-23"
          - property: "status"
            value: "passed"
          - property: "rule"
            value: "K5"
      - id: "link_order_items_order_id_orders"
        name: "every order_items.order_id -> orders row finds its orders row"
        type: "sql"
        dimension: "consistency"
        unit: "rows"
        description: "order_items rows with a value in order_id and no orders row. Counted 3 on 2026-11-23: 3 of 137 rows (2.2%) point at nothing."
        query: "SELECT COALESCE(orphans, 0) AS n FROM (SELECT COUNT(*) AS with_value, SUM(CASE WHEN t.`order_id` IS NULL THEN 1 ELSE 0 END) AS orphans FROM `shop_faults`.`order_items` AS s LEFT JOIN `shop_faults`.`orders` AS t ON s.`order_id` = t.`order_id` WHERE s.`order_id` IS NOT NULL) AS r"
        mustBe: 0
        customProperties:
          - property: "countedValue"
            value: 3
          - property: "countedOn"
            value: "2026-11-23"
          - property: "status"
            value: "failed"
          - property: "rule"
            value: "R1"
      - id: "link_order_items_product_id_products"
        name: "every order_items.product_id -> products row finds its products row"
        type: "sql"
        dimension: "consistency"
        unit: "rows"
        description: "order_items rows with a value in product_id and no products row. Counted 0 on 2026-11-23: holds for all 137 rows with a value."
        query: "SELECT COALESCE(orphans, 0) AS n FROM (SELECT COUNT(*) AS with_value, SUM(CASE WHEN t.`product_id` IS NULL THEN 1 ELSE 0 END) AS orphans FROM `shop_faults`.`order_items` AS s LEFT JOIN `shop_faults`.`products` AS t ON s.`product_id` = t.`product_id` WHERE s.`product_id` IS NOT NULL) AS r"
        mustBe: 0
        customProperties:
          - property: "countedValue"
            value: 0
          - property: "countedOn"
            value: "2026-11-23"
          - property: "status"
            value: "passed"
          - property: "rule"
            value: "R1"
customProperties:
  - property: "generatedBy"
    value: "Krusgraph (fabric_backend.data_contract)"
  - property: "countedOn"
    value: "2026-11-23"
  - property: "specification"
    value: "https://github.com/bitol-io/open-data-contract-standard (schema/odcs-json-schema-v3.1.0-20251208.json)"
```

## Next steps

- **Attach the contract to the data product's catalog entry** (`fabric_backend/catalog.py`, after the open catalog
  round merges), so the contract and the product are found together.
- Offer it from the hosted tools and the workload item beside the dry run; today it is a library function.
- Re-count on a schedule and write a new contract version when a counted value changes (the daily rules,
  `health.daily_rules`, already count the same keys and links).
