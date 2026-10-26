"""Dynamic client registration behind KRUSGRAPH_DCR: off by default (nothing served, Claude's sign-in unchanged), and
with the flag on a registration facade that answers with the Entra app's public client id for allowed redirect URIs."""
import json

import pytest
from starlette.testclient import TestClient

from fabric_backend import dcr, server
from fabric_backend.entra import EntraConfig, protected_resource_metadata

CFG = EntraConfig("https://mcp.example.com/mcp", "11111111-2222-3333-4444-555555555555", "s3cret")
ALLOWED = ["https://lovable.dev/oauth/callback", "http://127.0.0.1", "http://localhost"]


@pytest.fixture
def app(monkeypatch):
    a = server.Auth()
    a.entra = CFG
    monkeypatch.setattr(server, "auth", a)
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")

    def build():
        return TestClient(server.build_app())
    return build


def test_off_by_default_nothing_is_served_and_the_resource_metadata_is_unchanged(app, monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_DCR", raising=False)
    with app() as c:
        assert c.get("/.well-known/oauth-authorization-server").status_code == 404
        assert c.post("/oauth/register", json={"redirect_uris": ALLOWED[:1]}).status_code in (404, 405)
        assert c.get("/.well-known/oauth-protected-resource").json() == protected_resource_metadata(CFG)
        assert c.get("/.well-known/oauth-protected-resource").json()["authorization_servers"] == ["https://login.microsoftonline.com/organizations/v2.0"]


def test_metadata_points_at_entra_and_names_the_registration_endpoint():
    m = dcr.authorization_server_metadata(CFG)
    assert m["issuer"] == "https://mcp.example.com"
    assert m["authorization_endpoint"] == "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize"
    assert m["token_endpoint"] == "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"
    assert m["registration_endpoint"] == "https://mcp.example.com/oauth/register"
    assert m["code_challenge_methods_supported"] == ["S256"] and m["token_endpoint_auth_methods_supported"] == ["none"]
    assert m["scopes_supported"] == ["https://mcp.example.com/mcp/user_impersonation", "offline_access"]
    assert m["client_id_metadata_document_supported"] is False


def test_registration_answers_the_public_client_id_for_allowed_redirects_only():
    status, out = dcr.register(CFG, {"redirect_uris": ["https://lovable.dev/oauth/callback"], "client_name": "Lovable",
                                     "grant_types": ["authorization_code"], "token_endpoint_auth_method": "client_secret_post"}, ALLOWED)
    assert status == 201 and out["client_id"] == CFG.client_id and "client_secret" not in out
    assert out["token_endpoint_auth_method"] == "none" and out["grant_types"] == ["authorization_code", "refresh_token"]
    assert out["redirect_uris"] == ["https://lovable.dev/oauth/callback"] and out["client_name"] == "Lovable"
    assert out["scope"] == "https://mcp.example.com/mcp/user_impersonation offline_access"
    # loopback: any port and path on an allowed loopback host (RFC 8252)
    status, out = dcr.register(CFG, {"redirect_uris": ["http://127.0.0.1:53421/callback", "http://localhost:8080/auth/cb"]}, ALLOWED)
    assert status == 201
    # refused: not on the list, http on a real host, a fragment, no list, too many, a foreign grant
    for body in ({"redirect_uris": ["https://evil.example/cb"]}, {"redirect_uris": ["http://lovable.dev/oauth/callback"]},
                 {"redirect_uris": ["https://lovable.dev/oauth/callback#x"]}, {"redirect_uris": []}, {}, "nope",
                 {"redirect_uris": ["https://lovable.dev/oauth/callback"] * 11},
                 {"redirect_uris": ["https://lovable.dev/oauth/callback"], "grant_types": ["client_credentials"]}):
        status, out = dcr.register(CFG, body, ALLOWED)
        assert status == 400 and out["error"] in ("invalid_redirect_uri", "invalid_client_metadata"), body
    assert "evil.example" in dcr.register(CFG, {"redirect_uris": ["https://evil.example/cb"]}, ALLOWED)[1]["error_description"]
    assert dcr.register(CFG, {"redirect_uris": ["https://lovable.dev/oauth/callback"]}, [])[0] == 400       # empty allow-list: nobody


def test_with_the_flag_on_the_routes_exist_and_claude_s_challenge_is_unchanged(app, monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_DCR", "1")
    monkeypatch.setenv("KRUSGRAPH_DCR_REDIRECTS", ",".join(ALLOWED))
    with app() as c:
        prm = c.get("/.well-known/oauth-protected-resource").json()
        assert prm["authorization_servers"] == ["https://mcp.example.com", "https://login.microsoftonline.com/organizations/v2.0"]
        assert prm["resource"] == CFG.public_url
        m = c.get("/.well-known/oauth-authorization-server").json()
        assert m["registration_endpoint"] == "https://mcp.example.com/oauth/register"
        r = c.post("/oauth/register", json={"redirect_uris": ["https://lovable.dev/oauth/callback"]})
        assert r.status_code == 201 and r.json()["client_id"] == CFG.client_id and r.headers["cache-control"] == "no-store"
        assert c.post("/oauth/register", json={"redirect_uris": ["https://evil.example/cb"]}).status_code == 400
        assert c.post("/oauth/register", content=b"{not json", headers={"Content-Type": "application/json"}).status_code == 400
        assert c.post("/oauth/register", content=b"x" * (dcr.MAX_BODY + 1), headers={"Content-Type": "application/json"}).status_code == 413
        assert c.get("/oauth/register").status_code == 405
        # the MCP endpoint still answers 401 with the same challenge as before
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r.status_code == 401 and 'resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"' in r.headers["WWW-Authenticate"]
        assert "s3cret" not in json.dumps(m) and "s3cret" not in r.text
