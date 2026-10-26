"""The first customer demonstration (two companies, one sales view, an eight-week forecast; brief of 26 October 2026).

The numbers are checked against a second, independent calculation: SQL in SQLite over the same raw sales lines and
registers, written from the definition rather than from planning.py. The forecast is checked on small series whose
right answer is known, and the page is checked for what the brief requires: preview only, the decision handled honestly,
the summary saying no more than the numbers."""
import json
import sqlite3
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from fabric_backend import planning, sales_demo, sales_example, server

DS = sales_demo.dataset()
GROUP_A = ("A-101", "A-102", "A-103")


# ------------------------------------------------------------------ the independent calculation ---------------------

@pytest.fixture(scope="module")
def db():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE a_lines (product_id, quantity, status, delivered_on)")
    con.execute("CREATE TABLE b_lines (artnr, qty, state, ship_date)")
    con.executemany("INSERT INTO a_lines VALUES (?,?,?,?)", [(r["product_id"], r["quantity"], r["status"], r["delivered_on"]) for r in sales_example.lines()["A"]])
    con.executemany("INSERT INTO b_lines VALUES (?,?,?,?)", [(r["artnr"], r["qty"], r["state"], r["ship_date"]) for r in sales_example.lines()["B"]])
    con.execute("CREATE TABLE a_reg (product_id, category, gtin)")
    con.executemany("INSERT INTO a_reg VALUES (?,?,?)", [(r["product_id"], r["category"], r["gtin"]) for r in sales_example.REGISTER_A])
    con.execute("CREATE TABLE b_reg (artnr, ean, valid_to)")
    con.executemany("INSERT INTO b_reg VALUES (?,?,?)", [(r["artnr"], r["ean"], r["valid_to"]) for r in sales_example.REGISTER_B])
    return con


def sql_weekly(con, company: str, decision: str) -> dict[str, int]:
    """Units per week (Monday) for the group, from the definition: counted status only, Company B's products in the group
    through an identical GTIN to one of Company A's lights, or through the decision for B-7003; one register row each."""
    monday = "date({d}, '-' || ((strftime('%w', {d}) + 6) % 7) || ' days')"
    if company == "A":
        q = (f"SELECT {monday.format(d='delivered_on')} AS wk, SUM(quantity) FROM a_lines JOIN a_reg USING (product_id) "
             "WHERE status = 'delivered' AND category = 'Bike lights' GROUP BY wk")
    else:
        extra = "OR l.artnr = 'B-7003'" if decision in GROUP_A else ""
        q = (f"SELECT {monday.format(d='l.ship_date')} AS wk, SUM(l.qty) FROM b_lines l "
             "WHERE l.state = 'SHIPPED' AND (l.artnr IN (SELECT b.artnr FROM b_reg b JOIN a_reg a ON a.gtin = b.ean "
             f"WHERE b.valid_to = '' AND a.category = 'Bike lights') {extra}) GROUP BY wk")
    return {wk: n for wk, n in con.execute(q)}


@pytest.mark.parametrize("decision", ["open", "A-103", "A-101", "none"])
@pytest.mark.parametrize("company", ["all", "A", "B"])
@pytest.mark.parametrize("weeks", [13, 26, 52, 104])
def test_every_weekly_number_matches_an_independent_sql_calculation(db, decision, company, weeks):
    r = planning.result(DS, {} if decision == "open" else {"B-7003": decision}, company, weeks)
    want = {c: sql_weekly(db, c, decision) for c in ("A", "B")}
    first = {c: date.fromisoformat(r["history"][c]["first_week"]) for c in r["history"]}
    assert len(r["rows"]) == weeks
    for row in r["rows"]:
        wk = date.fromisoformat(row["week"])
        total = 0
        for c in r["companies"]:
            expect = want[c].get(row["week"], 0) if wk >= first[c] else None             # no data yet is not zero
            assert row[c] == expect, (row["week"], c)
            total += expect or 0
        assert row["total"] == total
    assert r["period"]["total"] == sum(x["total"] for x in r["rows"])               # combined = the companies added up


def test_the_open_product_stays_out_until_decided_and_then_counts_once(db):
    open_ = planning.result(DS, {}, "all", 26)
    linked = planning.result(DS, {"B-7003": "A-103"}, "all", 26)
    elsewhere = planning.result(DS, {"B-7003": "A-101"}, "all", 26)
    not_light = planning.result(DS, {"B-7003": "none"}, "all", 26)
    shown = {r["week"] for r in open_["rows"]}
    b7003 = sum(q["qty"] for q in sales_example.lines()["B"] if q["artnr"] == "B-7003" and q["state"] == "SHIPPED"
                and planning.week_of(date.fromisoformat(q["ship_date"])).isoformat() in shown)
    assert [o["product"] for o in open_["open"]] == ["B-7003"] and open_["open"][0]["units_in_period"] == b7003
    assert linked["period"]["total"] - open_["period"]["total"] == b7003 == elsewhere["period"]["total"] - open_["period"]["total"]
    assert not linked["open"] and not not_light["open"] and not_light["period"]["total"] == open_["period"]["total"]
    by = lambda r, t: sum(p["units"] for p in r["products"] if p["company"] == "B" and p["product"] == t)  # noqa: E731
    assert by(linked, "A-103") == b7003 and by(elsewhere, "A-103") == 0 and by(elsewhere, "A-101") - by(linked, "A-101") == b7003
    # the open product has 20 weeks of sales: no forecast for it, and a reason instead
    assert open_["open"][0]["weeks_sold"] == 20 and open_["open"][0]["forecast"] is None
    assert "20 weeks of history" in open_["open"][0]["no_forecast_because"]
    # the link shows its evidence and says it is a suggestion, not a proven identity
    item = next(l for l in open_["links"] if l["product"] == "B-7003")
    assert item["status"] == "open" and item["suggested"] == "A-103" and any("supplier article" in e for e in item["evidence"])
    assert any("no GTIN" in e for e in item["evidence"])


def test_the_renamed_product_would_be_counted_twice_by_a_join_on_every_row(db):
    naive = db.execute("SELECT SUM(l.qty) FROM b_lines l JOIN b_reg b ON b.artnr = l.artnr "
                       "WHERE l.state = 'SHIPPED' AND l.artnr = 'B-7002'").fetchone()[0]
    once = db.execute("SELECT SUM(qty) FROM b_lines WHERE state = 'SHIPPED' AND artnr = 'B-7002'").fetchone()[0]
    r = planning.result(DS, {}, "all", 26)
    check = next(c for c in r["checks"] if "counted once" in c["name"])
    assert naive - once == once > 0 and f"{once:,}".replace(",", " ") in check["result"]


def test_cancelled_lines_are_left_out_and_counted(db):
    r = planning.result(DS, {}, "all", 26)
    a = db.execute("SELECT COUNT(*), SUM(quantity) FROM a_lines WHERE status != 'delivered'").fetchone()
    assert any(f"{a[0]} cancelled lines ({a[1]} units)" in c["result"] for c in r["checks"])


# ------------------------------------------------------------------ the forecast on series with a known answer -------

def _weeks(n):
    return [date(2024, 1, 1) + timedelta(weeks=i) for i in range(n)]


def test_a_pure_repeating_season_is_forecast_by_repeating_last_year():
    season = [100 + 50 * (i % 52 < 26) for i in range(52)]
    series = season * 2
    f = planning.forecast(series, _weeks(len(series))[-1])
    assert f["available"] and f["method"] == "last_year" and f["elaborate_lost"]
    assert [p["forecast"] for p in f["points"]] == series[-52:][:8]
    assert next(m for m in f["methods"] if m["id"] == "last_year")["error_pct"] == 0.0


def test_growth_on_a_season_is_better_met_by_last_years_pattern_at_this_years_level():
    series = [round((100 + 60 * __import__("math").cos(i / 52 * 6.283)) * 1.004 ** i) for i in range(110)]
    f = planning.forecast(series, _weeks(110)[-1])
    errors = {m["id"]: m["error_pct"] for m in f["methods"]}
    assert f["method"] == min(errors, key=errors.get) == "seasonal_level" and not f["elaborate_lost"]
    assert f["total_low"] <= f["total_high"] and all(p["low"] <= p["high"] for p in f["points"])


def test_too_little_history_gives_no_forecast_and_says_why():
    f = planning.forecast([10] * 74, date(2026, 10, 19))
    assert not f["available"] and f["weeks_needed"] == 75 and "74 weeks of history" in f["reason"]
    assert planning.forecast([10] * 75, date(2026, 10, 19))["available"]


def test_the_method_used_is_the_one_with_the_smallest_test_error_on_the_example():
    for company in ("all", "A", "B"):
        f = planning.result(DS, {}, company, 26)["forecast"]
        assert f["available"]
        used = next(m for m in f["methods"] if m["used"])
        assert used["error_pct"] == min(m["error_pct"] for m in f["methods"]) and used["id"] == f["method"]
        assert f["elaborate_lost"] == (f["method"] != "seasonal_level")


# ------------------------------------------------------------------ what the summary may say ---------------------------

def test_the_summary_says_what_the_numbers_say_and_nothing_more():
    for decisions in ({}, {"B-7003": "A-103"}):
        r = planning.result(DS, decisions, "all", 26)
        text = " ".join(r["summary"]).lower()
        assert f"{r['period']['total']:,}".replace(",", " ") in " ".join(r["summary"])
        f = r["forecast"]
        assert f"{f['total_low']:,}".replace(",", " ") in " ".join(r["summary"]) and f"{f['tests']} past tests" in text
        assert "not demand" in text and "does not say why" in text
        for banned in ("should buy", "recommend", "order more", "because of", "guarantee", "will sell", "demand will"):
            assert banned not in text, banned
        assert ("not decided" in text) == bool(r["open"])


def test_the_same_choices_give_the_same_result_and_other_choices_another_id():
    a = sales_demo.result_json({"B-7003": "A-103"}, "all", 26)
    sales_demo._result.cache_clear()
    assert sales_demo.result_json({"B-7003": "A-103"}, "all", 26) == a
    ids = {json.loads(sales_demo.result_json(d, c, w))["result_id"]
           for d in ({}, {"B-7003": "A-103"}) for c in ("all", "B") for w in (26, 52)}
    assert len(ids) == 8


def test_choices_the_example_does_not_offer_are_refused():
    for args in (({"B-7003": "A-201"}, "all", 26), ({"B-7001": "A-101"}, "all", 26), ({}, "C", 26), ({}, "all", 30)):
        with pytest.raises(planning.PlanningInputError):
            planning.result(DS, *args)


def test_the_example_data_is_invented_and_says_so():
    assert all(r["gtin"].startswith("2") for r in sales_example.REGISTER_A)                     # GS1 in-house range
    assert all(r["ean"] == "" or r["ean"].startswith("2") for r in sales_example.REGISTER_B)
    assert {c["name"] for c in sales_example.COMPANIES.values()} == {"Company A", "Company B"}


# ------------------------------------------------------------------ the page: a preview, not published -------------

@pytest.fixture
def site(monkeypatch):
    def make(preview: bool):
        monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
        monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
        monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
        if preview:
            monkeypatch.setenv("KRUSGRAPH_PREVIEW", "1")
        else:
            monkeypatch.delenv("KRUSGRAPH_PREVIEW", raising=False)
        return TestClient(server.build_app())
    return make


def test_without_the_preview_flag_the_example_is_not_served(site):
    with site(False) as c:
        assert c.get(sales_demo.PATH).status_code == 404 and c.get(sales_demo.PATH + "/result.json").status_code == 404


def test_with_the_flag_it_is_a_noindex_page_outside_the_sitemap_and_the_navigation(site):
    with site(True) as c:
        r = c.get(sales_demo.PATH)
        assert r.status_code == 200 and r.headers["x-robots-tag"] == "noindex, nofollow"
        assert '<meta name="robots" content="noindex,nofollow">' in r.text and 'rel="canonical"' not in r.text
        assert "synthetic data" in r.text and "invented example" in r.text and "What is real here" in r.text
        assert "/example/" not in c.get("/sitemap.xml").text and "Disallow: /example/" in c.get("/robots.txt").text
        for page in ("/", "/docs", "/use-cases", "/partners", "/start"):
            assert "/example/sales-planning" not in c.get(page).text, page


def test_a_saved_link_opens_with_its_own_choices(site):
    with site(True) as c:
        html = c.get(sales_demo.PATH + "?d=B-7003:A-103&company=B&weeks=13").text
        data = json.loads(html.split('<script type="application/json" id="sp-data">')[1].split("</script>")[0])
        assert data["state"] == {"decisions": {"B-7003": "A-103"}, "company": "B", "weeks": 13}
        assert data == json.loads(c.get(sales_demo.PATH + "/result.json?d=B-7003:A-103&company=B&weeks=13").text)
        bad = c.get(sales_demo.PATH + "/result.json?company=Z")
        assert bad.status_code == 400 and bad.json()["kind"] == "bad_input"
        start = json.loads(c.get(sales_demo.PATH + "?company=Z").text.split('id="sp-data">')[1].split("</script>")[0])
        assert start["state"] == {"decisions": {}, "company": "all", "weeks": 26}                # a broken link starts over
