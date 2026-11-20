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
# n177: dbt_schema's project drawn as its flow (dbt_flow.py), with the chat demo's renderer (chat-demo.js, dbt-flow block)
FLOW_CARD_TOOLS = ("dbt_schema",)
# RQ1: requirements_draft's answer: its own words (kg_card) and its next steps, on the build card
REQUIREMENT_CARD_TOOLS = ("requirements_draft",)
# The tools whose answer gets `actions` (validate_plan's card draws them under its own next steps; n170: domain_draft's
# per data product).
ACTION_TOOLS = CARD_TOOLS + ("validate_plan", "domain_draft")
BUILD_TOOLS = ("create_semantic_model", "create_ontology", "create_backend", "create_report")
# What a button may ask for: the read tools by name, the creating tools only as a dry run or as Create after one.
ALLOWED = {"validate_plan": "call", "plan_backend": "call", "verify_build": "call",       # n229: verify_build only reads
           **{t: "build" for t in BUILD_TOOLS}}
SUFFIX = {"create_semantic_model": "model", "create_ontology": "ontology", "create_backend": "api"}
LABEL = {"create_semantic_model": "Build a semantic model", "create_ontology": "Create an ontology",
         "create_backend": "Create an API for GraphQL", "create_report": "Create a report on it"}
FABRIC_APP = "https://app.fabric.microsoft.com"
# n227: the item itself in the Fabric portal, per kind: /groups/{workspace}/<path>/{item}. Where each form comes from:
# - ontologies: Microsoft Learn, "Use Ontology MCP Server (Preview)" (fabric/iq/ontology/how-to-use-ontology-mcp-server,
#   ms.date 14 April 2026, read 15 November 2026): "View the URL in the browser, in the format
#   https://app.fabric.microsoft.com/groups/<workspace-ID>/ontologies/<ontology-item-ID>".
# - lakehouses (the pattern, for reference): Learn, "Workspace outbound access protection for data engineering
#   workloads": the workspace id follows /groups/, the item id follows /lakehouses/ (read 15 November 2026).
# - reports and datasets: the Power BI paths this module has used since n169 (/reports/{id}, /datasets/{id}/details).
# - graphql: Unverified on Learn. No Learn page found on 15 November 2026 shows the portal address of an API for
#   GraphQL; `graphql` is the segment the portal's own address bar is expected to show, by the pattern above. Until the
#   founder has opened one from a card, the link carries `fallback` (the workspace's item list), and the card offers it
#   beside the item link.
ITEM_PATHS = {"create_report": "reports/{id}", "create_semantic_model": "datasets/{id}/details",
              "create_ontology": "ontologies/{id}", "create_backend": "graphql/{id}"}
LINK_UNVERIFIED = ("create_backend",)
KIND_WORDS = {"create_semantic_model": "semantic model", "create_ontology": "ontology", "create_backend": "API for GraphQL",
              "create_report": "report"}
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


def list_url(workspace_id: str) -> str:
    """The workspace's item list in the Fabric portal."""
    return f"{FABRIC_APP}/groups/{workspace_id}/list"


def open_url(workspace_id: str, tool: str, item_id: str) -> str:
    """The item itself in the Fabric portal, for every kind a card creates (ITEM_PATHS, n227: before, an API for
    GraphQL and an ontology opened the workspace's item list). A kind without a known path opens the list."""
    path = ITEM_PATHS.get(tool)
    if not path or not item_id:
        return list_url(workspace_id)
    return f"{FABRIC_APP}/groups/{workspace_id}/{path.format(id=item_id)}"


# ------------------------------------------------------------------ actions -------------------------------------------

def _shown(args: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())


def action(kind: str, label: str, who: str, tool: str | None = None, arguments: dict | None = None,
           name: str | None = None, url: str | None = None, product: str | None = None, why: str | None = None,
           say: str | None = None, secondary: bool = False) -> dict:
    """One button: {kind, label, who, tool, arguments, name, say}. `say` is the exact prompt the card sends to the chat
    when the host does not run tools from the card, and what a text client reads as the next step. n229: `why` is the
    mascot's one sentence under the button; kind "say" only sends its sentence to the chat (it runs no tool from the
    card); kind "done" is no button, a line saying the step is already built; `secondary` draws a Create as an ordinary
    button, after the step that should come first (after_create's gate)."""
    out = {"kind": kind, "label": label, "who": who}
    if why:
        out["why"] = why
    if secondary:
        out["secondary"] = True
    if kind in ("say", "done"):
        if name:
            out["name"] = name
        out["say"] = str(say or (f"{label}: already built" + (f" ({name})" if name else "") + "."))[:2000]
        return out
    if tool:
        out["tool"], out["arguments"] = tool, dict(arguments or {})
    if name:
        out["name"] = name
    if product:
        out["product"] = product                                     # n170: drawn on that data product's card
    # n227: `ask` is the step in plain words: what the card shows and sends to the chat. `say` keeps the tool and its
    # arguments for text clients.
    if kind == "link":
        out["url"] = url
        out["say"] = f"Open it in Fabric: {url}"
        out["ask"] = out["say"]
    elif kind == "create":
        out["say"] = (f"Create it ({tool} with dry_run=false and the same arguments as the dry run: "
                      f"{_shown(out['arguments'])}).")
        out["ask"] = f"Create {name or 'it'} in Fabric, exactly as in the dry run."
    elif kind == "dry_run":
        out["say"] = f"{label}{' named ' + name if name else ''} ({tool} as a dry run with {_shown(out['arguments'])})."
        out["ask"] = f"{label}{' named ' + name if name else ''}, as a dry run first."
    elif kind == "status":
        out["say"] = f"{label} ({tool} with {_shown(out['arguments'])}; it only reads)."
        out["ask"] = f"Check whether {name or 'it'} is in Fabric now, without creating anything."
    else:
        where = (arguments or {}).get("schema") or (arguments or {}).get("source")
        out["say"] = f"{label} ({tool} with {_shown(out['arguments'])})."
        out["ask"] = f"{label}{' for ' + str(where) if where else ''}."
    return out


def name_why(base: str, name: str, taken) -> str | None:
    """n227: why a suggested name ends in _2, _3 ...: the names before it are taken in this workspace. None for the
    base name itself."""
    if name == base:
        return None
    low = {str(t).lower() for t in taken or ()}
    before = [base] + [f"{base}_{i}" for i in range(2, MAX_TRIES + 2)]
    used = [b for b in before[:before.index(name)] if b.lower() in low] if name in before else []
    if not used:
        return None
    shown = used[0] if len(used) == 1 else f"{used[0]} and {used[1]}" if len(used) == 2 else f"{used[0]} to {used[-1]}"
    return (f"Named {name} because {shown} {'is' if len(used) == 1 else 'are'} already in this workspace; nothing that "
            "exists is changed.")


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
        why = name_why(f"{base}_{SUFFIX[tool]}", name, taken)
        taken = set(taken) | {name}
        a = action("dry_run", LABEL[tool], "builder", tool, {**common, "name": name, "dry_run": True}, name=name)
        if why:
            a["name_why"] = why
        out.append(a)
    return out


def check_state(answer: dict) -> dict:
    """n227: what validate_plan's answer says about building: {keys_failed, links_failed, checked}."""
    t = answer.get("totals") if isinstance(answer.get("totals"), dict) else {}
    k = t.get("keys") if isinstance(t.get("keys"), dict) else {}
    r = t.get("relationships") if isinstance(t.get("relationships"), dict) else {}
    return {"keys_failed": int(k.get("failed") or 0), "links_failed": int(r.get("failed") or 0),
            "checked": int(k.get("checked") or 0) + int(r.get("checked") or 0)}


# n227 (12): Krusgraph's own output schemas are not sources to plan: the quarantine tables always, and the silver and
# gold layers a build wrote, when the source also has a schema that is none of these.
OWN_SCHEMAS = ("krusgraph_quarantine",)
BUILT_SCHEMAS = ("silver", "gold", "krusgraph")


def plannable(schemas: list) -> list:
    """The schemas a card offers to plan: never krusgraph_quarantine; not silver, gold or krusgraph (what a build
    writes) when another schema is left. The answer's own `schemas` list is unchanged."""
    rows = [x for x in schemas if isinstance(x, dict) and x.get("schema") and str(x["schema"]).lower() not in OWN_SCHEMAS]
    source = [x for x in rows if str(x["schema"]).lower() not in BUILT_SCHEMAS]
    return source or rows


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
    if not isinstance(answer, dict) or (answer.get("error") and not isinstance(answer.get("started"), dict)):
        return [], None
    unreadable = ("The workspace's item names could not be read, so no name is suggested and nothing can be created "
                  "from the card; ask in the chat.")
    if tool == "plan_backend" and isinstance(answer.get("schemas"), list) and answer.get("choose_schema"):
        from .mcp_apps_words import _plural
        return [action("call", f"Plan {s['schema']} ({_plural(int(s.get('tables') or 0), 'table')})", "thinker", "plan_backend",
                       {**args, "schema": s["schema"]}) for s in plannable(answer["schemas"])], None
    if tool == "plan_backend":
        # n227 (5): before the check, one primary step: Check against the rows. The builds come after the check.
        schema = answer.get("schema_chosen") or args.get("schema")
        out = []
        if _count_failed(answer):                                      # n172: a counting query could not run
            out.append(action("call", "Count again", "thinker", "plan_backend", dict(args)))
        check = action("call", "Check against the rows", "thinker", "validate_plan",
                       {**_carried(args, "workspace", "source"), **({"schema": schema} if schema else {}),
                        **_carried(args, "keys", "confirmed")})
        check["primary"] = True
        out.append(check)
        return out, "The builds (a semantic model, an ontology, an API) are offered after the check against the rows."
    if tool == "validate_plan":
        schema = answer.get("schema_chosen") or args.get("schema")
        st = check_state(answer)
        if st["keys_failed"]:                                          # a key that does not hold: nothing is built on it from here
            from .mcp_apps_words import _plural
            return [], (f"{_plural(st['keys_failed'], 'key does', 'keys do')} not hold in the rows, so no build is offered "
                        "here: a model or an API on a key that repeats gives wrong numbers. Look at what failed first; "
                        "you can still ask for a build in the chat.")
        if taken is None:
            return [], unreadable
        note = None
        if st["links_failed"]:
            from .mcp_apps_words import _plural
            note = (f"The keys hold. {_plural(st['links_failed'], 'link has', 'links have')} rows that point at nothing; a "
                    "build keeps the plan as it is, so look at them first if they matter to you.")
        return _builds(args, schema, taken), note
    if tool == "domain_draft":
        return _product_builds(args, answer, taken)
    if tool in BUILD_TOOLS and answer.get("dry_run") is True:
        if taken is None:
            return [], unreadable
        name = args.get("name")
        if name and str(name).lower() in {str(t).lower() for t in taken}:
            from .report import next_free_name                       # n220: the next free name, checked, as a dry run
            try:
                alt = next_free_name(str(name), taken)
            except ValueError:
                alt = None
            note = (f"An item named {name!r} already exists in the workspace. Create is not offered on the card, so "
                    "nothing is overwritten from here; " + (f"use {alt} (free when checked just now), " if alt else "")
                    + "choose another name, or ask in the chat to update it.")
            if not alt:
                return [], note
            return [action("dry_run", f"Use {alt}", "builder", tool, {**args, "name": alt, "dry_run": True}, name=alt)], note
        gate = answer.get("gate") if isinstance(answer.get("gate"), dict) else None
        if gate and isinstance(gate.get("first"), dict) and gate.get("said"):    # n229: the fix first, Create second
            first = _step_action(gate["first"], args)
            create = action("create", str(gate.get("create") or "Create anyway"), "builder", tool, {**args, "dry_run": False}, name=name,
                            why="It can be created as it is, and it would be of little use until the step above is done.", secondary=True)
            return ([first] if first else []) + [create], str(gate["said"])
        return [action("create", "Create", "builder", tool, {**args, "dry_run": False}, name=name)], None
    if tool in BUILD_TOOLS and isinstance(answer.get("started"), dict):
        # n227 (9): Fabric is still working. One step: Check status, which only reads; never a second Create.
        st = answer["started"]
        check_args = {k: v for k, v in args.items() if k not in ("dry_run", "check")}
        check_args["check"] = str(st.get("operation") or "name")
        return [action("status", "Check status", "builder", tool, check_args, name=args.get("name"))], None
    if tool in BUILD_TOOLS and (answer.get("dry_run") is False or answer.get("checked")):
        result = answer.get("result") if isinstance(answer.get("result"), dict) else {}
        if result.get("status") != "Succeeded" or not result.get("id") or not workspace_id:
            return [], None
        link = action("link", "Open in Fabric", "builder", url=open_url(workspace_id, tool, result["id"]),
                      name=args.get("name"))
        link["label"] = f"Open {args['name']} in Fabric" if args.get("name") else "Open in Fabric"
        if tool in LINK_UNVERIFIED:                                    # the item's address is not confirmed on Learn
            link["fallback"] = list_url(workspace_id)
        out = [link]
        if isinstance(answer.get("next_steps"), list):                # n229: the data product's next steps, as buttons
            return out + lifecycle_actions(answer, args), None
        if tool == "create_semantic_model" and taken is not None:
            model = args.get("name")
            name = free_name(f"{model}_report", set(taken) | {model})
            out.append(action("dry_run", LABEL["create_report"], "builder", "create_report",
                              {**_carried(args, "workspace"), "model": model, "name": name, "dry_run": True}, name=name))
        return out, None
    return [], None


def _step_action(s: dict, call: dict) -> dict | None:
    """n229: one of the answer's own next steps ({label, who, why, tool, args, ask}, after_create.py) as a button: the
    read-only verify_build as a call, a creating tool only as a dry run, anything else as its sentence for the chat."""
    if not isinstance(s, dict) or not isinstance(s.get("label"), str) or not s["label"].strip() or s.get("state"):
        return None
    who = s.get("who") if s.get("who") in ("builder", "thinker", "onto") else "builder"
    t, a = s.get("tool"), s.get("args") if isinstance(s.get("args"), dict) else None
    if t and a is not None and ALLOWED.get(t) == "call":
        out = action("call", s["label"], who, t, a, why=s.get("why"))
        if isinstance(s.get("ask"), str) and s["ask"].strip():
            out["say"] = s["ask"][:2000]
        return out
    if t and a is not None and ALLOWED.get(t) == "build":
        return action("dry_run", s["label"], who, t, {**a, "dry_run": True}, name=a.get("name"), why=s.get("why"))
    if isinstance(s.get("ask"), str) and s["ask"].strip():
        return action("say", s["label"], who, why=s.get("why"), say=s["ask"])
    return None


def lifecycle_actions(answer: dict, call: dict) -> list[dict]:
    """n229: after a Create that succeeded, the answer's next_steps as buttons in their order, then what is already
    built (no button: a line), then More (the dbt project, labelled a draft)."""
    out = [a for a in (_step_action(s, call) for s in answer.get("next_steps") or []) if a]
    for d in answer.get("already_built") or []:
        if isinstance(d, dict) and isinstance(d.get("label"), str):
            out.append(action("done", d["label"], "builder", name=d.get("name")))
    for m in answer.get("more") or []:
        a = _step_action({**m, "label": "More: " + str(m.get("label")) + (" (a draft)" if m.get("draft") else "")}, call) if isinstance(m, dict) else None
        if a:
            out.append(a)
    return out


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
        if not isinstance(data, dict) or (data.get("error") and not isinstance(data.get("started"), dict)):
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
        was_check = bool(call.pop("check", None))                    # n227: a status check: its answer is drawn as the create's
        if "workspace" not in call:
            return out
        made = name in BUILD_TOOLS and (data.get("dry_run") is False or (was_check and data.get("checked")))
        needs_names = name != "plan_backend" and not isinstance(data.get("started"), dict) and not (
            made and name != "create_semantic_model") and not (
            name == "validate_plan" and check_state(data)["keys_failed"])
        taken = None
        if needs_names:
            try:
                taken = set(item_names(call["workspace"], ctx))
            except Exception:                                        # noqa: BLE001 - the answer stands; no name offered
                taken = None
        ws_id = None
        if made:
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
  var ACT_ALLOWED = __ACT_ALLOWED__, WHO = { builder: "Builder", thinker: "Thinker", onto: "Onto" };
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
    if (a.kind === "say" || a.kind === "done") return typeof a.say === "string" && a.say.length > 0 && a.tool === undefined;   // n229
    if (!Object.prototype.hasOwnProperty.call(ACT_ALLOWED, a.tool) || !isObj(a.arguments)) return false;
    if (a.kind === "call") return ACT_ALLOWED[a.tool] === "call";
    if (a.kind === "dry_run") return ACT_ALLOWED[a.tool] === "build" && a.arguments.dry_run === true;
    if (a.kind === "create") return ACT_ALLOWED[a.tool] === "build" && a.arguments.dry_run === false && fromDryRun === true;
    // n227: Check status only reads: `check` is set (the tool then creates nothing) and dry_run is never false
    if (a.kind === "status") return ACT_ALLOWED[a.tool] === "build" && typeof a.arguments.check === "string" && !!a.arguments.check && a.arguments.dry_run !== false;
    return false;
  }
  function sendMessage(text) { return sendChat(text); }            // n218: NEXT_JS, the SDK's array form first
  function viaChat(a, out, button) {
    var text = readable(a.ask) || a.say;                             // n227: plain words, no tool's name
    out.textContent = "Sent to the chat: “" + text + "”";
    sendMessage(text).then(function () { button.disabled = true; }, function () {
      out.textContent = "This host runs no steps from the card. Type this in the chat: “" + text + "”";
      button.disabled = false;
    });
  }
  // n227 (9): after a Create whose outcome the card does not know (the host stopped waiting, or Fabric is still
  // working), the only step is Check status: the same tool with `check` set, which reads and creates nothing.
  function statusAction(a, args, check) {
    var sa = JSON.parse(JSON.stringify(args)); delete sa.dry_run; sa.check = check || "name";
    return { kind: "status", label: "Check status", who: "builder", tool: a.tool, arguments: sa, name: a.name,
             say: "Check whether " + (a.name || "it") + " is in Fabric now, without creating anything.",
             ask: "Check whether " + (a.name || "it") + " is in Fabric now, without creating anything." };
  }
  function statusButton(a, args, check, box) {
    var sa = statusAction(a, args, check), row = el("div", null, "act");
    var b = el("button", "Check status", "act-b"), out = el("div", null, "out"); b.type = "button"; out.hidden = true;
    b.setAttribute("data-kind", "status");
    b.addEventListener("click", function () { runAction(sa, b, out, sa.arguments); });
    row.appendChild(b); row.appendChild(out); box.appendChild(row);
  }
  function linkView(a, out) {
    out.hidden = false; out.textContent = "";
    var show = function (u, lead) { out.appendChild(el("p", lead + u)); };
    if (!canOpenLinks()) { show(a.url, "Open this address: "); }
    else request("ui/open-link", { url: a.url }).then(function () { out.insertBefore(el("p", "Opened in your browser."), out.firstChild); },
        function () { out.insertBefore(el("p", "The host did not open it. The address: " + a.url), out.firstChild); });
    if (typeof a.fallback === "string" && /^https:\/\/app\.fabric\.microsoft\.com\//.test(a.fallback)) {
      var p = el("p", "If the item does not open there, it is in ", "muted"), lb = el("button", "the workspace's list", "act-b"); lb.type = "button";
      lb.addEventListener("click", function () {
        if (!canOpenLinks()) { p.textContent = "The workspace's list: " + a.fallback; return; }
        request("ui/open-link", { url: a.fallback }).then(function () {}, function () { p.textContent = "The workspace's list: " + a.fallback; });
      });
      p.appendChild(lb); out.appendChild(p);
    }
  }
  function runAction(a, button, out, dryArgs) {
    out.hidden = false; out.textContent = "";
    if (a.kind === "link") { linkView(a, out); return; }
    if (a.kind === "say") { viaChat(a, out, button); return; }       // n229: a sentence for the chat; the card runs nothing
    var args = a.kind === "create" ? JSON.parse(JSON.stringify(dryArgs)) : JSON.parse(JSON.stringify(a.arguments));
    if (a.kind === "create") args.dry_run = false;
    button.disabled = true;
    if (!canCallTools()) { viaChat(a, out, button); return; }
    var wait = waitView(a);                                           // n227 (11): who is working, on what, for how long
    out.appendChild(wait.el);
    callTool(a.tool, args, function () { wait.note(stillWaiting()); }).then(function (r) {
      wait.stop(); out.textContent = "";
      var d = answerOf(r);
      if (isObj(d) && d.kind === "upgrade") { upgradeView(d, out); button.disabled = false; return; }   // n171
      out.appendChild(resultView(a.tool, r));
      if (isObj(d) && isObj(d.checks)) renderChecks(d, out);       // n229: verify_build's lines, one row per item and figure
      if (d) renderActions(d, out, args);
      if (a.kind !== "create") button.disabled = false;
    }, function (e) {
      wait.stop();
      if (e && e.kind === "unsupported") { viaChat(a, out, button); return; }
      if (a.kind === "create" && !(e && e.kind === "tool")) {
        // The host stopped waiting or did not answer: the request may have reached Fabric. Create stays off; the
        // user checks instead, so the same item is never created or updated a second time from this card.
        out.textContent = "";
        var why = e && typeof e.message === "string" && e.message.trim() ? " (" + e.message.trim().slice(0, 120).replace(/[.\s]+$/, "") + ")" : "";
        out.appendChild(el("p", "The host stopped waiting" + why + ". Fabric may still be creating " + (a.name || "it") + ", so Create is not offered again here. Check its status instead; that only reads.", "warn"));
        statusButton(a, args, "name", out);
        return;
      }
      out.textContent = callProblem(e, a.tool, readable(a.ask) || a.say);
      button.disabled = false;                                        // the tool answered an error: nothing was created
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
      if (a.kind === "done") {                                     // n229: already built: a line, never a button
        if (!groups.done) { groups.done = el("div", null, "acts acts-done"); groups.done.appendChild(el("p", "Already built", "act-who")); box.appendChild(groups.done); }
        groups.done.appendChild(el("p", a.label + ": already built" + (a.name ? " (" + a.name + ")" : "") + ".", "muted act-done"));
        return;
      }
      // n229: the next steps after a Create, and a gate's fix before Create, keep their order: one group, not one per
      // mascot (each step's own sentence names who says it)
      var ordered = Array.isArray(d.next_steps) && d.dry_run === false ? "Next steps, in order" : (isObj(d.gate) ? "First this, then Create" : "");
      var gk = ordered ? "ordered" : who;
      if (!groups[gk]) {
        groups[gk] = el("div", null, "acts acts-" + gk);
        groups[gk].appendChild(el("p", ordered || (WHO[who] + (who === "thinker" ? " asks" : " suggests")), "act-who"));
        box.appendChild(groups[gk]);
      }
      var row = el("div", null, "act");
      var label = a.label + (a.name && a.kind === "dry_run" ? " (" + a.name + ")" : "");
      var b = el("button", label, a.kind === "create" && a.secondary !== true ? "act-create" : (a.primary === true ? "act-b act-primary" : "act-b")); b.type = "button";
      b.setAttribute("data-kind", a.kind);
      if (readable(a.why)) row.appendChild(el("span", WHO[who] + ": " + a.why, "act-reason"));   // n229: the mascot's one sentence
      if (a.kind === "say") row.appendChild(el("span", "Asks in the chat; nothing runs from this card.", "muted act-why"));
      if (a.kind === "dry_run") row.appendChild(el("span", "Dry run first: nothing is created until you press Create.", "muted act-why"));
      if (a.kind === "dry_run" && readable(a.name_why)) row.appendChild(el("span", a.name_why, "muted act-why act-name-why"));   // n227: why _3
      if (a.kind === "status") row.appendChild(el("span", "Only reads: looks whether " + (a.name ? a.name : "it") + " is in Fabric now. Nothing is created again.", "muted act-why"));
      if (a.kind === "create") row.appendChild(el("span", "Creates " + (a.name ? a.name : "it") + " in Fabric with exactly the dry run's arguments.", "muted act-why"));
      var out = el("div", null, "out"); out.hidden = true;
      if (a.kind === "create") {                                   // n218: never writes on the first click
        var armed = false;
        b.addEventListener("click", function () {
          if (!armed) {
            armed = true; b.textContent = "Yes, create " + (a.name ? a.name : "it") + " in Fabric";
            b.setAttribute("data-armed", "true");
            out.hidden = false; out.textContent = "Press again to create " + (a.name ? a.name : "it") + ". Nothing has been created yet.";
            return;
          }
          runAction(a, b, out, callArgs || a.arguments);
        });
      } else b.addEventListener("click", function () { runAction(a, b, out, callArgs || a.arguments); });
      row.insertBefore(b, row.firstChild); row.appendChild(out); groups[gk].appendChild(row);
    });
  }
"""

ACTIONS_CSS = """
.acts { display: grid; gap: 6px; border-top: 1px solid var(--kg-line); padding-top: 8px; margin-top: 4px }
.act-who { margin: 0; font-size: 13px; font-weight: 650; color: var(--kg-muted) }
.act { display: grid; gap: 4px }
.act-why { font-size: 12.5px }
.act .out { border-left: 3px solid var(--kg-line); padding-left: 8px; display: grid; gap: 6px }
button.act-create, button.act-primary { background: var(--kg-ink); color: var(--kg-bg) }
.act-reason { font-size: 13.5px }
.act-done { margin: 0 }
"""


def actions_js() -> str:
    return ACTIONS_JS.replace("__ACT_ALLOWED__", json.dumps(ALLOWED, separators=(",", ":")))


def dbt_flow_js() -> str:
    """n177: the dbt flow's renderer, the block between the dbt-flow markers of static/chat-demo.js: one copy for the
    chat demo and the card."""
    from .pages import STATIC_DIR
    text = (STATIC_DIR / "chat-demo.js").read_text(encoding="utf-8")
    a, b = text.index("/* dbt-flow:start"), text.index("/* dbt-flow:end */")
    return "  " + text[a:b] + "/* dbt-flow:end */\n"


def card_html() -> str:
    """The build card: one self-contained HTML5 document, no external load. It draws the answer of a tool in CARD_TOOLS
    (resultView's summary, a dry run's checks, a schema choice) and its actions; since n170 also the pictures
    (mcp_apps_pictures): the map, the ontology proposal and the data products."""
    from . import mcp_apps_pictures as pictures
    pic = pictures.html_parts()
    from . import mcp_apps_next as nxt                       # n218: next steps as buttons
    from .mcp_apps_size import SIZE_JS                   # WB13 (#89)
    return (_HTML.replace("__SIZE_JS__", SIZE_JS).replace("__PROTOCOL__", mcp_apps.PROTOCOL_VERSION)
            .replace("__PICTURES__", pic["section"])
            .replace("__READ_JS__", mcp_apps.READ_JS + mcp_apps.CALL_JS + mcp_apps.RESULT_JS + nxt.js() + actions_js() + pic["js"] + dbt_flow_js())
            .replace("__MASCOT_CSS__", mascots.CSS).replace("__RESULT_CSS__", mcp_apps.RESULT_CSS + nxt.NEXT_CSS + ACTIONS_CSS + pic["css"])
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
  <div id="next"></div>
  __MASCOTS__
  <div id="answer"></div>
  __PICTURES__
  <p class="muted">The same answer is in the text of the tool result. A button asks the host to run that step, and the host may ask you first; a build always shows its dry run before Create.</p>
</main>
<script>
(function () {
  "use strict";
  var TITLES = { plan_backend: "Plan", create_semantic_model: "Semantic model", create_ontology: "Ontology",
                 create_backend: "API for GraphQL", create_report: "Report", ontology_draft: "Ontology proposal",
                 domain_draft: "Data products", dbt_schema: "dbt project" };
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
    if (isObj(d.dbt_flow) || (isObj(d.files) && isObj(d.models) && "adapter" in d)) return "dbt_schema";
    if (Array.isArray(d.domains) && "interfaces" in d) return "domain_draft";
    if (Array.isArray(d.bindings) && isObj(d.summary) && "entity_types" in d.summary) return "ontology_draft";
    if (d.choose_schema || "relationships" in d || "keys" in d) return "plan_backend";
    if (isObj(d.report)) return "create_report";
    if ("would" in d || "checks_passed" in d) return "create_backend";
    if (isObj(d.summary) && "entity_types" in d.summary) return "create_ontology";
    if (isObj(d.summary) && "relationships_active" in d.summary) return "create_semantic_model";
    return "";
  }
  function detailsOf(d) {                                   // the whole answer, folded: readable lines first, raw JSON last
    var box = el("div", null, "res-box");
    box.appendChild(detailsView(tool || guessTool(d), d, ""));
    return box;
  }
  function firstLine(s) { return readable(s) ? String(s).split("\\n")[0] : ""; }
  function render(result) {
    var d = answerOf(result), verdict = document.getElementById("verdict");
    var answer = document.getElementById("answer"), next = document.getElementById("next");
    answer.textContent = ""; next.textContent = ""; mascotsQuiet();
    if (!d) { verdict.textContent = "The card could not read the answer; it is in the text of the tool result."; return; }
    if (readable(d.error) && !isObj(d.started)) { verdict.textContent = d.error + (readable(d.hint) ? " " + d.hint : ""); mascots({ thinker: [d.error, "think"] }, false);
      renderNext(d, next); return; }                                // n220: an error ends with 1 to 3 next steps
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
    } else if (readable(words.result) && !(t === "dbt_schema" && isObj(d.dbt_flow))) {
      // n227: the card's words first, for a draft, a dry run, a created item and a create Fabric is still working on:
      // the one-line result (Onto says it once), up to five lines, the notes collapsed, then the details.
      verdict.textContent = words.result;
      onto = readable(words.onto) || words.result;
      verdict.setAttribute("data-echo", "onto"); verdict.setAttribute("data-said", onto);
      answer.appendChild(resultView(t, { structuredContent: d }, true));
      if (isObj(d.replaces) && readable(d.replaces.said)) answer.appendChild(el("p", d.replaces.said, "warn"));
    } else if (d.dry_run === true) {
      verdict.textContent = isObj(d.gate) && readable(d.gate.said)   // n229: a build of little use is said first
        ? "Dry run: nothing was created. " + d.gate.said + " Do the step below first; Create anyway stays possible."
        : "Dry run: nothing was created. Read it, then press Create to create it with exactly these arguments.";
      answer.appendChild(resultView(t, { structuredContent: d }));
      if (Array.isArray(d.checks_passed)) { var ul = el("ul"); d.checks_passed.forEach(function (c) { if (readable(c)) ul.appendChild(el("li", c)); }); answer.appendChild(ul); }
      if (isObj(d.replaces) && readable(d.replaces.said)) answer.appendChild(el("p", d.replaces.said, "warn"));
    } else if (d.dry_run === false) {
      var st = isObj(d.result) ? d.result.status : "";
      verdict.textContent = st === "Succeeded" ? "Created in Fabric." : "Fabric answered: " + (st || "no status") + ".";
      answer.appendChild(resultView(t, { structuredContent: d }));
    } else if (t === "dbt_schema" && isObj(d.dbt_flow)) {          // n177: the project's flow, boxes folded
      var nf = isObj(d.files) ? Object.keys(d.files).length : 0;
      verdict.textContent = "A draft: " + nf + (nf === 1 ? " file" : " files") + "; nothing was created or run. Choose a box to see its SQL or YAML.";
      KGF.wire(document);
      var fl = KGF.build(document, d.dbt_flow, isObj(d.files) ? d.files : {});
      if (fl) answer.appendChild(fl);
      answer.appendChild(detailsOf(d));
      onto = verdict.textContent;
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
    renderNext(d, next);                                            // n218: 2 to 4 next steps, each naming its tool
    var acts = (Array.isArray(d.actions) ? d.actions : []).filter(isObj);   // each mascot says its first step, word for word
    // n229: a step with a reason of its own is said by its reason, never by the sentence with the arguments (n172)
    var mine = function (who) { var a = acts.filter(function (x) { return x.who === who && x.kind !== "done"; })[0]; return a ? (readable(a.why) || readable(a.say)) : ""; };
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

__SIZE_JS__
  request("ui/initialize", {
    appInfo: { name: "Krusgraph plan and build", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function (r) {
    hostStarted(r);
    if (isObj(r) && isObj(r.hostContext) && isObj(r.hostContext.toolInfo) && isObj(r.hostContext.toolInfo.tool)) tool = r.hostContext.toolInfo.tool.name || "";
    notify("ui/notifications/initialized");
    watchSize();
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
