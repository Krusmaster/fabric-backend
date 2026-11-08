"""Round n171: Krusgraph bought through Microsoft Marketplace (fabric_backend/marketplace.py). The webhook's token
validation, each webhook action on the tenant's row, idempotency, resolve and activate against a fake fulfilment API,
the landing page with a fake sign-in, the licence check on the MCP tools and /workload/v1/build, routes absent with the
flag off, and the deploy script's dry run. Throw-away keys and fake HTTP; nothing here calls Entra, Azure or Fabric."""
import copy
import json
import time
import uuid
from types import SimpleNamespace

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import entitlements, marketplace as mp, server  # noqa: E402
from fabric_backend.entra import EntraConfig  # noqa: E402
from test_golden import SRC, fabric  # noqa: E402,F401  (the synthetic shop workspace, for the card in a browser)

OUR_TID = "11111111-0000-0000-0000-000000000001"           # the publisher's tenant
APP_ID = "22222222-0000-0000-0000-000000000002"           # the fulfilment app
SITE_APP = "33333333-0000-0000-0000-000000000003"         # the site's sign-in app
BUYER_TID = "44444444-0000-0000-0000-000000000004"
OTHER_TID = "55555555-0000-0000-0000-000000000005"
SUB = "66666666-0000-0000-0000-000000000006"
SUB2 = "77777777-0000-0000-0000-000000000007"
CFG = mp.Config(OUR_TID, APP_ID, "fulfilment-secret-value")
ENTRA = EntraConfig("https://krusgraph.example/mcp", SITE_APP, "site-secret-value")


@pytest.fixture(scope="module")
def priv():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.key)


def webhook_token(priv, **over):
    now = int(time.time())
    claims = {"aud": APP_ID, "iss": f"https://login.microsoftonline.com/{OUR_TID}/v2.0", "tid": OUR_TID,
              "azp": mp.SAAS_RESOURCE, "exp": now + 600, "iat": now - 5, "nbf": now - 5, **over}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, priv, algorithm="RS256")


def reply(status=200, body=None, headers=None):
    return SimpleNamespace(status_code=status, json=lambda: body if body is not None else {}, headers=headers or {})


class FakeAPI:
    """Entra's token endpoint and the SaaS fulfilment API as Microsoft documents them [M1][M4][M5]."""

    def __init__(self):
        self.calls, self.subs, self.ops, self.acks = [], {}, {}, []
        self.resolve_status = 200

    def __call__(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if url.endswith("/oauth2/v2.0/token"):
            return reply(200, {"access_token": "publisher-access-token", "expires_in": 3600, "token_type": "Bearer"})
        assert "api-version=2018-08-31" in url and kw["headers"]["Authorization"] == "Bearer publisher-access-token"
        path = url.split("/api/saas", 1)[1].split("?")[0]
        if method == "POST" and path == "/subscriptions/resolve":
            if self.resolve_status != 200:
                return reply(self.resolve_status)
            sub = self.subs[kw["headers"]["x-ms-marketplace-token"]]
            return reply(200, {"id": sub["id"], "subscriptionName": sub["name"], "offerId": sub["offerId"],
                               "planId": sub["planId"], "quantity": sub.get("quantity"), "subscription": sub})
        parts = path.split("/")
        sid = parts[2]
        if method == "POST" and path.endswith("/activate"):
            for s in self.subs.values():
                if s["id"] == sid:
                    s["saasSubscriptionStatus"] = "Subscribed"
            return reply(200)
        if method == "GET" and len(parts) == 3:
            return next((reply(200, s) for s in self.subs.values() if s["id"] == sid), reply(404))
        if method == "GET" and "operations" in parts:
            op = self.ops.get(parts[4])
            return reply(200, op) if op else reply(404)
        if method == "PATCH":
            self.acks.append((sid, parts[4], json.loads(kw["data"])))
            return reply(200)
        pytest.fail(f"unexpected call {method} {url}")


def subscription(sid=SUB, tid=BUYER_TID, status="PendingFulfillmentStart", plan="team"):
    return {"id": sid, "name": "Contoso Krusgraph", "publisherId": "krusecons", "offerId": "krusgraph-dev", "planId": plan,
            "saasSubscriptionStatus": status, "isFreeTrial": False, "isTest": True,
            "beneficiary": {"emailId": "buyer@contoso.example", "objectId": "obj-1", "tenantId": tid, "puid": "123"},
            "purchaser": {"emailId": "buyer@contoso.example", "objectId": "obj-1", "tenantId": tid, "puid": "123"},
            "term": {"termUnit": "P1M"}, "autoRenew": True}


def event(action, sid=SUB, tid=BUYER_TID, plan="team", quantity=None, op=None, ts="2026-11-08T10:00:00.0000000Z", status=None):
    sub = subscription(sid, tid, status or ("Suspended" if action in ("Suspend", "Reinstate") else "Subscribed"), "team")
    return {"id": op or str(uuid.uuid4()), "activityId": str(uuid.uuid4()), "publisherId": "krusecons",
            "offerId": "krusgraph-dev", "planId": plan, "quantity": quantity, "subscriptionId": sid, "timeStamp": ts,
            "action": action, "status": "InProgress" if action in mp.ACKNOWLEDGED else "Succeeded",
            "operationRequestSource": "Azure", "subscription": sub, "purchaseToken": None}


@pytest.fixture
def api():
    return FakeAPI()


@pytest.fixture
def subs():
    return mp.Subscriptions(mp.MemoryStore())


def hook(api, subs, body, later=None):
    api.ops[body["id"]] = {"id": body["id"], "subscriptionId": body["subscriptionId"], "action": body["action"],
                           "planId": body["planId"], "quantity": body["quantity"], "status": "InProgress"}
    return mp.handle_webhook(body, mp.Fulfilment(CFG, http=api), subs, run_later=later or (lambda fn: fn()))


# ------------------------------------------------------------------ the webhook's token ----------------------------

def test_webhook_token_good_and_both_issuer_forms(priv):
    v = mp.WebhookValidator(CFG, jwks_client=FakeJWKS(priv.public_key()))
    assert v.validate(webhook_token(priv))["tid"] == OUR_TID
    assert v.validate(webhook_token(priv, azp=None, appid=mp.SAAS_RESOURCE, iss=f"https://sts.windows.net/{OUR_TID}/"))


@pytest.mark.parametrize("over,why", [
    ({"aud": SITE_APP}, "wrong audience"),
    ({"azp": "99999999-0000-0000-0000-000000000009"}, "wrong appid"),
    ({"azp": None, "appid": None}, "wrong appid"),
    ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200, "nbf": int(time.time()) - 7200}, "expired"),
    ({"tid": OTHER_TID, "iss": f"https://login.microsoftonline.com/{OTHER_TID}/v2.0"}, "wrong tenant"),
    ({"iss": "https://login.microsoftonline.com/common/v2.0"}, "wrong issuer"),
])
def test_webhook_token_refused(priv, over, why):
    v = mp.WebhookValidator(CFG, jwks_client=FakeJWKS(priv.public_key()))
    with pytest.raises(mp.WebhookTokenError, match=why):
        v.validate(webhook_token(priv, **over))


def test_webhook_token_signed_by_another_key_is_refused(priv):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(mp.WebhookTokenError, match="invalid token"):
        mp.WebhookValidator(CFG, jwks_client=FakeJWKS(priv.public_key())).validate(webhook_token(other))


# ------------------------------------------------------------------ webhook actions -> the tenant's row -----------

def test_each_action_updates_the_tenant_row(api, subs):
    acks = []
    steps = [("Subscribe", {}, "Subscribed", "team", True), ("ChangePlan", {"plan": "team-annual"}, "Subscribed", "team-annual", True),
             ("ChangeQuantity", {"quantity": 3}, "Subscribed", "team-annual", True), ("Suspend", {}, "Suspended", "team", False),
             ("Reinstate", {}, "Subscribed", "team", True), ("Renew", {}, "Subscribed", "team", True),
             ("Unsubscribe", {}, "Unsubscribed", "team", False)]
    for i, (action, extra, status, plan, active) in enumerate(steps):
        body = event(action, plan=extra.get("plan", "team"), quantity=extra.get("quantity"), ts=f"2026-11-08T10:0{i}:00Z")
        code, out = hook(api, subs, body, later=lambda fn: (acks.append(action), fn()))
        assert (code, out) == (200, {"ok": True}), action
        row = subs.tenant(BUYER_TID, cached=False)
        assert row["status"] == status and row["subscription_id"] == SUB and row["plan"] == plan, action
        assert subs.active(BUYER_TID) is active or subs.tenant(BUYER_TID, cached=False)["active"] is active
        if action == "ChangeQuantity":
            assert json.loads(row["subscriptions"])[SUB]["quantity"] == 3
    assert acks == ["ChangePlan", "ChangeQuantity", "Reinstate"]                       # Patch operation for these only
    assert [a[2] for a in api.acks] == [{"status": "Success"}] * 3
    row = subs.tenant(BUYER_TID, cached=False)
    assert set(row) >= {"PartitionKey", "RowKey", "subscription_id", "offer", "plan", "status", "updated_at"}
    assert row["PartitionKey"] == "marketplace" and row["RowKey"] == BUYER_TID
    text = json.dumps(row)
    assert "buyer@contoso.example" not in text and "obj-1" not in text and "Contoso Krusgraph" not in text   # no user data


def test_webhook_is_idempotent_per_operation_id(api, subs):
    body = event("Subscribe")
    assert hook(api, subs, body) == (200, {"ok": True})
    gets = len([c for c in api.calls if "/operations/" in c[1]])
    assert hook(api, subs, copy.deepcopy(body)) == (200, {"ok": True, "duplicate": True})
    assert len([c for c in api.calls if "/operations/" in c[1]]) == gets               # not confirmed or applied twice
    late = event("Suspend", ts="2026-11-08T09:00:00Z")                                  # older than the Subscribe: ignored
    assert hook(api, subs, late)[0] == 200 and subs.tenant(BUYER_TID, cached=False)["status"] == "Subscribed"


def test_webhook_confirms_with_get_operation_and_never_rejects_a_change_by_accident(api, subs):
    body = event("ChangePlan", plan="team-annual")
    fulfil = mp.Fulfilment(CFG, http=api)
    code, _ = mp.handle_webhook(body, fulfil, subs, run_later=lambda fn: fn())        # Get operation answers 404
    assert code == 503 and subs.tenant(BUYER_TID, cached=False) is None and not api.acks   # retried, never a 4xx
    api.ops[body["id"]] = {"id": body["id"], "subscriptionId": SUB2, "action": "ChangePlan"}
    assert mp.handle_webhook(body, fulfil, subs)[0] == 503                             # payload does not match the operation
    assert mp.handle_webhook({"id": "x", "subscriptionId": SUB, "action": "Subscribe"}, fulfil, subs)[0] == 400
    assert mp.handle_webhook({**event("Something"), "action": "Something"}, fulfil, subs) == (200, {"ok": True, "ignored": "Something"})


def test_tenant_with_several_subscriptions_resolves_to_the_best_active(api, subs):
    assert hook(api, subs, event("Subscribe", sid=SUB, ts="2026-11-08T10:00:00Z"))[0] == 200
    assert hook(api, subs, event("Subscribe", sid=SUB2, plan="pilot", ts="2026-11-08T10:01:00Z"))[0] == 200
    assert hook(api, subs, event("Unsubscribe", sid=SUB2, plan="pilot", ts="2026-11-08T10:02:00Z"))[0] == 200
    row = subs.tenant(BUYER_TID, cached=False)
    assert row["subscription_id"] == SUB and row["status"] == "Subscribed" and subs.active(BUYER_TID)
    assert set(json.loads(row["subscriptions"])) == {SUB, SUB2}
    assert hook(api, subs, event("Suspend", sid=SUB, ts="2026-11-08T10:03:00Z"))[0] == 200
    assert not subs.tenant(BUYER_TID, cached=False)["active"]


def test_table_store_writes_with_optimistic_concurrency():
    rows, calls = {}, []

    def http(method, url, **kw):
        calls.append((method, url, kw.get("headers", {}).get("If-Match")))
        key = url.split("(", 1)[1] if "(" in url else None
        if method == "GET":
            return reply(200, rows[key][0], {"ETag": rows[key][1]}) if key in rows else reply(404)
        body = json.loads(kw["data"])
        k = f"PartitionKey='{body['PartitionKey']}',RowKey='{body['RowKey']}')"
        if method == "POST":
            if k in rows:
                return reply(409)
            rows[k] = (body, 'W/"1"')
            return reply(204)
        if rows[k][1] != kw["headers"]["If-Match"]:
            return reply(412)
        rows[k] = (body, f'W/"{int(rows[k][1][3:-1]) + 1}"')
        return reply(204)

    store = mp.TableStore("https://acct.table.core.windows.net/entitlements", http=http, token=lambda: "st")
    subs = mp.Subscriptions(store)
    subs.record(BUYER_TID, SUB, {"offer": "o", "plan": "team", "status": "Subscribed"})
    subs.record(BUYER_TID, SUB2, {"offer": "o", "plan": "pilot", "status": "Unsubscribed"})
    assert calls[1][0] == "POST" and calls[3] == ("PUT", f"https://acct.table.core.windows.net/entitlements(PartitionKey='marketplace',RowKey='{BUYER_TID}')", 'W/"1"')
    assert subs.active(BUYER_TID)


# ------------------------------------------------------------------ resolve and activate -------------------------

def test_resolve_and_activate_as_documented(api):
    api.subs["mt+/="] = subscription()
    f = mp.Fulfilment(CFG, http=api)
    out = f.resolve("mt+/=")
    assert out["id"] == SUB and out["planId"] == "team"
    token_call = api.calls[0]
    assert token_call[1] == f"https://login.microsoftonline.com/{OUR_TID}/oauth2/v2.0/token"
    assert token_call[2]["data"] == {"grant_type": "client_credentials", "client_id": APP_ID,
                                     "client_secret": "fulfilment-secret-value", "scope": f"{mp.SAAS_RESOURCE}/.default"}
    m, url, kw = api.calls[1]
    assert (m, url.split("?")[0]) == ("POST", "https://marketplaceapi.microsoft.com/api/saas/subscriptions/resolve")
    assert kw["headers"]["x-ms-marketplace-token"] == "mt+/=" and kw["headers"]["x-ms-requestid"]
    f.activate(SUB)
    assert api.calls[-1][1].startswith(f"https://marketplaceapi.microsoft.com/api/saas/subscriptions/{SUB}/activate?api-version=2018-08-31")
    assert len([c for c in api.calls if c[1].endswith("/token")]) == 1                # the publisher token is cached
    api.resolve_status = 400
    with pytest.raises(mp.MarketplaceError, match="expired"):
        f.resolve("old")
    assert "fulfilment-secret-value" not in repr(CFG)


# ------------------------------------------------------------------ the landing page ------------------------------

class FakeSignIn(mp.SignIn):
    def __init__(self, tid=BUYER_TID):
        super().__init__(ENTRA)
        self.tid, self.redeemed = tid, []

    def redeem(self, origin, code, verifier, nonce):
        self.redeemed.append((origin, code))
        return {"tid": self.tid, "oid": "someone", "nonce": nonce}


def landing_app(api, subs, signin, monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://testserver/mcp")
    routes = mp.routes(ENTRA, fulfilment=mp.Fulfilment(CFG, http=api), validator=mp.WebhookValidator(CFG, jwks_client=object()),
                       subs=subs, signin=signin)
    return TestClient(Starlette(routes=routes), base_url="https://testserver")


def test_landing_flow_signs_in_resolves_shows_and_activates(api, subs, monkeypatch):
    api.subs["mt-1"] = subscription()
    signin = FakeSignIn()
    c = landing_app(api, subs, signin, monkeypatch)
    r = c.get("/marketplace/landing", params={"token": "mt-1"}, follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?")
    assert f"client_id={SITE_APP}" in loc and "scope=openid+profile&" in loc and "code_challenge_method=S256" in loc
    assert "redirect_uri=https%3A%2F%2Ftestserver%2Fmarketplace%2Fcallback" in loc and "mt-1" not in loc
    state = dict(p.split("=", 1) for p in loc.split("?", 1)[1].split("&"))["state"]
    page = c.get("/marketplace/callback", params={"code": "c0de", "state": state})
    assert page.status_code == 200 and signin.redeemed == [("https://testserver", "c0de")]
    for shown in ("krusgraph-dev", "team", BUYER_TID, "PendingFulfillmentStart", "Activate the subscription"):
        assert shown in page.text
    assert "buyer@contoso.example" not in page.text and "payment details" in page.text   # no payment details asked
    assert subs.tenant(BUYER_TID, cached=False)["status"] == "PendingFulfillmentStart" and not subs.active(BUYER_TID)
    csrf = page.text.split('name="csrf" value="', 1)[1].split('"', 1)[0]
    assert c.post("/marketplace/activate", data={"csrf": "wrong"}).status_code == 400
    done = c.post("/marketplace/activate", data={"csrf": csrf}, headers={"Origin": "https://testserver"})
    assert done.status_code == 200 and "Activated" in done.text and "Open Fabric" in done.text and "Connect Claude" in done.text
    assert any(m == "POST" and u.split("?")[0].endswith(f"/subscriptions/{SUB}/activate") for m, u, _ in api.calls)
    assert subs.active(BUYER_TID)
    assert "<script" not in done.text.lower()                                          # a plain page, no scripts
    assert done.headers["content-security-policy"].startswith("default-src 'none'") and done.headers["cache-control"] == "no-store"


def test_landing_auto_activation_shows_nothing_to_activate(api, subs, monkeypatch):
    api.subs["mt-2"] = subscription(status="Subscribed")
    c = landing_app(api, subs, FakeSignIn(), monkeypatch)
    loc = c.get("/marketplace/landing", params={"token": "mt-2"}, follow_redirects=False).headers["location"]
    state = dict(p.split("=", 1) for p in loc.split("?", 1)[1].split("&"))["state"]
    page = c.get("/marketplace/callback", params={"code": "x", "state": state})
    assert "nothing to activate" in page.text and "Activate the subscription" not in page.text and "Open Fabric" in page.text
    assert not any(u.split("?")[0].endswith("/activate") for _, u, _ in api.calls)


def test_landing_refuses_another_tenant_an_expired_token_and_a_foreign_state(api, subs, monkeypatch):
    api.subs["mt-3"] = subscription()
    c = landing_app(api, subs, FakeSignIn(tid=OTHER_TID), monkeypatch)
    loc = c.get("/marketplace/landing", params={"token": "mt-3"}, follow_redirects=False).headers["location"]
    state = dict(p.split("=", 1) for p in loc.split("?", 1)[1].split("&"))["state"]
    page = c.get("/marketplace/callback", params={"code": "x", "state": state})
    assert "another organisation" in page.text and "Activate the subscription" not in page.text
    assert c.get("/marketplace/callback", params={"code": "x", "state": state}).status_code == 400   # used once
    c.get("/marketplace/landing", params={"token": "mt-3"}, follow_redirects=False)
    assert c.get("/marketplace/callback", params={"code": "x", "state": "forged"}).status_code == 400
    api.resolve_status = 400
    loc = c.get("/marketplace/landing", params={"token": "mt-3"}, follow_redirects=False).headers["location"]
    state = dict(p.split("=", 1) for p in loc.split("?", 1)[1].split("&"))["state"]
    page = c.get("/marketplace/callback", params={"code": "x", "state": state})
    assert page.status_code == 400 and "We couldn't identify this purchase." in page.text and "Configure Account" in page.text
    assert "Nothing to show yet" in c.get("/marketplace/landing").text


def test_id_token_is_validated_with_nonce_audience_and_issuer(priv):
    s = mp.SignIn(ENTRA, jwks_client=FakeJWKS(priv.public_key()))
    now = int(time.time())
    good = {"aud": SITE_APP, "iss": f"https://login.microsoftonline.com/{BUYER_TID}/v2.0", "tid": BUYER_TID, "nonce": "n1",
            "exp": now + 600, "iat": now}
    assert s.validate_id_token(jwt.encode(good, priv, algorithm="RS256"), "n1")["tid"] == BUYER_TID
    for bad, nonce in (({**good, "aud": APP_ID}, "n1"), (good, "n2"), ({**good, "iss": "https://login.microsoftonline.com/common/v2.0"}, "n1")):
        with pytest.raises(mp.MarketplaceError):
            s.validate_id_token(jwt.encode(bad, priv, algorithm="RS256"), nonce)


def test_webhook_route_checks_the_token_then_records(api, subs, priv, monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://testserver/mcp")
    routes = mp.routes(ENTRA, fulfilment=mp.Fulfilment(CFG, http=api),
                       validator=mp.WebhookValidator(CFG, jwks_client=FakeJWKS(priv.public_key())), subs=subs,
                       signin=FakeSignIn(), run_later=lambda fn: fn())
    c = TestClient(Starlette(routes=routes), base_url="https://testserver")
    body = event("Subscribe")
    api.ops[body["id"]] = {"id": body["id"], "subscriptionId": SUB, "action": "Subscribe"}
    assert c.post("/marketplace/webhook", json=body).status_code == 401
    assert c.post("/marketplace/webhook", json=body, headers={"Authorization": "Bearer " + webhook_token(priv, aud=SITE_APP)}).status_code == 401
    assert not subs.active(BUYER_TID)
    r = c.post("/marketplace/webhook", json=body, headers={"Authorization": "Bearer " + webhook_token(priv)})
    assert r.status_code == 200 and subs.active(BUYER_TID)


# ------------------------------------------------------------------ the licence check ------------------------------

@pytest.fixture
def shop(monkeypatch):
    from fabric_backend import seed
    from fabric_backend.schema import Schema
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: "ws-1")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, h: {"type": "Lakehouse", "id": "lh-1", "displayName": src, "sql_host": "h", "sql_db": src})
    ran = []
    ex = lambda sql: []  # noqa: E731
    ex.statement = lambda sql: ran.append(sql)
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: ex)
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    monkeypatch.setattr(server, "_identity", lambda ctx: {"oid": "u", "tid": BUYER_TID})
    return ran


@pytest.fixture
def market(monkeypatch, subs):
    monkeypatch.setenv("KRUSGRAPH_ENTITLEMENTS", "1")
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE", "1")
    monkeypatch.setenv("KRUSGRAPH_ENTITLEMENTS_SOURCE", "env")
    monkeypatch.delenv("KRUSGRAPH_ENTITLED_TENANTS", raising=False)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_OFFER_URL", "https://marketplace.microsoft.com/product/krusecons.krusgraph-dev")
    mp.set_store(subs)
    yield subs
    mp.set_store(None)


def test_no_subscription_means_upgrade_on_create_only(shop, market):
    out = json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))
    assert out["kind"] == "upgrade" and out["upgrade_url"].startswith("https://marketplace.microsoft.com/")
    assert out["upgrade_url"] in out["hint"] and not shop                               # nothing ran
    assert json.loads(server.create_backend("Sales", "shop_lh", "shop_api", schema="shop", dry_run=False))["kind"] == "upgrade"
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop"))["dry_run"] is True       # dry runs free
    assert entitlements.check("create_backend", True, BUYER_TID) is None
    assert "error" not in json.loads(server.plan_backend("Sales", "shop_lh", schema="shop"))            # reads free
    market.record(BUYER_TID, SUB, {"offer": "krusgraph-dev", "plan": "team", "status": "Subscribed"})
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["result"]["status"] == "Succeeded"
    market.record(BUYER_TID, SUB, {"status": "Suspended"})
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["kind"] == "upgrade"


def test_flags_off_change_nothing(shop, monkeypatch):
    for v in ("KRUSGRAPH_ENTITLEMENTS", "KRUSGRAPH_MARKETPLACE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(mp, "features", lambda tid: pytest.fail("no lookup while the flags are off"))
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["result"]["status"] == "Succeeded"
    assert entitlements.feature_of("create_backend", False) is None
    monkeypatch.setenv("KRUSGRAPH_ENTITLEMENTS", "1")                                   # entitlements alone: as before n171
    monkeypatch.setenv("KRUSGRAPH_ENTITLED_TENANTS", "{}")
    assert entitlements.feature_of("create_backend", False) is None
    assert "upgrade_url" not in entitlements.check("create_views", False, BUYER_TID)
    monkeypatch.delenv("KRUSGRAPH_ENTITLEMENTS")
    paths = _paths(server.build_app())
    assert "/healthz" in paths and not any(p.startswith("/marketplace") for p in paths)       # no route at all


def _paths(app) -> set:
    """Every route path of the app build_app returns, through its ASGI wrappers (closures and .app attributes)."""
    seen, stack, visited = set(), [app], set()
    while stack:
        a = stack.pop()
        if id(a) in visited:
            continue
        visited.add(id(a))
        for name in ("app", "inner", "_app"):
            if hasattr(a, name):
                stack.append(getattr(a, name))
        for r in getattr(getattr(a, "router", None), "routes", []) or []:
            seen.add(getattr(r, "path", ""))
        if getattr(a, "__closure__", None):
            for cell in a.__closure__:
                try:
                    v = cell.cell_contents
                except ValueError:
                    continue
                if v is not a and (hasattr(v, "router") or callable(v) and getattr(v, "__closure__", None)):
                    stack.append(v)
    return seen


def test_marketplace_routes_exist_only_with_the_flag(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE", "1")
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_TENANT_ID", OUR_TID)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_CLIENT_ID", APP_ID)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_CLIENT_SECRET", "x")
    assert {"/marketplace/landing", "/marketplace/webhook"} <= _paths(server.build_app())
    monkeypatch.delenv("KRUSGRAPH_MARKETPLACE_CLIENT_SECRET")
    with pytest.raises(ValueError, match="KRUSGRAPH_MARKETPLACE_CLIENT_SECRET"):
        server.build_app()


def test_workload_build_answers_upgrade_on_create_and_stays_free_on_dry_run(market, monkeypatch, priv):
    from fabric_backend import workload_api
    claims = {"tid": BUYER_TID, "oid": "u", "scp": "user_impersonation"}
    validator = SimpleNamespace(validate=lambda token: claims)
    ran = []
    monkeypatch.setattr(workload_api, "run_build", lambda req: ran.append(req["dry_run"]) or {"dry_run": req["dry_run"]})
    routes = workload_api.routes(SimpleNamespace(), validator=validator, obo=object())
    c = TestClient(Starlette(routes=routes))
    body = {"workspace": "ws", "source": "lh", "source_name": "lh", "schema": "shop", "name": "shop_api",
            "review": {"version": 1}, "outputs": ["graphql"]}
    monkeypatch.setattr(workload_api, "build_request", lambda b: {**b, "dry_run": b.get("dry_run", True)})
    r = c.post("/workload/v1/build", json={**body, "dry_run": False}, headers={"Authorization": "Bearer t"})
    assert r.status_code == 402 and r.json()["kind"] == "upgrade" and "upgrade_url" in r.json() and ran == []
    r = c.post("/workload/v1/build", json=body, headers={"Authorization": "Bearer t"})
    assert r.status_code == 200 and ran == [True]
    market.record(BUYER_TID, SUB, {"offer": "o", "plan": "team", "status": "Subscribed"})
    assert c.post("/workload/v1/build", json={**body, "dry_run": False}, headers={"Authorization": "Bearer t"}).status_code == 200
    assert ran == [True, False]


# ------------------------------------------------------------------ deploy ----------------------------------------

def test_deploy_dry_run_carries_the_marketplace_variables_and_lists_what_to_set(capsys, monkeypatch):
    from deploy import azure_containerapp as d
    from tests.test_deploy_workload import CONFIG, FakeApp
    monkeypatch.setattr(d, "verify_server", lambda *a, **k: None, raising=False)
    legacy = {k: v for k, v in CONFIG.items() if k not in d.MARKETPLACE_FLAGS and k not in d.MARKETPLACE_ENV}   # before n171
    az = FakeApp(env={"KRUSGRAPH_MARKETPLACE": "1", "KRUSGRAPH_MARKETPLACE_TENANT_ID": OUR_TID}, secret=False)
    assert d.update(az, legacy | {"marketplace_client_id": APP_ID, "entitlements": True}, dry_run=True) is None
    assert {c[:2] for c in az.calls} == {("containerapp", "show")}                      # read only
    out = capsys.readouterr().out
    assert "KRUSGRAPH_MARKETPLACE=1" in out and f"KRUSGRAPH_MARKETPLACE_TENANT_ID={OUR_TID}" in out
    assert '"marketplace": true' in out and '"marketplace_tenant_id"' in out             # carried, and named
    assert f"KRUSGRAPH_MARKETPLACE_CLIENT_ID={APP_ID}" in out and "KRUSGRAPH_ENTITLEMENTS=1" in out
    assert "marketplace-secret" in out and 'read -rsp' in out                            # how to store the secret, hidden
    assert "saknas KRUSGRAPH_MARKETPLACE_OFFER_URL" in out and "ok     KRUSGRAPH_MARKETPLACE_TENANT_ID" in out
    assert "/marketplace/callback" in out and "Storage Table Data Contributor" in out
    with pytest.raises(d.DeploymentError, match="marketplace-secret"):
        d.update(FakeApp(env={"KRUSGRAPH_MARKETPLACE": "1"}, secret=False), legacy)
    capsys.readouterr()
    assert d.update(FakeApp(env={"KRUSGRAPH_MARKETPLACE": "1"}), CONFIG | {"marketplace": False}, dry_run=True) is None
    assert "KRUSGRAPH_MARKETPLACE=0" in capsys.readouterr().out                         # false switches it off again


# ------------------------------------------------------------------ the card's Create ------------------------------

def test_in_a_browser_create_without_a_subscription_shows_the_upgrade_and_opens_the_offer(tmp_path, fabric):  # noqa: F811
    import subprocess
    from pathlib import Path
    from test_n169_clickable_cards import _call, _playwright
    if not _playwright():
        pytest.skip("node + playwright not available")
    from fabric_backend import mcp_apps_build as build
    plan = _call("plan_backend", **SRC)
    button = next(a for a in plan["actions"] if a["tool"] == "create_semantic_model")
    dry = _call("create_semantic_model", **button["arguments"])
    url = "https://marketplace.microsoft.com/product/krusecons.krusgraph-dev"
    refused = {"error": "Creating items in Fabric needs a Krusgraph subscription for your organisation, and it has none that is active.",
               "kind": "upgrade", "feature": "create", "upgrade_url": url, "hint": f"Subscribe through Microsoft Marketplace: {url}"}
    (tmp_path / "card.html").write_text(build.card_html())
    (tmp_path / "data.json").write_text(json.dumps({"args": SRC, "plan": plan, "dry": dry, "created": refused}))
    run = subprocess.run(["node", str(Path(__file__).parent / "mcp_apps_build_browser.js"), str(tmp_path / "card.html"),
                          str(tmp_path / "data.json"), "tools"], capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["errors"] == [] and "needs a Krusgraph subscription" in out["text"] and "Subscribe through Microsoft Marketplace" in out["text"]
    assert [m["params"]["url"] for m in out["log"] if m.get("method") == "ui/open-link"] == [url]
    assert out["createEnabled"] is True                                                 # Create again after subscribing
