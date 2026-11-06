"""Round n138: the MCP Apps cards after the first live run (Claude desktop app, 6 November 2026, demo_lh/shop).

1. review_plan's ER diagram drew edges through other tables (orders.customer_id -> customers ran through the audit_log
   box, as if audit_log were related to orders) and labels on top of each other. The layout is now a layered grid with
   right-angled edges in the gaps between tables (mcp_apps_review.LAYOUT_JS). Checked here geometrically, in SVG
   coordinates, for the shop (7 tables, 7 relationships) and a synthetic 15-table fixture, wide and light, narrow and
   dark: no edge segment enters any table box, every edge starts on its source and ends on its target, no label
   overlaps another label or a table, and every label sits on its own edge.
2. validate_plan's card with nothing to attend to: "Nothing needs attention." under Needs attention, and the result
   sentence once, in the summary line.
3. The buttons: what they send is the standard `tools/call` request of the MCP Apps specification (2026-01-26), only
   to a host whose `ui/initialize` answer has `hostCapabilities.serverTools`; a host without it, a JSON-RPC error, a
   result with isError and a host that does not answer each give a readable sentence on the card.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fabric_backend import mcp_apps, mcp_apps_review, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

ROOT = Path(__file__).resolve().parents[1]
CARDS = {"validate_plan": mcp_apps.card_html, "review_plan": mcp_apps_review.card_html}


def _playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, cwd=ROOT).returncode == 0


needs_browser = pytest.mark.skipif(not _playwright(), reason="node + playwright not available")


@pytest.fixture
def live_shop(fabric, monkeypatch):  # noqa: F811
    """The shop as the live run of 6 November 2026 answered: no header amount finding, so every check passes."""
    from fabric_backend import amounts
    monkeypatch.setattr(amounts, "check", lambda *a, **k: {"findings": []})
    return fabric


# ------------------------------------------------------------------ a 15-table fixture ---------------------------------

# Synthetic: invented names, no data. (table, key, {column: referenced table}); two tables refer to themselves.
FIFTEEN = [
    ("regions", ["region_id"], {}),
    ("countries", ["country_id"], {"region_id": "regions"}),
    ("cities", ["city_id"], {"country_id": "countries"}),
    ("warehouses", ["warehouse_id"], {"city_id": "cities"}),
    ("suppliers", ["supplier_id"], {"city_id": "cities"}),
    ("categories", ["category_id"], {"parent_id": "categories"}),
    ("products", ["product_id"], {"category_id": "categories", "supplier_id": "suppliers"}),
    ("customers", ["customer_id"], {"city_id": "cities"}),
    ("employees", ["employee_id"], {"manager_id": "employees", "warehouse_id": "warehouses"}),
    ("orders", ["order_id"], {"customer_id": "customers", "employee_id": "employees"}),
    ("order_lines", ["order_id", "line_no"], {"order_id": "orders", "product_id": "products"}),
    ("shipments", ["shipment_id"], {"order_id": "orders", "warehouse_id": "warehouses"}),
    ("stock", ["warehouse_id", "product_id"], {"warehouse_id": "warehouses", "product_id": "products"}),
    ("invoices", ["invoice_id"], {"order_id": "orders", "customer_id": "customers"}),
    ("payments", ["payment_id"], {"invoice_id": "invoices"}),
]


def fifteen_answer() -> dict:
    """A review_plan answer for FIFTEEN, in the shape review_plan gives (summary, attention, review, note)."""
    pk = {t: k for t, k, _ in FIFTEEN}
    tables, rels, items = {}, [], []
    for t, key, refs in FIFTEEN:
        cols = {c: "int" for c in key}
        cols.update({c: "int" for c in refs})
        cols.update({"name": "varchar", "created_at": "datetime"})
        tables[t] = {"columns": cols, "key": key, "key_rule": "K2"}
        items.append({"id": f"key:{t}", "type": "key", "table": t, "columns": key, "rule": "K2", "review": "proposed",
                      "reason": "", "check": {"status": "passed", "result": {"rows": 40, "nulls": 0, "distinct": 40},
                                              "verdict": "unique in all 40 rows"}})
        for c, target in refs.items():
            tcol = [k for k in pk[target] if k != "line_no"][:1] if target != t else ["employee_id" if t == "employees" else "category_id"]
            rels.append({"source": t, "columns": [c], "target": target, "target_columns": tcol, "rule": "R1"})
            items.append({"id": f"rel:{t}.{c}>{target}", "type": "relationship", "source": t, "columns": [c],
                          "target": target, "target_columns": tcol, "rule": "R1", "review": "proposed", "reason": "",
                          "check": {"status": "passed", "result": {"rows_with_value": 120, "orphans": 0},
                                    "verdict": "holds for all 120 rows with a value"}})
    summary = f"{len(FIFTEEN)} keys and {len(rels)} relationships: 0 accepted, 0 rejected, 0 open, {len(items)} still proposed"
    return {"summary": summary, "attention": [], "note": "Nothing was created or changed in the source.",
            "review": {"format": "krusgraph-review", "snapshot": {"tables": tables, "relationships": rels},
                       "items": items, "open_questions": []}}


# ------------------------------------------------------------------ the browser ---------------------------------------

def _browse(tmp_path, tool: str, args: dict, result: dict, reply: dict | None = None, width: int = 520,
            scheme: str = "light", mode: str = "tools", shot: str | None = None) -> dict:
    (tmp_path / "card.html").write_text(CARDS[tool]())
    (tmp_path / "input.json").write_text(json.dumps(args))
    (tmp_path / "result.json").write_text(json.dumps(result))
    (tmp_path / "reply.json").write_text(json.dumps(reply or {"content": [{"type": "text", "text": "{}"}]}))
    run = subprocess.run(["node", str(Path(__file__).parent / "mcp_apps_n138_browser.js"),
                          *(str(tmp_path / f) for f in ("card.html", "input.json", "result.json", "reply.json")),
                          str(width), scheme, mode, *([shot] if shot else [])],
                         capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["requests"] == [] and out["errors"] == [] and out["violations"] == []
    return out


def _text(answer: str | dict) -> dict:
    return {"content": [{"type": "text", "text": answer if isinstance(answer, str) else json.dumps(answer)}]}


# ------------------------------------------------------------------ the geometry --------------------------------------

def _inside(seg, box, pad: float = 0.5) -> bool:
    """True when the axis-parallel segment enters the box's interior (touching its border is not entering)."""
    (x1, y1), (x2, y2) = seg
    lx, hx, ly, hy = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
    return lx < box["x"] + box["w"] - pad and hx > box["x"] + pad and ly < box["y"] + box["h"] - pad and hy > box["y"] + pad


def _overlap(a, b) -> bool:
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


def _on_border(p, box) -> bool:
    x, y = p
    within_x, within_y = box["x"] - 0.5 <= x <= box["x"] + box["w"] + 0.5, box["y"] - 0.5 <= y <= box["y"] + box["h"] + 0.5
    return (within_x and (abs(y - box["y"]) < 0.6 or abs(y - box["y"] - box["h"]) < 0.6)) or \
           (within_y and (abs(x - box["x"]) < 0.6 or abs(x - box["x"] - box["w"]) < 0.6))


def check_geometry(d: dict, n_tables: int, n_rels: int) -> dict:
    """The diagram's promises, in SVG coordinates. Returns a few counts for the report."""
    boxes = {t["name"]: t["box"] for t in d["tables"]}
    assert len(boxes) == n_tables and len(d["edges"]) == n_rels and len(d["labels"]) == n_rels
    for a in boxes.values():
        assert 0 <= a["x"] and a["x"] + a["w"] <= d["width"] + 0.5, a                # inside the drawing
    for i, (na, a) in enumerate(boxes.items()):
        for nb, b in list(boxes.items())[i + 1:]:
            assert not _overlap(a, b), (na, nb)
    crossings = 0
    for e in d["edges"]:
        pts = e["points"]
        assert len(pts) >= 2
        assert _on_border(pts[0], boxes[e["source"]]), (e["id"], "starts on its source", pts[0])
        assert _on_border(pts[-1], boxes[e["target"]]), (e["id"], "ends on its target", pts[-1])
        for seg in zip(pts, pts[1:]):
            assert seg[0][0] == seg[1][0] or seg[0][1] == seg[1][1], (e["id"], seg)   # right-angled
            for name, box in boxes.items():
                # no segment crosses a table it does not connect, and none runs through its own two either
                assert not _inside(seg, box), (e["id"], "crosses", name, seg)
    labels = d["labels"]
    by_id = {e["id"]: e for e in d["edges"]}
    for i, lb in enumerate(labels):
        assert 0 <= lb["box"]["x"] and lb["box"]["x"] + lb["box"]["w"] <= d["width"] + 0.5, lb
        for name, box in boxes.items():
            assert not _overlap(lb["box"], box), (lb["for"], "over the table", name)
        for other in labels[i + 1:]:
            assert not _overlap(lb["box"], other["box"]), (lb["for"], "over the label of", other["for"])
        own = by_id[lb["for"]]["points"]                                               # the label is on its own edge
        assert any(_inside(seg, lb["box"], pad=0) for seg in zip(own, own[1:])), lb["for"]
        for e in d["edges"]:
            if e["id"] != lb["for"]:
                crossings += sum(_inside(seg, lb["box"], pad=0) for seg in zip(e["points"], e["points"][1:]))
    return {"lines_under_other_labels": crossings}


def _review_view(tmp_path, answer: dict, args: dict, width: int, scheme: str, name: str) -> dict:
    shot = os.environ.get("KRUSGRAPH_CARD_SHOT")
    out = _browse(tmp_path, "review_plan", args, _text(answer), width=width, scheme=scheme,
                  shot=shot and f"{shot}-n138-{name}-{width}-{scheme}.png")
    v = out["before"]
    assert v["docWidth"] <= v["viewWidth"] and v["diagram"]["svgWidth"] <= v["viewWidth"]   # no sideways scroll
    if scheme == "dark":
        assert v["background"] != "rgb(255, 255, 255)"
    return v


@needs_browser
@pytest.mark.parametrize("width,scheme", [(520, "light"), (340, "dark"), (900, "light")])
def test_the_shop_diagram_routes_around_tables(tmp_path, live_shop, width, scheme):
    args = {**SRC, "validate": True}
    answer = json.loads(server.review_plan(**args))
    v = _review_view(tmp_path, answer, args, width, scheme, "shop")
    d = v["diagram"]
    counts = check_geometry(d, 7, 7)
    if width >= 520:                                         # room enough: no line runs under another edge's label
        assert counts["lines_under_other_labels"] == 0, counts
    boxes = {t["name"]: t["box"] for t in d["tables"]}
    # referenced tables above the ones that refer to them
    for e in d["edges"]:
        assert boxes[e["target"]]["y"] < boxes[e["source"]]["y"], e["id"]
    # the live complaint: orders -> customers does not touch audit_log
    [oc] = [e for e in d["edges"] if e["id"] == "rel:orders.customer_id>customers"]
    for seg in zip(oc["points"], oc["points"][1:]):
        assert not _inside(seg, boxes["audit_log"], pad=-4)                            # not even close to it


@needs_browser
@pytest.mark.parametrize("width,scheme", [(520, "light"), (340, "dark"), (900, "dark")])
def test_a_fifteen_table_diagram_stays_readable(tmp_path, width, scheme):
    answer = fifteen_answer()
    v = _review_view(tmp_path, answer, {"workspace": "w", "source": "s", "schema": "fifteen"}, width, scheme, "fifteen")
    rels = answer["review"]["snapshot"]["relationships"]
    check_geometry(v["diagram"], 15, len(rels))
    boxes = {t["name"]: t["box"] for t in v["diagram"]["tables"]}
    for r in rels:
        if r["source"] != r["target"]:
            assert boxes[r["target"]]["y"] < boxes[r["source"]]["y"], r


def test_the_layout_is_inline_and_loads_nothing():
    html = mcp_apps_review.card_html()
    assert "function erLayout(spec)" in html and "__LAYOUT_JS__" not in html
    for bad in ("<script src", "href=", "url(", "@import", "fetch(", "XMLHttpRequest", "<img"):
        assert bad not in mcp_apps_review.LAYOUT_JS


# ------------------------------------------------------------------ nothing needs attention ---------------------------

@needs_browser
def test_nothing_needs_attention_is_one_short_line(tmp_path, live_shop):
    data = json.loads(server.validate_plan(**SRC))
    assert "attention" not in data and data["result"].startswith("All 13 counted checks passed")
    v = _browse(tmp_path, "validate_plan", SRC, _text(data))["before"]
    assert v["attentionShown"] and v["attention"] == [] and v["attentionNone"] == ["Nothing needs attention."]
    assert v["verdict"] == data["summary"] and v["result"] == [". " + data["result"]]   # the summary line
    assert v["text"].count(data["result"]) == 1                                         # said once, there
    after = [ln for ln in v["text"].split("Needs attention\n")[-1].split("\n") if ln.strip()]
    assert after[0] == "Nothing needs attention."                                       # the section's only line


@needs_browser
def test_attention_lines_when_something_needs_it(tmp_path, fabric):  # noqa: F811
    data = json.loads(server.validate_plan(**SRC))                                     # the shop's header amount
    v = _browse(tmp_path, "validate_plan", SRC, _text(data))["before"]
    assert len(v["attention"]) == 1 and v["attentionNone"] == [] and v["result"] == []


# ------------------------------------------------------------------ the buttons ---------------------------------------

def _spec_call(m: dict, tool: str):
    """The view's tools/call as the specification has it: a JSON-RPC 2.0 request with params {name, arguments}."""
    assert set(m) == {"jsonrpc", "id", "method", "params"}, m
    assert m["jsonrpc"] == "2.0" and m["method"] == "tools/call"
    assert isinstance(m["id"], (int, str)) and not isinstance(m["id"], bool)
    assert set(m["params"]) == {"name", "arguments"} and m["params"]["name"] == tool
    assert isinstance(m["params"]["arguments"], dict)
    json.dumps(m)                                                                       # plain JSON, nothing else


def _validate_case(fabric):  # noqa: F811
    return "validate_plan", SRC, _text(server.validate_plan(**SRC)), "semantic_model_draft"


def _review_case(fabric):  # noqa: F811
    args = {**SRC, "validate": True}
    return "review_plan", args, _text(server.review_plan(**args)), "review_plan"


CASES = {"validate_plan": _validate_case, "review_plan": _review_case}


@needs_browser
@pytest.mark.parametrize("tool", sorted(CASES))
def test_the_buttons_send_the_spec_request(tmp_path, live_shop, tool):
    card, args, result, called = CASES[tool](live_shop)
    out = _browse(tmp_path, card, args, result, reply=result)
    init = [m for m in out["log"] if m.get("method") == "ui/initialize"]
    assert len(init) == 1 and init[0]["params"]["protocolVersion"] == mcp_apps.PROTOCOL_VERSION
    calls = [m for m in out["log"] if m.get("method") == "tools/call"]
    assert len(calls) == 1
    _spec_call(calls[0], called)
    a = calls[0]["params"]["arguments"]
    assert {k: a[k] for k in ("workspace", "source", "schema")} == SRC
    if tool == "review_plan":
        assert set(a) <= set(mcp_apps_review.CARRIED) | {"previous", "decisions"} and len(a["decisions"]) == 1
    else:
        assert set(a) <= set(mcp_apps.CARRIED[called])


@needs_browser
@pytest.mark.parametrize("tool", sorted(CASES))
def test_a_host_without_server_tools_gets_a_note_and_no_request(tmp_path, live_shop, tool):
    card, args, result, called = CASES[tool](live_shop)
    out = _browse(tmp_path, card, args, result, mode="none")
    assert not [m for m in out["log"] if m.get("method") == "tools/call"]              # not asked at all
    note = (out["after"]["outputs"] + out["after"]["call"])[0]
    assert note.startswith("This host does not run tools from the card. Ask in the chat instead: “")
    assert called in note and not note.lstrip().startswith(("{", "["))


@needs_browser
@pytest.mark.parametrize("tool", sorted(CASES))
@pytest.mark.parametrize("mode,start", [("error", "This host does not run tools from the card."),
                                        ("iserror", "{tool} answered with an error: workspace not found."),
                                        ("silent", "No answer from the host yet; it may be asking you first.")])
def test_a_refusal_an_error_or_silence_reads_as_a_sentence(tmp_path, live_shop, tool, mode, start):
    card, args, result, called = CASES[tool](live_shop)
    out = _browse(tmp_path, card, args, result, mode=mode)
    [call] = [m for m in out["log"] if m.get("method") == "tools/call"]
    _spec_call(call, called)
    note = (out["after"]["outputs"] + out["after"]["call"])[0]
    assert note.startswith(start.format(tool=called)), note


def test_the_call_helper_is_in_both_cards():
    for html in (mcp_apps.card_html(), mcp_apps_review.card_html()):
        assert "function callTool(" in html and "hostCapabilities" in html and "serverTools" in html
        assert html.count('request("tools/call"') == 1                                 # one way to call, the helper


# ------------------------------------------------------------------ what a button's tool answered ---------------------

def _row_values() -> set[str]:
    """Every text value in the synthetic shop's rows (names, cities, categories, events): none may be on a summary."""
    from fabric_backend import seed
    return {v for rows in seed.rows().values() for row in rows for v in row if isinstance(v, str) and len(v) > 3}


def _sdk(answer: str) -> dict:
    """A str tool's answer as the SDK sends it, the shape seen live: text content plus {"result": text}."""
    return {"content": [{"type": "text", "text": answer}], "structuredContent": {"result": answer}}


@needs_browser
def test_draft_answers_as_short_summaries_with_details_closed(tmp_path, live_shop):
    v = json.loads(server.validate_plan(**SRC))
    assert [s["tool"] for s in v["next_steps"]] == ["semantic_model_draft", "ontology_draft"]
    smd_text, ont_text = server.semantic_model_draft(**SRC), server.ontology_draft(**SRC)
    smd, ont = json.loads(smd_text), json.loads(ont_text)
    # the live shapes the summaries read
    assert set(smd) >= {"parts", "summary", "note"} and smd["summary"]["tables"] == 7
    assert (smd["summary"]["relationships_active"], smd["summary"]["relationships_inactive"]) == (6, 1)
    assert set(ont) >= {"summary", "bindings", "ttl", "definition_parts"} and ont["summary"]["entity_types"] == 7
    assert ont["summary"]["with_key"] == 5 and ont["summary"]["relationship_types"] == 7 and len(ont["summary"]["notes"]) == 2

    shot = os.environ.get("KRUSGRAPH_CARD_SHOT")
    out = _browse(tmp_path, "validate_plan", SRC, _text(json.dumps(v)), mode="bytool",
                  reply={"semantic_model_draft": _sdk(smd_text), "ontology_draft": _sdk(ont_text)},
                  shot=shot and f"{shot}-n138-results.png")
    calls = [m for m in out["log"] if m.get("method") == "tools/call"]
    assert [c["params"]["name"] for c in calls] == ["semantic_model_draft", "ontology_draft"]
    first, second = out["after"]["results"]

    s = smd["summary"]
    measures = list(dict.fromkeys(f"{m['name']} ({m['table']})" for m in s["measures"] + s["order_amount"]["measures"]))
    assert first["lines"][:3] == [
        "Tables: 7 (dimension: customers, categories, products, addresses; fact: orders, order_items, audit_log)",
        "Relationships: 6 active, 1 inactive",
        f"Measures: {len(measures)}: " + ", ".join(measures),                     # one line per measure, no repeats
    ]
    notes = [ln for ln in first["lines"] if ln.startswith("Note: ")]
    assert "Note: No key: audit_log." in notes and "Note: Composite key: order_items." in notes
    assert any(n.startswith("Note: Inactive: orders.ship_to_id → addresses: it would close a cycle") for n in notes)
    assert f"Note: {smd['note']}" in notes and first["questions"] == []

    assert second["lines"][0] == "Entity types: 7, 5 with a key"
    entities = [ln for ln in second["lines"] if ln.startswith("Entity: ")]
    assert len(entities) == 7 and "Entity: Customers: key customer_id" in entities
    assert "Entity: OrderItems: no single key (order_id + line_no)" in entities and "Entity: AuditLog: no key" in entities
    assert any(ln.startswith("Relationship types: 7: ") and "OrderItems → Orders (OrderItemsHasOrders)" in ln for ln in second["lines"])
    assert second["questions"] == [["Which one property should be the key of OrderItems?", ont["summary"]["notes"][0]],
                                   ["Does AuditLog have a key?", ont["summary"]["notes"][1]]]

    for res, answer in ((first, smd), (second, ont)):
        d = res["details"]
        assert d["summary"] == "Show details" and not d["open"] and not d["preShown"]   # collapsed
        assert json.loads(d["text"]) == answer                                          # the whole answer, behind it
        assert "Show details" in res["visible"] and "{" not in res["visible"].replace("Show details", "")
        for marker in ("lineageTag", "tmdl", "@prefix", "compatibilityLevel"):
            assert marker not in res["visible"], marker                                 # no raw parts on the card
        for value in _row_values():
            assert value not in res["visible"], value                                   # no row values


@needs_browser
def test_any_other_tool_shows_its_summary_field(tmp_path, live_shop):
    v = json.loads(server.validate_plan(**SRC))
    v["next_steps"] = [{"tool": "suggest_relationships", "arguments": {}, "why": "find links the plan lacks."}]
    answer = {"summary": "2 candidate columns, 1 checked against the data", "candidates": [{"column": "x"}]}
    out = _browse(tmp_path, "validate_plan", SRC, _text(v), mode="bytool",
                  reply={"suggest_relationships": _text(answer)})
    [res] = out["after"]["results"]
    assert res["lines"] == ["Summary: 2 candidate columns, 1 checked against the data"] and res["questions"] == []
    assert json.loads(res["details"]["text"]) == answer and not res["details"]["open"]


@needs_browser
def test_review_card_shows_an_answer_without_a_review_as_a_summary(tmp_path, live_shop):
    args = {**SRC, "validate": True}
    answer = server.review_plan(**args)
    refusal = {"error": "previous does not belong to this source.", "hint": "Call review_plan without previous."}
    out = _browse(tmp_path, "review_plan", args, _text(answer), reply=_text(refusal))
    assert out["after"]["call"] == ["review_plan answered without a review file."]
    [res] = out["after"]["results"]
    assert res["lines"] == ["Error: previous does not belong to this source. Call review_plan without previous."]
    assert json.loads(res["details"]["text"]) == refusal and not res["details"]["open"]
