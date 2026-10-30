"""create_report (round n64): an empty Power BI report bound to a semantic model, with the REST calls mocked the way
test_creating_tools.py mocks create_semantic_model: the dry run, 201, 202 with a long-running operation, 403 as a
missing scope, a report of that name already there, a model that is not, and tools/list."""
import asyncio
import importlib
import json

import pytest
import requests

from fabric_backend import report, server
from fabric_backend.deploy import FABRIC
from fabric_backend.errors import HINTS

deploy = importlib.import_module("fabric_backend.deploy")     # the package exports a function of that name
WS = "11111111-1111-1111-1111-111111111111"
MODEL_ID = "22222222-2222-2222-2222-222222222222"
ITEMS = {"value": [{"id": MODEL_ID, "displayName": "shop_model", "type": "SemanticModel"},
                   {"id": "rp-0", "displayName": "old_report", "type": "Report"}]}


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


@pytest.fixture
def fabric(monkeypatch):
    """Fabric answered from memory: the item list for the lookups, and whatever `post` is set to for the create."""
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(deploy.time, "sleep", lambda s: None)
    gets, posts = [], []

    def get(url, **k):
        gets.append(url)
        if "/operations/" in url:
            return next(state["polls"])
        return Resp(200, state["after"] if posts and "after" in state else ITEMS)     # the item list once the create has run

    state = {"polls": iter([]), "post": lambda url, json, **k: Resp(500)}
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", lambda url, **k: posts.append((url, k.get("json"))) or state["post"](url, k.get("json")))
    state["gets"], state["posts"] = gets, posts
    return state


def test_payload_has_the_model_reference_and_no_definition():
    body = report.payload("shop_report", MODEL_ID, WS, "x" * 300)
    assert body["displayName"] == "shop_report" and "definition" not in body and len(body["description"]) == 256
    assert body["creationPayload"] == {"semanticModelReference": {"referenceType": "ById", "itemId": MODEL_ID, "workspaceId": WS}}
    assert "description" not in report.payload("r", MODEL_ID, WS)


def test_dry_run_shows_the_call_and_posts_nothing(fabric):
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report"))
    assert out["dry_run"] is True and fabric["posts"] == [] and "error" not in out
    assert out["rest"]["method"] == "POST" and out["rest"]["url"] == f"{FABRIC}/v1/workspaces/{WS}/reports"
    assert out["rest"]["body"]["creationPayload"]["semanticModelReference"] == {"referenceType": "ById", "itemId": MODEL_ID, "workspaceId": WS}
    assert "definition" not in out["rest"]["body"] and out["rest"]["delegated_scope"] == "Report.ReadWrite.All or Item.ReadWrite.All"
    assert out["report"]["pages"] == 1 and out["report"]["visuals"] == 0 and out["report"]["bound_to"] == {"semantic_model": "shop_model", "id": MODEL_ID}
    assert "blank page" in out["report"]["empty"] and any("Power BI Desktop" in s for s in out["after_creation"])
    assert "Fabric portal" in out["after_creation"][0] and "Not yet run against a live workspace" in out["note"]


def test_model_given_as_an_id_is_used_as_is(fabric):
    out = json.loads(server.create_report("Sales", MODEL_ID, "shop_report"))
    assert out["report"]["bound_to"]["id"] == MODEL_ID and out["rest"]["body"]["creationPayload"]["semanticModelReference"]["itemId"] == MODEL_ID
    assert fabric["posts"] == []


def test_201_creates_once_and_returns_the_id(fabric):
    fabric["post"] = lambda url, json: Resp(201, {"id": "rp-1", "displayName": "shop_report", "type": "Report", "workspaceId": WS})
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["result"] == {"status": "Succeeded", "mode": "created", "id": "rp-1"} and "error" not in out
    url, body = fabric["posts"][0]
    assert url == f"{FABRIC}/v1/workspaces/{WS}/reports" and body["displayName"] == "shop_report" and "definition" not in body
    assert len(fabric["posts"]) == 1 and not any("updateDefinition" in u for u in fabric["gets"])
    assert "fabric-token" not in json.dumps(out)


def test_202_waits_for_the_operation_then_finds_the_id(fabric):
    fabric["post"] = lambda url, json: Resp(202, None, {"x-ms-operation-id": "op-1"})
    fabric["polls"] = iter([Resp(200, {"status": "Running"}), Resp(200, {"status": "Succeeded"})])
    fabric["after"] = {"value": ITEMS["value"] + [{"id": "rp-2", "displayName": "shop_report", "type": "Report"}]}
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["result"] == {"status": "Succeeded", "mode": "created", "id": "rp-2"} and "error" not in out
    assert sum("/operations/op-1" in u for u in fabric["gets"]) == 2 and len(fabric["posts"]) == 1


def test_operation_that_fails_is_explained(fabric):
    fabric["post"] = lambda url, json: Resp(202, None, {"x-ms-operation-id": "op-2"})
    fabric["polls"] = iter([Resp(200, {"status": "Failed", "error": {"errorCode": "InvalidRequest", "message": "model not readable"}})])
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["result"]["status"] == "Failed" and out["kind"] in ("fabric_error", "unexpected") and "model not readable" in out["error"]


def test_403_without_the_scope_is_consent_naming_it(fabric):
    fabric["post"] = lambda url, json: Resp(403, {"errorCode": "InsufficientScopes", "message": "The caller lacks the required scope"})
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["kind"] == "consent" and out["scope"] == "Report.ReadWrite.All (or Item.ReadWrite.All)"
    assert "Report.ReadWrite.All" in out["hint"] and "docs/SCOPES.md" in out["hint"] and out["fabric_error_code"] == "InsufficientScopes"
    assert "fabric-token" not in json.dumps(out) and "Bearer" not in json.dumps(out)
    fabric["post"] = lambda url, json: Resp(403, {"errorCode": "InsufficientPrivileges", "message": "not enough"})
    out = json.loads(server.create_report("Sales", "shop_model", "shop_report", dry_run=False))
    assert out["kind"] == "no_access" and "Contributor" in out["hint"]


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_report_of_that_name_is_left_alone(fabric, dry_run):
    out = json.loads(server.create_report("Sales", "shop_model", "old_report", dry_run=dry_run))
    assert out["kind"] == "already_exists" and out["existing"] == {"id": "rp-0", "name": "old_report"}
    assert "nothing was created" in out["error"] and "never updates or deletes" in out["hint"]
    assert fabric["posts"] == [] and "rest" not in out


def test_a_model_that_is_not_there_is_not_found(fabric):
    out = json.loads(server.create_report("Sales", "ghost_model", "shop_report", dry_run=False))
    assert out["kind"] == "not_found" and "ghost_model" in out["error"] and "create_semantic_model" in out["hint"]
    assert fabric["posts"] == []


def test_the_listing_marks_it_as_a_creating_tool_with_short_descriptions():
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "create_report")
    a = tool.annotations
    assert a.read_only_hint is False and a.destructive_hint is True and a.idempotent_hint is True
    assert a.title == "Create an empty Power BI report on a semantic model (dry run by default)"
    props = tool.input_schema["properties"]
    assert set(props) == {"workspace", "model", "name", "dry_run"} and set(tool.input_schema["required"]) == {"workspace", "model", "name"}
    assert all(props[p]["description"] for p in props) and props["dry_run"]["default"] is True
    text = " ".join(tool.description.split())
    assert "one blank page, no visuals" in text and "{error, kind, hint}" in text and "already_exists" in text and len(text) < 700
    assert "already_exists" in HINTS and "never updates or deletes" in HINTS["already_exists"]
