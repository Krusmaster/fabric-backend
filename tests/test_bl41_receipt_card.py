"""BL41: the query behind every counted number on the chat's check card (receipt.build's statement, behind "Show the
SQL" with a "Select" button), one line beside the queries, no row value, and the card's rules kept: no clipboard and no
file save (tests/test_n119_mcp_apps.py), so the receipt notebook stays out of the card."""
from fabric_backend import mcp_apps, mcp_apps_next as nxt, receipt_card
from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)
from test_n218_cards_act import _row_values, _sc


def test_every_counted_row_has_its_own_query_and_no_row_value(fabric):
    _, d = _sc("validate_plan", **SRC)
    c = d["checks"]
    counted = [x for x in c["rows"] if x["state"] != "not_checked"]
    assert counted and all(x["sql"].lstrip().upper().startswith(("SELECT", "WITH")) for x in counted)
    assert c["sql_for_all"] is True and c["sql_beside"] == receipt_card.BESIDE
    assert len(set(x["sql"] for x in counted if x["kind"] == "key")) == sum(x["kind"] == "key" for x in counted)
    shown = str(c)
    assert not [v for v in _row_values() if v in shown]


def test_a_row_the_budget_did_not_reach_has_no_query(fabric):
    _, d = _sc("validate_plan", **SRC, max_items=3)
    assert not [x for x in d["checks"]["rows"] if x["state"] == "not_checked" and "sql" in x]


def test_the_card_ids_are_receipts_items():
    assert receipt_card._card_id("amount:orders<order_items") == "amount:orders>order_items"
    assert receipt_card._card_id("key:orders") == "key:orders"
    assert receipt_card._card_id("rel:order_items.order_id>orders") == "rel:order_items.order_id>orders"


def test_the_line_beside_is_short_and_the_card_keeps_its_rules():
    assert len(receipt_card.BESIDE.split()) <= 25
    js = nxt.js()
    assert '"Select"' in js and "getSelection" in js and "ck-beside" in js
    low = mcp_apps.card_html().lower()
    assert "navigator." not in low and "url(" not in low and "download" not in low
