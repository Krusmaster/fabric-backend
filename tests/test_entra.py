import time

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
