"""Start Krusgraph (round n219): one guided path through the tools for a customer who has just connected the connector.

Founder, 11 November 2026: customers who connect https://krusgraph.com/mcp in Claude do not know what to type. They say
"start" or "start Krusgraph" (or pick "Start Krusgraph" from the connector's prompts) and are led through the path the
home page shows, step by step: the workspace, the source (a lakehouse, warehouse or mirrored database), the schema
(every schema listed), the map of keys and links with their rules, the check against the rows, the decisions (accept or
reject), the doubled totals, a dry run of what would be built, and creating it only on the user's explicit confirmation.

How it works. `guide()` is the `start` tool's answer, a stepper: where the user is in the path, what was chosen so far,
and the next step as a call of one of the existing tools (tool, arguments, a button label and `say`, the exact sentence a
host that cannot run tools from a card puts in the chat). It calls no other tool and reads no rows (since WB12 the start
tool reads the names to choose from on steps 1-3: workspaces, sources, schemas with table counts): every step is the existing
tool, so the result is the one that tool gives when called directly. The flow is stateless: what was chosen (workspace,
source, schema, keys, confirmed, decisions) travels in the arguments, and `after` is the `start` call that shows the
next step with everything carried over.

Honesty on the first run: each step says whether it reads or writes. Steps 1-4 only read (the dry runs create nothing).
Step 5 writes, and only after the dry run (step 4) and a second, explicit confirmation that names the items: `create`
must list exactly names the dry run showed, and `confirm` must be true. Without both, step 5 answers what to confirm and
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
VAGUE = ("start", "start Krusgraph", "help", "what can you do", "check my data",
         "help me with my SAP data in Fabric")                  # CO1: a plain sentence starts the path too

# (key, title, reads or writes, the tool that runs it)
# SM2 (docs/SMOOTH/PLAN.md, row 1): five steps instead of nine. Steps 1-3 of before (workspace, source, schema) are one
# step, "Your data", that collapses into one line when each has one usable option; the map, the row check and the
# doubled totals run on their own in one step, "Check"; the three dry runs are one button.
STEPS = (
    ("data", "Your data: the workspace, the source and the schema", "reads", "list_sources"),
    ("check", "Check: the map, the rows and the totals, counted for you", "reads", "review_plan"),
    ("decide", "Decide: accept or reject what needs a person", "reads", "review_plan"),
    ("dry_run", "Dry run: what would be built; nothing is created", "reads", "create_pipeline"),
    ("create", "Create, only on your confirmation", "writes", "create_pipeline"),
)
KEYS = tuple(s[0] for s in STEPS)
# The stages inside the steps: choosing (workspace, source, schema) is step 1, the closing line after Create is step 5.
# The names of the nine steps before SM2 still work as `step` (a text client or an older card may send them).
STAGE = {"workspace": "data", "source": "data", "schema": "data", "data": "data", "map": "check", "check": "check",
         "totals": "check", "decide": "decide", "dry_run": "dry_run", "create": "create", "done": "create"}
# WB15 (B, F): the card's header and every text that names a step use these: "Step 2 of 5: Check".
# One path, one total, the same numbers in the card, in the Coach block and in what Claude is asked to write.
SHORT = {"data": "Your data", "check": "Check", "decide": "Decide", "dry_run": "Dry run", "create": "Create"}
# WB15: the mascot who speaks on each step, as the demo chat: Onto points the way, the Thinker checks, the Builder builds
WHO = {"data": "onto", "check": "thinker", "decide": "thinker", "dry_run": "builder", "create": "builder"}
# WB15 (item 11): the names suggested on step 5, the path of the coach: silver and gold, the model, the data agent
SUGGESTED = ("create_pipeline", "create_semantic_model", "create_data_agent")
BY_KEY = {s[0]: s for s in STEPS}

# What the dry run shows and step 5 creates, in the order they are built: (tool, suffix, what it is). The report binds to
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
# WB12 (#72): the full sentence on the first card, then this line, which opens to the full sentence.
HONEST_SHORT = "Only step 5 writes."
# WB12 (#71): each rule code in words, once per card (infer.RULES says the same at length).
RULE_WORDS = {
    "R0": "the source declares this foreign key",
    "R1": "the column is named after the table it points at",
    "R2": "the column has the same name as the other table's key",
    "R3": "the table holds every column of the other table's composite key",
    "R4": "a weaker name match, through the synonym table",
    "R5": "a code column checked against the rows of the table with the same stem",
    "R6": "every value was found in the other table's key, counted in the rows",
}
ARROW = "\u2192"
# WB12 (#76): steps 1-3 list what the account can open as buttons; a long list gets a search box on the card.
CHOICES_MAX = 60
CHOOSE = {"workspace": "Choose a workspace first.", "source": "Choose a source first.", "schema": "Choose a schema first."}
SKIPPED_ON_SAMPLE = ("data",)
# SM5 (G1 in docs/SMOOTH/MULTI-LAKEHOUSE.md): with several sources, step 1 suggests one by name rules, never by reading
# rows. A name's words are its parts split at anything that is not a letter or a digit ("bronze_lh" -> bronze, lh).
#   L1 layer: exactly one source is named as the raw layer (bronze, raw, landing, staging): it is the source, and the
#      ones named silver or gold are left as they are (they are where a build may write, SM6).
#   L2 product: no raw layer, exactly one source is named as a data product (product): it holds the sources as
#      schemas (layout (c), COMBINE-SOURCES.md section 1).
# Otherwise nothing is suggested and Next waits, as before. A suggestion is taken like a single option (0 extra taps)
# and is one tap from Change.
LAYERS = {"bronze": ("bronze", "raw", "landing", "staging"), "silver": ("silver", "curated", "cleansed"),
          "gold": ("gold", "serving", "mart")}
PRODUCT_WORDS = ("product",)


def _words(name: str) -> set[str]:
    import re
    return {w for w in re.split(r"[^0-9a-z]+", str(name).lower()) if w}


def layer_of(name: str) -> str | None:
    """'bronze', 'silver' or 'gold' when the name says so by one of LAYERS' words, else None."""
    w = _words(name)
    hit = [k for k, words in LAYERS.items() if w & set(words)]
    return hit[0] if len(hit) == 1 else None


def suggest_source(items: list[dict]) -> dict | None:
    """SM5: {name, rule, why, say, others: {name: what happens to it}} for the source the name rules point at, or None.
    `items` are the source step's options ({name, hint})."""
    names = [str(x.get("name") or "").strip() for x in items if isinstance(x, dict) and str(x.get("name") or "").strip()]
    if len(names) < 2:
        return None
    raw = [n for n in names if layer_of(n) == "bronze"]
    if len(raw) == 1:
        pick = raw[0]
        layered = [n for n in names if n != pick and layer_of(n) in ("silver", "gold")]
        others = {n: f"{layer_of(n)} layer: not read" for n in layered}
        rest = ", ".join(layered[:2]) if layered else ""
        say = (f"I picked {pick}: its name says raw data." + (f" {rest} stay untouched." if rest else ""))
        return {"name": pick, "rule": "L1", "why": "the name says raw data (bronze)", "say": say, "others": others}
    product = [n for n in names if _words(n) & set(PRODUCT_WORDS) and layer_of(n) is None]
    if len(product) == 1:
        pick = product[0]
        return {"name": pick, "rule": "L2", "why": "the name says data product: the sources as schemas",
                "say": f"I picked {pick}: its name says data product.", "others": {}}
    return None


# SM2: after Create, one closing step: open it in Fabric, add a source, schedule it
FABRIC_URL = "https://app.fabric.microsoft.com/"
HONEST = ("Steps 1-4 only read: they list, count and draft, and the dry runs create nothing. Only step 5 writes, and only "
          "after the dry run and a second confirmation from you that names each item. The answers are counts and names, "
          "no row values, unless you ask to see rows.")


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
    # DIR1: `say` describes the option (the tool and its arguments); it instructs nobody
    say = f"{label} ({tool} with {_shown(arguments)})." if arguments else f"{label} ({tool})."
    if kind == "dry_run":
        say = f"{label} ({tool} as a dry run with {_shown(arguments)})."
    elif kind == "create":
        say = f"{label} ({tool} with {_shown(arguments)})."
    # n227: `ask` is the step in plain words: what the card shows and sends to the chat; `say` names the tool and its
    # arguments for a text client.
    name = arguments.get("name") if isinstance(arguments, dict) else None
    return {"kind": kind, "label": label, "who": "builder" if kind in ("dry_run", "create") else "onto", "tool": tool,
            "arguments": arguments, "say": say, "ask": f"{label}." if kind != "create" else f"{label} in Fabric, as confirmed.",
            **({"name": name} if name else {})}


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
        out = {"sample": True, "step": step}
        plan = {k: c[k] for k in ("confirmed", "decisions") if c.get(k)}
        if plan:
            out["plan"] = plan
        return out
    out = {k: c[k] for k in ("workspace", "source", "schema") if c.get(k)}
    plan = {k: c[k] for k in ("keys", "confirmed", "decisions") if c.get(k)}
    if plan:
        out["plan"] = plan
    out["step"] = step
    return out


def _next_key(key: str) -> str | None:
    """The stage after `key`: data -> check -> decide -> dry_run -> create (choosing ends on data)."""
    order = ("data", "check", "decide", "dry_run", "create", "done")
    k = STAGE.get(key, key) if key not in order else key
    i = order.index(k)
    return order[i + 1] if i + 1 < len(order) else None


def current(step: str | None, c: dict) -> str:
    """Which stage to show: the one asked for, unless what it needs has not been chosen yet. A stage of before SM2
    maps onto its step (map and totals are part of check). With everything chosen and no step, "data": the one line
    of what was chosen, with Change."""
    s = (step or "").strip().lower() or None
    if c.get("sample"):
        k = STAGE.get(s or "", "check")
        return "check" if k == "data" else ("done" if s == "done" else k)
    if s in CHOOSE:                                      # Change: the list again, even when something was chosen
        if s == "source" and c.get("workspace"):
            return "source"
        if s == "schema" and c.get("workspace") and c.get("source"):
            return "schema"
        if s == "workspace":
            return "workspace"
    if not c.get("workspace"):
        return "workspace"
    if not c.get("source"):
        return "source"
    if not c.get("schema"):
        return "schema"
    if s in (None, "data") or s in CHOOSE:
        return "data"
    if s not in STAGE:
        return "check"
    return "done" if s == "done" else STAGE[s]


def only_choice(stage: str, options: dict | None) -> str | None:
    """SM2: the one usable option of a choosing stage (as _choices marks it), else None."""
    if not isinstance(options, dict) or options.get("step") != stage or not isinstance(options.get("items"), list):
        return None
    usable = [x for x in options["items"] if isinstance(x, dict) and str(x.get("name") or "").strip()
              and not str(x.get("hint") or "").startswith("no capacity")
              and (stage != "schema" or int(x.get("tables") or 0) > 0)
              and (stage != "schema" or "+" not in str(x.get("name")))]          # SM5: "all together" is never taken alone
    if len(usable) == 1:
        return str(usable[0]["name"])
    hit = suggest_source(usable) if stage == "source" else None             # SM5: the name rules' suggestion
    return hit["name"] if hit else None


def _path(now: str, sample: bool = False) -> list[dict]:
    """The five steps, each done, now or later; on the sample, step 1 is `skipped` (WB12, #73): nothing was chosen."""
    i = KEYS.index(STAGE.get(now, now))
    out = []
    for n, (k, t, d, _) in enumerate(STEPS):
        state = "done" if n < i else ("now" if n == i else "later")
        if sample and k in SKIPPED_ON_SAMPLE:
            state = "skipped"
        out.append({"n": n + 1, "key": k, "title": t, "does": d, "state": state,
                    **({"note": "skipped (sample)"} if state == "skipped" else {})})
    return out


def _finished(path: list[dict]) -> str:
    """'Done: 1-5' for the card's one collapsed line (WB12, #73); '' when nothing is finished yet."""
    def span(ns: list[int]) -> str:
        return str(ns[0]) if len(ns) == 1 else f"{ns[0]}-{ns[-1]}"
    done = [p["n"] for p in path if p["state"] == "done"]
    skipped = [p["n"] for p in path if p["state"] == "skipped"]
    parts = ([f"Done: {span(done)}"] if done else []) + ([f"skipped on the sample: {span(skipped)}"] if skipped else [])
    line = "; ".join(parts)
    return line[:1].upper() + line[1:]


def _honest(out: dict, first: bool) -> None:
    out["honest"] = HONEST
    out["honest_short"] = HONEST_SHORT
    out["honest_open"] = bool(first)


def rule_words(rules) -> list[str]:
    """'R1: the column is named after the table it points at', once per rule code, in the order met."""
    seen = []
    for r in rules:
        if r in RULE_WORDS and r not in seen:
            seen.append(r)
    return [f"{r}: {RULE_WORDS[r]}" for r in seen]


def _choice(label: str, hint: str, arguments: dict, disabled: str = "") -> dict:
    """WB12 (#76): one option of steps 1-3 as a button that calls start with the choice set."""
    return {"kind": "choose", "label": label, "who": "onto", "tool": TOOL, "arguments": arguments, "hint": hint,
            "say": f"{label} (start with {_shown(arguments)}).", "ask": f"Use {label}.",
            **({"disabled": disabled} if disabled else {})}


def _choices(now: str, c: dict, options: dict | None) -> tuple[list[dict], dict]:
    """The options the start tool read for this step (server.start: names and counts only), as buttons."""
    if not isinstance(options, dict) or options.get("step") != now or not isinstance(options.get("items"), list):
        return [], {}
    items = [x for x in options["items"] if isinstance(x, dict) and str(x.get("name") or "").strip()]
    shown, out = items[:CHOICES_MAX], []
    for x in shown:
        name = str(x["name"])
        if now == "workspace":
            out.append(_choice(name, str(x.get("hint") or ""), {"workspace": name}))
        elif now == "source":
            out.append(_choice(name, str(x.get("hint") or ""), {"workspace": c["workspace"], "source": name}))
        else:
            n = int(x.get("tables") or 0)
            hint = f"{n} table" + ("" if n == 1 else "s") + (", one plan" if "+" in name else "")
            out.append(_choice(name, hint, {"workspace": c["workspace"], "source": c["source"], "schema": name,
                                            "step": "check"},                 # SM2: the last choice goes on
                               disabled="" if n else "no tables"))
    meta = {"count": len(items), "shown": len(shown), "search": len(items) > 8}
    usable = [a for a in out if not a.get("disabled") and not str(a.get("hint", "")).startswith("no capacity")
              and not (now == "schema" and "+" in a["label"])]
    if len(usable) == 1:                                   # WB15 (A): one usable option is chosen for you
        usable[0]["selected"] = True
        meta["preselected"] = usable[0]["label"]
    elif now == "source" and (hit := suggest_source([{"name": a["label"]} for a in usable])):
        for a in out:                                      # SM5: the name rules' suggestion, chosen like one option
            if a["label"] == hit["name"]:
                a["selected"] = True
                a["hint"] = (a.get("hint") + "; " if a.get("hint") else "") + "suggested"
            elif a["label"] in hit["others"]:
                a["hint"] = (a.get("hint") + "; " if a.get("hint") else "") + hit["others"][a["label"]]
        meta["preselected"] = hit["name"]
        meta["suggested"] = {k: hit[k] for k in ("rule", "why")}
    return out, meta


def guide(workspace: str | None = None, source: str | None = None, schema: str | None = None, step: str | None = None,
          keys: dict | None = None, confirmed: list | None = None, decisions: list | None = None,
          create: list | None = None, confirm: bool = False, sample: bool = False, options: dict | None = None,
          review: dict | None = None, picked: list | None = None, suggested: dict | None = None) -> dict:
    """The stepper's answer (see the module docstring). Pure: no Fabric, no SQL. `options` (WB12, #76) is what the
    start tool read for a choosing stage: {step, items: [{name, hint?, tables?}]} or {step, error}. `review` (WB13, #66)
    is review_plan's file with the checks counted, built by the start tool for Check and Decide, or {error}. `picked`
    (SM2) names the stages the start tool chose on its own because each had one usable option."""
    c = {"workspace": (workspace or "").strip() or None, "source": (source or "").strip() or None,
         "schema": (schema or "").strip() or None, "keys": keys or None, "confirmed": confirmed or None,
         "decisions": decisions or None, "sample": bool(sample)}
    if c["sample"]:
        return _sample(step, c, run=bool(confirm))
    now = current(step, c)
    key = STAGE[now]
    _, title, does, tool = BY_KEY[key]
    n = KEYS.index(key) + 1
    out = {"flow": PROMPT_TITLE, "step": {"n": n, "of": len(STEPS), "key": key, "title": title, "does": does,
                                          "short": SHORT[key]},
           "stage": now, "who": WHO[key], "path": _path(key), "chosen": {k: v for k, v in c.items() if v and k != "sample"}}
    out["done_line"] = _finished(out["path"])
    actions: list[dict] = []
    nxt = _next_key(now) if now not in CHOOSE else None
    picks, meta = _choices(now, c, options)
    if picks:
        out["choices"] = meta
    elif isinstance(options, dict) and options.get("step") == now and options.get("error"):
        out["choices_error"] = str(options["error"])[:200]
    sample_button = {"kind": "sample", "label": "Show me on the synthetic shop sample", "who": "thinker", "tool": TOOL,
                     "arguments": {"sample": True}, "say": "Show me on the synthetic shop sample (start with sample=true).",
                     "ask": "Show me on the synthetic shop sample."}

    if now == "workspace":
        out["say"] = "Hi! Which workspace shall we start in?"
        if picks:
            if meta.get("preselected"):
                out["say"] = f"Hi! You have one workspace I can use, {meta['preselected']}. Shall we start there?"
            actions += picks
        else:
            actions.append(_call("List my workspaces", "list_workspaces", {}))
        out["then"] = "Next: start with workspace set to the one the user names."
        actions.append({**sample_button, **({"more": True} if picks else {})})   # SM2: into Details when you have data
    elif now == "source":
        out["say"] = f"Which lakehouse or warehouse in {c['workspace']} holds your tables?"
        if picks:
            if meta.get("suggested"):                  # SM5: several sources, one named as the source
                out["say"] = f"I suggest {meta['preselected']}: {meta['suggested']['why']}."
            elif meta.get("preselected"):
                out["say"] = f"{c['workspace']} has one source, {meta['preselected']}. I picked it for you."
            actions += picks
        elif isinstance(options, dict) and options.get("step") == "source" and options.get("items") == []:
            out["say"] = (f"{c['workspace']} has no lakehouse, warehouse or mirrored database I can read. Choose another "
                          "workspace, or try the synthetic shop sample.")
            actions.append(_call("Choose another workspace", TOOL, {"step": "workspace"}))
        else:
            actions.append(_call("List the sources", "list_sources", {"workspace": c["workspace"]}))
        out["then"] = "Next: start with workspace and source set to the user's choice."
    elif now == "schema":
        args = {"workspace": c["workspace"], "source": c["source"]}
        out["say"] = f"Which schema in {c['source']} shall I read?"
        if picks:
            if meta.get("preselected"):
                out["say"] = f"{c['source']} has one schema with tables, {meta['preselected']}. I picked it for you."
            actions += picks
        else:
            actions.append(_call("List the schemas", "plan_backend", args))
        out["then"] = "Next: start with schema set to the user's choice and step=\"check\"."
    elif now == "data":
        # SM2: steps 1-3 of before in one line: "demo › demo_lh › dbo ✓", with Change on tap
        out["line"] = f"{c['workspace']} › {c['source']} › {c['schema']} ✓"
        auto = [x for x in (picked or []) if x in CHOOSE]
        out["say"] = ("Your data, picked for you. Change it if it is wrong." if auto else "Your data. Change it if it is wrong.")
        if auto:
            out["picked"] = auto
        if isinstance(suggested, dict) and suggested.get("name") == c["source"]:    # SM5: why this source, in one line
            out["suggested"] = {k: suggested[k] for k in ("rule", "why", "others") if k in suggested}
            out["say"] = str(suggested.get("say") or out["say"])
        actions.append({**_call("Change", TOOL, {"step": "workspace"}), "kind": "call", "secondary": True,
                        "ask": "Change the workspace, source or schema."})
        actions.append({**sample_button, "more": True})
    elif now == "check":
        out.update(_check(c, review))
        actions += out.pop("actions")
    elif now == "decide":
        out["say"] = "Some links need you. The count supports it, and you decide."
        out["then"] = ("review_plan records the decisions (item ids are in its file); an accepted link goes into confirmed "
                       "for the next steps.")
        args = _plan_args(c)
        sent = [d for d in c.get("decisions") or [] if isinstance(d, dict) and d.get("review") in ("accepted", "rejected")]
        if sent:
            args["decisions"] = sent
        if c.get("decisions"):
            out["decided"] = [_decided_line(d, False) for d in c["decisions"] if isinstance(d, dict)]
        if isinstance(review, dict) and isinstance(review.get("items"), list):        # WB13 (#66): per decision
            decisions = review_decisions(review, c)
            waiting = [x for x in decisions if x["state"] == "open"]
            out["found"] = {"tool": "review_plan", "summary": _review_summary(review).split(" The check also")[0], "decisions":
                            [{k: v for k, v in x.items() if k != "actions"} for x in decisions]}
            for x in decisions:
                if x["state"] == "open":
                    actions += x["actions"]
                else:                                    # answered: one button to change it
                    other = [a for a in x["actions"] if a["decision"] != x["state"] and a["decision"] != "skipped"]
                    actions += [{**a, "label": "Change to " + ("Reject" if a["decision"] == "rejected" else "Accept")}
                                for a in other[:1]]
            if not decisions:
                out["say"] = "Nothing needs your decision: every link holds in the rows."
            elif waiting:
                out["say"] = ("One link needs you." if len(waiting) == 1 else f"{len(waiting)} links need you.")
            else:
                out["say"] = "Every decision is answered. Next: the dry run."
            out["then"] = ("Each button sends its decision to start in plan.decisions; an accepted link goes into "
                           "plan.confirmed for the next steps. Deciding writes nothing to Fabric. Next leaves an open "
                           "decision open.")
            out["open_decisions"] = len(waiting)
            if sent:                                     # the file to keep, once something is decided: under Details
                actions.append({**_call("Keep my decisions as a review file", "review_plan", args), "secondary": True,
                                "more": True})
        else:
            if isinstance(review, dict) and review.get("error"):
                out["review_error"] = str(review["error"])[:200]
            actions.append(_call("Record my decisions", "review_plan", args))
    elif now == "dry_run":
        names = build_names(c["source"], c["schema"])
        out["say"] = "One tap dry-runs everything. Nothing is created."
        out["would_build"] = [{"tool": t, "name": names[t], "what": w} for t, _, w in BUILDS]
        out["data_flow"] = list(FLOW)
        runs = []
        for t, _, w in BUILDS:
            if t == "create_report":
                continue
            args = {**_plan_args(c), "name": names[t]}
            label = {"create_pipeline": "Dry run: silver and gold", "create_semantic_model": "Dry run: semantic model",
                     "create_data_agent": "Dry run: data agent"}.get(t, f"Dry run: {w}")
            a = _call(label, t, args, kind="dry_run")
            a["more"] = True                               # SM2: one button runs them all; each one under Details
            actions.append(a)
            if t in SUGGESTED:
                runs.append({k: a[k] for k in ("label", "tool", "arguments", "name") if k in a})
        everything = _call("Dry run everything", runs[0]["tool"], runs[0]["arguments"], kind="dry_run")
        everything.update({"kind": "dry_run_all", "primary": True, "runs": runs,
                           "say": "Dry run everything: " + "; ".join(f"{r['tool']} as a dry run with "
                                                                    f"{_shown(r['arguments'])}" for r in runs) + ".",
                           "ask": "Dry run the silver and gold pipeline, the semantic model and the data agent."})
        actions.insert(0, everything)
        out["then"] = ("Next, once the user has read the dry runs: start with step=\"create\" and create set to the names "
                       "the user wants, e.g. " + json.dumps(sorted(names.values())[:2]) + "; nothing is created before "
                       "the user confirms them.")
    elif now == "create":
        out.update(_create(c, create, confirm))
        actions = out.pop("actions")
        if out.get("confirmed_by_user"):                 # SM2: never a dead end after Create
            nxt = "done"
        else:
            nxt = None
    elif now == "done":
        out.update(_closing(c))
        actions = out.pop("actions")
        nxt = None
    if isinstance(review, dict) and isinstance(review.get("items"), list) and now in ("check", "decide"):
        from . import mcp_apps_pictures as pictures, review as _review       # WB13 (#71): the small map
        m = pictures.map_from_review({"review": review}) or {}
        taken = {str(d.get("item")): str(d.get("review")) for d in c.get("decisions") or [] if isinstance(d, dict)}
        opened = {it["id"] for it in _review.open_decisions(review)}
        if m.get("tables"):
            out.update(start_map(m["tables"], m.get("relationships") or [], opened, taken))
            if now == "check":
                out.setdefault("found", {})["rules"] = rule_words(r.get("rule") for r in m.get("relationships") or [])
    asked = (step or "").strip()
    if asked and asked.lower() not in STAGE:             # F1 B13: an unknown step keeps the place and says so
        out["unknown_step"] = {"asked": asked, "steps": list(KEYS)}
        out["say"] = (f"I don't know a step called “{asked[:40]}”, so this is where you are. " + out.get("say", ""))
    out["actions"] = actions
    if c.get("decisions") and now in ("dry_run", "create", "done"):          # WB12 (#66): the decisions travel on
        out["decided"] = [_decided_line(d, False) for d in c["decisions"] if isinstance(d, dict)]
    pre = (out.get("choices") or {}).get("preselected")
    if now in CHOOSE and pre:                                                # WB15 (A): one option, chosen: Next works
        nc = {**c, now: pre}
        args = _choice_args(now, nc)
        out["after"] = {"tool": TOOL, "arguments": args, "label": "Next: Check" if now == "schema" else "Next",
                        "say": f"Next step (start with {_shown(args)}).", "ask": f"Use {pre}."}
    elif now in CHOOSE:                                                      # WB12 (#77): no Next before the choice
        out["next_waits"] = {"label": "Next", "why": CHOOSE[now]}
    elif nxt:
        label = "Next: what now?" if nxt == "done" else f"Next: {SHORT[STAGE[nxt]]}"
        out["after"] = {"tool": TOOL, "arguments": _start_args(c, nxt), "label": label,
                        "say": f"Next step (start with {_shown(_start_args(c, nxt))}).", "ask": f"{label}."}
        if now == "decide" and out.get("open_decisions"):    # WB13 (#66): secondary until each is answered or skipped
            out["after"]["secondary"] = True
            out["after"]["why"] = "Next leaves the open decision open."
        if now in ("dry_run", "create"):                      # the step's own button is the primary one
            out["after"]["secondary"] = True
    _honest(out, now in CHOOSE or now == "data")
    out["summary"] = (f"Step {n} of {len(STEPS)}: {SHORT[key]} ({does}). "
                      + ("Run the button's tool, show its answer, then continue with `after`." if actions else ""))
    return out


def _choice_args(stage: str, c: dict) -> dict:
    """The start arguments once `stage` is chosen: the next choice is read (and taken when it is the only one)."""
    out = {k: c[k] for k in ("workspace", "source", "schema") if c.get(k)}
    if stage == "schema":
        out["step"] = "check"
    return out


def _check(c: dict, review: dict | None) -> dict:
    """SM2: step 2. The map, the row check and the doubled totals have run on their own (review_plan's file with the
    checks counted, read by the start tool): one line each, the map and every count under Details."""
    from . import review as _review
    args = _plan_args(c)
    more = [{**_call("Show the map's answer", "plan_backend", args), "more": True},
            {**_call("Every check against the rows", "validate_plan", args), "more": True},
            {**_call("Doubled totals in full", "validate_plan", {**args, "fixes": True}), "more": True}]
    if not (isinstance(review, dict) and isinstance(review.get("items"), list)):
        err = str((review or {}).get("error") or "") if isinstance(review, dict) else ""
        return {"say": "I could not count the rows yet. Check against the rows tries again.",
                **({"review_error": err[:200]} if err else {}),
                "actions": [{**_call("Check against the rows", "validate_plan", args), "primary": True}] + more[:1] + more[2:]}
    items = review["items"]
    keys = sum(1 for it in items if it.get("type") == "key")
    rels = sum(1 for it in items if it.get("type") == "relationship")
    status = [(it.get("check") or {}).get("status", "not_checked") for it in items]
    counted = [x for x in status if x in ("passed", "failed", "stale")]
    held = sum(1 for x in status if x == "passed")
    waiting = len(_review.open_decisions(review))
    need = f"{waiting} {'needs' if waiting == 1 else 'need'} you" if waiting else "nothing needs you"
    lines = []
    if counted:
        lines.append(f"{held} of {len(counted)} checks hold.")
    amounts = ((review.get("other_checks") or {}).get("header_amounts") or {})
    bad = int(amounts.get("repeat_on_every_line") or 0)
    if amounts.get("checked"):
        lines.append(f"{bad} header {'amount' if bad == 1 else 'amounts'} would count twice." if bad else
                     "No total counts twice.")
    return {"say": f"{keys} tables, {rels} links, {need}.", "lines": lines,
            "counts": {"tables": keys, "links": rels, "checks": len(counted), "hold": held, "open_decisions": waiting,
                       "doubled_totals": bad},
            "found": {"tool": "review_plan", "summary": _review_summary(review)},
            "actions": more}


def _closing(c: dict) -> dict:
    """SM2: step 5 after Create. Open it in Fabric, add another source, or schedule the pipeline."""
    names = build_names(c["source"], c["schema"])
    pipe = names["create_pipeline"]
    return {"say": "Done. What next?",
            "actions": [{"kind": "link", "label": "Open in Fabric", "who": "builder", "tool": TOOL, "arguments": {},
                         "url": FABRIC_URL, "primary": True, "say": f"Open Fabric ({FABRIC_URL}).",
                         "ask": f"Open {c['workspace']} in Fabric."},
                        {**_call("Add a source", TOOL, {"workspace": c["workspace"], "step": "source"}),
                         "ask": f"Add another source in {c['workspace']}."},
                        {"kind": "chat", "label": "Schedule it", "who": "builder", "tool": TOOL, "arguments": {},
                         "say": f"Schedule {pipe} to run every day.", "ask": f"Schedule {pipe} to run every day."}]}


def _create(c: dict, create: list | None, confirm: bool) -> dict:
    """Step 9: the creating calls with dry_run=false, only for names the dry run showed and only with confirm=true."""
    names = build_names(c["source"], c["schema"])
    by_name = {v: k for k, v in names.items()}
    asked = [str(x) for x in (create or [])]
    unknown = [x for x in asked if x not in by_name]
    if not asked or unknown or not confirm:
        # WB15 (item 11): never a dead end: the names are suggested and one button confirms them
        suggest = [x for x in asked if x in by_name] or [names[t] for t in SUGGESTED]
        confirm_args = {**_start_args(c, "create"), "create": suggest, "confirm": True}
        why = (f"Not in the dry run: {', '.join(unknown)}. " if unknown else "")
        return {"needs_confirmation": True, "would_create": [{"tool": by_name[x], "name": x} for x in suggest],
                "suggested": suggest,
                "say": f"{why}Confirm these names; then each gets its own Create button.",
                "then": ("The question for the user: \"Create " + ", ".join(asked or sorted(names.values())) + " in " +
                         str(c["workspace"]) + "? Say yes to create exactly these.\" After a yes: start with "
                         "step=\"create\", create=[the names] and confirm=true."),
                "actions": [{**_call("Confirm these names", TOOL, confirm_args), "kind": "confirm", "primary": True,
                             "ask": "Yes, use the names " + ", ".join(suggest) + "."},
                            {**_call("Back to the dry run", TOOL, _start_args(c, "dry_run")), "secondary": True}]}
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
            "say": "Confirmed. Each button creates one item in Fabric, on a second tap. Nothing is deleted.",
            "then": "The calls go in this order.",
            "actions": actions}


# ------------------------------------------------------------------ decisions (WB12, #66) -----------------------------

def _decided_line(d: dict, sample: bool = True) -> str:
    item = str(d.get("item") or "")
    m = item[4:] if item.startswith("rel:") else item
    m = m.replace(">", f" {ARROW} ")
    how = {"accepted": "accepted", "rejected": "rejected", "skipped": "skipped for now"}.get(str(d.get("review")), str(d.get("review")))
    use = {"accepted": ": the next steps use this link", "rejected": ": the next steps leave it out",
           "skipped": ": the next steps leave it out until you decide"}.get(str(d.get("review")), "")
    if not sample and d.get("review") == "skipped":
        # WB15 (G): a rejected link is now left out of every dry run and build on the path (flow_state.BUILD_TOOLS)
        use = ": kept open; decide it before you build"
    return f"{m}: {how}{use}."


def _with_decision(c: dict, item: str, review: str, link: dict | None) -> dict:
    """The start arguments after one more decision: the decision in plan.decisions (one per item, the last one kept),
    and an accepted link in plan.confirmed (review_plan's and validate_plan's own `confirmed`)."""
    decisions = [d for d in c.get("decisions") or [] if isinstance(d, dict) and d.get("item") != item]
    decisions.append({"item": item, "review": review, "reason": "decided on the start card"})
    confirmed = [x for x in c.get("confirmed") or [] if x != link]
    if review == "accepted" and link:
        confirmed.append(link)
    nc = {**c, "decisions": decisions, "confirmed": confirmed or None}
    return _start_args(nc, "decide")


def _evidence_lines(s: dict) -> list[str]:
    """The counted evidence under a question: the share of values found in the target and the distinct values."""
    ev = s.get("evidence") or {}
    n, m = int(ev.get("rows_with_value") or 0), int(ev.get("matched") or 0)
    if not n:
        return []
    tgt = f"{s['target']}.{'+'.join(s.get('target_cols') or [])}"
    out = [f"{m} of {n} {s['table']}.{s['column']} values found in {tgt} ({round(100 * m / n)}%)."]
    if ev.get("distinct_values") is not None:
        out.append(f"{ev['distinct_values']} distinct values.")
    ru = s.get("runner_up") or {}
    if ru.get("rows_with_value"):
        out.append(f"The next candidate, {ru['target']}: {ru['matched']} of {ru['rows_with_value']} found.")
    return out


def open_decisions(suggestions: list[dict], c: dict) -> list[dict]:
    """Each column no naming rule linked, as a decision with its question, its evidence and its Accept, Reject and Skip
    buttons (each calls start again with the decision in plan.decisions)."""
    taken = {str(d.get("item")): str(d.get("review")) for d in c.get("decisions") or [] if isinstance(d, dict)}
    out = []
    for s in suggestions:
        item = f"rel:{s['table']}.{s['column']}>{s['target']}"
        link = s.get("confirmed")
        q = (f"Does {s['table']}.{s['column']} point at {s['target']}? {s['table']}.{s['column']} is not named after "
             f"any table, so no naming rule linked it.")
        acts = []
        for review, label in (("accepted", "Accept"), ("rejected", "Reject"), ("skipped", "Skip for now")):
            args = _with_decision(c, item, review, link)
            acts.append({"kind": "decide", "decision": review, "label": f"{label}", "who": "thinker", "tool": TOOL,
                         "arguments": args, "item": item,
                         "say": f"{label} {s['table']}.{s['column']} {ARROW} {s['target']} (start with {_shown(args)}).",
                         "ask": f"{label}: {s['table']}.{s['column']} points at {s['target']}."
                         if review == "accepted" else f"{label}: {s['table']}.{s['column']} {ARROW} {s['target']}."})
        ev = s.get("evidence") or {}
        n, m = int(ev.get("rows_with_value") or 0), int(ev.get("matched") or 0)
        out.append({"item": item, "question": q, "evidence": _evidence_lines(s), "state": taken.get(item, "open"),
                    "actions": acts, **({"count": f"{m} of {n} found ({round(100 * m / n)}%)."} if n else {})})
    return out


def start_map(tables: list[dict], rels: list[dict], open_ids: set[str], taken: dict[str, str]) -> dict:
    """WB13 (#71): the start card's map: every table with its key, every link with its rule and its state for the
    person: accepted (a decision, or a link the names prove), open (it waits for a decision) or rejected. Drawn small
    first (mcp_apps_pictures.mini_map) when there are more than six tables."""
    from . import mcp_apps_pictures as pictures
    out_rels = []
    for r in rels:
        rid = "rel:" + r["id"]
        state = taken.get(rid) or ("open" if rid in open_ids else r.get("review") or "proposed")
        out_rels.append({**r, "review": {"skipped": "open"}.get(state, state)})
    m = {"tables": tables, "relationships": out_rels, "checked": any(r.get("state") not in (None, "not_checked") for r in rels),
         "reviewed": True, "rules": rule_words(r.get("rule") for r in rels)}
    small = pictures.mini_map(m)
    return {"map": m, **({"map_mini": small} if small else {})}


def _review_summary(review: dict) -> str:
    from . import review as _review
    return _review.summary(review)


def review_decisions(review: dict, c: dict) -> list[dict]:
    """WB13 (#66): step 6 on your own data. The items review_plan's rule says wait for a person (review.needs_decision:
    a failed or stale check, a weaker rule, an item left open), each with review_plan's own evidence (the item's
    check counts) and its Accept, Reject and Skip buttons. A link with rows that point at nothing is accepted "with
    quarantine": the silver notebook puts those rows in krusgraph_quarantine with the reason. Each button calls start
    again with the decision in plan.decisions (and an accepted link in plan.confirmed); nothing is written to Fabric."""
    from . import review as _review
    taken = {str(d.get("item")): str(d.get("review")) for d in c.get("decisions") or [] if isinstance(d, dict)}
    out = []
    for it in _review.open_decisions(review, include=set(taken)):
        item = it["id"]
        failed = (it.get("check") or {}).get("status") == "failed"
        link = {"source": it["source"], "source_cols": list(it["columns"]), "target": it["target"],
                "target_cols": list(it.get("target_columns") or [])}
        what = f"{it['source']}.{'+'.join(it['columns'])} {ARROW} {it['target']}"
        q = f"Is {what} right? {_review.why_decide(it)}"
        acts = []
        labels = (("accepted", "Accept with quarantine" if failed else "Accept"), ("rejected", "Reject"), ("skipped", "Skip for now"))
        for review_, label in labels:
            args = _with_decision(c, item, review_, link)
            acts.append({"kind": "decide", "decision": review_, "label": label, "who": "thinker", "tool": TOOL,
                         "arguments": args, "item": item,
                         "say": f"{label} {what} (start with {_shown(args)}).",
                         "ask": f"{label}: {what}."})
        ev = _review.decision_evidence(it)
        r = (it.get("check") or {}).get("result") or {}
        n, o = int(r.get("rows_with_value") or 0), int(r.get("orphans") or 0)
        count = f"{n - o} of {n} found ({round(100 * (n - o) / n)}%)." if n and "rows_with_value" in r else ""
        if failed:
            ev.append("Accept with quarantine keeps the link; the silver step puts the rows that point at nothing in "
                      "quarantine with the reason, so nothing is lost.")
        out.append({"item": item, "question": q, "evidence": ev, "state": taken.get(item, "open"), "actions": acts,
                    **({"count": count} if count else {}),
                    "rule": it.get("rule"), "check": (it.get("check") or {}).get("status", "not_checked")})
    return out


# ------------------------------------------------------------------ the synthetic shop ---------------------------------

_PROOF: dict = {}


def sample_proof() -> dict:
    """WB12 (#70): what the check proved on the synthetic shop, as the Fabric item's proof tiles say it (ProofStrip in
    workload/.../NextStepsView.tsx): rows counted, keys unique, links holding, orphans, duplicate keys, and the grain
    line of the first link whose table has more rows than the one it points at. Counted on seed.py's rows."""
    if _PROOF:
        return _PROOF
    from . import demo, evidence
    from .infer import plan
    from .number_words import count
    from .seed import schema
    p = plan(schema("shop"), keys=demo.DEMO_KEYS)
    v = evidence.validate(p, demo._demo_db(), max_items=200)
    keys, rels = v["keys"], v["relationships"]
    rows = sum(int(k.get("rows") or 0) for k in keys)
    unique = [k for k in keys if k.get("nulls") == 0 and k.get("distinct") == k.get("rows")]
    held = [r for r in rels if r.get("orphans") == 0]
    orphans = sum(int(r.get("orphans") or 0) for r in rels)
    dups = sum(max(0, int(k.get("rows") or 0) - int(k.get("nulls") or 0) - int(k.get("distinct") or 0)) for k in keys)
    by = {k["table"]: int(k.get("rows") or 0) for k in keys}
    grain = ""
    key_cols = {k["table"]: {c.lower() for c in k.get("columns") or []} for k in keys}
    # the item's grain line: a line table over its header first (order_items over orders), then any other link
    held = sorted(held, key=lambda r: 0 if {c.lower() for c in r.get("columns") or r.get("source_cols") or []}
                  <= key_cols.get(r.get("source"), set()) else 1)
    for r in held:
        child, parent = r.get("source"), r.get("target")
        cr, pr = by.get(child, 0), by.get(parent, 0)
        if pr > 0 and cr > pr:
            ratio = round(cr / pr, 1)
            grain = (f"{count(cr)} {child} rows over {count(pr)} {parent} rows: an amount on {parent} summed over {child} "
                     f"would count each {parent} row {ratio}× on average. Sum {child} per {parent} row first.")
            break
    _PROOF.update({"rows": rows, "keys_unique": len(unique), "keys": len(keys), "links_holding": len(held),
                   "links": len(rels), "orphans": orphans, "duplicates": dups, "grain": grain,
                   "tiles": [[count(rows), "rows counted"], [f"{len(unique)} of {len(keys)}", "keys unique"],
                             [f"{len(held)} of {len(rels)}", "links holding"],
                             [count(orphans), "orphan" if orphans == 1 else "orphans"],
                             [count(dups), "duplicate key" if dups == 1 else "duplicate keys"]]})
    return _PROOF


def _singular(t: str) -> str:
    return t[:-3] + "y" if t.endswith("ies") else t[:-1] if t.endswith("s") and not t.endswith("ss") else t


def doubled_lines(findings: list[dict]) -> tuple[list[str], list[str]]:
    """WB12 (#67): each doubled total with its sums formatted (number_words), the factor, and one plain sentence."""
    from .number_words import amount, factor
    lines, advice = [], []
    for x in findings:
        sums = x.get("sums") or {}
        over, once = sums.get("summed_over_lines"), sums.get("summed_per_header")
        f = factor(over, once)
        lines.append(f"{x['table']}.{x['column']} summed over the joined {x['joined_with']} rows: {amount(over)}; "
                     f"once per {x['table']} row: {amount(once)}" + (f" ({f})." if f else "."))
        one = _singular(str(x["table"]))
        advice.append(f"A sum of {x['column']} after joining {x['joined_with']} counts each {one} once per "
                      f"{x['joined_with']} row; sum per {one} first.")
    return lines, advice


SAMPLE_SAY = {
    "decide": "Nothing needs your decision on the shop.",
    "dry_run": "One tap dry-runs everything on the shop.",
    "create": "This is the sample, so nothing is created. Try it on your own data.",
}


def _sample(step: str | None, c: dict | None = None, run: bool = False) -> dict:
    """The same path on the synthetic shop (demo.py: the engine's output on seed.py's shop). Nothing in Fabric is read
    or created; each step shows what the tool answered on the shop, and `after` moves on. WB12: the decisions made on
    step 3 (plan.decisions, plan.confirmed) travel with `after` into steps 4-5. SM2: the dry run has the same button as
    on your own data ("Dry run everything"); on the sample it is the start call with confirm=true on step dry_run, and
    its answer is the three dry runs, one line each."""
    from . import demo
    c = {"sample": True, **(c or {})}
    p = demo.demo_plan()
    now = current(step, c)
    if now == "done":
        now = "create"
    key = STAGE[now]
    _, title, does, tool = BY_KEY[key]
    n = KEYS.index(key) + 1
    d = p["drafts"]["as_is"]
    found: dict = {}
    actions: list[dict] = []
    decisions = open_decisions(p["suggestions"], c) if p["suggestions"] else []
    waiting = [x for x in decisions if x["state"] == "open"]
    lines: list[str] = []
    if now == "check":
        proof = sample_proof()
        f = [x for x in d["fixes"]["findings"] if x.get("sums")]
        doubled, advice = doubled_lines(f)
        found = {"tool": "plan_backend", "summary": p["summary"].splitlines()[0],
                 "links": [f"{r['source']}.{'+'.join(r['source_cols'])} {ARROW} {r['target']} ({r['rule']})" for r in p["relationships"]],
                 "rules": rule_words(r["rule"] for r in p["relationships"]),
                 "no_key": p["keyless"], "proof": proof, "doubled": doubled, "advice": advice,
                 "check": d["validation"]["summary"],
                 # F1 B4: the sample's plan is made from the names alone; on a real source the plan also counts
                 "note": ("This sample plan reads the names only. On your own data the plan also counts columns like "
                          "orders.ship_to_id against the rows and would already propose that link (rule R5); the "
                          "sample asks you about it in step 3.")}
        need = f"{len(waiting)} {'needs' if len(waiting) == 1 else 'need'} you" if waiting else "nothing needs you"
        lines = [f"{len(p['tables'])} tables, {len(p['relationships'])} links, {need}.",
                 f"{proof['links_holding']} of {proof['links']} links hold.",
                 (f"{len(f)} {'amount' if len(f) == 1 else 'amounts'} would count twice." if f else "No total counts twice.")]
    elif now == "decide":
        first = decisions[0] if decisions else None
        found = {"tool": "review_plan", "decisions": [{k: v for k, v in x.items() if k != "actions"} for x in decisions],
                 "question": (first["question"] + " Accept or reject.") if first else "Nothing needs a decision on the shop."}
        for x in decisions:
            if x["state"] == "open":
                actions += x["actions"]
            else:                                    # answered: one button to change it
                other = [a for a in x["actions"] if a["decision"] != x["state"] and a["decision"] != "skipped"]
                actions += [{**a, "kind": "decide", "label": "Change to " + ("Reject" if a["decision"] == "rejected" else "Accept")}
                            for a in other[:1]]
    elif now == "dry_run":
        names = build_names("shop", "shop")
        found = {"would_build": [{"tool": t, "name": names[t], "what": w} for t, _, w in BUILDS], "data_flow": list(FLOW)}
        if run:                                          # the three dry runs on the shop, one line each
            rels = len(p["relationships"]) + sum(1 for x in decisions if x["state"] == "accepted")
            found["dry_runs"] = [
                {"name": names["create_pipeline"], "line": f"{len(p['tables'])} silver tables, gold views, then the check."},
                {"name": names["create_semantic_model"], "line": f"{len(p['tables'])} tables, {rels} relationships."},
                {"name": names["create_data_agent"], "line": f"{len(p['tables'])} tables, the plan as instructions."}]
            lines = [f"\u2713 {x['name']}" for x in found["dry_runs"]]
        else:
            args = _start_args(c, "dry_run")
            actions.append({"kind": "dry_run_all", "label": "Dry run everything", "who": "builder", "tool": TOOL,
                            "arguments": {**args, "confirm": True}, "primary": True,
                            "say": f"Dry run everything on the sample (start with {_shown({**args, 'confirm': True})}).",
                            "ask": "Dry run everything on the synthetic shop."})
    elif now == "create":
        found = {"note": "This is the synthetic shop: nothing can be created here. Start on your own data to run the same "
                         "path on your Fabric workspace, or look at the dry run again."}
        actions.append({"kind": "call", "label": "Start on my data", "who": "onto", "tool": TOOL, "arguments": {},
                        "primary": True, "say": "Start on my data (start with no arguments; it lists my workspaces).",
                        "ask": "Start Krusgraph on my own Fabric data."})
        back = _start_args(c, "dry_run")
        actions.append({"kind": "call", "label": "Show the dry run again", "who": "onto", "tool": TOOL, "arguments": back,
                        "secondary": True,
                        "say": f"Show the dry run again (start with {_shown(back)}).", "ask": "Show the dry run again."})
    if c.get("decisions") and now in ("dry_run", "create"):
        found["decided"] = [_decided_line(x) for x in c["decisions"] if isinstance(x, dict)]
    pic = {}
    if now in ("check", "decide"):                       # WB13 (#71): the small map of the shop
        taken = {str(x.get("item")): str(x.get("review")) for x in c.get("decisions") or [] if isinstance(x, dict)}
        tables = [{"name": t["name"], "key": list(t.get("key") or []), "key_rule": t.get("key_rule") or "K3",
                   "columns": len(t.get("columns") or [])} for t in p["tables"]]
        rels = [{"id": f"{r['source']}.{'+'.join(r['source_cols'])}>{r['target']}", "source": r["source"],
                 "source_cols": list(r["source_cols"]), "target": r["target"], "target_cols": list(r["target_cols"]),
                 "rule": r["rule"], "review": "accepted"} for r in p["relationships"]]
        for x in decisions:                              # the open suggestion is a link too, dashed until accepted
            src, _, tgt = x["item"][4:].partition(">")
            t, _, col = src.partition(".")
            sug = next((s_ for s_ in p["suggestions"] if s_["table"] == t and s_["column"] == col), {})
            rels.append({"id": f"{t}.{col}>{tgt}", "source": t, "source_cols": [col], "target": tgt,
                         "target_cols": list(sug.get("target_cols") or []), "rule": "R5", "review": "proposed"})
        pic = start_map(tables, rels, {x["item"] for x in decisions if x["state"] == "open"}, taken)
    nxt = _next_key(now)
    out = {"flow": PROMPT_TITLE, "sample": True, "step": {"n": n, "of": len(STEPS), "key": key, "title": title, "does": does,
                                                         "short": SHORT[key]}, "stage": now, "who": WHO[key],
           "path": _path(key, sample=True), "found": found,
           "note": "Synthetic shop sample (fabric_backend/seed.py): no Fabric is read and nothing is created.",
           "actions": actions, **({"lines": lines} if lines else {}), **pic}
    out["done_line"] = _finished(out["path"])
    # SM1: each sample step says its own sentence, as on your own data. Without one the card fell back to the coach's
    # line, which on the sample is the step before's.
    out["say"] = SAMPLE_SAY.get(now, "")
    if now == "check":                                   # SM2: the first line is the sentence; the others under it
        out["say"], out["lines"] = lines[0], lines[1:]
    if now == "dry_run" and run:
        out["say"] = "Dry run done on the shop. Nothing was created."
    if now == "decide" and decisions:
        out["say"] = (("One link needs you." if len(waiting) == 1 else f"{len(waiting)} links need you.") if waiting
                      else "Every decision is answered. Go on to the dry run.")
    _honest(out, now == "check")
    if nxt and now != "create":
        args = _start_args(c, nxt)
        out["after"] = {"tool": TOOL, "arguments": args, "label": f"Next: {SHORT[STAGE[nxt]]}",
                        "say": f"Next step (start with {_shown(args)}).", "ask": f"Next: {SHORT[STAGE[nxt]]}."}
        if (now == "decide" and waiting) or (now == "dry_run" and not run):   # the step's own buttons come first
            out["after"]["secondary"] = True
            if now == "decide":
                out["after"]["why"] = "Next leaves the open decision open."
        out["actions"].append({"kind": "next", "label": out["after"]["label"], "who": "onto", "tool": TOOL,
                               "arguments": args, "say": out["after"]["say"], "ask": out["after"]["ask"],
                               **({"secondary": True} if out["after"].get("secondary") else {})})
    out["summary"] = f"Step {n} of {len(STEPS)} on the synthetic shop: {title}."
    return out


YES = ("yes", "y", "true", "1", "sample", "ja", "on")
NO = ("", "no", "n", "false", "0", "off", "nej")


def wants_sample(answer) -> bool:
    """WB12 (#75): the prompt's field: yes/true (and the like) for the sample; empty, no or false for your own data.
    Anything else is read as your own data, the path that asks before it reads anything."""
    return str(answer if answer is not None else "").strip().lower().rstrip(".!") in YES


def prompt_text(sample: bool = False) -> str:
    """The `start` prompt's user message (prompts/get)."""
    if sample:
        return ("Start Krusgraph on the synthetic shop sample (the start tool with sample=true) and lead me through "
                "each step, one at a time.")
    return ("Start Krusgraph (the start tool) and lead me through it one step at a time: my data (workspace, source "
            "and schema), the check (the map, the rows and the doubled totals), my decisions and a dry run of what "
            "would be built. Create nothing unless I confirm the names after the dry run.")
