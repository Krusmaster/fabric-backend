"""graphs.py: weights, centrality, roles, areas, ambiguity, the spanning forest, weighted paths and link prediction —
on the shop schema, TPC-H and Sakila, run twice for determinism — and the two MCP tools."""
import datetime
import json
import re
import sqlite3
import time

import pytest

from fabric_backend import dictionary, evidence, graphs, paths, seed, semantic_model, server
from fabric_backend.infer import plan
from fabric_backend.schema import Schema
from test_inference_quality import load, names_only

SHIP_TO = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}


def schema(*tables):
    return Schema.from_information_schema([("dbo", n, c, t, i) for n, cols in tables for i, (c, t) in enumerate(cols, 1)], schema="dbo")


@pytest.fixture
def shop_plan():
    return plan(seed.schema("shop"))


@pytest.fixture
def tpch():
    return plan(names_only(load("tpch")))


@pytest.fixture
def sakila():
    return plan(names_only(load("sakila")))


def sqlite_execute():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, ddl in seed.SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in seed.rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)

    def execute(sql):
        cur = con.execute(sql.replace("COUNT_BIG(", "COUNT("))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return execute


# ------------------------------------------------------------------ weights and edges -------------

def test_weights_table_and_costs(shop_plan):
    assert graphs.WEIGHTS == {"R0": 1.0, "confirmed": 1.0, "verified": 0.9, "R1": 0.8, "R2": 0.6, "R3": 0.5, "R4": 0.5}
    es = graphs.edges(shop_plan)
    assert len(es) == 6 and all(e["rule"] == "R1" and e["certainty"] == 0.8 and e["cost"] == 1.25 for e in es)
    assert [(e["source"], e["target"]) for e in es] == sorted((e["source"], e["target"]) for e in es)       # sorted: deterministic
    confirmed = plan(seed.schema("shop"), confirmed=[SHIP_TO])
    e = next(x for x in graphs.edges(confirmed) if x["columns"] == ["ship_to_id"])
    assert e["rule"] == "confirmed" and e["certainty"] == 1.0 and e["cost"] == 1.0
    # a link validate_plan confirmed is worth 0.9 whatever its rule; a declared one keeps 1.0
    validation = {"relationships": [{"source": "orders", "columns": ["customer_id"], "target": "customers", "verdict": "holds: 60 rows, 0 orphans"},
                                    {"source": "orders", "columns": ["ship_to_id"], "target": "addresses", "verdict": "holds"}]}
    es = {(x["source"], tuple(x["columns"])): x for x in graphs.edges(confirmed, validation)}
    assert es[("orders", ("customer_id",))]["certainty"] == 0.9 and es[("orders", ("customer_id",))]["verified"] is True
    assert es[("orders", ("ship_to_id",))]["certainty"] == 1.0 and es[("products", ("category_id",))]["certainty"] == 0.8


# ------------------------------------------------------------------ analysis ----------------------

def test_shop_roles_centrality_areas_and_no_ambiguity(shop_plan):
    a = graphs.analyze(shop_plan)
    assert {t: r["role"] for t, r in a["roles"].items()} == {
        "order_items": "fact", "orders": "fact", "audit_log": "fact",
        "customers": "dimension", "products": "dimension", "categories": "dimension", "addresses": "dimension"}
    assert "pointed at by a fact table" in a["roles"]["orders"]["why"] and "out 2, in 0" in a["roles"]["order_items"]["why"]
    top = a["centrality"]["top"]
    assert top[0]["table"] == "customers" and top[0]["in"] == 3 and top[0]["out"] == 0 and top[0]["betweenness"] == 0.6
    assert abs(sum(a["centrality"]["pagerank"].values()) - 1.0) < 0.01
    assert a["centrality"]["degree"]["order_items"] == {"in": 0, "out": 2}
    assert a["areas"] == [{"name": "customers area", "central_table": "customers",
                           "tables": ["addresses", "audit_log", "categories", "customers", "order_items", "orders", "products"]}]
    assert a["ambiguity"]["cycles"] == [] and a["ambiguity"]["pairs_with_multiple_paths"] == [] and "no cycles" in a["ambiguity"]["note"]
    assert len(a["active_relationships"]) == 6 and a["inactive_relationships"] == []
    assert a["summary"].startswith("7 tables, 6 relationships; roles: 3 fact, 4 dimension") and "0 cycle(s)" in a["summary"]
    assert graphs.analyze(shop_plan) == a                                                           # run twice: same answer


def test_tpch_roles_match_the_specification_and_cycles_are_found(tpch):
    """TPC-H: LINEITEM and ORDERS are the two scale-factor tables with the measures (the fact side); NATION (25 rows) and
    REGION (5 rows) are fixed lookup tables (dimensions)."""
    a = graphs.analyze(tpch)
    roles = {t: r["role"] for t, r in a["roles"].items()}
    assert roles["LINEITEM"] == "fact" and roles["ORDERS"] == "fact"
    assert roles["NATION"] == "dimension" and roles["REGION"] == "dimension"
    assert roles["PARTSUPP"] == "bridge" and "junction key (K4)" in a["roles"]["PARTSUPP"]["why"]
    assert roles["CUSTOMER"] == roles["SUPPLIER"] == roles["PART"] == "dimension"
    assert len(a["ambiguity"]["cycles"]) == 3 and ["LINEITEM", "ORDERS"] in a["ambiguity"]["pairs_with_multiple_paths"]
    closed = {c["closed_by"].split(" (")[0] for c in a["ambiguity"]["cycles"]}
    assert closed == {"PARTSUPP.PS_SUPPKEY -> SUPPLIER", "ORDERS.O_CUSTKEY -> CUSTOMER", "LINEITEM.L_PARTKEY+L_SUPPKEY -> PARTSUPP"}
    assert len(a["active_relationships"]) == 7 and len(a["inactive_relationships"]) == 3
    assert all(e["certainty"] <= 0.6 for e in a["inactive_relationships"])                         # only R2/R3 links lose
    assert all("cycle" in e["why"] and "certainty" in e["why"] for e in a["inactive_relationships"])
    assert a["centrality"]["top"][0]["table"] in ("REGION", "NATION")                               # where the references end up
    assert graphs.analyze(tpch) == a
    names = {g["name"] for g in a["areas"]}
    assert len(a["areas"]) == 2 and {"REGION area", "PART area"} == names


def test_sakila_bridges_and_determinism(sakila):
    a = graphs.analyze(sakila)
    roles = {t: r["role"] for t, r in a["roles"].items()}
    assert roles["film_actor"] == roles["film_category"] == "bridge" and roles["rental"] == roles["payment"] == "fact"
    assert roles["country"] == roles["city"] == roles["language"] == "dimension"
    assert len(a["ambiguity"]["cycles"]) == 8 and len(a["active_relationships"]) == 15                 # 16 tables in one component
    t0 = time.time()
    assert graphs.analyze(sakila) == a and time.time() - t0 < 2
    big = plan(names_only(load("adventureworks")))
    t0 = time.time()
    b = graphs.analyze(big)
    assert time.time() - t0 < 10 and len(b["centrality"]["top"]) == 10 and graphs.analyze(big) == b


def test_isolated_tables_and_a_triangle():
    s = schema(("a", [("a_id", "int"), ("b_id", "int"), ("c_id", "int")]), ("b", [("b_id", "int"), ("c_id", "int")]),
               ("c", [("c_id", "int"), ("name", "varchar")]), ("alone", [("alone_id", "int"), ("x", "int")]))
    a = graphs.analyze(plan(s))
    assert a["roles"]["alone"]["role"] == "isolated" and a["roles"]["c"]["role"] == "dimension"
    assert len(a["ambiguity"]["cycles"]) == 1 and sorted(a["ambiguity"]["cycles"][0]["tables"]) == ["a", "b", "c"]
    assert len(a["inactive_relationships"]) == 1
    # betweenness: a line a - b - c puts b between a and c once; normalised
    line = plan(schema(("a", [("a_id", "int"), ("b_id", "int")]), ("b", [("b_id", "int"), ("c_id", "int")]), ("c", [("c_id", "int")])))
    bc = graphs.analyze(line)["centrality"]["betweenness"]
    assert bc == {"a": 0.0, "b": 1.0, "c": 0.0}


# ------------------------------------------------------------------ spanning forest and the model --

def test_semantic_model_uses_the_forest_and_marks_roles(tpch, shop_plan):
    info = dict(workspace_id="ws", item_id="i", item_name="n", item_kind="Warehouse", schema="dbo", sql_endpoint="x", sql_db="n", schemas_enabled=True)
    out = semantic_model.draft(tpch, info, "m")
    forest = graphs.analyze(tpch)
    assert {(i["source"], i["target"]) for i in out["summary"]["inactive"]} == {(e["source"], e["target"]) for e in forest["inactive_relationships"] if len(e["columns"]) == 1}
    assert out["summary"]["roles"]["LINEITEM"] == "fact" and "annotation Krusgraph_Role = fact" in out["parts"]["definition/tables/LINEITEM.tmdl"]
    assert "| `NATION` | dimension |" in out["parts"]["README.generated.md"]
    # a verified link outranks an unverified one of the same rule when the forest is chosen
    s = schema(("f", [("f_id", "int"), ("a_id", "int"), ("b_id", "int")]), ("a", [("a_id", "int"), ("b_id", "int")]), ("b", [("b_id", "int")]))
    p = plan(s)
    v = {"relationships": [{"source": "a", "columns": ["b_id"], "target": "b", "verdict": "holds"}, {"source": "f", "columns": ["a_id"], "target": "a", "verdict": "holds"}]}
    active, inactive = semantic_model.active_relationships(p, p.relationships, v)
    assert [(r.source, r.target) for r, _ in inactive] == [("f", "b")]                               # the unverified one goes


# ------------------------------------------------------------------ weighted join path -----------

def test_safest_path_differs_from_shortest_and_is_explained():
    """a - x - b in two hops over composite-key links (R3, cost 2.0 each = 4.0); a - c - d - b in three hops over
    declared foreign keys (R0, cost 1.0 each = 3.0): the shortest path is not the safest."""
    cols = [("dbo", "a", "a_id", "int", 1), ("dbo", "a", "c_id", "int", 2), ("dbo", "a", "x1", "int", 3), ("dbo", "a", "x2", "int", 4),
            ("dbo", "c", "c_id", "int", 1), ("dbo", "c", "d_id", "int", 2), ("dbo", "d", "d_id", "int", 1), ("dbo", "d", "b_id", "int", 2),
            ("dbo", "b", "b_id", "int", 1), ("dbo", "b", "x1", "int", 2), ("dbo", "b", "x2", "int", 3),
            ("dbo", "x", "x1", "int", 1), ("dbo", "x", "x2", "int", 2), ("dbo", "x", "v", "varchar", 3)]
    keys = [("a", "PRIMARY KEY", "a_id", 1, "pk_a", None, None), ("c", "PRIMARY KEY", "c_id", 1, "pk_c", None, None),
            ("d", "PRIMARY KEY", "d_id", 1, "pk_d", None, None), ("b", "PRIMARY KEY", "b_id", 1, "pk_b", None, None),
            ("x", "PRIMARY KEY", "x1", 1, "pk_x", None, None), ("x", "PRIMARY KEY", "x2", 2, "pk_x", None, None),
            ("a", "FOREIGN KEY", "c_id", 1, "fk_ac", "c", "c_id"), ("c", "FOREIGN KEY", "d_id", 1, "fk_cd", "d", "d_id"),
            ("d", "FOREIGN KEY", "b_id", 1, "fk_db", "b", "b_id")]
    p = plan(Schema.from_information_schema(cols, keys=keys, schema="dbo"))
    rules = {(r.source, r.target): r.rule for r in p.relationships}
    assert rules[("a", "x")] == "R3" and rules[("b", "x")] == "R3" and rules[("a", "c")] == rules[("c", "d")] == rules[("d", "b")] == "R0"
    out = paths.join_path(p, "a", "b")
    assert out["paths"][0]["tables"] == ["a", "x", "b"] and out["paths"][0]["cost"] == 4.0 and [s["rule"] for s in out["paths"][0]["steps"]] == ["R3", "R3"]
    assert out["safest"]["tables"] == ["a", "c", "d", "b"] and out["safest"]["cost"] == 3.0 and out["safest"]["hops"] == 3
    assert "R3 link" in out["safest"]["why"] and "cost 3.0 against 4.0" in out["safest"]["why"]
    assert out["safest"]["sql"].count("JOIN") == 3 and all(s["certainty"] == 1.0 for s in out["safest"]["steps"])
    same = paths.join_path(plan(seed.schema("shop")), "customers", "categories")
    assert same["safest"]["why"] == "the shortest path is also the safest" and same["safest"]["tables"] == same["paths"][0]["tables"]
    assert all("certainty" in st and st["cost"] == 1.25 for st in same["paths"][0]["steps"])
    # once validate_plan has confirmed the two composite links (0.9 each, cost 2.22), the short path is the safest too
    v = {"relationships": [{"source": "a", "columns": ["x1", "x2"], "target": "x", "verdict": "holds"},
                           {"source": "b", "columns": ["x1", "x2"], "target": "x", "verdict": "holds"}]}
    verified = paths.join_path(p, "a", "b", validation=v)
    assert verified["safest"]["hops"] == 2 and verified["paths"][0]["cost"] == 2.2222 and verified["safest"]["why"] == "the shortest path is also the safest"


# ------------------------------------------------------------------ link prediction --------------

def test_inclusion_sql_and_suggestions_find_ship_to_on_the_seed_data(shop_plan):
    sql = evidence.inclusion_sql("shop", "orders", "ship_to_id", "addresses", "address_id")
    assert sql.startswith("SELECT COUNT_BIG(*) AS with_value, COUNT_BIG(t.[address_id]) AS matched, COUNT_BIG(DISTINCT s.[ship_to_id]) AS distinct_values")
    assert "LEFT JOIN (SELECT DISTINCT [address_id] FROM [shop].[addresses]) AS t ON s.[ship_to_id] = t.[address_id] WHERE s.[ship_to_id] IS NOT NULL" in sql
    out = graphs.suggest(shop_plan, sqlite_execute())
    best = out["candidates"][0]
    assert best["source"] == "orders" and best["source_cols"] == ["ship_to_id"] and best["target"] == "addresses"
    assert best["evidence"]["inclusion"] == 1.0 and best["evidence"]["rows_with_value"] == 60 and best["evidence"]["distinct_values"] == 15
    assert best["evidence"]["verdict"] == "every value exists in the target key"
    assert best["confirmed"] == SHIP_TO
    others = {c["target"]: c["evidence"]["inclusion"] for c in out["candidates"] if c["source_cols"] == ["ship_to_id"]}
    assert others["customers"] < 1.0 and others["categories"] < others["customers"]                # the data separates the candidates
    assert out["checked_against_data"] == len(out["candidates"]) <= 15 and "nothing is applied" in out["note"].lower()
    # applying the accepted suggestion closes the gap, and the suggestion list is then empty for that column
    closed = plan(seed.schema("shop"), confirmed=[best["confirmed"]])
    assert not any(c["source_cols"] == ["ship_to_id"] for c in graphs.suggest(closed)["candidates"])
    assert graphs.suggest(shop_plan, sqlite_execute()) == out


def test_candidates_rank_by_name_type_and_triangular_closure():
    # rep_id: a reference suffix and a role word (rep) that names a person; person_ref: resembles persons by name (an
    # abbreviation) but has no reference suffix. Both close the triangle orders -> customers -> persons (R1 0.8 x R1 0.8).
    s = schema(("orders", [("order_id", "int"), ("customer_id", "int"), ("rep_id", "int"), ("person_ref", "int"), ("note", "varchar")]),
               ("customers", [("customer_id", "int"), ("person_id", "int")]),
               ("persons", [("person_id", "int"), ("name", "varchar")]),
               ("tags", [("tag_id", "varchar"), ("label", "varchar")]))
    c = graphs.candidates(plan(s))
    top = c[0]
    assert (top["source"], top["source_cols"], top["target"]) == ("orders", ["rep_id"], "persons")                   # role word + suffix + triangle
    assert top["name_basis"] == "role word" and top["name_similarity"] == 0.6 and top["closure"] == 0.64 and top["score"] == 3.94
    assert top["closure_via"] == "orders -> customers -> persons" and "a role held by a person" in top["why"]
    ref = next(x for x in c if x["source_cols"] == ["person_ref"])
    assert ref["target"] == "persons" and ref["triangular_closure"] is True and ref["name_similarity"] == 0.7 and ref["name_basis"] == "abbreviation"
    assert ref["type_similarity"] == 1.0 and ref["score"] == 3.74                                                     # 3 x 0.7 + 1 + 0.64, no suffix
    reps = [(x["target"], x["score"]) for x in c if x["source_cols"] == ["rep_id"]]
    assert reps == [("persons", 3.94), ("customers", 1.25)]                                                        # customers: already referenced
    assert next(x for x in c if x["source_cols"] == ["rep_id"] and x["target"] == "customers")["penalties"] == [
        "orders already refers to customers through customer_id"]
    assert not any(x["target"] == "tags" for x in c)                                                              # varchar key, int column
    assert not any(x["source_cols"] == ["note"] for x in c)                                                       # a plain attribute
    assert not any(x["source_cols"] == ["customer_id"] and x["source"] == "orders" for x in c)                     # already a relationship
    assert graphs.suggest(plan(s), check=0)["checked_against_data"] == 0


def test_ship_to_ranks_addresses_first_without_data(shop_plan):
    # The live run on 26 October gave every candidate for orders.ship_to_id the same 1.5 before the data check.
    c = [x for x in graphs.candidates(shop_plan) if x["source_cols"] == ["ship_to_id"]]
    assert [x["target"] for x in c] == ["addresses", "categories", "customers", "products"]
    best = c[0]
    assert best["name_basis"] == "role word" and best["closure_via"] == "orders -> customers <- addresses" and best["closure"] == 0.64
    assert best["score"] == 3.94 and best["score"] > 2 * max(x["score"] for x in c[1:])
    assert "an address role (ship-to, bill-to, mail-to)" in best["why"] and "closes a triangle" in best["why"]
    against = {x["target"]: x["penalties"] for x in c}
    assert against["customers"] == ["orders already refers to customers through customer_id"]
    assert against["products"] == ["order_items already joins orders and products (many-to-many through it)"]
    assert against["addresses"] == [] and against["categories"] == []


def test_final_ranking_combines_inclusion_and_name_score(shop_plan):
    out = graphs.suggest(shop_plan, sqlite_execute())
    ship = [x for x in out["candidates"] if x["source_cols"] == ["ship_to_id"]]
    assert ship[0]["target"] == "addresses" and ship[0]["final_score"] == round(ship[0]["score"] + 3.0, 2)    # 100% of 15 distinct values
    for x in ship[1:]:
        assert x["final_score"] == round(x["score"] + 3.0 * graphs.evidence_strength(x["evidence"]), 2) < ship[0]["final_score"]
    assert [x["final_score"] for x in out["candidates"]] == sorted((x["final_score"] for x in out["candidates"]), reverse=True)
    assert "final_score" in out["note"]
    # two distinct values that all match prove little: the inclusion is damped to a fifth
    assert graphs.evidence_strength({"inclusion": 1.0, "distinct_values": 2}) == 0.2
    assert graphs.evidence_strength({"inclusion": None, "distinct_values": 0}) == 0.0 and graphs.evidence_strength(None) == 0.0
    assert all("final_score" not in x for x in graphs.suggest(shop_plan)["candidates"])                        # no data, no final score


# ------------------------------------------------------------------ dictionary section -----------

def test_data_dictionary_gets_the_graph_section(tpch):
    md = dictionary.data_dictionary(tpch, "tpch", "dbo")
    assert "## Roles, subject areas and ambiguity" in md and "| LINEITEM | fact |" in md and "| REGION | dimension |" in md
    assert "- REGION area:" in md and "cycle through" in md and "would have to leave inactive" in md


# ------------------------------------------------------------------ the MCP tools ----------------

@pytest.fixture
def shop(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src})
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    return "Sales", "shop_lh"


def test_analyze_schema_tool_runs_no_data_queries(shop, monkeypatch):
    ran = []

    def factory(item, tok):
        def execute(sql):
            ran.append(sql)
            return []
        return execute
    monkeypatch.setattr(server, "_execute_factory", factory)
    out = json.loads(server.analyze_schema(*shop, schema="shop"))
    assert ran == [] and out["roles"]["order_items"]["role"] == "fact" and out["summary"].startswith("7 tables, 6 with keys")
    assert "weights" not in out and out["centrality"]["top"][0]["table"] == "customers" and len(out["active_relationships"]) == 6   # the tool answer leaves the constant weights and the per-table maps out (graphs.analyze keeps them)


def test_suggest_relationships_tool_counts_against_the_source(shop, monkeypatch):
    execute = sqlite_execute()
    ran = []

    def factory(item, tok):
        def run(sql):
            ran.append(sql)
            return execute(sql)
        run.close = lambda: ran.append("closed")
        return run
    monkeypatch.setattr(server, "_execute_factory", factory)
    out = json.loads(server.suggest_relationships(*shop, schema="shop", check=3))
    assert out["checked_against_data"] == 3 and out["candidates"][0]["target"] == "addresses" and out["candidates"][0]["evidence"]["inclusion"] == 1.0
    assert sum(1 for s in ran if s.startswith("SELECT COUNT_BIG")) == 3 and ran[-1] == "closed"
    assert "3 checked against the data" in out["summary"]


def test_graph_tools_are_listed_read_only():
    from starlette.testclient import TestClient
    with TestClient(server.build_app()) as client:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        headers={"Accept": "application/json, text/event-stream"})
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
        tools = {t["name"]: t for t in payload["result"]["tools"]}
    for name in ("analyze_schema", "suggest_relationships"):
        assert tools[name]["annotations"]["readOnlyHint"] is True and tools[name]["title"], name
        assert name in server.mcp.instructions
    assert tools["suggest_relationships"]["inputSchema"]["properties"]["check"]["default"] == 15
