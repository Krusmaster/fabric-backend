"""Client registration for MCP clients other than Claude (KRUSGRAPH_CLIENT_REGISTRATION, fabric_backend/registration.py).

Off by default: nothing is served and Claude's sign-in is unchanged; tests below lock both modes. On: VS Code and a
Glama-like client sign in with a client ID metadata document, Cursor and Glama with dynamic client registration, each
through Krusgraph's own consent page, against a mocked Entra that enforces its own PKCE, redirect address and single use."""
import base64
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import registration as reg, registration_flow as flow, registration_store, server  # noqa: E402
from fabric_backend.entra import EntraConfig, Validator, challenge, protected_resource_metadata  # noqa: E402

CFG = EntraConfig("https://mcp.example.com/mcp", "11111111-2222-3333-4444-555555555555", "s3cret")
TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
KEY = base64.b64encode(b"k" * 32).decode()
BASE = "https://mcp.example.com"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "registration-test", "version": "1"}}}
ACCEPT = {"Accept": "application/json, text/event-stream"}

VSCODE = "https://vscode.dev/oauth/client-metadata.json"
GLAMA = "https://glama.ai/mcp/client-metadata.json"
DOCS = {
    VSCODE: {"client_id": VSCODE, "client_name": "Visual Studio Code", "client_uri": "https://code.visualstudio.com",
             "redirect_uris": ["http://127.0.0.1:33418/", "https://vscode.dev/redirect", "https://insiders.vscode.dev/redirect"],
             "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], "token_endpoint_auth_method": "none"},
    GLAMA: {"client_id": GLAMA, "client_name": "Glama", "redirect_uris": ["https://glama.ai/api/app/mcp/oauth/callback",
                                                                          "https://evil.example/steal"],
            "token_endpoint_auth_method": "none"},
}


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
    claims = {"aud": CFG.public_url, "iss": f"https://login.microsoftonline.com/{TID}/v2.0", "tid": TID,
              "exp": int(time.time()) + 600, "iat": int(time.time()) - 5, "scp": "user_impersonation", "oid": "user-1"}
    claims.update(over)
    return jwt.encode(claims, priv, algorithm="RS256")


class FakeEntra:
    """Entra's authorize and token endpoints as far as this layer uses them: codes bound to the PKCE challenge and the
    redirect address, single use, the client secret checked, refresh tokens that rotate."""

    def __init__(self, priv):
        self.priv, self.codes, self.refresh, self.user = priv, {}, {}, "user-1"
        self.authorize_requests, self.token_requests = [], []
        self.over = {}

    def authorize(self, location: str) -> str:
        p = urlsplit(location)
        assert p.netloc == "login.microsoftonline.com" and p.path == "/organizations/oauth2/v2.0/authorize"
        q = {k: v[0] for k, v in parse_qs(p.query).items()}
        self.authorize_requests.append(q)
        assert q["client_id"] == CFG.client_id and q["redirect_uri"] == f"{BASE}/oauth/callback"
        assert q["code_challenge_method"] == "S256" and q["response_type"] == "code"
        assert q["scope"] == f"{CFG.scope} offline_access" and "resource" not in q and "prompt" not in q
        code = secrets.token_urlsafe(24)
        self.codes[code] = (q["code_challenge"], q["redirect_uri"], self.user)
        return f"/oauth/callback?" + urlencode({"code": code, "state": q["state"]})

    def post(self, data: dict) -> dict:
        self.token_requests.append(dict(data))
        assert data["client_id"] == CFG.client_id and data["client_secret"] == CFG.client_secret
        if data["grant_type"] == "authorization_code":
            got = self.codes.pop(data["code"], None)
            if not got:
                raise flow.EntraError("invalid_grant", "AADSTS54005: OAuth2 Authorization code was already redeemed")
            challenge_, redirect, user = got
            assert reg.s256(data["code_verifier"]) == challenge_ and data["redirect_uri"] == redirect
        elif data["grant_type"] == "refresh_token":
            user = self.refresh.pop(data["refresh_token"], None)
            if not user:
                raise flow.EntraError("invalid_grant", "AADSTS70008: refresh token expired")
        else:
            raise AssertionError(data["grant_type"])
        rt = "entra-rt-" + secrets.token_urlsafe(8)
        self.refresh[rt] = user
        return {"access_token": tok(self.priv, oid=user, **self.over), "refresh_token": rt, "expires_in": 3599}


def fake_fetch(docs, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if url not in docs:
            return 404, {}, b"not found"
        return 200, {"content-type": "application/json", "cache-control": "max-age=60"}, json.dumps(docs[url]).encode()
    return fetch


@pytest.fixture
def env(monkeypatch, keys):
    a = server.Auth()
    a.entra = CFG
    a._validator = Validator(CFG, FakeJWKS(keys[1]))
    monkeypatch.setattr(server, "auth", a)
    for k in ("KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI", "KRUSGRAPH_REGISTRATION_CLIENT_DOMAINS",
              "KRUSGRAPH_CLIENT_REGISTRATION", "KRUSGRAPH_CLIENT_REGISTRATION_DCR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("KRUSGRAPH_REGISTRATION_KEY", KEY)
    monkeypatch.setenv("KRUSGRAPH_REGISTRATION_STORE", "memory")
    entra = FakeEntra(keys[0])
    monkeypatch.setattr(flow.Layer, "_entra_post", lambda self, data: entra.post(data))
    calls = []
    monkeypatch.setattr(reg, "fetch_https", fake_fetch(DOCS, calls))
    store, original = registration_store.MemoryStore(), registration_store.from_env
    # one store for every app a test builds, as two replicas (or two browsers on one server) would share the table
    monkeypatch.setattr(registration_store, "from_env",
                        lambda: store if os.environ.get("KRUSGRAPH_REGISTRATION_STORE") == "memory" else original())
    return {"entra": entra, "fetches": calls, "monkeypatch": monkeypatch, "priv": keys[0], "store": store}


def client(on=True, dcr=True, env=None):
    mp = env["monkeypatch"]
    if on:
        mp.setenv("KRUSGRAPH_CLIENT_REGISTRATION", "1")
    if dcr:
        mp.setenv("KRUSGRAPH_CLIENT_REGISTRATION_DCR", "1")
    return TestClient(server.build_app(), base_url=BASE, follow_redirects=False)


def pkce():
    verifier = secrets.token_urlsafe(48)
    return verifier, reg.s256(verifier)


def authorize_params(client_id, redirect_uri, challenge_, state="client-state-1", **extra):
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "code_challenge": challenge_,
         "code_challenge_method": "S256", "state": state, "resource": f"{BASE}/mcp/connect", "scope": CFG.scope}
    q.update(extra)
    return {k: v for k, v in q.items() if v is not None}


def hidden(page: str, name: str) -> str:
    return re.search(rf'name="{name}" value="([^"]*)"', page).group(1)


def approve(c, page: str, decision="allow"):
    return c.post("/oauth/consent", data={"request": hidden(page, "request"), "csrf": hidden(page, "csrf"), "decision": decision})


def sign_in(c, entra, client_id, redirect_uri, expect_page=True, **extra):
    """The browser's part: authorize, the consent page (or a remembered approval), Entra, the callback. Returns
    (code, verifier, the final redirect's query)."""
    verifier, ch = pkce()
    r = c.get("/oauth/authorize", params=authorize_params(client_id, redirect_uri, ch, **extra))
    if expect_page:
        assert r.status_code == 200, r.text[:300]
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["x-frame-options"] == "DENY"
        r = approve(c, r.text)
        assert r.status_code == 303, r.text[:300]
    else:
        assert r.status_code == 302 and r.headers["location"].startswith("https://login.microsoftonline.com/"), r.text[:300]
    r = c.get(entra.authorize(r.headers["location"]))
    assert r.status_code == 302, r.text[:300]
    loc = r.headers["location"]
    assert loc.startswith(redirect_uri.split("?")[0].rstrip("/")) or reg.is_loopback(redirect_uri)
    q = {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}
    assert q["iss"] == f"{BASE}/oauth" and q.get("state") == extra.get("state", "client-state-1")
    return q["code"], verifier, q


def redeem(c, cid, redirect, code, verifier, **extra):
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect, "client_id": cid,
            "code_verifier": verifier, "resource": f"{BASE}/mcp/connect"}
    data.update(extra)
    return c.post("/oauth/token", data={k: v for k, v in data.items() if v is not None})


def mcp_call(c, token):
    return c.post("/mcp/connect", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {token}"})


# ------------------------------------------------------------------ off by default, Claude unchanged ---------------

def test_off_by_default_nothing_is_served(env):
    with client(on=False, dcr=False, env=env) as c:
        for path in ("/oauth/authorize", "/oauth/callback", "/.well-known/oauth-authorization-server/oauth",
                     "/oauth/.well-known/oauth-authorization-server", "/.well-known/oauth-protected-resource/mcp/connect",
                     "/.well-known/oauth-authorization-server"):
            assert c.get(path).status_code == 404, path
        assert c.post("/oauth/token", data={"grant_type": "authorization_code"}).status_code in (404, 405)
        assert c.post("/oauth/register", json={"redirect_uris": ["http://127.0.0.1/cb"]}).status_code in (404, 405)
        assert c.post("/mcp/connect", json=INIT, headers=ACCEPT).status_code == 404     # not an endpoint at all
    assert env["fetches"] == [] and env["entra"].token_requests == []


@pytest.mark.parametrize("on", [False, True])
def test_claude_s_sign_in_is_exactly_the_same_in_both_modes(env, on):
    with client(on=on, env=env) as c:
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            r = c.get(path)
            assert r.status_code == 200 and r.json() == protected_resource_metadata(CFG)
            assert r.json()["authorization_servers"] == ["https://login.microsoftonline.com/organizations/v2.0"]
        r = c.post("/mcp", json=INIT, headers=ACCEPT)
        assert r.status_code == 401 and r.headers["www-authenticate"] == challenge(CFG)
        r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": "Bearer x.y.z"})
        assert r.status_code == 401 and r.headers["www-authenticate"] == challenge(CFG, "invalid_token")
        r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {tok(env['priv'])}"})
        assert r.status_code == 200 and '"serverInfo"' in r.text
        assert c.get("/.well-known/oauth-authorization-server").status_code == 404       # Claude finds no AS of ours


def test_switched_on_without_a_key_or_store_stays_off_and_says_why(env, capsys):
    env["monkeypatch"].delenv("KRUSGRAPH_REGISTRATION_KEY")
    with client(env=env) as c:
        assert c.get("/.well-known/oauth-authorization-server/oauth").status_code == 404
        assert c.get("/.well-known/oauth-protected-resource").json() == protected_resource_metadata(CFG)
    assert "client registration is switched on but not configured" in capsys.readouterr().err
    env["monkeypatch"].setenv("KRUSGRAPH_REGISTRATION_KEY", base64.b64encode(b"short").decode())
    with client(env=env) as c:
        assert c.get("/.well-known/oauth-authorization-server/oauth").status_code == 404
    env["monkeypatch"].setenv("KRUSGRAPH_REGISTRATION_KEY", KEY)
    env["monkeypatch"].delenv("KRUSGRAPH_REGISTRATION_STORE")
    with client(env=env) as c:
        assert c.get("/.well-known/oauth-authorization-server/oauth").status_code == 404
    assert "KRUSGRAPH_REGISTRATION_STORE is required" in capsys.readouterr().err


# ------------------------------------------------------------------ metadata ---------------------------------------

def test_metadata_for_mcp_connect_and_the_authorization_server(env):
    with client(dcr=False, env=env) as c:
        prm = c.get("/.well-known/oauth-protected-resource/mcp/connect").json()
        assert prm["resource"] == f"{BASE}/mcp/connect" and prm["authorization_servers"] == [f"{BASE}/oauth"]
        assert prm["scopes_supported"] == [CFG.scope]                      # no offline_access on a resource (MCP 2026-07-28)
        for path in ("/.well-known/oauth-authorization-server/oauth", "/oauth/.well-known/oauth-authorization-server"):
            r = c.get(path)
            m = r.json()
            assert r.headers["access-control-allow-origin"] == "*"
            assert m["issuer"] == f"{BASE}/oauth" and m["authorization_endpoint"] == f"{BASE}/oauth/authorize"
            assert m["token_endpoint"] == f"{BASE}/oauth/token" and m["code_challenge_methods_supported"] == ["S256"]
            assert m["client_id_metadata_document_supported"] is True and m["token_endpoint_auth_methods_supported"] == ["none"]
            assert m["authorization_response_iss_parameter_supported"] is True and "registration_endpoint" not in m
        r = c.post("/mcp/connect", json=INIT, headers=ACCEPT)
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == (f'Bearer resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp/connect", '
                                                 f'scope="{CFG.scope}"')
        assert c.post("/oauth/register", json={"redirect_uris": ["http://127.0.0.1/cb"]}).status_code in (404, 405)
    with client(env=env) as c:
        assert c.get("/.well-known/oauth-authorization-server/oauth").json()["registration_endpoint"] == f"{BASE}/oauth/register"


# ------------------------------------------------------------------ the three clients, end to end ----------------

def test_vs_code_signs_in_with_its_metadata_document_on_a_random_loopback_port(env):
    entra = env["entra"]
    with client(env=env) as c:
        r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:53012/", pkce()[1]))
        page = r.text
        assert r.status_code == 200 and "Visual Studio Code" in page and "<strong>vscode.dev</strong>" in page
        assert "a program on this computer" in page and "port 53012" in page and "Continue only if" in page
        assert "http://127.0.0.1:53012" in r.headers["content-security-policy"]       # Deny may go back to the client
        code, verifier, _ = sign_in(c, entra, VSCODE, "http://127.0.0.1:53012/")
        r = redeem(c, VSCODE, "http://127.0.0.1:53012/", code, verifier)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store", r.text
        body = r.json()
        assert body["token_type"] == "Bearer" and body["scope"] == CFG.scope and "." in body["refresh_token"]
        assert 3590 <= body["expires_in"] <= 3599                                # what is left of Entra's lifetime
        assert not body["refresh_token"].startswith("entra-rt-")              # Entra's refresh token never leaves the server
        r = mcp_call(c, body["access_token"])
        assert r.status_code == 200 and '"serverInfo"' in r.text
        assert c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {body['access_token']}"}).status_code == 200

        # refresh rotates; the old refresh token then ends the whole line
        r1 = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": body["refresh_token"], "client_id": VSCODE})
        assert r1.status_code == 200 and r1.json()["refresh_token"] != body["refresh_token"]
        assert mcp_call(c, r1.json()["access_token"]).status_code == 200
        replay = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": body["refresh_token"], "client_id": VSCODE})
        assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
        after = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": r1.json()["refresh_token"], "client_id": VSCODE})
        assert after.status_code == 400 and after.json()["error"] == "invalid_grant"

        # a program on this computer is asked about every time (MCP: localhost redirect risks), on any port
        r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:61000/", pkce()[1]))
        assert r.status_code == 200 and "asks every time" in r.text
        code, verifier, _ = sign_in(c, entra, VSCODE, "http://127.0.0.1:61000/")
        assert redeem(c, VSCODE, "http://127.0.0.1:61000/", code, verifier).status_code == 200
        # vscode.dev's web callback: approved once, then remembered for this user, client and address
        sign_in(c, entra, VSCODE, "https://vscode.dev/redirect")
        code, verifier, _ = sign_in(c, entra, VSCODE, "https://vscode.dev/redirect", expect_page=False)
        assert redeem(c, VSCODE, "https://vscode.dev/redirect", code, verifier).status_code == 200
        sign_in(c, entra, VSCODE, "https://insiders.vscode.dev/redirect")       # another address: asked again
    assert env["fetches"].count(VSCODE) == 1                                   # cached per Cache-Control


def test_cursor_signs_in_with_dynamic_registration_and_its_localhost_callback(env):
    entra = env["entra"]
    with client(env=env) as c:
        bad = c.post("/oauth/register", json={"client_name": "Cursor", "redirect_uris": ["cursor://anysphere.cursor-mcp/oauth/callback"],
                                              "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"]})
        assert bad.status_code == 400 and bad.json()["error"] == "invalid_redirect_uri"   # private-use schemes are not allowed
        r = c.post("/oauth/register", json={"client_name": "Cursor", "redirect_uris": ["http://localhost:8787/callback"],
                                            "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
                                            "response_types": ["code"]})
        assert r.status_code == 201 and r.headers["cache-control"] == "no-store"
        reg_ = r.json()
        assert "client_secret" not in reg_ and reg_["token_endpoint_auth_method"] == "none" and reg_["client_name"] == "Cursor"
        cid = reg_["client_id"]
        page = c.get("/oauth/authorize", params=authorize_params(cid, "http://localhost:8787/callback", pkce()[1])).text
        assert "Its name is not verified" in page and "Cursor" in page
        code, verifier, _ = sign_in(c, entra, cid, "http://localhost:8787/callback")
        r = redeem(c, cid, "http://localhost:8787/callback", code, verifier)
        assert r.status_code == 200 and mcp_call(c, r.json()["access_token"]).status_code == 200
        # Cursor's cloud agents use an https callback, which registers too
        web = c.post("/oauth/register", json={"client_name": "Cursor", "redirect_uris": ["https://www.cursor.com/agents/mcp/oauth/callback"]})
        assert web.status_code == 201


def test_a_glama_like_client_signs_in_with_cimd_and_glama_with_registration(env):
    entra = env["entra"]
    with client(env=env) as c:
        cb = "https://glama.ai/api/app/mcp/oauth/callback"
        code, verifier, _ = sign_in(c, entra, GLAMA, cb)
        r = redeem(c, GLAMA, cb, code, verifier)
        assert r.status_code == 200 and mcp_call(c, r.json()["access_token"]).status_code == 200
        # the document also listed an address on another domain: it was dropped, never allowed
        r = c.get("/oauth/authorize", params=authorize_params(GLAMA, "https://evil.example/steal", pkce()[1]))
        assert r.status_code == 400 and "location" not in r.headers and "not registered" in r.text
        cid = c.post("/oauth/register", json={"client_name": "Glama", "redirect_uris": [cb, "https://glama.ai/mcp/inspector/oauth/callback"]}).json()["client_id"]
        code, verifier, _ = sign_in(c, entra, cid, "https://glama.ai/mcp/inspector/oauth/callback")
        assert redeem(c, cid, "https://glama.ai/mcp/inspector/oauth/callback", code, verifier).status_code == 200


# ------------------------------------------------------------------ what must fail ---------------------------------

def test_wrong_redirect_addresses_get_an_error_page_never_a_redirect(env):
    with client(env=env) as c:
        for uri in ("http://127.0.0.1:33418/other", "https://vscode.dev/redirect/x", "https://evil.example/cb",
                    "http://evil.example:33418/", "http://localhost:33418/", "", "https://vscode.dev/redirect#f"):
            r = c.get("/oauth/authorize", params=authorize_params(VSCODE, uri, pkce()[1]))
            assert r.status_code == 400 and "location" not in r.headers, uri
        r = c.get("/oauth/authorize", params=authorize_params("https://unknown.example/client.json", "https://unknown.example/cb", pkce()[1]))
        assert r.status_code == 400 and "location" not in r.headers and "HTTP 404" in r.text
        r = c.get("/oauth/authorize", params=authorize_params(CFG.client_id, "https://claude.ai/api/mcp/auth_callback", pkce()[1]))
        assert r.status_code == 400 and "location" not in r.headers                # the Entra app's own id is not a client here


@pytest.mark.parametrize("change", [{"code_challenge": None}, {"code_challenge_method": None}, {"code_challenge_method": "plain"},
                                    {"code_challenge": "short"}])
def test_pkce_s256_is_required(env, change):
    with client(env=env) as c:
        r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "https://vscode.dev/redirect", pkce()[1], **change))
        assert r.status_code == 400 and "location" not in r.headers and "PKCE" in r.text
    assert env["entra"].authorize_requests == []


def test_request_errors_before_the_approval_stay_on_this_server(env):
    """Anyone can publish a client with any redirect address, so before the user approved it nothing is sent there
    (the review's open-redirect finding): a client on attacker.example with a wrong response_type gets a page here."""
    DOCS["https://attacker.example/client.json"] = {"client_id": "https://attacker.example/client.json", "client_name": "x",
                                                    "redirect_uris": ["https://attacker.example/phish"]}
    try:
        with client(env=env) as c:
            for change in ({"response_type": "x"}, {"response_type": "token"}, {"resource": "https://other.example/mcp"},
                           {"scope": "https://graph.microsoft.com/.default"}, {"response_mode": "form_post"},
                           {"code_challenge": None}, {"prompt": "none"}):
                for cid, uri in (("https://attacker.example/client.json", "https://attacker.example/phish"), (VSCODE, "https://vscode.dev/redirect")):
                    r = c.get("/oauth/authorize", params=authorize_params(cid, uri, pkce()[1], **change))
                    assert r.status_code == 400 and "location" not in r.headers, (change, cid)
    finally:
        del DOCS["https://attacker.example/client.json"]
        q = authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])
        r = c.get("/oauth/authorize?" + urlencode(q) + "&client_id=" + GLAMA)
        assert r.status_code == 400 and "location" not in r.headers                   # a repeated parameter


def test_a_code_works_once_and_a_second_try_revokes_what_the_first_got(env):
    entra = env["entra"]
    with client(env=env) as c:
        code, verifier, _ = sign_in(c, entra, VSCODE, "http://127.0.0.1:33418/")
        first = redeem(c, VSCODE, "http://127.0.0.1:33418/", code, verifier)
        assert first.status_code == 200
        again = redeem(c, VSCODE, "http://127.0.0.1:33418/", code, verifier)
        assert again.status_code == 400 and again.json()["error"] == "invalid_grant"
        r = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": first.json()["refresh_token"], "client_id": VSCODE})
        assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


@pytest.mark.parametrize("change", [{"code_verifier": "x" * 43}, {"code_verifier": None}, {"redirect_uri": "http://127.0.0.1:1/"},
                                    {"client_id": GLAMA}, {"resource": "https://other.example/mcp"}, {"client_secret": "guess"}])
def test_a_code_needs_its_own_verifier_redirect_and_client(env, change):
    entra = env["entra"]
    with client(env=env) as c:
        code, verifier, _ = sign_in(c, entra, VSCODE, "http://127.0.0.1:33418/")
        r = redeem(c, VSCODE, "http://127.0.0.1:33418/", code, verifier, **change)
        assert r.status_code in (400, 401) and r.json()["error"] in ("invalid_grant", "invalid_target", "invalid_client", "invalid_request")
        if "resource" not in change and "client_secret" not in change:            # the failed attempt used the code up
            assert redeem(c, VSCODE, "http://127.0.0.1:33418/", code, verifier).status_code == 400


def test_a_token_for_another_audience_is_refused_at_mcp_connect(env):
    priv = env["priv"]
    with client(env=env) as c:
        for bad in (tok(priv, aud="https://graph.microsoft.com"), tok(priv, scp="read"), tok(priv, exp=int(time.time()) - 5),
                    tok(rsa.generate_private_key(public_exponent=65537, key_size=2048))):
            r = mcp_call(c, bad)
            assert r.status_code == 401 and 'error="invalid_token"' in r.headers["www-authenticate"]
            assert "/.well-known/oauth-protected-resource/mcp/connect" in r.headers["www-authenticate"]


def test_entra_tokens_for_another_audience_never_reach_the_client(env):
    entra = env["entra"]
    entra.over = {"aud": "https://graph.microsoft.com"}
    with client(env=env) as c:
        verifier, ch = pkce()
        r = approve(c, c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", ch)).text)
        r = c.get(entra.authorize(r.headers["location"]))
        q = parse_qs(urlsplit(r.headers["location"]).query)
        assert q["error"] == ["access_denied"] and "code" not in q


def test_one_client_cannot_use_another_client_s_approval(env):
    entra = env["entra"]
    with client(env=env) as c:
        sign_in(c, entra, VSCODE, "https://vscode.dev/redirect")               # VS Code approved, remembered
        # a client that names itself like VS Code, on another domain, gets the page, with its own domain on it
        DOCS["https://vscode-mcp.example/client.json"] = {**DOCS[VSCODE], "client_id": "https://vscode-mcp.example/client.json",
                                                          "redirect_uris": ["http://127.0.0.1:33418/"]}
        try:
            r = c.get("/oauth/authorize", params=authorize_params("https://vscode-mcp.example/client.json", "http://127.0.0.1:33418/", pkce()[1]))
            assert r.status_code == 200 and "<strong>vscode-mcp.example</strong>" in r.text
            # VS Code's own consent form cannot be replayed for the other client: the client id is inside the signature
            page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1], prompt="consent")).text
            signed = hidden(page, "request")
            body, mac = signed.split(".")
            data = json.loads(reg.unb64u(body))
            data["client_id"] = "https://vscode-mcp.example/client.json"
            forged = reg.b64u(json.dumps(data).encode()) + "." + mac
            r = c.post("/oauth/consent", data={"request": forged, "csrf": hidden(page, "csrf"), "decision": "allow"})
            assert r.status_code == 403 and "location" not in r.headers
        finally:
            del DOCS["https://vscode-mcp.example/client.json"]
        # and a code issued to VS Code cannot be redeemed by Glama
        code, verifier, _ = sign_in(c, entra, VSCODE, "https://vscode.dev/redirect", expect_page=False)
        assert redeem(c, GLAMA, "https://vscode.dev/redirect", code, verifier).json()["error"] == "invalid_grant"


def test_the_consent_form_needs_its_csrf_cookie_and_works_once(env):
    with client(env=env) as c:
        page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).text
        c.cookies.delete(flow.CSRF_COOKIE + reg.sha256_hex(hidden(page, "csrf"))[:16])
        r = approve(c, page)
        assert r.status_code == 403 and "location" not in r.headers
    with client(env=env) as c:
        page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).text
        r = c.post("/oauth/consent", data={"request": hidden(page, "request"), "csrf": hidden(page, "csrf"), "decision": "allow"},
                   headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
        other = c.get("/oauth/authorize", params=authorize_params(GLAMA, "https://glama.ai/api/app/mcp/oauth/callback", pkce()[1])).text
        name = flow.CSRF_COOKIE + reg.sha256_hex(hidden(page, "csrf"))[:16]
        assert approve(c, page).status_code == 303                                 # a second page open meanwhile spoils nothing
        assert name not in c.cookies                                               # spent with the approval
        assert approve(c, other).status_code == 303
        c.cookies.set(name, hidden(page, "csrf"), domain="mcp.example.com")
        assert approve(c, page).status_code == 409                                 # the same approval, cookie and all, twice


def test_the_approval_form_works_with_the_origin_a_browser_actually_sends(env):
    """Live test of 27 October 2026: Glama's approval page showed, and Allow was refused with "The approval did not come
    from this server's own page": the page said Referrer-Policy: no-referrer, so the browser sent Origin: null on the
    form's POST. The page now says same-origin; Origin: null still counts only with Sec-Fetch-Site: same-origin."""
    glama_cb = "https://glama.ai/api/app/mcp/oauth/callback"
    with client(env=env) as c:
        page = c.get("/oauth/authorize", params=authorize_params(GLAMA, glama_cb, pkce()[1]))
        assert page.headers["referrer-policy"] == "same-origin"

        def post(headers):
            fresh = c.get("/oauth/authorize", params=authorize_params(GLAMA, glama_cb, pkce()[1])).text
            return c.post("/oauth/consent", data={"request": hidden(fresh, "request"), "csrf": hidden(fresh, "csrf"),
                                                  "decision": "allow"}, headers=headers)
        for refused in ({"Origin": "null", "Sec-Fetch-Site": "cross-site"}, {"Origin": "null", "Sec-Fetch-Site": "same-site"},
                        {"Origin": "null"}, {"Origin": "https://evil.example", "Sec-Fetch-Site": "same-origin"},
                        {"Origin": BASE, "Sec-Fetch-Site": "cross-site"}):
            r = post(refused)
            assert r.status_code == 403 and "location" not in r.headers, refused
        for accepted in ({"Origin": "null", "Sec-Fetch-Site": "same-origin"}, {"Origin": BASE, "Sec-Fetch-Site": "same-origin"}):
            r = post(accepted)
            assert r.status_code == 303 and r.headers["location"].startswith("https://login.microsoftonline.com/"), accepted
            assert r.headers["referrer-policy"] == "no-referrer"                  # the way to Entra still carries no referrer


def test_deny_goes_back_to_the_client_with_access_denied(env):
    with client(env=env) as c:
        page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "https://vscode.dev/redirect", pkce()[1])).text
        r = approve(c, page, "deny")
        assert r.status_code == 303 and r.headers["location"].startswith("https://vscode.dev/redirect?")
        q = parse_qs(urlsplit(r.headers["location"]).query)
        assert q["error"] == ["access_denied"] and q["state"] == ["client-state-1"] and q["iss"] == [f"{BASE}/oauth"]
    assert env["entra"].authorize_requests == []


def test_entra_s_answer_must_come_back_to_the_browser_that_approved_and_only_once(env):
    entra = env["entra"]
    with client(env=env) as c:
        page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).text
        callback = entra.authorize(approve(c, page).headers["location"])
        with client(env=env) as other:                                           # another browser, no flow cookie
            r = other.get(callback)
            assert r.status_code == 403 and "location" not in r.headers
        r = c.get(callback)                                                       # the state was used up by that attempt
        assert r.status_code == 400 and "location" not in r.headers
        r = c.get("/oauth/callback?state=nothing&code=x")
        assert r.status_code == 400


def test_a_remembered_approval_is_checked_against_the_account_that_actually_signed_in(env):
    entra = env["entra"]
    with client(env=env) as c:
        sign_in(c, entra, VSCODE, "https://vscode.dev/redirect")               # user-1 approves VS Code
        entra.user = "user-2"                                                    # user-2 signs in on the same browser
        verifier, ch = pkce()
        r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "https://vscode.dev/redirect", ch))
        assert r.status_code == 302                                              # skipped on the strength of user-1's cookie
        r = c.get(entra.authorize(r.headers["location"]))
        assert r.status_code == 302 and r.headers["location"].startswith("/oauth/authorize?")   # no code for user-2 yet
        r = c.get(r.headers["location"])
        assert r.status_code == 200 and "different account" in r.text
        r = c.get(entra.authorize(approve(c, r.text).headers["location"]))
        code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
        assert redeem(c, VSCODE, "https://vscode.dev/redirect", code, verifier).status_code == 200


def test_a_renamed_client_and_prompt_consent_are_asked_again(env):
    entra = env["entra"]
    with client(env=env) as c:
        sign_in(c, entra, VSCODE, "https://vscode.dev/redirect")
        sign_in(c, entra, VSCODE, "https://vscode.dev/redirect", prompt="consent")
    DOCS[VSCODE]["client_name"] = "Visual Studio Code (new)"
    try:
        with client(env=env) as c:
            c.cookies.set(flow.USER_COOKIE, reg.Keys(lambda: KEY).sign("user", {"u": reg.Keys(lambda: KEY).user_key(TID, "user-1")}, 600),
                          domain="mcp.example.com")
            r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "https://vscode.dev/redirect", pkce()[1]))
            assert r.status_code == 200 and "Visual Studio Code (new)" in r.text
    finally:
        DOCS[VSCODE]["client_name"] = "Visual Studio Code"


def test_entra_errors_and_refused_tenants_reach_the_client_as_errors(env, monkeypatch):
    entra = env["entra"]
    with client(env=env) as c:
        page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).text
        loc = approve(c, page).headers["location"]
        state = parse_qs(urlsplit(loc).query)["state"][0]
        r = c.get("/oauth/callback?" + urlencode({"state": state, "error": "consent_required", "error_description": "AADSTS65001: admin consent"}))
        q = parse_qs(urlsplit(r.headers["location"]).query)
        assert q["error"] == ["access_denied"] and "AADSTS65001" in q["error_description"][0]
    monkeypatch.setattr(server.auth._validator.cfg, "allowed_tenants", {"only-another-tenant"})
    try:
        with client(env=env) as c:
            page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).text
            r = c.get(entra.authorize(approve(c, page).headers["location"]))
            q = parse_qs(urlsplit(r.headers["location"]).query)
            assert q["error"] == ["access_denied"] and "tenant not allowed" in q["error_description"][0]
    finally:
        monkeypatch.setattr(server.auth._validator.cfg, "allowed_tenants", set())


def test_refresh_needs_the_client_that_got_it(env):
    entra = env["entra"]
    with client(env=env) as c:
        code, verifier, _ = sign_in(c, entra, VSCODE, "http://127.0.0.1:33418/")
        rt = redeem(c, VSCODE, "http://127.0.0.1:33418/", code, verifier).json()["refresh_token"]
        r = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": GLAMA})
        assert r.json()["error"] == "invalid_grant"
        r = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": VSCODE})
        assert r.json()["error"] == "invalid_grant"                               # the line was ended by the wrong client
        for data in ({"grant_type": "password", "client_id": VSCODE}, {"grant_type": "refresh_token", "refresh_token": "x", "client_id": VSCODE}):
            assert c.post("/oauth/token", data=data).status_code == 400
        assert c.post("/oauth/token", json={"grant_type": "refresh_token"}).json()["error"] == "invalid_request"
        r = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": VSCODE},
                   headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r.status_code == 401 and r.json()["error"] == "invalid_client" and r.headers["www-authenticate"].startswith("Basic")
        for bad in ("\uff41.b", "\u00e9t\u00e9\u00e9t\u00e9\u00e9t\u00e9.b"):                       # non-ASCII letters: refused, not a 500
            assert c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": bad, "client_id": VSCODE}).status_code == 400
        assert c.get("/oauth/callback?state=%C3%A9t%C3%A9&code=x").status_code == 400


def test_an_entra_outage_during_refresh_keeps_the_line(env):
    entra = env["entra"]
    with client(env=env) as c:
        code, verifier, _ = sign_in(c, entra, VSCODE, "http://127.0.0.1:33418/")
        rt = redeem(c, VSCODE, "http://127.0.0.1:33418/", code, verifier).json()["refresh_token"]
        post = entra.post

        def outage(data):
            raise flow.EntraError("http_503")
        entra.post = outage
        r = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": VSCODE})
        assert r.status_code == 503 and r.json()["error"] == "temporarily_unavailable"
        entra.post = post
        r = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": VSCODE})
        assert r.status_code == 200                                               # the same refresh token, once Entra is back


def test_rate_limits_per_network_and_per_client(env):
    env["monkeypatch"].setenv("KRUSGRAPH_REGISTRATION_RATE_IP", "3/minute")
    with client(env=env) as c:
        for _ in range(3):
            assert c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).status_code == 200
        r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1]))
        assert r.status_code == 429
        other = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1]),
                      headers={"X-Forwarded-For": "203.0.113.9, 198.51.100.7"})
        assert other.status_code == 200                                            # the ingress's entry decides, not the client's
        spoof = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1]),
                      headers={"X-Forwarded-For": "203.0.113.10, 198.51.100.7"})
        assert spoof.status_code == 200
    env["monkeypatch"].setenv("KRUSGRAPH_REGISTRATION_RATE_IP", "1000/minute")
    env["monkeypatch"].setenv("KRUSGRAPH_REGISTRATION_RATE_CLIENT", "2/minute")
    with client(env=env) as c:
        codes = [c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert c.get("/oauth/authorize", params=authorize_params(GLAMA, "https://glama.ai/api/app/mcp/oauth/callback", pkce()[1])).status_code == 200
        # VS Code's bucket is per network: garbage from other networks naming VS Code's id locks out nobody else
        for n in range(5):
            c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": "x" * 20 + ".y", "client_id": VSCODE},
                   headers={"X-Forwarded-For": f"198.51.100.{n}"})
        r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1]),
                  headers={"X-Forwarded-For": "203.0.113.50"})
        assert r.status_code == 200
        # an IPv6 network counts as its /64
        for n in range(2):
            c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1]),
                  headers={"X-Forwarded-For": f"2001:db8:1:2::{n + 1}"})
        r = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1]),
                  headers={"X-Forwarded-For": "2001:db8:1:2:ffff::9"})
        assert r.status_code == 429
    env["monkeypatch"].setenv("KRUSGRAPH_REGISTRATION_RATE_REGISTER", "2/hour")
    with client(env=env) as c:
        codes = [c.post("/oauth/register", json={"redirect_uris": ["http://127.0.0.1/cb"]}).status_code for _ in range(3)]
        assert codes == [201, 201, 429]


# ------------------------------------------------------------------ the rules, one by one -----------------------

@pytest.mark.parametrize("uri", ["https://vscode.dev/redirect", "https://a.example.com/cb?x=1", "http://127.0.0.1/cb",
                                 "http://localhost:8787/callback", "http://127.0.0.1:33418/"])
def test_redirect_addresses_that_are_allowed(uri):
    assert reg.redirect_problem(uri) is None


@pytest.mark.parametrize("uri", ["https://*.example.com/cb", "https://example.com/*", "http://example.com/cb", "cursor://anysphere.cursor-mcp/oauth/callback",
                                 "https://example.com/cb#x", "https://user:pw@example.com/cb", "https://10.0.0.1/cb", "https://localhost/cb",
                                 "http://127.0.0.2/cb", "http://[::1]/cb", "http://localhost.evil.example/cb", "javascript:alert(1)",
                                 "https://example/cb", "http://127.0.0.1:99999/cb", "", None, "https://exa mple.com/cb", "https://example.com./cb",
                                 "https://evil.example;sandbox,frame-ancestors/cb", "https://ex%61mple.com/cb", "https://exa_mple.com/cb",
                                 "https://1.2.3/cb", "https://evil.example'/cb", "https://[2001:db8::1]/cb"])
def test_redirect_addresses_that_are_refused(uri):
    assert reg.redirect_problem(uri) is not None


def test_loopback_addresses_match_on_any_port_and_nothing_else_loosely():
    assert reg.redirect_matches("http://127.0.0.1:5000/cb", "http://127.0.0.1/cb")
    assert reg.redirect_matches("http://127.0.0.1:5000", "http://127.0.0.1:33418/")
    assert not reg.redirect_matches("http://localhost:5000/cb", "http://127.0.0.1/cb")
    assert not reg.redirect_matches("http://127.0.0.1:5000/cb2", "http://127.0.0.1/cb")
    assert not reg.redirect_matches("https://vscode.dev/redirect/", "https://vscode.dev/redirect")
    assert not reg.redirect_matches("https://VSCODE.dev/redirect", "https://vscode.dev/redirect")


@pytest.mark.parametrize("url", ["http://vscode.dev/x.json", "https://10.0.0.1/x.json", "https://localhost/x.json",
                                 "https://vscode.dev:8443/x.json", "https://vscode.dev/", "https://vscode.dev",
                                 "https://vscode.dev/a/../x.json", "https://vscode.dev/a/%2e%2e/x.json", "https://vscode.dev/x.json?a=1",
                                 "https://vscode.dev/x.json#f", "https://u@vscode.dev/x.json", "https://intranet/x.json",
                                 "https://evil.example;x/c.json", "https://vscode%2edev/x.json", "https://vscode.dev:443/x.json"])
def test_client_id_urls_that_are_refused(url):
    assert reg.client_id_problem(url) is not None


@pytest.mark.parametrize("address", ["10.0.0.5", "169.254.169.254", "127.0.0.1", "::1", "::ffff:127.0.0.1", "fd00::1",
                                     "192.168.1.1", "100.64.0.1", "0.0.0.0", "224.0.0.1"])
def test_metadata_is_never_fetched_from_special_addresses(address):
    def resolve(host, port, type=None):
        return [(None, None, None, None, (address, port))]
    with pytest.raises(reg.ClientError, match="does not fetch from"):
        reg.fetch_https("https://client.example/meta.json", resolve=resolve)


def test_a_name_that_resolves_to_one_public_and_one_private_address_is_refused():
    def resolve(host, port, type=None):
        return [(None, None, None, None, ("93.184.215.14", port)), (None, None, None, None, ("10.1.2.3", port))]
    with pytest.raises(reg.ClientError):
        reg.fetch_https("https://client.example/meta.json", resolve=resolve)


@pytest.mark.parametrize("status,headers,body,match", [
    (301, {"location": "https://elsewhere.example/x"}, b"", "HTTP 301"),
    (200, {}, b"{" + b" " * 6000 + b"}", "larger than 5 KB"),
    (200, {}, b"not json", "not valid JSON"),
    (200, {}, json.dumps({**DOCS[VSCODE], "client_id": "https://vscode.dev/other.json"}).encode(), "different client id"),
    (200, {}, json.dumps({**DOCS[VSCODE], "client_secret": "x"}).encode(), "secret"),
    (200, {}, json.dumps({**DOCS[VSCODE], "token_endpoint_auth_method": "private_key_jwt"}).encode(), "public clients only"),
    (200, {}, json.dumps({**DOCS[VSCODE], "token_endpoint_auth_method": "client_secret_basic"}).encode(), "public clients only"),
    (200, {}, json.dumps({**DOCS[VSCODE], "client_name": "\u202e\u200b "}).encode(), "no client_name"),
    (200, {}, json.dumps({**DOCS[VSCODE], "redirect_uris": ["cursor://x/cb", "https://evil.example/cb"]}).encode(), "none of the client"),
    (200, {}, json.dumps({**DOCS[VSCODE], "grant_types": ["client_credentials"]}).encode(), "authorization code"),
])
def test_metadata_documents_that_are_refused(status, headers, body, match):
    r = reg.CimdResolver(fetch=lambda url: (status, headers, body))
    with pytest.raises(reg.ClientError, match=match):
        r.resolve(VSCODE)


def test_metadata_is_cached_per_cache_control_and_errors_are_not():
    calls, answers = [], [(500, {}, b""), (200, {"cache-control": "no-store"}, json.dumps(DOCS[VSCODE]).encode()),
                          (200, {"cache-control": "max-age=100"}, json.dumps(DOCS[VSCODE]).encode())]
    now = [1000.0]

    def fetch(url):
        calls.append(url)
        return answers[min(len(calls) - 1, 2)]
    r = reg.CimdResolver(fetch=fetch, clock=lambda: now[0])
    with pytest.raises(reg.ClientError):
        r.resolve(VSCODE)
    assert r.resolve(VSCODE).name == "Visual Studio Code"                         # no-store: not kept
    r.resolve(VSCODE)
    r.resolve(VSCODE)
    assert len(calls) == 3
    now[0] += 101
    r.resolve(VSCODE)
    assert len(calls) == 4
    with pytest.raises(reg.ClientError, match="not accepted on this server"):
        reg.CimdResolver(fetch=fetch, allow_domains={"glama.ai"}).resolve(VSCODE)


def test_display_names_lose_control_and_direction_characters():
    assert reg.clean_name("Visual\u202e Studio\x00 Code\u200b") == "Visual Studio Code"
    assert len(reg.clean_name("x" * 500)) == reg.MAX_NAME
    assert reg.clean_name("a" + "\u0301" * 30 + "b") == "\u00e1\u0301\u0301b"            # a stack of marks cannot cover the page
    assert reg.clean_name("\u0301\u0301x") == "x"
    assert reg.clean_name(None) == "" and reg.clean_name(["a"]) == ""


@pytest.mark.parametrize("body,error", [
    (None, "invalid_client_metadata"), ([], "invalid_client_metadata"), ({}, "invalid_redirect_uri"),
    ({"redirect_uris": ["http://127.0.0.1/cb"] * 6}, "invalid_redirect_uri"),
    ({"redirect_uris": ["http://127.0.0.1/cb"], "token_endpoint_auth_method": "client_secret_post"}, "invalid_client_metadata"),
    ({"redirect_uris": ["http://127.0.0.1/cb"], "client_secret": "mine"}, "invalid_client_metadata"),
    ({"redirect_uris": ["http://127.0.0.1/cb"], "grant_types": ["client_credentials"]}, "invalid_client_metadata"),
    ({"redirect_uris": ["http://127.0.0.1/cb"], "grant_types": ["authorization_code", "implicit"]}, "invalid_client_metadata"),
    ({"redirect_uris": ["http://127.0.0.1/cb"], "response_types": ["token"]}, "invalid_client_metadata"),
    ({"redirect_uris": ["http://127.0.0.1/cb"], "application_type": "service"}, "invalid_client_metadata"),
    ({"redirect_uris": ["https://*.example.com/cb"]}, "invalid_redirect_uri"),
    ({"redirect_uris": ["https://example.com/" + "a" * 600]}, "invalid_redirect_uri"),
])
def test_dynamic_registration_is_strict(body, error):
    status, out = reg.register(body, reg.Keys(lambda: KEY))
    assert status == 400 and out["error"] == error


def test_registered_client_ids_are_signed_and_carry_their_addresses():
    k = reg.Keys(lambda: KEY)
    status, out = reg.register({"client_name": "Cursor", "redirect_uris": ["http://localhost:8787/callback"]}, k)
    assert status == 201 and out["application_type"] == "native"
    c = reg.dcr_client(out["client_id"], k)
    assert c.kind == "dcr" and c.domain == "" and c.allows("http://localhost:9999/callback") and not c.allows("https://x.example/cb")
    body, mac = out["client_id"][len(reg.DCR_PREFIX):].split(".")
    forged = json.loads(reg.unb64u(body))
    forged["r"] = ["https://evil.example/cb"]
    with pytest.raises(reg.ClientError):
        reg.dcr_client(reg.DCR_PREFIX + reg.b64u(json.dumps(forged).encode()) + "." + mac, k)
    with pytest.raises(reg.ClientError):
        reg.dcr_client(out["client_id"], reg.Keys(lambda: base64.b64encode(b"z" * 32).decode()))   # a new key


def test_keys_seal_bind_the_purpose_and_signatures_expire():
    k = reg.Keys(lambda: KEY)
    sealed = k.seal("code", {"a": 1})
    assert k.open("code", sealed) == {"a": 1} and k.open("family:x", sealed) is None and k.open("code", sealed[:-2] + "AA") is None
    assert b'"a"' not in reg.unb64u(sealed)
    s = k.sign("user", {"u": "x"}, 60)
    assert k.verify("user", s) == {"u": "x", "exp": json.loads(reg.unb64u(s.split(".")[0]))["exp"]}
    assert k.verify("consent", s) is None
    expired = k.sign("user", {"u": "x", "exp": int(time.time()) - 1}, None)
    assert k.verify("user", expired) is None
    assert k.user_key(TID, "user-1") == k.user_key(TID.upper(), "USER-1") != k.user_key(TID, "user-2")
    assert "user-1" not in k.user_key(TID, "user-1") and TID not in k.user_key(TID, "user-1")


# ------------------------------------------------------------------ the store -------------------------------------

def test_memory_store_takes_once_and_expires():
    now = [100.0]
    s = registration_store.MemoryStore(clock=lambda: now[0])
    s.put("code", "abc", {"x": 1}, ttl=60)
    assert s.take("code", "abc") == {"x": 1} and s.take("code", "abc") is None
    s.put("txn", "t", {"x": 1}, ttl=10)
    now[0] += 11
    assert s.get("txn", "t") is None and s.take("txn", "t") is None
    assert s.add("used", "u", {}, ttl=5) and not s.add("used", "u", {}, ttl=5)
    s.put("family", "f", {"n": 1})
    data, etag = s.get("family", "f")
    assert s.replace("family", "f", {"n": 2}, etag) and not s.replace("family", "f", {"n": 3}, etag)
    with pytest.raises(ValueError):
        s.put("code", "a/b", {})
    with pytest.raises(ValueError):
        s.put("other", "a", {})


class FakeTable:
    """Azure Table Storage's entity endpoints as the store uses them, with ETags and If-Match, and the service's rules
    that the live test of 27 October 2026 ran into: an authorized request carries x-ms-date, an Edm.Int64 value is a
    JSON string ("Payload format for Table service operations"), and an Int64 literal in a filter ends in L."""

    def __init__(self):
        self.rows, self.n, self.calls, self.answers = {}, 0, [], []

    def __call__(self, method, url, headers=None, data=None, params=None):
        self.calls.append((method, url, dict(headers or {})))
        answer = self._answer(method, url, headers, data, params)
        self.answers.append((method, url, params, answer.status_code))
        return answer

    def _answer(self, method, url, headers, data, params):
        assert headers["Authorization"] == "Bearer t" and headers["x-ms-version"] == "2019-02-02"
        m = re.search(r"\(PartitionKey='(\w+)',RowKey='([^']+)'\)$", url)
        key = (m.group(1), m.group(2)) if m else None

        def resp(status, body=None, etag=None):
            return type("R", (), {"status_code": status, "json": lambda self: body or {},
                                  "headers": {"ETag": etag} if etag else {}})()

        def invalid(text):
            return resp(400, {"odata.error": {"code": "InvalidInput", "message": {"lang": "en-US", "value": text}}})
        if not headers.get("x-ms-date"):
            return resp(403, {"odata.error": {"code": "AuthenticationFailed", "message": {"value": "x-ms-date is missing"}}})
        if data is not None:
            entity = json.loads(data)
            for name, value in entity.items():
                if entity.get(name + "@odata.type") == "Edm.Int64" and not (isinstance(value, str) and value.isdigit()):
                    return invalid(f"The value for property {name} is not a valid Edm.Int64")
        if params and "$filter" in params and re.search(r"\bexp (gt|lt) \d+(?!L)\b", params["$filter"]):
            return invalid("Int64 literals need the L suffix")
        if method == "POST":
            e = json.loads(data)
            k = (e["PartitionKey"], e["RowKey"])
            if k in self.rows:
                return resp(409)
            self.n += 1
            self.rows[k] = (e, f'W/"{self.n}"')
            return resp(204)
        if method == "GET" and key:
            if key not in self.rows:
                return resp(404)
            return resp(200, self.rows[key][0], self.rows[key][1])
        if method == "GET":
            return resp(200, {"value": []})
        if method == "PUT":
            match = headers.get("If-Match")
            if match and (key not in self.rows or (match != "*" and self.rows[key][1] != match)):
                return resp(412 if key in self.rows else 404)
            self.n += 1
            self.rows[key] = (json.loads(data), f'W/"{self.n}"')
            return resp(204)
        if method == "DELETE":
            if key not in self.rows:
                return resp(404)
            if headers.get("If-Match") not in ("*", self.rows[key][1]):
                return resp(412)
            del self.rows[key]
            return resp(204)
        raise AssertionError(method)


def test_table_store_takes_once_with_if_match_and_needs_a_table_url():
    t = FakeTable()
    s = registration_store.TableStore("https://acct.table.core.windows.net/krusgraphoauth", http=t, token=lambda: "t")
    s.put("code", "abc", {"x": 1}, ttl=60)
    assert s.take("code", "abc") == {"x": 1} and s.take("code", "abc") is None
    delete = [h for m, u, h in t.calls if m == "DELETE"][0]
    assert delete["If-Match"].startswith('W/"')                               # the delete names the version it read
    assert s.add("used", "u", {}, ttl=60) and not s.add("used", "u", {}, ttl=60)
    s.put("family", "f", {"n": 1})
    data, etag = s.get("family", "f")
    assert s.replace("family", "f", {"n": 2}, etag) and not s.replace("family", "f", {"n": 3}, etag)
    s.put("txn", "old", {"x": 1}, ttl=1)
    t.rows[("txn", "old")][0]["exp"] = int(time.time()) - 5
    assert s.get("txn", "old") is None and s.take("txn", "old") is None
    for bad in ("memory", "https://acct.blob.core.windows.net/t", "http://acct.table.core.windows.net/t",
                "https://acct.table.core.windows.net/a/b", "https://acct.table.core.windows.net/"):
        with pytest.raises(ValueError):
            registration_store.TableStore(bad)


def test_table_store_writes_what_the_table_service_accepts():
    """Live test of 27 October 2026: every sign-in stopped with "The sign-in service is briefly unavailable", because
    the store wrote the expiry as a JSON number typed Edm.Int64 and sent no x-ms-date. Both as the service wants them
    now; the purge filters with Int64 literals; and an error names the service's own code."""
    t = FakeTable()
    s = registration_store.TableStore("https://acct.table.core.windows.net/krusgraphoauth", http=t, token=lambda: "t")
    s.put("txn", "abc", {"x": 1}, ttl=600)
    assert s.add("used", "u1", {}, ttl=600) and s.get("txn", "abc")[0] == {"x": 1}
    stored = t.rows[("txn", "abc")][0]
    assert isinstance(stored["exp"], str) and stored["exp"].isdigit() and stored["exp@odata.type"] == "Edm.Int64"
    assert all(h.get("x-ms-date") for _, _, h in t.calls)
    s._purge(time.time())                                                          # the filter the service accepts
    listing = [(params["$filter"], status) for m, u, params, status in t.answers if m == "GET" and u.endswith("()")]
    assert len(listing) == len(registration_store.KINDS) and all(status == 200 and " exp lt " in f and f.endswith("L")
                                                                   for f, status in listing)
    body = s._body("txn", "x", {}, 60).decode()
    assert '"exp": "' in body
    old = json.dumps({"PartitionKey": "txn", "RowKey": "y", "data": "{}", "exp": 123, "exp@odata.type": "Edm.Int64"}).encode()
    r = t("PUT", s._url("txn", "y"), s._headers(), old)
    assert r.status_code == 400                                                    # what the previous version sent
    with pytest.raises(registration_store.StoreError, match=r"HTTP 400 to a write \(InvalidInput: "):
        raise s._fail("a write", r)


def test_a_store_outage_fails_the_sign_in_and_grants_nothing(env, monkeypatch):
    with client(env=env) as c:
        page = c.get("/oauth/authorize", params=authorize_params(VSCODE, "http://127.0.0.1:33418/", pkce()[1])).text

        def broken(*a, **k):
            raise registration_store.StoreError("down")
        monkeypatch.setattr(registration_store.MemoryStore, "put", broken)
        monkeypatch.setattr(registration_store.MemoryStore, "take", broken)
        monkeypatch.setattr(registration_store.MemoryStore, "add", broken)
        r = approve(c, page)
        assert r.status_code == 503 and "location" not in r.headers
        r = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": "x", "client_id": VSCODE,
                                         "redirect_uri": "http://127.0.0.1:33418/", "code_verifier": "y" * 43})
        assert r.status_code == 503 and r.json()["error"] == "temporarily_unavailable"


def test_nothing_personal_is_stored(env):
    entra = env["entra"]
    with client(env=env) as c:
        code, verifier, _ = sign_in(c, entra, VSCODE, "http://127.0.0.1:33418/")
        redeem(c, VSCODE, "http://127.0.0.1:33418/", code, verifier)
        assert {kind for kind, _ in env["store"]._rows} == {"used", "family"}     # no approval kept for a loopback address
        code, verifier, _ = sign_in(c, entra, VSCODE, "https://vscode.dev/redirect")
        redeem(c, VSCODE, "https://vscode.dev/redirect", code, verifier)
    rows = env["store"]._rows
    assert {kind for kind, _ in rows} == {"consent", "used", "family"}
    dump = json.dumps(list(rows.values()), default=str)
    for secret in ("user-1", TID, "entra-rt-", "eyJ", "127.0.0.1:33418"):
        assert secret not in dump, secret


def test_the_privacy_page_says_what_is_stored_only_when_it_is_on(env):
    with client(on=False, dcr=False, env=env) as c:
        off = c.get("/privacy").text
    assert "no database, no cache on disk and no file storage of its own" in off and "/mcp/connect" not in off
    with client(env=env) as c:
        on = c.get("/privacy").text
    assert "Sign-in from MCP clients other than Claude" in on and "mcp.example.com/mcp/connect" in on
    assert "keyed hash of your user and organisation ids" in on and "180 days" in on and "60 seconds" in on
    assert "the server&#x27;s memory" in on or "the server's memory" in on                # this test runs with the memory store
    assert "no database, no cache on disk and no file storage of its own." not in on


# ------------------------------------------------------------------ the real fetch, against a local TLS server --------

@pytest.fixture(scope="module")
def tls_server(tmp_path_factory):
    """An HTTPS server on 127.0.0.1 with a certificate for client.example from a CA of its own."""
    import datetime
    import ssl
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    d = tmp_path_factory.mktemp("tls")
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test ca")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(1).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                       encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "client.example")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(2)
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("client.example")]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    (d / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (d / "leaf.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    (d / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()))
    doc = {**DOCS[GLAMA], "client_id": "https://client.example/meta.json", "redirect_uris": ["https://client.example/cb"]}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/meta.json":
                body = json.dumps(doc).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/moved.json":
                self.send_response(301)
                self.send_header("Location", "https://client.example/meta.json")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif self.path == "/big.json":
                self.send_response(200)
                self.send_header("Content-Length", "20000")
                self.end_headers()
                self.wfile.write(b" " * 20000)
            elif self.path == "/slow-headers.json":
                self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                for n in range(40):
                    try:
                        self.wfile.write(f"X-Drip-{n}: 1\r\n".encode())
                        self.wfile.flush()
                    except OSError:
                        return
                    time.sleep(0.25)
            elif self.path == "/slow.json":
                self.send_response(200)
                self.send_header("Content-Length", "4000")
                self.end_headers()
                for _ in range(40):
                    try:
                        self.wfile.write(b" ")
                        self.wfile.flush()
                    except OSError:
                        return
                    time.sleep(0.25)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(d / "leaf.pem"), str(d / "key.pem"))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"port": server.server_address[1], "ca": str(d / "ca.pem"), "doc": doc}
    server.shutdown()


def _local(monkeypatch, addresses=("127.0.0.1",)):
    monkeypatch.setattr(reg, "_special_address", lambda a: a == "10.9.9.9")       # the test server is on loopback
    return lambda host, port, type=None: [(None, None, None, None, (a, port)) for a in addresses]


def test_the_real_fetch_checks_the_name_and_reads_the_document(tls_server, monkeypatch):
    resolve = _local(monkeypatch, ("2001:db8::1", "127.0.0.1"))                   # IPv4 first, another address after a failure
    status, headers, body = reg.fetch_https("https://client.example/meta.json", resolve=resolve, ca_certs=tls_server["ca"],
                                            port=tls_server["port"])
    assert status == 200 and json.loads(body) == tls_server["doc"] and headers["content-type"] == "application/json"
    client_ = reg.CimdResolver(fetch=lambda url: reg.fetch_https(url, resolve=resolve, ca_certs=tls_server["ca"],
                                                                port=tls_server["port"])).resolve("https://client.example/meta.json")
    assert client_.domain == "client.example" and client_.allows("https://client.example/cb")
    with pytest.raises(reg.ClientError, match="could not be fetched"):           # the certificate is for client.example only
        reg.fetch_https("https://other.example/meta.json", resolve=resolve, ca_certs=tls_server["ca"], port=tls_server["port"])
    with pytest.raises(reg.ClientError):
        reg.fetch_https("https://client.example/meta.json", resolve=resolve, port=tls_server["port"])   # not a public CA


def test_the_real_fetch_follows_no_redirect_and_reads_at_most_5_kb(tls_server, monkeypatch):
    resolve = _local(monkeypatch)
    status, headers, body = reg.fetch_https("https://client.example/moved.json", resolve=resolve, ca_certs=tls_server["ca"],
                                            port=tls_server["port"])
    assert status == 301 and body == b""
    status, _, body = reg.fetch_https("https://client.example/big.json", resolve=resolve, ca_certs=tls_server["ca"], port=tls_server["port"])
    assert len(body) == reg.MAX_CIMD_BYTES + 1
    with pytest.raises(reg.ClientError, match="does not fetch from"):
        reg.fetch_https("https://client.example/meta.json", resolve=_local(monkeypatch, ("127.0.0.1", "10.9.9.9")),
                        ca_certs=tls_server["ca"], port=tls_server["port"])


@pytest.mark.parametrize("path", ["/slow.json", "/slow-headers.json"])
def test_a_server_that_sends_slowly_is_cut_off_at_the_deadline(tls_server, monkeypatch, path):
    monkeypatch.setattr(reg, "FETCH_DEADLINE", 1.0)
    started = time.monotonic()
    with pytest.raises(reg.ClientError, match="took longer than"):
        reg.fetch_https("https://client.example" + path, resolve=_local(monkeypatch), ca_certs=tls_server["ca"], port=tls_server["port"])
    assert time.monotonic() - started < 2.5


def test_a_slow_name_lookup_is_cut_off_and_fetches_are_bounded(monkeypatch):
    import threading
    monkeypatch.setattr(reg, "FETCH_DEADLINE", 0.5)
    release = threading.Event()

    def slow(host, port, type=None):
        release.wait(10)
        return []
    try:
        started = time.monotonic()
        with pytest.raises(reg.ClientError, match="did not resolve in time"):
            reg.fetch_https("https://client.example/meta.json", resolve=slow)
        assert time.monotonic() - started < 1.5
        slots = [reg._fetch_slots.acquire(timeout=0) for _ in range(reg.FETCH_SLOTS)]
        try:
            with pytest.raises(reg.ClientError, match="busy fetching"):
                reg.fetch_https("https://client.example/meta.json", resolve=slow)
        finally:
            for taken in slots:
                if taken:
                    reg._fetch_slots.release()
        # the hanging lookup still holds its slot; with the others taken too, a new lookup is refused, not queued
        held = [reg._lookup_slots.acquire(timeout=0) for _ in range(reg.FETCH_SLOTS)]
        assert held.count(True) == reg.FETCH_SLOTS - 1
        try:
            with pytest.raises(reg.ClientError, match="busy looking up"):
                reg.fetch_https("https://client.example/meta.json", resolve=slow)
        finally:
            for taken in held:
                if taken:
                    reg._lookup_slots.release()
    finally:
        release.set()
    for _ in range(50):                                                         # once the lookup ends, its slot is free again
        if reg._lookup_slots._value == reg.FETCH_SLOTS:
            break
        time.sleep(0.05)
    assert reg._lookup_slots._value == reg.FETCH_SLOTS
