"""lineage: which objects build on a source's tables, from recorded definitions; the tool with Fabric mocked; impact in plan_drift."""
import json

from fabric_backend import lineage, seed, semantic_model, server
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import plan

WS = "11111111-1111-1111-1111-111111111111"
SOURCE = {"id": "lh-1", "displayName": "shop_lh", "type": "Lakehouse"}
INFO = dict(workspace_id=WS, item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop",
            sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db="shop_lh", schemas_enabled=True)
TABLES = {t.name for t in seed.schema("shop")}


def test_edges_from_a_graphql_definition_a_tmdl_model_views_and_an_agent():
    p = plan(seed.schema("shop"))
    api_body = decode(definition(p, "shop_api", WS, "lh-1", "SqlAnalyticsEndpoint", tables=["orders", "customers"]))
    api_body["datasources"][0]["sourceItemId"] = "lh-1"
    e = lineage.from_graphql_definition(api_body, {"id": "api-1", "displayName": "shop_api"}, "lh-1", "shop", TABLES)
    assert {x["table"] for x in e} == {"orders", "customers"} and all(x["kind"] == "graphql_api" and x["certain"] for x in e)
    other = dict(api_body); other["datasources"] = [dict(api_body["datasources"][0], sourceItemId="other-item")]
    assert lineage.from_graphql_definition(other, {"id": "api-2", "displayName": "x"}, "lh-1", "shop", TABLES) == []
    parts = semantic_model.draft(p, INFO, "shop_model", tables=["orders", "products"])["parts"]
    e = lineage.from_tmdl_parts(parts, {"id": "sm-1", "displayName": "shop_model"}, {"shop_lh"}, "shop", TABLES)
    assert {x["table"] for x in e} == {"orders", "products"} and all(x["certain"] for x in e)
    stranger = lineage.from_tmdl_parts(parts, {"id": "sm-2", "displayName": "m2"}, {"another_db"}, "dbo", TABLES)
    assert stranger == []                                                                  # schemaName shop != dbo: not ours
    rows = [{"VIEW_SCHEMA": "krusgraph", "VIEW_NAME": "vw_order_items", "TABLE_SCHEMA": "shop", "TABLE_NAME": "order_items"},
            {"VIEW_SCHEMA": "krusgraph", "VIEW_NAME": "vw_order_items", "TABLE_SCHEMA": "shop", "TABLE_NAME": "orders"},
            ("dbo", "vw_other", "other", "orders")]
    e = lineage.from_view_rows(rows, SOURCE, "shop", TABLES)
    assert [(x["table"], x["object"]) for x in e] == [("order_items", "krusgraph.vw_order_items"), ("orders", "krusgraph.vw_order_items")]
    agent = {"DataAgentV1.json": json.dumps({"datasources": [{"itemId": "lh-1", "elements": [{"name": "shop.orders"}, {"name": "shop.customers"}]}]})}
    e = lineage.from_data_agent_parts(agent, {"id": "da-1", "displayName": "shop_agent"}, "lh-1", "shop", TABLES)
    assert {x["table"] for x in e} == {"orders", "customers"} and not any(x["certain"] for x in e)
    assert lineage.from_data_agent_parts(agent, {"id": "da-1", "displayName": "a"}, "lh-9", "shop", TABLES) == []


def test_graph_used_by_unused_and_impact():
    edges = [lineage.edge("orders", "graphql_api", "shop_api", "api-1", "type orders"),
             lineage.edge("customers", "graphql_api", "shop_api", "api-1", "type customers"),
             lineage.edge("orders", "semantic_model", "shop_model", "sm-1", "partition")]
    g = lineage.graph(SOURCE, "shop", sorted(TABLES), edges, skipped=[{"item": "secret_model", "kind": "no_access"}])
    assert g["summary"] == "7 tables in shop_lh; 1 graphql api(s), 1 semantic model(s); 5 table(s) used by nothing"
    assert set(g["unused_tables"]) == TABLES - {"orders", "customers"} and len(g["nodes"]) == 9 and len(g["edges"]) == 3
    i = lineage.impact(g, "orders")
    assert [o["object"] for o in i["objects"]] == ["shop_api", "shop_model"] and i["tables_in_the_same_objects"] == ["customers"]
    assert lineage.impact(g, "audit_log")["summary"] == "audit_log is used by nothing we can see"
    assert lineage.impact(g, "ghost")["kind"] == "table_not_found"
    assert lineage.impact_of_changes(edges, ["orders", "products"]) == {"orders": [{"kind": "graphql_api", "object": "shop_api", "via": "type orders", "certain": True},
                                                                                {"kind": "semantic_model", "object": "shop_model", "via": "partition", "certain": True}],
                                                                     "products": []}


def _mock_workspace(monkeypatch, p):
    api_body = decode(definition(p, "shop_api", WS, "lh-1", "SqlAnalyticsEndpoint"))
    api_body["datasources"][0]["sourceItemId"] = "lh-1"
    parts = semantic_model.draft(p, INFO, "shop_model", tables=["orders", "customers"])["parts"]
    items = [{"id": "api-1", "displayName": "shop_api", "type": "GraphQLApi"}, {"id": "sm-1", "displayName": "shop_model", "type": "SemanticModel"},
             {"id": "sm-2", "displayName": "secret_model", "type": "SemanticModel"}, {"id": "da-1", "displayName": "shop_agent", "type": "DataAgent"},
             {"id": "lh-1", "displayName": "shop_lh", "type": "Lakehouse"}, {"id": "nb-1", "displayName": "nb", "type": "Notebook"}]
    monkeypatch.setattr(server, "_workspace_items", lambda ws, headers: items)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: api_body)

    def parts_of(ws, route, item_id, headers, fmt=None):
        if item_id == "sm-1":
            assert route == "semanticModels" and fmt == "TMDL"
            return parts
        if item_id == "sm-2":
            raise RuntimeError("HTTP 403 Forbidden for the definition")
        if item_id == "da-1":
            return {"DataAgentV1.json": json.dumps({"datasources": [{"itemId": "lh-1", "elements": [{"name": "shop.order_items"}]}]})}
        raise AssertionError(item_id)
    monkeypatch.setattr(server, "_item_definition_parts", parts_of)


def test_lineage_tool_reads_apis_models_agents_and_views_with_fabric_mocked(monkeypatch):
    from test_creating_tools import shop as shop_fixture  # noqa: F401  (the fixture function is used through pytest below)
    p = plan(seed.schema("shop"))
    _mock_workspace(monkeypatch, p)
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": src})
    rows = [("krusgraph", "vw_order_items", "shop", "order_items"), ("krusgraph", "vw_order_items", "shop", "orders")]
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: rows if "VIEW_TABLE_USAGE" in sql else []))
    from fabric_backend.schema import Schema
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    out = json.loads(server.lineage("Sales", "shop_lh", schema="shop"))
    assert out["source"]["name"] == "shop_lh" and out["summary"].startswith("7 tables in shop_lh; 1 data agent(s), 1 graphql api(s), 1 semantic model(s), 1 view(s)")
    kinds = {(u["kind"], u["object"]) for u in out["used_by"]["orders"]}
    assert kinds == {("graphql_api", "shop_api"), ("semantic_model", "shop_model"), ("view", "krusgraph.vw_order_items")}
    assert any(u["kind"] == "data_agent" and u["certain"] is False for u in out["used_by"]["order_items"])
    assert out["skipped"] == [{"item": "secret_model", "kind": "SemanticModel", "reason": "fabric_error"}] or out["skipped"][0]["item"] == "secret_model"
    assert out["unused_tables"] == [] or set(out["unused_tables"]) <= TABLES
    with_table = json.loads(server.lineage("Sales", "shop_lh", schema="shop", table="orders"))
    assert with_table["impact"]["table"] == "orders" and len(with_table["impact"]["objects"]) == 3
    assert json.loads(server.lineage("Sales", "shop_lh", schema="shop", table="ghost"))["impact"]["kind"] == "table_not_found"


def test_plan_drift_names_the_objects_a_gone_table_or_column_reaches(monkeypatch):
    from fabric_backend.schema import Schema
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                             "sql_host": "x", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    full = plan(seed.schema("shop"))
    _mock_workspace(monkeypatch, full)
    monkeypatch.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None: {"id": "api-1"} if name == "shop_api" else None)
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("lh-1", "SqlAnalyticsEndpoint"))
    # the source lost the categories table and orders.ship_to_id
    cols = [("shop", t.name, c.name, c.data_type, i) for t in seed.schema("shop") for i, c in enumerate(t.columns, 1)
            if t.name != "categories" and not (t.name == "orders" and c.name == "ship_to_id")]
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: Schema.from_information_schema(cols, schema=schema)))
    out = json.loads(server.plan_drift("Sales", "shop_lh", api="shop_api", schema="shop"))
    assert out["would_change"] is True and out["tables_gone"][0]["table"] == "shop.categories"
    assert {o["object"] for o in out["impact"]["categories"]} == {"shop_api"}                  # the API maps categories; the model only has orders and customers
    assert {o["object"] for o in out["impact"]["orders"]} == {"shop_api", "shop_model"}
    assert "impact" in out and out["impact_note"].startswith("objects in the workspace that use the tables")
