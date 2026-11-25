"""Round AP2b: the fixes from the founder's live test of /app on his phone (25 November 2026), on invented names
(tests/ap2b_support.py: `demo` with demo_lh and the schema shop; `build_ws`, a build target whose lakehouse build_lh holds
dbo and Krusgraph's own output gold, krusgraph and silver).

1. One greeting: the first answer is the start tool's own "Hi! ..."; the coach's line is said only when it is not.
2. Krusgraph's own output schemas: labelled with the Model editor's words, after the source schemas, never suggested;
   no combined chip that mixes them with sources; system schemas left out.
3. The check counts every table the map has (the start tool's "tables" counts the tables with a key), and one line names
   the tables without a key; a plan over several schemas speaks of those schemas by name, not of "the two sources".
4. A typed name that is not here but was listed earlier in the session: where it is, and a chip to go there; no new
   Fabric read.
5. The header and the closing line say when /app writes and what this session wrote.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import ap1_support as s  # noqa: E402
import ap2b_support as b  # noqa: E402
from fabric_backend import guided_app, guided_build, start_flow  # noqa: E402

SCHEMA_STEP = {"workspace": "build_ws", "source": "build_lh", "step": "schema"}


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


@pytest.fixture
def journey(monkeypatch, keys):
    app, a, fake = s.entra_app(monkeypatch, keys)
    seen = s.data(monkeypatch)
    b.install(monkeypatch)
    token = s.tok(keys[0])
    c = TestClient(app, base_url=s.ORIGIN, follow_redirects=False)
    with c:
        assert s.sign_in(c, fake, token).status_code == 302
        yield c, seen


# ------------------------------------------------------------------ 1. one greeting -----------------------------------

def test_the_first_answer_is_the_one_greeting(journey):
    c, _ = journey
    first = s.step(c, {}).json()
    assert first["stage"] == "workspace" and first["say"].startswith("Hi! ")
    js = (guided_app.__file__.rsplit("/", 1)[0] + "/static/app.js")
    text = open(js, encoding="utf-8").read()
    begin = text[text.index("function begin()"):].split("\n", 1)[0]
    assert "LINES.hello" not in begin                          # the page no longer greets before the first answer
    assert "if (!/^Hi\\b/.test(v.say || '')) say('onto', [LINES.hello]);" in text     # only when start does not


# ------------------------------------------------------------------ 2. Krusgraph's own schemas -------------------------

def test_own_schemas_are_labelled_last_and_not_suggested(journey):
    c, _ = journey
    v = s.step(c, SCHEMA_STEP).json()
    assert v["stage"] == "schema"
    labels = [(x["label"], x["hint"]) for x in v["choices"]]
    assert labels == [("dbo", "17 tables, suggested"),
                      ("gold", "7 tables, looks like Krusgraph output"),
                      ("krusgraph", "3 tables, written by Krusgraph"),
                      ("silver", "17 tables, looks like Krusgraph output")]
    assert [x["label"] for x in v["choices"] if x.get("selected")] == ["dbo"]
    assert not any("+" in x["label"] for x in v["choices"])     # no "dbo+gold+krusgraph+silver · one plan"
    assert "gold, krusgraph, silver" in v["own_line"]


def test_the_start_tool_offered_the_mixed_chip_and_the_view_drops_it():
    out = start_flow.guide(workspace="build_ws", source="build_lh", step="schema", options={"step": "schema", "items": [
        {"name": "dbo", "tables": 17}, {"name": "gold", "tables": 7}, {"name": "krusgraph", "tables": 3},
        {"name": "silver", "tables": 17}, {"name": "dbo+gold+krusgraph+silver", "tables": 44}]})
    assert any(a.get("label") == "dbo+gold+krusgraph+silver" for a in out["actions"])     # what the live test saw
    v = guided_app.view(out)
    assert [x["label"] for x in v["choices"]] == ["dbo", "gold", "krusgraph", "silver"]


def test_sources_together_stay_a_choice_and_system_schemas_go():
    out = start_flow.guide(workspace="w", source="lh", step="schema", options={"step": "schema", "items": [
        {"name": "_rsc", "tables": 1}, {"name": "sap", "tables": 18}, {"name": "crm", "tables": 6},
        {"name": "silver", "tables": 24}]})
    v = guided_app.view(out)
    assert [x["label"] for x in v["choices"]] == ["sap", "crm", "sap+crm", "silver"]
    combo = v["choices"][2]
    assert combo["hint"] == "24 tables, one plan"
    assert combo["arguments"] == {"workspace": "w", "source": "lh", "schema": "sap+crm", "step": "check"}
    assert not any(x.get("selected") for x in v["choices"])        # two sources: the person picks
    # a source with only source schemas keeps the start tool's own list, chip and all
    plain = start_flow.guide(workspace="w", source="lh", step="schema", options={"step": "schema", "items": [
        {"name": "sap", "tables": 18}, {"name": "crm", "tables": 6}, {"name": "sap+crm", "tables": 24}]})
    assert [x["label"] for x in guided_app.view(plain)["choices"]] == ["sap", "crm", "sap+crm"]


def test_an_own_schema_the_start_tool_picked_is_not_picked_here():
    out = start_flow.guide(workspace="w", source="lh", step="schema", options={"step": "schema", "items": [
        {"name": "dbo", "tables": 0}, {"name": "gold", "tables": 7}]})
    assert out["after"]["arguments"]["schema"] == "gold"                       # the start tool's one usable option
    v = guided_app.view(out)
    assert not any(x.get("selected") for x in v["choices"]) and not v.get("buttons")
    assert v["say"] == "Which schema in lh shall I read?"


# ------------------------------------------------------------------ 3. the same count everywhere -----------------------

def test_tiles_sentence_and_map_count_the_same_tables(journey):
    c, _ = journey
    v = s.step(c, {"workspace": "demo", "source": "demo_lh", "schema": "shop", "step": "check"}).json()
    assert v["stage"] == "check"
    total = len(v["map"]["tables"])
    assert total == 18 and v["counts"]["tables"] == 18 and v["counts"]["keyed"] == 17
    assert v["say"].startswith("18 tables, ")
    assert v["lines"][0] == ("17 of the 18 tables have a key the rules could prove; 1 has none (sap_notes), so no "
                             "link can point at it and no key of its is counted.")
    assert [t["name"] for t in v["map"]["tables"] if not t["key"]] == ["sap_notes"]


def test_a_check_where_every_table_has_a_key_is_as_before():
    out = {"stage": "check", "say": "2 tables, 1 links, nothing needs you.", "counts": {"tables": 2, "links": 1},
           "lines": ["1 of 1 checks hold."],
           "map": {"tables": [{"name": "a", "key": ["id"]}, {"name": "b", "key": ["id"]}], "relationships": []}}
    v = guided_app.view(out)
    assert v["counts"] == {"tables": 2, "links": 1} and v["lines"] == ["1 of 1 checks hold."]


def test_several_schemas_are_named_not_called_two_sources():
    c = {"workspace": "w", "source": "lh", "schema": "dbo+gold+krusgraph+silver"}
    out = start_flow.guide(**c, step="check", combine={"error": "the rows could not be read"},
                           review={"items": [], "snapshot": {"tables": {}}})
    assert out["lines"][0] == ("The customers of the 4 schemas (dbo, gold, krusgraph and silver) could not be counted, "
                               "so nothing is combined.")
    out = start_flow.guide(**{**c, "schema": "sap+crm"}, step="check", combine={"sources": ["crm", "sap"]},
                           review={"items": [], "snapshot": {"tables": {}}})
    assert out["lines"][0] == "No rule pairs the customers of crm and sap, so each is built apart."
    assert "two sources" not in json.dumps(out)


# ------------------------------------------------------------------ 4. a name from elsewhere --------------------------

def test_a_typed_name_listed_elsewhere_says_where_and_offers_to_go(journey):
    c, seen = journey
    s.step(c, {})                                                      # the workspaces
    s.step(c, {"workspace": "demo"})                                   # demo › demo_lh › shop, picked for you
    s.step(c, {"workspace": "build_ws"})
    s.step(c, SCHEMA_STEP)
    reads = len(seen["fabric"])
    v = s.step(c, {**SCHEMA_STEP, "text": "Shop"}).json()
    assert v["stage"] == "schema"
    assert v["match"]["say"] == "No name here matches “Shop”, but “shop” is a schema in demo › demo_lh."
    go = v["match"]["go"]
    assert go == [{"label": "Go to demo › demo_lh › shop", "primary": True,
                   "arguments": {"workspace": "demo", "source": "demo_lh", "schema": "shop", "step": "check"}}]
    assert len(seen["fabric"]) - reads <= 1               # only the step's own listing; nothing read for the search
    assert s.step(c, go[0]["arguments"]).json()["stage"] == "check"


def test_a_name_never_listed_in_this_session_is_not_found(journey):
    c, _ = journey
    s.step(c, SCHEMA_STEP)
    v = s.step(c, {**SCHEMA_STEP, "text": "Shop"}).json()            # demo was never opened: shop is not known
    assert v["match"]["say"] == "No name here matches “Shop”. Tap one of the names, or type part of it."
    assert "go" not in v["match"]


def test_elsewhere_follows_match_choices_rules_in_order():
    sid = "sid-test"
    guided_app.SEEN.drop(sid)
    guided_app.remember(sid, {"stage": "workspace", "chosen": {}, "actions": [
        {"kind": "choose", "label": "demo"}, {"kind": "choose", "label": "shop_ws"}]})
    guided_app.remember(sid, {"stage": "data", "chosen": {"workspace": "demo", "source": "demo_lh", "schema": "shop"}})
    hits = guided_app.elsewhere(sid, "SHOP", ("build_ws", "build_lh"))
    assert [(h["kind"], h["name"], h["where"]) for h in hits] == [("schema", "shop", "demo › demo_lh")]   # same name first
    hits = guided_app.elsewhere(sid, "sho", ("build_ws", "build_lh"))
    assert {h["name"] for h in hits} == {"shop_ws", "shop"}                                              # then by start
    here = guided_app.elsewhere(sid, "shop", ("demo", "demo_lh"))            # its own place is not "elsewhere"
    assert [(h["kind"], h["name"]) for h in here] == [("workspace", "shop_ws")]
    assert guided_app.elsewhere("", "shop", None) == []
    guided_app.SEEN.drop(sid)


# ------------------------------------------------------------------ 5. what the page says about writing ---------------

def test_the_header_and_the_closing_line_are_true(journey, monkeypatch):
    c, _ = journey
    page = c.get(guided_app.PATH).text
    assert "Nothing is written to Fabric until you confirm a Create." in page
    assert "only reads here" not in page and "this page only reads" not in page
    check = {"workspace": "demo", "source": "demo_lh", "schema": "shop", "step": "check"}
    v = s.step(c, check).json()
    assert v["closing"] == guided_app.NOTHING_WRITTEN and "Nothing has been written" in v["closing"]
    sid = guided_app._digest(c.cookies.get(guided_app.SESSION_COOKIE))
    guided_build._state(sid)["created"].append({"id": "x1", "name": "shop_model", "type": "SemanticModel"})
    v = s.step(c, check).json()
    assert v["closing"] == ("In this session Create wrote 1 item to Fabric, after your confirm: shop_model. The check, "
                            "Decide and the dry run only read.")
    guided_build.BUILDS.drop(sid)
