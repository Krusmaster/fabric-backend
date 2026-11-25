"""Round LFD7 (25 November 2026): versions and undo of the change list (docs/CHANGES.md, "Versions and undo (LFD7)").

The change list is versions v0 (no changes), v1, v2 ..., each with an id of its content (changes.versions). A `revert`
names an earlier change: of an unknown id or of one already reverted it is denied, and when a later change stands on the
reverted one it is a question naming that change. v0 + c1 + c2 - c2 gives every draft byte for byte as v0 + c1. The
review file carries the list as `changes` with `since_previous`; the silver notebook carries it in its parameters cell
(CHANGE_LIST), and silver.read_changes reads it back. An empty list gives today's review file and notebook byte for byte.
Scenario A6 on the synthetic shop_lfd sample: undo "remove test customers", and the drafts are the earlier version's.
No network, no model: SQLite over fabric_backend/lfd_demo.py."""
from __future__ import annotations

import itertools
import json

import pytest

from fabric_backend import change_diff, change_numbers, changes, gold, lfd_demo, notebook, pipeline, review, semantic_model, server, silver
from fabric_backend.infer import plan as make_plan

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
IS_TEST = {"column": "is_test", "op": "is_true"}
SHIP_TO = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
A2 = {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST, "cascade": ["orders", "order_items", "addresses", "audit_log"]}
A3 = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"], "via": [SHIP_TO]}
A4 = {"type": "add_measure", "name": "Order value per customer",
      "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                  "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}
ORDERS = {"type": "add_measure", "name": "Orders counted", "measure": {"form": "count", "table": "orders"}}
PER_ORDER = {"type": "add_measure", "name": "Amount per order",
             "measure": {"form": "ratio", "numerator": {"measure": "Order amount"}, "denominator": {"measure": "Orders counted"}}}
SOURCE = {"platform": "fabric", "workspace": "demo", "source": "shop_lh", "schema": "shop"}


@pytest.fixture(scope="module")
def shop():
    schema, execute = lfd_demo.sqlite("shop_lfd")
    p = server._hosted_plan(schema, None, None, execute)            # the plan as plan_backend makes it (names, R5)
    data = {t.name: execute(f"SELECT * FROM [shop].[{t.name}]") for t in p.schema}
    return p, data, execute


def drafts(p, applied=None) -> dict:
    """Every draft as text: the silver spec and notebook, the check notebook, the gold spec and notebook (facts and
    dimensions), the pipeline, the TMDL parts on the source and on gold, and change_diff's own drafts."""
    kw = {"changes": applied} if applied is not None else {}
    s = silver.spec(p, INFO, **kw)
    g = gold.spec(p, INFO, **kw)
    dims = gold.spec(p, INFO, dimensions=True, **kw)
    check = pipeline.check_spec(p, s, g, pipeline.plan_mark_of(p))
    return {"silver_spec": repr(s), "silver_notebook": silver.notebook_source(s), "gold_spec": repr(g),
            "gold_notebook": gold.notebook_source(g), "gold_dimensions": gold.notebook_source(dims),
            "check_notebook": pipeline.check_source(check, "shop_lh.shop", INFO["workspace_id"], INFO["item_id"], INFO["item_name"]),
            "tmdl": semantic_model.draft(p, INFO, **kw)["parts"],
            "tmdl_on_gold": semantic_model.draft_on_gold(p, INFO, dims, **kw)["parts"],
            "items": change_diff.drafts(p, INFO, applied)["text"]}


def ids_of(p, changes_list) -> list[str]:
    return [x["id"] for x in changes.apply(changes_list, p)["changes"]]


def revert(cid: str) -> dict:
    return {"type": "revert", "change": cid}


# ------------------------------------------------------------------ versions ------------------------------------------

def test_versions_are_the_list_up_to_each_change_with_an_id_of_the_content(shop):
    p, _, _ = shop
    listed = [A2, A3, A4]
    vs = changes.versions(listed)
    assert [v["version"] for v in vs] == ["v0", "v1", "v2", "v3"]
    assert vs[0] == {"version": "v0", "id": changes.version_id([]), "change": None, "type": None}
    assert [v["change"] for v in vs[1:]] == [changes.change_id(c) for c in listed]
    assert [v["type"] for v in vs[1:]] == ["filter_rows", "add_column", "add_measure"]
    assert all(v["id"] == changes.version_id(listed[:i]) for i, v in enumerate(vs))
    assert len({v["id"] for v in vs}) == 4 and all(v["id"].startswith("ver-") and len(v["id"]) == 20 for v in vs)
    # the same content, spelled another way, is the same version; another order is another version
    spelled = [{**A2, "cascade": list(reversed(A2["cascade"]))}, A3, A4]
    assert changes.versions(spelled) == vs
    assert changes.version_id([A3, A2]) != changes.version_id([A2, A3])
    # ok answers of validate are read as their change
    ok = changes.validate(A2, p)
    assert changes.versions([ok])[1]["change"] == ok["id"]
    assert changes.version(listed, "v2") == [A2, A3] and changes.version(listed, "v0") == []
    for bad in ("v4", "2", "v01", None):
        with pytest.raises(changes.ChangeError):
            changes.version(listed, bad)


def test_a_revert_is_a_version_of_its_own_and_since_says_what_it_took_out(shop):
    p, _, _ = shop
    a2, a3 = ids_of(p, [A2, A3])
    listed = [A2, A3, revert(a3)]
    vs = changes.versions(listed)
    assert vs[3]["type"] == "revert" and vs[3]["reverts"] == a3 and vs[3]["id"] != vs[1]["id"]
    s = changes.since(listed[:2], listed)
    assert s["later"] and s["previous"] == "v2" and s["current"] == "v3" and s["reverted"] == [a3] and not s["dropped"]
    assert s["added"] == [{"id": changes.change_id(revert(a3)), "type": "revert", "reverts": a3}]
    back = changes.since(listed, listed[:1])                         # going back to v1: the list went apart
    assert not back["later"] and back["added"] == [] and back["dropped"] == [changes.change_id(A3), changes.change_id(revert(a3))]
    assert changes.since([], []) == {"previous": "v0", "previous_id": changes.version_id([]), "current": "v0",
                                     "current_id": changes.version_id([]), "later": True, "added": [], "reverted": [], "dropped": []}
    assert changes.since([A2], [A3])["dropped"] == [changes.change_id(A2)] and a2 != a3


# ------------------------------------------------------------------ v0 + c1 + c2 - c2 == v0 + c1 ----------------------

@pytest.mark.parametrize("c1,c2", list(itertools.permutations([A2, A3, A4], 2)), ids=lambda c: c["type"])
def test_v0_c1_c2_minus_c2_gives_every_draft_of_v0_c1_byte_for_byte(shop, c1, c2):
    p, _, _ = shop
    ids = ids_of(p, [c1, c2])
    undone = changes.apply([c1, c2, revert(ids[1])], p)
    assert undone["result"] == "ok" and [x["id"] for x in undone["changes"]] == ids[:1] and undone["reverted"] == [ids[1]]
    assert drafts(p, undone) == drafts(p, changes.apply([c1], p))


def test_v0_c1_minus_c1_is_v0_and_the_three_changes_minus_one_is_the_other_two(shop):
    p, _, _ = shop
    a2, a3, a4 = ids_of(p, [A2, A3, A4])
    v0 = drafts(p)
    assert drafts(p, changes.apply([A2, revert(a2)], p)) == v0 == drafts(p, changes.apply([], p))
    assert drafts(p, changes.apply([A2, A3, A4, revert(a3)], p)) == drafts(p, changes.apply([A2, A4], p))
    assert drafts(p, changes.apply([A2, A3, A4, revert(a4), revert(a3), revert(a2)], p)) == v0
    # a change sent again after its revert is applied again
    again = changes.apply([A2, revert(a2), A2], p)
    assert [x["id"] for x in again["changes"]] == [a2] and drafts(p, again) == drafts(p, changes.apply([A2], p))


# ------------------------------------------------------------------ denials and questions -----------------------------

def test_a_revert_of_an_unknown_id_is_denied_with_a_plain_reason(shop):
    p, _, _ = shop
    got = changes.apply([A2, revert("chg-" + "0" * 16)], p)
    assert got["result"] == "denied" and got["kind"] == "unknown_change" and got["at"] == 1
    assert "chg-0000000000000000 is not among the changes applied" in got["reason"]
    assert changes.validate(revert("chg-" + "0" * 16), p, applied=[])["kind"] == "unknown_change"


def test_a_second_revert_of_the_same_change_is_denied_as_already_reverted(shop):
    p, _, _ = shop
    a2, a3 = ids_of(p, [A2, A3])
    got = changes.apply([A2, A3, revert(a2), revert(a2)], p)
    assert got["result"] == "denied" and got["kind"] == "already_reverted" and got["at"] == 3
    assert got["reason"].startswith(f"{a2} was already taken out by an earlier revert")
    one = changes.validate(revert(a2), p, applied=[a3], reverted=[a2])
    assert one["result"] == "denied" and one["kind"] == "already_reverted"


def test_a_revert_that_a_later_measure_stands_on_is_a_question_naming_it(shop):
    p, _, _ = shop
    orders, per_order = ids_of(p, [ORDERS, PER_ORDER])
    q = changes.apply([ORDERS, PER_ORDER, revert(orders)], p)
    assert q["result"] == "question" and q["kind"] == "revert_dependent" and q["at"] == 2 and q["answer_with"] == "revert"
    assert q["candidates"] == [{"change": per_order, "type": "add_measure", "why": "its ratio reads the measure Orders counted",
                                "revert": revert(per_order)}]
    assert per_order in q["question"] and "nothing is taken out for you" in q["question"]
    # the dependent first, then the one it stood on: both are taken out
    ok = changes.apply([ORDERS, PER_ORDER, revert(per_order), revert(orders)], p)
    assert ok["result"] == "ok" and ok["changes"] == [] and ok["reverted"] == [per_order, orders]


def test_a_revert_of_a_link_a_later_column_joins_over_is_a_question_naming_the_column():
    schema = lfd_demo.sqlite("shop_lfd")[0]
    p0 = make_plan(schema)                                            # names only: no ship_to link
    link = {"type": "add_link", **SHIP_TO}
    first = changes.apply([link], p0)
    assert first["result"] == "replan"
    p1 = make_plan(schema, confirmed=first["confirmed"])
    column = {**A3, "via": [SHIP_TO]}
    listed = [x["change"] for x in changes.apply([link, column], p1)["changes"]]      # as the client keeps them: the ok answers
    link_id, column_id = (changes.change_id(c) for c in listed)
    q = changes.apply([*listed, revert(link_id)], p1)
    assert q["result"] == "question" and q["kind"] == "revert_dependent" and q["at"] == 2
    assert [c["change"] for c in q["candidates"]] == [column_id] and q["candidates"][0]["why"] == "its join path follows the link"
    # reverting the column, then the link: on the plan without the link the list asks for no new plan
    undone = changes.apply([*listed, revert(column_id), revert(link_id)], p0)
    assert undone["result"] == "ok" and undone["changes"] == [] and undone["confirmed"] == []
    assert drafts(p0, undone) == drafts(p0)


def test_a_filter_and_a_copied_column_stand_on_nothing_a_later_change_needs(shop):
    p, _, _ = shop
    a2, a3, _ = ids_of(p, [A2, A3, A4])
    for target in (a2, a3):
        assert changes.apply([A2, A3, A4, revert(target)], p)["result"] == "ok"


# ------------------------------------------------------------------ an empty list changes nothing ---------------------

def test_an_empty_list_gives_todays_review_file_and_notebook_byte_for_byte(shop):
    p, _, _ = shop
    base = make_plan(p.schema)
    today = review.build(p, base, SOURCE)
    for empty in ([], None):
        got = review.build(p, base, SOURCE, changes=empty)
        assert json.dumps(got, indent=1, ensure_ascii=False) == json.dumps(today, indent=1, ensure_ascii=False)
        assert review.markdown(got) == review.markdown(today)
    assert "changes" not in today
    plain = silver.notebook_source(silver.spec(p, INFO))
    assert silver.notebook_source(silver.spec(p, INFO, changes=changes.apply([], p))) == plain
    assert "CHANGE_LIST" not in plain and silver.read_changes(plain) == []
    a2 = ids_of(p, [A2])[0]                                           # a list whose every change is reverted is v0 too
    assert silver.notebook_source(silver.spec(p, INFO, changes=changes.apply([A2, revert(a2)], p))) == plain


def test_the_review_file_carries_the_list_and_what_changed_since_the_previous_version(shop):
    p, _, _ = shop
    base = make_plan(p.schema)
    a2 = ids_of(p, [A2])[0]
    listed = [A2, A3, A4, revert(a2)]
    got = review.build(p, base, SOURCE, changes=listed)
    ch = got["changes"]
    assert ch["version"] == "v4" and ch["id"] == changes.version_id(listed)
    assert [(x["version"], x["id"], x["type"]) for x in ch["list"]] == [
        ("v1", changes.change_id(A2), "filter_rows"), ("v2", changes.change_id(A3), "add_column"),
        ("v3", changes.change_id(A4), "add_measure"), ("v4", changes.change_id(revert(a2)), "revert")]
    assert ch["list"][3]["change"] == changes.canonical(revert(a2))
    sp = ch["since_previous"]
    assert sp["previous"] == "v3" and sp["reverted"] == [a2] and [x["type"] for x in sp["added"]] == ["revert"]
    assert review.read(json.dumps(got)) == json.loads(json.dumps(got))
    text = review.markdown(got)
    assert "## Changes (v4, `" in text and f"v4. `{changes.change_id(revert(a2))}` revert of `{a2}`" in text
    assert "Since v3: 1 added; 1 reverted." in text
    # with a previous file: since that file's list
    earlier = review.build(p, base, SOURCE, changes=[A2])
    later = review.build(p, base, SOURCE, changes=listed, previous=review.read(json.dumps(earlier)))
    assert later["changes"]["since_previous"]["previous"] == "v1" and len(later["changes"]["since_previous"]["added"]) == 3
    first = review.build(p, base, SOURCE, changes=[A2], previous=review.read(json.dumps(review.build(p, base, SOURCE))))
    assert first["changes"]["since_previous"]["previous"] == "v0"
    with pytest.raises(review.ReviewFileError):
        review.read({**got, "changes": {"version": "v1"}})


# ------------------------------------------------------------------ the list in the silver notebook --------------------

def test_the_silver_notebook_carries_the_applied_list_and_it_is_read_back(shop):
    p, _, _ = shop
    a2 = ids_of(p, [A2])[0]
    applied = changes.apply([A2, A3, A4], p)
    text = silver.notebook_source(silver.spec(p, INFO, changes=applied))
    params = next(body for kind, body in notebook.parse(text) if kind == "parameters")
    assert sum(1 for x in params.splitlines() if x.startswith("CHANGE_LIST = ")) == 1
    back = silver.read_changes(text)
    assert back == [{"id": x["id"], "change": x["change"]} for x in applied["changes"]]
    # from the item definition, as Get Notebook Definition gives it
    env = notebook.envelope("silver_shop", text)
    assert silver.read_changes(env) == back == silver.read_changes({"parts": env["definition"]["parts"]})
    # the basis for what is built: the list read back gives the same list and the same notebook again
    again = changes.apply([x["change"] for x in back], p)
    assert [x["id"] for x in again["changes"]] == [x["id"] for x in applied["changes"]]
    assert silver.notebook_source(silver.spec(p, INFO, changes=again)) == text
    # what is read back is the applied list, without the reverted change and the revert
    undone = silver.notebook_source(silver.spec(p, INFO, changes=changes.apply([A2, A3, A4, revert(a2)], p)))
    assert [x["id"] for x in silver.read_changes(undone)] == ids_of(p, [A3, A4])
    # the notebook's code still compiles; the list is a string the run does not use
    for kind, body in notebook.parse(text):
        if kind != "markdown":
            compile(body, "<cell>", "exec")


def test_a_list_edited_by_hand_is_not_read_as_one_krusgraph_wrote(shop):
    p, _, _ = shop
    text = silver.notebook_source(silver.spec(p, INFO, changes=changes.apply([A2], p)))
    line = next(x for x in text.splitlines() if x.startswith("CHANGE_LIST = "))
    tampered = text.replace(line, line.replace("is_test", "is_demo"))
    with pytest.raises(changes.ChangeError) as e:
        silver.read_changes(tampered)
    assert e.value.kind == "bad_request" and "edited" in e.value.reason
    with pytest.raises(changes.ChangeError):
        silver.read_changes(text.replace(line, "CHANGE_LIST = 'not json'"))
    with pytest.raises(changes.ChangeError):
        silver.read_changes({"parts": []})


# ------------------------------------------------------------------ propose_change with a revert -----------------------

def test_propose_a_revert_shows_the_removal_in_the_plan_items_and_numbers_layers(shop):
    p, _, execute = shop
    a2 = ids_of(p, [A2])[0]

    def counter(*, before, after):
        return change_numbers.count(after["applied"], after["plan"], execute, dialect="sqlite", no_row_values=False)
    ok = change_diff.propose(revert(a2), p, INFO, [A2, A3, A4], numbers=counter)
    assert ok["result"] == "ok" and ok["reverts"] == {"id": a2, "type": "filter_rows"}
    assert ok["changes"] == ids_of(p, [A3, A4])
    plan = ok["diff"]["plan"]
    assert [f["id"] for f in plan["filters_removed"]] == [a2] and plan["reverted"] == {"id": a2, "type": "filter_rows"}
    assert plan["summary"] == "1 filter removed"
    items = {x["item"]: x for x in ok["diff"]["items"]}
    assert items["silver_notebook"]["status"] == change_diff.UPDATE
    assert items["silver_notebook"]["summary"] == "the filter step on customers taken out"
    assert items["pipeline"]["status"] == change_diff.UNCHANGED
    numbers = ok["diff"]["numbers"]
    assert numbers["status"] == "counted" and numbers["reverts"]["id"] == a2 and "reverted change" in numbers["read"]
    counted = next(x for x in numbers["counted"]["changes"] if x["id"] == a2)
    rows = {n["item"]: n for n in counted["numbers"]}
    assert (rows["rows:customers"]["before"], rows["rows:customers"]["after"]) == (12, 10)   # the revert takes 10 back to 12
    # without a counter the layer says so, as for any change
    assert change_diff.propose(revert(a2), p, INFO, [A2, A3, A4])["diff"]["numbers"]["status"] == change_diff.NOT_COUNTED


def test_propose_a_revert_passes_the_question_and_the_denial_through(shop):
    p, _, _ = shop
    orders, per_order = ids_of(p, [ORDERS, PER_ORDER])
    q = change_diff.propose(revert(orders), p, INFO, [ORDERS, PER_ORDER])
    assert q["result"] == "question" and q["kind"] == "revert_dependent" and q["at"] == 2 and "diff" not in q
    assert [c["change"] for c in q["candidates"]] == [per_order]
    d = change_diff.propose(revert(orders), p, INFO, [ORDERS, revert(orders)])
    assert d["result"] == "denied" and d["kind"] == "already_reverted"


def test_propose_a_revert_of_a_link_plans_again_without_it():
    schema = lfd_demo.sqlite("shop_lfd")[0]
    link = {"type": "add_link", **SHIP_TO}
    entry = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    p1 = make_plan(schema, confirmed=[entry])
    kept = changes.apply([link], p1)["changes"][0]                    # as the client keeps it: the ok answer
    link_id = kept["id"]
    planned = []

    def replan(confirmed):
        planned.append(confirmed)
        return make_plan(schema, None, confirmed or None)
    ok = change_diff.propose(revert(link_id), p1, INFO, [kept["change"]], confirmed=[entry], replan=replan)
    assert ok["result"] == "ok" and planned == [[]] and ok["confirmed"] == [] and ok["changes"] == []
    plan = ok["diff"]["plan"]
    assert [(r["source"], r["target"], r["rule"]) for r in plan["links_removed"]] == [("orders", "addresses", "confirmed")]
    assert plan["reverted"] == {"id": link_id, "type": "add_link"}


# ------------------------------------------------------------------ scenario A6 on shop_lfd ----------------------------

def test_a6_undo_remove_test_customers_and_the_drafts_return_to_the_earlier_version(shop):
    """A6: after A2 (remove the test customers), A3 (region) and A4 (order value per customer), the person writes "undo
    remove test customers". The revert names A2; the drafts are those of the list without it, the silver rows are the
    source's again (12 customers, 66 orders, 146 lines), and the review file says v4 took A2 out."""
    p, data, _ = shop
    a2, a3, a4 = ids_of(p, [A2, A3, A4])
    with_filter = changes.apply([A2, A3, A4], p)
    undone = changes.apply([A2, A3, A4, revert(a2)], p)
    assert undone["result"] == "ok" and [x["id"] for x in undone["changes"]] == [a3, a4] and undone["reverted"] == [a2]
    assert drafts(p, undone) == drafts(p, changes.apply([A3, A4], p))
    assert drafts(p, undone) != drafts(p, with_filter)
    # the silver steps are v0's again: only the list in the parameters cell says which changes stand
    s = silver.spec(p, INFO, changes=undone)
    assert "change_filters" not in repr(s) and [x["id"] for x in silver.read_changes(silver.notebook_source(s))] == [a3, a4]
    rows = silver.simulate(s, data)
    filtered = silver.simulate(silver.spec(p, INFO, changes=with_filter), data)
    count = {t: len(rows["silver"][t]) for t in ("customers", "orders", "order_items")}
    assert count == {"customers": 12, "orders": 66, "order_items": 146}
    assert {t: len(filtered["silver"][t]) for t in count} == {"customers": 10, "orders": 60, "order_items": 134}
    assert rows == silver.simulate(silver.spec(p, INFO), data)
    # the versions and the review file
    listed = [A2, A3, A4, revert(a2)]
    assert [v["version"] for v in changes.versions(listed)][-1] == "v4"
    ch = review.build(p, make_plan(p.schema), SOURCE, changes=listed)["changes"]
    assert ch["since_previous"]["reverted"] == [a2] and ch["version"] == "v4"
