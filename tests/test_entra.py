import time
from urllib.parse import parse_qs, urlsplit

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from fabric_backend.entra import (EntraConfig, Validator, OnBehalfOf, TokenError, protected_resource_metadata,  # noqa: E402
                                  challenge, admin_consent_url)

CFG = EntraConfig("https://mcp.example.com/mcp", "11111111-2222-3333-4444-555555555555", "s3cret")
TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


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
              "exp": int(time.time()) + 600, "scp": "user_impersonation", "oid": "user-1"}
    claims.update(over)
    return jwt.encode(claims, priv, algorithm="RS256")


def test_metadata_and_challenge():
    m = protected_resource_metadata(CFG)
    assert m["resource"] == "https://mcp.example.com/mcp"                         # must equal the URL users enter
    assert m["authorization_servers"][0] == "https://login.microsoftonline.com/organizations/v2.0"
    assert "https://mcp.example.com/mcp/user_impersonation" in m["scopes_supported"]
    c = challenge(CFG)
    assert c.startswith("Bearer ") and 'resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"' in c
    assert 'error="invalid_token"' in challenge(CFG, "invalid_token")
    assert "adminconsent" in admin_consent_url(CFG) and CFG.client_id in admin_consent_url(CFG)
    consent = urlsplit(admin_consent_url(CFG, TID))
    assert consent.path == f"/{TID}/adminconsent"
    assert parse_qs(consent.query) == {"client_id": [CFG.client_id]}


def test_validator_accepts_good_token_and_rejects_the_rest(keys):
    priv, pub = keys
    v = Validator(CFG, FakeJWKS(pub))
    assert v.validate(tok(priv))["tid"] == TID
    assert v.validate(tok(priv, aud=CFG.client_id))["tid"] == TID                 # v2 tokens may carry the client id
    for bad in (tok(priv, aud="someone-else"), tok(priv, exp=int(time.time()) - 10),
                tok(priv, iss="https://login.microsoftonline.com/other-tenant/v2.0")):
        with pytest.raises(TokenError):
            v.validate(bad)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(TokenError):
        v.validate(tok(other))                                                    # wrong signature
    v2 = Validator(EntraConfig(CFG.public_url, CFG.client_id, CFG.client_secret, {"only-this-tenant"}), FakeJWKS(pub))
    with pytest.raises(TokenError):
        v2.validate(tok(priv))


@pytest.mark.parametrize("scope", [None, "", "read", "user_impersonation.extra", ["user_impersonation"]])
def test_validator_requires_delegated_permission(keys, scope):
    priv, pub = keys
    with pytest.raises(TokenError):
        Validator(CFG, FakeJWKS(pub)).validate(tok(priv, scp=scope, roles=["user_impersonation"]))


def test_validator_accepts_permission_among_other_scopes(keys):
    priv, pub = keys
    assert Validator(CFG, FakeJWKS(pub)).validate(tok(priv, scp="read user_impersonation"))["tid"] == TID


def test_missing_entra_configuration_stops_public_server(monkeypatch):
    for name in ("MCP_PUBLIC_URL", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_REQUIRED"):
        monkeypatch.delenv(name, raising=False)
    assert EntraConfig.from_env() is None
    monkeypatch.setenv("ENTRA_REQUIRED", "true")
    with pytest.raises(ValueError):
        EntraConfig.from_env()
    monkeypatch.delenv("ENTRA_REQUIRED")
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    with pytest.raises(ValueError):
        EntraConfig.from_env()
    monkeypatch.setenv("ENTRA_CLIENT_ID", CFG.client_id)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", CFG.client_secret)
    assert EntraConfig.from_env().scope == CFG.scope
    assert CFG.client_secret not in repr(EntraConfig.from_env())


def test_http_pages_metadata_and_mcp_authentication(monkeypatch, keys):
    from starlette.testclient import TestClient
    from fabric_backend import server
    priv, pub = keys
    a = server.Auth()
    a.entra = CFG
    a._validator = Validator(CFG, FakeJWKS(pub))
    monkeypatch.setattr(server, "auth", a)
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    with TestClient(server.build_app(), base_url="https://mcp.example.com") as client:
        for path in ("/", "/docs", "/privacy"):
            response = client.get(path)
            assert response.status_code == 200
            assert "Krusgraph" in response.text and "{{" not in response.text
        assert client.get("/healthz").json() == {"ok": True, "auth": "entra"}
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.json()["resource"] == CFG.public_url
        # discovery documents stay public in Entra mode: the guard covers exactly /mcp, nothing under it
        for path in ("/mcp/server-card", "/.well-known/ai-catalog.json", "/llms.txt", "/sitemap.xml", "/robots.txt",
                     "/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/lovable"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "www-authenticate" not in response.headers, path
        assert client.get("/mcp").status_code == 401
        for path in ("/mcp", "/mcp/"):
            response = client.post(path, json={})
            assert response.status_code == 401
            assert CFG.metadata_url in response.headers["www-authenticate"]
        response = client.post("/mcp", json={}, headers={"Authorization": "Bearer invalid"})
        assert response.status_code == 401
        assert 'error="invalid_token"' in response.headers["www-authenticate"]
        response = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "deployment-test", "version": "1"}}},
            headers={"Authorization": f"Bearer {tok(priv)}", "Accept": "application/json, text/event-stream"})
        assert response.status_code == 200
        assert '"serverInfo"' in response.text


def test_on_behalf_of_exchanges_and_caches():
    calls = []

    def post(url, data):
        calls.append((url, data))
        return {"access_token": f"fabric-for-{data['assertion'][:4]}", "expires_in": 3600}

    o = OnBehalfOf(CFG, post)
    assert o.token("userTOKEN", TID, "https://api.fabric.microsoft.com/.default") == "fabric-for-user"
    assert o.token("userTOKEN", TID, "https://api.fabric.microsoft.com/.default") == "fabric-for-user"
    assert len(calls) == 1                                                        # cached
    url, data = calls[0]
    assert url.endswith(f"/{TID}/oauth2/v2.0/token") and data["requested_token_use"] == "on_behalf_of"
    assert data["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    o.token("userTOKEN", TID, "https://database.windows.net/.default")
    assert len(calls) == 2                                                        # different audience, new exchange


def test_privacy_and_docs_pages(monkeypatch):
    from fabric_backend.pages import privacy_html, docs_html
    monkeypatch.setenv("PRODUCT_NAME", "Testname")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://mcp.testname.io/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@testname.io")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    p, d = privacy_html(), docs_html()
    assert "<h1>Privacy policy — Testname</h1>" in p and "Kruse Consulting AB" in p and "{{" not in p
    assert "Template." not in p and "hello@testname.io" in p
    for must in ("What we process", "Kept", "Third parties", "Your rights", "Contact"):   # directory: collection, storage, sharing, retention, contact
        assert must in p, must
    assert "<table>" in p and "never written to disk or logs" in p
    assert "client_id=cid-123" in d and "https://mcp.testname.io/mcp" in d and "{{" not in d
    assert "<td><code>create_backend</code></td>" in d
