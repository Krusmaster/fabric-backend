"""n151: create_report's default page reads like a report (Gustav's review of shop_report_visuals, 7 November 2026).

Plain titles from a small mapping that never invents a meaning; cards for business tables only; a grid that fills
1280 x 720 between even margins, with or without the month chart; whole-number formats for counts and quantities in
create_semantic_model's TMDL, and in the visual when a model of someone else's lacks them; the Krusgraph theme, a page
title and a footnote; a Date table over the data's range with Year Month; slicers only when their fields exist; data
labels on the charts, bars and table rows largest first, the table with a total row. The PBIR parts are validated
against Microsoft's schemas in tests/test_create_report.py (schema_errors); the theme here against the property names
of Microsoft's report theme schema."""
import copy
import json
import re
from pathlib import Path

import pytest

from fabric_backend import model_compare, report, seed, semantic_model, server
from fabric_backend.infer import plan
from test_create_report import MODEL_ID, SHOP, SHOP_PARTS, _check_against_model, schema_errors
from test_creating_tools import shop  # noqa: F401  (the mocked hosted source)

ROOT = Path(__file__).resolve().parents[1]
INNER = (report.MARGIN, report.MARGIN, report.PAGE_W - report.MARGIN, report.PAGE_H - report.MARGIN)


def _model(*, tables, rels=()):
    rel = lambda f, fc, t, tc: {"name": f"{f}-{t}", "active": True, "cross_filter": "oneDirection", "from_cardinality": "many",
                                "to_cardinality": "one", "from_table": f, "from_column": fc, "to_table": t, "to_column": tc}
    return {"tables": tables, "relationships": [rel(*r) for r in rels]}


def _col(n, dt="int64", key=False, s="none"):
    return {"name": n, "data_type": dt, "is_key": key, "summarize_by": s}


# ------------------------------------------------------------------ 1. plain titles ---------------------------------

def test_table_names_in_plain_words_and_lines_only_when_the_header_is_there():
    assert report.plain_table(SHOP, "order_items") == "Order lines"           # order_items points at orders
    assert report.plain_table(SHOP, "audit_log") == "Audit log" and report.plain_table(SHOP, "orders") == "Orders"
    lone = _model(tables={"news_items": {"columns": {}, "measures": {}}})
    assert report.plain_table(lone, "news_items") == "News items"             # no news table: never "News lines"
    other = _model(tables={"order_items": {"columns": {}, "measures": {}}, "orders": {"columns": {}, "measures": {}},
                           "products": {"columns": {}, "measures": {}}}, rels=[("order_items", "product_id", "products", "product_id")])
    assert report.plain_table(other, "order_items") == "Order items"          # orders is there but not pointed at


@pytest.mark.parametrize("measure,expression,kind,title", [
    ("Rows in orders", "COUNTROWS('orders')", "count", "Orders"),
    ("Rows in order_items", "COUNTROWS('order_items')", "count", "Order lines"),
    ("Total quantity", "SUM('order_items'[quantity])", "quantity", "Units"),
    ("Order amount", "SUMX('order_items', 'order_items'[quantity] * RELATED('products'[list_price]))", "amount", "Order amount"),
    ("Rows in orders", "DISTINCTCOUNT('orders'[customer_id])", "count", "Rows in orders"),   # not a row count: kept
    ("Rows in orders", "COUNTROWS('customers')", "count", "Rows in orders"),                 # another table's rows: kept
    ("Total weight", "SUM('order_items'[weight])", "amount", "Total weight"),                # not a quantity: never "Units"
    ("Customers", "COUNTROWS('orders')", "count", "Customers"),                               # an own name: kept
])
def test_measure_titles_never_invent_a_meaning(measure, expression, kind, title):
    m = {"table": "order_items" if "order_items" in expression or "weight" in expression else "orders", "measure": measure,
         "expression": expression, "kind": kind}
    assert report.title_of(SHOP, m) == title


def test_the_shop_page_has_the_titles_of_the_review():
    titles = [v["title"] for v in report.definition_parts(SHOP, MODEL_ID, model_name="shop_model", created="8 November 2026")["visuals"]]
    assert titles == ["Overview · shop_model", "Orders", "Order lines", "Units", "Units by month", "Units by category", "Products by units",
                      "Month", "Category", "8 November 2026. Created by Krusgraph from the checked plan."]


# ------------------------------------------------------------------ 2. cards ----------------------------------------

def test_log_like_and_keyless_tables_get_no_card_unless_nothing_else():
    cards = [v for v in report.definition_parts(SHOP, MODEL_ID)["visuals"] if v["type"] == "card"]
    assert [c["fields"][0] for c in cards] == ["orders[Rows in orders]", "order_items[Rows in order_items]", "order_items[Total quantity]"]
    only_logs = _model(tables={"audit_log": {"columns": {"event": _col("event", "string")},
                                             "measures": {"Rows in audit_log": {"expression": "COUNTROWS('audit_log')"}}}})
    d = report.visuals(only_logs)
    assert [v["fields"] for v in d["visuals"] if v["type"] == "card"] == [["audit_log[Rows in audit_log]"]] and d["not_drawn"][-1]["visual"] == "clusteredColumnChart"
    many = _model(tables={f"t{i}": {"columns": {"id": _col("id", key=True)}, "measures": {f"Rows in t{i}": {"expression": f"COUNTROWS('t{i}')"}}}
                          for i in range(6)})
    assert len([v for v in report.visuals(many)["visuals"] if v["type"] == "card"]) == report.MAX_CARDS == 4


# ------------------------------------------------------------------ 3. layout ---------------------------------------

def _boxes(parts):
    out = []
    for path, text in parts.items():
        if path.endswith("/visual.json"):
            doc = json.loads(text)
            p = doc["position"]
            out.append((doc["visual"]["visualType"], p["x"], p["y"], p["x"] + p["width"], p["y"] + p["height"]))
    return out


def _fills_the_page(boxes):
    assert min(b[1] for b in boxes) == INNER[0] and min(b[2] for b in boxes) == INNER[1]
    assert max(b[3] for b in boxes) == pytest.approx(INNER[2]) and max(b[4] for b in boxes) == pytest.approx(INNER[3])
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert not (a[1] < b[3] - 0.01 and b[1] < a[3] - 0.01 and a[2] < b[4] - 0.01 and b[2] < a[4] - 0.01), (a, b)


def _without_calendar(model):
    m = copy.deepcopy(model)
    m["tables"].pop("Calendar")
    m["relationships"] = [r for r in m["relationships"] if "Calendar" not in (r["from_table"], r["to_table"])]
    return m


def test_the_grid_fills_the_page_with_the_month_chart():
    boxes = _boxes(report.definition_parts(SHOP, MODEL_ID)["parts"])
    _fills_the_page(boxes)
    charts = [b for b in boxes if b[0] in ("clusteredColumnChart", "clusteredBarChart")]
    assert len(charts) == 2 and charts[0][2] == charts[1][2] and charts[0][4] == charts[1][4]          # side by side, same row
    table = next(b for b in boxes if b[0] == "tableEx")
    assert (table[1], table[3]) == (INNER[0], INNER[2])                                               # the table spans the page


def test_without_the_month_chart_the_category_chart_takes_its_width():
    model = _without_calendar(SHOP)
    d = report.definition_parts(model, MODEL_ID)
    _check_against_model(d["parts"], model)
    boxes = _boxes(d["parts"])
    _fills_the_page(boxes)
    assert [b[0] for b in boxes].count("clusteredColumnChart") == 0
    bar = next(b for b in boxes if b[0] == "clusteredBarChart")
    assert (bar[1], bar[3]) == (INNER[0], INNER[2])
    assert any(x["visual"] == "clusteredColumnChart" and "no date table" in x["why"] for x in d["not_drawn"])


def test_the_table_columns_fill_the_table_and_it_has_a_total_row():
    doc = next(json.loads(t) for p, t in report.definition_parts(SHOP, MODEL_ID)["parts"].items() if '"tableEx"' in t)
    widths = [x["properties"]["value"]["expr"]["Literal"]["Value"] for x in doc["visual"]["objects"]["columnWidth"]]
    assert sum(float(w.rstrip("D")) for w in widths) == pytest.approx(doc["position"]["width"] - 40)
    assert [x["selector"]["metadata"] for x in doc["visual"]["objects"]["columnWidth"]] == ["products.name", "order_items.Total quantity"]
    assert doc["visual"]["objects"]["total"] == [{"properties": {"totals": {"expr": {"Literal": {"Value": "true"}}}}}]
    assert doc["visual"]["query"]["sortDefinition"]["sort"][0]["direction"] == "Descending"


def test_charts_have_data_labels_and_bars_largest_first():
    parts = report.definition_parts(SHOP, MODEL_ID)["parts"]
    for kind, direction in (("clusteredBarChart", "Descending"), ("clusteredColumnChart", "Ascending")):     # months in time order
        doc = next(json.loads(t) for t in parts.values() if f'"{kind}"' in t)
        assert doc["visual"]["objects"]["labels"][0]["properties"]["show"] == {"expr": {"Literal": {"Value": "true"}}}
        assert doc["visual"]["query"]["sortDefinition"]["sort"][0]["direction"] == direction
        assert doc["visual"]["drillFilterOtherVisuals"] is True                                          # cross-filtering stays on


# ------------------------------------------------------------------ 4. whole numbers --------------------------------

def test_counts_and_sums_of_whole_numbers_are_whole_in_the_tmdl():
    from test_amounts import demo_schema
    tmdl = "\n".join(SHOP_PARTS.values())
    assert re.search(r"measure 'Rows in orders' = COUNTROWS\('orders'\)\n\t\tformatString: #,0\n", tmdl)
    assert re.search(r"measure 'Total quantity' = SUM\('order_items'\[quantity\]\)\n\t\tformatString: #,##0.00\n", tmdl)   # DOUBLE
    whole = semantic_model.draft(plan(seed.schema()), {"schema": "shop"}, "shop_model", whole_quantities={("order_items", "quantity")})["parts"]
    assert "measure 'Total quantity' = SUM('order_items'[quantity])\n\t\tformatString: #,0\n" in "\n".join(whole.values())
    assert semantic_model.number_format("int64") == "#,0" and semantic_model.number_format("double") == "#,##0.00"
    assert semantic_model.quantity_columns(plan(seed.schema())) == [("order_items", "quantity")]
    assert "#,##0\n" not in "\n".join(semantic_model.draft(plan(demo_schema()), {"schema": "demo"}, "m")["parts"].values())


def test_the_visual_sets_no_decimals_only_for_a_model_that_lacks_the_format():
    ours = next(json.loads(t) for t in report.definition_parts(SHOP, MODEL_ID)["parts"].values() if '"card"' in t and "Rows in orders" in t)
    assert "objects" not in ours["visual"]                                                          # "#,0" in the model already
    theirs = copy.deepcopy(SHOP)
    for t in theirs["tables"].values():
        for m in t["measures"].values():
            m.pop("format_string", None)
    parts = report.definition_parts(theirs, MODEL_ID)["parts"]
    card = next(json.loads(t) for t in parts.values() if '"card"' in t and "Rows in orders" in t)
    assert card["visual"]["objects"]["labels"] == [{"properties": {"labelPrecision": {"expr": {"Literal": {"Value": "0L"}}}}}]
    units = next(json.loads(t) for t in parts.values() if '"card"' in t and "Total quantity" in t)
    assert "objects" not in units["visual"]                                                       # a DOUBLE quantity: not ours to round
    assert all(schema_errors(json.loads(t)) == [] for p, t in parts.items() if not p.startswith("StaticResources/"))


# ------------------------------------------------------------------ 5. theme, title, footnote -----------------------

# The top-level properties of Microsoft's report theme JSON schema (microsoft/powerbi-desktop-samples e2f326b,
# "Report Theme JSON Schema/reportThemeSchema-2.159.json", read 8 November 2026) that the theme uses, and textClasses' four.
THEME_PROPERTIES = {"name", "dataColors", "foreground", "foregroundNeutralSecondary", "background", "backgroundLight", "tableAccent", "textClasses"}
TEXT_CLASSES = {"title", "label", "callout", "header"}


def _lum(hex_):
    c = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_theme_is_registered_and_uses_the_sites_colours_with_enough_contrast():
    parts = report.definition_parts(SHOP, MODEL_ID)["parts"]
    rj = json.loads(parts["definition/report.json"])
    assert rj["themeCollection"] == {"customTheme": {"name": "Krusgraph.json", "type": "RegisteredResources",
                                                     "reportVersionAtImport": {"visual": "2.0.0", "page": "2.0.0", "report": "3.1.0"}}}
    assert rj["resourcePackages"] == [{"name": "RegisteredResources", "type": "RegisteredResources",
                                       "items": [{"name": "Krusgraph.json", "path": "Krusgraph.json", "type": "CustomTheme"}]}]
    theme = json.loads(parts["StaticResources/RegisteredResources/Krusgraph.json"])
    assert set(theme) == THEME_PROPERTIES and set(theme["textClasses"]) == TEXT_CLASSES and theme["name"] == "Krusgraph"
    css = (ROOT / "fabric_backend/static/site.css").read_text()
    root = css[css.index(":root{"):css.index("}", css.index(":root{"))]
    tokens = {m.group(2).upper() for m in re.finditer(r"--([a-z0-9-]+):(#[0-9A-Fa-f]{6})", root)}
    used = {theme["foreground"], theme["foregroundNeutralSecondary"], theme["tableAccent"], *theme["dataColors"]}
    assert {c.upper() for c in used} <= tokens, {c for c in used if c.upper() not in tokens}
    assert _contrast(theme["foreground"], theme["background"]) >= 7 and _contrast(theme["foregroundNeutralSecondary"], theme["background"]) >= 4.5
    assert all(_contrast(c, theme["background"]) >= 3 for c in theme["dataColors"])                # bars against the page (WCAG 1.4.11)
    assert all(tc["fontSize"] >= 12 for tc in theme["textClasses"].values())


def test_the_page_title_and_the_footnote():
    parts = report.definition_parts(SHOP, MODEL_ID, model_name="shop_model", created="8 November 2026")["parts"]
    texts = [json.loads(t)["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"]
             for t in parts.values() if '"textbox"' in t]
    assert texts == ["Overview · shop_model", "8 November 2026. Created by Krusgraph from the checked plan."] or \
        sorted(texts) == sorted(["Overview · shop_model", "8 November 2026. Created by Krusgraph from the checked plan."])
    boxes = _boxes(parts)
    title = min((b for b in boxes if b[0] == "textbox"), key=lambda b: b[2])
    foot = max((b for b in boxes if b[0] == "textbox"), key=lambda b: b[2])
    assert title[2] == INNER[1] and foot[4] == pytest.approx(INNER[3])


# ------------------------------------------------------------------ 6. the Date table and slicers -------------------

def test_the_date_table_is_marked_related_and_spans_the_datas_years():
    cal = SHOP_PARTS["definition/tables/Calendar.tmdl"]
    assert "\tdataCategory: Time" in cal and "column 'Year Month'" in cal and 'FORMAT([Date], "yyyy-mm")' in cal
    assert "DATE(2020, 1, 1), DATE(2030, 12, 31)" in cal                                                # placeholder without rows
    assert "fromColumn: orders.order_date\n\ttoColumn: Calendar.Date" in SHOP_PARTS["definition/relationships.tmdl"]
    d = semantic_model.draft(plan(seed.schema()), {"schema": "shop"}, "shop_model", date_range=("2026-09-01", "2026-10-30"))
    assert "DATE(2026, 1, 1), DATE(2026, 12, 31)" in d["parts"]["definition/tables/Calendar.tmdl"]
    assert d["summary"]["date_table"]["range"].startswith("2026-01-01 to 2026-12-31 (the data's years")
    assert "2026-09-01 to 2026-10-30" in d["parts"]["README.generated.md"] and "placeholder" not in d["parts"]["README.generated.md"].split("## Date table")[1]
    assert semantic_model.related_date_columns(plan(seed.schema())) == [("orders", "order_date")]


def test_slicers_only_when_their_fields_exist():
    slicers = lambda m: [v["fields"] for v in report.visuals(m)["visuals"] if v["type"] == "slicer"]
    assert slicers(SHOP) == [["Calendar[Year Month]"], ["categories[name]"]]
    assert slicers(_without_calendar(SHOP)) == [["categories[name]"]]
    bare = _model(tables={"t": {"columns": {"id": _col("id", key=True)}, "measures": {"Rows in t": {"expression": "COUNTROWS('t')"}}}})
    assert slicers(bare) == []
    doc = next(json.loads(t) for t in report.definition_parts(SHOP, MODEL_ID)["parts"].values() if '"slicer"' in t)
    assert doc["visual"]["objects"]["data"] == [{"properties": {"mode": {"expr": {"Literal": {"Value": "'Dropdown'"}}}}}]


def test_the_month_chart_uses_year_month_so_years_stay_apart():
    v = next(v for v in report.visuals(SHOP)["visuals"] if v["type"] == "clusteredColumnChart")
    assert v["category"] == ("Calendar", "Year Month") and v["title"] == "Units by month"
    older = copy.deepcopy(SHOP)
    older["tables"]["Calendar"]["columns"].pop("Year Month")                                # a model made before n151
    assert next(v for v in report.visuals(older)["visuals"] if v["type"] == "clusteredColumnChart")["category"] == ("Calendar", "Month")


# ------------------------------------------------------------------ create_semantic_model reads two counts ----------

def test_create_semantic_model_reads_the_date_range_and_whole_quantities(shop, monkeypatch):
    def execute(sql):
        if "first_date" in sql:
            return [{"first_date": "2026-09-01", "last_date": "2026-10-30"}]
        if "fractions" in sql:
            return [{"fractions": 0}]
        return []
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: execute)
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop"))
    assert "DATE(2026, 1, 1), DATE(2026, 12, 31)" in out["parts"]["definition/tables/Calendar.tmdl"]
    assert "measure 'Total quantity' = SUM('order_items'[quantity])\n\t\tformatString: #,0\n" in out["parts"]["definition/tables/order_items.tmdl"]
    assert out["read_from_rows"][0].startswith("Dates: 2026-09-01 to 2026-10-30 in orders.order_date")
    assert "whole numbers only" in out["read_from_rows"][1]


def test_create_semantic_model_keeps_the_placeholder_when_the_rows_cannot_be_read(shop, monkeypatch):
    def execute(sql):
        if "first_date" in sql or "fractions" in sql:
            raise RuntimeError("endpoint unavailable")
        return []
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: execute)
    out = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop"))
    assert "DATE(2020, 1, 1), DATE(2030, 12, 31)" in out["parts"]["definition/tables/Calendar.tmdl"]
    assert out["read_from_rows"] == ["Stopped reading (RuntimeError); what was read before is used."]
