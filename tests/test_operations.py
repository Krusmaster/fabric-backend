"""Operations before real customers: fair-use limits per user and organisation, anonymous usage statistics,
/health and /metrics, the client secret from Key Vault, the dormant paid-plan check, and the --key-vault deploy step.
Everything with throw-away keys and fake HTTP; nothing here calls Azure, Entra or Fabric."""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import entitlements, errors, keyvault, limits, pages, server, usage  # noqa: E402
from fabric_backend.entra import EntraConfig, OnBehalfOf, TokenError, Validator  # noqa: E402

CFG = EntraConfig("https://mcp.example.com/mcp", "11111111-2222-3333-4444-555555555555", "s3cret")
TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_TID = "bbbbbbbb-0000-0000-0000-000000000000"
ACCEPT = {"Accept": "application/json, text/event-stream"}


class FakeJWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key})()


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def tok(priv, oid="user-1", tid=TID):
    claims = {"aud": CFG.public_url, "iss": f"https://login.microsoftonline.com/{tid}/v2.0", "tid": tid, "oid": oid,
              "exp": int(time.time()) + 600, "iat": int(time.time()) - 5, "scp": "user_impersonation"}
    return jwt.encode(claims, priv, algorithm="RS256")


@pytest.fixture
def entra(monkeypatch, keys):
    a = server.Auth()
    a.entra = CFG
    a._validator = Validator(CFG, FakeJWKS(keys[1]))
    monkeypatch.setattr(server, "auth", a)
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    # list_workspaces without Fabric: the tool body runs, nothing leaves the test
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspaces", lambda headers: [{"name": "Sales", "id": "ws-1"}])
    return keys


def call(client, token, name="list_workspaces", arguments=None, rid=1):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}},
                    headers={**ACCEPT, "Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.text
    payload = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) if "data: " in body else r.json()
    return json.loads(payload["result"]["content"][0]["text"])


# ------------------------------------------------------------------ limits ---------------------

def test_limit_specs_parse_and_bad_ones_stop_startup():
    assert limits.parse("30/minute,600/hour") == [(30, 60), (600, 3600)]
    assert limits.parse("5/10s, 2/day") == [(5, 10), (2, 86400)]
    assert limits.parse("1/minutes") == [(1, 60)]
    for bad in ("30", "x/minute", "0/minute", "30/fortnight", "30 per minute"):
        with pytest.raises(ValueError):
            limits.parse(bad)


def test_bucket_allows_a_burst_then_refuses_with_the_wait_and_refills():
    now = [1000.0]
    lim = limits.Limiter([(3, 60)], [(100, 60)], clock=lambda: now[0])
    assert [lim.check("u", "t") for _ in range(3)] == [None, None, None]
    hit = lim.check("u", "t")
    assert hit == {"scope": "user", "limit": "3 calls per minute", "retry_after": 20}
    assert lim.check("someone-else", "t") is None                    # another user in the same organisation is not held back
    now[0] += 20
    assert lim.check("u", "t") is None and lim.check("u", "t")["retry_after"] == 20
    now[0] += 600
    assert all(lim.check("u", "t") is None for _ in range(3))          # refilled to the burst size, not beyond


def test_the_organisation_limit_covers_all_its_users_and_a_refusal_costs_nothing():
    now = [0.0]
    lim = limits.Limiter([(100, 60)], [(4, 60)], clock=lambda: now[0])
    assert all(lim.check(f"u{i}", "t") is None for i in range(4))
    hit = lim.check("u9", "t")
    assert hit["scope"] == "organisation" and hit["retry_after"] == 15
    assert lim.check("u9", "other-org") is None
    # the refused calls did not take from the user's own bucket: after the org refills, u9 still has its full burst
    now[0] += 60
    assert lim.check("u9", "t") is None


def test_buckets_hold_no_ids_in_clear_and_idle_ones_are_pruned(monkeypatch):
    now = [0.0]
    lim = limits.Limiter([(2, 60)], [(2, 60)], clock=lambda: now[0])
    lim.check("user-object-id-123", TID)
    assert not any("user-object-id-123" in str(k) or TID in str(k) for k in lim._buckets)
    monkeypatch.setattr(limits, "MAX_KEYS", 3)
    lim.check("b", "t2")
    now[0] += 120                                                       # both users idle long enough to be full again
    lim.check("c", "t3")
    assert len(lim._buckets) <= 3


def test_limits_from_env(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_RATE_LIMITS", "0")
    assert limits.Limiter.from_env() is None
    monkeypatch.setenv("KRUSGRAPH_RATE_LIMITS", "1")
    monkeypatch.setenv("KRUSGRAPH_RATE_USER", "7/minute")
    monkeypatch.delenv("KRUSGRAPH_RATE_ORG", raising=False)
    lim = limits.Limiter.from_env()
    assert lim.rules == {"user": [(7, 60)], "organisation": limits.parse(limits.DEFAULT_ORG)}
    monkeypatch.setenv("KRUSGRAPH_RATE_USER", "seven")
    with pytest.raises(ValueError):
        limits.Limiter.from_env()


def test_rate_limited_answer_has_the_error_format():
    a = limits.answer({"scope": "user", "limit": "30 calls per minute", "retry_after": 12})
    assert a["kind"] == "rate_limited" and a["retry_after"] == 12 and "12 seconds" in a["hint"] and a["error"]
    assert "3 minutes" in limits.answer({"scope": "organisation", "limit": "x", "retry_after": 150})["hint"]
    assert "rate_limited" in errors.HINTS and "upgrade" in errors.HINTS


def test_rate_limit_through_mcp_never_touches_the_401_flow(entra, monkeypatch):
    priv = entra[0]
    monkeypatch.setattr(server, "limiter", limits.Limiter([(2, 60)], [(3, 60)]))
    with TestClient(server.build_app()) as client:
        a = tok(priv, oid="alice")
        assert "workspaces" in call(client, a) and "workspaces" in call(client, a, rid=2)
        refused = call(client, a, rid=3)
        assert refused["kind"] == "rate_limited" and refused["retry_after"] >= 1 and "Try again in" in refused["hint"]
        # tools/list and initialize are not limited
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}}, headers={**ACCEPT, "Authorization": f"Bearer {a}"})
        assert r.status_code == 200 and "list_workspaces" in r.text
        # no token, or a bad one: still Claude's 401 with the challenge, limit or no limit
        for headers in ({}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Bearer " + tok(priv, oid="alice")[:-4] + "AAAA"}):
            r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "list_workspaces", "arguments": {}}},
                            headers={**ACCEPT, **headers})
            assert r.status_code == 401 and "resource_metadata=" in r.headers["WWW-Authenticate"]
        # another user of the same organisation has their own bucket until the organisation's is empty
        bob = tok(priv, oid="bob")
        assert "workspaces" in call(client, bob, rid=5)
        assert call(client, bob, rid=6)["kind"] == "rate_limited"                       # org: 3 calls per minute used up
        assert "workspaces" in call(client, tok(priv, oid="carol", tid=OTHER_TID), rid=7)  # another organisation


def test_without_entra_nothing_is_limited(monkeypatch):
    monkeypatch.setattr(server, "limiter", limits.Limiter([(1, 3600)], [(1, 3600)]))
    monkeypatch.setattr(server.auth, "entra", None)
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(server, "_workspaces", lambda headers: [])
    for _ in range(3):
        assert json.loads(server.list_workspaces()) == {"workspaces": []}


# ------------------------------------------------------------------ usage ----------------------

def test_outcome_is_the_top_level_kind_only():
    assert usage.outcome_of('{"workspaces": []}') == "ok"
    assert usage.outcome_of(json.dumps({"error": "x", "kind": "not_found", "hint": "y"})) == "not_found"
    assert usage.outcome_of(json.dumps({"summary": "s", "error": "x", "kind": "consent"})) == "consent"
    assert usage.outcome_of(json.dumps({"nodes": [{"kind": "table"}]})) == "ok"
    assert usage.outcome_of("plain text") == "ok" and usage.outcome_of(None) == "ok"


def test_usage_line_carries_only_the_listed_fields(capsys, monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_USAGE_SALT", raising=False)
    u = usage.Usage()
    line = u.record("plan_backend", "ok", 1.234, None, TID)
    assert line == {"event": "krusgraph.tool_call", "tool": "plan_backend", "outcome": "ok", "ms": 1234}
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", "pepper" * 6)
    line = u.record("create_views", "consent", 0.2, False, TID)
    assert set(line) - {"event"} <= set(usage.FIELDS) and line["dry_run"] is False and len(line["org"]) == 16
    assert TID not in json.dumps(line) and line["org"] == usage.org_hash(TID.upper())         # case does not split an org
    out = capsys.readouterr().out.strip().splitlines()
    assert [json.loads(x)["tool"] for x in out] == ["plan_backend", "create_views"]
    monkeypatch.setenv("KRUSGRAPH_USAGE_LOG", "0")
    u.record("plan_backend", "ok", 0.1)
    assert capsys.readouterr().out == ""


def test_no_content_reaches_the_usage_line_or_metrics(monkeypatch, capsys):
    """Table names, workspace names, the query and the result of real tool calls never appear in what is counted."""
    from fabric_backend import seed
    from fabric_backend.schema import Schema
    fresh = usage.Usage()
    monkeypatch.setattr(usage, "usage", fresh)                      # the module the server's wrapper records into
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda w, h: "ws-secretive")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server, "_resolve_source", lambda ws, src, h: {"type": "Lakehouse", "id": "lh-1", "displayName": src, "sql_host": "h", "sql_db": src})
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: (lambda sql: [{"customer_id": 1, "name": "Harbour Bikes", "country": "DE"}]))
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: seed.schema(schema)))
    server.plan_backend("Confidential Workspace", "secret_lakehouse", schema="shop")
    server.sample_rows("Confidential Workspace", "secret_lakehouse", "customers", schema="shop")
    server.join_path("Confidential Workspace", "secret_lakehouse", "order_items", "categories", schema="shop")
    server.query_graphql("Confidential Workspace", "api", "mutation { deleteEverything }")
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith('{"event":"krusgraph.tool_call"')]
    assert [x["tool"] for x in lines] == ["plan_backend", "sample_rows", "join_path", "query_graphql"]
    assert lines[-1]["outcome"] == "read_only"
    text = json.dumps(lines) + fresh.prometheus()
    for secret in ("Confidential", "secret_lakehouse", "ws-secretive", "customers", "order_items", "categories", "Harbour",
                   "deleteEverything", "shop", "test-only", "sql-token"):
        assert secret not in text, secret


def test_prometheus_text_has_counters_and_a_histogram(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_USAGE_SALT", raising=False)
    monkeypatch.setenv("KRUSGRAPH_USAGE_LOG", "0")
    u = usage.Usage()
    u.record("plan_backend", "ok", 0.3)
    u.record("plan_backend", "not_found", 3.0)
    text = u.prometheus()
    assert 'krusgraph_tool_calls_total{tool="plan_backend",outcome="ok"} 1' in text
    assert 'krusgraph_tool_calls_total{tool="plan_backend",outcome="not_found"} 1' in text
    assert 'krusgraph_tool_duration_seconds_bucket{tool="plan_backend",le="0.5"} 1' in text
    assert 'krusgraph_tool_duration_seconds_bucket{tool="plan_backend",le="+Inf"} 2' in text
    assert 'krusgraph_tool_duration_seconds_count{tool="plan_backend"} 2' in text
    assert "organisations" not in text
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", "s" * 32)
    u.record("plan_backend", "ok", 0.1, None, TID)
    u.record("plan_backend", "ok", 0.1, None, OTHER_TID)
    assert "krusgraph_organisations_seen 2" in u.prometheus() and TID not in u.prometheus()


# ------------------------------------------------------------------ /health and /metrics -------

def test_health_needs_no_sign_in_and_says_nothing_about_the_server(entra, monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_BUILD", "src-abcdef")
    with TestClient(server.build_app()) as client:
        r = client.get("/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"} and r.headers["cache-control"] == "no-store"
        assert client.head("/health").status_code == 200
        assert "Strict-Transport-Security" in r.headers
        assert client.post("/mcp", json={}, headers=ACCEPT).status_code == 401           # the guard is still in front of /mcp
        assert client.get("/healthz").json()["build"] == "src-abcdef"                  # the probes' endpoint is unchanged


def test_metrics_is_off_by_default_and_needs_its_token(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_METRICS_TOKEN", raising=False)
    client = TestClient(server.build_app())
    assert client.get("/metrics").status_code == 404
    monkeypatch.setenv("KRUSGRAPH_METRICS_TOKEN", "too-short")
    assert client.get("/metrics", headers={"Authorization": "Bearer too-short"}).status_code == 404
    token = "m" * 40
    monkeypatch.setenv("KRUSGRAPH_METRICS_TOKEN", token)
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer " + "m" * 39}).status_code == 401
    r = client.get("/metrics", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain") and "krusgraph_uptime_seconds" in r.text
    assert token not in r.text


# ------------------------------------------------------------------ privacy page ---------------

def test_privacy_page_lists_exactly_what_is_counted_and_follows_the_settings(monkeypatch):
    for k in ("KRUSGRAPH_LOG_RETENTION_DAYS", "KRUSGRAPH_USAGE_SALT", "KRUSGRAPH_RATE_LIMITS"):
        monkeypatch.delenv(k, raising=False)
    md = pages.privacy_md()
    assert "{{" not in md and "Usage statistics" in md
    for field in ("`tool`", "`outcome`", "`ms`", "`dry_run`"):
        assert field in md, field
    assert "`org`" not in md and "without a\nlog destination" in md and "deleted after" not in md
    assert "fair-use limits" in md
    monkeypatch.setenv("KRUSGRAPH_LOG_RETENTION_DAYS", "30")
    monkeypatch.setenv("KRUSGRAPH_USAGE_SALT", "x" * 32)
    monkeypatch.setenv("KRUSGRAPH_RATE_LIMITS", "0")
    md = pages.privacy_md()
    assert "`org`" in md and "deleted after 30 days" in md and "no IP address is kept" in md and "without a\nlog destination" not in md
    assert "fair-use limits" not in md and "{{" not in md
    # the page's field list and the code's agree
    assert set(usage.FIELDS) == {"tool", "outcome", "ms", "dry_run", "org"}


# ------------------------------------------------------------------ Key Vault ------------------

class FakeHTTP:
    def __init__(self, kv_status=200, value="kv-secret-value", identity_status=200):
        self.calls = []
        self.kv_status, self.value, self.identity_status = kv_status, value, identity_status

    def __call__(self, url, headers=None, params=None):
        self.calls.append((url, dict(headers or {}), dict(params or {})))
        if url.startswith("http://localhost:42356"):
            return SimpleNamespace(status_code=self.identity_status, json=lambda: {"access_token": "mi-token", "expires_on": "0"})
        return SimpleNamespace(status_code=self.kv_status, json=lambda: {"value": self.value, "id": url})


@pytest.fixture
def identity_env(monkeypatch):
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://localhost:42356/msi/token")
    monkeypatch.setenv("IDENTITY_HEADER", "hdr-123")


def test_key_vault_reader_uses_the_managed_identity_and_caches(identity_env):
    http, now = FakeHTTP(), [0.0]
    r = keyvault.SecretReader("https://kv-test.vault.azure.net/secrets/entra-client-secret", client_id="uami-client", get=http, clock=lambda: now[0])
    assert r.get() == "kv-secret-value" and r.get() == "kv-secret-value"
    (mi_url, mi_headers, mi_params), (kv_url, kv_headers, kv_params) = http.calls
    assert mi_headers == {"X-IDENTITY-HEADER": "hdr-123"}
    assert mi_params == {"resource": "https://vault.azure.net", "api-version": "2019-08-01", "client_id": "uami-client"}
    assert kv_url == "https://kv-test.vault.azure.net/secrets/entra-client-secret" and kv_params == {"api-version": "7.4"}
    assert kv_headers == {"Authorization": "Bearer mi-token"}
    now[0] += keyvault.TTL + 1
    r.get()
    r.get(refresh=True)
    assert len(http.calls) == 6
    assert "kv-secret-value" not in repr(r)


def test_key_vault_errors_say_what_to_fix_and_map_to_server_config(identity_env, monkeypatch):
    r = keyvault.SecretReader("https://kv-test.vault.azure.net/secrets/x", get=FakeHTTP(kv_status=403))
    with pytest.raises(keyvault.KeyVaultError, match="Key Vault Secrets User"):
        r.get()
    with pytest.raises(keyvault.KeyVaultError, match="no such secret"):
        keyvault.SecretReader("https://kv-test.vault.azure.net/secrets/x", get=FakeHTTP(kv_status=404)).get()
    try:
        keyvault.SecretReader("https://kv-test.vault.azure.net/secrets/x", get=FakeHTTP(identity_status=500)).get()
    except keyvault.KeyVaultError as e:
        answer = errors.explain(e)
    assert answer["kind"] == "server_config" and "Key Vault" in answer["error"]
    monkeypatch.delenv("IDENTITY_ENDPOINT")
    with pytest.raises(keyvault.KeyVaultError, match="no managed identity"):
        keyvault.SecretReader("https://kv-test.vault.azure.net/secrets/x", get=FakeHTTP()).get()


@pytest.mark.parametrize("uri", ["http://kv.vault.azure.net/secrets/x", "https://evil.example.com/secrets/x", "https://kv.vault.azure.net/keys/x",
                                 "https://kv.vault.azure.net/secrets", "https://kv.vault.azure.net/secrets/x?api-version=1"])
def test_key_vault_uri_is_checked(uri):
    with pytest.raises(ValueError):
        keyvault.check_uri(uri)


def test_config_reads_the_secret_from_key_vault_when_configured_else_as_before(monkeypatch, identity_env):
    for k in ("MCP_PUBLIC_URL", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_CLIENT_SECRET_KEYVAULT_URI", "ENTRA_REQUIRED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MCP_PUBLIC_URL", CFG.public_url)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CFG.client_id)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "env-secret")
    cfg = EntraConfig.from_env()
    assert cfg.secret() == "env-secret" and cfg.secret_reader is None                       # as before
    monkeypatch.setenv("ENTRA_CLIENT_SECRET_KEYVAULT_URI", "https://kv-test.vault.azure.net/secrets/entra-client-secret")
    monkeypatch.delenv("ENTRA_CLIENT_SECRET")
    cfg = EntraConfig.from_env()
    assert cfg.client_secret == "" and isinstance(cfg.secret_reader, keyvault.SecretReader)
    cfg.secret_reader._get = FakeHTTP()
    assert cfg.secret() == "kv-secret-value" and "kv-secret-value" not in repr(cfg)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "env-secret")                                  # Key Vault wins when both are set
    assert EntraConfig.from_env().client_secret == ""
    monkeypatch.setenv("ENTRA_CLIENT_SECRET_KEYVAULT_URI", "https://example.com/secrets/x")
    with pytest.raises(ValueError):
        EntraConfig.from_env()
    monkeypatch.delenv("ENTRA_CLIENT_SECRET_KEYVAULT_URI")
    monkeypatch.delenv("ENTRA_CLIENT_SECRET")
    with pytest.raises(ValueError, match="KEYVAULT_URI"):
        EntraConfig.from_env()


def test_on_behalf_of_rereads_a_rotated_secret_once(identity_env):
    http = FakeHTTP(value="old-secret")
    reader = keyvault.SecretReader("https://kv-test.vault.azure.net/secrets/s", get=http)
    cfg = EntraConfig(CFG.public_url, CFG.client_id, "", set(), reader)
    sent = []

    def post(url, data):
        sent.append(data["client_secret"])
        if data["client_secret"] == "old-secret":
            raise TokenError("on-behalf-of failed: invalid_client — AADSTS7000215: Invalid client secret provided.")
        return {"access_token": "fabric-token", "expires_in": 3600}

    o = OnBehalfOf(cfg, post=post)
    http.value = "new-secret"                      # rotated in Key Vault after the server read the old one
    reader._value, reader._read_at = "old-secret", reader.clock()
    assert o.token("user-token", TID, "scope") == "fabric-token" and sent == ["old-secret", "new-secret"]
    # another failure is not retried, and a config without Key Vault is not retried either
    o2 = OnBehalfOf(EntraConfig(CFG.public_url, CFG.client_id, "old-secret"), post=post)
    with pytest.raises(TokenError):
        o2.token("user-token-2", TID, "scope")


# ------------------------------------------------------------------ entitlements ---------------

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
    monkeypatch.setattr(server, "_identity", lambda ctx: {"oid": "u", "tid": TID})
    return ran


def test_entitlements_off_changes_nothing(shop, monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_ENTITLEMENTS", raising=False)
    monkeypatch.setattr(entitlements, "check", lambda *a, **k: pytest.fail("the check must not run while the flag is off"))
    assert entitlements.enabled() is False
    out = json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and shop                                     # the paid feature ran
    monkeypatch.setenv("KRUSGRAPH_ENTITLEMENTS", "0")
    assert "error" not in json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))


def test_entitlements_on_refuses_paid_features_with_upgrade_but_dry_runs_stay_free(shop, monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_ENTITLEMENTS", "1")
    monkeypatch.setenv("KRUSGRAPH_ENTITLEMENTS_SOURCE", "env")
    monkeypatch.setenv("KRUSGRAPH_ENTITLED_TENANTS", json.dumps({OTHER_TID: ["create"]}))
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.example/mcp")
    out = json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))
    assert out["kind"] == "upgrade" and out["feature"] == "create" and "https://krusgraph.example/pricing" in out["hint"]
    assert "dry_run=true" in out["hint"] and not shop                                      # nothing ran
    dry = json.loads(server.create_views("Sales", "shop_lh", schema="shop"))
    assert dry["dry_run"] is True and "error" not in dry
    assert "error" not in json.loads(server.plan_backend("Sales", "shop_lh", schema="shop"))   # read-only tools are free
    monkeypatch.setenv("KRUSGRAPH_ENTITLED_TENANTS", json.dumps({TID.upper(): "create,lineage"}))
    assert json.loads(server.create_views("Sales", "shop_lh", schema="shop", dry_run=False))["result"]["status"] == "Succeeded"
    monkeypatch.setenv("KRUSGRAPH_UPGRADE_URL", "https://pay.example/plans")
    monkeypatch.setenv("KRUSGRAPH_ENTITLED_TENANTS", "{}")
    out = json.loads(server.lineage("Sales", "shop_lh", schema="shop"))
    assert out["kind"] == "upgrade" and out["feature"] == "lineage" and "https://pay.example/plans" in out["hint"]
    monkeypatch.setenv("KRUSGRAPH_ENTITLED_TENANTS", json.dumps({TID: ["*"]}))
    assert "kind" not in json.loads(server.lineage("Sales", "shop_lh", schema="shop")) or \
        json.loads(server.lineage("Sales", "shop_lh", schema="shop"))["kind"] != "upgrade"


def test_feature_map_matches_the_pricing_notes():
    assert entitlements.feature_of("create_backend", False) is None                       # the free tier's one API
    assert entitlements.feature_of("create_views", True) is None and entitlements.feature_of("create_views", False) == "create"
    assert entitlements.feature_of("lineage", None) == "lineage"
    assert entitlements.feature_of("drift_monitor_draft", None) == "drift_monitor"
    assert entitlements.feature_of("plan_drift", None) is None and entitlements.feature_of("plan_backend", None) is None
    notes = (Path(__file__).resolve().parents[1] / "docs" / "PRICING-NOTES.md").read_text(encoding="utf-8")
    assert "KRUSGRAPH_ENTITLEMENTS" in notes and "kind: upgrade" in notes
    for tools in entitlements.FEATURES.values():
        for t in tools:
            assert f"`{t}`" in notes, t


def test_table_source_reads_one_entity_and_denies_on_failure(monkeypatch):
    seen = []

    def get(url, headers=None, params=None):
        seen.append((url, headers))
        if "RowKey='" + TID + "'" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"PartitionKey": "tenant", "RowKey": TID, "features": "create, lineage"})
        if "broken" in url:
            return SimpleNamespace(status_code=500, json=lambda: {})
        return SimpleNamespace(status_code=404, json=lambda: {})

    src = entitlements.TableSource("https://acct.table.core.windows.net/entitlements", get=get, token=lambda: "st-token")
    assert src.features(TID) == {"create", "lineage"} and src.features(TID) == {"create", "lineage"}
    assert len(seen) == 1                                                          # cached
    url, headers = seen[0]
    assert url == f"https://acct.table.core.windows.net/entitlements(PartitionKey='tenant',RowKey='{TID}')"
    assert headers["Authorization"] == "Bearer st-token" and headers["x-ms-version"] == "2019-02-02"
    assert src.features(OTHER_TID) == set()
    with pytest.raises(LookupError):
        src.features("broken")
    monkeypatch.setattr(entitlements, "source", lambda: src)
    out = entitlements.check("lineage", None, "broken")
    assert out["kind"] == "upgrade" and "could not be read" in out["error"]
    with pytest.raises(ValueError):
        entitlements.TableSource("https://acct.table.core.windows.net/")


# ------------------------------------------------------------------ deploy: --key-vault --------

from deploy import azure_containerapp as d  # noqa: E402

_CONFIG_FILE = next(p for p in (d.ROOT / "deploy/krusgraph.json", d.ROOT / "deploy/krusgraph.example.json") if p.exists())
CONFIG = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))


class FakeVaultAzure:
    def __init__(self, vault_exists=False, forbidden_first=0):
        self.calls, self.secret = [], ""
        self.vault = {"id": "kv-id", "tags": dict(d.OWNER_TAG), "properties": {"enableRbacAuthorization": True}} if vault_exists else None
        self.forbidden = forbidden_first
        self.roles: list = []
        self.written = None

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] == ("containerapp", "show"):
            return {"id": "app-id", "tags": dict(d.OWNER_TAG), "properties": {"configuration": {"ingress": {"fqdn": "app.test"}}}}
        if args[:2] == ("identity", "show"):
            return {"id": "identity-id", "principalId": "identity-principal", "clientId": "identity-client-id"}
        if args[0] == "provider":
            return {"registrationState": "Registered"}
        if args[:2] == ("keyvault", "show"):
            return self.vault
        if args[:2] == ("keyvault", "create"):
            assert args[args.index("--enable-rbac-authorization") + 1] == "true"
            self.vault = {"id": "kv-id", "tags": dict(d.OWNER_TAG), "properties": {"enableRbacAuthorization": True}}
            return self.vault
        if args[:3] == ("ad", "signed-in-user", "show"):
            return {"id": "me-id"}
        if args[:3] == ("role", "assignment", "list"):
            return [r for r in self.roles if r["principalId"] == args[args.index("--assignee") + 1]]
        if args[:3] == ("role", "assignment", "create"):
            self.roles.append({"principalId": args[args.index("--assignee-object-id") + 1], "roleDefinitionName": args[args.index("--role") + 1]})
            return None
        if args[:3] == ("keyvault", "secret", "set"):
            if self.forbidden:
                self.forbidden -= 1
                raise d.DeploymentError("(Forbidden) Caller is not authorized")
            self.written = Path(args[args.index("--file") + 1]).read_text(encoding="utf-8")
            return None
        if args[:2] == ("containerapp", "update"):
            return None
        pytest.fail(f"--key-vault must not run: {args}")


def test_key_vault_step_creates_grants_stores_and_points_the_app(monkeypatch, tmp_path):
    az = FakeVaultAzure(forbidden_first=1)
    monkeypatch.setattr(d, "report", lambda *a, **k: None)
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "test-secret")
    d.move_secret_to_key_vault(az, CONFIG | {"key_vault": "kv-krusgraph-test"})
    assert az.written == "test-secret"
    assert all("test-secret" not in " ".join(map(str, c)) for c in az.calls)               # never in a process argument
    secret_file = Path(next(c for c in az.calls if c[:3] == ("keyvault", "secret", "set"))[-3])
    assert not secret_file.exists()
    assert {(r["principalId"], r["roleDefinitionName"]) for r in az.roles} == {("me-id", "Key Vault Secrets Officer"),
                                                                               ("identity-principal", "Key Vault Secrets User")}
    update = next(c for c in az.calls if c[:2] == ("containerapp", "update"))
    env = update[update.index("--set-env-vars") + 1:]
    assert "ENTRA_CLIENT_SECRET_KEYVAULT_URI=https://kv-krusgraph-test.vault.azure.net/secrets/entra-client-secret" in env
    assert "AZURE_CLIENT_ID=identity-client-id" in env
    assert not any(c[:3] in (("containerapp", "secret", "remove"),) or "--remove-env-vars" in c for c in az.calls)   # nothing deleted
    keyvault.check_uri(d.key_vault_uri(CONFIG | {"key_vault": "kv-krusgraph-test"}))       # the server accepts what the script sets
    # a rerun creates nothing new
    before = len(az.roles)
    d.move_secret_to_key_vault(az, CONFIG | {"key_vault": "kv-krusgraph-test"})
    assert len(az.roles) == before and sum(c[:2] == ("keyvault", "create") for c in az.calls) == 1


def test_key_vault_step_refuses_without_a_name_or_a_vault_that_is_not_ours(monkeypatch):
    with pytest.raises(d.DeploymentError, match="key_vault"):
        d.move_secret_to_key_vault(FakeVaultAzure(), CONFIG | {"key_vault": ""})
    az = FakeVaultAzure(vault_exists=True)
    az.vault["tags"] = {"managed-by": "someone-else"}
    with pytest.raises(d.DeploymentError, match="tillhör inte"):
        d.move_secret_to_key_vault(az, CONFIG | {"key_vault": "kv-shared"})


def test_plain_env_carries_key_vault_and_log_retention_only_when_configured():
    env = d.plain_env(CONFIG)
    assert not any(k.startswith(("ENTRA_CLIENT_SECRET", "AZURE_CLIENT_ID", "KRUSGRAPH_LOG", "KRUSGRAPH_ACCESS")) for k in env)
    env = d.plain_env(CONFIG | {"key_vault": "kv-x", "log_retention_days": 30}, identity_client_id="cid")
    assert env["ENTRA_CLIENT_SECRET_KEYVAULT_URI"] == "https://kv-x.vault.azure.net/secrets/entra-client-secret" and env["AZURE_CLIENT_ID"] == "cid"
    assert env["KRUSGRAPH_LOG_RETENTION_DAYS"] == "30" and env["KRUSGRAPH_ACCESS_LOG"] == "0"


def test_cli_dispatches_the_key_vault_flag(monkeypatch):
    called = []
    monkeypatch.setattr(d, "move_secret_to_key_vault", lambda *a, **k: called.append("kv"))
    monkeypatch.setattr(d.Azure, "check_context", lambda self: called.append("check_context"))
    monkeypatch.setattr(d.sys, "argv", ["azure_containerapp.py", "--config", str(_CONFIG_FILE), "--key-vault"])
    d.main()
    assert called == ["check_context", "kv"]


def test_operations_doc_has_the_commands_in_order():
    doc = (Path(__file__).resolve().parents[1] / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")
    order = ["--update", "--key-vault", "--remove-env-vars ENTRA_CLIENT_SECRET", "log_retention_days", "log-analytics workspace create",
             "--logs-destination log-analytics", "KRUSGRAPH_USAGE_SALT=secretref", "KRUSGRAPH_METRICS_TOKEN=secretref",
             "action-group create", "statusCodeCategory includes 5xx", "web-test create", "availabilityPercentage < 50"]
    positions = [doc.index(x) for x in order]
    assert positions == sorted(positions)
    assert "/health" in doc and "unit-tested" in doc
