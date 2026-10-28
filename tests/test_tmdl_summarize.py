"""TMDL drafts never sum a key, a relationship column or an identifier, in any benchmark schema (names only, as a
lakehouse gives them, and with the declared keys, as a warehouse or SQL Server gives them) or the shop schema."""
import re

import pytest

from fabric_backend import seed, semantic_model
from fabric_backend.infer import plan
from fabric_backend.schema import Schema
from test_inference_quality import NAMES, load, names_only

INFO = dict(workspace_id="w", item_id="i", item_name="src", item_kind="Warehouse", schema="dbo",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db="src", schemas_enabled=True)


def declared(fixture: dict) -> Schema:
    rows = [("dbo", t["name"], c, typ, i) for t in fixture["tables"] for i, (c, typ) in enumerate(t["columns"], 1)]
    keys = []
    for t in fixture["tables"]:
        keys += [{"table_name": t["name"], "constraint_type": "PRIMARY KEY", "column_name": c, "ordinal_position": i,
                  "constraint_name": f"PK_{t['name']}"} for i, c in enumerate(t["primary_key"], 1)]
        for j, f in enumerate(t["foreign_keys"]):
            keys += [{"table_name": t["name"], "constraint_type": "FOREIGN KEY", "column_name": c, "ordinal_position": i,
                      "constraint_name": f"FK_{t['name']}_{j}", "ref_table": f["ref_table"], "ref_column": rc}
                     for i, (c, rc) in enumerate(zip(f["columns"], f["ref_columns"]), 1)]
    return Schema.from_information_schema(rows, keys, schema="dbo")


def summarize_by(p) -> dict[tuple[str, str], str]:
    """(table, column) -> summarizeBy, read back from the drafted TMDL."""
    out = {}
    for path, text in semantic_model.draft(p, INFO, "m")["parts"].items():
        if path.startswith("definition/tables/"):
            table = re.search(r"^table (.+)$", text, re.M).group(1).strip("'")
            for m in re.finditer(r"^\tcolumn (.+)\n((?:\t\t.*\n|\n)*?)\t\tsummarizeBy: (\w+)", text, re.M):
                out[(table, m.group(1).strip("'"))] = m.group(3)
    return out


CASES = [("shop", lambda: plan(seed.schema("shop")))]
for _n in NAMES:
    CASES.append((f"{_n} names only", lambda n=_n: plan(names_only(load(n)))))
    CASES.append((f"{_n} declared", lambda n=_n: plan(declared(load(n)))))


@pytest.mark.parametrize("label,make", CASES, ids=[c[0] for c in CASES])
def test_no_key_relationship_or_identifier_is_summed(label, make):
    p = make()
    s = summarize_by(p)
    assert s and "sum" in s.values(), label                                          # every schema has measures left
    keys = {(t, c) for t, (cols, _) in p.keys.items() for c in cols}
    rels = {(r.source, c) for r in p.relationships for c in r.source_cols} | {(r.target, c) for r in p.relationships for c in r.target_cols}
    ids = {k for k in s if semantic_model._looks_like_id(k[1])}
    summed = {k for k, v in s.items() if v == "sum"}
    assert not summed & keys, (label, sorted(summed & keys))
    assert not summed & rels, (label, sorted(summed & rels))
    assert not summed & ids, (label, sorted(summed & ids))


def test_camelcase_ids_codes_and_label_numbers_are_not_summed():
    aw = summarize_by(plan(names_only(load("adventureworks"))))
    for col in [("Customer", "PersonID"), ("Customer", "TerritoryID"), ("SalesOrderHeader", "SalesPersonID"),
                ("TransactionHistory", "ReferenceOrderID"), ("AWBuildVersion", "SystemInformationID"),
                ("SalesOrderHeader", "RevisionNumber"), ("SalesOrderHeader", "Status"), ("CreditCard", "ExpYear"),
                ("SalesTaxRate", "TaxType")]:
        assert aw[col] == "none", col
    for col in [("SalesOrderDetail", "OrderQty"), ("SalesOrderDetail", "UnitPrice")]:
        assert aw[col] == "sum", col
    # the total that doubles (amounts.py): an amount on a table that another has several rows per row of is not summed
    # by default; SubTotal on the header, ListPrice on the product, each repeated per SalesOrderDetail row in a join
    for col in [("SalesOrderHeader", "SubTotal"), ("Product", "ListPrice")]:
        assert aw[col] == "none", col
    for word, expected in (("PersonID", True), ("CustomerId", True), ("ship_to_id", True), ("FiscalYear", True),
                           ("PAID", False), ("unit_price", False), ("Quantity", False), ("Typeface", False)):
        assert semantic_model._looks_like_id(word) is expected, word


def test_a_reference_no_rule_names_is_summed_until_it_is_confirmed():
    # Orders.ShipVia points at Shippers, but nothing in its name says so: the names-only plan leaves it a number. Once the
    # user confirms the relationship it is a reference and is not summed. (The declared plan has it as R0 already.)
    nw = load("northwind")
    assert summarize_by(plan(names_only(nw)))[("Orders", "ShipVia")] == "sum"
    ship_via = {"source": "Orders", "source_cols": ["ShipVia"], "target": "Shippers", "target_cols": ["ShipperID"]}
    assert summarize_by(plan(names_only(nw), confirmed=[ship_via]))[("Orders", "ShipVia")] == "none"
    assert summarize_by(plan(declared(nw)))[("Orders", "ShipVia")] == "none"
