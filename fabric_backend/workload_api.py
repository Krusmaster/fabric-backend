"""The engine API of the Fabric workload, phase 1 (n166; docs/WORKLOAD-FEASIBILITY.md sections 2-3 and "Phase 1").

The "Krusgraph Model" item (workload/) is an editor that Fabric shows in an iframe. It cannot read a lakehouse's
columns itself (the SQL analytics endpoint speaks TDS), so it calls two routes here with a Bearer token that the Fabric
host issued for the workload's own Entra app (entra.WorkloadConfig, a separate audience from the MCP app):

  POST /workload/v1/review   source -> the review file (review.py): keys and relationships with their rules, review
                             and check status; with `previous` (the item's saved review.json) the decisions carry over
  POST /workload/v1/check    n173: the review checked against the rows (validate_plan's counting queries): each key and
                             relationship passed, failed (with its orphans, duplicates or empty keys) or not checked,
                             written into the review file; with the map and Thinker's questions
  POST /workload/v1/build    the reviewed plan -> an API for GraphQL item (create_backend's path); dry_run defaults to
                             true and then nothing is written. n174: with outputs [{kind, name}], every output the MCP
                             tools build (KINDS), one card each, a data product over them and the data flow drawn

Every call runs as the signed-in user: the token is exchanged on-behalf-of the user (entra.OnBehalfOf, the same code
the MCP server uses) for Fabric and SQL tokens, so Fabric's own permissions decide what the user may read or create.
Nothing is stored here. Answers carry names, types, rules, decisions and counts, never a row value, a token or a secret.

Browsers may call these routes only from Fabric's own domains (CORS) and the answers may only be framed by them (CSP
frame-ancestors). The routes exist only when the KRUSGRAPH_WORKLOAD_* variables are set (server.build_app).

n171: with KRUSGRAPH_ENTITLEMENTS=1, /build with dry_run=false runs the same licence check as the MCP tools
(entitlements.check for create_backend on the token's tid); with KRUSGRAPH_MARKETPLACE=1 as well, a tenant without an
active Marketplace subscription gets `kind: upgrade` (HTTP 402) with the offer's link, which the editor shows as it shows
every error (error and hint). /review and every dry run stay free. With the flags off nothing here changes.

n213: with KRUSGRAPH_TRIAL=1 (billing.py) every route records the organisation's call (the first one starts its 30-day
trial) and billing.decide replaces the licence check: after the trial, without an active subscription, /build and
/product retire with dry_run=false answer `kind: upgrade` (HTTP 402) with the days and the offer's link; every read,
check and dry run still runs. POST /workload/v1/access gives the editor its one quiet line. Off, nothing changes.

n173: /review takes the person's own `keys` and `confirmed` (the editor's inline answers to Thinker's questions: a key
for a table the rules found none for, the table an ambiguous column points at); every answer carries `map`, the MCP
Apps cards' map data (mcp_apps_pictures.map_from_review) with each key's check state added, which the editor draws
with the cards' own drawing code (workload/scripts/build_card_map.py). /check is free like /review: it counts, it
never writes to Fabric, and its answer holds counts and verdicts, never a row value.

n174 (run_build_many): each output goes through its own MCP tool function (create_silver_notebook, create_gold_views,
create_pipeline, create_semantic_model, create_report, create_backend, create_ontology, create_data_agent with
publish=false), called as the tool is called, inside server.plan_scope so every plan has the review's rejections left out
and the lakehouse is read once. An item of the same name that this Model did not build (outputs.json's created ids) is
never written, and a report is never updated. The token's delegated permissions (its scp claim) are compared with what
each output needs: the dry run says what is missing, Create refuses that output with kind consent and the Entra steps.
Nothing runs or is scheduled; no Execute permission is used. The data product is domain_draft's proposal with the
build's own items; the flow is data_flow.py's, from the same drafts.

n180: "already built" means built from this plan. Every item a Create writes records the plan it was built from (plan id,
schema fingerprint, exact schema name, links after the review) in outputs.json's created[].plan and as a marker at the
end of its Fabric description. On a re-run an item recorded with another plan, or with none (built before n180), is not
skipped as built: its card says which plan it was built from and offers Update (where the tool updates in place; the
dry run first, whose confirm_update the Create must send back) or a new name. Cards of existing items carry what the
item holds where one read of its definition says it (existing_counts), never a zero for what was not read.

n181: one more output, App (Rayfin, preview) (rayfin_app.py, docs/RAYFIN-APP.md). The tenant setting "Enable Fabric App
Items (preview)" is checked before the source is read (off: the admin card, nothing more); the ticked key figures, list
pages and charts come as outputs[].app; the dry run gives the pages, the read-only connector and its API with every
link, the package and the commands; Create makes the empty App item by Create App Backend (the only documented call)
and records it like every other output. Fabric's 403 "The feature is not available" is the same admin card.

n185: two choices on the pipeline, both off unless ticked (outputs[].jobs = {run_once, schedule}): Run once starts one
run after the pipeline and its notebooks exist, and Schedule adds a daily or every-N-hours schedule, or updates the one
this Model made (outputs.json's schedule ids, sent as schedule_ids); a schedule it did not make is never touched
(pipeline_jobs.py, which cites the Job Scheduler APIs). Both need DataPipeline.Execute.All (or Item.Execute.All) on the
workload app: without it the card's `jobs.permission` says so with the Entra steps and the manual Fabric steps, and
Create builds the pipeline and runs or schedules nothing. Create does not wait for the run: the editor reads it with
POST /workload/v1/pipeline-run, so no other card waits for it.

n185, the data agent (the founder's additions 1 to 4 of 9 November 2026): outputs[].agent = {layer, publish, copilot}.
The agent reads one layer: the silver tables when they are in the lakehouse (the default), the gold views as an option,
else the source tables, and never two (data_agent.select_layer). "Publish the agent in Fabric" and "Also make it
available in Microsoft 365 Copilot" are separate ticks, both off; Copilot needs Publish ticked first. Publishing in
Fabric (Items_PublishDataAgent) happens only when ticked, when the agent reads one layer, and, with Run once ticked, after
that run succeeded: Create starts the run without waiting, so the editor sends the agent once more with
after_run {status} when it has read the run's end (agent_publish.decide). Microsoft 365 Copilot has no documented API:
its card is the preflight (agent_publish.copilot_preflight: capacity SKU, tenant settings, licences, each with Learn's
link, Unverified where it cannot be read) and the portal step. Nothing is ever retried in a loop.
n209: with Run once ticked, the examples are "not checked yet" until the after_run call of a run that succeeded checks
them (a run that did not succeed leaves them not checked and publishes nothing); an example Fabric could not connect
for is sent once more, exactly once, and then reads "not checked yet" with the reason, never invalid (recheck_examples).
n222 (the founder's live test of 11 November 2026, "it must go faster, and I want suggestions on which data products to
create"): a dry run prepares its outputs side by side (the report after its model) and says how many are prepared; every
build lists the workspace's items once (deploy.one_listing); /review and /check answer suggested_products, domain_draft's
proposal in the editor's words (suggest_products), and the ticked ones come back on the dry run as data products.
"""
from __future__ import annotations

import contextvars
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sys
import time

from .deploy import list_items as _list_items, one_listing as _one_listing, outside_listing as _outside_listing

PREFIX = "/workload/v1"
FABRIC_ORIGIN = re.compile(r"^https://([a-z0-9-]+\.)*(fabric\.microsoft\.com|powerbi\.com)$")
FRAME_ANCESTORS = "https://*.fabric.microsoft.com https://*.powerbi.com"
SECURITY_HEADERS = {
    "Content-Security-Policy": f"default-src 'none'; frame-ancestors {FRAME_ANCESTORS}",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}
OUTPUTS = {"graphql": "API for GraphQL"}
# n174: every output the MCP tools can build, in the order a build runs them and the preview shows them: the data flow
# (silver, gold, pipeline), then the model before its report, the API, the ontology and the data agent. `needs` is the
# delegated permissions, each a tuple of alternatives (Item.ReadWrite.All covers every item type); none is an Execute
# permission, since nothing here runs or schedules a notebook or a pipeline. `updates`: the tool updates an item of that
# name in place (a report is never updated: create_report refuses a name that exists).
NOTEBOOK = ("Notebook.ReadWrite.All", "Item.ReadWrite.All")
KINDS = {
    "silver_notebook": {"label": "Silver notebook", "type": "Notebook", "tool": "create_silver_notebook", "updates": True,
                        "needs": (NOTEBOOK,), "suffix": "silver"},
    "gold_views": {"label": "Gold views", "type": "Notebook", "tool": "create_gold_views", "updates": True,
                   "needs": (NOTEBOOK,), "suffix": "gold"},
    "pipeline": {"label": "Pipeline", "type": "DataPipeline", "tool": "create_pipeline", "updates": True,
                 "needs": (NOTEBOOK, ("DataPipeline.ReadWrite.All", "Item.ReadWrite.All")), "suffix": "pipeline"},
    "semantic_model": {"label": "Semantic model", "type": "SemanticModel", "tool": "create_semantic_model", "updates": True,
                       "needs": (("SemanticModel.ReadWrite.All", "Item.ReadWrite.All"),), "suffix": "model"},
    "report": {"label": "Report", "type": "Report", "tool": "create_report", "updates": False,
               "needs": (("Report.ReadWrite.All", "Item.ReadWrite.All"), ("SemanticModel.ReadWrite.All", "Item.ReadWrite.All")),
               "suffix": "report"},
    "graphql": {"label": "API for GraphQL", "type": "GraphQLApi", "tool": "create_backend", "updates": True,
                "needs": (("GraphQLApi.ReadWrite.All", "Item.ReadWrite.All"),), "suffix": "api"},
    "ontology": {"label": "Ontology", "type": "Ontology", "tool": "create_ontology", "updates": True,
                 "needs": (("Item.ReadWrite.All",),), "suffix": "ontology"},
    "data_agent": {"label": "Data agent", "type": "DataAgent", "tool": "create_data_agent", "updates": True,
                   "needs": (("DataAgent.ReadWrite.All", "Item.ReadWrite.All"),), "suffix": "agent"},
    # n181: the App item (AppBackend, preview) by Create App Backend (Item.ReadWrite.All); its pages, read-only connector
    # and GraphQL API go in with the package and `rayfin up` (rayfin_app.py). Never updated: an App of that name is not
    # rebuilt, a new name is offered.
    "rayfin_app": {"label": "App (Rayfin, preview)", "type": "AppBackend", "tool": "rayfin_connector", "updates": False,
                   "needs": (("Item.ReadWrite.All",),), "suffix": "app"},
}
ORDER = tuple(KINDS)
WORKLOAD_APP_NAME = "Krusgraph workload (dev)"
_PRODUCT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
STATUS = {"bad_request": 400, "bad_input": 400, "sign_in": 401, "sql_sign_in": 401, "mfa": 401, "consent": 403,
          "no_access": 403, "feature_disabled": 403, "not_found": 404, "schema_not_found": 404, "table_not_found": 404,
          "would_remove": 409, "already_exists": 409, "capacity": 409, "source_not_ready": 409, "rate_limited": 429,
          "throttled": 429, "server_config": 500, "timeout": 504, "upgrade": 402}
NOTHING_CHANGED = "Nothing was created or changed in Fabric."
_NAME = re.compile(r"^[A-Za-z0-9_]{1,123}$")


class BadRequest(ValueError):
    pass


def log(event: str, **fields) -> None:
    """n179: one JSON line on the console (Log Analytics when the deploy sends console logs there): what the workload
    routes did and why a call failed, so 'Failed to fetch' in the browser can be matched to a cause. Names of routes,
    outputs, kinds and durations only: no token, no body, no table contents, no item names."""
    try:                                                          # the process's peak memory so far, to tell an OOM restart
        import resource
        fields.setdefault("peak_rss_mb", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024))
    except (ImportError, OSError):
        pass
    line = json.dumps({"krusgraph": "workload", "event": event, **fields}, default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ------------------------------------------------------------------ request checks -----------------------------------

def _text(body: dict, key: str, default: str | None = None, limit: int = 200) -> str:
    v = body.get(key, default)
    if not isinstance(v, str) or not v.strip() or len(v) > limit:
        raise BadRequest(f"{key!r} is required: a non-empty text of at most {limit} characters")
    return v.strip()


def _source(body: dict) -> dict:
    """workspace and source as ids (what the editor's lakehouse picker gives), source_name for the review file."""
    return {"workspace": _text(body, "workspace"), "source": _text(body, "source"),
            "source_name": _text(body, "source_name", body.get("source")), "schema": _text(body, "schema", "dbo", 128)}


def schemas_request(body) -> dict:
    """n179: workspace and source (ids, from the lakehouse picker); the schema is what this call lists."""
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    return {"workspace": _text(body, "workspace"), "source": _text(body, "source"),
            "source_name": _text(body, "source_name", body.get("source"))}


def review_request(body) -> dict:
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    req = _source(body)
    prev, decisions = body.get("previous"), body.get("decisions") or []
    if prev is not None and not isinstance(prev, dict):
        raise BadRequest("'previous' must be the saved review.json object or null")
    if not isinstance(decisions, list) or not all(isinstance(d, dict) and isinstance(d.get("item"), str) for d in decisions):
        raise BadRequest("'decisions' must be a list of {item, review, reason}")
    return {**req, "previous": prev, "decisions": decisions, **_keys_and_confirmed(body)}


def _keys_and_confirmed(body: dict) -> dict:
    keys, confirmed = body.get("keys"), body.get("confirmed")
    if keys is not None and not (isinstance(keys, dict) and all(
            isinstance(t, str) and isinstance(c, list) and c and all(isinstance(x, str) for x in c) for t, c in keys.items())):
        raise BadRequest("'keys' must be {table: [column, ...]} or null")
    fields = ("source", "source_cols", "target", "target_cols")
    if confirmed is not None and not (isinstance(confirmed, list) and all(
            isinstance(c, dict) and isinstance(c.get("source"), str) and isinstance(c.get("target"), str)
            and all(isinstance(c.get(f), list) and c[f] for f in fields[1::2]) for c in confirmed)):
        raise BadRequest("'confirmed' must be a list of {source, source_cols, target, target_cols} or null")
    return {"keys": keys or None, "confirmed": [{f: c[f] for f in fields} for c in confirmed] if confirmed else None}


def check_request(body) -> dict:
    """n173: the source, the item's review.json (the decisions and corrections to check) and max_items (default 60)."""
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    req = _source(body)
    if not isinstance(body.get("review"), dict):
        raise BadRequest("'review' (the item's review.json) is required: the check counts what the review holds")
    n = body.get("max_items", 60)
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 200:
        raise BadRequest("'max_items' must be a whole number from 1 to 200 (default 60)")
    return {**req, "review": body["review"], "max_items": n}


def _item_name(v, what: str) -> str:
    if not isinstance(v, str) or not _NAME.match(v.strip()):
        raise BadRequest(f"{what} {v!r}: letters, digits and underscores only, at most 123")
    return v.strip()


def build_request(body) -> dict:
    """Two forms. Phase 1 (n166): name plus outputs ["graphql"], answered as before. n174: outputs as a list of
    {kind, name} (report: model, the name or id of an existing semantic model, or omitted for the one this build makes),
    with product {name} to bundle them and created (outputs.json's created ids: the items this Model may update)."""
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    req = _source(body)
    dry_run = body.get("dry_run", True)
    if not isinstance(dry_run, bool):
        raise BadRequest("'dry_run' must be true or false (default true)")
    outputs = body.get("outputs", ["graphql"])
    if not isinstance(outputs, list) or not outputs:
        raise BadRequest("'outputs' must be a non-empty list of {kind, name}")
    if all(isinstance(o, str) for o in outputs):                 # phase 1's form
        name = _item_name(_text(body, "name", limit=123), "item name")
        unknown = [o for o in outputs if o not in OUTPUTS]
        if unknown:
            raise BadRequest(f"unknown output: {', '.join(map(str, unknown))}. With a name and a list of kinds the build makes an "
                             f"API for GraphQL; send outputs as [{{kind, name}}] for {', '.join(k for k in ORDER if k != 'graphql')}.")
        if not isinstance(body.get("review"), dict):
            raise BadRequest("'review' (the item's review.json) is required: the build uses its decisions")
        return {**req, "name": name, "outputs": outputs, "dry_run": dry_run, "review": body["review"], "form": 1}
    chosen = []
    for o in outputs:
        if not isinstance(o, dict) or o.get("kind") not in KINDS:
            raise BadRequest(f"each output is {{kind, name}} with kind one of {', '.join(ORDER)}; got {o!r}")
        if any(c["kind"] == o["kind"] for c in chosen):
            raise BadRequest(f"{o['kind']} is chosen twice; one of each per build")
        c = {"kind": o["kind"], "name": _item_name(o.get("name"), KINDS[o["kind"]]["label"] + " name")}
        if o["kind"] == "rayfin_app" and o.get("app") is not None:     # n181: the ticked key figures, pages and charts
            c["app"] = _app_request(o["app"])
        if o["kind"] == "data_agent" and o.get("agent") is not None:  # n185: one layer; Publish and Copilot, both off by default
            c["agent"] = _agent_request(o["agent"])
        if o["kind"] == "pipeline" and o.get("jobs") is not None:    # n185: Run once and Schedule, both off by default
            c["jobs"] = _jobs_request(o["jobs"])
        if o["kind"] == "report" and o.get("model") not in (None, ""):
            if not isinstance(o["model"], str) or len(o["model"]) > 123:
                raise BadRequest("report.model: the name or id of an existing semantic model, or empty for the one this build makes")
            c["model"] = o["model"].strip()
        chosen.append(c)
    kinds = {c["kind"] for c in chosen}
    report = next((c for c in chosen if c["kind"] == "report"), None)
    if report and not report.get("model") and "semantic_model" not in kinds:
        raise BadRequest("a report needs a semantic model: choose Semantic model too, or name an existing model for the report")
    names = [c["name"].lower() for c in chosen if c["kind"] in ("silver_notebook", "gold_views")]
    if len(names) != len(set(names)):
        raise BadRequest("the silver and the gold notebook need two different names")
    product = body.get("product")
    if product is not None:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not _PRODUCT.match(product["name"].strip()):
            raise BadRequest("product: {name}, letters, digits, spaces, '.', '_' or '-', at most 80, or null")
        product = {"name": product["name"].strip()}
    created = body.get("created") or []
    if not isinstance(created, list) or not all(isinstance(c, dict) and isinstance(c.get("id"), str) for c in created):
        raise BadRequest("'created' must be outputs.json's created list ({type, id, name, workspace}) or empty")
    if not isinstance(body.get("review"), dict):
        raise BadRequest("'review' (the item's review.json) is required: the build uses its decisions")
    flags = {}
    for f in ("skip_built", "finish", "refresh_only"):                            # n179: Create one output per request, then the summary
        v = body.get(f, False)
        if not isinstance(v, bool):
            raise BadRequest(f"'{f}' must be true or false (default false)")
        flags[f] = v
    if flags["finish"] and dry_run:
        raise BadRequest("'finish' gives the product and the data flow of a Create from 'created'; it needs dry_run false")
    only = body.get("only")                                       # n179: the outputs this request builds; the rest is context
    if only is not None:
        if not isinstance(only, list) or not only or any(k not in {c["kind"] for c in chosen} for k in only):
            raise BadRequest("'only' must be a non-empty list of kinds among the outputs (the ones this request builds)")
        flags["only"] = list(only)
    if flags["refresh_only"] and (dry_run or flags.get("only") != ["semantic_model"]):
        raise BadRequest("'refresh_only' refreshes the semantic model this Model built: only [semantic_model], dry_run false")
    update = body.get("update")                                   # n180: Update of an output built from another plan
    if update is not None:
        if not isinstance(update, list) or any(k not in {c["kind"] for c in chosen} for k in update):
            raise BadRequest("'update' must be a list of kinds among the outputs (the ones to update in place)")
        if any(not KINDS[k]["updates"] for k in update):
            raise BadRequest("a report is never updated in place; choose a new name for it")
        flags["update"] = list(update)
    confirm = body.get("confirm") or {}
    if not isinstance(confirm, dict) or not all(isinstance(v, str) for v in confirm.values()):
        raise BadRequest("'confirm' must be {kind: the confirm_update its Update's dry run gave}")
    flags["confirm"] = confirm
    sids = body.get("schedule_ids") or []                         # n185: outputs.json's schedules, the ones this Model made
    if not isinstance(sids, list) or not all(isinstance(x, str) and len(x) <= 64 for x in sids):
        raise BadRequest("'schedule_ids' must be outputs.json's schedule ids (a list of ids) or empty")
    flags["schedule_ids"] = sids
    after = body.get("after_run")                                 # n185: the pipeline run's end, as the editor read it
    if after is not None:
        if not isinstance(after, dict) or after.get("status") not in ("Succeeded", "Failed", "Running", "Unknown", "NotStarted"):
            raise BadRequest("'after_run' is {status: Succeeded, Failed, Running, Unknown or NotStarted}")
        flags["after_run"] = {"status": after["status"]}
    pending = body.get("pending") or []                           # n197: items a Create sent and Fabric may finish later
    if (not isinstance(pending, list) or len(pending) > 60
            or not all(isinstance(x, dict) and isinstance(x.get("name"), str) and isinstance(x.get("type"), str) for x in pending)):
        raise BadRequest("'pending' must be outputs.json's pending list ({output, type, name}) or empty")
    flags["pending"] = [{"type": x["type"][:40], "name": x["name"][:123], "output": str(x.get("output") or "")[:40],
                         "at": str(x.get("at") or "")[:40]} for x in pending]   # n207: when the step was sent
    flags["target"] = target_request(body.get("target"))         # n201, n221
    flags["products"] = _ticked_products(body.get("products"))     # n222: the suggested data products the person ticked
    flags.update(_ids(body))
    chosen.sort(key=lambda c: ORDER.index(c["kind"]))
    return {**req, "outputs": chosen, "dry_run": dry_run, "review": body["review"], "product": product,
            "created": [{k: c.get(k) for k in ("type", "id", "name", "workspace", "output", "plan") if k != "plan" or isinstance(c.get(k), dict)}
                        for c in created], "form": 2, **flags}


_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_LAKEHOUSE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,122}$")
BUILD_IN = ("item", "source")


def target_request(target) -> dict | None:
    """Where the build writes. n201: lakehouse, the id or name of the lakehouse a read-only source's silver and gold go to
    (null: the first of the workspace). n221: workspace, the workspace the Krusgraph Model builds in (a GUID: the item's
    own by default, or the source's, as `where` says); create_lakehouse, the name of a lakehouse Create may make there,
    with schemas, when the person ticked it (the dry run names it and makes nothing)."""
    if target is None:
        return None
    if not isinstance(target, dict) or not (target.get("lakehouse") is None or isinstance(target.get("lakehouse"), str)
                                            and 0 < len(target["lakehouse"].strip()) <= 128):
        raise BadRequest("'target' is {lakehouse: the id or name of a lakehouse of this workspace} or null for the default")
    out = {"lakehouse": (target.get("lakehouse") or "").strip() or None}
    ws = target.get("workspace")
    if ws is not None:
        if not isinstance(ws, str) or not _GUID.match(ws):
            raise BadRequest("'target.workspace' is the id (a GUID) of the workspace the build writes to")
        out["workspace"] = ws.lower()
    where = target.get("where")
    if where is not None:
        if where not in BUILD_IN:
            raise BadRequest("'target.where' is item (this item's workspace, the default) or source (the source's workspace)")
        out["where"] = where
    make = target.get("create_lakehouse")
    if make not in (None, ""):
        if not isinstance(make, str) or not _LAKEHOUSE.match(make.strip()):
            raise BadRequest("'target.create_lakehouse': a lakehouse name, letters, digits and underscores, starting with a letter")
        out["create_lakehouse"] = make.strip()
    return out


_CREATE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


_SLUG = re.compile(r"^[a-z0-9_]{1,80}$")


def _ticked_products(v) -> list[dict]:
    """n222: [{id, name}] of the suggestions the person ticked (outputs.json's products); the tables come from the engine."""
    if v is None:
        return []
    if (not isinstance(v, list) or len(v) > 30
            or not all(isinstance(x, dict) and isinstance(x.get("id"), str) and _SLUG.match(x["id"]) for x in v)):
        raise BadRequest("'products' must be the ticked suggestions [{id, name}] (outputs.json's products) or empty")
    return [{"id": x["id"], "name": str(x.get("name") or x["id"])[:80]} for x in v]


def _ids(body: dict) -> dict:
    """n197: item_id (the Krusgraph Model item, a GUID) and create_id (one Create of it), both optional: with them a
    background operation is listed under the item, so a reopened editor finds the Create it left."""
    out = {}
    item, create = body.get("item_id"), body.get("create_id")
    if item is not None:
        if not isinstance(item, str) or not _GUID.match(item):
            raise BadRequest("'item_id' is the Krusgraph Model item's id (a GUID)")
        out["item_id"] = item.lower()
    if create is not None:
        if not isinstance(create, str) or not _CREATE_ID.match(create):
            raise BadRequest("'create_id' is letters, digits, '-' or '_', at most 64")
        out["create_id"] = create
    return out


def operation_request(body) -> dict:
    """n197: POST /workload/v1/operation {operation_id} (one operation) or {item_id} (the item's latest Create)."""
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    op = body.get("operation_id")
    if op is not None:
        if not isinstance(op, str) or not re.fullmatch(r"[0-9a-f]{32}", op):
            raise BadRequest("'operation_id' is the id a 202 answer gave")
        return {"operation_id": op, "workspace": "", "source_name": ""}
    ids = _ids(body)
    if "item_id" not in ids:
        raise BadRequest("send operation_id, or item_id for the item's latest Create")
    return {**ids, "workspace": "", "source_name": ""}


def _app_request(app) -> dict:
    """n181/n189: the App's choices as outputs.json keeps them: kpis, tables, charts and filters (lists of option ids;
    filters absent: the defaults), chart_types {chart id: bar|line|table}, page_order [page ids], accent (a preset).
    Whether an id or a type fits the plan is rayfin_app.resolve's to say (a bad_input answer with the options)."""
    if not isinstance(app, dict) or any(not isinstance(app.get(k, []), list) or not all(isinstance(i, str) for i in app.get(k, []))
                                        for k in ("kpis", "tables", "charts", "filters", "page_order")):
        raise BadRequest("rayfin_app.app: {kpis, tables, charts, filters, page_order}, each a list of ids from the dry run; "
                         "chart_types {chart id: bar|line|table}; accent")
    out = {k: list(app.get(k, [])) for k in ("kpis", "tables", "charts")}
    if app.get("filters") is not None:
        out["filters"] = list(app["filters"])
    types = app.get("chart_types")
    if types is not None:
        if not isinstance(types, dict) or not all(isinstance(k, str) and v in ("bar", "line", "table") for k, v in types.items()):
            raise BadRequest("rayfin_app.app.chart_types: {chart id: bar, line or table}")
        out["chart_types"] = dict(types)
    if app.get("page_order"):
        out["page_order"] = list(app["page_order"])
    if app.get("accent") is not None:
        if not isinstance(app["accent"], str) or len(app["accent"]) > 20:
            raise BadRequest("rayfin_app.app.accent: one of the presets the dry run lists")
        out["accent"] = app["accent"]
    return out


def _agent_request(agent) -> dict:
    """outputs[].agent of the data agent: {layer: silver (default), gold or source, publish: false, copilot: false}."""
    if not isinstance(agent, dict):
        raise BadRequest("data_agent.agent: {layer, publish, copilot}")
    layer = agent.get("layer", "silver")
    if layer not in ("silver", "gold", "source"):
        raise BadRequest("data_agent.agent.layer is silver, gold or source")
    for k in ("publish", "copilot"):
        if not isinstance(agent.get(k, False), bool):
            raise BadRequest(f"data_agent.agent.{k} must be true or false (default false)")
    if agent.get("copilot") and not agent.get("publish"):
        raise BadRequest("data_agent.agent.copilot needs publish: an agent is made available in Microsoft 365 Copilot only once published")
    return {"layer": layer, "publish": agent.get("publish", False), "copilot": agent.get("copilot", False)}


def _jobs_request(jobs) -> dict:
    """outputs[].jobs of the pipeline: {run_once: bool, schedule: null or pipeline_jobs.schedule_spec's input}."""
    from . import pipeline_jobs
    if not isinstance(jobs, dict) or not isinstance(jobs.get("run_once", False), bool):
        raise BadRequest("pipeline.jobs: {run_once: true or false, schedule: null or {every, at, hours, time_zone, start}}")
    try:
        spec = pipeline_jobs.schedule_spec(jobs.get("schedule"))
    except pipeline_jobs.ScheduleError as exc:
        raise BadRequest(f"pipeline.jobs.{exc}") from None
    return {"run_once": jobs.get("run_once", False), "schedule": spec}


def pipeline_run_request(body) -> dict:
    """n185: POST /workload/v1/pipeline-run {workspace, pipeline_id, pipeline_name, run_id, started}: the run now."""
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    out = {}
    for k in ("workspace", "pipeline_id", "pipeline_name", "run_id"):
        v = body.get(k)
        if not isinstance(v, str) or not v.strip() or len(v) > 200:
            raise BadRequest(f"'{k}' is required")
        out[k] = v.strip()
    if not _GUID.match(out["pipeline_id"]) or not _GUID.match(out["run_id"]) or not _GUID.match(out["workspace"]):
        raise BadRequest("workspace, pipeline_id and run_id are Fabric ids (GUIDs)")
    started = body.get("started")
    out["started"] = started if isinstance(started, str) and len(started) <= 40 else None
    out["source_name"] = out["pipeline_name"]                     # for the error layer's words
    return out


def product_request(body) -> dict:
    """n198: POST /workload/v1/product {action, workspace, item_id, outputs, product, plan_id, ...} (product_life.py):
    status, retire (scope soft or delete; dry_run true by default; confirm and typed_name for the real call), leftovers
    and adopt. outputs is the item's outputs.json; only its created, removed, pending and pipeline_jobs are read."""
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    action = body.get("action")
    if action not in ("status", "retire", "leftovers", "adopt"):
        raise BadRequest("'action' is status, retire, leftovers or adopt")
    ws = body.get("workspace")
    if not isinstance(ws, str) or not _GUID.match(ws):
        raise BadRequest("'workspace' is the Krusgraph Model's workspace id (a GUID)")
    out = {"action": action, "workspace": ws.lower(), "source": "", "schema": ""}
    out.update(_ids(body))
    o = body.get("outputs")
    if not isinstance(o, dict):
        raise BadRequest("'outputs' is the item's outputs.json")
    lists = {}
    for k in ("created", "removed", "pending"):
        v = o.get(k) or []
        if not isinstance(v, list) or len(v) > 500 or not all(isinstance(x, dict) for x in v):
            raise BadRequest(f"outputs.{k} must be a list of items")
        lists[k] = v
    for c in lists["created"]:
        if not isinstance(c.get("id"), str) or not _GUID.match(c["id"]) or not isinstance(c.get("workspace"), str) or not _GUID.match(c["workspace"]):
            raise BadRequest("each of outputs.created has the Fabric id and workspace (GUIDs) Create recorded")
    jobs = o.get("pipeline_jobs") if isinstance(o.get("pipeline_jobs"), dict) else {}
    # n210: a schedule's id goes into a DELETE path, so one that is not a GUID is never used (it is left out, not followed)
    schedules = [s for s in jobs.get("schedules") or [] if isinstance(s, dict)
                 and all(isinstance(s.get(k), str) and _GUID.match(s[k]) for k in ("id", "pipeline_id"))][:100]
    out["outputs"] = {**lists, "pipeline_jobs": {"schedules": schedules}}
    name = body.get("product")
    if not isinstance(name, str) or not _PRODUCT.match(name.strip()):
        raise BadRequest("'product' is the data product's name: letters, digits, spaces, '.', '_' or '-', at most 80")
    out["product"] = out["source_name"] = name.strip()
    plan = body.get("plan_id")
    out["plan_id"] = plan if isinstance(plan, str) and len(plan) <= 80 else None
    if action in ("retire", "adopt"):
        items = body.get("items")
        if action == "adopt" or items is not None:
            if not isinstance(items, list) or not items or len(items) > 200 or not all(isinstance(i, str) and _GUID.match(i) for i in items):
                raise BadRequest("'items' is a list of Fabric item ids (GUIDs)" + ("" if action == "adopt" else ", or absent for the whole data product"))
            items = [i.lower() for i in items]
        out["items"] = items
    if action == "retire":
        if body.get("scope") not in ("soft", "delete"):
            raise BadRequest("'scope' is soft (turn off what Krusgraph scheduled or published) or delete (Delete from Fabric)")
        out["scope"] = body["scope"]
        for k in ("dry_run", "leftovers"):
            v = body.get(k, k == "dry_run")
            if not isinstance(v, bool):
                raise BadRequest(f"'{k}' must be true or false")
            out[k] = v
        for k, limit in (("confirm", 40), ("typed_name", 120)):
            v = body.get(k)
            if v is not None and (not isinstance(v, str) or len(v) > limit):
                raise BadRequest(f"'{k}' is text of at most {limit} characters")
            out[k] = v
        if out["leftovers"] and items is None:
            raise BadRequest("deleting leftovers needs the leftovers' ids in 'items'")
    return out


def run_product(req: dict) -> dict:
    """n198: the data product page's actions as the signed-in user (product_life.py). Lists and deletes only."""
    from . import product_life as life, server as S
    from .deploy import send
    from .lineage import _definition_response
    headers = S._headers(None)

    def http(method, url, **kw):
        return send(method, url, headers, write=method != "get", timeout=30, **kw)

    def read_definition(ws, item_id):
        r = _definition_response(f"{life.FABRIC}/v1/workspaces/{ws}/items/{item_id}/getDefinition", headers)
        return (r.json().get("definition") or {}).get("parts", [])

    o = req["outputs"]
    lefts = None
    if req["action"] in ("leftovers", "adopt") or req.get("leftovers"):
        lefts = life.leftovers(http, req["workspace"], o, req.get("item_id"), req.get("plan_id"), read_definition)
    try:
        if req["action"] == "leftovers":
            log("product", action="leftovers", found=len(lefts["leftovers"]), unread=len(lefts["unread_models"]))
            return {**lefts, "note": NOTHING_CHANGED}
        if req["action"] == "adopt":
            got = life.adopt(lefts, req["items"], req.get("by", ""))
            log("product", action="adopt", adopted=len(got["adopted"]), refused=len(got["refused"]))
            return {**got, "note": "Nothing was changed in Fabric; the editor adds the adopted items to outputs.json."}
        wss = {req["workspace"]} | {c.get("workspace") for c in life.active(o) if c.get("workspace")}
        listings = {ws: life.list_items(http, ws) for ws in sorted(wss)}
        if req["action"] == "status":
            rows = life.status(o, listings)
            log("product", action="status", **{s: sum(1 for r in rows if r["state"] == s) for s in life.STATES})
            return {"items": rows, "you": req.get("by", ""), "people": life.people(http, req["workspace"]), "note": NOTHING_CHANGED}
        got = life.retire(http, {**req, "items": req.get("items")}, listings, lefts)
        log("product", action="retire", scope=req["scope"], dry_run=req["dry_run"], leftovers=bool(lefts),
            items=len(got.get("items") or got.get("results") or got.get("steps") or []), refused=len(got["refused"]))
        return got
    except life.Refused as e:
        return {"error": str(e), "kind": "bad_input", "hint": "Nothing was deleted or changed in Fabric."}


def run_pipeline_status(req: dict) -> dict:
    """The run as the card shows it (pipeline_jobs.read_run), as the signed-in user. Only reads."""
    from . import pipeline_jobs, server as S
    from .deploy import send
    headers = S._headers(None)

    def http(method, url, **kw):
        return send(method, url, headers, write=False, timeout=30, **kw)
    run = pipeline_jobs.read_run(http, req["workspace"], req["pipeline_id"], req["pipeline_name"], req["run_id"], req["started"])
    run["note"] = pipeline_jobs.run_note(run)
    log("pipeline_run", outcome=run["status"])
    return run


# ------------------------------------------------------------------ the review's decisions applied to a plan --------

def apply_review(plan, review: dict):
    """The plan with what the person rejected left out: a rejected relationship, and a rejected key (its table then has
    no key, so nothing can point at it). Returns (plan, left_out) where left_out lists what was taken out and why."""
    from dataclasses import replace
    from .review import key_id, rel_id
    rejected = {it["id"]: it for it in review.get("items", []) if it.get("review") == "rejected"}
    no_key = {t for t in plan.keys if key_id(t) in rejected}
    left = [{"id": key_id(t), "what": f"key of {t}", "because": "rejected in the review"} for t in sorted(no_key)]
    keep = []
    for r in plan.relationships:
        rid = rel_id(r.source, r.source_cols, r.target)
        if rid in rejected:
            left.append({"id": rid, "what": f"{r.source}.{'+'.join(r.source_cols)} → {r.target}", "because": "rejected in the review"})
        elif r.target in no_key:
            left.append({"id": rid, "what": f"{r.source}.{'+'.join(r.source_cols)} → {r.target}",
                         "because": f"the key of {r.target} was rejected"})
        else:
            keep.append(r)
    return replace(plan, keys={t: v for t, v in plan.keys.items() if t not in no_key}, relationships=keep), left


def _counts(rv: dict) -> dict:
    items = rv["items"]
    by = lambda f: {v: sum(1 for it in items if f(it) == v) for v in sorted({f(it) for it in items})}   # noqa: E731
    return {"keys": sum(1 for it in items if it["type"] == "key"),
            "relationships": sum(1 for it in items if it["type"] == "relationship"),
            "review": by(lambda it: it["review"]), "open_questions": len(rv.get("open_questions", []))}


def check_totals(rv: dict) -> dict:
    """What the check found, per kind: passed, failed, stale and not checked, and each failed item with its counts in
    words the editor shows (orphans for a relationship; duplicates and empty keys for a key). Counts only."""
    out = {"checked_at": None, "checked": 0}
    for kind in ("key", "relationship"):
        t = {"passed": 0, "failed": 0, "stale": 0, "not_checked": 0}
        for it in rv["items"]:
            if it["type"] != kind:
                continue
            c = it.get("check") or {}
            st = c.get("status") if c.get("status") in t else "not_checked"
            t[st] += 1
            if st in ("passed", "failed"):
                out["checked"] += 1
                if c.get("checked_at") and (out["checked_at"] or "") < c["checked_at"]:
                    out["checked_at"] = c["checked_at"]
        out[kind + "s"] = t
    failed = []
    for it in rv["items"]:
        c = it.get("check") or {}
        if c.get("status") != "failed":
            continue
        res = c.get("result") or {}
        f = {"id": it["id"], "type": it["type"], "verdict": c.get("verdict", "")}
        if it["type"] == "key":
            rows, nulls, distinct = (int(res.get(k) or 0) for k in ("rows", "nulls", "distinct"))
            f.update(rows=rows, nulls=nulls, duplicates=max(rows - nulls - distinct, 0))
        else:
            f.update(orphans=int(res.get("orphans") or 0), rows_with_value=int(res.get("rows_with_value") or 0))
        failed.append(f)
    out["failed"] = failed
    return out


def map_of(rv: dict) -> dict | None:
    """The MCP Apps cards' map of the review (n170, mcp_apps_pictures.map_from_review), with each table's key check
    added (key_check: passed, failed, stale, not_checked) so the editor can mark it on the table."""
    from .mcp_apps_pictures import map_from_review
    m = map_from_review({"review": rv})
    if not m:
        return None
    checks = {it["table"]: (it.get("check") or {}).get("status") or "not_checked" for it in rv["items"] if it["type"] == "key"}
    for t in m["tables"]:
        if t["name"] in checks:
            t["key_check"] = checks[t["name"]]
    return m


def _exact(req: dict, used: str) -> dict:
    """n175: the request with the schema as the metadata spells it ("Shop" typed, "shop" read), and schema_asked kept so
    the answer can say which name was used."""
    if used == req["schema"]:
        return req
    return {**req, "schema": used, "schema_asked": req.get("schema_asked") or req["schema"]}


def _schema_used(req: dict) -> dict | None:
    if not req.get("schema_asked"):
        return None
    return {"asked": req["schema_asked"], "used": req["schema"],
            "note": f"Schema {req['schema_asked']!r} was read as {req['schema']!r}, the name the lakehouse's metadata returns; "
                    f"every query used {req['schema']!r}."}


def _with_schema(out: dict, req: dict) -> dict:
    used = _schema_used(req)
    return {"schema_used": used, **out} if used else out


def _answer(rv: dict, note: str = NOTHING_CHANGED) -> dict:
    from . import review as R
    return {"review": rv, "summary": R.summary(rv), "attention": R.attention(rv), "counts": _counts(rv),
            "map": map_of(rv), "note": note}


# ------------------------------------------------------------------ n222: suggested data products ----------------------
# The founder's live test of 11 November 2026: "I want suggestions on which data products to create". The suggestions are
# domain_draft's own proposal (domains.propose_plan: the same function the MCP tool and /check's domain step call), on the
# plan the review left, weighted by the check's counts when the rows were checked. Deterministic, no AI. Each suggestion
# names its tables, the rule that grouped them, its interface (the links that cross to another suggestion: it provides
# the key, or it consumes another's key) and its evidence (the keys and the links inside it, each with its rule and the
# check's verdict). The weekend's suggestion engine (W2) can extend this function; the editor only draws what it returns.
SUGGEST_RULE = ("Tables joined by their keys and links, cut where the links are weakest (Leiden-style communities on the key "
                "graph, domain_draft's method); a table whose key holds its parent's key stays with that parent.")


def suggest_products(p, validation: dict | None = None) -> dict:
    """The suggested data products of a plan (domains.propose_plan), in the words the editor shows."""
    from . import domains as D
    label = getattr(p, "label", None) or (lambda r: r)
    prop = D.propose_plan(p, validation)
    names = {d["slug"]: d["name"] for d in prop["domains"]}
    verdicts = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r.get("verdict", "")
                for r in (validation or {}).get("relationships", [])}
    key_checks = {k["table"]: k.get("verdict", "") for k in (validation or {}).get("keys", [])}
    link = lambda src, cols, tgt: f"{src}.{'+'.join(cols)} → {tgt}"   # noqa: E731
    out = []
    for d in prop["domains"]:
        inside = set(d["tables"])
        evidence = []
        for t in d["tables"]:
            cols, rule = p.keys.get(t, ([], ""))
            if cols:
                v = key_checks.get(t)
                evidence.append(f"key {t}.{'+'.join(cols)} ({label(rule)}; " + (f"the rows: {v}" if v else "not checked against the rows") + ")")
        for r in list(p.relationships) + list(getattr(p, "extended", [])):
            if r.source in inside and r.target in inside and r.source != r.target:
                v = verdicts.get((r.source, tuple(c.lower() for c in r.source_cols), r.target))
                evidence.append(f"link {link(r.source, r.source_cols, r.target)} ({label(r.rule)}; "
                                + (f"the rows: {v}" if v else "not checked against the rows") + ")")
        face = {"provides": [], "consumes": []}
        for i in prop["interfaces"]:
            if d["slug"] not in (i["provider"], i["consumer"]):
                continue
            mine = i["provider"] == d["slug"]
            other = i["consumer"] if mine else i["provider"]
            face["provides" if mine else "consumes"].append(
                {"product": names.get(other, other), "id": other, "link": link(i["source"], i["source_cols"], i["target"]),
                 "rule": label(i["rule"]) if i.get("rule") else ""})
        out.append({"id": d["slug"], "name": d["name"], "tables": list(d["tables"]), "rule": SUGGEST_RULE,
                    "name_reason": d.get("name_reason", ""), "why": dict(d.get("reasons", {})), "interface": face,
                    "evidence": evidence})
    return {"products": out, "unassigned": [{"table": u["table"], "reason": u["reason"]} for u in prop["unassigned"]],
            "checked": validation is not None, "from": "domain_draft's proposal (domains.propose_plan)",
            "note": ("Suggestions, not decisions: tick the ones to build. Each becomes a data product over this Model's outputs; "
                     "a Fabric domain itself needs a Fabric administrator.")}


def _chosen_products(req: dict, p, cards: list[dict], dry_run: bool) -> list[dict]:
    """The ticked suggestions as data products of this build: the engine's suggestion of the same id on this plan (its
    tables and interface), with the build's items; a ticked one this plan no longer suggests says so."""
    now = {x["id"]: x for x in suggest_products(p)["products"]}
    items = []
    for c in cards:
        if c.get("refusal") or (c.get("answer") or {}).get("error"):
            continue
        items += ([{"output": c["output"], "type": c["type"], "name": c["name"], "would": c.get("would")}] if dry_run
                  else [{**x, "label": c["label"]} for x in c.get("created", [])])
    out = []
    for t in req.get("products") or []:
        s = now.get(t["id"])
        if s is None:
            out.append({"id": t["id"], "name": t["name"], "gone": True,
                        "words": "This plan no longer suggests it (the review or the data changed); untick it or choose another."})
            continue
        out.append({"id": s["id"], "name": s["name"], "tables": s["tables"], "interface": s["interface"], "items": items,
                    "words": f"{len(s['tables'])} table(s); the outputs of this build cover them."})
    return out


# ------------------------------------------------------------------ the three calls ----------------------------------

def run_review(req: dict) -> dict:
    """review_plan's work for the editor. The review file's source names the lakehouse and schema, not ids, so the
    saved review.json stays the same across workspaces (Git, deployment pipelines)."""
    from . import server as S, review as R
    prev = R.read(req["previous"]) if req["previous"] else None
    keys, confirmed = req.get("keys"), req.get("confirmed")
    k, c = R.merge_arguments(R.carried_arguments(prev), keys, confirmed) if prev else (keys, confirmed)
    s, execute = S._connected(req["workspace"], req["source"], req["schema"], None)
    req = _exact(req, s.schema)
    try:
        counted = S._within_call(execute)
        p, base = S._hosted_plan(s, k, c, counted), S._hosted_plan(s, None, None, counted)
    finally:
        getattr(execute, "close", lambda: None)()
    rv = R.build(p, base, {"platform": "fabric", "source": req["source_name"], "schema": req["schema"]},
                 decisions=req["decisions"], previous=prev)
    out = _with_source(_answer(rv), p, execute)
    out["suggested_products"] = _suggested(p, rv)                  # n222
    return _with_schema(out, req)


def _suggested(p, rv: dict, validation: dict | None = None) -> dict | None:
    """n222: the suggestions on the plan the review left; None (and a logged cause) if they could not be made."""
    try:
        return suggest_products(apply_review(p, rv)[0], validation)
    except Exception as exc:  # noqa: BLE001 — the review and the check stand without them
        log("suggest_failed", error=type(exc).__name__)
        return None


def _with_source(out: dict, p, execute) -> dict:
    """n201: what kind of item was read (a mirrored database is read-only: what Krusgraph builds with Spark goes to a
    lakehouse), and the SAP pack's keys and links marked "from the SAP pack" with its sources when the tables are SAP's."""
    from . import mirroring as M
    kind = (getattr(execute, "source_item", None) or {}).get("type") or "Lakehouse"
    if M.is_read_only(kind):                                       # a lakehouse's answer is as it was before n201
        out["source_kind"] = kind
        out["read_only"] = {"kind": kind, "words": f"A {M.kind_words(kind)} is read-only: the review and the check read its SQL "
                                                  "analytics endpoint, and the silver tables, gold views and the pipeline's check "
                                                  "are written to a lakehouse you choose (Target lakehouse)."}
        if kind == "MirroredDatabase":
            out["read_only"]["mirroring"] = M.MIRRORING_NOTE
    sap = M.sap_offer(p)
    if sap:
        out["sap"] = sap
    return out


def check_progress(clock=time.monotonic, every: float = 1.0):
    """n223: the check's progress for the editor ("3 of 7 keys and links counted"), written to the running operation at
    most once a second and always at the end; outside an operation (the MCP tools, a synchronous request) it does
    nothing (operations.progress)."""
    from . import operations
    last = [None]

    def step(done: int, total: int) -> None:
        now = clock()
        if done < total and last[0] is not None and now - last[0] < every:
            return
        last[0] = now
        operations.progress("running", done=done, total=total, unit="keys and links counted")
    return step


def run_check(req: dict) -> dict:
    """validate_plan's counting queries on the reviewed plan (review_plan with validate=true): the review file comes back
    with each item's check status, the decisions unchanged. Read-only; nothing in Fabric changes."""
    from datetime import datetime, timezone
    from . import server as S, review as R, evidence as E
    prev = R.read(req["review"])
    carried = R.carried_arguments(prev)
    k, c = carried["keys"] or None, carried["confirmed"] or None
    s, execute = S._connected(req["workspace"], req["source"], req["schema"], None)
    req = _exact(req, s.schema)
    try:
        counted = S._within_call(execute)
        p, base = S._hosted_plan(s, k, c, counted), S._hosted_plan(s, None, None, counted)
        checks = E.validate(p, execute, max_items=req["max_items"], on_step=check_progress())
    finally:
        getattr(execute, "close", lambda: None)()
    rv = R.build(p, base, {"platform": "fabric", "source": req["source_name"], "schema": req["schema"]}, previous=prev,
                 checks=checks, checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
    out = _with_source(_answer(rv, NOTHING_CHANGED + " The check counted rows; it returns counts, never a value."), p, execute)
    out["check"] = check_totals(rv)
    out["questions"] = rv.get("open_questions", [])
    out["suggested_products"] = _suggested(p, rv, checks)        # n222: weighted by what the rows hold
    return _with_schema(out, req)


# n179: every schema of the source with its number of tables, empty ones included (shown greyed in the editor). The
# role schemas SQL Server lists in SCHEMATA (db_owner, db_datareader, ...) and the system schemas are left out.
SCHEMATA_SQL = """
SELECT s.SCHEMA_NAME AS TABLE_SCHEMA, COUNT(t.TABLE_NAME) AS TABLE_COUNT
FROM INFORMATION_SCHEMA.SCHEMATA s
LEFT JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA = s.SCHEMA_NAME AND t.TABLE_TYPE = 'BASE TABLE'
WHERE s.SCHEMA_NAME NOT IN ('sys', 'INFORMATION_SCHEMA', 'queryinsights', 'guest') AND s.SCHEMA_NAME NOT LIKE 'db[_]%'
GROUP BY s.SCHEMA_NAME
ORDER BY s.SCHEMA_NAME
"""


def preselect(schemas: list[dict]) -> str | None:
    """The schema to preselect: the only one with tables; dbo when it is the only schema; else none (the person picks)."""
    with_tables = [x["schema"] for x in schemas if x["tables"] > 0]
    if len(with_tables) == 1:
        return with_tables[0]
    if [x["schema"] for x in schemas] == ["dbo"]:
        return "dbo"
    return None


def run_schemas(req: dict) -> dict:
    """The source's schemas as the SQL analytics endpoint names them, each with its table count. The editor offers them
    as a list and sends the chosen name back unchanged, so the schema is never typed. Read-only."""
    from . import server as S
    headers = S._headers(None)
    workspace = S._workspace_id(req["workspace"], headers)
    item = S._resolve_source(workspace, req["source"], headers)
    execute = S._execute_factory(item, S.auth.sql(None))
    try:
        try:
            rows = list(execute(SCHEMATA_SQL))
        except Exception as exc:  # noqa: BLE001 — an endpoint without SCHEMATA: the schemas that hold tables (n169's query)
            log("schemata_fallback", error=type(exc).__name__)
            rows = list(execute(S.SCHEMAS_SQL))
    finally:
        getattr(execute, "close", lambda: None)()
    out = []
    for r in rows:
        r = {str(k).upper(): v for k, v in (r.items() if hasattr(r, "items") else zip(("TABLE_SCHEMA", "TABLE_COUNT"), r))}
        if r.get("TABLE_SCHEMA"):
            out.append({"schema": str(r["TABLE_SCHEMA"]), "tables": int(r.get("TABLE_COUNT") or 0)})
    chosen = preselect(out)
    with_tables = sum(1 for x in out if x["tables"])
    return {"schemas": out, "preselect": chosen,
            "note": (f"{with_tables} of {len(out)} schema(s) hold tables." if out else "The source lists no schema.")
                    + ("" if chosen else " Choose the schema to plan.") + " " + NOTHING_CHANGED}


def run_build_background(req: dict) -> dict:
    """n197: a background build: one Create step with its waits (run_build_step), anything else as run_build."""
    if req.get("refresh_only"):
        return run_refresh_only(req)
    if req.get("form") == 2 and req.get("only") and not req["dry_run"] and not req.get("finish"):
        return run_build_step(req)
    return run_build(req)


def run_operation(req: dict) -> dict:
    """Placeholder: /operation is answered in the route itself (it needs the caller's identity)."""
    raise BadRequest("operation")


def run_build(req: dict) -> dict:
    """Phase 1's form (a name and ["graphql"]) answers as before; n174's form ({kind, name} per output) builds several."""
    if req.get("refresh_only"):
        return run_refresh_only(req)
    return _run_graphql(req) if req.get("form", 1) == 1 else run_build_many(req)


def _run_graphql(req: dict) -> dict:
    """create_backend for the editor: the plan with the review's keys and confirmed relationships, minus what was
    rejected; a dry run unless dry_run is false. Never removes relationships an existing API has (no allow_removals)."""
    from . import server as S, review as R
    rv = R.read(req["review"])
    carried = R.carried_arguments(rv)
    keys, confirmed = carried["keys"] or None, carried["confirmed"] or None
    workspace = S._workspace_id(req["workspace"], S._headers(None))
    p, item, headers = S._plan(workspace, req["source"], req["schema"], keys, confirmed, None)
    req = _exact(req, p.schema.schema)
    p, left_out = apply_review(p, rv)
    out = json.loads(S._create_backend_from_plan(p, item, headers, workspace, req["name"], False, None, confirmed,
                                                 False, req["dry_run"], token_provider=lambda: S.auth.fabric(None)))
    out["output"] = "graphql"
    out["left_out_by_review"] = left_out
    if _schema_used(req):
        out["schema_used"] = _schema_used(req)
    totals = check_totals(rv)                        # n173: the review's own check, so the dry run says what passed
    out["row_check"] = totals
    if totals["checked"]:
        out.pop("not_checked", None)
    if "error" in out:
        return out
    if req["dry_run"]:
        out["note"] = NOTHING_CHANGED + " This is what Create would send."
        return out
    res = out.get("result") or {}
    if res.get("status") == "Succeeded" and res.get("id"):
        from .deploy import endpoint_url
        made_in = S._out_ws(workspace)                              # n221: the build's workspace
        out["created"] = [{"type": "GraphQLApi", "id": res["id"], "name": req["name"], "workspace": made_in}]
        out["endpoint"] = endpoint_url(made_in, res["id"])
        out["portal_steps"] = [f"{req['name']} → Settings → Introspection → On (workspace admin), if an app reads the schema",
                               f"{req['name']} → Manage permissions → add who may run queries"]
    return out


# ------------------------------------------------------------------ n174: every output, the data product, the flow --

def token_scopes() -> set[str] | None:
    """The delegated permissions on the signed-in user's Fabric token (the on-behalf-of token's scp claim), or None when
    it cannot be read (then Fabric's own answer decides, and a 403 still comes back as kind consent). Read only, never
    verified here: Fabric verifies the token; this only says early which permission is missing."""
    import base64
    from . import server as S
    w = S._WORKLOAD_TOKENS.get()
    if w is None:
        return None
    try:
        part = w.fabric().split(".")[1]
        scp = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("scp")
    except Exception:                                              # noqa: BLE001 — not a JWT, or no exchange: unknown
        return None
    return set(scp.split()) if isinstance(scp, str) else None


def permissions(kind: str, scopes: set[str] | None) -> dict:
    """What the output needs, each as "A or B", and what the token lacks (None: the token's permissions are unknown)."""
    needs = KINDS[kind]["needs"]
    out = {"needs": [" or ".join(alt) for alt in needs], "execute": "none: nothing is run or scheduled"}
    if kind == "semantic_model":                                   # n180: one refresh of the model Create makes
        out["execute"] = f"{REFRESH_PLANNED} The refresh needs {REFRESH_SCOPE}."
    if kind == "pipeline":                                         # n185: Run once and Schedule, only when ticked
        out["execute"] = (f"none unless Run once or Schedule is ticked; they need {EXECUTE_SCOPE} (or {EXECUTE_ALT}).")
    out["missing"] = None if scopes is None else [alt[0] for alt in needs if not set(alt) & scopes]
    return out


# n185: the permission Run once and Schedule need. Not part of the pipeline's own needs: without it the pipeline is built
# and the two choices are shown disabled with this explanation.
EXECUTE_SCOPE, EXECUTE_ALT = "DataPipeline.Execute.All", "Item.Execute.All"
FABRIC_API_APP = "00000009-0000-0000-c000-000000000000"           # Power BI Service, whose delegated permissions Fabric's are


def az_permission_line(scope: str, app_id: str | None) -> str:
    """The Cloud Shell line that adds one delegated permission of Power BI Service to the workload app."""
    return (f"az ad app permission add --id {app_id or '<workload app id>'} --api {FABRIC_API_APP} --api-permissions "
            f"\"$(az ad sp show --id {FABRIC_API_APP} --query \"oauth2PermissionScopes[?value=='{scope}'].id\" -o tsv)=Scope\"")


def jobs_permission(scopes: set[str] | None, app_id: str | None) -> dict:
    """Whether the sign-in can run and schedule pipelines: granted true, false (with the steps) or None (unknown)."""
    from . import pipeline_jobs
    granted = None if scopes is None else bool({EXECUTE_SCOPE, EXECUTE_ALT} & scopes)
    out = {"granted": granted, "scope": EXECUTE_SCOPE, "or": EXECUTE_ALT}
    if granted is False:
        out.update(why=f"Your sign-in does not carry {EXECUTE_SCOPE}, which running and scheduling a pipeline need; Krusgraph "
                       "builds the pipeline and runs or schedules nothing.",
                   entra_steps=entra_steps(EXECUTE_SCOPE, app_id), az=az_permission_line(EXECUTE_SCOPE, app_id),
                   consent_note=CONSENT_NOTE, manual=list(pipeline_jobs.MANUAL))
    return out


CONSENT_NOTE = ("Grant admin consent in the Entra portal (App registrations -> the workload app -> API permissions -> Grant "
                "admin consent): `az ad app permission admin-consent` fails in Cloud Shell.")


def entra_steps(scope: str, app_id: str | None) -> list[str]:
    """The Entra admin centre steps that add one delegated permission to the workload's own app (docs/WORKLOAD-DEV.md)."""
    app = f"{WORKLOAD_APP_NAME}" + (f" (Application (client) ID {app_id})" if app_id else "")
    return [f"Entra admin centre (entra.microsoft.com) → App registrations → All applications → {app}.",
            "API permissions → Add a permission → Microsoft APIs → Power BI Service → Delegated permissions.",
            f"Tick {scope} → Add permissions.",
            "Grant admin consent for your organisation (a Global Administrator or Privileged Role Administrator) → Yes.",
            "Reload the Fabric tab and open the item again, so the next sign-in carries the permission."]


def _consent(kind: str, missing: list[str], app_id: str | None) -> dict:
    label = KINDS[kind]["label"]
    return {"error": f"Your sign-in does not carry {missing[0]}, which the {label.lower()} needs; nothing was created.",
            "kind": "consent", "scope": missing[0], "missing": missing, "entra_steps": entra_steps(missing[0], app_id),
            "hint": f"An administrator adds {', '.join(missing)} to the workload's Entra app and consents; the steps are below."}


def _names(o: dict, chosen: dict, schema: str) -> list[tuple[str, str]]:
    """(item type, name) of every item an output writes; the pipeline writes its three notebooks too."""
    if o["kind"] != "pipeline":
        return [(KINDS[o["kind"]]["type"], o["name"])]
    silver, gold = chosen.get("silver_notebook") or f"silver_{schema}", chosen.get("gold_views") or f"gold_{schema}"
    return [("DataPipeline", o["name"]), ("Notebook", silver), ("Notebook", gold), ("Notebook", f"{o['name']}_check")]


def _pending(req: dict, typ: str, name: str) -> bool:
    """n197: outputs.json records every item as pending the moment its create is sent (the editor's withPending)."""
    return any(p.get("type") == typ and p.get("name", "").lower() == name.lower() for p in req.get("pending") or [])


def _when(text) -> datetime | None:
    """An ISO 8601 time (the editor's toISOString, Fabric's createdDate) as an aware UTC datetime; None when unreadable."""
    if not isinstance(text, str) or not text.strip():
        return None
    t = text.strip().replace("Z", "+00:00").replace("z", "+00:00")
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", t)    # at most microseconds: Fabric may send seven digits
    if m and m.group(2):
        t = m.group(1) + m.group(2)[:7] + m.group(3)
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _pending_at(req: dict, typ: str, name: str) -> list[datetime]:
    """n207: the times this item's pending entries were recorded (entries without a readable `at` give none)."""
    return [w for p in req.get("pending") or []
            if p.get("type") == typ and p.get("name", "").lower() == name.lower() and (w := _when(p.get("at")))]


CREATED_KEYS = ("createdDate", "createdDateTime", "createdAt")


def _created_at(item: dict | None) -> datetime | None:
    """n207: the item's creation time when Fabric's listing gives one; None otherwise."""
    for k in CREATED_KEYS:
        w = _when((item or {}).get(k))
        if w:
            return w
    return None


def _adoptable(req: dict, workspace: str, name: str, headers: dict, typ: str) -> bool:
    """n207: whether an existing item that outputs.json does not list may be adopted as built by this Model. A pending
    entry alone is not enough: the editor records each step's own names as pending before it sends the step, so a
    colleague's item of the same name would be taken (and its definition updated). It is adopted only when it is pending
    and Krusgraph made it (its description: a create this Model sent, finished by Fabric after the wait, n197's
    demo_lh_model4), or Fabric gives its creation time and that is later than the pending entry's `at`. With no creation
    time and no Krusgraph description it is not adopted: Create says what the dry run says, not built by this Model."""
    if not _pending(req, typ, name):
        return False
    from .deploy import find_item_by_name
    it = find_item_by_name(workspace, name, headers, (typ,))
    if not it:
        return False
    if "krusgraph" in str(it.get("description") or "").lower():
        return True
    made, sent = _created_at(it), _pending_at(req, typ, name)
    return bool(made and sent and made > min(sent))


def _krusgraph_made(workspace: str, name: str, headers: dict, typ: str) -> dict | None:
    """n179: the existing item of that name and type when its description says Krusgraph made it (every creating tool
    writes "Created by Krusgraph ...", "... generated by Krusgraph ..." or "Krusgraph pipeline ..."), else None."""
    from .deploy import find_item_by_name
    it = find_item_by_name(workspace, name, headers, (typ,))
    return it if it and "krusgraph" in str(it.get("description") or "").lower() else None


def _already_built(o: dict, chosen: dict, req: dict, workspace: str, headers: dict, ours: set[str]) -> list[dict] | None:
    """n179, Create with skip_built: the output's items when every one of them is already in the workspace and was built by
    this Model (outputs.json) or carries Krusgraph's description (a Create whose answer the browser lost, 9 November
    2026); None when anything is missing, so the tool is called. Nothing is written for an output found built. n180:
    whether those items were built from this plan is the caller's question (recorded_mark, same_plan)."""
    from . import server as S
    found = []
    for typ, name in _names(o, chosen, req["schema"]):
        existing = S._find_item(workspace, name, headers, typ)
        if not existing:
            return None
        adopted = existing not in ours and _adoptable(req, workspace, name, headers, typ)   # n207: never a colleague's
        if existing not in ours and not adopted and not _krusgraph_made(workspace, name, headers, typ):
            return None                                            # someone else's: _ownership refuses it as before
        found.append({"type": typ, "id": existing, "name": name, "workspace": workspace, "output": o["kind"],
                      **({"adopted": True} if adopted else {})})
    return found


def existing_decision(o: dict, chosen: dict, req: dict, workspace: str, headers: dict, ours: set[str], mark: dict, listed,
                      dry_run: bool) -> dict | None:
    """n209: the one decision the dry run and Create (skip_built) both take for an output whose items are all in the
    workspace and were built by Krusgraph (this Model's outputs.json, a pending item Fabric finished, or Krusgraph's
    description, which another Krusgraph Model item's Create also writes). None when Create would call the tool (nothing
    there, or an item someone else made: _ownership refuses it, n207). Otherwise {outcome, card, adopted}: built from this
    plan -> already built, skipped; built from another plan or plan unknown -> the person chooses (nothing written)."""
    kind = o["kind"]
    done = _already_built(o, chosen, req, workspace, headers, ours)
    if done is None:
        return None
    marks = [recorded_mark(c["id"], req, listed()) or (mark if c.get("adopted") else None) for c in done]
    counts = existing_counts(kind, done, workspace, headers)
    if all(same_plan(m, mark) for m in marks):                    # built from this plan: as n179 showed it
        adopted = [c for c in done if c.pop("adopted", False)]
        done = [{**c, "plan": mark} for c in done]
        note = ("Already built from this plan; Create will skip it." if dry_run else
                "Fabric finished it after the wait; it is kept as built by this Model, and nothing was written "
                "again." if adopted else
                "Already in the workspace, built from this plan by an earlier Create; nothing "
                "was written. Choose a new name to make another one.")
        ours.update(c["id"] for c in done)
        return {"outcome": "already_built", "adopted": adopted,
                "card": {"would": "create", "created": done, "already_built": True, "existing": counts,
                         "answer": {"dry_run": dry_run, "already_built": True, "note": note,
                                    **({"adopted": len(adopted)} if adopted else {})}}}
    was = next((m for m in marks if m and not same_plan(m, mark)), None)   # n180: another plan, or none recorded
    bf = built_from(was, mark)
    choices = ["update", "new_name"] if KINDS[kind]["updates"] else ["new_name"]
    for c in done:
        c.pop("adopted", None)
    return {"outcome": "built_from_" + bf["status"], "adopted": [],
            "card": {"would": "update" if KINDS[kind]["updates"] else "create", "built_from": bf, "existing_items": done,
                     "existing": counts, "choices": choices,
                     "answer": {"dry_run": dry_run, "plan_differs": True,
                                "note": f"{KINDS[kind]['label']} {o['name']} was {bf['words']}; nothing was written. "
                                        + ("Update it (a dry run first) or choose a new name." if "update" in choices
                                           else "A report is never updated in place: choose a new name.")}}}


DECISION_WORDS = {
    "skip": ("Already built from this plan; Create will skip it.", "Already built from this plan; nothing was written again."),
    "create": ("Create will create it.", "Created."),
    "update": ("Create will update it in place.", "Updated in place."),
}


def decision_of(card: dict) -> dict:
    """n209: what Create does (or did) for one card, in one word and one sentence, the same for the dry run and Create:
    skip (already built from this plan), choose (built from another plan or plan unknown: nothing is written until the
    person picks Update or a new name), refuse (an item someone else made, n207; a report never updated; a missing
    permission), error (the tool's own error), update (Create writes into the existing item), create."""
    dry = bool(card.get("dry_run"))
    if card.get("refusal"):
        r = card["refusal"]
        return {"action": "refuse", "words": " ".join(x for x in (r.get("error"), r.get("hint")) if x)}
    if card.get("already_built"):
        return {"action": "skip", "words": DECISION_WORDS["skip"][0 if dry else 1]}
    if card.get("built_from") and card.get("choices"):
        what = ("Update (a dry run first) or a new name" if "update" in card["choices"] else "a new name")
        lead = "Create writes nothing and asks" if dry else "Nothing was written; choose"
        return {"action": "choose", "words": f"{card['built_from']['words'][:1].upper()}{card['built_from']['words'][1:]}. {lead}: {what}."}
    a = card.get("answer") or {}
    if a.get("error"):
        return {"action": "error", "words": " ".join(x for x in (a.get("error"), a.get("hint")) if x)}
    action = "update" if card.get("would") == "update" else "create"
    return {"action": action, "words": DECISION_WORDS[action][0 if dry else 1]}


def _ownership(o: dict, chosen: dict, req: dict, workspace: str, headers: dict, ours: set[str]) -> tuple[str, dict | None, dict]:
    """("create" or "update", a refusal or None, {name: existing id}). The Model updates only items it built itself
    (outputs.json's created ids, and those this build created); an item of that name made by anyone else is refused, and
    a report is never updated (create_report adds one item and never updates it)."""
    from . import server as S
    found, would = {}, "create"
    names = _names(o, chosen, req["schema"])
    for typ, name in names:
        existing = S._find_item(workspace, name, headers, typ)
        if not existing:
            continue
        found[name] = existing
        if existing not in ours and _adoptable(req, workspace, name, headers, typ):   # n197/n207: sent by this Model, finished later
            ours.add(existing)
        if existing not in ours:
            return would, {"error": f"{typ} {name!r} already exists in this workspace and was not built by this Krusgraph Model; "
                                    "nothing was written.", "kind": "already_exists", "existing": {"type": typ, "id": existing, "name": name},
                           "hint": "Choose another name. The Krusgraph Model updates only the items it built itself (outputs.json)."}, found
        if not KINDS[o["kind"]]["updates"]:
            return would, {"error": f"{name!r} was built by this Model, and a {KINDS[o['kind']]['label'].lower()} is never updated in place; "
                                    "nothing was written.", "kind": "already_exists", "existing": {"type": typ, "id": existing, "name": name},
                           "hint": "Choose a new name to create another one."}, found
        if (typ, name) == names[0]:
            # n184 (the founder's live Create, 9 November 2026): only the output's own item decides "updated". The pipeline
            # also rewrites its notebooks, and the silver and gold notebooks this same Create made a moment earlier exist,
            # which made a pipeline that did not exist say "updated".
            would = "update"
    return would, None, found


# ------------------------------------------------------------------ n180: the plan each output was built from --------
# The founder's re-run of 9 November 2026, 12:14: items built that morning from schema "Shop" with 6 links were shown as
# "already built" for a plan on "shop" with 7 links. Now every item a Create writes carries the plan it was built from,
# in outputs.json (created[].plan) and in its Fabric description (the marker below), and "already built" means built
# from this plan. An item built from another plan, or by Krusgraph before plans were recorded, gets a card with two
# choices: Update (dry run first; only where the tool updates in place) or a new name. Nothing is written for it.
MARK = re.compile(r"\[Krusgraph plan (plan-[0-9a-f]+), schema (.+?) \((sha256:[0-9a-f]+)\), (\d+) links?\]")
DESCRIPTION_LIMIT = 256


def plan_mark(rv: dict, p, schema: str) -> dict:
    """What an output is built from: the review's plan id and schema fingerprint, the exact schema name and the number
    of links left after the review (its rejections taken out)."""
    return {"plan_id": rv.get("plan_id"), "schema_fingerprint": rv.get("schema_fingerprint"), "schema": schema,
            "links": len(p.relationships)}


def mark_text(mark: dict) -> str:
    n = mark["links"]
    return (f"[Krusgraph plan {mark['plan_id']}, schema {mark['schema']} ({mark['schema_fingerprint']}), "
            f"{n} link{'' if n == 1 else 's'}]")


def mark_of_description(text) -> dict | None:
    m = MARK.search(str(text or ""))
    if not m:
        return None
    return {"plan_id": m.group(1), "schema": m.group(2), "schema_fingerprint": m.group(3), "links": int(m.group(4))}


def with_mark(description, mark: dict) -> str:
    """The item's description with the plan marker at its end (an older marker replaced), at most 256 characters."""
    tag = mark_text(mark)
    base = MARK.sub("", str(description or "")).strip()
    room = DESCRIPTION_LIMIT - len(tag) - 1
    if room <= 0:
        return tag[:DESCRIPTION_LIMIT]
    base = base if len(base) <= room else base[:max(room - 1, 0)].rstrip() + "…"
    return f"{base} {tag}" if base else tag


def same_plan(was: dict | None, now: dict) -> bool:
    if not was:
        return False
    return all(was.get(k) == now.get(k) for k in ("plan_id", "schema_fingerprint", "schema", "links"))


def _plan_words(m: dict) -> str:
    n = m.get("links")
    return f"schema {m.get('schema')}, {n} link{'' if n == 1 else 's'}"


def built_from(was: dict | None, now: dict) -> dict:
    """The card's line: built from a different plan (schema Shop, 6 links; now shop, 7 links), or plan unknown."""
    if was:
        words = f"built from a different plan ({_plan_words(was)}; now {now.get('schema')}, {now.get('links')} links)"
        return {"status": "different", "was": was, "now": now, "words": words}
    return {"status": "unknown", "was": None, "now": now,
            "words": f"built by Krusgraph, plan unknown (now {now.get('schema')}, {now.get('links')} links)"}


def _items_of(workspace: str, headers: dict) -> dict[str, dict]:
    """{id: item} of the workspace's items (one listing, the request's own when it has one: n222), for the descriptions."""
    return {it.get("id"): it for it in _list_items(workspace, headers)}


def recorded_mark(item_id: str, req: dict, listed: dict[str, dict]) -> dict | None:
    """The plan an existing item was built from: outputs.json's created[].plan, else its description's marker."""
    for c in req["created"]:
        if c.get("id") == item_id and isinstance(c.get("plan"), dict) and c["plan"].get("plan_id"):
            return c["plan"]
    return mark_of_description((listed.get(item_id) or {}).get("description"))


def mark_items(workspace: str, headers: dict, items: list[dict], mark: dict) -> int:
    """Write the plan marker into each created item's description (PATCH /workspaces/{ws}/items/{id}). Best effort: the
    item stands either way and outputs.json holds the plan too; a failure is logged, never raised."""
    from .deploy import FABRIC, send
    done = 0
    try:
        listed = _items_of(workspace, headers)
    except Exception as exc:  # noqa: BLE001
        log("plan_mark", outcome="list_failed", error=type(exc).__name__)
        return 0
    for c in items:
        try:
            desc = with_mark((listed.get(c["id"]) or {}).get("description"), mark)
            r = send("patch", f"{FABRIC}/v1/workspaces/{workspace}/items/{c['id']}", headers, write=True,
                     json={"description": desc}, timeout=30)
            if getattr(r, "status_code", 200) < 400:
                done += 1
            else:
                log("plan_mark", outcome="patch_failed", status=r.status_code, type=c.get("type"))
        except Exception as exc:  # noqa: BLE001
            log("plan_mark", outcome="patch_failed", error=type(exc).__name__, type=c.get("type"))
    return done


_VIEW = re.compile(r"CREATE\s+OR\s+(?:REPLACE|ALTER)\s+(?:MATERIALIZED\s+LAKE\s+)?VIEW", re.I)


def _notebook_counts(parts: dict[str, str]) -> dict:
    from .notebook import parse
    cells, code = 0, ""
    for path, text in parts.items():
        if path.endswith(".ipynb"):
            nb = json.loads(text)
            for c in nb.get("cells", []):
                cells += 1
                src = c.get("source", "")
                code += "".join(src) if isinstance(src, list) else str(src)
        elif path.endswith(".py"):
            got = parse(text)
            cells += len(got)
            code += "\n".join(t for _, t in got)
    out = {"cells": cells} if cells else {}
    views = len(_VIEW.findall(code))
    if views:
        out["views"] = views
    return out


def _report_counts(parts: dict[str, str]) -> dict:
    pages = sum(1 for p in parts if re.fullmatch(r"definition/pages/[^/]+/page\.json", p))
    visuals = sum(1 for p in parts if re.fullmatch(r"definition/pages/[^/]+/visuals/[^/]+/visual\.json", p))
    if not pages and "report.json" in parts:                      # the older PBIR-Legacy layout
        sections = json.loads(parts["report.json"]).get("sections", [])
        pages, visuals = len(sections), sum(len(s.get("visualContainers", [])) for s in sections)
    return {k: v for k, v in (("pages", pages), ("visuals", visuals)) if v}


def _model_counts(parts: dict[str, str]) -> dict:
    tables = sum(1 for p in parts if re.fullmatch(r"definition/tables/[^/]+\.tmdl", p))
    rels = len(re.findall(r"^relationship\s", parts.get("definition/relationships.tmdl", ""), re.M))
    return {k: v for k, v in (("tables", tables), ("relationships", rels)) if v}


def _agent_counts(workspace: str, agent_id: str, headers: dict) -> dict:
    """The data agent's data sources and example questions, from its staging configuration (two or three reads)."""
    from .deploy import FABRIC, send
    stage = f"{FABRIC}/v1/workspaces/{workspace}/dataAgents/{agent_id}/staging"
    r = send("get", f"{stage}/datasources", headers, write=False, timeout=30)
    r.raise_for_status()
    sources = r.json().get("value", [])
    questions = 0
    for d in sources[:5]:
        q = send("get", f"{stage}/datasources/{d.get('id')}/fewshots", headers, write=False, timeout=30)
        q.raise_for_status()
        questions += len(q.json().get("value", []))
    return {k: v for k, v in (("data_sources", len(sources)), ("questions", questions)) if v}


def existing_counts(kind: str, items: list[dict], workspace: str, headers: dict) -> dict:
    """n180: what an existing item holds, read from its definition where that is one cheap read (a notebook's cells and
    views, a report's pages and visuals, a model's tables and relationships, a data agent's example questions). Only
    what was read and found is returned: an empty answer means show no counts, never zero."""
    from .lineage import rest_definition_parts
    first = next((c for c in items if c.get("output", kind) == kind and c["type"] == KINDS[kind]["type"]), None)
    if first is None or kind in ("pipeline", "graphql", "ontology", "rayfin_app"):
        return {}
    try:
        if kind == "data_agent":
            return _agent_counts(workspace, first["id"], headers)
        fmt = "TMDL" if kind == "semantic_model" else None
        parts = rest_definition_parts(workspace, "items", first["id"], headers, fmt)
        if kind in ("silver_notebook", "gold_views"):
            return _notebook_counts(parts)
        if kind == "report":
            return _report_counts(parts)
        return _model_counts(parts)
    except Exception as exc:  # noqa: BLE001 — no counts rather than wrong ones
        log("existing_counts", output=kind, outcome="unread", error=type(exc).__name__)
        return {}


def confirm_token(kind: str, mark: dict, ids: list[str]) -> str:
    """What the Update's dry run hands the editor and its Create must send back: the update is written only for the plan
    and the items that dry run showed."""
    import hashlib
    raw = json.dumps([kind, mark.get("plan_id"), mark.get("schema"), mark.get("links"), sorted(ids)])
    return "upd-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ n180 addition 4: one refresh of a new model -------
# The founder's report of 9 November 2026, 12:40 CET showed "Error fetching data" on every visual until the new semantic
# model was refreshed by hand. Now Create refreshes a semantic model it has just created, once, and waits for it before
# the report is built on it. Power BI REST, read 9 November 2026:
#   Datasets - Refresh Dataset In Group, learn.microsoft.com/rest/api/power-bi/datasets/refresh-dataset-in-group
#     POST https://api.powerbi.com/v1.0/myorg/groups/{groupId}/datasets/{datasetId}/refreshes, body {notifyOption},
#     202 Accepted with x-ms-request-id and Location; Required Scope Dataset.ReadWrite.All; shared capacities allow
#     eight refreshes a day.
#   Datasets - Get Refresh History In Group, learn.microsoft.com/rest/api/power-bi/datasets/get-refresh-history-in-group
#     GET .../refreshes?$top=1; status Unknown (in progress), Completed, Failed (serviceExceptionJson holds the error
#     code) or Disabled; Required Scope Dataset.ReadWrite.All or Dataset.Read.All.
# The workspace id is the group id and the semantic model's id the dataset id. The token is the signed-in user's, for
# the Power BI audience (on-behalf-of, Tokens.powerbi). Only a model this request created is refreshed: never one that
# was updated, found built, or named by the person.
POWERBI = "https://api.powerbi.com/v1.0/myorg"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
REFRESH_SCOPE = "Dataset.ReadWrite.All"
REFRESH_POLL_SECONDS = 5
REFRESH_MAX_POLLS = 24                                             # two minutes; five times that in a background operation (n197)
REFRESH_STEP = "Refresh the model once (framing)"
REFRESH_PLANNED = "Create refreshes the model once; nothing else is run or scheduled."


def _refresh_reason(entry: dict) -> str:
    raw = entry.get("serviceExceptionJson") or ""
    try:
        code = json.loads(raw).get("errorCode") if raw else None
    except (ValueError, AttributeError):
        code = None
    return code or raw or f"status {entry.get('status')}"


def refresh_new_model(workspace: str, model_id: str, scopes: set[str] | None, app_id: str | None) -> dict:
    """One refresh of a semantic model this Create has just made, waited for within REFRESH_MAX_POLLS. The answer is the
    card's `refresh`: status refreshed, refreshing (still running when the wait ended), failed (with Fabric's reason) or
    not_run (the permission is missing: which one, and the Entra steps)."""
    from . import server as S
    from .deploy import send
    started = time.monotonic()

    def done(out: dict) -> dict:
        log("model_refresh", outcome=out["status"], seconds=round(time.monotonic() - started, 1))
        return out

    def no_consent(why: str) -> dict:
        return done({"status": "not_run", "reason": why, "scope": REFRESH_SCOPE, "entra_steps": entra_steps(REFRESH_SCOPE, app_id),
                     "hint": f"An administrator adds {REFRESH_SCOPE} to the workload's Entra app and consents; until then refresh "
                             "the model once in the Fabric portal before opening the report."})
    if scopes is not None and REFRESH_SCOPE not in scopes:
        return no_consent(f"Your sign-in does not carry {REFRESH_SCOPE}, which refreshing a semantic model needs.")
    w = S._WORKLOAD_TOKENS.get()
    if w is None or not hasattr(w, "powerbi"):
        return done({"status": "not_run", "reason": "no Power BI sign-in in this request"})
    try:
        headers = {"Authorization": f"Bearer {w.powerbi()}", "Content-Type": "application/json"}
        base = f"{POWERBI}/groups/{workspace}/datasets/{model_id}/refreshes"
        r = send("post", base, headers, write=True, json={"notifyOption": "NoNotification"}, timeout=30)
        status = getattr(r, "status_code", 0)
        if status in (401, 403):
            return no_consent(f"Power BI refused the refresh (HTTP {status}); it needs {REFRESH_SCOPE}.")
        if status >= 400:
            return done({"status": "failed", "reason": f"Power BI answered HTTP {status} to the refresh request"})
        request_id = (getattr(r, "headers", {}) or {}).get("x-ms-request-id")
        from . import operations                                   # n197: in the background nobody waits: ten minutes
        for _ in range(REFRESH_MAX_POLLS * (5 if operations.current() is not None else 1)):
            if REFRESH_POLL_SECONDS:
                time.sleep(REFRESH_POLL_SECONDS)
            h = send("get", base + "?$top=1", headers, write=False, timeout=30)
            if getattr(h, "status_code", 0) >= 400:
                continue
            entries = (h.json() or {}).get("value") or []
            entry = next((e for e in entries if not request_id or e.get("requestId") == request_id), None)
            if not entry or entry.get("status") == "Unknown":
                continue
            if entry.get("status") == "Completed":
                return done({"status": "refreshed"})
            return done({"status": "failed", "reason": _refresh_reason(entry)})
        return done({"status": "refreshing", "reason": "still running in Fabric when Krusgraph stopped waiting"})
    except Exception as exc:  # noqa: BLE001 — the model stands; the card says the refresh did not happen
        return done({"status": "failed", "reason": type(exc).__name__})


RUN_STEP = "Run the pipeline once in Fabric (Run) to fill the silver tables and the gold views."


# n184: the steps on a card are plain words. A tool's name means nothing to the person in Fabric ("Run
# create_silver_notebook's notebook first"); a sentence about another tool is left out.
TOOL_NAME = re.compile(r"\b(?:create|export|compare|describe|validate|plan|query)_[a-z_]+\b|\b[a-z]+(?:_[a-z]+)+_draft\b")
REPORT_REFRESH_STEP = "If the model was just created, refresh it once"


def plain_steps(steps: list[str], chosen: dict) -> list[str]:
    """The steps of a card without tool names: the silver notebook's step names the notebook this Create builds."""
    silver = chosen.get("silver_notebook")
    out = []
    for step in steps:
        step = step.replace("Run create_silver_notebook's notebook first", f"Run {silver} first" if silver else "Run the silver notebook first")
        if TOOL_NAME.search(step):
            continue
        out.append(step)
    return out


def _portal_steps(kind: str, a: dict, chosen: dict | None = None, built: dict | None = None, jobs: dict | None = None) -> list[str]:
    """What is still to do, as the tool's own answer says it, in plain words (plain_steps). The report's "refresh it once"
    stays only when this Create's model was not refreshed (failed, or skipped for want of a permission): a model Create
    refreshed, or one that existed before, needs no such step on the report's card."""
    chosen = chosen or {}
    if kind == "report":
        model = (built or {}).get("semantic_model") or {}
        status = (model.get("refresh") or {}).get("status")
        steps = [x for x in (a.get("after_creation") or []) if not (x.startswith(REPORT_REFRESH_STEP) and status not in ("failed", "not_run"))]
        return plain_steps(steps, chosen)
    if kind in ("semantic_model", "ontology"):
        return plain_steps(list(a.get("after_creation") or []), chosen)
    if kind in ("silver_notebook", "gold_views"):
        if chosen.get("pipeline") and (jobs or {}).get("run_once"):   # n197: run by this Create's pipeline, not "Run all"
            return [f"It runs in {chosen['pipeline']}: Create started one run of it (Run once); follow it on the pipeline's card."]
        return plain_steps(list(a.get("run") or []), chosen)
    if kind == "pipeline":                                         # n185: what Run once and Schedule did not do already
        res = a.get("result") or {}
        ran = (res.get("run") or {}).get("status") in ("Running", "Succeeded")
        scheduled = (res.get("schedule") or {}).get("status") == "Succeeded"
        if not ran and not scheduled:
            return [a.get("runs", ""), "To run it regularly, add a schedule on the pipeline in Fabric (Schedule); Krusgraph adds none."]
        return ([] if ran else [RUN_STEP]) + ([] if scheduled else ["To run it regularly, add a schedule on the pipeline in Fabric (Schedule)."])
    if kind == "data_agent":                                       # n185: Publish and Copilot left to do, if any
        from . import agent_publish
        steps = ["Open the agent in Fabric: its data source, selected tables and example queries are under its staging configuration."]
        if not (a.get("result") or {}).get("published"):
            steps.append(agent_publish.FABRIC_STEP)
        return steps
    return list(a.get("portal_steps") or [])


def chosen_jobs(req: dict) -> dict:
    """The pipeline's Run once and Schedule as chosen in this build ({} without a pipeline)."""
    return next(((o.get("jobs") or {}) for o in req["outputs"] if o["kind"] == "pipeline"), {})


def agent_card(o: dict, answer: dict, jobs: dict, after_run: dict | None, dry_run: bool, workspace: str, headers: dict,
               scopes: set[str] | None) -> dict:
    """The data agent card's `agent`: the layer it reads, its examples' validation, and Publish / Copilot: what Create
    will do (dry run) or did, and why not when it did not."""
    from . import agent_publish
    from .deploy import send
    opts = o.get("agent") or {"layer": "silver", "publish": False, "copilot": False}
    res = answer.get("result") or {}
    sel = res.get("selection") or {}
    out = {"layer": opts["layer"], "layer_words": answer.get("layer"), "publish": opts["publish"], "copilot": opts["copilot"],
           "where_examples": ("Krusgraph's example questions are the agent's example queries (Example queries pane, per data source): "
                              "Fabric uses them to answer. The chat's suggested questions are Fabric's own; no documented API sets them.")}
    if sel:
        out["selection"] = {k: sel.get(k) for k in ("layer", "schema", "selected", "deselected", "one_layer", "words")}
    if res.get("examples"):
        out["examples"] = res["examples"]
    # n209: with Run once ticked (or the editor's after_run call), the examples are reported only after the run succeeded
    run_once = bool(jobs.get("run_once")) or after_run is not None
    run_status = (after_run or {}).get("status")
    if not dry_run and res.get("examples") and run_once and run_status != "Succeeded":
        # n197: Fabric checks each example query against the tables the agent reads, and the pipeline's run is writing the
        # silver tables now ("Failed to connect to server ...datawarehouse...", 10 November 2026): not checked yet.
        # n209: a run that ended without success leaves them not checked too (and nothing is published: decide)
        ended = run_status not in (None, "Running", "NotStarted", "Unknown")
        out["examples"] = {"status": "not_checked", "count": res["examples"].get("count"),
                           "words": RUN_NOT_OK_WORDS.format(status=str(run_status).lower()) if ended else NOT_CHECKED_WORDS}
    elif not dry_run and res.get("examples") and res.get("id") and res.get("datasource_id"):
        # n209: after the run succeeded, or without Run once: a failure to connect is sent once more, never "invalid"
        out["examples"] = recheck_examples(workspace, res["id"], res["datasource_id"], res.get("examples") or {}, headers)
    if not dry_run and out.get("examples") is not res.get("examples") and isinstance(answer.get("result"), dict):
        answer["result"]["examples"] = out["examples"]             # n209: the tool's answer says the same as the card

    def http(method, url, **kw):
        return send(method, url, headers, write=method != "get", timeout=30, **kw)
    if dry_run:
        out["words"] = ([agent_publish.publish_words(o["name"])] if opts["publish"] else
                        ["Create leaves the agent a draft only you see: tick Publish the agent in Fabric to publish it."])
        if opts["publish"] and jobs.get("run_once"):
            out["words"].append("It is published after the pipeline's run has succeeded.")
        if opts["copilot"]:
            out["words"].append(agent_publish.copilot_words(o["name"]))
            out["copilot_preflight"] = agent_publish.copilot_preflight(http, workspace, scopes)
        return out
    d = agent_publish.decide(opts["publish"], sel.get("one_layer") if sel else None, run_once, run_status)
    out["decision"] = d
    out["published"] = False
    agent_id = res.get("id")
    if d["publish"] and agent_id:
        r = http("post", f"{FABRIC_API}/v1/workspaces/{workspace}/dataAgents/{agent_id}/staging/publish",
                 json={"publishedDescription": agent_publish.DESCRIPTION.format(source=o["name"])})
        status = getattr(r, "status_code", 0)
        if status < 400:
            out["published"] = True
            out["words"] = [f"Published {o['name']} in Fabric: people with access to the workspace can use it."]
        else:
            out["decision"] = {"publish": False, "state": "draft",
                               "why": f"Fabric refused to publish (HTTP {status}); it stays a draft. Publish it in Fabric (Publish)."}
    if not out["published"]:
        out["words"] = [out["decision"]["why"]]
    if opts["copilot"]:
        out["copilot_preflight"] = agent_publish.copilot_preflight(http, workspace, scopes)
        out["copilot_step"] = agent_publish.COPILOT_STEP
    log("agent_publish", state="published" if out["published"] else out["decision"]["state"], copilot=opts["copilot"])
    return out


FABRIC_API = "https://api.fabric.microsoft.com"
NOT_CHECKED_WORDS = ("Example queries: not checked yet. Fabric checks them against the tables the agent reads, which the "
                     "pipeline's run is writing now; Krusgraph checks them when the run has succeeded.")
RUN_NOT_OK_WORDS = ("Example queries: not checked yet. The pipeline's run {status}, so the tables the agent reads may not be "
                    "written; Krusgraph checks the examples only after a run that succeeded, and published nothing.")
CONNECT_WORDS = ("Example queries: {n} not checked yet. Fabric could not connect to the tables the agent reads ({reason}); "
                 "Krusgraph sent them once more and Fabric still could not connect. This says nothing about the queries "
                 "themselves: Fabric checks them again when they are opened in the agent's Example queries pane.")
_CONNECT = re.compile(r"connect|network|timeout|unavailable|transport", re.I)
RECHECK_WAITS = (5, 5, 10, 10)                                     # seconds, at most thirty in all


def _connect_failures(examples: dict) -> list[dict]:
    """The examples Fabric marked Invalid only because it could not connect (the _CONNECT reasons)."""
    return [x for x in examples.get("invalid_examples") or [] if _CONNECT.search(str(x.get("reason") or ""))]


def _not_checked(examples: dict, failed: list[dict]) -> dict:
    """n209: the examples with those Fabric could not connect for moved out of Invalid into "not checked yet", with
    Fabric's reason in words. Only a real query error stays invalid."""
    qs = {x.get("question") for x in failed}
    real = [x for x in examples.get("invalid_examples") or [] if x.get("question") not in qs]
    reason = next((str(x["reason"]) for x in failed if x.get("reason")), "could not connect")
    return {**examples, "invalid": len(real), "invalid_examples": real, "not_checked": len(failed),
            "not_checked_examples": [{"question": x.get("question"), "reason": str(x.get("reason") or reason)} for x in failed],
            "not_checked_words": CONNECT_WORDS.format(n=len(failed), reason=reason)}


def recheck_examples(workspace: str, agent_id: str, ds_id: str, examples: dict, headers: dict, sleep=time.sleep) -> dict:
    """n197: an example Fabric marked Invalid because it could not connect (the run was still writing the tables) is
    sent once more (its query written again, which makes Fabric validate it again), then the status is read until none
    is Validating, for at most RECHECK_WAITS. Any other reason stands: a query that is wrong is not retried.
    n209: sent once more exactly once; an example that still could not connect, or whose second sending (or the reading
    after it) failed, reads "not checked yet" with Fabric's reason, never invalid."""
    from . import data_agent
    from .deploy import send
    stage = f"{FABRIC_API}/v1/workspaces/{workspace}/dataAgents/{agent_id}/staging"
    url = f"{stage}/datasources/{ds_id}/fewshots"
    bad = _connect_failures(examples)
    if not bad:
        return examples

    class _Http:                                                   # data_agent's helpers call requests.get(url, headers=..)
        @staticmethod
        def get(u, headers=None, timeout=60):
            return send("get", u, headers, write=False, timeout=timeout)
    try:
        rows = send("get", url, headers, write=False, timeout=60).json().get("value", [])
        for row in rows:
            if any(row.get("question") == b.get("question") for b in bad):
                send("patch", f"{url}/{row['id']}", headers, write=True, json={"query": row.get("query")}, timeout=60)
    except Exception as exc:  # noqa: BLE001 — n209: the first reading stands, those that could not connect not checked yet
        log("agent_examples", outcome="recheck_failed", error=type(exc).__name__)
        return _not_checked(examples, bad)
    questions = [r.get("question") for r in rows]
    now = examples
    for wait in RECHECK_WAITS:
        sleep(wait)
        now = data_agent.example_status(_Http, headers, url, questions)
        if now.get("status") != "read" or not now.get("validating"):
            break
    if now.get("status") != "read":                                # n209: not read after the second try: as first read
        now = _not_checked(examples, bad)
    elif _connect_failures(now):                                   # n209: still could not connect: not checked yet
        now = _not_checked(now, _connect_failures(now))
    now = {**now, "rechecked": len(bad)}
    log("agent_examples", outcome="rechecked", invalid=now.get("invalid"), not_checked=now.get("not_checked", 0), rechecked=len(bad))
    return now


def _jobs_card(o: dict, answer: dict, permission: dict, dry_run: bool) -> dict:
    """The pipeline card's `jobs`: what was asked, the permission, the dry run's sentences, and after Create the run
    (started; the editor reads on) and the schedule (created or updated, its id and next run)."""
    from . import pipeline_jobs
    jobs = o.get("jobs") or {}
    run_once, spec = bool(jobs.get("run_once")), jobs.get("schedule")
    out = {"run_once": run_once, "schedule": spec, "permission": permission}
    if not (run_once or spec):
        out["words"] = ["Nothing runs and nothing is scheduled: tick Run once or Schedule to have Create do it."]
        return out
    if permission["granted"] is False:
        out["words"] = ["Neither runs: " + permission["why"]]
        return out
    out["words"] = pipeline_jobs.describe(o["name"], run_once, spec)
    res = answer.get("result") or {}
    if not dry_run:
        if "run" in res:
            out["run"] = res["run"]
        if "schedule" in res:
            out["schedule_result"] = res["schedule"]
    return out


def _jobs_on_built(o: dict, done: list[dict], permission: dict, dry_run: bool, workspace: str, headers: dict,
                   schedule_ids: list[str]) -> dict:
    """n197: a pipeline already built from this plan is not written again, but Run once and Schedule, when ticked, still
    run it once and set its schedule (the founder's Create of 10 November 2026 skipped the built pipeline, and Next said
    it had not run). The dry run says the same words it says for a new pipeline."""
    from . import pipeline_jobs
    from .deploy import send
    jobs = o.get("jobs") or {}
    pipe = next((c for c in done if c["type"] == "DataPipeline"), None)
    if dry_run or not pipe or not (jobs.get("run_once") or jobs.get("schedule")) or permission["granted"] is False:
        return _jobs_card(o, {}, permission, dry_run)

    def http(method, url, **kw):
        return send(method, url, {**headers, "Content-Type": "application/json"}, write=method != "get", timeout=30, **kw)
    try:
        res = pipeline_jobs.apply(http, workspace, pipe["id"], o["name"], bool(jobs.get("run_once")), jobs.get("schedule"),
                                  ours=schedule_ids, wait_seconds=0)
    except Exception as exc:  # noqa: BLE001 — said on the card, the pipeline stands
        res = {"run": {"status": "NotStarted", "why": f"Krusgraph could not start the run ({type(exc).__name__})"}}
    return _jobs_card(o, {"result": res}, permission, False)


def _created_ids(kind: str, a: dict, chosen: dict, workspace: str, o: dict, req: dict) -> list[dict]:
    """The items the tool's answer says were created, with their ids; nothing the answer does not hold."""
    res = a.get("result") or {}
    typ = KINDS[kind]["type"]
    if kind == "pipeline":
        out = []
        for t, n in _names(o, chosen, req["schema"]):
            r = res.get(n) or {}
            if r.get("status") == "Succeeded" and r.get("id"):
                out.append({"type": t, "id": r["id"], "name": n, "workspace": workspace, "output": kind})
        return out
    if kind == "data_agent":
        rid = res.get("id") or res.get("agent_id")
        return [{"type": typ, "id": rid, "name": o["name"], "workspace": workspace, "output": kind}] if res.get("status") == "Succeeded" and rid else []
    if res.get("status") == "Succeeded" and res.get("id"):
        return [{"type": typ, "id": res["id"], "name": o["name"], "workspace": workspace, "output": kind}]
    return []


def _report_on_draft(model_answer: dict, model_name: str, name: str) -> dict:
    """create_report's dry run for a report on the semantic model this same build makes: the visuals are drawn from that
    model's TMDL in the dry run (report.definition_parts, as create_report draws them from the model it reads)."""
    from . import model_compare as _mc, report as _report, server as S
    parts = model_answer.get("parts") or {}
    drawn = _report.definition_parts(_mc.from_tmdl(parts), "<the semantic model's id, filled in when it is created>",
                                     model_name=model_name)
    rep = {"name": name, "pages": 1, "visuals": drawn["visuals"],
           "bound_to": {"semantic_model": model_name, "id": None, "built_in_this_build": True},
           "drawn_from": "the measures and columns of the semantic model in this dry run (its TMDL)"}
    if drawn.get("left_out"):
        rep["left_out"] = [{"measure": f"{m['table']}[{m['measure']}]", "why": m["why"]} for m in drawn["left_out"]]
    if model_answer.get("omitted"):
        rep["partial"] = "Some table definitions of the model did not fit in the dry run; Create draws from the whole model."
    return {"dry_run": True, "report": rep, "rest": {"method": "POST", "delegated_scope": _report.SCOPE, "spec": _report.DEFINITION_SPEC},
            "after_creation": list(S.REPORT_AFTER_CREATION)}


def _call(kind: str, o: dict, chosen: dict, req: dict, keys, confirmed, dry_run: bool, built: dict) -> dict:
    """The MCP tool behind the output, called as the tool is called (same arguments, same answer)."""
    from . import server as S
    common = {"workspace": req["workspace"], "source": req["source"], "schema": req["schema"], "keys": keys,
              "confirmed": confirmed, "dry_run": dry_run}
    if kind == "silver_notebook":
        text = S.create_silver_notebook(name=o["name"], **common)
    elif kind == "gold_views":
        text = S.create_gold_views(name=o["name"], **common)
    elif kind == "pipeline":
        jobs = o.get("jobs") or {}
        allowed = jobs_permission(token_scopes(), None)["granted"] is not False     # n185: without the scope, neither runs
        token = S.PIPELINE_JOBS.set({"wait": 0, "schedule_ids": list(req.get("schedule_ids") or []),
                                     "plan": req.get("plan_mark")})       # n200: the health rows name this review's plan
        try:
            text = S.create_pipeline(name=o["name"], silver_name=chosen.get("silver_notebook", ""), gold_name=chosen.get("gold_views", ""),
                                     run_once=bool(jobs.get("run_once")) and allowed,
                                     schedule=(jobs.get("schedule") if allowed else None), **common)
        finally:
            S.PIPELINE_JOBS.reset(token)
    elif kind == "semantic_model":
        text = S.create_semantic_model(name=o["name"], **common)
    elif kind == "ontology":
        text = S.create_ontology(name=o["name"], **common)
    elif kind == "data_agent":                                     # n185: one layer; publishing is decided after (agent_card)
        text = S.create_data_agent(name=o["name"], publish=False, layer=(o.get("agent") or {}).get("layer", "silver"), **common)
    elif kind == "rayfin_app":                                     # n181: preflight first, then the package (rayfin_app.py)
        from . import rayfin_app
        from .deploy import write_and_wait, find_item
        headers = S._headers(None)
        pre, off = rayfin_app.first_check(headers, token_scopes(), dry_run)
        if off:
            return off
        p, info = S._source_inputs(req["workspace"], req["source"], req["schema"], keys, confirmed, None)
        ws = S._out_ws(info["workspace_id"])                       # n221: the App goes to the build's workspace
        create = (lambda url, body: write_and_wait(f"{S.FABRIC}/v1/workspaces/{ws}/appBackends", body, headers, mode="created",
                                                   item_type="AppBackend", find=lambda: find_item(ws, o["name"], headers, "AppBackend")))
        return rayfin_app.answer(p, info, headers, o["name"], o.get("app"), dry_run, token_scopes(), S._out_ws(req["workspace"]),
                                 create=None if dry_run else create, pre=pre, title=(req.get("product") or {}).get("name"))
    elif kind == "report":
        model = o.get("model")
        if not model:
            m = built.get("semantic_model")
            if m is None or m.get("refusal") or (m.get("answer") or {}).get("error"):
                return {"error": "the semantic model of this build was not made, so the report has nothing to be built on; nothing was "
                                 "created.", "kind": "not_found", "hint": "Fix the semantic model first, or name an existing model."}
            if dry_run:
                return _report_on_draft(m["answer"], chosen["semantic_model"], o["name"])
            model = next((c["id"] for c in m.get("created", [])), None) or chosen["semantic_model"]
        text = S.create_report(workspace=req["workspace"], model=model, name=o["name"], dry_run=dry_run)
    else:
        raise BadRequest(kind)
    return json.loads(text)


def _product(req: dict, rv: dict, p, cards: list[dict], dry_run: bool) -> dict:
    """The data product: one name over the outputs of this build, with the domains domain_draft proposes for the plan,
    an owner nobody has chosen yet and the plan's version. Items only as the build's answers name them."""
    from . import domains as _domains
    proposal = _domains.draft(p, req["schema"], req["source_name"])
    items = []
    for c in cards:
        if c.get("refusal") or (c.get("answer") or {}).get("error"):
            continue
        if dry_run:
            items.append({"output": c["output"], "type": c["type"], "name": c["name"], "would": c["would"],
                          "decision": (c.get("decision") or decision_of(c))["action"]})   # n209: skip and choose are not "would be updated"
        else:
            items += [{**x, "label": c["label"]} for x in c.get("created", [])]
    return {"name": req["product"]["name"], "owner": None, "owner_note": "Nobody has chosen an owner yet.",
            "plan": {"plan_id": rv.get("plan_id"), "schema_fingerprint": rv.get("schema_fingerprint"),
                     "review_version": rv.get("version")},
            "source": {"lakehouse": req["source_name"], "schema": req["schema"]},
            "items": items,
            "domains": [{"name": d["name"], "tables": list(d["tables"]), "why": d.get("name_reason", "")} for d in proposal["domains"]],
            "unassigned": [u["table"] for u in proposal.get("unassigned", [])],
            "from": "domain_draft's proposal for this plan: domains are proposed, not created (that needs a Fabric administrator)"}


def _flow(req: dict, p, chosen: dict, cards: list[dict], keys, confirmed) -> dict | None:
    """The data flow when the build has the silver notebook, the gold views or the pipeline (data_flow.py)."""
    from . import data_flow, server as S
    if not set(chosen) & set(data_flow.FLOW_KINDS):
        return None
    _, info = S._source_inputs(req["workspace"], req["source"], req["schema"], keys, confirmed, None)   # the build's own read
    info, refusal = S._write_info(info, "The data flow")           # n201: a read-only source flows into the target lakehouse
    if refusal:
        return None
    items = []
    for c in cards:
        if c["output"] not in data_flow.ON_SOURCE + ("report",) or c.get("refusal"):
            continue
        reads = f"reads the source tables in {req['schema']} (bronze) directly"
        if "gold_views" in chosen:                                 # n179: said plainly when gold views are built in the same run
            reads += ", not the gold views built in this run"
        it = {"output": c["output"], "label": c["label"], "name": c["name"], "reads": reads}
        if c["output"] == "semantic_model" and isinstance((c.get("answer") or {}).get("parts"), dict):
            it.update(code=data_flow.tmdl_excerpt(c["answer"]["parts"]), language="tmdl", code_title=f"{c['name']}: relationships and measures")
        if c["output"] == "report":
            model = next((x for x in req["outputs"] if x["kind"] == "report"), {}).get("model")
            if model:
                it["reads"] = f"on the existing model {model}"
            else:
                it.update(on_model="item:semantic_model", reads=f"on {chosen.get('semantic_model')}")
        items.append(it)
    names = None
    if "pipeline" in chosen:
        names = (chosen.get("silver_notebook") or f"silver_{req['schema']}", chosen.get("gold_views") or f"gold_{req['schema']}",
                 f"{chosen['pipeline']}_check")
    out = data_flow.flow(p, info, chosen, pipeline_names=names, items=items)
    if info.get("target") and isinstance(out, dict):              # n201: said on the flow, where the dry run shows it
        out["target"] = info["target"]
        if isinstance(out.get("notes"), list):
            out["notes"].insert(0, info["target"]["words"])
    return out


AFTER_RUN_REFRESH = "Create refreshes the model once, after the pipeline's run has succeeded."


def _runs_first(req: dict, chosen: dict) -> bool:
    """n197: Run once is ticked on a pipeline of this build: the model's refresh, the report and the agent's examples
    wait for the run's success (the editor sends them then)."""
    return "pipeline" in chosen and bool(chosen_jobs(req).get("run_once"))


def run_refresh_only(req: dict) -> dict:
    """n197: after the pipeline's run has succeeded, the semantic model this Model made is refreshed once (only:
    [semantic_model], refresh_only: true). Its card as Create gives it, with the refresh; nothing else is written."""
    from . import server as S
    o = next(x for x in req["outputs"] if x["kind"] == "semantic_model")
    scopes = token_scopes()
    app_id = getattr(S._WORKLOAD_TOKENS.get(), "app_id", None)
    made = [c for c in req["created"] if c.get("output") == "semantic_model" and c.get("name", "").lower() == o["name"].lower()]
    card = {"output": "semantic_model", "label": KINDS["semantic_model"]["label"], "type": "SemanticModel", "name": o["name"],
            "dry_run": False, "would": "create", "updates_in_place": True, "permissions": permissions("semantic_model", scopes),
            "created": made, "answer": {"dry_run": False, "refresh_only": True}}
    if not made:
        card["refresh"] = {"status": "not_run", "reason": f"{o['name']} is not among the items this Model built."}
    else:
        headers = S._headers(None)
        ws = made[0].get("workspace") or build_place(req, headers)["workspace_id"]   # n221: where the model was built
        card["refresh"] = refresh_new_model(ws, made[0]["id"], scopes, app_id)
    log("build_output", output="semantic_model", dry_run=False, outcome="refresh:" + card["refresh"]["status"], seconds=0)
    return _with_schema({"dry_run": False, "outputs": [card], "order": ["semantic_model"], "left_out_by_review": [],
                         "refused": 0, "to_decide": 0, "note": "The model was refreshed once." if card["refresh"]["status"] == "refreshed"
                         else "The model's refresh: " + card["refresh"]["status"] + ".", "created": made}, req)


def run_build_many(req: dict) -> dict:
    """Every output chosen, in ORDER, each through its MCP tool on the plan the review left (rejections taken out),
    as the signed-in user. A dry run first; Create with dry_run=false. Each output gets one card: the tool's answer,
    create or update, the permissions it needs, and with Create the items and the portal steps left. An item of the same
    name that this Model did not build is never written; a missing permission is said before any call."""
    from . import server as S, review as R
    rv = R.read(req["review"])
    carried = R.carried_arguments(rv)
    keys, confirmed = carried["keys"] or None, carried["confirmed"] or None
    dry_run, scopes = req["dry_run"], token_scopes()
    app_id = getattr(S._WORKLOAD_TOKENS.get(), "app_id", None)
    chosen = {o["kind"]: o["name"] for o in req["outputs"]}
    ours = {c["id"] for c in req["created"]}
    cards, built, left = [], {}, []

    def adjust(plan):                                              # the review's rejections, on every plan of the build
        kept, left_out = apply_review(plan, rv)
        if not left:
            left.append(left_out)
        return kept
    checked = checked_keys(rv)                                     # n221: the row check and the review, into silver

    def adjust_checked(plan):
        from dataclasses import replace
        kept = adjust(plan)
        return replace(kept, checked_keys=checked) if checked and hasattr(kept, "checked_keys") else kept
    tgt = req.get("target") or {}
    place = build_place(req, S._headers(None))                     # n221: the item's workspace by default
    write_target = S.WRITE_TARGET.set({"lakehouse": tgt.get("lakehouse"), "create": tgt.get("create_lakehouse"),
                                       "workspace_name": place["name"]})   # n201: a read-only source; n221: another workspace
    build_in = S.BUILD_IN.set(place["workspace_id"] if place["cross"] else None)
    try:
        made = None
        if not dry_run and place["cross"] and tgt.get("create_lakehouse") and not tgt.get("lakehouse") and needs_lakehouse(req):
            made = ensure_lakehouse(place["workspace_id"], tgt["create_lakehouse"], S._headers(None), req)
            if made.get("error"):
                return _with_schema({"dry_run": False, "outputs": [], "order": [], "left_out_by_review": [], "refused": 1,
                                     "to_decide": 0, "build_in": place, "error": made["error"], "kind": made.get("kind", "bad_input"),
                                     "hint": made.get("hint", ""), "note": made["error"]}, req)
        with _one_listing():                                # n222: the workspace's items listed once, not per name
            out = _build_many(req, S, rv, keys, confirmed, dry_run, scopes, app_id, chosen, ours, cards, built, left, adjust_checked,
                              place)
        out["build_in"] = place
        if made and made.get("made"):
            out["lakehouse_made"] = made
        return out
    finally:
        S.BUILD_IN.reset(build_in)
        S.WRITE_TARGET.reset(write_target)


def checked_keys(rv: dict) -> dict:
    """n221: the keys this build may de-duplicate silver on beyond the plan's own (K0, K1, R5): every key of the review
    that is not rejected and whose row check passed (not stale: what it rests on has not changed since), and every key
    accepted in the review. {table: {columns, how: rows|accepted, checked_at}}; the row check wins over the acceptance."""
    out = {}
    for it in rv.get("items", []):
        if it.get("type") != "key" or it.get("review") == "rejected" or not it.get("columns"):
            continue
        c = it.get("check") or {}
        if c.get("status") == "passed":
            out[it["table"]] = {"columns": list(it["columns"]), "how": "rows", "checked_at": c.get("checked_at") or ""}
        elif it.get("review") == "accepted":
            out[it["table"]] = {"columns": list(it["columns"]), "how": "accepted", "checked_at": ""}
    return out


def _workspace_name(ws_id: str, headers: dict) -> str:
    from . import server as S
    try:
        return next((w.get("displayName") or w.get("name") or "" for w in S._workspaces(headers)
                     if str(w.get("id") or "").lower() == ws_id.lower()), "")
    except Exception:                                              # noqa: BLE001 — the name is words only; the id decides
        return ""


def build_place(req: dict, headers: dict) -> dict:
    """n221: where this build's outputs go. target.workspace (the editor sends the Model item's own workspace by default,
    or the source's when the person chose that); without it, the source's workspace as before. `cross`: it is not the
    source's, so the source is read across workspaces."""
    from . import server as S
    source_ws = S._workspace_id(req["workspace"], headers)
    tgt = req.get("target") or {}
    ws = (tgt.get("workspace") or source_ws).lower()
    cross = ws != str(source_ws).lower()
    where = tgt.get("where") or ("item" if cross else "source")
    name = _workspace_name(ws, headers)
    whose = "this item's workspace" if where == "item" else "the source's workspace"
    words = (f"Builds in {('the workspace ' + name) if name else 'workspace ' + ws} ({whose}"
             + (", the same as the source's" if where == "item" and not cross else "")
             + (f"; the source {req.get('source_name') or ''} is read from its own workspace" if cross else "") + ").")
    return {"workspace_id": ws, "name": name, "where": where, "cross": cross, "source_workspace_id": str(source_ws).lower(),
            "words": words}


def needs_lakehouse(req: dict) -> bool:
    """n221: whether the outputs this request builds write Delta tables (silver, gold, the pipeline's check) or read them."""
    kinds = set(req.get("only") or [o["kind"] for o in req["outputs"]])
    agent = next((o for o in req["outputs"] if o["kind"] == "data_agent"), None)
    return bool(kinds & {"silver_notebook", "gold_views", "pipeline"}) or (
        "data_agent" in kinds and (agent.get("agent") or {}).get("layer", "silver") != "source")


LAKEHOUSE_DOC = "https://learn.microsoft.com/rest/api/fabric/lakehouse/items/create-lakehouse"


def ensure_lakehouse(ws: str, name: str, headers: dict, req: dict) -> dict:
    """n221: the lakehouse the person asked Create to make in the build's workspace (Items - Create Lakehouse, POST
    /v1/workspaces/{ws}/lakehouses with creationPayload.enableSchemas true; Lakehouse.ReadWrite.All or Item.ReadWrite.All,
    Contributor). One of that name already there is used, not made again, so the per-output requests of one Create make
    it once. Only after a dry run named it, and only when ticked."""
    from . import server as S
    from .deploy import find_item, write_and_wait
    try:
        hit = find_item(ws, name, headers, "Lakehouse")
    except Exception as exc:                                       # noqa: BLE001
        from .errors import explain
        return explain(exc, f"Lakehouse {name!r}")
    if hit:
        return {"id": hit, "name": name, "workspace": ws, "made": False}
    body = {"displayName": name, "creationPayload": {"enableSchemas": True},
            "description": f"Made by Krusgraph for the silver tables and gold views of {req.get('source_name') or 'the source'}."}
    r = write_and_wait(f"{S.FABRIC}/v1/workspaces/{ws}/lakehouses", body, headers, mode="created", item_type="Lakehouse",
                       find=lambda: find_item(ws, name, headers, "Lakehouse"))
    if r.get("status") == "Succeeded" and r.get("id"):
        log("lakehouse_made", outcome="ok")
        return {"id": r["id"], "name": name, "workspace": ws, "made": True, "doc": LAKEHOUSE_DOC}
    from .errors import classify_http
    if r.get("http"):
        got = classify_http(int(r["http"]), r.get("body", ""), f"creating the lakehouse {name!r}")
    else:
        got = {"error": f"Fabric did not confirm the lakehouse {name!r} in time.", "kind": "timeout",
               "hint": "Choose Create again in a minute: a lakehouse of that name is used, not made twice."}
    log("lakehouse_made", outcome=str(got.get("kind")))
    return {**got, "error": got.get("error") or f"The lakehouse {name!r} was not made; nothing else was written."}


def _build_many(req, S, rv, keys, confirmed, dry_run, scopes, app_id, chosen, ours, cards, built, left, adjust, place=None) -> dict:
    with S.plan_scope(adjust):
        headers = S._headers(None)
        workspace = place["workspace_id"] if place else S._workspace_id(req["workspace"], headers)   # n221: where outputs go
        source_ws = place["source_workspace_id"] if place else workspace   # n221: the source is read in its own workspace
        p, _item, _ = S._plan(source_ws, req["source"], req["schema"], keys, confirmed, None)
        req = _exact(req, p.schema.schema)                         # n175: every output reads and writes the exact name
        mark = plan_mark(rv, p, req["schema"])                     # n180: what every item of this build is built from
        req = {**req, "plan_mark": mark}                           # n200: handed to the pipeline's health step
        listing: list[dict] = []

        def listed() -> dict:
            if not listing:
                listing.append(_items_of(workspace, headers))
            return listing[0]
        def one(o: dict) -> dict | None:
            """The card of one output (None: not part of this request)."""
            kind = o["kind"]
            if req.get("only") and kind not in req["only"]:
                return None                                        # n179: chosen with this Create, built by its own request
            card = {"output": kind, "label": KINDS[kind]["label"], "type": KINDS[kind]["type"], "name": o["name"], "dry_run": dry_run,
                    "updates_in_place": KINDS[kind]["updates"], "permissions": permissions(kind, scopes)}
            if o.get("model"):
                card["model"] = o["model"]
            if req.get("finish"):                                  # n179: no tool runs; the cards from what was created
                made = [c for c in req["created"] if c.get("output") == kind and c.get("id")]
                card.update(would="create", created=made, dry_run=False)
                if not made:
                    card["refusal"] = {"error": f"{KINDS[kind]['label']} {o['name']!r} was not created in this Create.", "kind": "not_built",
                                       "hint": "Its own card said why; choose Create again to retry it."}
                card["decision"] = decision_of(card)
                return card
            started = time.monotonic()
            updating = kind in req.get("update", [])
            # n197/n209: the dry run asks the same question Create asks (skip_built), through one function, so it predicts what
            # Create does: an item built from this plan is "already built, will be skipped" in both, never "would be updated"
            if (req.get("skip_built") or dry_run) and not updating:
                said = existing_decision(o, chosen, req, workspace, headers, ours, mark, listed, dry_run)
                if said is not None:
                    card.update(said["card"])
                    if said["adopted"] and not dry_run:
                        mark_items(workspace, headers, said["adopted"], mark)
                    if said["outcome"] == "already_built" and kind == "pipeline":   # n197: Run once and Schedule still do what they say
                        card["jobs"] = _jobs_on_built(o, card["created"], jobs_permission(scopes, app_id), dry_run, workspace, headers,
                                                      req.get("schedule_ids") or [])
                    card["decision"] = decision_of(card)
                    log("build_output", output=kind, dry_run=dry_run, outcome=said["outcome"], seconds=round(time.monotonic() - started, 1))
                    return card
            update_ids: list[str] = []
            if updating:                                           # n180: the person chose Update for this output
                for typ, name in _names(o, chosen, req["schema"]):
                    existing = S._find_item(workspace, name, headers, typ)
                    if existing and (existing in ours or _krusgraph_made(workspace, name, headers, typ)):
                        ours.add(existing)
                        update_ids.append(existing)
                if update_ids:
                    was = next((m for m in (recorded_mark(i, req, listed()) for i in update_ids) if m and not same_plan(m, mark)), None)
                    card["built_from"] = built_from(was, mark)
                    card["confirm_update"] = confirm_token(kind, mark, update_ids)
            would, refusal, _found = _ownership(o, chosen, req, workspace, headers, ours)
            card["would"] = would
            missing = card["permissions"]["missing"]
            if refusal is None and missing and not dry_run:
                refusal = _consent(kind, missing, app_id)
            if refusal is None and updating and not dry_run and update_ids and req["confirm"].get(kind) != card.get("confirm_update"):
                refusal = {"error": f"{KINDS[kind]['label']} {o['name']!r} is updated only after its dry run; nothing was written.",
                           "kind": "dry_run_first",
                           "hint": "Choose Update to see what would change, then confirm the update."}
            if refusal is not None:
                card["refusal"] = refusal
                log("build_output", output=kind, dry_run=dry_run, outcome="refused:" + str(refusal.get("kind")), seconds=0)
            else:
                if missing:                                        # the dry run says it now, Create would refuse
                    card["consent"] = _consent(kind, missing, app_id)
                try:                                               # n222: a dry run writes nothing, so its tools read the
                    tool = (lambda: _run_graphql({**req, "name": o["name"], "dry_run": dry_run}) if kind == "graphql"   # request's
                            else _call(kind, o, chosen, req, keys, confirmed, dry_run, built))          # listing; Create's do not
                    answer = tool() if dry_run else _outside_listing(tool)
                except BadRequest:
                    raise
                except Exception as exc:                           # noqa: BLE001 — explained per card, never leaked
                    from .errors import explain
                    answer = explain(exc, f"{KINDS[kind]['label']} {o['name']!r}")
                if answer.get("kind") == "consent" and answer.get("scope"):
                    answer["entra_steps"] = entra_steps(str(answer["scope"]).split(" ")[0], app_id)
                card["answer"] = answer
                if kind == "data_agent" and not answer.get("error"):   # n185: the layer, the examples, Publish and Copilot
                    card["agent"] = agent_card(o, answer, chosen_jobs(req), req.get("after_run"), dry_run, workspace, headers, scopes)
                    if not dry_run and card["agent"].get("published"):
                        answer.setdefault("result", {})["published"] = True
                if kind == "pipeline":                             # n185: the two choices, what they will do or did
                    card["jobs"] = _jobs_card(o, answer, jobs_permission(scopes, app_id), dry_run)
                if kind == "semantic_model" and not answer.get("error") and dry_run and would == "create":
                    card["refresh"] = {"status": "planned", "note": AFTER_RUN_REFRESH if _runs_first(req, chosen) else REFRESH_PLANNED}
                    if scopes is not None and REFRESH_SCOPE not in scopes:
                        card["refresh"].update(scope=REFRESH_SCOPE, entra_steps=entra_steps(REFRESH_SCOPE, app_id),
                                               hint=f"Without {REFRESH_SCOPE} Create cannot refresh it: refresh it once in the portal.")
                log("build_output", output=kind, dry_run=dry_run, outcome=answer.get("kind") if answer.get("error") else "ok",
                    seconds=round(time.monotonic() - started, 1))
                if not dry_run and not answer.get("error"):
                    card["created"] = (answer.get("created") or []) if kind == "graphql" else _created_ids(kind, answer, chosen, workspace, o, req)
                    for c in card["created"]:
                        c.setdefault("output", kind)
                        c["plan"] = mark                           # n180: outputs.json keeps what it was built from
                        ours.add(c["id"])
                    card.pop("confirm_update", None)
                    if card["created"]:
                        mark_items(workspace, headers, card["created"], mark)
                    card["portal_steps"] = _portal_steps(kind, answer, chosen, built, chosen_jobs(req))
                    if kind == "data_agent" and card.get("agent"):    # n185: the state outputs.json keeps; Copilot's portal step
                        for c in card["created"]:
                            c["published"] = bool(card["agent"].get("published"))
                        if card["agent"].get("decision", {}).get("state") == "waiting":
                            card["portal_steps"] = [x for x in card["portal_steps"] if not x.startswith("In Fabric, open the agent → Publish,")]
                        if card["agent"].get("copilot"):
                            from . import agent_publish
                            card["portal_steps"].append(agent_publish.COPILOT_STEP)
                    new_model = next((c["id"] for c in card["created"] if c["type"] == "SemanticModel"), None)
                    if kind == "semantic_model" and would == "create" and new_model and _runs_first(req, chosen):
                        card["refresh"] = {"status": "planned", "note": AFTER_RUN_REFRESH}   # n197: after the run succeeded
                    elif kind == "semantic_model" and would == "create" and new_model:   # only a model this request created
                        card["refresh"] = refresh_new_model(workspace, new_model, scopes, app_id)
                        if card["refresh"]["status"] == "refreshed":
                            card["portal_steps"] = [x for x in card["portal_steps"] if not x.startswith(REFRESH_STEP)]
            card["decision"] = decision_of(card)                  # n209: one action per card, the same in the dry run and Create
            return card
        _all_cards(req, dry_run, one, cards, built)
        out = {"dry_run": dry_run, "outputs": cards, "order": [c["output"] for c in cards],
               "left_out_by_review": left[0] if left else [],
               "row_check": check_totals(rv)}
        where = next(((c.get("answer") or {}).get("target") for c in cards if (c.get("answer") or {}).get("target")), None)
        if where:                                                  # n201: the lakehouse silver, gold and the check write to
            out["target"] = where
        if req.get("product"):
            out["product"] = _product(req, rv, p, cards, dry_run)
        if req.get("products"):                                    # n222: the ticked suggestions
            out["products"] = _chosen_products(req, p, cards, dry_run)
        out["flow"] = None if req.get("only") else _flow(req, p, chosen, cards, keys, confirmed)   # n179: finish draws it
    refused = [c for c in cards if c.get("refusal") or (c.get("answer") or {}).get("error")]
    out["refused"] = len(refused)
    out["to_decide"] = sum(1 for c in cards if c.get("built_from") and c.get("choices"))
    ok = len(cards) - len(refused) - out["to_decide"]
    out["note"] = (NOTHING_CHANGED + " This is what Create would send, output by output." if dry_run else
                   f"{ok} of {len(cards)} output(s) built." + (f" {out['to_decide']} wait for your choice: Update or a new name."
                                                              if out["to_decide"] else "")
                   + (_runs_note(cards) if cards else ""))
    if not dry_run:
        out["created"] = [x for c in cards for x in c.get("created", [])]
    if req.get("finish"):
        out["note"] = f"{len(cards) - len(refused)} of {len(cards)} output(s) are in Fabric." + (_runs_note(cards) if cards else "")
    return _with_schema(out, req)


# ------------------------------------------------------------------ n222: the dry run's outputs side by side --------
# The founder's live test of 11 November 2026: "Preparing the dry run of each output..." took long, one output after
# another. A dry run writes nothing, so its outputs are prepared at once, DRY_RUN_THREADS at a time, each in a copy of
# the request's context (the review's plan, read once; the token; the request's item listing); the report waits for its
# semantic model's card, whose definition it is drawn on. The cards keep the request's order. A Create keeps one output
# after the other (the editor sends one output per request and runs those that do not depend on each other at once).
DRY_RUN_THREADS = 4
PREPARED_WORDS = "Dry run: {done} of {total} outputs prepared ({names})."


def _all_cards(req: dict, dry_run: bool, one, cards: list[dict], built: dict) -> None:
    """Every output's card into `cards` (request order) and `built` (by kind); see above."""
    from . import operations
    outputs = list(req["outputs"])
    got: dict[int, dict | None] = {}
    if not dry_run:
        for i, o in enumerate(outputs):
            got[i] = one(o)
            if got[i] is not None:
                built[o["kind"]] = got[i]
    else:
        later = [i for i, o in enumerate(outputs) if o["kind"] == "report" and not o.get("model")]
        first = [i for i in range(len(outputs)) if i not in later]
        total = sum(1 for o in outputs if not (req.get("only") and o["kind"] not in req["only"]))
        lock, ready = threading.Lock(), []

        def run(i: int) -> None:
            card = one(outputs[i])
            with lock:
                got[i] = card
                if card is not None:
                    built[outputs[i]["kind"]] = card
                    ready.append(card["label"])
                    operations.progress(None, words=PREPARED_WORDS.format(done=len(ready), total=total, names=", ".join(ready)))
        with ThreadPoolExecutor(max_workers=max(1, min(DRY_RUN_THREADS, len(first)))) as pool:
            for f in [pool.submit(contextvars.copy_context().run, run, i) for i in first]:
                f.result()                                         # an exception is raised here, as the loop raised it
        for i in later:
            run(i)
    cards.extend(got[i] for i in sorted(got) if got[i] is not None)


# ------------------------------------------------------------------ n197: one Create step in the background ---------
# In a background operation (operations.py) no browser waits, so a step can wait for Fabric as long as Fabric needs:
#   - throttling (HTTP 429, PFE_FABRIC_THROTTLED: kind throttled or rate_limited) means Fabric did not take the request;
#     the step is sent again after CAPACITY_WAITS, with what it already made adopted (pending), and the card says
#     "waiting for capacity" with the Capacity Metrics app's link meanwhile. Never failed for it within the waits.
#   - a long-running operation still going when the tool's own wait ended (kind timeout) is followed: the operation's
#     state and the items' names are read every PENDING_POLL seconds for at most PENDING_MAX; once every item is in the
#     workspace the step is asked again with skip_built, which adopts them (nothing is written twice). "Still running in
#     Fabric" is pending, never failed.
CAPACITY_KINDS = ("throttled", "rate_limited")
CAPACITY_WAITS = (20, 40, 80, 160, 300, 300, 300)                 # about twenty minutes in all
CAPACITY_APP = "https://learn.microsoft.com/fabric/enterprise/metrics-app"
CAPACITY_WORDS = ("Waiting for capacity: Fabric is throttling this workspace's capacity, so the step is tried again by itself "
                  "(attempt {n}, next in {s} s). Nothing failed. The Capacity Metrics app shows what uses the capacity.")
PENDING_POLL = 20
PENDING_MAX = 20 * 60
PENDING_WORDS = ("Still running in Fabric: {label} {name} was sent and Fabric is finishing it. Krusgraph follows it and adopts "
                 "it when it is there; nothing failed.")


def _step_problem(out: dict) -> tuple[str | None, dict]:
    """(kind, card) of a one-output build answer: the error kind of its card (or of the whole answer), else None."""
    if out.get("error"):
        return out.get("kind"), {}
    card = (out.get("outputs") or [{}])[0]
    ans = card.get("answer") or {}
    if ans.get("error"):
        return ans.get("kind"), card
    if (card.get("refusal") or {}).get("kind"):
        return card["refusal"]["kind"], card
    return None, card


def _operations_of(answer: dict) -> list[str]:
    """The Fabric operation ids a tool's answer names (result.operation, or per item for the pipeline)."""
    ops, res = [], answer.get("result") or {}
    for v in [res] + [x for x in res.values() if isinstance(x, dict)]:
        if isinstance(v, dict) and isinstance(v.get("operation"), str):
            ops.append(v["operation"])
    return ops


def _items_there(req: dict, kind: str) -> tuple[bool, list[str]]:
    """(every item of the output is in the workspace, the names still missing), one read per name."""
    from . import server as S
    o = next(x for x in req["outputs"] if x["kind"] == kind)
    chosen = {x["kind"]: x["name"] for x in req["outputs"]}
    headers = S._headers(None)
    workspace = build_place(req, headers)["workspace_id"]          # n221: the build's workspace
    missing = [name for typ, name in _names(o, chosen, req["schema"]) if not S._find_item(workspace, name, headers, typ)]
    return not missing, missing


def _operation_failed(op: str) -> dict | None:
    """Fabric's own answer when the operation it runs has Failed; None while it runs or when it cannot be read."""
    from . import server as S
    from .deploy import FABRIC, send
    try:
        r = send("get", f"{FABRIC}/v1/operations/{op}", S._headers(None), write=False, timeout=30)
        body = r.json() if getattr(r, "status_code", 0) == 200 else {}
    except Exception:  # noqa: BLE001 — reading again later is always safe
        return None
    return body if isinstance(body, dict) and body.get("status") == "Failed" else None


def run_build_step(req: dict, sleep=time.sleep, clock=time.monotonic) -> dict:
    """One Create step (only: [kind], dry_run false) in a background operation: run_build_many, throttling waited out and
    Fabric's long-running operations followed (above). The answer is run_build_many's, as the synchronous route gives it."""
    from . import operations
    kind = req["only"][0]
    o = next(x for x in req["outputs"] if x["kind"] == kind)
    label = KINDS[kind]["label"]
    chosen = {x["kind"]: x["name"] for x in req["outputs"]}
    sent = datetime.now(timezone.utc).isoformat()                 # n207: before the first attempt, so only what it made is newer
    mine = [{"type": t, "name": n, "output": kind, "at": sent} for t, n in _names(o, chosen, req["schema"])]
    attempt, followed = 0, 0
    while True:
        out = run_build_many(req)
        problem, card = _step_problem(out)
        if problem in CAPACITY_KINDS and attempt < len(CAPACITY_WAITS):
            wait = CAPACITY_WAITS[attempt]
            attempt += 1
            operations.progress("waiting_capacity", words=CAPACITY_WORDS.format(n=attempt + 1, s=wait), capacity_app=CAPACITY_APP,
                                attempt=attempt + 1, wait=wait)
            log("build_step", output=kind, outcome="waiting_capacity", attempt=attempt)
            sleep(wait)
            req = {**req, "pending": (req.get("pending") or []) + mine}   # what the throttled attempt made is ours
            operations.progress("running", words=None, capacity_app=None, attempt=None, wait=None)
            continue
        if problem in CAPACITY_KINDS:                              # still throttled after the waits: said, never "failed"
            out["capacity"] = {"words": "Fabric is still throttling the capacity after about twenty minutes; try again later.",
                               "capacity_app": CAPACITY_APP}
            if card:
                card["waiting_capacity"] = True
            return out
        if problem == "timeout" and card and followed < 2:         # Fabric is still working on it: follow, never fail
            followed += 1
            ops = _operations_of(card.get("answer") or {})
            operations.progress("pending_fabric", words=PENDING_WORDS.format(label=label, name=o["name"]))
            until = clock() + PENDING_MAX
            there, missing = False, []
            while clock() < until:
                sleep(PENDING_POLL)
                failed = next((f for f in (_operation_failed(x) for x in ops) if f), None)
                if failed:
                    from .errors import classify_http
                    err = failed.get("error") if isinstance(failed.get("error"), dict) else {}
                    card["answer"] = {**(card.get("answer") or {}),
                                      **classify_http(400, json.dumps(err) if err else "", f"creating {label} {o['name']!r}")}
                    return out
                try:
                    there, missing = _items_there(req, kind)
                except Exception as exc:  # noqa: BLE001 — a failed read is read again at the next poll
                    log("build_step", output=kind, outcome="pending_read_failed", error=type(exc).__name__)
                    continue
                if there:
                    break
            if not there:
                card["pending_fabric"] = True
                card["answer"] = {**(card.get("answer") or {}), "kind": "pending_fabric",
                                  "error": f"{label} {o['name']} is still being created in Fabric after {PENDING_MAX // 60} minutes.",
                                  "hint": "It is recorded as pending: when Fabric finishes it, Try again adopts it as built by "
                                          "this Model. " + (f"Not there yet: {', '.join(missing)}." if missing else "")}
                return out
            operations.progress("running", words=None)
            req = {**req, "skip_built": True, "pending": (req.get("pending") or []) + mine}
            continue                                               # asked again: the items there are adopted, the rest made
        return out


def _runs_note(cards: list[dict]) -> str:
    """' Nothing runs or is scheduled.' unless the pipeline's Run once or Schedule did something (n185)."""
    j = next((c.get("jobs") for c in cards if c.get("output") == "pipeline" and c.get("jobs")), None) or {}
    did = []
    if (j.get("run") or {}).get("run_id"):
        did.append("one pipeline run was started")
    if (j.get("schedule_result") or {}).get("status") == "Succeeded":
        did.append("the pipeline's schedule was " + j["schedule_result"]["mode"])
    return " " + (" and ".join(did).capitalize() + "; nothing else runs." if did else "Nothing runs or is scheduled.")


# ------------------------------------------------------------------ HTTP -------------------------------------------

class Tokens:
    """Fabric and SQL tokens for the signed-in user, from the workload app's on-behalf-of exchange."""

    def __init__(self, obo, user_token: str, tenant: str, app_id: str | None = None) -> None:
        self.obo, self.user_token, self.tenant, self.app_id = obo, user_token, tenant, app_id

    def refresh(self, other: "Tokens") -> None:
        """n197: a later poll's sign-in replaces this one, so a long background step never outlives its token."""
        if getattr(other, "user_token", None) and other.tenant == self.tenant:
            self.user_token = other.user_token

    def fabric(self) -> str:
        from .entra import FABRIC_SCOPE
        return self.obo.token(self.user_token, self.tenant, FABRIC_SCOPE)

    def sql(self) -> str:
        from .entra import SQL_SCOPE
        return self.obo.token(self.user_token, self.tenant, SQL_SCOPE)

    def powerbi(self) -> str:
        """n180: for the Power BI REST API (a new semantic model's one refresh)."""
        return self.obo.token(self.user_token, self.tenant, POWERBI_SCOPE)


def cors_headers(origin: str | None) -> dict:
    if origin and FABRIC_ORIGIN.match(origin.lower()):
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin", "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Prefer", "Access-Control-Max-Age": "600"}
    return {"Vary": "Origin"}


def who(claims: dict) -> str:
    """n210: the signed-in person's name for outputs.json ('by whom') and the page's Me button. A B2B guest's token can
    lack name and preferred_username and carry only email; its upn, when present, is the guest form
    eva_contoso.com#EXT#@publisher.onmicrosoft.com, and unique_name may start with the identity provider (live.com#).
    Never the tenant or object id."""
    for key in ("name", "preferred_username", "email", "upn", "unique_name"):
        v = claims.get(key)
        if not isinstance(v, str) or not v.strip():
            continue
        v = v.strip()
        if "#EXT#" in v.upper():                                  # eva_contoso.com#EXT#@pub... -> eva@contoso.com
            local = v[:v.upper().index("#EXT#")]
            v = local[:local.rfind("_")] + "@" + local[local.rfind("_") + 1:] if "_" in local else local
        elif "#" in v:                                            # live.com#eva@contoso.com -> eva@contoso.com
            v = v.rsplit("#", 1)[1]
        if v:
            return v[:120]
    return ""


PILOT_PAGE = "https://krusgraph.com/pilot/fabric"


def tenant_refusal(tenant: str) -> dict:
    """What a signed-in user from a tenant outside KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS sees in the editor (n176): who to ask
    and what to send, in plain words. The tenant id is the user's own; nothing about other tenants is said."""
    return {"error": "Krusgraph is not turned on for your organisation yet.",
            "hint": (f"It runs for a small number of pilot organisations. Your Fabric administrator can ask for it at "
                     f"hello@krusgraph.com with your tenant id, {tenant}; the steps are at {PILOT_PAGE}. Nothing was read or "
                     f"changed."),
            "kind": "tenant_not_allowed", "tenant": tenant, "pilot_page": PILOT_PAGE}


def routes(cfg, validator=None, obo=None) -> list:
    """The three routes, bound to the workload app's validator and on-behalf-of exchange (doubles in tests)."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route
    from .entra import Validator, OnBehalfOf, TokenError, TenantNotAllowed
    from .errors import explain
    from .workload_host import same_host_origin       # n168: the hosted editor's own calls are same-origin, no CORS
    validator = validator or Validator(cfg)
    obo = obo or OnBehalfOf(cfg)

    def reply(body: dict, status: int, origin: str | None, extra: dict | None = None) -> Response:
        return JSONResponse(body, status_code=status, headers={**SECURITY_HEADERS, **cors_headers(origin), **(extra or {})})

    def licence(req: dict, tid: str) -> dict | None:
        from . import entitlements
        if not entitlements.enabled():
            return None
        return entitlements.check("create_backend", req["dry_run"], tid)

    def endpoint(parse, run, where: str, gate=None):
        async def handler(request):
            """n179: whatever fails, the answer is JSON with the CORS headers, and the cause is logged. Without them the
            browser reports only 'Failed to fetch' and the editor cannot say which output or why."""
            started = time.monotonic()
            origin = request.headers.get("origin")
            try:
                response = await inner(request, origin)
            except Exception as exc:  # noqa: BLE001 — logged by type and route, answered without details
                log("route_failed", route=where, error=type(exc).__name__, seconds=round(time.monotonic() - started, 1))
                return reply({"error": f"The Krusgraph engine stopped on this {where} request ({type(exc).__name__}); nothing more "
                                       "was done after that point.", "kind": "unexpected",
                              "hint": "Try again. If it repeats, the server's log has the cause (event route_failed)."}, 500, origin)
            if response.status_code >= 400:
                log("route_answer", route=where, status=response.status_code, seconds=round(time.monotonic() - started, 1))
            return response

        async def inner(request, origin):
            if origin and not FABRIC_ORIGIN.match(origin.lower()) and not same_host_origin(origin):
                return reply({"error": "this API answers only the Krusgraph editor inside Fabric", "kind": "origin"}, 403, None)
            if request.method == "OPTIONS":
                return Response(status_code=204, headers={**SECURITY_HEADERS, **cors_headers(origin)})
            a = request.headers.get("authorization", "")
            token = a[7:].strip() if a.lower().startswith("bearer ") else ""
            if not token:
                return reply({"error": "sign-in required", "kind": "sign_in"}, 401, origin,
                             {"WWW-Authenticate": 'Bearer error="invalid_request"'})
            try:
                claims = await run_in_threadpool(validator.validate, token)
            except TenantNotAllowed as e:              # n176: a clear answer the editor shows, not a sign-in loop
                return reply(tenant_refusal(e.tenant), 403, origin)
            except TokenError as e:
                return reply({"error": str(e), "kind": "sign_in"}, 401, origin, {"WWW-Authenticate": 'Bearer error="invalid_token"'})
            try:
                req = parse(json.loads(await request.body() or b"null"))
            except (ValueError, BadRequest) as e:
                return reply({"error": str(e) if isinstance(e, BadRequest) else "the body is not valid JSON",
                              "kind": "bad_request"}, 400, origin)

            from . import billing
            if billing.enabled():                      # n213: one decision for every route (billing.decide)
                got = await run_in_threadpool(lambda: billing.decide(
                    str(claims.get("tid") or ""), claims.get("oid") or claims.get("sub"),
                    write=billing.route_writes(where, req), product="workload"))
                if where == "access":
                    return reply(access_answer(got), 200, origin)
                refusal = got.get("refusal")
            elif where == "access":
                return reply(access_answer({"state": "off"}), 200, origin)
            else:
                refusal = await run_in_threadpool(gate, req, str(claims.get("tid") or "")) if gate is not None else None
            if refusal is not None:
                return reply(refusal, STATUS["upgrade"], origin)

            tokens = Tokens(obo, token, claims["tid"], getattr(cfg, "client_id", None))
            if where == "product":                     # n198: who removed or adopted an item, for outputs.json
                req["by"] = who(claims)
            if where == "operation":                   # n197: the state of a background operation, for its owner only
                from . import operations
                owner = operations.owner_of(claims)
                if req.get("operation_id"):
                    got = await run_in_threadpool(operations.state, req["operation_id"], owner, tokens)
                    if got is None:
                        return reply({"error": "No such operation for this sign-in (it may have expired after two days).",
                                      "kind": "not_found"}, 404, origin)
                    return reply(got, 200, origin)
                return reply(await run_in_threadpool(operations.of_item, req["item_id"], owner), 200, origin)

            def work(fn=run):
                from .server import workload_tokens
                with workload_tokens(tokens):
                    try:
                        return fn(req)
                    except Exception as exc:  # noqa: BLE001 — explained, never leaked (errors.explain)
                        answer = explain(exc, f"{where}: workspace {req['workspace']!r}, source {req['source_name']!r}")
                        log("run_failed", route=where, error=type(exc).__name__, kind=answer.get("kind"))
                        return answer

            def answered(out: dict) -> tuple[dict, int]:
                return out, (STATUS.get(out.get("kind"), 502) if "error" in out else 200)
            if "respond-async" in request.headers.get("prefer", "").lower():
                # n197: answer at once; the work goes on in a thread and the editor reads POST /operation until it ends
                from . import operations
                fn = run_build_background if where == "build" else run
                try:
                    op = await run_in_threadpool(
                        lambda: operations.start(where, operations.owner_of(claims), lambda: answered(work(fn)), tokens=tokens,
                                                 item=req.get("item_id"), output=(req.get("only") or [None])[0],
                                                 create=req.get("create_id")))
                    return reply(op, 202, origin, {"Preference-Applied": "respond-async"})
                except Exception as exc:  # noqa: BLE001 — no store to keep it in: answered the way it was before n197
                    log("op_start_failed", route=where, error=type(exc).__name__)
            out, status = answered(await run_in_threadpool(work))
            return reply(out, status, origin)
        return handler

    return [Route(f"{PREFIX}/schemas", endpoint(schemas_request, run_schemas, "schemas"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/review", endpoint(review_request, run_review, "review"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/check", endpoint(check_request, run_check, "check"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/build", endpoint(build_request, run_build, "build", gate=licence), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/pipeline-run", endpoint(pipeline_run_request, run_pipeline_status, "pipeline-run"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/operation", endpoint(operation_request, run_operation, "operation"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/product", endpoint(product_request, run_product, "product"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/health", endpoint(health_request, run_health, "health"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/access", endpoint(access_request, None, "access"), methods=["POST", "OPTIONS"])]


def access_request(body) -> dict:
    """n213: POST /workload/v1/access {} - the organisation's trial or subscription in one line, for the editor. The
    editor calls it when the item opens, which is also what starts the trial (billing.decide). Takes no fields."""
    if body is not None and not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object (or empty)")
    return {"workspace": "", "source_name": ""}


def access_answer(got: dict) -> dict:
    """n213: what the editor shows: one quiet line (`words`, empty when there is nothing to say), the state, the days
    left and the offer link. Never a user id or another tenant's anything."""
    return {k: got[k] for k in ("state", "words", "days_left", "trial_ends", "offer_url", "notice") if k in got} | {
        "words": got.get("words") or ""}


# ------------------------------------------------------------------ n200: health per data product -------------------

def health_request(body) -> dict:
    """n200: POST /workload/v1/health (docs/HEALTH.md). Read-only. Two forms: {workspace, source, products: [{name,
    plan_id}]}; or the Data product page's {workspace, item_id, product}, where the lakehouse and the plan id are read
    from the Krusgraph Model item's own definition (source.json and outputs.json)."""
    from . import health as H
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    if "products" not in body and "source" not in body and body.get("item_id") is not None:
        ws, item = body.get("workspace"), body.get("item_id")
        if not isinstance(ws, str) or not _GUID.match(ws) or not isinstance(item, str) or not _GUID.match(item):
            raise BadRequest("'workspace' and 'item_id' are the Krusgraph Model's workspace and item ids (GUIDs)")
        name = body.get("product")
        name = name.strip()[:200] if isinstance(name, str) and name.strip() else "this data product"
        return {"workspace": ws.lower(), "item_id": item.lower(), "source": "", "source_name": "", "product_name": name}
    req = {"workspace": _text(body, "workspace"), "source": _text(body, "source"),
           "source_name": _text(body, "source_name", body.get("source"))}
    products = body.get("products")
    if not isinstance(products, list) or not 1 <= len(products) <= 50:
        raise BadRequest("'products' must be a list of 1 to 50 {name, plan_id}")
    out = []
    for x in products:
        if not isinstance(x, dict) or not isinstance(x.get("plan_id"), str) or not H.PLAN_ID.match(x["plan_id"]):
            raise BadRequest("each product needs plan_id as outputs.json records it (plan-<hex>)")
        name = x.get("name", x["plan_id"])
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise BadRequest("a product's name is a non-empty text of at most 200 characters")
        out.append({"name": name.strip(), "plan_id": x["plan_id"]})
    return {**req, "products": out}


def run_health(req: dict) -> dict:
    """n200: one health word per data product (green, amber, red, not checked yet) and the open findings of its latest
    run, read from the lakehouse's health table through its SQL analytics endpoint as the signed-in user. Nothing in
    Fabric changes; the answer holds names, rules, statuses and counts, never a row value."""
    from . import health as H, server as S
    headers = S._headers(None)
    if req.get("item_id"):                                        # the Data product page's form
        found = _health_target(req, headers)
        if found is None:
            return _with_word({"products": H.summarize([], [{"name": req["product_name"], "plan_id": "plan-000000"}]),
                               "table": "krusgraph.health", "read_as": "the signed-in user",
                               "note": "This Krusgraph Model has no plan or lakehouse recorded yet: nothing to read. " + NOTHING_CHANGED})
        return _with_word(run_health({**req, **found, "item_id": None}))
    workspace = S._workspace_id(req["workspace"], headers)
    item = S._resolve_source(workspace, req["source"], headers)
    enabled = bool(item.get("schemas_enabled", True))
    execute = S._execute_factory(item, S.auth.sql(None))
    try:
        found = execute(H.exists_sql(enabled))                    # rows as dicts (platforms.fabric.connect)
        there = bool(found) and int(next(iter(found[0].values()), 0) or 0) > 0
        rows = list(execute(H.read_sql(enabled, sorted({p["plan_id"] for p in req["products"]})))) if there else []
    finally:
        getattr(execute, "close", lambda: None)()
    table = "krusgraph.health" if enabled else "dbo.krusgraph_health"
    return {"products": H.summarize(rows, req["products"]), "table": table, "read_as": "the signed-in user",
            "note": (("" if there else f"The table {table} does not exist yet: the pipeline has not run since it got its health "
                                       "step. ") + NOTHING_CHANGED + " The health table holds names, rules, statuses and counts, "
                     "never a row value.")}


def _health_target(req: dict, headers: dict) -> dict | None:
    """n200: the lakehouse whose health table the pipeline writes (source.json's target for a read-only source, else the
    source lakehouse) and the data product's plan id (outputs.json), read from the Model item's definition as the user."""
    import base64
    from . import health as H, product_life as life
    from .lineage import _definition_response
    r = _definition_response(f"{life.FABRIC}/v1/workspaces/{req['workspace']}/items/{req['item_id']}/getDefinition", headers)
    parts = (r.json().get("definition") or {}).get("parts", [])
    outputs = life.outputs_of_definition(parts) or {}
    source = {}
    for p in parts:
        if p.get("path") == "source.json":
            try:
                source = json.loads(base64.b64decode(p.get("payload") or "").decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                source = {}
    plan = ((outputs.get("product") or {}).get("plan") or {}).get("plan_id")
    if not plan:
        marks = [(c.get("plan") or {}).get("plan_id") for c in outputs.get("created") or [] if isinstance(c, dict)]
        plan = next((m for m in reversed(marks) if m), None)
    target = source.get("target") or {}
    lakehouse = target.get("itemId") or (source.get("itemId") if str(source.get("itemType", "")).lower() == "lakehouse" else None)
    # n221: a build in another workspace than the source's keeps its lakehouse's workspace with it (target.workspaceId)
    ws = (target.get("workspaceId") if target.get("itemId") else None) or source.get("workspaceId") or req["workspace"]
    if not plan or not H.PLAN_ID.match(str(plan)) or not lakehouse:
        return None
    return {"workspace": ws, "source": lakehouse, "source_name": target.get("displayName") or source.get("displayName") or lakehouse,
            "products": [{"name": req["product_name"], "plan_id": plan}]}


def _with_word(out: dict) -> dict:
    """n200: the one product's word at the top, as the Data product page reads it (word, words, checked_at)."""
    p = (out.get("products") or [{}])[0]
    fails = sum(f["status"] == "fail" for f in p.get("findings", []))
    warns = sum(f["status"] == "warn" for f in p.get("findings", []))
    words = ("every check passed in the latest run" if p.get("health") == "green" else
             ", ".join(x for x in (f"{fails} failed" if fails else "", f"{warns} warning(s)" if warns else "") if x) + " in the latest run"
             if p.get("findings") else "the pipeline has not written a health row for this plan yet")
    return {**out, "word": p.get("health"), "status": p.get("health"), "words": words, "checked_at": p.get("checked_at")}
