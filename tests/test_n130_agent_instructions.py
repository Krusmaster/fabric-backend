"""Round n130: the data agent's instructions from the ontology names and the checked plan (fabric_backend/agent_context.py,
create_data_agent's draft and dry run). Deterministic, only counted joins are called safe, the repeated amounts are named,
the documented size limits hold (and what was cut is said), and no row value reaches the text."""
import json
import re

import golden_support as gs
from fabric_backend import agent_context, amounts, data_agent, evidence, seed, server
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table
from test_creating_tools import INFO, holds, runnable, shop  # noqa: F401 - the fixture is used by name

SHIP_TO = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]


def shop_rows():
    db = gs.shop_database()

    def execute(sql):
        cur = db.execute(gs._sqlite(sql))
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    return execute


def schema_of(tables: dict[str, str], name: str = "dbo") -> Schema:
    s = Schema(schema=name)
    for t, cols in tables.items():
        s.tables[t] = Table(t, [Column(c.split()[0], c.split()[1].lower()) for c in cols.split(", ")], schema=name)
    return s


def joins_in(sql: str) -> set[tuple[str, str]]:
    """(table, table) for every JOIN ... ON a.x = b.y in a drafted query, by alias."""
    alias = dict((a, t) for t, a in re.findall(r"\[\w+\]\.\[(\w+)\] AS (t\d+)", sql))
    return {(alias[a], alias[b]) for a, b in re.findall(r"ON (t\d+)\.\[\w+\] = (t\d+)\.\[\w+\]", sql)}


# ------------------------------------------------------------------ determinism --------------

def test_the_same_plan_gives_the_same_agent_every_time():
    p = plan(seed.schema("shop"), confirmed=SHIP_TO)
    v = evidence.validate(p, shop_rows(), max_items=200)
    first = agent_context.build(p, "shop_lh", "shop", validation=v)
    for _ in range(3):
        again = plan(seed.schema("shop"), confirmed=SHIP_TO)
        assert agent_context.build(again, "shop_lh", "shop", validation=evidence.validate(again, shop_rows(), max_items=200)) == first
    assert json.dumps(first, sort_keys=True) == json.dumps(agent_context.build(p, "shop_lh", "shop", validation=v), sort_keys=True)


# ------------------------------------------------------------------ only checked joins are safe -

def test_without_counts_no_join_is_called_safe_and_the_examples_use_one_table():
    p = plan(seed.schema("shop"), confirmed=SHIP_TO)         # a confirmed join is still not counted
    out = agent_context.build(p, "shop_lh", "shop")
    assert out["context"]["safe_joins"] == [] and out["context"]["safe_paths"] == []
    assert len(out["context"]["not_safe_joins"]) == len(p.relationships)
    assert "## Safe joins (checked, many-to-one)\n- None. Nothing was counted: run create_data_agent with validate=true." in out["datasource_instructions"]
    assert "confirmed by you; not counted" in out["datasource_instructions"]
    assert 3 <= len(out["fewshots"]) <= 5 and all("JOIN" not in f["query"] for f in out["fewshots"])
    assert all(f["query"].startswith("-- One table, no join.\n") for f in out["fewshots"])


def test_only_joins_that_held_when_counted_are_safe():
    p = plan(seed.schema("shop"))
    v = holds(p)
    by = {(r["source"], r["target"]): r for r in v["relationships"]}
    by[("order_items", "products")]["verdict"] = "3 of 134 rows with a value have no match (orphans)"
    by[("addresses", "customers")]["verdict"] = "holds for all 17 rows with a value; but the target key of customers is not unique, so a row can match more than one"
    v["relationships"].remove(by[("audit_log", "customers")])                 # not counted: max_items used up
    out = agent_context.build(p, "shop_lh", "shop", validation=v)
    safe = {(e["source"], e["target"]) for e in out["context"]["safe_joins"]}
    assert safe == {("products", "categories"), ("orders", "customers"), ("order_items", "orders")}
    why = {(e["source"], e["target"]): e["why"] for e in out["context"]["not_safe_joins"]}
    assert "orphans" in why[("order_items", "products")] and "inner join drops those rows" in why[("order_items", "products")]
    assert "not unique" in why[("addresses", "customers")] and "a join repeats rows" in why[("addresses", "customers")]
    assert "not counted (validate_plan's max_items was used up)" in why[("audit_log", "customers")]
    for f in out["fewshots"]:                                                 # every join in every example is a safe one
        assert joins_in(f["query"]) <= safe, f
    assert out["context"]["safe_paths"] == [["order_items", "orders", "customers"]]
    assert not any("categor" in f["question"] and "order items" in f["question"] for f in out["fewshots"])  # via the orphan join
    runnable(out["fewshots"])


def test_the_counted_shop_gets_safe_paths_and_examples_from_answer_query_draft():
    from fabric_backend import answers
    p = plan(seed.schema("shop"))
    out = agent_context.build(p, "shop_lh", "shop", validation=evidence.validate(p, shop_rows(), max_items=200))
    assert len(out["context"]["safe_joins"]) == len(p.relationships)
    assert out["context"]["safe_paths"] == [["order_items", "orders", "customers"], ["order_items", "products", "categories"]]
    assert 3 <= len(out["fewshots"]) <= 5
    for f in out["fewshots"]:
        comment, sql = f["query"].split("\n", 1)
        assert comment.startswith("-- Safe many-to-one join(s): ") and "checked" in comment
        tables = sorted({t for pair in joins_in(sql) for t in pair})
        assert sql == answers.draft(p, f["question"], [t for t in re.findall(r"\[shop\]\.\[(\w+)\]", sql)])["tsql"], f
        assert tables
    assert "OrderItemsHasOrders" in out["datasource_instructions"]          # the ontology's relationship name


# ------------------------------------------------------------------ amounts --------------------

def test_header_amounts_and_flat_table_amounts_are_named_not_to_be_summed():
    s = schema_of({"orders": "order_id INT, order_date DATE, order_amount DECIMAL",
                   "order_lines": "order_id INT, line_no INT, line_amount DECIMAL",
                   "invoice_rows": "invoice_id INT, row_no INT, invoice_total DECIMAL, row_amount DECIMAL"})
    p = plan(s)
    out = agent_context.build(p, "lh", "dbo")
    assert "Never SUM(orders.order_amount) over order_lines rows: sum it on orders first" in out["datasource_instructions"]
    assert "never SUM(orders.order_amount) over order_lines rows" in out["instructions"]
    v = holds(p)
    v["amount_levels"] = amounts.check(p)
    v["amount_levels"]["flat_tables"] = [{"table": "invoice_rows", "header_column": "invoice_id", "amount_column": "invoice_total",
                                          "pattern": True}]
    out = agent_context.build(p, "lh", "dbo", validation=v)
    named = {(a["table"], a["column"]) for a in out["context"]["repeated_amounts"]}
    assert named == {("orders", "order_amount"), ("invoice_rows", "invoice_total")}
    assert "invoice_rows.invoice_total repeats the same value on every row of one invoice_id. Never SUM it" in out["datasource_instructions"]
    assert "never SUM(invoice_rows.invoice_total) over invoice_rows rows" in out["instructions"]
    for f in out["fewshots"]:                                    # no example sums a repeated amount over the lines
        assert "SUM(t1.[order_amount])" not in f["query"] and "[invoice_total])" not in f["query"]


def test_a_price_on_the_header_is_named_with_what_to_do_instead():
    out = agent_context.build(plan(seed.schema("shop")), "shop_lh", "shop")
    assert ("Never SUM(products.list_price) over order_items rows: it is a price, so multiply it by the quantity on each "
            "order_items row") in out["datasource_instructions"]


# ------------------------------------------------------------------ size limits ----------------

def test_the_documented_limits_are_the_ones_in_the_docs():
    assert agent_context.MAX_INSTRUCTIONS == 15_000 and agent_context.MAX_EXAMPLES <= agent_context.MAX_EXAMPLES_DOCUMENTED == 100
    assert agent_context.LIMITS["instructions"]["source"].endswith("ms.date 05/20/2026")
    assert "no number in the documentation" in agent_context.LIMITS["datasource_instructions"]["source"]


def test_a_large_schema_stays_inside_the_limits_and_says_what_was_cut():
    import itertools
    words = ("north", "south", "east", "west", "inner", "outer", "upper", "lower", "early", "late", "small", "large")
    tables = {"customers": "customer_id INT, " + ", ".join(f"customer_attribute_{w} STRING" for w in words)}
    for a, b in itertools.islice(itertools.product(words, ("sales", "returns", "shipments", "visits", "claims", "quotes",
                                                           "invoices", "payments", "bookings", "refunds", "orders", "tickets")), 150):
        tables[f"{a}_{b}"] = f"{a}_{b}_id INT, customer_id INT, " + ", ".join(f"{w}_amount DECIMAL" for w in words)
    p = plan(schema_of(tables))
    out = agent_context.build(p, "lh", "dbo", validation=holds(p))
    sizes = out["context"]["sizes"]
    assert sizes["instructions"] == len(out["instructions"]) <= 15_000
    assert sizes["datasource_instructions"] == len(out["datasource_instructions"]) <= 15_000
    assert sizes["datasource_description"] <= 1_000 and 3 <= sizes["examples"] <= 5
    cut = {(c["part"], c["what"]): c["left_out"] for c in out["context"]["cut"]}
    assert cut[("datasource_instructions", "column lists in the table descriptions")] == len(tables)
    assert any(part == "datasource_description" for part, _ in cut)
    assert "## Safe joins (checked, many-to-one)" in out["datasource_instructions"]
    assert agent_context.build(p, "lh", "dbo", validation=holds(p)) == out


def test_the_shop_needs_no_cut():
    p = plan(seed.schema("shop"))
    out = agent_context.build(p, "shop_lh", "shop", validation=evidence.validate(p, shop_rows(), max_items=200))
    assert out["context"]["cut"] == [] and out["context"]["sizes"]["instructions"] < 15_000


# ------------------------------------------------------------------ no row values ---------------

def test_no_row_value_reaches_the_agent():
    p = plan(seed.schema("shop"))
    out = agent_context.build(p, "shop_lh", "shop", validation=evidence.validate(p, shop_rows(), max_items=200))
    text = json.dumps({k: out[k] for k in ("instructions", "datasource_instructions", "datasource_description", "fewshots")})
    rows = seed.rows()
    values = {str(v) for table in rows.values() for row in table for v in row
              if isinstance(v, str) and len(str(v)) > 3}
    leaked = sorted(v for v in values if v in text and v not in {t.name for t in p.schema} | {c for t in p.schema for c in t.column_names})
    assert leaked == []


# ------------------------------------------------------------------ the tool -------------------

def test_the_dry_run_shows_context_sizes_and_limits_and_validate_counts(shop, monkeypatch):
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop"))
    assert set(out["agent"]) >= {"instructions", "datasource_instructions", "datasource_description", "fewshots"}
    ctx = out["context"]
    assert ctx["validated"] is False and ctx["limits"]["instructions"]["max_chars"] == 15_000 and ctx["cut"] == []
    seen = []
    monkeypatch.setattr(server._evidence, "validate", lambda p, execute, max_items=60: seen.append(max_items) or holds(p))
    out = json.loads(server.create_data_agent(*shop, name="shop_agent", schema="shop", validate=True))
    assert seen == [200] and out["context"]["validated"] is True and out["dry_run"] is True
    assert any("JOIN" in f["query"] for f in out["agent"]["fewshots"])
