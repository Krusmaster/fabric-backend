"""Finding 7 of the live test of 27 October 2026: create_backend shop_api with orders.ship_to_id -> addresses.address_id
confirmed (field_name "address") stopped with kind would_remove. The plan names the reverse field orders_as_ship_to;
the API has it as orders. The same relationship under another name counted as removed plus new, keep_with_confirmed
was empty, and plan_drift's keep_with_confirmed (without reverse_name) led into the same stop. With reverse_name
"orders" plan_drift said no drift and create_backend updated shop_api in place (Succeeded, updated).

Fabric is the golden tests' double at `requests` (tests/golden_support.py) with shop_api as it stands in the demo
workspace after that run: the ship-to relationship as `address` on orders and `orders` on addresses."""
import base64
import json
import sys

import pytest

import golden_support as gs
from fabric_backend import server
from fabric_backend.graphql import decode

_REAL_EXISTING_API = server._existing_api          # tests/conftest.py stubs the guard out; here it runs, as in production
LIVE_NAMES = {**gs.SHIP_TO, "field_name": "address", "reverse_name": "orders"}
AS_ASKED = {**gs.SHIP_TO, "field_name": "address"}                       # what the live call passed


def _live_api_definition() -> dict:
    from fabric_backend import seed
    from fabric_backend.graphql import definition
    from fabric_backend.infer import plan
    return definition(plan(seed.schema("shop"), confirmed=[LIVE_NAMES]), "shop_api", gs.WS, gs.EP, "SqlAnalyticsEndpoint")["definition"]


class LiveShopApi(gs.FakeFabric):
    def _route(self, method, url, body=None):
        if method == "POST" and url.endswith(f"/items/{gs.API}/getDefinition"):
            self.calls.append((method, url.split("api.fabric.microsoft.com", 1)[1]))
            return gs.Response(200, {"definition": _live_api_definition()})
        return super()._route(method, url, body)


@pytest.fixture
def fabric(monkeypatch):
    import requests
    fake = LiveShopApi()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "limiter", None)
    monkeypatch.setattr(server, "_existing_api", _REAL_EXISTING_API)
    return fake


SRC = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}


def _written(fake) -> dict:
    """The graphql-definition.json create_backend sent with updateDefinition."""
    update = [c for c in fake.created if c["route"].endswith("updateDefinition")]
    assert len(update) == 1, fake.created
    part = next(p for p in update[0]["body"]["definition"]["parts"] if p["path"] == "graphql-definition.json")
    return json.loads(base64.b64decode(part["payload"]))


def _fields(body: dict, table: str) -> dict[str, tuple]:
    o = next(o for ds in body["datasources"] for o in ds["objects"] if o["sourceObject"] == f"shop.{table}")
    return {r["field"]: (r["targetObject"], tuple(r["sourceFields"]), r["cardinality"]) for r in o["relationships"]}


def test_the_live_call_keeps_the_apis_field_names_and_updates_in_place(fabric):
    out = json.loads(server.create_backend(**SRC, name="shop_api", confirmed=[AS_ASKED]))
    assert out.get("kind") != "would_remove", out
    assert out["result"]["status"] == "Succeeded" and out["result"]["mode"] == "updated"
    written = _written(fabric)
    assert _fields(written, "addresses")["orders"] == ("shop.orders", ("address_id",), "OneToMany")
    assert "orders_as_ship_to" not in _fields(written, "addresses") and "address" in _fields(written, "orders")
    assert written == decode({"definition": _live_api_definition()})                 # the API is left as it was
    assert out["names_kept_from_api"] == [{"table": "shop.addresses", "field": "orders", "instead_of": "orders_as_ship_to",
                                           "relationship": "orders.ship_to_id -> addresses.address_id"}]


def test_plan_drift_sees_no_drift_for_the_same_relationship_under_the_apis_name(fabric):
    out = json.loads(server.plan_drift(**SRC, api="shop_api", confirmed=[AS_ASKED]))
    assert out["would_change"] is False and out["summary"].startswith("no drift"), out
    assert out["relationships_unsupported"] == [] and out["new_relationships"] == []
    assert out["names_kept_from_api"][0]["field"] == "orders"


def test_keep_with_confirmed_carries_both_field_names_and_following_it_changes_nothing(fabric):
    stopped = json.loads(server.create_backend(**SRC, name="shop_api"))
    assert stopped["kind"] == "would_remove" and not fabric.created
    assert stopped["keep_with_confirmed"] == [LIVE_NAMES]
    drift = json.loads(server.plan_drift(**SRC, api="shop_api"))
    assert drift["keep_with_confirmed"] == [LIVE_NAMES]
    out = json.loads(server.create_backend(**SRC, name="shop_api", confirmed=drift["keep_with_confirmed"]))
    assert out["result"]["status"] == "Succeeded" and _written(fabric) == decode({"definition": _live_api_definition()})


def test_a_name_given_in_confirmed_wins_and_a_rename_is_still_a_removal(fabric):
    out = json.loads(server.create_backend(**SRC, name="shop_api", confirmed=[{**gs.SHIP_TO, "field_name": "address",
                                                                              "reverse_name": "shipments"}]))
    assert out["kind"] == "would_remove" and not fabric.created
    assert [r["field"] for r in out["relationships_lost"]] == ["orders"]              # what an app queries today would go
    assert out["keep_with_confirmed"] == [LIVE_NAMES]


def test_the_entry_without_field_names_keeps_both_of_the_apis_names(fabric):
    """docs/LIVE-TEST.md section 3 passes the relationship without names; the API's address and orders stay."""
    out = json.loads(server.create_backend(**SRC, name="shop_api", confirmed=[gs.SHIP_TO]))
    assert out["result"]["status"] == "Succeeded" and _written(fabric) == decode({"definition": _live_api_definition()})
    assert [(k["table"], k["field"], k["instead_of"]) for k in out["names_kept_from_api"]] == [
        ("shop.orders", "address", "ship_to"), ("shop.addresses", "orders", "orders_as_ship_to")]
    assert json.loads(server.plan_drift(**SRC, api="shop_api", confirmed=[gs.SHIP_TO]))["would_change"] is False


def test_a_name_that_would_clash_is_not_taken_from_the_api():
    """An API name that another field of the same type already uses in the plan is left alone (the update then reports
    the relationship as one to keep, as before)."""
    from fabric_backend import drift, seed
    from fabric_backend.graphql import definition
    from fabric_backend.infer import plan
    p = plan(seed.schema("shop"), confirmed=[gs.SHIP_TO])
    api = decode(definition(plan(seed.schema("shop"), confirmed=[{**gs.SHIP_TO, "field_name": "customer"}]), "shop_api", gs.WS, gs.EP))
    kept_plan, kept = drift.keep_api_names(p, api)
    ship = next(r for r in kept_plan.relationships if r.source_cols == ["ship_to_id"])
    assert ship.field_name == "ship_to" and all(k["field"] != "customer" for k in kept)     # orders.customer is customer_id's
