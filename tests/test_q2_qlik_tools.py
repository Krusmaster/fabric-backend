"""Q2: the three Qlik tools (fabric_backend/qlik_tools.py; docs/QLIK-MIGRATION-PRODUCT.md).

Synthetic only: the script is tests/fixtures/q1/sales.qvs and the rows are the ones tests/test_q1_qlik.py plants. The
DAX is compared as text and was never run; the reconciliation statements run here on SQLite, not on a Fabric SQL
analytics endpoint. Nothing was exported from Qlik.
"""
import asyncio
import json
import re
import sqlite3
from pathlib import Path

import pytest

from fabric_backend import evidence, mcp_apps_words, mcp_server, qlik, qlik_tools, semantic_model, server, tool_status
from fabric_backend.platforms.local import _sqlite_execute
from fabric_backend.qlik import expr, measures, reconcile

from test_q1_qlik import ROWS

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "tests" / "fixtures" / "q1" / "sales.qvs").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def read():
    return qlik.read_script(SCRIPT)


@pytest.fixture(scope="module")
def execute(read):
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute("ATTACH DATABASE ':memory:' AS landed")
    for t in read["tables"]:
        cols = [c["column"] for c in t["columns"]]
        con.execute(f"CREATE TABLE landed.[{t['table']}] ({', '.join('[' + c + ']' for c in cols)})")
        con.executemany(f"INSERT INTO landed.[{t['table']}] VALUES ({','.join('?' * len(cols))})", ROWS[t["name"]])
    run = _sqlite_execute(con)
    yield lambda sql: run(re.sub(r"\bN'", "'", sql))             # SQLite has no N'...' literal; T-SQL does
    con.close()


def _card_is_plain(card: dict):
    """The rules the other tools' cards follow (mcp_apps_words): one result line, at most five lines, no tool name,
    no argument syntax, numbers that agree with their nouns."""
    assert card["result"].endswith(".") and card["title"]
    assert len(card.get("lines", [])) <= mcp_apps_words.LINES_MAX
    said = [card["result"]] + card.get("lines", []) + [n["line"] for n in card.get("notes", [])]
    for line in said:
        assert not mcp_apps_words.WORDS_WITH_ARGUMENTS.search(line), line
        assert not mcp_apps_words.TOOL_NAME.search(line) and not re.search(r"\bqlik_[a-z_]+\b", line), line
        assert not re.search(r"\(s\)|\(ies\)|\b1 (tables|rows|keys|relationships|measures|expressions|KPIs|statements)\b", line), line
        assert mcp_apps_words.plain(line) == line


# ------------------------------------------------------------------ qlik_plan ----------------------------------------

def test_plan_without_rows_says_that_nothing_was_counted(read):
    a = qlik_tools.plan_answer(SCRIPT)
    assert a["kind"] == "qlik_plan" and a["decided_by"] == "names only: nothing was counted"
    assert a["read"] == {"tables": 9, "linking_fields": 8, "synthetic_keys": 3, "circular_references": 1, "mapping_tables": 2,
                         "calculated_fields": len(read["calculated_fields"]), "dollar_expansions": read["dollar_expansions"],
                         "section_access": False}
    assert a["statements"]["total"] == len(read["statements"]) and a["statements"]["not_read"] == 1
    assert [n["line"] for n in a["not_read"]] == [82]
    assert a["counting"] == {"queries": 0, "not_counted_limit": 0, "failed": []}
    assert "statements" in a and "kg_card" in a and "No AI model" not in a["note"] and "no AI model" in a["note"]
    cases = {tuple(s["tables"]): s["case"] for s in a["synthetic_keys"]}
    assert cases[("Budget", "StoreSales")] == "not_decided"       # nothing is said about a pair nobody counted
    assert "Nothing was counted" in " ".join(a["kg_card"]["lines"])
    _card_is_plain(a["kg_card"])
    assert len(json.dumps(a, indent=2)) < server.MAX_RESULT_CHARS


def test_plan_counted_in_the_rows_puts_each_synthetic_key_in_its_case(execute):
    a = qlik_tools.plan_answer(SCRIPT, execute, schema="landed")
    assert a["decided_by"] == "counts in the rows" and a["counting"]["queries"] > 0 and a["counting"]["failed"] == []
    assert {tuple(s["tables"]): s["case"] for s in a["synthetic_keys"]} == {
        ("Budget", "StoreSales"): "two_facts_sharing_dimensions", ("OrderLines", "Returns"): "composite_key",
        ("Orders", "Shipments"): "one_field_links"}
    star = a["star_schema"]
    assert [p["field"] for p in star["proposed_dimensions"]] == ["Month"]
    assert {d["table"] for d in star["dimensions"]} == {"Customers", "Products", "Stores"}
    assert "Orders" in {t["table"] for t in star["tables_in_between"]}
    assert any("combined key column for OrderID+LineNo" in c for c in star["changes"])
    assert any("dimension table of the distinct values of Month" in c for c in star["changes"])
    card = a["kg_card"]
    assert card["result"] == "Read 9 tables and 8 linking fields from the load script; 9 relationships are in the plan. Nothing was created."
    assert "3 synthetic keys: 1 two facts sharing dimensions, 1 a combined key, 1 one field links." in card["lines"]
    assert "The one sides were counted in the rows." in card["lines"]
    assert any("move" in n["line"] and "numbers" in n["line"] for n in card["notes"])
    _card_is_plain(card)


def test_the_plan_format_is_what_the_engine_takes(execute):
    """plan.keys and plan.confirmed are the `keys` and `confirmed` arguments of the planning tools: the engine's own
    check and the semantic model draft take them as they are."""
    a = qlik_tools.plan_answer(SCRIPT, execute, schema="landed")
    keys, confirmed = a["plan"]["keys"], a["plan"]["confirmed"]
    assert keys["OrderLines"] == ["OrderID", "LineNo"] and keys["Customers"] == ["CustomerID"]
    assert {"source": "Orders", "source_cols": ["CustomerID"], "target": "Customers", "target_cols": ["CustomerID"]} in confirmed
    assert all(set(c) == {"source", "source_cols", "target", "target_cols"} for c in confirmed)
    mapping = qlik.map_associations(qlik.read_script(SCRIPT), execute, schema="landed")
    p, _ = qlik.to_plan(mapping, "landed")
    assert {t: cols for t, (cols, _) in p.keys.items() if t in keys} == keys
    assert len([r for r in p.relationships]) == len(confirmed)
    checked = evidence.validate(p, execute, max_items=200)
    assert checked["summary"].startswith("7 of 7 keys unique")
    draft = semantic_model.draft(p, {"endpoint": "x.datawarehouse.fabric.microsoft.com", "database": "db"}, "from_qlik", validation=checked)
    assert draft["summary"]["tables"] == 9


def test_plan_full_detail_adds_sources_and_steps_and_names_built_at_run_time_are_flagged():
    full = qlik_tools.plan_answer(SCRIPT, detail="full")
    lines = next(t for t in full["tables"] if t["qlik"] == "OrderLines")
    assert lines["steps"] and lines["sources"] and any(c.get("expression") for c in lines["column_sources"])
    summary = next(t for t in qlik_tools.plan_answer(SCRIPT)["tables"] if t["qlik"] == "OrderLines")
    assert "steps" not in summary and summary["shaped_in_the_script"] == len(lines["steps"])
    built = qlik_tools.plan_answer("$(vTable):\nLOAD a, b FROM [lib://X/t.qvd] (qvd);\nIf 1 = 1 then\n$(Include=lib://X/more.qvs);\nEnd If")
    assert "name_built_when_the_script_runs" in built["tables"][0]
    assert built["includes"][0]["file"] == "lib://X/more.qvs"
    assert "2 control statements were listed, not run; 1 included file was not given." in built["kg_card"]["lines"]
    _card_is_plain(built["kg_card"])
    with pytest.raises(ValueError):
        qlik_tools.plan_answer(SCRIPT, detail="everything")


def test_section_access_is_said_and_stays_out_of_the_plan():
    a = qlik_tools.plan_answer("SECTION ACCESS;\nLOAD * INLINE [\nACCESS, USERID\nADMIN, USER_A\n];\nSECTION APPLICATION;\n"
                               "T:\nLOAD k, v FROM [lib://X/t.qvd] (qvd);")
    assert a["read"]["section_access"] is True and "row-level security" in a["section_access"]
    assert "USER_A" not in json.dumps(a) and [t["qlik"] for t in a["tables"]] == ["T"]


# ------------------------------------------------------------------ expressions --------------------------------------

@pytest.mark.parametrize("text,why", [
    ("Sum({State1} Amount)", "alternate state or a bookmark"),
    ("Sum({<Year={2025}> + <Year={2024}>} Amount)", "set operators"),
    ("Sum({<Customer=P({1<Year={2025}>} Customer)>} Amount)", "P() and E() have no rule yet"),
    ('Sum({<Month={">=2026-09"}>} Amount)', "a search inside the set"),
    ("Sum({<Year+={2025}>} Amount)", "changes the user's selection"),
    ("Sum({<Year={$(vYear)}>} Amount)", "dollar-sign expansion"),
    ("Sum(Aggr(Sum(Amount), Customer))", "Aggr()"),
    ("RangeSum(Above(Sum(Amount), 0, RowNo()))", "RangeSum()"),
    ("Only(Status)", "Only()"),
    ("Sum(Amount", "expected"),
    ("Sum(Amount) §", "is not read"),
    ("", "empty"),
])
def test_what_no_rule_carries_over_stops_with_its_reason(text, why):
    with pytest.raises(expr.Unsupported) as e:
        expr.parse(text)
    assert why in str(e.value)


def test_an_expression_is_read_as_a_tree():
    tree = expr.parse("=Sum({<Year={2025, 'x'}, Region=>} TOTAL <Country> DISTINCT [Line Amount] * 2) / Count(DISTINCT OrderID)")
    agg = tree[2][1]
    assert agg["fn"] == "sum" and agg["distinct"] is True and agg["total"] == ["Country"]
    assert agg["set"] == {"identifier": "$", "modifiers": [("Year", [("num", "2025"), ("str", "x")]), ("Region", None)]}
    assert expr.fields(tree) == ["Country", "Year", "Region", "Line Amount", "OrderID"]
    assert expr.expand("Sum($(vField)) * $(vRate) + $(vUnknown)", {"vField": "Amount", "vRate": "0.25"}) == (
        "Sum(Amount) * 0.25 + $(vUnknown)", ["vField", "vRate"])


# ------------------------------------------------------------------ qlik_measures_draft ------------------------------

MEASURES = [
    ("Revenue", "Sum(LineAmount)", "translated", "SUM('OrderLines'[LineAmount])"),
    ("Smallest line", "Min(LineAmount)", "translated", "MIN('OrderLines'[LineAmount])"),
    ("Average price", "=Avg(UnitPrice)", "translated", "AVERAGE('OrderLines'[UnitPrice])"),
    ("Shipments", "Count(ShipmentID)", "translated", "COUNTA('Shipments'[ShipmentID])"),
    ("Customers", "Count(DISTINCT [Customers.Name])", "translated", "DISTINCTCOUNTNOBLANK('Customers'[Customers_Name])"),
    ("Gross", "Sum(Quantity * UnitPrice)", "translated", "SUMX('OrderLines', 'OrderLines'[Quantity] * 'OrderLines'[UnitPrice])"),
    ("Large lines", "Sum(If(Quantity > 2, LineAmount, 0))", "translated",
     "SUMX('OrderLines', IF('OrderLines'[Quantity] > 2, 'OrderLines'[LineAmount], 0))"),
    ("Revenue per unit", "Revenue / Sum(Quantity)", "translated", "DIVIDE([Revenue], SUM('OrderLines'[Quantity]))"),
    ("Margin", "(Revenue - Sum(Quantity * 2)) / [Revenue]", "translated",
     "DIVIDE(([Revenue] - SUMX('OrderLines', 'OrderLines'[Quantity] * 2)), [Revenue])"),
    ("Web sales", "Sum({<Channel={'web'}>} SalesAmount)", "suggested",
     "CALCULATE(SUM('StoreSales'[SalesAmount]), 'StoreSales'[Channel] IN {\"web\"})"),
    ("Sales, all channels", "Sum({$<Channel=>} SalesAmount)", "suggested",
     "CALCULATE(SUM('StoreSales'[SalesAmount]), REMOVEFILTERS('StoreSales'[Channel]))"),
    ("All revenue", "Sum({1} LineAmount)", "suggested", "CALCULATE(SUM('OrderLines'[LineAmount]), REMOVEFILTERS())"),
    ("Share", "Sum(LineAmount) / Sum(TOTAL LineAmount)", "suggested",
     "DIVIDE(SUM('OrderLines'[LineAmount]), CALCULATE(SUM('OrderLines'[LineAmount]), ALLSELECTED()))"),
    ("Share in channel", "Sum(SalesAmount) / Sum(TOTAL <Channel> SalesAmount)", "suggested",
     "DIVIDE(SUM('StoreSales'[SalesAmount]), CALCULATE(SUM('StoreSales'[SalesAmount]), ALLSELECTED(), VALUES('StoreSales'[Channel])))"),
    ("Formatted", "Num(Sum(LineAmount), '#,##0')", "suggested", "SUM('OrderLines'[LineAmount])"),
    ("Unknown field", "Sum(Margin%)", "suggested", "SUM('<table>'[Margin%])"),
    ("Orders", "Count(DISTINCT OrderID)", "not_translated", "the field OrderID is in 4 tables"),
    ("List value", "Sum(Quantity * ListPrice)", "not_translated", "fields of 2 tables"),
    ("Per order", "Avg(Aggr(Sum(LineAmount), OrderID))", "not_translated", "Aggr()"),
    ("Selected", "Sum({Bookmark01} LineAmount)", "not_translated", "alternate state or a bookmark"),
    ("Bare field", "LineAmount * 2", "not_translated", "outside an aggregation"),
    ("Constant", "42", "not_translated", "a constant"),
    ("Run time", "Sum({<Month={'$(=Max(Month))'}>} BudgetAmount)", "not_translated", "dollar-sign expansion"),
    ("Nested", "Sum(Sum(LineAmount))", "not_translated", "needs Aggr()"),
]


def test_each_measure_gets_its_label_and_its_dax_or_its_reason(read):
    out = measures.draft([{"name": n, "expression": e} for n, e, _, _ in MEASURES], read)
    by = {m["name"]: m for m in out["measures"]}
    for name, _, label, want in MEASURES:
        m = by[name]
        assert m["label"] == label, (name, m)
        if label == "not_translated":
            assert want in m["why"] and "dax" not in m, (name, m["why"])
        else:
            assert m["dax"] == want, (name, m["dax"])
            assert ("may_differ" in m) == (label == "suggested"), name
    assert out["counts"] == {"translated": 9, "suggested": 7, "not_translated": 8, "total": 24}
    assert by["Revenue"]["table"] == "OrderLines" and "table" not in by["Unknown field"]
    assert "not a dimension of the visual" in by["Web sales"]["may_differ"][0]
    assert "is not known" in by["Unknown field"]["may_differ"][0]


def test_a_set_variable_is_expanded_and_a_let_variable_is_not():
    script = "SET vRate = 0.25;\nLET vToday = Today();\nT:\nLOAD Amount, Qty FROM [lib://X/t.qvd] (qvd);"
    out = qlik_tools.measures_answer([{"name": "Fee", "expression": "Sum(Amount) * $(vRate)"},
                                      {"name": "Today", "expression": "Sum(Amount) * $(vToday)"}], script)
    fee, today = out["measures"]
    assert fee["label"] == "translated" and fee["dax"] == "SUM('T'[Amount]) * 0.25"
    assert fee["expanded"] == ["$(vRate) from its SET in the script"]
    assert today["label"] == "not_translated" and "dollar-sign expansion" in today["why"]


def test_measures_are_read_from_a_list_from_lines_and_from_json():
    lines = measures.read_measures("// the app's measures\nRevenue = Sum(LineAmount)\nShare = Sum(a) / Sum(TOTAL a)\n")
    assert lines == [{"name": "Revenue", "expression": "Sum(LineAmount)"}, {"name": "Share", "expression": "Sum(a) / Sum(TOTAL a)"}]
    as_json = measures.read_measures(json.dumps([{"qMeasure": {"qLabel": "Revenue", "qDef": "Sum(LineAmount)"}},
                                                 {"qMetaDef": {"title": "Units"}, "qMeasure": {"qDef": "Sum(Quantity)"}}]))
    assert [m["name"] for m in as_json] == ["Revenue", "Units"]
    for bad in ("no equals sign here", [{"name": "x"}], [1], {"a": 1}, "[not json"):
        with pytest.raises(ValueError):
            measures.read_measures(bad)
    twice = measures.draft([{"name": "A", "expression": "Sum(x)"}, {"name": "A", "expression": "Sum(y)"}])
    assert [m["label"] for m in twice["measures"]] == ["not_translated"] * 2 and "2 measures are named A" in twice["measures"][0]["why"]


def test_the_measures_answer_counts_says_what_it_is_and_gives_tmdl_on_request():
    a = qlik_tools.measures_answer([{"name": n, "expression": e} for n, e, _, _ in MEASURES], SCRIPT, tmdl=True)
    assert a["kg_card"]["result"] == ("9 of 24 expressions translated by rule, 7 suggested, 8 not translated. "
                                      "Nothing was created and no DAX was run.")
    assert "no share of an app's expressions is promised" in a["note"] and set(a["labels"]) == {"translated", "suggested", "not_translated"}
    _card_is_plain(a["kg_card"])
    assert "measure 'Revenue' = SUM('OrderLines'[LineAmount])" in a["tmdl"]
    assert "<table>" not in a["tmdl"] and "/// suggested, may differ from Qlik:" in a["tmdl"]
    assert a["tmdl"].index("/// suggested, may differ from Qlik: Channel set to fixed values") < a["tmdl"].index("measure 'Web sales'")
    bare = qlik_tools.measures_answer("Revenue = Sum(LineAmount)")
    assert bare["field_tables"].startswith("not known") and "tmdl" not in bare
    assert "No load script was given, so the fields have no table yet." in bare["kg_card"]["lines"]


# ------------------------------------------------------------------ qlik_reconcile_draft -----------------------------

KPIS = [
    {"name": "Revenue", "expression": "Sum(LineAmount)", "value": 220},
    {"name": "Revenue by store", "expression": "Sum(LineAmount)", "by": ["StoreName"],
     "values": [{"StoreName": "North", "value": 50}, {"StoreName": "West", "value": 130},
                {"StoreName": "South", "value": 41},          # planted: the rows give 40
                {"StoreName": "East", "value": 5}]},           # planted: no such store in the rows
    {"name": "Revenue by segment", "expression": "Sum(Quantity * UnitPrice)", "by": ["Segment"],
     "values": [{"Segment": "Retail", "value": 140}, {"Segment": "Trade", "value": 70}, {"Segment": "-", "value": 10}]},
    {"name": "Price", "expression": "Sum(LineAmount) / Sum(Quantity)", "value": "20.0"},
    {"name": "Two shipments", "expression": "Count({<ShipmentID={'SH1','SH2'}>} ShippedOn)", "value": 2},
    {"name": "Budget by month", "expression": "Sum(BudgetAmount)", "by": ["Month"],
     "values": [{"Month": "2026-09", "value": 220}]},          # planted: 2026-10 is in the rows and not in the export
    {"name": "Share", "expression": "Sum(LineAmount) / Sum(TOTAL LineAmount)", "value": 1},
    {"name": "List value", "expression": "Sum(Quantity * ListPrice)", "value": 1},
    {"name": "By month", "expression": "Sum(LineAmount)", "by": ["Month"], "values": [{"Month": "2026-09", "value": 1}]},
]


def test_the_statements_run_and_find_the_planted_differences(read, execute):
    out = reconcile.draft(read, KPIS, schema="landed")
    by = {k["name"]: k for k in out["kpis"]}
    assert out["totals"]["with_sql"] == 6 and out["totals"]["without_sql"] == 3 and out["totals"]["to_compute"] == out["totals"]["rows"]
    assert by["Revenue by store"]["joins"] == ["OrderLines.OrderID -> Orders", "Orders.StoreID -> Stores"]
    assert "TOTAL" in by["Share"]["why_no_sql"] and "two tables' rows" in by["List value"]["why_no_sql"]
    assert "no relationship path" in by["By month"]["why_no_sql"]
    rows = {name: execute(k["sql"]) for name, k in by.items() if k["sql"]}
    assert rows["Revenue"] == [{"qlik_value": 220.0, "new_value": 220, "difference": 0.0, "status": "equal"}]
    assert {r["StoreName"]: r["status"] for r in rows["Revenue by store"]} == {
        "North": "equal", "West": "equal", "South": "different", "East": "only in Qlik"}
    assert next(r for r in rows["Revenue by store"] if r["StoreName"] == "South")["difference"] == -1.0
    assert {r["Segment"]: r["status"] for r in rows["Revenue by segment"]} == {"Retail": "equal", "Trade": "equal", None: "equal"}
    assert rows["Price"][0]["status"] == "equal" and rows["Two shipments"][0]["new_value"] == 2
    assert {r["Month"]: r["status"] for r in rows["Budget by month"]} == {"2026-09": "equal", "2026-10": "only on the migrated tables"}

    filled = reconcile.draft(read, KPIS, schema="landed", results=rows)
    assert filled["totals"] == {"kpis": 9, "with_sql": 6, "without_sql": 3, "rows": 15, "equal": 9, "different": 1, "only_in_qlik": 1,
                                "only_on_the_migrated_tables": 1, "to_compute": 3}
    store = {r["StoreName"]: r for r in next(k for k in filled["kpis"] if k["name"] == "Revenue by store")["comparison"]["rows"]}
    assert store["South"] == {"StoreName": "South", "qlik_value": 41.0, "new_value": 40.0, "difference": -1.0, "status": "different"}
    assert store["East"]["status"] == "only in Qlik" and store["East"]["new_value"] is None
    opened = next(k for k in filled["kpis"] if k["name"] == "Revenue by store")["open"]
    assert "2 row(s) differ" in opened and "No reason is named" in opened
    assert "probably" not in json.dumps(filled).lower() and "likely" not in json.dumps(filled).lower()


def test_the_statement_is_t_sql_with_the_exported_values_inside_and_a_tolerance(read):
    k = reconcile.draft(read, [KPIS[1]], schema="dbo", tolerance=0.5)["kpis"][0]
    sql = k["sql"]
    assert sql.startswith("WITH qlik ([g1], [value], [present]) AS (\n    SELECT N'North', 50.0, 1\n    UNION ALL SELECT N'West', 130.0, 1")
    assert "FROM [dbo].[OrderLines] AS b\n    LEFT JOIN [dbo].[Orders] AS t1 ON b.[OrderID] = t1.[OrderID]" in sql
    assert "GROUP BY t2.[StoreName]" in sql and "FULL OUTER JOIN migrated AS n" in sql and "<= 0.5 THEN 'equal'" in sql
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|EXEC)\b", sql)
    null_first = reconcile.draft(read, [{"name": "n", "expression": "Sum(LineAmount)", "by": ["Segment"],
                                         "values": [{"Segment": None, "value": None}, {"Segment": "It's", "value": 1}]}])["kpis"][0]["sql"]
    assert "SELECT CAST(NULL AS NVARCHAR(4000)), CAST(NULL AS FLOAT), 1" in null_first and "N'It''s'" in null_first
    given = reconcile.draft(read, [KPIS[0]], confirmed=[])
    assert given["relationships_from"] == "the relationships given"


@pytest.mark.parametrize("kpis,said", [
    ([], "kpis must be a list"),
    ([{"name": "a"}], "needs a name and an expression"),
    ([{"name": "a", "expression": "Sum(x)"}], "no exported value"),
    ([{"name": "a", "expression": "Sum(x)", "value": "1 234,5"}], "is not a number"),
    ([{"name": "a", "expression": "Sum(x)", "by": ["y"], "value": 1}], "give values"),
    ([{"name": "a", "expression": "Sum(x)", "by": ["y"], "values": [{"value": 1}]}], "no value for y"),
    ([{"name": "a", "expression": "Sum(x)", "by": ["y"], "values": [{"y": 1, "value": 1}, {"y": "1", "value": 2}]}], "given twice"),
])
def test_kpis_that_cannot_be_read_are_refused_in_plain_words(read, kpis, said):
    with pytest.raises(ValueError) as e:
        reconcile.draft(read, kpis)
    assert said in str(e.value)


def test_the_reconcile_answer_and_its_card(read, execute):
    first = qlik_tools.reconcile_answer(SCRIPT, KPIS, schema="landed")
    assert first["kg_card"]["result"] == "SQL written for 6 of 9 KPIs. Nothing was run."
    assert "3 KPIs have no SQL: Share, List value, By month." in first["kg_card"]["lines"]
    _card_is_plain(first["kg_card"])
    rows = {k["name"]: execute(k["sql"]) for k in first["kpis"] if k["sql"]}
    second = qlik_tools.reconcile_answer(SCRIPT, KPIS, schema="landed", results=rows)
    card = second["kg_card"]
    assert card["result"] == "Compared 12 rows for 9 KPIs: 9 equal, 3 not."
    assert "9 rows equal within 0.005, 1 different, 1 only in Qlik, 1 only on the migrated tables." in card["lines"]
    assert "3 rows have no result yet." in card["lines"]
    assert "Each difference is open: no reason is named until a count reproduces it." in card["lines"]
    assert any("Revenue by store, StoreName South: Qlik 41.0, migrated 40.0 (different)" in i for n in card["notes"] for i in n["items"])
    _card_is_plain(card)
    assert len(second["checks_that_may_explain_a_difference"]) == len(reconcile.CANDIDATES) and "no selections" in second["export_rule"]


# ------------------------------------------------------------------ the tools on both servers ------------------------

def _tools(module):
    return {t.name: t for t in asyncio.run(module.mcp.list_tools())}


@pytest.mark.parametrize("module", [server, mcp_server], ids=["hosted", "local"])
def test_the_three_tools_are_registered_read_only_with_honest_descriptions(module):
    tools = _tools(module)
    for name in qlik_tools.NAMES:
        t = tools[name]
        assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False, name
        text = " ".join((t.description or "").split())
        assert "no AI model" in text.replace("No AI model", "no AI model") and "Errors: {error, kind, hint}" in text, name
        for word in ("fast", "automat", "seamless", "complete", "accurate", "certif", "partner", "endorse", "compliant", "%"):
            assert word not in text.lower(), (name, word)
        for p, spec in t.input_schema["properties"].items():
            assert spec.get("description"), (name, p)
    assert "Not tested on a customer's Qlik installation" in " ".join(tools["qlik_plan"].description.split())
    assert "Qlik" not in " ".join(n for n in tools)                      # the names are lower case and say what is read


def test_the_hosted_tools_have_a_status_and_carry_the_experimental_label():
    tools = _tools(server)
    for name in qlik_tools.NAMES:
        s = tool_status.STATUS[name]
        assert s.kind == tool_status.DRAFT and s.available == tool_status.HOSTED and "unit tests" in s.tested
        assert tool_status.experimental(name) and tools[name].title.endswith("(experimental)")


def test_the_hosted_plan_reads_fabric_only_when_a_workspace_and_a_source_are_named(monkeypatch):
    called = []
    monkeypatch.setattr(server, "_connected", lambda *a: called.append(a) or (_ for _ in ()).throw(AssertionError("no Fabric call expected")))
    a = json.loads(server.qlik_plan(script=SCRIPT))
    assert a["kind"] == "qlik_plan" and a["decided_by"].startswith("names only") and not called
    half = json.loads(server.qlik_plan(script=SCRIPT, workspace="demo"))
    assert half["kind"] == "bad_input" and "workspace and source together" in half["error"] and not called


def test_the_hosted_plan_counts_over_the_connection_it_is_given_and_closes_it(monkeypatch, execute):
    closed = []

    class Landed:
        schema = "landed"

    def run(sql):
        return execute(sql)
    run.close = lambda: closed.append(True)
    monkeypatch.setattr(server, "_connected", lambda workspace, source, schema, ctx: (Landed(), run))
    a = json.loads(server.qlik_plan(script=SCRIPT, workspace="demo", source="demo_lh", schema="Landed"))
    assert a["decided_by"] == "counts in the rows" and a["counting"]["failed"] == [] and closed == [True]


def test_bad_input_is_answered_as_bad_input_and_the_local_server_answers_the_same_three():
    for call in (lambda: server.qlik_plan(script=12), lambda: server.qlik_measures_draft(measures=[{"name": "x"}]),
                 lambda: mcp_server.qlik_reconcile_draft(script=SCRIPT, kpis=[]),
                 lambda: mcp_server.qlik_plan(script=SCRIPT, detail="everything")):
        a = json.loads(call())
        assert a["kind"] == "bad_input" and a["error"] and "Nothing was created" in a["hint"]
    local = json.loads(mcp_server.qlik_plan(script=SCRIPT))
    hosted = json.loads(server.qlik_plan(script=SCRIPT))
    assert local == hosted                                                # same rules, same answer, nothing counted
    m = json.loads(mcp_server.qlik_measures_draft(measures="Revenue = Sum(LineAmount)", script=SCRIPT))
    assert m["measures"][0]["dax"] == "SUM('OrderLines'[LineAmount])"
    r = json.loads(mcp_server.qlik_reconcile_draft(script=SCRIPT, kpis=[KPIS[0]]))
    assert r["totals"]["with_sql"] == 1


def test_the_card_shows_the_tools_own_words():
    a = json.loads(server.qlik_plan(script=SCRIPT))
    card = mcp_apps_words.card("qlik_plan", a)
    assert card["title"] == "Plan from a Qlik load script" and card["result"] == a["kg_card"]["result"] == card["onto"]
    assert card["lines"] == a["kg_card"]["lines"] and [n["line"] for n in card["notes"]] == [n["line"] for n in a["kg_card"]["notes"]]
    assert mcp_apps_words.card("qlik_plan", {"error": "x", "kind": "bad_input"}) is None


def test_the_answers_stay_under_the_size_cap_on_the_largest_public_script():
    big = (ROOT / "tests" / "fixtures" / "qlik" / "butler" / "butler_subs.qvs").read_text(encoding="utf-8")
    text = server.qlik_plan(script=big, detail="full")
    assert len(text) <= server.MAX_RESULT_CHARS and json.loads(text)["kind"] == "qlik_plan"


def test_no_script_text_is_kept_between_calls():
    """The module holds no state: two calls share nothing, and the answer holds no inline rows and no connection."""
    script = ("LIB CONNECT TO 'secret-connection';\nSET vPassword = hunter2;\nT:\nLOAD * INLINE [\nk, v\n1, hidden-value\n];")
    text = server.qlik_plan(script=script)
    assert "hidden-value" not in text and "secret-connection" not in text and "hunter2" not in text
    assert not [n for n in vars(qlik_tools) if n.startswith("_cache") or n.startswith("_store")]
