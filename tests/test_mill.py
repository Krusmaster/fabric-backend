"""n192: the synthetic manufacturing sample 'mill' (fabric_backend/mill.py) beside the shop.

The expected keys, links with their rules and findings are written out here, and the planted problems in
tests/fixtures/mill/planted_issues.json: these are the source of truth. When the engine's answer on the mill changes,
one of these tests says what changed."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from fabric_backend import browser_check as bc, evidence, mill, seed
from fabric_backend.infer import plan

ROOT = Path(__file__).resolve().parents[1]
PLANTED = json.loads((ROOT / "tests/fixtures/mill/planted_issues.json").read_text(encoding="utf-8"))

TABLES = ["customers", "suppliers", "items", "bill_of_materials", "work_centers", "sales_orders", "sales_order_lines",
          "purchase_orders", "purchase_order_lines", "production_orders", "production_operations", "inventory_transactions",
          "deliveries", "item_prices", "stg_supplier_prices", "machine_events"]

KEYS = {
    "customers": (["customer_id"], "K2"), "suppliers": (["supplier_id"], "K2"), "items": (["item_id"], "K2"),
    "bill_of_materials": (["parent_item_id", "component_item_id"], "K4"),           # a junction of two role columns
    "work_centers": (["work_center_code"], "K2"),                                    # a code, not a number
    "sales_orders": (["sales_order_id"], "K2"),
    "sales_order_lines": (["sales_order_id", "line_no"], "K5"),                      # the composite key: order + line
    "purchase_orders": (["purchase_order_id"], "K2"), "purchase_order_lines": (["purchase_order_id", "line_no"], "K5"),
    "production_orders": (["production_order_id"], "K2"), "production_operations": (["production_operation_id"], "K2"),
    "inventory_transactions": (["inventory_transaction_id"], "K2"), "deliveries": (["delivery_id"], "K2"),
    "item_prices": (["item_price_id"], "K2"), "stg_supplier_prices": (["supplier_price_id"], "K2"),   # stg_ is a kind word
}

LINKS = {  # (source, source columns, target, target columns): rule
    ("items", ("supplier_id",), "suppliers", ("supplier_id",)): "R1",
    ("bill_of_materials", ("parent_item_id",), "items", ("item_id",)): "R4",         # role columns
    ("bill_of_materials", ("component_item_id",), "items", ("item_id",)): "R4",
    ("sales_orders", ("bill_to_customer_id",), "customers", ("customer_id",)): "R4",
    ("sales_orders", ("ship_to_customer_id",), "customers", ("customer_id",)): "R4",
    ("sales_order_lines", ("sales_order_id",), "sales_orders", ("sales_order_id",)): "R1",
    ("sales_order_lines", ("item_id",), "items", ("item_id",)): "R1",
    ("purchase_orders", ("supplier_id",), "suppliers", ("supplier_id",)): "R1",
    ("purchase_order_lines", ("purchase_order_id",), "purchase_orders", ("purchase_order_id",)): "R1",
    ("purchase_order_lines", ("item_id",), "items", ("item_id",)): "R1",
    ("production_orders", ("item_id",), "items", ("item_id",)): "R1",
    ("production_orders", ("work_center_code",), "work_centers", ("work_center_code",)): "R1",
    ("production_orders", ("sales_order_id",), "sales_orders", ("sales_order_id",)): "R1",
    ("production_operations", ("production_order_id",), "production_orders", ("production_order_id",)): "R1",
    ("production_operations", ("work_center_code",), "work_centers", ("work_center_code",)): "R1",
    ("inventory_transactions", ("item_id",), "items", ("item_id",)): "R1",
    ("inventory_transactions", ("production_order_id",), "production_orders", ("production_order_id",)): "R1",
    ("inventory_transactions", ("purchase_order_id",), "purchase_orders", ("purchase_order_id",)): "R1",
    ("deliveries", ("sales_order_id",), "sales_orders", ("sales_order_id",)): "R1",
    ("deliveries", ("sales_order_id", "line_no"), "sales_order_lines", ("sales_order_id", "line_no")): "R3",   # to the composite key
    ("item_prices", ("item_id",), "items", ("item_id",)): "R1",
    ("stg_supplier_prices", ("supplier_id",), "suppliers", ("supplier_id",)): "R1",
    ("stg_supplier_prices", ("item_id",), "items", ("item_id",)): "R1",
    ("machine_events", ("work_center_code",), "work_centers", ("work_center_code",)): "R1",
}

# What /check shows on the mill: the planted problems, the keyless event log, and the engine's amount-level warnings
# for items.standard_cost (an item's cost repeated on every line that points at the item: true, and the reason the BOM
# cost roll-up multiplies by quantity instead of summing the cost). Nothing else, and no suggestion.
FINDINGS = sorted([
    ("problem", "key", "Key of stg_supplier_prices is not clean: supplier_price_id"),
    ("warning", "relationship", "sales_order_lines.item_id → items: 2 orphan(s)"),
    ("warning", "relationship", "inventory_transactions.item_id → items: 1 orphan(s)"),
    ("warning", "relationship", "production_operations.work_center_code → work_centers: 1 orphan(s)"),
    ("warning", "amount_level", "items.standard_cost would be summed once per bill_of_materials row"),
    ("warning", "amount_level", "items.standard_cost would be summed once per bill_of_materials row"),
    ("warning", "amount_level", "items.standard_cost would be summed once per production_orders row"),
    ("warning", "amount_level", "items.standard_cost would be summed once per purchase_order_lines row"),
    ("warning", "amount_level", "items.standard_cost would be summed once per sales_order_lines row"),
    ("info", "keyless", "machine_events has no key"),
])


@pytest.fixture(scope="module")
def src():
    s = mill.source()
    yield s
    s.close()


@pytest.fixture(scope="module")
def mill_plan(src):
    return plan(src.schema)


@pytest.fixture(scope="module")
def validation(mill_plan, src):
    return evidence.validate(mill_plan, src.execute)


@pytest.fixture(scope="module")
def checked():
    return bc.analyze("mill")


# ------------------------------------------------------------------ the rows ----------------------------------------

def test_the_same_seed_gives_the_same_rows_and_another_seed_other_rows():
    a, b = mill.rows(), mill.rows()
    assert a == b and list(a) == TABLES == list(mill.SCHEMAS)
    assert mill.rows(8) != a
    assert mill.rows(8)["items"] == a["items"]                    # master data is fixed; only the movements vary


def test_about_fifteen_tables_a_few_thousand_rows_two_years_of_dates():
    r = mill.rows()
    total = sum(len(v) for v in r.values())
    assert len(r) == 16 and 3000 <= total <= 8000, total
    assert {k: len(v) for k, v in r.items()} == {
        "customers": 32, "suppliers": 12, "items": 74, "bill_of_materials": 137, "work_centers": 8, "sales_orders": 200,
        "sales_order_lines": 499, "purchase_orders": 120, "purchase_order_lines": 203, "production_orders": 317,
        "production_operations": 1451, "inventory_transactions": 1158, "deliveries": 496, "item_prices": 36,
        "stg_supplier_prices": 49, "machine_events": 220}
    ahead = {"promised_date", "planned_start", "planned_finish", "expected_date"}   # the open work's dates may lie ahead
    happened, planned = [], []
    for name, rows in r.items():
        cols = [c.split()[0] for c in mill.SCHEMAS[name].split(", ")]
        for row in rows:
            for c, v in zip(cols, row):
                if isinstance(v, dt.date):
                    (planned if c in ahead else happened).append(v.date() if isinstance(v, dt.datetime) else v)
    assert min(happened + planned) >= mill.START and max(happened) <= mill.END and (max(happened) - min(happened)).days >= 700
    assert max(planned) <= mill.END + dt.timedelta(weeks=8)
    for name, rows in r.items():                                  # every row has the columns its DDL says
        assert all(len(row) == len(mill.SCHEMAS[name].split(", ")) for row in rows), name


def test_items_are_finished_goods_parts_and_raw_materials_and_the_bom_has_two_levels():
    r = mill.rows()
    kinds = {i[0]: i[3] for i in r["items"]}
    assert set(kinds.values()) == {"finished good", "part", "raw material"}
    for parent, comp, qty in r["bill_of_materials"]:
        assert qty > 0 and (kinds[parent], kinds[comp]) in {("finished good", "part"), ("finished good", "raw material"), ("part", "raw material")}
    assert len({(p, c) for p, c, _q in r["bill_of_materials"]}) == len(r["bill_of_materials"])   # the K4 key holds


def test_the_rows_hold_exactly_the_planted_problems():
    r = mill.rows()
    items = {i[0] for i in r["items"]}
    wcs = {w[0] for w in r["work_centers"]}
    orphans = {
        ("sales_order_lines", ("item_id",)): [{"sales_order_id": x[0], "line_no": x[1], "item_id": x[2]} for x in r["sales_order_lines"] if x[2] not in items],
        ("inventory_transactions", ("item_id",)): [{"inventory_transaction_id": x[0], "item_id": x[1]} for x in r["inventory_transactions"] if x[1] not in items],
        ("production_operations", ("work_center_code",)): [{"production_operation_id": x[0], "work_center_code": x[3]} for x in r["production_operations"] if x[3] not in wcs],
    }
    assert orphans == {(o["source"], tuple(o["columns"])): o["rows"] for o in PLANTED["orphans"]}
    ids = [x[0] for x in r["stg_supplier_prices"]]
    assert sorted({i for i in ids if ids.count(i) > 1}) == PLANTED["non_unique_keys"][0]["duplicated_values"]
    customers = {c[0] for c in r["customers"]}
    assert all(c[4] in customers for c in r["customers"] if c[4] is not None) and any(c[4] for c in r["customers"])   # the self-reference holds


def test_the_late_deliveries_are_exactly_the_planted_ones():
    r = mill.rows()
    promised = {(x[0], x[1]): x[5] for x in r["sales_order_lines"]}
    late = sorted({(d[1], d[2]) for d in r["deliveries"] if d[4] > promised[(d[1], d[2])]})
    delivered = {(d[1], d[2]) for d in r["deliveries"]}
    planted = PLANTED["late_deliveries"]
    assert [list(x) for x in late] == planted["lines"] and len(delivered) == planted["delivered_lines"]
    assert round(100 * (len(delivered) - len(late)) / len(delivered), 1) == planted["on_time_percent"]


def test_no_vendor_names_in_the_dataset():
    """Plain English names of our own: no ERP vendor's name, and none of the well-known vendor table or column codes."""
    vendors = re.compile(r"\b(monitor|sap|visma|business ?central|navision|dynamics|nav|oracle|netsuite|infor|jeeves|ifs|"
                         r"pyramid|garp|fortnox|odoo|epicor|sage|m3|axapta|ax)\b", re.I)
    codes = re.compile(r"\b(vbak|vbap|likp|lips|mara|marc|ekko|ekpo|afko|afpo|stko|stpo|kna1|lfa1|t001|bkpf|bseg|"
                       r"prodtable|inventtrans|salestable|salesline|purchtable|purchline|bomtable|custtable|vendtable)\b", re.I)
    names = list(mill.SCHEMAS) + [c.split()[0] for cols in mill.SCHEMAS.values() for c in cols.split(", ")]
    values = [str(v) for rows in mill.rows().values() for row in rows for v in row if isinstance(v, str)]
    text = (ROOT / "fabric_backend/mill.py").read_text(encoding="utf-8").split('"""', 2)[2]     # the code, not the docstring that says what it avoids
    for s in names + values + [mill.COMPANY]:
        assert not vendors.search(s) and not codes.search(s), s
    assert not codes.search(text)
    assert "(fictional)" in mill.COMPANY


# ------------------------------------------------------------------ plan and check ----------------------------------

def test_plan_finds_the_expected_keys_and_links(mill_plan):
    assert {t: (list(k), r) for t, (k, r) in mill_plan.keys.items()} == KEYS
    assert mill_plan.keyless == ["machine_events"]
    got = {(x.source, tuple(x.source_cols), x.target, tuple(x.target_cols)): x.rule for x in mill_plan.relationships}
    assert got == LINKS
    assert not mill_plan.ambiguous and not getattr(mill_plan, "proposed", [])


def test_the_self_reference_is_not_linked_by_name(mill_plan):
    """customers.parent_customer_id points at customers itself; the name rules never link a table to itself (infer.py
    skips the own table), so the plan leaves it out. Pinned here, and said in docs/SAMPLE-MILL.md."""
    (gap,) = PLANTED["not_linked_by_the_engine"]
    assert not [x for x in mill_plan.relationships if x.source == gap["source"] and [c.lower() for c in x.source_cols] == gap["columns"]]


def test_validate_counts_exactly_the_planted_problems(validation):
    bad_keys = [(k["table"], k["columns"], k["rows"], k["distinct"]) for k in validation["keys"] if not k["verdict"].startswith("unique")]
    assert bad_keys == [(k["table"], k["columns"], k["rows"], k["distinct"]) for k in PLANTED["non_unique_keys"]]
    bad = sorted((x["source"], x["columns"], x["target"], x["orphans"]) for x in validation["relationships"] if x["orphans"])
    assert bad == sorted((o["source"], o["columns"], o["target"], o["orphans"]) for o in PLANTED["orphans"])
    assert validation["summary"] == "14 of 15 keys unique, 21 of 24 relationships hold without orphans"


def test_check_finds_exactly_the_planted_issues(checked):
    assert checked["verdict"]["headline"]["title"] == "Enough to start"
    assert sorted((f["severity"], f["check"], f["title"]) for f in checked["findings"]) == FINDINGS
    assert checked["suggestions"] == []                            # each table numbers its rows in its own range
    assert checked["coverage"]["complete"] and checked["coverage"]["keys"] == 15 and checked["coverage"]["relationships"] == 24
    assert len(checked["tables"]) == 16 and len(checked["relationships"]) == 24
    planted = {f"{o['source']}.{o['columns'][0]} → {o['target']}: {o['orphans']} orphan(s)" for o in PLANTED["orphans"]} \
        | {f"Key of {k['table']} is not clean: {', '.join(k['columns'])}" for k in PLANTED["non_unique_keys"]} \
        | {f"{k['table']} has no key" for k in PLANTED["keyless"]}
    assert planted == {f["title"] for f in checked["findings"] if f["check"] != "amount_level"}
    assert "synthetic" in checked["source"]["label"].lower()
    assert checked["evidence_report"]["name"] == "mill_evidence_report.md"


# ------------------------------------------------------------------ the seed ----------------------------------------

class _Spark:
    """Enough of a SparkSession for seed(): records the SQL and the tables written."""
    def __init__(self, schemas=("dbo",)):
        self.sql_run, self.saved, self.schemas = [], {}, schemas

    def sql(self, text):
        self.sql_run.append(text)
        rows = [(s,) for s in self.schemas]

        class Result:
            def collect(self):
                return rows
        return Result()

    def createDataFrame(self, data, ddl):
        spark = self

        class Writer:
            def mode(self, _m):
                return self

            def option(self, *_a):
                return self

            def saveAsTable(self, name):
                spark.saved[name] = (ddl, len(data))

        class Frame:
            write = Writer()
        return Frame()


def test_the_seed_writes_the_mill_only_when_asked():
    spark = _Spark()
    counts = seed.seed(spark)                                      # the default: the shop alone
    assert set(spark.saved) == {f"shop.{t}" for t in seed.SCHEMAS} and not any(k.startswith("mill.") for k in counts)
    spark = _Spark()
    counts = seed.seed(spark, mill=True)
    assert {k for k in spark.saved if k.startswith("mill.")} == {f"mill.{t}" for t in TABLES}
    assert "CREATE SCHEMA IF NOT EXISTS mill" in spark.sql_run
    assert counts["mill.sales_orders"] == 200 and counts["orders"] == len(seed.rows()["orders"])
    spark = _Spark(schemas=("default",))                           # a lakehouse without schemas: the mill is not written
    seed.seed(spark, mill=True)
    assert not any(k.startswith("mill.") for k in spark.saved)


# ------------------------------------------------------------------ the docs ----------------------------------------

def test_the_kpi_queries_in_the_docs_run_on_the_sample(src):
    """docs/SAMPLE-MILL.md: on-time delivery, order backlog, inventory value, work center load, BOM cost roll-up. Each
    SQL block runs on the sample and gives rows; on-time delivery agrees with the planted late lines."""
    doc = (ROOT / "docs/SAMPLE-MILL.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\n(.*?)```", doc, re.S)
    assert len(blocks) == 5
    out = [src.execute(sql) for sql in blocks]
    assert all(out), [len(x) for x in out]
    late = PLANTED["late_deliveries"]
    assert out[0] == [{"delivered_lines": late["delivered_lines"], "on_time_lines": late["delivered_lines"] - len(late["lines"])}]
    assert out[1][0]["open_lines"] > 0 and out[1][0]["open_value"] > 0
    assert {r["item_type"] for r in out[2]} == {"finished good", "part", "raw material"}
    assert {r["work_center_code"] for r in out[3]} == {w[0] for w in mill.rows()["work_centers"]}
    finished = {i[0]: i[5] for i in mill.rows()["items"] if i[3] == "finished good"}
    assert {r["top_item_id"] for r in out[4]} == set(finished)
    assert all(0 < r["material_cost"] < finished[r["top_item_id"]] for r in out[4])   # material is part of the standard cost
    for name in ("on-time delivery", "order backlog", "inventory value", "work center load", "bom cost roll-up"):
        assert name in doc.lower(), name
    rows = mill.rows()
    assert f"{sum(len(v) for v in rows.values()):,}".replace(",", " ") in doc
    for t, v in rows.items():
        assert re.search(rf"\| `{t}` \| {f'{len(v):,}'.replace(',', ' ')} \|", doc), t
