"""n110: the pipeline draft. export_item_definitions(items=["pipeline"]) adds one Fabric Data Pipeline in Git format that
runs the existing drafts in order (the silver notebook, the gold views notebook) and then a check notebook, each step
only after the one before succeeded, and fails when the check fails. The check runs here on SQLite over the silver
tables the silver notebook makes of the shop seed (silver.simulate) and the gold views' SELECTs (gold.run_select);
tests/test_spark_notebooks.py runs the check notebook itself on a local Spark."""
import base64
import json
import sqlite3

import jsonschema
import pytest
import requests

from fabric_backend import git_export, gold, notebook, pipeline, seed, server, silver
from fabric_backend.dialects import DATABRICKS
from fabric_backend.infer import plan
from fabric_backend.platforms.base import connection
from fabric_backend.schema import Schema
from silver_cases import seed_rows

WS = "11111111-1111-1111-1111-111111111111"
INFO = dict(workspace_id=WS, item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop", schemas_enabled=True)


@pytest.fixture
def shop(monkeypatch):
    kind = {"type": "Lakehouse", "schemas_enabled": True}
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": kind["type"], "id": "lh-1", "displayName": src, "sql_host": "x",
                                                                             "sql_db": src, "schemas_enabled": kind["schemas_enabled"]})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("the pipeline draft posts nothing"))
    monkeypatch.setattr(requests, "put", lambda *a, **k: pytest.fail("the pipeline draft puts nothing"))
    return kind


def export(**kw):
    return json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", items=["pipeline"], **kw))


def content(out, name="pipeline_shop"):
    return json.loads(out["files"][f"{name}.DataPipeline/pipeline-content.json"])


# ------------------------------------------------------------------ the pipeline definition --------------------------

def test_activities_run_silver_then_gold_then_the_check(shop):
    out = export()
    acts = content(out)["properties"]["activities"]
    assert [a["name"] for a in acts] == ["Silver tables", "Gold views", "Check keys, orphans and sums"]
    assert [a["dependsOn"] for a in acts] == [[], [{"activity": "Silver tables", "dependencyConditions": ["Succeeded"]}],
                                              [{"activity": "Gold views", "dependencyConditions": ["Succeeded"]}]]
    assert all(a["type"] == "TridentNotebook" and a["policy"]["retry"] == 0 for a in acts)
    assert [e["folder"] for e in out["items"]] == ["silver_shop.Notebook", "gold_shop.Notebook", "pipeline_shop_check.Notebook",
                                                   "pipeline_shop.DataPipeline"]
    assert out["pipeline"]["steps"] == ["Silver tables: silver_shop", "Gold views: gold_shop", "Check keys, orphans and sums: pipeline_shop_check"]


def test_the_activities_name_the_notebooks_the_existing_drafts_produce(shop):
    out = export(names={"create_silver_notebook": "silver_shop", "create_gold_views": "gold_shop"})
    files = {**out["files"], **json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", items=["create_silver_notebook"]))["files"]}
    ids = [a["typeProperties"]["notebookId"] for a in content(out)["properties"]["activities"]]
    folders = ["silver_shop.Notebook", "gold_shop.Notebook", "pipeline_shop_check.Notebook"]
    assert ids == [json.loads(files[f"{f}/.platform"])["config"]["logicalId"] for f in folders]
    assert all(a["typeProperties"]["workspaceId"] == pipeline.ZERO_WORKSPACE for a in content(out)["properties"]["activities"])
    # the notebooks are the drafts' own, unchanged: no transformation is added for the pipeline
    assert files["silver_shop.Notebook/notebook-content.py"] == json.loads(server.silver_notebook_draft("Sales", "shop_lh", schema="shop"))["notebook"]["content"]
    assert files["gold_shop.Notebook/notebook-content.py"] == json.loads(server.gold_views_draft("Sales", "shop_lh", schema="shop"))["notebook"]["content"]
    # given names travel into the references
    named = export(names={"create_silver_notebook": "s1", "create_gold_views": "g1", "pipeline": "nightly_build"})
    acts = content(named, "nightly_build")["properties"]["activities"]
    assert [a["typeProperties"]["notebookId"] for a in acts] == [git_export.logical_id("Notebook", n) for n in ("s1", "g1", "nightly_build_check")]
    assert "nightly_build_check.Notebook/notebook-content.py" in named["files"]


def test_the_definition_parses_against_the_documented_shape(shop):
    out = export()
    text = out["files"]["pipeline_shop.DataPipeline/pipeline-content.json"]
    doc = json.loads(text)
    jsonschema.validate(doc, pipeline.SHAPE, format_checker=jsonschema.FormatChecker())
    names = [a["name"] for a in doc["properties"]["activities"]]
    for i, a in enumerate(doc["properties"]["activities"]):
        assert all(d["activity"] in names[:i] for d in a["dependsOn"])            # only on activities before it: no cycle
    pf = json.loads(out["files"]["pipeline_shop.DataPipeline/.platform"])
    assert pf["metadata"] == {"type": "DataPipeline", "displayName": "pipeline_shop"}
    # the REST body has the parts of fabric-rest-api-specs' CreateDataPipeline example: pipeline-content.json and .platform
    body = notebook.pipeline_envelope("pipeline_shop", doc)
    assert [p["path"] for p in body["definition"]["parts"]] == ["pipeline-content.json", ".platform"]
    assert json.loads(base64.b64decode(body["definition"]["parts"][0]["payload"])) == doc
    with pytest.raises(jsonschema.ValidationError):                               # the shape is not a rubber stamp
        jsonschema.validate({"properties": {"activities": [dict(doc["properties"]["activities"][0], type="Notebook")]}}, pipeline.SHAPE)


def test_output_is_deterministic(shop):
    a, b = export(), export()
    assert a == b
    assert server.export_item_definitions("Sales", "shop_lh", schema="shop", items=["pipeline"]) == \
        server.export_item_definitions("Sales", "shop_lh", schema="shop", items=["pipeline"])
    assert pipeline.check_source(pipeline.check_spec(plan(seed.schema("shop")), silver.spec(plan(seed.schema("shop")), INFO),
                                                     gold.spec(plan(seed.schema("shop")), INFO)), "shop_lh.shop", WS, "lh-1", "shop_lh") \
        == a["files"]["pipeline_shop_check.Notebook/notebook-content.py"]


def test_the_draft_says_it_creates_and_schedules_nothing(shop):
    out = export()
    assert "nothing was created and nothing is scheduled" in out["pipeline"]["created"]
    assert "No schedule" in content(out)["properties"]["description"]
    readme = out["files"]["KRUSGRAPH-EXPORT.md"]
    assert "a draft that no tool creates" in readme and "nothing is scheduled" in readme
    assert "fails" in out["pipeline"]["stops"] and "Not run in Fabric" in out["pipeline"]["not_verified"]
    for word in ("minute", "second", "fast", "one click", "one-click", "instant"):
        assert word not in json.dumps({k: out[k] for k in ("pipeline", "items", "notes")}).lower(), word


def test_without_a_lakehouse_with_schemas_there_is_no_pipeline(shop):
    shop["schemas_enabled"] = False
    out = export()
    assert {s["tool"] for s in out["skipped"]} == {"create_gold_views", "pipeline"} and "pipeline" not in out
    shop["type"] = "Warehouse"
    out = export()
    assert all("needs a lakehouse" in s["why"] for s in out["skipped"]) and not any(e["type"] == "DataPipeline" for e in out["items"])
    bad = json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", items=["pipelines"]))
    assert bad["kind"] == "bad_input" and "pipeline" in bad["error"]


def test_the_default_export_is_unchanged(shop):
    out = json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", items=list(server.EXPORTABLE)))
    assert not any(e["tool"] == "pipeline" for e in out["items"]) and "pipeline" not in out


# ------------------------------------------------------------------ the check ---------------------------------------

def shop_plan():
    return plan(seed.schema("shop"))


def spec():
    p = shop_plan()
    return pipeline.check_spec(p, silver.spec(p, INFO, order_by={"orders": "order_date"}), gold.spec(p, INFO))


def lakehouse(break_with=None):
    """SQLite with the silver tables (silver.simulate on the seed with a bronze layer's problems) and the gold views as
    tables of their SELECT with the rules applied (gold.run_select); `break_with(silver_rows, gold_rows)` spoils them."""
    p = shop_plan()
    sim = silver.simulate(silver.spec(p, INFO, order_by={"orders": "order_date"}), seed_rows())["silver"]
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    for s in ("silver", "gold"):
        con.execute(f"ATTACH DATABASE ':memory:' AS {s}")

    def load(schema, table, cols, rows):
        con.execute(f"CREATE TABLE {schema}.`{table}` ({', '.join('`' + c + '`' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.`{table}` VALUES ({', '.join('?' * len(cols))})",
                        [tuple(str(v) if hasattr(v, "isoformat") else v for v in (r.get(c) for c in cols)) for r in rows])
    for t, rows in sim.items():
        load("silver", t, [c.split()[0] for c in seed.SCHEMAS[t].split(", ")], rows)
    g = gold.spec(p, INFO)

    def execute(sql):
        return [dict(r) for r in con.execute(sql).fetchall()]
    views = {v["name"].split(".", 1)[1]: ([c["as"] for c in v["columns"]], gold.run_select(v, g, execute)) for v in g["views"]}
    if break_with:
        break_with(sim, views)
        for t in list(sim):
            con.execute(f"DELETE FROM silver.`{t}`")
            cols = [c.split()[0] for c in seed.SCHEMAS[t].split(", ")]
            con.executemany(f"INSERT INTO silver.`{t}` VALUES ({', '.join('?' * len(cols))})",
                            [tuple(str(v) if hasattr(v, "isoformat") else v for v in (r.get(c) for c in cols)) for r in sim[t]])
    for name, (cols, rows) in views.items():
        load("gold", name, cols, rows)
    return seed.schema("silver"), connection(execute, dialect=DATABRICKS)


def test_the_check_holds_on_what_the_silver_and_gold_steps_produce():
    s = spec()
    assert [k["table"] for k in s["keys"]] == ["categories", "customers", "addresses", "orders", "products", "order_items"]
    assert len(s["relationships"]) == 6
    assert {v["view"]: [x["column"] for x in v["sums"]] for v in s["views"]} == {"audit_log": [], "order_items": ["quantity"], "orders": []}
    result = pipeline.run(s, *lakehouse())
    assert result["passed"] and result["failures"] == [] and result["lines"][-1] == "The check holds."
    items = next(j for j in result["joins"] if j["view"] == "gold.order_items")
    assert items["rows_before"] == items["rows_after"] > 0 and items["sums"][0]["before"] == items["sums"][0]["after"]
    pipeline.raise_if_failed(result)                                              # nothing to stop


@pytest.mark.parametrize("spoil,expected", [
    (lambda sim, views: sim["customers"].append(dict(sim["customers"][0])), "key customers(customer_id): not unique"),
    (lambda sim, views: sim["orders"].append(dict(sim["orders"][0], order_id=None)), "key orders(order_id): not a key"),
    (lambda sim, views: sim["order_items"].append({"order_id": 4242, "line_no": 1, "product_id": 1, "quantity": 1.0}),
     "order_items.order_id -> orders: 1 of"),
    (lambda sim, views: views["order_items"][1].append(dict(views["order_items"][1][0])), "gold.order_items: "),     # the join doubled a row
    (lambda sim, views: views["order_items"][1].pop(), "gold.order_items: "),                                        # a rule dropped a row
    (lambda sim, views: views["order_items"][1].__setitem__(0, dict(views["order_items"][1][0], quantity=99.0)),
     "gold.order_items: SUM(quantity)"),
])
def test_the_check_stops_the_pipeline_when_keys_orphans_or_sums_do_not_hold(spoil, expected):
    result = pipeline.run(spec(), *lakehouse(spoil))
    assert not result["passed"] and any(f.startswith(expected) for f in result["failures"]), result["failures"]
    with pytest.raises(pipeline.CheckFailed, match="the pipeline stops"):
        pipeline.raise_if_failed(result)


def test_a_missing_silver_table_fails_the_check():
    schema, execute = lakehouse()
    del schema.tables["orders"]
    with pytest.raises(pipeline.CheckFailed, match="silver tables missing in silver: orders"):
        pipeline.run(spec(), schema, execute)


def test_the_check_notebook_stops_before_it_reports_success():
    cells = pipeline.check_cells(spec(), "shop_lh.shop")
    kinds = [k for k, _ in cells]
    assert kinds == ["markdown", "parameters", "code", "code", "code", "code"]
    assert "_inlineInstallationEnabled" not in json.dumps(pipeline.pipeline_content("s", "g", "c", "x"))   # nothing to install
    last = cells[-1][1]
    assert last.index("raise_if_failed(result)") < last.index("notebookutils.notebook.exit")
    assert "only reads" in cells[0][1] and "nothing is installed" in cells[0][1]
    assert cells[3][1].endswith(pipeline.CHECK_CODE)                              # the code the tests below run, verbatim
    # the setup cell is valid Python that holds the spec as data
    ns = {"SILVER_SCHEMA": "silver", "GOLD_SCHEMA": "gold"}
    exec(cells[2][1], ns)
    assert ns["CHECK"] == dict({k: spec()[k] for k in ("keys", "relationships", "views")}, silver_schema="silver", gold_schema="gold")


# ------------------------------------------------------------------ n140: the check notebook is self-contained --------
# The first live run (7 November 2026): silver_shop and gold_shop succeeded, pipeline_shop_check failed with
# "ImportError: cannot import name 'pipeline' from 'fabric_backend'": its %pip installed the published release, which is
# older than main and has no pipeline module. The notebook now carries the check as plain Python and installs nothing.

def check_source():
    p = shop_plan()
    return pipeline.check_source(pipeline.check_spec(p, silver.spec(p, INFO), gold.spec(p, INFO)), "shop_lh.shop", WS, "lh-1", "shop_lh")


def test_the_check_notebook_installs_nothing_and_imports_nothing_of_the_library():
    text = check_source()
    assert "%pip" not in text and "pip install" not in text.lower() and "fabric_backend" not in text and "fabric-backend" not in text
    assert "github" not in text.lower() and "http" not in text.lower()         # nothing is fetched at run time
    for kind, code in notebook.parse(text):
        if kind == "markdown":
            continue
        assert not code.lstrip().startswith(("%", "!")), code[:40]
        imported = {n.split(".")[0] for line in code.splitlines() for n in
                    (line.split()[1:2] if line.lstrip().startswith(("import ", "from ")) else [])}
        assert imported <= {"json", "math"}, imported                              # the standard library only


class FakeSpark:
    """spark.sql and spark.catalog.tableExists over the SQLite lakehouse above, for the notebook's own cells."""
    def __init__(self, execute, tables):
        self._execute = execute
        silver = {f"`silver`.`{t}`".lower() for t in tables}

        class Catalog:
            @staticmethod
            def tableExists(name):
                if name.lower().startswith("`silver`."):
                    return name.lower() in silver
                try:
                    execute(f"SELECT 1 FROM {name} LIMIT 1")
                    return True
                except Exception:  # noqa: BLE001
                    return False
        self.catalog = Catalog()

    def sql(self, text):
        rows = self._execute(text)
        return type("DF", (), {"collect": lambda _self: [type("Row", (), {"asDict": lambda _r, d=d: dict(d)})() for d in rows]})()


def guarded_builtins():
    import builtins

    def guarded(name, *a, **k):
        if name.split(".")[0] == "fabric_backend":
            raise ImportError(f"the check notebook imported {name}")
        return builtins.__import__(name, *a, **k)
    return dict(vars(builtins), __import__=guarded)


def run_notebook(break_with=None):
    schema, execute = lakehouse(break_with)
    ns = {"spark": FakeSpark(execute, [t.name for t in schema]), "__builtins__": guarded_builtins()}
    for kind, code in notebook.parse(check_source()):
        if kind != "markdown":
            exec(compile(code, "<pipeline_shop_check>", "exec"), ns)
    return ns


def test_the_check_notebooks_own_cells_pass_on_what_the_steps_produce(capsys):
    ns = run_notebook()
    assert ns["result"]["passed"] and ns["result"]["lines"][-1] == "The check holds."
    out = capsys.readouterr().out
    assert "Keys in silver: 6 of 6 unique and never NULL." in out and "References in silver: 6 of 6 without orphans." in out
    assert "Gold views: 3 of 3 keep the rows and sums of their fact table." in out and out.rstrip().endswith("passed")


def test_the_check_notebook_raises_a_readable_error_on_an_orphan_and_a_sum_mismatch():
    def spoil(sim, views):
        sim["order_items"].append({"order_id": 4242, "line_no": 1, "product_id": 1, "quantity": 1.0})      # an orphan
        views["order_items"][1][0] = dict(views["order_items"][1][0], quantity=99.0)                      # a gold sum mismatch
    with pytest.raises(Exception) as e:
        run_notebook(spoil)
    assert type(e.value).__name__ == "CheckFailed"
    msg = str(e.value)
    assert msg.startswith("The check failed, so the pipeline stops: ")
    assert "order_items.order_id -> orders: 1 of " in msg and "find no row in orders(order_id) (orphans)" in msg
    assert "gold.order_items: SUM(quantity) is " in msg and " in silver.order_items" in msg


def test_the_check_reads_the_names_the_silver_and_gold_notebooks_write():
    """The silver notebook writes `<silver_schema>`.`<table>` (silver.target_parts) and the gold notebook creates
    `<gold_schema>`.`<fact, lowercased>` (gold.spec's view names); the check asks for exactly those."""
    p = shop_plan()
    s, g = silver.spec(p, INFO, order_by={"orders": "order_date"}), gold.spec(p, INFO)
    c = pipeline.check_spec(p, s, g)
    asked = []
    pipeline._CHECK["check"](c, lambda sql: [{"n": 0, "nulls": 0, "d": 0, "o": 0}], lambda name: asked.append(name) or True)
    written = {f"`{s['silver_schema']}`.`{t['table']}`" for t in s["tables"]}
    created = {".".join(f"`{x}`" for x in v["name"].split(".", 1)) for v in g["views"]}
    assert created <= set(asked) and set(asked) - created <= written


def test_a_missing_gold_view_fails_the_check_notebook_with_its_name():
    schema, execute = lakehouse()
    spark = FakeSpark(execute, [t.name for t in schema])
    spark.catalog.tableExists = lambda name, real=spark.catalog.tableExists: name != "`gold`.`orders`" and real(name)
    ns = {"spark": spark, "__builtins__": guarded_builtins()}
    with pytest.raises(Exception, match="gold views missing in gold: orders; the gold notebook did not create them") as e:
        for kind, code in notebook.parse(check_source()):
            if kind != "markdown":
                exec(compile(code, "<pipeline_shop_check>", "exec"), ns)
    assert type(e.value).__name__ == "CheckFailed"
