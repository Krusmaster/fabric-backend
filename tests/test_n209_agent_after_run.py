"""Round n209, item 5 (the founder's live test of 10 November 2026): the data agent's example queries and the pipeline's run.

- With Run once ticked, Create reports no example validity before the run has succeeded: the examples read "not
  checked yet" and nothing is published. The editor's after_run call with Succeeded checks them (and publishes when
  Publish is ticked); a Failed run publishes nothing and leaves them not checked.
- An example Fabric marked Invalid because it could not connect ("Failed to connect to server ...datawarehouse...") is
  sent once more, exactly once; when it still cannot connect, or the second sending itself raises, it reads "not checked
  yet" with the reason in words, never invalid; also without Run once. Only a real query error is invalid.

Through POST /workload/v1/build with the doubles of tests/test_workload_create.py (Workspace, make, _review): the
create_data_agent tool answers as it does after its apply (agent id, data source id, the examples as Fabric holds
them), and the agent's staging API (few-shots, publish) is the in-memory double below, behind deploy.send.
"""
import importlib
import json

import pytest

import golden_support as gs
from fabric_backend import server, workload_api as W
from test_workload_api import SRC, keys  # noqa: F401
from test_workload_create import _post, _review, make  # noqa: F401

CONNECT = "Failed to connect to server x1.datawarehouse.fabric.microsoft.com"
SHOTS = [("Sales by month?", "SELECT 1"), ("Orders per customer?", "SELECT 2")]
AGENT = {"kind": "data_agent", "name": "shop_agent", "agent": {"layer": "silver", "publish": True, "copilot": False}}
PIPE = {"kind": "pipeline", "name": "shop_flow", "jobs": {"run_once": True, "schedule": None}}


class Staging:
    """The agent's staging few-shots and publish. `states[i]` is what the i-th read of the few-shots shows, each a
    {question: (value, reason)}; the last one stays. `patch_raises` makes the second sending raise."""

    def __init__(self, states, patch_raises=False):
        self.states, self.reads, self.patched, self.published = list(states), 0, [], 0
        self.patch_raises = patch_raises

    def __call__(self, method, url, headers=None, write=False, **kw):
        if url.endswith("/staging/publish"):
            self.published += 1
            return gs.Response(200, {})
        if method == "patch" and "/fewshots/" in url:
            self.patched.append(url.rsplit("/", 1)[-1])
            if self.patch_raises:
                raise ConnectionError("the connection was reset")
            return gs.Response(200, {})
        if method == "get" and url.endswith("/fewshots"):
            state = self.states[min(self.reads, len(self.states) - 1)]
            self.reads += 1
            return gs.Response(200, {"value": [
                {"id": f"f{i}", "question": q, "query": sql, "validationStatus": {"value": state[q][0], **({"reason": state[q][1]} if state[q][1] else {})}}
                for i, (q, sql) in enumerate(SHOTS)]})
        return None


def _status(state):
    """What data_agent.example_status reads from that state (the tool's own answer after its apply)."""
    by = {"Valid": 0, "Invalid": 0, "Validating": 0}
    for v, _ in state.values():
        by[v] += 1
    return {"status": "read", "count": len(state), **{k.lower(): n for k, n in by.items()},
            "invalid_examples": [{"question": q, "reason": r} for q, (v, r) in state.items() if v == "Invalid"]}


@pytest.fixture
def agent_build(make, monkeypatch):
    """(build, staging): build(states, outputs, **extra) sends one Create of the data agent; the tool answers with
    the first state, Fabric's staging API with each state in turn."""
    d = importlib.import_module("fabric_backend.deploy")
    real_send = d.send
    monkeypatch.setattr(W, "RECHECK_WAITS", (0, 0))
    monkeypatch.setattr(W.time, "sleep", lambda s: None)
    client, fake, priv = make()
    rv = _review(client, priv)
    box = {}

    def build(states, outputs=(PIPE, AGENT), patch_raises=False, **extra):
        staging = Staging(states, patch_raises)
        box["staging"] = staging

        def send(method, url, headers, **kw):
            if "/dataAgents/" in url:
                got = staging(method, url, headers, **kw)
                if got is not None:
                    return got
            return real_send(method, url, headers, **kw)
        monkeypatch.setattr(d, "send", send)

        def tool(name, publish, layer, dry_run=True, **kw):
            assert publish is False                                # publishing is the card's decision (agent_publish)
            return json.dumps({"dry_run": dry_run, "agent": {"name": name}, "layer": "the silver tables",
                               "result": {"status": "Succeeded", "id": "da-1", "datasource_id": "ds-1",
                                          "selection": {"layer": "silver", "one_layer": True, "words": "Silver tables selected."},
                                          "examples": _status(states[0])}})
        monkeypatch.setattr(server, "create_data_agent", tool)
        body = {**SRC, "review": rv, "outputs": list(outputs), "only": ["data_agent"], "dry_run": False, "created": [], **extra}
        r = _post(client, "/build", body, priv)
        assert r.status_code == 200, r.text
        card = next(c for c in r.json()["outputs"] if c["output"] == "data_agent")
        assert not card.get("refusal") and not card["answer"].get("error"), card
        return card, staging
    return build


def _all(value, reason=None):
    return {q: (value, reason) for q, _ in SHOTS}


# ------------------------------------------------------------------ (a) with Run once ticked ------------------------

def test_with_run_once_create_reports_no_validity_and_publishes_nothing_before_the_run(agent_build):
    card, staging = agent_build([_all("Invalid", CONNECT)], skip_built=True)
    ex = card["agent"]["examples"]
    assert ex["status"] == "not_checked" and ex["words"] == W.NOT_CHECKED_WORDS
    assert "invalid" not in ex and "invalid_examples" not in ex and "valid" not in ex
    assert card["answer"]["result"]["examples"] == ex                 # the tool's answer says the same
    assert card["agent"]["published"] is False and card["agent"]["decision"]["state"] == "waiting"
    assert staging.patched == [] and staging.published == 0 and staging.reads == 0


def test_after_a_run_that_succeeded_the_examples_are_checked_and_the_agent_published(agent_build):
    created = [{"type": "DataAgent", "id": "da-1", "name": "shop_agent", "workspace": gs.WS, "output": "data_agent"}]
    card, staging = agent_build([_all("Invalid", CONNECT), _all("Validating"), _all("Valid")],
                                after_run={"status": "Succeeded"}, created=created)
    ex = card["agent"]["examples"]
    assert ex["status"] == "read" and ex["valid"] == 2 and ex["invalid"] == 0 and ex["rechecked"] == 2
    assert not ex.get("not_checked")
    assert sorted(staging.patched) == ["f0", "f1"]                      # each sent once more, once
    assert card["agent"]["published"] is True and staging.published == 1


def test_a_failed_run_publishes_nothing_and_leaves_the_examples_not_checked(agent_build):
    card, staging = agent_build([_all("Invalid", CONNECT)], after_run={"status": "Failed"})
    ex = card["agent"]["examples"]
    assert ex["status"] == "not_checked" and "failed" in ex["words"] and set(ex) == {"status", "count", "words"}
    assert card["agent"]["published"] is False and "failed" in card["agent"]["decision"]["why"]
    assert staging.patched == [] and staging.published == 0


def test_after_run_without_the_pipeline_in_the_request_still_waits_for_success(agent_build):
    card, staging = agent_build([_all("Valid")], outputs=(AGENT,), after_run={"status": "Failed"})
    assert card["agent"]["examples"]["status"] == "not_checked" and card["agent"]["published"] is False and staging.published == 0


# ------------------------------------------------------------------ (b) a failure to connect -------------------------

def test_a_connection_failure_is_retried_once_then_reads_not_checked_with_the_reason_without_run_once(agent_build):
    agent = {**AGENT, "agent": {**AGENT["agent"], "publish": False}}
    mixed = {SHOTS[0][0]: ("Invalid", CONNECT), SHOTS[1][0]: ("Invalid", "Invalid column name 'x'")}
    card, staging = agent_build([mixed], outputs=(agent,))
    ex = card["agent"]["examples"]
    assert staging.patched == ["f0"]                                    # once, and never the real query error
    assert ex["status"] == "read" and ex["rechecked"] == 1
    assert ex["invalid"] == 1 and ex["invalid_examples"] == [{"question": SHOTS[1][0], "reason": "Invalid column name 'x'"}]
    assert ex["not_checked"] == 1 and ex["not_checked_examples"] == [{"question": SHOTS[0][0], "reason": CONNECT}]
    assert "not checked yet" in ex["not_checked_words"] and CONNECT in ex["not_checked_words"]
    assert "invalid" not in ex["not_checked_words"].lower()


def test_when_the_second_sending_raises_the_examples_read_not_checked_never_invalid(agent_build):
    card, staging = agent_build([_all("Invalid", CONNECT)], outputs=({**AGENT, "agent": {**AGENT["agent"], "publish": False}},),
                                patch_raises=True)
    ex = card["agent"]["examples"]
    assert staging.patched == ["f0"]                                    # the first sending raised: no third try
    assert ex["invalid"] == 0 and ex["invalid_examples"] == [] and ex["not_checked"] == 2
    assert {x["reason"] for x in ex["not_checked_examples"]} == {CONNECT}


def test_after_a_run_that_succeeded_a_connection_that_still_fails_is_not_checked(agent_build):
    card, staging = agent_build([_all("Invalid", CONNECT)], after_run={"status": "Succeeded"})
    ex = card["agent"]["examples"]
    assert sorted(staging.patched) == ["f0", "f1"] and ex["not_checked"] == 2 and ex["invalid"] == 0
    assert card["agent"]["published"] is True                           # the run succeeded and Publish was ticked


def test_recheck_unreadable_after_the_second_try_keeps_real_errors_and_not_checked(monkeypatch):
    d = importlib.import_module("fabric_backend.deploy")
    calls = []

    def send(method, url, headers, **kw):
        calls.append(method)
        if method == "get" and len([c for c in calls if c == "get"]) > 1:
            raise ConnectionError("down")
        return gs.Response(200, {"value": [{"id": "f0", "question": "q1", "query": "SELECT 1"}]})
    monkeypatch.setattr(d, "send", send)
    before = {"status": "read", "count": 2, "valid": 0, "invalid": 2, "validating": 0, "invalid_examples": [
        {"question": "q1", "reason": CONNECT}, {"question": "q2", "reason": "Invalid object name 'x'"}]}
    now = W.recheck_examples(gs.WS, "da-1", "ds-1", before, {}, sleep=lambda s: None)
    assert calls.count("patch") == 1
    assert now["invalid"] == 1 and now["invalid_examples"][0]["question"] == "q2" and now["not_checked"] == 1 and now["rechecked"] == 1
