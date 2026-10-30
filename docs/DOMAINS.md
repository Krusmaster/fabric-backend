# Domains, data products and data contracts

`domain_draft` proposes how a schema could be cut into domains (domain-driven design), treats each domain as a
candidate data product, and writes one data contract per domain in the Open Data Contract Standard (ODCS) v3.2.0. It
is a draft: it reads metadata (and, with `check_rows=true`, runs validate_plan's counting queries) and changes
nothing. Status: unit tests on the shop schema, the synthetic SAP demo and the Salesforce + ERP example; it has not
been run against a Fabric workspace.

## What is proposed

- **Domains**: groups of tables with a key, each with a proposed name, the reason for the name and, per table, why it
  is in that domain (the strongest relationship inside it, or that it is part of a parent's aggregate).
- **Interfaces**: the relationships that cross from one domain to another. They are the boundaries between data
  products: the consuming domain holds the reference column, the providing domain owns the key.
- **Unassigned**: tables the engine will not guess about. A table without a key cannot carry a uniqueness promise in a
  contract, so it is listed with the domain it points at, to place by hand; a table linked to nothing, or a group
  smaller than two tables, is unassigned rather than a domain of one.
- **Contracts**: per domain an ODCS v3.2.0 YAML file built from the plan.

## How

1. **The graph** is the plan's tables and relationships. Each relationship is weighted by how sure the engine is of
   it: declared (R0), confirmed or from the SAP pack 1.0; R1 0.9; R2 and R3 0.8; R4 0.5; an extended join (a unique
   non-key column, a validity period) 0.6 or 0.4. With `check_rows=true`, a relationship that holds in the rows
   counts 1.0 and one with orphans half its weight.
2. **Aggregates first**: a table whose key holds its reference to a parent (`order_items` → `orders`, VBAP → VBAK,
   MAKT → MARA) is kept with that parent, so a header and its lines never land in two domains. This follows Service
   Cutter's identity-and-lifecycle coupling criterion (https://github.com/ServiceCutter/ServiceCutter/wiki).
3. **Communities** are found with a compact Leiden-style method (Traag, Waltman and van Eck 2019,
   https://arxiv.org/abs/1810.08473): local moving on modularity, a refinement that keeps every community connected
   (what Leiden adds over Louvain), aggregation, repeated until nothing moves. Nodes are visited in name order and ties
   go to the lower name, so the same schema always gives the same proposal. It is plain Python in
   `fabric_backend/domains.py`, with no dependency, so it also runs in the browser engine that /check loads.
4. **Names**: SAP tables the pack recognises are named by their part of order-to-cash (public SAP table roles: sales
   documents, deliveries, billing, customer master, material master, organisation; "order-to-cash" when a domain holds
   sales documents, deliveries and billing); otherwise the tables' common name prefix; otherwise the table the others
   point at most. Names are proposals to rename.

What the three examples give (unit tests, `tests/test_domains.py`):

| Schema | Domains | Interfaces | Unassigned |
| --- | --- | --- | --- |
| shop | customers (customers, addresses, orders, order_items), products (products, categories) | order_items.product_id → products | audit_log (no key) |
| SAP demo | order-to-cash (VBAK, VBAP, VBEP, VBFA, LIKP, LIPS, VBRK, VBRP, MARA, MAKT, T001, TVKO), customer master (KNA1, KNVK, VBPA, ADRC, ADR6) | VBAK, VBRK, LIKP → KNA1; T001 → ADRC | none |
| Salesforce + ERP | Account (Account, Contact, Opportunity), sales_orders (customers, sales_orders, sales_order_lines) | none: the Account → customers link is only a suggestion until it is confirmed | none |

## The contract

Per table: its columns with logical and physical type, the key as `primaryKey`/`primaryKeyPosition` and
`required`. Then the checks as quality rules:

- unique key: `metric: duplicateValues`, `mustBe: 0`, `dimension: uniqueness`, the key's columns in
  `arguments.properties` (one or several);
- relationship: `relationships: [{type: foreignKey, from, to}]`;
- orphans: a `type: sql` rule counting rows whose reference finds no target, `mustBe: 0`, `dimension: consistency`;
- with `check_rows=true`, each rule carries validate_plan's verdict under `customProperties` (`lastCheck`).

Freshness is left as a commented `slaProperties` block naming a date column: the latency is for the data owner to
agree, so no value is assumed. dbt contracts were considered; on Fabric they enforce little beyond not_null, so ODCS is
the format, and `dbt_schema` stays for teams that test with dbt.

Example, the products domain of the shop schema (`domain_draft` on schema `shop` in `shop_lh`):

```yaml
# ODCS v3.2.0 draft from Krusgraph's plan: review before use. Nothing was created in Fabric.
apiVersion: v3.2.0
kind: DataContract
id: krusgraph-shop_lh-shop-products
name: products
version: "0.1.0"
status: draft
domain: products
dataProduct: products
description:
  purpose: "Proposed data product for the products domain of shop in shop_lh: products is the table the others in the domain point at most."
  usage: "Draft written by Krusgraph from the plan's keys and relationships; review before agreeing it. Provides keys to: customers."
schema:
  - name: categories
    physicalName: shop.categories
    physicalType: table
    logicalType: object
    description: "1 relationship(s) inside the domain; strongest: products.category_id → categories (R1, weight 0.9); key by rule K2"
    properties:
      - name: id
        physicalName: id
        logicalType: integer
        physicalType: int
        primaryKey: true
        primaryKeyPosition: 1
        required: true
      - name: name
        physicalName: name
        logicalType: string
        physicalType: string
    quality:
      - name: categories_key_unique
        description: "Key id (K2) has no duplicates"
        dimension: uniqueness
        type: library
        metric: duplicateValues
        mustBe: 0
        arguments:
          properties:
            - id
  - name: products
    physicalName: shop.products
    physicalType: table
    logicalType: object
    description: "1 relationship(s) inside the domain; strongest: products.category_id → categories (R1, weight 0.9); key by rule K2"
    properties:
      - name: product_id
        physicalName: product_id
        logicalType: integer
        physicalType: int
        primaryKey: true
        primaryKeyPosition: 1
        required: true
      - name: name
        physicalName: name
        logicalType: string
        physicalType: string
      - name: category_id
        physicalName: category_id
        logicalType: integer
        physicalType: int
    quality:
      - name: products_key_unique
        description: "Key product_id (K2) has no duplicates"
        dimension: uniqueness
        type: library
        metric: duplicateValues
        mustBe: 0
        arguments:
          properties:
            - product_id
      - name: products_category_id_no_orphans
        description: "Every products.category_id with a value finds a row in categories (R1)"
        dimension: consistency
        type: sql
        query: "SELECT COUNT(*) FROM [shop].[products] s WHERE (s.[category_id] IS NOT NULL) AND NOT EXISTS (SELECT 1 FROM [shop].[categories] t WHERE t.[id] = s.[category_id])"
        mustBe: 0
    relationships:
      - type: foreignKey
        from: products.category_id
        to: categories.id
```

## Who creates the Fabric domains

Krusgraph proposes; it creates no Fabric domain. Fabric's domains API (`POST /v1/admin/domains`, generally available)
needs a Fabric administrator and the Tenant.ReadWrite.All permission, which this connector does not ask for. The
customer's Fabric admin creates the domains and assigns workspaces from the proposal.

## In the browser

`fabric_backend.domains.propose_from_check(result)` takes the result of /check's `browser_check.analyze` and returns the
same proposal, in the same engine zip /check already loads. The site does not call it yet.
