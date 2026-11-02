"""n87, point 7: personal data the same way everywhere (fabric_backend/privacy.py). create_views and app_starter showed
customers.name where sample_rows, the drafted queries and the gold views leave it out; "Which city" left addresses.city
out without saying so and grouped by address instead; and the GraphQL note said "the T-SQL returns the name" when the
T-SQL left the name out. Against the golden doubles and the shop seed."""
import json

from fabric_backend import answers, server, views
from tests.test_answer_query import description, run_tsql, shop_plan, sqlite_with_seed
from tests.test_golden import SRC, fabric  # noqa: F401  (fabric: fixture)


def test_create_views_leaves_personal_columns_out_and_says_so(fabric):
    out = json.loads(server.create_views(**SRC))
    sql = "\n".join(v["sql"] for v in out["views"])
    assert "[customers_name]" not in sql and "t.[city]" not in sql and "[addresses_city]" not in sql
    left = " ".join(out["personal_data"]["left_out"])
    assert "customers.name (P1" in left and "addresses.city (P5" in left
    assert "left out" in out["personal_data"]["notice"]


def test_the_views_statements_leave_them_out_by_default():
    p = shop_plan()
    sql = "\n".join(v["sql"] for v in views.statements(p, "krusgraph")["views"])
    assert "[customers_name]" not in sql
    assert "[customers_name]" in "\n".join(v["sql"] for v in views.statements(p, "krusgraph", show_personal_data=True)["views"])


def test_app_starter_queries_select_no_personal_field(fabric):
    out = json.loads(server.app_starter(workspace="demo", api="shop_api"))
    for q in out["queries"]:
        assert not any(f" {f} " in q["query"] for f in ("name", "city")) or "categories" in q["query"] or "products" in q["query"], q
    assert "customers.name" in " ".join(out["personal_data"]["left_out"])
    assert "personal data" in out["lovable_prompt"]


def test_which_city_says_city_was_left_out_and_groups_by_it_when_shown():
    p = shop_plan()
    out = answers.draft(p, "Which city has the most orders?", ["orders", "addresses"])
    assert "addresses.city (P5: an address)" in out["personal_data"]["left_out"]
    assert any("city" in a and "address_id" in a and "show_personal_data=true" in a for a in out["assumptions"])
    shown = answers.draft(p, "Which city has the most orders?", ["orders", "addresses"], show_personal_data=True)
    assert "GROUP BY t" in shown["tsql"] and "[city]" in shown["tsql"].split("GROUP BY")[1]
    assert "[address_id]" not in shown["tsql"].split("GROUP BY")[1]
    rows = run_tsql(sqlite_with_seed(), shown["tsql"])
    assert len({r[0] for r in rows}) == len(rows)                           # one row per city


def test_the_graphql_note_says_what_the_tsql_returns():
    p = shop_plan()
    out = answers.draft(p, "How many orders per customer?", ["orders", "customers"], description(p), "shop_api")
    notes = " ".join(out["graphql"]["notes"])
    assert "the T-SQL returns the name" not in notes
    assert "customer_id" in notes and "personal data" in notes
    shown = answers.draft(p, "How many orders per customer?", ["orders", "customers"], description(p), "shop_api", show_personal_data=True)
    assert "the T-SQL also returns customers.name" in " ".join(shown["graphql"]["notes"])
