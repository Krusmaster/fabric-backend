"""W3 (Gustav's run of 23 November 2026 in a real tenant): "Publish to OneLake catalog" also describes the Krusgraph
Model item itself, which kept Fabric's "Make this item more discoverable by adding a description", and no description
carries the owner's name any more (the owner is the card's field; a later owner change would leave a stale name).
The Model item is written the same way as the others: Items - Update Item, shown in the diff, covered by the dry run's
confirm, only in a workspace on the operator's list; a description only, no tags. Synthetic shop schema only."""
import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from fabric_backend import catalog_publish as cp  # noqa: E402
from fabric_backend.catalog_publish import recorded, writes  # noqa: E402
from tests.test_ca1_catalog import DAY, TAGS, _answer, _items, shop  # noqa: E402,F401
from test_workload_api import SRC, _post, _writes, api, keys, tok  # noqa: E402,F401

MODEL = {"id": "model-1", "displayName": "shop_product", "type": "Org.Krusgraph.Model", "description": "", "tags": []}
MODEL_ID = "cccccccc-0000-4000-8000-0000000000a1"


def test_no_description_carries_the_owner(shop):
    a = _answer(shop, owners={"customers": "KJELL GUSTAV KRUSE", "products": "Data team"})
    assert [c["owner"] for c in a["products"]] == ["KJELL GUSTAV KRUSE", "Data team"]          # on the card, as before
    for text in [c["description"] for c in a["products"]] + [w["after"] for w in a["writes"] if w["field"] == "description"]:
        assert "Owner" not in text and "KRUSE" not in text and "Data team" not in text, text
    owner_row = next(r for r in cp.apis.ROLES if r["action"] == "Set the owner or contact")
    assert "never in a description" in owner_row["krusgraph"]


def test_the_model_item_is_described_first_with_the_counts_and_what_was_built(shop):
    a = _answer(shop, model_item=MODEL)
    w = a["writes"][0]
    assert w["item"] == "shop_product" and w["field"] == "description" and w["operation"] == "Items_UpdateItem"
    assert w["method"] == "PATCH" and w["url"].endswith("/v1/workspaces/ws-1/items/model-1") and w["model_item"] is True
    assert w["after"] == ("Krusgraph data products customers and products over demo_lh: 6 of 6 keys unique, "
                          "6 of 6 links holding, checked 17 Nov 2026. Built: silver_shop.")
    assert len(w["after"]) <= cp.DESCRIPTION_MAX
    assert a["diff"][0] == {"item": "shop_product", "type": "Org.Krusgraph.Model", "field": "description", "before": "",
                            "after": w["after"], "action": "write", "model_item": True}
    assert not [x for x in a["writes"] if x["item"] == "shop_product" and x["field"] == "tags"]     # a description only
    assert a["undo"][0]["body"] == {"description": ""}
    assert a["confirm"] != _answer(shop)["confirm"]                       # the confirm covers the Model item's write too


def test_a_persons_own_sentence_is_kept_and_a_second_run_does_not_repeat_ours(shop):
    own = {**MODEL, "description": "Sales data for the Nordic team. Ask in #data."}
    first = _answer(shop, model_item=own)["writes"][0]["after"]
    assert first.startswith("Sales data for the Nordic team. Krusgraph data products customers and products over demo_lh")
    again = _answer(shop, model_item={**MODEL, "description": first + " Old note."})["writes"][0]["after"]
    assert again == first and again.count("Krusgraph data products") == 1   # ours replaced, the person's sentence kept
    same = _answer(shop, model_item={**MODEL, "description": _answer(shop, model_item=MODEL)["writes"][0]["after"]})
    assert not [w for w in same["writes"] if w["item"] == "shop_product"]  # nothing to write when it already says it


def test_a_long_list_of_built_items_is_shortened_never_the_counts():
    many = [f"item_number_{i:02d}_with_a_long_name" for i in range(12)]
    texts = cp.model_texts([{"name": "customers"}], "demo_lh", {"keys": [{"table": "t", "rows": 3, "status": "passed"}],
                                                               "relationships": [{"source": "a", "target": "b", "orphans": 2}]},
                           "2026-11-23", many)
    fit = writes.new_description(MODEL, texts)
    assert fit.startswith("Krusgraph data product customers over demo_lh: 1 of 1 key unique, 0 of 1 link holding, checked 23 Nov 2026.")
    assert "more." in fit and len(fit) <= cp.DESCRIPTION_MAX


def test_without_a_check_nothing_is_claimed():
    texts = cp.model_texts([{"name": "customers"}], "demo_lh", None, None, [])
    assert texts == ["Krusgraph data product customers over demo_lh: keys and links not yet checked against the rows."]


# ------------------------------------------------------------------ the editor's route ------------------------------

def _review(client, priv):
    return _post(client, "/review", SRC, tok(priv)).json()["review"]


def test_the_route_writes_the_model_item_only_with_the_confirm(api, monkeypatch):
    client, fake, _, priv = api
    stamp = recorded.with_recorded
    monkeypatch.setattr(recorded, "with_recorded", lambda v, r, now: stamp(v, r, "2026-11-23T19:09Z"))
    monkeypatch.setattr(gs, "ITEMS", gs.ITEMS + [{"id": MODEL_ID, "displayName": "shop_product", "type": "Org.Krusgraph.Model"}])
    rv = _review(client, priv)
    fake.calls.clear()
    body = {**SRC, "review": rv, "item_id": MODEL_ID.upper()}
    dry = _post(client, "/catalog", body, tok(priv)).json()
    assert dry["workspace"] == gs.WS.lower()
    row = dry["diff"][0]
    assert row["item"] == "shop_product" and row["action"] == "write" and row["model_item"] is True
    assert row["after"].startswith("Krusgraph data products customers and products over demo_lh:")
    assert dry["confirm"] and _writes(fake) == []                         # the dry run writes nothing
    monkeypatch.delenv(writes.ALLOW_ENV, raising=False)
    no = _post(client, "/catalog", {**body, "dry_run": False, "confirm": dry["confirm"]}, tok(priv)).json()
    assert no["kind"] == "not_allowed" and _writes(fake) == []
    monkeypatch.setenv(writes.ALLOW_ENV, gs.WS)
    real = fake._route

    def route(method, url, body=None):
        if method == "PATCH" and "/items/" in url:
            fake.calls.append((method, url))
            return gs.Response(200, {})
        return real(method, url, body)
    monkeypatch.setattr(fake, "_route", route)
    out = _post(client, "/catalog", {**body, "dry_run": False, "confirm": dry["confirm"]}, tok(priv)).json()
    assert [r["item"] for r in out["results"]] == ["shop_product"] and all(r["ok"] for r in out["results"])
    assert [c for c in _writes(fake)] == [("PATCH", f"https://api.fabric.microsoft.com/v1/workspaces/{gs.WS}/items/{MODEL_ID}")]


def test_an_item_id_that_is_not_a_model_item_is_not_described(api, monkeypatch):
    client, _, _, priv = api
    rv = _review(client, priv)
    out = _post(client, "/catalog", {**SRC, "review": rv, "item_id": gs.API}, tok(priv)).json()   # an API, not the Model item
    assert not [r for r in out["diff"] if r.get("model_item")]
    assert _post(client, "/catalog", {**SRC, "review": rv, "item_id": "not-a-guid"}, tok(priv)).status_code == 400
