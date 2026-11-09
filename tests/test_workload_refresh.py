"""Round n180, addition 4: the founder's report of 9 November 2026, 12:40 CET.

demo_lh_report2, built from the editor, showed "Error fetching data" on every visual until demo_lh_model3 was refreshed
by hand; then its figures were right. Its title read "Overview · 3cd7bfba-…" (the model's id), and the captions under
the cards' numbers and the slicer's title "Category name" were cut off. Now:

(a) Create refreshes a semantic model it has just created, once (Power BI REST, Refresh Dataset In Group, scope
    Dataset.ReadWrite.All), waits for it within a bounded poll, and says refreshed / refreshing / failed: reason on the
    model's card; the dry run says it will; without the permission it says which one with the Entra steps and keeps the
    portal step. A model that was updated, found built or named by the person is never refreshed.
(b) the report's title names the model's display name when the model is given by id;
(c) the cards and the slicer are sized so their text fits at 1280 x 720.
Fabric REST, Power BI REST and the SQL endpoint are doubles (tests/golden_support.py)."""
import json
import sys

import pytest

pytest.importorskip("jwt")
from starlette.testclient import TestClient  # noqa: E402

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, WL, FakeJWKS, keys, tok  # noqa: E402,F401
from test_workload_build import NEW_SM, ScopedOBO  # noqa: E402
from test_workload_create import _review  # noqa: E402
from test_workload_plans import Defined  # noqa: E402
from fabric_backend import report, server, workload_api  # noqa: E402
from fabric_backend.entra import Validator  # noqa: E402

WITH_REFRESH = "Workspace.Read.All Lakehouse.Read.All Item.ReadWrite.All Dataset.ReadWrite.All"
WITHOUT_REFRESH = "Workspace.Read.All Lakehouse.Read.All Item.ReadWrite.All"
MODEL = {"kind": "semantic_model", "name": "demo_lh_model3"}


class PowerBI(Defined):
    """The workspace, plus Power BI's refresh routes: POST .../refreshes answers 202 with a request id, and GET
    .../refreshes?$top=1 answers `states` one after another (the last one repeats). `refresh_status` overrides the POST."""

    def __init__(self, states=("Unknown", "Completed"), refresh_status=202, items=(), **kw):
        super().__init__(items=items, **kw)
        self.states, self.refresh_status, self.refreshed, self.polls = list(states), refresh_status, [], 0

    def _route(self, method, url, body=None):
        if url.startswith("https://api.powerbi.com/"):
            path = url.split("?")[0]
            self.calls.append((method, path))
            model = path.split("/datasets/")[1].split("/")[0]
            if method == "POST":
                self.refreshed.append(model)
                return gs.Response(self.refresh_status, {} if self.refresh_status < 400 else {"error": {"code": "Forbidden"}},
                                   {"x-ms-request-id": "req-1", "Location": url + "/req-1"})
            state = self.states[min(self.polls, len(self.states) - 1)]
            self.polls += 1
            entry = {"requestId": "req-1", "status": state, "refreshType": "ViaApi"}
            if state == "Failed":
                entry["serviceExceptionJson"] = json.dumps({"errorCode": "ModelRefreshFailed_CredentialsNotSpecified"})
            return gs.Response(200, {"value": [entry]})
        return super()._route(method, url, body)


@pytest.fixture
def make(keys, monkeypatch):
    import requests
    from starlette.applications import Starlette
    priv, pub = keys
    monkeypatch.setattr(server, "MODEL_DEFINITION_PAUSES", (0, 0, 0))
    monkeypatch.setattr(workload_api, "REFRESH_POLL_SECONDS", 0)

    def build(fake=None, scp=WITH_REFRESH):
        fake = fake or PowerBI()
        for verb in ("get", "post", "patch"):
            monkeypatch.setattr(requests, verb, getattr(fake, verb))
        monkeypatch.setitem(sys.modules, "pyodbc", gs.fake_pyodbc())
        monkeypatch.setattr(server, "limiter", None)
        obo = ScopedOBO(scp)
        app = Starlette(routes=workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), obo))
        return TestClient(app, raise_server_exceptions=False), fake, priv, obo
    return build


def _build(client, priv, outputs, created=(), **extra):
    rv = _review(client, priv)
    body = {**SRC, "review": rv, "outputs": outputs, "dry_run": False, "created": list(created), "skip_built": True, **extra}
    return client.post(workload_api.PREFIX + "/build", json=body,
                       headers={"Authorization": f"Bearer {tok(priv)}", "Origin": "https://app.fabric.microsoft.com"}).json()


# ------------------------------------------------------------------ (a) one refresh of a new model -----------------

def test_create_refreshes_the_new_model_once_waits_and_says_refreshed(make):
    client, fake, priv, obo = make()
    out = _build(client, priv, [MODEL])
    card = out["outputs"][0]
    assert card["refresh"] == {"status": "refreshed"}, card.get("refresh")
    assert fake.refreshed == [NEW_SM] and fake.polls == 2
    assert not any(s.startswith(workload_api.REFRESH_STEP) for s in card["portal_steps"])
    assert ("https://analysis.windows.net/powerbi/api/.default" in [s for _, s in obo.calls])   # the Power BI audience
    posts = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/refreshes")]
    assert posts == [("POST", f"https://api.powerbi.com/v1.0/myorg/groups/{gs.WS}/datasets/{NEW_SM}/refreshes")]


def test_the_report_is_built_after_the_refresh_on_the_refreshed_model(make):
    client, fake, priv, _ = make()
    created = _build(client, priv, [MODEL])["created"]
    order = [c[1] for c in fake.calls if c[1].endswith("/refreshes") or c[1].endswith("/reports")]
    out = _build(client, priv, [MODEL, {"kind": "report", "name": "demo_lh_report2", "model": NEW_SM}], created, only=["report"])
    assert out["outputs"][0]["created"], out["outputs"][0]
    assert order and all(p.endswith("/refreshes") for p in order)                 # the refresh came first, finished


def test_a_failed_refresh_says_why_and_keeps_the_portal_step(make):
    client, fake, priv, _ = make(PowerBI(states=("Unknown", "Failed")))
    card = _build(client, priv, [MODEL])["outputs"][0]
    assert card["refresh"] == {"status": "failed", "reason": "ModelRefreshFailed_CredentialsNotSpecified"}
    assert any(s.startswith(workload_api.REFRESH_STEP) for s in card["portal_steps"])
    assert card["created"]                                                       # the model stands


def test_the_wait_is_bounded_and_then_says_refreshing(make):
    client, fake, priv, _ = make(PowerBI(states=("Unknown",)))
    card = _build(client, priv, [MODEL])["outputs"][0]
    assert card["refresh"]["status"] == "refreshing" and fake.polls == workload_api.REFRESH_MAX_POLLS
    assert any(s.startswith(workload_api.REFRESH_STEP) for s in card["portal_steps"])


def test_without_the_permission_nothing_is_refreshed_and_the_card_names_it_with_the_entra_steps(make):
    client, fake, priv, _ = make(scp=WITHOUT_REFRESH)
    card = _build(client, priv, [MODEL])["outputs"][0]
    r = card["refresh"]
    assert r["status"] == "not_run" and r["scope"] == "Dataset.ReadWrite.All"
    assert any("Tick Dataset.ReadWrite.All" in s for s in r["entra_steps"])
    assert fake.refreshed == [] and any(s.startswith(workload_api.REFRESH_STEP) for s in card["portal_steps"])


def test_power_bi_refusing_the_refresh_is_said_as_consent(make):
    client, fake, priv, _ = make(PowerBI(refresh_status=403), scp=None)            # the token's scopes cannot be read
    r = _build(client, priv, [MODEL])["outputs"][0]["refresh"]
    assert r["status"] == "not_run" and "HTTP 403" in r["reason"] and r["scope"] == "Dataset.ReadWrite.All"


def test_the_dry_run_says_create_refreshes_once_and_refreshes_nothing(make):
    client, fake, priv, _ = make()
    out = _build(client, priv, [MODEL], dry_run=True, skip_built=False)
    card = out["outputs"][0]
    assert card["refresh"] == {"status": "planned", "note": "Create refreshes the model once; nothing else is run or scheduled."}
    assert card["permissions"]["execute"].startswith("Create refreshes the model once")
    assert fake.refreshed == []


def test_the_dry_run_without_the_permission_says_which_one(make):
    client, fake, priv, _ = make(scp=WITHOUT_REFRESH)
    r = _build(client, priv, [MODEL], dry_run=True, skip_built=False)["outputs"][0]["refresh"]
    assert r["status"] == "planned" and r["scope"] == "Dataset.ReadWrite.All" and r["entra_steps"]


def test_a_model_the_create_did_not_just_make_is_never_refreshed(make):
    """Built from this plan earlier (already built), and updated in place: neither is refreshed."""
    client, fake, priv, _ = make()
    created = _build(client, priv, [MODEL])["created"]
    fake.refreshed.clear()
    again = _build(client, priv, [MODEL], created)["outputs"][0]
    assert again["already_built"] and "refresh" not in again
    old = [{"id": "sm-old", "displayName": "demo_lh_model_old", "type": "SemanticModel",
            "description": "Created by Krusgraph [Krusgraph plan plan-0123456789ab, schema Shop (sha256:00112233aabbccdd), 6 links]"}]
    fake.items += old
    o = {"kind": "semantic_model", "name": "demo_lh_model_old"}
    dry = _build(client, priv, [o], dry_run=True, update=["semantic_model"], skip_built=False)["outputs"][0]
    assert dry["would"] == "update" and "refresh" not in dry
    upd = _build(client, priv, [o], update=["semantic_model"], confirm={"semantic_model": dry["confirm_update"]})["outputs"][0]
    assert upd["would"] == "update" and "refresh" not in upd, upd.get("refusal") or upd["answer"].get("error")
    assert fake.refreshed == []


# ------------------------------------------------------------------ (b) the title names the model -----------------

def test_a_report_on_a_model_given_by_id_is_titled_with_the_models_name(make):
    client, fake, priv, _ = make()
    created = _build(client, priv, [MODEL])["created"]
    _build(client, priv, [MODEL, {"kind": "report", "name": "demo_lh_report2", "model": NEW_SM}], created, only=["report"])
    body = next(c["body"] for c in fake.created if c["route"] == "reports")
    import base64
    parts = {p["path"]: base64.b64decode(p["payload"]).decode() for p in body["definition"]["parts"]}
    texts = [json.dumps(json.loads(p), ensure_ascii=False) for k, p in parts.items() if k.endswith("visual.json") and '"textbox"' in p]
    assert any("Overview · demo_lh_model3" in t for t in texts)
    assert not any(NEW_SM in t for t in texts)
    assert body["description"].endswith("demo_lh_model3")


# ------------------------------------------------------------------ (c) the text fits ----------------------------

def _shop_page():
    from fabric_backend import model_compare
    from fabric_backend.lineage import decode_parts
    model = model_compare.from_tmdl(decode_parts(gs._model_parts()))
    return model, report.definition_parts(model, NEW_SM, model_name="demo_lh_model3")


def test_the_cards_captions_and_the_slicers_title_fit_at_1280_by_720():
    model, drawn = _shop_page()
    vs = report.visuals(model, "demo_lh_model3")["visuals"]
    listed = {v["title"]: v for v in drawn["visuals"]}
    cards = [v for v in vs if v["type"] == "card"]
    slicers = [v for v in vs if v["type"] == "slicer"]
    assert cards and slicers
    for v in cards + slicers:
        pos = listed[v["title"]]["position"]
        assert report.text_problems(v, pos) == [], v["title"]
        assert pos["x"] + pos["width"] <= report.PAGE_W and pos["y"] + pos["height"] <= report.PAGE_H
    # the founder's captions and slicer title, at the sizes of 9 November, did not fit
    card = {"type": "card", "title": "Order lines", "measure": {"measure": "Rows in order_items"}}
    assert report.text_problems(card, {"x": 0, "y": 0, "width": 400, "height": 72}) != []
    slicer = {"type": "slicer", "title": "Category name"}
    assert report.text_problems(slicer, {"x": 0, "y": 0, "width": 220, "height": 44}) != []
    assert report.text_problems(slicer, {"x": 0, "y": 0, "width": 220, "height": report.TITLE_H}) == []


def test_the_card_and_slicer_set_their_font_sizes_and_the_slicer_header_is_off():
    _, drawn = _shop_page()
    parts = {k: json.loads(v) for k, v in drawn["parts"].items() if k.endswith("visual.json")}
    cards = [p["visual"] for p in parts.values() if p["visual"]["visualType"] == "card"]
    slicers = [p["visual"] for p in parts.values() if p["visual"]["visualType"] == "slicer"]
    for c in cards:
        assert c["objects"]["categoryLabels"][0]["properties"]["show"] == {"expr": {"Literal": {"Value": "true"}}}
        assert c["objects"]["labels"][0]["properties"]["fontSize"] == {"expr": {"Literal": {"Value": "24D"}}}
        assert c["visualContainerObjects"]["title"][0]["properties"]["fontSize"] == {"expr": {"Literal": {"Value": "11D"}}}
    for s in slicers:
        assert s["objects"]["header"][0]["properties"]["show"] == {"expr": {"Literal": {"Value": "false"}}}


def test_a_long_measure_name_gets_a_smaller_caption_rather_than_being_cut():
    assert report.caption_pt("Rows in order_items", 400) == report.CARD_CAPTION_PT
    long = "Distinct customers with a delivered order"
    assert report.caption_pt(long, 300) < report.CARD_CAPTION_PT
