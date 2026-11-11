"""The data product page's engine (round n198): see, retire and clean up what a Krusgraph Model built.

docs/LIFECYCLE-DESIGN.md section 6 (the Lifecycle view) and docs/FABRIC-IQ-AT-SCALE.md section 8 are the design; this
is its first slice. The founder asked on 10 November 2026 how to remove items, update ontologies and data products and
look after the workspace after Create. A live test left demo_lh_model4 (made by Fabric after a timeout, never adopted)
and items of earlier Creates listed in a later data product.

Four actions, each as the signed-in user (POST /workload/v1/product, workload_api.run_product):

  status     every item in this Model's outputs.json, as Fabric lists it now: built, missing (not in the workspace any
             more), changed outside (renamed in Fabric, another type, or its description names another plan), pending
             (sent, not confirmed). Only reads (List Items).
  retire     scope "soft": remove the schedules Krusgraph made on the pipeline (the ids outputs.json and the pipeline's
             description recorded; any other schedule stays), and say how to take a published data agent out of use
             (no documented API, below). scope "delete": Delete Item for each chosen item. Both are a dry run first,
             which lists exactly what goes and gives a confirmation; the real call needs that confirmation back and, for
             delete, the data product's name typed by the person. Only items in this Model's outputs.json, and only the
             item types Krusgraph makes (DELETABLE): never a lakehouse, a warehouse, a table, a view's data or anything
             outside outputs.json. With `leftovers` the items are leftovers (below) instead, under the same rules.
  leftovers  the workspace's items whose description carries Krusgraph's plan marker (workload_api.MARK) and that no
             Krusgraph Model's outputs.json lists (this one, or another Model in the workspace, read with Get Item
             Definition). If another Model cannot be read, nothing is offered for deletion: its items cannot be told
             apart from leftovers.
  adopt      a leftover whose marker names this data product's plan, added to outputs.json (the editor saves it).

Each removal and adoption comes back with when and by whom (the sign-in's name), which the editor writes into
outputs.json (removed[] and created[].adopted_at).

What it rests on (read 11 November 2026):
- Microsoft Learn, Fabric REST API, Core / Items, Delete Item (learn.microsoft.com/rest/api/fabric/core/items/delete-item;
  microsoft/fabric-rest-api-specs main, platform/swagger.json, Items_DeleteItem): DELETE
  /v1/workspaces/{ws}/items/{id}[?hardDelete]; "The default behavior is to soft delete the item for supported item
  types"; write permission on the item for a soft delete; delegated scope Item.ReadWrite.All or <itemType>.ReadWrite.All.
  Krusgraph never sends hardDelete.
- dataPipeline/swagger.json, BackgroundJobs_DeleteExecuteSchedule: DELETE
  /v1/workspaces/{ws}/dataPipelines/{id}/jobs/execute/schedules/{scheduleId}; DataPipeline.ReadWrite.All or
  Item.ReadWrite.All; write permission on the pipeline.
- Learn, Core / Workspaces, List Workspace Role Assignments (platform/swagger.json, Workspaces_ListWorkspaceRoleAssignments):
  GET /v1/workspaces/{ws}/roleAssignments; Workspace.Read.All or Workspace.ReadWrite.All (the workload app has
  Workspace.Read.All). The owner is picked from the people and groups with a role in the workspace; only their display
  name and user principal name are shown, nothing is stored but the one chosen.
- dataAgent/swagger.json: Items_PublishDataAgent (staging/publish) and Staging_Reset exist; no operation unpublishes a
  data agent. Taking a published agent out of use is a portal step here (Unverified: the portal's exact words), or the
  agent is deleted with Delete from Fabric.
- Learn, Get Item Definition (core/items/get-item-definition) and the Extensibility Toolkit's key concepts (ms.date
  2025-12-15: an item's definition is stored "using the same format applied by public APIs"): a Krusgraph Model's
  outputs.json is read with POST /v1/workspaces/{ws}/items/{id}/getDefinition. Unverified against a live workspace.
Not verified against Fabric: none of these calls has run against a live workspace yet; unit-tested with a fake Fabric.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone

FABRIC = "https://api.fabric.microsoft.com"
# The item types Krusgraph makes (workload_api.KINDS); nothing else is ever deleted.
DELETABLE = ("Notebook", "DataPipeline", "SemanticModel", "Report", "GraphQLApi", "Ontology", "DataAgent", "AppBackend")
# Never deleted, whatever a list says: where the data lives.
NEVER = ("Lakehouse", "Warehouse", "SQLEndpoint", "SQLDatabase", "MirroredDatabase", "MirroredWarehouse", "MirroredAzureDatabricksCatalog",
         "KQLDatabase", "Eventhouse", "Datamart", "SnowflakeDatabase", "CosmosDBDatabase")
# Dependents first: a report before its model, the agent and the API before what they read, the pipeline before its notebooks.
DELETE_ORDER = ("Report", "AppBackend", "DataAgent", "GraphQLApi", "Ontology", "SemanticModel", "DataPipeline", "Notebook")
MODEL_TYPES = re.compile(r"^(Org\.Krusgraph|Krusgraph\.Modeler)\.Model$")
SCHEDULE_MARK = re.compile(r"\[Krusgraph schedule ([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]")
# n210: a schedule id goes into a DELETE path, so only a GUID is ever used; anything else could walk the path elsewhere.
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DELETE_DOC = "https://learn.microsoft.com/rest/api/fabric/core/items/delete-item"
KEEP_DATA = ("Krusgraph never deletes a lakehouse, a warehouse, a table or a view's data. The views and tables the "
             "notebooks wrote stay in the lakehouse; drop them in the lakehouse yourself if you no longer want them.")
AGENT_STEP = ("Microsoft documents no API to unpublish a data agent, so Krusgraph does not try. In Fabric, open the agent "
              "and stop sharing it, or delete it with Delete from Fabric below.")
STATES = ("built", "pending", "failed", "changed_outside", "missing", "removed")
WORDS = {
    "built": "Built",
    "pending": "Pending: sent to Fabric, not confirmed yet",
    "failed": "Failed in the last Create",
    "changed_outside": "Changed outside Krusgraph",
    "missing": "Missing: not in the workspace",
    "removed": "Removed",
}


class Refused(ValueError):
    """A retire or adopt that cannot go ahead; the message says why in plain words."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ reading the workspace -----------------------------

def list_items(http, workspace: str) -> dict[str, dict]:
    """{id: item} of the workspace (List Items, every page)."""
    out, url, pages = {}, f"{FABRIC}/v1/workspaces/{workspace}/items", 0
    while url and pages < 50:
        r = http("get", url)
        if getattr(r, "status_code", 200) >= 400:
            r.raise_for_status()
        body = r.json() or {}
        for it in body.get("value", []):
            if it.get("id"):
                out[it["id"]] = it
        url, pages = body.get("continuationUri"), pages + 1
    return out


def _mark(text) -> dict | None:
    from .workload_api import mark_of_description
    return mark_of_description(text)


def active(outputs: dict) -> list[dict]:
    """outputs.json's created items that have not been removed."""
    gone = {r.get("id") for r in outputs.get("removed") or [] if isinstance(r, dict)}
    return [c for c in outputs.get("created") or [] if isinstance(c, dict) and c.get("id") and c["id"] not in gone]


def status(outputs: dict, listings: dict[str, dict[str, dict]]) -> list[dict]:
    """One row per item of outputs.json: its state as Fabric lists it now (listings: {workspace: {id: item}})."""
    rows = []
    for c in active(outputs):
        listed = (listings.get(c.get("workspace") or "") or {})
        it = listed.get(c["id"])
        row = {k: c.get(k) for k in ("id", "type", "name", "workspace", "output")}
        if it is None:
            row.update(state="missing", why="Fabric does not list it in the workspace any more (deleted, or moved outside Krusgraph).")
        else:
            why = []
            if (it.get("displayName") or "") != (c.get("name") or ""):
                why.append(f"renamed in Fabric to {it.get('displayName')}")
            if it.get("type") and c.get("type") and it["type"] != c["type"]:
                why.append(f"Fabric lists it as {it['type']}")
            m = _mark(it.get("description"))
            rec = c.get("plan") if isinstance(c.get("plan"), dict) else None
            if m and rec and rec.get("plan_id") and m["plan_id"] != rec["plan_id"]:
                why.append(f"its description names another plan ({m['plan_id']})")
            if why:
                text = "; ".join(why)
                row.update(state="changed_outside", why=text[0].upper() + text[1:] + ".", fabric_name=it.get("displayName"))
            else:
                row.update(state="built", why="")
        row["words"] = WORDS[row["state"]]
        rows.append(row)
    made = {(c.get("type"), (c.get("name") or "").lower()) for c in active(outputs)}
    for p in outputs.get("pending") or []:
        if not isinstance(p, dict) or (p.get("type"), (p.get("name") or "").lower()) in made:
            continue
        rows.append({"id": None, "type": p.get("type"), "name": p.get("name"), "workspace": None, "output": p.get("output"),
                     "state": "pending", "words": WORDS["pending"],
                     "why": "A Create sent it and has not seen it finish. Reopening the item or Try again adopts it when Fabric has made it."})
    return rows


def people(http, workspace: str) -> list[dict] | None:
    """The people and groups with a role in the workspace, to pick the owner from; None when Fabric does not answer."""
    out, url, pages = [], f"{FABRIC}/v1/workspaces/{workspace}/roleAssignments", 0
    while url and pages < 10:
        try:
            r = http("get", url)
        except Exception:  # noqa: BLE001 — the owner can still be typed
            return None
        if getattr(r, "status_code", 200) >= 400:
            return None
        body = r.json() or {}
        for a in body.get("value", []):
            p = a.get("principal") or {}
            if p.get("type") not in ("User", "Group") or not p.get("displayName"):
                continue
            upn = (p.get("userDetails") or {}).get("userPrincipalName")
            out.append({"name": p["displayName"], "type": p["type"], "role": a.get("role"), **({"upn": upn} if upn else {})})
        url, pages = body.get("continuationUri"), pages + 1
    out.sort(key=lambda x: (x["type"] != "User", x["name"].lower()))
    return out


# ------------------------------------------------------------------ the other Krusgraph Models --------------------------

def outputs_of_definition(parts: list[dict]) -> dict | None:
    """outputs.json of a Krusgraph Model's definition parts (base64 payloads), or None."""
    for p in parts or []:
        if p.get("path") == "outputs.json":
            try:
                return json.loads(base64.b64decode(p.get("payload") or "").decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None
    return None


def leftovers(http, workspace: str, outputs: dict, item_id: str | None, plan_id: str | None, read_definition) -> dict:
    """Items carrying Krusgraph's plan marker that no Krusgraph Model's outputs.json lists. read_definition(ws, id) gives
    an item's definition parts (raises when it cannot be read)."""
    listed = list_items(http, workspace)
    claimed = {c.get("id") for c in outputs.get("created") or [] if isinstance(c, dict)}
    unread = []
    for it in listed.values():
        if not MODEL_TYPES.match(str(it.get("type") or "")) or (item_id and it["id"].lower() == item_id.lower()):
            continue
        try:
            other = outputs_of_definition(read_definition(workspace, it["id"]))
        except Exception:  # noqa: BLE001 — a Model that cannot be read blocks deletion, it does not stop the list
            other = None
            unread.append(it.get("displayName") or it["id"])
            continue
        claimed |= {c.get("id") for c in (other or {}).get("created") or [] if isinstance(c, dict)}
    found = []
    for it in listed.values():
        m = _mark(it.get("description"))
        if not m or it["id"] in claimed or MODEL_TYPES.match(str(it.get("type") or "")):
            continue
        typ = it.get("type") or ""
        same = bool(plan_id and m["plan_id"] == plan_id)
        delete_ok, why = True, ""
        if typ in NEVER or typ not in DELETABLE:
            delete_ok, why = False, f"Krusgraph never deletes a {typ or 'item of this type'}."
        elif unread:
            delete_ok, why = False, (f"Another Krusgraph Model ({', '.join(unread)}) could not be read, so this item may be one of "
                                     "its outputs. Open that Model's Data product page first.")
        found.append({"id": it["id"], "type": typ, "name": it.get("displayName"), "workspace": workspace, "plan": m,
                      "plan_id": m["plan_id"], "same_plan": same, "adopt_ok": same and typ in DELETABLE,
                      "adopt_why": "" if same else "Built from another plan than this data product's; Adopt is offered only for the same plan.",
                      "delete_ok": delete_ok, "why": why})
    found.sort(key=lambda x: (x["type"], (x["name"] or "").lower()))
    return {"leftovers": found, "unread_models": unread, "workspace": workspace}


# ------------------------------------------------------------------ retire ---------------------------------------------

def confirm_token(scope: str, ids: list[str], product: str) -> str:
    raw = json.dumps([scope, sorted(ids), product])
    return "ret-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _schedules_of(outputs: dict, pipeline: dict, listed: dict) -> list[dict]:
    """The schedules Krusgraph made on this pipeline: outputs.json's pipeline_jobs and the pipeline's description."""
    recs = [s for s in ((outputs.get("pipeline_jobs") or {}).get("schedules") or [])
            if isinstance(s, dict) and s.get("pipeline_id") == pipeline["id"] and isinstance(s.get("id"), str) and GUID.match(s["id"])]
    ids = {s["id"] for s in recs}
    desc = (listed.get(pipeline["id"]) or {}).get("description")
    recs += [{"id": sid, "pipeline_id": pipeline["id"], "every": "", "from": "description"}
             for sid in SCHEDULE_MARK.findall(str(desc or "")) if sid not in ids]
    return recs


def _targets(outputs: dict, ids: list[str] | None, listings: dict[str, dict], lefts: dict | None) -> tuple[list[dict], list[dict]]:
    """(the items that may go, the ones refused with why). ids None: the whole data product."""
    go, refused = [], []
    if lefts is not None:
        pool = {x["id"]: x for x in lefts["leftovers"]}
        for i in ids or []:
            x = pool.get(i)
            if not x:
                refused.append({"id": i, "why": "Not a leftover: it is in a Krusgraph Model's outputs.json, carries no Krusgraph plan "
                                                 "marker, or is not in this workspace. Nothing outside the list is deleted."})
            elif not x["delete_ok"]:
                refused.append({**x, "why": x["why"]})
            else:
                go.append({k: x[k] for k in ("id", "type", "name", "workspace")} | {"output": None})
        return go, refused
    mine = {c["id"]: c for c in active(outputs)}
    for i in (list(mine) if ids is None else ids):
        c = mine.get(i)
        if not c:
            refused.append({"id": i, "why": "Not in this data product's outputs.json; Krusgraph deletes only what this Model built."})
            continue
        typ = c.get("type") or ""
        it = (listings.get(c.get("workspace") or "") or {}).get(i)
        if typ in NEVER or typ not in DELETABLE or (it and it.get("type") in NEVER):
            refused.append({**c, "why": f"Krusgraph never deletes a {typ or 'item of this type'}."})
        elif it is None:
            refused.append({**c, "why": "Already gone: Fabric does not list it in the workspace.", "gone": True})
        elif it.get("type") != typ:
            refused.append({**c, "why": f"Fabric lists it as {it.get('type')}, not the {typ} Krusgraph made; it is left alone."})
        else:
            go.append({k: c.get(k) for k in ("id", "type", "name", "workspace", "output")})
    go.sort(key=lambda x: (DELETE_ORDER.index(x["type"]) if x["type"] in DELETE_ORDER else 99, (x["name"] or "").lower()))
    return go, refused


def retire(http, req: dict, listings: dict[str, dict], lefts: dict | None = None) -> dict:
    """The dry run (dry_run true) or the retire itself. req: scope (soft|delete), items (ids or None), dry_run, confirm,
    typed_name, product (the data product's name), outputs, by."""
    outputs, scope, product = req["outputs"], req["scope"], req["product"]
    if scope == "soft" and lefts is not None:
        raise Refused("A leftover has no schedule Krusgraph recorded; offer Adopt or Delete for it.")
    go, refused = _targets(outputs, req.get("items"), listings, lefts)
    steps = []
    if scope == "soft":
        for x in go:
            listed = listings.get(x["workspace"] or "") or {}
            if x["type"] == "DataPipeline":
                for s in _schedules_of(outputs, x, listed):
                    steps.append({"id": x["id"], "name": x["name"], "type": x["type"], "workspace": x["workspace"], "action": "remove_schedule",
                                  "schedule_id": s["id"], "words": f"Remove the schedule Krusgraph made on {x['name']}"
                                  + (f" ({s.get('every')}{' at ' + s['at'] if s.get('at') else ''})" if s.get("every") else "")
                                  + "; any other schedule on it stays."})
            if x["type"] == "DataAgent":
                c = next((c for c in active(outputs) if c["id"] == x["id"]), {})
                if c.get("published"):
                    steps.append({"id": x["id"], "name": x["name"], "type": x["type"], "workspace": x["workspace"], "action": "manual",
                                  "words": f"{x['name']} is published. {AGENT_STEP}"})
        token = confirm_token("soft", [s.get("schedule_id") or s["id"] for s in steps], product)
    else:
        token = confirm_token("delete" + (":leftovers" if lefts is not None else ""), [x["id"] for x in go], product)
    head = {"scope": scope, "leftovers": lefts is not None, "product": product, "refused": refused, "keeps": KEEP_DATA,
            "doc": DELETE_DOC}
    if req.get("dry_run", True):
        if scope == "soft":
            words = (f"{sum(1 for s in steps if s['action'] == 'remove_schedule')} schedule(s) would be removed. Nothing is deleted."
                     if steps else "Krusgraph made no schedule here and published no agent: there is nothing to turn off.")
            return {**head, "dry_run": True, "steps": steps, "confirm": token if steps else None, "words": words}
        return {**head, "dry_run": True, "items": go, "confirm": token if go else None,
                "words": (f"{len(go)} item(s) would be deleted from Fabric. Type the data product's name, {product}, to confirm."
                          if go else "Nothing here can be deleted.")}
    if not (steps if scope == "soft" else go):
        raise Refused("Nothing in this list can be " + ("turned off" if scope == "soft" else "deleted") + "; nothing was changed. "
                      + "; ".join(f"{x.get('name') or x['id']}: {x['why']}" for x in refused[:5]))
    if not req.get("confirm") or req["confirm"] != token:
        raise Refused("The list is not the one the dry run showed (or no dry run was confirmed). Nothing was deleted or "
                      "changed; run the dry run again.")
    by, at = req.get("by") or "", now()
    if scope == "soft":
        done = []
        for s in steps:
            if s["action"] != "remove_schedule":
                done.append({**s, "result": "manual"})
                continue
            r = http("delete", f"{FABRIC}/v1/workspaces/{s['workspace']}/dataPipelines/{s['id']}/jobs/execute/schedules/{s['schedule_id']}")
            code = getattr(r, "status_code", 0)
            done.append({**s, "result": "done" if code < 400 or code == 404 else "failed", "http": code,
                         **({"why": _fabric_words(r)} if code >= 400 and code != 404 else {}),
                         **({"note": "Fabric no longer had it."} if code == 404 else {})})
        return {**head, "dry_run": False, "steps": done, "at": at, "by": by,
                "words": f"{sum(1 for d in done if d['result'] == 'done')} schedule(s) removed; nothing was deleted."}
    if (req.get("typed_name") or "").strip() != product:
        raise Refused(f"Type the data product's name exactly ({product}) to delete. Nothing was deleted.")
    results = []
    for x in go:
        r = http("delete", f"{FABRIC}/v1/workspaces/{x['workspace']}/items/{x['id']}")
        code = getattr(r, "status_code", 0)
        if code < 400:
            results.append({**x, "result": "deleted", "http": code, "removed_at": at, "by": by})
        elif code == 404:
            results.append({**x, "result": "already_gone", "http": code, "removed_at": at, "by": by})
        else:
            results.append({**x, "result": "failed", "http": code, "why": _fabric_words(r)})
    ok = sum(1 for x in results if x["result"] != "failed")
    return {**head, "dry_run": False, "results": results, "at": at, "by": by,
            "removed": [{k: x.get(k) for k in ("id", "type", "name", "workspace", "output", "removed_at", "by")}
                        for x in results if x["result"] != "failed"],
            "words": f"{ok} of {len(results)} item(s) deleted from Fabric." + (" The rest say why." if ok < len(results) else "")}


def _fabric_words(r) -> str:
    try:
        body = r.json() or {}
    except ValueError:
        body = {}
    msg = body.get("message") or (body.get("error") or {}).get("message") if isinstance(body, dict) else None
    code = getattr(r, "status_code", 0)
    if code in (401, 403):
        return (f"Fabric refused (HTTP {code}): deleting needs write permission on the item and the delegated permission "
                f"Item.ReadWrite.All (or the item type's). {msg or ''}").strip()
    return f"Fabric answered HTTP {code}" + (f": {msg}" if msg else "") + "."


# ------------------------------------------------------------------ adopt ----------------------------------------------

def output_of(typ: str, name: str) -> str | None:
    """Which output made an item of this type and name (adopted items carry no record of it)."""
    n = (name or "").lower()
    by_type = {"DataPipeline": "pipeline", "SemanticModel": "semantic_model", "Report": "report", "GraphQLApi": "graphql",
               "Ontology": "ontology", "DataAgent": "data_agent", "AppBackend": "rayfin_app"}
    if typ in by_type:
        return by_type[typ]
    if typ == "Notebook":
        return "pipeline" if n.endswith("_check") else "silver_notebook" if "silver" in n else "gold_views" if "gold" in n else None
    return None


def adopt(lefts: dict, ids: list[str], by: str) -> dict:
    pool = {x["id"]: x for x in lefts["leftovers"]}
    added, refused, at = [], [], now()
    for i in ids:
        x = pool.get(i)
        if not x:
            refused.append({"id": i, "why": "Not a leftover of this workspace (no Krusgraph plan marker, or a Model lists it)."})
        elif not x["adopt_ok"]:
            refused.append({**x, "why": x["adopt_why"] or "This type is not one Krusgraph makes."})
        else:
            added.append({"type": x["type"], "id": x["id"], "name": x["name"], "workspace": x["workspace"],
                          "output": output_of(x["type"], x["name"]), "plan": x["plan"], "adopted_at": at, "adopted_by": by})
    return {"adopted": added, "refused": refused, "at": at, "by": by,
            "words": f"{len(added)} item(s) added to this data product." if added else "Nothing was adopted."}
