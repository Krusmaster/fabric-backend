"""B3 (15 November 2026, backlog I-02): the file route's load notebook, the parts that need no Spark.

The notebook itself runs on a local Spark in tests/test_b3_connect_files_spark.py (CI's `notebooks` job). Not run in Fabric."""
import ast
import re

import pytest

from fabric_backend import connect_files as cf
from fabric_backend import mill, notebook
from fabric_backend.schema import Column, Schema, Table


def test_source_types_map_to_the_spark_type_the_notebook_casts_to():
    assert [cf.spark_type(t) for t in ("INT", "bigint", "tinyint", "bit", "nvarchar", "varchar(50)", "decimal(18,2)", "numeric(9)",
                                       "decimal", "money", "float", "real", "datetime2", "date", "uniqueidentifier")] == [
        ("int", True), ("bigint", True), ("smallint", True), ("boolean", True), ("string", True), ("string", True),
        ("decimal(18,2)", True), ("decimal(9,0)", True), ("decimal(38,10)", True), ("decimal(19,4)", True), ("double", True),
        ("float", True), ("timestamp", True), ("date", True), ("string", True)]
    # a type the notebook does not convert is loaded as text and said, not guessed
    assert cf.spark_type("geography") == ("string", False) and cf.spark_type("decimal(60,2)") == ("decimal(38,10)", True)
    s = Schema(schema="erp")
    s.tables["sites"] = Table("sites", [Column("site_id", "int"), Column("shape", "geography")], schema="erp")
    spec = cf.spec(s)
    assert cf.kept_as_text(spec) == ["sites.shape (geography)"]
    assert "Loaded as text, because the source type is not one this notebook converts: sites.shape (geography)." in cf.cells(spec)[0][1]


def test_the_notebook_has_one_load_per_table_and_round_trips_as_a_fabric_notebook():
    spec = cf.spec(mill.schema())
    cells = cf.cells(spec)
    assert [k for k, _ in cells] == ["markdown", "parameters", "code"] + ["code"] * 16 + ["code"]
    assert [c for k, c in cells[3:-1]] == [f"load({t!r})" for t in mill.SCHEMAS]
    for kind, code in cells:
        if kind != "markdown":
            ast.parse(code)
    params = {t.targets[0].id: ast.literal_eval(t.value) for t in ast.parse(cells[1][1]).body}
    assert params == {"CONNECT_FOLDER": "Files/connect", "BRONZE_SCHEMA": "bronze", "TABLE_FORMAT": "delta", "DELIMITER": ",",
                      "ENCODING": "UTF-8", "DECIMAL_COMMA": False, "DATE_FORMAT": "", "TIMESTAMP_FORMAT": "", "ON_BAD_VALUE": "refuse",
                      "READ_EXCEL": True, "LOCAL_FILES_ROOT": "/lakehouse/default"}
    entities = next(ast.literal_eval(n.value) for n in ast.parse(cells[2][1]).body
                    if isinstance(n, ast.Assign) and n.targets[0].id == "ENTITIES")
    assert entities["sales_orders"] == [("sales_order_id", "int"), ("order_date", "date"), ("bill_to_customer_id", "int"),
                                        ("ship_to_customer_id", "int"), ("status", "string")]
    text = cf.source(spec, "11111111-1111-1111-1111-111111111111", "lh-1", "erp_lh")
    assert text.startswith(notebook.HEADER) and '"default_lakehouse": "lh-1"' in text
    assert notebook.parse(text) == [(k, c.strip("\n")) for k, c in cells]


def test_the_notebook_installs_nothing_calls_nothing_and_prints_no_rows():
    code = "\n".join(c for k, c in cf.cells(cf.spec(mill.schema())) if k != "markdown")
    for word in ("pip", "http", "requests", "urlopen", "socket", "getSecret", "mssparkutils", "notebookutils", ".show(", "display(",
                 "toPandas", "DROP ", "overwrite", "DELETE "):
        assert word not in code, word
    imports = {n.names[0].name if isinstance(n, ast.Import) else n.module for n in ast.walk(ast.parse(code))
               if isinstance(n, (ast.Import, ast.ImportFrom))}
    assert imports == {"json", "os", "datetime", "urllib.parse", "pyspark.sql", "pandas"}
    # the only things written: appends to its own tables, after the owner check
    assert re.findall(r"\.mode\(\"(\w+)\"\)", code) == ["append"] and code.count("saveAsTable") == 1
    assert code.index("is_ours_or_absent(name)") < code.index("saveAsTable")
    # a refused file is described by the kind of error, never by its text (Spark's message quotes the row)
    assert "type(e).__name__" in code and "str(e)}" not in code


def test_names_that_cannot_be_a_folder_or_a_table_are_refused_before_anything_is_written():
    def one(name, cols=("id",)):
        s = Schema(schema="erp")
        s.tables[name] = Table(name, [Column(c, "int") for c in cols], schema="erp")
        return s
    for bad in ("a/b", "..", "x*", "t`", " lead", "q?", "back\\slash"):
        with pytest.raises(ValueError, match="cannot be a folder"):
            cf.spec(one(bad))
    with pytest.raises(ValueError, match="keeps its own record"):
        cf.spec(one(cf.STATE))
    with pytest.raises(ValueError, match="twice"):
        cf.spec(one("t", ("id", "ID")))
    with pytest.raises(ValueError, match="Not in the schema 'mill': nope"):
        cf.spec(mill.schema(), tables=["customers", "nope"])
    with pytest.raises(ValueError, match="cannot be a folder"):
        cf.spec(mill.schema(), bronze_schema="br/onze")
    with pytest.raises(ValueError, match="No tables"):
        cf.spec(Schema(schema="empty"))
    assert cf.spec(one("Order Lines 2026"))["entities"][0]["entity"] == "Order Lines 2026"      # spaces are fine: names are quoted


def test_a_type_can_be_overridden_per_column_and_only_to_a_type_the_notebook_knows():
    spec = cf.spec(mill.schema(), tables=["stg_supplier_prices"], types={"stg_supplier_prices": {"LOADED_AT": "string",
                                                                                                "unit_price": "decimal(18,4)"}})
    assert [(c["name"], c["type"]) for c in spec["entities"][0]["columns"]] == [
        ("supplier_price_id", "int"), ("supplier_id", "int"), ("item_id", "int"), ("unit_price", "decimal(18,4)"), ("loaded_at", "string")]
    for types, match in (({"items": {"name": "string"}}, "not loaded"), ({"stg_supplier_prices": {"nope": "string"}}, "does not have"),
                         ({"stg_supplier_prices": {"unit_price": "int); DROP"}}, "use one of")):
        with pytest.raises(ValueError, match=match):
            cf.spec(mill.schema(), tables=["stg_supplier_prices"], types=types)


def test_the_schema_export_of_b2_feeds_the_notebook():
    """The DBA's export (connect_export.py) gives SQL Server's type names; the notebook's types come from them."""
    from fabric_backend import connect_export as ce
    rows = [{"kind": "column", "table_schema": "dbo", "table_name": "orders", "column_name": n, "data_type": t, "ordinal_position": i + 1}
            for i, (n, t) in enumerate([("order_id", "int"), ("placed", "datetime2"), ("total", "money"), ("note", "nvarchar"),
                                        ("paid", "bit")])]
    import json
    spec = cf.spec(ce.parse(json.dumps(rows), "dbo"))
    assert [(c["name"], c["type"]) for c in spec["entities"][0]["columns"]] == [
        ("order_id", "int"), ("placed", "timestamp"), ("total", "decimal(19,4)"), ("note", "string"), ("paid", "boolean")]
    assert spec["owner"] == "connect-files/dbo" and cf.kept_as_text(spec) == []
