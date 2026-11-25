"""ON1: a synthetic SAP + Dynamics 365 pair in one product lakehouse, local only (docs/SMOOTH/COMBINE-SOURCES.md).

SYNTHETIC DEMO DATA. Every row is made up: the SAP rows are fabric_backend/sap_demo.py's default demo tables, the
Dynamics 365 rows are fabric_backend/dynamics_demo.py's Dataverse tables (as Link to Microsoft Fabric lands them). Both
demos and their goldens stay unchanged; this fixture adds a few rows and two columns, in the way
tests/fixtures/multi_lakehouse.py adds `SAP_Customer_No__c` to the Salesforce demo:

- SAP `KNA1` gets customers 0000000013 and 0000000014 in client 100 (6 rows: 5 in client 100, 1 in client 200).
- Dataverse `account` gets accounts 5 and 6 and the standard column `accountnumber`, filled with the SAP customer
  number the way a sales team types it: 10, 0000000011, 12, 13, 0000000013, and empty for account 6 (a prospect).
  Accounts 4 and 5 both carry customer 13: the ambiguous pair.
- Dataverse `product` gets the standard column `productnumber`: 1, 000000000000000002, and empty for the service day.

What the counts must say (EXPECTED; the tests assert every number):

| Match | Rows (D365 / SAP) | Filled | As written | After normalising | Matched | Ambiguous | Only in SAP | Only in D365 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `d365.account.accountnumber` -> `sap.KNA1.KUNNR` (M2) | 6 / 6 | 5 | 2 | 5 | 3 | 2 accounts on 1 customer | 2 (14, and client 200's 10) | 1 (account 6) |
| `d365.product.productnumber` -> `sap.MARA.MATNR` (M2) | 3 / 4 | 2 | 1 | 2 | 2 | 0 | 2 (material 3, and client 200's 1) | 1 (the service day) |

The match runs within SAP's client with the most rows (100); client 200's rows stay, counted as only in SAP.

`install(monkeypatch)` is tests/fixtures/multi_lakehouse.py's `install` over these lakehouses: the same fake Fabric
readers and SQL endpoint, and a POST, PATCH, PUT or DELETE to any address fails the test.
"""
from __future__ import annotations

from fixtures import multi_lakehouse as mlh

from fabric_backend import dynamics_demo, sap_demo

WORKSPACE = mlh.WORKSPACE
SOURCE = "sales_product_lh"
SCHEMA = "sap+d365"
LAKEHOUSES = {
    "sap_lh": {"sap_silver": ("sap", "sap_lh.sap_silver")},
    "d365_lh": {"d365_silver": ("d365", "d365_lh.d365_silver")},
    SOURCE: {"sap": ("sap", "sap_lh.sap_silver"), "d365": ("d365", "d365_lh.d365_silver")},   # schema shortcuts
}
SHORTCUTS = {(SOURCE, "sap"): "sap_lh.sap_silver", (SOURCE, "d365"): "d365_lh.d365_silver"}
ITEMS = {name: {"id": f"bbbbbbbb-0000-0000-0000-{i:012d}", "displayName": name, "type": "Lakehouse",
                "schemas_enabled": True} for i, name in enumerate(LAKEHOUSES, 1)}

KNA1_EXTRA = [("100", "0000000013", "Demo Customer 13", "Demo Street 4", "11114", "Demo City", "DE", "+00 000 0013", ""),
              ("100", "0000000014", "Demo Customer 14", "Demo Street 5", "11115", "Demo City", "DE", "+00 000 0014", "")]
ACCOUNT_NUMBER = ["10", "0000000011", "12", "13", "0000000013", None]       # accounts 1-6, in order
PRODUCT_NUMBER = ["1", "000000000000000002", None]                         # products 1-3, in order

CUSTOMER = "match:d365.account.accountnumber>sap.KNA1.KUNNR"
PRODUCT = "match:d365.product.productnumber>sap.MARA.MATNR"
EXPECTED = {
    "customer": {"id": CUSTOMER, "rule": "M2", "counts": {
        "a_rows": 6, "filled": 5, "found_raw": 2, "found": 5, "b_rows": 6, "b_found": 4, "b_shared": 1, "distinct": 4,
        "only_a": 1, "only_b": 2, "ambiguous": 2, "matched": 3}, "customers": 7},
    "product": {"id": PRODUCT, "rule": "M2", "counts": {
        "a_rows": 3, "filled": 2, "found_raw": 1, "found": 2, "b_rows": 4, "b_found": 2, "b_shared": 0, "distinct": 2,
        "only_a": 1, "only_b": 2, "ambiguous": 0, "matched": 2}, "customers": 5},
}


def _guid(prefix: str, n: int) -> str:
    return f"{prefix}000000-0000-4000-8000-{n:012d}"


def rows(source: str) -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    """{table: (columns, kinds, rows)}: "sap" (the SAP demo plus two customers) or "d365" (the Dataverse demo tables
    plus two accounts, accountnumber and productnumber)."""
    if source == "sap":
        out = dict(sap_demo.tables())
        cols, kinds, rws = out["KNA1"]
        out["KNA1"] = (cols, kinds, list(rws) + KNA1_EXTRA)
        return out
    if source != "d365":
        return mlh.rows(source)
    out = {n: v for n, v in dynamics_demo.tables().items() if dynamics_demo.module_of(n) == "dataverse"}
    cols, kinds, rws = out["account"]
    rws = list(rws)
    last = rws[-1]
    for n in (5, 6):                                  # two more accounts, shaped like account 4
        i = _guid("a1", n)
        rws.append((i, i, f"Demo Account {n}") + tuple(last[3:-1]) + (1000 + n,))
    out["account"] = (cols + ["accountnumber"], kinds + ["string"],
                      [tuple(r) + (ACCOUNT_NUMBER[k],) for k, r in enumerate(rws)])
    cols, kinds, rws = out["product"]
    out["product"] = (cols + ["productnumber"], kinds + ["string"],
                      [tuple(r) + (PRODUCT_NUMBER[k],) for k, r in enumerate(rws)])
    return out


def install(monkeypatch) -> mlh.Workspace:
    """The tools over the SAP + Dynamics 365 lakehouses (multi_lakehouse.install with this fixture's tables)."""
    monkeypatch.setattr(mlh, "LAKEHOUSES", LAKEHOUSES)
    monkeypatch.setattr(mlh, "SHORTCUTS", SHORTCUTS)
    monkeypatch.setattr(mlh, "ITEMS", ITEMS)
    monkeypatch.setattr(mlh, "LAYOUTS", {**mlh.LAYOUTS, "on1": tuple(LAKEHOUSES)})
    monkeypatch.setattr(mlh, "rows", rows)
    return mlh.install(monkeypatch, "on1")
