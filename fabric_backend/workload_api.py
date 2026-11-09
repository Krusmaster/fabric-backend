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
"""
from __future__ import annotations

import json
import re

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
    chosen.sort(key=lambda c: ORDER.index(c["kind"]))
    return {**req, "outputs": chosen, "dry_run": dry_run, "review": body["review"], "product": product,
            "created": [{k: c.get(k) for k in ("type", "id", "name", "workspace", "output")} for c in created], "form": 2}


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
    return _with_schema(_answer(rv), req)


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
        checks = E.validate(p, execute, max_items=req["max_items"])
    finally:
        getattr(execute, "close", lambda: None)()
    rv = R.build(p, base, {"platform": "fabric", "source": req["source_name"], "schema": req["schema"]}, previous=prev,
                 checks=checks, checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
    out = _answer(rv, NOTHING_CHANGED + " The check counted rows; it returns counts, never a value.")
    out["check"] = check_totals(rv)
    out["questions"] = rv.get("open_questions", [])
    return _with_schema(out, req)


def run_build(req: dict) -> dict:
    """Phase 1's form (a name and ["graphql"]) answers as before; n174's form ({kind, name} per output) builds several."""
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
        out["created"] = [{"type": "GraphQLApi", "id": res["id"], "name": req["name"], "workspace": workspace}]
        out["endpoint"] = endpoint_url(workspace, res["id"])
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
    out["missing"] = None if scopes is None else [alt[0] for alt in needs if not set(alt) & scopes]
    return out


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


def _ownership(o: dict, chosen: dict, req: dict, workspace: str, headers: dict, ours: set[str]) -> tuple[str, dict | None, dict]:
    """("create" or "update", a refusal or None, {name: existing id}). The Model updates only items it built itself
    (outputs.json's created ids, and those this build created); an item of that name made by anyone else is refused, and
    a report is never updated (create_report adds one item and never updates it)."""
    from . import server as S
    found, would = {}, "create"
    for typ, name in _names(o, chosen, req["schema"]):
        existing = S._find_item(workspace, name, headers, typ)
        if not existing:
            continue
        found[name] = existing
        if existing not in ours:
            return would, {"error": f"{typ} {name!r} already exists in this workspace and was not built by this Krusgraph Model; "
                                    "nothing was written.", "kind": "already_exists", "existing": {"type": typ, "id": existing, "name": name},
                           "hint": "Choose another name. The Krusgraph Model updates only the items it built itself (outputs.json)."}, found
        if not KINDS[o["kind"]]["updates"]:
            return would, {"error": f"{name!r} was built by this Model, and a {KINDS[o['kind']]['label'].lower()} is never updated in place; "
                                    "nothing was written.", "kind": "already_exists", "existing": {"type": typ, "id": existing, "name": name},
                           "hint": "Choose a new name to create another one."}, found
        would = "update"
    return would, None, found


def _portal_steps(kind: str, a: dict) -> list[str]:
    """What is still to do in the Fabric portal, as the tool's own answer says it."""
    if kind == "semantic_model" or kind in ("report", "ontology"):
        return list(a.get("after_creation") or [])
    if kind in ("silver_notebook", "gold_views"):
        return list(a.get("run") or [])
    if kind == "pipeline":
        return [a.get("runs", ""), "To run it regularly, add a schedule on the pipeline in Fabric (Schedule); Krusgraph adds none."]
    if kind == "data_agent":
        return ["Open the agent in Fabric: its data source, selected tables and example queries are under its staging configuration.",
                "Publish it there when its answers are right; the Model creates it unpublished, so only you see the draft."]
    return list(a.get("portal_steps") or [])


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
        text = S.create_pipeline(name=o["name"], silver_name=chosen.get("silver_notebook", ""), gold_name=chosen.get("gold_views", ""),
                                 **common)
    elif kind == "semantic_model":
        text = S.create_semantic_model(name=o["name"], **common)
    elif kind == "ontology":
        text = S.create_ontology(name=o["name"], **common)
    elif kind == "data_agent":
        text = S.create_data_agent(name=o["name"], publish=False, **common)
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
            items.append({"output": c["output"], "type": c["type"], "name": c["name"], "would": c["would"]})
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
    if info.get("item_kind") != "Lakehouse":
        return None
    items = []
    for c in cards:
        if c["output"] not in data_flow.ON_SOURCE + ("report",) or c.get("refusal"):
            continue
        it = {"output": c["output"], "label": c["label"], "name": c["name"], "reads": f"reads {req['schema']} (bronze) directly"}
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
    return data_flow.flow(p, info, chosen, pipeline_names=names, items=items)


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
    with S.plan_scope(adjust):
        headers = S._headers(None)
        workspace = S._workspace_id(req["workspace"], headers)
        p, _item, _ = S._plan(workspace, req["source"], req["schema"], keys, confirmed, None)
        req = _exact(req, p.schema.schema)                         # n175: every output reads and writes the exact name
        for o in req["outputs"]:
            kind = o["kind"]
            card = {"output": kind, "label": KINDS[kind]["label"], "type": KINDS[kind]["type"], "name": o["name"], "dry_run": dry_run,
                    "updates_in_place": KINDS[kind]["updates"], "permissions": permissions(kind, scopes)}
            if o.get("model"):
                card["model"] = o["model"]
            would, refusal, _found = _ownership(o, chosen, req, workspace, headers, ours)
            card["would"] = would
            missing = card["permissions"]["missing"]
            if refusal is None and missing and not dry_run:
                refusal = _consent(kind, missing, app_id)
            if refusal is not None:
                card["refusal"] = refusal
            else:
                if missing:                                        # the dry run says it now, Create would refuse
                    card["consent"] = _consent(kind, missing, app_id)
                try:
                    answer = (_run_graphql({**req, "name": o["name"], "dry_run": dry_run}) if kind == "graphql"
                              else _call(kind, o, chosen, req, keys, confirmed, dry_run, built))
                except BadRequest:
                    raise
                except Exception as exc:                           # noqa: BLE001 — explained per card, never leaked
                    from .errors import explain
                    answer = explain(exc, f"{KINDS[kind]['label']} {o['name']!r}")
                if answer.get("kind") == "consent" and answer.get("scope"):
                    answer["entra_steps"] = entra_steps(str(answer["scope"]).split(" ")[0], app_id)
                card["answer"] = answer
                if not dry_run and not answer.get("error"):
                    card["created"] = (answer.get("created") or []) if kind == "graphql" else _created_ids(kind, answer, chosen, workspace, o, req)
                    for c in card["created"]:
                        c.setdefault("output", kind)
                        ours.add(c["id"])
                    card["portal_steps"] = _portal_steps(kind, answer)
            built[kind] = card
            cards.append(card)
        out = {"dry_run": dry_run, "outputs": cards, "order": [c["output"] for c in cards],
               "left_out_by_review": left[0] if left else [],
               "row_check": check_totals(rv)}
        if req.get("product"):
            out["product"] = _product(req, rv, p, cards, dry_run)
        out["flow"] = _flow(req, p, chosen, cards, keys, confirmed)
    refused = [c for c in cards if c.get("refusal") or (c.get("answer") or {}).get("error")]
    out["refused"] = len(refused)
    out["note"] = (NOTHING_CHANGED + " This is what Create would send, output by output." if dry_run else
                   f"{len(cards) - len(refused)} of {len(cards)} output(s) built." + (" Nothing runs or is scheduled." if cards else ""))
    if not dry_run:
        out["created"] = [x for c in cards for x in c.get("created", [])]
    return _with_schema(out, req)


# ------------------------------------------------------------------ HTTP -------------------------------------------

class Tokens:
    """Fabric and SQL tokens for the signed-in user, from the workload app's on-behalf-of exchange."""

    def __init__(self, obo, user_token: str, tenant: str, app_id: str | None = None) -> None:
        self.obo, self.user_token, self.tenant, self.app_id = obo, user_token, tenant, app_id

    def fabric(self) -> str:
        from .entra import FABRIC_SCOPE
        return self.obo.token(self.user_token, self.tenant, FABRIC_SCOPE)

    def sql(self) -> str:
        from .entra import SQL_SCOPE
        return self.obo.token(self.user_token, self.tenant, SQL_SCOPE)


def cors_headers(origin: str | None) -> dict:
    if origin and FABRIC_ORIGIN.match(origin.lower()):
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin", "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Max-Age": "600"}
    return {"Vary": "Origin"}


def routes(cfg, validator=None, obo=None) -> list:
    """The three routes, bound to the workload app's validator and on-behalf-of exchange (doubles in tests)."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route
    from .entra import Validator, OnBehalfOf, TokenError
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
            origin = request.headers.get("origin")
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
            except TokenError as e:
                return reply({"error": str(e), "kind": "sign_in"}, 401, origin, {"WWW-Authenticate": 'Bearer error="invalid_token"'})
            try:
                req = parse(json.loads(await request.body() or b"null"))
            except (ValueError, BadRequest) as e:
                return reply({"error": str(e) if isinstance(e, BadRequest) else "the body is not valid JSON",
                              "kind": "bad_request"}, 400, origin)

            refusal = await run_in_threadpool(gate, req, str(claims.get("tid") or "")) if gate is not None else None
            if refusal is not None:
                return reply(refusal, STATUS["upgrade"], origin)

            def work():
                from .server import workload_tokens
                with workload_tokens(Tokens(obo, token, claims["tid"], getattr(cfg, "client_id", None))):
                    try:
                        return run(req)
                    except Exception as exc:  # noqa: BLE001 — explained, never leaked (errors.explain)
                        return explain(exc, f"{where}: workspace {req['workspace']!r}, source {req['source_name']!r}")
            out = await run_in_threadpool(work)
            status = STATUS.get(out.get("kind"), 502) if "error" in out else 200
            return reply(out, status, origin)
        return handler

    return [Route(f"{PREFIX}/review", endpoint(review_request, run_review, "review"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/check", endpoint(check_request, run_check, "check"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/build", endpoint(build_request, run_build, "build", gate=licence), methods=["POST", "OPTIONS"])]
