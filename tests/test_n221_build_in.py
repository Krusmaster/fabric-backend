"""Round n221, the founder's live test of 11 November 2026 (server 17a6a36).

1. Where outputs are built. A new Krusgraph Model item in a new workspace (demo_Sandvik) read the lakehouse demo_lh of
   the workspace demo; the dry run said "Create makes 0 of 5; 5 already built from this plan" and linked to the items in
   demo. Now the Model builds in its own workspace by default (target.workspace, which the editor sends: buildPlace.ts):
   every item is created there, "already built from this plan" is looked up there, silver and gold go to a lakehouse
   there (chosen, made by Create when ticked, after a dry run that names it and makes nothing) and the notebooks read
   demo_lh through OneLake. The source's workspace stays a choice and builds as before.
2. Silver and the check. After Check against the rows passed every key, the silver cards still said "every row kept: key
   ... not checked". The review's passing checks (and its accepted keys) now reach the plan the build uses: silver
   de-duplicates on them and the card says "one row per key: key ... checked against the rows on <date>".

Fabric REST is the shop double of tests/test_workload_plans.py (workspace demo) next to a second, empty workspace."""
import base64
import json
import uuid
from dataclasses import replace

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from test_workload_api import SRC, keys  # noqa: E402,F401
from test_workload_create import _post, _review, make  # noqa: E402,F401
from test_workload_plans import Defined  # noqa: E402
from test_n208_guessed_keys import INFO, schema  # noqa: E402
from fabric_backend import data_flow, product_life, silver, workload_api  # noqa: E402
from fabric_backend.infer import plan  # noqa: E402

SANDVIK = "99999999-8888-7777-6666-555555555555"                     # the Model item's own, new workspace
OUTPUTS = [
    {"kind": "silver_notebook", "name": "demo_lh_silver"},
    {"kind": "gold_views", "name": "demo_lh_gold"},
    {"kind": "pipeline", "name": "demo_lh_pipeline"},
    {"kind": "semantic_model", "name": "demo_lh_model"},
    {"kind": "graphql", "name": "demo_lh_api"},
]
ROUTES = {"notebooks": "Notebook", "dataPipelines": "DataPipeline", "semanticModels": "SemanticModel",
          "graphQLApis": "GraphQLApi", "ontologies": "Ontology", "lakehouses": "Lakehouse", "reports": "Report"}


class TwoWorkspaces(Defined):
    """demo (gs.WS) is the shop double with every output already built there from this plan, as in the founder's test;
    demo_Sandvik answers List Items, the creates (each item listed with a GUID), Get Lakehouse, descriptions and
    definitions. `sandvik` is its items; `sent` lists (method, workspace, route) of every write."""

    def __init__(self, sandvik_items=()):
        super().__init__()
        self.sandvik = [dict(x) for x in sandvik_items]
        self.sandvik_defs: dict[str, list] = {}
        self.sent: list[tuple[str, str, str]] = []

    def _route(self, method, url, body=None):
        path = url.split("?")[0]
        if method == "GET" and path.endswith("/v1/workspaces"):
            self.calls.append((method, path))
            return gs.Response(200, {"value": [{"id": gs.WS, "displayName": "demo", "type": "Workspace"},
                                               {"id": SANDVIK, "displayName": "demo_Sandvik", "type": "Workspace"}]})
        if f"/workspaces/{SANDVIK}" not in path:
            if method in ("POST", "PATCH") and not path.endswith("/getDefinition"):
                self.sent.append((method, "demo", path.split(f"/workspaces/{gs.WS}/")[-1]))
            return super()._route(method, url, body)
        self.calls.append((method, path))
        rest = path.split(f"/workspaces/{SANDVIK}/")[-1].split("/") if f"/workspaces/{SANDVIK}/" in path else []
        if method in ("POST", "PATCH") and rest[-1:] != ["getDefinition"]:
            self.sent.append((method, "demo_Sandvik", "/".join(rest)))
        want = url.split("type=")[-1] if "type=" in url else None
        if method == "GET" and rest == ["items"]:
            return gs.Response(200, {"value": [i for i in self.sandvik if want in (None, i["type"])]})
        if method == "GET" and len(rest) == 2 and rest[0] == "lakehouses":
            it = next((i for i in self.sandvik if i["id"] == rest[1]), None)
            if not it:
                return gs.Response(404, {"errorCode": "EntityNotFound"})
            return gs.Response(200, {**it, "properties": {"defaultSchema": "dbo", "oneLakeTablesPath":
                                                          f"https://onelake.dfs.fabric.microsoft.com/{SANDVIK}/{it['id']}/Tables"}})
        if method == "GET" and len(rest) == 2 and rest[0] == "items":
            it = next((i for i in self.sandvik if i["id"] == rest[1]), None)
            return gs.Response(200, it) if it else gs.Response(404, {"errorCode": "EntityNotFound"})
        if method == "PATCH" and len(rest) == 2 and rest[0] == "items":
            for it in self.sandvik:
                if it["id"] == rest[1]:
                    it["description"] = body["description"]
            return gs.Response(200, {"id": rest[1], **body})
        if method == "POST" and rest[-1:] == ["getDefinition"] and rest[-2] in self.sandvik_defs:
            return gs.Response(200, {"definition": {"parts": self.sandvik_defs[rest[-2]]}})
        if method == "POST" and rest[-1:] == ["updateDefinition"]:
            return gs.Response(200, None)
        if method == "POST" and len(rest) == 1 and rest[0] in ROUTES:
            iid = str(uuid.uuid4())
            self.sandvik.append({"id": iid, "displayName": body.get("displayName"), "type": ROUTES[rest[0]],
                                 "description": body.get("description", ""), "workspaceId": SANDVIK})
            if isinstance(body.get("definition"), dict):
                self.sandvik_defs[iid] = body["definition"]["parts"]
            return gs.Response(201, {"id": iid, "displayName": body.get("displayName"), "workspaceId": SANDVIK})
        return gs.Response(404, {"errorCode": "EntityNotFound", "message": f"no route {method} /{'/'.join(rest)}"})


def _in(where="item", **more) -> dict:
    return {"target": {"lakehouse": None, "workspace": SANDVIK if where == "item" else gs.WS, "where": where, **more}}


def _built_in_demo(client, priv, rv) -> list[dict]:
    """The founder's starting point: every output built in demo, from this plan, by an earlier Create."""
    created = []
    for o in OUTPUTS:
        out = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "only": [o["kind"]], "dry_run": False,
                                       "created": created, "skip_built": True}, priv).json()
        created += out["outputs"][0]["created"]
    return created


def _writes(fake) -> list:
    return list(fake.sent)


# ------------------------------------------------------------------ 1. where the outputs are built -------------------

def test_a_model_in_a_new_workspace_builds_there_not_in_the_sources_workspace(make):
    client, fake, priv = make(TwoWorkspaces([{"id": str(uuid.uuid4()), "displayName": "sandvik_lh", "type": "Lakehouse"}]))
    rv = _review(client, priv)
    earlier = _built_in_demo(client, priv, rv)
    assert {c["workspace"] for c in earlier} == {gs.WS}

    fake.sent.clear()
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "created": earlier,
                                   "product": {"name": "Sandvik"}, **_in()}, priv).json()
    assert dry["build_in"]["workspace_id"] == SANDVIK and dry["build_in"]["cross"] is True and dry["build_in"]["where"] == "item"
    assert dry["build_in"]["words"].startswith("Builds in the workspace demo_Sandvik (this item's workspace")
    # nothing is "already built from this plan" in demo_Sandvik, though all five are in demo
    assert [c["decision"]["action"] for c in dry["outputs"]] == ["create"] * len(OUTPUTS), [c.get("decision") for c in dry["outputs"]]
    assert not _writes(fake), _writes(fake)
    silver_card = dry["outputs"][0]["answer"]
    assert silver_card["target"]["workspace_id"] == SANDVIK and silver_card["target"]["lakehouse"] == "sandvik_lh"
    # demo_lh is read through OneLake: its oneLakeTablesPath (the double's) in the abfss form
    assert 'MIRROR_TABLES_PATH = "abfss://x@onelake.dfs.fabric.microsoft.com/y/Tables"' in silver_card["notebook"]["content"]
    assert "The source is the lakehouse demo_lh in another workspace: its tables are read through OneLake" in silver_card["notebook"]["content"]
    assert "# The source is the lakehouse demo_lh in another workspace: its tables are read by their OneLake path" in silver_card["notebook"]["content"]
    assert "read-only" not in silver_card["notebook"]["content"].split("MIRROR_TABLES_PATH")[0].split("Silver tables for")[-1]
    assert SANDVIK in json.dumps(silver_card["rest"])

    created = []
    for o in OUTPUTS:
        out = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "only": [o["kind"]], "dry_run": False,
                                       "created": earlier + created, "skip_built": True, **_in()}, priv).json()
        card = out["outputs"][0]
        assert card["decision"]["action"] == "create" and card.get("created"), card
        created += card["created"]
    assert {c["workspace"] for c in created} == {SANDVIK}
    in_demo = [x for x in _writes(fake) if x[1] == "demo" and SANDVIK not in x[2]]   # the refresh: Power BI groups/<demo_Sandvik>
    assert in_demo == [], in_demo                                   # nothing written in demo
    names = {i["displayName"] for i in fake.sandvik}
    assert {"demo_lh_silver", "demo_lh_gold", "demo_lh_pipeline", "demo_lh_model", "demo_lh_api"} <= names

    # the next dry run there: everything is already built from this plan, in demo_Sandvik
    again = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "created": earlier + created,
                                     **_in()}, priv).json()
    assert [c["decision"]["action"] for c in again["outputs"]] == ["skip"] * len(OUTPUTS)
    assert {x["workspace"] for c in again["outputs"] for x in c.get("created", [])} == {SANDVIK}


def test_the_sources_workspace_is_still_a_choice_and_builds_beside_it(make):
    client, fake, priv = make(TwoWorkspaces())
    rv = _review(client, priv)
    earlier = _built_in_demo(client, priv, rv)
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "created": earlier,
                                   **_in("source")}, priv).json()
    assert dry["build_in"]["workspace_id"] == gs.WS and dry["build_in"]["cross"] is False
    assert dry["build_in"]["words"].startswith("Builds in the workspace demo (the source's workspace")
    assert [c["decision"]["action"] for c in dry["outputs"]] == ["skip"] * len(OUTPUTS)   # per workspace: built in demo


def test_a_new_workspace_without_a_lakehouse_needs_a_choice_or_consent(make):
    client, fake, priv = make(TwoWorkspaces())
    rv = _review(client, priv)
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:1], "dry_run": True, "created": [], **_in()}, priv).json()
    err = dry["outputs"][0]["answer"]
    assert err["kind"] == "not_found" and "has no lakehouse" in err["error"] and "Create a lakehouse" in err["error"]
    assert not _writes(fake)


def test_create_makes_the_lakehouse_only_when_ticked_once_and_after_the_dry_run_named_it(make):
    client, fake, priv = make(TwoWorkspaces())
    rv = _review(client, priv)
    tick = _in(create_lakehouse="demo_lh_krusgraph")
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:3], "dry_run": True, "created": [], **tick}, priv).json()
    t = dry["outputs"][0]["answer"]["target"]
    assert t["how"] == "create" and t["lakehouse"] == "demo_lh_krusgraph" and "Create makes it first" in t["words"]
    assert not _writes(fake)                                        # the dry run makes nothing
    created = []
    for o in OUTPUTS[:3]:
        out = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:3], "only": [o["kind"]], "dry_run": False,
                                       "created": created, "skip_built": True, **tick}, priv).json()
        created += out["outputs"][0]["created"]
    made = [x for x in fake.sent if x[2] == "lakehouses"]
    assert len(made) == 1                                           # one lakehouse for the three requests
    lh = next(i for i in fake.sandvik if i["type"] == "Lakehouse")
    assert lh["displayName"] == "demo_lh_krusgraph"
    assert {c["workspace"] for c in created} == {SANDVIK}
    nb = fake.sandvik_defs[next(c["id"] for c in created if c["name"] == "demo_lh_silver")]
    text = base64.b64decode(next(p["payload"] for p in nb if p["path"] == "notebook-content.py")).decode()
    assert lh["id"] in text and SANDVIK in text                     # attached to the lakehouse it made, as its default


def test_the_request_names_the_build_workspace_as_a_guid():
    base = {**SRC, "review": {}, "outputs": [{"kind": "graphql", "name": "x_api"}]}
    with pytest.raises(workload_api.BadRequest):
        workload_api.build_request({**base, "target": {"workspace": "demo_Sandvik"}})
    with pytest.raises(workload_api.BadRequest):
        workload_api.build_request({**base, "target": {"workspace": SANDVIK, "create_lakehouse": "1 bad name"}})
    got = workload_api.build_request({**base, "target": {"workspace": SANDVIK.upper(), "where": "item", "create_lakehouse": "lh_new"}})
    assert got["target"] == {"lakehouse": None, "workspace": SANDVIK, "where": "item", "create_lakehouse": "lh_new"}


def test_delete_stays_in_the_data_products_workspace(make):
    """n210: Retire's delete goes only to the items in the data product's workspace; the editor sends the build's."""
    items = [{"id": str(uuid.uuid4()), "type": "Notebook", "name": "s", "workspace": SANDVIK, "output": "silver_notebook"},
             {"id": str(uuid.uuid4()), "type": "Notebook", "name": "s", "workspace": gs.WS, "output": "silver_notebook"}]
    listings = {SANDVIK: {items[0]["id"]: {"id": items[0]["id"], "type": "Notebook", "displayName": "s"}},
                gs.WS: {items[1]["id"]: {"id": items[1]["id"], "type": "Notebook", "displayName": "s"}}}
    got = product_life.retire(lambda *a, **k: None, {"workspace": SANDVIK, "scope": "delete", "dry_run": True, "items": None,
                                                    "product": "p", "outputs": {"created": items, "removed": [], "pending": []}},
                              listings, None)
    ids = json.dumps(got)
    assert items[0]["id"] in ids and "another workspace" in ids


# ------------------------------------------------------------------ 2. the row check reaches silver -------------------

def test_a_key_that_passed_the_row_check_deduplicates_silver_and_the_card_says_so():
    p = plan(schema())
    key = list(p.keys["sales"][0])
    rv = {"items": [{"id": "key:sales", "type": "key", "table": "sales", "columns": key, "rule": "K4", "review": "proposed",
                     "check": {"status": "passed", "checked_at": "2026-11-11T09:40Z"}},
                    {"id": "key:invoice_lines", "type": "key", "table": "invoice_lines", "columns": ["no"], "rule": "K2",
                     "review": "accepted", "check": {"status": "not_checked"}}]}
    checked = workload_api.checked_keys(rv)
    assert checked["sales"] == {"columns": key, "how": "rows", "checked_at": "2026-11-11T09:40Z"}
    assert checked["invoice_lines"]["how"] == "accepted"
    s = silver.spec(replace(p, checked_keys=checked), INFO)
    by = {t["table"]: t for t in s["tables"]}
    assert by["sales"]["dedupe"] is True and by["invoice_lines"]["dedupe"] is True
    assert by["sales"]["key_basis"].startswith("checked against the rows on 11 November 2026")
    assert {x["table"] for x in silver.not_deduplicated(s)} & {"sales", "invoice_lines"} == set()
    nodes, _ = data_flow.silver_nodes(s, True)
    lines = {n["table"]: n["lines"] for n in nodes}
    assert lines["sales"][0] == "one row per key: key customer_id + product_id + store_id checked against the rows on 11 November 2026"
    assert lines["invoice_lines"][0] == "one row per key: key no accepted in the review"
    cell = next(c for k, c in silver.cells(s) if c.startswith("# ---- sales -> "))
    assert "keep_latest(" in cell and "checked against the rows on 11 November 2026" in cell


def test_a_stale_failed_or_rejected_check_or_other_columns_leave_every_row():
    p = plan(schema())
    key = list(p.keys["sales"][0])
    for item in ({"check": {"status": "stale", "was": "passed"}, "review": "proposed"},
                 {"check": {"status": "failed"}, "review": "proposed"},
                 {"check": {"status": "passed", "checked_at": "2026-11-11T09:40Z"}, "review": "rejected"}):
        rv = {"items": [{"id": "key:sales", "type": "key", "table": "sales", "columns": key, "rule": "K4", **item}]}
        s = silver.spec(replace(p, checked_keys=workload_api.checked_keys(rv)), INFO)
        assert next(t for t in s["tables"] if t["table"] == "sales")["dedupe"] is False, item
    other = {"sales": {"columns": ["customer_id"], "how": "rows", "checked_at": "2026-11-11T09:40Z"}}
    assert next(t for t in silver.spec(replace(p, checked_keys=other), INFO)["tables"] if t["table"] == "sales")["dedupe"] is False


def test_the_build_passes_the_editors_check_into_the_silver_dry_run(make):
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    plain = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:1], "dry_run": True, "created": []}, priv).json()
    guessed = [t for t in plain["outputs"][0]["answer"].get("not_deduplicated", [])]
    for it in rv["items"]:                                          # Check against the rows passed every key
        if it["type"] == "key":
            it["check"] = {"status": "passed", "checked_at": "2026-11-11T09:40Z", "result": {"rows": 5, "nulls": 0, "distinct": 5}}
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": OUTPUTS[:3], "dry_run": True, "created": []}, priv).json()
    assert "not_deduplicated" not in dry["outputs"][0]["answer"]
    lines = [ln for n in dry["flow"]["nodes"] if n["column"] == "silver" for ln in n["lines"]]
    assert not any("not checked" in ln for ln in lines), lines
    if guessed:                                                     # what was guessed before is checked now
        assert any("checked against the rows on 11 November 2026" in ln for ln in lines), lines
