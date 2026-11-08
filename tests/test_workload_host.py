"""Round n168: the hosted Krusgraph Model editor on workload.krusgraph.com (fabric_backend/workload_host.py).

Host-based routing: the workload host serves only the editor's files (index.html for its routes, with the engine scope
written in), /close and /workload/v1; krusgraph.com still serves the site and /mcp. The headers on the workload host:
frame-ancestors for Fabric only, CORS for Fabric's origins only, HSTS, no cookies. And the editor's own same-origin calls
to the engine API are accepted."""
import pytest
from starlette.testclient import TestClient

from fabric_backend import server, workload_api, workload_host
from fabric_backend.entra import EntraConfig

HOST = "workload.krusgraph.com"
SITE = "krusgraph.com"
APP_ID_URI = "https://krusgraph.com/workload/Org.Krusgraph"
WL_ENV = {"KRUSGRAPH_WORKLOAD_CLIENT_ID": "99999999-8888-7777-6666-555555555555", "KRUSGRAPH_WORKLOAD_CLIENT_SECRET": "wl-secret",
          "KRUSGRAPH_WORKLOAD_APP_ID_URI": APP_ID_URI}
MCP = EntraConfig("https://krusgraph.com/mcp", "11111111-2222-3333-4444-555555555555", "mcp-secret")
FABRIC = "https://app.fabric.microsoft.com"
INDEX = "<html><head><title>Krusgraph</title></head><body><div id=\"root\"></div><script src=\"/bundle.0f3a.js\"></script></body></html>"


@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets" / "locales").mkdir(parents=True)
    (d / "index.html").write_text(INDEX, encoding="utf-8")
    (d / "bundle.0f3a.js").write_text("console.log('editor')", encoding="utf-8")
    (d / "assets" / "locales" / "translation.json").write_text("{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    return d


def client_for(monkeypatch, dist, entra=None, host=HOST, workload=True):
    for k in ("MCP_PUBLIC_URL", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_REQUIRED", "ENTRA_CLIENT_SECRET_KEYVAULT_URI",
              "KRUSGRAPH_CLIENT_REGISTRATION", *WL_ENV):
        monkeypatch.delenv(k, raising=False)
    if workload:
        for k, v in WL_ENV.items():
            monkeypatch.setenv(k, v)
    if host:
        monkeypatch.setenv(workload_host.HOST_ENV, host)
    else:
        monkeypatch.delenv(workload_host.HOST_ENV, raising=False)
    monkeypatch.setenv(workload_host.DIST_ENV, str(dist))
    monkeypatch.setattr(server.auth, "entra", entra)
    return TestClient(server.build_app(), base_url="https://" + SITE)


def on(host):
    return {"host": host}


@pytest.mark.parametrize("entra", [None, MCP], ids=["no-entra", "entra"])
def test_the_workload_host_serves_the_editor_and_not_the_site(monkeypatch, dist, entra):
    c = client_for(monkeypatch, dist, entra)
    r = c.get("/", headers=on(HOST))
    assert r.status_code == 200 and '<div id="root">' in r.text and "Krusgraph" in r.text
    assert "Fabric-native" not in r.text and "/static/site" not in r.text      # not the website's home page
    r = c.get("/ModelItem-editor/abc/def", headers=on(HOST))                    # an editor route → index.html
    assert r.status_code == 200 and '<div id="root">' in r.text
    r = c.get("/bundle.0f3a.js", headers=on(HOST))
    assert r.status_code == 200 and r.text == "console.log('editor')" and r.headers["content-type"].startswith("text/javascript")
    assert "immutable" in r.headers["cache-control"]
    assert c.get("/assets/locales/translation.json", headers=on(HOST)).json() == {}
    for path in ("/mcp", "/docs", "/privacy", "/healthz", "/.well-known/oauth-protected-resource", "/static/site.css",
                 "/missing.js", "/../secret.txt", "/%2e%2e/secret.txt"):
        r = c.get(path, headers=on(HOST))
        assert r.status_code == 404, path
        assert "outside" not in r.text
    assert c.post("/mcp", headers=on(HOST), json={}).status_code == 404
    assert c.post("/", headers=on(HOST)).status_code == 405


def test_close_only_closes_the_window(monkeypatch, dist):
    c = client_for(monkeypatch, dist)
    r = c.get("/close", headers=on(HOST))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.text.count("<script") == 1 and "<script>window.close();</script>" in r.text and "src=" not in r.text
    csp = r.headers["content-security-policy"]
    assert workload_host.CLOSE_HASH in csp and "'unsafe-inline'" not in csp and "frame-ancestors" in csp
    assert c.get("/close/", headers=on(HOST)).text == r.text
    assert c.get("/close", headers=on(SITE)).status_code == 404                 # the site has no /close


@pytest.mark.parametrize("entra", [None, MCP], ids=["no-entra", "entra"])
def test_krusgraph_com_still_serves_the_site_and_mcp(monkeypatch, dist, entra):
    c = client_for(monkeypatch, dist, entra)
    r = c.get("/", headers=on(SITE))
    assert r.status_code == 200 and '<div id="root">' not in r.text and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert c.get("/docs", headers=on(SITE)).status_code == 200
    assert c.get("/healthz", headers=on(SITE)).status_code == 200
    assert c.get("/bundle.0f3a.js", headers=on(SITE)).status_code == 404
    with c:                                   # the MCP session manager runs inside the app's lifespan
        r = c.post("/mcp", headers={**on(SITE), "accept": "application/json, text/event-stream"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    if entra:
        assert r.status_code == 401 and "oauth-protected-resource" in r.headers["www-authenticate"]
    else:
        assert r.status_code == 200 and '"result"' in r.text
    r = c.post(workload_api.PREFIX + "/review", headers=on(SITE), json={})
    assert r.status_code == 401 and r.json()["kind"] == "sign_in"               # the engine API is unchanged there


def test_without_the_variable_nothing_changes(monkeypatch, dist):
    c = client_for(monkeypatch, dist, host="")
    r = c.get("/", headers=on(HOST))
    assert r.status_code == 200 and '<div id="root">' not in r.text            # every host gets the site, as before
    assert c.get("/close", headers=on(HOST)).status_code == 404


def test_headers_on_the_workload_host(monkeypatch, dist):
    c = client_for(monkeypatch, dist)
    for path in ("/", "/bundle.0f3a.js", "/close", "/ModelItem-editor"):
        r = c.get(path, headers={**on(HOST), "origin": FABRIC})
        csp = r.headers["content-security-policy"]
        assert "frame-ancestors https://*.fabric.microsoft.com https://*.powerbi.com" in csp, path
        assert "frame-ancestors 'none'" not in csp
        assert r.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["access-control-allow-origin"] == FABRIC
        assert "set-cookie" not in r.headers
    assert "script-src 'self';" in c.get("/", headers=on(HOST)).headers["content-security-policy"]
    for origin in ("https://evil.example", "https://fabric.microsoft.com.evil.example", "http://app.powerbi.com"):
        r = c.get("/", headers={**on(HOST), "origin": origin})
        assert "access-control-allow-origin" not in r.headers, origin
    r = c.get("/", headers={**on(HOST), "origin": "https://msit.powerbi.com"})
    assert r.headers["access-control-allow-origin"] == "https://msit.powerbi.com"
    r = c.options("/bundle.0f3a.js", headers={**on(HOST), "origin": FABRIC, "access-control-request-method": "GET"})
    assert r.status_code == 204 and r.headers["access-control-allow-methods"] == "GET, HEAD, OPTIONS"


def test_the_engine_api_on_the_workload_host(monkeypatch, dist):
    c = client_for(monkeypatch, dist)
    # the editor's own call: same origin, no CORS needed, not refused as a foreign origin
    r = c.post(workload_api.PREFIX + "/review", headers={**on(HOST), "origin": "https://" + HOST}, json={})
    assert r.status_code == 401 and r.json()["kind"] == "sign_in"
    assert "access-control-allow-origin" not in r.headers
    assert r.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains" and "set-cookie" not in r.headers
    assert "frame-ancestors https://*.fabric.microsoft.com" in r.headers["content-security-policy"]
    r = c.options(workload_api.PREFIX + "/review", headers={**on(HOST), "origin": FABRIC, "access-control-request-method": "POST"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == FABRIC
    r = c.post(workload_api.PREFIX + "/review", headers={**on(HOST), "origin": "https://evil.example"}, json={})
    assert r.status_code == 403 and r.json()["kind"] == "origin"
    # the same-origin exception is only for the workload host itself, never for krusgraph.com's own origin
    r = c.post(workload_api.PREFIX + "/review", headers={**on(SITE), "origin": "https://krusgraph.com"}, json={})
    assert r.status_code == 403


def test_index_carries_the_engine_scope_from_the_server(monkeypatch, dist):
    c = client_for(monkeypatch, dist)
    r = c.get("/", headers=on(HOST))
    assert f'<meta name="krusgraph-engine-scope" content="{APP_ID_URI}/user_impersonation">' in r.text
    assert r.headers["cache-control"] == "no-cache"
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_SCOPE", 'Model.Build"><script>')
    r = c.get("/", headers=on(HOST))
    assert "<script>" not in r.text.split("</head>")[0] and "&quot;&gt;&lt;script&gt;" in r.text


def test_an_image_without_the_editor_says_so(monkeypatch, tmp_path):
    c = client_for(monkeypatch, tmp_path / "nothing")
    r = c.get("/", headers=on(HOST))
    assert r.status_code == 503 and "editor" in r.text


@pytest.mark.parametrize("value, expected", [("workload.krusgraph.com", HOST), ("https://Workload.Krusgraph.com/", HOST),
                                             ("workload.krusgraph.com:443", HOST), ("", "")])
def test_the_host_setting(monkeypatch, value, expected):
    monkeypatch.setenv(workload_host.HOST_ENV, value)
    assert workload_host.configured_host() == expected


def test_a_bad_host_setting_stops_the_server(monkeypatch):
    monkeypatch.setenv(workload_host.HOST_ENV, "workload krusgraph com")
    with pytest.raises(ValueError):
        workload_host.configured_host()
