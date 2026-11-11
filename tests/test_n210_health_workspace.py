"""n210: the Data product page asks /health with the Model item's own workspace (n200's contract: 'workspace' and
'item_id' are the Model's). The Model's definition is read there; the lakehouse is then found in source.json's
workspace, which may be another one. Before n210 the page sent the source's workspace, so a Model kept in another
workspace than its source got a 404 instead of a health word."""
import base64
import json

from fabric_backend import lineage, workload_api

MODEL_WS = "aaaaaaaa-0000-4000-8000-000000000001"
SOURCE_WS = "bbbbbbbb-0000-4000-8000-000000000002"
ITEM = "cccccccc-0000-4000-8000-000000000003"


def test_the_definition_is_read_in_the_models_workspace_and_the_lakehouse_in_the_sources(monkeypatch):
    source = {"workspaceId": SOURCE_WS, "itemId": "lh-1", "itemType": "Lakehouse", "displayName": "demo_lh"}
    outputs = {"product": {"plan": {"plan_id": "plan-0123abcd"}}}
    parts = [{"path": k, "payload": base64.b64encode(json.dumps(v).encode()).decode()}
             for k, v in (("source.json", source), ("outputs.json", outputs))]
    asked = []

    class R:
        def json(self):
            return {"definition": {"parts": parts}}
    monkeypatch.setattr(lineage, "_definition_response", lambda url, headers: asked.append(url) or R())
    req = workload_api.health_request({"workspace": MODEL_WS, "item_id": ITEM, "product": "Shop sales"})
    got = workload_api._health_target(req, {})
    assert asked == [f"https://api.fabric.microsoft.com/v1/workspaces/{MODEL_WS}/items/{ITEM}/getDefinition"]
    assert got["workspace"] == SOURCE_WS and got["source"] == "lh-1"
    assert got["products"] == [{"name": "Shop sales", "plan_id": "plan-0123abcd"}]
