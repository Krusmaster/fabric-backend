"""n210: a Microsoft Entra B2B guest in the publisher's tenant (docs/GUEST-TRIAL.md) uses the Krusgraph Model like a member.

A guest's access token for the publisher's workload app is issued by the publisher's tenant: `tid` and `iss` name the
publisher (the resource tenant), not the guest's home tenant. Its other claims can differ from a member's: `idp` names the
guest's home issuer, `acct` is 1, `upn` is usually missing, `preferred_username` (when present) is the home sign-in name, and
`email` may be the only readable name. Throw-away keys and fake HTTP; nothing calls Entra or Fabric."""
from __future__ import annotations

import time

import pytest

jwt = pytest.importorskip("jwt")

from test_workload_api import FakeJWKS, FakeOBO, TID, WL, WL_URI, keys  # noqa: E402,F401
from fabric_backend import operations, server, workload_api  # noqa: E402
from fabric_backend.entra import TenantNotAllowed, Validator, WorkloadConfig  # noqa: E402

HOME_TID = "12345678-0000-4000-8000-00000000abcd"             # the guest's own organisation (fake)
FABRIC_ORIGIN = "https://app.fabric.microsoft.com"


def guest_claims(**over) -> dict:
    claims = {"aud": WL_URI, "iss": f"https://login.microsoftonline.com/{TID}/v2.0", "tid": TID,
              "exp": int(time.time()) + 600, "iat": int(time.time()) - 5, "scp": "user_impersonation",
              "oid": "0b5e57a1-0000-4000-8000-000000000001", "sub": "guest-sub",
              "idp": f"https://sts.windows.net/{HOME_TID}/", "acct": 1,
              "name": "Eva Gäst", "preferred_username": "eva@contoso.example", "email": "eva@contoso.example"}
    claims.update(over)
    return {k: v for k, v in claims.items() if v is not None}


def guest(priv, **over) -> str:
    return jwt.encode(guest_claims(**over), priv, algorithm="RS256")


def allowed(*tenants) -> WorkloadConfig:
    return WorkloadConfig(WL.client_id, "wl-secret", WL_URI, allowed_tenants={t.lower() for t in tenants})


def test_a_guest_token_passes_the_validator_on_the_publishers_tenant(keys):
    priv, pub = keys
    claims = Validator(WL, FakeJWKS(pub)).validate(guest(priv))
    assert claims["tid"] == TID and claims["acct"] == 1


def test_the_allowed_tenants_list_is_the_publishers_tenant_never_the_guests_home(keys):
    priv, pub = keys
    assert Validator(allowed(TID.upper()), FakeJWKS(pub)).validate(guest(priv))["tid"] == TID
    with pytest.raises(TenantNotAllowed) as e:                # the guest's home tenant on the list does not let a guest in
        Validator(allowed(HOME_TID), FakeJWKS(pub)).validate(guest(priv))
    assert e.value.tenant == TID


def test_a_token_from_the_guests_home_tenant_is_not_taken_for_the_publishers(keys):
    priv, pub = keys
    with pytest.raises(TenantNotAllowed):
        Validator(allowed(TID), FakeJWKS(pub)).validate(
            guest(priv, tid=HOME_TID, iss=f"https://login.microsoftonline.com/{HOME_TID}/v2.0", idp=None, acct=None))


def test_a_guests_operations_are_keyed_to_the_guest_in_the_publishers_tenant():
    a = operations.owner_of(guest_claims())
    assert a == operations.owner_of(guest_claims(idp=None, acct=None, email=None, preferred_username=None, name=None))
    assert a != operations.owner_of(guest_claims(oid="0b5e57a1-0000-4000-8000-000000000002"))
    assert a != operations.owner_of(guest_claims(tid=HOME_TID))


@pytest.mark.parametrize("over, by", [
    ({}, "Eva Gäst"),
    ({"name": None}, "eva@contoso.example"),
    ({"name": None, "preferred_username": None}, "eva@contoso.example"),                    # only email: a guest's usual case
    ({"name": None, "preferred_username": None, "email": None, "upn": "eva_contoso.example#EXT#@pub.example"},
     "eva@contoso.example"),                                                               # the guest UPN, read back
    ({"name": None, "preferred_username": None, "email": None, "unique_name": "live.com#eva@contoso.example"},
     "eva@contoso.example"),
])
def test_who_is_recorded_for_a_guest(over, by):
    assert workload_api.who(guest_claims(**over)) == by


@pytest.fixture
def client(keys, monkeypatch):
    import requests
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    priv, pub = keys
    seen = {}

    def fake_product(req):
        seen.update(req)
        return {"items": [], "you": req.get("by", ""), "people": [], "note": "nothing changed"}
    monkeypatch.setattr(workload_api, "run_product", fake_product)
    for verb in ("get", "post", "patch", "delete", "put"):
        monkeypatch.setattr(requests, verb, lambda *a, **k: pytest.fail("no HTTP in this test"))
    monkeypatch.setattr(server, "limiter", None)
    app = Starlette(routes=workload_api.routes(allowed(TID), Validator(allowed(TID), FakeJWKS(pub)), FakeOBO()))
    return TestClient(app, raise_server_exceptions=False), priv, seen


def test_the_product_route_answers_a_guest_with_only_an_email_claim(client):
    c, priv, seen = client
    body = {"workspace": "11111111-1111-4111-8111-111111111111", "item_id": "22222222-2222-4222-8222-222222222222",
            "outputs": {}, "product": "Shop sales", "plan_id": "plan-0123456789ab", "action": "status"}
    r = c.post(workload_api.PREFIX + "/product", json=body, headers={
        "Authorization": f"Bearer {guest(priv, name=None, preferred_username=None)}", "Origin": FABRIC_ORIGIN})
    assert r.status_code == 200, r.text
    assert r.json()["you"] == "eva@contoso.example" and seen["by"] == "eva@contoso.example"
