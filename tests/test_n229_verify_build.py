"""n229, part A: verify_build, the verifier by rules of what was built (fabric_backend/verify_build.py, server.verify_build).

Fabric's REST API, the SQL endpoint and the two Power BI reads are test doubles: the "workspace" holds exactly the
definitions the creating tools would send, and each test changes one thing in it. The rows are the synthetic shop
sample in SQLite (seed.py) and, for the header-level query, the synthetic SAP-shaped sample (sap_demo.py): no Fabric, no
customer data, no SAP system.
"""
import base64
import json
import sqlite3

import pytest

from fabric_backend import amounts, answers, budget, sap_demo, seed, server, verify_build as vb
from fabric_backend import model_compare as mc, ontology, report, semantic_model
from fabric_backend.dialects import sqlite_sql
from fabric_backend.graphql import definition
from fabric_backend.infer import plan
from fabric_backend.platforms import local
from fabric_backend.schema import Column, Schema, Table

WS = "11111111-1111-1111-1111-111111111111"
MODEL_ID = "22222222-2222-2222-2222-222222222222"
INFO = {"workspace_id": WS, "item_id": "33333333-3333-3333-3333-333333333333", "item_name": "demo_lh", "item_kind": "Lakehouse",
        "schema": "shop", "sql_endpoint": "h", "sql_db": "demo_lh", "schemas_enabled": True, "onelake_tables_path": ""}


def shop_plan():
    return plan(seed.schema("shop"))


@pytest.fixture(scope="module")
def rows():
    src = local.sample_source()
    yield src.execute
    src.close()


class Workspace:
    """A Fabric workspace as the verifier reads it: the item list and each item's definition, built from the same
    functions the creating tools use, so that "identical" means byte for byte what a Create sends."""

    def __init__(self):
        p = shop_plan()
        self.plan = p
        self.model_parts = semantic_model.draft(p, INFO, "shop_model")["parts"]
        model = mc.from_tmdl(self.model_parts)
        self.report_parts = report.definition_parts(model, MODEL_ID, model_name="shop_model")["parts"]
        self.ontology_parts = ontology.ontology_parts(p, "shop_ontology", **{k: INFO[k] for k in ("workspace_id", "item_id", "item_name",
                                                                                                    "item_kind", "schema", "sql_endpoint")})
        env = definition(p, "shop_api", WS, "ep-1", "SqlAnalyticsEndpoint")
        self.api = json.loads(base64.b64decode(next(x for x in env["definition"]["parts"] if x["path"] == "graphql-definition.json")["payload"]))
        build = server._pipeline_build(p, INFO, "shop", "silver", "gold", None, False, "pipeline_shop", "", "")
        self.notebooks = {n["name"]: n["content"] for n in build["notebooks"]}
        ids = {n: f"aaaaaaaa-0000-0000-0000-00000000000{i}" for i, n in enumerate(self.notebooks, start=1)}
        self.pipeline = server._pipeline_content(build, ids, WS)
        self.items = [{"id": MODEL_ID, "displayName": "shop_model", "type": "SemanticModel"},
                      {"id": "r-1", "displayName": "shop_model_report", "type": "Report"},
                      {"id": "o-1", "displayName": "shop_ontology", "type": "Ontology"},
                      {"id": "g-1", "displayName": "shop_api", "type": "GraphQLApi"},
                      {"id": "p-1", "displayName": "pipeline_shop", "type": "DataPipeline"},
                      {"id": "app-1", "displayName": "shop_app", "type": "AppBackend"}]
        self.items += [{"id": i, "displayName": n, "type": "Notebook"} for n, i in ids.items()]
        self.refreshes = [{"status": "Completed", "endTime": "2026-11-15T10:00:00Z"}]
        self.runs = [{"status": "Completed"}]
        self.dax = None                      # None: the model answers what the rows give; a dict: {measure: number}; an exception
        self.reads: list[str] = []

    def parts(self, ws, route, item_id, headers, fmt=None):
        self.reads.append(f"{route}/{item_id}")
        by = {"semanticModels": self.model_parts, "reports": self.report_parts, "ontologies": self.ontology_parts,
              "dataPipelines": {"pipeline-content.json": json.dumps(self.pipeline)}}
        if route == "notebooks":
            name = next(i["displayName"] for i in self.items if i["id"] == item_id)
            return {"notebook-content.py": self.notebooks[name]}
        return by[route]


@pytest.fixture
def fabric(monkeypatch, rows):
    w = Workspace()
    monkeypatch.setattr(server, "_source_inputs", lambda workspace, source, schema, keys, confirmed, ctx: (w.plan, dict(INFO)))
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_items", lambda ws, headers: list(w.items))
    monkeypatch.setattr(server, "_item_definition_parts", w.parts)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: w.api)
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "_connected", lambda workspace, source, schema, ctx: (w.plan.schema, rows))
    monkeypatch.setattr(server, "_job_instances", lambda ws, item_id, headers: list(w.runs))

    def refreshes(ws, model_id, ctx):
        if isinstance(w.refreshes, BaseException):
            raise w.refreshes
        return list(w.refreshes)

    def dax(ws, model_id, query, ctx):
        if isinstance(w.dax, BaseException):
            raise w.dax
        name = query.split("[", 1)[1].rsplit("]", 1)[0]
        if isinstance(w.dax, dict) and name in w.dax:
            return [{"[v]": w.dax[name]}]
        model = mc.from_tmdl(w.model_parts)
        expr = next(m["expression"] for t in model["tables"].values() for n, m in t["measures"].items() if n == name)
        return [{"[v]": rows(vb.measure_sql(model, expr, "shop")["sql"])[0]["v"]}]
    monkeypatch.setattr(server, "_powerbi_refreshes", refreshes)
    monkeypatch.setattr(server, "_powerbi_dax", dax)
    return w


ALL = {"semantic_model": "shop_model", "report": "shop_model_report", "ontology": "shop_ontology", "api": "shop_api",
       "pipeline": "pipeline_shop"}


def verify(items=None, **kw):
    return json.loads(server.verify_build("demo", "demo_lh", items or ALL, schema="shop", **kw))


def line(out, name):
    return next(x for x in out["lines"] if x["item"] == name)


# ------------------------------------------------------------------ identical ----------------------------------------

def test_identical_definitions_are_verified_item_by_item(fabric):
    fabric.items.append({"id": "gm-1", "displayName": "shop_ontology_graph", "type": "GraphModel"})
    out = verify()
    assert out["label"].startswith("A check by rules, not a review by AI") and "No AI model was used" in out["label"]
    assert [x["item"] for x in out["lines"]] == ["shop_model", "shop_model_report", "shop_ontology", "shop_api", "pipeline_shop",
                                                 "silver_shop", "gold_shop", "pipeline_shop_check"]
    assert {x["state"] for x in out["lines"]} == {"verified"}, out["result_lines"]
    assert out["counts"] == {"verified": 8, "differs": 0, "not_checked": 0, "items": 8}
    assert out["summary"].startswith("8 item(s): 8 verified, 0 differ, 0 not checked. Figures: 3 verified")
    assert out["writes"] == "nothing: every call is a read" and out["fixes"] == [] and "next_steps" not in out
    assert line(out, "shop_model")["checked"] == {"tables": 8, "relationships": 7, "active": 7, "inactive": 0, "measures": 5,
                                                   "combined_key_columns": 0}
    assert line(out, "shop_ontology")["checked"] == {"entity_types": 7, "with_key": 5, "relationship_types": 6, "data_bindings": 13}
    assert line(out, "pipeline_shop")["checked"] == {"steps": 3}
    assert len(out["result_lines"]) == 8 and all(s.split(": ")[1].startswith("verified") for s in out["result_lines"])


def test_the_reports_cards_are_counted_again_from_the_rows_and_the_sql_is_shown(fabric):
    out = verify({"semantic_model": "shop_model", "report": "shop_model_report"})
    figs = {f["kpi"]: f for f in line(out, "shop_model_report")["figures"]}
    assert {k: (f["source_rows"], f["model"], f["state"]) for k, f in figs.items()} == {
        "Orders": (60, 60, "verified"), "Order lines": (134, 134, "verified"), "Units": (324, 324, "verified")}
    assert figs["Orders"]["measure"] == "orders[Rows in orders]" and figs["Units"]["measure"] == "order_items[Total quantity]"
    assert figs["Orders"]["sql"] == "SELECT COUNT_BIG(*) AS v FROM [shop].[orders]"
    assert figs["Units"]["sql"] == "SELECT SUM([quantity]) AS v FROM [shop].[order_items]"
    assert figs["Units"]["dax"] == 'EVALUATE ROW("v", [Total quantity])'
    assert figs["Units"]["said"] == "Units = 324: the model and the source rows agree."
    assert {(s["what"], s["sql"]) for s in out["sql"]} >= {("Orders", figs["Orders"]["sql"]), ("Units", figs["Units"]["sql"])}
    assert "No doubled total found." in line(out, "shop_model_report")["said"]
    assert "figures" not in line(out, "shop_model")                       # with a report, the figures are the report's cards


def test_a_model_without_a_report_gets_its_own_measures_as_figures(fabric):
    out = verify({"semantic_model": "shop_model"})
    figs = line(out, "shop_model")["figures"]
    assert len(figs) == 5 and all(f["state"] == "verified" for f in figs)
    assert next(f for f in figs if f["kpi"] == "Rows in orders")["source_rows"] == 60


def test_a_figure_that_differs_is_said_with_both_numbers(fabric):
    fabric.dax = {"Total quantity": 648}
    out = verify({"report": "shop_model_report"})
    ln = line(out, "shop_model_report")
    units = next(f for f in ln["figures"] if f["kpi"] == "Units")
    assert units["state"] == "differs" and units["said"] == "Units: the model says 648, the source rows give 324."
    assert ln["state"] == "differs" and "the model says 648" in ln["said"]
    assert out["counts"]["differs"] == 1 and "Figures: 2 verified, 1 differs" in out["summary"]


def test_without_a_power_bi_answer_the_figure_is_shown_and_never_called_verified(fabric):
    fabric.dax = RuntimeError("HTTP 403")
    fabric.refreshes = RuntimeError("HTTP 403")
    out = verify({"semantic_model": "shop_model", "report": "shop_model_report"})
    rep = line(out, "shop_model_report")
    assert rep["state"] == "not checked" and all(f["state"] == "not checked" for f in rep["figures"])
    assert "Orders = 60 from the source rows; not checked against the model" in rep["figures"][1]["said"] or \
        any("= 60 from the source rows; not checked against the model" in f["said"] for f in rep["figures"])
    assert "from the rows: " in rep["said"] and "Orders = 60" in rep["said"] and "Units = 324" in rep["said"]
    model = line(out, "shop_model")
    assert model["state"] == "not checked" and model["state_check"]["state"] == "not checked"
    assert "Definition as the dry run" in model["said"] and "was not read (HTTP 403: " in model["said"]
    assert "Dataset.Read.All or Dataset.ReadWrite.All" in model["said"] and "Entra" in model["said"]
    assert out["counts"]["verified"] == 0


# ------------------------------------------------------------------ one differing relationship -----------------------

def _edit_relationship(parts: dict, edit) -> dict:
    out = dict(parts)
    blocks = out["definition/relationships.tmdl"].split("\nrelationship ")
    i = next(k for k, b in enumerate(blocks) if "fromColumn: orders.customer_id" in b)
    blocks[i] = edit(blocks[i])
    out["definition/relationships.tmdl"] = "\nrelationship ".join(b for b in blocks if b is not None)
    return out


def test_one_relationship_made_inactive_in_fabric_is_the_one_difference(fabric):
    fabric.model_parts = _edit_relationship(fabric.model_parts, lambda b: b.rstrip("\n") + "\n\tisActive: false\n")
    out = verify({"semantic_model": "shop_model", "api": "shop_api"})
    ln = line(out, "shop_model")
    assert ln["state"] == "differs" and ln["differences_total"] == 1 and line(out, "shop_api")["state"] == "verified"
    assert ln["differences"] == [{"what": "relationship", "said": "Relationship orders.customer_id -> customers.customer_id is active in "
                                                                  "the dry run and inactive in Fabric."}]
    assert "Definition: 1 difference(s) from the dry run" in ln["said"] and "inactive in Fabric" in ln["said"]
    assert out["counts"]["differs"] == 1


def test_a_relationship_gone_another_cardinality_and_a_moved_measure_are_each_listed(fabric):
    gone = _edit_relationship(fabric.model_parts, lambda b: None)
    d = vb.compare_model(fabric.model_parts, gone)["differences"]
    assert [x["said"] for x in d] == ["Relationship orders.customer_id -> customers.customer_id is in the dry run and not in Fabric."]
    card = _edit_relationship(fabric.model_parts, lambda b: b.rstrip("\n") + "\n\ttoCardinality: many\n")
    d = vb.compare_model(fabric.model_parts, card)["differences"]
    assert [x["said"] for x in d] == ["Relationship orders.customer_id -> customers.customer_id is many-to-one in the dry run and "
                                      "many-to-many in Fabric."]
    moved = dict(fabric.model_parts)
    text = moved["definition/tables/order_items.tmdl"]
    a = text.index("\tmeasure 'Total quantity'")
    b = min(text.index("\tcolumn ", a), text.index("\tmeasure ", a + 5) if "\tmeasure " in text[a + 5:] else len(text))
    measure = text[a:b]
    moved["definition/tables/order_items.tmdl"] = text[:a] + text[b:]
    orders = moved["definition/tables/orders.tmdl"]
    k = orders.index("\tcolumn ")
    moved["definition/tables/orders.tmdl"] = orders[:k] + measure + orders[k:]
    d = vb.compare_model(fabric.model_parts, moved)["differences"]
    assert [x["said"] for x in d] == ["Measure Total quantity sits on orders in Fabric and on order_items in the dry run: another level."]


def test_a_missing_combined_key_column_is_named_as_one():
    schema, _ = sap_demo.sqlite()
    p = plan(schema)
    info = {**INFO, "schema": "sap"}
    draft = semantic_model.draft(p, info, "sap_model")
    assert draft["summary"]["relationships_active"] + draft["summary"]["relationships_inactive"] == 24
    parts = dict(draft["parts"])
    path = "definition/tables/sap_vbak.tmdl"
    a = parts[path].index("\tcolumn MANDT_VBELN_key")
    b = parts[path].index("\tcolumn ", a + 5) if "\tcolumn " in parts[path][a + 5:] else parts[path].index("\tpartition ", a)
    parts[path] = parts[path][:a] + parts[path][b:]
    d = vb.compare_model(draft["parts"], parts, draft["summary"]["combined_key_columns"])
    assert d["checked"]["combined_key_columns"] == len(draft["summary"]["combined_key_columns"]) > 0
    assert [x["said"] for x in d["differences"]] == ["Column sap_vbak.MANDT_VBELN_key is in the dry run and not in Fabric: the combined "
                                                     "key column for MANDT + VBELN."]


def test_ontology_keys_bindings_and_relationships_are_compared(fabric):
    changed = dict(fabric.ontology_parts)
    ent = "entities/Customers.tmdl"
    changed[ent] = changed[ent].replace("keyProperty: customer_id", "keyProperty: name").replace("valueColumn: Customers.country",
                                                                                                    "valueColumn: Customers.city")
    rel = changed["entityRelationships.tmdl"]
    a = rel.index("/// orders.customer_id -> customers.customer_id")
    b = rel.index("/// ", a + 5)
    changed["entityRelationships.tmdl"] = rel[:a] + rel[b:]
    changed["relationships.tmdl"] = changed["relationships.tmdl"].replace("toColumn: Orders.order_id", "toColumn: Orders.customer_id")
    said = [x["said"] for x in vb.compare_ontology(fabric.ontology_parts, changed)["differences"]]
    assert said == ["Entity type Customers has the key name in Fabric and customer_id in the dry run.",
                    "Property Customers.country is bound to Customers.city in Fabric and to Customers.country in the dry run.",
                    "Relationship type OrdersHasCustomers (Orders -> Customers) is in the dry run and not in Fabric.",
                    "The column binding OrderItems_order_id_Orders goes OrderItems.order_id -> Orders.customer_id in Fabric and "
                    "OrderItems.order_id -> Orders.order_id in the dry run."]


def test_pipeline_steps_a_changed_notebook_and_an_api_field_are_compared(fabric):
    fabric.pipeline["properties"]["activities"][2]["dependsOn"] = []
    fabric.notebooks["gold_shop"] = fabric.notebooks["gold_shop"] + "\nprint('added in the portal')\n"
    fabric.api["datasources"][0]["objects"][0]["fieldMappings"].pop(next(iter(fabric.api["datasources"][0]["objects"][0]["fieldMappings"])))
    out = verify({"pipeline": "pipeline_shop", "api": "shop_api"})
    assert line(out, "pipeline_shop")["state"] == "differs" and "waits for nothing in Fabric" in line(out, "pipeline_shop")["said"]
    assert line(out, "silver_shop")["state"] == "verified" and line(out, "gold_shop")["state"] == "differs"
    assert "differs from the dry run on 1 line(s)" in line(out, "gold_shop")["said"]
    assert line(out, "shop_api")["state"] == "differs" and "is in the dry run and not in Fabric" in line(out, "shop_api")["said"]


# ------------------------------------------------------------------ state --------------------------------------------

def test_a_model_never_refreshed_differs_and_the_one_fix_is_a_refresh(fabric):
    fabric.refreshes = []
    out = verify({"semantic_model": "shop_model"})
    ln = line(out, "shop_model")
    assert ln["state"] == "differs" and ln["state_check"] == {**vb.model_state([])}
    assert "never refreshed" in ln["said"] and "Invalid Date" in ln["said"] and ln["said"].endswith("Fix: Refresh the model once.")
    assert "Definition as the dry run" in ln["said"]                        # the definition is right; the state is not
    assert out["fixes"] == [{"item": "shop_model", **vb.REFRESH_FIX}]
    step = out["next_steps"][0]
    assert step["label"] == "Refresh the model once" and "create_semantic_model" in step["ask"] and '"refresh": true' not in step["ask"]
    assert "refresh=true" in step["ask"] and "dry_run=false" in step["ask"] and "confirm" in step["ask"]


def test_pipeline_never_run_ontology_without_a_graph_and_an_app_each_say_their_one_action(fabric):
    fabric.runs = []
    out = verify({"pipeline": "pipeline_shop", "ontology": "shop_ontology", "app": "shop_app"})
    assert line(out, "pipeline_shop")["state"] == "differs" and "never ran" in line(out, "pipeline_shop")["said"]
    assert line(out, "shop_ontology")["state"] == "differs" and "does not look built" in line(out, "shop_ontology")["said"]
    assert "no documented call reads the graph's state" in line(out, "shop_ontology")["said"]
    app = line(out, "shop_app")
    assert app["state"] == "not checked" and "empty" in app["said"] and "one command" in app["said"]
    assert [f["label"] for f in out["fixes"]] == ["Build the ontology's graph", "Run the pipeline once", "Publish the App's package"] or \
        sorted(f["label"] for f in out["fixes"]) == sorted(["Build the ontology's graph", "Run the pipeline once", "Publish the App's package"])
    assert vb.pipeline_state([{"status": "Failed"}])["state"] == "differs"
    assert vb.model_state([{"status": "Failed"}])["said"].startswith("The model has no completed refresh")
    assert vb.ontology_state("x", [{"type": "GraphModel", "displayName": "other"}])["state"] == "not checked"


def test_an_item_that_is_not_there_or_cannot_be_read_is_not_checked_with_the_reason(fabric, monkeypatch):
    out = verify({"semantic_model": "nope_model"})
    assert out["lines"][0]["state"] == "not checked" and "no semantic model named nope_model" in out["lines"][0]["said"]

    def refuse(*a, **k):
        raise RuntimeError("getDefinition answered Failed")
    monkeypatch.setattr(server, "_item_definition_parts", refuse)
    out = verify({"ontology": "shop_ontology"})
    assert out["lines"][0]["state"] == "not checked" and "could not be read (getDefinition answered Failed)" in out["lines"][0]["said"]
    assert out["counts"] == {"verified": 0, "differs": 0, "not_checked": 1, "items": 1}


def test_the_time_budget_gives_not_checked_never_verified(fabric, monkeypatch):
    clock = iter([0.0, 0.0] + [100.0] * 500)
    with budget.call(seconds=45, clock=lambda: next(clock)):
        out = server._verify_built("demo", "demo_lh", dict(ALL), "shop", None, None, None, None)
    assert {x["state"] for x in out["lines"]} == {"not checked"} and out["counts"]["verified"] == 0
    assert all("not checked (time)" in x["said"] for x in out["lines"])
    assert out["time_budget"]["seconds"] == 45 and out["time_budget"]["used"] >= 45
    out = verify({"semantic_model": "shop_model"})
    assert out["time_budget"] == {"seconds": budget.call_seconds()}        # a budget on every call; no measured time unless it ran out


def test_bad_items_are_refused_before_anything_is_read(fabric):
    assert json.loads(server.verify_build("demo", "demo_lh", {}, schema="shop"))["kind"] == "bad_input"
    out = json.loads(server.verify_build("demo", "demo_lh", {"lakehouse": "x"}, schema="shop"))
    assert out["kind"] == "bad_input" and "not known: lakehouse" in out["error"] and fabric.reads == []


# ------------------------------------------------------------------ doubled totals -----------------------------------

def _flat():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS demo")
    con.execute("CREATE TABLE demo.[orders] (order_id INT, order_amount DOUBLE)")
    con.execute("CREATE TABLE demo.[order_lines] (order_id INT, line_no INT, order_amount DOUBLE, line_amount DOUBLE)")
    con.executemany("INSERT INTO demo.[orders] VALUES (?, ?)", [(1, 1000.0), (2, 500.0), (3, 70.0)])
    con.executemany("INSERT INTO demo.[order_lines] VALUES (?, ?, ?, ?)",
                    [(1, 1, 1000.0, 600.0), (1, 2, 1000.0, 400.0), (2, 1, 500.0, 200.0), (2, 2, 500.0, 300.0), (3, 1, 70.0, 70.0)])
    s = Schema(schema="demo")
    s.tables["orders"] = Table("orders", [Column("order_id", "int"), Column("order_amount", "double")], schema="demo")
    s.tables["order_lines"] = Table("order_lines", [Column("order_id", "int"), Column("line_no", "int"), Column("order_amount", "double"),
                                                    Column("line_amount", "double")], schema="demo")

    def execute(sql):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return plan(s), execute


def _model(measures: dict) -> dict:
    def table(name, cols, ms=None):
        return {"name": name, "source": name, "source_schema": "demo", "kind": "entity", "measures": ms or {},
                "columns": {c: {"name": c, "source_column": c, "data_type": "double", "is_key": False} for c in cols}}
    return {"tables": {"orders": table("orders", ["order_id", "order_amount"], measures.get("orders")),
                       "order_lines": table("order_lines", ["order_id", "line_no", "order_amount", "line_amount"], measures.get("order_lines"))},
            "relationships": [{"from_table": "order_lines", "from_column": "order_id", "to_table": "orders", "to_column": "order_id",
                               "active": True}]}


def test_a_header_amount_summed_over_its_lines_is_flagged_with_both_sums():
    p, execute = _flat()
    model = _model({"order_lines": {"Total order amount": {"expression": "SUM('order_lines'[order_amount])"},
                                    "Total line amount": {"expression": "SUM('order_lines'[line_amount])"}}})
    figs = vb.figures(model, None, execute, dax=None, default_schema="demo")
    assert {f["kpi"]: f["source_rows"] for f in figs} == {"Total order amount": 3070, "Total line amount": 1570}
    found = vb.doubled(p, model, figs, execute)
    assert len(found) == 1 and found[0]["measure"] == "order_lines[Total order amount]" and found[0]["state"] == "differs"
    assert (found[0]["summed_over_rows"], found[0]["summed_once"]) == (3070, 1570)
    assert found[0]["said"] == ("Total order amount looks doubled: order_lines.order_amount has one value per order_id and is repeated "
                                "on its rows, so the sum over the rows is 3 070 where once per order_id gives 1 570.")
    assert len(found[0]["sql"]) == 2 and all(s.startswith("SELECT") for s in found[0]["sql"])
    ln = vb.line("semantic_model", "flat_model", {"differences": [], "checked": {"tables": 2}}, figs=figs, doubles=found)
    assert ln["state"] == "differs" and "looks doubled" in ln["said"] and ln["doubled_totals"] == found
    out = vb.result([ln])
    assert any(s["what"] == "Total order amount (doubled total)" for s in out["sql"])


def test_a_figure_equal_to_the_header_amount_over_the_joined_lines_and_a_sumx_of_related_are_flagged():
    p, execute = _flat()
    model = _model({"orders": {"Total order amount": {"expression": "SUM('orders'[order_amount])"}},
                    "order_lines": {"Order amount per line": {"expression": "SUMX('order_lines', RELATED('orders'[order_amount]))"}}})
    f = next(h for h in amounts.header_amounts(p) if h["header"] == "orders")
    ba = amounts.before_after("demo", f, execute)
    assert (ba["summed_over_lines"], ba["summed_per_header"]) == (3070.0, 1570.0)
    right = vb.figures(model, None, execute, dax=lambda q: [{"[v]": 1570.0 if "Total order amount" in q else 3070.0}], default_schema="demo")
    found = vb.doubled(p, model, right, execute)
    assert [d["measure"] for d in found] == ["order_lines[Order amount per line]"]          # the SUMX of RELATED, by its expression
    assert "once per order_lines row (SUMX over RELATED)" in found[0]["said"]
    wrong = vb.figures(model, None, execute, dax=lambda q: [{"[v]": 3070.0}], default_schema="demo")
    found = vb.doubled(p, model, wrong, execute)
    hit = next(d for d in found if d["measure"] == "orders[Total order amount]")
    assert hit["said"] == ("Total order amount looks doubled: its number 3 070 is orders.order_amount summed over the order_lines rows; "
                           "once per orders row it is 1 570.")


def test_measure_sql_translates_four_forms_and_says_no_to_the_rest(rows):
    model = mc.from_tmdl(semantic_model.draft(shop_plan(), INFO, "shop_model")["parts"])
    assert vb.measure_sql(model, "COUNTROWS('orders')", "shop")["sql"] == "SELECT COUNT_BIG(*) AS v FROM [shop].[orders]"
    assert vb.measure_sql(model, "DISTINCTCOUNT('orders'[customer_id])", "shop")["sql"] == "SELECT COUNT(DISTINCT [customer_id]) AS v FROM [shop].[orders]"
    q = vb.measure_sql(model, "SUMX('order_items', 'order_items'[quantity] * RELATED('products'[list_price]))", "shop")
    assert q["sql"] == ("SELECT SUM(l.[quantity] * d.[list_price]) AS v FROM [shop].[order_items] AS l LEFT JOIN [shop].[products] AS d "
                        "ON l.[product_id] = d.[product_id]")
    by_hand = sum(r["quantity"] * r["list_price"] for r in rows(
        "SELECT i.quantity AS quantity, p.list_price AS list_price FROM shop.[order_items] AS i JOIN shop.[products] AS p ON i.product_id = p.product_id"))
    assert abs(rows(q["sql"])[0]["v"] - by_hand) < 1e-6
    no = vb.measure_sql(model, "CALCULATE(SUM('order_items'[quantity]), 'orders'[status] = \"open\")", "shop")
    assert "sql" not in no and "not one of the forms the rules translate" in no["why"]
    fig = vb.figures({"tables": {"t": {"name": "t", "source": "t", "source_schema": "shop", "columns": {}, "measures": {"M": {"expression": "DIVIDE(1, 2)"}}}},
                      "relationships": []}, None, rows)
    assert fig[0]["state"] == "not checked" and "not checked" in fig[0]["said"]


# ------------------------------------------------------------------ the header-level query (answers.py) --------------

@pytest.fixture(scope="module")
def sap():
    schema, execute = sap_demo.sqlite()
    return plan(schema), execute


def test_total_netwr_per_sales_order_sums_on_the_header_alone(sap):
    p, execute = sap
    out = answers.draft(p, "total NETWR per sales order", ["sap_vbap", "sap_vbak"])
    assert "sap_vbap" not in out["tsql"] and "DISTINCT" not in out["tsql"] and "JOIN" not in out["tsql"]
    assert out["tsql"] == ("SELECT t0.[MANDT], t0.[VBELN], SUM(t0.[NETWR]) AS [total_NETWR]\nFROM [sap].[sap_vbak] AS t0\n"
                           "GROUP BY t0.[MANDT], t0.[VBELN]\nORDER BY [total_NETWR] DESC")
    assert out["tables"] == ["sap_vbak"] and out["path"] == []
    assert any("summed on sap_vbak alone" in a and "would drop every sap_vbak row without a row there" in a for a in out["assumptions"])
    assert any(a.startswith("NETWR is a column of both sap_vbap and sap_vbak") for a in out["assumptions"])     # named first, so said
    same = answers.draft(p, "total NETWR per sales order", ["sap_vbak", "sap_vbap"])                       # the founder's order
    assert same["tsql"] == out["tsql"] and same["assumptions"][0].startswith("NETWR is a column of sap_vbak and of sap_vbap; sap_vbak.NETWR is used")
    words = answers.draft(p, "total net value per sales order", ["sap_vbak", "sap_vbap"])                 # F1 B1: the same choice in other words
    assert words["tsql"] == out["tsql"] and words["assumptions"][0].startswith("NETWR is a column of both sap_vbap and sap_vbak")
    got = execute(out["tsql"])
    assert len(got) == execute("SELECT COUNT(*) AS n FROM sap.[sap_vbak]")[0]["n"]                     # every order, also one without lines


def test_the_join_it_replaces_dropped_orders_without_lines(sap):
    p, execute = sap
    execute("SELECT 1 AS one")                                                                          # the connection is open
    joined = ("SELECT COUNT(*) AS n FROM (SELECT DISTINCT t1.[MANDT], t1.[VBELN] FROM [sap].[sap_vbap] AS t0 "
              "JOIN [sap].[sap_vbak] AS t1 ON t0.[MANDT] = t1.[MANDT] AND t0.[VBELN] = t1.[VBELN]) AS x")
    with_lines, all_orders = execute(joined)[0]["n"], execute("SELECT COUNT(*) AS n FROM sap.[sap_vbak]")[0]["n"]
    assert with_lines <= all_orders


def test_a_question_that_needs_the_lines_still_joins_them(sap):
    p, _ = sap
    per_customer = answers.draft(p, "total order value per customer", ["sap_vbak", "sap_vbap", "sap_kna1"])
    assert "FROM [sap].[sap_vbap] AS t0" in per_customer["tsql"] and "SUM(t0.[NETWR])" in per_customer["tsql"]     # a line amount: unchanged
    shop = answers.draft(shop_plan(), "Total quantity per category", ["order_items", "categories"])
    assert "JOIN" in shop["tsql"] and "GROUP BY" in shop["tsql"]


# ------------------------------------------------------------------ the tool -----------------------------------------

def test_verify_build_is_a_read_only_tool_and_says_by_rules_in_its_title():
    import asyncio
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    t = tools["verify_build"]
    assert t.annotations.read_only_hint is True and "by rules, no AI" in t.title
    assert set(t.input_schema["required"]) == {"workspace", "source", "items"}
    assert "Changes nothing" in " ".join(t.description.split()) and "not by AI" in " ".join(t.description.split())


def test_the_answer_invites_an_ai_clients_own_review_apart_from_the_rules(fabric):
    out = verify({"semantic_model": "shop_model"})
    assert "under its own heading" in out["review_by_ai"] and "never change a state Krusgraph's rules gave" in out["review_by_ai"]
    assert "checks" not in out                                              # the cards' rows only while the cards are on


def test_with_the_cards_on_the_answer_carries_rows_in_the_cards_words(fabric, monkeypatch):
    monkeypatch.setattr(server._mcp_apps, "enabled", lambda environ=None: True)
    fabric.refreshes = []
    out = verify({"semantic_model": "shop_model", "report": "shop_model_report"})
    c = out["checks"]
    assert c["words"] == {"passed": "verified", "failed": "differs", "not_checked": "not checked"} and c["sql_for_all"] is True
    assert c["label"] == vb.LABEL
    kinds = [r["kind"] for r in c["rows"]]
    assert kinds == ["item", "item", "figure", "figure", "figure"]
    assert c["rows"][0]["what"] == "Semantic model" and c["rows"][0]["state"] == "failed"
    assert all(r["sql"].startswith("SELECT") for r in c["rows"] if r["kind"] == "figure")
    assert c["counts"] == {"passed": 4, "failed": 1, "not_checked": 0}


# ------------------------------------------------------------------ the Model editor's route -------------------------

def _review(p):
    from fabric_backend import review as R
    return R.build(p, p, {"platform": "fabric", "source": "demo_lh", "schema": "shop"})


def test_the_editors_verify_route_reads_back_what_outputs_json_records(fabric):
    from fabric_backend import workload_api as W
    created = [{"type": "SemanticModel", "id": MODEL_ID, "name": "shop_model", "workspace": WS, "output": "semantic_model"},
               {"type": "Notebook", "id": "aaaaaaaa-0000-0000-0000-000000000001", "name": "silver_shop", "workspace": WS, "output": "pipeline"}]
    body = {"workspace": WS, "source": INFO["item_id"], "source_name": "demo_lh", "schema": "shop", "review": _review(fabric.plan),
            "created": created}
    req = W.verify_request(body)
    fabric.items[0]["id"] = MODEL_ID
    fabric.refreshes = []
    out = W.run_verify(req)
    assert out["label"].startswith("A check by rules, not a review by AI") and "review_by_ai" not in out and "checks" not in out
    assert [x["item"] for x in out["lines"]] == ["shop_model"] and out["lines"][0]["state"] == "differs"   # a notebook alone is no pipeline
    steps = [s["step"] for s in out["next_steps"]]
    assert steps[0] == "refresh_model" and steps[1:] == ["refresh", "pipeline", "report", "data_agent", "app", "drift_monitor", "data_product"]
    assert all(s["why"] and s["how"] for s in out["next_steps"]) and "Tick Report" in next(s for s in out["next_steps"] if s["step"] == "report")["how"]
    assert out["more"][0]["label"] == "Download a dbt project draft (a draft)" and out["note"].startswith(W.NOTHING_CHANGED)
    with pytest.raises(W.BadRequest):
        W.verify_request({**body, "created": [{"id": "not-a-guid", "name": "x"}]})
    with pytest.raises(W.BadRequest):
        W.verify_request({k: v for k, v in body.items() if k != "review"})
    empty = W.run_verify(W.verify_request({**body, "created": []}))
    assert empty["lines"] == [] and "Nothing to verify yet" in empty["summary"]
    assert 'f"{PREFIX}/verify"' in open(W.__file__, encoding="utf-8").read()                         # the route is registered


def test_a_build_in_another_workspace_compares_the_pipeline_s_activities(fabric, monkeypatch):
    """W4 (it was left not checked): the pipeline in the build's workspace is read and its activities compared with the
    dry run; without a lakehouse there to rebuild the notebooks' dry run, each notebook says why it is not checked."""
    from fabric_backend import workload_api as W
    other = "99999999-9999-9999-9999-999999999999"
    monkeypatch.setattr(server, "_list_items", lambda ws, headers: [])
    created = [{"type": "DataPipeline", "id": "aaaaaaaa-0000-0000-0000-0000000000ff", "name": "pipeline_shop",
                "workspace": other, "output": "pipeline"}]
    fabric.items[4]["id"] = "aaaaaaaa-0000-0000-0000-0000000000ff"
    out = W.run_verify(W.verify_request({"workspace": WS, "source": INFO["item_id"], "source_name": "demo_lh", "schema": "shop",
                                         "review": _review(fabric.plan), "created": created}))
    assert out["lines"][0]["item"] == "pipeline_shop" and out["lines"][0]["checked"] == {"steps": 3}
    assert all(x["state"] == "not checked" and "build's lakehouse" in x["said"] for x in out["lines"][1:])
