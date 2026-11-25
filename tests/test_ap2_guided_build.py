"""Round AP2: decide, dry run, create and verify in /app (fabric_backend/guided_build.py, the BUILD route of
guided_app.py). The read side is AP1's doubles (tests/ap1_support.py: Entra, the synthetic SAP demo); Fabric's REST is
tests/ap2_support.py's in-memory workspaces `demo` (the source) and `build` (a separate build workspace).

Checked: a decision tap is the start tool's own button and is recorded in the guided path's shared state exactly as the
start card records it, and shown as "Decided by you"; the dry run is the Fabric workload's build for the same inputs
(the same cards, the same answers) and writes nothing; Create refuses without the dry run's token, with another token,
with a token gone stale (a decision changed, an item appeared, the time ran out, the token was used) and with other
names, and then writes nothing; a confirmed Create writes only the dry run's items, in order, each once, in the chosen
build workspace, and never deletes; a second dry run says "already built"; verify_build's card is "Checked by rules,
not by AI"; every lock of AP1 holds on the new address (404 for a foreign tenant and while the list is empty, Origin
and JSON, a session), and no token or tenant id reaches an answer or a log line.
"""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import ap1_support as s  # noqa: E402
import ap2_support as s2  # noqa: E402
from fabric_backend import flow_state, guided_app, guided_build, server, workload_api  # noqa: E402

CH = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}
ITEM = "rel:sap_vbap.MANDT+VBELN>sap_vbak"
LINK = {"source": "sap_vbap", "source_cols": ["MANDT", "VBELN"], "target": "sap_vbak", "target_cols": ["MANDT", "VBELN"]}
NAMES = ["demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline", "demo_lh_model", "demo_lh_report", "demo_lh_agent"]
BUILD = {"workspace": s2.BUILD_WS, "lakehouse": "build_lh"}
WHO = flow_state.who_of({"oid": "person-1", "tid": s.TID}, None)


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


@pytest.fixture
def app(monkeypatch, keys):
    flow_state.clear()
    guided_build.BUILDS.clear()
    a, auth, fake = s.entra_app(monkeypatch, keys)
    fabric = s2.data(monkeypatch)
    token = s.tok(keys[0])
    c = TestClient(a, base_url=s.ORIGIN, follow_redirects=False)
    c.__enter__()
    assert s.sign_in(c, fake, token).status_code == 302
    yield c, fabric, token, auth
    c.__exit__(None, None, None)


def build(c, body: dict, **headers):
    h = {"Origin": s.ORIGIN, "Content-Type": "application/json", **headers}
    return c.post(guided_app.BUILD, content=json.dumps(body), headers=h)


def dry(c, target=BUILD, **extra):
    body = {"action": "dry_run", **CH, **extra}
    if target:
        body["target"] = target
    r = build(c, body)
    assert r.status_code == 200, r.text
    return r.json()


def create_all(c, v) -> list[dict]:
    got = build(c, {"action": "confirm", "token": v["token"], "names": [x["name"] for x in v["creates"]]}).json()
    assert "run" in got, got
    cards = []
    for it in got["items"]:
        op = build(c, {"action": "create", "run": got["run"], "kind": it["kind"]}).json()
        for _ in range(200):
            st = build(c, {"action": "state", "operation_id": op["operation_id"]}).json()
            if st.get("status") == "done":
                cards.append(st["item"])
                break
            time.sleep(0.05)
        else:
            raise AssertionError(f"{it['kind']} did not finish")
    return cards


# ------------------------------------------------------------------ Decide ---------------------------------------------

def test_a_decision_is_the_start_cards_own_tap_recorded_in_the_flow_state(app):
    c, _, token, auth = app
    open_ = s.step(c, {**CH, "step": "decide"}).json()
    assert open_["stage"] == "decide" and open_["open"] == 1
    card = open_["decisions"][0]
    assert card["item"] == ITEM and card["state"] == "open" and "decided" not in card
    assert card["rule"] == "SAP pack" and "SAP pack" in card["rule_words"]
    assert [o["label"] for o in card["options"]] == ["Accept with quarantine", "Reject", "Skip for now"]
    assert card["options"][0]["words"] == "Keeps the link: 5 of 6 rows join; 1 goes to quarantine with the reason."
    assert open_["buttons"][0]["arguments"]["step"] == "dry_run" and open_["buttons"][0]["primary"] is False

    after = s.step(c, {**CH, "step": "decide", "decide": {"item": ITEM, "review": "accepted"}}).json()
    card = after["decisions"][0]
    assert card["state"] == "accepted" and card["decided"] == "Decided by you: Accepted"
    assert card["rule"] == "SAP pack"                                           # the rule that proposed it stays on the card
    assert next(o for o in card["options"] if o["review"] == "accepted").get("selected") is True
    assert after["buttons"][0]["primary"] is True
    kept = flow_state.state(WHO, "demo", "demo_lh", "dbo")
    assert kept["decisions"] == [{"item": ITEM, "review": "accepted", "reason": "decided on the start card"}]
    assert kept["confirmed"] == [LINK]

    # exactly what the start tool records when its own card's button is tapped
    flow_state.clear()
    with server.workload_tokens(guided_app.SessionTokens(auth._obo, token, s.TID, WHO)):
        out = json.loads(server.start(**CH, step="decide"))
        args = guided_build.decide_action(out, ITEM, "accepted")
        server.start(**args)
    assert flow_state.state(WHO, "demo", "demo_lh", "dbo") == {**kept, "seq": flow_state.state(WHO, "demo", "demo_lh", "dbo")["seq"]}


def test_a_decision_not_offered_is_not_recorded_and_a_bad_one_is_refused(app):
    c = app[0]
    r = s.step(c, {**CH, "step": "decide", "decide": {"item": "rel:x.y>z", "review": "accepted"}}).json()
    assert "not offered" in r["match"]["say"]
    assert not (flow_state.state(WHO, "demo", "demo_lh", "dbo") or {}).get("decisions")
    assert s.step(c, {**CH, "step": "decide", "decide": {"item": ITEM, "review": "maybe"}}).status_code == 400
    assert s.step(c, {**CH, "step": "decide", "decide": "accept"}).status_code == 400


def test_the_check_leads_to_decide(app):
    check = s.step(app[0], {**CH, "step": "check"}).json()
    assert check["next"] == guided_app.NEXT_LINE
    assert check["buttons"] == [{"label": "Next: Decide", "primary": True, "arguments": {**CH, "step": "decide"}}]


# ------------------------------------------------------------------ the dry run ----------------------------------------

def test_the_dry_run_is_the_workloads_build_for_the_same_inputs_and_writes_nothing(app, monkeypatch):
    c, fabric, token, auth = app
    s.step(c, {**CH, "step": "decide", "decide": {"item": ITEM, "review": "rejected"}})
    seen = []
    real = workload_api.run_build_many
    monkeypatch.setattr(workload_api, "run_build_many", lambda req: seen.append(req) or real(req))
    v = dry(c)
    assert fabric.writes == []
    assert v["target"]["line"] == "build › build_lh" and v["target"]["cross"] is True
    assert [x["name"] for x in v["items"]] == NAMES and [x["badge"] for x in v["items"]] == ["New"] * 6
    assert [x["name"] for x in v["creates"]] == NAMES
    assert all(x["definition"] for x in v["items"])
    assert "definition/model.tmdl" in next(x for x in v["items"] if x["kind"] == "semantic_model")["definition"]
    assert v["decided"] == ["sap_vbap.MANDT+VBELN → sap_vbak: rejected: the next steps leave it out."]
    assert v["left_out"] == ["sap_vbap.MANDT+VBELN → sap_vbak"]                   # the rejection reaches the build

    # the same request to the workload's build gives the same cards: the page's dry run is that build, nothing else
    req = seen[0]
    assert req["dry_run"] is True and req["target"]["workspace"] == s2.BUILD_WS and req["target"]["lakehouse"] == "build_lh"
    assert [o["kind"] for o in req["outputs"]] == [k for k, _ in guided_build.OUTPUTS]
    assert {i["id"]: i["review"] for i in req["review"]["items"]}[ITEM] == "rejected"
    tokens = guided_app.SessionTokens(auth._obo, token, s.TID, WHO)
    with server.workload_tokens(tokens):
        again = real(req)
    assert [guided_build.card(x) for x in again["outputs"]] == v["items"]
    for x in again["outputs"]:
        assert x["answer"].get("dry_run") is True and not x["answer"].get("error")
    assert fabric.writes == []


def test_the_data_agents_dry_run_is_the_tools_own(app):
    c, _, token, auth = app
    v = dry(c, target=None)
    assert v["target"]["line"] == "demo › demo_lh"                                # the source's workspace by default
    shown = next(x for x in v["items"] if x["kind"] == "data_agent")["definition"]
    tokens = guided_app.SessionTokens(auth._obo, token, s.TID, WHO)
    with server.workload_tokens(tokens):
        direct = json.loads(server.create_data_agent(**CH, name="demo_lh_agent", publish=False, layer="silver",
                                                     silver_schema="silver", gold_schema="gold", dry_run=True))
    whole = json.dumps({"agent": direct["agent"]}, indent=1, ensure_ascii=False)
    assert shown[:guided_build.DEFINITION_MAX] == whole[:guided_build.DEFINITION_MAX]


def test_the_build_target_is_checked(app):
    c = app[0]
    places = build(c, {"action": "places"}).json()
    assert [w["name"] for w in places["workspaces"]] == ["demo", "build"]
    assert build(c, {"action": "lakehouses", "workspace": s2.BUILD_WS}).json()["lakehouses"] == ["build_lh"]
    assert build(c, {"action": "lakehouses", "workspace": "nope"}).json()["kind"] == "not_found"
    assert build(c, {"action": "dry_run", **CH, "target": {"workspace": "elsewhere"}}).status_code == 400
    assert build(c, {"action": "dry_run", **CH, "target": {"workspace": s2.BUILD_WS, "lakehouse": "other_lh"}}).status_code == 400
    assert build(c, {"action": "dry_run", "workspace": "demo"}).status_code == 400
    assert build(c, {"action": "dry_run", **CH, "update": ["everything"]}).status_code == 400


# ------------------------------------------------------------------ Create: only after a fresh token ---------------------

def test_create_refuses_without_the_dry_runs_token_and_writes_nothing(app):
    c, fabric = app[0], app[1]
    assert build(c, {"action": "confirm", "token": "", "names": NAMES}).json()["kind"] == "stale"      # no dry run yet
    v = dry(c)
    assert build(c, {"action": "confirm", "token": "dry-" + "0" * 32, "names": NAMES}).json()["kind"] == "stale"
    assert build(c, {"action": "confirm", "token": v["token"], "names": NAMES[:5]}).json()["kind"] == "bad_request"
    assert build(c, {"action": "confirm", "token": v["token"], "names": NAMES + ["extra"]}).json()["kind"] == "bad_request"
    assert build(c, {"action": "create", "run": "made-up", "kind": "silver_notebook"}).json()["kind"] == "stale"
    assert fabric.writes == []


def test_a_decision_changed_after_the_dry_run_makes_its_token_stale(app):
    c, fabric = app[0], app[1]
    v = dry(c)
    s.step(c, {**CH, "step": "decide", "decide": {"item": ITEM, "review": "rejected"}})
    got = build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()
    assert got["kind"] == "stale" and guided_build.STALE == got["error"]
    assert fabric.writes == []


def test_an_item_that_appeared_in_the_workspace_makes_the_token_stale(app):
    c, fabric = app[0], app[1]
    v = dry(c)
    fabric.items[s2.BUILD_WS].append({"id": "9d9d9d9d-0000-0000-0000-000000000001", "displayName": "demo_lh_model",
                                      "type": "SemanticModel", "description": "a colleague's model"})
    assert build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()["kind"] == "stale"
    assert fabric.writes == []


def test_an_old_or_used_token_is_stale(app, monkeypatch):
    c, fabric = app[0], app[1]
    v = dry(c)
    monkeypatch.setattr(guided_build, "DRY_TTL", -1)
    assert build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()["kind"] == "stale"
    monkeypatch.setattr(guided_build, "DRY_TTL", 900)
    v = dry(c)
    first = build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()
    assert "run" in first
    assert build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()["kind"] == "stale"
    assert fabric.writes == []                                                    # confirming writes nothing by itself


def test_create_writes_only_the_dry_runs_items_in_order_once_and_never_deletes(app):
    c, fabric = app[0], app[1]
    s.step(c, {**CH, "step": "decide", "decide": {"item": ITEM, "review": "accepted"}})
    v = dry(c)
    got = build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()
    assert build(c, {"action": "create", "run": got["run"], "kind": "report"}).json()["kind"] == "bad_request"   # out of order
    assert fabric.writes == []
    fabric.calls.clear()
    cards = []
    for it in got["items"]:
        op = build(c, {"action": "create", "run": got["run"], "kind": it["kind"]}).json()
        assert build(c, {"action": "create", "run": got["run"], "kind": it["kind"]}).json()["kind"] == "bad_request"  # once
        for _ in range(200):
            st = build(c, {"action": "state", "operation_id": op["operation_id"]}).json()
            if st.get("status") == "done":
                cards.append(st["item"])
                break
            time.sleep(0.05)
    assert [x["name"] for x in cards] == NAMES and all(x["action"] == "create" for x in cards), cards
    made = fabric.created()
    assert sorted(i["displayName"] for i in made) == sorted(NAMES + ["demo_lh_pipeline_check"])
    assert all(i["workspace"] == s2.BUILD_WS for i in made)
    assert not any(m == "DELETE" for m, _ in fabric.calls)
    ours = {i["id"] for i in made}
    for method, path in fabric.writes:                                            # every write is one of these items
        if method == "POST" and path.rstrip("/").split("/")[-1] in s2.ROUTE_TYPES:
            continue
        assert any(i in path for i in ours), (method, path)
    for x in cards:
        for link in x["created"]:
            assert link["url"].startswith(f"https://app.fabric.microsoft.com/groups/{s2.BUILD_WS}/")
    model = next(x for x in cards if x["kind"] == "semantic_model")
    assert "/datasets/" in model["created"][0]["url"] and model["steps"]
    report = next(i for i in made if i["type"] == "Report")
    assert report["displayName"] == "demo_lh_report"

    # a second dry run sees what this Create made: already built from this plan, nothing to write
    again = dry(c)
    assert [x["action"] for x in again["items"]] == ["skip"] * 6 and again["creates"] == []
    assert all(x["badge"] == "Already built" for x in again["items"])


def test_verify_reads_back_what_was_built_by_rules(app):
    c = app[0]
    assert build(c, {"action": "verify"}).json()["kind"] == "not_found"            # nothing created yet
    create_all(c, dry(c))
    v = build(c, {"action": "verify"}).json()
    assert v["title"] == "Checked by rules, not by AI" and "not a review by AI" in v["label"]
    assert v["counts"]["items"] >= 5 and v["counts"]["verified"] >= 1
    assert {x["item"] for x in v["lines"]} >= {"demo_lh_model", "demo_lh_pipeline", "demo_lh_report"}
    assert any(x["label"] == "Run the pipeline once" for x in v["next_steps"])


def test_a_create_that_fabric_has_not_finished_says_started(app, monkeypatch):
    c = app[0]
    v = dry(c)
    got = build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()

    def slow(req):
        return {"dry_run": False, "outputs": [{"output": "silver_notebook", "label": "Silver notebook", "name": "demo_lh_silver",
                                               "type": "Notebook", "pending_fabric": True,
                                               "answer": {"kind": "pending_fabric", "error": "Still being created in Fabric.",
                                                          "hint": "It is recorded as pending."}}], "created": []}
    monkeypatch.setattr(workload_api, "run_build_background", slow)
    op = build(c, {"action": "create", "run": got["run"], "kind": "silver_notebook"}).json()
    for _ in range(100):
        st = build(c, {"action": "state", "operation_id": op["operation_id"]}).json()
        if st.get("status") == "done":
            break
        time.sleep(0.05)
    assert st["item"]["action"] == "started" and st["item"]["badge"] == "Started"
    assert "Still being created" in st["item"]["words"]


def test_a_missing_permission_is_said_as_consent(app, monkeypatch):
    c = app[0]
    v = dry(c)
    got = build(c, {"action": "confirm", "token": v["token"], "names": NAMES}).json()

    def refused(req):
        return {"dry_run": False, "created": [], "outputs": [{
            "output": "silver_notebook", "label": "Silver notebook", "name": "demo_lh_silver", "type": "Notebook",
            "refusal": {"error": "Creating a notebook needs Notebook.ReadWrite.All.", "kind": "consent",
                        "hint": "An admin grants it.", "entra_steps": ["Open Entra", "Grant consent"]},
            "decision": {"action": "refuse", "words": "Creating a notebook needs Notebook.ReadWrite.All. An admin grants it."}}]}
    monkeypatch.setattr(workload_api, "run_build_background", refused)
    op = build(c, {"action": "create", "run": got["run"], "kind": "silver_notebook"}).json()
    for _ in range(100):
        st = build(c, {"action": "state", "operation_id": op["operation_id"]}).json()
        if st.get("status") == "done":
            break
        time.sleep(0.05)
    assert st["item"]["action"] == "refuse" and st["item"]["consent"]["steps"] == ["Open Entra", "Grant consent"]


# ------------------------------------------------------------------ AP1's locks on the new address ------------------------

def test_the_build_address_is_the_sites_404_while_the_list_is_empty(monkeypatch, keys):
    a, _, fake = s.entra_app(monkeypatch, keys, None)
    with TestClient(a, base_url=s.ORIGIN, follow_redirects=False) as c:
        assert build(c, {"action": "places"}).status_code == 404
        assert c.get(guided_app.BUILD, headers={"Accept": "text/html"}).status_code == 404
        assert build(c, {"action": "places"}).text == "not found"


def test_a_foreign_tenant_gets_no_session_and_the_build_address_runs_nothing(monkeypatch, keys):
    a, _, fake = s.entra_app(monkeypatch, keys)
    s2.data(monkeypatch)
    with TestClient(a, base_url=s.ORIGIN, follow_redirects=False) as c:
        r = s.sign_in(c, fake, s.tok(keys[0], tid=s.OTHER))
        assert r.status_code == 404
        assert not any(x.startswith(guided_app.SESSION_COOKIE + "=") for x in r.headers.get_list("set-cookie"))
        r = build(c, {"action": "dry_run", **CH})
        assert r.status_code == 401                                                # no session: nothing runs
        s.sign_in(c, fake, s.tok(keys[0]), code="code-2")
        assert build(c, {"action": "places"}).status_code == 200
        monkeypatch.setenv(guided_app.ENV, s.OTHER)                               # the list changed: the session ends
        assert build(c, {"action": "places"}).status_code == 401


def test_the_build_address_takes_json_from_this_sites_page_only(app):
    c = app[0]
    assert build(c, {"action": "places"}, Origin="https://evil.example").status_code == 403
    r = c.post(guided_app.BUILD, content=json.dumps({"action": "places"}), headers={"Origin": s.ORIGIN, "Content-Type": "text/plain"})
    assert r.status_code == 403
    assert build(c, {"action": "delete"}).status_code == 400
    assert build(c, {"action": "places", "pad": "x" * 5000}).status_code == 400


def test_no_token_or_tenant_id_in_answers_or_logs(app, capsys):
    c, _, token, _ = app
    s.step(c, {**CH, "step": "decide", "decide": {"item": ITEM, "review": "accepted"}})
    v = dry(c)
    cards = create_all(c, v)
    ver = build(c, {"action": "verify"}).json()
    text = json.dumps([v, cards, ver]) + capsys.readouterr().out
    assert token not in text and s.TID not in text and "obo|" not in text
