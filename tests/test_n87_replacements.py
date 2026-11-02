"""n87, point 6: no silent replacement. export_item_definitions of shop_api left out orders.address, which the live API
has, without a word; create_semantic_model's dry run with an existing name and fewer tables did not say the model would
be replaced. Now the export keeps the API's names for the same relationships and names what the files would drop, and
the dry run says which tables, relationships and measures of the existing model disappear. Against the golden doubles
(Fabric answered from memory, an SQL endpoint backed by SQLite)."""
import base64
import json

import pytest

import tests.test_create_backend_names as live
from fabric_backend import server
from tests.test_golden import SRC, fabric  # noqa: F401  (fabric: fixture)


def _api_file(out: dict, name: str = "shop_api") -> dict:
    return json.loads(out["files"][f"{name}.GraphQLApi/graphql-definition.json"])


def _fields(body: dict, table: str) -> set[str]:
    o = next(o for ds in body["datasources"] for o in ds["objects"] if o["sourceObject"] == f"shop.{table}")
    return {r["field"] for r in o.get("relationships", [])}


def test_the_export_of_an_existing_api_keeps_its_field_names(monkeypatch):
    with pytest.MonkeyPatch.context() as mp:
        live.fabric.__wrapped__(mp)                                   # the API as it is live: orders.address, addresses.orders
        out = json.loads(server.export_item_definitions(**SRC, items=["create_backend"], names={"create_backend": "shop_api"}))
        body = _api_file(out)
        assert "address" in _fields(body, "orders") and "orders" in _fields(body, "addresses")
        assert out["existing_api"]["names_kept_from_api"]


def test_the_export_says_what_it_would_drop_from_the_live_api(monkeypatch):
    with pytest.MonkeyPatch.context() as mp:
        live.fabric.__wrapped__(mp)
        mp.setattr(server, "R5_MAX_QUERIES", 0)                       # R5 not counted: the plan lacks ship_to_id -> addresses
        out = json.loads(server.export_item_definitions(**SRC, items=["create_backend"], names={"create_backend": "shop_api"}))
        lost = out["existing_api"]["relationships_lost"]
        assert lost and any(r["field"] == "address" for r in lost)
        assert any("shop_api" in n and "would remove" in n for n in out["notes"])
        assert out["existing_api"]["keep_with_confirmed"]


def test_create_semantic_model_dry_run_names_what_the_replacement_removes(fabric):
    out = json.loads(server.create_semantic_model(**SRC, name="shop_model", tables=["orders", "customers"]))
    r = out["replaces"]
    assert r["existing"] is True and "replaced" in r["said"]
    assert {"Order Lines", "products", "categories", "addresses"} <= set(r["tables_gone"])
    assert any("Order Lines" in x for x in r["relationships_gone"])
    assert "orders[Total order id]" in r["measures_gone"]
    assert list(out)[0] == "replaces" or out["summary"].startswith("replaces")


def test_a_new_name_says_nothing_is_replaced(fabric):
    out = json.loads(server.create_semantic_model(**SRC, name="shop_model_v2"))
    assert "replaces" not in out
