"""n228: Krusgraph's diagrams as draw.io files (fabric_backend/drawio.py). The founder, 12 November 2026, looking at the
semantic model draft card in claude.ai: "can I see this as a draw.io file/flow if I want?"

What is checked, on the synthetic shop and on the synthetic SAP-shaped demo in a schema named dbo:
- every export is XML, a well-formed mxfile (the root and the layer first, unique ids, every edge between cells that
  exist), holds every table and every link, and is byte for byte the golden file in tests/golden/drawio/
  (regenerate with KRUSGRAPH_UPDATE_GOLDEN=1, as tests/test_golden.py does);
- no two boxes overlap and no edge passes through a box, also for 60 and for 200 tables; the checker itself is shown to
  see a planted overlap and a planted edge through a box;
- the semantic model draft: fact and dimension colours, R5's orders.ship_to_id -> addresses dashed and inactive, a
  composite-key relationship dotted red with its reason, the Calendar table, the measures in the fact boxes;
- names are escaped; ids are stable; two exports are the same text;
- plan_backend(drawio=...) answers the file read-only and the listing keeps its tool count; POST /workload/v1/drawio
  makes the editor's file from what the editor sends and calls nothing in Fabric.

Not checked here: opening the files in draw.io itself. The structure is the documented uncompressed mxfile; the first
opening in app.diagrams.net is the founder's.
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import golden_support as gs  # noqa: E402
from fabric_backend import data_flow, demo, drawio, sap_demo, seed, semantic_model  # noqa: E402
from fabric_backend.infer import plan  # noqa: E402
from fabric_backend.schema import Column, Schema, Table  # noqa: E402
from test_golden import fabric  # noqa: E402,F401  (the hosted server against the workspace answered from memory)
from test_workload_api import _post, api, keys, tok  # noqa: E402,F401

GOLDEN = Path(__file__).parent / "golden" / "drawio"
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"
SAP_INFO = {**demo.FLOW_INFO, "schema": "dbo"}


def _shop():
    db = gs.shop_database()

    def execute(sql):
        cur = db.execute(gs._sqlite(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return plan(seed.schema("shop"), execute=execute)                 # with the rows: R5 finds orders.ship_to_id -> addresses


def _sap():
    schema, execute = sap_demo.sqlite(schema="dbo")
    return plan(schema, execute=execute)


def _files() -> dict[str, tuple[str, object]]:
    shop, sap = _shop(), _sap()
    shop_map, sap_map = drawio.map_data(shop), drawio.map_data(sap)
    return {
        "shop-map": (drawio.map_file(shop_map, "demo_lh.shop: the map"), shop),
        "shop-semantic-model": (drawio.model_file(drawio.model_data(
            shop_map, semantic_model.draft(shop, demo.FLOW_INFO, "shop_model"), "shop_model"), "shop_model"), shop),
        "shop-data-flow": (drawio.flow_file(drawio.source_flow(shop, demo.FLOW_INFO), "demo_lh.shop: the data flow"), shop),
        "sap-dbo-map": (drawio.map_file(sap_map, "demo_lh.dbo: the map"), sap),
        "sap-dbo-semantic-model": (drawio.model_file(drawio.model_data(
            sap_map, semantic_model.draft(sap, SAP_INFO, "sap_model", combined=False), "sap_model"), "sap_model"), sap),
        "sap-dbo-data-flow": (drawio.flow_file(drawio.source_flow(sap, SAP_INFO), "demo_lh.dbo: the data flow"), sap),
    }


FILES = _files()


def _cells(text: str) -> dict[str, dict]:
    """id -> {label, style, edge, vertex, source, target} of a file."""
    out = {}
    for el in ET.fromstring(text).find("./diagram/mxGraphModel/root"):
        cell = el if el.tag == "mxCell" else el.find("mxCell")
        out[el.get("id")] = {"label": el.get("value") if el.tag == "mxCell" else el.get("label"), "style": cell.get("style") or "",
                             "edge": cell.get("edge") == "1", "vertex": cell.get("vertex") == "1",
                             "source": cell.get("source"), "target": cell.get("target"), "tooltip": el.get("tooltip")}
    return out


@pytest.mark.parametrize("name", sorted(FILES))
def test_an_export_is_a_valid_mxfile_without_overlaps_and_matches_its_golden_file(name):
    text, _ = FILES[name]
    root = ET.fromstring(text)                                        # parses as XML
    assert root.tag == "mxfile" and root.get("host") == "Krusgraph" and not root.get("compressed")
    diagrams = root.findall("diagram")
    assert len(diagrams) == 1 and diagrams[0].get("id") in drawio.DIAGRAMS and diagrams[0].get("name")
    model = diagrams[0].find("mxGraphModel")
    cells = list(model.find("root"))
    assert [c.get("id") for c in cells[:2]] == ["0", "1"] and cells[1].get("parent") == "0"
    assert drawio.problems(text) == []                                # ids, edges' ends, no overlap, no edge through a box
    assert text.count("\n") == len(cells) + 8                         # one cell a line: a changed plan is a small diff
    path = GOLDEN / f"{name}.drawio"
    if UPDATE:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"no golden file {path.name}: run with KRUSGRAPH_UPDATE_GOLDEN=1 once"
    assert text == path.read_text(encoding="utf-8"), f"{path.name} differs from the golden file"


@pytest.mark.parametrize("name", ["shop-map", "sap-dbo-map"])
def test_the_map_has_every_table_with_its_key_and_every_link_with_its_rule(name):
    text, p = FILES[name]
    cells = _cells(text)
    for t in p.schema:
        box = cells[drawio.cell_id("table", t.name)]
        key, rule = p.keys.get(t.name, ([], None))
        assert box["vertex"] and f"<b>{t.name}</b>" in box["label"]
        if key:
            assert f"key: {' + '.join(key)} ({p.label(rule)})" in box["label"] and "dashed=1" not in box["style"]
        else:
            assert "<br>no key<br>" in box["label"] and "dashed=1" in box["style"]
    for r in p.relationships:
        e = cells[drawio.cell_id("link", r.source, "+".join(r.source_cols), r.target)]
        assert e["edge"] and e["source"] == drawio.cell_id("table", r.source) and e["target"] == drawio.cell_id("table", r.target)
        assert e["label"] == f"{'+'.join(r.source_cols)} · {p.label(r.rule)}"
    assert drawio.counts(text) == (len(p.schema), len(p.relationships))


def test_the_shop_map_shows_the_rules_no_key_and_the_composite_key():
    cells = _cells(FILES["shop-map"][0])
    assert "<br>no key<br>" in cells["table-audit_log"]["label"]
    assert "key: order_id + line_no (K5)" in cells["table-order_items"]["label"]
    assert cells["link-orders-customer_id-customers"]["label"] == "customer_id · R1"
    assert cells["link-orders-ship_to_id-addresses"]["label"] == "ship_to_id · R5"
    sap = _cells(FILES["sap-dbo-map"][0])
    labels = {c["label"] for c in sap.values() if c["edge"]}
    assert labels and all(x.endswith(" · SAP pack") for x in labels)
    assert "key: MANDT + VBELN (SAP pack)" in sap["table-sap_vbak"]["label"]


def test_the_semantic_model_draft_of_the_shop():
    text, p = FILES["shop-semantic-model"]
    cells = _cells(text)
    draft = semantic_model.draft(p, demo.FLOW_INFO, "shop_model")
    fact, dim = drawio.COLOURS["fact"][0], drawio.COLOURS["dimension"][0]
    for t, role in draft["summary"]["roles"].items():
        box = cells[drawio.cell_id("table", t)]
        assert f"<i>{role} · " in box["label"]
        assert (f"fillColor={fact};" in box["style"]) == (role == "fact") and (f"fillColor={dim};" in box["style"]) == (role == "dimension")
    assert fact != dim
    for m in draft["summary"]["measures"]:                            # the measures, in their table's box
        assert f"{m['name']} = " in cells[drawio.cell_id("table", m["table"])]["label"]
    assert "Total quantity = SUM(&#x27;order_items&#x27;[quantity])" in cells["table-order_items"]["label"] \
        or "Total quantity = SUM('order_items'[quantity])" in cells["table-order_items"]["label"]
    # R5's orders.ship_to_id -> addresses is inactive: dashed, said on the arrow and with its reason in the notes
    r5 = cells["rel-orders-ship_to_id-addresses"]
    assert "dashed=1" in r5["style"] and "dashPattern" not in r5["style"] and r5["label"].endswith("· R5 · inactive")
    why = next(x["why"] for x in draft["summary"]["inactive"] if x["columns"] == ["ship_to_id"])
    assert why in r5["tooltip"] and f"Inactive: orders.ship_to_id -&gt; addresses.address_id: {why}" in cells["semantic_model-notes"]["label"]
    active = cells["rel-orders-customer_id-customers"]
    assert "dashed" not in active["style"] and active["label"] == "customer_id · * : 1 · R1"
    assert "startArrow=ERmany" in active["style"] and "endArrow=ERone" in active["style"]      # many to one
    # the date table, with the fact's date column related to it
    cal = cells["table-Calendar"]
    assert "date table" in cal["label"] and f"fillColor={drawio.COLOURS['date'][0]};" in cal["style"]
    assert cells["rel-orders-order_date-Calendar"]["target"] == "table-Calendar"
    # the picture is the file: as many relationships as relationships.tmdl holds
    n_tmdl = draft["parts"]["definition/relationships.tmdl"].count("\nrelationship ") + 1
    assert drawio.counts(text) == (len(draft["summary"]["roles"]) + 1, n_tmdl)


def test_a_relationship_a_tabular_model_cannot_express_is_dotted_red_with_the_reason():
    text, p = FILES["sap-dbo-semantic-model"]
    cells = _cells(text)
    summary = semantic_model.draft(p, SAP_INFO, "sap_model", combined=False)["summary"]
    assert summary["not_expressible"]
    for x in summary["not_expressible"]:
        e = cells[drawio.cell_id("rel", x["source"], "+".join(x["columns"]), x["target"])]
        assert "dashPattern=1 4" in e["style"] and f"strokeColor={drawio.RED}" in e["style"]
        assert "not in the model: " in e["label"] and x["why"].rstrip(".") in e["tooltip"]
    vbap = cells[drawio.cell_id("rel", "sap_vbap", "MANDT+VBELN", "sap_vbak")]
    assert vbap["label"].endswith("· SAP pack · not in the model: composite key")
    notes = cells["semantic_model-notes"]["label"]
    first = summary["not_expressible"][0]
    assert (f"Not in the model: {first['source']}.{'+'.join(first['columns'])} -&gt; {first['target']}.{'+'.join(first['target_columns'])}: "
            in notes)
    more = len(summary["not_expressible"]) - drawio.MAX_NOTES
    assert more > 0 and f"And {more} more: hover over an arrow to read its reason." in notes


def test_the_data_flow_has_data_flow_pys_nodes_and_edges_left_to_right():
    text, p = FILES["shop-data-flow"]
    cells = _cells(text)
    flow = drawio.source_flow(p, demo.FLOW_INFO)
    assert flow["nodes"][:-1] == data_flow.flow(p, demo.FLOW_INFO, {"silver_notebook": "silver_shop", "gold_views": "gold_shop",
                                                                    "semantic_model": "demo_lh_model"}, items=[
        {"output": o, "label": label, "name": n.format(item="demo_lh"), "reads": "reads the source tables in shop (bronze) directly"}
        for o, label, n in drawio.BUILT_ON_SOURCE] + [{"output": "report", "label": "Report", "name": "demo_lh_report",
                                                      "on_model": "item:semantic_model", "reads": "on demo_lh_model"}])["nodes"]
    x = {}
    for el in ET.fromstring(text).find("./diagram/mxGraphModel/root"):
        g = (el if el.tag == "mxCell" else el.find("mxCell")).find("mxGeometry")
        if g is not None and g.get("x") and g.get("width"):
            x[el.get("id")] = float(g.get("x"))
    for n in flow["nodes"]:
        assert f"<b>{n['label']}</b>" in cells[drawio.cell_id("flow", n["id"])]["label"]
    for e in flow["edges"]:                                           # every arrow, and it points to the right
        a, b = drawio.cell_id("flow", e["from"]), drawio.cell_id("flow", e["to"])
        assert any(c["edge"] and c["source"] == a and c["target"] == b for c in cells.values()), (e["from"], e["to"])
        assert x[a] < x[b]
    gold = next(n["id"] for n in flow["nodes"] if n["column"] == "gold")
    order = [x[drawio.cell_id("flow", i)] for i in ("bronze:orders", "silver:orders", gold, "item:semantic_model", "item:report")]
    assert order == sorted(order) and len(set(order)) == 5            # bronze -> silver -> gold -> model -> report
    assert x[drawio.cell_id("flow", "item:graphql")] < x[drawio.cell_id("flow", "item:app")]
    for wanted in ("item:ontology", "item:data_agent"):
        assert drawio.cell_id("flow", wanted) in cells
    assert sum(1 for c in cells.values() if c["edge"]) == len(flow["edges"])


# ------------------------------------------------------------------------------------------------- at size ----

def _synthetic(n: int) -> Schema:
    """n tables: hubs, tables that point at up to three earlier ones (some far back, so edges pass columns), a
    self-reference, and tables nothing links."""
    s = Schema(schema="big")
    for i in range(n):
        cols = [Column(f"t{i:03d}_id", "int")]
        if i % 9 != 8:                                                # every ninth table links nothing
            for back in (1, 7, 31):
                if i - back >= 0 and (i - back) % 9 != 8 and (back == 1 or i % back == 0 or i % 5 == 0):
                    cols.append(Column(f"t{i - back:03d}_id", "int"))
            if i % 11 == 0:
                cols.append(Column(f"parent_t{i:03d}_id", "int"))
        cols.append(Column("name", "varchar"))
        s.tables[f"t{i:03d}"] = Table(f"t{i:03d}", cols, schema="big")
    return s


@pytest.mark.parametrize("n", [60, 200])
def test_a_large_schema_exports_without_overlaps_and_without_an_edge_through_a_box(n):
    p = plan(_synthetic(n))
    assert len(p.schema) == n and len(p.relationships) > n
    text = drawio.map_file(drawio.map_data(p), f"{n} tables")
    assert drawio.problems(text) == []
    assert drawio.counts(text) == (n, len(p.relationships))
    draft = semantic_model.draft(p, {**demo.FLOW_INFO, "schema": "big"}, "big_model")
    model = drawio.model_file(drawio.model_data(drawio.map_data(p), draft, "big_model"))
    assert drawio.problems(model) == []
    assert drawio.problems(drawio.flow_file(drawio.source_flow(p, {**demo.FLOW_INFO, "schema": "big"}))) == []


def test_the_checker_sees_a_planted_overlap_and_a_planted_edge_through_a_box():
    text = FILES["shop-map"][0]
    assert drawio.problems("<mxfile><diagram/></mxfile>") and drawio.problems("not xml")[0].startswith("not XML")
    root = ET.fromstring(text)
    cells = {el.get("id"): el for el in root.find("./diagram/mxGraphModel/root")}
    a, b = cells["table-orders"].find("mxGeometry"), cells["table-customers"].find("mxGeometry")
    was = (b.get("x"), b.get("y"))
    b.set("x", a.get("x"))
    b.set("y", a.get("y"))
    assert any("overlap" in x and "table-orders" in x for x in drawio.problems(ET.tostring(root, encoding="unicode")))
    b.set("x", was[0])
    b.set("y", was[1])
    box = lambda i, x: (f'<mxCell id="{i}" value="{i}" style="rounded=1;" vertex="1" parent="1">'
                        f'<mxGeometry x="{x}" y="0" width="100" height="60" as="geometry"/></mxCell>')
    edge = lambda style: (f'<mxCell id="e" value="" style="{style}" edge="1" parent="1" source="a" target="c">'
                          '<mxGeometry relative="1" as="geometry"/></mxCell>')
    file = lambda style: ('<mxfile><diagram id="map" name="Map"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                          + box("a", 0) + box("b", 200) + box("c", 400) + edge(style) + "</root></mxGraphModel></diagram></mxfile>")
    straight = "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
    assert drawio.problems(file(straight)) == ["the edge e passes through the box b"]
    assert drawio.problems(file("")) == ["e: no exit or entry point"]
    assert drawio.problems(file(straight).replace('target="c"', 'target="z"')) == ["e: joins a cell that is not a box in the file"]
    assert drawio.problems(file(straight).replace('id="b"', 'id="a"'))[0].startswith("the id 'a' is used more than once")


# ---------------------------------------------------------------------------------- names, ids, determinism ----

def test_names_are_escaped_and_the_file_still_parses():
    s = Schema(schema="odd")
    names = ['a<b>&"c"', "it's <script>alert(1)</script>", "tab\x01le", "Ünïcode ✓", "x" * 150]
    for i, n in enumerate(names):
        cols = [Column("id", "int"), Column('we"ird<col>&', "int")] + ([Column(f'{names[0]}_id', "int")] if i else [])
        s.tables[n] = Table(n, cols, schema="odd")
    p = plan(s, keys={n: ["id"] for n in names}, confirmed=[
        {"source": names[1], "source_cols": ['we"ird<col>&'], "target": names[0], "target_cols": ["id"]}])
    text = drawio.map_file(drawio.map_data(p), 'odd & "quoted" <title>')
    assert drawio.problems(text) == [] and drawio.counts(text)[0] == len(names)
    assert "<script>" not in text and "\x01" not in text
    cells = _cells(text)                                              # parsed back: the label is HTML with the name escaped once
    assert "<b>a&lt;b&gt;&amp;\"c\"</b>" in cells[drawio.cell_id("table", names[0])]["label"]
    assert "<b>it's &lt;script&gt;alert(1)&lt;/script&gt;</b>" in cells[drawio.cell_id("table", names[1])]["label"]
    assert "tab�le" in cells[drawio.cell_id("table", names[2])]["label"]
    assert len({drawio.cell_id("table", n) for n in names}) == len(names)
    link = next(c for c in cells.values() if c["edge"])
    assert link["label"].startswith("we\"ird&lt;col&gt;&amp; · ")
    assert drawio.filename('demo lh/../<x>', "semantic_model") == "demo-lh-..-x-semantic-model.drawio"


def test_two_exports_are_the_same_text_and_ids_do_not_move_when_a_table_is_added():
    again = _files()
    assert {k: v[0] for k, v in again.items()} == {k: v[0] for k, v in FILES.items()}
    s = seed.schema("shop")
    s.tables["returns"] = Table("returns", [Column("return_id", "int"), Column("order_id", "int")], schema="shop")
    more = _cells(drawio.map_file(drawio.map_data(plan(s)), "demo_lh.shop: the map"))
    before = _cells(drawio.map_file(drawio.map_data(plan(seed.schema("shop"))), "demo_lh.shop: the map"))
    assert set(before) < set(more) and set(more) - set(before) == {"table-returns", "link-returns-order_id-orders"}
    assert drawio.cell_id("table", "Orders") != drawio.cell_id("table", "orders")
    assert drawio.cell_id("table", "a b") != drawio.cell_id("table", "a-b") != drawio.cell_id("table", "a_b")


def test_the_module_uses_the_standard_library_only():
    import ast
    tree = ast.parse(Path(drawio.__file__).read_text(encoding="utf-8"))
    tops = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert tops <= {"hashlib", "html", "math", "re", "xml", "json"}
    assert all(n.level == 1 for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module != "__future__")


# ----------------------------------------------------------------------------------------- the tool, the route ----

SRC = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}


@pytest.mark.parametrize("which, diagram, boxes", [("map", "map", 7), ("model", "semantic_model", 8), ("flow", "data_flow", None)])
def test_plan_backend_answers_the_diagram_as_a_file_and_writes_nothing(fabric, which, diagram, boxes):  # noqa: F811
    from fabric_backend import server
    out = json.loads(server.plan_backend(**SRC, drawio=which))
    assert out["format"] == "drawio" and out["diagram"] == diagram and out["mime_type"] == drawio.MIME
    assert out["filename"] == f"demo_lh.shop-{diagram.replace('_', '-')}.drawio" and out["boxes"] == (boxes or out["boxes"])
    assert out["boxes"] >= 7 and out["arrows"] >= 7
    assert "problems" not in out and drawio.problems(out["content"]) == []
    assert "Nothing was written to Fabric" in out["how"] and out["changes"].startswith("nothing")
    assert all(c[0] == "GET" for c in fabric.calls) and not fabric.created and not fabric.odbc.ddl      # read-only
    for t in seed.SCHEMAS:
        assert f"<b>{t}</b>" in json.dumps(_cells(out["content"])) or f"shop.{t}" in out["content"]


def test_plan_backend_without_drawio_answers_as_before_and_a_wrong_value_is_an_input_error(fabric):  # noqa: F811
    from fabric_backend import server
    assert json.loads(server.plan_backend(**SRC)) == json.loads(server.plan_backend(**SRC, drawio=""))
    err = json.loads(server.plan_backend(**SRC, drawio="visio"))
    assert err["kind"] == "bad_input" and 'drawio: "map", "model" or "flow"' in err["error"]
    part = json.loads(server.plan_backend(**SRC, drawio="map", tables=["order*"]))
    assert part["boxes"] == 2 and part["arrows"] == 1


def test_a_file_over_the_answers_limit_is_left_out_with_how_to_get_a_part():
    p = plan(_synthetic(200))
    out = drawio.export("map", p, None, "big.big", None, 60000)
    assert "content" not in out and "tables=[...]" in out["too_large"] and out["boxes"] == 200
    assert "content" in drawio.export("map", p, None, "big.big", {f"t{i:03d}" for i in range(20)}, 60000)


def test_the_listing_keeps_its_tool_count_and_plan_backend_describes_the_parameter():
    import asyncio
    from fabric_backend import server
    tools = asyncio.run(server.mcp.list_tools())
    assert len(tools) == 42 and sum(1 for t in tools if t.annotations.read_only_hint) == 31      # no tool added by n228 (n229 added verify_build, CA1 publish_catalog)
    prop = next(t for t in tools if t.name == "plan_backend").input_schema["properties"]["drawio"]
    assert prop["default"] == "" and "draw.io file" in prop["description"]
    assert not any("drawio" in t.input_schema.get("properties", {}) for t in tools if t.name != "plan_backend")


def test_the_editors_route_makes_the_file_from_what_it_is_sent_and_calls_nothing(api):  # noqa: F811
    client, fake, obo, priv = api
    p = _shop()
    sent_map = {"tables": [{"name": t["name"], "key": t["key"], "key_rule": t["key_rule"], "columns": t["columns"], "review": "accepted"}
                           for t in drawio.map_data(p)["tables"]],
                "relationships": [{**r, "state": "passed"} for r in drawio.map_data(p)["relationships"]], "checked": True}
    r = _post(client, "/drawio", {"diagram": "map", "map": sent_map, "name": "demo_lh.shop"}, tok(priv))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["filename"] == "demo_lh.shop-map.drawio" and (out["boxes"], out["arrows"]) == (7, 7)
    assert drawio.problems(out["content"]) == [] and "customer_id · R1 · passed" in out["content"]
    flow = drawio.source_flow(p, demo.FLOW_INFO)
    r = _post(client, "/drawio", {"diagram": "data_flow", "flow": {k: flow[k] for k in ("columns", "nodes", "edges", "notes", "said")},
                                  "name": "demo_lh.shop"}, tok(priv))
    assert r.status_code == 200 and r.json()["content"] == drawio.flow_file(flow, "demo_lh.shop: the data flow")
    assert fake.calls == [] and obo.calls == []                       # nothing read in Fabric, nothing written, no token asked for
    for bad in ({"diagram": "visio"}, {"diagram": "map"}, {"diagram": "map", "map": {"tables": [{"key": []}]}},
                {"diagram": "data_flow", "flow": {"nodes": "x"}}):
        assert _post(client, "/drawio", bad, tok(priv)).status_code == 400
    assert _post(client, "/drawio", {"diagram": "map", "map": sent_map}, None).status_code == 401
