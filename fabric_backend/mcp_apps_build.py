"""MCP Apps, clickable next steps (round n169): the Builder's and the Thinker's buttons, and the build card.

Founder, 8 November 2026: "I want to click the mascots' suggestions and have everything created, without writing text."
Behind the n119 flag (KRUSGRAPH_MCP_APPS, off unless "1"); with the flag off nothing here reaches the server: no
resource, no `_meta`, no `actions` in any answer, and the tool listing is what it was.

What the specification allows a card to do, and what is used here. Source: modelcontextprotocol/ext-apps,
specification/2026-01-26/apps.mdx ("SEP-1865: MCP Apps", Status: Stable), at commit
19256f52cad5517ba8272581ed2e11d6a81273d5, read again on 8 November 2026; only the specification was read, no code copied.

- "Standard MCP Messages": a view may send `tools/call` ("Execute a tool on the MCP server"). The host says whether it
  proxies such calls in its `ui/initialize` answer, `hostCapabilities.serverTools` ("Host Capabilities"); "Transport
  Layer", point 8: the host "MAY decide to block some messages or subject them to further user approval". A button
  therefore says that the host may ask first, and waits (CALL_JS in mcp_apps.py).
- "MCP Apps Specific Messages", Requests (View → Host): `ui/message` sends a message to the conversation as the user
  ("Host MAY request user consent"), and `ui/open-link` asks the host to open a URL (`hostCapabilities.openLinks`).
- "Visibility": a tool without `_meta.ui.visibility` is visible to the model and callable by the app; nothing here
  sets it, so every tool a button names is one Claude can also call from the chat.

How a button runs (ACTIONS_JS):
1. A host with `serverTools` gets `tools/call` for the action's tool with the action's arguments.
2. Otherwise, or when the host answers -32601 (method not found), the card sends the action's `say` sentence with
   `ui/message`: the user sees it in the chat as their own message and Claude runs it. Only when that is refused too
   does the card show the sentence to copy.
3. "Open in Fabric" uses `ui/open-link` when the host has `openLinks`, otherwise it shows the address.

What the buttons are, all of them built here on the server from the tool's own answer (actions_for), never invented
by the card; the card draws only what the answer's `actions` list holds, and only for the tools in ALLOWED:
- after plan_backend: "Check against the rows" (validate_plan), then the three builds; after validate_plan the three
  builds ("Build a semantic model", "Create an ontology", "Create an API for GraphQL");
- plan_backend's answer when the source has several schemas with tables and the call named none: one button per
  schema, nothing else (server.plan_backend asks instead of picking);
- every build button is a dry run (`dry_run: true`); the dry run's answer is drawn on the card, and only that answer
  carries "Create": the same tool, the dry run's arguments unchanged, `dry_run: false`;
- after a create that succeeded: "Open in Fabric" (the item's address, from the answer's result id) and, after a
  semantic model, "Create a report on it" (create_report, again a dry run first).

Names: each build gets a free name derived from the source (the schema, or the source's name when the schema is dbo):
shop_model, then shop_model_2, shop_model_3 ... until no item of the workspace has it (any type, case-insensitive).
The card shows the name on the button before the click. When the workspace's item names cannot be read, no build
button is offered and the answer says why; a dry run whose name an item already has gets no Create button.

Text-only clients (Lovable, VS Code, Cursor) get the same answer text with the same `actions`, each with its `say`
sentence: the next steps listed as text.
"""
from __future__ import annotations

import functools
import inspect
import json
import re

from . import mcp_apps
from . import mcp_apps_mascots as mascots

CARD_URI = "ui://krusgraph/build-card.html"
# The tools whose answer is drawn on the build card (validate_plan and review_plan keep their own cards).
CARD_TOOLS = ("plan_backend", "create_semantic_model", "create_ontology", "create_backend", "create_report")
# n170: the drafts with a picture (mcp_apps_pictures) are drawn on the build card too.
PICTURE_CARD_TOOLS = ("ontology_draft", "domain_draft")
# The tools whose answer gets `actions` (validate_plan's card draws them under its own next steps; n170: domain_draft's
# per data product).
ACTION_TOOLS = CARD_TOOLS + ("validate_plan", "domain_draft")
BUILD_TOOLS = ("create_semantic_model", "create_ontology", "create_backend", "create_report")
# What a button may ask for: the read tools by name, the creating tools only as a dry run or as Create after one.
ALLOWED = {"validate_plan": "call", "plan_backend": "call", **{t: "build" for t in BUILD_TOOLS}}
SUFFIX = {"create_semantic_model": "model", "create_ontology": "ontology", "create_backend": "api"}
LABEL = {"create_semantic_model": "Build a semantic model", "create_ontology": "Create an ontology",
         "create_backend": "Create an API for GraphQL", "create_report": "Create a report on it"}
FABRIC_APP = "https://app.fabric.microsoft.com"
_NOT_NAME = re.compile(r"[^A-Za-z0-9_]+")
MAX_TRIES = 200


def tool_meta(on: bool | None = None) -> dict | None:
    """The build card's `_meta` for a tool in CARD_TOOLS when the flag is on, else None."""
    if not (mcp_apps.enabled() if on is None else on):
        return None
    return {"ui": {"resourceUri": CARD_URI}, "ui/resourceUri": CARD_URI}


def add_to(apps) -> None:
    """Registers the build card on the SDK's Apps extension that mcp_apps.extensions() builds."""
    apps.add_html_resource(CARD_URI, card_html(), name="build_card", title="Plan and build",
                           description="A plan, a dry run or a created item as a card, with the Builder's and the "
                                       "Thinker's next steps as buttons. A build button runs a dry run first; only the "
                                       "dry run's card has Create.",
                           prefers_border=True)


# ------------------------------------------------------------------ names ---------------------------------------------

def name_base(source: str, schema: str | None) -> str:
    """shop for schema shop; the source's name when the schema is dbo or not given. Letters, digits and underscores."""
    raw = schema if schema and str(schema).lower() != "dbo" else source
    base = _NOT_NAME.sub("_", str(raw or "")).strip("_") or "krusgraph"
    return ("kg_" + base if base[0].isdigit() else base)[:60]


def free_name(base: str, taken) -> str:
    """base, else base_2, base_3 ...: the first that no name in `taken` has (case-insensitive). Never one taken."""
    low = {str(t).lower() for t in taken}
    if base.lower() not in low:
        return base
    for i in range(2, MAX_TRIES + 2):
        cand = f"{base}_{i}"
        if cand.lower() not in low:
            return cand
    raise ValueError(f"no free name for {base!r}")


def open_url(workspace_id: str, tool: str, item_id: str) -> str:
    """The item in the Fabric portal: a report and a semantic model open themselves (the Power BI paths
    /groups/{workspace}/reports/{id} and /datasets/{id}/details); an API for GraphQL and an ontology open the
    workspace's item list, where the item is."""
    if tool == "create_report":
        return f"{FABRIC_APP}/groups/{workspace_id}/reports/{item_id}"
    if tool == "create_semantic_model":
        return f"{FABRIC_APP}/groups/{workspace_id}/datasets/{item_id}/details"
    return f"{FABRIC_APP}/groups/{workspace_id}/list"


# ------------------------------------------------------------------ actions -------------------------------------------

def _shown(args: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())


def action(kind: str, label: str, who: str, tool: str | None = None, arguments: dict | None = None,
           name: str | None = None, url: str | None = None, product: str | None = None) -> dict:
    """One button: {kind, label, who, tool, arguments, name, say}. `say` is the exact prompt the card sends to the chat
    when the host does not run tools from the card, and what a text client reads as the next step."""
    out = {"kind": kind, "label": label, "who": who}
    if tool:
        out["tool"], out["arguments"] = tool, dict(arguments or {})
    if name:
        out["name"] = name
    if product:
        out["product"] = product                                     # n170: drawn on that data product's card
    if kind == "link":
        out["url"] = url
        out["say"] = f"Open it in Fabric: {url}"
    elif kind == "create":
        out["say"] = (f"Create it: run {tool} with dry_run=false and the same arguments as the dry run: "
                      f"{_shown(out['arguments'])}.")
    elif kind == "dry_run":
        out["say"] = f"{label}{' named ' + name if name else ''}: run {tool} as a dry run with {_shown(out['arguments'])}."
    else:
        out["say"] = f"{label}: run {tool} with {_shown(out['arguments'])}."
    return out


def _carried(args: dict, *keys) -> dict:
    return {k: args[k] for k in keys if args.get(k) is not None}


def _builds(args: dict, schema: str | None, taken) -> list[dict]:
    """The three build buttons, each a dry run under a free name."""
    base = name_base(args.get("source", ""), schema)
    common = {**_carried(args, "workspace", "source"), **({"schema": schema} if schema else {}),
              **_carried(args, "keys", "confirmed")}
    out = []
    for tool in ("create_semantic_model", "create_ontology", "create_backend"):
        name = free_name(f"{base}_{SUFFIX[tool]}", taken)
        taken = set(taken) | {name}
        out.append(action("dry_run", LABEL[tool], "builder", tool, {**common, "name": name, "dry_run": True}, name=name))
    return out


def _product_builds(args: dict, answer: dict, taken) -> tuple[list[dict], str | None]:
    """n170: per data product of domain_draft's answer, the Builder's two dry runs over that product's tables: a
    semantic model and an API for GraphQL, each under a free name derived from the product. Only the products the
    answer holds; a product without tables gets none."""
    products = [d for d in answer.get("domains") or [] if isinstance(d, dict) and d.get("tables")]
    if not products:
        return [], None
    if taken is None:
        return [], ("The workspace's item names could not be read, so no name is suggested and nothing can be created "
                    "from the card; ask in the chat.")
    common = {**_carried(args, "workspace", "source", "schema", "confirmed")}
    out = []
    for d in products:
        slug = str(d.get("slug") or d.get("name"))
        base = name_base(slug, None)
        for tool in ("create_backend", "create_semantic_model"):
            name = free_name(f"{base}_{SUFFIX[tool]}", taken)
            taken = set(taken) | {name}
            label = LABEL[tool] + " for " + str(d.get("name") or slug)
            out.append(action("dry_run", label, "builder", tool, {**common, "tables": list(d["tables"]), "name": name, "dry_run": True},
                              name=name, product=slug))
    return out, None


def _count_failed(answer: dict) -> bool:
    """n172: the plan holds a candidate whose counting query could not run (infer.count_failed), in either detail form."""
    from .infer import R5_COUNT_FAILED
    return any((isinstance(x, dict) and x.get("not_counted") == "failed") or (isinstance(x, str) and R5_COUNT_FAILED in x)
               for x in answer.get("proposed") or [])


def actions_for(tool: str, args: dict, answer: dict, taken=None, workspace_id: str | None = None) -> tuple[list[dict], str | None]:
    """(actions, note) for one answer. `args` are the call's arguments as given (no ctx); `taken` the workspace's item
    names, or None when they could not be read (then no build button and no Create, and `note` says why)."""
    if not isinstance(answer, dict) or answer.get("error"):
        return [], None
    unreadable = ("The workspace's item names could not be read, so no name is suggested and nothing can be created "
                  "from the card; ask in the chat.")
    if tool == "plan_backend" and isinstance(answer.get("schemas"), list) and answer.get("choose_schema"):
        return [action("call", f"Plan {s['schema']} ({s['tables']} tables)", "thinker", "plan_backend",
                       {**args, "schema": s["schema"]}) for s in answer["schemas"] if isinstance(s, dict) and s.get("schema")], None
    if tool in ("plan_backend", "validate_plan"):
        schema = answer.get("schema_chosen") or args.get("schema")
        out = []
        if tool == "plan_backend" and _count_failed(answer):           # n172: a counting query could not run
            out.append(action("call", "Count again", "thinker", "plan_backend", dict(args)))
        if tool == "plan_backend":
            out.append(action("call", "Check against the rows", "thinker", "validate_plan",
                              {**_carried(args, "workspace", "source"), **({"schema": schema} if schema else {}),
                               **_carried(args, "keys", "confirmed")}))
        if taken is None:
            return out, unreadable
        return out + _builds(args, schema, taken), None
    if tool == "domain_draft":
        return _product_builds(args, answer, taken)
    if tool in BUILD_TOOLS and answer.get("dry_run") is True:
        if taken is None:
            return [], unreadable
        name = args.get("name")
        if name and str(name).lower() in {str(t).lower() for t in taken}:
            return [], (f"An item named {name!r} already exists in the workspace. Create is not offered on the card, so "
                        "nothing is overwritten from here; choose another name, or ask in the chat to update it.")
        return [action("create", "Create", "builder", tool, {**args, "dry_run": False}, name=name)], None
    if tool in BUILD_TOOLS and answer.get("dry_run") is False:
        result = answer.get("result") if isinstance(answer.get("result"), dict) else {}
        if result.get("status") != "Succeeded" or not result.get("id") or not workspace_id:
            return [], None
        out = [action("link", "Open in Fabric", "builder", url=open_url(workspace_id, tool, result["id"]))]
        if tool == "create_semantic_model" and taken is not None:
            model = args.get("name")
            name = free_name(f"{model}_report", set(taken) | {model})
            out.append(action("dry_run", LABEL["create_report"], "builder", "create_report",
                              {**_carried(args, "workspace"), "model": model, "name": name, "dry_run": True}, name=name))
        return out, None
    return [], None


def with_actions(name: str, fn, item_names, workspace_id):
    """The registered form of a tool in ACTION_TOOLS when the flag is on: the tool's answer plus `actions` (and
    `actions_note`). `item_names(workspace, ctx)` gives the workspace's item names or raises; `workspace_id(workspace,
    ctx)` its id. Neither runs for an answer that gets no buttons; a failure in either never changes the answer."""
    sig = inspect.signature(fn)
    defaults = {k: p.default for k, p in sig.parameters.items()
                if k != "ctx" and p.default is not inspect.Parameter.empty and isinstance(p.default, (str, int, float, bool))}

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        if not isinstance(out, str):
            return out
        try:
            data = json.loads(out)
        except ValueError:
            return out
        if not isinstance(data, dict) or data.get("error"):
            return out
        try:
            bound = sig.bind_partial(*args, **kwargs).arguments
        except TypeError:
            return out
        ctx = bound.get("ctx")
        # n172: the MCP SDK calls a tool with every parameter, its defaults included (keys=None, writable=False ...),
        # where a direct call has only what was given. The buttons are built from what the call changed: an argument
        # equal to the tool's own default, or null, is left out, so a Create carries the dry run's arguments as the
        # card sent them (founder, 8 November 2026: the dry run drew no Create in Claude).
        call = {k: v for k, v in bound.items() if k != "ctx" and v is not None
                and not (k in defaults and k != "dry_run" and v == defaults[k])}
        if "workspace" not in call:
            return out
        needs_names = not (name == "plan_backend" and data.get("choose_schema")) and not (
            name in BUILD_TOOLS and data.get("dry_run") is False and name != "create_semantic_model")
        taken = None
        if needs_names:
            try:
                taken = set(item_names(call["workspace"], ctx))
            except Exception:                                        # noqa: BLE001 - the answer stands; no name offered
                taken = None
        ws_id = None
        if name in BUILD_TOOLS and data.get("dry_run") is False:
            try:
                ws_id = workspace_id(call["workspace"], ctx)
            except Exception:                                        # noqa: BLE001
                ws_id = None
        acts, note = actions_for(name, call, data, taken, ws_id)
        for a in acts:                                               # the card compares a Create's arguments modulo these
            if a.get("kind") == "create":
                a["defaults"] = {k: v for k, v in defaults.items() if k != "dry_run"}
        if not acts and not note:
            return out
        if acts:
            data["actions"] = acts
        if note:
            data["actions_note"] = note
        return json.dumps(data, indent=2, default=str)
    return wrapper


# ------------------------------------------------------------------ the card's script ---------------------------------
# Shared by both cards (mcp_apps.card_html and card_html below). renderActions(list, box) draws the answer's `actions`
# as buttons under the mascot who suggests them; a click runs the action (tools/call, else ui/message, else the sentence
# to copy) and draws the answer under the button, with that answer's own actions under it: a dry run's Create, a
# create's Open in Fabric. The card enforces what the server built: only tools in ALLOWED, a build button's arguments
# with dry_run true, and Create only from an answer whose dry_run is true, with exactly that answer's arguments.
ACTIONS_JS = r"""
  var ACT_ALLOWED = __ACT_ALLOWED__, WHO = { builder: "Builder", thinker: "Thinker" };
  function canOpenLinks() { return isObj(hostCaps) && isObj(hostCaps.openLinks); }
  function canon(x) {                                            // JSON with sorted keys: the order of arguments does not matter
    if (Array.isArray(x)) return "[" + x.map(canon).join(",") + "]";
    if (isObj(x)) return "{" + Object.keys(x).sort().map(function (k) { return JSON.stringify(k) + ":" + canon(x[k]); }).join(",") + "}";
    return JSON.stringify(x === undefined ? null : x);
  }
  function sameArgs(a, b) { return canon(a) === canon(b); }
  // n172: the arguments as the tool runs them: a null, or a value equal to the tool's own default (the Create action's
  // `defaults`), is the same as leaving the argument out. The MCP SDK fills in defaults; the card sends only what it set.
  function effective(x, defs) {
    var out = {};
    Object.keys(x || {}).forEach(function (k) {
      var v = x[k];
      if (v === null || v === undefined) return;
      if (k !== "dry_run" && isObj(defs) && Object.prototype.hasOwnProperty.call(defs, k) && canon(defs[k]) === canon(v)) return;
      out[k] = v;
    });
    return out;
  }
  function okAction(a, fromDryRun) {
    if (!isObj(a) || typeof a.label !== "string") return false;
    if (a.kind === "link") return typeof a.url === "string" && /^https:\/\/app\.fabric\.microsoft\.com\//.test(a.url);
    if (!Object.prototype.hasOwnProperty.call(ACT_ALLOWED, a.tool) || !isObj(a.arguments)) return false;
    if (a.kind === "call") return ACT_ALLOWED[a.tool] === "call";
    if (a.kind === "dry_run") return ACT_ALLOWED[a.tool] === "build" && a.arguments.dry_run === true;
    if (a.kind === "create") return ACT_ALLOWED[a.tool] === "build" && a.arguments.dry_run === false && fromDryRun === true;
    return false;
  }
  function sendMessage(text) { return request("ui/message", { role: "user", content: { type: "text", text: text } }); }
  function viaChat(a, out, button) {
    out.textContent = "Sent to the chat: “" + a.say + "”";
    sendMessage(a.say).then(function () { button.disabled = true; }, function () {
      out.textContent = "This host runs neither tools nor messages from the card. Ask in the chat: “" + a.say + "”";
      button.disabled = false;
    });
  }
  function runAction(a, button, out, dryArgs) {
    out.hidden = false; out.textContent = "";
    if (a.kind === "link") {
      if (!canOpenLinks()) { out.textContent = "Open this address: " + a.url; return; }
      request("ui/open-link", { url: a.url }).then(function () { out.textContent = "Opened in your browser."; },
        function () { out.textContent = "The host did not open it. The address: " + a.url; });
      return;
    }
    var args = a.kind === "create" ? JSON.parse(JSON.stringify(dryArgs)) : JSON.parse(JSON.stringify(a.arguments));
    if (a.kind === "create") args.dry_run = false;
    button.disabled = true;
    if (!canCallTools()) { viaChat(a, out, button); return; }
    out.textContent = a.kind === "create" ? "Asked the host to create it; it may ask you first." : "Asked the host to run " + a.tool + "; it may ask you first.";
    callTool(a.tool, args, function () { out.textContent = stillWaiting(a.say); }).then(function (r) {
      out.textContent = "";
      var d = answerOf(r);
      if (isObj(d) && d.kind === "upgrade") { upgradeView(d, out); button.disabled = false; return; }   // n171
      out.appendChild(resultView(a.tool, r));
      if (d) renderActions(d, out, args);
      if (a.kind !== "create") button.disabled = false;
    }, function (e) {
      if (e && e.kind === "unsupported") { viaChat(a, out, button); return; }
      out.textContent = callProblem(e, a.tool, a.say);
      button.disabled = false;
    });
  }
  // n171: a Create refused because the organisation has no active subscription (entitlements.py with
  // KRUSGRAPH_MARKETPLACE=1): the reason, the hint, and a button to the offer (https only), instead of a bare error.
  function upgradeView(d, out) {
    out.textContent = "";
    out.appendChild(el("p", readable(d.error) ? d.error : "Creating needs a subscription for your organisation.", "warn"));
    if (readable(d.hint)) out.appendChild(el("p", d.hint, "muted"));
    var url = typeof d.upgrade_url === "string" && /^https:\/\/[^\s"<>]+$/.test(d.upgrade_url) ? d.upgrade_url : "";
    if (!url) return;
    var b = el("button", "See the subscription", "act-b"), said = el("p", "", "muted"); b.type = "button";
    b.addEventListener("click", function () {
      if (!canOpenLinks()) { said.textContent = "Open this address: " + url; return; }
      request("ui/open-link", { url: url }).then(function () { said.textContent = "Opened in your browser."; },
        function () { said.textContent = "The host did not open it. The address: " + url; });
    });
    out.appendChild(b); out.appendChild(said);
  }
  // d: an answer; box: where its buttons go; callArgs: the arguments of the call that gave d (a dry run's, for Create)
  // n170: product: draw only the actions of that data product (its card); without it, only the actions of none
  function renderActions(d, box, callArgs, product) {
    var list = Array.isArray(d.actions) ? d.actions : [], fromDry = d.dry_run === true, groups = {};
    if (readable(d.actions_note) && !product) box.appendChild(el("p", d.actions_note, "muted act-note"));
    list.forEach(function (a) {
      if (!okAction(a, fromDry)) return;
      if ((isObj(a) && a.product ? String(a.product) : "") !== (product ? String(product) : "")) return;
      if (a.kind === "create" && callArgs) {                      // Create carries the dry run's own arguments
        var want = JSON.parse(JSON.stringify(callArgs)); want.dry_run = false;
        if (!sameArgs(effective(want, a.defaults), effective(a.arguments, a.defaults))) return;
      }
      var who = WHO[a.who] ? a.who : "builder";
      if (!groups[who]) {
        groups[who] = el("div", null, "acts acts-" + who);
        groups[who].appendChild(el("p", WHO[who] + (who === "thinker" ? " asks" : " suggests"), "act-who"));
        box.appendChild(groups[who]);
      }
      var row = el("div", null, "act");
      var label = a.label + (a.name && a.kind === "dry_run" ? " (" + a.name + ")" : "");
      var b = el("button", label, a.kind === "create" ? "act-create" : "act-b"); b.type = "button";
      if (a.kind === "dry_run") row.appendChild(el("span", "Dry run first: nothing is created until you press Create.", "muted act-why"));
      if (a.kind === "create") row.appendChild(el("span", "Creates " + (a.name ? a.name : "it") + " in Fabric with exactly the dry run's arguments.", "muted act-why"));
      var out = el("div", null, "out"); out.hidden = true;
      b.addEventListener("click", function () { runAction(a, b, out, callArgs || a.arguments); });
      row.insertBefore(b, row.firstChild); row.appendChild(out); groups[who].appendChild(row);
    });
  }
"""

ACTIONS_CSS = """
.acts { display: grid; gap: 6px; border-top: 1px solid var(--kg-line); padding-top: 8px; margin-top: 4px }
.act-who { margin: 0; font-size: 13px; font-weight: 650; color: var(--kg-muted) }
.act { display: grid; gap: 4px }
.act-why { font-size: 12.5px }
.act .out { border-left: 3px solid var(--kg-line); padding-left: 8px; display: grid; gap: 6px }
button.act-create { background: var(--kg-ink); color: var(--kg-bg) }
"""


def actions_js() -> str:
    return ACTIONS_JS.replace("__ACT_ALLOWED__", json.dumps(ALLOWED, separators=(",", ":")))


def card_html() -> str:
    """The build card: one self-contained HTML5 document, no external load. It draws the answer of a tool in CARD_TOOLS
    (resultView's summary, a dry run's checks, a schema choice) and its actions; since n170 also the pictures
    (mcp_apps_pictures): the map, the ontology proposal and the data products."""
    from . import mcp_apps_pictures as pictures
    pic = pictures.html_parts()
    return (_HTML.replace("__PROTOCOL__", mcp_apps.PROTOCOL_VERSION)
            .replace("__PICTURES__", pic["section"])
            .replace("__READ_JS__", mcp_apps.READ_JS + mcp_apps.CALL_JS + mcp_apps.RESULT_JS + actions_js() + pic["js"])
            .replace("__MASCOT_CSS__", mascots.CSS).replace("__RESULT_CSS__", mcp_apps.RESULT_CSS + ACTIONS_CSS + pic["css"])
            .replace("__MASCOT_TOGGLE__", mascots.TOGGLE).replace("__MASCOTS__", mascots.section())
            .replace("__MASCOT_JS__", mascots.JS))


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plan and build</title>
<style>
:root {
  color-scheme: light dark;
  --kg-bg: var(--color-background-primary, light-dark(#ffffff, #1b1b1f));
  --kg-card: var(--color-background-secondary, light-dark(#f6f5fb, #26252c));
  --kg-ink: var(--color-text-primary, light-dark(#1b1b1f, #f3f2f7));
  --kg-muted: var(--color-text-secondary, light-dark(#55535e, #b9b6c4));
  --kg-line: var(--color-border-primary, light-dark(#d9d6e3, #3c3a44));
  --kg-ok: var(--color-text-success, light-dark(#1d6b3a, #8fd6a6));
  --kg-warn: var(--color-text-warning, light-dark(#8a4b00, #f2c27a));
  --kg-radius: var(--border-radius-lg, 14px);
  --kg-font: var(--font-sans, system-ui, -apple-system, "Segoe UI", sans-serif);
}
* { box-sizing: border-box }
[hidden] { display: none !important }
html, body { margin: 0; background: var(--kg-bg); color: var(--kg-ink); font: 15px/1.45 var(--kg-font) }
main { padding: 14px 16px; display: grid; gap: 12px }
h1 { margin: 0; font-size: 17px; font-weight: 650 }
p { margin: 0 }
.muted { color: var(--kg-muted); font-size: 13.5px }
ul { margin: 0; padding-left: 18px }
button { font: inherit; font-weight: 650; justify-self: start; color: var(--kg-ink); background: var(--kg-card);
  border: 1px solid var(--kg-line); border-radius: 999px; padding: 4px 14px; cursor: pointer; min-height: 32px }
button:disabled { cursor: default; opacity: .6 }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important } }
__MASCOT_CSS__
__RESULT_CSS__
</style>
</head>
<body>
<main>
  <div class="kg-head"><h1 id="title">Plan and build</h1>__MASCOT_TOGGLE__</div>
  <p class="muted" role="status" id="verdict">Waiting for the tool's answer.</p>
  __MASCOTS__
  __PICTURES__
  <div id="answer"></div>
  <div id="next"></div>
  <p class="muted">The same answer is in the text of the tool result. A button asks the host to run the tool, and the host may ask you first; a build always shows its dry run before Create.</p>
</main>
<script>
(function () {
  "use strict";
  var TITLES = { plan_backend: "Plan", create_semantic_model: "Semantic model", create_ontology: "Ontology",
                 create_backend: "API for GraphQL", create_report: "Report", ontology_draft: "Ontology proposal",
                 domain_draft: "Data products" };
  var input = {}, tool = "";
  var nextId = 1, pending = {};
  function send(msg) { window.parent.postMessage(msg, "*"); }
  function request(method, params) {
    var id = nextId++;
    send({ jsonrpc: "2.0", id: id, method: method, params: params });
    return new Promise(function (resolve, reject) { pending[id] = { resolve: resolve, reject: reject }; });
  }
  function notify(method, params) { send({ jsonrpc: "2.0", method: method, params: params || {} }); }
__MASCOT_JS__
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = String(text); if (cls) e.className = cls; return e; }

__READ_JS__
  function guessTool(d) {
    if (Array.isArray(d.domains) && "interfaces" in d) return "domain_draft";
    if (Array.isArray(d.bindings) && isObj(d.summary) && "entity_types" in d.summary) return "ontology_draft";
    if (d.choose_schema || "relationships" in d || "keys" in d) return "plan_backend";
    if (isObj(d.report)) return "create_report";
    if ("would" in d || "checks_passed" in d) return "create_backend";
    if (isObj(d.summary) && "entity_types" in d.summary) return "create_ontology";
    if (isObj(d.summary) && "relationships_active" in d.summary) return "create_semantic_model";
    return "";
  }
  function detailsOf(d) {                                   // the whole answer, folded: what the summary sentences came from
    var box = el("div", null, "res-box"), det = el("details"), full = JSON.stringify(d, null, 2);
    det.appendChild(el("summary", "Show details"));
    det.appendChild(el("pre", full.length > 60000 ? full.slice(0, 60000) + "\\n… (the rest is in the tool's own answer)" : full));
    box.appendChild(det);
    return box;
  }
  function firstLine(s) { return readable(s) ? String(s).split("\\n")[0] : ""; }
  function render(result) {
    var d = answerOf(result), verdict = document.getElementById("verdict");
    var answer = document.getElementById("answer"), next = document.getElementById("next");
    answer.textContent = ""; next.textContent = ""; mascotsQuiet();
    if (!d) { verdict.textContent = "The card could not read the answer; it is in the text of the tool result."; return; }
    if (readable(d.error)) { verdict.textContent = d.error + (readable(d.hint) ? " " + d.hint : ""); mascots({ thinker: [d.error, "think"] }, false); return; }
    var t = tool || guessTool(d);
    // n172: the card's words (mcp_apps_words.py): a short title, the summary as sentences Onto says once, and bubbles
    // in plain English; the buttons carry the arguments.
    var words = isObj(d.kg_card) ? d.kg_card : {};
    document.getElementById("title").textContent = readable(words.title) ? words.title :
      (TITLES[t] || "Plan and build") + (d.dry_run === true ? ": dry run" : (d.dry_run === false ? ": created" : ""));
    verdict.removeAttribute("data-echo"); verdict.removeAttribute("data-said"); verdict.hidden = false;
    var builder = readable(words.builder), thinker = readable(words.thinker), onto = "";
    if (d.choose_schema) {
      verdict.textContent = readable(d.summary);
      thinker = readable(d.summary);
    } else if (d.dry_run === true) {
      verdict.textContent = "Dry run: nothing was created. Read it, then press Create to create it with exactly these arguments.";
      answer.appendChild(resultView(t, { structuredContent: d }));
      if (Array.isArray(d.checks_passed)) { var ul = el("ul"); d.checks_passed.forEach(function (c) { if (readable(c)) ul.appendChild(el("li", c)); }); answer.appendChild(ul); }
      if (isObj(d.replaces) && readable(d.replaces.said)) answer.appendChild(el("p", d.replaces.said, "warn"));
    } else if (d.dry_run === false) {
      var st = isObj(d.result) ? d.result.status : "";
      verdict.textContent = st === "Succeeded" ? "Created in Fabric." : "Fabric answered: " + (st || "no status") + ".";
      answer.appendChild(resultView(t, { structuredContent: d }));
    } else if (t === "domain_draft") {
      var n = (Array.isArray(d.domains) ? d.domains : []).length;
      verdict.textContent = n + (n === 1 ? " data product" : " data products") + " proposed from the keys and relationships; nothing was created." + (readable(d.note) ? " " + d.note : "");
    } else if (t === "ontology_draft") {
      verdict.textContent = "A draft: nothing was created." + (readable(d.note) ? " " + d.note : "");
    } else if (Array.isArray(words.lines) && words.lines.length) {
      verdict.textContent = words.lines.filter(readable).join(" ");
      onto = readable(words.onto);
      if (onto && onto === verdict.textContent) { verdict.setAttribute("data-echo", "onto"); verdict.setAttribute("data-said", onto); }
      answer.appendChild(detailsOf(d));
    } else {
      var s = isObj(d.summary) ? "" : firstLine(d.summary);
      verdict.textContent = s || "The plan is in the answer.";
      answer.appendChild(resultView(t, { structuredContent: d }));
      onto = s;
    }
    // n170: the chat demo's pictures; Onto presents them (the picture's own description, which the list under it repeats)
    var pictured = drawPictures(d, isObj(input) ? input : null);
    if (pictured) onto = onto || pictured;
    renderActions(d, next, isObj(input) ? input : null);
    var acts = (Array.isArray(d.actions) ? d.actions : []).filter(isObj);   // each mascot says its first step, word for word
    var mine = function (who) { var a = acts.filter(function (x) { return x.who === who; })[0]; return a ? readable(a.say) : ""; };
    if (next.querySelector("button") && !isObj(d.kg_card)) { builder = builder || mine("builder"); thinker = thinker || mine("thinker"); }
    if (readable(d.actions_note)) thinker = thinker || d.actions_note;
    mascots({ onto: [onto, "point"], thinker: [thinker, "think"], builder: [builder, "explain"] }, false);
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var m = event.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id != null && !m.method && pending[m.id]) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) p.reject(m.error); else p.resolve(m.result);
      return;
    }
    if (m.method === "ui/notifications/tool-input") input = (m.params && m.params.arguments) || {};
    else if (m.method === "ui/notifications/tool-result") render(m.params);
    else if (m.method === "ui/notifications/tool-cancelled") { document.getElementById("verdict").textContent = "The call was cancelled."; mascotsQuiet(); }
    else if (m.method === "ui/resource-teardown" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
    else if (m.method === "ping" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
  });

  var last = 0;
  function reportSize() {
    var h = Math.ceil(document.documentElement.scrollHeight), w = Math.ceil(document.documentElement.scrollWidth);
    if (h !== last) { last = h; notify("ui/notifications/size-changed", { width: w, height: h }); }
  }
  request("ui/initialize", {
    appInfo: { name: "Krusgraph plan and build", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function (r) {
    hostStarted(r);
    if (isObj(r) && isObj(r.hostContext) && isObj(r.hostContext.toolInfo) && isObj(r.hostContext.toolInfo.tool)) tool = r.hostContext.toolInfo.tool.name || "";
    notify("ui/notifications/initialized");
    reportSize();
    if (window.ResizeObserver) new ResizeObserver(reportSize).observe(document.body);
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
