"""ED3: Gustav's editor test of 21 November 2026, part 3: Publish to OneLake catalog and the handover files.

- the source lakehouse (shop's own, possibly in another workspace) is never written by default, even when an earlier
  write left Krusgraph's plan marker on it: opt-in, unticked, with one line why;
- no e-mail address in any description; the owner's contact only in Purview's add_by_hand.owner;
- one grouping (ED2's domains.data_products) for every card, contract and line; one contract per data product; the
  card totals add up to the page's;
- one description template for every item Krusgraph built;
- each handover file is exactly one clean file (valid YAML or JSON), and no file contains another;
- the Purview retirement sentence is quoted word for word from the Learn page read on 21 November 2026;
- the rules the recorded check did not reach take this step's fresh count, so they are proven, not "not counted".
Synthetic shop schema only; nothing reaches Fabric.
"""
import json
import re

import pytest
import yaml

from fabric_backend import catalog_publish as cp, domains
from fabric_backend.catalog_publish import apis, cards, recorded, writes
from tests.test_ca1_catalog import MARKED, TAGS, _items, shop  # noqa: F401

EMAIL = re.compile(r"[^\s()<>,;]+@[^\s()<>,;]+")
OWNER = "Data Steward (steward@contoso.example)"


def _answer(shop, **kw):
    p, v = shop
    args = dict(source="demo_lh", validation=v, checked_on="2026-11-21", created_ids={"nb"}, tenant_tags=TAGS)
    args.update(kw)
    return cp.prepare(p, "shop", "ws-1", _items(), **args)


def test_the_source_is_never_written_by_default_even_with_the_plan_marker_on_it(shop):  # noqa: F811
    items = _items()
    items[0] = {**items[0], "description": MARKED, "workspace": "ws-source"}      # an earlier write marked the source
    p, v = shop
    a = cp.prepare(p, "shop", "ws-1", items, source="demo_lh", validation=v, checked_on="2026-11-21", created_ids={"nb"},
                   tenant_tags=TAGS, source_id="lh")
    assert not [w for w in a["writes"] if w["item_id"] == "lh"]
    opt = [o for o in a["optional"] if o["item_id"] == "lh"]
    assert opt and opt[0]["why"] == "demo_lh belongs to its own workspace; tick to describe it too"
    ticked = cp.prepare(p, "shop", "ws-1", items, source="demo_lh", validation=v, checked_on="2026-11-21", created_ids={"nb"},
                        tenant_tags=TAGS, source_id="lh", include={"lh"})
    w = next(w for w in ticked["writes"] if w["item_id"] == "lh")
    assert "/workspaces/ws-source/items/lh" in w["url"]                              # its own workspace


def test_a_ticked_item_in_a_workspace_where_writing_is_off_is_refused(shop, monkeypatch):  # noqa: F811
    monkeypatch.setenv(writes.ALLOW_ENV, "ws-1")
    w = [{"method": "PATCH", "url": "https://api.fabric.microsoft.com/v1/workspaces/ws-source/items/lh", "body": {}, "before": ""}]
    with pytest.raises(writes.NotAllowed):
        writes.check_write("ws-1", w, writes.confirm_of("ws-1", w))


def test_no_email_address_in_any_description_and_the_contact_only_in_the_owner_field(shop):  # noqa: F811
    p, _ = shop
    slugs = [d["slug"] for d in domains.data_products(p)["domains"]]
    a = _answer(shop, owners={s: OWNER for s in slugs})
    for c in a["products"]:
        assert not EMAIL.search(c["description"]) and c["owner"] == "Data Steward"
        assert not EMAIL.search(c["contract"]["yaml"])
    for w in a["writes"]:
        assert not EMAIL.search(json.dumps(w["body"]))
    pv = json.loads(a["handover"]["files"]["handover/purview.json"])
    for prod in pv["products"]:
        for r in prod["requests"]:
            assert not EMAIL.search(json.dumps(r.get("body"))), r["step"]
        dp = next(r for r in prod["requests"] if r["step"].startswith("Data product"))
        assert dp["add_by_hand"]["owner"] == OWNER                                      # the owner field meant for it
    for path, text in a["handover"]["files"].items():
        if path != "handover/purview.json":
            assert not EMAIL.search(text), path


def test_owner_name_keeps_the_name_only():
    assert cards.owner_name("Eva Berg (eva@contoso.example)") == "Eva Berg"
    assert cards.owner_name("eva@contoso.example") is None
    assert cards.owner_name("Data team") == "Data team"


def test_one_grouping_one_contract_per_data_product_and_the_totals_agree(shop):  # noqa: F811
    p, _ = shop
    a = _answer(shop)
    want = domains.data_products(p)["domains"]
    assert [c["slug"] for c in a["products"]] == [d["slug"] for d in want]
    assert [c["tables"] for c in a["products"]] == [d["tables"] for d in want]
    files = a["handover"]["files"]
    contracts = sorted(k for k in files if k.startswith("contracts/"))
    assert contracts == sorted(f"contracts/{d['slug']}.odcs.yaml" for d in want)
    assert len(contracts) == len(a["products"]) >= 2
    for c in a["products"]:
        doc = yaml.safe_load(files[c["contract"]["file"]])
        assert doc["dataProduct"] == c["slug"]
    page = a["evidence"]
    keys = sum(len([k for k in c["evidence"].get("keys", [])]) for c in a["products"]) if "keys" in page else None
    assert keys is None or keys == len(page["keys"])


def test_every_item_krusgraph_built_gets_one_clean_description(shop):  # noqa: F811
    items = _items() + [{"id": "fx", "displayName": "shop_lh_orders_features", "type": "Notebook", "tags": [],
                         "description": "Krusgraph starter: a feature table from the keys and links proven on shop_lh"}]
    p, v = shop
    a = cp.prepare(p, "shop", "ws-1", items, source="demo_lh", validation=v, checked_on="2026-11-21",
                   created_ids={"nb", "fx"}, tenant_tags=TAGS, source_id="lh")
    after = next(w["after"] for w in a["writes"] if w["item_id"] == "fx" and w["field"] == "description")
    assert after.startswith("Krusgraph notebook shop_lh_orders_features. Data products ")
    assert "starter" not in after and after.count("Data product") == 1


def test_each_handover_file_is_one_clean_file_and_none_contains_another(shop):  # noqa: F811
    p, _ = shop
    a = _answer(shop, owners={d["slug"]: OWNER for d in domains.data_products(p)["domains"]})
    files = a["handover"]["files"]
    assert {"handover/endorsement.md", "handover/purview.json"} <= set(files)
    for path, text in files.items():
        if path.endswith(".json"):
            json.loads(text)
        elif path.endswith(".yaml"):
            docs = list(yaml.safe_load_all(text))
            assert len(docs) == 1 and isinstance(docs[0], dict), path
            assert '"retiring"' not in text and "purview" not in text.lower().split("description", 1)[0]
        for other, body in files.items():
            if other != path and len(body.strip()) > 40:
                assert body.strip() not in text, f"{path} contains {other}"
    # the chat's answer leaves the YAML and the Purview bodies out, but lists every file
    chat = cp.for_chat(a)
    assert set(chat["handover"]["files"]) | set(chat["handover"]["also"]) == set(files)


def test_the_purview_retirement_sentence_is_learns_word_for_word():
    # Learn, "Learn about Microsoft Purview Unified Catalog", ms.date 2026-10-13, updated 2026-11-12, read 21 Nov 2026
    page = ("Microsoft Purview Unified Catalog and classic Microsoft Purview data governance capabilities (formerly Azure "
            "Purview) are being retired. Microsoft is consolidating its data governance capabilities in Microsoft Fabric. "
            "New Microsoft Purview data governance accounts can no longer be created, and existing data governance "
            "capabilities will remain in maintenance mode through November 12, 2027.")
    assert apis.PURVIEW_RETIRING == page
    assert apis.PURVIEW_RETIRING_SOURCE == "https://learn.microsoft.com/en-us/purview/unified-catalog"
    assert "2026-11-12" in apis.PURVIEW_RETIRING_READ


def test_rules_the_recorded_check_did_not_reach_take_the_fresh_count():
    review = {"items": [{"id": "k1", "type": "key", "table": "customers", "columns": ["customer_id"], "review": "accepted",
                         "check": {"status": "passed", "checked_at": "2026-11-11T20:23Z",
                                   "result": {"rows": 5, "nulls": 0, "distinct": 5}, "verdict": "unique"}}]}
    fresh = {"keys": [{"table": "customers", "columns": ["customer_id"], "rows": 6, "nulls": 0, "distinct": 6, "verdict": "unique"},
                      {"table": "products", "columns": ["product_id"], "rows": 4, "nulls": 0, "distinct": 4, "verdict": "unique"}],
             "relationships": []}
    v, at = recorded.with_recorded(fresh, review, "2026-11-21T13:40Z")
    assert [k["table"] for k in v["keys"]] == ["customers", "products"]
    assert v["keys"][0]["rows"] == 5                                                 # the recorded check stands
    assert at == "2026-11-21T13:40Z"                                                 # and the time is the newest
    v2, at2 = recorded.with_recorded({"keys": fresh["keys"][:1], "relationships": []}, review, "2026-11-21T13:40Z")
    assert at2 == "2026-11-11T20:23Z" and len(v2["keys"]) == 1
