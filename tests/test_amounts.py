"""The total that doubles (fabric_backend/amounts.py): an amount on a header table summed over its line rows.

The synthetic example is fabric_backend.seed.AMOUNT_DEMO: one order of 1 000 with two lines (600 and 400). Summed over
the joined lines the order comes out at 2 000; summed once per order, 1 000. Every check here runs on SQLite."""
import sqlite3

from fabric_backend import amounts, answers, evidence, gold, seed, semantic_model
from fabric_backend.demo_app import Session
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan
from fabric_backend.platforms.local import sample_source
from fabric_backend.schema import Column, Schema, Table


def demo_schema(with_lines: bool = True) -> Schema:
    s = Schema(schema="demo")
    for name, (ddl, _) in seed.AMOUNT_DEMO.items():
        if name == "order_lines" and not with_lines:
            continue
        s.tables[name] = Table(name, [Column(c.split()[0], c.split()[1].lower()) for c in ddl.split(", ")], schema="demo")
    return s


def demo_execute():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS demo")
    for name, (ddl, data) in seed.AMOUNT_DEMO.items():
        con.execute(f"CREATE TABLE demo.[{name}] ({ddl})")
        con.executemany(f"INSERT INTO demo.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)

    def execute(sql):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return execute


def test_the_header_amount_is_found_from_names_with_the_rule_and_unknown_rows_per_header():
    out = amounts.check(plan(demo_schema()))
    [f] = out["findings"]
    assert (f["header"], f["line"], f["amount_columns"], f["rule"]) == ("orders", "order_lines", ["order_amount"], "R1")
    assert f["rows_per_header"] == "unknown" and "unknown until the data is counted" in f["explanation"]
    assert "order amount and line amount are different levels" in f["explanation"]
    assert "unknown" in out["summary"]


def test_with_rows_the_lines_per_header_are_counted():
    [f] = amounts.check(plan(demo_schema()), demo_execute())["findings"]
    assert f["rows_per_header"] == {"headers": 1, "avg_lines": 2.0, "max_lines": 2}
    assert "2 rows for each row of orders" in f["explanation"] and "about 2 times too large" in f["explanation"]


def test_before_2000_after_1000():
    d = amounts.demo()
    assert (d["before"], d["after"], d["lines_total"]) == (2000.0, 1000.0, 1000.0)
    assert d["explanation"] == "order amount and line amount are different levels"


def test_validate_plan_gets_a_section_and_keeps_its_fields():
    out = evidence.validate(plan(demo_schema()), demo_execute())
    assert {"summary", "keys", "relationships", "note"} <= set(out)
    assert out["amount_levels"]["findings"][0]["rows_per_header"]["max_lines"] == 2


def test_names_that_read_as_amounts_and_names_that_do_not():
    for name in ("order_amount", "TotalDue", "SubTotal", "Freight", "belopp", "OrderVärde", "netto_sek", "Summa", "line_total"):
        assert amounts.looks_like_amount(name, "decimal(18,2)"), name
    for name in ("amount_id", "line_no", "StatusCode", "tax_rate", "Quantity", "order_date", "price_type"):
        assert not amounts.looks_like_amount(name, "decimal"), name
    assert not amounts.looks_like_amount("order_amount", "nvarchar")


def test_the_shop_has_no_header_amount_and_a_one_to_one_link_is_not_a_header():
    assert amounts.check(seed.schema() and plan(seed.schema()))["findings"] == []
    s = Schema(schema="x")
    s.tables["orders"] = Table("orders", [Column("order_id", "int"), Column("order_amount", "decimal")], schema="x")
    s.tables["order_extras"] = Table("order_extras", [Column("order_id", "int"), Column("note", "string")], schema="x")
    p = plan(s, keys={"order_extras": ["order_id"]}, confirmed=[{"source": "order_extras", "source_cols": ["order_id"], "target": "orders", "target_cols": ["order_id"]}])
    assert amounts.header_amounts(p) == []


def test_semantic_model_does_not_sum_the_header_amount_and_puts_a_measure_on_the_header():
    info = {"schema": "demo"}
    with_lines = semantic_model.draft(plan(demo_schema()), info)
    alone = semantic_model.draft(plan(demo_schema(with_lines=False)), info)

    def summarize(d):
        tmdl = d["parts"]["definition/tables/orders.tmdl"]
        block = tmdl.split("column order_amount", 1)[1].split("annotation", 1)[0]
        return block.split("summarizeBy: ", 1)[1].split()[0]
    assert summarize(alone) == "sum"                                   # no line table: the amount is summed as before
    assert summarize(with_lines) == "none"                             # with order_lines: not summed by default
    tmdl = with_lines["parts"]["definition/tables/orders.tmdl"]
    assert "/// An amount at the level of orders" in tmdl and "measure 'Total order_amount' = SUM('orders'[order_amount])" in tmdl
    assert with_lines["summary"]["header_amounts"] == [{"table": "orders", "column": "order_amount", "lines": ["order_lines"], "summarize_by": "none"}]
    assert "## Amounts at header level" in with_lines["parts"]["README.generated.md"]


def test_answer_query_sums_the_order_amount_once_per_order():
    p = plan(demo_schema())
    execute = demo_execute()
    ans = answers.tsql(p, "total order_amount", ["orders", "order_lines"])
    assert execute(ans["sql"])[0]["total_order_amount"] == 1000.0
    naive = "SELECT SUM(h.[order_amount]) AS t FROM [demo].[order_lines] AS l JOIN [demo].[orders] AS h ON l.[order_id] = h.[order_id]"
    assert execute(naive)[0]["t"] == 2000.0
    assert any("different levels" in a for a in ans["assumptions"])
    lines = answers.tsql(p, "total line_amount", ["order_lines"])
    assert execute(lines["sql"])[0]["total_line_amount"] == 1000.0 and "DISTINCT" not in lines["sql"]


def test_gold_view_at_line_level_leaves_the_order_amount_out():
    info = dict(workspace_id="ws", item_id="lh", item_name="lh", item_kind="Lakehouse", schema="demo", schemas_enabled=True)
    s = gold.spec(plan(demo_schema()), info)
    lines_view = next(v for v in s["views"] if v["fact"] == "order_lines")
    assert "orders_order_amount" not in [c["as"] for c in lines_view["columns"]]
    assert s["header_amounts_left_out"][0]["column"] == "order_amount"
    assert "different levels" in s["header_amounts_left_out"][0]["why"]


def test_the_demo_health_check_shows_the_example_as_a_finding_of_its_own():
    st = Session(sample_source()).state()
    f = next(x for x in st["health"]["findings"] if x["id"] == "amt:demo")
    assert "1 000" in f["saw"] and "2 000" in f["saw"] and "order amount and line amount are different levels" in f["title"].lower()
    assert f["kind"] == "amount_level" and not f["can_accept"]
    assert st["plan"]["summary"].startswith("7 tables")                # the example is not part of the shop's map



def test_the_problem_card_on_use_cases(monkeypatch):
    from starlette.testclient import TestClient

    from fabric_backend import server
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        page, md = c.get("/use-cases").text, c.get("/use-cases.md").text
    for text in (page, md):
        for part in ("The total that doubles", "Why is our order total twice what finance says?", "Why it matters.",
                     "shows it.", "What we do not know.", "different levels", "1 000 with two lines"):
            assert part in text, part
    assert 'href="/local#the-20-minute-demo"' in page and "/local" in md
