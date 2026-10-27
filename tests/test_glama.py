"""Finding 8 of 27 October 2026: the Glama catalog lists Krusgraph (glama.ai/mcp/connectors/com.krusgraph/krusgraph) and
asks the owner to confirm it with a file at the domain. /.well-known/glama.json serves the maintainer's claim, a token
made to be public, without sign-in; only when the server's public host (MCP_PUBLIC_URL) is krusgraph.com, so a
self-hosted copy never claims the listing of someone else's domain. Both with Entra sign-in in front of /mcp and
without it."""
import json

import pytest
from starlette.testclient import TestClient

from fabric_backend import server
from fabric_backend.entra import EntraConfig

BODY = b'{"$schema": "https://glama.ai/mcp/schemas/connector.json", "claim": "glama_claim_nlxchmx_fb4bANK8J8zGgfTdUrOH6Wq1"}'


def _app(monkeypatch, public_url: str | None, entra: bool):
    a = server.Auth()
    if public_url is None:
        monkeypatch.delenv("MCP_PUBLIC_URL", raising=False)
    else:
        monkeypatch.setenv("MCP_PUBLIC_URL", public_url)
    a.entra = EntraConfig(client_id="cid-123", public_url=public_url or "https://krusgraph.com/mcp", client_secret="s3cret") if entra else None
    monkeypatch.setattr(server, "auth", a)
    return TestClient(server.build_app())


@pytest.mark.parametrize("entra", [True, False])
def test_served_from_krusgraph_com_without_sign_in(monkeypatch, entra):
    c = _app(monkeypatch, "https://krusgraph.com/mcp", entra)
    r = c.get("/.well-known/glama.json")
    assert r.status_code == 200 and r.headers["content-type"] == "application/json" and r.content == BODY
    assert json.loads(r.content) == {"$schema": "https://glama.ai/mcp/schemas/connector.json",
                                     "claim": "glama_claim_nlxchmx_fb4bANK8J8zGgfTdUrOH6Wq1"}
    assert "www-authenticate" not in r.headers
    assert c.get("/.well-known/glama.json", headers={"Authorization": "Bearer not-a-token"}).content == BODY   # never validated
    assert c.head("/.well-known/glama.json").status_code == 200
    if entra:                                                    # /mcp keeps its 401 challenge in the same app
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r.status_code == 401 and "resource_metadata=" in r.headers["WWW-Authenticate"]


@pytest.mark.parametrize("entra", [True, False])
@pytest.mark.parametrize("public_url", ["https://mcp.example.com/mcp", "https://www.krusgraph.com/mcp",
                                        "https://krusgraph.com.example.org/mcp", None])
def test_any_other_host_answers_404(monkeypatch, entra, public_url):
    if public_url is None and entra:
        pytest.skip("Entra sign-in needs a public URL")
    c = _app(monkeypatch, public_url, entra)
    r = c.get("/.well-known/glama.json")
    assert r.status_code == 404 and b"glama_claim" not in r.content
    assert "www-authenticate" not in r.headers


def test_not_in_the_sitemap_or_llms_txt(monkeypatch):
    c = _app(monkeypatch, "https://krusgraph.com/mcp", False)
    assert "glama" not in c.get("/sitemap.xml").text and "glama" not in c.get("/llms.txt").text
