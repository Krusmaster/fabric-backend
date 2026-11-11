"""Start Krusgraph (round n219): one guided path through the tools for a customer who has just connected the connector.

Founder, 11 November 2026: customers who connect https://krusgraph.com/mcp in Claude do not know what to type. They say
"start" or "start Krusgraph" (or pick "Start Krusgraph" from the connector's prompts) and are led through the path the
home page shows, step by step: the workspace, the source (a lakehouse, warehouse or mirrored database), the schema
(every schema listed), the map of keys and links with their rules, the check against the rows, the decisions (accept or
reject), the doubled totals, a dry run of what would be built, and creating it only on the user's explicit confirmation.

How it works. `guide()` is the `start` tool's answer, a stepper: where the user is in the path, what was chosen so far,
and the next step as a call of one of the existing tools (tool, arguments, a button label and `say`, the exact sentence a
host that cannot run tools from a card puts in the chat). It reads nothing and calls nothing: every step is the existing
tool, so the result is the one that tool gives when called directly. The flow is stateless: what was chosen (workspace,
source, schema, keys, confirmed, decisions) travels in the arguments, and `after` is the `start` call that shows the
next step with everything carried over.

Honesty on the first run: each step says whether it reads or writes. Steps 1-8 only read (the dry runs create nothing).
Step 9 writes, and only after the dry run (step 8) and a second, explicit confirmation that names the items: `create`
must list exactly names the dry run showed, and `confirm` must be true. Without both, step 9 answers what to confirm and
hands over no call with dry_run=false. No row values: the steps return counts (sample_rows is never part of the path).
A user without Fabric data gets the same path on the synthetic shop (`sample=true`, demo.py: the engine's own output on
fabric_backend/seed.py's shop), which reads and creates nothing in Fabric.

Wording: the home page's replay of Krusgraph's answers (page_templates/home.html, "A replay of Krusgraph's answers") and
the chat demo (static/chat-demo.js) say each step as a short question and a short answer with counts and the tool's
name; the steps below say theirs the same way.

Sources for the prompt (read 11 November 2026): the MCP specification, server/prompts ("Prompts are designed to be
user-controlled ... For example, as slash commands"; prompts/list gives name, title, description, arguments;
prompts/get gives messages), modelcontextprotocol/modelcontextprotocol, docs/specification/2025-11-25/server/prompts.mdx
at commit 0b22bfed6e94c0c7751046d2e845fac954cac8a7; claude.com/docs/connectors/building ("Your server can expose these
to Claude: Tools, prompts, and resources"); code.claude.com/docs/en/mcp, "Use MCP prompts as commands" (Claude Code lists
a prompt as /servername:promptname (MCP)). Unverified: where claude.ai on the web, the desktop app and the mobile app
show a connector's prompts (no Anthropic page that says so could be opened), so the docs say "type start Krusgraph",
which works in every client.
"""
from __future__ import annotations

import json

TOOL = "start"
PROMPT = "start"
PROMPT_TITLE = "Start Krusgraph"
VAGUE = ("start", "start Krusgraph", "help", "what can you do", "check my data")

# (key, title, reads or writes, the tool that runs it)
STEPS = (
    ("workspace", "Choose the workspace", "reads", "list_workspaces"),
    ("source", "Choose the lakehouse, warehouse or mirrored database", "reads", "list_sources"),
    ("schema", "Choose the schema (every schema is listed)", "reads", "plan_backend"),
    ("map", "The map: keys and links, each with its rule", "reads", "plan_backend"),
    ("check", "Check the map against the rows", "reads", "validate_plan"),
    ("decide", "Decide: accept or reject what needs a person", "reads", "review_plan"),
    ("totals", "Doubled totals: where a sum counts twice", "reads", "validate_plan"),
    ("dry_run", "Dry run: what would be built, and the data flow", "reads", "create_pipeline"),
    ("create", "Create, only on your confirmation", "writes", "create_pipeline"),
)
KEYS = tuple(s[0] for s in STEPS)
BY_KEY = {s[0]: s for s in STEPS}

# What the dry run shows and step 9 creates, in the order they are built: (tool, suffix, what it is). The report binds to
# the semantic model, so its dry run can run only once the model exists (create_report finds the model by name).
BUILDS = (
    ("create_pipeline", "pipeline", "silver and gold notebooks and a pipeline that runs them, then the check"),
    ("create_semantic_model", "model", "a Power BI semantic model (Direct Lake) with the links as relationships"),
    ("create_report", "report", "a Power BI report on that model"),
    ("create_backend", "api", "an API for GraphQL"),
    ("create_ontology", "ontology", "a Fabric IQ ontology"),
    ("create_data_agent", "agent", "a Fabric data agent with the plan as instructions"),
)
# The data flow, as data_flow.COLUMNS draws it: bronze -> silver -> gold, the check last; the model, the API, the
# ontology and the data agent read the source tables; the report reads the model.
FLOW = (
    "source tables (bronze) -> silver (one row per key, references checked) -> gold views -> the check, in one pipeline",
    "source tables -> semantic model -> report",
    "source tables -> API for GraphQL",
    "source tables -> ontology",
    "source tables -> data agent",
)
HONEST = ("Steps 1-8 only read: they list, count and draft, and the dry runs create nothing. Only step 9 writes, and only "
          "after the dry run and a second confirmation from you that names each item. The answers are counts and names, "
          "no row values, unless you ask for rows (sample_rows).")


def base_name(source: str | None, schema: str | None) -> str:
    """The stem of the names the dry run proposes: the schema, or the source's name when the schema is dbo."""
    stem = schema if schema and schema.lower() != "dbo" else (source or "krusgraph")
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in str(stem)).strip("_").lower()
    return out or "krusgraph"


def build_names(source: str | None, schema: str | None) -> dict[str, str]:
    """{tool: proposed name}: <stem>_pipeline, <stem>_model, ... (the dry run's own answer says when one is taken)."""
    stem = base_name(source, schema)
    return {tool: f"{stem}_{suffix}" for tool, suffix, _ in BUILDS}


def _shown(args: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())


def _call(label: str, tool: str, arguments: dict, kind: str = "call") -> dict:
    """One button, in the shape of mcp_apps_build.action: {kind, label, who, tool, arguments, say}."""
    say = f"{label}: run {tool} with {_shown(arguments)}." if arguments else f"{label}: run {tool}."
    if kind == "dry_run":
        say = f"{label}: run {tool} as a dry run with {_shown(arguments)}."
    elif kind == "create":
        say = f"{label}: run {tool} with {_shown(arguments)}."
    return {"kind": kind, "label": label, "who": "builder" if kind in ("dry_run", "create") else "onto", "tool": tool,
            "arguments": arguments, "say": say}


def _plan_args(c: dict) -> dict:
    out = {k: c[k] for k in ("workspace", "source", "schema") if c.get(k)}
    for k in ("keys", "confirmed"):
        if c.get(k):
            out[k] = c[k]
    return out


def _start_args(c: dict, step: str) -> dict:
    """The `start` tool's arguments for `step`, with everything chosen so far: workspace, source, schema, and keys,
    confirmed and decisions together in `plan`."""
    if c.get("sample"):
        return {"sample": True, "step": step}
    out = {k: c[k] for k in ("workspace", "source", "schema") if c.get(k)}
    plan = {k: c[k] for k in ("keys", "confirmed", "decisions") if c.get(k)}
    if plan:
        out["plan"] = plan
    out["step"] = step
    return out


def _next_key(key: str) -> str | None:
    i = KEYS.index(key)
    return KEYS[i + 1] if i + 1 < len(KEYS) else None


def current(step: str | None, c: dict) -> str:
    """Which step to show: the one asked for, unless what it needs has not been chosen yet."""
    if c.get("sample"):
        return step if step in KEYS else "map"
    if not c.get("workspace"):
        return "workspace"
    if not c.get("source"):
        return "source"
    if not c.get("schema"):
        return "schema"
    if step in (None, "", "workspace", "source", "schema") or step not in KEYS:
        return "map"
    return step


def _path(now: str) -> list[dict]:
    i = KEYS.index(now)
    return [{"n": n + 1, "key": k, "title": t, "does": d,
             "state": "done" if n < i else ("now" if n == i else "later")} for n, (k, t, d, _) in enumerate(STEPS)]


def guide(workspace: str | None = None, source: str | None = None, schema: str | None = None, step: str | None = None,
          keys: dict | None = None, confirmed: list | None = None, decisions: list | None = None,
          create: list | None = None, confirm: bool = False, sample: bool = False) -> dict:
    """The stepper's answer (see the module docstring). Pure: no Fabric, no SQL."""
    c = {"workspace": (workspace or "").strip() or None, "source": (source or "").strip() or None,
         "schema": (schema or "").strip() or None, "keys": keys or None, "confirmed": confirmed or None,
         "decisions": decisions or None, "sample": bool(sample)}
    if c["sample"]:
        return _sample(step)
    now = current((step or "").strip().lower() or None, c)
    key, title, does, tool = BY_KEY[now]
    n = KEYS.index(now) + 1
    out = {"flow": PROMPT_TITLE, "step": {"n": n, "of": len(STEPS), "key": key, "title": title, "does": does},
           "path": _path(now), "chosen": {k: v for k, v in c.items() if v and k != "sample"}}
    actions: list[dict] = []
    nxt = _next_key(now)

    if now == "workspace":
        out["say"] = "Which workspace? list_workspaces lists the ones your account can open."
        actions.append(_call("List my workspaces", "list_workspaces", {}))
        out["then"] = "When the user names one, call start with workspace set to it."
        actions.append({"kind": "sample", "label": "Show me on the synthetic shop sample", "who": "thinker", "tool": TOOL,
                        "arguments": {"sample": True}, "say": "Show me on the synthetic shop sample: run start with sample=true."})
    elif now == "source":
        out["say"] = f"Which source in {c['workspace']}? list_sources lists its lakehouses, warehouses and mirrored databases."
        actions.append(_call("List the sources", "list_sources", {"workspace": c["workspace"]}))
        out["then"] = "When the user names one, call start with workspace and source set."
    elif now == "schema":
        args = {"workspace": c["workspace"], "source": c["source"]}
        out["say"] = (f"Which schema in {c['source']}? plan_backend without a schema lists every schema that holds tables, "
                      "with its table count, and plans nothing until one is chosen; a source with one schema is planned at once.")
        actions.append(_call("List the schemas", "plan_backend", args))
        out["then"] = ("When the user picks a schema, call start with schema set (and step=\"check\" if plan_backend already "
                       "planned it because the source has one schema).")
    elif now == "map":
        out["say"] = ("How are the tables connected? plan_backend proposes each key and link with the rule that found it "
                      "(K0-K5, R0-R5), and lists the tables without a key and the columns it would not guess.")
        actions.append(_call("Show the map", "plan_backend", _plan_args(c)))
    elif now == "check":
        out["say"] = ("Check the map against the rows: validate_plan counts whether each key is unique and how many "
                      "references find no row. Counts only, no row values.")
        actions.append(_call("Check against the rows", "validate_plan", _plan_args(c)))
    elif now == "decide":
        out["say"] = ("Decide what needs a person: for each proposed link or key the user says accept or reject. "
                      "review_plan records the decisions (item ids are in its file) and lists what needs attention first. "
                      "An accepted link goes into confirmed for the next steps.")
        args = _plan_args(c)
        if c.get("decisions"):
            args["decisions"] = c["decisions"]
        actions.append(_call("Record my decisions", "review_plan", args))
    elif now == "totals":
        out["say"] = ("Where does a total double? validate_plan with fixes=true sums each amount over the joined rows and "
                      "once per row of its own table, and asks at which level it belongs. It proposes; it applies nothing.")
        actions.append(_call("Find doubled totals", "validate_plan", {**_plan_args(c), "fixes": True}))
    elif now == "dry_run":
        names = build_names(c["source"], c["schema"])
        out["say"] = ("What would be built, as dry runs: each answers with what it would create and changes nothing. "
                      "The report's dry run needs the model to exist, so it comes after the model is created.")
        out["would_build"] = [{"tool": t, "name": names[t], "what": w} for t, _, w in BUILDS]
        out["data_flow"] = list(FLOW)
        for t, _, w in BUILDS:
            if t == "create_report":
                continue
            args = {**_plan_args(c), "name": names[t]}
            actions.append(_call(f"Dry run: {w}", t, args, kind="dry_run"))
        out["then"] = ("When the user has read the dry runs, call start with step=\"create\" and create set to the names "
                       "the user wants, e.g. " + json.dumps(sorted(names.values())[:2]) + "; nothing is created before "
                       "the user confirms them.")
    elif now == "create":
        out.update(_create(c, create, confirm))
        actions = out.pop("actions")
    out["actions"] = actions
    if nxt and now != "create":
        out["after"] = {"tool": TOOL, "arguments": _start_args(c, nxt), "label": f"Next: {BY_KEY[nxt][1]}",
                        "say": f"Next step: run start with {_shown(_start_args(c, nxt))}."}
    out["honest"] = HONEST
    out["summary"] = (f"Step {n} of {len(STEPS)}: {title} ({does}). "
                      + ("Run the button's tool, show its answer, then continue with `after`." if actions else ""))
    return out


def _create(c: dict, create: list | None, confirm: bool) -> dict:
    """Step 9: the creating calls with dry_run=false, only for names the dry run showed and only with confirm=true."""
    names = build_names(c["source"], c["schema"])
    by_name = {v: k for k, v in names.items()}
    asked = [str(x) for x in (create or [])]
    unknown = [x for x in asked if x not in by_name]
    if not asked or unknown or not confirm:
        why = ("No item named yet." if not asked else
               f"Not in the dry run: {', '.join(unknown)}." if unknown else "Not confirmed yet.")
        return {"needs_confirmation": True, "would_create": [{"tool": by_name[x], "name": x} for x in asked if x in by_name],
                "say": (f"{why} Nothing is created until the user has seen the dry run (step 8) and confirms by name. "
                        "Ask: \"Create " + ", ".join(asked or sorted(names.values())) + " in " + str(c["workspace"]) +
                        "? Say yes to create exactly these.\" Then call start with step=\"create\", create=[the names] "
                        "and confirm=true."),
                "actions": [_call("Back to the dry run", TOOL, _start_args(c, "dry_run"))]}
    ordered = [t for t, _, _ in BUILDS if names[t] in asked]
    actions = []
    for t in ordered:
        if t == "create_report":                 # no dry run of it could run before the model existed: one now, first
            args = {"workspace": c["workspace"], "model": names["create_semantic_model"], "name": names[t]}
            actions.append(_call(f"Dry run: {names[t]} on {names['create_semantic_model']}, once the model exists",
                                 t, args, kind="dry_run"))
            continue
        args = {**_plan_args(c), "name": names[t], "dry_run": False}
        actions.append(_call(f"Create {names[t]}", t, args, kind="create"))
    return {"confirmed_by_user": [names[t] for t in ordered],
            "say": ("The user confirmed these names after the dry run. Each call below writes to Fabric: run them in this "
                    "order; the host may ask the user again. The report gets its own dry run once the model exists, and is "
                    "created only after the user confirms that dry run too. Nothing is deleted."),
            "actions": actions}


# ------------------------------------------------------------------ the synthetic shop ---------------------------------

def _sample(step: str | None) -> dict:
    """The same path on the synthetic shop (demo.py: the engine's output on seed.py's shop). Nothing in Fabric is read
    or created; each step shows what the tool answered on the shop, and `after` moves on."""
    from . import demo
    p = demo.demo_plan()
    now = (step or "map").strip().lower()
    if now not in KEYS or now in ("workspace", "source", "schema"):
        now = "map"
    key, title, does, tool = BY_KEY[now]
    n = KEYS.index(now) + 1
    d = p["drafts"]["as_is"]
    found: dict = {}
    if now == "map":
        found = {"tool": "plan_backend", "summary": p["summary"].splitlines()[0],
                 "links": [f"{r['source']}.{'+'.join(r['source_cols'])} -> {r['target']} ({r['rule']})" for r in p["relationships"]],
                 "no_key": p["keyless"]}
    elif now == "check":
        found = {"tool": "validate_plan", "summary": d["validation"]["summary"]}
    elif now == "decide":
        s = p["suggestions"][0] if p["suggestions"] else None
        found = {"tool": "review_plan", "question": (f"{s['table']}.{s['column']} is not named after any table, so no "
                                                     f"naming rule linked it. Does it point at {s['target']}? Accept or reject.")
                 if s else "Nothing needs a decision on the shop."}
    elif now == "totals":
        f = [x for x in d["fixes"]["findings"] if x.get("sums")]
        found = {"tool": "validate_plan (fixes=true)",
                 "doubled": [f"{x['table']}.{x['column']} summed over the joined {x['joined_with']} rows: "
                             f"{x['sums']['summed_over_lines']}; once per {x['table']} row: {x['sums']['summed_per_header']}"
                             for x in f]}
    elif now == "dry_run":
        names = build_names("shop", "shop")
        found = {"would_build": [{"tool": t, "name": names[t], "what": w} for t, _, w in BUILDS], "data_flow": list(FLOW)}
    elif now == "create":
        found = {"note": "This is the synthetic shop: nothing can be created here. Connect your own workspace and type "
                         "\"start Krusgraph\" to run the same path on your data."}
    nxt = _next_key(now)
    out = {"flow": PROMPT_TITLE, "sample": True, "step": {"n": n, "of": len(STEPS), "key": key, "title": title, "does": does},
           "path": _path(now), "found": found,
           "note": "Synthetic shop sample (fabric_backend/seed.py): no Fabric is read and nothing is created.",
           "actions": [], "honest": HONEST}
    if nxt:
        args = {"sample": True, "step": nxt}
        out["after"] = {"tool": TOOL, "arguments": args, "label": f"Next: {BY_KEY[nxt][1]}",
                        "say": f"Next step: run start with {_shown(args)}."}
        out["actions"].append({"kind": "call", "label": f"Next: {BY_KEY[nxt][1]}", "who": "onto", "tool": TOOL,
                               "arguments": args, "say": out["after"]["say"]})
    out["summary"] = f"Step {n} of {len(STEPS)} on the synthetic shop: {title}."
    return out


def prompt_text(sample: bool = False) -> str:
    """The `start` prompt's user message (prompts/get)."""
    if sample:
        return ("Start Krusgraph on the synthetic shop sample: call the start tool with sample=true and lead me through "
                "each step, one at a time.")
    return ("Start Krusgraph: call the start tool and lead me through it one step at a time: my workspace, the source, "
            "the schema, the map of keys and links with their rules, the check against the rows, my decisions, doubled "
            "totals and a dry run of what would be built. Create nothing unless I confirm the names after the dry run.")
