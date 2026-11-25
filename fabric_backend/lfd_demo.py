"""Two synthetic samples for the change-by-chat demo (round LFD1, 24 November 2026): `shop_lfd` and `sap_lfd`.

The demo changes a plan in conversation and shows the diff. These samples hold the rows such a change acts on: test
customers that a filter leaves out, a region to group by, a second sales organisation, a cancelled billing document and
its cancellation. Every value is made up, as in fabric_backend/seed.py and fabric_backend/sap_demo.py, and neither of
those, nor any golden file, changes: the samples are built from their rows and add to them.

shop_lfd: the shop of seed.rows(42) (the `sample` source) plus
- customers.is_test, a boolean flag (0/1 in SQLite), 0 on the ten shop customers;
- addresses.region, "North" (SE, NO, FI) or "South" (DE): two distinct values among the addresses orders ship to;
- two test customers (11, 12), one address each, three orders each (160-165), two lines per order: one trail bike
  (899.00) and two bottles (2 × 12.00), 923.00 per order.
Without the test customers (is_test = 0) every number is the shop's.

sap_lfd: the 17 tables of sap_demo.tables() plus
- sales organisation 2000 in TVKO (client 100) with one order, 0000000003, one item, 200.00;
- VBRK gets the columns VBTYP, FKSTO and SFAKN (empty on the existing invoice 0090000001, which gets VBTYP M);
- billing document 0090000002 (FKSTO X, cancelled, 100.00) for order 0000000002, and its cancellation 0090000003
  (FKART S1, VBTYP N, 100.00, SFAKN 0090000002), one item each and their document flow in VBFA.
Not verified against an SAP system: that FKSTO, SFAKN and VBTYP mean exactly this. The SAP pack's own note on VBRK
says only that cancellations are billing documents too and that FKART and the cancellation flag decide whether to count
them (docs/SAMPLE-LFD.md).

    shop_rows() / sap_tables()           -> the rows
    sqlite("shop_lfd" | "sap_lfd")       -> (Schema, execute) in an in-memory SQLite database, like sap_demo.sqlite()
    EXPECTED                             -> what the plan, the check and the numbers give; tests/test_lfd1_samples.py
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
from datetime import date, timedelta

from . import sap_demo, seed

SAMPLES = ("shop_lfd", "sap_lfd")

# ---------------------------------------------------------------- shop_lfd
REGIONS = {"DE": "South", "SE": "North", "NO": "North", "FI": "North"}
TEST_CUSTOMERS = [(11, "Test Customer Alpha", "SE"), (12, "Test Customer Beta", "DE")]
TEST_ORDER_LINES = [(1, 1.0), (7, 2.0)]           # product, quantity: 899.00 + 2 × 12.00 = 923.00 per order
SHOP_SCHEMAS = {
    **seed.SCHEMAS,
    "customers": "customer_id INT, name STRING, country STRING, is_test BOOLEAN",
    "addresses": "address_id INT, customer_id INT, city STRING, region STRING",
}


def shop_rows(include_test: bool = True) -> dict[str, list[tuple]]:
    """seed.rows(42) with is_test and region added, and the two test customers with their address and orders.
    include_test=False leaves the test customers out: the shop's rows, with the two new columns."""
    base = seed.rows(42)
    country = {c[0]: c[2] for c in seed.CUSTOMERS + TEST_CUSTOMERS}
    customers = [(c[0], c[1], c[2], False) for c in base["customers"]] + \
        ([(c[0], c[1], c[2], True) for c in TEST_CUSTOMERS] if include_test else [])
    addresses = [(a[0], a[1], a[2], REGIONS[country[a[1]]]) for a in base["addresses"]]
    orders, items = list(base["orders"]), list(base["order_items"])
    aid, oid = max(a[0] for a in addresses) + 1, max(o[0] for o in orders) + 1
    for cid, _, land in TEST_CUSTOMERS if include_test else []:
        addresses.append((aid, cid, seed.CITIES[land][0], REGIONS[land]))
        for n in range(3):
            orders.append((oid, cid, date(2026, 10, 5) + timedelta(days=7 * n), aid))
            items += [(oid, line, pid, qty) for line, (pid, qty) in enumerate(TEST_ORDER_LINES, 1)]
            oid += 1
        aid += 1
    return {**base, "customers": customers, "addresses": addresses, "orders": orders, "order_items": items}


def _shop_schema(name: str):
    from .schema import Column, Schema, Table
    s = Schema(schema=name)
    for table, cols in SHOP_SCHEMAS.items():
        s.tables[table] = Table(table, [Column(c.split()[0], c.split()[1].lower()) for c in cols.split(", ")], schema=name)
    return s


# ---------------------------------------------------------------- sap_lfd
def sap_tables() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    """sap_demo.tables() (17 tables) with the second sales organisation and the cancelled billing document added."""
    out = {name: (list(c), list(k), list(r)) for name, (c, k, r) in sap_demo.tables().items()}
    m2 = "000000000000000002"

    def add(name: str, *rows: tuple) -> None:
        out[name][2].extend(rows)
    add("TVKO", ("100", "2000", "1000", "EUR"))
    add("VBAK", ("100", "0000000003", "TA", "C", "0000000012", "2000", 200.00, "EUR", "20261005", "20261005", "0000000503"))
    add("VBAP", ("100", "0000000003", "000010", m2, 200.00, "EUR", 2, "ST", "20261005"))
    cols, kinds, rows = out["VBRK"]
    out["VBRK"] = (cols + ["VBTYP", "FKSTO", "SFAKN"], kinds + ["string"] * 3, [r + ("M", "", "") for r in rows] + [
        ("100", "0090000002", "F2", "0000000011", "0000000011", "1000", "1000", 100.00, 20.00, "EUR", "20261012", "0000000602", "M", "X", ""),
        ("100", "0090000003", "S1", "0000000011", "0000000011", "1000", "1000", 100.00, 20.00, "EUR", "20261013", "0000000603", "N", "", "0090000002")])
    add("VBRP", ("100", "0090000002", "000010", "000000000000000001", "0000000002", "000010", "", "", 100.00, 1, "ST"),
        ("100", "0090000003", "000010", "000000000000000001", "0000000002", "000010", "", "", 100.00, 1, "ST"))
    add("VBFA", ("100", "0000000002", "000010", "0090000002", "000010", "M", "C", 1),
        ("100", "0090000002", "000010", "0090000003", "000010", "N", "M", 1))
    return out


# ---------------------------------------------------------------- both
def sqlite(sample: str = "shop_lfd", schema: str | None = None, include_test: bool = True):
    """(Schema, execute) over a sample's rows in an in-memory SQLite database. shop_lfd: the shop's seven tables in
    schema `shop` (as the `sample` source names them; include_test=False without the test customers); sap_lfd:
    sap_<name> tables in schema `sap` (as sap_demo.sqlite())."""
    from .platforms.local import _sqlite_execute
    from .schema import Schema
    if sample not in SAMPLES:
        raise ValueError(f"unknown sample {sample!r}; one of {', '.join(SAMPLES)}")
    con = sqlite3.connect(":memory:", check_same_thread=False)
    if sample == "shop_lfd":
        schema = schema or "shop"
        con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
        data = shop_rows(include_test)
        for name, ddl in SHOP_SCHEMAS.items():
            con.execute(f"CREATE TABLE {schema}.[{name}] ({ddl})")
            rows = [tuple(v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else v for v in r) for r in data[name]]
            con.executemany(f"INSERT INTO {schema}.[{name}] VALUES ({','.join('?' * len(rows[0]))})", rows)
        return _shop_schema(schema), _sqlite_execute(con)
    schema = schema or "sap"
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in sap_tables().items():
        t = sap_demo.PREFIX + name.lower()
        con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
        info += [(schema, t, c, "decimal" if k != "string" else "nvarchar", i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]
    return Schema.from_information_schema(info, schema=schema), _sqlite_execute(con)


# ---------------------------------------------------------------- the numbers
# Read-only statements over sqlite()'s tables ({s} is the schema). Amounts are summed in cents (whole numbers), so no
# float rounding enters; numbers() turns them back into two decimals. The shop's order value is quantity × list_price
# summed over the order lines, as amounts.order_amount_measures builds it (order_items has no amount of its own).
_LINE_VALUE = "CAST(ROUND(i.[quantity] * p.[list_price] * 100, 0) AS INTEGER)"
_REAL = "JOIN {s}.[customers] AS c ON c.[customer_id] = o.[customer_id] AND c.[is_test] = 0"
SHOP_SQL = {
    "customers": "SELECT COUNT(*) AS n FROM {s}.[customers]",
    "addresses": "SELECT COUNT(*) AS n FROM {s}.[addresses]",
    "orders": "SELECT COUNT(*) AS n FROM {s}.[orders]",
    "order_lines": "SELECT COUNT(*) AS n FROM {s}.[order_items]",
    "order_value_cents": ("SELECT SUM(" + _LINE_VALUE + ") AS n FROM {s}.[order_items] AS i "
                          "JOIN {s}.[products] AS p ON p.[product_id] = i.[product_id]"),
    "real_customers": "SELECT COUNT(*) AS n FROM {s}.[customers] WHERE [is_test] = 0",
    "real_addresses": ("SELECT COUNT(*) AS n FROM {s}.[addresses] AS a JOIN {s}.[customers] AS c "
                       "ON c.[customer_id] = a.[customer_id] AND c.[is_test] = 0"),
    "real_orders": "SELECT COUNT(*) AS n FROM {s}.[orders] AS o " + _REAL,
    "real_order_lines": ("SELECT COUNT(*) AS n FROM {s}.[order_items] AS i JOIN {s}.[orders] AS o "
                         "ON o.[order_id] = i.[order_id] " + _REAL),
    "real_order_value_cents": ("SELECT SUM(" + _LINE_VALUE + ") AS n FROM {s}.[order_items] AS i "
                               "JOIN {s}.[products] AS p ON p.[product_id] = i.[product_id] "
                               "JOIN {s}.[orders] AS o ON o.[order_id] = i.[order_id] " + _REAL),
    # the path the plan does not take: orders to addresses through the customer instead of ship_to_id, so every
    # order is repeated once per address of its customer
    "real_via_customer_rows": ("SELECT COUNT(*) AS n FROM {s}.[orders] AS o " + _REAL +
                               " JOIN {s}.[addresses] AS a ON a.[customer_id] = c.[customer_id]"),
    "real_via_customer_value_cents": ("SELECT SUM(" + _LINE_VALUE + ") AS n FROM {s}.[order_items] AS i "
                                      "JOIN {s}.[products] AS p ON p.[product_id] = i.[product_id] "
                                      "JOIN {s}.[orders] AS o ON o.[order_id] = i.[order_id] " + _REAL +
                                      " JOIN {s}.[addresses] AS a ON a.[customer_id] = c.[customer_id]"),
    "real_ship_to_found": ("SELECT COUNT(*) AS n FROM {s}.[orders] AS o " + _REAL +
                           " WHERE EXISTS (SELECT 1 FROM {s}.[addresses] AS a WHERE a.[address_id] = o.[ship_to_id])"),
    "ship_to_regions": ("SELECT COUNT(DISTINCT a.[region]) AS n FROM {s}.[orders] AS o "
                        "JOIN {s}.[addresses] AS a ON a.[address_id] = o.[ship_to_id]"),
    "test_orders": ("SELECT COUNT(*) AS n FROM {s}.[orders] AS o JOIN {s}.[customers] AS c "
                    "ON c.[customer_id] = o.[customer_id] AND c.[is_test] = 1"),
}
_NOT_CANCELLED = "COALESCE(k.[FKSTO], '') <> 'X' AND COALESCE(k.[SFAKN], '') = ''"
SAP_SQL = {
    "orders": "SELECT COUNT(*) AS n FROM {s}.[sap_vbak]",
    "sales_organisations": "SELECT COUNT(*) AS n FROM {s}.[sap_tvko] WHERE [MANDT] = '100'",
    "orders_in_2000": "SELECT COUNT(*) AS n FROM {s}.[sap_vbak] WHERE [VKORG] = '2000'",
    "order_value_per_header_cents": "SELECT SUM(CAST(ROUND([NETWR] * 100, 0) AS INTEGER)) AS n FROM {s}.[sap_vbak]",
    "order_value_over_lines_cents": ("SELECT SUM(CAST(ROUND(h.[NETWR] * 100, 0) AS INTEGER)) AS n FROM {s}.[sap_vbap] AS l "
                                     "JOIN {s}.[sap_vbak] AS h ON h.[MANDT] = l.[MANDT] AND h.[VBELN] = l.[VBELN]"),
    "billing_documents": "SELECT COUNT(*) AS n FROM {s}.[sap_vbrk]",
    "billed_cents": "SELECT SUM(CAST(ROUND([NETWR] * 100, 0) AS INTEGER)) AS n FROM {s}.[sap_vbrk]",
    "billed_over_lines_cents": ("SELECT SUM(CAST(ROUND(k.[NETWR] * 100, 0) AS INTEGER)) AS n FROM {s}.[sap_vbrp] AS l "
                                "JOIN {s}.[sap_vbrk] AS k ON k.[MANDT] = l.[MANDT] AND k.[VBELN] = l.[VBELN]"),
    "billing_documents_counted": "SELECT COUNT(*) AS n FROM {s}.[sap_vbrk] AS k WHERE " + _NOT_CANCELLED,
    "billed_without_cancellations_cents": ("SELECT SUM(CAST(ROUND(k.[NETWR] * 100, 0) AS INTEGER)) AS n "
                                           "FROM {s}.[sap_vbrk] AS k WHERE " + _NOT_CANCELLED),
    "cancelled": "SELECT COUNT(*) AS n FROM {s}.[sap_vbrk] WHERE [FKSTO] = 'X'",
    "cancellations": "SELECT COUNT(*) AS n FROM {s}.[sap_vbrk] WHERE COALESCE([SFAKN], '') <> ''",
}


def _money(cents: int) -> str:
    from decimal import Decimal
    return str((Decimal(int(cents)) / 100).quantize(Decimal("0.01")))


def _per(cents: int, n: int) -> str:
    from decimal import ROUND_HALF_UP, Decimal
    return str((Decimal(int(cents)) / 100 / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def numbers(sample: str, execute, schema: str | None = None) -> dict:
    """The sample's numbers (EXPECTED[sample]["numbers"]) counted over `execute`: counts as whole numbers, amounts as
    text with two decimals ("51296.70"); a value per customer is rounded half up."""
    sql = SHOP_SQL if sample == "shop_lfd" else SAP_SQL
    s = f"[{schema or ('shop' if sample == 'shop_lfd' else 'sap')}]"
    raw = {k: int(list(execute(q.format(s=s)))[0]["n"] or 0) for k, q in sql.items()}
    out = {k.removesuffix("_cents"): (_money(v) if k.endswith("_cents") else v) for k, v in raw.items()}
    if sample == "shop_lfd":
        out["order_value_per_customer"] = _per(raw["order_value_cents"], raw["customers"])
        out["real_order_value_per_customer"] = _per(raw["real_order_value_cents"], raw["real_customers"])
    return out


# ---------------------------------------------------------------- what the plan, the check and the numbers give
# Locked on 24 November 2026 (round LFD1) from the engine: the plan as plan_backend makes it (server._hosted_plan: the
# names rules, R5 and the SAP pack), the check as validate_plan runs it (evidence.validate, max_items 60), and
# numbers() above. tests/test_lfd1_samples.py compares them byte for byte; docs/SAMPLE-LFD.md explains each number.
# "real_*" are the shop without its test customers (is_test = 0): every one of them is the shop's own number.
EXPECTED = {'shop_lfd': {'plan_summary': '7 tables, 6 with keys, 7 relationships\n'
                              'R5 counted 1 code or role column(s) in the rows: 1 counting query(ies), at most 200 '
                              'distinct values of a column each\n'
                              'counted in this call: 6 key(s), 6 unique\n'
                              'no key (query only; can reference others, cannot be referenced): audit_log',
              'keys': {'customers': 'customer_id (K2)',
                       'categories': 'id (K2)',
                       'products': 'product_id (K2)',
                       'addresses': 'address_id (K2)',
                       'orders': 'order_id (K2)',
                       'order_items': 'order_id+line_no (K5)'},
              'relationships': ['products.category_id -> categories.id (R1)',
                                'addresses.customer_id -> customers.customer_id (R1)',
                                'orders.customer_id -> customers.customer_id (R1)',
                                'order_items.order_id -> orders.order_id (R1)',
                                'order_items.product_id -> products.product_id (R1)',
                                'audit_log.customer_id -> customers.customer_id (R1)',
                                'orders.ship_to_id -> addresses.address_id (R5)'],
              'check_summary': '6 of 6 keys unique, 7 of 7 relationships hold without orphans',
              'key_rows': {'customers': [12, 12],
                           'categories': [3, 3],
                           'products': [8, 8],
                           'addresses': [19, 19],
                           'orders': [66, 66],
                           'order_items': [146, 146]},
              'checked': ['products.category_id -> categories.id: 8 with a value, 0 orphan(s)',
                          'addresses.customer_id -> customers.customer_id: 19 with a value, 0 orphan(s)',
                          'orders.customer_id -> customers.customer_id: 66 with a value, 0 orphan(s)',
                          'order_items.order_id -> orders.order_id: 146 with a value, 0 orphan(s)',
                          'order_items.product_id -> products.product_id: 146 with a value, 0 orphan(s)',
                          'audit_log.customer_id -> customers.customer_id: 40 with a value, 0 orphan(s)',
                          'orders.ship_to_id -> addresses.address_id: 66 with a value, 0 orphan(s)'],
              'header_amounts': ['products.list_price over order_items: up to 27 per header'],
              'numbers': {'customers': 12,
                          'addresses': 19,
                          'orders': 66,
                          'order_lines': 146,
                          'order_value': '56834.70',
                          'real_customers': 10,
                          'real_addresses': 17,
                          'real_orders': 60,
                          'real_order_lines': 134,
                          'real_order_value': '51296.70',
                          'real_via_customer_rows': 103,
                          'real_via_customer_value': '93842.80',
                          'real_ship_to_found': 60,
                          'ship_to_regions': 2,
                          'test_orders': 6,
                          'order_value_per_customer': '4736.23',
                          'real_order_value_per_customer': '5129.67'}},
 'sap_lfd': {'plan_summary': '17 tables, 17 with keys, 24 relationships\n'
                             'counted in this call: 17 key(s), 17 unique\n'
                             '17 table(s) recognised by the sap pack: keys and relationships from its public sources '
                             '(rule "SAP pack"), to be checked with validate_plan — see plan.pack',
             'keys': {'sap_t001': 'MANDT+BUKRS (SAP pack)',
                      'sap_tvko': 'MANDT+VKORG (SAP pack)',
                      'sap_kna1': 'MANDT+KUNNR (SAP pack)',
                      'sap_mara': 'MANDT+MATNR (SAP pack)',
                      'sap_makt': 'MANDT+MATNR+SPRAS (SAP pack)',
                      'sap_vbak': 'MANDT+VBELN (SAP pack)',
                      'sap_vbap': 'MANDT+VBELN+POSNR (SAP pack)',
                      'sap_vbep': 'MANDT+VBELN+POSNR+ETENR (SAP pack)',
                      'sap_likp': 'MANDT+VBELN (SAP pack)',
                      'sap_lips': 'MANDT+VBELN+POSNR (SAP pack)',
                      'sap_vbrk': 'MANDT+VBELN (SAP pack)',
                      'sap_vbrp': 'MANDT+VBELN+POSNR (SAP pack)',
                      'sap_vbfa': 'MANDT+VBELV+POSNV+VBELN+POSNN+VBTYP_N (SAP pack)',
                      'sap_vbpa': 'MANDT+VBELN+POSNR+PARVW (SAP pack)',
                      'sap_knvk': 'MANDT+PARNR (SAP pack)',
                      'sap_adrc': 'CLIENT+ADDRNUMBER+DATE_FROM+NATION (SAP pack)',
                      'sap_adr6': 'CLIENT+ADDRNUMBER+PERSNUMBER+DATE_FROM+CONSNUMBER (SAP pack)'},
             'relationships': ['sap_vbap.MANDT+VBELN -> sap_vbak.MANDT+VBELN (SAP pack)',
                               'sap_vbep.MANDT+VBELN+POSNR -> sap_vbap.MANDT+VBELN+POSNR (SAP pack)',
                               'sap_vbak.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR (SAP pack)',
                               'sap_vbak.MANDT+VKORG -> sap_tvko.MANDT+VKORG (SAP pack)',
                               'sap_vbap.MANDT+MATNR -> sap_mara.MANDT+MATNR (SAP pack)',
                               'sap_makt.MANDT+MATNR -> sap_mara.MANDT+MATNR (SAP pack)',
                               'sap_tvko.MANDT+BUKRS -> sap_t001.MANDT+BUKRS (SAP pack)',
                               'sap_lips.MANDT+VBELN -> sap_likp.MANDT+VBELN (SAP pack)',
                               'sap_lips.MANDT+VGBEL+VGPOS -> sap_vbap.MANDT+VBELN+POSNR (SAP pack)',
                               'sap_lips.MANDT+MATNR -> sap_mara.MANDT+MATNR (SAP pack)',
                               'sap_likp.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR (SAP pack)',
                               'sap_likp.MANDT+KUNAG -> sap_kna1.MANDT+KUNNR (SAP pack)',
                               'sap_vbrp.MANDT+VBELN -> sap_vbrk.MANDT+VBELN (SAP pack)',
                               'sap_vbrp.MANDT+AUBEL+AUPOS -> sap_vbap.MANDT+VBELN+POSNR (SAP pack)',
                               'sap_vbrp.MANDT+VGBEL+VGPOS -> sap_lips.MANDT+VBELN+POSNR (SAP pack)',
                               'sap_vbrp.MANDT+MATNR -> sap_mara.MANDT+MATNR (SAP pack)',
                               'sap_vbrk.MANDT+KUNAG -> sap_kna1.MANDT+KUNNR (SAP pack)',
                               'sap_vbrk.MANDT+KUNRG -> sap_kna1.MANDT+KUNNR (SAP pack)',
                               'sap_vbrk.MANDT+VKORG -> sap_tvko.MANDT+VKORG (SAP pack)',
                               'sap_vbpa.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR (SAP pack)',
                               'sap_vbrk.MANDT+BUKRS -> sap_t001.MANDT+BUKRS (SAP pack)',
                               'sap_likp.MANDT+VKORG -> sap_tvko.MANDT+VKORG (SAP pack)',
                               'sap_knvk.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR (SAP pack)',
                               'sap_vbpa.MANDT+PARNR -> sap_knvk.MANDT+PARNR (SAP pack)'],
             'check_summary': '17 of 17 keys unique, 32 of 34 relationships hold without orphans',
             'key_rows': {'sap_t001': [2, 2],
                          'sap_tvko': [3, 3],
                          'sap_kna1': [4, 4],
                          'sap_mara': [4, 4],
                          'sap_makt': [6, 6],
                          'sap_vbak': [4, 4],
                          'sap_vbap': [7, 7],
                          'sap_vbep': [5, 5],
                          'sap_likp': [1, 1],
                          'sap_lips': [2, 2],
                          'sap_vbrk': [3, 3],
                          'sap_vbrp': [4, 4],
                          'sap_vbfa': [6, 6],
                          'sap_vbpa': [5, 5],
                          'sap_knvk': [1, 1],
                          'sap_adrc': [7, 7],
                          'sap_adr6': [2, 2]},
             'checked': ['sap_vbap.MANDT+VBELN -> sap_vbak.MANDT+VBELN: 7 with a value, 1 orphan(s)',
                         'sap_vbep.MANDT+VBELN+POSNR -> sap_vbap.MANDT+VBELN+POSNR: 5 with a value, 0 orphan(s)',
                         'sap_vbak.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR: 4 with a value, 0 orphan(s)',
                         'sap_vbak.MANDT+VKORG -> sap_tvko.MANDT+VKORG: 4 with a value, 0 orphan(s)',
                         'sap_vbap.MANDT+MATNR -> sap_mara.MANDT+MATNR: 7 with a value, 0 orphan(s)',
                         'sap_makt.MANDT+MATNR -> sap_mara.MANDT+MATNR: 6 with a value, 0 orphan(s)',
                         'sap_tvko.MANDT+BUKRS -> sap_t001.MANDT+BUKRS: 3 with a value, 0 orphan(s)',
                         'sap_lips.MANDT+VBELN -> sap_likp.MANDT+VBELN: 2 with a value, 0 orphan(s)',
                         'sap_lips.MANDT+VGBEL+VGPOS -> sap_vbap.MANDT+VBELN+POSNR: 2 with a value, 0 orphan(s)',
                         'sap_lips.MANDT+MATNR -> sap_mara.MANDT+MATNR: 2 with a value, 0 orphan(s)',
                         'sap_likp.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR: 1 with a value, 0 orphan(s)',
                         'sap_likp.MANDT+KUNAG -> sap_kna1.MANDT+KUNNR: 1 with a value, 0 orphan(s)',
                         'sap_vbrp.MANDT+VBELN -> sap_vbrk.MANDT+VBELN: 4 with a value, 0 orphan(s)',
                         'sap_vbrp.MANDT+AUBEL+AUPOS -> sap_vbap.MANDT+VBELN+POSNR: 4 with a value, 0 orphan(s)',
                         'sap_vbrp.MANDT+VGBEL+VGPOS -> sap_lips.MANDT+VBELN+POSNR: 2 with a value, 0 orphan(s)',
                         'sap_vbrp.MANDT+MATNR -> sap_mara.MANDT+MATNR: 4 with a value, 0 orphan(s)',
                         'sap_vbrk.MANDT+KUNAG -> sap_kna1.MANDT+KUNNR: 3 with a value, 0 orphan(s)',
                         'sap_vbrk.MANDT+KUNRG -> sap_kna1.MANDT+KUNNR: 3 with a value, 0 orphan(s)',
                         'sap_vbrk.MANDT+VKORG -> sap_tvko.MANDT+VKORG: 3 with a value, 0 orphan(s)',
                         'sap_vbpa.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR: 4 with a value, 0 orphan(s)',
                         'sap_vbrk.MANDT+BUKRS -> sap_t001.MANDT+BUKRS: 3 with a value, 0 orphan(s)',
                         'sap_likp.MANDT+VKORG -> sap_tvko.MANDT+VKORG: 1 with a value, 0 orphan(s)',
                         'sap_knvk.MANDT+KUNNR -> sap_kna1.MANDT+KUNNR: 1 with a value, 0 orphan(s)',
                         'sap_vbpa.MANDT+PARNR -> sap_knvk.MANDT+PARNR: 1 with a value, 0 orphan(s)',
                         'sap_kna1.MANDT+ADRNR -> sap_adrc.CLIENT+ADDRNUMBER: 3 with a value, 0 orphan(s)',
                         'sap_t001.MANDT+ADRNR -> sap_adrc.CLIENT+ADDRNUMBER: 1 with a value, 0 orphan(s)',
                         'sap_vbpa.MANDT+ADRNR -> sap_adrc.CLIENT+ADDRNUMBER: 1 with a value, 0 orphan(s)',
                         'sap_adr6.CLIENT+ADDRNUMBER+DATE_FROM -> sap_adrc.CLIENT+ADDRNUMBER+DATE_FROM: 2 with a '
                         'value, 0 orphan(s)',
                         'sap_vbfa.MANDT+VBELV+POSNV -> sap_vbap.MANDT+VBELN+POSNR: 5 with a value, 0 orphan(s)',
                         'sap_vbfa.MANDT+VBELN+POSNN -> sap_lips.MANDT+VBELN+POSNR: 2 with a value, 0 orphan(s)',
                         'sap_vbfa.MANDT+VBELN+POSNN -> sap_vbrp.MANDT+VBELN+POSNR: 4 with a value, 0 orphan(s)',
                         'sap_vbfa.MANDT+VBELN -> sap_vbak.MANDT+VBELN: 0 with a value, 0 orphan(s)',
                         'sap_vbfa.MANDT+VBELN -> sap_likp.MANDT+VBELN: 2 with a value, 0 orphan(s)',
                         'sap_vbfa.MANDT+VBELN -> sap_vbrk.MANDT+VBELN: 4 with a value, 0 orphan(s)'],
             'header_amounts': ['sap_vbak.NETWR over sap_vbap: up to 3 per header',
                                'sap_vbap.NETWR over sap_vbep: up to 2 per header',
                                'sap_vbap.NETWR over sap_lips: up to 1 per header',
                                'sap_vbrk.NETWR+MWSBK over sap_vbrp: up to 2 per header',
                                'sap_vbap.NETWR over sap_vbrp: up to 2 per header'],
             'numbers': {'orders': 4,
                         'sales_organisations': 2,
                         'orders_in_2000': 1,
                         'order_value_per_header': '950.00',
                         'order_value_over_lines': '2150.00',
                         'billing_documents': 3,
                         'billed': '600.00',
                         'billed_over_lines': '1000.00',
                         'billing_documents_counted': 1,
                         'billed_without_cancellations': '400.00',
                         'cancelled': 1,
                         'cancellations': 1}}}
