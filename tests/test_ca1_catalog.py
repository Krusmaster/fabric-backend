"""CA1: Publish to OneLake catalog. Product cards from the plan, domain_draft and validate_plan's counts; the diff of
what would be written as the signed-in user (descriptions, existing tags); handover files for what needs a Fabric
admin, a Purview steward or a reviewer; a dry run by default; writes only with the dry run's confirm and in a workspace
on the operator's list; endorsement never set. Synthetic shop schema only."""
import json

import pytest

import golden_support as gs
from fabric_backend import catalog_publish as cp, evidence, seed, server
from fabric_backend.catalog_publish import apis, purview, quality, writes
from fabric_backend.infer import plan
from tests.test_golden import SRC, fabric  # noqa: F401

DAY = "2026-11-17"
MARKED = "Built by Krusgraph [Krusgraph plan plan-abc, schema shop (sha256:12ab), 6 links]"


def _validation(p):
    db = gs.shop_database()

    def execute(sql):
        cur = db.execute(gs._sqlite(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return evidence.validate(p, execute)


@pytest.fixture(scope="module")
def shop():
    p = plan(seed.schema("shop"))
    return p, _validation(p)


def _items():
    return [{"id": "lh", "displayName": "demo_lh", "type": "Lakehouse", "description": "Our own words", "tags": []},
            {"id": "sm", "displayName": "shop_model", "type": "SemanticModel", "description": MARKED,
             "tags": [{"id": "t-k", "displayName": "Krusgraph"}]},
            {"id": "nb", "displayName": "silver_shop", "type": "Notebook", "description": "", "tags": []}]


TAGS = [{"id": "t-k", "displayName": "Krusgraph"}, {"id": "t-c", "displayName": "customers"}]


def _answer(shop, **kw):
    p, v = shop
    args = dict(source="demo_lh", validation=v, checked_on=DAY, created_ids={"nb"}, tenant_tags=TAGS)
    args.update(kw)
    return cp.prepare(p, "shop", "ws-1", _items(), **args)


# ------------------------------------------------------------------ the cards ------------------------------------

def test_a_card_per_product_with_everything_a_catalog_entry_needs(shop):
    a = _answer(shop, owners={"customers": "Data team"})
    names = [c["name"] for c in a["products"]]
    assert names == ["customers", "products"]
    c = a["products"][0]
    for k in ("description", "owner", "domain", "tags", "contract", "glossary", "evidence", "quality_rules"):
        assert c[k], k
    assert c["owner"] == "Data team" and a["products"][1]["owner"] == "not chosen yet"
    assert len(c["description"]) <= cp.DESCRIPTION_MAX and "Owner: Data team." in c["description"]
    assert c["evidence"]["line"] == ("4 of 4 keys unique, 0 orphan rows over 3 links inside customers, 1 link between "
                                     "customers and products and 1 link to tables in no data product, checked 17 Nov 2026")
    assert c["contract"]["yaml"].startswith("# ODCS v3.2.0") and c["contract"]["file"] == "contracts/customers.odcs.yaml"
    assert c["tags"] == ["Krusgraph", "customers"]
    assert {t["term"] for t in c["glossary"]} == {"Addresses", "Customers", "Order items", "Orders"}
    assert "a proposal" in c["domain"]["note"]


def test_without_counts_nothing_is_claimed(shop):
    p, _ = shop
    a = cp.prepare(p, "shop", "ws-1", _items(), validation=None, created_ids={"nb"}, tenant_tags=TAGS)
    for c in a["products"]:
        assert not c["evidence"]["counted"] and "not yet checked" in c["description"]
        assert {r["status"] for r in c["quality_rules"]} == {"not counted"}
        assert "unique" not in c["description"]


def test_quality_rules_follow_what_was_proven(shop):
    p, v = shop
    rules = quality.rules(p, [t.name for t in p.schema], "shop", v, DAY)
    kinds = {r["kind"] for r in rules}
    assert kinds == {"unique_key", "no_orphans", "rows_kept_after_join"}
    assert all(r["must_be"] == 0 and r["sql"].startswith("SELECT") for r in rules)
    grain = next(r for r in rules if r["kind"] == "rows_kept_after_join")
    assert grain["table"] == "order_items" and grain["target"] == "products" and grain["status"] == "proven"
    assert grain["grain"]["header_amounts"] == ["list_price"]
    # every rule's SQL counts 0 on the shop rows, as the rule says
    db = gs.shop_database()
    for r in rules:
        assert db.execute(gs._sqlite(r["sql"])).fetchone()[0] == 0, r["id"]


def test_a_broken_rule_is_proposed_not_proven(shop):
    p, v = shop
    bad = json.loads(json.dumps(v))
    bad["relationships"][0]["orphans"] = 3
    bad["relationships"][0]["verdict"] = "3 orphans"
    rules = quality.rules(p, [t.name for t in p.schema], "shop", bad, DAY)
    r = next(x for x in rules if x["kind"] == "no_orphans" and x["table"] == v["relationships"][0]["source"])
    assert r["status"] == "proposed" and r["verdict"] == "3 orphans"


# ------------------------------------------------------------------ the diff -------------------------------------

def test_the_diff_writes_only_what_the_user_may_and_keeps_other_peoples_words(shop):
    a = _answer(shop)
    by = {(w["item"], w["field"]): w for w in a["writes"]}
    assert set(by) == {("shop_model", "description"), ("silver_shop", "description"),
                       ("silver_shop", "tags"), ("shop_model", "tags")}
    assert not any(w["item"] == "demo_lh" for w in a["writes"])      # WB10: not built by Krusgraph: offered, unticked
    assert [o["item"] for o in a["optional"]] == ["demo_lh"]
    row = next(d for d in a["diff"] if d["item"] == "demo_lh")
    assert row["action"] == "optional" and "did not build demo_lh" in row["why"] and row["after"].startswith("Our own words. ")
    assert by[("shop_model", "description")]["after"].endswith("[Krusgraph plan plan-abc, schema shop (sha256:12ab), 6 links]")
    assert by[("shop_model", "description")]["after"].startswith("Built by Krusgraph. Data products customers and products")
    assert by[("shop_model", "tags")]["body"] == {"tags": ["t-c"]}   # Krusgraph is there already: only adds
    assert [w["field"] for w in a["writes"]][:2] == ["description", "description"]
    assert {w["operation"] for w in a["writes"]} == {"Items_UpdateItem", "Tags_ApplyTags"}
    assert all(len(w["after"]) <= 256 for w in a["writes"] if w["field"] == "description")
    assert [d["action"] for d in a["diff"]].count("kept") == len(a["kept"])


def test_undo_puts_back_what_was_there(shop):
    a = _answer(shop)
    undo = {(u["item"], u["operation"]): u for u in a["undo"]}
    assert undo[("shop_model", "Items_UpdateItem")]["body"] == {"description": MARKED}
    assert undo[("shop_model", "Tags_UnapplyTags")]["body"] == {"tags": ["t-c"]}
    assert undo[("shop_model", "Tags_UnapplyTags")]["url"].endswith("/unapplyTags")


def test_missing_tags_go_to_the_admin_and_unreadable_tags_use_the_workspace(shop):
    a = _answer(shop, tenant_tags=[], tags_readable=False, workspace_tags=[{"id": "t-k", "displayName": "Krusgraph"}])
    assert all(w["body"] == {"tags": ["t-k"]} for w in a["writes"] if w["field"] == "tags")
    req = next(r for r in a["handover"]["requests"] if r["step"] == "Create the tags")
    assert req["by"] == "fabric_admin" and "Tag.Read.All" in req["why"]
    assert {t["displayName"] for t in req["body"]["createTagsRequest"]} == {"customers", "products"}


def test_ten_tags_at_most(shop):
    p, v = shop
    full = [{"id": f"x{i}", "displayName": f"x{i}"} for i in range(9)]
    items = [{"id": "nb", "displayName": "nb", "type": "Notebook", "description": "", "tags": full}]
    a = cp.prepare(p, "shop", "ws-1", items, validation=v, checked_on=DAY, created_ids={"nb"},
                   tenant_tags=TAGS + [{"id": "t-p", "displayName": "products"}])
    t = next(w for w in a["writes"] if w["field"] == "tags")
    assert len(t["body"]["tags"]) == 1 and any(k["field"] == "tags" for k in a["kept"])


# ------------------------------------------------------------------ handover and endorsement -----------------------

def test_handover_names_who_must_approve_and_never_endorses(shop):
    a = _answer(shop)
    h = a["handover"]
    assert set(h["files"]) >= {"handover/fabric-admin.md", "handover/endorsement.md", "handover/purview.json",
                               "contracts/customers.odcs.yaml"}
    bys = {r["by"] for r in h["requests"]}
    assert {"fabric_admin", "workspace_admin", "reviewer"} <= bys and "you" not in bys
    assert all(r["method"] is None for r in h["requests"] if r["by"] == "reviewer")
    assert "Krusgraph does not endorse" in h["files"]["handover/endorsement.md"]
    bodies = [r.get("body") or r["rule"] for prod in h["purview"]["products"] for r in prod["requests"]]
    assert all("endorsed" not in b for b in bodies)
    assert not any("endors" in w["url"].lower() for w in a["writes"])


def test_purview_requests_are_handed_over_with_its_rule_types(shop):
    a = _answer(shop)
    pv = a["handover"]["purview"]
    assert pv["retiring"] == apis.PURVIEW_RETIRING
    rules = [r for prod in pv["products"] for r in prod["rules"]]
    types = {r["rule_type"] for r in rules}
    assert types <= {"Unique values", "Duplicate rows", "Empty/blank fields", "Table lookup", None}
    assert {"Unique values", "Empty/blank fields", "Table lookup"} <= types
    for prod in pv["products"]:
        assert [r["by"] for r in prod["requests"]][:2] == ["purview_domain_creator", "purview_steward"]
        assert all(r["url"].startswith(purview.ENDPOINT) for r in prod["requests"])


def test_every_role_cites_a_learn_page_read_today():
    assert apis.READ_ON == "2026-11-17"
    for r in apis.ROLES:
        url, when = apis.SOURCES[r["source"]]
        assert url.startswith("https://learn.microsoft.com/") and when
    assert any(r["action"].startswith("Certify") and r["krusgraph"] == "never" for r in apis.ROLES)


# ------------------------------------------------------------------ the guard -------------------------------------

def test_writing_needs_the_confirm_and_a_listed_workspace(shop, monkeypatch):
    a = _answer(shop)
    sent = []

    def send(method, url, body):
        sent.append((method, url, body))
        return 200
    monkeypatch.delenv(writes.ALLOW_ENV, raising=False)
    with pytest.raises(writes.NotAllowed, match="not listed"):
        cp.apply(a, "ws-1", a["confirm"], send)
    monkeypatch.setenv(writes.ALLOW_ENV, "other, WS-1")
    with pytest.raises(writes.NotAllowed, match="confirm"):
        cp.apply(a, "ws-1", None, send)
    with pytest.raises(writes.NotAllowed, match="changed"):
        cp.apply(a, "ws-1", "catalog-0000", send)
    assert not sent
    got = cp.apply(a, "ws-1", a["confirm"], send)
    assert [r["ok"] for r in got["results"]] == [True] * len(a["writes"])
    assert [(m, u) for m, u, _ in sent] == [(w["method"].lower(), w["url"]) for w in a["writes"]]


def test_a_refused_write_is_reported_and_the_rest_still_go(shop, monkeypatch):
    a = _answer(shop)
    monkeypatch.setenv(writes.ALLOW_ENV, "ws-1")
    got = cp.apply(a, "ws-1", a["confirm"], lambda m, u, b: 403 if "applyTags" in u else 200)
    assert any(not r["ok"] and "Contributor" in r["hint"] for r in got["results"])
    assert any(r["ok"] for r in got["results"])


def test_the_same_plan_gives_the_same_answer(shop):
    assert json.dumps(_answer(shop), sort_keys=True) == json.dumps(_answer(shop), sort_keys=True)


# ------------------------------------------------------------------ the MCP tool ----------------------------------

def test_publish_catalog_is_a_dry_run_by_default_and_sends_nothing(fabric):
    out = json.loads(server.publish_catalog(**SRC))
    assert "error" not in out, out
    assert out["confirm"] is None and "dry run" in out["note"]   # WB10: nothing of Krusgraph's here to write
    assert [c["name"] for c in out["products"]] == ["customers", "products"]
    assert [(d["item"], d["action"]) for d in out["diff"]] == [("demo_lh", "optional")]   # WB10: not Krusgraph's
    assert not [c for c in fabric.calls if c[0] != "GET"]
    assert not fabric.created


def test_publish_catalog_refuses_to_write_outside_the_allowed_workspaces(fabric, monkeypatch):
    monkeypatch.delenv(writes.ALLOW_ENV, raising=False)
    dry = json.loads(server.publish_catalog(**SRC))
    out = json.loads(server.publish_catalog(**SRC, dry_run=False, confirm=dry["confirm"]))
    assert out["kind"] == "not_allowed" and "Nothing was written" in out["hint"]
    assert not [c for c in fabric.calls if c[0] == "PATCH" or c[1].endswith("applyTags")]


def test_publish_catalog_writes_nothing_to_an_item_krusgraph_did_not_build(fabric, monkeypatch):
    # WB10 (Gustav's live test, 18 Nov 2026, #61): the lakehouse is the owner's: the tool offers it, never writes it
    monkeypatch.setenv(writes.ALLOW_ENV, gs.WS)
    dry = json.loads(server.publish_catalog(**SRC))
    assert dry["writes"] == [] and dry["confirm"] is None and [o["item"] for o in dry["optional"]] == ["demo_lh"]
    assert not [c for c in fabric.calls if c[0] == "PATCH" or c[1].endswith("applyTags")]
