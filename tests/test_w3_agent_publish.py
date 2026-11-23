"""W3 (Gustav's run of 23 November 2026): the data agent card's "Make it available in Copilot" step
(POST /workload/v1/agent-publish). It reuses agent_publish.py: a dry run by default that only reads (the agent item and
the Microsoft 365 Copilot preflight) and says what is needed and what would be done; publishing in Fabric only with the
dry run's confirm, once; "Publish to Agent Store" stays the person's step in Fabric (no documented API). Fabric doubles
only; nothing is sent to Fabric."""
import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from fabric_backend import agent_publish, billing  # noqa: E402
from test_workload_api import _post, _writes, api, keys, tok  # noqa: E402,F401

AGENT = "dddddddd-0000-4000-8000-0000000000a1"
BODY = {"workspace": gs.WS, "agent_id": AGENT, "name": "shop_agent", "source_name": "demo_lh"}


@pytest.fixture
def agent(api, monkeypatch):
    client, fake, obo, priv = api
    real = fake._route
    state = {"publish": 200}

    def route(method, url, body=None):
        if method == "GET" and url.endswith(f"/workspaces/{gs.WS}/items/{AGENT}"):
            fake.calls.append((method, url))
            return gs.Response(200, {"id": AGENT, "displayName": "shop_agent", "type": "DataAgent"})
        if method == "POST" and url.endswith(f"/dataAgents/{AGENT}/staging/publish"):
            fake.calls.append((method, url))
            fake.created.append({"route": "publish", "body": body})
            return gs.Response(state["publish"], {})
        return real(method, url, body)
    monkeypatch.setattr(fake, "_route", route)
    return client, fake, priv, state


def test_the_dry_run_says_what_is_needed_and_what_would_be_done_and_writes_nothing(agent):
    client, fake, priv, _ = agent
    fake.calls.clear()
    out = _post(client, "/agent-publish", BODY, tok(priv)).json()
    assert out["confirm"].startswith("agent-") and out["published"] is False and "Nothing was created" in out["note"]
    names = [r["requirement"] for r in out["requirements"]]
    assert names[0] == "Paid capacity, F2 or higher (or P1 or higher)" and any("licence" in n for n in names)
    assert all(r["doc"].startswith("https://learn.microsoft.com/") for r in out["requirements"])
    assert [p["by"] for p in out["plan"]] == ["Krusgraph, as you", "you, in Fabric"]
    assert out["plan"][1]["how"] == agent_publish.COPILOT_STEP and "no API" in out["copilot_step"]
    assert _writes(fake) == [] and not fake.created                        # reads only: no write in the dry run


def test_publishing_needs_the_dry_runs_confirm_and_sends_one_call(agent):
    client, fake, priv, _ = agent
    dry = _post(client, "/agent-publish", BODY, tok(priv)).json()
    for wrong in (None, "agent-0000"):
        no = _post(client, "/agent-publish", {**BODY, "dry_run": False, "confirm": wrong}, tok(priv)).json()
        assert no["kind"] == "not_allowed" and not fake.created
    out = _post(client, "/agent-publish", {**BODY, "dry_run": False, "confirm": dry["confirm"]}, tok(priv)).json()
    assert out["published"] is True and "Published shop_agent in Fabric" in out["words"]
    assert "Microsoft 365 Copilot is the last step, yours" in out["note"]
    assert [c["route"] for c in fake.created] == ["publish"]
    assert fake.created[0]["body"] == {"publishedDescription": agent_publish.DESCRIPTION.format(source="demo_lh")}
    assert [c[0] for c in _writes(fake)] == ["POST"]


def test_a_refused_publish_is_said_and_not_retried(agent):
    client, fake, priv, state = agent
    dry = _post(client, "/agent-publish", BODY, tok(priv)).json()
    state["publish"] = 403
    out = _post(client, "/agent-publish", {**BODY, "dry_run": False, "confirm": dry["confirm"]}, tok(priv)).json()
    assert out["kind"] == "fabric" and "stays a draft" in out["error"] and len(fake.created) == 1


def test_an_item_that_is_not_a_data_agent_is_refused_before_anything(api):
    client, fake, _, priv = api
    out = _post(client, "/agent-publish", {**BODY, "agent_id": gs.API.replace("aaaaaaaa", "eeeeeeee")}, tok(priv)).json()
    assert out["kind"] == "not_found" and _writes(fake) == []


def test_bad_input_is_refused(api):
    client, _, _, priv = api
    for bad in ({**BODY, "agent_id": "x"}, {**BODY, "workspace": "demo"}, {**BODY, "dry_run": "no"}, {k: v for k, v in BODY.items() if k != "name"}):
        assert _post(client, "/agent-publish", bad, tok(priv)).status_code == 400


def test_publishing_counts_as_a_write_for_the_trial_and_the_dry_run_does_not():
    assert billing.route_writes("agent-publish", {"dry_run": False}) is True
    assert billing.route_writes("agent-publish", {"dry_run": True}) is False
