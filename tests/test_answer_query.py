"""answer_query_draft and query_graphql(question=...): what is read from Swedish and English questions, the T-SQL run on
the shop seed in SQLite (and checked against the same numbers computed in Python), the GraphQL validated against a
schema built from the API's own definition (types, fields, relationships, groupBy and aggregations as Fabric's docs
describe them), and how many characters an agent reads with and without the suggestion."""
import datetime
import json
import re
import sqlite3
from collections import Counter

import pytest
import requests
from graphql import build_schema, parse, validate

from fabric_backend import answers, seed, server
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import PlanInputError, plan
from fabric_backend.schema import Schema

WS = "11111111-1111-1111-1111-111111111111"
SHIP_TO = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]


def shop_plan(confirmed=None):
    return plan(seed.schema("shop"), None, confirmed)


def description(p=None):
    return server.describe_definition(decode(definition(p or shop_plan(), "shop_api", WS, "ep-1", "SqlAnalyticsEndpoint")))


def sdl(desc: dict) -> str:
    """A GraphQL schema with the shape Fabric generates for an API for GraphQL (fabric-docs api-graphql-aggregations.md:
    <type>Result with items and groupBy(fields: [<type>ScalarFields!]), aggregations count/sum/avg/min/max(field:)),
    relationships as an object (ManyToOne) or a connection with items (OneToMany). Scalars are String: only names are
    checked here, not values."""
    by_source = {t["source"]: t for t in desc["types"]}
    out = ["enum SortOrder { ASC DESC }", "type Query {"]
    out += [f"  {t['query_field']}(first: Int, after: String, filter: {t['type']}Filter, orderBy: {t['type']}OrderBy): {t['type']}Result!" for t in desc["types"]]
    out.append("}")
    for t in desc["types"]:
        n = t["type"]
        fields = [f"  {f}: String" for f in t["fields"]]
        for r in t["relationships"]:
            target = by_source[r["to"]]["type"]
            fields.append(f"  {r['field']}: {target}" if r["cardinality"] == "ManyToOne" else f"  {r['field']}(first: Int): {target}Result!")
        out += [f"type {n} {{", *fields, "}"]
        out += [f"enum {n}ScalarFields {{ {' '.join(t['fields'])} }}",
                f"input {n}Filter {{ {' '.join(f + ': String' for f in t['fields'])} }}",
                f"input {n}OrderBy {{ {' '.join(f + ': SortOrder' for f in t['fields'])} }}",
                f"type {n}Fields {{ {' '.join(f + ': String' for f in t['fields'])} }}",
                f"type {n}Aggregations {{ " + " ".join(f"{a}(field: {n}ScalarFields!, distinct: Boolean): Float" for a in ("count", "sum", "avg", "min", "max")) + " }",
                f"type {n}GroupBy {{ fields: {n}Fields aggregations: {n}Aggregations }}",
                f"type {n}Result {{ items: [{n}!]! endCursor: String hasNextPage: Boolean! groupBy(fields: [{n}ScalarFields!]): [{n}GroupBy!]! }}"]
    return "\n".join(out)


def sqlite_with_seed():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")                 # so [shop].[orders] means what it means on the endpoint
    for name, ddl in seed.SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in seed.rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    return con


def run_tsql(con, sql: str):
    """The few T-SQL words SQLite spells differently: TOP (n) -> LIMIT n, COUNT_BIG -> COUNT, float -> REAL."""
    top = re.match(r"SELECT TOP \((\d+)\) ", sql)
    if top:
        sql = "SELECT " + sql[top.end():] + f"\nLIMIT {top.group(1)}"
    return con.execute(sql.replace("COUNT_BIG(", "COUNT(").replace("AS float)", "AS REAL)")).fetchall()


QUESTIONS = [
    ("How many orders per customer?", ["orders", "customers"], {"aggregate": "count", "counted": "orders", "group_table": "customers"}),
    ("Hur många ordrar per kund?", ["orders", "customers"], {"aggregate": "count", "counted": "orders", "group_table": "customers"}),
    ("Vilka 5 kunder har flest ordrar?", ["customers", "orders"], {"aggregate": "count", "top": 5, "group_table": "customers"}),
    ("Total quantity per category", ["order_items", "categories"], {"aggregate": "sum", "group_table": "categories", "measure": ["order_items", "quantity"]}),
    ("Antal kunder per land", ["customers"], {"aggregate": "count", "group_column": ["customers", "country"]}),
    ("De 10 senaste ordrarna med kund", ["orders", "customers"], {"aggregate": None, "top": 10, "latest": True}),
    ("Show order lines with product and category", ["order_items", "products", "categories"], {"aggregate": None, "top": None}),
    ("Average quantity per product", ["order_items", "products"], {"aggregate": "avg", "group_table": "products"}),
    ("How many orders per order date", ["orders"], {"aggregate": "count", "group_column": ["orders", "order_date"], "group_table": None}),
    ("How many order lines per order", ["order_items", "orders"], {"counted": "order_items", "group_table": "orders"}),
    ("Beräkna summan av quantity per produkt", ["order_items", "products"], {"aggregate": "sum", "measure": ["order_items", "quantity"]}),
    ("Beräkna genomsnittlig quantity per produkt", ["order_items", "products"], {"aggregate": "avg"}),
    ("Total quantity per customer over the 12 months", ["order_items", "customers"], {"aggregate": "sum", "top": None, "not_used": ["12"]}),
    ("Antal ordrar per kund efter 2024", ["orders", "customers"], {"aggregate": "count", "not_used": ["2024"]}),
    ("Customers per country", ["customers"], {"aggregate": "count", "count_assumed": True, "group_column": ["customers", "country"]}),
]


@pytest.mark.parametrize("question,tables,expect", QUESTIONS)
def test_what_is_read_from_the_question(question, tables, expect):
    u = answers.understand(question, shop_plan(), tables)
    for k, v in expect.items():
        assert u[k] == v, (k, u)


@pytest.mark.parametrize("question,tables,expect", QUESTIONS)
def test_the_tsql_runs_on_the_seed_and_the_graphql_validates_against_the_api(question, tables, expect):
    p = shop_plan()
    out = answers.draft(p, question, tables, description(p), "shop_api")
    rows = run_tsql(sqlite_with_seed(), out["tsql"])
    assert rows, out["tsql"]
    for step in out["path"]:
        assert step["rule"] in ("R1", "R2", "R3", "R4", "R0", "confirmed") and 0 < step["certainty"] <= 1 and step["on"]
    g = out["graphql"]
    if "query" in g:
        errors = validate(build_schema(sdl(description(p))), parse(g["query"]))
        assert not errors, (g["query"], errors)
    else:
        assert "T-SQL" in g["not_possible"]
    assert out["runs"].startswith("nothing")


def test_the_numbers_are_right():
    con, p, rows = sqlite_with_seed(), shop_plan(), seed.rows()
    per_customer = Counter(o[1] for o in rows["orders"])
    got = run_tsql(con, answers.draft(p, "How many orders per customer?", ["orders", "customers"], show_personal_data=True)["tsql"])
    assert {r[0]: r[2] for r in got} == dict(per_customer) and [r[2] for r in got] == sorted(per_customer.values(), reverse=True)
    top5 = run_tsql(con, answers.draft(p, "Vilka 5 kunder har flest ordrar?", ["customers", "orders"], show_personal_data=True)["tsql"])
    assert len(top5) == 5 and top5[0][2] == max(per_customer.values())
    category = {pr[0]: pr[2] for pr in rows["products"]}
    per_category = Counter()
    for item in rows["order_items"]:
        per_category[category[item[2]]] += item[3]
    got = run_tsql(con, answers.draft(p, "Total quantity per category", ["order_items", "categories"])["tsql"])
    assert {r[0]: r[2] for r in got} == dict(per_category)
    by_country = Counter(c[2] for c in rows["customers"])
    got = run_tsql(con, answers.draft(p, "Antal kunder per land", ["customers"])["tsql"])
    assert {r[0]: r[1] for r in got} == dict(by_country)
    latest = run_tsql(con, answers.draft(p, "De 10 senaste ordrarna med kund", ["orders", "customers"], show_personal_data=True)["tsql"])
    assert [r[2] for r in latest] == sorted((o[2].isoformat() for o in rows["orders"]), reverse=True)[:10]


def test_the_path_is_the_safest_and_says_why():
    p = shop_plan(SHIP_TO)
    out = answers.draft(p, "Orders with the city they ship to", ["orders", "addresses"], show_personal_data=True)
    assert [(s["from"], s["to"], s["rule"], s["direction"]) for s in out["path"]] == [("orders", "addresses", "confirmed", "many-to-one")]
    assert "t1.[city] AS [addresses_city]" in out["tsql"] and out["assumptions"] == ["no number of rows asked for: the first 100"]
    fan = answers.draft(shop_plan(), "Orders with the customer's city", ["orders", "addresses"])
    assert [s["direction"] for s in fan["path"]] == ["many-to-one", "one-to-many"]
    assert any("one-to-many (customers -> addresses)" in a for a in fan["assumptions"])


def test_graphql_explains_what_it_cannot_do():
    p = shop_plan()
    g = answers.draft(p, "Total quantity per category", ["order_items", "categories"], description(p), "shop_api")["graphql"]
    assert "groups only by a table's own columns" in g["not_possible"] and g["api"] == "shop_api"
    g = answers.draft(p, "How many orders?", ["orders"], description(p), "shop_api")["graphql"]
    assert "groupBy" in g["not_possible"]
    g = answers.draft(p, "How many orders per customer?", ["orders", "customers"], description(p), "shop_api")["graphql"]
    assert g["query"] == "query { orders { groupBy(fields: [customer_id]) { fields { customer_id } aggregations { count(field: order_id) } } } }"
    assert any("not by customers's name" in n or "not by customers" in n for n in g["notes"])


def test_bad_tables_are_refused():
    with pytest.raises(PlanInputError, match="not in the schema"):
        answers.draft(shop_plan(), "How many?", ["nope"])
    with pytest.raises(PlanInputError, match="name the tables"):
        answers.draft(shop_plan(), "How many?", [])
    from fabric_backend.schema import Column, Table
    s = seed.schema("shop")
    s.tables["island"] = Table("island", [Column("x", "int")], schema="shop")
    with pytest.raises(PlanInputError, match="no chain of relationships"):
        answers.draft(plan(s), "List island with orders", ["island", "orders"])


def test_tokens_an_agent_reads_with_and_without_the_suggestion():
    """The suggestion replaces describe_backend + join_path + writing the query: characters read for the same question
    (a token is roughly four characters). The numbers are the input for the measurement rig in fabric-eval."""
    p = shop_plan()
    desc = description(p)
    from fabric_backend.paths import join_path
    measured = {}
    for question, tables in (("How many orders per customer?", ["orders", "customers"]),
                             ("Total quantity per category", ["order_items", "categories"]),
                             ("De 10 senaste ordrarna med kund", ["orders", "customers"])):
        without = len(json.dumps(desc, indent=2)) + len(json.dumps(join_path(p, tables[0], tables[-1]), indent=2))
        with_ = len(json.dumps(answers.draft(p, question, tables, desc, "shop_api"), indent=2))
        measured[question] = (without, with_)
        assert with_ < without, (question, without, with_)
    assert measured == MEASURED, measured


MEASURED = {"How many orders per customer?": (4851, 1505), "Total quantity per category": (5569, 1512),
            "De 10 senaste ordrarna med kund": (4851, 1295)}          # docs/NOTEBOOKS.md quotes these


# ------------------------------------------------------------------ the tools ------------------------------------

class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body


@pytest.fixture
def shop(monkeypatch):
    p = shop_plan()
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src, "sql_host": "h", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(server, "_api_id", lambda ws, api, headers: "api-1" if api == "shop_api" else None)
    monkeypatch.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None: {"id": "api-1"} if name == "shop_api" else None)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: decode(definition(p, "shop_api", WS, "ep-1", "SqlAnalyticsEndpoint")))


def test_answer_query_draft_tool_runs_nothing(shop, monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("a draft runs nothing"))
    out = json.loads(server.answer_query_draft("Sales", "shop_lh", "Hur många ordrar per kund?", ["orders", "customers"], schema="shop", api="shop_api"))
    assert out["tsql"].startswith("SELECT") and out["graphql"]["query"].startswith("query { orders { groupBy")
    assert out["path"][0]["rule"] == "R1"
    out = json.loads(server.answer_query_draft("Sales", "shop_lh", "How many orders per customer?", ["orders", "customers"], schema="shop"))
    assert "graphql" not in out and "SELECT" in out["tsql"]
    assert json.loads(server.answer_query_draft("Sales", "shop_lh", "x", ["orders"], schema="shop", api="nope"))["kind"] == "not_found"
    assert json.loads(server.answer_query_draft("Sales", "shop_lh", "x", ["nope"], schema="shop"))["kind"] == "bad_input"


def test_query_graphql_runs_the_suggested_query(shop, monkeypatch):
    sent = []
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None: sent.append((url, json)) or Resp(200, {"data": {"orders": {"groupBy": []}}}))
    out = json.loads(server.query_graphql("Sales", "shop_api", question="How many orders per customer?", tables=["orders", "customers"],
                                          source="shop_lh", schema="shop"))
    assert sent[0][0].endswith("/graphqlapis/api-1/graphql") and sent[0][1]["query"] == out["suggested"]["query"]
    assert out["result"] == {"data": {"orders": {"groupBy": []}}} and out["suggested"]["path"][0]["to"] == "customers"
    sent.clear()
    out = json.loads(server.query_graphql("Sales", "shop_api", question="Total quantity per category", tables=["order_items", "categories"],
                                          source="shop_lh", schema="shop"))
    assert out["kind"] == "unsupported" and out["tsql"].startswith("SELECT") and sent == []
    assert json.loads(server.query_graphql("Sales", "shop_api", question="x"))["kind"] == "bad_input"
    assert json.loads(server.query_graphql("Sales", "shop_api"))["kind"] == "bad_input"
    # a plain query still works as before
    monkeypatch.setattr(requests, "post", lambda url, json=None, headers=None, timeout=None: Resp(200, {"data": {}}))
    assert json.loads(server.query_graphql("Sales", "shop_api", "{ customers { items { name } } }")) == {"data": {}}


def test_what_is_not_used_is_said():
    p = shop_plan()
    a = answers.draft(p, "Antal ordrar per kund efter 2024", ["orders", "customers"])
    assert any("not applied: 2024" in x and "WHERE" in x for x in a["assumptions"])
    a = answers.draft(p, "Customers per country", ["customers"])
    assert "GROUP BY t0.[country]" in a["tsql"] and any("counted per group" in x for x in a["assumptions"])
    a = answers.draft(p, "How many orders?", ["orders"])
    assert any("one total" in x for x in a["assumptions"]) and "GROUP BY" not in a["tsql"]
