"""Columns that are probably personal data: the rules (one per pattern, by name), the masking in sample_rows, and the
promise that no personal value of the shop seed reaches an answer unless show_personal_data=true is passed."""
import json
import re

import pytest
import requests

from fabric_backend import answers, gold, mcp_server, privacy, seed, server
from fabric_backend.infer import plan
from fabric_backend.schema import Schema
from test_answer_query import SHIP_TO, WS, description, run_tsql, sqlite_with_seed


# ------------------------------------------------------------------ the rules --------------------------------------

@pytest.mark.parametrize("table,column,rule", [
    ("customers", "email", "P2"), ("Customer", "EmailAddress", "P2"), ("users", "e_mail", "P2"), ("kunder", "epost", "P2"),
    ("kunder", "telefon", "P3"), ("users", "phone_number", "P3"), ("Person", "MobilePhone", "P3"),
    ("kunder", "personnummer", "P4"), ("employees", "ssn", "P4"), ("Mitarbeiter", "steuer_id", "P4"),
    ("employees", "first_name", "P1"), ("Person", "LastName", "P1"), ("kunder", "efternamn", "P1"), ("customers", "name", "P1"),
    ("dim_customer", "CustomerName", "P1"), ("kund", "namn", "P1"),
    ("Customer", "AddressLine1", "P5"), ("customers", "zip", "P5"), ("orders", "shipping_address", "P5"), ("addresses", "city", "P5"),
    ("kunder", "postnummer", "P5"), ("people", "DateOfBirth", "P6"), ("anstallda", "fodelsedatum", "P6"),
])
def test_a_rule_per_pattern(table, column, rule):
    assert privacy.classify(table, column)["rule"] == rule


@pytest.mark.parametrize("table,column", [
    ("products", "name"), ("categories", "name"), ("vendors", "name"), ("customers", "customer_id"), ("orders", "ship_to_id"),
    ("customers", "country"), ("stores", "city"), ("orders", "order_date"), ("customers", "email_verified"), ("audit_log", "event"),
    ("customers", "company_name"), ("x", "mailing_list_id"), ("email_log", "sent_at"),
])
def test_nothing_is_guessed(table, column):
    assert privacy.classify(table, column) is None


def test_the_shop_seed_has_two_personal_columns_and_masking_keeps_nulls():
    flagged = privacy.personal_columns(seed.schema("shop"))
    assert {k: v["rule"] for k, v in flagged.items()} == {("customers", "name"): "P1", ("addresses", "city"): "P5"}
    rows, masked = privacy.mask_rows("customers", [{"customer_id": 1, "name": "Harbour Bikes"}, {"customer_id": 2, "name": None}], flagged)
    assert rows == [{"customer_id": 1, "name": "***"}, {"customer_id": 2, "name": None}] and masked == ["name"]
    assert privacy.label_of({"sensitivityLabel": {"id": "b7b4f4d9-3f0d-4b3e-8f3d-4f6d3f4f3f4f"}})["id"].startswith("b7b4")
    assert privacy.label_of({}) is None


# ------------------------------------------------------------------ nothing personal leaks by default -------------

PERSONAL = {c[1] for c in seed.CUSTOMERS} | {a[2] for a in seed.rows()["addresses"]}     # names and cities in the seed


def leaks(text: str) -> set[str]:
    return {v for v in PERSONAL if v in text}


def fake_execute(sql: str):
    """The shop seed behind the SQL endpoint: samples return rows, counting queries return counts."""
    m = re.search(r"SELECT TOP \((\d+)\) (.*?) FROM \[shop\]\.\[([^\]]+)\]", sql, re.S)
    if m:
        n, cols, table = int(m.group(1)), re.findall(r"\[([^\]]+)\]", m.group(2)), m.group(3)
        names = [c.split()[0] for c in seed.SCHEMAS[table].split(", ")]
        return [{c: v for c, v in zip(names, r) if c in cols} for r in seed.rows()[table][:n]]
    if "AS orphans" in sql:
        return [{"with_value": 10, "orphans": 0}]
    return [{"n": 10, "nulls": 0, "distinct_keys": 10}]


@pytest.fixture
def shop(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {
        "type": "Lakehouse", "id": "lh-1", "displayName": src, "sql_host": "x", "sql_db": src, "schemas_enabled": True,
        "sensitivityLabel": {"id": "b7b4f4d9-3f0d-4b3e-8f3d-4f6d3f4f3f4f"}})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: fake_execute(sql)))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    return monkeypatch


def test_sample_rows_masks_with_the_rule_and_shows_on_request(shop):
    out = json.loads(server.sample_rows("Sales", "shop_lh", "customers", schema="shop"))
    assert {r["name"] for r in out["rows"]} == {"***"} and [r["customer_id"] for r in out["rows"]][:3] == [1, 2, 3]
    pd = out["personal_data"]
    assert pd["masked"] is True and pd["columns"][0]["rule"] == "P1" and "show_personal_data=true" in pd["notice"]
    assert pd["sensitivity_label"]["id"] == "b7b4f4d9-3f0d-4b3e-8f3d-4f6d3f4f3f4f" and not leaks(json.dumps(out))
    shown = json.loads(server.sample_rows("Sales", "shop_lh", "customers", schema="shop", show_personal_data=True))
    assert "Harbour Bikes" in {r["name"] for r in shown["rows"]} and shown["personal_data"]["masked"] is False
    products = json.loads(server.sample_rows("Sales", "shop_lh", "products", schema="shop"))
    assert "Trail bike" in {r["name"] for r in products["rows"]} and "columns" not in products["personal_data"] or \
        products["personal_data"]["columns"] == []


def test_no_personal_value_of_the_shop_seed_reaches_an_answer_without_the_parameter(shop):
    answers_text = []
    for t in seed.SCHEMAS:
        answers_text.append(server.sample_rows("Sales", "shop_lh", t, schema="shop", n=20))
    answers_text.append(server.validate_plan("Sales", "shop_lh", schema="shop"))
    shop.setattr(server, "_api_id", lambda ws, api, headers: "api-1")
    shop.setattr(server, "_graphql_definition", lambda ws, api_id, headers: __import__("fabric_backend.graphql", fromlist=["decode"]).decode(
        __import__("fabric_backend.graphql", fromlist=["definition"]).definition(plan(seed.schema("shop"), None, SHIP_TO), "shop_api", WS, "ep-1",
                                                                                  "SqlAnalyticsEndpoint")))
    for question, tables in (("How many orders per customer?", ["orders", "customers"]), ("De 10 senaste ordrarna med kund", ["orders", "customers"]),
                             ("Orders with the city they ship to", ["orders", "addresses"]), ("List the customers", ["customers"])):
        answers_text.append(server.answer_query_draft("Sales", "shop_lh", question, tables, schema="shop", api="shop_api", confirmed=SHIP_TO))

    # query_graphql with a question runs the suggested query; the endpoint answers with the fields that query asks for
    def endpoint(url, json=None, **k):
        asked = set(re.findall(r"\b([a-z_]+)\b", json["query"]))
        customers = [{f: v for f, v in zip(("customer_id", "name", "country"), c) if f in asked} for c in seed.CUSTOMERS]

        class R:
            status_code, text = 200, ""

            def json(self):
                return {"data": {"customers": {"items": customers}}}
        return R()
    shop.setattr(requests, "post", endpoint)
    answers_text.append(server.query_graphql("Sales", "shop_api", question="List the customers", tables=["customers"], source="shop_lh", schema="shop"))
    answers_text.append(server.gold_views_draft("Sales", "shop_lh", schema="shop"))
    answers_text.append(server.silver_notebook_draft("Sales", "shop_lh", schema="shop"))
    for text in answers_text:
        assert not leaks(text), (leaks(text), text[:300])
    # the SQL that answer_query_draft suggests returns no personal value either, when it is run
    con = sqlite_with_seed()
    for question, tables in (("How many orders per customer?", ["orders", "customers"]), ("De 10 senaste ordrarna med kund", ["orders", "customers"]),
                             ("Orders with the city they ship to", ["orders", "addresses"])):
        sql = answers.draft(plan(seed.schema("shop"), None, SHIP_TO), question, tables)["tsql"]
        assert not leaks(json.dumps(run_tsql(con, sql), default=str)), question
    # and with the parameter, they do
    shown = server.sample_rows("Sales", "shop_lh", "customers", schema="shop", show_personal_data=True)
    assert leaks(shown)
    sql = answers.draft(plan(seed.schema("shop"), None, SHIP_TO), "How many orders per customer?", ["orders", "customers"], show_personal_data=True)["tsql"]
    assert leaks(json.dumps(run_tsql(con, sql), default=str))


def test_the_local_server_masks_too(monkeypatch):
    monkeypatch.setattr(mcp_server, "plan_from", lambda execute=None, schema="dbo", **k: plan(seed.schema("shop")))

    class Conn:
        def __enter__(self):
            return fake_execute

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(mcp_server, "_connection", lambda schema: Conn())
    out = json.loads(mcp_server.sample_rows("customers", schema="shop"))
    assert {r["name"] for r in out["rows"]} == {"***"} and out["personal_data"]["columns"][0]["rule"] == "P1"
    assert "Harbour Bikes" in json.dumps(json.loads(mcp_server.sample_rows("customers", schema="shop", show_personal_data=True)))


def test_validate_plan_names_the_personal_columns_it_counts_and_returns_no_values(shop):
    out = json.loads(server.validate_plan("Sales", "shop_lh", schema="shop"))
    # no key or relationship in the shop plan uses a personal column: the label is still named
    assert out["personal_data"]["columns"] == [] and out["personal_data"]["sensitivity_label"]["id"].startswith("b7b4")
    assert "counts and verdicts only" in out["personal_data"]["note"]


def test_the_silver_quarantine_keeps_personal_columns_masked_and_the_gold_views_leave_them_out():
    from fabric_backend import silver
    from silver_cases import seed_rows
    info = dict(workspace_id="ws", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop", schemas_enabled=True)
    s = silver.spec(plan(seed.schema("shop")), info)
    assert s["personal"] == {"addresses": ["city"], "customers": ["name"]} and s["mask_personal_data"] is True
    q = silver.simulate(s, seed_rows())["quarantine"]
    customers = [x["row"] for x in q if x["source_table"] == "customers"]
    assert customers and all(r["name"] == "***" for r in customers)
    assert 'MASK_PERSONAL_DATA = True' in dict(silver.cells(s))["parameters"]
    shown = silver.spec(plan(seed.schema("shop")), info, show_personal_data=True)
    assert "MASK_PERSONAL_DATA = False" in dict(silver.cells(shown))["parameters"]
    assert "Nameless" in {x["row"]["name"] for x in silver.simulate(shown, seed_rows())["quarantine"] if x["source_table"] == "customers"}
    g = gold.spec(plan(seed.schema("shop")), info)
    assert all(c["as"] != "customers_name" for v in g["views"] for c in v["columns"])
