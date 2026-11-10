"""Round n204: the Marketplace landing page accepts personal Microsoft accounts as well as work accounts.

With KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID set, the buyer signs in through /common with that separate app (openid profile
email); unset, through /organizations with the site's app (openid profile), as before. A personal account's ID token
(tenant 9188040d-6c67-4c5b-b112-36a304b66dad) and a work account's are both accepted, a token for another app is not; the
subscription is resolved, shown and activated the same way for both, the beneficiary tenant coming from resolve. The
landing page's cookies are signed. No secret in code, in a repr or in the log. Throw-away keys and fake HTTP only."""
import logging
import re
import subprocess
import time
from pathlib import Path

import pytest

jwt = pytest.importorskip("jwt")
from starlette.applications import Starlette  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import marketplace as mp, server  # noqa: E402
from test_marketplace import (APP_ID, BUYER_TID, CFG, ENTRA, OTHER_TID, OUR_TID, SITE_APP, SUB, FakeAPI, FakeJWKS,  # noqa: E402
                              priv, subscription)
from fabric_backend.marketplace import Subscriptions, MemoryStore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SIGNIN_APP = "88888888-0000-0000-0000-000000000008"
SIGNIN_SECRET = "signin-secret-value-n204"
PERSONAL = mp.MSA_TENANT
assert priv  # the fixture, imported for the tests below


def signin_cfg():
    return mp.SignInConfig(SIGNIN_APP, SIGNIN_SECRET)


def query(url: str) -> dict:
    from urllib.parse import parse_qsl, urlsplit
    return dict(parse_qsl(urlsplit(url).query))


class FakeEntra(FakeAPI):
    """FakeAPI plus Entra's authorization-code redemption, answering with an ID token for the sign-in app."""

    def __init__(self, key, tid, aud=SIGNIN_APP):
        super().__init__()
        self.key, self.tid, self.aud, self.redeemed = key, tid, aud, []

    def __call__(self, method, url, **kw):
        if "/oauth2/v2.0/token" in url and kw.get("data", {}).get("grant_type") == "authorization_code":
            self.redeemed.append((url, dict(kw["data"])))
            return self.reply_token()
        return super().__call__(method, url, **kw)

    def reply_token(self):
        from types import SimpleNamespace
        now = int(time.time())
        claims = {"aud": self.aud, "iss": f"https://login.microsoftonline.com/{self.tid}/v2.0", "tid": self.tid,
                  "nonce": self.nonce, "exp": now + 600, "iat": now, "oid": "u-1", "email": "someone@example.invalid"}
        body = {"id_token": jwt.encode(claims, self.key, algorithm="RS256")}
        return SimpleNamespace(status_code=200, json=lambda: body, headers={})


def app_with(api, subs, signin, monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://testserver/mcp")
    routes = mp.routes(ENTRA, fulfilment=mp.Fulfilment(CFG, http=api), validator=mp.WebhookValidator(CFG, jwks_client=object()),
                       subs=subs, signin=signin)
    return TestClient(Starlette(routes=routes), base_url="https://testserver")


def sign_in(c, api, token):
    """Landing -> Entra (the redirect) -> callback, with the nonce the landing page chose."""
    loc = c.get("/marketplace/landing", params={"token": token}, follow_redirects=False).headers["location"]
    q = query(loc)
    api.nonce = q["nonce"]
    return loc, c.get("/marketplace/callback", params={"code": "c0de", "state": q["state"]})


# ------------------------------------------------------------------ the sign-in URL --------------------------------

def test_sign_in_url_uses_common_and_the_new_app_when_set(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID", SIGNIN_APP)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET", SIGNIN_SECRET)
    monkeypatch.setenv("ENTRA_CLIENT_ID", SITE_APP)
    api = FakeAPI()
    api.subs["mt-1"] = subscription()
    c = app_with(api, Subscriptions(MemoryStore()), None, monkeypatch)
    loc = c.get("/marketplace/landing", params={"token": "mt-1"}, follow_redirects=False).headers["location"]
    assert loc.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?")
    q = query(loc)
    assert q["client_id"] == SIGNIN_APP and q["scope"] == "openid profile email" and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "https://testserver/marketplace/callback" and "mt-1" not in loc and SIGNIN_SECRET not in loc


def test_sign_in_url_keeps_organizations_and_the_site_app_when_unset(monkeypatch):
    monkeypatch.delenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID", raising=False)
    api = FakeAPI()
    api.subs["mt-1"] = subscription()
    c = app_with(api, Subscriptions(MemoryStore()), None, monkeypatch)
    loc = c.get("/marketplace/landing", params={"token": "mt-1"}, follow_redirects=False).headers["location"]
    assert loc.startswith("https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?")
    q = query(loc)
    assert q["client_id"] == SITE_APP and q["scope"] == "openid profile"


def test_signin_config_from_env(monkeypatch):
    for k in ("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID", "KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET",
              "KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET_KEYVAULT_URI"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ENTRA_CLIENT_ID", SITE_APP)
    assert mp.SignInConfig.from_env() is None
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID", SIGNIN_APP)
    with pytest.raises(ValueError, match="KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET"):
        mp.SignInConfig.from_env()
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET", SIGNIN_SECRET)
    got = mp.SignInConfig.from_env()
    assert got.client_id == SIGNIN_APP and got.secret() == SIGNIN_SECRET and SIGNIN_SECRET not in repr(got)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID", SITE_APP)             # never the main app
    with pytest.raises(ValueError, match="separate sign-in app"):
        mp.SignInConfig.from_env()
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID", "not-a-guid")
    with pytest.raises(ValueError, match="GUID"):
        mp.SignInConfig.from_env()


def test_server_refuses_to_start_with_the_sign_in_id_and_no_secret(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE", "1")
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_TENANT_ID", OUR_TID)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_CLIENT_ID", APP_ID)
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_CLIENT_SECRET", "x")
    monkeypatch.setenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID", SIGNIN_APP)
    monkeypatch.delenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET_KEYVAULT_URI", raising=False)
    with pytest.raises(ValueError, match="KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET"):
        server.build_app()


# ------------------------------------------------------------------ the ID token -----------------------------------

def id_token(priv, tid, aud=SIGNIN_APP, iss=None, nonce="n1"):
    now = int(time.time())
    return jwt.encode({"aud": aud, "iss": iss or f"https://login.microsoftonline.com/{tid}/v2.0", "tid": tid, "nonce": nonce,
                       "exp": now + 600, "iat": now}, priv, algorithm="RS256")


def test_personal_and_work_id_tokens_are_accepted_another_app_is_refused(priv):
    s = mp.SignIn.for_landing(ENTRA, signin_cfg(), jwks_client=FakeJWKS(priv.public_key()))
    assert s.tenant == "common" and s.scope == "openid profile email"
    assert s.validate_id_token(id_token(priv, PERSONAL), "n1")["tid"] == PERSONAL
    assert s.validate_id_token(id_token(priv, BUYER_TID), "n1")["tid"] == BUYER_TID
    for bad in (id_token(priv, PERSONAL, aud=SITE_APP),                   # the site's app, not this one
                id_token(priv, BUYER_TID, aud=APP_ID),                    # the fulfilment app
                id_token(priv, PERSONAL, iss=f"https://login.microsoftonline.com/{BUYER_TID}/v2.0"),   # issuer of another tenant
                id_token(priv, PERSONAL, iss="https://login.microsoftonline.com/common/v2.0"),
                id_token(priv, PERSONAL, iss=f"https://sts.windows.net/{PERSONAL}/"),                 # v1.0 form: not an ID token here
                id_token(priv, BUYER_TID, nonce="other")):
        with pytest.raises(mp.MarketplaceError):
            s.validate_id_token(bad, "n1")


def test_the_site_app_through_organizations_refuses_a_personal_account(priv):
    s = mp.SignIn.for_landing(ENTRA, None, jwks_client=FakeJWKS(priv.public_key()))
    assert s.tenant == "organizations" and s.scope == "openid profile"
    assert s.validate_id_token(id_token(priv, BUYER_TID, aud=SITE_APP), "n1")["tid"] == BUYER_TID
    with pytest.raises(mp.MarketplaceError, match="personal"):
        s.validate_id_token(id_token(priv, PERSONAL, aud=SITE_APP), "n1")


# ------------------------------------------------------------------ the activation path ----------------------------

def run_flow(priv, monkeypatch, tid):
    api = FakeEntra(priv, tid)
    api.subs["mt-1"] = subscription()
    subs = Subscriptions(MemoryStore())
    signin = mp.SignIn.for_landing(ENTRA, signin_cfg(), http=api, jwks_client=FakeJWKS(priv.public_key()))
    c = app_with(api, subs, signin, monkeypatch)
    _, page = sign_in(c, api, "mt-1")
    assert page.status_code == 200, page.text
    csrf = page.text.split('name="csrf" value="', 1)[1].split('"', 1)[0]
    done = c.post("/marketplace/activate", data={"csrf": csrf}, headers={"Origin": "https://testserver"})
    calls = [(m, u.split("?")[0].replace("https://marketplaceapi.microsoft.com/api/saas", "")) for m, u, _ in api.calls
             if "marketplaceapi" in u]
    return api, subs, page, done, calls


def test_activation_path_is_the_same_for_a_personal_and_a_work_account(priv, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    work = run_flow(priv, monkeypatch, BUYER_TID)
    personal = run_flow(priv, monkeypatch, PERSONAL)
    for api, subs, page, done, calls in (work, personal):
        url, data = api.redeemed[0]
        assert url == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        assert data["client_id"] == SIGNIN_APP and data["scope"] == "openid profile email"
        for shown in ("krusgraph-dev", "team", BUYER_TID, "PendingFulfillmentStart", "Activate the subscription"):
            assert shown in page.text
        assert done.status_code == 200 and "Activated" in done.text
        assert subs.active(BUYER_TID) and not subs.tenant(PERSONAL, cached=False)   # the beneficiary is from resolve
    assert work[4] == personal[4]                                                     # the same fulfilment calls
    assert [c for c in work[4] if c[1].endswith("/activate")] == [("POST", f"/subscriptions/{SUB}/activate")]
    assert "personal-account" not in work[2].text
    note = personal[2].text
    assert "personal Microsoft account" in note and "work account" in note and BUYER_TID in note
    assert f"https://login.microsoftonline.com/{BUYER_TID}/adminconsent?client_id={SITE_APP}" in note
    assert "personal Microsoft account" in personal[3].text and "another organisation" not in note
    log = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("krusgraph"))
    for secret in (SIGNIN_SECRET, "fulfilment-secret-value", "site-secret-value", "mt-1", "someone@example.invalid", "c0de"):
        assert secret not in log
    assert "personal account" in log and "work account" in log


def test_a_third_organisation_still_cannot_activate(priv, monkeypatch):
    api = FakeEntra(priv, OTHER_TID)
    api.subs["mt-1"] = subscription()
    signin = mp.SignIn.for_landing(ENTRA, signin_cfg(), http=api, jwks_client=FakeJWKS(priv.public_key()))
    c = app_with(api, Subscriptions(MemoryStore()), signin, monkeypatch)
    _, page = sign_in(c, api, "mt-1")
    assert "another organisation" in page.text and "Activate the subscription" not in page.text


def test_a_hand_made_cookie_is_refused(priv, monkeypatch):
    """The session cookie is signed: another subscription id or tenant in a cookie made by hand is not activated."""
    api = FakeEntra(priv, OTHER_TID)
    api.subs["mt-1"] = subscription()
    c = app_with(api, Subscriptions(MemoryStore()), None, monkeypatch)
    forged = mp._b64({"sub": SUB, "csrf": "x", "tid": BUYER_TID, "at": int(time.time())})
    c.cookies.set(mp.SESSION_COOKIE, forged + ".AAAA", domain="testserver")
    r = c.post("/marketplace/activate", data={"csrf": "x"})
    assert r.status_code == 400 and not any(u.split("?")[0].endswith("/activate") for _, u, _ in api.calls)
    key = b"wrong key"
    c.cookies.set(mp.SESSION_COOKIE, mp._seal({"sub": SUB, "csrf": "x", "tid": BUYER_TID, "at": int(time.time())}, key),
                  domain="testserver")
    assert c.post("/marketplace/activate", data={"csrf": "x"}).status_code == 400


# ------------------------------------------------------------------ scopes and secrets -----------------------------

def test_activation_asks_for_nothing_beyond_openid_profile_email():
    """Policy 1000.3: during activation, Microsoft Graph at most with User.Read; here no Graph call at all."""
    text = (ROOT / "fabric_backend" / "marketplace.py").read_text(encoding="utf-8")
    assert "graph.microsoft.com" not in text
    scopes = set(re.findall(r'"scope":\s*([^,}\n]+)', text))
    assert scopes <= {"self.scope", "SAAS_SCOPE"}, scopes                 # the user's scopes, and the app-only SaaS scope
    assert mp.SIGNIN_SCOPE_COMMON == "openid profile email" and mp.SIGNIN_SCOPE_SITE == "openid profile"


def test_no_client_secret_in_the_repository():
    """An Entra client secret has a recognisable shape (three characters, a digit, 'Q~'); none is committed."""
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    shape = re.compile(r"[A-Za-z0-9_\-.]{3}\dQ~[A-Za-z0-9_~.\-]{31,34}")
    hits = []
    for name in files:
        p = ROOT / name
        if p.suffix in {".png", ".jpg", ".mp4", ".webm", ".ico", ".woff2", ".zip", ".pdf", ".gif", ".webp"} or not p.is_file():
            continue
        try:
            if shape.search(p.read_text(encoding="utf-8", errors="ignore")):
                hits.append(name)
        except OSError:
            continue
    assert hits == []


def test_the_access_log_line_keeps_the_path_and_drops_the_purchase_token():
    mp.hide_query_in_access_log()
    access = logging.getLogger("uvicorn.access")
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("203.0.113.9:1", "GET", "/marketplace/landing?token=secret-purchase-token", "1.1", 302), None)
    assert all(f.filter(record) for f in access.filters)
    assert "secret-purchase-token" not in record.getMessage() and "/marketplace/landing" in record.getMessage()
    other = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                              ("203.0.113.9:1", "GET", "/docs?x=1", "1.1", 200), None)
    assert all(f.filter(other) for f in access.filters) and "/docs?x=1" in other.getMessage()


# ------------------------------------------------------------------ deploy ----------------------------------------

def test_deploy_wires_the_sign_in_app_like_the_other_marketplace_settings(capsys, monkeypatch):
    from deploy import azure_containerapp as d
    from tests.test_deploy_workload import CONFIG, FakeApp
    import json
    example = json.loads((ROOT / "deploy" / "krusgraph.example.json").read_text(encoding="utf-8"))
    assert example["marketplace_signin_client_id"] == "" and example["marketplace_signin_secret_keyvault_uri"] == ""
    assert d.MARKETPLACE_ENV["marketplace_signin_client_id"] == "KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID"
    on = CONFIG | {"marketplace": True, "marketplace_tenant_id": OUR_TID, "marketplace_client_id": APP_ID,
                   "marketplace_secret_keyvault_uri": "https://kv.vault.azure.net/secrets/mp"}
    # unset: the checklist says personal accounts cannot sign in yet, and names the site's app's redirect URI
    assert d.update(FakeApp(env={}), on, dry_run=True) is None
    out = capsys.readouterr().out
    assert "saknas KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID" in out and "personligt Microsoft-konto" in out
    # set, no secret anywhere: --update stops and says how to store it hidden
    with pytest.raises(d.DeploymentError, match="marketplace-signin-secret"):
        d.update(FakeApp(env={}), on | {"marketplace_signin_client_id": SIGNIN_APP})
    capsys.readouterr()
    # set, with the container-app secret: the variable points at it, never a value
    app = FakeApp(env={})
    app.app["properties"]["configuration"]["secrets"].append({"name": "marketplace-signin-secret"})
    assert d.update(app, on | {"marketplace_signin_client_id": SIGNIN_APP}, dry_run=True) is None
    out = capsys.readouterr().out
    assert f"KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID={SIGNIN_APP}" in out
    assert "KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_SECRET=secretref:marketplace-signin-secret" in out
    assert "ok     KRUSGRAPH_MARKETPLACE_SIGNIN_CLIENT_ID" in out and "personliga Microsoft-konton" in out


def test_the_main_app_audience_check_is_unchanged():
    text = (ROOT / "deploy" / "azure_containerapp.py").read_text(encoding="utf-8")
    assert 'app.get("signInAudience") != "AzureADMultipleOrgs"' in text
    assert "AzureADandPersonalMicrosoftAccount" not in text
