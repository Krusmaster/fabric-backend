"""WB7: the Marketplace licence check, end to end with doubles, ready to switch on and off by default.
The webhook (Subscribe, ChangePlan, Suspend, Reinstate, Unsubscribe) writes the tenant's row, the workload engine reads
it, and a Create (dry_run=false) on /build, /starter, /sap-demo and /catalog is allowed or answered with kind upgrade;
dry runs and reads stay free; the 30-day trial opens Create and its end closes it; with the flags off nothing changes.
Throw-away keys and fake HTTP: nothing here calls Entra, Azure, Marketplace or Fabric."""
from types import SimpleNamespace

import pytest

pytest.importorskip("jwt")
from starlette.applications import Starlette  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import billing, marketplace as mp, workload_api  # noqa: E402
from test_marketplace import BUYER_TID, OTHER_TID, FakeAPI, event, hook, market, subs  # noqa: E402,F401  (fixtures)
from test_n213_trial import DAY, world  # noqa: E402,F401  (fixture)

CREATES = ("build", "starter", "sap-demo", "catalog")


@pytest.fixture
def engine(monkeypatch):
    """The workload routes with a fake token validator and every create route's run replaced by a recorder."""
    claims = {"tid": BUYER_TID, "oid": "u", "scp": "user_impersonation"}
    ran = []
    for where, (parse, run) in {"build": ("build_request", "run_build"), "starter": ("starter_request", "run_starter"),
                                "sap-demo": ("sap_demo_request", "run_sap_demo"),
                                "catalog": ("catalog_request", "run_catalog")}.items():
        monkeypatch.setattr(workload_api, parse, lambda b: {**b, "dry_run": b.get("dry_run", True)})
        monkeypatch.setattr(workload_api, run, lambda req, w=where: ran.append((w, req["dry_run"])) or {"dry_run": req["dry_run"]})
    routes = workload_api.routes(SimpleNamespace(), validator=SimpleNamespace(validate=lambda t: claims), obo=object())
    c = TestClient(Starlette(routes=routes))

    def post(where, dry_run, tid=BUYER_TID):
        claims["tid"] = tid
        return c.post(f"/workload/v1/{where}", json={"dry_run": dry_run}, headers={"Authorization": "Bearer t"})
    return SimpleNamespace(post=post, ran=ran)


def _creates_allowed(engine, tid=BUYER_TID) -> set:
    return {w for w in CREATES if engine.post(w, False, tid).status_code == 200}


def test_the_webhook_lifecycle_opens_and_closes_create_on_every_create_route(market, engine):
    api = FakeAPI()
    assert _creates_allowed(engine) == set()                                         # no subscription: refused
    r = engine.post("build", False)
    assert r.status_code == 402 and r.json()["kind"] == "upgrade" and r.json()["upgrade_url"].startswith("https://")
    assert all(engine.post(w, True).status_code == 200 for w in CREATES)               # dry runs stay free
    assert all(d is True for _, d in engine.ran)
    steps = [("Subscribe", True), ("ChangePlan", True), ("Suspend", False), ("Reinstate", True), ("Unsubscribe", False)]
    for i, (action, open_) in enumerate(steps):
        body = event(action, plan="team-annual" if action == "ChangePlan" else "team", ts=f"2026-11-08T10:0{i}:00Z")
        assert hook(api, market, body)[0] == 200, action
        market.tenant(BUYER_TID, cached=False)                                         # the engine reads the fresh row
        mp.set_store(market)
        assert _creates_allowed(engine) == (set(CREATES) if open_ else set()), action
        assert _creates_allowed(engine, OTHER_TID) == set(), action                   # another tenant never inherits it


def test_the_trial_opens_create_and_its_end_closes_it_until_a_subscription(world, engine):
    assert _creates_allowed(engine) == set(CREATES)                                    # first call starts the trial
    world.clock.t += 31 * DAY
    r = engine.post("sap-demo", False)
    assert r.status_code == 402 and r.json()["kind"] == "upgrade" and "trial ended" in r.json()["error"].lower()
    assert engine.post("sap-demo", True).status_code == 200                            # dry run still free
    world.subs.record(BUYER_TID, "sub-1", {"offer": "o", "plan": "team", "status": "Subscribed"})
    assert _creates_allowed(engine) == set(CREATES)


def test_flags_off_change_nothing(monkeypatch, engine):
    for v in ("KRUSGRAPH_ENTITLEMENTS", "KRUSGRAPH_MARKETPLACE", "KRUSGRAPH_TRIAL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(mp, "features", lambda tid: pytest.fail("no lookup while the flags are off"))
    assert _creates_allowed(engine) == set(CREATES)


def test_run_and_reads_are_not_writes():
    for where in ("run", "check", "analysis", "verify", "review", "selfcheck"):
        assert billing.route_writes(where, {"dry_run": False}) is False
    for where in CREATES:
        assert billing.route_writes(where, {"dry_run": False}) is True
        assert billing.route_writes(where, {"dry_run": True}) is False
