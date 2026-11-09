"""n185, the founder's additions of 9 November 2026 for the data agent the Krusgraph Model makes.

(a) one layer: with shop and silver copies of the tables in the lakehouse, the agent's data source selects the silver
tables only (or the gold views, or the source when no silver exists) and deselects the plan's tables in the other layer,
by schema, never by name alone; its instructions and examples name the layer's schema. (b) the examples are written as
the documented few-shots and their validation status is read back; the card says where Fabric shows them. Publishing:
off by default; on only when ticked, the agent reads one layer and, with Run once, after the run succeeded; Microsoft
365 Copilot is a separate tick that needs Publish, has a preflight (capacity, tenant settings, licences, Unverified
where unreadable) and is never called. Fabric is the in-memory staging API of tests/test_creating_tools.py, with a
schema tree that has two schemas."""
import json

import pytest
import requests

from fabric_backend import agent_publish as AP, data_agent, server, workload_api
from test_creating_tools import FakeFabric, Resp, WS, shop  # noqa: F401  (the hosted source fixture)

SHOP = ["addresses", "categories", "customers", "order_items", "orders", "products", "audit_log"]


class TwoLayers(FakeFabric):
    """The lakehouse after the pipeline ran: schemas shop and silver, the same table names in both, all selected (the
    founder's screen), plus a gold view and a table Krusgraph does not know."""

    def __init__(self, silver=True, gold=False, examples_status="Valid", **kw):
        super().__init__(**kw)
        self.state = {}
        tables = lambda sch, sel: [{"id": f"{sch}.{t}", "type": "Table", "displayName": t, "isSelected": sel, "hasSubElements": True}  # noqa: E731
                                   for t in SHOP]
        self.tree = {None: [{"id": "S", "type": "Schemas", "displayName": "Schemas", "hasSubElements": True}],
                     "S": [{"id": "shop", "type": "Schema", "displayName": "shop", "hasSubElements": True}]
                          + ([{"id": "silver", "type": "Schema", "displayName": "silver", "hasSubElements": True}] if silver else [])
                          + ([{"id": "gold", "type": "Schema", "displayName": "gold", "hasSubElements": True}] if gold else []),
                     "shop": [{"id": "shop-T", "type": "Tables", "displayName": "Tables", "hasSubElements": True}],
                     "shop-T": tables("shop", True) + [{"id": "shop.other", "type": "Table", "displayName": "other", "isSelected": True}],
                     "silver": [{"id": "silver-T", "type": "Tables", "displayName": "Tables", "hasSubElements": True}],
                     "silver-T": tables("silver", True),
                     "gold": [{"id": "gold-M", "type": "MaterializedViews", "displayName": "Materialized views", "hasSubElements": True}],
                     "gold-M": []}
        self.examples_status = examples_status

    def _hit(self, method, url, **k):
        if method == "get" and url.endswith("/elements"):
            self.calls.append((method, url.split("/v1/")[1], None, k.get("params")))
            return Resp(200, {"value": self.tree.get((k.get("params") or {}).get("rootId"), [])})
        if method == "patch" and url.endswith("/elements"):
            self.calls.append((method, url.split("/v1/")[1], k.get("json"), k.get("params")))
            self.state[k["params"]["id"]] = k["json"]["isSelected"]
            return Resp(200, {})
        if method == "get" and url.endswith("/fewshots"):
            self.calls.append((method, url.split("/v1/")[1], None, None))
            return Resp(200, {"value": [{**f, "validationStatus": {"value": self.examples_status, **({"reason": "Invalid object name"} if self.examples_status == "Invalid" else {})}}
                                        for f in self.fewshots]})
        return super()._hit(method, url, **k)

    def selected_now(self):
        out = []
        for kids in self.tree.values():
            for e in kids:
                if e.get("type") in ("Table", "MaterializedView") and self.state.get(e["id"], e.get("isSelected")):
                    out.append(e["id"])
        return sorted(out)


@pytest.fixture
def two(monkeypatch):
    def install(**kw):
        f = TwoLayers(**kw)
        for m in ("get", "post", "patch"):
            monkeypatch.setattr(requests, m, (lambda method: lambda url, **k: f._hit(method, url, **k))(m))
        return f
    return install


@pytest.fixture(autouse=True)
def schemas_on(request, monkeypatch):
    """The founder's lakehouse has schemas; the hosted fixture's info does not say so for the tests that create."""
    if "two" in request.fixturenames:
        real = server._source_inputs
        monkeypatch.setattr(server, "_source_inputs", lambda *a, **k: (lambda p, i: (p, {**i, "schemas_enabled": True}))(*real(*a, **k)))


def agent(shop, **kw):  # noqa: F811
    return json.loads(server.create_data_agent(*shop, name="demo_lh_agent", schema="shop", **kw))


# ------------------------------------------------------------------ (a) one layer --------------------------------

def test_silver_is_selected_and_the_shop_copies_deselected(shop, two):  # noqa: F811
    f = two()
    out = agent(shop, dry_run=False, publish=False, layer="silver")
    sel = out["result"]["selection"]
    assert sel["layer"] == "silver" and sel["schema"] == "silver" and sel["one_layer"] is True
    assert f.selected_now() == sorted([f"silver.{t}" for t in SHOP] + ["shop.other"])   # a table Krusgraph does not know stays
    assert all(f"shop.{t}" in f.state and f.state[f"shop.{t}"] is False for t in SHOP)
    assert "schema silver" in f.settings["aiInstructions"] and "[shop]" not in json.dumps(f.fewshots)
    assert all("[silver]" in x["query"] for x in f.fewshots)


def test_without_silver_tables_the_source_is_the_one_layer(shop, two):  # noqa: F811
    f = two(silver=False)
    sel = agent(shop, dry_run=False, publish=False, layer="silver")["result"]["selection"]
    assert sel["layer"] == "source" and sel["schema"] == "shop" and sel["one_layer"] is True
    assert all("[shop]" in x["query"] for x in f.fewshots)


def test_the_source_layer_deselects_silver_copies_the_founder_saw(shop, two):  # noqa: F811
    f = two()
    sel = agent(shop, dry_run=False, publish=False, layer="silver")["result"]["selection"]
    assert sel["layer"] == "silver"
    f2 = two()                                                         # same lakehouse, the source asked for by name
    for t in SHOP:
        f2.tree["silver-T"] = [{**e, "isSelected": True} for e in f2.tree["silver-T"]]
    sel = data_agent.select_layer(requests, {}, "https://api.fabric.microsoft.com/v1/x/elements", data_agent._tree(requests, {}, "https://api.fabric.microsoft.com/v1/x/elements"),
                                  {"schema": "shop", "tables_to_select": SHOP,
                                   "layers": [{"layer": "silver", "schema": "silver", "tables": SHOP, "kinds": ("Table",)},
                                              {"layer": "source", "schema": "shop", "tables": SHOP, "kinds": ("Table",)}]},
                                  {"layer": "source", "schema": "shop", "tables": SHOP, "kinds": ("Table",)})
    assert sel["deselected"] == len(SHOP) and all(f2.state[f"silver.{t}"] is False for t in SHOP)


def test_the_dry_run_names_the_layer(shop, monkeypatch):  # noqa: F811
    assert agent(shop)["layer"] == "The agent reads the source tables in shop only."
    assert agent(shop, layer="silver")["layer"].endswith("The silver layer needs a lakehouse with schemas; this one has none.")
    real = server._source_inputs
    monkeypatch.setattr(server, "_source_inputs", lambda *a, **k: (lambda p, i: (p, {**i, "schemas_enabled": True}))(*real(*a, **k)))
    words = agent(shop, layer="silver")["layer"]
    assert words.startswith("The agent reads the silver tables in silver only (cleaned, keys and links held)")
    assert "Never two layers at once" in words
    assert agent(shop, layer="gold")["layer"].startswith("The agent reads the gold views in gold only")
    assert agent(shop, layer="both")["kind"] == "bad_request"


# ------------------------------------------------------------------ (b) the examples --------------------------------

def test_the_examples_validation_is_read_back(shop, two):  # noqa: F811
    two(examples_status="Invalid")
    ex = agent(shop, dry_run=False, publish=False, layer="silver")["result"]["examples"]
    assert ex["invalid"] == ex["count"] >= 3 and ex["invalid_examples"][0]["reason"] == "Invalid object name"
    assert "Example queries" in ex["where"] and "not the chat's suggested questions" in ex["where"]


# ------------------------------------------------------------------ publishing: the three conditions ----------------

@pytest.mark.parametrize("ticked, one, run_once, run, state", [
    (False, True, False, None, "draft"),                    # off by default: a draft
    (True, True, False, None, "publish"),                   # ticked, one layer, no run asked: published at Create
    (True, False, False, None, "draft"),                    # two layers: never published
    (True, True, True, "Running", "waiting"),               # Run once ticked: waits for the run
    (True, True, True, "Succeeded", "publish"),             # ... and is published after it succeeded
    (True, True, True, "Failed", "draft"),                  # a failed run: stays a draft, says why
])
def test_publish_only_when_ticked_one_layer_and_the_run_succeeded(ticked, one, run_once, run, state):
    d = AP.decide(ticked, one, run_once, run)
    assert d["state"] == state and d["publish"] is (state == "publish")
    if state != "publish":
        assert d["why"]


def test_the_dry_run_says_who_can_use_it():
    assert AP.publish_words("demo_lh_agent") == "Create publishes demo_lh_agent: people with access to the workspace can use it"


# ------------------------------------------------------------------ Microsoft 365 Copilot: preflight only ----------

class Http:
    def __init__(self, sku="FT1", region="West Europe", settings=None, cap_status=200):
        self.sku, self.region, self.settings, self.cap_status, self.calls = sku, region, settings, cap_status, []

    def __call__(self, method, url, **kw):
        self.calls.append((method, url))
        if url.endswith(f"/workspaces/{WS}"):
            return Resp(200, {"id": WS, "capacityId": "cap-1", "capacityRegion": self.region})
        if url.endswith("/capacities"):
            return Resp(self.cap_status, {"value": [{"id": "cap-1", "sku": self.sku, "region": self.region, "state": "Active"}]})
        if url.endswith("/admin/tenantsettings"):
            if self.settings is None:
                return Resp(403, {"errorCode": "Unauthorized"})
            return Resp(200, {"tenantSettings": [{"title": t, "enabled": on} for t, on in self.settings.items()]})
        raise AssertionError(url)


def test_the_founders_trial_capacity_is_named_as_what_is_missing():
    pf = AP.copilot_preflight(Http(sku="FT1"), WS, None)
    cap = pf["requirements"][0]
    assert cap["status"] == "missing" and "trial capacity (FT1)" in cap["detail"] and cap["doc"] == AP.COPILOT_DOC
    assert pf["missing"] >= 1 and pf["words"].startswith("Missing for Microsoft 365 Copilot: Paid capacity")
    lic = [r for r in pf["requirements"] if "licence" in r["requirement"]][0]
    assert lic["status"] == "unverified" and lic["detail"].startswith("Unverified")
    assert all(m == "get" for m, _ in Http().calls)                     # reads only


def test_f2_and_the_settings_on_leave_only_the_unverified_licences():
    on = {t: True for t, _ in AP.SETTINGS}
    pf = AP.copilot_preflight(Http(sku="F2", settings=on), WS, None)
    assert pf["missing"] == 0 and {r["status"] for r in pf["requirements"]} == {"ok", "unverified"}
    off = dict(on, **{AP.SETTINGS[0][0]: False})
    pf = AP.copilot_preflight(Http(sku="F64", settings=off), WS, None)
    assert pf["missing"] == 1 and AP.SETTINGS[0][0] in pf["words"]


def test_without_the_scopes_the_capacity_and_settings_are_unverified_not_guessed():
    http = Http(sku="F64")
    pf = AP.copilot_preflight(http, WS, {"Item.ReadWrite.All"})
    assert pf["missing"] == 0 and pf["requirements"][0]["status"] == "unverified" and "Capacity.Read.All" in pf["requirements"][0]["detail"]
    assert not any(u.endswith("/capacities") or u.endswith("/tenantsettings") for _, u in http.calls)
    cross = [r for r in AP.copilot_preflight(Http(region="Japan East"), WS, None)["requirements"] if "outside" in r["requirement"]]
    assert len(cross) == 2                                             # outside the EU data boundary and the US: both listed


# ------------------------------------------------------------------ the editor's card --------------------------------

def _card(monkeypatch, http, *, publish, copilot=False, run_once=False, after=None, one=True, dry=False):
    import importlib
    monkeypatch.setattr(importlib.import_module("fabric_backend.deploy"), "send", lambda m, u, h, **k: http(m, u, **k))
    o = {"kind": "data_agent", "name": "demo_lh_agent", "agent": {"layer": "silver", "publish": publish, "copilot": copilot}}
    answer = {"layer": "words", "result": {"id": "da-9", "selection": {"layer": "silver", "one_layer": one}}}
    return workload_api.agent_card(o, answer, {"run_once": run_once}, after, dry, WS, {}, None)


class PubHttp(Http):
    def __call__(self, method, url, **kw):
        if url.endswith("/staging/publish"):
            self.calls.append((method, url))
            return Resp(200, {})
        return super().__call__(method, url, **kw)


def test_the_card_publishes_only_when_allowed_and_never_calls_copilot(monkeypatch):
    http = PubHttp()
    c = _card(monkeypatch, http, publish=False)
    assert c["published"] is False and not any(u.endswith("/publish") for _, u in http.calls)
    c = _card(monkeypatch, http, publish=True)
    assert c["published"] is True and sum(u.endswith("/staging/publish") for _, u in http.calls) == 1
    http = PubHttp()
    c = _card(monkeypatch, http, publish=True, run_once=True)                       # the run has not ended yet
    assert c["published"] is False and c["decision"]["state"] == "waiting" and not http.calls
    c = _card(monkeypatch, http, publish=True, run_once=True, after={"status": "Succeeded"})
    assert c["published"] is True
    c = _card(monkeypatch, PubHttp(), publish=True, run_once=True, after={"status": "Failed"})
    assert c["published"] is False and "failed" in c["words"][0]
    c = _card(monkeypatch, PubHttp(), publish=True, one=False)
    assert c["published"] is False and "not one layer" in c["words"][0]
    http = PubHttp()
    c = _card(monkeypatch, http, publish=True, copilot=True)
    assert c["copilot_preflight"]["missing"] >= 1 and c["copilot_step"].startswith("In Fabric, open the agent → Publish → tick Publish to Agent Store")
    assert sum(u.endswith("/staging/publish") for _, u in http.calls) == 1        # one publish, no Copilot call, no retry


def test_the_editor_dry_run_says_what_create_will_do(monkeypatch):
    c = _card(monkeypatch, PubHttp(), publish=True, copilot=True, dry=True, run_once=True)
    assert c["words"][0] == "Create publishes demo_lh_agent: people with access to the workspace can use it"
    assert "after the pipeline's run has succeeded" in c["words"][1] and "no documented API" in c["words"][2]
    assert "Example queries" in c["where_examples"]
    off = _card(monkeypatch, PubHttp(), publish=False, dry=True)
    assert off["words"][0].startswith("Create leaves the agent a draft")


def test_copilot_needs_publish_and_both_are_off_by_default():
    base = {"workspace": "demo", "source": "demo_lh", "review": {}, "dry_run": True}
    out = workload_api.build_request({**base, "outputs": [{"kind": "data_agent", "name": "a", "agent": {}}]})
    assert out["outputs"][0]["agent"] == {"layer": "silver", "publish": False, "copilot": False}
    with pytest.raises(workload_api.BadRequest, match="copilot needs publish"):
        workload_api.build_request({**base, "outputs": [{"kind": "data_agent", "name": "a", "agent": {"copilot": True}}]})
    with pytest.raises(workload_api.BadRequest, match="after_run"):
        workload_api.build_request({**base, "outputs": [{"kind": "data_agent", "name": "a"}], "after_run": {"status": "maybe"}})
