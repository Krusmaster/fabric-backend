"""ontology_draft through the remote server, create_ontology through deploy, the stdio tool and the CLI command."""
import base64
import importlib
import json

import pytest
import requests

from fabric_backend import mcp_server, seed, server
from fabric_backend.schema import Schema

dep = importlib.import_module("fabric_backend.deploy")


@pytest.fixture
def shop(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, headers: {"type": "Lakehouse", "id": "lh-1", "displayName": "shop_lh",
                                                                             "sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": "shop_lh"})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    return "Sales", "shop_lh"


def test_ontology_draft_returns_summary_bindings_ttl_definition_and_the_rest_call(shop):
    out = json.loads(server.ontology_draft(*shop, name="shop_ontology", schema="shop"))
    assert out["summary"]["entity_types"] == 7 and out["summary"]["relationship_types"] == 6
    assert out["bindings"][0]["source"] == "shop_lh" and out["ttl"].startswith("@prefix rdf:")
    parts = out["definition_parts"]
    assert "entities/Orders.tmdl" in parts and "keyProperty: order_id" in parts["entities/Orders.tmdl"]
    assert "ONT_SqlEndpoint = x.datawarehouse.fabric.microsoft.com" in parts["tables/Orders.tmdl"]
    assert out["rest"]["url"].endswith("/workspaces/11111111-1111-1111-1111-111111111111/ontologies") and out["rest"]["delegated_scope"] == "Item.ReadWrite.All"
    body = out["rest"]["body"]
    assert body["displayName"] == "shop_ontology" and {p["path"] for p in body["definition"]["parts"]} == set(parts)
    assert "Import ontology" in out["note"] and "error" not in out
    small = json.loads(server.ontology_draft(*shop, name="x", schema="shop", tables=["orders", "customers"]))
    assert {p for p in small["definition_parts"] if p.startswith("entities/")} == {"entities/Orders.tmdl", "entities/Customers.tmdl"}
    bad = json.loads(server.ontology_draft(*shop, name="x", schema="shop", tables=["ghost"]))
    assert bad["kind"] == "bad_input"


def test_create_ontology_is_offered_with_a_dry_run_by_default_and_write_hints():
    from starlette.testclient import TestClient
    with TestClient(server.build_app()) as client:
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        headers={"Accept": "application/json, text/event-stream"})
        body = r.text
        payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
        tools = {t["name"]: t for t in payload["result"]["tools"]}
        assert "ontology_draft" in tools and "create_ontology" in tools
        assert tools["ontology_draft"]["annotations"]["readOnlyHint"] is True
        create = tools["create_ontology"]
        assert create["annotations"]["readOnlyHint"] is False and create["annotations"]["destructiveHint"] is True
        assert create["inputSchema"]["properties"]["dry_run"]["default"] is True
        text = " ".join(create["description"].split())
        assert "Item.ReadWrite.All" in text and "no item is deleted" in text


def test_create_ontology_dry_run_returns_the_parts_and_the_rest_call_and_creates_nothing(shop, monkeypatch):
    monkeypatch.setattr(server, "_create_ontology", lambda *a, **k: pytest.fail("a dry run must not call Fabric"))
    out = json.loads(server.create_ontology(*shop, name="shop_ontology", schema="shop"))
    assert out["dry_run"] is True and out["summary"]["entity_types"] == 7
    assert out["rest"]["url"].endswith("/workspaces/11111111-1111-1111-1111-111111111111/ontologies") and out["rest"]["update"].endswith("/ontologies/{id}/updateDefinition")
    assert out["rest"]["delegated_scope"] == "Item.ReadWrite.All" and out["rest"]["workspace_role"] == "Contributor" and "preview" in out["rest"]["spec"]
    assert {"model.tmdl", "database.tmdl", "namespaces/default.tmdl", ".platform", "entities/Orders.tmdl", "tables/Orders.tmdl", "relationships.tmdl"} <= set(out["parts"])
    assert out["rest"]["parts"] == list(out["parts"])
    bad = json.loads(server.create_ontology(*shop, name="x", schema="shop", tables=["ghost"]))
    assert bad["kind"] == "bad_input"


def test_create_ontology_without_the_permission_answers_consent_naming_the_scope(shop, monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_create_ontology", lambda env, ws, token_provider=None: calls.append(env) or {"status": "Failed", "mode": "created", "http": 403, "body": "InsufficientScopes"})
    out = json.loads(server.create_ontology(*shop, name="shop_ontology", schema="shop", dry_run=False))
    assert out["kind"] == "consent" and "Item.ReadWrite.All" in out["hint"] and "body" not in out["result"] and out["result"]["http"] == 403
    assert calls[0]["displayName"] == "shop_ontology" and calls[0]["definition"]["parts"][0]["payloadType"] == "InlineBase64"
    monkeypatch.setattr(server, "_create_ontology", lambda env, ws, token_provider=None: {"status": "Succeeded", "mode": "updated", "id": "ont-1"})
    out = json.loads(server.create_ontology(*shop, name="shop_ontology", schema="shop", dry_run=False))
    assert out["result"] == {"status": "Succeeded", "mode": "updated", "id": "ont-1"} and out["after_creation"] and "kind" not in out
    monkeypatch.setattr(server, "_create_ontology", lambda env, ws, token_provider=None: {"status": "Timeout", "mode": "created"})
    out = json.loads(server.create_ontology(*shop, name="shop_ontology", schema="shop", dry_run=False))
    assert out["kind"] == "timeout"


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        pass


def test_create_ontology_posts_the_envelope_and_waits_for_the_operation(monkeypatch):
    posted, polls = [], iter([Resp(200, {"status": "Running"}), Resp(200, {"status": "Succeeded"})])
    items = {"value": []}
    monkeypatch.setattr(requests, "get", lambda url, **k: next(polls) if "/operations/" in url else Resp(200, items))
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append((url, k["json"])) or Resp(202, None, {"x-ms-operation-id": "op-9"}))
    monkeypatch.setattr(dep.time, "sleep", lambda s: None)
    env = {"displayName": "shop_ontology", "description": "d", "definition": {"parts": [{"path": "model.tmdl", "payload": base64.b64encode(b"model x").decode(), "payloadType": "InlineBase64"}]}}
    result = dep.create_ontology(env, "ws-1", token_provider=lambda: "tok")
    assert result["status"] == "Succeeded" and result["mode"] == "created"
    assert posted[0][0].endswith("/workspaces/ws-1/ontologies") and posted[0][1]["displayName"] == "shop_ontology"
    # an existing ontology of that name is updated in place through updateDefinition
    items["value"] = [{"displayName": "shop_ontology", "type": "Ontology", "id": "ont-1"}]
    monkeypatch.setattr(requests, "post", lambda url, **k: posted.append((url, k["json"])) or Resp(200, {}))
    result = dep.create_ontology(env, "ws-1", token_provider=lambda: "tok")
    assert result == {"status": "Succeeded", "mode": "updated", "id": "ont-1"} and posted[-1][0].endswith("/ontologies/ont-1/updateDefinition")
    assert "displayName" not in posted[-1][1]
    # Fabric refusing (the scope is missing) comes back with the status and body for the tool to explain
    monkeypatch.setattr(requests, "post", lambda url, **k: Resp(403, {"errorCode": "InsufficientScopes", "message": "Item.ReadWrite.All required"}))
    result = dep.create_ontology(env, "ws-1", token_provider=lambda: "tok")
    assert result["status"] == "Failed" and result["http"] == 403 and "Item.ReadWrite.All" in result["body"]


def test_local_stdio_server_drafts_the_schema_part(monkeypatch):
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: (lambda sql: []))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    out = json.loads(mcp_server.ontology_draft("shop_ontology", schema="shop", tables=["orders", "customers"]))
    assert out["summary"]["entity_types"] == 2 and ":OrdersHasCustomers a owl:ObjectProperty" in out["ttl"]
    assert json.loads(mcp_server.ontology_draft("x", schema="shop", tables=["ghost"]))["kind"] == "bad_input"


def test_cli_ontology_command_writes_the_files(tmp_path, capsys):
    import csv
    from fabric_backend import cli
    rows = seed.schema("shop").to_rows()
    columns = tmp_path / "columns.csv"
    with open(columns, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    assert cli.main(["ontology", str(columns), "--schema", "shop", "--name", "shop ontology", "--workspace", "ws-1", "--source-item", "lh-1",
                     "--source-name", "shop_lh", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "ontology" / "shop_ontology" / "definition" / "entities" / "Orders.tmdl").exists()
    assert (tmp_path / "ontology" / "shop_ontology" / "shop_ontology.ttl").exists()
    assert "wrote" in capsys.readouterr().out


def test_a_big_schema_keeps_summary_bindings_and_ttl_and_drops_the_definition(shop, monkeypatch):
    import random
    from fabric_backend.schema import Column, Schema as _Schema, Table
    rnd = random.Random(3)
    big = _Schema(schema="dbo")
    names = [f"table_{i}" for i in range(120)]
    for n in names:
        cols = [Column(f"{n}_id", "int")] + [Column(f"{names[rnd.randrange(120)]}_id" if rnd.random() < 0.3 else f"col{j}", "int") for j in range(10)]
        big.tables[n] = Table(n, cols, schema="dbo")
    monkeypatch.setattr(_Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: big))
    out = json.loads(server.ontology_draft(*shop, name="big", schema="dbo"))
    assert "definition_parts" not in out and "body" not in out["rest"] and "the definition" in out["omitted"]
    assert out["summary"]["entity_types"] == 120 and out["bindings"] and out["rest"]["url"].endswith("/ontologies")
    assert len(json.dumps(out, indent=2)) <= server.MAX_RESULT_CHARS
    # a medium schema keeps the TTL and loses only the definition
    medium = _Schema(schema="dbo")
    for n in names[:8]:
        medium.tables[n] = big.tables[n]
    monkeypatch.setattr(_Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: medium))
    out = json.loads(server.ontology_draft(*shop, name="medium", schema="dbo"))
    assert "definition_parts" not in out and out["ttl"].count(" a owl:Class ;") == 8 and "the TTL" not in out["omitted"]
