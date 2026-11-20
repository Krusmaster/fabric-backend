"""Round n176: Krusgraph.Modeler, the permanent workload name, for up to 20 selected tenants.

The package names (Org.Krusgraph, Krusgraph.Modeler, every other name refused) are tested in
tests/test_workload_package_names.py, which needs no server extras (WP1). The server accepts tokens for every URI in
KRUSGRAPH_WORKLOAD_APP_ID_URI (a comma list while both names run) and gives a tenant outside the allowed list a plain
refusal, not a sign-in loop. The pilot page renders and lists the administrator's steps in order. Docs and site only
describe; nothing here uploads, consents or calls Entra or Fabric."""
import json
import re
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WL_ID = "99999999-8888-7777-6666-555555555555"


# The package-name tests (n176) are in tests/test_workload_package_names.py (WP1): they need no server extras.

# ------------------------------------------------------------------ the server: both URIs, allowed tenants -----------

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import entra, server, workload_api, workload_host  # noqa: E402
from fabric_backend.entra import EntraConfig, TenantNotAllowed, TokenError, Validator, WorkloadConfig  # noqa: E402

TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER = "12121212-3434-5656-7878-909090909090"
DEV_URI = "https://krusgraph.com/workload/workload/Org.Krusgraph"
PUB_URI = "https://krusgraph.com/workload/workload/Krusgraph.Modeler"
ENV = {"KRUSGRAPH_WORKLOAD_CLIENT_ID": WL_ID, "KRUSGRAPH_WORKLOAD_CLIENT_SECRET": "wl-secret",
       "KRUSGRAPH_WORKLOAD_APP_ID_URI": f"{DEV_URI}, {PUB_URI}/", "KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS": f" {TID.upper()} "}


class FakeJWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key})()


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def tok(priv, tid=TID, **over):
    claims = {"aud": PUB_URI, "iss": f"https://login.microsoftonline.com/{tid}/v2.0", "tid": tid,
              "exp": int(time.time()) + 600, "scp": "user_impersonation", "oid": "user-1"}
    claims.update(over)
    return jwt.encode(claims, priv, algorithm="RS256")


@pytest.fixture
def cfg(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    return WorkloadConfig.from_env()


def test_the_app_id_uri_setting_is_a_list(cfg):
    assert cfg.app_id_uris == [DEV_URI, PUB_URI] and cfg.app_id_uri == DEV_URI         # the first stays the primary one
    assert cfg.audiences == [DEV_URI, PUB_URI, WL_ID, f"api://{WL_ID}"]
    assert cfg.allowed_tenants == {TID}
    assert entra.split_uris(f"{PUB_URI} {PUB_URI}/,,{DEV_URI}") == [PUB_URI, DEV_URI]
    one = WorkloadConfig(WL_ID, "s", DEV_URI + "/")                                    # the one-URI form is unchanged
    assert one.app_id_uris == [DEV_URI] and one.app_id_uri == DEV_URI


def test_both_audiences_are_accepted_and_no_other(keys, cfg):
    priv, pub = keys
    v = Validator(cfg, FakeJWKS(pub))
    for aud in (DEV_URI, PUB_URI, WL_ID):
        assert v.validate(tok(priv, aud=aud))["tid"] == TID
    for aud in ("https://krusgraph.com/workload/workload/Krusgraph.Other", "https://krusgraph.com/mcp", "api://someone-else"):
        with pytest.raises(TokenError) as e:
            v.validate(tok(priv, aud=aud))
        assert not isinstance(e.value, TenantNotAllowed)


def test_the_mcp_app_cannot_hide_in_the_list(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_APP_ID_URI", f"{PUB_URI},https://krusgraph.com/mcp")
    with pytest.raises(ValueError, match="own Entra app"):
        WorkloadConfig.from_env(EntraConfig("https://krusgraph.com/mcp", "11111111-2222-3333-4444-555555555555", "x"))
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_APP_ID_URI", " , ")
    with pytest.raises(ValueError, match="names no URI"):
        WorkloadConfig.from_env()


def test_a_tenant_outside_the_list_gets_a_plain_refusal(keys, cfg, monkeypatch):
    from starlette.applications import Starlette
    priv, pub = keys
    v = Validator(cfg, FakeJWKS(pub))
    with pytest.raises(TenantNotAllowed) as e:
        v.validate(tok(priv, tid=OTHER))
    assert e.value.tenant == OTHER and isinstance(e.value, TokenError)                # /mcp still treats it as before
    monkeypatch.setattr(server, "limiter", None)

    class NoOBO:
        def token(self, *a):
            raise AssertionError("no exchange for a refused tenant")

    c = TestClient(Starlette(routes=workload_api.routes(cfg, v, NoOBO())))
    r = c.post(workload_api.PREFIX + "/review", json={}, headers={"Authorization": f"Bearer {tok(priv, tid=OTHER)}",
                                                                   "Origin": "https://app.fabric.microsoft.com"})
    assert r.status_code == 403 and "www-authenticate" not in r.headers                 # not a sign-in prompt
    body = r.json()
    assert body["kind"] == "tenant_not_allowed" and body["tenant"] == OTHER
    assert body["error"] == "Krusgraph is not turned on for your organisation yet."
    assert OTHER in body["hint"] and "/pilot/fabric" in body["hint"] and "Nothing was read or changed" in body["hint"]
    assert TID not in json.dumps(body)                                                  # never names another tenant
    r = c.post(workload_api.PREFIX + "/review", json={}, headers={"Authorization": f"Bearer {tok(priv, aud='api://x')}",
                                                                   "Origin": "https://app.fabric.microsoft.com"})
    assert r.status_code == 401 and r.json()["kind"] == "sign_in"                      # a bad token is still a sign-in


def test_the_editor_page_lists_every_scope(monkeypatch, tmp_path):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert workload_host.engine_scopes() == [f"{DEV_URI}/user_impersonation", f"{PUB_URI}/user_impersonation"]
    assert workload_host.engine_scope() == f"{DEV_URI}/user_impersonation"
    (tmp_path / "index.html").write_text("<html><head><title>x</title></head><body></body></html>", encoding="utf-8")
    page = workload_host.Editor(tmp_path).index().decode()
    assert f'<meta name="krusgraph-engine-scope" content="{DEV_URI}/user_impersonation">' in page
    assert (f'<meta name="krusgraph-engine-scopes" content="{DEV_URI}/user_impersonation {PUB_URI}/user_impersonation">'
            in page)


# ------------------------------------------------------------------ the pilot page and the docs ----------------------

@pytest.fixture
def site(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


STEPS = ["tenant-id", "tenant-setting", "consent", "network", "new-item"]


def test_the_pilot_page_lists_the_steps_in_order(site):
    r = site.get("/pilot/fabric")
    assert r.status_code == 200
    page = r.text
    positions = [page.index(f'id="{s}"') for s in STEPS]
    assert positions == sorted(positions)
    for words in ("Users can see and work with additional workloads not validated by Microsoft",
                  "adminconsent?client_id=853a0cf0-7d35-42b7-b384-26178755a72a", "&lt;your tenant id&gt;",
                  "<code>krusgraph.com</code>", "<code>workload.krusgraph.com</code>", "port 443",
                  "+ New item → Krusgraph Model", "synthetic", "not affiliated with Microsoft", "hello@krusgraph.test"):
        assert words in page, words
    assert '<a href="/pilot/fabric">' in site.get("/partners").text


def test_the_pilot_page_and_docs_make_no_speed_or_compliance_claims(site):
    texts = [re.sub(r"<[^>]+>", " ", site.get("/pilot/fabric").text.split("<main", 1)[-1].split("<footer", 1)[0]),
             (ROOT / "docs/PILOT-ONBOARDING.md").read_text(encoding="utf-8")]
    banned = ("faster", "minutes to", "in seconds", "compliant", "gdpr", "iso 27001", "certified", "secure by", "seamless",
              "effortless", "guarantee", "endorsed", "partner of microsoft", "validated by microsoft.")
    for text in texts:
        low = text.lower()
        for word in banned:
            assert word not in low, word
    pilot_ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", " ".join(texts))
    assert set(pilot_ids) <= {"853a0cf0-7d35-42b7-b384-26178755a72a"}                  # the app id only, no tenant ids


def test_the_publish_doc_has_the_founders_steps_in_order():
    doc = (ROOT / "docs/WORKLOAD-PUBLISH.md").read_text(encoding="utf-8")
    # n195: the runbook's steps 0-8 first (tests/test_n195_attestation.py), n176's detail after them as A1-A4
    order = ["## Step 1. The name-registration blocker", "## Step 2. Publisher verification", "## Step 3. Upload Krusgraph.Modeler",
             "## Step 4. Microsoft's test tenant", "## Step 8. The submission form", "## A1. Entra", "## A2. The server",
             "## A3. Upload Krusgraph.Modeler", "## A4. Publish", "## Adding the next pilot", "## Withdrawing", "## Decision"]
    at = [doc.index(h) for h in order]
    assert at == sorted(at)
    for words in ("Confirm workload Name", "cannot be undone", "Selected tenants", "--name Krusgraph.Modeler",
                  "https://krusgraph.com/workload/workload/Krusgraph.Modeler", "workloadSignIn/$TENANT/Krusgraph.Modeler",
                  "msit.fabric.microsoft.com", "workload_allowed_tenants", "not turned on for your organisation yet",
                  "Recommendation: keep the existing app"):
        assert words in doc, words
    assert doc.count("**Check on first run") + doc.count("check on first run") >= 5
    # the az lines keep what is there: the current lists are read and added to, never replaced from scratch
    assert '--query "spa.redirectUris[]"' in doc and '--query "identifierUris[]"' in doc


def test_contributing_names_the_one_allowed_krusgraph_name():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Krusgraph.Modeler" in text and "docs/WORKLOAD-PUBLISH.md" in text
