"""Round n181: an App (Rayfin, preview) output in the Krusgraph Model item.

The founder published shop-desk by hand (5-7 November 2026): `rayfin up` answered 403 "The feature is not available"
until "Enable Fabric App Items (preview)" was on, the data-app project lacked rayfin/tsconfig.json, and the GraphQL API
it made allowed mutations on all seven tables and missed orders.ship_to_id -> addresses. Now (fabric_backend/rayfin_app.py,
docs/RAYFIN-APP.md):

- the preflight reads the tenant setting before anything else; off gives the admin card and nothing more, and Fabric's
  own 403 on the create gives the same card, never a generic error;
- the options are rules over the plan (key figures, list pages, charts), with defaults for shop, and the ticks go back
  with the request (the editor stores them in outputs.json);
- the dry run shows the pages, the connector and its API: read-only (no mutation types) with every link, R5 included;
- Create makes the App item by the documented call (POST /appBackends), records its id and plan, and never writes an
  item Krusgraph did not make (shop-desk, shop_desk_gql, shop_api stay as they are);
- a missing Item.ReadWrite.All refuses with the consent card; the package and the commands are there either way.
The package's type check with the pinned template packages is in tests/test_rayfin_app.py."""
import base64
import io
import json
import zipfile

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, keys, tok  # noqa: E402,F401
from test_workload_create import Workspace, _post, _review, make  # noqa: E402,F401
from fabric_backend import demo, plan, rayfin_app, server, workload_api  # noqa: E402
from fabric_backend.seed import schema  # noqa: E402

APP = {"kind": "rayfin_app", "name": "shop_app"}
SETTING = {"settingName": "AppBackendTenant", "title": "Enable Fabric App Items (preview)", "enabled": True,
           "tenantSettingGroup": "Microsoft Fabric"}
THEIRS = [{"id": "app-shop-desk", "displayName": "shop-desk", "type": "AppBackend", "description": ""},
          {"id": "gql-shop-desk", "displayName": "shop_desk_gql", "type": "GraphQLApi", "description": ""},
          {"id": "gql-shop-api", "displayName": "shop_api", "type": "GraphQLApi", "description": ""}]


class Apps(Workspace):
    """The workspace double with the admin tenant settings (None: 403, not a Fabric administrator) and Create App Backend
    (feature_off: 403 "The feature is not available", as `rayfin up` answered on 5 November)."""

    def __init__(self, setting=SETTING, feature_off=False, items=()):
        super().__init__(items=list(items))
        self.setting, self.feature_off, self.app_posts = setting, feature_off, []

    def _route(self, method, url, body=None):
        path = url.split("?")[0]
        if path.endswith("/v1/admin/tenantsettings"):
            self.calls.append((method, path))
            if self.setting is None:
                return gs.Response(403, {"errorCode": "Unauthorized", "message": "The caller is not a Fabric administrator"})
            return gs.Response(200, {"tenantSettings": [{"settingName": "Other", "title": "Other", "enabled": True}, self.setting]})
        if method == "POST" and path.endswith(f"/workspaces/{gs.WS}/appBackends"):
            self.calls.append((method, path))
            self.app_posts.append(body)
            if self.feature_off:
                return gs.Response(403, {"errorCode": "FeatureNotAvailable", "message": "The feature is not available"})
            iid = f"new-app-{len(self.items)}"
            self.items.append({"id": iid, "displayName": body["displayName"], "type": "AppBackend", "description": body.get("description", "")})
            return gs.Response(201, {"id": iid, "displayName": body["displayName"], "type": "AppBackend"})
        if method == "PATCH" and "/items/" in path:
            self.calls.append((method, path))
            iid = path.rsplit("/", 1)[-1]
            for it in self.items:
                if it["id"] == iid:
                    it["description"] = body["description"]
            return gs.Response(200, {"id": iid})
        return super()._route(method, url, body)


def _app(client, priv, rv, dry_run=True, app=None, created=(), **extra):
    out = {**APP, **({"app": app} if app is not None else {})}
    body = {**SRC, "review": rv, "outputs": [out], "dry_run": dry_run, "created": list(created), **extra}
    r = _post(client, "/build", body, priv)
    assert r.status_code == 200, r.text
    return r.json()["outputs"][0]


def _writes(fake):
    return [c for c in fake.calls if c[0] in ("POST", "PATCH") and not c[1].endswith("/getDefinition")]


@pytest.fixture(scope="module")
def shop_rows():
    return plan(schema("shop"), keys=demo.DEMO_KEYS, execute=demo._demo_db())


# ------------------------------------------------------------------ preflight -------------------------------------

def test_preflight_off_shows_the_admin_card_and_reads_nothing_else(make):
    client, fake, priv = make(Apps(setting={**SETTING, "enabled": False}))
    rv = _review(client, priv)
    fake.calls.clear()
    card = _app(client, priv, rv)
    a = card["answer"]
    assert a["kind"] == "feature_disabled" and a["setting"] == "Enable Fabric App Items (preview)"
    assert "Microsoft Fabric" in a["where"] and any("Admin portal" in s for s in a["admin_steps"])
    assert "options" not in a and "package" not in a
    assert [c[1].split(".com")[-1] for c in fake.calls if "admin" in c[1]] == ["/v1/admin/tenantsettings"]
    assert _writes(fake) == []


def test_preflight_on_says_so_and_unknown_when_not_an_admin(make):
    client, fake, priv = make(Apps())
    rv = _review(client, priv)
    on = _app(client, priv, rv)["answer"]["preflight"]
    assert on["status"] == "on" and "On for the organisation" in on["note"]
    fake.setting = None
    unknown = _app(client, priv, rv)["answer"]["preflight"]
    assert unknown["status"] == "unknown" and "Fabric administrator" in unknown["note"]


def test_preflight_names_the_security_groups(monkeypatch):
    s = {**SETTING, "enabledSecurityGroups": [{"graphId": "g", "name": "App makers"}]}
    import sys
    monkeypatch.setattr(sys.modules["fabric_backend.deploy"], "send", lambda *a, **k: gs.Response(200, {"tenantSettings": [s]}))
    assert "App makers" in rayfin_app.preflight({}, None)["note"]
    assert rayfin_app.preflight({}, {"Item.ReadWrite.All"})["status"] == "unknown"    # no Tenant.Read.All: not called


def test_fabric_s_403_on_create_is_the_admin_card_not_a_generic_error(make):
    client, fake, priv = make(Apps(setting=None, feature_off=True))
    rv = _review(client, priv)
    card = _app(client, priv, rv, dry_run=False)
    assert card["answer"]["kind"] == "feature_disabled" and card["answer"]["admin_steps"]
    assert "created" not in card or card["created"] == []
    assert rayfin_app.feature_disabled(403, {"message": "The feature is not available"})
    assert not rayfin_app.feature_disabled(403, {"errorCode": "InsufficientScopes"})


# ------------------------------------------------------------------ choices -----------------------------------------

def test_the_shop_defaults(shop_rows):
    o = rayfin_app.options(shop_rows)
    d = rayfin_app.defaults(o)
    assert d["kpis"] == ["rows:orders", "rows:order_items", "sum:order_items.quantity"]
    assert sorted(d["tables"]) == ["table:order_items", "table:orders", "table:products"]
    labels = {c["id"]: c["label"] for c in o["charts"]}
    assert [labels[i] for i in d["charts"]] == ["Total quantity by customers (country)", "Total quantity by categories (name)"]
    # personal data by name is never a chart's label (customers.name, addresses.city)
    assert not any(c["label_column"] in ("name",) and c["label_table"] == "customers" for c in o["charts"])
    assert not any(c["label_table"] == "addresses" for c in o["charts"])


def test_the_ticks_go_with_the_request_and_a_gone_id_is_listed(make):
    client, fake, priv = make(Apps())
    rv = _review(client, priv)
    a = _app(client, priv, rv, app={"kpis": ["rows:orders"], "tables": [], "charts": ["chart:nope"]})["answer"]
    assert a["chosen"] == {"kpis": ["rows:orders"], "tables": [], "charts": []} and a["gone"] == ["chart:nope"]
    assert [p["id"] for p in a["pages"]] == ["kpis"]
    r = _post(client, "/build", {**SRC, "review": rv, "outputs": [{**APP, "app": {"kpis": "x"}}]}, priv)
    assert r.status_code == 400
    nothing = _app(client, priv, rv, app={"kpis": [], "tables": [], "charts": []})["answer"]
    assert nothing["kind"] == "bad_input"


# ------------------------------------------------------------------ the dry run -------------------------------------

def test_the_dry_run_shows_the_pages_and_a_read_only_api_with_every_link(make):
    client, fake, priv = make(Apps())
    rv = _review(client, priv)
    fake.calls.clear()
    card = _app(client, priv, rv)
    a = card["answer"]
    assert a["dry_run"] is True and a["preview"] is True and a["label"] == "App (Rayfin, preview)"
    assert [p["title"] for p in a["pages"]][:2] == ["Key figures", "Charts"]
    api = a["api"]
    assert api["read_only"] is True and api["mutations"] == [] and api["operations"] == ["read"]
    assert all(set(t["queries"]) <= {"Query", "Query_by_pk"} for t in api["types"])
    links = {(l["from"], l["to"]) for l in api["links"]}
    assert len(links) == len(api["links"]) and ("orders.customer_id", "customers.customer_id") in links
    files = zipfile.ZipFile(io.BytesIO(base64.b64decode(a["package"]["zip_base64"])))
    names = set(files.namelist())
    assert {"rayfin/tsconfig.json", "src/App.tsx", "src/lib/app-connectors.ts", "KRUSGRAPH-APP.md"} <= names
    for n in names:
        text = files.read(n).decode()
        assert "declare " not in text and not __import__("re").search(r"'(create|update|delete)'", text), n
    assert [c["command"].split()[:2] for c in a["commands"]][1:] == [["npx", "rayfin"]] * 3
    assert any("rayfin login" in c["command"] for c in a["commands"]) and any("--operations read" in c["command"] for c in a["commands"])
    assert "not documented" in a["why_not_published"] or "no definition" in a["why_not_published"]
    assert _writes(fake) == []


def test_the_api_carries_the_r5_link(shop_rows):
    api = rayfin_app.api_summary(shop_rows, "shop", "SqlAnalyticsEndpoint")
    assert {"from": "orders.ship_to_id", "to": "addresses.address_id", "rule": "R5"} in api["links"]
    assert len(api["links"]) == 7 and api["read_only"] and api["mutations"] == []


# ------------------------------------------------------------------ Create ----------------------------------------

def test_create_makes_the_app_item_and_records_its_id_and_plan(make):
    client, fake, priv = make(Apps(items=THEIRS))
    rv = _review(client, priv)
    card = _app(client, priv, rv, dry_run=False, only=["rayfin_app"], skip_built=True)
    assert fake.app_posts == [{"displayName": "shop_app", "description": rayfin_app.description("shop_app")}]
    made = card["created"]
    assert len(made) == 1 and made[0]["type"] == "AppBackend" and made[0]["output"] == "rayfin_app"
    assert made[0]["plan"]["plan_id"] == rv["plan_id"]
    item = next(i for i in fake.items if i["id"] == made[0]["id"])
    assert workload_api.mark_of_description(item["description"]) == made[0]["plan"]
    assert card["answer"]["package"]["zip_base64"] and card["portal_steps"]
    # nothing Krusgraph did not make was written
    touched = " ".join(c[1] for c in _writes(fake))
    for t in THEIRS:
        assert t["id"] not in touched
    # a re-run skips what is built from this plan
    again = _app(client, priv, rv, dry_run=False, only=["rayfin_app"], skip_built=True, created=made)
    assert again.get("already_built") is True and len(fake.app_posts) == 1


def test_an_app_of_that_name_someone_else_made_is_refused(make):
    client, fake, priv = make(Apps(items=[{"id": "app-other", "displayName": "shop_app", "type": "AppBackend", "description": ""}]))
    rv = _review(client, priv)
    card = _app(client, priv, rv, dry_run=False)
    assert card["refusal"]["kind"] == "already_exists" and fake.app_posts == []


def test_without_item_readwrite_all_create_is_refused_with_the_consent_steps(make, monkeypatch):
    monkeypatch.setattr(workload_api, "token_scopes", lambda: {"Workspace.Read.All", "Lakehouse.Read.All"})
    client, fake, priv = make(Apps())
    rv = _review(client, priv)
    dry = _app(client, priv, rv)
    assert dry["consent"]["scope"] == "Item.ReadWrite.All" and dry["answer"]["package"]["zip_base64"]   # the package path
    card = _app(client, priv, rv, dry_run=False)
    assert card["refusal"]["kind"] == "consent" and card["refusal"]["entra_steps"] and fake.app_posts == []


# ------------------------------------------------------------------ MCP -------------------------------------------

def test_rayfin_connector_checks_first_and_stops_when_off(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {})
    monkeypatch.setattr(rayfin_app, "preflight", lambda h, s: {"status": "off", **rayfin_app.off_card("The tenant setting is off.")})
    read = []
    monkeypatch.setattr(server, "_source_inputs", lambda *a, **k: read.append(a))
    monkeypatch.setattr(server, "_plan", lambda *a, **k: read.append(a))
    out = json.loads(server.rayfin_connector(workspace="demo", source="shop_lh", schema="shop"))
    assert out["kind"] == "feature_disabled" and out["admin_steps"] and read == []
