"""app_readiness: what an app still needs on a created API, from the definition and one introspection probe."""
import json

from fabric_backend import readiness, seed, server
from fabric_backend.graphql import decode, definition
from fabric_backend.infer import plan

WS = "11111111-1111-1111-1111-111111111111"
SHIP_TO = [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}]


def test_probe_classification():
    assert readiness.classify_probe(200, {"data": {"__schema": {"queryType": {"name": "Query"}}}})["status"] == "on"
    off = readiness.classify_probe(200, {"errors": [{"message": "Introspection is disabled for this API"}]})
    assert off["status"] == "off" and "disabled" in off["detail"]
    assert readiness.classify_probe(403, {})["status"] == "unknown" and readiness.classify_probe(500, None)["status"] == "unknown"
    assert readiness.classify_probe(200, {"data": {"__schema": None}})["status"] == "off"


def test_assessment_names_keyless_and_unlinked_types_and_the_portal_steps():
    desc = server.describe_definition(decode(definition(plan(seed.schema("shop"), confirmed=SHIP_TO), "shop_api", WS, "ep", "SqlAnalyticsEndpoint")))
    out = readiness.assess(desc, {"status": "off", "detail": "Introspection is disabled"}, "https://x/graphql", "shop_api")
    by = {c["check"]: c for c in out["checks"]}
    assert by["api"]["status"] == "ok" and "7 type(s)" in by["api"]["detail"]
    assert by["introspection"]["status"] == "missing" and "Settings (gear) -> Introspection" in by["introspection"]["next_step"]
    assert by["permissions"]["status"] == "unknown" and "Run Queries and Mutations" in by["permissions"]["next_step"]
    assert by["keys"]["status"] == "missing" and by["keys"]["detail"] == "no key: audit_log"
    assert by["relationships"]["status"] == "ok"                                      # ship_to confirmed: everything is linked
    assert by["write_access"]["detail"].startswith("read-only")
    assert out["missing"] == ["introspection", "keys"] and out["unknown"] == ["permissions"]
    assert out["verdict"].startswith("2 check(s) pass; 2 need a step (introspection, keys); 1 cannot be read")
    on = readiness.assess(desc, {"status": "on", "detail": "answered"}, "https://x/graphql", "shop_api")
    assert {c["check"]: c["status"] for c in on["checks"]}["introspection"] == "ok" and on["missing"] == ["keys"]
    two = {"types": [{"type": "a", "by_key": True, "relationships": []}, {"type": "b", "by_key": True, "relationships": []}]}
    alone = readiness.assess(two, {"status": "on"}, "e", "x")
    assert {c["check"]: c for c in alone["checks"]}["relationships"]["status"] == "info"


def test_app_readiness_tool_probes_introspection_with_the_users_token(monkeypatch):
    from test_creating_tools import Resp
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    existing = decode(definition(plan(seed.schema("shop")), "shop_api", WS, "ep-1", "SqlAnalyticsEndpoint"))
    monkeypatch.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None: {"id": "api-1"} if name == "shop_api" else None)
    monkeypatch.setattr(server, "_graphql_definition", lambda ws, api_id, headers: existing)
    posted = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        posted["url"], posted["query"] = url, json["query"]
        return Resp(200, {"errors": [{"message": "Introspection is disabled"}]})
    monkeypatch.setattr(server.requests, "post", fake_post)
    out = json.loads(server.app_readiness("Sales", "shop_api"))
    assert posted["url"].endswith("/graphqlapis/api-1/graphql") and "__schema" in posted["query"]
    assert out["missing"] == ["introspection", "keys"] and out["endpoint"] == posted["url"]
    assert json.loads(server.app_readiness("Sales", "nope"))["kind"] == "not_found"
    monkeypatch.setattr(server.requests, "post", lambda *a, **k: Resp(403, {"error": "no"}))
    out = json.loads(server.app_readiness("Sales", "shop_api"))
    assert {c["check"]: c["status"] for c in out["checks"]}["introspection"] == "unknown"
