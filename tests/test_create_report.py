"""create_report (round n64): a Power BI report bound to a semantic model, with the REST calls mocked the way
test_creating_tools.py mocks create_semantic_model: the dry run, 201, 202 with a long-running operation, 403 as a
missing scope, a report of that name already there, a model that is not, and tools/list.

Round n144: the default page is drawn from the model's own measures and columns (report.definition_parts, PBIR). The
model is semantic_model_draft's shop_model, read back with model_compare.from_tmdl as the tool reads getDefinition.
Checked here: every part parses and has the shape of the Microsoft schemas report.py cites (required fields, no
top-level field the schemas leave out), every visual names a measure or column the model has, no visual draws a
header amount over lines (amount_levels, n106), the same model gives the same parts, and empty_page=true keeps the
blank page of n64.

Round n151: every part with a `$schema` is validated against that schema, copied from microsoft/json-schemas eecc60d
into tests/fixtures/pbir_schemas (jsonschema, Draft 7, the `$ref`s resolved to those files); the theme under
StaticResources has no published per-file schema in the PBIR definition structure and is checked in
tests/test_n151_report_look.py."""
import asyncio
import importlib
import json
from pathlib import Path

import pytest
import requests

from fabric_backend import evidence, model_compare, report, seed, semantic_model, server
from fabric_backend.deploy import FABRIC
from fabric_backend.errors import HINTS
from fabric_backend.infer import plan

deploy = importlib.import_module("fabric_backend.deploy")     # the package exports a function of that name
WS = "11111111-1111-1111-1111-111111111111"
MODEL_ID = "22222222-2222-2222-2222-222222222222"
SHOP_PARTS = semantic_model.draft(plan(seed.schema()), {"schema": "shop"}, "shop_model")["parts"]
ITEMS = {"value": [{"id": MODEL_ID, "displayName": "shop_model", "type": "SemanticModel"},
                   {"id": "rp-0", "displayName": "old_report", "type": "Report"}]}


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture
def fabric(monkeypatch):
    """Fabric answered from memory: the item list for the lookups, and whatever `post` is set to for the create."""
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(deploy.time, "sleep", lambda s: None)
    gets, posts = [], []

    def get(url, **k):
        gets.append(url)
        if "/operations/" in url:
            return next(state["polls"])
        return Resp(200, state["after"] if posts and "after" in state else ITEMS)     # the item list once the create has run

    state = {"polls": iter([]), "post": lambda url, json, **k: Resp(500), "tmdl": SHOP_PARTS, "reads": []}

    def read(workspace, route, item_id, headers, fmt=None):
        state["reads"].append((workspace, route, item_id, fmt))
        if isinstance(state["tmdl"], Exception):
            raise state["tmdl"]
        return state["tmdl"]
    monkeypatch.setattr(server, "_item_definition_parts", read)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", lambda url, **k: posts.append((url, k.get("json"))) or state["post"](url, k.get("json")))
    state["gets"], state["posts"] = gets, posts
    return state


def test_payload_has_the_model_reference_and_no_definition():
    body = report.payload("shop_report", MODEL_ID, WS, "x" * 300)
    assert body["displayName"] == "shop_report" and "definition" not in body and len(body["description"]) == 256
    assert body["creationPayload"] == {"semanticModelReference": {"referenceType": "ById", "itemId": MODEL_ID, "workspaceId": WS}}
    assert "description" not in report.payload("r", MODEL_ID, WS)


def test_empty_page_dry_run_shows_the_call_and_posts_nothing(fabric):
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", empty_page=True))
    assert out["dry_run"] is True and fabric["posts"] == [] and "error" not in out
    assert out["rest"]["method"] == "POST" and out["rest"]["url"] == f"{FABRIC}/v1/workspaces/{WS}/reports"
    assert out["rest"]["body"]["creationPayload"]["semanticModelReference"] == {"referenceType": "ById", "itemId": MODEL_ID, "workspaceId": WS}
    assert "definition" not in out["rest"]["body"] and out["rest"]["delegated_scope"] == "Report.ReadWrite.All or Item.ReadWrite.All"
    assert out["report"]["pages"] == 1 and out["report"]["visuals"] == [] and out["report"]["bound_to"] == {"semantic_model": "shop_model", "id": MODEL_ID}
    assert "blank page" in out["report"]["empty"] and any("Power BI Desktop" in s for s in out["after_creation"])
    assert "Fabric portal" in out["after_creation"][0] and "On 30 October 2026 it created the report shop_report_live live" in out["note"]
    assert fabric["reads"] == [] and "parts" not in out                     # the empty page reads nothing of the model


def test_model_given_as_an_id_is_used_as_is(fabric):
    out = json.loads(server.create_report("Sales", MODEL_ID, "shop_report", empty_page=True))
    assert out["report"]["bound_to"]["id"] == MODEL_ID and out["rest"]["body"]["creationPayload"]["semanticModelReference"]["itemId"] == MODEL_ID
    out = json.loads(server.create_report("Sales", MODEL_ID, "shop_report"))
    pbir = json.loads(out["parts"]["definition.pbir"])
    assert pbir["datasetReference"] == {"byConnection": {"connectionString": f"semanticmodelid={MODEL_ID}"}}
    assert fabric["reads"] == [(WS, "semanticModels", MODEL_ID, "TMDL")] and fabric["posts"] == []


@pytest.mark.parametrize("empty", [False, True])
def test_201_creates_once_and_returns_the_id(fabric, empty):
    fabric["post"] = lambda url, json: Resp(201, {"id": "rp-1", "displayName": "shop_report", "type": "Report", "workspaceId": WS})
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", empty_page=empty, dry_run=False))
    assert out["result"] == {"status": "Succeeded", "mode": "created", "id": "rp-1"} and "error" not in out
    url, body = fabric["posts"][0]
    assert url == f"{FABRIC}/v1/workspaces/{WS}/reports" and body["displayName"] == "shop_report"
    if empty:
        assert "definition" not in body and "creationPayload" in body
    else:
        assert "creationPayload" not in body and {p["payloadType"] for p in body["definition"]["parts"]} == {"InlineBase64"}
        paths = {p["path"] for p in body["definition"]["parts"]}
        assert {"definition.pbir", "definition/version.json", "definition/report.json", "definition/pages/pages.json"} <= paths
        assert sum(p.endswith("/visual.json") for p in paths) == len(out["report"]["visuals"]) == 10
        assert "StaticResources/RegisteredResources/Krusgraph.json" in paths
    assert len(fabric["posts"]) == 1 and not any("updateDefinition" in u for u in fabric["gets"])
    assert "fabric-token" not in json.dumps(out)


def test_202_waits_for_the_operation_then_finds_the_id(fabric):
    fabric["post"] = lambda url, json: Resp(202, None, {"x-ms-operation-id": "op-1"})
    fabric["polls"] = iter([Resp(200, {"status": "Running"}), Resp(200, {"status": "Succeeded"})])
    fabric["after"] = {"value": ITEMS["value"] + [{"id": "rp-2", "displayName": "shop_report", "type": "Report"}]}
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["result"] == {"status": "Succeeded", "mode": "created", "id": "rp-2"} and "error" not in out
    assert sum("/operations/op-1" in u for u in fabric["gets"]) == 2 and len(fabric["posts"]) == 1


def test_operation_that_fails_is_explained(fabric):
    fabric["post"] = lambda url, json: Resp(202, None, {"x-ms-operation-id": "op-2"})
    fabric["polls"] = iter([Resp(200, {"status": "Failed", "error": {"errorCode": "InvalidRequest", "message": "model not readable"}})])
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["result"]["status"] == "Failed" and out["kind"] in ("fabric_error", "unexpected") and "model not readable" in out["error"]


def test_a_model_that_cannot_be_read_is_consent_and_names_the_empty_page(fabric):
    err = requests.HTTPError("403", response=Resp(403, {"errorCode": "InsufficientScopes"}))
    fabric["tmdl"] = err
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["kind"] == "consent" and out["scope"] == server.MODEL_READ_SCOPE and "empty_page=true" in out["hint"]
    assert "Nothing was created" in out["error"] and fabric["posts"] == []
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", empty_page=True, dry_run=False))
    assert fabric["posts"] and "creationPayload" in fabric["posts"][0][1]


def test_403_without_the_scope_is_consent_naming_it(fabric):
    fabric["post"] = lambda url, json: Resp(403, {"errorCode": "InsufficientScopes", "message": "The caller lacks the required scope"})
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["kind"] == "consent" and out["scope"] == "Report.ReadWrite.All (or Item.ReadWrite.All)"
    assert "Report.ReadWrite.All" in out["hint"] and "docs/SCOPES.md" in out["hint"] and out["fabric_error_code"] == "InsufficientScopes"
    assert "fabric-token" not in json.dumps(out) and "Bearer" not in json.dumps(out)
    fabric["post"] = lambda url, json: Resp(403, {"errorCode": "InsufficientPrivileges", "message": "not enough"})
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["kind"] == "no_access" and "Contributor" in out["hint"]


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_report_of_that_name_is_left_alone(fabric, dry_run):
    out = json.loads(server.create_report("Sales", "shop_model", "old_report", dry_run=dry_run))
    assert out["kind"] == "already_exists" and out["existing"] == {"id": "rp-0", "name": "old_report"}
    assert "nothing was created" in out["error"] and "never updates or deletes" in out["hint"]
    assert fabric["posts"] == [] and "rest" not in out


def test_a_model_that_is_not_there_is_not_found(fabric):
    out = json.loads(server.create_report("Sales", "ghost_model", "shop_report", dry_run=False))
    assert out["kind"] == "not_found" and "ghost_model" in out["error"] and "create_semantic_model" in out["hint"]
    assert fabric["posts"] == []


def test_the_listing_marks_it_as_a_creating_tool_with_short_descriptions():
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "create_report")
    a = tool.annotations
    assert a.read_only_hint is False and a.destructive_hint is True and a.idempotent_hint is True
    assert a.title == "Create a Power BI report on a semantic model (dry run by default)"
    props = tool.input_schema["properties"]
    assert set(props) == {"workspace", "model", "name", "empty_page", "dry_run"} and set(tool.input_schema["required"]) == {"workspace", "model", "name"}
    assert all(props[p]["description"] for p in props) and props["dry_run"]["default"] is True and props["empty_page"]["default"] is False
    text = " ".join(tool.description.split())
    assert "empty_page=true" in text and "{error, kind, hint}" in text and "already_exists" in text and len(text) < 700
    assert "already_exists" in HINTS and "never updates or deletes" in HINTS["already_exists"]



# ------------------------------------------------------------------ n144: the page with visuals ---------------------

SHOP = model_compare.from_tmdl(SHOP_PARTS)
TOP = {   # top-level fields per file: (required, allowed), from microsoft/json-schemas eecc60d (report.py's docstring)
    "definition.pbir": ({"$schema", "version", "datasetReference"}, {"$schema", "version", "datasetReference"}),
    "version.json": ({"$schema", "version"}, {"$schema", "version"}),
    "report.json": ({"$schema", "themeCollection"}, {"$schema", "themeCollection", "filterConfig", "objects", "reportSource", "publicCustomVisuals",
                                                     "resourcePackages", "organizationCustomVisuals", "annotations", "dataSourceVariables",
                                                     "settings", "slowDataSourceSettings"}),
    "pages.json": ({"$schema"}, {"$schema", "pageOrder", "activePageName"}),
    "page.json": ({"$schema", "name", "displayName", "displayOption"}, {"$schema", "name", "displayName", "displayOption", "height", "width",
                                                                      "filterConfig", "pageBinding", "objects", "type", "visibility",
                                                                      "visualInteractions", "autoPageGenerationConfig", "annotations", "howCreated"}),
    "visual.json": ({"$schema", "name", "position"}, {"$schema", "name", "position", "visual", "visualGroup", "parentGroupName", "filterConfig",
                                                      "isHidden", "annotations", "howCreated"}),
}
ROLES = {"card": {"Values"}, "clusteredColumnChart": {"Category", "Y"}, "clusteredBarChart": {"Category", "Y"}, "tableEx": {"Values"},
         "slicer": {"Values"}}
SCHEMAS = Path(__file__).resolve().parent / "fixtures" / "pbir_schemas"
_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/report/"


def _registry():
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7
    reg = Registry()
    for f in sorted(SCHEMAS.rglob("*.json")):
        reg = reg.with_resource(_BASE + f.relative_to(SCHEMAS).as_posix(),
                                Resource.from_contents(json.loads(f.read_text(encoding="utf-8-sig")), default_specification=DRAFT7))
    return reg


REGISTRY = _registry()


def schema_errors(doc: dict) -> list[str]:
    """The messages of every way the document breaks the schema its `$schema` names (one of the copied files)."""
    from jsonschema import Draft7Validator
    schema = REGISTRY.get_or_retrieve(doc["$schema"]).value.contents
    return [f"{list(e.absolute_path)}: {e.message}" for e in Draft7Validator(schema, registry=REGISTRY).iter_errors(doc)]


def _fields(v: dict) -> list[tuple[str, str, str]]:
    """(Column|Measure, table, property) of every field a visual.json names: projections and sorts."""
    out, q = [], v["visual"].get("query", {"queryState": {}})                      # a text box has no query
    for role in q["queryState"].values():
        for pr in role["projections"]:
            out.append(pr["field"])
    out += [x["field"] for x in q.get("sortDefinition", {}).get("sort", [])]
    return [(k, f[k]["Expression"]["SourceRef"]["Entity"], f[k]["Property"]) for f in out for k in f]


def _check_against_model(parts: dict[str, str], model: dict) -> list[dict]:
    visuals = []
    for path, text in parts.items():
        doc = json.loads(text)
        if path.startswith("StaticResources/"):                       # the theme (n151): no $schema, checked in test_n151
            continue
        assert schema_errors(doc) == [], path
        required, allowed = TOP[path.rsplit("/", 1)[-1]]
        assert required <= set(doc) <= allowed, path
        assert doc["$schema"].startswith("https://developer.microsoft.com/json-schemas/fabric/item/report/"), path
        if path.endswith("/visual.json"):
            assert path.split("/")[-2] == doc["name"] and set(doc["position"]) == {"x", "y", "z", "width", "height", "tabOrder"}
            assert doc["position"]["x"] + doc["position"]["width"] <= report.PAGE_W and doc["position"]["y"] + doc["position"]["height"] <= report.PAGE_H
            if doc["visual"]["visualType"] == "textbox":                # the page's title and footnote (n151): no data
                assert set(doc["visual"]) == {"visualType", "objects"}
                continue
            assert {"visualType", "query", "drillFilterOtherVisuals", "visualContainerObjects"} <= set(doc["visual"]) <= \
                {"visualType", "query", "drillFilterOtherVisuals", "visualContainerObjects", "objects"}
            assert set(doc["visual"]["query"]["queryState"]) == ROLES[doc["visual"]["visualType"]]
            for role in doc["visual"]["query"]["queryState"].values():
                for pr in role["projections"]:
                    assert {"field", "queryRef"} <= set(pr) <= {"field", "queryRef", "nativeQueryRef", "active"}
            for x in doc["visual"]["query"].get("sortDefinition", {}).get("sort", []):
                assert x["direction"] in ("Ascending", "Descending")
            for kind, table, prop in _fields(doc):
                where = model["tables"][table]["measures" if kind == "Measure" else "columns"]
                assert prop in where, (path, kind, table, prop)
            visuals.append(doc)
    pages = json.loads(parts["definition/pages/pages.json"])
    assert [p for p in parts if p.endswith("/page.json")] == [f"definition/pages/{pages['activePageName']}/page.json"]
    assert pages["pageOrder"] == [pages["activePageName"]]
    assert json.loads(parts["definition/version.json"])["version"] == "2.0.0"
    return visuals


def test_shop_model_gets_cards_a_column_chart_by_month_a_bar_chart_by_category_and_a_table():
    d = report.definition_parts(SHOP, MODEL_ID)
    # n151: the cards of the business tables (orders first: order_items points at it) and the units; the title and the
    # footnote as text boxes; the table by the same units; a slicer for the month and one for the category
    assert [(v["type"], v["fields"]) for v in d["visuals"]] == [
        ("textbox", []),
        ("card", ["orders[Rows in orders]"]),
        ("card", ["order_items[Rows in order_items]"]),
        ("card", ["order_items[Total quantity]"]),
        ("clusteredColumnChart", ["Calendar[Year Month]", "order_items[Total quantity]"]),
        ("clusteredBarChart", ["categories[name]", "order_items[Total quantity]"]),
        ("tableEx", ["products[name]", "order_items[Total quantity]"]),
        ("slicer", ["Calendar[Year Month]"]),
        ("slicer", ["categories[name]"]),
        ("textbox", []),
    ]
    assert [v["title"] for v in d["visuals"]][1:-1] == ["Orders", "Order lines", "Units", "Units by month", "Units by category",
                                                         "Products by units", "Month", "Category"]
    assert d["left_out"] == [] and [x["measure"] for x in d["not_drawn"]] == ["audit_log[Rows in audit_log]"]
    visuals = _check_against_model(d["parts"], SHOP)
    assert len(visuals) == 8 and len({v["name"] for v in visuals}) == 8           # the two text boxes hold no data
    bar = next(v for v in visuals if v["visual"]["visualType"] == "clusteredBarChart")
    assert bar["visual"]["query"]["sortDefinition"]["sort"][0]["direction"] == "Descending"


def test_the_definition_is_deterministic():
    a = report.definition_parts(SHOP, MODEL_ID)
    b = report.definition_parts(model_compare.from_tmdl(dict(reversed(list(SHOP_PARTS.items())))), MODEL_ID)
    assert a == b and report.definition_payload("r", a["parts"]) == report.definition_payload("r", b["parts"])
    assert report.definition_parts(SHOP, "33333333-3333-3333-3333-333333333333")["parts"] != a["parts"]


def test_the_dry_run_lists_the_visuals_and_the_parts(fabric):
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report"))
    assert [v["type"] for v in out["report"]["visuals"]] == (["textbox"] + ["card"] * 3 + ["clusteredColumnChart", "clusteredBarChart", "tableEx"]
                                                             + ["slicer"] * 2 + ["textbox"])
    assert out["report"]["visuals"][5]["title"] == "Units by category" and out["report"]["visuals"][0]["title"] == "Overview · shop_model"
    assert all({"x", "y", "width", "height"} == set(v["position"]) for v in out["report"]["visuals"])     # n151: titles, positions, formats
    assert out["report"]["visuals"][1]["format"] == {"format_string": "#,0", "whole_number": True, "visual_sets_no_decimals": False}
    assert out["report"]["not_drawn"][0]["why"] == "audit_log is named like a log: not a business figure for a card"
    assert out["rest"]["body"]["definition"] == {"parts": "<base64 PBIR parts, see parts>"} and "creationPayload" not in out["rest"]["body"]
    assert out["parts"] == report.definition_parts(SHOP, MODEL_ID, model_name="shop_model")["parts"] and fabric["posts"] == []
    assert "PBIR" in out["rest"]["spec"] and "empty" not in out["report"]


def test_a_header_amount_is_never_summed_over_lines():
    """amount_levels' two shapes: a header amount next to its lines (n88/n133), and a flat table that repeats it (n106)."""
    from test_amounts import demo_schema
    from test_n106_flat_amounts import _flat
    header = model_compare.from_tmdl(semantic_model.draft(plan(demo_schema()), {"schema": "demo"}, "m")["parts"])
    p, ex = _flat()
    flat = model_compare.from_tmdl(semantic_model.draft(p, {"schema": "x"}, "m", validation=evidence.validate(p, ex))["parts"])
    for model, refused in ((header, ("orders", "Total order_amount")), (flat, None)):
        d = report.definition_parts(model, MODEL_ID)
        _check_against_model(d["parts"], model)
        drawn = {(t, prop) for path, text in d["parts"].items() if path.endswith("/visual.json")
                 for kind, t, prop in _fields(json.loads(text)) if kind == "Measure"}
        for t, c in (("orders", "order_amount"), ("order_lines", "order_amount")):
            plain = {(t, m) for m, x in model["tables"].get(t, {}).get("measures", {}).items() if x["expression"] == f"SUM('{t}'[{c}])"}
            assert not plain & drawn
        if refused:
            assert refused in {(m["table"], m["measure"]) for m in d["left_out"]} and "summarizeBy: none" in d["left_out"][0]["why"]


def test_an_amount_copied_onto_lines_and_a_header_measure_out_of_reach_are_not_drawn():
    """A model of the user's own: order_lines carries the header's order_amount and sums it (summarizeBy sum), and
    orders has a plain sum of its own amount. Neither is drawn by the products dimension the lines reach."""
    rel = lambda f, fc, t, tc: {"name": f"{f}-{t}", "active": True, "cross_filter": "oneDirection", "from_cardinality": "many",
                                "to_cardinality": "one", "from_table": f, "from_column": fc, "to_table": t, "to_column": tc}
    col = lambda n, dt="int64", key=False, s="none": {"name": n, "data_type": dt, "is_key": key, "summarize_by": s}
    model = {"tables": {
        "orders": {"columns": {"order_id": col("order_id", key=True), "order_amount": col("order_amount", "double", s="sum")},
                   "measures": {"Order total": {"expression": "SUM('orders'[order_amount])"}}},
        "order_lines": {"columns": {"order_id": col("order_id"), "product_id": col("product_id"), "qty": col("qty", s="sum"),
                                    "order_amount": col("order_amount", "double", s="sum")},
                        "measures": {"Lines": {"expression": "COUNTROWS('order_lines')"}, "Qty": {"expression": "SUM('order_lines'[qty])"},
                                     "Amount on lines": {"expression": "SUM('order_lines'[order_amount])"}}},
        "products": {"columns": {"product_id": col("product_id", key=True), "title": col("title", "string")}, "measures": {}}},
        "relationships": [rel("order_lines", "order_id", "orders", "order_id"), rel("order_lines", "product_id", "products", "product_id")]}
    d = report.definition_parts(model, MODEL_ID)
    _check_against_model(d["parts"], model)
    assert [(v["type"], v["fields"]) for v in d["visuals"]] == [
        ("textbox", []),
        ("card", ["order_lines[Lines]"]),
        ("card", ["order_lines[Qty]"]),
        ("clusteredBarChart", ["products[title]", "order_lines[Qty]"]),
        ("tableEx", ["products[title]", "order_lines[Qty]"]),
        ("slicer", ["products[title]"]),
        ("textbox", []),
    ]
    assert [v["title"] for v in d["visuals"]][1:-1] == ["Lines", "Units", "Units by product", "Products by units", "Product"]
    assert [(m["measure"], "orders has a column order_amount too" in m["why"]) for m in d["left_out"]] == [("Amount on lines", True)]


def test_a_model_with_nothing_to_draw_falls_back_to_the_blank_page(fabric):
    fabric["tmdl"] = {"definition/tables/t.tmdl": "table t\n\tcolumn a\n\t\tdataType: string\n\t\tsourceColumn: a\n"}
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report"))
    assert out["report"]["visuals"] == [] and "left blank" in out["report"]["why_empty"] and "creationPayload" in out["rest"]["body"]
