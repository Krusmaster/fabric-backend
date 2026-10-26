"""export_item_definitions: what the creating tools would create, as folders in Fabric's Git format, built from the same
REST bodies the tools send; nothing is created and no Git provider is called."""
import base64
import json
import re
import uuid

import pytest
import requests

from fabric_backend import git_export, gold, notebook, seed, semantic_model, server, silver
from fabric_backend.graphql import definition
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

WS = "11111111-1111-1111-1111-111111111111"
PLATFORM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"


@pytest.fixture
def shop(monkeypatch):
    kind = {"type": "Lakehouse", "schemas_enabled": True}
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": kind["type"], "id": "lh-1", "displayName": src, "sql_host": "x",
                                                                             "sql_db": src, "schemas_enabled": kind["schemas_enabled"]})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(server, "source_for", lambda ws, item, headers: ("ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("an export posts nothing"))
    return kind


def test_every_item_is_a_folder_with_a_platform_file_and_its_definition(shop):
    out = json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", names={"create_backend": "shop_api"}))
    # everything at once is over the 60 000 characters of one answer: the largest file is named under `omitted`, not lost
    assert out["omitted"] == ["silver_shop.Notebook/notebook-content.py"] and "pass `items`" in out["note"]
    files = {**out["files"], **json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", items=["create_silver_notebook"]))["files"]}
    folders = {e["folder"] for e in out["items"]}
    assert folders == {"shop_api.GraphQLApi", "shop_lh_model.SemanticModel", "krusgraph-sql", "silver_shop.Notebook",
                       "drift_monitor_shop.Notebook", "drift_monitor_shop_nightly.DataPipeline", "gold_shop.Notebook"}
    for f in folders - {"krusgraph-sql"}:
        pf = json.loads(files[f"{f}/.platform"])
        assert pf["$schema"] == PLATFORM_SCHEMA and pf["config"]["version"] == "2.0" and f == f"{pf['metadata']['displayName']}.{pf['metadata']['type']}"
        assert uuid.UUID(pf["config"]["logicalId"]).int != 0
        assert not any(k.startswith(f + "/") and k.endswith(".md") for k in files)        # Fabric deletes non-definition files in item folders
    assert json.loads(files["shop_api.GraphQLApi/graphql-definition.json"])["datasources"][0]["sourceItemId"] == "ep-1"
    assert {"shop_lh_model.SemanticModel/definition.pbism", "shop_lh_model.SemanticModel/definition/model.tmdl",
            "shop_lh_model.SemanticModel/definition/tables/orders.tmdl", "shop_lh_model.SemanticModel/definition/relationships.tmdl"} <= set(files)
    assert files["silver_shop.Notebook/notebook-content.py"].startswith("# Fabric notebook source")
    assert "CREATE OR REPLACE MATERIALIZED LAKE VIEW" in files["gold_shop.Notebook/notebook-content.py"]
    assert json.loads(files["drift_monitor_shop_nightly.DataPipeline/pipeline-content.json"])
    assert "CREATE OR ALTER VIEW" in files["krusgraph-sql/krusgraph-views.sql"] and "git-integration.md" in files["krusgraph-sql/krusgraph-views.sql"]
    assert "Source control -> Updates -> Update all" in files["KRUSGRAPH-EXPORT.md"] and out["skipped"] == []
    assert any("notebook reference" in n or "Notebook activity" in n for n in out["notes"])


def test_the_files_are_the_parts_the_creating_tools_send(shop):
    out = {"files": {}, "items": []}
    for tool in ("create_backend", "create_semantic_model", "create_silver_notebook", "create_gold_views"):
        one = json.loads(server.export_item_definitions("Sales", "shop_lh", schema="shop", items=[tool]))
        assert "omitted" not in one
        out["files"].update(one["files"])
        out["items"] += one["items"]
    p = plan(seed.schema("shop"))
    info = dict(workspace_id=WS, item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop", sql_endpoint="x", sql_db="shop_lh",
                schemas_enabled=True)

    def parts(body):
        return {x["path"]: base64.b64decode(x["payload"]).decode() for x in body["definition"]["parts"]}
    api = parts(definition(p, "shop_lh_api", WS, "ep-1", "SqlAnalyticsEndpoint"))
    assert json.loads(out["files"]["shop_lh_api.GraphQLApi/graphql-definition.json"]) == json.loads(api["graphql-definition.json"])
    sm = parts(semantic_model.envelope(semantic_model.draft(p, info, "shop_lh_model")["parts"], "shop_lh_model"))
    for path, text in sm.items():
        if path != ".platform":
            assert out["files"][f"shop_lh_model.SemanticModel/{path}"] == text, path
    nb = parts(notebook.envelope("silver_shop", silver.notebook_source(silver.spec(p, info))))
    assert out["files"]["silver_shop.Notebook/notebook-content.py"] == nb["notebook-content.py"]
    gnb = parts(notebook.envelope("gold_shop", gold.notebook_source(gold.spec(p, info))))
    assert out["files"]["gold_shop.Notebook/notebook-content.py"] == gnb["notebook-content.py"]
    assert {e["tool"] for e in out["items"]} == {"create_backend", "create_semantic_model", "create_silver_notebook", "create_gold_views"}


def test_a_warehouse_gets_no_notebooks_and_unknown_items_are_refused(shop):
    shop["type"] = "Warehouse"
    out = json.loads(server.export_item_definitions("Sales", "wh", schema="shop"))
    assert {s["tool"] for s in out["skipped"]} == {"create_silver_notebook", "create_drift_monitor", "create_gold_views"}
    assert not any(k.endswith("notebook-content.py") for k in out["files"])
    bad = json.loads(server.export_item_definitions("Sales", "wh", schema="shop", items=["create_everything"]))
    assert bad["kind"] == "bad_input" and "create_everything" in bad["error"]
    shop["type"], shop["schemas_enabled"] = "Lakehouse", False
    out = json.loads(server.export_item_definitions("Sales", "lh", schema="dbo", items=["create_gold_views"]))
    assert out["skipped"] == [{"tool": "create_gold_views", "why": "materialized lake views need a lakehouse created with schemas"}]


def test_folder_names_write_unsafe_characters_as_html_numbers():
    assert git_export.folder("Sales/EU: v2", "SemanticModel") == "Sales&#47;EU&#58; v2.SemanticModel"
    a, b = (json.loads(git_export.platform("Notebook", n))["config"]["logicalId"] for n in ("one", "one"))
    assert a == b and json.loads(git_export.platform("Notebook", "two"))["config"]["logicalId"] != a     # stable per item, unique per name
