"""Security review of the Entra sign-in path: entra.Validator, server.Auth and the 401 guard in front of /mcp.

Every token here is minted with a throw-away RSA key; the JWKS client is replaced by one that returns that key's
public half, exactly as `tests/test_entra.py` does. Findings and what cannot be fixed here: docs/SECURITY.md.
"""
import json
import logging
import socket
import threading
import time

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import errors, server  # noqa: E402
from fabric_backend.entra import EntraConfig, OnBehalfOf, TokenError, Validator  # noqa: E402

CFG = EntraConfig("https://mcp.example.com/mcp", "11111111-2222-3333-4444-555555555555", "s3cret")
TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_TID = "bbbbbbbb-0000-0000-0000-000000000000"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "security-test", "version": "1"}}}
ACCEPT = {"Accept": "application/json, text/event-stream"}


class FakeJWKS:
    def __init__(self, key):
        self.key = key
        self.calls = 0

    def get_signing_key_from_jwt(self, token):
        self.calls += 1
        return type("K", (), {"key": self.key})()


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def tok(priv, **over):
    claims = {"aud": CFG.public_url, "iss": f"https://login.microsoftonline.com/{TID}/v2.0", "tid": TID,
              "exp": int(time.time()) + 600, "iat": int(time.time()) - 5, "scp": "user_impersonation", "oid": "user-1"}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}                  # None removes a claim
    return jwt.encode(claims, priv, algorithm="RS256")


@pytest.fixture
def validator(keys):
    return Validator(CFG, FakeJWKS(keys[1]))


@pytest.fixture
def app(monkeypatch, keys):
    a = server.Auth()
    a.entra = CFG
    a._validator = Validator(CFG, FakeJWKS(keys[1]))
    monkeypatch.setattr(server, "auth", a)
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    return server.build_app()


# ------------------------------------------------------------------ token validation ----------

def test_good_token_is_accepted_and_claims_are_returned(validator, keys):
    claims = validator.validate(tok(keys[0]))
    assert claims["tid"] == TID and claims["oid"] == "user-1"


def test_wrong_audience_is_rejected(validator, keys):
    for aud in ("someone-else", "https://api.fabric.microsoft.com", f"api://{OTHER_TID}", [CFG.public_url + "x"]):
        with pytest.raises(TokenError, match="invalid token"):
            validator.validate(tok(keys[0], aud=aud))
    # the three forms Entra uses for this app are the only ones accepted
    for aud in (CFG.public_url, CFG.client_id, f"api://{CFG.client_id}"):
        assert validator.validate(tok(keys[0], aud=aud))["tid"] == TID


def test_wrong_issuer_is_rejected(validator, keys):
    with pytest.raises(TokenError):                                              # v1 issuer
        validator.validate(tok(keys[0], iss=f"https://sts.windows.net/{TID}/"))
    with pytest.raises(TokenError, match="issuer does not match"):               # another tenant's issuer, same tid claim
        validator.validate(tok(keys[0], iss=f"https://login.microsoftonline.com/{OTHER_TID}/v2.0"))
    with pytest.raises(TokenError, match="issuer does not match"):               # tid says one tenant, iss another
        validator.validate(tok(keys[0], tid=OTHER_TID))
    with pytest.raises(TokenError):                                              # no issuer at all
        validator.validate(tok(keys[0], iss=None))


def test_expired_and_not_yet_valid_tokens_are_rejected(validator, keys):
    with pytest.raises(TokenError, match="ExpiredSignatureError"):
        validator.validate(tok(keys[0], exp=int(time.time()) - 1))
    with pytest.raises(TokenError, match="ImmatureSignatureError"):
        validator.validate(tok(keys[0], nbf=int(time.time()) + 300))
    with pytest.raises(TokenError, match="MissingRequiredClaimError"):
        validator.validate(tok(keys[0], exp=None))


def test_tenant_not_on_the_allow_list_is_rejected(keys):
    cfg = EntraConfig(CFG.public_url, CFG.client_id, CFG.client_secret, {OTHER_TID})
    v = Validator(cfg, FakeJWKS(keys[1]))
    with pytest.raises(TokenError, match="tenant not allowed"):
        v.validate(tok(keys[0]))
    assert v.validate(tok(keys[0], tid=OTHER_TID, iss=f"https://login.microsoftonline.com/{OTHER_TID}/v2.0"))["tid"] == OTHER_TID
    # case of the tenant id does not open a gap
    assert v.validate(tok(keys[0], tid=OTHER_TID.upper(), iss=f"https://login.microsoftonline.com/{OTHER_TID.upper()}/v2.0"))["tid"] == OTHER_TID.upper()


def test_token_without_the_delegated_scope_is_rejected(validator, keys):
    for scp in (None, "", "Workspace.Read.All", "user_impersonation_x", "User_Impersonation"):
        with pytest.raises(TokenError, match="user_impersonation"):
            validator.validate(tok(keys[0], scp=scp))
    with pytest.raises(TokenError):                                              # an app-only token (roles, no scp)
        validator.validate(tok(keys[0], scp=None, roles=["user_impersonation"]))
    assert validator.validate(tok(keys[0], scp="offline_access user_impersonation"))["tid"] == TID


def test_alg_none_and_key_confusion_are_rejected(validator, keys):
    claims = jwt.decode(tok(keys[0]), options={"verify_signature": False})
    unsigned = jwt.encode(claims, key=None, algorithm="none")
    assert unsigned.endswith(".")
    with pytest.raises(TokenError):
        validator.validate(unsigned)
    # HS256 signed with the server's public key as the shared secret: must not verify under RS256-only
    import base64
    import hashlib
    import hmac
    pem = keys[1].public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    signing_input = f"{b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())}.{b64(json.dumps(claims).encode())}"
    confused = f"{signing_input}.{b64(hmac.new(pem, signing_input.encode(), hashlib.sha256).digest())}"
    with pytest.raises(TokenError):
        validator.validate(confused)
    for header_only in ("eyJhbGciOiJub25lIn0", "eyJhbGciOiJub25lIn0..", "not-a-token", ""):
        with pytest.raises(TokenError):
            validator.validate(header_only)


def test_altered_signature_and_altered_payload_are_rejected(validator, keys):
    good = tok(keys[0])
    h, p, s = good.split(".")
    flipped = s[:-2] + ("A" if s[-2] != "A" else "B") + s[-1]
    with pytest.raises(TokenError):
        validator.validate(f"{h}.{p}.{flipped}")
    with pytest.raises(TokenError):
        validator.validate(f"{h}.{p}.")
    claims = jwt.decode(good, options={"verify_signature": False})
    claims["tid"] = OTHER_TID
    claims["iss"] = f"https://login.microsoftonline.com/{OTHER_TID}/v2.0"
    forged_payload = jwt.utils.base64url_encode(json.dumps(claims).encode()).decode()
    with pytest.raises(TokenError):
        validator.validate(f"{h}.{forged_payload}.{s}")                        # payload changed, old signature
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(TokenError):
        validator.validate(tok(other))                                          # signed by a key Entra never published


def test_token_errors_never_quote_the_token(validator, keys):
    bad = tok(keys[0], aud="x")
    with pytest.raises(TokenError) as e:
        validator.validate(bad)
    assert bad[:20] not in str(e.value) and "eyJ" not in str(e.value)


# ------------------------------------------------------------------ the /mcp guard -------------

def test_guard_answers_401_for_every_method_and_token_shape(app, keys):
    with TestClient(app, base_url="https://mcp.example.com") as c:
        for method in ("get", "post", "delete", "options", "put"):
            r = getattr(c, method)("/mcp", headers=ACCEPT)
            assert r.status_code == 401 and "resource_metadata=" in r.headers["www-authenticate"], method
        for auth in ("Basic dXNlcjpwYXNz", "Bearer", "Bearer ", "bearer  ", "Token " + tok(keys[0]), tok(keys[0])):
            r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": auth})
            assert r.status_code == 401 and 'error="invalid_token"' not in r.headers["www-authenticate"], auth
        for bad in (tok(keys[0], aud="x"), tok(keys[0], exp=int(time.time()) - 1), tok(keys[0], scp="read"),
                    tok(keys[0], iss=f"https://login.microsoftonline.com/{OTHER_TID}/v2.0"), "eyJhbGciOiJub25lIn0..", "x" * 10):
            r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {bad}"})
            assert r.status_code == 401 and 'error="invalid_token"' in r.headers["www-authenticate"]
            assert bad[:16] not in r.text and bad[:16] not in r.headers["www-authenticate"]
            assert r.headers["strict-transport-security"] == "max-age=31536000" and r.headers["x-content-type-options"] == "nosniff"
        r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {tok(keys[0])}"})
        assert r.status_code == 200 and '"serverInfo"' in r.text
        assert r.headers["strict-transport-security"] == "max-age=31536000"


def test_guard_cannot_be_walked_around_with_path_variants(app, keys):
    """The MCP endpoint is exactly /mcp; everything that reaches it is guarded, everything else is not the endpoint."""
    import anyio

    async def call(path):
        sent = []

        async def receive():
            return {"type": "http.request", "body": json.dumps(INIT).encode(), "more_body": False}

        async def send(message):
            sent.append(message)
        scope = {"type": "http", "method": "POST", "path": path, "raw_path": path.encode(), "query_string": b"",
                 "headers": [(b"host", b"mcp.example.com"), (b"content-type", b"application/json"),
                             (b"accept", b"application/json, text/event-stream")], "scheme": "https", "server": ("mcp.example.com", 443),
                 "client": ("127.0.0.1", 1), "http_version": "1.1", "root_path": "", "app": None}
        await app(scope, receive, send)
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return status, body
    with TestClient(app, base_url="https://mcp.example.com") as c:
        for path in ("/mcp/", "/mcp?x=1", "/mcp%2F", "/mcp/./", "/MCP", "/mcp/x", "//mcp", "/mcp;x", "/mcp/server-card/../"):
            r = c.post(path, json=INIT, headers=ACCEPT)
            assert r.status_code in (401, 404, 405), (path, r.status_code)
            assert '"serverInfo"' not in r.text, path
        for path in ("/mcp/../mcp", "/./mcp", "/mcp/.", "/%6dcp", "/mcp\x00"):   # raw ASGI: no client normalises the path
            status, body = anyio.run(call, path)
            assert status in (401, 404, 405) and b"serverInfo" not in body, (path, status, body[:80])


def test_oversized_authorization_header_is_refused_fast_and_not_echoed(app):
    big = "A" * 256_000
    with TestClient(app, base_url="https://mcp.example.com") as c:
        t0 = time.time()
        r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {big}"})
        assert r.status_code == 401 and time.time() - t0 < 2
        assert "AAAAAAAA" not in r.text and "AAAAAAAA" not in r.headers["www-authenticate"]
        r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer eyJ{big}.{big}.{big}"})
        assert r.status_code == 401


def test_oversized_headers_through_the_real_http_server(app):
    """uvicorn with h11, as the image runs it: a 100 KiB Authorization header is either refused by the HTTP layer
    or answered 401 in bounded time without being echoed, and the server keeps serving afterwards."""
    import uvicorn
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="on", http="h11")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if srv.started:
                break
            time.sleep(0.05)
        assert srv.started
        port = srv.servers[0].sockets[0].getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"POST /mcp HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer " + b"A" * 100_000 + b"\r\nContent-Length: 0\r\n\r\n")
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 65536:
                chunk = s.recv(4096)
                if not chunk:
                    break
                head += chunk
        status = head.split(b" ", 2)[1] if head.startswith(b"HTTP/1.1") else b"closed"
        assert status in (b"400", b"401", b"431", b"closed"), head[:200]
        assert b"AAAAAAAA" not in head
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:    # the server is still fine afterwards
            s.sendall(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n")
            assert s.recv(4096).startswith(b"HTTP/1.1 200")
    finally:
        srv.should_exit = True
        thread.join(timeout=10)


def test_request_bodies_are_capped_even_without_content_length(app, keys):
    """A declared body over the limit is 413 before it is read; an undeclared (chunked) one is cut off at the limit."""
    with TestClient(app, base_url="https://mcp.example.com") as c:
        auth = {**ACCEPT, "Authorization": f"Bearer {tok(keys[0])}", "Content-Type": "application/json"}
        r = c.post("/mcp", content=b"{}", headers={**auth, "Content-Length": str(server.MAX_BODY_BYTES + 1)})
        assert r.status_code == 413

        def chunks():
            yield b'{"pad": "'
            for _ in range(5):
                yield b"x" * (1024 * 1024)
            yield b'"}'
        r = c.post("/mcp", content=chunks(), headers=auth)
        assert r.status_code == 413 and "request body over" in r.text
        r = c.post("/mcp", json=INIT, headers=auth)                              # and the server still answers
        assert r.status_code == 200 and '"serverInfo"' in r.text


# ------------------------------------------------------------------ on-behalf-of cache ---------

def test_on_behalf_of_cache_never_shares_tokens_between_users():
    calls = []

    def post(url, data):
        calls.append(data["assertion"])
        return {"access_token": f"downstream-for-{data['assertion']}", "expires_in": 3600}

    o = OnBehalfOf(CFG, post)
    scope = "https://api.fabric.microsoft.com/.default"
    assert o.token("user-A-token", TID, scope) == "downstream-for-user-A-token"
    assert o.token("user-B-token", TID, scope) == "downstream-for-user-B-token"
    assert o.token("user-A-token", TID, scope) == "downstream-for-user-A-token"           # A's cache hit is A's token
    assert calls == ["user-A-token", "user-B-token"]
    # the same user with a new token (new sign-in) is a new entry; a token differing in one character too
    assert o.token("user-A-token2", TID, scope) == "downstream-for-user-A-token2"
    assert o.token("user-A-toker", TID, scope) == "downstream-for-user-A-toker"
    # the cache holds hashes, never the user's token itself
    assert all(len(k[0]) == 64 and "user-" not in k[0] for k in o._cache)
    assert not any("user-A-token" in v[0] for v in o._cache.values() if False)              # downstream tokens only


def test_on_behalf_of_cache_is_bounded_and_keeps_the_newest_entries(monkeypatch):
    from fabric_backend import entra
    monkeypatch.setattr(entra, "MAX_CACHED_TOKENS", 10)
    now = [1000.0]
    monkeypatch.setattr(entra.time, "time", lambda: now[0])
    o = OnBehalfOf(CFG, lambda url, data: {"access_token": "t-" + data["assertion"], "expires_in": 3600})
    for i in range(11):
        now[0] += 1
        o.token(f"user-{i}", TID, "s")
    assert len(o._cache) <= 10 and o.token("user-10", TID, "s") == "t-user-10"
    # expired entries go first: after everything above has expired, the next overflow keeps only live entries
    now[0] += 4000
    for i in range(11):
        o.token(f"later-{i}", TID, "s")
    assert len(o._cache) <= 10 and all(v[1] > now[0] for v in o._cache.values())


def test_on_behalf_of_failures_do_not_leak_the_user_token():
    def post(url, data):
        raise TokenError("on-behalf-of failed: invalid_grant — AADSTS65001: consent required")

    o = OnBehalfOf(CFG, post)
    with pytest.raises(TokenError) as e:
        o.token("eyJ-secret-user-token", TID, "s")
    assert "secret-user-token" not in str(e.value)
    o2 = OnBehalfOf(CFG, lambda url, data: {"error": "x"})
    with pytest.raises(TokenError, match="without an access token"):
        o2.token("eyJ-secret-user-token", TID, "s")


# ------------------------------------------------------------------ nothing is logged ----------

def test_tokens_and_secrets_never_reach_logs_or_stdout(app, keys, caplog, capsys, monkeypatch):
    caplog.set_level(logging.DEBUG)
    secret_token = tok(keys[0], aud="wrong")
    good = tok(keys[0])
    with TestClient(app, base_url="https://mcp.example.com") as c:
        c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {secret_token}"})
        c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {good}"})
        # a tool call whose downstream exchange fails
        calls = {}

        def failing_post(url, data):
            calls["assertion"] = data["assertion"]
            raise TokenError("on-behalf-of failed: invalid_grant — AADSTS50013")
        server.auth._obo = OnBehalfOf(CFG, failing_post)
        r = c.post("/mcp", headers={**ACCEPT, "Authorization": f"Bearer {good}"}, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_workspaces", "arguments": {}}})
        assert r.status_code == 200 and calls["assertion"] == good
    out, err = capsys.readouterr()
    for text in (caplog.text, out, err, r.text):
        assert secret_token[:24] not in text and good[:24] not in text and "s3cret" not in text
    assert "sign_in" in r.text or "consent" in r.text                            # the user gets a kind, not a token


def test_error_layer_scrubs_tokens_and_secrets_from_messages():
    bearer = "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJlLXNpZ25hdHVyZQ"
    for msg in (f"401 from https://api.fabric.microsoft.com with Authorization: {bearer}",
                "client_secret=super-secret-value failed", f"token {bearer.split(' ')[1]} rejected", "X-Fabric-SQL-Token: abc.def.ghi"):
        clean = errors.scrub(msg)
        assert "eyJ" not in clean and "super-secret" not in clean and "abc.def.ghi" not in clean, clean
    answer = json.loads(errors.safe(lambda: (_ for _ in ()).throw(RuntimeError(f"failed with {bearer}")))())
    assert "eyJ" not in json.dumps(answer) and set(answer) >= {"error", "kind", "hint"}


def test_config_never_prints_its_secret_and_challenge_never_reflects_input():
    from fabric_backend.entra import challenge
    assert "s3cret" not in repr(CFG) and "s3cret" not in str(CFG)
    assert "<script>" not in challenge(CFG, "invalid_token") and challenge(CFG, 'x" evil="y') .count('"') % 2 == 0
