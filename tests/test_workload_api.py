"""Round n166: the Fabric workload's engine API (fabric_backend/workload_api.py), phase 1 of docs/WORKLOAD-FEASIBILITY.md.

A separate token audience for the workload's own Entra app (entra.WorkloadConfig): its tokens are accepted on
/workload/v1/*, the MCP app's and anybody else's are not, and the MCP validator does not accept a workload token. The
review and build answers on seed.py's synthetic shop schema (Fabric REST and the SQL endpoint are the doubles of
tests/golden_support.py); a build with the default dry run writes nothing; the routes do not exist without the
KRUSGRAPH_WORKLOAD_* variables; CORS and frame-ancestors name Fabric's domains only."""
import json
import sys
import time

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import golden_support as gs  # noqa: E402
from fabric_backend import entra, server, workload_api  # noqa: E402
from fabric_backend.entra import EntraConfig, TokenError, Validator, WorkloadConfig  # noqa: E402

TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MCP = EntraConfig("https://mcp.example.com/mcp", "11111111-2222-3333-4444-555555555555", "mcp-secret")
WL_URI = f"api://localdevinstance/{TID}/Org.Krusgraph/Ab"
WL = WorkloadConfig("99999999-8888-7777-6666-555555555555", "wl-secret", WL_URI)
WL_ENV = {"KRUSGRAPH_WORKLOAD_CLIENT_ID": WL.client_id, "KRUSGRAPH_WORKLOAD_CLIENT_SECRET": "wl-secret",
          "KRUSGRAPH_WORKLOAD_APP_ID_URI": WL_URI}
SRC = {"workspace": gs.WS, "source": "demo_lh", "source_name": "demo_lh", "schema": "shop"}
FABRIC_ORIGIN = "https://app.fabric.microsoft.com"


class FakeJWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key})()


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def tok(priv, **over):
    claims = {"aud": WL_URI, "iss": f"https://login.microsoftonline.com/{TID}/v2.0", "tid": TID,
              "exp": int(time.time()) + 600, "scp": "user_impersonation", "oid": "user-1"}
    claims.update(over)
    return jwt.encode(claims, priv, algorithm="RS256")


class FakeOBO:
    """Records each exchange: the routes must run as the user, through on-behalf-of, never with a stored identity."""

    def __init__(self):
        self.calls = []

    def token(self, user_token, tenant, scope):
        self.calls.append((tenant, scope))
        return f"obo:{scope}"


@pytest.fixture
def api(keys, monkeypatch):
    """A client on the workload routes alone, with the Fabric and SQL doubles; returns (client, fake fabric, obo)."""
    import requests
    from starlette.applications import Starlette
    priv, pub = keys
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
    monkeypatch.setattr(server, "limiter", None)
    obo = FakeOBO()
    app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), obo))
    return TestClient(app), fake, obo, priv


def _post(client, path, body, token, origin=FABRIC_ORIGIN):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    if origin:
        h["Origin"] = origin
    return client.post(workload_api.PREFIX + path, json=body, headers=h)


def _writes(fake):
    return [c for c in fake.calls if c[0] != "GET" and not c[1].endswith("/getDefinition")]


# ------------------------------------------------------------------ the audience ------------------------------------

def test_the_workload_audience_is_accepted_and_the_mcp_and_foreign_audiences_are_not(keys):
    priv, pub = keys
    v = Validator(WL, FakeJWKS(pub))
    assert v.validate(tok(priv))["tid"] == TID
    assert v.validate(tok(priv, aud=WL.client_id))["tid"] == TID
    for aud in (MCP.public_url, MCP.client_id, f"api://{MCP.client_id}", "api://someone-else", "https://graph.microsoft.com"):
        with pytest.raises(TokenError):
            v.validate(tok(priv, aud=aud))
    with pytest.raises(TokenError):                                   # and the MCP server does not take a workload token
        Validator(MCP, FakeJWKS(pub)).validate(tok(priv))
    assert Validator(MCP, FakeJWKS(pub)).validate(tok(priv, aud=MCP.public_url))["tid"] == TID   # unchanged for /mcp


def test_the_workload_scope_is_its_own_setting(keys, monkeypatch):
    priv, pub = keys
    for k, v in WL_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_SCOPE", "Model.Build")
    cfg = WorkloadConfig.from_env()
    assert Validator(cfg, FakeJWKS(pub)).validate(tok(priv, scp="Model.Build"))["tid"] == TID
    with pytest.raises(TokenError, match="Model.Build"):
        Validator(cfg, FakeJWKS(pub)).validate(tok(priv))


def test_configuration_is_all_or_nothing_and_never_the_mcp_app(monkeypatch):
    for k in WL_ENV:
        monkeypatch.delenv(k, raising=False)
    assert WorkloadConfig.from_env() is None
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_CLIENT_ID", WL.client_id)
    with pytest.raises(ValueError, match="KRUSGRAPH_WORKLOAD_CLIENT_SECRET"):
        WorkloadConfig.from_env()
    for k, v in WL_ENV.items():
        monkeypatch.setenv(k, v)
    assert WorkloadConfig.from_env(MCP).audiences[0] == WL_URI
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_CLIENT_ID", MCP.client_id)
    with pytest.raises(ValueError, match="own Entra app"):
        WorkloadConfig.from_env(MCP)


def test_requests_without_a_good_token_get_401_and_reach_nothing(api):
    client, fake, obo, priv = api
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for token in ("", tok(priv, aud=MCP.public_url), tok(priv, aud="api://foreign"), tok(other)):
        r = _post(client, "/review", SRC, token)
        assert r.status_code == 401 and r.json()["kind"] == "sign_in", r.text
        assert r.headers["www-authenticate"].startswith("Bearer ")
    assert fake.calls == [] and obo.calls == []


# ------------------------------------------------------------------ the routes are off without the variables --------

def test_the_routes_are_off_when_the_variables_are_unset(monkeypatch):
    for k in list(WL_ENV) + ["MCP_PUBLIC_URL", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_REQUIRED",
                             "ENTRA_CLIENT_SECRET_KEYVAULT_URI"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(server.auth, "entra", None)
    client = TestClient(server.build_app())
    for path in ("/review", "/build"):
        assert client.post(workload_api.PREFIX + path, json=SRC).status_code == 404


def test_the_routes_are_on_with_the_variables_and_mcp_is_unchanged(monkeypatch):
    for k, v in WL_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(server.auth, "entra", None)
    client = TestClient(server.build_app())
    r = client.post(workload_api.PREFIX + "/review", json=SRC)
    assert r.status_code == 401 and r.json()["kind"] == "sign_in"
    assert client.get("/healthz").status_code == 200


# ------------------------------------------------------------------ CORS and frames ---------------------------------

@pytest.mark.parametrize("origin", ["https://app.fabric.microsoft.com", "https://app.powerbi.com", "https://msit.fabric.microsoft.com"])
def test_preflight_from_fabric_is_allowed(api, origin):
    client = api[0]
    r = client.options(workload_api.PREFIX + "/build", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == origin
    assert "Authorization" in r.headers["access-control-allow-headers"]


@pytest.mark.parametrize("origin", ["https://krusgraph.com", "https://evil.example", "http://app.fabric.microsoft.com",
                                    "https://fabric.microsoft.com.evil.example", "https://evilpowerbi.com"])
def test_other_origins_are_refused(api, origin):
    client, fake, obo, priv = api
    r = client.options(workload_api.PREFIX + "/review", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    assert r.status_code == 403 and "access-control-allow-origin" not in r.headers
    r = _post(client, "/review", SRC, tok(priv), origin=origin)
    assert r.status_code == 403 and fake.calls == [] and obo.calls == []


def test_answers_may_be_framed_only_by_fabric(api):
    client, _, _, priv = api
    r = _post(client, "/review", SRC, tok(priv))
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors https://*.fabric.microsoft.com https://*.powerbi.com" in csp
    assert r.headers["cache-control"] == "no-store"


# ------------------------------------------------------------------ review ------------------------------------------

def test_review_on_the_shop_schema(api):
    client, fake, obo, priv = api
    r = _post(client, "/review", SRC, tok(priv))
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {"review", "summary", "attention", "counts", "map", "note", "suggested_products"}   # n173: the map; n222
    rv = out["review"]
    assert rv["format"] == "krusgraph-review" and rv["version"] == 1
    assert rv["source"] == {"platform": "fabric", "source": "demo_lh", "schema": "shop"}      # names, no ids
    assert set(rv["snapshot"]["tables"]) == {"customers", "categories", "products", "addresses", "orders", "order_items", "audit_log"}
    rules = {it["rule"][0] for it in rv["items"]}
    assert rules <= {"K", "R"} and {"K", "R"} <= rules                                     # the K and R pills
    assert out["counts"]["keys"] + out["counts"]["relationships"] == len(rv["items"])
    assert {s for _, s in obo.calls} == {entra.FABRIC_SCOPE, entra.SQL_SCOPE}   # as the user, OBO
    assert _writes(fake) == []
    text = json.dumps(out)
    assert "Harbour Bikes" not in text and "obo:" not in text and "wl-secret" not in text     # no row values, tokens, secrets


def test_reopening_reapplies_the_saved_decisions(api):
    client, _, _, priv = api
    first = _post(client, "/review", SRC, tok(priv)).json()["review"]
    rel = next(it["id"] for it in first["items"] if it["type"] == "relationship")
    decided = _post(client, "/review", {**SRC, "decisions": [{"item": rel, "review": "rejected", "reason": "not a reference"}]},
                    tok(priv)).json()["review"]
    again = _post(client, "/review", {**SRC, "previous": decided}, tok(priv)).json()
    item = next(it for it in again["review"]["items"] if it["id"] == rel)
    assert item["review"] == "rejected" and item["reason"] == "not a reference"
    assert again["review"]["since_previous"]["source_differs"] == []


@pytest.mark.parametrize("body, word", [({"source": "demo_lh"}, "workspace"), ({**SRC, "previous": "x"}, "previous"),
                                        ({**SRC, "decisions": "x"}, "decisions")])
def test_review_refuses_bad_bodies(api, body, word):
    client, fake, _, priv = api
    r = _post(client, "/review", body, tok(priv))
    assert r.status_code == 400 and word in r.json()["error"] and fake.calls == []


# ------------------------------------------------------------------ build -------------------------------------------

def _reviewed(client, priv, decisions=None):
    return _post(client, "/review", {**SRC, "decisions": decisions or []}, tok(priv)).json()["review"]


def test_build_is_a_dry_run_by_default_and_writes_nothing(api):
    client, fake, _, priv = api
    rv = _reviewed(client, priv)
    fake.calls.clear()
    r = _post(client, "/build", {**SRC, "name": "shop_model_api", "review": rv}, tok(priv))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["dry_run"] is True and out["output"] == "graphql" and out["would"] == "create"
    assert out["left_out_by_review"] == [] and "checks_passed" in out and "Nothing was created" in out["note"]
    assert "created" not in out and "result" not in out
    assert _writes(fake) == [] and fake.created == []


def test_build_leaves_out_what_the_review_rejected(api):
    client, fake, _, priv = api
    rv = _reviewed(client, priv)
    rel = next(it for it in rv["items"] if it["type"] == "relationship")
    rv = _reviewed(client, priv, [{"item": rel["id"], "review": "rejected"}])
    out = _post(client, "/build", {**SRC, "name": "shop_model_api", "review": rv}, tok(priv)).json()
    assert [x["id"] for x in out["left_out_by_review"]] == [rel["id"]]
    assert _writes(fake) == []


def test_a_real_build_creates_the_api_and_says_what_is_left(api):
    client, fake, _, priv = api
    rv = _reviewed(client, priv)
    out = _post(client, "/build", {**SRC, "name": "shop_model_api", "review": rv, "dry_run": False}, tok(priv)).json()
    assert out["dry_run"] is False and len(fake.created) == 1, out
    assert out["created"][0]["type"] == "GraphQLApi" and out["endpoint"].endswith("/graphql")
    assert len(out["portal_steps"]) == 2


@pytest.mark.parametrize("extra, word", [({"outputs": ["semantic_model"]}, "send outputs as [{kind, name}]"),
                                         ({"name": "bad name"}, "letters, digits"), ({"dry_run": "no"}, "dry_run"),
                                         ({"review": None}, "review")])
def test_build_refuses_what_phase_1_s_form_does_not_do(api, extra, word):
    client, fake, _, priv = api
    body = {**SRC, "name": "shop_model_api", "review": {"format": "krusgraph-review"}, **extra}
    r = _post(client, "/build", body, tok(priv))
    assert r.status_code == 400 and word in r.json()["error"] and fake.calls == []


def test_the_mcp_tools_still_take_their_tokens_from_the_request(monkeypatch):
    """Outside a workload call the override is empty: Auth answers as before (here: no Entra, a bearer on the request)."""
    monkeypatch.setattr(server.auth, "entra", None)
    ctx = type("C", (), {"headers": {"authorization": "Bearer from-mcp"}})()
    assert server.auth.fabric(ctx) == "from-mcp"
    with server.workload_tokens(type("T", (), {"fabric": lambda self: "from-workload", "sql": lambda self: "s"})()):
        assert server.auth.fabric(ctx) == "from-workload"
    assert server.auth.fabric(ctx) == "from-mcp"
