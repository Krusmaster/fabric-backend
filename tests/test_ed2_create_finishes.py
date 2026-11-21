"""ED2: Gustav's editor test of 21 November 2026, part 2 (the Dry run step and two Creates), on the Fabric doubles.

The editor's own order, Fix and finish, the shared error and the freshest review are tested in
workload/Workload/app/items/ModelItem/ed2Create.test.ts; here the engine's side with a fake Fabric client:
- a lakehouse name taken (409, or by another item) -> the next free name, said once; the dry run names it first;
- a workspace with no lakehouse -> the dry run says which lakehouse Create makes, and Create makes it;
- the report's model definition answering 404 a few times -> waited for with longer pauses, then the report is drawn;
- this item's own items from an older plan are updated in place, not "choose a new name";
- the data product's owner is the signed-in person by default; the grouping is one function everywhere;
- Run once on: the pipeline card says it runs once and that no schedule is set, with how to add one.
Synthetic shop data only; nothing reaches Fabric.
"""
from __future__ import annotations

import pytest
import requests

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, keys  # noqa: E402,F401
from test_workload_create import _post, _review, make  # noqa: E402,F401
from test_n221_build_in import OUTPUTS, SANDVIK, TwoWorkspaces, _in, _writes  # noqa: E402
from fabric_backend import domains, server, workload_api  # noqa: E402


class InUse(TwoWorkspaces):
    """Fabric answers 409 "is already in use" for lakehouse names in `held` (an item deleted a moment ago)."""

    def __init__(self, held=(), sandvik_items=()):
        super().__init__(sandvik_items)
        self.held = {h.lower() for h in held}
        self.lakehouse_posts: list[str] = []

    def _route(self, method, url, body=None):
        path = url.split("?")[0]
        if method == "POST" and path.endswith(f"/workspaces/{SANDVIK}/lakehouses"):
            self.lakehouse_posts.append(body.get("displayName"))
            if str(body.get("displayName")).lower() in self.held:
                self.calls.append((method, path))
                return gs.Response(409, {"errorCode": "ItemDisplayNameAlreadyInUse",
                                         "message": f"Requested '{body.get('displayName')}' is already in use"})
        return super()._route(method, url, body)


def _create_all(client, priv, rv, outputs, tick, created=None):
    created = list(created or [])
    answers = []
    for o in outputs:
        out = _post(client, "/build", {**SRC, "review": rv, "outputs": outputs, "only": [o["kind"]], "dry_run": False,
                                       "created": created, "skip_built": True, **tick}, priv).json()
        answers.append(out)
        created += [c for c in out.get("outputs", [{}])[0].get("created", [])] if out.get("outputs") else []
    return answers, created


# ------------------------------------------------------------------ 4. the lakehouse name -------------------------

def test_a_name_held_by_fabric_409_moves_to_the_next_free_name_said_once(make):
    client, fake, priv = make(InUse(held=["shop_lh"]))
    rv = _review(client, priv)
    tick = _in(create_lakehouse="shop_lh")
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:2], "dry_run": True, "created": [], **tick}, priv).json()
    assert dry["lakehouse"] == {"name": "shop_lh", "action": "make", "words": "Create will make the lakehouse shop_lh for silver and gold.",
                                "rule": workload_api.LAKEHOUSE_NAME_RULE}
    assert not _writes(fake)
    answers, created = _create_all(client, priv, rv, OUTPUTS[:2], tick)
    assert fake.lakehouse_posts == ["shop_lh", "shop_lh_2"]          # one 409, then the next free name, once
    first = answers[0]
    assert first["lakehouse"]["name"] == "shop_lh_2" and "shop_lh was in use" in first["lakehouse"]["words"]
    assert answers[1]["lakehouse"]["action"] == "use" and answers[1]["lakehouse"]["name"] == "shop_lh_2"   # gold: the same one
    lh = [i for i in fake.sandvik if i["type"] == "Lakehouse"]
    assert [i["displayName"] for i in lh] == ["shop_lh_2"]
    assert {c["name"] for c in created} == {"demo_lh_silver", "demo_lh_gold"}


def test_a_name_taken_by_another_item_is_moved_before_create_and_the_dry_run_says_so(make):
    taken = [{"id": "nb-1", "displayName": "shop_lh", "type": "Notebook", "description": "made by hand"}]
    client, fake, priv = make(InUse(sandvik_items=taken))
    rv = _review(client, priv)
    tick = _in(create_lakehouse="shop_lh")
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:1], "dry_run": True, "created": [], **tick}, priv).json()
    assert dry["lakehouse"]["name"] == "shop_lh_2"
    assert dry["lakehouse"]["words"] == ("Create will make the lakehouse shop_lh_2 for silver and gold "
                                         "(shop_lh is taken by a Notebook, so the next free name is used).")
    _create_all(client, priv, rv, OUTPUTS[:1], tick)
    assert fake.lakehouse_posts == ["shop_lh_2"]                    # no 409: the name was checked first


def test_an_existing_lakehouse_of_that_name_is_used_not_made_again(make):
    there = [{"id": "11111111-2222-3333-4444-555555555555", "displayName": "shop_lh", "type": "Lakehouse", "description": ""}]
    client, fake, priv = make(InUse(sandvik_items=there))
    rv = _review(client, priv)
    tick = _in(create_lakehouse="shop_lh")
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:1], "dry_run": True, "created": [], **tick}, priv).json()
    assert dry["lakehouse"]["action"] == "use" and "already in this workspace" in dry["lakehouse"]["words"]
    _create_all(client, priv, rv, OUTPUTS[:1], tick)
    assert fake.lakehouse_posts == []


def test_without_a_lakehouse_the_default_is_named_after_the_data_product_never_test():
    assert workload_api.default_lakehouse_name({"product": {"name": "Shop orders"}, "source_name": "shop_lh"}) == "Shop_orders_lh"
    assert workload_api.default_lakehouse_name({"item_name": "shop model", "source_name": "shop_lh"}) == "shop_model_lh"
    assert workload_api.default_lakehouse_name({"source_name": "shop_lh"}) == "shop_lh_krusgraph"
    for req in ({"product": {"name": "x"}}, {"item_name": "y"}, {"source_name": "z"}):
        assert "_test" not in workload_api.default_lakehouse_name(req)


def test_free_name_rule():
    items = [{"displayName": "a", "type": "Notebook"}, {"displayName": "a_2", "type": "Lakehouse"}]
    assert workload_api.free_lakehouse_name("a", items) == {"name": "a_2", "action": "use", "asked": "a"}
    assert workload_api.free_lakehouse_name("a", items, ("a_2",))["name"] == "a_3"
    assert workload_api.free_lakehouse_name("b", items) == {"name": "b", "action": "make"}


def test_a_workspace_without_a_lakehouse_gets_one_made_by_create(make):
    client, fake, priv = make(InUse())
    rv = _review(client, priv)
    product = {"product": {"name": "shop"}}
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:2], "dry_run": True, "created": [], **product, **_in()},
                priv).json()
    assert dry["lakehouse"]["words"] == "Create will make the lakehouse shop_lh for silver and gold."
    assert not dry["refused"]
    answers, _ = _create_all(client, priv, rv, OUTPUTS[:2], {**product, **_in()})
    assert fake.lakehouse_posts == ["shop_lh"]
    assert not [a for a in answers if a.get("error")]


# ------------------------------------------------------------------ 6. the report's model definition --------------

def test_report_waits_longer_for_a_new_models_definition_then_succeeds(monkeypatch):
    calls, slept = [], []

    def parts(ws, kind, iid, headers, fmt=None):
        calls.append(iid)
        if len(calls) <= 4:
            resp = requests.Response()
            resp.status_code = 404
            resp._content = b'{"errorCode": "EntityNotFound", "message": "not yet"}'
            raise requests.HTTPError(response=resp)
        return {"model.tmdl": "model Model"}

    monkeypatch.setattr(server, "_item_definition_parts", parts)
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    with pytest.raises(server._ModelNotReadable) as e:                 # the chat's 40-second answer: three tries
        server._fresh_model_definition("ws", "m1", {}, give_up_at=__import__("time").monotonic() + 30)
    assert e.value.attempts == 3 and "404" in e.value.reason
    calls.clear(), slept.clear()
    token = server.MODEL_WAIT.set(workload_api.REPORT_MODEL_WAIT_SECONDS)   # the editor's background step
    try:
        got = server._fresh_model_definition("ws", "m1", {}, give_up_at=__import__("time").monotonic() + 250)
    finally:
        server.MODEL_WAIT.reset(token)
    assert got == {"model.tmdl": "model Model"} and len(calls) == 5
    assert slept == list(server.MODEL_DEFINITION_PAUSES_LONG[:4])     # longer and longer waits
    assert sum(server.MODEL_DEFINITION_PAUSES_LONG) < workload_api.REPORT_MODEL_WAIT_SECONDS


def test_the_report_hint_offers_try_again_on_the_report_only():
    import inspect
    src = inspect.getsource(server.create_report)
    assert "Choose Try again on the report in a minute: only the report is sent" in src
    assert "Choose Create again in a minute" not in src


# ------------------------------------------------------------------ 2, 7, 8, 10 -----------------------------------

def test_owner_is_the_signed_in_person_by_default_and_said_the_same_everywhere():
    assert workload_api.product_owner({"by": "someone@example.com"}) == "someone@example.com"
    assert workload_api.product_owner({"by": "a@example.com", "product": {"name": "p", "owner": "Data team"}}) == "Data team"
    assert workload_api.owner_words("Data team") == "Owner: Data team. Change it on the Choose step."
    assert "nobody" not in workload_api.owner_words(None).lower()


def test_one_grouping_of_data_products_everywhere():
    """The suggestions, the dry run's and the result's data product, and the site's demo: one function, and a row check
    never moves a table between products."""
    from fabric_backend import demo
    from fabric_backend.infer import plan
    from fabric_backend.seed import schema
    p = plan(schema("shop"), keys=demo.DEMO_KEYS)
    one = [(d["name"], sorted(d["tables"])) for d in domains.data_products(p)["domains"]]
    weak = {"relationships": [{"source": r.source, "columns": r.source_cols, "target": r.target, "verdict": "orphans", "orphans": 3}
                              for r in p.relationships], "keys": []}
    sugg = [(x["name"], sorted(x["tables"])) for x in workload_api.suggest_products(p, weak)["products"]]
    site = [(x["name"], sorted(x["tables"])) for x in demo._drafts(p)["domains"]["domains"]]
    assert one == sugg == site and one


def test_run_once_card_says_no_schedule_and_how_to_add_one():
    o = {"name": "p", "jobs": {"run_once": True, "schedule": None}}
    card = workload_api._jobs_card(o, {}, {"granted": True}, True)
    assert card["words"][-1] == workload_api.NO_SCHEDULE_LINE
    assert "adds none" not in " ".join(card["words"])


# ------------------------------------------------------------------ 1. the review and check the dry run uses -------

def test_review_and_check_now_dry_run_shows_todays_check_and_no_stale_rejection(make):
    """The dry run counts what it is sent, so the editor sends the freshest review (ed2Create.freshestReview: a re-read of
    an older saved review never replaces a check run meanwhile). Here: a review, a check now, and the dry run on it shows
    today's check time and leaves nothing out because of a review the person did not make."""
    import datetime as dt
    client, fake, priv = make(InUse())
    rv = _review(client, priv)
    checked = _post(client, "/check", {**SRC, "review": rv}, priv).json()["review"]
    old = {**checked, "items": [{**it, **({"check": {**it["check"], "checked_at": "2026-11-11T20:23:00Z"}} if it.get("check") else {})}
                                for it in checked["items"]]}
    dry = _post(client, "/build", {**SRC, "review": checked, "outputs": OUTPUTS[:1], "dry_run": True, "created": []}, priv).json()
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    assert dry["row_check"]["checked"] and dry["row_check"]["checked_at"].startswith(today)
    assert dry["left_out_by_review"] == []
    stale = _post(client, "/build", {**SRC, "review": old, "outputs": OUTPUTS[:1], "dry_run": True, "created": []}, priv).json()
    assert stale["row_check"]["checked_at"].startswith("2026-11-11")   # what the old one would have said
