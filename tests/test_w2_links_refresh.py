"""W2 (Gustav's Create of 23 November 2026 in the Krusgraph Model item: source demo_lh in one workspace, built into another
workspace with a new build lakehouse; silver notebook, gold notebook, pipeline, semantic model and data agent, and the
pipeline's run once, which succeeded in 5m41s). What he found, and what these tests hold:

1. Open in Fabric on the data agent led to Fabric's 404 page: the portal addresses by item type (mcp_apps_build.TYPE_PATHS,
   the same as the editor's NavigationController.ts) are the ones he copied from his workspace list.
2. The agent's tables: none selected after the run. The data source's schema tree lists a new table only once the
   lakehouse's SQL analytics endpoint has synced it; after the run the engine asks for that sync once and reads the tree
   again a bounded number of times (data_agent.TABLE_WAITS). Krusgraph's own quarantine table is never selected.
3. The model's refresh failed: gold had only the fact views, the model reads the dimension views too. The pipeline wrote
   the gold notebook again without them (server._pipeline_build had no `dimensions`).
4. "Pipeline was modified after this run": the plan marker was written into the pipeline's description after Run once had
   started it. Now before.
5. "this item has no id saved for it" on the gold notebook: the pipeline step recorded the notebook as its own output.

Synthetic shop schema and in-memory fakes only; nothing calls Fabric."""
from __future__ import annotations

import json
import re

import pytest
import requests

from fabric_backend import data_agent, demo, gold, mcp_apps_build as build, server, semantic_model as sm, workload_api

WS = "11111111-1111-1111-1111-111111111111"
SEVEN = ["addresses", "audit_log", "categories", "customers", "order_items", "orders", "products"]


# ------------------------------------------------------------------ 1. the portal addresses --------------------------

# Source: Gustav's workspace list, 23 Nov 2026 (the addresses copied from the portal's item list)
VERIFIED = {"DataAgent": "aiskills/{id}", "Notebook": "synapsenotebooks/{id}", "SemanticModel": "datasets/{id}/details",
            "DataPipeline": "pipelines/{id}", "Lakehouse": "lakehouses/{id}", "SQLEndpoint": "sqlanalyticsendpoints/{id}"}


@pytest.mark.parametrize("typ,path", sorted(VERIFIED.items()))
def test_every_verified_type_opens_the_address_gustav_copied(typ, path):
    assert build.TYPE_PATHS[typ] == path and typ in build.VERIFIED_TYPES
    assert build.item_url(WS, typ, "it-1") == f"https://app.fabric.microsoft.com/groups/{WS}/{path.format(id='it-1')}"


def test_the_data_agent_and_the_pipeline_open_their_own_page_not_the_list_or_a_404():
    assert build.open_url(WS, "create_data_agent", "da-1").endswith(f"/groups/{WS}/aiskills/da-1")
    assert "/dataagents/" not in build.open_url(WS, "create_data_agent", "da-1")
    assert build.open_url(WS, "create_pipeline", "pl-1").endswith("/pipelines/pl-1")
    assert build.open_url(WS, "create_gold_views", "nb-1").endswith("/synapsenotebooks/nb-1")
    assert build.item_url(WS, "AppBackend", "x") == build.list_url(WS)            # no verified address: the list


def test_the_editor_s_mapping_says_the_same_as_the_engine():
    from pathlib import Path
    ts = (Path(__file__).resolve().parents[1] / "workload/Workload/app/controller/NavigationController.ts").read_text()
    for typ, path in VERIFIED.items():
        seg, _, rest = path.partition("/{id}")
        block = re.search(r'"%s": \{(.*?)\}' % typ, ts, re.S)
        assert block, typ
        assert f'frontendTypePath: "{seg}"' in block.group(1), typ
        assert (f'suffix: "{rest}"' in block.group(1)) == bool(rest), typ
    assert "Gustav's workspace list, 23 Nov 2026" in ts


# ------------------------------------------------------------------ 2. the agent's tables ------------------------------

class Lakehouse:
    """The build lakehouse's data source tree as Gustav saw it once the run had written silver: dbo, gold (three fact
    views), krusgraph (health) and silver (seven tables and the quarantine). `listed_after` readings of the tree pass
    before the SQL analytics endpoint lists the silver tables (None: never)."""

    def __init__(self, listed_after: int | None = 0, quarantine_selected: bool = True, refresh_status: int = 200):
        self.reads, self.listed_after = 0, listed_after
        self.patches, self.posts, self.refresh_status = [], [], refresh_status
        self.quarantine_selected = quarantine_selected

    def tree(self, root):
        silver = self.listed_after is not None and self.reads > self.listed_after
        t = lambda sch, names, typ="Table", sel=False: [{"id": f"{sch}.{n}", "type": typ, "displayName": n, "isSelected": sel}  # noqa: E731
                                                         for n in names]
        nodes = {None: [{"id": "S", "type": "Schemas", "displayName": "Schemas", "hasSubElements": True}],
                 "S": [{"id": s, "type": "Schema", "displayName": s, "hasSubElements": True} for s in ("dbo", "gold", "krusgraph", "silver")],
                 "dbo": [{"id": "dbo-T", "type": "Tables", "hasSubElements": True}], "dbo-T": t("dbo", ["sys_dq_metrics"]),
                 "gold": [{"id": "gold-T", "type": "Tables", "hasSubElements": True}], "gold-T": t("gold", ["audit_log", "order_items", "orders"]),
                 "krusgraph": [{"id": "kg-T", "type": "Tables", "hasSubElements": True}], "kg-T": t("krusgraph", ["health"]),
                 "silver": [{"id": "silver-T", "type": "Tables", "hasSubElements": True}],
                 "silver-T": (t("silver", SEVEN) if silver else [])
                             + t("silver", ["krusgraph_quarantine"], sel=self.quarantine_selected)}
        return nodes.get(root, [])

    def get(self, url, headers=None, params=None, timeout=None):
        if url.endswith("/elements"):
            if not (params or {}).get("rootId"):
                self.reads += 1
            return R(200, {"value": self.tree((params or {}).get("rootId"))})
        if url.endswith("/staging/datasources"):
            return R(200, {"value": [{"id": "ds-1", "type": "LakehouseTables", "lakehouseReference": {"itemId": "lh-1"}}]})
        if "/lakehouses/lh-1" in url:
            return R(200, {"properties": {"sqlEndpointProperties": {"id": "ep-1"}}})
        if url.endswith("/fewshots"):
            return R(200, {"value": []})
        return R(404, {})

    def post(self, url, headers=None, json=None, timeout=None, **k):
        self.posts.append(url)
        if url.endswith("/refreshMetadata"):
            return R(self.refresh_status, {})
        return R(200, {})

    def patch(self, url, headers=None, params=None, json=None, timeout=None):
        if url.endswith("/elements"):
            self.patches.append((params["id"], json["isSelected"]))
        return R(200, {})

    def put(self, *a, **k):
        return R(200, {})


class R:
    def __init__(self, status, body):
        self.status_code, self._body, self.text, self.headers = status, body, json.dumps(body), {}

    def json(self):
        return self._body


def _spec():
    lay = {"layer": "silver", "schema": "silver", "tables": SEVEN, "kinds": ("Table",), "instructions": "i",
           "datasource_instructions": "d", "datasource_description": "x", "fewshots": [], "topics": [], "templates": []}
    return {"name": "demo_lh_agent", "schema": "shop", "tables_to_select": SEVEN, "layers": [lay],
            "datasource": {"type": "LakehouseTables", "lakehouseReference": {"referenceType": "ById", "itemId": "lh-1", "workspaceId": WS}},
            "instructions": "i", "datasource_instructions": "d", "fewshots": [], "topics": [], "templates": []}


@pytest.fixture
def lakehouse(monkeypatch):
    import importlib
    deploy = importlib.import_module("fabric_backend.deploy")

    def install(**kw):
        f = Lakehouse(**kw)
        for verb in ("get", "post", "patch", "put"):
            monkeypatch.setattr(requests, verb, getattr(f, verb))
        monkeypatch.setattr(deploy, "find_item", lambda *a, **k: "da-1")
        return f
    return install


def _apply(waits=()):
    token = data_agent.TABLE_WAITS.set(waits)
    try:
        return data_agent.apply(_spec(), WS, {}, publish=False, sleep=lambda s: None)
    finally:
        data_agent.TABLE_WAITS.reset(token)


def test_at_create_none_are_listed_yet_and_the_card_names_them_without_waiting(lakehouse):
    f = lakehouse(listed_after=None)
    sel = _apply()["selection"]
    assert sel["selected"] == 0 and sel["total"] == 7 and sel["missing"] == SEVEN and "waited" not in sel
    assert sel["words"].startswith("selected 0 of 7 tables in silver (silver); not listed yet: addresses")
    assert f.reads == 1 and not any(u.endswith("/refreshMetadata") for u in f.posts)   # no wait at Create


def test_after_the_run_the_endpoint_is_synced_once_and_the_tables_selected_when_listed(lakehouse):
    f = lakehouse(listed_after=2)
    sel = _apply(data_agent.AFTER_RUN_WAITS)["selection"]
    assert sel["selected"] == 7 and sel["missing"] == [] and sel["one_layer"] is True
    assert sel["waited"]["attempts"] == 3 and sel["waited"]["refresh"]["status"] == "succeeded"
    assert [u for u in f.posts if u.endswith("/refreshMetadata")] == [f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/sqlEndpoints/ep-1/refreshMetadata"]
    assert sorted(i for i, on in f.patches if on) == sorted(f"silver.{t}" for t in SEVEN)


def test_the_quarantine_table_is_never_selected_and_is_deselected_when_fabric_shows_it(lakehouse):
    f = lakehouse(listed_after=0, quarantine_selected=True)
    sel = _apply()["selection"]
    assert ("silver.krusgraph_quarantine", False) in f.patches
    assert ("silver.krusgraph_quarantine", True) not in f.patches and sel["own_deselected"] == 1
    assert not any(i.startswith(("gold.", "dbo.", "krusgraph.")) for i, _ in f.patches)   # other schemas untouched


def test_the_wait_is_bounded_and_says_select_tables_now(lakehouse):
    f = lakehouse(listed_after=None, refresh_status=403)
    sel = _apply((1, 2, 3))["selection"]
    assert f.reads == 4 and sel["waited"]["attempts"] == 4 and sel["waited"]["seconds"] == 6      # the first and three more
    assert sel["waited"]["refresh"] == {"status": "refused", "http": 403, "doc": data_agent.METADATA_DOC}
    assert sel["selected"] == 0 and "Select tables now" in sel["words"] and "metadata sync" in sel["words"]


def test_waits_only_after_a_succeeded_run_or_select_tables_never_in_a_dry_run():
    assert workload_api.agent_waits({"after_run": {"status": "Succeeded"}}, False) is True
    assert workload_api.agent_waits({"select_tables": True}, False) is True
    assert workload_api.agent_waits({"after_run": {"status": "Failed"}}, False) is False
    assert workload_api.agent_waits({}, False) is False
    assert workload_api.agent_waits({"select_tables": True}, True) is False
    assert sum(data_agent.AFTER_RUN_WAITS) <= 60


def test_select_tables_is_only_for_the_agent_and_only_in_create():
    base = {"workspace": WS, "source": "demo_lh", "schema": "shop", "review": {"items": []}, "dry_run": False,
            "outputs": [{"kind": "data_agent", "name": "demo_lh_agent"}], "only": ["data_agent"], "select_tables": True}
    assert workload_api.build_request(base)["select_tables"] is True
    with pytest.raises(workload_api.BadRequest):
        workload_api.build_request({**base, "dry_run": True})
    with pytest.raises(workload_api.BadRequest):
        workload_api.build_request({**base, "outputs": base["outputs"] + [{"kind": "semantic_model", "name": "m"}],
                                    "only": ["semantic_model"]})


# ------------------------------------------------------------------ 3. gold has every view the model reads ------------

INFO = {**demo.FLOW_INFO, "workspace_id": WS, "item_id": "lh-1", "item_name": "demo_lh"}


def _gold_views_in(notebook: str) -> set[str]:
    """The views the gold notebook creates: its CREATE ... MATERIALIZED LAKE VIEW statements, by name."""
    return {m.lower() for m in re.findall(r"CREATE OR REPLACE MATERIALIZED LAKE VIEW `[^`]+`\.`([^`]+)`", notebook)}


def test_the_pipeline_s_gold_notebook_creates_every_view_the_model_on_gold_reads():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    token = server.MODEL_ON_GOLD.set({"silver_schema": "silver", "gold_schema": "gold"})
    try:
        b = server._pipeline_build(p, INFO, "shop", "silver", "gold", None, False, "demo_lh_pipeline", "demo_lh_silver", "demo_lh_gold")
    finally:
        server.MODEL_ON_GOLD.reset(token)
    nb = next(n for n in b["notebooks"] if n["name"] == "demo_lh_gold")["content"]
    written = _gold_views_in(nb)
    g = gold.spec(p, INFO, "silver", "gold", dimensions=True)
    model = sm.draft_on_gold(p, INFO, g, "demo_lh_model", validation=demo.demo_validation())
    reads = {m.lower() for path, text in model["parts"].items() if path.startswith("definition/tables/") and "directLake" in text
             for m in re.findall(r"entityName: (\S+)", text)}
    assert reads and reads <= written, f"the model reads {sorted(reads - written)}, which the pipeline's gold notebook does not create"
    assert {"customers", "products", "addresses", "categories"} <= written       # the dimension views Gustav's gold lacked
    assert written == {v["name"].split(".", 1)[1] for v in gold.all_views(g)}    # the same notebook as create_gold_views


def test_without_a_model_on_gold_the_pipeline_s_gold_notebook_is_as_before():
    p = demo.plan(demo.schema("shop"), keys=demo.DEMO_KEYS)
    b = server._pipeline_build(p, INFO, "shop", "silver", "gold", None, False, "demo_lh_pipeline", "", "")
    nb = next(n for n in b["notebooks"] if n["name"] == "gold_shop")["content"]
    assert _gold_views_in(nb) == {v["name"].split(".", 1)[1] for v in gold.spec(p, INFO, "silver", "gold")["views"]}


# ------------------------------------------------------------------ 5. the notebooks keep their own output -------------

def test_the_pipeline_s_notebooks_keep_the_output_that_made_them():
    chosen = {"silver_notebook": "demo_lh_silver", "gold_views": "demo_lh_gold", "pipeline": "demo_lh_pipeline"}
    assert workload_api.notebook_output("Notebook", "demo_lh_gold", chosen) == "gold_views"
    assert workload_api.notebook_output("Notebook", "DEMO_LH_SILVER", chosen) == "silver_notebook"
    assert workload_api.notebook_output("Notebook", "demo_lh_pipeline_check", chosen) == "pipeline"
    assert workload_api.notebook_output("DataPipeline", "demo_lh_pipeline", chosen) == "pipeline"
    assert workload_api.notebook_output("Notebook", "gold_shop", {"pipeline": "p"}) == "pipeline"   # no gold output of its own
    res = {n: {"status": "Succeeded", "id": f"id-{n}"} for n in ("demo_lh_pipeline", "demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline_check")}
    made = workload_api._created_ids("pipeline", {"result": res}, chosen, WS, {"kind": "pipeline", "name": "demo_lh_pipeline"},
                                     {"schema": "shop"})
    assert {c["name"]: c["output"] for c in made} == {"demo_lh_pipeline": "pipeline", "demo_lh_silver": "silver_notebook",
                                                       "demo_lh_gold": "gold_views", "demo_lh_pipeline_check": "pipeline"}


# ------------------------------------------------------------------ 4. nothing changes the pipeline after its run ----
from test_workload_build import make  # noqa: E402,F401  (the editor's fixture)
from test_workload_api import keys  # noqa: E402,F401
import test_n185_pipeline_jobs as pj  # noqa: E402


def test_the_plan_marker_is_written_before_run_once_starts_and_nothing_after(make, monkeypatch):  # noqa: F811
    client, fake, priv, job = pj._jobs_fabric(make, monkeypatch, pj.wl.EVERY_SCOPE + " DataPipeline.Execute.All")
    out = pj.wl._build(client, priv, pj._with_jobs({"run_once": True, "schedule": None}), dry_run=False)[0].json()
    card = pj._pipeline_card(out)
    assert card["jobs"]["run"]["status"] == "Running"
    assert "marked_before_run" in card["answer"]["result"]           # the fake answers the PATCH with 404: counted 0
    started = next(i for i, c in enumerate(fake.calls) if c[0] == "POST" and "/jobs/" in c[1])
    item_patches = [i for i, c in enumerate(fake.calls) if c[0] == "PATCH" and re.search(r"/items/[^/]+$", c[1])]
    assert item_patches, "the plan marker was written"
    assert max(item_patches) < started, "an item's description was changed after the run started"
    outputs = {c["name"]: c["output"] for c in card["created"]}
    assert outputs["shop_gold"] == "gold_views" and outputs["shop_silver"] == "silver_notebook" and outputs["shop_flow"] == "pipeline"
