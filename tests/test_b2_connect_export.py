"""B2 (15 November 2026, backlog I-03): the SQL Server schema export a DBA runs, and its parser.

Synthetic files only, built from the mill sample's tables (fabric_backend/mill.py) with keys declared here; not run
against a live SQL Server.
"""
import json

import pytest
import sqlglot
from sqlglot import exp

from fabric_backend import connect_export as ce
from fabric_backend import mill
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

SQLTYPE = {"INT": "int", "STRING": "nvarchar", "DOUBLE": "float", "DATE": "date", "TIMESTAMP": "datetime2"}
PKS = {"customers": ["customer_id"], "items": ["item_id"], "sales_orders": ["sales_order_id"],
       "sales_order_lines": ["sales_order_id", "line_no"], "work_centers": ["work_center_code"]}
FKS = [  # (table, constraint, cols, ref_schema, ref_table, ref_cols)
    ("sales_order_lines", "FK_sol_items", ["item_id"], "mill", "items", ["item_id"]),
    ("sales_order_lines", "FK_sol_orders", ["sales_order_id"], "mill", "sales_orders", ["sales_order_id"]),
    ("sales_orders", "FK_so_billto", ["bill_to_customer_id"], "mill", "customers", ["customer_id"]),
    ("deliveries", "FK_del_lines", ["sales_order_id", "line_no"], "mill", "sales_order_lines", ["sales_order_id", "line_no"]),
    ("items", "FK_items_supplier_elsewhere", ["supplier_id"], "staging", "suppliers_raw", ["supplier_id"]),
]


def export_rows() -> list[dict]:
    out = []
    for table, cols in mill.SCHEMAS.items():
        for i, c in enumerate(cols.split(", "), 1):
            name, typ = c.split()
            out.append({"kind": "column", "table_schema": "mill", "table_name": table, "column_name": name,
                        "data_type": SQLTYPE[typ], "ordinal_position": i})
    out.append({"kind": "column", "table_schema": "staging", "table_name": "suppliers_raw", "column_name": "supplier_id",
                "data_type": "int", "ordinal_position": 1})
    for table, cols in PKS.items():
        for i, c in enumerate(cols, 1):
            out.append({"kind": "key", "table_schema": "mill", "table_name": table, "column_name": c, "ordinal_position": i,
                        "constraint_type": "PRIMARY KEY", "constraint_name": f"PK_{table}"})
    for table, name, cols, rs, rt, rcols in FKS:
        for i, (c, rc) in enumerate(zip(cols, rcols), 1):
            out.append({"kind": "key", "table_schema": "mill", "table_name": table, "column_name": c, "ordinal_position": i,
                        "constraint_type": "FOREIGN KEY", "constraint_name": name, "ref_schema": rs, "ref_table": rt,
                        "ref_column": rc})
    return out


def direct() -> Schema:
    """What Schema.from_sql makes of the same metadata (the rows of COLUMNS_SQL and KEYS_SQL for schema 'mill')."""
    rs = export_rows()
    cols = sorted((r for r in rs if r["kind"] == "column" and r["table_schema"] == "mill"),
                  key=lambda r: (r["table_name"], r["ordinal_position"]))       # COLUMNS_SQL's ORDER BY
    keys = [{**r, "ref_table": r.get("ref_table"), "ref_column": r.get("ref_column"), "ref_schema": r.get("ref_schema")}
            for r in rs if r["kind"] == "key"]
    return Schema.from_information_schema(cols, keys, schema="mill")


def shape(s: Schema):
    return [(t.name, [(c.name, c.data_type) for c in t.columns], t.keys, t.foreign_keys) for t in s]


def test_parse_equals_what_from_sql_reads():
    s = ce.parse(ce.to_csv(export_rows()), schema="mill")
    assert len(s) == 16 and s.schema == "mill"
    assert shape(s) == shape(direct())
    assert s["sales_order_lines"].keys == ["sales_order_id", "line_no"]
    assert s["deliveries"].foreign_keys == [(["sales_order_id", "line_no"], "sales_order_lines", ["sales_order_id", "line_no"])]
    assert s["items"].foreign_keys == []                         # a key into another schema is left out, as from_sql does
    assert [c.name for c in s["items"].columns] == ["item_id", "item_number", "name", "item_type", "unit",
                                                    "standard_cost", "supplier_id"]


def test_the_plan_from_the_file_is_the_plan_from_the_metadata():
    a, b = plan(ce.parse(ce.to_csv(export_rows()), schema="mill")), plan(direct())
    assert a.summary() == b.summary()
    assert a.keys["customers"] == (["customer_id"], "K0")          # declared in the export


def test_row_order_and_case_do_not_matter():
    rs = list(reversed(export_rows()))
    assert shape(ce.parse(ce.to_csv(rs), schema="MILL")) == shape(direct())


def test_json_export_reads_the_same():
    text = json.dumps(export_rows())
    assert shape(ce.parse(text, schema="mill")) == shape(direct())
    assert shape(ce.parse(json.dumps({"rows": export_rows()}), schema="mill")) == shape(direct())


def test_sqlcmd_output_with_its_dashed_line_and_nulls():
    text = ce.to_csv(export_rows())
    head, rest = text.split("\n", 1)
    dashed = ",".join("-" * len(h) for h in head.split(","))
    text = "﻿" + head + "\n" + dashed + "\n" + rest.replace(",,", ",NULL,")
    assert shape(ce.parse(text, schema="mill")) == shape(direct())


def test_schemas_lists_every_schema_with_its_tables():
    assert ce.schemas(ce.to_csv(export_rows())) == [{"schema": "mill", "tables": 16}, {"schema": "staging", "tables": 1}]


@pytest.mark.parametrize("bad, said", [
    ("sample_value", "columns that are not in a schema export"),
    ("column_default", "columns that are not in a schema export"),
    ("row_count", "columns that are not in a schema export"),
])
def test_a_file_with_values_added_is_refused(bad, said):
    text = ce.to_csv(export_rows()).splitlines()
    text = [text[0] + "," + bad] + [line + ",ACME AB" for line in text[1:]]
    with pytest.raises(ce.ExportError, match=said):
        ce.parse("\n".join(text), "mill")


def test_extra_column_in_json_is_refused():
    rs = export_rows()
    rs[3]["value"] = 42
    with pytest.raises(ce.ExportError, match="not in a schema export"):
        ce.rows(json.dumps(rs))


@pytest.mark.parametrize("change, said", [
    ({"kind": "row"}, "kind 'row'"),
    ({"kind": "key", "constraint_type": "CHECK"}, "constraint type 'CHECK'"),
    ({"column_name": ""}, "no table or column name"),
    ({"ordinal_position": "first"}, "not a number"),
])
def test_rows_an_export_cannot_hold_are_refused(change, said):
    rs = export_rows()
    rs[0] = {**rs[0], **change}
    with pytest.raises(ce.ExportError, match=said):
        ce.rows(ce.to_csv(rs))


def test_wrong_schema_and_empty_files_say_what_is_there():
    with pytest.raises(ce.ExportError, match=r"schema 'shop' is not in the export \(it has \['mill', 'staging'\]\)"):
        ce.parse(ce.to_csv(export_rows()), "shop")
    with pytest.raises(ce.ExportError, match="empty"):
        ce.rows("  ")
    with pytest.raises(ce.ExportError, match="no column rows"):
        ce.rows(ce.to_csv([r for r in export_rows() if r["kind"] == "key"]))
    with pytest.raises(ce.ExportError, match="list of objects"):
        ce.rows('{"a": 1}')


def test_the_query_reads_only_information_schema_and_no_values():
    """The export query is T-SQL that reads INFORMATION_SCHEMA views only, writes nothing, and selects no view column
    that can hold a value from the data (a column default, a check clause)."""
    statements = [s for s in sqlglot.parse(ce.export_sql(), read="tsql") if s is not None]
    selects = [s for s in statements if isinstance(s, (exp.Select, exp.Union))]
    assert len(selects) == 1
    q = selects[0]
    tables = {(t.db.upper(), t.name.upper()) for t in q.find_all(exp.Table)}
    assert tables == {("INFORMATION_SCHEMA", n) for n in
                      ("COLUMNS", "TABLES", "TABLE_CONSTRAINTS", "KEY_COLUMN_USAGE", "REFERENTIAL_CONSTRAINTS")}
    cols = {c.name.upper() for c in q.find_all(exp.Column)}
    assert not cols & {"COLUMN_DEFAULT", "CHECK_CLAUSE", "VIEW_DEFINITION", "ROUTINE_DEFINITION"}
    for kind in (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Merge):
        assert not any(isinstance(s, kind) or s.find(kind) for s in statements)
    first = q.this if isinstance(q, exp.Union) else q
    while isinstance(first, exp.Union):
        first = first.this
    assert [e.alias_or_name.lower() for e in first.expressions] == list(ce.FIELDS)
