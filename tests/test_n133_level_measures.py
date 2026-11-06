"""Round n133: suggested measures that sum at the right level, in semantic_model_draft's TMDL (fabric_backend/level_measures.py).

A header amount a join repeats over lines gets a measure at header level; a header amount repeated in a flat table gets
one when amount_levels counted it; a true line amount keeps its plain sum and gets neither. The TMDL is read back with
the reader the repo uses (model_compare.from_tmdl) and every reference resolved with the n126 scanner (dax_refs). All
rows are synthetic."""
from __future__ import annotations

import contextlib
import json

from fabric_backend import dax_refs, evidence, mcp_server, model_compare, seed, semantic_model
from fabric_backend.infer import plan
from test_amounts import demo_schema
from test_n106_flat_amounts import _flat
from test_tmdl_documents import check_document


def _by_name(d: dict) -> dict[str, dict]:
    return {m["name"]: m for m in d["summary"]["measures"]}


def _summarize(d: dict, table: str, column: str) -> str:
    block = d["parts"][f"definition/tables/{table}.tmdl"].split(f"\tcolumn {column}\n", 1)[1]
    return block.split("summarizeBy: ", 1)[1].split()[0]


def _flat_draft():
    p, ex = _flat()
    return semantic_model.draft(p, {"schema": "x"}, validation=evidence.validate(p, ex))


def _parses_and_resolves(d: dict) -> dax_refs.Model:
    for path, text in d["parts"].items():
        if path.endswith(".tmdl"):
            check_document(path, text)
    shape = model_compare.from_tmdl(d["parts"])
    for m in d["summary"]["measures"]:
        assert m["name"] in shape["tables"][m["table"]]["measures"], m["name"]
    model = dax_refs.Model(d["parts"])
    for m in d["summary"]["measures"]:
        r = model.refs[("measure", m["table"], m["name"])]
        assert r["unread"] == [] and not r["anywhere"] and not r["ambiguous"], (m["name"], r["unread"])
    return model


def test_a_header_amount_a_join_repeats_gets_a_header_level_measure_and_the_line_amount_does_not():
    d = semantic_model.draft(plan(demo_schema()), {"schema": "demo"})
    by = _by_name(d)
    m = by["Total order_amount by order_lines"]
    assert m["table"] == "orders"
    assert m["expression"] == "CALCULATE(SUM('orders'[order_amount]), TREATAS(VALUES('order_lines'[order_id]), 'orders'[order_id]))"
    assert "once per orders row" in m["why"] and "count each orders once per line" in m["why"]
    assert by["Total order_amount"]["expression"] == "SUM('orders'[order_amount])"          # the amount from the header table
    line = [x for x in d["summary"]["measures"] if "line_amount" in x["expression"]]
    assert [x["expression"] for x in line] == ["SUM('order_lines'[line_amount])"]           # a true line amount: its own sum only
    assert _summarize(d, "orders", "order_amount") == "none" and _summarize(d, "order_lines", "line_amount") == "sum"
    tmdl = d["parts"]["definition/tables/orders.tmdl"]
    assert "\t/// Suggested by Krusgraph: sums orders.order_amount at the level of orders" in tmdl
    model = _parses_and_resolves(d)
    r = model.refs[("measure", "orders", "Total order_amount by order_lines")]
    assert r["columns"] == {("orders", "order_amount"), ("orders", "order_id"), ("order_lines", "order_id")}


def test_a_flat_header_amount_gets_a_measure_once_per_header_value_and_the_line_amount_does_not():
    d = _flat_draft()
    by = _by_name(d)
    assert set(by) == {"Total line_amount", "Total order_amount once per order_id"}
    assert by["Total order_amount once per order_id"]["expression"] == \
        "SUMX(VALUES('order_lines'[order_id]), CALCULATE(MAX('order_lines'[order_amount])))"
    assert by["Total line_amount"]["expression"] == "SUM('order_lines'[line_amount])"
    assert "counts each order_id once per row" in by["Total order_amount once per order_id"]["why"]
    assert _summarize(d, "order_lines", "order_amount") == "none" and _summarize(d, "order_lines", "line_amount") == "sum"
    assert d["summary"]["flat_amounts"] == [{"table": "order_lines", "column": "order_amount", "header": "order_id", "summarize_by": "none"}]
    model = _parses_and_resolves(d)
    r = model.refs[("measure", "order_lines", "Total order_amount once per order_id")]
    assert r["columns"] == {("order_lines", "order_id"), ("order_lines", "order_amount")}


def test_without_counts_the_flat_table_gets_plain_sums_only():
    p, _ = _flat()
    d = semantic_model.draft(p, {"schema": "x"})
    assert sorted(m["expression"] for m in d["summary"]["measures"]) == \
        ["SUM('order_lines'[line_amount])", "SUM('order_lines'[order_amount])"]
    assert "flat_amounts" not in d["summary"]
    _parses_and_resolves(d)


def test_measures_are_marked_as_suggestions_and_the_shop_parses_and_resolves():
    d = semantic_model.draft(plan(seed.schema()), {"schema": "shop"})
    _parses_and_resolves(d)
    for t in d["parts"]:
        if t.startswith("definition/tables/"):
            lines = d["parts"][t].splitlines()
            for i, line in enumerate(lines):
                if line.startswith("\tmeasure "):
                    assert lines[i - 1].startswith("\t/// Suggested by Krusgraph: "), (t, line)


def test_deterministic():
    assert json.dumps(_flat_draft(), sort_keys=True) == json.dumps(_flat_draft(), sort_keys=True)
    one = semantic_model.draft(plan(demo_schema()), {"schema": "demo"})
    assert json.dumps(one, sort_keys=True) == json.dumps(semantic_model.draft(plan(demo_schema()), {"schema": "demo"}), sort_keys=True)


def test_the_local_tool_counts_with_validate_and_reads_metadata_only_without(monkeypatch):
    p, ex = _flat()

    @contextlib.contextmanager
    def connection(schema):
        yield ex
    monkeypatch.setattr(mcp_server, "_connection", connection)
    monkeypatch.setattr(mcp_server, "_plan_on", lambda execute, schema, keys=None, confirmed=None: p)
    monkeypatch.setattr(mcp_server, "_plan", lambda schema, keys=None, confirmed=None: p)
    monkeypatch.setattr(mcp_server, "_fabric_only", lambda tool, schema: None)
    before = len(ex.sent)
    out = json.loads(mcp_server.semantic_model_draft(schema="x"))
    assert len(ex.sent) == before and "flat_amounts" not in out["summary"]
    out = json.loads(mcp_server.semantic_model_draft(schema="x", validate=True))
    assert len(ex.sent) > before
    assert out["summary"]["flat_amounts"][0]["column"] == "order_amount"


def test_the_hosted_tool_counts_with_validate(monkeypatch):
    from fabric_backend import server
    p, ex = _flat()
    info = {"schema": "x", "item_kind": "Lakehouse"}
    monkeypatch.setattr(server, "_source_inputs", lambda *a: (p, info))
    monkeypatch.setattr(server, "_connected", lambda *a: (p.schema, ex))
    out = json.loads(server.semantic_model_draft("ws", "src", schema="x"))
    assert "flat_amounts" not in out["summary"]
    out = json.loads(server.semantic_model_draft("ws", "src", schema="x", validate=True))
    assert out["summary"]["flat_amounts"][0]["column"] == "order_amount"
    assert "SUMX(VALUES('order_lines'[order_id]), CALCULATE(MAX('order_lines'[order_amount])))" in \
        out["parts"]["definition/tables/order_lines.tmdl"]
