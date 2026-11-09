"""Round n179: Create from the Krusgraph Model editor, made robust after the founder's live Create of 9 November 2026.

That Create (eight outputs, one request, schema typed "Shop") ended in the browser with only "Failed to fetch" after
about 60 s, while the server went on and created six of the eight items; the report and the API failed and nobody saw
why. Now the editor sends one /workload/v1/build per output (createEach in buildWords.ts, tested in createEach.test.ts
with a slow and a failing fetch), and the engine:

- answers every error on the workload routes as JSON with the CORS headers, and logs the cause (one JSON line);
- with skip_built, shows an output whose items are already in the workspace (built by this Model, or carrying
  Krusgraph's description from a Create whose answer was lost) as already built, and writes nothing for it;
- builds the report on the model created by the previous request (its id), and tries a new model's definition again
  before it gives up, with the reason on the report's own card;
- with finish, gives the data product and the data flow from the created ids, calling no tool;
- lists the lakehouse's schemas with their table counts (POST /workload/v1/schemas), so the schema is picked, not typed.
Fabric REST and the SQL endpoint are the doubles of tests/golden_support.py, with the items a build creates listed."""
import json
import sys

import pytest

pytest.importorskip("jwt")
from starlette.testclient import TestClient  # noqa: E402

import golden_support as gs  # noqa: E402
from test_workload_api import FABRIC_ORIGIN, SRC, WL, FakeJWKS, FakeOBO, keys, tok  # noqa: E402,F401
from test_workload_build import NEW_SM, Fabric  # noqa: E402
from fabric_backend import server, workload_api  # noqa: E402
from fabric_backend.entra import Validator  # noqa: E402

TYPE_OF = {"notebooks": "Notebook", "dataPipelines": "DataPipeline", "semanticModels": "SemanticModel", "reports": "Report",
           "graphQLApis": "GraphQLApi", "ontologies": "Ontology"}


class Workspace(Fabric):
    """The build's Fabric double, with what it creates listed among the workspace's items (as Fabric lists them), and
    `fail_definition` failed reads of the new model's definition before it can be read (None: never readable)."""

    def __init__(self, fail_definition: int | None = 0, items=()):
        super().__init__()
        self.items, self.fail_definition, self.definition_reads = list(items), fail_definition, 0

    def _route(self, method, url, body=None):
        path = url.split("?")[0]
        rest = path.split(f"/workspaces/{gs.WS}/")[-1].split("/") if f"/workspaces/{gs.WS}/" in path else []
        if method == "GET" and rest == ["items"]:
            r = super()._route(method, url, body)
            return gs.Response(200, {"value": r.json()["value"] + self.items})
        if method == "POST" and rest[-1:] == ["getDefinition"] and NEW_SM in rest:
            self.calls.append((method, path))
            self.definition_reads += 1
            if self.fail_definition is None or self.definition_reads <= self.fail_definition:
                return gs.Response(400, {"errorCode": "OperationNotSupportedForItem", "message": "The item is not ready"})
        r = super()._route(method, url, body)
        if method == "POST" and r.status_code == 201 and len(rest) == 1 and rest[0] in TYPE_OF:
            got = r.json()
            iid = NEW_SM if rest[0] == "semanticModels" else f"new-{rest[0]}-{len(self.items)}"
            self.items.append({"id": iid, "displayName": got.get("displayName"), "type": TYPE_OF[rest[0]],
                               "description": (body or {}).get("description", "")})
            return gs.Response(201, {**got, "id": iid})
        return r


@pytest.fixture
def make(keys, monkeypatch):
    import requests
    from starlette.applications import Starlette
    priv, pub = keys
    monkeypatch.setattr(server, "MODEL_DEFINITION_PAUSES", (0, 0, 0))

    def build(fake=None, case_sensitive=False, schemas=("shop",)):
        fake = fake or Workspace()
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        odbc = gs.fake_pyodbc(case_sensitive=case_sensitive, schemas=schemas)
        monkeypatch.setitem(sys.modules, "pyodbc", odbc)
        monkeypatch.setattr(server, "limiter", None)
        app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), FakeOBO()))
        return TestClient(app, raise_server_exceptions=False), fake, priv
    return build


def _post(client, path, body, priv, origin=FABRIC_ORIGIN):
    return client.post(workload_api.PREFIX + path, json=body,
                       headers={"Authorization": f"Bearer {tok(priv)}", "Origin": origin})


def _review(client, priv, src=SRC):
    return _post(client, "/review", src, priv).json()["review"]


def _one(client, priv, rv, output, created=(), src=SRC, **extra):
    body = {**src, "review": rv, "outputs": [output], "dry_run": False, "created": list(created), "skip_built": True, **extra}
    return _post(client, "/build", body, priv)


# ------------------------------------------------------------------ errors carry CORS and a logged cause ----------

def test_an_exception_in_build_still_answers_json_with_the_cors_headers(make, monkeypatch, capsys):
    def boom(req):
        raise MemoryError("out of memory")
    monkeypatch.setattr(workload_api, "run_build", boom)              # before the routes are made: they bind run_build
    client, _, priv = make()
    rv = _review(client, priv)
    r = _post(client, "/build", {**SRC, "review": rv, "outputs": [{"kind": "graphql", "name": "x_api"}], "dry_run": False}, priv)
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["access-control-allow-origin"] == FABRIC_ORIGIN
    out = r.json()
    assert out["kind"] == "unexpected" and "MemoryError" in out["error"] and r.status_code == 502
    logged = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"krusgraph"')]
    assert any(x["event"] == "run_failed" and x["error"] == "MemoryError" for x in logged)


def test_an_exception_outside_the_tool_call_is_json_with_cors_and_logged(make, monkeypatch, capsys):
    client, _, priv = make()

    def broken(*a, **k):
        raise RuntimeError("token cache broke")
    monkeypatch.setattr(server, "workload_tokens", broken)
    r = _post(client, "/build", {**SRC, "review": {"format": "krusgraph-review"}, "outputs": [{"kind": "graphql", "name": "x_api"}]}, priv)
    assert r.status_code == 500
    assert r.headers["access-control-allow-origin"] == FABRIC_ORIGIN
    assert r.json()["kind"] == "unexpected" and "token cache broke" not in r.text
    logged = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{"krusgraph"')]
    assert {"event": "route_failed", "route": "build", "error": "RuntimeError"}.items() <= next(
        x for x in logged if x["event"] == "route_failed").items()


def test_the_preflight_for_build_and_schemas_answers_fabric(make):
    client, _, _ = make()
    for path in ("/build", "/schemas"):
        r = client.options(workload_api.PREFIX + path, headers={"Origin": FABRIC_ORIGIN, "Access-Control-Request-Method": "POST"})
        assert r.status_code == 204 and r.headers["access-control-allow-origin"] == FABRIC_ORIGIN


# ------------------------------------------------------------------ Create, one output per request ------------------

def test_create_one_output_at_a_time_and_the_report_on_the_model_just_created(make, capsys):
    client, fake, priv = make()
    rv = _review(client, priv)
    created = []
    for o in ({"kind": "silver_notebook", "name": "demo_lh_silver"}, {"kind": "semantic_model", "name": "demo_lh_model"}):
        r = _one(client, priv, rv, o, created)
        assert r.status_code == 200, r.text
        card = r.json()["outputs"][0]
        assert card["output"] == o["kind"] and not card.get("refusal") and "error" not in card["answer"], card
        created += r.json()["created"]
    model = next(c for c in created if c["output"] == "semantic_model")
    assert model["id"] == NEW_SM
    r = _one(client, priv, rv, {"kind": "report", "name": "demo_lh_report", "model": model["id"]}, created)
    card = r.json()["outputs"][0]
    assert "error" not in card["answer"], card["answer"]
    assert card["created"] and card["created"][0]["type"] == "Report"
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith('{"krusgraph"')]
    assert [x["output"] for x in lines if x["event"] == "build_output"][-3:] == ["silver_notebook", "semantic_model", "report"]
    assert all("seconds" in x and "peak_rss_mb" in x for x in lines if x["event"] == "build_output")


def test_a_new_model_whose_definition_is_not_readable_at_first_is_read_again(make):
    client, fake, priv = make(Workspace(fail_definition=2))
    rv = _review(client, priv)
    created = _one(client, priv, rv, {"kind": "semantic_model", "name": "demo_lh_model"}).json()["created"]
    r = _one(client, priv, rv, {"kind": "report", "name": "demo_lh_report", "model": NEW_SM}, created)
    card = r.json()["outputs"][0]
    assert "error" not in card["answer"] and card["created"], card
    assert fake.definition_reads == 3


def test_a_report_whose_model_stays_unreadable_says_why_on_its_own_card(make):
    client, fake, priv = make(Workspace(fail_definition=None))
    rv = _review(client, priv)
    created = _one(client, priv, rv, {"kind": "semantic_model", "name": "demo_lh_model"}).json()["created"]
    r = _one(client, priv, rv, {"kind": "report", "name": "demo_lh_report", "model": NEW_SM}, created)
    a = r.json()["outputs"][0]["answer"]
    assert a["kind"] == "source_not_ready"
    assert "OperationNotSupportedForItem" in a["error"] and "4 tries" in a["error"]
    assert "Create again in a minute" in a["hint"]
    assert not [i for i in fake.items if i["type"] == "Report"]


def test_a_rerun_skips_what_a_lost_create_already_built_and_writes_nothing_for_it(make):
    """The live case: the items exist (Krusgraph's description), but outputs.json never got their ids."""
    lost = [{"id": "nb-silver", "displayName": "demo_lh_silver", "type": "Notebook",
             "description": "Silver tables for demo_lh.shop, generated by Krusgraph from the plan"},
            {"id": NEW_SM, "displayName": "demo_lh_model", "type": "SemanticModel", "description": "Created by Krusgraph from demo_lh (shop)"}]
    client, fake, priv = make(Workspace(items=lost))
    rv = _review(client, priv)
    fake.created.clear()
    for o, iid in (({"kind": "silver_notebook", "name": "demo_lh_silver"}, "nb-silver"),
                   ({"kind": "semantic_model", "name": "demo_lh_model"}, NEW_SM)):
        card = _one(client, priv, rv, o).json()["outputs"][0]
        assert card["already_built"] is True and card["created"][0]["id"] == iid and not card.get("refusal"), card
    assert fake.created == []                                          # nothing written again
    r = _one(client, priv, rv, {"kind": "report", "name": "demo_lh_report", "model": NEW_SM})
    assert r.json()["outputs"][0]["created"]                            # only the one that failed is tried


def test_an_item_of_that_name_someone_else_made_is_still_refused(make):
    theirs = [{"id": "nb-x", "displayName": "demo_lh_silver", "type": "Notebook", "description": "my own notebook"}]
    client, fake, priv = make(Workspace(items=theirs))
    rv = _review(client, priv)
    card = _one(client, priv, rv, {"kind": "silver_notebook", "name": "demo_lh_silver"}).json()["outputs"][0]
    assert card["refusal"]["kind"] == "already_exists" and not card.get("already_built")


def test_finish_gives_the_product_and_the_flow_from_the_created_ids_and_calls_no_tool(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    outputs = [{"kind": "silver_notebook", "name": "demo_lh_silver"}, {"kind": "gold_views", "name": "demo_lh_gold"},
               {"kind": "semantic_model", "name": "demo_lh_model"}]
    created = []
    for o in outputs:
        created += _one(client, priv, rv, o, created).json()["created"]
    fake.created.clear()
    r = _post(client, "/build", {**SRC, "review": rv, "outputs": outputs, "dry_run": False, "created": created,
                                 "product": {"name": "Shop"}, "finish": True}, priv)
    out = r.json()
    assert r.status_code == 200, out
    assert fake.created == []
    assert {i["id"] for i in out["product"]["items"]} == {c["id"] for c in created}
    assert out["flow"]["nodes"] and out["refused"] == 0
    model = next(n for n in out["flow"]["nodes"] if n["id"] == "item:semantic_model")
    assert model["lines"] == ["reads the source tables in shop (bronze) directly, not the gold views built in this run"]
    assert any("later option" in n for n in out["flow"]["notes"])


def test_finish_needs_dry_run_false(make):
    client, _, priv = make()
    r = _post(client, "/build", {**SRC, "review": {}, "outputs": [{"kind": "graphql", "name": "a"}], "finish": True}, priv)
    assert r.status_code == 400 and "finish" in r.json()["error"]


# ------------------------------------------------------------------ the schema, typed as Shop, everywhere ----------

def test_the_api_and_the_flow_use_the_lakehouse_s_spelling_when_shop_was_typed(make):
    client, fake, priv = make(case_sensitive=True)
    src = {**SRC, "schema": "Shop"}
    rv = _review(client, priv, src)
    r = _post(client, "/build", {**src, "review": rv, "dry_run": True, "outputs": [
        {"kind": "graphql", "name": "demo_lh_api"}, {"kind": "silver_notebook", "name": "demo_lh_silver"},
        {"kind": "gold_views", "name": "demo_lh_gold"}, {"kind": "semantic_model", "name": "demo_lh_model"}]}, priv)
    out = r.json()
    assert out["refused"] == 0, [c.get("refusal") or c["answer"].get("error") for c in out["outputs"]]
    text = json.dumps(out)
    assert "Shop." not in text and "[Shop]" not in text and '"Shop"' not in text.replace('"asked": "Shop"', "")
    bronze = [n["label"] for n in out["flow"]["nodes"] if n["column"] == "bronze"]
    assert bronze and all(b.startswith("shop.") for b in bronze)


# ------------------------------------------------------------------ the schemas to pick from ----------------------

def test_schemas_lists_each_schema_with_its_tables_and_preselects_the_only_one_with_tables(make):
    client, _, priv = make()
    r = _post(client, "/schemas", {"workspace": gs.WS, "source": "demo_lh"}, priv)
    out = r.json()
    assert r.status_code == 200, out
    assert out["schemas"] == [{"schema": "dbo", "tables": 0}, {"schema": "shop", "tables": 7}]
    assert out["preselect"] == "shop" and "Nothing was created" in out["note"]


def test_schemas_gives_the_exact_names_and_does_not_choose_between_two_that_differ_by_case(make):
    client, _, priv = make(case_sensitive=True, schemas=("Shop", "shop"))
    out = _post(client, "/schemas", {"workspace": gs.WS, "source": "demo_lh"}, priv).json()
    assert [x["schema"] for x in out["schemas"]] == ["Shop", "dbo", "shop"]
    assert out["preselect"] is None


def test_preselect():
    p = workload_api.preselect
    assert p([{"schema": "dbo", "tables": 3}]) == "dbo"
    assert p([{"schema": "dbo", "tables": 0}]) == "dbo"
    assert p([{"schema": "dbo", "tables": 0}, {"schema": "shop", "tables": 7}]) == "shop"
    assert p([{"schema": "sap", "tables": 9}, {"schema": "shop", "tables": 7}]) is None
    assert p([]) is None


def test_schemas_falls_back_to_the_schemas_with_tables_when_schemata_cannot_be_read(make, monkeypatch):
    client, _, priv = make()
    monkeypatch.setattr(workload_api, "SCHEMATA_SQL", "SELECT broken FROM nowhere_at_all")
    out = _post(client, "/schemas", {"workspace": gs.WS, "source": "demo_lh"}, priv).json()
    assert out["schemas"] == [{"schema": "shop", "tables": 7}] and out["preselect"] == "shop"


# ------------------------------------------------------------------ generated code: the rule, not the certainty ---

def test_generated_gold_sql_and_silver_code_name_the_rule_without_a_certainty_number(make):
    client, _, priv = make()
    rv = _review(client, priv)
    r = _post(client, "/build", {**SRC, "review": rv, "dry_run": True, "outputs": [
        {"kind": "silver_notebook", "name": "demo_lh_silver"}, {"kind": "gold_views", "name": "demo_lh_gold"}]}, priv)
    cards = {c["output"]: c["answer"] for c in r.json()["outputs"]}
    code = json.dumps(cards["gold_views"]) + json.dumps(cards["silver_notebook"])
    assert "rule R1" in code and "certainty" not in code


def test_a_pipeline_built_on_its_own_runs_the_notebooks_chosen_with_it(make):
    """Each request carries every chosen output and builds `only` its own: the pipeline runs demo_lh_silver and
    demo_lh_gold (chosen with it), not the default silver_shop and gold_shop."""
    client, fake, priv = make()
    rv = _review(client, priv)
    outputs = [{"kind": "silver_notebook", "name": "demo_lh_silver"}, {"kind": "gold_views", "name": "demo_lh_gold"},
               {"kind": "pipeline", "name": "demo_lh_pipeline"}]
    created = []
    for o in outputs:
        r = _post(client, "/build", {**SRC, "review": rv, "outputs": outputs, "only": [o["kind"]], "dry_run": False,
                                     "created": created, "skip_built": True}, priv)
        out = r.json()
        assert r.status_code == 200 and [c["output"] for c in out["outputs"]] == [o["kind"]], out
        assert out["flow"] is None
        created += out["created"]
    steps = json.dumps(out["outputs"][0]["answer"])
    assert "demo_lh_silver" in steps and "demo_lh_gold" in steps and "silver_shop" not in steps
    assert {c["name"] for c in created} >= {"demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline"}
    bad = _post(client, "/build", {**SRC, "review": rv, "outputs": outputs, "only": ["report"], "dry_run": False}, priv)
    assert bad.status_code == 400 and "only" in bad.json()["error"]
