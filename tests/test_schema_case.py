"""Round n175: a schema typed in another case ("Shop") than the lakehouse spells it ("shop").

Live, 9 November 2026: the review listed the 7 tables (the metadata query compares case-insensitively), but Check against
the rows failed with ('42S02', "Invalid object name 'Shop.addresses'") from the SQL analytics endpoint, and the review
showed 6 links instead of 7 (R5's counting query for orders.ship_to_id failed the same way). The engine now takes the
schema, table and column names as the metadata returns them before any SQL is written, on every path (the MCP tools,
the workload's review, check and build, R5), says in the answer which name it used, and asks when two schemas differ
only by case. The SQL endpoint here is tests/golden_support.py's double with case_sensitive=True: a name in another
case fails as the real endpoint fails."""
import json
import sys

import pytest

import golden_support as gs
from fabric_backend import errors, infer, seed, server
from fabric_backend.schema import Schema, SchemaAmbiguous, exact_schema

ROWS = seed.schema("shop").to_rows()


# ------------------------------------------------------------------ the engine, without a connection -----------------

@pytest.mark.parametrize("asked", ["Shop", "SHOP", "sHoP", "shop"])
def test_the_schema_is_the_metadata_s_spelling_whatever_case_was_typed(asked):
    s = Schema.from_information_schema(ROWS, schema=asked)
    assert s.schema == "shop" and len(s) == 7
    assert {t.schema for t in s} == {"shop"}
    assert s.asked == (None if asked == "shop" else asked)


def test_two_schemas_that_differ_only_by_case_are_asked_about_not_guessed():
    rows = ROWS + seed.schema("Shop").to_rows()
    with pytest.raises(SchemaAmbiguous) as e:
        Schema.from_information_schema(rows, schema="SHOP")
    assert e.value.names == ["Shop", "shop"] and "Which one" in str(e.value)
    answer = errors.explain(e.value)
    assert answer["kind"] == "schema_ambiguous" and answer["schemas"] == ["Shop", "shop"] and "Ask the user" in answer["hint"]
    assert Schema.from_information_schema(rows, schema="shop").schema == "shop"      # typed exactly: no question
    assert Schema.from_information_schema(rows, schema="Shop").schema == "Shop"
    assert exact_schema([], "Shop") == "Shop"                                         # no rows: the name as asked


def test_keys_and_confirmed_in_another_case_are_written_as_the_metadata_spells_them():
    s = Schema.from_information_schema(ROWS, schema="Shop")
    p = infer.plan(s, keys={"ORDERS": ["Order_ID"]},
                   confirmed=[{"source": "Orders", "source_cols": ["SHIP_TO_ID"], "target": "Addresses", "target_cols": ["Address_Id"]}])
    assert p.keys["orders"][0] == ["order_id"]
    r = next(r for r in p.relationships if r.source_cols == ["ship_to_id"])
    assert (r.source, r.target, r.target_cols) == ("orders", "addresses", ["address_id"])
    assert set(p.keys) <= {t.name for t in s}


# ------------------------------------------------------------------ the MCP tools, on the case-sensitive endpoint ----

@pytest.fixture
def endpoint(monkeypatch):
    import requests

    def make(schemas=("shop",)):
        fake = gs.FakeFabric()
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        odbc = gs.fake_pyodbc(case_sensitive=True, schemas=schemas)
        monkeypatch.setitem(sys.modules, "pyodbc", odbc)
        monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
        monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
        monkeypatch.setattr(server, "limiter", None)
        return fake, odbc
    return make


def _queries(odbc):
    return [q for q in odbc.log if "INFORMATION_SCHEMA" not in q]


def test_the_double_fails_as_the_endpoint_does_on_a_name_in_another_case(endpoint):
    _, odbc = endpoint()
    con = odbc.connect("Database=demo_lh")
    with pytest.raises(odbc.Error, match="Invalid object name 'Shop.addresses'"):
        con.cursor().execute("SELECT COUNT_BIG(*) AS n FROM [Shop].[addresses]")
    with pytest.raises(odbc.Error, match="Invalid column name 'Address_ID'"):
        con.cursor().execute("SELECT COUNT_BIG([Address_ID]) AS n FROM [shop].[addresses]")
    assert con.cursor().execute("SELECT COUNT_BIG(*) AS n FROM [shop].[addresses]").fetchall()


def test_validate_plan_with_shop_counts_every_key_and_link_and_says_which_name_it_used(endpoint):
    _, odbc = endpoint()
    exact = json.loads(server.validate_plan("demo", "demo_lh", schema="shop", detail="full"))
    odbc.log.clear()
    out = json.loads(server.validate_plan("demo", "demo_lh", schema="Shop", detail="full"))
    assert "error" not in out, out
    assert out["schema_used"]["asked"] == "Shop" and out["schema_used"]["used"] == "shop"
    assert "'Shop' was read as 'shop'" in out["schema_used"]["note"]
    assert len(out["relationships"]) == len(exact["relationships"]) == 7
    assert {r.get("verdict") for r in out["relationships"]} == {r.get("verdict") for r in exact["relationships"]}
    assert _queries(odbc) and not any("[Shop]" in q for q in _queries(odbc))
    assert "schema_used" not in exact


def test_plan_backend_with_shop_finds_the_seventh_link_that_r5_counts(endpoint):
    _, odbc = endpoint()
    exact = json.loads(server.plan_backend("demo", "demo_lh", schema="shop", detail="full"))
    out = json.loads(server.plan_backend("demo", "demo_lh", schema="SHOP", detail="full"))
    assert "error" not in out, out
    links = lambda a: sorted((r["source"], tuple(r["source_cols"]), r["target"]) for r in a["relationships"])   # noqa: E731
    assert links(out) == links(exact) and len(links(out)) == 7
    assert ("orders", ("ship_to_id",), "addresses") in links(out)
    assert out["schema_used"]["used"] == "shop"
    assert not any("[SHOP]" in q for q in odbc.log)


def test_a_creating_tool_s_dry_run_writes_the_exact_name_into_its_definition(endpoint):
    _, _ = endpoint()
    out = server.create_gold_views("demo", "demo_lh", name="shop_gold", schema="Shop")
    data = json.loads(out)
    assert "error" not in data, data
    assert data["schema_used"]["used"] == "shop"
    body = json.dumps({k: v for k, v in data.items() if k != "schema_used"})
    assert "Shop." not in body and "[Shop]" not in body and "`Shop`" not in body


def test_an_ambiguous_schema_is_a_question_and_nothing_is_counted(endpoint):
    _, odbc = endpoint(schemas=("shop", "Shop"))
    out = json.loads(server.validate_plan("demo", "demo_lh", schema="SHOP"))
    assert out["kind"] == "schema_ambiguous" and out["schemas"] == ["Shop", "shop"]
    assert _queries(odbc) == []
    assert "error" not in json.loads(server.validate_plan("demo", "demo_lh", schema="shop"))


# ------------------------------------------------------------------ the workload editor's calls -------------------------

jwt = pytest.importorskip("jwt")


@pytest.fixture
def wl(keys, monkeypatch):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    import requests
    from fabric_backend import workload_api
    from fabric_backend.entra import Validator
    from test_workload_api import WL, FakeJWKS, FakeOBO
    priv, pub = keys

    def make(schemas=("shop",)):
        fake = gs.FakeFabric()
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        odbc = gs.fake_pyodbc(case_sensitive=True, schemas=schemas)
        monkeypatch.setitem(sys.modules, "pyodbc", odbc)
        monkeypatch.setattr(server, "limiter", None)
        app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), FakeOBO()))
        return TestClient(app), odbc, priv
    return make


from test_workload_api import _post, keys, tok  # noqa: E402,F401


def test_the_editor_s_review_check_and_build_with_shop(wl):
    client, odbc, priv = wl()
    src = {"workspace": gs.WS, "source": "demo_lh", "source_name": "demo_lh", "schema": "Shop"}
    r = _post(client, "/review", src, tok(priv))
    assert r.status_code == 200, r.text
    rv = r.json()
    assert rv["counts"]["relationships"] == 7                          # the founder saw 6: R5's query had failed
    assert rv["review"]["source"]["schema"] == "shop"
    assert rv["schema_used"] == {"asked": "Shop", "used": "shop", "note": rv["schema_used"]["note"]}
    c = _post(client, "/check", {**src, "review": rv["review"]}, tok(priv))
    assert c.status_code == 200, c.text
    chk = c.json()["check"]
    assert chk["relationships"]["failed"] == 0 and chk["relationships"]["passed"] == 7, chk
    assert chk["keys"]["failed"] == 0 and chk["keys"]["passed"] == 6
    assert c.json()["schema_used"]["used"] == "shop"
    b = _post(client, "/build", {**src, "review": c.json()["review"], "outputs": [
        {"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "semantic_model", "name": "shop_sales"}]}, tok(priv))
    assert b.status_code == 200, b.text
    out = b.json()
    assert out["refused"] == 0, [c.get("answer", {}).get("error") for c in out["outputs"]]
    assert out["schema_used"]["used"] == "shop"
    assert "Shop." not in json.dumps(out["outputs"]) and "[Shop]" not in json.dumps(out["outputs"])
    assert not any("[Shop]" in q for q in odbc.log)


def test_the_editor_is_asked_which_schema_when_two_differ_only_by_case(wl):
    client, odbc, priv = wl(schemas=("shop", "Shop"))
    r = _post(client, "/review", {"workspace": gs.WS, "source": "demo_lh", "schema": "SHOP"}, tok(priv))
    out = r.json()
    assert out.get("kind") == "schema_ambiguous", out
    assert out["schemas"] == ["Shop", "shop"]
