"""The engine API of the Fabric workload, phase 1 (n166; docs/WORKLOAD-FEASIBILITY.md sections 2-3 and "Phase 1").

The "Krusgraph Model" item (workload/) is an editor that Fabric shows in an iframe. It cannot read a lakehouse's
columns itself (the SQL analytics endpoint speaks TDS), so it calls two routes here with a Bearer token that the Fabric
host issued for the workload's own Entra app (entra.WorkloadConfig, a separate audience from the MCP app):

  POST /workload/v1/review   source -> the review file (review.py): keys and relationships with their rules, review
                             and check status; with `previous` (the item's saved review.json) the decisions carry over
  POST /workload/v1/build    the reviewed plan -> an API for GraphQL item (create_backend's path); dry_run defaults to
                             true and then nothing is written

Every call runs as the signed-in user: the token is exchanged on-behalf-of the user (entra.OnBehalfOf, the same code
the MCP server uses) for Fabric and SQL tokens, so Fabric's own permissions decide what the user may read or create.
Nothing is stored here. Answers carry names, types, rules, decisions and counts, never a row value, a token or a secret.

Browsers may call these routes only from Fabric's own domains (CORS) and the answers may only be framed by them (CSP
frame-ancestors). The routes exist only when the KRUSGRAPH_WORKLOAD_* variables are set (server.build_app).

n171: with KRUSGRAPH_ENTITLEMENTS=1, /build with dry_run=false runs the same licence check as the MCP tools
(entitlements.check for create_backend on the token's tid); with KRUSGRAPH_MARKETPLACE=1 as well, a tenant without an
active Marketplace subscription gets `kind: upgrade` (HTTP 402) with the offer's link, which the editor shows as it shows
every error (error and hint). /review and every dry run stay free. With the flags off nothing here changes.
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
LATER = {"semantic_model": "Semantic model", "report": "Report", "pipeline": "Pipeline", "ontology": "Ontology",
         "data_agent": "Data agent"}
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
    return {**req, "previous": prev, "decisions": decisions}


def build_request(body) -> dict:
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")
    req = _source(body)
    name = _text(body, "name", limit=123)
    if not _NAME.match(name):
        raise BadRequest(f"item name {name!r}: letters, digits and underscores only")
    outputs = body.get("outputs", ["graphql"])
    if not isinstance(outputs, list) or not outputs:
        raise BadRequest("'outputs' must be a non-empty list; phase 1 builds ['graphql']")
    later = [o for o in outputs if o not in OUTPUTS]
    if later:
        raise BadRequest(f"not available yet: {', '.join(map(str, later))}. The Krusgraph Model builds an API for GraphQL "
                         f"for now; {', '.join(LATER.values())} come later.")
    dry_run = body.get("dry_run", True)
    if not isinstance(dry_run, bool):
        raise BadRequest("'dry_run' must be true or false (default true)")
    if not isinstance(body.get("review"), dict):
        raise BadRequest("'review' (the item's review.json) is required: the build uses its decisions")
    return {**req, "name": name, "outputs": outputs, "dry_run": dry_run, "review": body["review"]}


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


# ------------------------------------------------------------------ the two calls ------------------------------------

def run_review(req: dict) -> dict:
    """review_plan's work for the editor. The review file's source names the lakehouse and schema, not ids, so the
    saved review.json stays the same across workspaces (Git, deployment pipelines)."""
    from . import server as S, review as R
    prev = R.read(req["previous"]) if req["previous"] else None
    k, c = R.merge_arguments(R.carried_arguments(prev), None, None) if prev else (None, None)
    s, execute = S._connected(req["workspace"], req["source"], req["schema"], None)
    try:
        counted = S._within_call(execute)
        p, base = S._hosted_plan(s, k, c, counted), S._hosted_plan(s, None, None, counted)
    finally:
        getattr(execute, "close", lambda: None)()
    rv = R.build(p, base, {"platform": "fabric", "source": req["source_name"], "schema": req["schema"]},
                 decisions=req["decisions"], previous=prev)
    return {"review": rv, "summary": R.summary(rv), "attention": R.attention(rv), "counts": _counts(rv),
            "note": NOTHING_CHANGED}


def run_build(req: dict) -> dict:
    """create_backend for the editor: the plan with the review's keys and confirmed relationships, minus what was
    rejected; a dry run unless dry_run is false. Never removes relationships an existing API has (no allow_removals)."""
    from . import server as S, review as R
    rv = R.read(req["review"])
    carried = R.carried_arguments(rv)
    keys, confirmed = carried["keys"] or None, carried["confirmed"] or None
    workspace = S._workspace_id(req["workspace"], S._headers(None))
    p, item, headers = S._plan(workspace, req["source"], req["schema"], keys, confirmed, None)
    p, left_out = apply_review(p, rv)
    out = json.loads(S._create_backend_from_plan(p, item, headers, workspace, req["name"], False, None, confirmed,
                                                 False, req["dry_run"], token_provider=lambda: S.auth.fabric(None)))
    out["output"] = "graphql"
    out["left_out_by_review"] = left_out
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


# ------------------------------------------------------------------ HTTP -------------------------------------------

class Tokens:
    """Fabric and SQL tokens for the signed-in user, from the workload app's on-behalf-of exchange."""

    def __init__(self, obo, user_token: str, tenant: str) -> None:
        self.obo, self.user_token, self.tenant = obo, user_token, tenant

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
    """The two routes, bound to the workload app's validator and on-behalf-of exchange (doubles in tests)."""
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
                with workload_tokens(Tokens(obo, token, claims["tid"])):
                    try:
                        return run(req)
                    except Exception as exc:  # noqa: BLE001 — explained, never leaked (errors.explain)
                        return explain(exc, f"{where}: workspace {req['workspace']!r}, source {req['source_name']!r}")
            out = await run_in_threadpool(work)
            status = STATUS.get(out.get("kind"), 502) if "error" in out else 200
            return reply(out, status, origin)
        return handler

    return [Route(f"{PREFIX}/review", endpoint(review_request, run_review, "review"), methods=["POST", "OPTIONS"]),
            Route(f"{PREFIX}/build", endpoint(build_request, run_build, "build", gate=licence), methods=["POST", "OPTIONS"])]
