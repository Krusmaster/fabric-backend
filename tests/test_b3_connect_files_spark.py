"""B3 (15 November 2026, backlog I-02): the file route's load notebook runs for real on a local Spark session.

Synthetic files only, written here from the mill sample's rows (fabric_backend/mill.py, an invented company). Skipped when
PySpark is not installed; CI's `notebooks` job installs it and runs this file:

    python -m pytest -q --noconftest tests/test_b3_connect_files_spark.py

Delta is not available in a local Spark, so TABLE_FORMAT is parquet here; Fabric keeps "delta". Not run in Fabric.
Only pure modules are imported (no MCP server)."""
import csv
import datetime
import json
import os

import pytest

from fabric_backend import connect_files as cf
from fabric_backend import mill

pytest.importorskip("pyspark")

TABLES = ["customers", "items", "sales_orders", "stg_supplier_prices"]
ROWS = mill.rows()
SECRET = "Ystervik-row-value-9431"          # a value planted in a refused file: it must never reach the summary


def names(table):
    return [c.split()[0] for c in mill.SCHEMAS[table].split(", ")]


def text(v):
    if v is None:
        return ""
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v.isoformat() if isinstance(v, datetime.date) else str(v)


def write_csv(root, entity, file_name, rows, header=None, delimiter=",", encoding="utf-8", mtime=None):
    folder = root / entity
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f, delimiter=delimiter)
        w.writerow(header or names(entity))
        w.writerows([[text(v) for v in r] for r in rows])
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    from pyspark.sql import SparkSession
    base = tmp_path_factory.mktemp("b3-spark")
    s = (SparkSession.builder.master("local[1]").appName("krusgraph-connect-files-test")
         .config("spark.sql.warehouse.dir", str(base / "warehouse")).config("spark.ui.enabled", "false")
         .config("spark.sql.shuffle.partitions", "2").config("spark.sql.session.timeZone", "UTC").getOrCreate())
    yield s
    s.stop()


def run(spark, spec, root, bronze, extra="", capture=None):
    """Run the notebook's code cells as a pipeline would, with the parameters cell overridden."""
    ns = {"spark": spark}
    if capture is not None:
        ns["print"] = lambda *a, **k: capture.append(" ".join(map(str, a)))
    for kind, code in cf.cells(spec):
        if kind == "markdown":
            continue
        exec(compile(code, "<notebook>", "exec"), ns)
        if kind == "parameters":
            exec(f'TABLE_FORMAT = "parquet"; CONNECT_FOLDER = {str(root)!r}; BRONZE_SCHEMA = {bronze!r}; LOCAL_FILES_ROOT = ""; ' + extra, ns)
    return ns["RESULT"]["entities"]


def test_the_mill_files_load_with_their_types_and_no_file_is_loaded_twice(spark, tmp_path):
    root = tmp_path / "connect"
    for i, t in enumerate(TABLES):
        write_csv(root, t, f"{t}_1.csv", ROWS[t], mtime=1_790_000_000 + i)
    spec = cf.spec(mill.schema(), tables=TABLES + ["suppliers"])
    out = run(spark, spec, root, "b3a")
    for t in TABLES:
        assert out[t]["loaded"] == [{"file": f"{t}_1.csv", "rows": len(ROWS[t])}], t
        assert out[t]["bronze_rows"] == len(ROWS[t]) and not out[t]["refused"] and not out[t]["skipped"]
        got = {f.name: f.dataType.simpleString() for f in spark.read.table(f"b3a.{t}").schema.fields}
        assert got == {c.split()[0]: c.split()[1].lower() for c in mill.SCHEMAS[t].split(", ")}, t
    assert out["customers"]["newest_file"] == "2026-09-21T14:13:20Z"            # 1 790 000 000 s, the file's own time in UTC
    assert out["suppliers"] == {"files_found": 0, "loaded": [], "skipped": [], "refused": [], "rows_loaded": 0, "newest_file": None,
                                "folder": f"{root}/suppliers does not exist yet", "bronze_rows": 0}
    # the rows are the files' rows: keys, a sum, a date and a timestamp, and the empty parent id stays NULL
    items = spark.read.table("b3a.items")
    assert sorted(r[0] for r in items.select("item_id").collect()) == sorted(r[0] for r in ROWS["items"])
    assert items.groupBy().sum("standard_cost").collect()[0][0] == pytest.approx(sum(r[5] for r in ROWS["items"]))
    orders = {r["sales_order_id"]: r["order_date"] for r in spark.read.table("b3a.sales_orders").collect()}
    assert orders == {r[0]: r[1] for r in ROWS["sales_orders"]}
    loaded_at = {r["supplier_price_id"]: r["loaded_at"] for r in spark.read.table("b3a.stg_supplier_prices").collect()}
    assert loaded_at[ROWS["stg_supplier_prices"][0][0]] == ROWS["stg_supplier_prices"][0][4].replace(microsecond=0)
    assert spark.read.table("b3a.customers").filter("parent_customer_id is null").count() == sum(r[4] is None for r in ROWS["customers"])

    # a second run loads nothing; a new file is the only one loaded; freshness follows the newest file
    again = run(spark, spec, root, "b3a")
    for t in TABLES:
        assert again[t]["loaded"] == [] and again[t]["skipped"] == [{"file": f"{t}_1.csv", "why": "loaded before"}]
        assert again[t]["bronze_rows"] == len(ROWS[t])
    more = [(9001, "Nytt Verkstad AB (invented)", "SE", "Gävle", None), (9002, "Annan Kund (invented)", "NO", "Bergen", 9001)]
    write_csv(root, "customers", "customers_2.csv", more, mtime=1_790_100_000)
    third = run(spark, spec, root, "b3a")
    assert third["customers"]["loaded"] == [{"file": "customers_2.csv", "rows": 2}]
    assert third["customers"]["bronze_rows"] == len(ROWS["customers"]) + 2 and third["customers"]["files_found"] == 2
    assert third["customers"]["newest_file"] == "2026-09-22T18:00:00Z"

    # a loaded file that is changed afterwards is not loaded again, and the summary says so
    write_csv(root, "customers", "customers_2.csv", more + [(9003, "En till (invented)", "SE", "Umeå", None)], mtime=1_790_200_000)
    fourth = run(spark, spec, root, "b3a")
    assert fourth["customers"]["loaded"] == [] and fourth["customers"]["bronze_rows"] == len(ROWS["customers"]) + 2
    assert {"file": "customers_2.csv", "why": "loaded before; the file has changed since and was not loaded again "
            "(give a corrected file a new name)"} in fourth["customers"]["skipped"]

    # the record: one 'started' and one 'loaded' line per loaded file, with the rows, and nothing else
    state = spark.read.table(f"b3a.{cf.STATE}").collect()
    assert sorted((r["entity"], r["file_name"], r["status"], r["rows"]) for r in state if r["entity"] == "customers") == [
        ("customers", "customers_1.csv", "loaded", len(ROWS["customers"])), ("customers", "customers_1.csv", "started", None),
        ("customers", "customers_2.csv", "loaded", 2), ("customers", "customers_2.csv", "started", None)]


def test_a_bad_file_is_refused_whole_with_counts_and_never_with_values(spark, tmp_path):
    root = tmp_path / "connect"
    cols = names("customers")
    write_csv(root, "customers", "a_missing.csv", [(1, "x", "SE")], header=cols[:3], mtime=1_790_000_001)
    write_csv(root, "customers", "b_bad.csv", [(1, SECRET, "SE", "Uppsala", "not-a-number"), (SECRET, "y", "SE", "Lund", ""),
                                               (3, "z", "SE", "Lund", "7")], mtime=1_790_000_002)
    ragged = root / "customers" / "c_ragged.csv"
    ragged.write_text(",".join(cols) + "\n1,x,SE,Lund,\n2,y,SE\n", encoding="utf-8")
    os.utime(ragged, (1_790_000_003, 1_790_000_003))
    (root / "customers" / "d_notes.txt").write_text(SECRET, encoding="utf-8")
    write_csv(root, "customers", "e_good.csv", [(5, "ok", "SE", "Lund", None, "ignored")], header=[c.upper() for c in cols] + ["Extra"],
              mtime=1_790_000_005)
    spec = cf.spec(mill.schema(), tables=["customers"])
    printed = []
    out = run(spark, spec, root, "b3b", capture=printed)["customers"]
    assert out["refused"] == [
        {"file": "a_missing.csv", "why": "missing column(s): city, parent_customer_id"},
        {"file": "b_bad.csv", "why": "value(s) that are not of the column's type: customer_id (1), parent_customer_id (1)"},
        {"file": "c_ragged.csv", "why": "a row has a different number of fields than the header"}]
    assert out["skipped"] == [{"file": "d_notes.txt", "why": "not read: not a .csv or .xlsx file"}]
    assert out["loaded"] == [{"file": "e_good.csv", "rows": 1}] and out["bronze_rows"] == 1      # header matched whatever its case
    assert out["columns_ignored"] == {"e_good.csv": ["extra"]}
    assert SECRET not in "\n".join(printed) and json.loads("\n".join(printed))["entities"]["customers"] == out
    assert not [r for r in spark.read.table(f"b3b.{cf.STATE}").collect() if SECRET in str(r)]

    # a refused file corrected under the same name is loaded by the next run; ON_BAD_VALUE = "null" loads and counts
    write_csv(root, "customers", "a_missing.csv", [(1, "x", "SE", "Lund", None)], mtime=1_790_000_010)
    out = run(spark, spec, root, "b3b", extra='ON_BAD_VALUE = "null"')["customers"]
    assert {"file": "a_missing.csv", "rows": 1} in out["loaded"]
    assert {"file": "b_bad.csv", "rows": 3, "values_left_empty": {"customer_id": 1, "parent_customer_id": 1}} in out["loaded"]
    assert out["bronze_rows"] == 5
    assert spark.read.table("b3b.customers").filter("customer_id is null").count() == 1


def test_semicolons_decimal_commas_day_first_dates_and_a_byte_order_mark(spark, tmp_path):
    root = tmp_path / "connect"
    folder = root / "items"
    folder.mkdir(parents=True)
    body = ("item_id;item_number;name;item_type;unit;standard_cost;supplier_id\n"
            "1;A-1;Plåt 2 mm;raw;kg;1 234,5;7\n"
            '2;A-2;"Bult; M8";part;st;0,25;\n')
    (folder / "items.csv").write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    (root / "sales_orders").mkdir()
    (root / "sales_orders" / "so.csv").write_text("sales_order_id;order_date;bill_to_customer_id;ship_to_customer_id;status\n"
                                                  "10;15.11.2026;1;1;open\n", encoding="utf-8")
    spec = cf.spec(mill.schema(), tables=["items", "sales_orders"])
    out = run(spark, spec, root, "b3c", extra='DELIMITER = ";"; DECIMAL_COMMA = True; DATE_FORMAT = "dd.MM.yyyy"')
    assert out["items"]["refused"] == [] and out["items"]["loaded"] == [{"file": "items.csv", "rows": 2}]
    got = {r["item_id"]: (r["name"], r["standard_cost"], r["supplier_id"]) for r in spark.read.table("b3c.items").collect()}
    assert got == {1: ("Plåt 2 mm", 1234.5, 7), 2: ("Bult; M8", 0.25, None)}
    assert spark.read.table("b3c.sales_orders").collect()[0]["order_date"] == datetime.date(2026, 11, 15)
    # without the setting, 1 234,5 is not a number: the file is refused, not half read
    out = run(spark, spec, root, "b3c2", extra='DELIMITER = ";"; DATE_FORMAT = "dd.MM.yyyy"')
    assert out["items"]["refused"] == [{"file": "items.csv", "why": "value(s) that are not of the column's type: standard_cost (2)"}]
    assert out["items"]["bronze_rows"] == 0


def test_a_stopped_run_needs_a_person_and_someone_elses_table_is_never_written(spark, tmp_path):
    root = tmp_path / "connect"
    write_csv(root, "customers", "c1.csv", ROWS["customers"][:3], mtime=1_790_000_001)
    spec = cf.spec(mill.schema(), tables=["customers"])
    spark.sql("CREATE SCHEMA IF NOT EXISTS b3d")
    state = spark.createDataFrame([("customers", "c1.csv", datetime.datetime(2026, 9, 22, 2, 13, 21), 1, "started", None,
                                    datetime.datetime(2026, 11, 15, 8, 0, 0))],
                                  "entity string, file_name string, file_modified timestamp, file_bytes long, status string, rows long, at timestamp")
    state.write.format("parquet").saveAsTable(f"b3d.{cf.STATE}")
    spark.sql(f"ALTER TABLE b3d.{cf.STATE} SET TBLPROPERTIES ('krusgraph.connect' = '{spec['owner']}')")
    out = run(spark, spec, root, "b3d")["customers"]
    assert out["loaded"] == [] and out["bronze_rows"] == 0
    assert out["skipped"] == [{"file": "c1.csv", "why": "a run stopped while loading this file; a person must check `b3d`.`customers` "
                               "before it is loaded again"}]

    spark.sql("CREATE SCHEMA IF NOT EXISTS b3e")
    spark.createDataFrame([(1,)], "x int").write.format("parquet").saveAsTable("b3e.customers")
    with pytest.raises(ValueError, match="was not written by this notebook"):
        run(spark, spec, root, "b3e")
    assert spark.read.table("b3e.customers").count() == 1 and not spark.catalog.tableExists(f"b3e.{cf.STATE}")
    # a lakehouse without schemas: the prefix form
    out = run(spark, cf.spec(mill.schema(), tables=["customers"], schemas_enabled=False), root, "b3f")["customers"]
    assert out["bronze_rows"] == 3 and spark.read.table("b3f_customers").count() == 3


def test_an_excel_workbook_is_read_from_its_first_sheet(spark, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    pytest.importorskip("pandas")
    root = tmp_path / "connect"
    (root / "sales_orders").mkdir(parents=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(names("sales_orders"))
    ws.append([10, datetime.date(2026, 11, 15), 1, 2, "open"])
    ws.append([11, datetime.datetime(2026, 11, 16), 1, None, "closed"])
    wb.create_sheet("notes").append(["not read"])
    wb.save(root / "sales_orders" / "orders.xlsx")
    spec = cf.spec(mill.schema(), tables=["sales_orders"])
    out = run(spark, spec, root, "b3g")["sales_orders"]
    assert out["refused"] == [] and out["loaded"] == [{"file": "orders.xlsx", "rows": 2}]
    got = {r["sales_order_id"]: (r["order_date"], r["ship_to_customer_id"], r["status"]) for r in spark.read.table("b3g.sales_orders").collect()}
    assert got == {10: (datetime.date(2026, 11, 15), 2, "open"), 11: (datetime.date(2026, 11, 16), None, "closed")}
    out = run(spark, spec, root, "b3h", extra="READ_EXCEL = False")["sales_orders"]
    assert out["skipped"] == [{"file": "orders.xlsx", "why": "not read: READ_EXCEL is False"}] and out["bronze_rows"] == 0
