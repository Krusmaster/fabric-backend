"""AP2: the writing half of the guided chat at /app (guided_app.py): decide, dry run, create and verify.

The founder's decision stands (24 November 2026): no AI model in the product; guided choices; rules decide, rows prove,
the person approves. Nothing here has rules of its own. Every step is an engine the product already has, called with
the signed-in person's own on-behalf-of tokens (guided_app.SessionTokens, through server.workload_tokens):

- Decide: the `start` tool's decide step (server.start). The page shows each open decision from the check as a card (the
  options, the counts behind each, the rule that proposed it); a tap runs `start` again with the arguments of the
  start answer's own button for that option, so the decision is recorded in the guided path's shared state
  (flow_state.record, tapped) exactly as on the Start Krusgraph card.
- Dry run: the Fabric workload's build (workload_api.build_request and run_build_many): the silver and gold notebooks,
  the pipeline, the semantic model, the report and the data agent, each through its own MCP tool, on the review file
  of the person's decisions (server._review_file with the flow's decisions and accepted links: review_plan's file, the
  check counted). Each item is marked as the workload marks it (decision_of: create, update in place, already built,
  waits for a choice, refused), with its definition and the exact target (workspace › lakehouse). The build workspace
  and lakehouse are chosen as the workload's target (target_request: another workspace than the source's, one of its
  lakehouses or the default the engine names).
- Create: only after the page's confirm dialog, which lists each item by name, sends back the dry run's token and those
  names. The token is the digest of what the dry run showed (the inputs, the plan, each item's name and action, the
  confirm_update of an item updated in place); it is kept in this process for this session only, used once, and
  older than DRY_TTL it is stale. Before anything is written the dry run is made again; if its token differs (a
  decision changed, an item appeared in the workspace, the plan changed), nothing is written and the person sees why.
  Then each item is one background operation (operations.py, as the workload's Prefer: respond-async), run by
  workload_api.run_build_background: one output per request, capacity throttling waited out, Fabric's long-running
  operations followed, an item still in Fabric's hands answered as started (pending_fabric), never failed for it. The
  workload's own rules hold: an item someone else made is never written, a report is never updated, a missing
  permission is said as kind consent; nothing is ever deleted.
- Verify: workload_api.run_verify, verify_build's rules on what this session created (W4/W5: across workspaces when
  the build is in another workspace than the source's), with its next steps. Checked by rules, not by AI.

What is kept: per session, in memory, next to the session itself (guided_app.SESSIONS): the last dry run (its token,
inputs and review file) and the items this session created (the workload keeps those in outputs.json; here they let a
second dry run say "already built from this plan"). Never a token in a page or a log line.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time

from .guided_app import MAX_SESSIONS, NAME_MAX, Store

DRY_TTL = 900                     # seconds a dry run's token stays fresh
OUTPUTS = (("silver_notebook", "silver"), ("gold_views", "gold"), ("pipeline", "pipeline"), ("semantic_model", "model"),
           ("report", "report"), ("data_agent", "agent"))
REVIEWS = {"accepted": "Accepted", "rejected": "Rejected", "skipped": "Skipped for now"}
DEFINITION_MAX = 24000            # characters of one item's definition shown under "Show definition"
DEFINITION_KEYS = {"silver_notebook": ("notebook", "steps"), "gold_views": ("notebook", "views"),
                   "pipeline": ("pipeline", "steps"), "semantic_model": ("parts",), "report": ("report",),
                   "data_agent": ("agent",)}
BADGE = {"create": "New", "update": "Update in place", "skip": "Already built", "choose": "Waits for your choice",
         "refuse": "Not written", "error": "Not written"}
WRITES = ("create", "update")     # the actions Create carries out; every other card writes nothing
CHECKED_BY = "Checked by rules, not by AI"
STALE = "Something changed since this dry run, so nothing was written."

BUILDS = Store(MAX_SESSIONS)      # per session digest: {"dry": {...}, "run": {...}, "created": [...]}
_LOCK = threading.Lock()


def _state(sid: str) -> dict:
    with _LOCK:
        st = BUILDS.get(sid)
        if st is None:
            st = {"created": []}
            BUILDS.put(sid, st, time.time() + 2 * 3600)
        return st


def outputs(source: str, schema: str) -> list[dict]:
    """The items a dry run shows, named as the start path names them (start_flow.base_name): <stem>_silver, ..."""
    from .start_flow import base_name
    stem = base_name(source, schema)
    return [{"kind": k, "name": f"{stem}_{suffix}"[:123]} for k, suffix in OUTPUTS]


def chosen(data: dict) -> dict | None:
    """The workspace, source and schema a build call names, trimmed, or None when one is missing."""
    c = {k: str(data.get(k) or "").strip()[:NAME_MAX] for k in ("workspace", "source", "schema")}
    return c if all(c.values()) else None


def flow(tokens, c: dict) -> dict:
    """The decisions and accepted links of this person's path for (workspace, source, schema): flow_state, as the start
    tool recorded them."""
    from . import flow_state
    return flow_state.state(tokens.who, c["workspace"], c["source"], c["schema"]) or {}


def review(c: dict, kept: dict) -> dict:
    """review_plan's file with the person's decisions, the check counted: the start path's own (server._review_file)."""
    from . import server
    return server._review_file(c["workspace"], c["source"], c["schema"], None, kept.get("confirmed"),
                               kept.get("decisions"), None, True, None, 60, None)


def _request(c: dict, rv: dict, target: dict | None, update: list[str], confirm: dict, *, dry_run: bool,
             created: list[dict], only: list[str] | None = None, model: str | None = None) -> dict:
    """The workload's build request (workload_api.build_request: its checks, its shape)."""
    from . import server, workload_api as W
    ws_id = server._workspace_id(c["workspace"], server._headers(None))
    outs = outputs(c["source"], c["schema"])
    if model:
        outs = [{**o, "model": model} if o["kind"] == "report" else o for o in outs]
    body = {"workspace": ws_id, "source": c["source"], "source_name": c["source"], "schema": c["schema"], "review": rv,
            "outputs": outs, "dry_run": dry_run, "created": created, "skip_built": not dry_run,
            "update": list(update) or None, "confirm": dict(confirm) or None,
            "target": ({"workspace": target["workspace_id"], "where": "item",
                        **({"lakehouse": target["lakehouse"]} if target.get("lakehouse") else {})} if target else None)}
    if only:
        body["only"] = only
    return W.build_request({k: v for k, v in body.items() if v is not None})


def token_of(c: dict, kept: dict, target: dict | None, update: list[str], rv: dict, out: dict) -> str:
    """What the dry run showed, as a digest: the inputs, the plan and each item's name, action and update confirmation."""
    cards = [[x.get("output"), x.get("name"), x.get("type"), x.get("would"), (x.get("decision") or {}).get("action"),
              x.get("confirm_update")] for x in out.get("outputs") or []]
    raw = json.dumps([c, kept.get("decisions"), kept.get("confirmed"), target, sorted(update), rv.get("plan_id"),
                      rv.get("schema_fingerprint"), (out.get("build_in") or {}).get("workspace_id"),
                      (out.get("target") or {}).get("lakehouse"), (out.get("lakehouse") or {}).get("name"), cards],
                     sort_keys=True, default=str)
    return "dry-" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _definition(kind: str, answer: dict) -> str:
    """What Create sends for this item, as text for "Show definition": the semantic model's parts, the pipeline's
    definition, the notebooks' steps, the report's page, the agent's instructions. Shortened past DEFINITION_MAX."""
    if kind == "semantic_model" and isinstance(answer.get("parts"), dict):
        text = "\n\n".join(f"--- {p}\n{t}" for p, t in answer["parts"].items())
    else:
        text = json.dumps({k: answer[k] for k in DEFINITION_KEYS.get(kind, ()) if k in answer}, indent=1, ensure_ascii=False)
    if len(text) > DEFINITION_MAX:
        text = text[:DEFINITION_MAX] + "\n… (shortened here; Create sends the whole definition)"
    return text


def where(out: dict, c: dict) -> dict:
    """The exact target: {workspace, lakehouse, line: "build › build_lh", words}."""
    place = out.get("build_in") or {}
    ws = place.get("name") or c["workspace"]
    t = out.get("target") or {}
    lh_plan = out.get("lakehouse") or {}
    if t.get("lakehouse"):
        lh = t["lakehouse"]
    elif lh_plan.get("name"):
        lh = lh_plan["name"]
    else:
        lh = c["source"]                                    # the source lakehouse writes into itself (its silver, gold schemas)
    words = [x for x in (place.get("words"), lh_plan.get("words"), t.get("words")) if x]
    return {"workspace": ws, "workspace_id": place.get("workspace_id"), "lakehouse": lh, "line": f"{ws} › {lh}",
            "cross": bool(place.get("cross")), "words": words}


def card(x: dict, workspace_id: str | None = None) -> dict:
    """One item as the page draws it, the same for the dry run and Create."""
    from .mcp_apps_build import item_url
    d = x.get("decision") or {}
    a = x.get("answer") or {}
    action = d.get("action") or ("refuse" if x.get("refusal") else "error" if a.get("error") else "create")
    out = {"kind": x.get("output"), "label": x.get("label"), "name": x.get("name"), "type": x.get("type"),
           "action": action, "badge": BADGE.get(action, ""), "words": d.get("words") or ""}
    if x.get("dry_run") and not a.get("error") and action in WRITES:
        out["definition"] = _definition(str(x.get("output")), a)
    if x.get("consent") or (a.get("kind") == "consent") or (x.get("refusal") or {}).get("kind") == "consent":
        con = x.get("consent") or x.get("refusal") or a
        out["consent"] = {k: con[k] for k in ("error", "hint", "scope") if con.get(k)}
        if con.get("entra_steps"):
            out["consent"]["steps"] = [str(s) for s in con["entra_steps"]][:6]
    if x.get("created"):
        out["created"] = [{"type": i.get("type"), "name": i.get("name"),
                           "url": item_url(i.get("workspace") or workspace_id or "", i.get("type") or "", i.get("id") or "")}
                          for i in x["created"]]
    if x.get("portal_steps"):
        out["steps"] = [str(s) for s in x["portal_steps"]][:6]
    if x.get("pending_fabric") or a.get("kind") in ("pending_fabric", "timeout"):
        out["action"], out["badge"] = "started", "Started"
        out["words"] = " ".join(v for v in (a.get("error"), a.get("hint")) if v) or (
            "Sent once; Fabric is still working on it. A new dry run shows it as built when Fabric has finished.")
    if x.get("waiting_capacity"):
        out["action"], out["badge"] = "capacity", "Capacity busy"
        out["words"] = "Fabric is still throttling the capacity; nothing more was sent. Try Create again later."
    return out


def dry_run(tokens, sid: str, c: dict, target: dict | None, update: list[str]) -> dict:
    """The dry run, kept for this session with its token. Writes nothing."""
    from . import server, workload_api as W
    from .start_flow import _decided_line
    st = _state(sid)
    with server.workload_tokens(tokens):
        kept = flow(tokens, c)
        rv = review(c, kept)
        out = W.run_build_many(_request(c, rv, target, update, {}, dry_run=True, created=list(st["created"])))
    if out.get("error"):
        return {k: str(out[k])[:400] for k in ("error", "kind", "hint") if out.get(k)}
    token = token_of(c, kept, target, update, rv, out)
    place = where(out, c)
    cards = [card(x) for x in out.get("outputs") or []]
    confirm = {x["output"]: x["confirm_update"] for x in out.get("outputs") or [] if x.get("confirm_update")}
    st["dry"] = {"token": token, "at": time.time(), "c": c, "target": target, "update": list(update), "rv": rv,
                 "confirm": confirm, "items": [{"kind": x["kind"], "name": x["name"], "label": x["label"]}
                                               for x in cards if x["action"] in WRITES]}
    st.pop("run", None)
    from .guided_app import log
    log("dry_run", items=len(cards), writes=len(st["dry"]["items"]), cross=place["cross"])
    v = {"stage": "dry_run", "who": "builder", "token": token, "target": place, "items": cards,
         "creates": st["dry"]["items"], "note": W.NOTHING_CHANGED, "chosen": c,
         "decided": [_decided_line(d, False) for d in kept.get("decisions") or [] if isinstance(d, dict)]}
    if out.get("left_out_by_review"):
        v["left_out"] = [str(x.get("what") or x.get("id")) if isinstance(x, dict) else str(x) for x in out["left_out_by_review"]][:20]
    if out.get("access"):
        v["access"] = str(out["access"])
    waiting = [x["name"] for x in cards if x["action"] == "choose"]
    n = len(st["dry"]["items"])
    v["say"] = (f"The dry run: {n} item{'' if n == 1 else 's'} would be written in {place['line']}. Nothing is created yet."
                if n else f"The dry run: nothing would be written in {place['line']}.")
    if waiting:
        v["say"] += f" {len(waiting)} wait{'s' if len(waiting) == 1 else ''} for your choice: update in place or a new name."
    return v


def places(tokens) -> dict:
    """The workspaces this person can build in (server._workspaces), for "Change where to build"."""
    from . import server
    with server.workload_tokens(tokens):
        listed = server._workspaces(server._headers(None))
    return {"workspaces": [{"id": str(w.get("id")), "name": str(w.get("name") or w.get("displayName") or w.get("id"))}
                           for w in listed if w.get("id")][:200]}


def lakehouses(tokens, workspace_id: str) -> dict:
    """The lakehouses of one workspace this person can see, for the build's lakehouse."""
    from . import server
    with server.workload_tokens(tokens):
        ids = {str(w.get("id")).lower(): w for w in server._workspaces(server._headers(None)) if w.get("id")}
        w = ids.get(str(workspace_id).lower())
        if w is None:
            return {"error": "That workspace is not one you can open.", "kind": "not_found"}
        items = server._list_items(str(w["id"]), server._headers(None))
    names = sorted({str(i.get("displayName")) for i in items if i.get("type") == "Lakehouse" and i.get("displayName")},
                   key=str.lower)
    return {"workspace": {"id": str(w["id"]), "name": str(w.get("name") or w.get("displayName") or w["id"])},
            "lakehouses": names[:200]}


def target_of(tokens, c: dict, data) -> dict | None:
    """The build target the page asked for, checked: a workspace this person can see (by id) other than the source's,
    and a lakehouse of it by name (or none: the engine's default). None: build in the source's workspace."""
    from . import server
    if not isinstance(data, dict) or not data.get("workspace"):
        return None
    want = str(data["workspace"]).strip().lower()
    with server.workload_tokens(tokens):
        headers = server._headers(None)
        source_ws = str(server._workspace_id(c["workspace"], headers)).lower()
        listed = {str(w.get("id")).lower(): w for w in server._workspaces(headers) if w.get("id")}
    if want == source_ws:
        return None
    if want not in listed:
        raise ValueError("That workspace is not one you can open.")
    lh = str(data.get("lakehouse") or "").strip()[:NAME_MAX]
    if lh:
        names = lakehouses(tokens, want).get("lakehouses") or []
        if lh not in names:
            raise ValueError("That lakehouse is not in the workspace you chose.")
    return {"workspace_id": str(listed[want]["id"]), **({"lakehouse": lh} if lh else {})}


def confirm(tokens, sid: str, token: str, names: list[str]) -> dict:
    """Create's gate: the dry run's token, fresh and unused, and exactly the names it showed; then the dry run once more
    with the same inputs, whose token must be the same. On any difference nothing is written."""
    from . import server, workload_api as W
    st = _state(sid)
    dry = st.get("dry")
    if not dry or not isinstance(token, str) or token != dry["token"]:
        return {"error": STALE, "kind": "stale", "hint": "Run the dry run again: Create writes only what the latest dry run showed."}
    if time.time() - dry["at"] > DRY_TTL:
        st.pop("dry", None)
        return {"error": STALE, "kind": "stale", "hint": f"A dry run is fresh for {DRY_TTL // 60} minutes. Run it again."}
    want = sorted(x["name"] for x in dry["items"])
    if not isinstance(names, list) or sorted(str(n) for n in names) != want or not want:
        return {"error": "The names you confirmed are not the ones the dry run would write; nothing was written.",
                "kind": "bad_request", "hint": "Confirm the list the dry run shows."}
    st.pop("dry", None)                                      # one Create per dry run: the token is used now
    c, target, update = dry["c"], dry["target"], dry["update"]
    with server.workload_tokens(tokens):
        kept = flow(tokens, c)
        rv = review(c, kept)
        again = W.run_build_many(_request(c, rv, target, update, {}, dry_run=True, created=list(st["created"])))
    if again.get("error") or token_of(c, kept, target, update, rv, again) != token:
        from .guided_app import log
        log("create_refused", reason="stale")
        return {"error": STALE, "kind": "stale",
                "hint": "A decision, the plan or the items in the workspace changed. Run the dry run again and read it."}
    run = {"id": secrets.token_urlsafe(16), "c": c, "target": target, "update": update, "rv": rv,
           "confirm": {x["output"]: x["confirm_update"] for x in again.get("outputs") or [] if x.get("confirm_update")},
           "todo": [x["kind"] for x in dry["items"]], "started": {}, "done": {}, "created": [],
           "workspace_id": (again.get("build_in") or {}).get("workspace_id")}
    st["run"] = run
    from .guided_app import log
    log("create_confirmed", items=len(run["todo"]))
    return {"run": run["id"], "items": dry["items"]}


def create_item(tokens, sid: str, run_id: str, kind: str, owner: str) -> dict:
    """One confirmed item, in the order the dry run showed, as a background operation (operations.start). Never an item
    the dry run did not show, never one twice."""
    from . import operations, server, workload_api as W
    st = _state(sid)
    run = st.get("run")
    if not run or not isinstance(run_id, str) or run_id != run["id"]:
        return {"error": "This Create is not the one confirmed; nothing was written.", "kind": "stale",
                "hint": "Run the dry run again and confirm the names."}
    nxt = next((k for k in run["todo"] if k not in run["started"]), None)
    if kind != nxt:
        return {"error": "Not the next item of the confirmed list; nothing was written.", "kind": "bad_request",
                "hint": "Create writes the items in the order the dry run showed, each once."}
    run["started"][kind] = time.time()
    model = None
    if kind == "report":                                    # the report binds to the model this Create made (its id), else
        name = next(o["name"] for o in outputs(run["c"]["source"], run["c"]["schema"]) if o["kind"] == "semantic_model")
        model = next((i["id"] for i in list(run["created"]) + list(st["created"])          # the one built before, by name
                      if i.get("type") == "SemanticModel" and i.get("name") == name), None) or name
    with server.workload_tokens(tokens):
        req = _request(run["c"], run["rv"], run["target"], [k for k in run["update"] if k == kind],
                       {k: v for k, v in run["confirm"].items() if k == kind}, dry_run=False,
                       created=list(st["created"]) + list(run["created"]), only=[kind], model=model)

    def work():
        with server.workload_tokens(tokens):
            try:
                out = W.run_build_background(req)
            except Exception as exc:                        # noqa: BLE001 — explained, never leaked
                from .errors import explain
                out = explain(exc, f"creating {kind}")
        made = [i for i in out.get("created") or [] if isinstance(i, dict) and i.get("id")]
        with _LOCK:
            run["created"] += made
            st["created"] += made
            run["done"][kind] = True
        return out, 200
    op = operations.start("app-create", owner, work, tokens=tokens, output=kind, create=run["id"])
    from .guided_app import log
    log("create_item", output=kind)
    return {"operation_id": op["id"], "kind": kind}


def item_state(tokens, sid: str, op_id: str, owner: str) -> dict:
    """The state of one item's operation; once done, its card (with links to the items in Fabric)."""
    from . import operations
    got = operations.state(op_id, owner, tokens) if isinstance(op_id, str) and len(op_id) <= 64 else None
    if got is None:
        return {"error": "No such step for this sign-in.", "kind": "not_found"}
    out = {"status": got.get("status"), "kind": got.get("output")}
    prog = got.get("progress") or {}
    if prog.get("words"):
        out["words"] = str(prog["words"])[:300]
    if got.get("status") == "lost":
        out["words"] = str(got.get("lost") or "The engine stopped working on this step.")
    if got.get("status") == "done":
        ans = got.get("answer") or {}
        run = _state(sid).get("run") or {}
        if ans.get("error") and not ans.get("outputs"):
            out["item"] = {"kind": got.get("output"), "action": "error", "badge": BADGE["error"],
                           "words": " ".join(str(ans[k]) for k in ("error", "hint") if ans.get(k))[:600]}
        else:
            x = (ans.get("outputs") or [{}])[0]
            out["item"] = card(x, run.get("workspace_id"))
            if ans.get("capacity"):
                out["item"].update(action="capacity", badge="Capacity busy", words=str(ans["capacity"].get("words") or ""))
    return out


def verify(tokens, sid: str) -> dict:
    """verify_build's rules on what this session created (workload_api.run_verify), read-only."""
    from . import server, workload_api as W
    st = _state(sid)
    run = st.get("run")
    if not run or not st["created"]:
        return {"error": "Nothing was created here yet, so there is nothing to verify.", "kind": "not_found"}
    c = run["c"]
    with server.workload_tokens(tokens):
        ws_id = server._workspace_id(c["workspace"], server._headers(None))
        req = W.verify_request({"workspace": ws_id, "source": c["source"], "source_name": c["source"], "schema": c["schema"],
                                "review": run["rv"], "created": st["created"]})
        out = W.run_verify(req)
    if out.get("error"):
        return {k: str(out[k])[:400] for k in ("error", "kind", "hint") if out.get(k)}
    lines = []
    for x in out.get("lines") or []:
        if not isinstance(x, dict):
            continue
        said = [str(f.get("said")) for f in x.get("figures") or [] if isinstance(f, dict) and f.get("said")][:4]
        lines.append({"item": x.get("item"), "kind": x.get("kind"), "state": x.get("state") or x.get("verdict") or "",
                      "said": str(x.get("said") or x.get("summary") or ""), "figures": said})
    return {"stage": "verify", "who": "thinker", "title": CHECKED_BY, "label": str(out.get("label") or ""),
            "summary": str(out.get("summary") or ""), "counts": out.get("counts") or {}, "lines": lines,
            "next_steps": [{"label": s.get("label"), "why": s.get("why")} for s in out.get("next_steps") or []][:8],
            "note": str(out.get("note") or "")}


# ------------------------------------------------------------------ Decide: the start tool's own buttons ------------

def option_words(review_: str, link: dict | None, source_target: tuple[str, str]) -> str:
    """The count behind one option, from the check's own counts on the map (rows with a value, rows that point at
    nothing), in plain words."""
    src, tgt = source_target
    n = int((link or {}).get("rows_with_value") or 0)
    o = int((link or {}).get("orphans") or 0)
    if review_ == "accepted":
        if n and o:
            return f"Keeps the link: {n - o} of {n} rows join; {o} {'goes' if o == 1 else 'go'} to quarantine with the reason."
        return f"Keeps the link: {n} of {n} rows join." if n else "Keeps the link."
    if review_ == "rejected":
        return f"Leaves the link out: nothing built joins {src} to {tgt}."
    return "Leaves it open: the build leaves the link out until you decide."


def decisions_view(out: dict) -> list[dict]:
    """Each decision of the start tool's decide step as a card: the question, the rule that proposed it in words, the
    evidence, the options with the count behind each, and the person's choice when made ("Decided by you")."""
    from .start_flow import RULE_WORDS
    found = (out.get("found") or {}).get("decisions") or []
    links = {}
    for r in ((out.get("map") or {}).get("relationships") or []):
        if isinstance(r, dict) and r.get("id"):
            links["rel:" + str(r["id"])] = r
    acts = [a for a in out.get("actions") or [] if isinstance(a, dict) and a.get("kind") == "decide"]
    cards = []
    for d in found:
        if not isinstance(d, dict) or not d.get("item"):
            continue
        item = str(d["item"])
        link = links.get(item)
        st = (link or {}).get("source") or item.split(":", 1)[-1].split(".")[0]
        tg = (link or {}).get("target") or item.rsplit(">", 1)[-1]
        rule = str(d.get("rule") or "")
        state = str(d.get("state") or "open")
        labels = {a.get("decision"): a.get("label") for a in acts if a.get("item") == item}
        options = []
        for rv in ("accepted", "rejected", "skipped"):
            label = labels.get(rv)
            if not label and state != rv:
                continue
            if not label:                                   # the one taken: start offers only the others
                label = {"accepted": "Accept with quarantine" if d.get("check") == "failed" else "Accept",
                         "rejected": "Reject", "skipped": "Skip for now"}[rv]
            options.append({"review": rv, "label": str(label).replace("Change to ", ""), "words": option_words(rv, link, (st, tg)),
                            **({"selected": True} if state == rv else {})})
        cards.append({"item": item, "what": item.split(":", 1)[-1].replace(">", " \u2192 "), "question": str(d.get("question") or ""), "evidence": [str(x) for x in d.get("evidence") or []][:6],
                      "count": str(d.get("count") or ""), "rule": rule,
                      "rule_words": RULE_WORDS.get(rule) or ("Krusgraph's list of known SAP keys and links (the SAP pack)"
                                                              if rule == "SAP pack" else ""),
                      "check": str(d.get("check") or ""), "state": state,
                      **({"decided": f"Decided by you: {REVIEWS.get(state, state)}"} if state != "open" else {}),
                      "options": options})
    return cards


def remember_rules(sid: str, cards: list[dict]) -> list[dict]:
    """An accepted link is passed on as confirmed, so the review names its rule "confirmed" from then on. The rule that
    proposed it, as this session saw it while the decision was open, stays on its card."""
    seen = _state(sid).setdefault("rules", {})
    for x in cards:
        if x.get("rule") and x["rule"] != "confirmed":
            seen[x["item"]] = (x["rule"], x.get("rule_words") or "")
        elif x.get("rule") == "confirmed":
            rule, words = seen.get(x["item"]) or ("", "")
            x["rule"], x["rule_words"] = (rule, words) if rule else ("confirmed", "a link you confirmed")
    return cards


def decide_action(out: dict, item: str, review_: str) -> dict | None:
    """The arguments of the start answer's own button for (item, review): what the Start Krusgraph card would send."""
    for a in out.get("actions") or []:
        if (isinstance(a, dict) and a.get("kind") == "decide" and a.get("item") == item and a.get("decision") == review_
                and isinstance(a.get("arguments"), dict)):
            return a["arguments"]
    return None
