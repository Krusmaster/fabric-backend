"""MG1: Snowflake and Databricks metadata to a Fabric migration plan, and the before/after comparison
(fabric_backend/migrate/).

Every fixture is synthetic (tests/fixtures/mg1/README.md): hand-written exports of a made-up database and catalog, and
made-up rows in fabric_backend/migrate/demo.py. Nothing here connects to Snowflake, Databricks or Fabric.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from fabric_backend import migrate
from fabric_backend.migrate import compare, demo, metadata, plan, sqlrules

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "mg1"
SF, DB = FIX / "snowflake", FIX / "databricks"
DOC = ROOT / "docs" / "MIGRATE-DATABRICKS-SNOWFLAKE.md"


def _sf():
    return metadata.read(SF, "snowflake", "SALES")


def _db():
    return metadata.read(DB, "databricks")


# ------------------------------------------------------------------------------------------------------ fixtures

def test_the_fixtures_say_they_are_synthetic():
    readme = (FIX / "README.md").read_text(encoding="utf-8")
    assert "synthetic" in readme.lower() and "No\nfile was exported" in readme
    for f in (SF / "tables.csv", DB / "tables.csv"):
        assert "Synthetic" in f.read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------------ reading

def test_reads_the_snowflake_export():
    m = _sf()
    s = metadata.summary(m)
    assert s["objects"] == {"table": 5, "view": 4} and s["other_schemas_left_out"] == 1
    assert s["declared_primary_keys"] == 4 and s["declared_foreign_keys"] == 3 and s["user_functions"] == 1
    assert m.tables["ORDER_LINES"].primary_key == ["ORDER_ID", "LINE_NO"]           # by key_sequence, not file order
    assert m.tables["EVENTS"].flags == ["transient"]
    assert m.tables["ORDERS"].comment.startswith("Synthetic") and m.tables["CUSTOMERS"].columns[2].comment == "ISO country code"
    assert m.tables["PRODUCTS"].columns[2].data_type == "VARIANT" and m.functions == ["MARGIN_PCT"]
    fk = m.tables["ORDER_LINES"].foreign_keys
    assert [(x["columns"], x["ref_table"], x["ref_columns"]) for x in fk] == [
        (["ORDER_ID"], "ORDERS", ["ORDER_ID"]), (["PRODUCT_ID"], "PRODUCTS", ["PRODUCT_ID"])]
    assert "qualify" in m.tables["V_LATEST_ORDER"].view_sql


def test_reads_the_databricks_export():
    m = _db()
    assert m.schema == "sales"
    assert {n: t.kind for n, t in m.tables.items() if t.kind != "table"} == {
        "crm_contacts": "foreign", "mv_daily_sales": "materialized view", "v_open_orders": "view", "v_order_items": "view",
        "v_orders_yesterday": "view"}
    assert m.tables["payments"].flags == ["row filter"] and m.tables["products_ext"].format == "PARQUET"
    assert m.tables["order_lines"].columns[4].data_type == "ARRAY<STRING>"
    assert m.ignored == [{"what": "foreign key order_lines_products_fk on order_lines",
                          "why": "it points into schema reference, outside this plan"}]


def test_two_schemas_need_a_choice_and_bad_input_says_what_is_wrong(tmp_path):
    with pytest.raises(ValueError, match="2 schemas .*SALES, STAGING.*say which one"):
        metadata.read(SF, "snowflake")
    with pytest.raises(ValueError, match="source must be one of"):
        metadata.read(SF, "oracle")
    (tmp_path / "columns.csv").write_text("table_name,column_name\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no tables.csv"):
        metadata.read(tmp_path, "snowflake")
    with pytest.raises(ValueError, match="no such file"):
        metadata.read(tmp_path / "missing", "databricks")


def test_one_json_file_with_quoted_headers_reads_the_same(tmp_path):
    export = {"tables": [{'"TABLE_SCHEMA"': "S", '"TABLE_NAME"': "A", '"TABLE_TYPE"': "BASE TABLE"},
                         {'"TABLE_SCHEMA"': "S", '"TABLE_NAME"': "B", '"TABLE_TYPE"': "BASE TABLE"}],
              "columns": [{"TABLE_SCHEMA": "S", "TABLE_NAME": t, "COLUMN_NAME": c, "ORDINAL_POSITION": i, "DATA_TYPE": "TEXT"}
                          for t, cs in (("A", ["A_ID"]), ("B", ["B_ID", "A_ID"])) for i, c in enumerate(cs, 1)],
              "primary_keys": [{"schema_name": "S", "table_name": "A", "column_name": "A_ID", "key_sequence": 1, "constraint_name": "PK_A"}],
              "imported_keys": [{"pk_schema_name": "S", "pk_table_name": "A", "pk_column_name": "A_ID", "fk_schema_name": "S",
                                 "fk_table_name": "B", "fk_column_name": "A_ID", "key_sequence": 1, "fk_name": "FK_B_A"}],
              "notes": [{"x": 1}]}
    f = tmp_path / "export.json"
    f.write_text(json.dumps(export), encoding="utf-8")
    m = metadata.read(f, "snowflake")
    assert m.tables["A"].primary_key == ["A_ID"] and m.tables["B"].foreign_keys[0]["ref_table"] == "A"
    assert {"what": "file notes", "why": "not one of the exports this reader reads"} in m.ignored


# ------------------------------------------------------------------------------------------------------ the model

def test_declared_keys_and_links_are_candidates_with_their_provenance():
    p, r = plan.build(_sf())
    assert {t: rule for t, (_, rule) in p.keys.items()} == {"CUSTOMERS": "Snowflake metadata", "ORDERS": "Snowflake metadata",
                                                           "ORDER_LINES": "Snowflake metadata", "PRODUCTS": "Snowflake metadata",
                                                           "EVENTS": "K2"}
    rels = {(x.source, x.target): x for x in p.relationships}
    assert all(x.rule == "Snowflake metadata" for x in rels.values()) and len(rels) == 3
    assert rels[("ORDER_LINES", "ORDERS")].note.startswith("declared by metadata (Snowflake): FOREIGN KEY FK_LINES_ORDER")
    assert r["model"]["provenance"] == "declared by metadata (Snowflake)" and "not verified against the rows" in r["model"]["status"]
    pd, rd = plan.build(_db())
    assert pd.keys["orders"][1] == "Databricks metadata"
    assert {(x.source, x.target, x.rule) for x in pd.relationships} >= {("payments", "orders", "Databricks metadata")}


def test_the_callers_keys_win_and_a_foreign_key_to_a_non_key_is_not_applied(tmp_path):
    p, r = plan.build(_sf(), keys={"ORDERS": ["ORDER_ID", "CUSTOMER_ID"]})
    assert p.keys["ORDERS"] == (["ORDER_ID", "CUSTOMER_ID"], "K1")
    assert not any(x.target == "ORDERS" and x.rule == "Snowflake metadata" for x in p.relationships)
    export = json.loads(json.dumps({"tables": [{"table_schema": "s", "table_name": t, "table_type": "MANAGED"} for t in ("a", "b")],
                                    "columns": [{"table_schema": "s", "table_name": t, "column_name": c, "ordinal_position": 1, "data_type": "STRING"}
                                                for t, c in (("a", "a_id"), ("a", "code"), ("b", "code"))],
                                    "constraints": [{"table_schema": "s", "table_name": "a", "constraint_name": "pk", "constraint_type": "PRIMARY KEY",
                                                     "column_name": "a_id", "ordinal_position": 1},
                                                    {"table_schema": "s", "table_name": "a", "constraint_name": "uq", "constraint_type": "CHECK",
                                                     "column_name": "code", "ordinal_position": 1},
                                                    {"table_schema": "s", "table_name": "b", "constraint_name": "fk", "constraint_type": "FOREIGN KEY",
                                                     "column_name": "code", "ordinal_position": 1, "ref_schema": "s", "ref_table": "a", "ref_column": "code"}]}))
    f = tmp_path / "e.json"
    f.write_text(json.dumps(export), encoding="utf-8")
    m = metadata.read(f, "databricks")
    _, r = plan.build(m)
    assert r["model"]["not_applied"][0]["why"].startswith("it references code, not a's declared key (a_id)")
    assert any(x["why"].startswith("constraint_type CHECK") for x in m.ignored)


def test_the_plan_on_the_landed_names_matches_without_case():
    from fabric_backend.schema import Schema
    rows = [("lh", t.lower(), c.lower(), "varchar", i) for t, cs in (("CUSTOMERS", ["CUSTOMER_ID", "NAME"]), ("ORDERS", ["ORDER_ID", "CUSTOMER_ID"]))
            for i, c in enumerate(cs, 1)]
    p, r = plan.build(_sf(), fabric_schema=Schema.from_information_schema(rows, schema="lh"))
    assert p.keys["orders"] == (["order_id"], "Snowflake metadata")
    assert [(x.source, x.source_cols, x.target) for x in p.relationships] == [("orders", ["customer_id"], "customers")]
    assert r["model"]["matched"] == {"CUSTOMERS": "customers", "ORDERS": "orders"}
    assert {x["object"] for x in r["model"]["not_applied"]} >= {"ORDER_LINES.FK_LINES_ORDER -> ORDERS"}


# ------------------------------------------------------------------------------------------------------ the plan

def test_landing_and_target_per_object_follow_the_dated_pages():
    _, r = plan.build(_sf())
    o = {x["object"]: x for x in r["objects"]}
    assert o["ORDERS"]["landing"]["how"] == "Mirroring (Snowflake)" and o["ORDERS"]["landing"]["doc"] == "mirror_snowflake"
    assert o["EVENTS"]["landing"]["mirroring"] == "not supported (transient table)"
    assert o["EVENTS"]["landing"]["how"].startswith("Copy job (Snowflake source")
    assert o["PRODUCTS"]["target"] == "Lakehouse Delta table" and o["PRODUCTS"]["rule"].startswith("T1 semi-structured column(s) ATTRIBUTES")
    assert o["V_LATEST_ORDER"]["landing"]["mirroring"] == "supported, 'syncs every 12 hours'"
    assert [c["short"] for c in o["EVENTS"]["column_findings"]] == ["VARIANT", "TIMESTAMP_TZ"]
    _, rw = plan.build(_sf(), "warehouse")
    assert {x["object"]: x["target"] for x in rw["objects"]}["ORDERS"] == "Warehouse table"
    _, d = plan.build(_db())
    o = {x["object"]: x for x in d["objects"]}
    assert o["orders"]["landing"]["how"].startswith("Mirroring (Azure Databricks Unity Catalog) for the parallel run")
    assert o["payments"]["landing"]["mirroring"] == "not supported (Tables with RLS/CLM policies)"
    assert o["products_ext"]["landing"]["mirroring"] == "not shown (PARQUET, not Delta)"
    assert o["crm_contacts"]["landing"]["how"] == "land from the system it federates (manual)"
    assert o["v_open_orders"]["landing"]["mirroring"] == "not supported ('Views and metric views don't appear')"
    assert [c["short"] for c in o["customers"]["column_findings"]] == ["TIMESTAMP_NTZ"]
    for doc in d["docs"].values():
        assert doc["url"].startswith("https://learn.microsoft.com/") and doc["read"] == "2026-11-16" and doc["page_date"]
    with pytest.raises(ValueError, match="lakehouse or warehouse"):
        plan.build(_db(), "lakewarehouse")


def test_more_than_a_thousand_tables_are_flagged_for_mirroring(tmp_path):
    n = plan.MIRROR_TABLE_LIMIT + 2
    export = {"tables": [{"table_schema": "S", "table_name": f"T{i:04d}", "table_type": "BASE TABLE"} for i in range(n)],
              "columns": [{"table_schema": "S", "table_name": f"T{i:04d}", "column_name": "ID", "ordinal_position": 1, "data_type": "TEXT"}
                          for i in range(n)]}
    f = tmp_path / "e.json"
    f.write_text(json.dumps(export), encoding="utf-8")
    _, r = plan.build(metadata.read(f, "snowflake"))
    beyond = [o["object"] for o in r["objects"] if o["landing"]["doc"] == "mirror_snowflake_limits"]
    assert beyond == [f"T{plan.MIRROR_TABLE_LIMIT:04d}", f"T{plan.MIRROR_TABLE_LIMIT + 1:04d}"]


def test_the_manual_list_and_what_it_does_not_do():
    _, r = plan.build(_db())
    assert "view v_order_items: LATERAL VIEW / explode (line 1)" in r["manual"]
    assert any(x.startswith("payments: Copy job") and "(manual)" in x for x in r["manual"])
    assert r["dry_run"] is True and any(x.startswith("creates nothing in Fabric") for x in r["not_done"])


# ------------------------------------------------------------------------------------------------------ view SQL

@pytest.mark.parametrize("source,sql,tsql", [
    ("snowflake", "select IFF(a > 0, a, 0) as x from t", "select IIF(a > 0, a, 0) as x from t"),
    ("snowflake", "select NVL(a, 0), IFNULL(b, 1) from t", "select COALESCE(a, 0), COALESCE(b, 1) from t"),
    ("snowflake", "select ZEROIFNULL(amount) from t", "select COALESCE(amount, 0) from t"),
    ("snowflake", "select a::NUMBER(12,2), b::string from t", "select CAST(a AS decimal(12,2)), CAST(b AS varchar(8000)) from t"),
    ("snowflake", "select (a + b)::int from t", "select CAST((a + b) AS int) from t"),
    ("snowflake", "select v:color::string from t", "select CAST(JSON_VALUE(v, '$.color') AS varchar(8000)) from t"),
    ("snowflake", "select v:a.b from t", "select JSON_VALUE(v, '$.a.b') from t"),
    ("snowflake", "select LISTAGG(n, ',') WITHIN GROUP (ORDER BY n) from t", "select STRING_AGG(n, ',') WITHIN GROUP (ORDER BY n) from t"),
    ("snowflake", "select TO_DATE(s) from t", "select CAST(s AS date) from t"),
    ("snowflake", "select distinct a from t order by a limit 5", "SELECT distinct TOP 5 a from t order by a"),
    ("snowflake", "create or replace view v as select 'a:b::c' as s from t", "CREATE OR ALTER VIEW v as select 'a:b::c' as s from t"),
    ("databricks", "select `a b`, if(x, 1, 2), date_add(d, 7) from t", "select [a b], IIF(x, 1, 2), DATEADD(day, 7, d) from t"),
    ("databricks", "select current_timestamp() as now from t -- nvl(x) in a comment", "select CURRENT_TIMESTAMP as now from t"),
])
def test_simple_constructs_are_translated_by_rule(source, sql, tsql):
    r = sqlrules.translate(sql, source)
    assert r["status"] == "translated by rule" and r["tsql"] == tsql and r["why"] is None


@pytest.mark.parametrize("source,sql,construct", [
    ("snowflake", "select f.value from t, lateral flatten(input => t.v) f", "FLATTEN (semi-structured to rows)"),
    ("snowflake", "select * from t at(timestamp => '2026-01-01'::timestamp)", "time travel"),
    ("snowflake", "select parse_json(s) from t", "semi-structured construction or parsing"),
    ("snowflake", "select array_agg(a) from t", "array aggregation"),
    ("snowflake", "select a from t where n ilike 'x%'", "ILIKE / RLIKE / regular expression"),
    ("snowflake", "select seq.nextval from t", "sequence"),
    ("snowflake", "select a from t connect by prior a = b", "recursive query"),
    ("snowflake", "select (a)::variant from t", ":: cast of an expression"),
    ("snowflake", "select v:items[0] from t", "semi-structured path with an index"),
    ("snowflake", "select a from t limit 5 offset 2", "LIMIT"),
    ("databricks", "select explode(tags) from t", "LATERAL VIEW / explode"),
    ("databricks", "select * from t VERSION AS OF 3", "time travel"),
    ("databricks", "select transform(xs, x -> x + 1) from t", "lambda / higher-order function"),
    ("databricks", "select date_add(current_date(), 1) from t", "source function not rewritten"),
    ("databricks", "with recursive r as (select 1) select * from r", "recursive query"),
])
def test_other_constructs_are_manual_with_their_line(source, sql, construct):
    r = sqlrules.translate("\n" + sql, source)
    assert r["status"] == "manual" and r["tsql"] is None
    assert any(c["construct"] == construct and c["line"] == 2 and c["status"] == "manual" for c in r["constructs"]), r["constructs"]


def test_supported_constructs_are_named_with_the_page_and_user_functions_are_manual():
    r = sqlrules.translate("select a from t qualify row_number() over (order by a) = 1", "snowflake")
    assert r["status"] == "no change needed" and r["constructs"][0]["construct"] == "QUALIFY"
    assert r["constructs"][0]["source"] == sqlrules.TSQL_PAGE
    r = sqlrules.translate("select margin_pct(a) from t", "snowflake", ["MARGIN_PCT"])
    assert r["why"] == "user-defined function MARGIN_PCT (line 1)"


def test_the_fixture_views():
    _, s = plan.build(_sf())
    _, d = plan.build(_db())
    status = {v["view"]: v["status"] for v in s["views"] + d["views"]}
    assert status == {"V_LATEST_ORDER": "translated by rule", "V_ORDER_MARGIN": "manual", "V_PRODUCT_ATTRIBUTES": "manual",
                      "V_TOP_CUSTOMERS": "translated by rule", "v_open_orders": "translated by rule", "v_order_items": "manual",
                      "v_orders_yesterday": "manual"}
    v = next(v for v in s["views"] if v["view"] == "V_LATEST_ORDER")
    assert "CAST(IIF(TOTAL_AMOUNT > 0, TOTAL_AMOUNT, 0) AS decimal(12,2)) as TOTAL" in v["tsql"] and "qualify" in v["tsql"]
    v = next(v for v in s["views"] if v["view"] == "V_TOP_CUSTOMERS")
    assert "'a:b'" in v["tsql"] and "-- synthetic" not in v["tsql"] and v["tsql"].startswith("CREATE OR ALTER VIEW")


def test_translation_is_deterministic():
    m = _sf()
    a = [sqlrules.translate(t.view_sql, "snowflake", m.functions, n) for n, t in m.tables.items() if t.view_sql]
    b = [sqlrules.translate(t.view_sql, "snowflake", m.functions, n) for n, t in m.tables.items() if t.view_sql]
    assert a == b


# ------------------------------------------------------------------------------------------------------ before / after

def test_the_before_and_after_comparison_on_the_synthetic_rows():
    f = demo.facts()
    e = demo.EXPECTED
    assert f["tables_before"] == e["tables_before"] and f["tables_after"] == e["tables_after"]
    assert f["declared_keys"] == e["declared_keys"] and f["declared_links"] == e["declared_links"]
    assert len(f["differences"]) == e["differences"] and f["verdict"] == "4 difference(s)"
    assert f["rows"]["ORDER_LINES"] == e["rows"]["ORDER_LINES"] and f["rows"]["EVENTS"] == (2, None)
    for k, (b, a) in e["totals"].items():
        assert (float(f["totals"][k][0]), float(f["totals"][k][1])) == (b, a)
    assert f["not_unique"] == e["not_unique"] and f["orphans"] == e["orphans"]
    assert f["fabric_checks"] == "3 of 4 keys unique, 1 of 3 relationships hold without orphans"
    assert "| order_lines | 6 | 5 | yes / yes | no: quantity, line_amount |" in f["report_markdown"]


def test_equal_sides_are_kept_and_the_report_says_counts_are_not_values():
    sp = {"tables": {"t": {"key": ["id"], "amounts": ["x"]}}, "links": []}
    same = {"rows|t": "3", "key_distinct|t": "3", "key_null|t": "0", "sum|t|x": "10.50"}
    c = compare.compare(same, {**same, "sum|t|x": "10.5"}, sp)
    assert c["kept"] and c["differences"] == [] and "do not prove that every value is equal" in c["note"]
    c = compare.compare(same, {**same, "key_distinct|t": "2"}, sp)
    assert c["differences"] == ["t: key (id) duplicates 0 -> 1, NULLs 0 -> 0"]


def test_counting_sql_quotes_per_dialect_and_results_read_from_csv_and_json(tmp_path):
    sp = {"tables": {"orders": {"key": ["order_id"], "amounts": ["total"]}, "customers": {"key": ["id"], "amounts": []}},
          "links": [{"source": "orders", "cols": ["customer_id"], "target": "customers", "target_cols": ["id"]}]}
    names = {"orders": "ORDERS", "orders.order_id": "ORDER_ID", "orders.total": "TOTAL", "orders.customer_id": "CUSTOMER_ID",
             "customers": "CUSTOMERS", "customers.id": "ID"}
    sf = compare.counting_sql(sp, "snowflake", "SALES", names)
    assert '"SALES"."ORDERS"' in sf and "CAST(SUM(\"TOTAL\") AS VARCHAR)" in sf and "'orphans|orders(customer_id)->customers'" in sf
    assert "`sales`.`orders`" in compare.counting_sql(sp, "databricks", "sales")
    assert "[dbo].[orders]" in compare.counting_sql(sp, "tsql", "dbo") and "VARCHAR(100)" in compare.counting_sql(sp, "tsql", "dbo")
    (tmp_path / "r.csv").write_text('"METRIC","VALUE"\nrows|orders,4\nsum|orders|total,\n', encoding="utf-8")
    assert compare.read_results(tmp_path / "r.csv") == {"rows|orders": "4", "sum|orders|total": None}
    (tmp_path / "r.json").write_text(json.dumps([{"metric": "rows|orders", "value": 4}]), encoding="utf-8")
    assert compare.read_results(tmp_path / "r.json") == {"rows|orders": "4"}


# ------------------------------------------------------------------------------------------------------ inputs

def test_cli_plans_writes_the_counting_sql_and_compares(tmp_path, capsys):
    from fabric_backend.cli import main
    assert main(["migrate", str(SF), "--source", "snowflake", "--schema", "SALES", "--counting-sql", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Snowflake schema SALES: 5 table(s), 4 view(s)" in out
    assert "key ORDER_LINES(ORDER_ID, LINE_NO)  [Snowflake metadata]" in out
    assert "EVENTS (table): Lakehouse Delta table; Copy job (Snowflake source" in out
    assert "view V_ORDER_MARGIN: user-defined function MARGIN_PCT (line 2)" in out
    assert (tmp_path / "before_snowflake.sql").read_text(encoding="utf-8").startswith("SELECT 'rows|customers'")
    b, a = tmp_path / "b.csv", tmp_path / "a.csv"
    b.write_text("metric,value\nrows|customers,3\nrows|orders,4\n", encoding="utf-8")
    a.write_text("metric,value\nrows|customers,3\nrows|orders,3\n", encoding="utf-8")
    assert main(["migrate", str(SF), "--source", "snowflake", "--schema", "SALES", "--before", str(b), "--after", str(a),
                 "--report", str(tmp_path / "r.md"), "--json", str(tmp_path / "r.json")]) == 0
    out = capsys.readouterr().out
    assert "orders: rows 4 before, 3 after (-1)" in out and (tmp_path / "r.md").exists()
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["dry_run"] is True
    assert main(["migrate", str(SF), "--source", "snowflake", "--schema", "SALES", "--before", str(b)]) == 2
    assert main(["migrate", str(tmp_path / "nothing"), "--source", "databricks"]) == 2


def test_the_local_mcp_tool_plans_refuses_to_create_and_counts_the_fabric_side(monkeypatch):
    pytest.importorskip("mcp")
    from contextlib import contextmanager
    from fabric_backend import mcp_server
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert "plan_migration" in tools and tools["plan_migration"].annotations.read_only_hint is True
    out = json.loads(mcp_server.plan_migration(str(DB), "databricks"))
    assert out["source"] == "Databricks" and out["dry_run"] is True and "tsql" not in json.dumps(out["views"])
    assert "source_sql" not in out["after_landing"]
    full = json.loads(mcp_server.plan_migration(str(DB), "databricks", detail="full"))
    assert full["after_landing"]["source_sql"].startswith("SELECT 'rows|crm_contacts'")
    refused = json.loads(mcp_server.plan_migration(str(DB), "databricks", dry_run=False))
    assert refused["kind"] == "unsupported" and "creates nothing" in refused["error"]

    con, execute = demo._db(True)
    from fabric_backend.schema import Schema

    @contextmanager
    def fake(schema):
        yield execute
    monkeypatch.setattr(mcp_server, "_connection", fake)
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, ex, schema="dbo", with_keys=True: demo.landed_schema()))
    try:
        out = json.loads(mcp_server.plan_migration(str(SF), "snowflake", "SALES", fabric_schema="SALES"))
    finally:
        con.close()
    assert out["fabric_checks"]["summary"] == "3 of 4 keys unique, 1 of 3 relationships hold without orphans"
    assert out["after_landing"]["not_on_fabric_side"] == ["events"]


def test_nothing_here_connects_or_uses_a_model():
    for f in sorted((ROOT / "fabric_backend" / "migrate").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(requests|httpx|urllib|socket|subprocess|anthropic|openai|snowflake|databricks)\b", src, re.M), f.name
    assert not re.search(r"\bqlik\b", (ROOT / "fabric_backend" / "mcp_server.py").read_text(encoding="utf-8"), re.I)


# ------------------------------------------------------------------------------------------------------ the doc

def test_the_doc_has_the_export_queries_the_pages_and_the_measured_numbers():
    doc = DOC.read_text(encoding="utf-8")
    for q in ("SHOW PRIMARY KEYS IN SCHEMA", "SHOW IMPORTED KEYS IN SCHEMA", "INFORMATION_SCHEMA.TABLES", "INFORMATION_SCHEMA.VIEWS",
              "information_schema.table_constraints", "information_schema.key_column_usage",
              "information_schema.referential_constraints", "information_schema.row_filters", "information_schema.column_masks"):
        assert q in doc, q
    for d in plan.DOCS.values():
        assert d["url"] in doc
    f = demo.facts()
    for line in f["differences"]:
        assert line in doc, line
    assert "## 5. What Krusgraph does not do" in doc and "synthetic" in doc


def test_no_claims_in_the_doc_or_the_code():
    text = DOC.read_text(encoding="utf-8") + "".join(f.read_text(encoding="utf-8") for f in (ROOT / "fabric_backend" / "migrate").glob("*.py"))
    low = text.lower()
    for bad in ("faster", "cheaper", "save money", "cost saving", "cost-saving", "compliant", "compliance", "certified",
                "endorsed", "partner", "official", "guarantee"):
        assert bad not in low, bad
