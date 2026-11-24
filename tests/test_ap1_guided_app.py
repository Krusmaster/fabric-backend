"""Round AP1: the guided chat at /app (fabric_backend/guided_app.py), the founder's decision of 24 November 2026.

Hidden and closed by default: every /app address answers the site's own 404 while KRUSGRAPH_APP_TENANTS is empty, for a
method a route does not take, and for a sign-in from a tenant that is not on the list. Signed out, /app sends the browser
to sign in; the sign-in is the authorization code flow with PKCE against the Krusgraph MCP Entra app, and the browser
gets one HttpOnly, Secure, SameSite=Lax session cookie, never a token. The page is noindex, absent from the sitemap,
robots.txt, llms.txt and every page's navigation, and its HTML carries no token and no tenant id. The journey's read
steps run the `start` tool's own engine with the session's on-behalf-of tokens (the synthetic SAP demo behind the
doubles of tests/wb15_fake.py, no write possible), and the steps that write are refused here (AP2: the dry run and
Create have their own address, tests/test_ap2_guided_build.py).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re

import pytest

pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import ap1_support as s  # noqa: E402
from fabric_backend import flow_state, guided_app, server  # noqa: E402
from fabric_backend.csn_onelake import STORAGE_SCOPE  # noqa: E402
from fabric_backend.entra import FABRIC_SCOPE, SQL_SCOPE  # noqa: E402

HTML = {"Accept": "text/html"}
APP_LINK = re.compile(r"(?<![\w/.])/app(?=[/\"'?#\s<)]|$)")


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def client(app):
    return TestClient(app, base_url=s.ORIGIN, follow_redirects=False)


# ------------------------------------------------------------------ closed by default ----------------------------------

ROUTES = [("GET", guided_app.PATH), ("GET", guided_app.LOGIN), ("GET", guided_app.CALLBACK + "?code=x&state=" + "a" * 20),
          ("POST", guided_app.LOGOUT), ("POST", guided_app.STEP)]


@pytest.mark.parametrize("tenants", [None, "", " , "])
def test_every_app_address_is_the_sites_404_while_the_list_is_empty(monkeypatch, keys, tenants):
    app, _, _ = s.entra_app(monkeypatch, keys, tenants)
    with client(app) as c:
        nothing = c.get("/no-such-page", headers=HTML)
        for method, path in ROUTES:
            r = c.request(method, path, headers=HTML)
            assert r.status_code == 404, (method, path)
            if method == "GET":
                bare = path.split("?")[0]
                assert r.text.replace(f"<code>{bare}</code>", "") == nothing.text.replace("<code>/no-such-page</code>", ""), path
                for h in ("content-security-policy", "x-robots-tag", "content-type", "referrer-policy"):
                    assert r.headers.get(h) == nothing.headers.get(h), (path, h)
            assert "set-cookie" not in r.headers, path
        assert c.post(guided_app.STEP, json={}).text == c.post("/no-such-api", json={}).text == "not found"


def test_without_entra_sign_in_there_is_no_app(monkeypatch):
    monkeypatch.setenv(guided_app.ENV, s.TID)
    monkeypatch.setattr(server.auth, "entra", None)
    with TestClient(server.build_app(), base_url=s.ORIGIN, follow_redirects=False) as c:
        for method, path in ROUTES:
            assert c.request(method, path).status_code == 404, path


def test_a_method_a_route_does_not_take_is_a_404_not_a_405(monkeypatch, keys):
    app, _, _ = s.entra_app(monkeypatch, keys)
    with client(app) as c:
        for method, path in [("POST", guided_app.PATH), ("DELETE", guided_app.PATH), ("GET", guided_app.STEP),
                             ("GET", guided_app.LOGOUT), ("POST", guided_app.LOGIN), ("PUT", guided_app.CALLBACK)]:
            assert c.request(method, path).status_code == 404, (method, path)


# ------------------------------------------------------------------ sign-in --------------------------------------------

def test_signed_out_the_page_sends_the_browser_to_sign_in(monkeypatch, keys):
    app, _, _ = s.entra_app(monkeypatch, keys)
    with client(app) as c:
        r = c.get(guided_app.PATH, headers=HTML)
        assert r.status_code == 302 and r.headers["location"] == guided_app.LOGIN
        assert r.headers["cache-control"] == "no-store"
        r, loc, q = s.start_login(c)
        assert loc.startswith("https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?")
        assert q["client_id"] == s.CFG.client_id and q["response_type"] == "code"
        assert q["redirect_uri"] == "https://kg.example.com/app/callback"
        assert q["scope"] == s.CFG.scope and "offline_access" not in q["scope"]      # no refresh token is asked for
        assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
        flow = r.headers["set-cookie"]
        assert flow.startswith(guided_app.FLOW_COOKIE + "=")
        for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
            assert flag.lower() in flow.lower(), flag


def test_the_sign_in_sets_one_short_secure_session_cookie_and_the_page_holds_no_token(monkeypatch, keys):
    app, a, fake = s.entra_app(monkeypatch, keys)
    token = s.tok(keys[0])
    with client(app) as c:
        r = s.sign_in(c, fake, token)
        assert r.status_code == 302 and r.headers["location"] == guided_app.PATH
        cookies = r.headers.get_list("set-cookie")
        session = next(x for x in cookies if x.startswith(guided_app.SESSION_COOKIE + "="))
        low = session.lower()
        for flag in ("httponly", "secure", "samesite=lax", "path=/"):
            assert flag in low, flag
        assert "domain=" not in low                                        # __Host-: this host only
        age = int(re.search(r"max-age=(\d+)", low).group(1))
        assert 0 < age <= guided_app.SESSION_TTL
        sid = session.split(";")[0].split("=", 1)[1]
        assert sid != token and token not in " ".join(cookies)
        assert any(x.startswith(guided_app.FLOW_COOKIE + '=""') or "max-age=0" in x.lower() for x in cookies
                   if x.startswith(guided_app.FLOW_COOKIE))                # the flow cookie is spent
        # the code was redeemed with the verifier whose S256 the browser was sent with, as the confidential client
        req = fake.requests[-1]
        assert req["grant_type"] == "authorization_code" and req["client_secret"] == s.CFG.client_secret
        assert req["redirect_uri"] == "https://kg.example.com/app/callback"
        page = c.get(guided_app.PATH, headers=HTML)
        assert page.status_code == 200
        body = page.text
        for secret in (token, sid, s.TID, s.CFG.client_secret, "person-1", req["code_verifier"]):
            assert secret not in body
        assert f"Signed in as {s.NAME}." in body
        assert '<meta name="robots" content="noindex,nofollow">' in body and 'rel="canonical"' not in body
        assert page.headers["x-robots-tag"] == "noindex, nofollow" and page.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        assert "lovable for data" not in body.lower()                      # the internal name never shows
        assert 'aria-live="polite"' in body and "/static/app.js" in body and "/static/app.css" in body


def test_the_verifier_matches_the_challenge(monkeypatch, keys):
    app, _, fake = s.entra_app(monkeypatch, keys)
    with client(app) as c:
        _, _, q = s.start_login(c)
        fake.codes["c"] = s.tok(keys[0])
        c.get(guided_app.CALLBACK, params={"code": "c", "state": q["state"]})
        v = fake.requests[-1]["code_verifier"]
        assert base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode() == q["code_challenge"]


def test_a_tenant_not_on_the_list_gets_the_404_and_no_session(monkeypatch, keys):
    app, _, fake = s.entra_app(monkeypatch, keys, tenants=f"{s.TID.upper()}, ")
    with client(app) as c:
        r = s.sign_in(c, fake, s.tok(keys[0], tid=s.OTHER), code="other")
        assert r.status_code == 404
        assert not any(x.startswith(guided_app.SESSION_COOKIE + "=") for x in r.headers.get_list("set-cookie"))
        assert s.OTHER not in r.text
        assert c.get(guided_app.PATH).status_code == 302                 # still signed out
        assert s.sign_in(c, fake, s.tok(keys[0]), code="ok").status_code == 302      # the list ignores case and spaces
        assert c.get(guided_app.PATH).status_code == 200


def test_an_unsigned_or_wrong_audience_token_gets_no_session(monkeypatch, keys):
    app, _, fake = s.entra_app(monkeypatch, keys)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with client(app) as c:
        for i, bad in enumerate((s.tok(other), s.tok(keys[0], aud="api://someone-else"), s.tok(keys[0], scp="Other.Scope"))):
            r = s.sign_in(c, fake, bad, code=f"bad{i}")
            assert r.status_code in (403, 404)
            assert not any(x.startswith(guided_app.SESSION_COOKIE + "=") for x in r.headers.get_list("set-cookie"))
        assert c.get(guided_app.PATH).status_code == 302


def test_state_is_taken_once_and_bound_to_the_browser(monkeypatch, keys):
    app, _, fake = s.entra_app(monkeypatch, keys)
    with client(app) as c:
        _, _, q = s.start_login(c)
        fake.codes["a"] = s.tok(keys[0])
        c.cookies.clear()                                                  # another browser: no flow cookie
        assert c.get(guided_app.CALLBACK, params={"code": "a", "state": q["state"]}).status_code == 403
        assert c.get(guided_app.CALLBACK, params={"code": "a", "state": q["state"]}).status_code == 400   # spent
        assert s.sign_in(c, fake, s.tok(keys[0]), code="b").status_code == 302
        assert c.get(guided_app.CALLBACK, params={"code": "b", "state": "x" * 30}).status_code == 400


def test_the_session_ends_when_the_tenant_leaves_the_list_and_on_sign_out(monkeypatch, keys):
    app, _, fake = s.entra_app(monkeypatch, keys)
    with client(app) as c:
        s.sign_in(c, fake, s.tok(keys[0]))
        assert c.get(guided_app.PATH).status_code == 200
        monkeypatch.setenv(guided_app.ENV, s.OTHER)
        assert c.get(guided_app.PATH).status_code == 302
        monkeypatch.setenv(guided_app.ENV, s.TID)
        assert c.get(guided_app.PATH).status_code == 302                 # the session was dropped, not paused
        s.sign_in(c, fake, s.tok(keys[0]), code="again")
        assert c.post(guided_app.LOGOUT, headers={"Origin": "https://evil.example"}).status_code == 403
        r = c.post(guided_app.LOGOUT, headers={"Origin": s.ORIGIN})
        assert r.status_code == 303 and r.headers["location"] == "/"
        assert c.get(guided_app.PATH).status_code == 302
        assert len(guided_app.SESSIONS) == 0


def test_an_expired_token_gives_no_session_longer_than_itself(monkeypatch, keys):
    app, _, fake = s.entra_app(monkeypatch, keys)
    import time
    with client(app) as c:
        r = s.sign_in(c, fake, s.tok(keys[0], exp=int(time.time()) + 400))
        session = next(x for x in r.headers.get_list("set-cookie") if x.startswith(guided_app.SESSION_COOKIE + "="))
        assert int(re.search(r"max-age=(\d+)", session.lower()).group(1)) <= 340


# ------------------------------------------------------------------ hidden ---------------------------------------------

def test_the_page_is_in_no_sitemap_robots_llms_or_navigation(monkeypatch, keys):
    app, _, fake = s.entra_app(monkeypatch, keys)
    with client(app) as c:
        for path in ("/sitemap.xml", "/robots.txt", "/llms.txt", "/llms-full.txt", "/", "/docs", "/start", "/check",
                     "/use-cases", "/partners", "/support", "/blog", "/it", "/docs.md", "/start.md"):
            r = c.get(path, headers=HTML)
            assert r.status_code == 200, path
            assert not APP_LINK.search(r.text), path
        s.sign_in(c, fake, s.tok(keys[0]))
        page = c.get(guided_app.PATH, headers=HTML).text
        nav = re.search(r'<nav id="site-nav".*?</nav>', page, re.S).group(0)
        assert not APP_LINK.search(nav) and "/app" not in re.search(r'<footer.*?</footer>', page, re.S).group(0)


# ------------------------------------------------------------------ the journey ----------------------------------------

@pytest.fixture
def journey(monkeypatch, keys):
    app, a, fake = s.entra_app(monkeypatch, keys)
    seen = s.data(monkeypatch)
    token = s.tok(keys[0])
    c = client(app)
    c.__enter__()
    assert s.sign_in(c, fake, token).status_code == 302
    yield c, a, seen, token
    c.__exit__(None, None, None)


def test_the_read_steps_run_the_start_engine_with_the_sessions_own_tokens(journey):
    import wb15_fake
    c, a, seen, token = journey
    first = s.step(c, {}).json()
    assert first["stage"] == "workspace" and first["who"] == "onto"
    assert [x["label"] for x in first["choices"]] == ["demo", "sales_archive"]
    assert seen["fabric"] == ["Bearer " + s.RecordingOBO.expected(token, FABRIC_SCOPE)]     # the person's own token
    assert {(t, sc) for _, t, sc in a._obo.calls} == {(s.TID, FABRIC_SCOPE)}

    chosen = s.step(c, first["choices"][0]["arguments"]).json()
    assert chosen["stage"] == "data" and chosen["line"] == "demo › demo_lh › dbo ✓"         # one source, one schema
    assert chosen["buttons"][0] == {"label": "Next: Check", "primary": True,
                                    "arguments": {"workspace": "demo", "source": "demo_lh", "schema": "dbo", "step": "check"}}

    check = s.step(c, chosen["buttons"][0]["arguments"]).json()
    assert check["stage"] == "check" and check["who"] == "thinker"
    assert check["say"] == "17 tables, 24 links, 1 needs you."
    assert check["counts"]["tables"] == 17 and check["counts"]["hold"] == 40 and check["counts"]["checks"] == 41
    assert len(check["map"]["tables"]) == 17 and len(check["map"]["links"]) == 24
    assert any(r["state"] == "failed" and r["orphans"] == 1 for r in check["map"]["links"])     # the planted orphan
    assert check["next"] == guided_app.NEXT_LINE                                             # AP2: Decide comes next
    assert [b["label"] for b in check["buttons"]] == ["Next: Decide"]
    assert seen["sql"] and set(seen["sql"]) == {s.RecordingOBO.expected(token, SQL_SCOPE)}
    scopes = {sc for _, t, sc in a._obo.calls if t == s.TID}         # Fabric, SQL, and OneLake's read of CSN files
    assert {FABRIC_SCOPE, SQL_SCOPE} <= scopes <= {FABRIC_SCOPE, SQL_SCOPE, STORAGE_SCOPE}
    assert {u for u, _, _ in a._obo.calls} == {hashlib.sha256(token.encode()).hexdigest()[:12]}
    assert wb15_fake.WRITES == []                                                             # nothing was written
    # the guided path's shared state is the person's (the session's digest), never the shared "local"
    who = flow_state.who_of({"oid": "person-1", "tid": s.TID}, None)
    assert flow_state.state(who, "demo", "demo_lh", "dbo") and not flow_state.state("local", "demo", "demo_lh", "dbo")
    text = json.dumps(check)
    assert token not in text and s.TID not in text


@pytest.mark.parametrize("step", ["dry_run", "create", "done", "latest"])
def test_the_steps_that_write_are_refused_here(journey, monkeypatch, step):
    c, _, _, _ = journey
    calls = []
    monkeypatch.setattr(server, "start", lambda **k: calls.append(k) or "{}")
    r = s.step(c, {"workspace": "demo", "source": "demo_lh", "schema": "dbo", "step": step, "create": ["x"], "confirm": True})
    assert r.status_code == 400 and r.json()["kind"] == "wrong_step" and calls == []


def test_only_the_names_and_a_read_step_reach_the_engine(journey, monkeypatch):
    c, _, _, _ = journey
    calls = []
    monkeypatch.setattr(server, "start", lambda **k: calls.append(k) or json.dumps({"stage": "workspace", "say": "Hi"}))
    s.step(c, {"workspace": " demo ", "plan": {"decisions": [1]}, "create": ["a"], "confirm": True, "sample": True})
    assert calls == [{"workspace": "demo"}]


def test_the_step_needs_a_session_this_sites_origin_and_json(journey):
    c, _, _, _ = journey
    assert s.step(c, {}, Origin="https://evil.example").status_code == 403
    assert c.post(guided_app.STEP, content="{}", headers={"Origin": s.ORIGIN, "Content-Type": "text/plain"}).status_code == 403
    c.cookies.clear()
    r = s.step(c, {})
    assert r.status_code == 401 and r.json()["login"] == guided_app.LOGIN


def test_a_typed_name_is_matched_by_fixed_rules(journey):
    c, _, _, _ = journey
    hit = s.step(c, {"step": "workspace", "text": "  DEMO "}).json()
    assert hit["stage"] == "data" and hit["chosen"]["workspace"] == "demo"
    prefix = s.step(c, {"step": "workspace", "text": "sales"}).json()
    assert prefix["chosen"]["workspace"] == "sales_archive"
    none = s.step(c, {"step": "workspace", "text": "finance"}).json()
    assert none["stage"] == "workspace" and none["match"]["candidates"] == [] and "No name here matches" in none["match"]["say"]


def test_match_choice_rules():
    names = ["demo", "demo_lh", "sales_archive", "Sales"]
    assert guided_app.match_choice("demo", names) == ("demo", [])                 # the same name wins over prefixes
    assert guided_app.match_choice("SALES", names) == ("Sales", [])
    assert guided_app.match_choice("demo_", names) == ("demo_lh", [])
    assert guided_app.match_choice("arch", names) == ("sales_archive", [])        # contained, once
    assert guided_app.match_choice("de", names) == (None, ["demo", "demo_lh"])    # two: nothing is guessed
    assert guided_app.match_choice("", names) == (None, [])
    assert guided_app.match_choice("xyz", names) == (None, [])


def test_the_view_keeps_only_what_the_page_draws():
    v = guided_app.view({"stage": "check", "who": "thinker", "say": "x", "counts": {"tables": 1, "secret": 2},
                         "after": {"label": "Next: Decide", "arguments": {"step": "decide"}},
                         "actions": [{"kind": "call", "label": "Dry run", "arguments": {"dry_run": True}}]})
    assert v["counts"] == {"tables": 1} and v["next"] == guided_app.NEXT_LINE
    assert v["buttons"] == [{"label": "Next: Decide", "arguments": {"step": "decide"}, "primary": True}]
    assert guided_app.view({"error": "e", "kind": "no_access", "hint": "h", "trace": "t"}) == {"error": "e", "kind": "no_access", "hint": "h"}
