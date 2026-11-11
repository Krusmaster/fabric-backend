"""Round n213: a 30-day trial per organisation on the hosted MCP server and the Fabric workload, then a Microsoft
Marketplace subscription (fabric_backend/billing.py, docs/BILLING-MODEL.md).

Trial start on the first call (both products; a guest in the publisher's tenant exempt), expiry, the gate for every
writing tool and route, reads still allowed, exempt tenants, the user count without raw ids, the founder's events, the
deploy dry run, and the switch off = no change. In-memory store, fake clock; nothing calls Entra, Azure or Fabric."""
import inspect
import json
from types import SimpleNamespace

import pytest

from starlette.applications import Starlette
from starlette.testclient import TestClient

from fabric_backend import billing, marketplace as mp, server, switches, workload_api

PUB = "11111111-0000-0000-0000-000000000001"          # Kruse Consulting's own tenant
PILOT = "22222222-0000-0000-0000-000000000002"
BUYER = "44444444-0000-0000-0000-000000000004"
OTHER = "55555555-0000-0000-0000-000000000005"
SUB = "66666666-0000-0000-0000-000000000006"
OID = "99999999-aaaa-bbbb-cccc-000000000001"
OFFER = "https://marketplace.microsoft.com/product/krusecons.krusgraph-dev"
T0 = 1_790_000_000.0                                  # a fixed start, in November 2026
DAY = 86400


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_TRIAL", "1")
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE", "1")
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_OFFER_URL", OFFER)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_TENANT_ID", PUB)
    monkeypatch.setenv("KRUSGRAPH_TRIAL_EXEMPT_TENANTS", PILOT)
    monkeypatch.setenv("KRUSGRAPH_PLAN_USER_CAPS", '{"up-to-5-users": 2}')
    monkeypatch.delenv("KRUSGRAPH_ENTITLEMENTS", raising=False)
    store = mp.MemoryStore()
    subs = mp.Subscriptions(store)
    clock, events = Clock(), []
    trials = billing.Trials(store, clock=clock, emit=events.append, salt="test-salt-not-secret")
    mp.set_store(subs)
    billing.set_trials(trials)
    yield SimpleNamespace(store=store, subs=subs, clock=clock, events=events, trials=trials)
    mp.set_store(None)
    billing.set_trials(None)


@pytest.fixture
def shop(monkeypatch):
    from fabric_backend import seed
    from fabric_backend.schema import Schema
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: "ws-1")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, h: {"type": "Lakehouse", "id": "lh-1", "displayName": src,
                                                                        "sql_host": "h", "sql_db": src})
    ran = []
    ex = lambda sql: []  # noqa: E731
    ex.statement = lambda sql: ran.append(sql)
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: ex)
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    who = {"oid": OID, "tid": BUYER}
    monkeypatch.setattr(server, "_identity", lambda ctx: dict(who))
    monkeypatch.setattr(server, "limiter", None)              # many calls from one user here; the fair-use limit is not tested
    return SimpleNamespace(ran=ran, who=who)


def _row(world, tid=BUYER):
    return world.store.get(billing.PARTITION, tid)[0]


# ------------------------------------------------------------------ trial start -----------------------------------------

def test_the_first_mcp_call_starts_the_trial_and_tells_the_founder(world, shop):
    assert _row(world) is None
    assert "error" not in json.loads(server.plan_backend("Sales", "shop_lh", schema="shop"))
    row = _row(world)
    assert row["first_product"] == "mcp" and row["first_seen"] == billing._iso(T0)
    assert row["trial_ends"] == billing._iso(T0 + 30 * DAY)
    assert [e["event"] for e in world.events] == ["trial_started"] and world.events[0]["tenant"] == BUYER
    server.plan_backend("Sales", "shop_lh", schema="shop")
    assert [e["event"] for e in world.events] == ["trial_started"]                    # once, not per call


def test_opening_the_model_item_starts_the_trial_and_shows_the_days_left(world):
    c = _workload_client({"tid": OTHER, "oid": OID})
    r = c.post("/workload/v1/access", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    got = r.json()
    assert got["state"] == "trial" and got["days_left"] == 30 and got["offer_url"] == OFFER
    assert got["words"].startswith("Trial: 30 days left") and OFFER in got["words"]
    assert _row(world, OTHER)["first_product"] == "workload"
    assert world.events[0]["event"] == "trial_started" and world.events[0]["product"] == "workload"


def test_a_guest_in_the_publishers_tenant_and_the_pilots_are_exempt_and_never_written(world, shop):
    shop.who.update(tid=PUB)                       # a B2B guest's token carries the publisher's tid
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["result"]["status"] == "Succeeded"
    c = _workload_client({"tid": PUB, "oid": OID, "email": "eva@contoso.example"})
    assert c.post("/workload/v1/access", headers={"Authorization": "Bearer t"}).json() == {"state": "exempt", "words": "",
                                                                                           "offer_url": OFFER}
    assert billing.decide(PILOT, OID, write=True, product="mcp")["allowed"] is True
    assert world.store.query(billing.PARTITION) == [] and world.events == []          # no trial for the guest's home tenant


# ------------------------------------------------------------------ expiry and the gate ---------------------------------

def test_after_30_days_writes_are_refused_in_plain_words_and_reads_dry_runs_still_run(world, shop):
    server.plan_backend("Sales", "shop_lh", schema="shop")
    world.clock.t = T0 + 29 * DAY
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["result"]["status"] == "Succeeded"
    world.clock.t = T0 + 30 * DAY + 1
    shop.ran.clear()
    out = json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))
    assert out["kind"] == "upgrade" and out["upgrade_url"] == OFFER and OFFER in out["hint"] and out["days_left"] == 0
    assert "trial ended on" in out["error"] and "Nothing was created or changed" in out["error"] and shop.ran == []
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop"))["dry_run"] is True        # dry run
    assert "error" not in json.loads(server.plan_backend("Sales", "shop_lh", schema="shop"))            # read
    world.subs.record(BUYER, SUB, {"offer": "krusgraph", "plan": "up-to-5-users", "status": "Subscribed"})
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["result"]["status"] == "Succeeded"
    world.subs.record(BUYER, SUB, {"status": "Unsubscribed"})
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["kind"] == "upgrade"


# the hosted server's creating tools (switches.KNOWN also holds the local server's tools once mcp_server is imported)
WRITERS = [n for n, a in switches.KNOWN.items() if switches.creates(n, a) and callable(getattr(server, n, None))]


def test_every_creating_tool_is_gated_on_its_real_call_only():
    assert set(WRITERS) >= {"create_backend", "create_views", "create_semantic_model", "create_report", "create_data_agent",
                            "create_ontology", "create_silver_notebook", "create_gold_views", "create_pipeline",
                            "create_drift_monitor"}
    for name in WRITERS:
        fn = getattr(server, name)
        assert inspect.signature(fn).parameters["dry_run"].default is True, name
        assert billing.tool_writes(name, False) and not billing.tool_writes(name, True), name
    for name, a in switches.KNOWN.items():
        if name not in WRITERS and callable(getattr(server, name, None)):
            assert not billing.tool_writes(name, False) and not billing.tool_writes(name, None), name


@pytest.mark.parametrize("name", WRITERS)
def test_each_creating_tool_answers_upgrade_after_the_trial_without_running(world, shop, monkeypatch, name):
    billing.decide(BUYER, OID, write=False, product="mcp")
    world.clock.t = T0 + 31 * DAY
    def refused(dry_run: bool = True, ctx=None):
        pytest.fail("the tool ran")

    def dry(dry_run: bool = True, ctx=None):
        return json.dumps({"dry_run": dry_run})
    out = json.loads(server._instrumented(refused, name)(dry_run=False, ctx=None))
    assert out["kind"] == "upgrade" and out["upgrade_url"] == OFFER
    assert json.loads(server._instrumented(dry, name)(dry_run=True, ctx=None)) == {"dry_run": True}


def test_workload_routes_refuse_create_and_retire_after_the_trial_and_keep_reads(world, monkeypatch):
    ran = []
    monkeypatch.setattr(workload_api, "run_build", lambda req: ran.append(("build", req["dry_run"])) or {"dry_run": req["dry_run"]})
    monkeypatch.setattr(workload_api, "build_request", lambda b: {**b, "dry_run": b.get("dry_run", True)})
    monkeypatch.setattr(workload_api, "run_product", lambda req: ran.append(("product", req["action"])) or {"ok": True})
    monkeypatch.setattr(workload_api, "product_request", lambda b: {**b, "workspace": "ws", "source_name": "p",
                                                                    "dry_run": b.get("dry_run", True)})
    monkeypatch.setattr(workload_api, "run_review", lambda req: ran.append(("review", None)) or {"ok": True})
    monkeypatch.setattr(workload_api, "review_request", lambda b: {**b, "workspace": "ws", "source_name": "lh"})
    monkeypatch.setattr(workload_api, "run_check", lambda req: ran.append(("check", None)) or {"ok": True})
    monkeypatch.setattr(workload_api, "check_request", lambda b: {**b, "workspace": "ws", "source_name": "lh"})
    c = _workload_client({"tid": BUYER, "oid": OID})
    h = {"Authorization": "Bearer t"}
    body = {"workspace": "ws", "source": "lh", "source_name": "lh"}
    assert c.post("/workload/v1/build", json={**body, "dry_run": False}, headers=h).status_code == 200    # in the trial
    world.clock.t = T0 + 40 * DAY
    ran.clear()
    r = c.post("/workload/v1/build", json={**body, "dry_run": False}, headers=h)
    assert r.status_code == 402 and r.json()["kind"] == "upgrade" and r.json()["upgrade_url"] == OFFER
    r = c.post("/workload/v1/product", json={"action": "retire", "dry_run": False}, headers=h)
    assert r.status_code == 402 and ran == []
    for path, extra in (("build", {"dry_run": True}), ("review", {}), ("check", {})):
        assert c.post(f"/workload/v1/{path}", json={**body, **extra}, headers=h).status_code == 200, path
    for action in ("status", "leftovers"):
        assert c.post("/workload/v1/product", json={"action": action}, headers=h).status_code == 200
    assert c.post("/workload/v1/product", json={"action": "retire", "dry_run": True}, headers=h).status_code == 200
    assert ran == [("build", True), ("review", None), ("check", None), ("product", "status"), ("product", "leftovers"),
                   ("product", "retire")]
    got = c.post("/workload/v1/access", headers=h).json()
    assert got["state"] == "ended" and got["words"].startswith("Trial ended on") and OFFER in got["words"]
    assert billing.route_writes("product", {"action": "adopt"}) is False         # adopt only returns entries to save


def test_an_unreadable_store_closes_writing_for_the_call_and_never_reading(world, monkeypatch):
    def broken(*a, **k):
        raise mp.MarketplaceError("the table answered HTTP 503", 503)
    monkeypatch.setattr(world.store, "get", broken)
    monkeypatch.setattr(world.subs, "tenant", broken)
    assert billing.decide(BUYER, OID, write=False, product="mcp")["allowed"] is True
    got = billing.decide(BUYER, OID, write=True, product="mcp")
    assert got["allowed"] is False and got["refusal"]["kind"] == "upgrade" and "Try again" in got["refusal"]["hint"]


# ------------------------------------------------------------------ users per organisation ------------------------------

def test_users_are_counted_by_a_salted_hash_only_and_age_out_after_30_days(world):
    oids = [f"0000000{i}-aaaa-bbbb-cccc-000000000000" for i in range(3)]
    for o in oids:
        billing.decide(BUYER, o, write=False, product="mcp")
    row = _row(world)
    raw = json.dumps(row)
    assert all(o not in raw for o in oids) and "test-salt-not-secret" not in raw
    assert world.trials.users(row) == 3
    assert set(json.loads(row["users"])) == {billing.user_hash(BUYER, o, "test-salt-not-secret") for o in oids}
    assert billing.user_hash(BUYER, oids[0], "a") != billing.user_hash(BUYER, oids[0], "b")      # the salt matters
    world.clock.t = T0 + 31 * DAY
    billing.decide(BUYER, oids[0], write=False, product="mcp")
    assert world.trials.users(_row(world)) == 1


def test_without_a_salt_no_user_is_counted(world, monkeypatch):
    t = billing.Trials(world.store, clock=world.clock, emit=world.events.append, salt="")
    t.touch(BUYER, OID, "mcp")
    assert json.loads(_row(world)["users"]) == {}


def test_over_the_plans_cap_the_users_and_the_founder_are_warned_and_nothing_is_blocked(world, shop):
    world.subs.record(BUYER, SUB, {"offer": "krusgraph", "plan": "up-to-5-users", "status": "Subscribed"})
    for i in range(3):
        billing.decide(BUYER, f"0000000{i}-aaaa-bbbb-cccc-000000000000", write=False, product="mcp")
    got = billing.decide(BUYER, OID, write=True, product="workload")
    assert got["allowed"] is True and "covers up to 2 users" in got["words"] and "Nothing is blocked" in got["notice"]
    caps = [e for e in world.events if e["event"] == "plan_over_cap"]
    assert len(caps) == 1 and caps[0]["cap"] == 2 and caps[0]["users_30_days"] >= 3
    billing.decide(BUYER, OID, write=False, product="mcp")
    assert len([e for e in world.events if e["event"] == "plan_over_cap"]) == 1          # once in 30 days
    assert "trial_started" not in [e["event"] for e in world.events]                       # subscribed before first use
    out = json.loads(server.plan_backend("Sales", "shop_lh", schema="shop"))
    assert "covers up to 2 users" in out["billing_notice"]


# ------------------------------------------------------------------ founder notices ------------------------------------

def test_seven_days_before_the_end_the_founder_gets_one_event_from_a_call_or_the_sweep(world):
    billing.decide(BUYER, OID, write=False, product="mcp")
    billing.decide(OTHER, OID, write=False, product="workload")
    world.clock.t = T0 + 22 * DAY
    assert world.trials.sweep() == 0
    world.clock.t = T0 + 23 * DAY + 60
    got = billing.decide(BUYER, OID, write=False, product="mcp")
    assert got["days_left"] == 7 and "ends on" in got["notice"]
    assert world.trials.sweep() == 1                                                       # OTHER only; BUYER already sent
    soon = [e for e in world.events if e["event"] == "trial_ends_soon"]
    assert sorted(e["tenant"] for e in soon) == sorted([BUYER, OTHER]) and all(e["days_left"] == 7 for e in soon)
    assert world.trials.sweep() == 0
    assert all(set(e) <= {"event", "tenant", "product", "first_seen", "trial_ends", "days_left", "plan", "cap", "users_30_days"}
               for e in world.events)                                                     # no names, no e-mail, no oid


def test_the_founder_line_is_one_json_line_and_the_webhook_card_carries_the_same_fields(monkeypatch, capsys):
    monkeypatch.delenv("KRUSGRAPH_FOUNDER_WEBHOOK_URL", raising=False)
    billing._default_emit({"event": "trial_started", "tenant": BUYER, "trial_ends": "2026-12-11T00:00:00Z"})
    line = json.loads(capsys.readouterr().out.strip())
    assert line == {"krusgraph": "billing", "event": "trial_started", "tenant": BUYER, "trial_ends": "2026-12-11T00:00:00Z"}
    card = json.dumps(billing.founder_card({"event": "trial_ends_soon", "tenant": BUYER, "days_left": 7}))
    assert "A Krusgraph trial ends in 7 days or less" in card and BUYER in card


# ------------------------------------------------------------------ the switch off ------------------------------------

def test_the_switch_off_changes_nothing(shop, monkeypatch):
    for v in ("KRUSGRAPH_TRIAL", "KRUSGRAPH_ENTITLEMENTS", "KRUSGRAPH_MARKETPLACE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(billing, "trials", lambda: pytest.fail("no store while the switch is off"))
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["result"]["status"] == "Succeeded"
    assert "billing_notice" not in server.plan_backend("Sales", "shop_lh", schema="shop")
    assert billing.decide(BUYER, OID, write=True, product="mcp") == {"allowed": True, "state": "off", "words": ""}
    assert billing.start_sweeper() is False
    c = _workload_client({"tid": BUYER, "oid": OID})
    assert c.post("/workload/v1/access", headers={"Authorization": "Bearer t"}).json() == {"state": "off", "words": ""}


def test_no_price_is_written_in_the_code():
    import re
    text = open(billing.__file__, encoding="utf-8").read()
    assert not re.search(r"(?i)(\bSEK\b|\bEUR\b|\bUSD\b|kr/|€|\$\d)", text)


# ------------------------------------------------------------------ deploy ---------------------------------------------

def test_the_deploy_dry_run_lists_what_the_trial_still_needs(capsys):
    import importlib
    d = importlib.import_module("deploy.azure_containerapp")
    assert d.MARKETPLACE_FLAGS["trial"] == "KRUSGRAPH_TRIAL"
    lines = d.trial_checklist({"app": "a", "resource_group": "rg"}, {"KRUSGRAPH_TRIAL": "1"}, has_salt=False, has_webhook=False)
    text = "\n".join(lines)
    assert "saknas KRUSGRAPH_MARKETPLACE=1" in text and "saknas Container-apphemligheten user-hash-salt" in text
    assert "valfri  KRUSGRAPH_TRIAL_EXEMPT_TENANTS" in text and "trial_ends_soon" in text
    d.print_trial_checklist({"app": "a", "resource_group": "rg"}, {"KRUSGRAPH_TRIAL": "1"}, False, False)
    out = capsys.readouterr().out
    assert "openssl rand -hex 32" in out and "user-hash-salt" in out
    example = json.load(open(d.ROOT / "deploy/krusgraph.example.json", encoding="utf-8"))
    assert example["trial"] is False                                                     # off until the founder says so


def _workload_client(claims):
    validator = SimpleNamespace(validate=lambda token: claims)
    return TestClient(Starlette(routes=workload_api.routes(SimpleNamespace(), validator=validator, obo=object())))


def test_privacy_and_pricing_describe_the_trial_without_a_price(monkeypatch):
    from fabric_backend import pages
    privacy = pages.privacy_md()
    assert "## Trial and subscription" in privacy and "salted hash" in privacy and "not switched on yet" in privacy
    assert "HMAC-SHA256" in privacy and "no object ids" in privacy
    pricing = open(pages.__file__.replace("pages.py", "page_templates/pricing.html"), encoding="utf-8").read()
    assert 'id="trial"' in pricing and "Not switched on yet" in pricing and "No prices yet" in pricing
    doc = open(pages.__file__.replace("fabric_backend/pages.py", "docs/BILLING-MODEL.md"), encoding="utf-8").read()
    assert "DRAFT" in doc and "learn.microsoft.com" in doc and "Unverified" in doc
