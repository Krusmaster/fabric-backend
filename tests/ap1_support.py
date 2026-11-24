"""AP1: shared doubles for the /app tests (tests/test_ap1_*.py). Invented names and ids only: the tenant ids below are
made up for the tests, and the data is the synthetic SAP demo of tests/wb15_fake.py (fabric_backend/sap_demo.py).

- `entra_app(monkeypatch, keys)`: the hosted app (server.build_app) in Entra mode with a test Entra app, its validator on
  a test key, a recording on-behalf-of exchange and a fake token endpoint; nothing reaches Microsoft.
- `sign_in(client, entra, token)`: the browser's way through /app/login, "Entra" and /app/callback.
- `data(monkeypatch)`: the synthetic SAP demo behind the tools (wb15_fake.install), with the tool's token readers left as
  the product has them, so every Fabric and SQL token comes from the session's on-behalf-of exchange; the tokens that
  reached the Fabric listing and the SQL endpoint are recorded.
"""
from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import jwt

from fabric_backend import guided_app, server
from fabric_backend.entra import EntraConfig, Validator

ORIGIN = "https://kg.example.com"
CFG = EntraConfig(ORIGIN + "/mcp", "11111111-2222-3333-4444-555555555555", "test-client-secret")
TID = "0a0a0a0a-1111-2222-3333-444444444444"          # invented: the allowed tenant of these tests
OTHER = "0b0b0b0b-5555-6666-7777-888888888888"        # invented: a tenant not on the list
NAME = "Alex Example"


class FakeJWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key})()


def tok(priv, tid: str = TID, **over) -> str:
    claims = {"aud": CFG.public_url, "iss": f"https://login.microsoftonline.com/{tid}/v2.0", "tid": tid,
              "exp": int(time.time()) + 3000, "scp": "user_impersonation", "oid": "person-1", "name": NAME}
    claims.update(over)
    return jwt.encode(claims, priv, algorithm="RS256")


class FakeEntra:
    """The token endpoint: an authorization code from `codes` is redeemed once for its access token."""

    def __init__(self):
        self.codes: dict[str, str] = {}
        self.requests: list[dict] = []

    def post(self, url, data):
        self.requests.append({"url": url, **data})
        token = self.codes.pop(data.get("code"), None)
        if token is None:
            from fabric_backend.entra import TokenError
            raise TokenError("invalid_grant")
        return {"access_token": token, "token_type": "Bearer", "expires_in": 3000}


class RecordingOBO:
    """On-behalf-of: each downstream token names its scope and a digest of the user token it came from."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    @staticmethod
    def expected(user_token: str, scope: str) -> str:
        return f"obo|{scope}|{hashlib.sha256(user_token.encode()).hexdigest()[:12]}"

    def token(self, user_token, tenant, scope):
        self.calls.append((hashlib.sha256(user_token.encode()).hexdigest()[:12], tenant, scope))
        return self.expected(user_token, scope)


def entra_app(monkeypatch, keys, tenants: str | None = TID):
    a = server.Auth()
    a.entra = CFG
    a._validator = Validator(CFG, FakeJWKS(keys[1]))
    a._obo = RecordingOBO()
    monkeypatch.setattr(server, "auth", a)
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    for k in ("KRUSGRAPH_CLIENT_REGISTRATION", "KRUSGRAPH_WORKLOAD_CLIENT_ID", "KRUSGRAPH_WORKLOAD_CLIENT_SECRET",
              "KRUSGRAPH_WORKLOAD_APP_ID_URI", "KRUSGRAPH_WORKLOAD_HOST"):
        monkeypatch.delenv(k, raising=False)
    if tenants is None:
        monkeypatch.delenv(guided_app.ENV, raising=False)
    else:
        monkeypatch.setenv(guided_app.ENV, tenants)
    fake = FakeEntra()
    monkeypatch.setattr(guided_app.App, "_entra_post", lambda self, data: fake.post(None, data))
    guided_app.SESSIONS.clear()
    guided_app.TXNS.clear()
    return server.build_app(), a, fake


def start_login(client):
    """GET /app/login: (the Entra address it sends the browser to, its query)."""
    r = client.get(guided_app.LOGIN)
    assert r.status_code == 302, r.status_code
    loc = r.headers["location"]
    return r, loc, {k: v[0] for k, v in parse_qs(urlsplit(loc).query).items()}


def sign_in(client, fake: FakeEntra, token: str, code: str = "code-1"):
    """The whole sign-in; returns the callback's response."""
    _, _, q = start_login(client)
    fake.codes[code] = token
    return client.get(guided_app.CALLBACK, params={"code": code, "state": q["state"]})


def data(monkeypatch) -> dict:
    """The synthetic SAP demo behind the tools, the tokens recorded where they reach Fabric and the SQL endpoint."""
    import wb15_fake
    seen = {"fabric": [], "sql": []}
    keep = server.auth                                  # install() patches the token readers on this object ...
    wb15_fake.install(monkeypatch)
    monkeypatch.setattr(keep, "fabric", type(keep).fabric.__get__(keep))     # ... and they are put back here
    monkeypatch.setattr(keep, "sql", type(keep).sql.__get__(keep))
    factory = server._execute_factory

    def workspaces(headers):
        seen["fabric"].append(headers.get("Authorization"))
        return [{"id": "w-demo", "name": "demo", "capacity_id": "cap-1"},
                {"id": "w-arch", "name": "sales_archive", "capacity_id": "cap-1"}]

    def execute_factory(item, token):
        seen["sql"].append(token)
        return factory(item, token)
    monkeypatch.setattr(server, "_workspaces", workspaces)
    monkeypatch.setattr(server, "_execute_factory", execute_factory)
    monkeypatch.setattr(server, "_workspace_hints", lambda ids, headers: {"w-demo": "1 lakehouse"})
    return seen


def step(client, body: dict, **headers):
    h = {"Origin": ORIGIN, "Content-Type": "application/json", **headers}
    return client.post(guided_app.STEP, content=json.dumps(body), headers=h)
