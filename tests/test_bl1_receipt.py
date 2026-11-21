"""BL1 (21 Nov 2026): a receipt for every number (fabric_backend/receipt.py, `krusgraph receipt`, docs/RECEIPTS.md).

Every statement in a receipt re-runs on the synthetic shop and SAP demo (SQLite) to the counts it states, the receipt
holds no row value, and the command writes the Markdown file.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from fabric_backend import evidence, receipt, sap_demo, seed
from fabric_backend import krusgraph_cli as cli
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local


def _shop():
    src = local.sample_source()
    return src.schema, src.execute


SOURCES = {"shop": _shop, "sap": sap_demo.sqlite}


def _receipt(name: str, dialect="sqlite"):
    schema, execute = SOURCES[name]()
    p = infer_plan(schema)
    v = evidence.validate(p, execute, 200)
    return p, v, execute, receipt.build(p, v, dt.datetime(2026, 11, 21, 10, 0, tzinfo=dt.timezone.utc), dialect=dialect)


def _same(stated, got) -> bool:
    if isinstance(stated, float) or isinstance(got, float):
        return round(float(got or 0), 2) == round(float(stated), 2)
    return int(got or 0) == int(stated)


@pytest.mark.parametrize("name", sorted(SOURCES))
@pytest.mark.parametrize("dialect", ["sqlite", "tsql"])
def test_every_receipt_sql_reruns_to_its_count(name, dialect):
    p, v, execute, rows = _receipt(name, dialect)
    counted = [r for r in rows if r["sql"]]
    assert counted and all(r["dialect"] == dialect for r in rows)
    for r in counted:
        got = execute(r["sql"])[0]
        for k, stated in r["counts"].items():
            assert _same(stated, got.get(k)), (r["item"], k, stated, got.get(k), r["sql"])


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_one_row_per_number_in_validate(name):
    p, v, _, rows = _receipt(name)
    kinds = [r["kind"] for r in rows]
    assert kinds.count("key") == len(v["keys"])
    assert kinds.count("link") + kinds.count("extended link") == len(v["relationships"])
    counted_levels = [f for f in v["amount_levels"]["findings"] if isinstance(f["rows_per_header"], dict)]
    assert kinds.count("amount level") == len(counted_levels)
    assert kinds.count("flat amount") == len(v["amount_levels"].get("flat_tables", []))
    assert [r["n"] for r in rows] == list(range(1, len(rows) + 1))
    assert all(r["generated_at"] == "2026-11-21T10:00:00Z" for r in rows)
    if name == "sap":                                   # the SAP demo has extended links and links with orphans
        assert "extended link" in kinds
        assert any(r["counts"].get("orphans") for r in rows if r["kind"] == "link")


def test_sql_comes_from_evidence_builders():
    p, v, _, rows = _receipt("shop", "tsql")
    k = v["keys"][0]
    assert rows[0]["sql"] == evidence.key_sql(p.schema.schema, k["table"], k["columns"])
    assert "COUNT_BIG" in rows[0]["sql"]
    _, _, _, lite = _receipt("shop", "sqlite")
    assert "COUNT_BIG" not in lite[0]["sql"]


def _cell_values(name: str) -> set[str]:
    if name == "shop":
        data = [r for rs in seed.rows().values() for r in rs]
    else:
        data = [r for _, _, rs in sap_demo.tables().values() for r in rs]
    values = set()
    for row in data:
        for x in row:
            if isinstance(x, (dt.date, dt.datetime)):
                values.add(x.isoformat())
            elif isinstance(x, str) and len(x.strip()) >= 4 and not x.strip().isdigit():
                values.add(x.strip())
            elif isinstance(x, float) and x != int(x):
                values.add(repr(x))
    return values


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_no_receipt_holds_a_row_value(name):
    schema, _ = SOURCES[name]()
    names = {t.lower() for t in schema.tables} | {c.name.lower() for t in schema.tables.values() for c in t.columns}
    p, v, _, rows = _receipt(name)
    text = receipt.markdown(rows, "test") + json.dumps(rows)
    values = {x for x in _cell_values(name) if x.lower() not in names}
    assert values, "the sample should have values to look for"
    leaked = sorted(x for x in values if x in text)
    assert not leaked, leaked


def test_markdown_has_a_section_and_a_fenced_block_per_number():
    _, _, _, rows = _receipt("sap")
    md = receipt.markdown(rows, "sample sap")
    assert md.startswith("# Krusgraph receipt\n")
    assert md.count("\n## ") == len(rows)
    assert md.count("```sql\n") == sum(1 for r in rows if r["sql"])


def test_not_counted_items_have_no_number():
    schema, execute = sap_demo.sqlite()
    p = infer_plan(schema)

    def failing(sql):
        if "sap_vbap" in sql:
            raise RuntimeError("boom")
        return execute(sql)
    failing.dialect = getattr(execute, "dialect", None)
    v = evidence.validate(p, failing, 200)
    assert v.get("not_counted")
    rows = receipt.build(p, v)
    nc = [r for r in rows if r["kind"] == "not counted"]
    assert len(nc) == len(v["not_counted"]) and all(r["sql"] is None and r["counts"] is None for r in nc)
    assert "Not counted, so there is no number" in receipt.markdown(rows)


def test_unknown_dialect_is_refused():
    p, v, _, _ = _receipt("shop")
    with pytest.raises(ValueError):
        receipt.build(p, v, dialect="oracle")


def test_cli_receipt_json(capsys):
    code = cli.main(["receipt", "--sample", "shop", "--json"])
    d = json.loads(capsys.readouterr().out)
    assert code == 0 and d["ok"] and d["command"] == "receipt" and d["read_only"]
    r = d["result"]
    assert r["numbers"] == len([x for x in r["rows"] if x["sql"]]) > 0 and r["not_counted"] == 0
    assert r["markdown"].startswith("# Krusgraph receipt") and all(x["dialect"] == "sqlite" for x in r["rows"])


def test_cli_receipt_human_prints_the_markdown_file(capsys):
    assert cli.main(["receipt", "--sample", "sap", "--human"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Krusgraph receipt")


def test_cli_receipt_needs_rows(capsys, tmp_path):
    cols = tmp_path / "columns.csv"
    cols.write_text("TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,DATA_TYPE,ORDINAL_POSITION\ndbo,t,id,int,1\n", encoding="utf-8")
    assert cli.main(["receipt", "--columns", str(cols), "--json"]) == cli.NEEDS_ROWS
