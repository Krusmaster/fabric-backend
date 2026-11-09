"""Round n174: the Krusgraph Model builds everything the MCP tools can (fabric_backend/workload_api.py, run_build_many).

One /workload/v1/build with outputs [{kind, name}] runs each output through its MCP tool on the plan the review left:
dry run first, one card per output in ORDER (the model before its report), the permissions each needs and kind consent
when the token lacks one, never writing over an item this Model did not build, a data product only from domain_draft's
proposal and the build's own answers, and the data flow (bronze -> silver -> gold, the pipeline) whose nodes and edges
are the engine's silver, gold and pipeline output on seed.py's shop schema, each node's code exactly the dry run's.
Fabric REST and the SQL endpoint are the doubles of tests/golden_support.py."""
import base64
import json
import sys

import pytest

jwt = pytest.importorskip("jwt")
from starlette.testclient import TestClient  # noqa: E402

import golden_support as gs  # noqa: E402
from test_workload_api import FABRIC_ORIGIN, SRC, WL, FakeJWKS, keys, tok  # noqa: E402,F401
from fabric_backend import data_flow, gold, pipeline, server, silver, workload_api  # noqa: E402
from fabric_backend.entra import Validator  # noqa: E402

ALL = [{"kind": "report", "name": "shop_report"}, {"kind": "semantic_model", "name": "shop_sales"},
       {"kind": "pipeline", "name": "shop_flow"}, {"kind": "gold_views", "name": "shop_gold"},
       {"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "graphql", "name": "shop_model_api"},
       {"kind": "ontology", "name": "shop_onto"}, {"kind": "data_agent", "name": "shop_agent"}]
NEW_SM = "bbbbbbbb-0000-0000-0000-000000000001"             # Fabric's ids are GUIDs; create_report takes a model by its id
EVERY_SCOPE = "Workspace.Read.All Lakehouse.Read.All Item.ReadWrite.All"


def _jwt(scp: str) -> str:
    part = base64.urlsafe_b64encode(json.dumps({"scp": scp}).encode()).decode().rstrip("=")
    return f"h.{part}.s"


class ScopedOBO:
    """The on-behalf-of exchange of test_workload_api, with a Fabric token that carries `scp` (None: not a JWT)."""

    def __init__(self, scp: str | None):
        self.scp, self.calls = scp, []

    def token(self, user_token, tenant, scope):
        self.calls.append((tenant, scope))
        return _jwt(self.scp) if self.scp is not None and "fabric" in scope else f"obo:{scope}"


class Fabric(gs.FakeFabric):
    """The golden workspace, plus what a report needs: creating one, and the definition of a model created in the build."""

    def _route(self, method, url, body=None):
        path = url.split("?")[0]
        if method == "POST" and path.endswith(f"/workspaces/{gs.WS}/reports"):
            self.calls.append((method, path))
            self.created.append({"route": "reports", "body": body})
            return gs.Response(201, {"id": "new-reports", "displayName": (body or {}).get("displayName")})
        if method == "POST" and path.endswith(f"/workspaces/{gs.WS}/semanticModels"):
            self.calls.append((method, path))
            self.created.append({"route": "semanticModels", "body": body})
            return gs.Response(201, {"id": NEW_SM, "displayName": (body or {}).get("displayName")})
        if method == "POST" and path.endswith(f"/semanticModels/{NEW_SM}/getDefinition"):
            self.calls.append((method, path))
            return gs.Response(200, {"definition": {"parts": gs._model_parts()}})
        return super()._route(method, url, body)


@pytest.fixture
def make(keys, monkeypatch):
    import requests
    from starlette.applications import Starlette
    priv, pub = keys

    def build(scp=None):
        fake = Fabric()
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
        monkeypatch.setattr(server, "limiter", None)
        obo = ScopedOBO(scp)
        app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), obo))
        return TestClient(app), fake, priv
    return build


def _post(client, path, body, token):
    return client.post(workload_api.PREFIX + path, json=body, headers={"Authorization": f"Bearer {token}", "Origin": FABRIC_ORIGIN})


def _review(client, priv, decisions=None):
    return _post(client, "/review", {**SRC, "decisions": decisions or []}, tok(priv)).json()["review"]


def _writes(fake):
    return [c for c in fake.calls if c[0] != "GET" and not c[1].endswith("/getDefinition")]


def _build(client, priv, outputs, **extra):
    rv = extra.pop("review", None) or _review(client, priv)
    r = _post(client, "/build", {**SRC, "review": rv, "outputs": outputs, **extra}, tok(priv))
    return r, rv


# ------------------------------------------------------------------ the dry run, per kind ---------------------------

def test_a_dry_run_of_every_output_gives_one_card_each_in_order_and_writes_nothing(make):
    client, fake, priv = make()
    _review(client, priv)
    fake.calls.clear()
    r, _ = _build(client, priv, ALL)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["dry_run"] is True and out["refused"] == 0, [c.get("refusal") or c["answer"].get("error") for c in out["outputs"]]
    assert out["order"] == list(workload_api.ORDER)                     # the flow, then the model before its report
    assert out["order"].index("semantic_model") < out["order"].index("report")
    for card in out["outputs"]:
        k = card["output"]
        assert card["label"] == workload_api.KINDS[k]["label"] and card["would"] == "create" and card["dry_run"] is True
        assert card["permissions"]["needs"] == [" or ".join(a) for a in workload_api.KINDS[k]["needs"]]
        assert card["permissions"]["missing"] is None                   # this token is not a JWT: unknown, Fabric decides
        assert "Execute" not in json.dumps(card["permissions"]["needs"])
        assert card["answer"].get("dry_run") is True and "error" not in card["answer"], (k, card["answer"])
        assert "created" not in card
    cards = {c["output"]: c for c in out["outputs"]}
    assert cards["data_agent"]["answer"]["agent"]["name"] == "shop_agent"
    assert cards["report"]["answer"]["report"]["bound_to"] == {"semantic_model": "shop_sales", "id": None, "built_in_this_build": True}
    assert cards["report"]["answer"]["report"]["visuals"]
    assert cards["pipeline"]["answer"]["steps"][0].endswith("shop_silver") and cards["pipeline"]["answer"]["steps"][1].endswith("shop_gold")
    assert "Nothing was created" in out["note"]
    assert _writes(fake) == [] and fake.created == []


def test_each_card_is_the_tools_own_dry_run(make):
    """The card's answer is what the MCP tool answers to the same arguments (the review carried as keys and confirmed)."""
    client, fake, priv = make()
    out, rv = _build(client, priv, [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "ontology", "name": "shop_onto"}])
    cards = {c["output"]: c for c in out.json()["outputs"]}
    tools = server.workload_tokens(workload_api.Tokens(ScopedOBO(None), "t", gs.WS))
    with tools:
        direct = json.loads(server.create_silver_notebook(gs.WS, "demo_lh", "shop_silver", "shop"))
        onto = json.loads(server.create_ontology(gs.WS, "demo_lh", "shop_onto", "shop"))
    assert cards["silver_notebook"]["answer"]["notebook"]["content"] == direct["notebook"]["content"]
    assert cards["ontology"]["answer"]["parts"] == onto["parts"]


def test_the_review_s_rejections_reach_every_output(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    rel = next(it for it in rv["items"] if it["type"] == "relationship" and it["source"] == "orders")
    rv = _review(client, priv, [{"item": rel["id"], "review": "rejected"}])
    out = _build(client, priv, [{"kind": "semantic_model", "name": "shop_sales"}, {"kind": "silver_notebook", "name": "s1"}],
                 review=rv)[0].json()
    assert [x["id"] for x in out["left_out_by_review"]] == [rel["id"]]
    cards = {c["output"]: c for c in out["outputs"]}
    rels = cards["semantic_model"]["answer"]["parts"]["definition/relationships.tmdl"]
    assert f"fromColumn: {rel['source']}.{rel['columns'][0]}" not in rels
    checks = [c for s in cards["silver_notebook"]["answer"]["steps"] if s["table"] == "orders" for c in s["checks"]]
    assert rel["columns"] not in [c["columns"] for c in checks]


@pytest.mark.parametrize("outputs, word", [
    ([{"kind": "dashboard", "name": "x"}], "kind one of"),
    ([{"kind": "report", "name": "r"}], "needs a semantic model"),
    ([{"kind": "semantic_model", "name": "bad name"}], "letters, digits"),
    ([{"kind": "silver_notebook", "name": "same"}, {"kind": "gold_views", "name": "same"}], "two different names"),
    ([{"kind": "ontology", "name": "a"}, {"kind": "ontology", "name": "b"}], "twice"),
])
def test_bad_outputs_are_refused_before_anything_is_read(make, outputs, word):
    client, fake, priv = make()
    r = _post(client, "/build", {**SRC, "review": {"format": "krusgraph-review"}, "outputs": outputs}, tok(priv))
    assert r.status_code == 400 and word in r.json()["error"] and fake.calls == []


# ------------------------------------------------------------------ refusal to overwrite -----------------------------

def test_an_item_of_the_same_name_not_built_by_this_model_is_never_written(make):
    client, fake, priv = make()
    for dry in (True, False):
        out = _build(client, priv, [{"kind": "semantic_model", "name": "shop_model"}, {"kind": "graphql", "name": "shop_api"}],
                     dry_run=dry)[0].json()
        for card in out["outputs"]:
            assert card["refusal"]["kind"] == "already_exists" and "not built by this Krusgraph Model" in card["refusal"]["error"]
            assert "answer" not in card
    assert _writes(fake) == [] and fake.created == []


def test_an_item_this_model_built_is_updated_in_place_and_a_report_never_is(make):
    client, fake, priv = make()
    mine = [{"type": "SemanticModel", "id": gs.SM, "name": "shop_model", "workspace": gs.WS}]
    out = _build(client, priv, [{"kind": "semantic_model", "name": "shop_model"}], created=mine)[0].json()
    assert out["outputs"][0]["would"] == "update" and "refusal" not in out["outputs"][0]
    assert out["outputs"][0]["updates_in_place"] is True


# ------------------------------------------------------------------ permissions and consent --------------------------

def test_a_missing_permission_is_named_in_the_dry_run_and_refused_by_create(make):
    client, fake, priv = make(scp="Workspace.Read.All Lakehouse.Read.All Notebook.ReadWrite.All")
    outputs = [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "pipeline", "name": "shop_flow"}]
    out = _build(client, priv, outputs)[0].json()
    cards = {c["output"]: c for c in out["outputs"]}
    assert cards["silver_notebook"]["permissions"]["missing"] == [] and "consent" not in cards["silver_notebook"]
    assert cards["pipeline"]["permissions"]["missing"] == ["DataPipeline.ReadWrite.All"]
    assert cards["pipeline"]["consent"]["kind"] == "consent" and cards["pipeline"]["consent"]["scope"] == "DataPipeline.ReadWrite.All"
    fake.calls.clear()
    out = _build(client, priv, outputs, dry_run=False)[0].json()
    cards = {c["output"]: c for c in out["outputs"]}
    refusal = cards["pipeline"]["refusal"]
    assert refusal["kind"] == "consent" and refusal["scope"] == "DataPipeline.ReadWrite.All"
    steps = " ".join(refusal["entra_steps"])
    assert WL.client_id in steps and "Krusgraph workload (dev)" in steps and "Power BI Service" in steps
    assert "Grant admin consent" in steps and "DataPipeline.ReadWrite.All" in steps
    assert "Execute" not in steps
    routes = [c["route"] for c in fake.created]
    assert routes == ["notebooks"]                                     # the silver notebook only; the pipeline wrote nothing
    assert out["refused"] == 1 and [c["output"] for c in out["created"]] == ["silver_notebook"]


def test_item_readwrite_all_covers_every_output(make):
    client, fake, priv = make(scp=EVERY_SCOPE)
    out = _build(client, priv, ALL)[0].json()
    assert all(c["permissions"]["missing"] == [] for c in out["outputs"])


# ------------------------------------------------------------------ create, the result and the data product ----------

def test_create_builds_the_flow_the_model_and_its_report_and_says_what_is_left(make):
    client, fake, priv = make(scp=EVERY_SCOPE)
    outputs = [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "gold_views", "name": "shop_gold"},
               {"kind": "pipeline", "name": "shop_flow"}, {"kind": "semantic_model", "name": "shop_sales"},
               {"kind": "report", "name": "shop_report"}, {"kind": "ontology", "name": "shop_onto"}]
    out = _build(client, priv, outputs, dry_run=False, product={"name": "Shop sales"})[0].json()
    assert out["dry_run"] is False and out["refused"] == 0, [c.get("refusal") or c["answer"].get("error") for c in out["outputs"]]
    cards = {c["output"]: c for c in out["outputs"]}
    assert [c["type"] for c in cards["pipeline"]["created"]] == ["DataPipeline", "Notebook", "Notebook", "Notebook"]
    assert cards["semantic_model"]["created"] == [{"type": "SemanticModel", "id": NEW_SM, "name": "shop_sales",
                                                   "workspace": gs.WS, "output": "semantic_model"}]
    assert cards["report"]["created"][0]["id"] == "new-reports"
    assert cards["report"]["answer"]["report"]["bound_to"]["id"] == NEW_SM
    # the portal steps are the tools' own
    assert cards["semantic_model"]["portal_steps"][0].startswith("Refresh the model once")
    assert cards["report"]["portal_steps"] == list(server.REPORT_AFTER_CREATION)
    assert cards["silver_notebook"]["portal_steps"] == cards["silver_notebook"]["answer"]["run"]
    assert cards["pipeline"]["portal_steps"][0] == pipeline.NOT_RUN and "schedule" in cards["pipeline"]["portal_steps"][1]
    # nothing ran and nothing was scheduled
    assert not [c for c in fake.calls if "/jobs/" in c[1] or "schedules" in c[1]]
    # the data product: the created items with their ids, the plan's version, the domains domain_draft proposes
    prod = out["product"]
    ids = {x["id"] for c in out["outputs"] for x in c["created"]}
    assert {x["id"] for x in prod["items"]} == ids and {x["id"] for x in out["created"]} == ids
    assert prod["owner"] is None and prod["plan"]["plan_id"] and prod["plan"]["schema_fingerprint"].startswith("sha256:")
    with server.workload_tokens(workload_api.Tokens(ScopedOBO(None), "t", gs.WS)):
        domains = json.loads(server.domain_draft(gs.WS, "demo_lh", "shop"))["domains"]
    assert [(d["name"], d["tables"]) for d in prod["domains"]] == [(d["name"], d["tables"]) for d in domains]


def test_the_product_of_a_dry_run_lists_only_what_would_be_built(make):
    client, fake, priv = make()
    out = _build(client, priv, [{"kind": "semantic_model", "name": "shop_model"}, {"kind": "ontology", "name": "shop_onto"}],
                 product={"name": "Shop"})[0].json()
    assert [(x["output"], x["would"]) for x in out["product"]["items"]] == [("ontology", "create")]   # shop_model is not ours
    assert "id" not in json.dumps(out["product"]["items"])


# ------------------------------------------------------------------ the data flow ------------------------------------

def test_the_flow_is_the_engine_s_silver_gold_and_pipeline_output(make):
    client, fake, priv = make()
    outputs = [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "gold_views", "name": "shop_gold"},
               {"kind": "pipeline", "name": "shop_flow"}, {"kind": "semantic_model", "name": "shop_sales"},
               {"kind": "report", "name": "shop_report"}]
    out = _build(client, priv, outputs)[0].json()
    cards = {c["output"]: c for c in out["outputs"]}
    flow = out["flow"]
    nodes = {n["id"]: n for n in flow["nodes"]}
    # silver: one node per step of the dry run, with exactly the notebook's cell
    steps = cards["silver_notebook"]["answer"]["steps"]
    silver_nodes = [n for n in flow["nodes"] if n["column"] == "silver"]
    assert [n["table"] for n in silver_nodes] == [s["table"] for s in steps]
    assert [n["label"] for n in silver_nodes] == [s["writes"] for s in steps]
    content = cards["silver_notebook"]["answer"]["notebook"]["content"]
    for n in silver_nodes:
        assert n["code"] in content and n["code"].startswith(f"# ---- {n['table']} ->")
        assert {"from": f"bronze:{n['table']}", "to": n["id"], "label": "cleaned", "built": True} in flow["edges"]
    # gold: one node per view, its code the dry run's SQL, an edge from every silver table it joins, on its columns
    views = cards["gold_views"]["answer"]["views"]
    gold_nodes = [n for n in flow["nodes"] if n["column"] == "gold"]
    assert [(n["label"], n["code"]) for n in gold_nodes] == [(v["name"], v["sql"]) for v in views]
    for v in views:
        into = {(e["from"], e.get("rule")) for e in flow["edges"] if e["to"] == f"gold:{v['name']}"}
        joined = [ln for ln in v["sql"].splitlines() if ln.startswith("-- join ")]
        assert len(into) == len(joined) + 1                            # the fact table and one per join
    # the pipeline: its activities, in order, each the dry run's definition
    acts = cards["pipeline"]["answer"]["pipeline"]["content"]["properties"]["activities"]
    steps_ = [nodes[i] for i in flow["pipeline"]["steps"]]
    assert [json.loads(s["code"]) for s in steps_] == acts
    assert [s["notebook"] for s in steps_] == ["shop_silver", "shop_gold", "shop_flow_check"]
    # the model reads the source tables, its code its relationships and measures; the report is on the model
    model = nodes["item:semantic_model"]
    assert model["code"].startswith("// definition/relationships.tmdl") and "measure 'Rows in orders'" in model["code"]
    assert {"from": "bronze", "to": "item:semantic_model", "label": "reads the source tables", "built": True} in flow["edges"]
    assert {"from": "item:semantic_model", "to": "item:report", "label": "on the model", "built": True} in flow["edges"]


def test_what_the_build_does_not_make_is_marked_not_built(make):
    client, fake, priv = make()
    out = _build(client, priv, [{"kind": "gold_views", "name": "shop_gold"}])[0].json()
    flow = out["flow"]
    assert all(not n["built"] for n in flow["nodes"] if n["column"] == "silver")   # dashed: the silver notebook is not chosen
    assert all(n["built"] for n in flow["nodes"] if n["column"] == "gold")
    assert flow["pipeline"] is None
    assert _build(client, priv, [{"kind": "ontology", "name": "o"}])[0].json()["flow"] is None


def test_the_flow_module_on_the_seed_plan_directly():
    """Without Fabric: the same plan gives the same nodes as silver.steps and gold.statements."""
    from fabric_backend import seed
    from fabric_backend.infer import plan
    p = plan(seed.schema("shop"))
    info = {"workspace_id": gs.WS, "item_id": gs.LH, "item_name": "demo_lh", "item_kind": "Lakehouse", "schema": "shop",
            "schemas_enabled": True}
    f = data_flow.flow(p, info, {"silver_notebook": "s"})
    sspec, gspec = silver.spec(p, info), gold.spec(p, info)
    assert [n["table"] for n in f["nodes"] if n["column"] == "silver"] == [s["table"] for s in silver.steps(sspec)]
    assert [n["code"] for n in f["nodes"] if n["column"] == "gold"] == [s["sql"] for s in gold.statements(gspec)]
    no_schemas = data_flow.flow(p, {**info, "schemas_enabled": False}, {"silver_notebook": "s"})
    assert not [n for n in no_schemas["nodes"] if n["column"] == "gold"] and "schemas" in no_schemas["notes"][0]


def test_phase_1_s_form_still_answers_as_before(make):
    client, fake, priv = make()
    rv = _review(client, priv)
    out = _post(client, "/build", {**SRC, "name": "shop_model_api", "review": rv}, tok(priv)).json()
    assert out["output"] == "graphql" and out["would"] == "create" and out["dry_run"] is True
    assert "outputs" not in out


def test_tokens_carry_the_workload_app_id_for_the_entra_steps():
    t = workload_api.Tokens(None, "u", "t", "app-id")
    assert t.app_id == "app-id"


# ------------------------------------------------------------------ the editor's copies -------------------------------

def test_the_editor_s_flow_fixture_is_current():
    """dataFlow.test.ts lays out and renders flow.fixture.json; it must be what data_flow.py sends today."""
    import subprocess
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "workload/scripts/build_flow_fixture.py", "--check"], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_editor_s_kinds_are_the_engine_s():
    """buildWords.ts KINDS: the same order, labels, item types and permissions as workload_api.KINDS."""
    import re
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    ts = (root / "workload/Workload/app/items/ModelItem/buildWords.ts").read_text(encoding="utf-8")
    ts = ts.replace("[NOTEBOOK]", '["Notebook.ReadWrite.All or Item.ReadWrite.All"]').replace(
        "[NOTEBOOK,", '["Notebook.ReadWrite.All or Item.ReadWrite.All",')
    rows = re.findall(r'\{ kind: "(\w+)", label: "([^"]+)", type: "(\w+)", suffix: "\w+", updates: (true|false),\s*needs: \[([^\]]*)\]', ts)
    assert [r[0] for r in rows] == list(workload_api.ORDER)
    for kind, label, typ, updates, needs in rows:
        k = workload_api.KINDS[kind]
        assert (label, typ, updates == "true") == (k["label"], k["type"], k["updates"]), kind
        assert re.findall(r'"([^"]+)"', needs) == [" or ".join(a) for a in k["needs"]], kind


def test_a_build_of_every_output_reads_the_lakehouse_once(make):
    """plan_scope keeps the plan for the build: eight tools, one read of the columns."""
    client, fake, priv = make()
    rv = _review(client, priv)
    import fabric_backend.server as S
    reads = []
    real = S._plan_read
    S._plan_read = lambda *a, **k: reads.append(a[:3]) or real(*a, **k)
    try:
        out = _build(client, priv, ALL, review=rv)[0].json()
    finally:
        S._plan_read = real
    assert out["refused"] == 0 and len(reads) == 1, reads
