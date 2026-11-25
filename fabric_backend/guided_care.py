"""AP3: the caretaker in /app (guided_app.py): a "Since last time" report per data product the person built, and at
most three fixes as buttons, chosen by fixed rules.

The founder's decision (25 November 2026): "we run it for the customer", with the rule engine as the agent. No AI model
anywhere: every number in the report comes from an engine reader the product already has, called with the signed-in
person's own on-behalf-of tokens (guided_app.SessionTokens, through server.workload_tokens), and every proposal is one
rule of PROPOSE below over what those readers said. Nothing runs on a schedule, and nothing is written without the
person's click and confirm.

Which data products (find_products), in this order, at most MAX_PRODUCTS:
- the Krusgraph Model items the person can open (the Fabric workload's Model, product_life.MODEL_TYPES), in at most
  MAX_WORKSPACES of the workspaces they can see: each Model's own definition (getDefinition) gives outputs.json (what it
  built: product_life.active), source.json (the source, the schema, the build's target) and review.json (the plan the
  items were built from). The same parts the Model editor's Data product view and verify read. A Model that has built
  nothing, or whose parts cannot be read, is not a data product here.
- the items this session built through AP2's Create (guided_build.BUILDS: the dry run's inputs and review file, and
  the ids Fabric answered), unless a Model already lists them.

The report's sources, each said with the number it gave ("from verify_build", "from the last pipeline run"):
- pipeline   run_results.answer (lineage's run reader: Fabric's job list for the pipeline and its notebooks): the latest
             run's status, when, how long, the failed step with Fabric's own message and the catalog's heuristic.
- health     workload_api.run_health (the health table the pipeline's check notebook writes, read through the SQL
             analytics endpoint): the latest run's word and the failed checks by name.
- verify     workload_api.run_verify (verify_build: definitions against their dry run, figures against the rows, the
             model's refresh state and the pipeline's runs; W4/W5: the build in another workspace than the source's).
- drift      server._review_file with the plan's review as `previous`: review.build's since_previous, which is
             drift.snapshot_diff of the plan's snapshot and the source now (tables, columns, types, keys, links), the
             same comparison the drift monitor makes. With the health table's key and reference checks it says which
             links no longer hold.

The actions (PROPOSE: the first rules that hold, at most MAX_ACTIONS), each a thing the engine already does:
- run_pipeline   "Run the pipeline once": workload_api.run_item (Run On Demand, one run), only while the operator's
                 opt-in switch for pipeline runs is on (access.pipeline_execute_on) and the sign-in carries the
                 permission (workload_api.run_permission); otherwise run_manual says the step in Fabric.
- update_build   "Update the build in place": AP2's own path, re-planned on this product's review (its decisions carry
                 over), the dry run first, then the confirm dialog and Create/Update by name (guided_build.basis).
- recheck_links  "Re-check the links": the plan's keys and links counted against the rows again (evidence.validate
                 through _review_file), compared with what the plan recorded. Reads only.
- refresh_model  "Refresh the model once": the Fabric workload's refresh of the semantic model this product built
                 (workload_api.run_refresh_only), one background operation.
A writing action (run_pipeline, refresh_model) is AP2's discipline: a preview first that writes nothing and gives a
token (a digest of what it showed: the product, the action, the item's id and name as Fabric lists it now; kept in
this process for this session only, used once, CARE_TTL seconds fresh); the confirm dialog names the item; the token
and the name are sent back, the preview is made again and must give the same token, else nothing is written.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time

from .guided_app import MAX_SESSIONS, Store, log

CARE_TTL = 900                    # seconds a preview's token stays fresh
MAX_WORKSPACES = 30               # workspaces looked through for Krusgraph Model items
MAX_MODELS = 12                   # Model definitions read
MAX_PRODUCTS = 6                  # data products reported
MAX_ACTIONS = 3
LINE_MAX = 300                    # characters of one line of Fabric's own text
VERIFY_LINE_MAX = 600             # characters of one verify_build line in the report (the page lets a long one wrap)
VERIFY_LINES = 12                 # lines of the verify section
CARE_SECONDS = 40.0               # AP3b: one time budget per report, its four sections read at once (budget.py)
GRACE = 2.0                       # seconds past the budget the report waits for a section before saying "not in time"
SOURCE = {"pipeline": "from the last pipeline run", "health": "from the health check's latest run",
          "verify": "from verify_build", "drift": "from the source now, compared with the plan",
          "recheck": "counted against the rows now"}
TITLE = {"pipeline": "Pipeline runs", "health": "Health check", "verify": "What was built, read back",
         "drift": "The source since the plan"}
WRITES = ("run_pipeline", "refresh_model")
LABEL = {"run_pipeline": "Run the pipeline once", "run_manual": "How to run the pipeline", "update_build": "Update the build in place",
         "recheck_links": "Re-check the links", "refresh_model": "Refresh the model once"}
CHECKED_BY = "Checked by rules, not by AI"
STALE = "Something changed since this preview, so nothing was done."
NOTHING_DONE = "Nothing was changed in Fabric: the report only reads."
LINK_CHECKS = ("key", "orphans")

CARES = Store(MAX_SESSIONS)       # per session digest: {"products": {id: product}, "previews": {token: {...}}}
_LOCK = threading.Lock()


def _state(sid: str) -> dict:
    with _LOCK:
        st = CARES.get(sid)
        if st is None:
            st = {"products": {}, "previews": {}}
            CARES.put(sid, st, time.time() + 2 * 3600)
        return st


def _guid(v) -> bool:
    from .workload_api import _GUID
    return isinstance(v, str) and bool(_GUID.match(v))


def _cut(text, n: int = LINE_MAX) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# ------------------------------------------------------------------ finding the data products -----------------------

def _json_part(parts: dict, name: str) -> dict:
    try:
        got = json.loads(parts.get(name) or "{}")
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


def _names_of(outputs: dict) -> dict:
    """{kind: name} of the outputs a Model chose (outputs.json's outputs: [{type, name, enabled}])."""
    from .guided_build import OUTPUTS
    kinds = dict(OUTPUTS)
    return {str(o["type"]): str(o["name"]) for o in outputs.get("outputs") or []
            if isinstance(o, dict) and o.get("type") in kinds and isinstance(o.get("name"), str) and o["name"].strip()}


def model_product(ws: dict, item: dict, parts: dict) -> dict | None:
    """One data product from a Krusgraph Model's definition parts, or None when it has built nothing or lacks its plan."""
    from . import product_life as life
    outputs, source, review = _json_part(parts, "outputs.json"), _json_part(parts, "source.json"), _json_part(parts, "review.json")
    created = [c for c in life.active(outputs) if _guid(c.get("id")) and _guid(c.get("workspace"))]
    if not created or not review.get("snapshot") or not source.get("displayName") or not source.get("schema"):
        return None
    src_ws = str(source.get("workspaceId") or ws["id"]).lower()
    target = None
    t = source.get("target") if isinstance(source.get("target"), dict) else {}
    build_ws = str(t.get("workspaceId") or next((c["workspace"] for c in created if c["workspace"].lower() != src_ws), "")).lower()
    if build_ws and build_ws != src_ws and _guid(build_ws):
        target = {"workspace_id": build_ws, **({"lakehouse": str(t["displayName"])} if t.get("displayName") else {})}
    product = outputs.get("product") if isinstance(outputs.get("product"), dict) else {}
    return {"origin": "model", "name": str(product.get("name") or item.get("displayName") or source["displayName"])[:80],
            "model": {"workspace_id": ws["id"], "item_id": item["id"], "name": str(item.get("displayName") or "")},
            "c": {"workspace": src_ws, "source": str(source["displayName"]), "schema": str(source["schema"])},
            "review": review, "created": created, "target": target, "names": _names_of(outputs),
            "health": {"workspace": str(t.get("workspaceId") or src_ws) if t.get("itemId") else src_ws,
                       "source": str(t.get("itemId") or source.get("itemId") or source["displayName"])}}


def session_product(st: dict) -> dict | None:
    """The data product this session built through AP2's Create (guided_build.BUILDS), or None."""
    from .guided_build import outputs
    run = (st or {}).get("run") or {}
    created = [c for c in (st or {}).get("created") or [] if isinstance(c, dict) and _guid(c.get("id"))]
    if not created or not run.get("c") or not isinstance(run.get("rv"), dict):
        return None
    c = dict(run["c"])
    target = run.get("target")
    attached = next((x.get("attached") for x in reversed(created) if x.get("attached")), None)
    lakehouse = (target or {}).get("lakehouse") or attached or c["source"]
    return {"origin": "session", "name": f"{c['source']} · {c['schema']}", "model": None, "c": c, "review": run["rv"],
            "created": created, "target": dict(target) if target else None,
            "names": {o["kind"]: o["name"] for o in outputs(c["source"], c["schema"])},
            "health": {"workspace": (target or {}).get("workspace_id") or c["workspace"], "source": lakehouse}}


def find_products(tokens, sid: str) -> list[dict]:
    """The data products this person built: Krusgraph Model items in the workspaces they can see (outputs.json), then
    this session's own builds. Each is kept for this session under a random id; the page gets the id and the words."""
    from . import guided_build, product_life as life, server
    found: list[dict] = []
    skipped = 0
    with server.workload_tokens(tokens):
        headers = server._headers(None)
        try:
            spaces = [w for w in server._workspaces(headers) if _guid(str(w.get("id") or ""))][:MAX_WORKSPACES]
        except Exception:                                       # noqa: BLE001 — no list, no Models; the session's own still count
            spaces = []
        read = 0
        for w in spaces:
            if read >= MAX_MODELS or len(found) >= MAX_PRODUCTS:
                break
            try:
                items = server._workspace_items(str(w["id"]), headers)
            except Exception:                                   # noqa: BLE001 — a workspace that cannot be listed has none here
                continue
            for it in items:
                if not life.MODEL_TYPES.match(str(it.get("type") or "")) or not _guid(str(it.get("id") or "")):
                    continue
                if read >= MAX_MODELS or len(found) >= MAX_PRODUCTS:
                    break
                read += 1
                try:
                    parts = server._item_definition_parts(str(w["id"]), "items", it["id"], headers)
                    p = model_product({"id": str(w["id"]).lower(), "name": str(w.get("name") or "")}, it, parts)
                except Exception:                               # noqa: BLE001 — a Model not read is said, not guessed
                    skipped += 1
                    continue
                if p:
                    p["where"] = str(w.get("name") or w.get("displayName") or "")
                    found.append(p)
    mine = session_product(guided_build.BUILDS.get(sid) or {})
    listed = {c["id"].lower() for p in found for c in p["created"]}
    if mine and len(found) < MAX_PRODUCTS and not {c["id"].lower() for c in mine["created"]} & listed:
        mine["where"] = ""
        found.append(mine)
    st = _state(sid)
    st["products"] = {}
    out = []
    for p in found:
        pid = "p-" + secrets.token_urlsafe(9)
        p["id"] = pid
        st["products"][pid] = p
        out.append(summary_of(p))
    log("care_products", found=len(out), models_not_read=skipped)
    return out


def summary_of(p: dict) -> dict:
    built = sorted({str(c.get("name")) for c in p["created"] if c.get("name")}, key=str.lower)
    return {"id": p["id"], "name": p["name"], "origin": p["origin"], "built": built[:20],
            "from": (f"the Krusgraph Model {p['model']['name']}" + (f" in {p['where']}" if p.get("where") else "")
                     if p["model"] else "what you built here in this session"),
            "source": f"{p['c']['source']} · {p['c']['schema']}"}


def product(sid: str, pid) -> dict | None:
    if not isinstance(pid, str) or len(pid) > 40:
        return None
    return _state(sid)["products"].get(pid)


def basis(sid: str, pid) -> dict | None:
    """What AP2's dry run builds on for "Update the build in place": this product's review (its decisions carry over to
    the new plan), the items it built (so they are updated in place, never someone else's) and their names."""
    p = product(sid, pid)
    if p is None:
        return None
    return {"key": p["id"], "previous": p["review"], "created": list(p["created"]), "names": dict(p["names"]),
            # AP3b: what the report's verify found, so the dry run updates exactly those items and says the rest is unchanged
            **({"update": list(p["update"])} if p.get("update") is not None else {}),
            "verdicts": dict(p.get("verdicts") or {})}


# ------------------------------------------------------------------ the four sources --------------------------------

def _latest(p: dict, typ: str, output: str | None = None) -> dict | None:
    hits = [c for c in p["created"] if c.get("type") == typ and (output is None or c.get("output") in (output, None, ""))]
    return hits[-1] if hits else None


def _when(t) -> str:
    t = str(t or "")
    return (t[:16].replace("T", " ") + " UTC") if len(t) >= 16 else t


def _section(key: str, state: str, lines: list[str], **more) -> dict:
    return {"key": key, "title": TITLE[key], "source": SOURCE[key], "state": state, "lines": [x for x in lines if x], **more}


def _not_read(key: str, exc: BaseException) -> dict:
    from .errors import explain
    got = explain(exc, TITLE[key].lower())
    return _section(key, "unknown", [f"Not read: {_cut(got.get('error') or type(exc).__name__, 200)}"]), {}


def pipeline_section(p: dict) -> tuple[dict, dict]:
    """The latest runs of the pipeline this product built (run_results.answer: Fabric's job list). Reads only."""
    from . import pipeline_jobs, run_results as rr, server
    pipe = _latest(p, "DataPipeline", "pipeline")
    if pipe is None:
        return _section("pipeline", "none", ["This data product has no pipeline, so there are no runs to read."]), {"pipeline": None}
    ws = pipe.get("workspace") or (p.get("target") or {}).get("workspace_id") or p["c"]["workspace"]
    headers = server._headers(None)
    got = rr.answer(ws, pipe["id"], server._workspace_items(ws, headers), lambda w, i: server._job_instances(w, i, headers),
                    lambda w, route, i: server._item_definition_parts(w, route, i, headers), True)
    sig = {"pipeline": {"id": pipe["id"], "name": pipe["name"], "workspace": ws}}
    if got.get("kind") == "not_found":                          # AP3b: said by the name recorded at Create, not its id
        return (_section("pipeline", "unknown", [f"Not read: {pipe['name']}, the pipeline recorded at Create, is not in its "
                                                 "workspace's item list any more (deleted, or moved to another workspace)."]),
                {**sig, "pipeline_state": "unknown"})
    if got.get("error"):
        return _section("pipeline", "unknown", [f"Not read: {_cut(got['error'], 200)}"]), {**sig, "pipeline_state": "unknown"}
    runs = got.get("runs") or []
    link = pipeline_jobs.run_link(ws, pipe["id"], pipe["name"], (runs[0].get("id") if runs else None))
    if not runs:
        return (_section("pipeline", "bad", [f"{pipe['name']} has never run: the silver tables and the gold views it writes "
                                             "are not there yet."], link=link["pipeline"]),
                {**sig, "pipeline_state": "never"})
    last = runs[0]
    status = str(last.get("status") or "")
    secs = pipeline_jobs._seconds(last.get("startTimeUtc"), last.get("endTimeUtc"))
    took = pipeline_jobs.duration_words(secs)
    words = {"Completed": "succeeded", "Failed": "failed", "Cancelled": "was cancelled", "InProgress": "is running",
             "NotStarted": "is queued", "Deduped": "was skipped by Fabric (a run was already going)"}.get(status, status or "unknown")
    lines = [f"Latest run of {pipe['name']}: {words}" + (f", started {_when(last.get('startTimeUtc'))}" if last.get("startTimeUtc") else "")
             + (f", took {took}" if took and status in ("Completed", "Failed", "Cancelled") else "") + "."]
    failed_steps = [a for a in last.get("activities") or [] if a.get("status") == "Failed"]
    for a in failed_steps[:2]:
        msg = ((a.get("failure") or {}).get("message")) or ""
        lines.append(f"Failed step: {a.get('activity')}" + (f": {_cut(msg, 200)}" if msg else "") + ".")
    if status == "Failed" and not failed_steps and (last.get("failure") or {}).get("message"):
        lines.append(f"Fabric says: {_cut(last['failure']['message'], 200)}")
    diags = [a.get("diagnosis") for a in failed_steps] + [last.get("diagnosis")]   # the failed step's own error first
    diag = next((d for d in diags if d and d.get("category") not in (None, "unknown")), None)
    if diag and diag.get("next_step"):
        lines.append(f"What usually helps (a heuristic from Krusgraph's catalog of Fabric errors): {_cut(diag['next_step'], 240)}")
    bad = sum(1 for r in runs if r.get("status") in ("Failed", "Cancelled"))
    lines.append(f"Failures: {bad} of the last {_plural(len(runs), 'run')} in Fabric's run history.")
    state = {"Completed": "ok", "Failed": "bad", "Cancelled": "bad"}.get(status, "warn")
    run_state = {"Completed": "ok", "Failed": "failed", "Cancelled": "failed", "InProgress": "running", "NotStarted": "running"}.get(status, "unknown")
    return (_section("pipeline", state, lines, link=link.get("run") or link["pipeline"],
                     facts={"status": status, "seconds": secs, "failures": bad, "runs": len(runs)}),
            {**sig, "pipeline_state": run_state, "last_run": _when(last.get("startTimeUtc"))[:10] if last.get("startTimeUtc") else ""})


def health_section(p: dict) -> tuple[dict, dict]:
    """The latest health run of this product's plan (workload_api.run_health: the health table, read as the person)."""
    from . import workload_api as W
    if p["model"]:
        req = W.health_request({"workspace": p["model"]["workspace_id"], "item_id": p["model"]["item_id"], "product": p["name"],
                                **({"plan_id": p["review"]["plan_id"]} if p["review"].get("plan_id") else {})})
    else:
        if not p["review"].get("plan_id"):
            return _section("health", "none", ["No plan id is recorded for this build, so its health rows cannot be found."]), {}
        req = W.health_request({"workspace": p["health"]["workspace"], "source": p["health"]["source"],
                                "source_name": p["health"]["source"], "products": [{"name": p["name"][:200], "plan_id": p["review"]["plan_id"]}]})
    out = W.run_health(req)
    out = out if "word" in out else W._with_word(out)
    word = out.get("word")
    findings = ((out.get("products") or [{}])[0].get("findings")) or []
    fails = [f for f in findings if f.get("status") == "fail"]
    links = [f for f in fails if f.get("check") in LINK_CHECKS]
    drift = [f for f in findings if f.get("check") == "drift" and f.get("status") in ("fail", "warn")]
    head = {"green": "green", "amber": "amber", "red": "red"}.get(str(word), "")
    if not head:
        return (_section("health", "none", ["The pipeline has not written a health row for this plan yet: the check runs as "
                                            "the pipeline's last step."]),
                {"health": "none", "health_table_name": out.get("table") or "krusgraph.health",
                 # AP3b: run_health's documented answer says a missing table in its note (n200), not as a field
                 "health_table": False if "does not exist yet" in str(out.get("note") or "") else None})
    lines = [f"Latest health check: {head}, {out.get('words') or ''}"
             + (f" (run of {_when(out['checked_at'])})" if out.get("checked_at") else "") + "."]
    if links:
        lines.append(f"{_plural(len(links), 'key or link check')} failed: "
                     + ", ".join(sorted({str(f.get('object') or f.get('check')) for f in links})[:4]) + ".")
    return (_section("health", {"green": "ok", "amber": "warn", "red": "bad"}[head], lines,
                     facts={"word": head, "failed": len(fails), "link_checks_failed": len(links)}),
            {"health": head, "links_failing": len(links), "health_drift": len(drift)})


# output kind a verify line's item belongs to (guided_build.OUTPUTS / workload_api.KINDS)
OUTPUT_OF = {"semantic_model": "semantic_model", "report": "report", "pipeline": "pipeline", "api": "graphql",
             "ontology": "ontology", "app": "rayfin_app"}
NOTEBOOK_OUTPUT = {"silver_notebook", "gold_views"}
NOT_UPDATED_REPORT = "a report is never updated in place; make a new one with another name."
NOT_UPDATED_HERE = ("Update the build in place here does not rebuild this kind of item; update it from the Krusgraph Model "
                    "that built it.")


def verdicts(p: dict, lines: list) -> dict:
    """AP3b: one rule, shared by the report's proposal and the update's dry run: per output of this product, whether
    verify_build found what it built different from the dry run ("differs": a definition difference or a figure that
    differs), the same ("same") or could not tell ("not_checked"); with the items' names and whether an earlier version
    of Krusgraph built them. A notebook a pipeline writes belongs to the pipeline: its Create writes its notebooks."""
    by_name = {str(c.get("name") or "").lower(): c for c in p["created"]}
    has_pipeline = any(c.get("type") == "DataPipeline" for c in p["created"])
    out: dict = {}
    names: dict = {}
    for x in lines or []:
        if not isinstance(x, dict):
            continue
        name = str(x.get("item") or "")
        if x.get("kind") == "notebook":
            made = by_name.get(name.lower()) or {}
            kind = "pipeline" if has_pipeline else (made.get("output") if made.get("output") in NOTEBOOK_OUTPUT else "pipeline")
        else:
            kind = OUTPUT_OF.get(str(x.get("kind")), str(x.get("kind")))
        diffs = x.get("differences") or []
        differs = bool(diffs) or any(isinstance(f, dict) and f.get("state") == "differs" for f in x.get("figures") or [])
        same = not differs and "checked" in x
        state = "differs" if differs else ("same" if same else "not_checked")
        names[name.lower()] = state
        v = out.setdefault(kind, {"state": state, "items": [], "differs": [], "earlier": False})
        v["items"].append(name)
        if differs:
            v["differs"].append(name)
            v["earlier"] = v["earlier"] or any(d.get("earlier_version") for d in diffs if isinstance(d, dict))
        v["state"] = "differs" if v["differs"] else ("not_checked" if "not_checked" in (v["state"], state) else "same")
    return {"outputs": out, "items": names}


def updatable(kinds) -> list[str]:
    """The outputs /app's update can write: guided_build's outputs that the tool updates in place, in build order."""
    from . import workload_api as W
    from .guided_build import OUTPUTS
    return [k for k, _ in OUTPUTS if k in set(kinds) and W.KINDS[k]["updates"]]


def verify_section(p: dict) -> tuple[dict, dict]:
    """verify_build's rules on what this product built (workload_api.run_verify). Reads only."""
    from . import workload_api as W
    from .guided_build import verify_lines
    req = W.verify_request({"workspace": p["c"]["workspace"], "source": p["c"]["source"], "source_name": p["c"]["source"],
                            "schema": p["c"]["schema"], "review": p["review"], "created": p["created"]})
    out = W.run_verify(req)
    if out.get("error"):
        return _section("verify", "unknown", [f"Not read: {_cut(out['error'], 200)}"]), {}
    c = out.get("counts") or {}
    n, ok, differs, unchecked = (int(c.get(k) or 0) for k in ("items", "verified", "differs", "not_checked"))
    lines = [f"{_plural(n, 'item')} read back: {ok} as the dry run, {differs} {'differs' if differs == 1 else 'differ'}, "
             f"{unchecked} not checked."]
    rows = verify_lines(out)
    for x in rows:
        if x["state"] in ("differs", "not checked"):
            lines.append(_cut(x["said"], VERIFY_LINE_MAX))
    fixes = {str(f.get("action")) for f in out.get("fixes") or [] if isinstance(f, dict)}
    state = "bad" if differs else ("warn" if unchecked else "ok")
    v = verdicts(p, out.get("lines"))
    # what an update in place can mend: a definition or a figure that differs from the dry run (a model never refreshed
    # or a pipeline never run differs too, but its fix is the refresh or the run, below)
    found = [k for k, x in v["outputs"].items() if x["state"] == "differs"]
    kept = [k for k in found if k not in updatable(found)]
    for k in kept:                                              # differs, and /app's update does not write it: said
        names = ", ".join(v["outputs"][k]["differs"])
        lines.append(f"{names}: " + (NOT_UPDATED_REPORT if k == "report" else NOT_UPDATED_HERE))
    model_line = next((x for x in out.get("lines") or [] if isinstance(x, dict) and x.get("kind") == "semantic_model"), {})
    refresh = (model_line.get("state_check") or {}).get("state")
    return (_section("verify", state, lines[:VERIFY_LINES], title_note=CHECKED_BY,
                     facts={"items": n, "verified": ok, "differs": differs, "not_checked": unchecked, "model_refresh": refresh}),
            {"verify_differs": sum(len(v["outputs"][k]["differs"]) for k in found), "verdicts": v,
             "update": updatable(found), "needs_refresh": "refresh_model" in fixes, "needs_run": "run_pipeline" in fixes,
             "model": bool(model_line), "model_name": model_line.get("item") or ""})


DRIFT_WORDS = (("tables_added", "New table{s} in the source: {x}."), ("tables_removed", "Gone from the source: {x}."),
               ("columns_added", "New column{s}: {x}."), ("columns_removed", "Column{s} gone: {x}."),
               ("types_changed", "Type{s} changed: {x}."), ("keys_changed", "Key{s} changed: {x}."),
               ("relationships_added", "New link{s} the rules propose: {x}."), ("relationships_removed", "Link{s} the rules no longer find: {x}."))


def _drift_name(kind: str, x) -> str:
    if isinstance(x, str):
        return x
    if kind.startswith("columns"):
        return f"{x.get('table')}.{x.get('column')}"
    if kind == "types_changed":
        return f"{x.get('table')}.{x.get('column')} ({x.get('from')} → {x.get('to')})"
    if kind == "keys_changed":
        return f"{x.get('table')} ({'+'.join(x.get('from') or []) or 'none'} → {'+'.join(x.get('to') or []) or 'none'})"
    return f"{x.get('source')}.{'+'.join(x.get('columns') or [])} → {x.get('target')}"


def drift_section(p: dict, health_sig: dict | None = None) -> tuple[dict, dict]:
    """What changed in the source since the plan: review.build's since_previous (drift.snapshot_diff of the plan's
    snapshot and the source now). Reads names and types only; counts nothing. AP3b: read at the same time as the health
    check, so the links it found failing are added once both are read (links_into_drift); `health_sig` is for a caller
    that has it already."""
    from . import server
    c = p["c"]
    now = server._review_file(c["workspace"], c["source"], c["schema"], None, None, None, p["review"], False, None, 60, None)
    since = now.get("since_previous") or {}
    ch = since.get("changes") or {}
    lines = []
    for kind, words in DRIFT_WORDS:
        xs = ch.get(kind) or []
        if xs:
            names = [_drift_name(kind, x) for x in xs]
            shown = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")
            lines.append(words.replace("{s}", "" if len(xs) == 1 else "s").replace("{x}", shown))
    gone = since.get("decisions_no_longer_in_plan") or []
    if gone:
        lines.append(f"{_plural(len(gone), 'decision')} you made {'is' if len(gone) == 1 else 'are'} about something no longer in the plan.")
    changed = bool(ch.get("changed"))
    breaking = bool(ch.get("tables_removed") or ch.get("columns_removed"))
    links_changed = bool(ch.get("keys_changed") or ch.get("relationships_added") or ch.get("relationships_removed"))
    if not changed and not gone:
        lines.insert(0, "The source still matches the plan: the same tables, columns, types, keys and links.")
    plan_now = now.get("plan_id")
    state = "bad" if breaking else ("warn" if changed or gone else "ok")
    sec = _section("drift", state, lines[:8], facts={"changed": changed, "breaking": breaking, "plan_was": p["review"].get("plan_id"),
                                                     "plan_now": plan_now})
    if health_sig:
        links_into_drift(sec, health_sig)
    return sec, {"drift": changed, "drift_breaking": breaking, "links_changed": links_changed}


def links_into_drift(sec: dict, health_sig: dict) -> None:
    """The key and link checks the health check's latest run found failing, said in the source section too."""
    links_failing = int((health_sig or {}).get("links_failing") or 0)
    if not links_failing or sec.get("key") != "drift" or sec.get("state") == "unknown":
        return
    sec["lines"].append(f"{_plural(links_failing, 'key or link check')} no longer {'holds' if links_failing == 1 else 'hold'} "
                        "against the rows (from the health check's latest run).")
    if sec["state"] == "ok":
        sec["state"] = "warn"


def health_why(sec: dict, sig: dict) -> None:
    """AP3b: why a product has no health row, in plain words, from what the other parts read (the founder's live run of
    25 November 2026: a pipeline that succeeded on 9 November and "Nothing yet"). Health rows are matched to the
    product by its plan id, exactly (health.read_sql): the pipeline's check writes the plan it was built from. That
    match is right; what was missing is the reason. Krusgraph's check notebooks write health rows since 11 November
    2026 (n200); a pipeline built before has no health step."""
    if sec.get("key") != "health" or sig.get("health") != "none":
        return
    run = sig.get("last_run") or ""
    ps = sig.get("pipeline_state")
    earlier = bool((((sig.get("verdicts") or {}).get("outputs") or {}).get("pipeline") or {}).get("earlier"))
    if not sig.get("pipeline"):
        return
    if ps == "never":
        line = "The pipeline has not run yet, so it has written no health row: the check runs as the pipeline's last step."
    elif ps in ("ok", "failed") and earlier:
        line = (f"The last run ({run or 'date not given'}) was of a pipeline built by an earlier version of Krusgraph, before "
                "its check wrote health rows; Update the build in place adds the health step.")
    elif ps in ("ok", "failed") and sig.get("health_table") is False:
        line = (f"The last run ({run or 'date not given'}) wrote no health table ({sig.get('health_table_name') or 'krusgraph.health'}): "
                "its check notebook was built before the check wrote health rows (Krusgraph's checks write them since "
                "11 November 2026). Update the build in place adds the health step.")
    elif ps in ("ok", "failed"):
        line = (f"The health table has no row for this plan: the last run ({run or 'date not given'}) was of a pipeline built "
                "from another plan, or before the check wrote health rows. Update the build in place builds it from this plan.")
    else:
        return
    sec["lines"] = [line]


# ------------------------------------------------------------------ the rules that propose -------------------------

def can_run() -> tuple[bool, str]:
    """Run the pipeline from here only with the operator's opt-in switch on and the sign-in's permission (or unknown)."""
    from . import access, workload_api as W
    if not access.pipeline_execute_on():
        return False, ("Krusgraph starts pipeline runs only when the operator has turned on the opt-in permission "
                       f"{W.EXECUTE_SCOPE}; it is off here.")
    refused = W.run_permission(W.token_scopes(), "DataPipeline")
    return (False, refused["error"]) if refused else (True, "")


def propose(sig: dict, runnable: tuple[bool, str]) -> list[dict]:
    """At most MAX_ACTIONS actions, by fixed rules in this order; each says which source made it."""
    out: list[dict] = []
    pipe = sig.get("pipeline")
    ps = sig.get("pipeline_state")
    if pipe and (ps in ("failed", "never") or sig.get("needs_run")):
        why = ("The latest run failed (from the last pipeline run)." if ps == "failed" else
               "The pipeline has never run (from the last pipeline run)." if ps == "never" else
               "verify_build found no completed run (from verify_build).")
        if runnable[0]:
            out.append({"act": "run_pipeline", "why": why, "item": pipe["name"], "writes": True})
        else:
            out.append({"act": "run_manual", "why": why + " " + runnable[1], "item": pipe["name"], "writes": False})
    if sig.get("drift") or sig.get("update"):
        out.append({"act": "update_build", "why": update_why(sig) + " A dry run comes first; nothing is written until you confirm.",
                    "writes": True, "items": update_items(sig)})
    if sig.get("links_failing") or sig.get("links_changed"):
        why = (f"{_plural(int(sig['links_failing']), 'key or link check')} failed (from the health check's latest run)."
               if sig.get("links_failing") else "The rules find other keys or links than the plan (from the source now).")
        out.append({"act": "recheck_links", "why": why + " This only counts; it writes nothing.", "writes": False})
    if sig.get("needs_refresh") and ps not in ("failed", "never", "running"):
        out.append({"act": "refresh_model", "why": "The model has no completed refresh (from verify_build).", "writes": True})
    for a in out:
        a["label"] = LABEL[a["act"]]
    return out[:MAX_ACTIONS]


def update_items(sig: dict) -> list[str]:
    """The items "Update the build in place" would write: the ones verify_build found different (AP3b: the same rule
    the dry run then follows); with drift, every item the update rebuilds."""
    v = ((sig.get("verdicts") or {}).get("outputs")) or {}
    if sig.get("drift"):
        return [n for k in sig.get("rebuild") or [] for n in (v.get(k) or {}).get("items") or []] or list(sig.get("rebuild_names") or [])
    return [n for k in sig.get("update") or [] for n in (v.get(k) or {}).get("differs") or []]


def update_why(sig: dict) -> str:
    if sig.get("drift"):
        return "The source changed since the plan (from the source now, compared with the plan)."
    v = ((sig.get("verdicts") or {}).get("outputs")) or {}
    names = update_items(sig)
    said = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else (names[0] if names else "")
    why = f"{said} {'differs' if len(names) == 1 else 'differ'} from the dry run (from verify_build)"
    if any((v.get(k) or {}).get("earlier") for k in sig.get("update") or []):
        why += ", built by an earlier version of Krusgraph"
    pipe = (sig.get("pipeline") or {}).get("name")
    if "pipeline" in (sig.get("update") or []) and pipe and any(n != pipe for n in (v.get("pipeline") or {}).get("differs") or []):
        why += f"; the update writes them through {pipe}, whose Create writes its notebooks"
    return why + "."


SECTIONS = (("pipeline", pipeline_section), ("health", health_section), ("verify", verify_section), ("drift", drift_section))
PART = {"pipeline": "pipeline runs", "health": "the health check", "verify": "verify_build", "drift": "the source"}


def late(key: str) -> dict:
    """A section that was not read within the report's time budget."""
    return _section(key, "unknown", [f"Not read in time: the report's time budget of {CARE_SECONDS:g} s ran out before "
                                     f"{PART[key]} {'was' if key != 'pipeline' else 'were'} read. Read again reads this data "
                                     "product once more."], again=True)


def read_sections(tokens, p: dict, seconds: float | None = None) -> tuple[list[dict], dict]:
    """AP3b: the four sections read at the same time, each in its own thread with the person's own tokens, under one
    time budget for the report (budget.call: every read inside sees the same deadline). A section not done when the
    budget and GRACE have passed is "Not read in time"; its thread is left to finish on its own and its answer unused."""
    import contextvars
    from . import budget, server
    seconds = CARE_SECONDS if seconds is None else seconds
    results: dict = {}
    progress = p.setdefault("progress", {})
    progress.update(done=[], started=time.time(), parts=[k for k, _ in SECTIONS])
    threads = []
    with budget.call(seconds):
        for key, fn in SECTIONS:
            ctx = contextvars.copy_context()

            def work(key=key, fn=fn):
                with server.workload_tokens(tokens):
                    try:
                        got = fn(p)
                    except Exception as exc:                    # noqa: BLE001 — one source not read never hides the others
                        got = _not_read(key, exc)
                with _LOCK:
                    results[key] = got
                    progress["done"] = [k for k, _ in SECTIONS if k in results]
            th = threading.Thread(target=ctx.run, args=(work,), name=f"care-{key}", daemon=True)
            th.start()
            threads.append(th)
        end = time.monotonic() + seconds + GRACE
        for th in threads:
            th.join(max(0.0, end - time.monotonic()))
    sections, sig = [], {}
    with _LOCK:
        got = dict(results)
    for key, _ in SECTIONS:
        sec, s = got.get(key) or (late(key), {})
        sections.append(sec)
        sig.update(s)
    by = {s["key"]: s for s in sections}
    links_into_drift(by["drift"], sig)
    health_why(by["health"], sig)
    return sections, sig


def report(tokens, sid: str, pid) -> dict:
    """The "Since last time" report of one data product: the four sources, then the proposals. Reads only."""
    from . import server
    p = product(sid, pid)
    if p is None:
        return {"error": "That data product is not one found for this sign-in. Open /app again.", "kind": "not_found"}
    sections, sig = read_sections(tokens, p)
    rebuild = updatable({c.get("output") for c in p["created"]})
    sig["rebuild"] = rebuild
    sig["rebuild_names"] = [p["names"][k] for k in rebuild if p["names"].get(k)]
    p["verdicts"] = sig.get("verdicts") or {}
    p["update"] = rebuild if sig.get("drift") else list(sig.get("update") or [])
    with server.workload_tokens(tokens):
        runnable = can_run() if sig.get("pipeline") else (False, "")
    actions = propose(sig, runnable)
    for a in actions:
        if a["act"] == "update_build":
            a["build"] = update_args(p)
        if a["act"] == "run_manual":
            from . import pipeline_jobs
            a["steps"] = list(pipeline_jobs.MANUAL)[:3]
            a["link"] = pipeline_jobs.run_link(sig["pipeline"]["workspace"], sig["pipeline"]["id"], sig["pipeline"]["name"], None)["pipeline"]
    p["actions"] = {a["act"] for a in actions}
    bad = [s["title"] for s in sections if s["state"] == "bad"]
    say = (f"{p['name']}: " + ("all is well. Nothing needs you." if not bad and not actions else
                               (f"{len(bad)} of {len(sections)} parts need a look." if bad else "a few things to look at.")))
    log("care_report", sections=len(sections), bad=len(bad), actions=len(actions))
    return {"product": summary_of(p), "say": say, "sections": sections, "actions": actions, "note": NOTHING_DONE,
            "title": CHECKED_BY, "budget": CARE_SECONDS}


def progress(sid: str, pid) -> dict:
    """AP3b: which parts of a report being read are done, for the page's busy line. Reads nothing in Fabric."""
    p = product(sid, pid)
    if p is None:
        return {"error": "That data product is not one found for this sign-in.", "kind": "not_found"}
    pr = p.get("progress") or {}
    return {"parts": [{"key": k, "part": PART[k], "done": k in (pr.get("done") or [])} for k, _ in SECTIONS]}


def update_args(p: dict) -> dict:
    """The AP2 dry run that "Update the build in place" opens: the same inputs, every built item that can be updated."""
    from . import workload_api as W
    from .guided_build import OUTPUTS
    update = list(p.get("update") if p.get("update") is not None else
                  [k for k, _ in OUTPUTS if k in {c.get("output") for c in p["created"]} and W.KINDS[k]["updates"]])
    t = p.get("target")
    return {"workspace": p["c"]["workspace"], "source": p["c"]["source"], "schema": p["c"]["schema"], "update": update,
            "product": p["id"], **({"target": {"workspace": t["workspace_id"], **({"lakehouse": t["lakehouse"]} if t.get("lakehouse") else {})}}
                                   if t else {})}


# ------------------------------------------------------------------ Re-check the links (reads only) -----------------

def recheck(tokens, sid: str, pid) -> dict:
    """The plan's keys and links counted against the rows again, compared with what the plan recorded. Reads only."""
    from . import server
    p = product(sid, pid)
    if p is None:
        return {"error": "That data product is not one found for this sign-in. Open /app again.", "kind": "not_found"}
    c = p["c"]
    with server.workload_tokens(tokens):
        now = server._review_file(c["workspace"], c["source"], c["schema"], None, None, None, p["review"], True, None, 60, None)
    was = {it.get("id"): ((it.get("check") or {}).get("status") or "") for it in p["review"].get("items") or [] if isinstance(it, dict)}
    rows, holds, counted, broke = [], 0, 0, []
    for it in now.get("items") or []:
        if not isinstance(it, dict) or it.get("review") == "rejected":
            continue
        st = str((it.get("check") or {}).get("status") or "")
        if st not in ("passed", "failed"):
            continue
        counted += 1
        holds += st == "passed"
        what = (f"{it.get('table')} key {'+'.join(it.get('columns') or [])}" if it.get("type") == "key" else
                f"{it.get('source')}.{'+'.join(it.get('columns') or [])} → {it.get('target')}")
        res = (it.get("check") or {}).get("result") or {}
        if st == "failed":
            n = res.get("orphans") if it.get("type") != "key" else res.get("duplicates") or res.get("nulls")
            then = (" It held when the plan was made." if was.get(it.get("id")) == "passed" else
                    " You accepted it so (the rows that do not join go to quarantine)." if it.get("review") == "accepted" else
                    " It did not hold when the plan was made either.")
            line = f"{what}: does not hold" + (f" ({_plural(n, 'row')})" if isinstance(n, int) and n else "") + "." + then
            rows.append(line)
            if was.get(it.get("id")) == "passed":
                broke.append(what)
    lines = [f"{holds} of {_plural(counted, 'key and link check')} hold now ({SOURCE['recheck']})."] + rows[:8]
    log("care_recheck", counted=counted, holds=holds, broke=len(broke))
    return {"stage": "recheck", "who": "thinker", "title": CHECKED_BY, "lines": lines, "broke": broke[:20],
            "counts": {"checked": counted, "hold": holds, "no_longer": len(broke)}, "note": NOTHING_DONE}


# ------------------------------------------------------------------ the writing actions: preview, confirm, run ------

def refresh_offer(sid: str) -> dict | None:
    """AP3b: AP2's verify card proposes "Refresh the model once" for what this session created: that build is made a
    data product of this session (session_product) whose one allowed action is refresh_model, so the button goes through
    the same preview, confirm dialog naming the model and single-use token as the report's refresh. Only Power BI's
    refresh is called (workload_api.run_refresh_only); the model's definition is not written. None: no model built."""
    from . import guided_build
    p = session_product(guided_build.BUILDS.get(sid) or {})
    if p is None or _target_item(p, "refresh_model") is None:
        return None
    st = _state(sid)
    with _LOCK:
        old = next((k for k, v in st["products"].items() if v.get("origin") == "session" and v.get("refresh_only")), None)
        pid = old or "p-" + secrets.token_urlsafe(9)
        p.update(id=pid, where="", refresh_only=True, actions={"refresh_model"})
        st["products"][pid] = p
    return {"product": pid, "act": "refresh_model", "label": LABEL["refresh_model"], "item": _target_item(p, "refresh_model")["name"]}


def _target_item(p: dict, act: str) -> dict | None:
    return _latest(p, "SemanticModel", "semantic_model") if act == "refresh_model" else _latest(p, "DataPipeline", "pipeline")


def _token(p: dict, act: str, item: dict, listed: dict) -> str:
    raw = json.dumps([p["id"], act, item["id"], item.get("workspace"), listed.get("displayName"), listed.get("type")], sort_keys=True)
    return "care-" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _look(tokens, p: dict, act: str) -> tuple[dict | None, dict | None, str]:
    """The item an action writes, as Fabric lists it now (List Items): (item, listed, why not)."""
    from . import server
    item = _target_item(p, act)
    if item is None:
        return None, None, ("This data product has no semantic model." if act == "refresh_model" else "This data product has no pipeline.")
    ws = item.get("workspace") or (p.get("target") or {}).get("workspace_id") or p["c"]["workspace"]
    with server.workload_tokens(tokens):
        items = server._workspace_items(ws, server._headers(None))
    listed = next((i for i in items if str(i.get("id") or "").lower() == item["id"].lower()), None)
    if listed is None:
        return item, None, f"{item['name']} is not in its workspace any more, so nothing can be done to it."
    if (listed.get("displayName") or "") != item.get("name"):
        return item, listed, f"{item['name']} was renamed in Fabric to {listed.get('displayName')}; Krusgraph leaves it as it is."
    return {**item, "workspace": ws}, listed, ""


def preview(tokens, sid: str, pid, act: str) -> dict:
    """What a writing action would do, and its token. Writes nothing."""
    p = product(sid, pid)
    if p is None or act not in WRITES:
        return {"error": "That action is not offered here.", "kind": "bad_request"}
    if act not in p.get("actions", set()):
        return {"error": "That action is not among the ones proposed for this data product now.", "kind": "bad_request",
                "hint": "Read the report again: the proposals come from what it found."}
    if act == "run_pipeline":
        from . import server
        with server.workload_tokens(tokens):
            ok, why = can_run()
        if not ok:
            return {"error": why, "kind": "needs_permission", "hint": "Open the pipeline in Fabric and choose Run there."}
    item, listed, why = _look(tokens, p, act)
    if why:
        return {"error": why, "kind": "not_found", "hint": "Nothing was changed."}
    token = _token(p, act, item, listed)
    _state(sid)["previews"] = {k: v for k, v in _state(sid)["previews"].items() if time.time() - v["at"] <= CARE_TTL}
    _state(sid)["previews"][token] = {"at": time.time(), "pid": p["id"], "act": act, "name": item["name"]}
    words = (f"Refreshes the semantic model {item['name']} once (Direct Lake framing), as you. Nothing else is run or scheduled."
             if act == "refresh_model" else
             f"Starts one run of the pipeline {item['name']} in Fabric, as you: silver, then gold, then the check. No schedule is added.")
    log("care_preview", act=act)
    return {"stage": "care_preview", "who": "builder", "token": token, "act": act, "label": LABEL[act], "item": item["name"],
            "say": words, "note": "This is the preview: nothing is done until you confirm."}


def confirm(tokens, sid: str, token, names, owner: str) -> dict:
    """The confirm dialog's yes: the preview's token, fresh and unused, and exactly its item's name; the preview is made
    again and must give the same token. Then the action, once."""
    from . import operations, server, workload_api as W
    st = _state(sid)
    pv = st["previews"].pop(token, None) if isinstance(token, str) else None
    if not pv or time.time() - pv["at"] > CARE_TTL:
        return {"error": STALE, "kind": "stale", "hint": "Make the preview again: a confirmation works once, for 15 minutes."}
    if not isinstance(names, list) or [str(n) for n in names] != [pv["name"]]:
        return {"error": "The name you confirmed is not the one the preview showed; nothing was done.", "kind": "bad_request",
                "hint": "Confirm the name the preview shows."}
    p = product(sid, pv["pid"])
    if p is None:
        return {"error": STALE, "kind": "stale", "hint": "Open /app again."}
    item, listed, why = _look(tokens, p, pv["act"])
    if why or _token(p, pv["act"], item, listed) != token:
        log("care_refused", reason="stale")
        return {"error": STALE, "kind": "stale", "hint": why or "The item changed in Fabric. Make the preview again."}
    if pv["act"] == "run_pipeline":
        with server.workload_tokens(tokens):
            ok, why = can_run()
            if not ok:
                return {"error": why, "kind": "needs_permission", "hint": "Open the pipeline in Fabric and choose Run there."}
            run = W.run_item(W.run_item_request({"workspace": item["workspace"], "item_id": item["id"], "item_type": "DataPipeline",
                                                 "name": item["name"]}))
        from . import pipeline_jobs
        log("care_run", outcome=run.get("state"))
        return {"stage": "care_done", "act": "run_pipeline", "item": item["name"], "state": run.get("state"),
                "words": run.get("words") or "", "only_when": W.RUN_ONLY_WHEN,
                "link": pipeline_jobs.run_link(item["workspace"], item["id"], item["name"], run.get("run_id")).get("run")
                or pipeline_jobs.run_link(item["workspace"], item["id"], item["name"], None)["pipeline"]}
    c = p["c"]
    with server.workload_tokens(tokens):
        req = W.build_request({"workspace": c["workspace"], "source": c["source"], "source_name": c["source"], "schema": c["schema"],
                               "review": p["review"], "outputs": [{"kind": "semantic_model", "name": item["name"]}],
                               "dry_run": False, "only": ["semantic_model"], "refresh_only": True, "created": p["created"]})

    def work():
        with server.workload_tokens(tokens):
            try:
                out = W.run_build_background(req)
            except Exception as exc:                            # noqa: BLE001 — explained, never leaked
                from .errors import explain
                out = explain(exc, "refreshing the model")
        return out, 200
    op = operations.start("app-care", owner, work, tokens=tokens, output="semantic_model", create=pv["pid"])
    log("care_refresh")
    return {"stage": "care_started", "act": "refresh_model", "item": item["name"], "operation_id": op["id"]}


REFRESH_WORDS = {"refreshed": "Refreshed once: the model's tables show the data now.",
                 "not_run": "Not refreshed: {reason}", "failed": "The refresh failed: {reason}",
                 "refreshing": "Started; Power BI was still refreshing it when Krusgraph stopped waiting. Read the report again later."}


def op_state(tokens, op_id, owner: str) -> dict:
    """How a refresh is going; its words once done."""
    from . import operations
    got = operations.state(op_id, owner, tokens) if isinstance(op_id, str) and len(op_id) <= 64 else None
    if got is None:
        return {"error": "No such step for this sign-in.", "kind": "not_found"}
    out = {"status": got.get("status")}
    if got.get("status") == "lost":
        out["words"] = str(got.get("lost") or "The engine stopped working on this step.")
    if got.get("status") == "done":
        ans = got.get("answer") or {}
        if ans.get("error") and not ans.get("outputs"):
            out["words"] = _cut(" ".join(str(ans[k]) for k in ("error", "hint") if ans.get(k)), 600)
        else:
            ref = ((ans.get("outputs") or [{}])[0].get("refresh")) or {}
            st = str(ref.get("status") or "")
            reason = _cut(ref.get("reason") or ref.get("why") or ref.get("words") or st or "no answer", 300)
            out["refresh"] = st
            out["words"] = REFRESH_WORDS.get(st, "The refresh: {reason}").format(reason=reason)
    return out
