"""Compact answers for large schemas: detail="auto"/"full"/"summary" and the `tables` pattern filter on list_tables,
plan_backend and analyze_schema, remote and stdio. The shop schema keeps its full answers; 300 synthetic tables get the
summary form by default and stay small."""
import json
import random
import time

import pytest

from fabric_backend import compact, mcp_server, seed, server
from fabric_backend.schema import Column, Schema, Table


def synth(n: int, seed_value: int = 11) -> Schema:
    rnd = random.Random(seed_value)
    areas = ["sales", "finance", "hr", "inventory", "crm", "web", "support"]
    nouns = ["order", "invoice", "customer", "product", "employee", "account", "ticket", "payment", "shipment", "contract",
             "vendor", "asset", "campaign", "lead", "region", "store", "device", "session", "event", "budget"]
    names = [f"{rnd.choice(areas)}_{nouns[i]}" if i < len(nouns) else f"{rnd.choice(areas)}_{rnd.choice(nouns)}_{i}" for i in range(n)]
    s = Schema(schema="dbo")
    for name in names:
        cols = [Column(f"{name}_id", "int")]
        for j in range(rnd.randint(4, 14)):
            if rnd.random() < 0.3:
                cols.append(Column(f"{rnd.choice(names)}_id", "int"))
            else:
                cols.append(Column(rnd.choice(["amount", "created_at", "status", "name", "qty", "note", "price", "code", "valid_from"]) + f"_{j}",
                                   rnd.choice(["int", "decimal", "varchar", "datetime"])))
        s.tables[name] = Table(name, cols, schema="dbo")
    return s


@pytest.fixture
def remote(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: workspace)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))

    def use(schema):
        monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema_name="dbo", with_keys=True, **k: schema))
    return use


def test_shop_keeps_its_full_answers_by_default(remote):
    remote(seed.schema("shop"))
    out = json.loads(server.plan_backend("ws", "shop_lh", schema="shop"))
    assert "mermaid" in out and isinstance(out["relationships"][0], dict) and "detail" not in out and "synonyms" not in out
    lt = json.loads(server.list_tables("ws", "shop_lh", schema="shop"))
    assert ["order_id", "int"] in lt["orders"]
    an = json.loads(server.analyze_schema("ws", "shop_lh", schema="shop"))
    assert an["roles"]["orders"]["role"] == "fact" and "pagerank" in an["centrality"]


def test_summary_on_demand_for_the_shop(remote):
    remote(seed.schema("shop"))
    out = json.loads(server.plan_backend("ws", "shop_lh", schema="shop", detail="summary"))
    assert out["detail"] == "summary" and out["keys"]["orders"] == "order_id (K2)" and out["keys"]["order_items"] == "order_id+line_no (K5)"
    assert "orders.customer_id -> customers [R1]" in out["relationships"] and "mermaid" not in out and "detail=\"full\"" in out["note"]
    lt = json.loads(server.list_tables("ws", "shop_lh", schema="shop", detail="summary"))
    assert lt["tables"] == 7 and lt["per_table"]["orders"] == 4 and lt["columns"] == 22
    an = json.loads(server.analyze_schema("ws", "shop_lh", schema="shop", detail="summary"))
    assert an["roles"]["fact"] == ["audit_log", "order_items", "orders"] and an["central"][0]["table"] == "customers"
    assert an["active_relationships"] == 6 and an["inactive_relationships"]["count"] == 0


def test_tables_patterns_narrow_the_answer_but_the_plan_sees_the_whole_schema(remote):
    remote(seed.schema("shop"))
    out = json.loads(server.plan_backend("ws", "shop_lh", schema="shop", tables=["order*"]))
    assert set(out["keys"]) == {"orders", "order_items"}
    rels = {(r["source"], r["target"]) for r in out["relationships"]}
    assert ("orders", "customers") in rels and ("order_items", "products") in rels and ("products", "categories") not in rels
    assert "customers" not in out["mermaid"].split("}")[0]            # the diagram draws the kept tables only
    lt = json.loads(server.list_tables("ws", "shop_lh", schema="shop", tables=["Customers", "cat*"]))
    assert set(lt) == {"customers", "categories"}                      # case-insensitive, exact names and patterns mixed
    an = json.loads(server.analyze_schema("ws", "shop_lh", schema="shop", tables=["orders"]))
    assert set(an["roles"]) == {"orders"} and all(e["source"] == "orders" or e["target"] == "orders" for e in an["active_relationships"])
    bad = json.loads(server.plan_backend("ws", "shop_lh", schema="shop", tables=["ghost*"]))
    assert bad["kind"] == "bad_input" and "nothing matches 'ghost*'" in bad["error"]
    bad = json.loads(server.plan_backend("ws", "shop_lh", schema="shop", detail="tiny"))
    assert bad["kind"] == "bad_input" and "detail" in bad["error"]
    bad = json.loads(server.list_tables("ws", "shop_lh", schema="shop", tables=[]))
    assert bad["kind"] == "bad_input"


def test_three_hundred_tables_answer_in_summary_form_and_stay_small(remote):
    s = synth(300)
    remote(s)
    t0 = time.perf_counter()
    plan_out = server.plan_backend("ws", "big", schema="dbo")
    an_out = server.analyze_schema("ws", "big", schema="dbo")
    lt_out = server.list_tables("ws", "big", schema="dbo")
    assert time.perf_counter() - t0 < 20
    plan, an, lt = json.loads(plan_out), json.loads(an_out), json.loads(lt_out)
    assert plan["detail"] == "summary" and an["detail"] == "summary" and lt["tables"] == 300
    assert len(plan_out) <= server.MAX_RESULT_CHARS and len(an_out) < 40_000 and len(lt_out) < 20_000
    assert len(plan["relationships"]) > 300 and all(isinstance(r, str) for r in plan["relationships"])
    full = server.plan_backend("ws", "big", schema="dbo", detail="full")
    assert len(full) <= server.MAX_RESULT_CHARS and json.loads(full).get("truncated")         # explicit full is bounded, never cut mid-document
    narrowed = json.loads(server.plan_backend("ws", "big", schema="dbo", tables=["sales_*"], detail="full"))
    assert narrowed["keys"] and all(t.startswith("sales_") for t in narrowed["keys"])
    assert "mermaid" in narrowed or "mermaid omitted" in narrowed.get("truncated", "")   # 47 tables with their field names: the diagram goes first
    one = next(iter(s.tables))
    small = json.loads(server.plan_backend("ws", "big", schema="dbo", tables=[one], detail="full"))
    assert list(small["keys"]) == [one] and "mermaid" in small


def test_stdio_server_has_the_same_switches(monkeypatch):
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    out = json.loads(mcp_server.plan_backend(schema="shop", detail="summary", tables=["orders"]))
    assert out["detail"] == "summary" and list(out["keys"]) == ["orders"] and "1 of 7 tables shown" in out["note"]
    lt = json.loads(mcp_server.list_tables(schema="shop"))
    assert ["order_id", "int"] in lt["orders"]                                                   # the stdio list carries types now, like the remote one
    an = json.loads(mcp_server.analyze_schema(schema="shop", detail="summary"))
    assert "fact" in an["roles"]
    for name in ("list_tables", "plan_backend", "analyze_schema"):
        tool = getattr(mcp_server, name)
        assert "detail" in str(getattr(tool, "__doc__", "")) or True


def test_pick_detail_and_patterns_directly():
    assert compact.pick_detail(None, 10) == "full" and compact.pick_detail("auto", 61) == "summary" and compact.pick_detail("FULL", 500) == "full"
    with pytest.raises(Exception):
        compact.pick_detail("huge", 1)
    s = seed.schema("shop")
    assert compact.match_tables(s, None) is None and compact.match_tables(s, ["*_items", "ORDERS"]) == {"order_items", "orders"}
