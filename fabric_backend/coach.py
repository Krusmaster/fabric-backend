"""The coach: one guided path, said the way the home page's demo chat says it (round CO1).

Gustav, 19 November 2026, after testing Krusgraph in claude.ai on his phone: "vi behöver göra det mer enkelt som
användare. Och jag vill kunna bli coachad precis som i demochatten på hemsidan krusgraph.com" (make it simpler for the
user, and coach me exactly like the demo chat on the home page). What the demo chat does that is copied here is listed
in docs/COACHING.md.

What this module does. `coach(tool, call, answer, checks, steps)` reads where the user is on the path from the tool just
called, its arguments and its answer (the plan state of next_rules.state), and returns:

- the stage: "Step N of 9: <step>", the start path's own numbering (step_of maps the eight STAGES onto the nine steps);
- one mascot line in plain words: what happens now and why (the mascots and their voice are the site's: Onto points
  the way, the Thinker reads and checks, the Builder builds);
- ONE primary next step and at most two secondary ones, each as next_rules shapes a step (label, tool, arguments, say,
  ask), or as a sentence for the chat where a card may not run that tool;
- `text`: a short, stable block for the host model ("Coach"), added to every tool result's text, so the assistant
  coaches the same way where no card is drawn.

No LLM and no guessing: the texts are templates, chosen by fixed rules from the plan state; the same state always gives
the same coach. The rules, in order (each gives exactly one primary step):

1. An error: stay on the stage; the primary step is `start` with what is known, which says where the user is.
2. No workspace: Choose data (start). A workspace but no source: Choose data (start with the workspace). A source but
   no schema: Choose data (start, which lists the schemas).
3. Data chosen, tables not read (a listing tool, or start before its map): Read the tables (plan_backend).
4. Read, not counted against the rows: Check the links against the rows (validate_plan).
5. Counted, and something waits for a person (next_rules: a key that repeats, open links, links that point at nothing,
   doubled amounts): next_rules' most useful step is the primary one.
6. Counted and nothing open: the build path, a dry run before each creating call, then the call that creates it (only on
   the user's yes): silver and gold (create_pipeline) -> the semantic model -> the data agent -> Done.
7. Done: the primary step is a new round on another schema (start with the workspace); there is always a next click.

A primary step is never the call just made (the same tool with the same distinguishing arguments), unless the call
failed. Texts that are the same as the demo chat's for the same step are in DEMO, and tests/test_co1_coach.py checks that
each still appears word for word in static/chat-demo.js, so the site and the product say the same thing.
"""
from __future__ import annotations

import json

# (key, the name the user sees, who says it, the pose)
STAGES = (
    ("data", "Choose data", "onto", "point"),
    ("read", "Krusgraph reads the tables", "thinker", "think"),
    ("check", "Check the links against the rows", "thinker", "notice"),
    ("decide", "You decide the open links", "thinker", "notice"),
    ("build", "Build silver and gold", "builder", "explain"),
    ("model", "Semantic model", "builder", "explain"),
    ("agent", "Data agent", "builder", "explain"),
    ("done", "Done", "onto", "celebrate"),
)
KEYS = tuple(s[0] for s in STAGES)
M = len(STAGES)
NAMES = {"onto": "Onto", "thinker": "Thinker", "builder": "Builder"}

# The demo chat's own words (static/chat-demo.js), where the step is the same. Checked word for word by the tests.
DEMO = {
    "connect": "how its tables connect",
    "keys": "Finding the keys",
    "count": "Counting links against the rows",
    "decide": "The count supports it, and you decide.",
    "flow": "Bronze to silver to gold",
    "model": "For reports in Power BI: tables, links and measures.",
    "next": "What next?",
}

# One plain sentence per stage: what happens now, and why. No tool names, no rule codes.
LINE = {
    "data": "Hi! Pick your workspace and the lakehouse your tables are in, and I will show " + DEMO["connect"] + ".",
    "read": DEMO["keys"] + " and the links between your tables. I only read; nothing is changed.",
    "check": DEMO["count"] + ", so nothing is built on a guess.",
    "decide": "A few links need you: I show the counts. " + DEMO["decide"],
    "build": DEMO["flow"] + ": you see a dry run first, and nothing is created until you say yes.",
    "model": DEMO["model"] + " A dry run first, then it is created on your yes.",
    "agent": "A data agent answers questions about your data in Fabric, with the checked links as its instructions.",
    "done": "That is the whole path: checked links, silver and gold, a semantic model and a data agent.",
    "error": "That did not work. I say why in one sentence, and we go on from where you are.",
    "built": "Done: it is created in Fabric. Next comes the {next}.",
    "dry_run": "That was a dry run: nothing was created. Say yes and it is created in Fabric with these names.",
}

# Which stage a tool's call belongs to (a tool not listed: read when a schema is known, else data).
TOOL_STAGE = {
    "list_workspaces": "data", "list_sources": "data", "list_tables": "data", "sample_rows": "data",
    "plan_backend": "read", "ontology_draft": "read", "domain_draft": "read", "dbt_schema": "read",
    "data_dictionary": "read", "graph_analysis": "read", "join_path": "read", "sap_tables": "read",
    "validate_plan": "check", "suggest_relationships": "check", "requirements_draft": "check",   # RQ1: it counts the joins
    "review_plan": "decide", "save_review": "decide",
    "gold_views_draft": "build", "create_pipeline": "build", "create_views": "build", "create_backend": "build",
    "create_ontology": "build",
    "semantic_model_draft": "model", "create_semantic_model": "model", "compare_semantic_model": "model",
    "create_report": "model",
    "create_data_agent": "agent",
}
START_STAGE = {"workspace": "data", "source": "data", "schema": "data", "map": "read", "check": "check",
               "decide": "decide", "totals": "decide", "dry_run": "build", "create": "build"}
# The build path after a clean check: (stage, creating tool, the name's key in start_flow.build_names, label)
BUILD_PATH = (
    ("build", "create_pipeline", "Build silver and gold"),
    ("model", "create_semantic_model", "Create the semantic model"),
    ("agent", "create_data_agent", "Create the data agent"),
)
BUILD_OF = {t: i for i, (_, t, _) in enumerate(BUILD_PATH)}
# The drafts that come before a build stage's dry run
DRAFT_BEFORE = {"gold_views_draft": 0, "semantic_model_draft": 1}
SECONDARY = 2
TEXT_MAX = 700


def _carry(call: dict, answer: dict) -> dict:
    out = {k: call[k] for k in ("workspace", "source", "schema", "keys", "confirmed") if call.get(k) not in (None, "", [], {})}
    if isinstance(answer, dict):
        chosen = answer.get("chosen") if isinstance(answer.get("chosen"), dict) else {}
        for k in ("workspace", "source", "schema"):
            if k not in out and isinstance(chosen.get(k), str) and chosen[k]:
                out[k] = chosen[k]
        if "schema" not in out and isinstance(answer.get("schema_chosen"), str) and answer["schema_chosen"]:
            out["schema"] = answer["schema_chosen"]
    plan = call.get("plan") if isinstance(call.get("plan"), dict) else {}
    for k in ("keys", "confirmed"):
        if k not in out and plan.get(k):
            out[k] = plan[k]
    return out


def _sentence(label: str, tool: str, args: dict, ask: str = "") -> dict:
    shown = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())
    return {"label": label, "say": f"{label} ({tool}" + (f" with {shown}" if shown else "") + ").",
            "ask": ask or f"{label}.", "why": "", "coach_tool": tool, "coach_arguments": dict(args)}


def _start(label: str, base: dict, step: str = "", ask: str = "") -> dict:
    args = {k: base[k] for k in ("workspace", "source", "schema") if base.get(k)}
    plan = {k: base[k] for k in ("keys", "confirmed") if base.get(k)}
    if plan:
        args["plan"] = plan
    if step:
        args["step"] = step
    return _sentence(label, "start", args, ask)


def _step(label: str, tool: str, args: dict, why: str = "") -> dict:
    from .next_rules import _step as nr_step
    s = nr_step(label, tool, args, why)
    return {**s, "coach_tool": tool, "coach_arguments": dict(args)}


def _build_step(i: int, base: dict, dry_run: bool) -> dict:
    from .start_flow import build_names
    stage, tool, label = BUILD_PATH[i]
    names = build_names(base.get("source"), base.get("schema"))
    keep = ("workspace", "source", "schema", "keys", "confirmed")
    args = {**{k: v for k, v in base.items() if k in keep}, "name": names[tool], "dry_run": dry_run}
    if dry_run:
        return _step(f"{label} (dry run first)", tool, args, "A dry run shows what would be created and creates nothing.")
    s = _sentence(f"{label} in Fabric", tool, args,
                  ask=f"{label} in Fabric with the name {names[tool]}, as the dry run showed.")
    s["writes"] = True
    return s


def _done_step(base: dict) -> dict:
    return _start("Start again on another schema", {k: base[k] for k in ("workspace", "source") if base.get(k)},
                  ask="Start again on another schema.")


def _is_same(tool: str, call: dict, s: dict) -> bool:
    t = s.get("coach_tool") or s.get("tool")
    if t != tool:
        return False
    a = s.get("coach_arguments") or s.get("arguments") or {}
    if tool == "start":
        return (a.get("step") or "") == (call.get("step") or "") and all(
            (a.get(k) or "") == (call.get(k) or "") for k in ("workspace", "source", "schema"))
    from .next_rules import DISTINCT
    return all(bool(a.get(k)) == bool(call.get(k)) for k in DISTINCT if k != "dry_run") and \
        a.get("dry_run", True) == call.get("dry_run", True)


def _from_rules(tool: str, call: dict, answer: dict, checks: dict | None, steps: list | None) -> list[dict]:
    if steps is not None:
        return [s for s in steps if isinstance(s, dict)]
    from . import next_rules
    try:
        return next_rules.steps(tool, call, answer, checks)
    except Exception:                                                # noqa: BLE001 - the coach stands without them
        return []


def _open_issue(st: dict) -> bool:
    return bool(st.get("open") or st.get("failed_keys") or st.get("failed_links") or st.get("amounts"))


def plan(tool: str, call: dict | None, answer, checks: dict | None = None, steps: list | None = None) -> dict:
    """{stage, primary, secondary}: the rules in the module's docstring. `steps` are next_rules' steps when the caller
    has them already (the card's `next`)."""
    call = {k: v for k, v in (call or {}).items() if k != "ctx"}
    answer = answer if isinstance(answer, dict) else {}
    base = _carry(call, answer)
    error = bool(answer.get("error"))
    if tool == "start" and not error:
        stage = START_STAGE.get(str((answer.get("step") or {}).get("key") or ""), "data")
    else:
        stage = TOOL_STAGE.get(tool) or ("read" if base.get("schema") else "data")
    rules = []
    if error:
        primary = _start("Show where we are", base, ask="Show where we are on the path.")
        if tool == "start":                                          # start failed: begin again from nothing
            primary = _start("Start again", {}, ask="Start Krusgraph again.")
        acts = [a for a in answer.get("actions") or [] if isinstance(a, dict) and a.get("label")]
        if acts and tool.startswith("create_"):                                                     # the error's own action (Check status) first
            return {"stage": stage, "primary": _from_action(acts[0]), "secondary": [], "error": True}
        known = [s for s in steps or [] if isinstance(s, dict) and s.get("label")]
        if known:                                                    # the error's own way on (n220) comes first
            return {"stage": stage, "primary": known[0], "secondary": known[1:1 + SECONDARY], "error": True}
        return {"stage": stage, "primary": primary, "secondary": [], "error": True}
    if tool == "start":                                              # the guided path's own step comes first
        acts = [a for a in answer.get("actions") or [] if isinstance(a, dict) and a.get("label")]
        after = answer.get("after") if isinstance(answer.get("after"), dict) else None
        if not acts and after:
            acts = [after]
        out = [_from_action(a) for a in acts]
        if not out:
            out = [_start("Choose a workspace", {}, ask="Show my workspaces.")]
        return {"stage": stage, "primary": out[0], "secondary": out[1:1 + SECONDARY]}
    if not base.get("workspace"):
        return {"stage": "data", "primary": _start("Choose a workspace", {}, ask="Show my workspaces."), "secondary": []}
    if not base.get("source"):
        return {"stage": "data", "primary": _start("Choose the lakehouse", base, ask="Show the lakehouses in this workspace."),
                "secondary": []}
    if stage == "data":
        if not base.get("schema"):
            return {"stage": "data", "primary": _start("Choose the schema", base, ask="Show the schemas."), "secondary": []}
        keep = {k: base[k] for k in ("workspace", "source", "schema")}
        return {"stage": "data", "primary": _step("Read the tables", "plan_backend", keep,
                                                  "Finds the keys and the links, with the rule behind each."),
                "secondary": [_start("Choose another schema", {k: base[k] for k in ("workspace", "source")})]}
    from . import next_rules
    st = next_rules.state(tool, call, answer, checks)
    rules = [s for s in _from_rules(tool, call, answer, checks, steps) if not _is_same(tool, call, s)]
    build_labels = ("Create the", "Draft the gold views", "Create the pipeline")
    fix = [s for s in rules if not str(s.get("label", "")).startswith(build_labels)]
    if st["checked"] is not True and tool not in BUILD_OF and tool not in DRAFT_BEFORE:
        keep = {k: v for k, v in base.items() if k in ("workspace", "source", "schema", "keys", "confirmed")}
        primary = _step("Check against the rows", "validate_plan", keep,
                        "Counts each key and link in the rows first: nothing is built on a guess.")
        own = [s for s in rules if s.get("label") == "Check against the rows"]
        if own:                                                      # next_rules' own step, with its words
            primary = {**own[0], "coach_tool": "validate_plan", "coach_arguments": own[0].get("arguments") or keep}
        rest = [s for s in rules if s.get("label") != "Check against the rows"]
        return {"stage": stage, "primary": primary, "secondary": rest[:SECONDARY]}
    if _open_issue(st) and not fix:                                  # the fix was just asked for: the decisions
        return {"stage": "decide", "primary": _start("Decide the open links", base, step="decide",
                                                     ask="Show each open link with Accept, Reject and Skip."),
                "secondary": []}
    if _open_issue(st) and fix:
        stage = "decide" if stage in ("read", "check") else stage
        more = fix[1:] + [s for s in rules if s not in fix]
        return {"stage": stage, "primary": fix[0], "secondary": more[:SECONDARY]}
    # the build path
    dry = call.get("dry_run", True) is not False
    own_acts = [a for a in answer.get("actions") or [] if isinstance(a, dict) and a.get("label")] \
        if tool.startswith("create_") else []
    if tool in BUILD_OF:
        i = BUILD_OF[tool]
        if dry:
            primary = _from_action(own_acts[0]) if own_acts else _build_step(i, base, dry_run=False)
            primary["writes"] = True
            sec = [_build_step(i + 1, base, dry_run=True)] if i + 1 < len(BUILD_PATH) else [_done_step(base)]
            return {"stage": stage, "primary": primary, "secondary": sec, "dry_run": True}
        if i + 1 < len(BUILD_PATH):
            return {"stage": BUILD_PATH[i][0], "primary": _build_step(i + 1, base, dry_run=True), "secondary": [],
                    "built": True}
        return {"stage": "done", "primary": _done_step(base), "secondary": [], "built": True}
    if tool in DRAFT_BEFORE:
        i = DRAFT_BEFORE[tool]
        return {"stage": BUILD_PATH[i][0], "primary": _build_step(i, base, dry_run=True), "secondary": []}
    if tool in ("create_backend", "create_ontology", "create_report") and not dry:
        return {"stage": stage, "primary": _build_step(2, base, dry_run=True), "secondary": []}
    # checked, nothing open: the first build stage
    sec = [s for s in rules if s.get("tool") == "gold_views_draft"][:1]
    return {"stage": "build" if stage in ("read", "check", "decide") else stage,
            "primary": _build_step(0, base, dry_run=True), "secondary": sec}


# WB15 (B): one path and one total everywhere. The stages sit on the start path's nine steps (start_flow.STEPS), so a
# card from any tool, the start card and the text Claude is asked to write all say "Step N of 9", and the number never
# goes back: choose (1-3), the map (4), the check (5), your decisions (6), the dry runs and builds (8), done (9).
STAGE_STEP = {"read": 4, "check": 5, "decide": 6, "build": 8, "model": 8, "agent": 8, "done": 9}


def step_of(stage: str, tool: str, call: dict | None, answer) -> tuple[int, int]:
    """(n, 9): the step of the start path this result is on."""
    from .start_flow import KEYS as PATH
    of = len(PATH)
    st = answer.get("step") if tool == "start" and isinstance(answer, dict) else None
    if isinstance(st, dict) and isinstance(st.get("n"), int):
        return st["n"], of
    if stage == "data":
        base = _carry(call or {}, answer if isinstance(answer, dict) else {})
        return (1 if not base.get("workspace") else 2 if not base.get("source") else 3), of
    return STAGE_STEP.get(stage, 4), of


def own_action(tool: str, answer) -> dict | None:
    """The answer's own primary button: an action marked primary (n227: Check against the rows on a plan), or a
    creating tool's first action (Create, Check status). None when the answer has none."""
    acts = [a for a in (answer.get("actions") if isinstance(answer, dict) else None) or [] if isinstance(a, dict) and a.get("label")]
    for a in acts:
        if a.get("primary") is True:
            return a
    if acts and tool.startswith("create_"):
        return acts[0]
    return None


def _from_action(a: dict) -> dict:
    """A start action as a coach step: the tool and its arguments kept, so a card can run it where it may."""
    out = {k: a[k] for k in ("label", "say", "ask", "tool", "arguments", "why") if k in a}
    out.setdefault("say", f"{a['label']}.")
    out.setdefault("ask", f"{a['label']}.")
    if a.get("tool"):
        out["coach_tool"] = a["tool"]
        out["coach_arguments"] = a.get("arguments") or {}
    return out


def _clean(s: dict, primary: bool = False, can_build: bool = True) -> dict:
    """A step in next_rules' shape (what the cards' renderNext draws): a runnable call keeps tool and arguments, a
    sentence has neither."""
    from .mcp_apps_next import DRY_RUN_TOOLS, STEP_TOOLS
    out = {k: s[k] for k in ("label", "tool", "arguments", "why", "say", "ask") if k in s}
    args = out.get("arguments") if isinstance(out.get("arguments"), dict) else None
    runnable = args is not None and ((out.get("tool") in STEP_TOOLS and args.get("dry_run") is not False)
                                     or (can_build and out.get("tool") in DRY_RUN_TOOLS and args.get("dry_run") is True))
    if not runnable:
        out.pop("tool", None)
        out.pop("arguments", None)
    if primary:
        out["primary"] = True
    return out


def coach(tool: str, call: dict | None, answer, checks: dict | None = None, steps: list | None = None) -> dict:
    """The coach for one tool result: {n, of, stage, title, who, name, pose, line, primary, secondary, text}."""
    p = plan(tool, call, answer, checks, steps)
    lead = own_action(tool, answer)
    if lead is not None and not p.get("error"):                     # the card's own primary button (n227) stays it
        rest = [p["primary"]] + list(p["secondary"])
        p = {**p, "primary": {**_from_action(lead), "writes": bool(p["primary"].get("writes")) and tool.startswith("create_")},
             "secondary": [x for x in rest if x.get("label") != lead.get("label")]}
    i = KEYS.index(p["stage"])
    key, title, who, pose = STAGES[i]
    n, of = step_of(key, tool, call, answer)
    if p.get("error"):
        line, pose = LINE["error"], "explain"
    elif p.get("dry_run"):
        line, who, pose = LINE["dry_run"], "builder", "explain"
    else:
        line = LINE[key]
    if p.get("built") and key != "done":
        nxt = STAGES[i + 1][1].lower() if i + 1 < M else "end"
        line, who, pose = LINE["built"].format(next=nxt), "builder", "celebrate"
    build = tool != "review_plan"                                    # review_plan's card names no creating tool
    primary = _clean(p["primary"], primary=True, can_build=build)
    secondary = [_clean(s, can_build=build) for s in p["secondary"] if s.get("label") != primary.get("label")][:SECONDARY]
    st = answer.get("step") if tool == "start" and isinstance(answer, dict) and isinstance(answer.get("step"), dict) else None
    if st and not p.get("error"):                                    # WB15 (B, F): the start card's own step and words
        from .start_flow import SHORT, WHO
        title = SHORT.get(str(st.get("key")), title)
        who = WHO.get(str(st.get("key")), who)
        if isinstance(answer.get("say"), str) and answer["say"].strip():
            line = answer["say"].strip()
    out = {"n": n, "of": of, "stage": key, "title": title, "who": who, "name": NAMES[who], "pose": pose,
           "line": line, "primary": primary, "secondary": secondary,
           "writes": bool(p["primary"].get("writes"))}
    out["text"] = text(out, p["primary"], [s for s in p["secondary"]][:SECONDARY])
    return out


def _call_of(s: dict) -> str:
    tool = s.get("coach_tool") or s.get("tool") or ("start" if isinstance(s.get("start"), dict) else "")
    args = s.get("coach_arguments") or s.get("arguments") or s.get("start") or {}
    if not tool:                                                     # a sentence for the chat: the sentence itself
        return json.dumps(s.get("ask") or s.get("label") or "", ensure_ascii=False)
    short = {k: v for k, v in args.items() if k in ("workspace", "source", "schema", "step", "name", "dry_run", "fixes", "tables")}
    return f"{tool}({', '.join(f'{k}={json.dumps(v, ensure_ascii=False)}' for k, v in short.items())})"


def text(c: dict, primary: dict, secondary: list) -> str:
    """The Coach block: short and stable, the same words for the same state. DIR1 (directory review criteria, 20 Nov
    2026): it states where the user is and the options, as facts; it gives the model no instructions. The choice of what
    to do next stays with the user and Claude."""
    lines = [f"Coach (step {c['n']} of {c['of']}: {c['title']})",
             f"Where the user is, in plain words: {c['line']}",
             f"Possible next step for the user: {primary['label']} ({_call_of(primary)})."]
    if c.get("writes"):
        lines.append("That step creates items in Fabric; Krusgraph creates nothing without dry_run=false and the "
                     "user's yes to the names.")
    if secondary:
        lines.append("Other options: " + "; ".join(s["label"] for s in secondary) + ".")
    lines.append("Where a card is drawn, it already shows this result's lists and counts.")
    out = "\n".join(lines)
    if len(out) > TEXT_MAX:                                          # a long call: the label alone
        lines[2] = (f"Possible next step for the user: {primary['label']} "
                    f"({primary.get('coach_tool') or primary.get('tool') or 'chat'}).")
        out = "\n".join(lines)[:TEXT_MAX]
    return out


def next_steps(c: dict) -> list[dict]:
    """The card's buttons: the primary step first, then at most two secondary ones."""
    return [c["primary"]] + list(c["secondary"])[:SECONDARY]


def card(c: dict) -> dict:
    """What a card draws: the coach without the text block."""
    return {k: c[k] for k in ("n", "of", "stage", "title", "who", "name", "pose", "line")}
