"""RQ1 (19 November 2026): requirements_draft, a pasted requirements list matched to the checked SAP data by rules.

Everything runs on synthetic data: fabric_backend/sap_demo.py's SAP-shaped tables in SQLite (17 tables, one planted
orphan, header amounts that repeat on every line, two clients). The rules are deterministic (no AI): the same list and
the same plan give the same answer, byte for byte; the golden is tests/golden/rq1_sap_demo.json. Regenerate it
deliberately with KRUSGRAPH_UPDATE_GOLDEN=1.

One section per state (answerable, trap, missing, unclear), then the golden, the queries run on SQLite, the leak test
(no row value in any answer), the tool on the sample, the next steps, create_data_agent's requirements= and the card in
a browser at 390 px, light and dark.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from fabric_backend import evidence, mcp_apps, mcp_apps_build, requirements_draft as rq, sap_demo, server
from fabric_backend.infer import plan

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"
DEMO_LIST = """Requirements from the sales meeting (summarised by Copilot):
- Revenue per customer and month
- Order value per material and month
- Late deliveries per customer
- Unpaid invoices per customer
- Show our best customers
"""


def _golden(name: str, value) -> None:
    path = GOLDEN / f"rq1_{name}.json"
    text = json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    if UPDATE:
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"no golden file {path.name}: run with KRUSGRAPH_UPDATE_GOLDEN=1 once"
    assert text == path.read_text(encoding="utf-8"), f"{path.name} changed; regenerate deliberately if that is right"


def _demo(tables=None):
    if tables is not None:
        real = sap_demo.tables
        sap_demo.tables = lambda: tables
        try:
            s, execute = sap_demo.sqlite()
        finally:
            sap_demo.tables = real
    else:
        s, execute = sap_demo.sqlite()
    p = plan(s)
    return p, execute, evidence.validate(p, execute, max_items=200)


@pytest.fixture(scope="module")
def demo():
    return _demo()


@pytest.fixture(scope="module")
def answer(demo):
    p, _, v = demo
    return rq.draft(p, DEMO_LIST, v, "sap")


def _one(demo, text: str) -> dict:
    p, _, v = demo
    [r] = rq.draft(p, text, v, "sap")["requirements"]
    return r


# ------------------------------------------------------------------ the input -----------------------------------------

def test_the_list_is_read_line_by_line_without_bullets_headings_or_blank_lines():
    got = rq.parse("Krav från mötet:\n\n# Rubrik\n- Revenue per customer\n2. Order value per material\n* [x] Late "
                   "deliveries\n• Krav 7: Unpaid invoices\n---\n")
    assert got == [{"id": "R1", "text": "Revenue per customer"}, {"id": "R2", "text": "Order value per material"},
                   {"id": "R3", "text": "Late deliveries"}, {"id": "R4", "text": "Unpaid invoices"}]
    assert rq.parse(["a requirement", "", None, "another one"]) == [{"id": "R1", "text": "a requirement"},
                                                                     {"id": "R2", "text": "another one"}]
    assert len(rq.parse("\n".join(f"- Revenue per customer {i}" for i in range(40)))) == rq.MAX_REQUIREMENTS
    assert len(rq.parse("x" * 1000)[0]["text"]) == rq.MAX_LINE_CHARS


def test_an_empty_list_asks_for_one(demo):
    p, _, v = demo
    out = rq.draft(p, "\n\n", v, "sap")
    assert out["requirements"] == [] and out["ask"].startswith("Paste the requirements")


def test_swedish_words_mean_the_same():
    assert rq.understand("Intäkter per kund och månad") == rq.understand("Revenue per customer and month")
    assert rq.understand("Försenade leveranser per kund")["measure"] == "late_delivery"
    assert rq.understand("Obetalda fakturor per kund")["measure"] == "open_items"
    assert rq.understand("Ordervärde per artikel")["dims"] == ["material"]


# ------------------------------------------------------------------ answerable now -------------------------------------

def test_revenue_per_customer_and_month_is_answerable_on_the_billing_header(demo):
    r = _one(demo, "Revenue per customer and month")
    assert r["state"] == "answerable" and r["rule"] == "RQ-M1" and r["checked"] is True
    assert r["key"] == {"table": "sap_vbrk", "key": ["MANDT", "VBELN"], "state": "checked", "verdict": "unique in all 1 rows"}
    assert r["columns"][0].startswith("VBRK.NETWR") and "VBRK.KUNAG (sold-to party)" in r["columns"]
    assert "SUM(h.[NETWR])" in r["query"] and "JOIN" not in r["query"] and r["query"].startswith("-- R1: Revenue per")
    assert "h.[WAERK] AS currency" in r["query"] and "h.[MANDT] AS client" in r["query"]   # per currency and client
    assert any("payer" in n for n in r["notes"])                                         # sold-to by default, said
    assert r["traps"] == []


def test_the_payer_is_used_when_the_requirement_says_payer(demo):
    r = _one(demo, "Revenue per payer")
    assert r["state"] == "answerable" and "h.[KUNRG] AS customer" in r["query"]


def test_revenue_per_country_joins_the_customer_master_over_a_checked_join(demo):
    r = _one(demo, "Revenue per country and year")
    assert r["state"] == "answerable"
    assert [(j["join"], j["state"]) for j in r["joins"]] == [("sap_vbrk → sap_kna1", "checked")]
    assert "k.[LAND1] AS country" in r["query"] and ", 1, 4) AS year" in r["query"]


def test_a_personal_data_column_is_never_used(demo):
    r = _one(demo, "Revenue per customer and month")
    assert "NAME1" not in r["query"] and "TELF1" not in r["query"]


# ------------------------------------------------------------------ answerable with a trap ----------------------------

def test_order_value_per_material_has_the_header_amount_trap_and_sums_the_items(demo):
    r = _one(demo, "Order value per material and month")
    assert r["state"] == "trap" and r["rule"] == "RQ-M2"
    assert r["traps"][0].startswith("VBAK.NETWR is the whole document's value and repeats on every VBAP row")
    assert "1.67 rows per VBAK row on average and up to 3" in r["traps"][0]               # counted, not guessed
    assert "SUM(i.[NETWR])" in r["query"] and "SUM(h.[NETWR])" not in r["query"]
    # the planted orphan: one item of an order that does not exist
    assert r["joins"][0]["state"] == "failed" and r["joins"][0]["orphans"] == 1
    assert any(t.startswith("1 VBAP row(s) point at no VBAK row") for t in r["traps"])


def test_quantity_is_summed_per_unit(demo):
    r = _one(demo, "Quantity per material")
    assert r["state"] == "trap" and "i.[VRKME] AS unit" in r["query"]
    assert any("never add pieces and kilograms" in t for t in r["traps"])


def test_without_counts_nothing_is_called_checked(demo):
    p, _, _ = demo
    [r] = rq.draft(p, "Revenue per customer", None, "sap")["requirements"]
    assert r["checked"] is False and r["key"]["state"] == "not_checked"
    assert any("Not counted yet" in n for n in r["notes"])


# ------------------------------------------------------------------ missing data --------------------------------------

def test_late_deliveries_need_the_actual_goods_issue_date(demo):
    r = _one(demo, "Late deliveries per customer")
    assert r["state"] == "missing" and r["rule"] == "RQ-X2"
    assert [m["field"] for m in r["missing"]] == ["LIKP.WADAT_IST"]
    assert "LIKP.ERDAT is when the delivery was created" in r["missing"][0]["why"]


def test_late_deliveries_are_answerable_once_the_date_is_there():
    t = sap_demo.tables()
    cols, kinds, rows = t["LIKP"]
    t["LIKP"] = (cols + ["WADAT_IST"], kinds + ["string"], [row + ("20261015",) for row in rows])
    p, execute, v = _demo(t)
    [r] = rq.draft(p, "Late deliveries per customer", v, "sap")["requirements"]
    assert r["state"] == "answerable" and r["rule"] == "RQ-M5" and r["checked"] is True
    assert {j["state"] for j in r["joins"]} == {"checked"}
    assert "MIN([EDATU])" in r["query"]
    got = execute(r["query"].replace("[sap].", ""))
    # demo: item 10 asked for 10 Oct (first schedule line), item 20 for 10 Oct; both left on 15 Oct: two late items
    assert [(x["late_items"], x["deliveries_with_late_items"]) for x in got] == [(2, 1)]


def test_unpaid_invoices_need_accounting_open_items(demo):
    r = _one(demo, "Unpaid invoices per customer")
    assert r["state"] == "missing" and r["missing"][0]["field"] == "BSID"
    assert "ACDOCA" in r["missing"][0]["or"]


def test_margin_needs_a_cost(demo):
    r = _one(demo, "Margin per material")
    assert r["state"] == "missing" and r["missing"][0]["field"] == "VBAP.WAVWR"


def test_a_schema_the_sap_pack_does_not_know_says_so():
    from fabric_backend import seed
    p = plan(seed.shop_schema() if hasattr(seed, "shop_schema") else seed.schema())
    [r] = rq.draft(p, "Revenue per customer", None, "shop")["requirements"]
    assert r["state"] == "missing" and r["rule"] == "RQ-X0"


# ------------------------------------------------------------------ unclear -------------------------------------------

@pytest.mark.parametrize("text,rule,starts", [
    ("Show our best customers", "RQ-U3", "Best or top by which measure"),
    ("Sales per customer", "RQ-U2", "Sales as invoiced revenue"),
    ("Something about the regions", "RQ-U4", "Which number should this show"),
    ("Revenue and quantity per material", "RQ-U1", "This line asks for"),
    ("Revenue per ship-to", "RQ-U5", "The ship-to party is on the delivery"),
    ("Order value per payer", "RQ-U6", "The payer of a sales order is a partner row"),
    ("Revenue per customer and week", "RQ-U7", "Per week"),
])
def test_an_unclear_requirement_gets_one_question(demo, text, rule, starts):
    r = _one(demo, text)
    assert r["state"] == "unclear" and r["rule"] == rule and r["question"].startswith(starts), r


# ------------------------------------------------------------------ the golden and the queries ------------------------

def test_the_sap_demo_list_gives_one_of_each_state_and_the_golden(answer):
    assert [(x["id"], x["state"]) for x in answer["requirements"]] == [
        ("R1", "answerable"), ("R2", "trap"), ("R3", "missing"), ("R4", "missing"), ("R5", "unclear")]
    assert answer["counts"] == {"answerable": 1, "trap": 1, "missing": 2, "unclear": 1}
    assert answer["questions"] == [{"requirement": "R5", "question": answer["requirements"][4]["question"]}]
    f = answer["feeds"]
    assert f["gold_views_draft"] == {"tables": ["sap_vbak", "sap_vbap", "sap_vbrk"], "requirements": ["R1", "R2"]}
    assert [m["requirement"] for m in f["semantic_model_draft"]["measures"]] == ["R1", "R2"]
    assert f["semantic_model_draft"]["measures"][1]["rule"] == "sum the item amount"
    assert [x["requirement"] for x in f["create_data_agent"]["example_queries"]] == ["R1", "R2"]
    _golden("sap_demo", answer)


def test_the_answer_is_the_same_byte_for_byte(demo):
    p, _, v = demo
    assert json.dumps(rq.draft(p, DEMO_LIST, v, "sap")) == json.dumps(rq.draft(p, DEMO_LIST, v, "sap"))


def test_the_queries_run_and_avoid_the_doubled_total(demo, answer):
    _, execute, _ = demo
    r1, r2 = answer["requirements"][:2]
    rows1 = execute(r1["query"].replace("[sap].", ""))
    assert sum(x["net_value"] for x in rows1) == 400                       # the one invoice, once
    rows2 = execute(r2["query"].replace("[sap].", ""))
    assert sum(x["net_value"] for x in rows2) == 750                        # items with an order: 700 + 50, the orphan out
    naive = execute("SELECT SUM(h.NETWR) AS s FROM sap_vbap i JOIN sap_vbak h ON i.MANDT = h.MANDT AND i.VBELN = h.VBELN")
    assert naive[0]["s"] == 1950                                            # what the trap would have given


# ------------------------------------------------------------------ no row value leaves ---------------------------------

def _row_values() -> set[str]:
    out = set()
    for cols, kinds, rows in sap_demo.tables().values():
        for row in rows:
            for v in row:
                if isinstance(v, float):
                    out |= {f"{v:.2f}", f"{v:.1f}"}
                elif isinstance(v, str) and (len(v) >= 5 or " " in v or "@" in v):
                    out.add(v)
    return out


def test_no_row_value_leaks_into_any_answer(demo, answer):
    values = _row_values()
    assert "0000000010" in values and "Demo Customer 10" in values and "600.00" in values   # the test means it
    texts = [json.dumps(answer, ensure_ascii=False), json.dumps(rq.card(answer), ensure_ascii=False),
             server.requirements_draft(DEMO_LIST, sample=True)]
    for text in texts:
        leaked = sorted(v for v in values if re.search(r"(?<![0-9A-Za-z])" + re.escape(v) + r"(?![0-9A-Za-z])", text))
        assert leaked == [], leaked


# ------------------------------------------------------------------ the tool, the steps and the data agent ------------

def test_the_tool_runs_offline_on_the_sample():
    out = json.loads(server.requirements_draft(DEMO_LIST, sample=True))
    assert out["counts"] == {"answerable": 1, "trap": 1, "missing": 2, "unclear": 1}
    assert out["where"].startswith("the synthetic SAP demo") and "no API to read a Copilot Workspace" in out["note"]
    assert out["kg_card"]["result"] == "5 requirements: 1 answerable now, 1 with a trap, 2 missing data, 1 unclear."


def test_without_a_source_it_asks_for_one_or_the_sample():
    out = json.loads(server.requirements_draft("Revenue per customer"))
    assert out["kind"] == "bad_input" and "sample=true" in out["error"]


def test_the_next_steps_name_their_requirement_ids_and_create_nothing(answer):
    call = {"workspace": "demo", "source": "demo_lh", "schema": "sap"}
    steps = rq.next_steps(call, answer)
    assert [s["label"] for s in steps] == ["Draft the gold views for R1, R2", "Draft the semantic model for R1, R2",
                                           "Data agent with R1, R2 as examples (dry run)", "Answer the question for R5"]
    assert steps[0]["primary"] and steps[0]["tool"] == "gold_views_draft"
    assert steps[0]["arguments"]["tables"] == ["sap_vbak", "sap_vbap", "sap_vbrk"]
    assert "tool" not in steps[2] and "dry_run=True" in steps[2]["say"]    # a sentence: Claude runs the dry run
    assert all(s.get("arguments", {}).get("dry_run", True) is True for s in steps)
    assert rq.next_steps({"sample": True}, answer)[0]["label"] == "Run it on my lakehouse"


def test_the_card_words_and_steps_with_the_flag_on(monkeypatch):
    monkeypatch.setenv(mcp_apps.FLAG, "1")
    assert mcp_apps.registration("requirements_draft", on=True)["meta"] == mcp_apps_build.tool_meta(on=True)
    r = mcp_apps.structured(server.requirements_draft, "requirements_draft")(DEMO_LIST, sample=True)
    d = r.structured_content
    assert d["kg_card"]["title"] == "Requirements" and len(d["kg_card"]["lines"]) == 5
    assert d["kg_card"]["lines"][0] == "R1 Answerable now: Revenue per customer and month. key and joins counted"
    assert [s["label"] for s in d["next"]] == ["Run it on my lakehouse"]
    assert "Match the same requirements list on my lakehouse" in " ".join(c.text for c in r.content)


def test_create_data_agent_adds_the_answerable_requirements_as_example_queries(monkeypatch, demo):
    p, _, v = demo
    info = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="demo_lh", schema="sap",
                schemas_enabled=True, item_kind="Lakehouse", item_type="Lakehouse")
    monkeypatch.setattr(server, "_source_inputs", lambda *a, **k: (p, info))
    monkeypatch.setattr(server, "_connected", lambda *a, **k: sap_demo.sqlite())
    monkeypatch.setattr(server._evidence, "validate", lambda p_, execute, max_items=200: v)
    out = json.loads(server.create_data_agent("demo", "demo_lh", name="sap_agent", schema="sap", validate=True,
                                              requirements=DEMO_LIST))
    assert out["dry_run"] is True
    assert out["requirements"]["added"] == ["R1", "R2"] and out["requirements"]["states"]["R3"] == "missing"
    mine = [f for f in out["agent"]["fewshots"] if f["query"].startswith("-- R")]
    assert [f["question"] for f in mine] == ["Revenue per customer and month", "Order value per material and month"]
    assert mine[1]["query"].startswith("-- R2: Order value per material and month")


# ------------------------------------------------------------------ the card in a browser -----------------------------

from test_wb13_chat_cards import _browse, _fits, _result, needs_browser  # noqa: E402


@needs_browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_card_fits_a_phone_with_its_steps_first_and_no_blank_space(tmp_path, monkeypatch, answer, scheme):
    monkeypatch.setenv(mcp_apps.FLAG, "1")
    call = {"workspace": "demo", "source": "demo_lh", "schema": "sap"}

    def fn(requirements, workspace="", source="", schema="dbo", ctx=None):
        return json.dumps({**answer, "kg_card": rq.card(answer)})
    fn.__name__ = "requirements_draft"
    r = mcp_apps.structured(fn, "requirements_draft")(DEMO_LIST, **call)
    out = _browse(tmp_path, mcp_apps_build.card_html(), {
        "result": _result(r), "args": call, "caps": {"serverTools": {}}, "width": 390, "scheme": scheme,
        "clicks": [{"css": "details > summary"}, {"css": "details > summary"}]})
    _fits(out)
    assert not out["overflow"], "the card scrolls sideways at 390 px"
    assert "5 requirements: 1 answerable now, 1 with a trap, 2 missing data, 1 unclear." in out["text"]
    texts = [b["text"] for b in out["buttons"]]
    assert any(t.startswith("Draft the gold views for R1, R2") for t in texts), texts
    assert any(b["primary"] for b in out["buttons"]), out["buttons"]
    o = out["order"]
    assert o["firstButton"] and o["firstButtonTop"] < 600, o
    dark = out["background"] in ("rgb(27, 27, 31)",)
    assert dark == (scheme == "dark"), out["background"]


def test_the_demo_scripts_step_4_answers_the_question(demo):
    p, _, v = demo
    out = rq.draft(p, DEMO_LIST.replace("Show our best customers", "Revenue per customer and year"), v, "sap")
    assert out["requirements"][4]["state"] == "answerable" and out["counts"]["unclear"] == 0
    script = (Path(__file__).parents[1] / "docs" / "demo" / "REQUIREMENTS-DEMO.md").read_text(encoding="utf-8")
    assert DEMO_LIST.strip() in script                                      # the script pastes the tested list
