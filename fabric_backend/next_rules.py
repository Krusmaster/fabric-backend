"""The one most useful next step, by fixed rules from the plan state (round WB13, issue #91).

Gustav's phone test in claude.ai on 19 November 2026: "man kan liksom inte komma vidare i processen riktigt" (you cannot
really get further in the process). After "Draft a semantic model" the card ended with no next step, and the ontology
and review cards looped between the same three buttons (Check against the rows, Review keys and links, Draft a semantic
model).

What this module does. `state(tool, call, answer, checks)` reads the plan state from what a card has: validate_plan's
check rows (mcp_apps_next.check_rows), review_plan's items (review.needs_decision decides which wait for a person), or,
for any other tool, only whether this call counted the rows (validate=true). `steps(tool, call, answer, checks)` then
applies the rules below in order, keeps at most four steps and marks the first as the primary one. No AI and no
guessing: the same state always gives the same steps.

The rules, in order:
1. Not checked against the rows (or not known): "Check against the rows" (validate_plan). A key that repeats or is
   empty: "Propose a fix per failure" (validate_plan with fixes=true).
2. Open decisions: "Decide the N open links": the start card's step 6 with Accept, Reject and Skip per link and the
   counted evidence (start_flow, #66). A host runs it in the chat (a `say` step), where the start card draws it.
3. A link with rows that point at nothing: "Show what points at nothing": validate_plan with fixes=true for the tables
   concerned. It counts them and proposes the fix (quarantine in silver, or a NULL reference); it changes nothing.
   The decision itself (accept with quarantine, or reject) is made in step 2.
4. Header amounts that repeat on every line: "Use the line amounts": the doubled totals, with one sentence of why.
5. Checked and nothing open: the build path, each a dry run first (nothing is created by the step): the semantic model,
   the gold views (a draft), the data agent and the pipeline. A card's buttons run only the read and draft tools and the
   build card's dry runs (mcp_apps_next STEP_TOOLS, DRY_RUN_TOOLS); the data agent's and the pipeline's dry runs are
   sentences for the chat, which Claude runs as dry runs. After a draft of an ontology the ontology's own dry run
   comes first; after a draft of a semantic model, the model's.
A step is never the call the user just made (the same tool and the same distinguishing arguments) unless something
changed, and a step a card cannot run (a creating tool on review_plan's card) becomes a sentence for the chat.
"""
from __future__ import annotations

import json

MAX = 4
CHECK = ("validate_plan",)
# The tools whose answer carries the next steps (mcp_apps.structured adds them as `next`, structuredContent only).
TOOLS = ("plan_backend", "validate_plan", "review_plan", "ontology_draft", "semantic_model_draft", "domain_draft",
         "dbt_schema", "gold_views_draft", "create_semantic_model", "create_ontology", "create_backend")
# What distinguishes one call of a tool from another for "the step the user just did".
DISTINCT = ("fixes", "detail", "validate", "tables", "dry_run")
WHY = {
    "check": "Counts each key and link in the rows first: nothing is built on a guess.",
    "keys": "A key that repeats or is empty makes every link to its table unsure; the fix is proposed, nothing changes.",
    "decide": "Each one waits for your Accept, Reject or Skip, with the counts underneath. Deciding writes nothing to Fabric.",
    "orphans": "Counts the rows and proposes the fix: in silver they go to quarantine with the reason, so nothing is lost.",
    "amounts": ("A header amount repeats on every line of its header, so a sum over the lines counts it again. Sum the "
                "line amounts instead, or take the header amount once per header."),
    "model": "A dry run: it shows what would be created and creates nothing.",
    "gold": "A draft of the gold views on silver: SQL to read, nothing is created.",
    "agent": "A dry run of the Fabric data agent with the plan as its instructions.",
    "pipeline": "A dry run of the pipeline: silver and gold notebooks and the check, in one run.",
    "ontology": "A dry run of the ontology you just drafted: it creates nothing.",
}


def _base(call: dict, answer: dict) -> dict:
    out = {k: call[k] for k in ("workspace", "source", "schema", "keys", "confirmed") if call.get(k) not in (None, "", [], {})}
    chosen = answer.get("schema_chosen") if isinstance(answer, dict) else None
    if chosen and "schema" not in out:
        out["schema"] = chosen
    return out


def _link_of(item: dict) -> dict:
    return {"source": item["source"], "source_cols": list(item["columns"]), "target": item["target"],
            "target_cols": list(item.get("target_columns") or [])}


# ------------------------------------------------------------------ the plan state ------------------------------------

def state(tool: str, call: dict, answer: dict, checks: dict | None = None) -> dict:
    """{checked: True | False | None, open: [ids], failed_links: [labels], failed_tables: [tables], amounts: n}.
    checked None means this card cannot know (a draft that did not count the rows)."""
    from . import review as _review
    confirmed = {(c.get("source", "").lower(), tuple(x.lower() for x in c.get("source_cols") or []), c.get("target", "").lower())
                 for c in call.get("confirmed") or [] if isinstance(c, dict)}
    st = {"checked": None, "open": [], "failed_links": [], "failed_tables": [], "amounts": 0, "failed_keys": []}
    if tool == "validate_plan" and isinstance(answer.get("totals"), dict):
        st["checked"] = True
        rows = [x for x in (checks or {}).get("rows") or [] if isinstance(x, dict)]
        for x in rows:
            if x.get("kind") == "key" and x.get("state") == "failed":
                st["failed_keys"].append(x.get("id", ""))
            if x.get("kind") == "link" and x.get("state") == "failed":
                st["failed_links"].append(x.get("label", ""))
                st["failed_tables"].append(str(x.get("id", "")).split(":", 1)[-1].split(".", 1)[0])
            if x.get("kind") == "amount" and x.get("state") == "failed":
                st["amounts"] += 1
            if x.get("kind") == "link" and not x.get("other"):
                rid = str(x.get("id", ""))
                src, _, tgt = rid[4:].partition(">")
                s_t, _, cols = src.partition(".")
                item = {"type": "relationship", "review": "proposed", "rule": x.get("rule"),
                        "check": {"status": {"failed": "failed"}.get(x.get("state"), "passed")}}
                if (s_t.lower(), tuple(c.lower() for c in cols.split("+")), tgt.lower()) in confirmed:
                    continue
                if _review.needs_decision(item):
                    st["open"].append(rid)
        if not rows:                                                 # the summary alone: what it says failed
            t = answer["totals"]
            if int((t.get("keys") or {}).get("failed") or 0):
                st["failed_keys"] = [f"key:{k.get('table')}" for k in (answer.get("attention") or {}).get("keys") or []
                                     if isinstance(k, dict)] or ["key"]
            st["amounts"] = int((t.get("amount_levels") or {}).get("failed") or 0)
            for r in (answer.get("attention") or {}).get("relationships") or []:
                if isinstance(r, dict) and int(r.get("orphans") or 0):
                    st["failed_links"].append(f"{r['source']}.{'+'.join(r['columns'])} → {r['target']}")
                    st["failed_tables"].append(r["source"])
    elif tool == "review_plan" and isinstance(answer.get("review"), dict):
        rv = answer["review"]
        items = [it for it in rv.get("items") or [] if isinstance(it, dict)]
        counted = [it for it in items if (it.get("check") or {}).get("status", "not_checked") != "not_checked"]
        st["checked"] = bool(counted)
        st["open"] = [it["id"] for it in _review.open_decisions(rv)]
        st["failed_keys"] = [it["id"] for it in items if it.get("type") == "key"
                             and (it.get("check") or {}).get("status") == "failed" and it.get("review") != "rejected"]
        for it in items:
            if it.get("type") == "relationship" and (it.get("check") or {}).get("status") == "failed" \
                    and it.get("review") != "rejected":
                st["failed_links"].append(f"{it['source']}.{'+'.join(it['columns'])} → {it['target']}")
                st["failed_tables"].append(it["source"])
        st["amounts"] = int(((rv.get("other_checks") or {}).get("header_amounts") or {}).get("repeat_on_every_line") or 0)
    elif call.get("validate") is True:
        st["checked"] = True
    st["failed_tables"] = sorted(set(t for t in st["failed_tables"] if t), key=str.lower)
    return st


# ------------------------------------------------------------------ the steps -----------------------------------------

def _step(label: str, tool: str, arguments: dict, why: str, ask: str = "") -> dict:
    shown = ", ".join(f"{k}={v!r}" for k, v in arguments.items()
                      if k in ("source", "schema", "detail", "fixes", "validate", "name", "dry_run", "tables"))
    return {"label": label, "tool": tool, "arguments": dict(arguments), "why": why,
            "say": f"{label} ({tool}" + (f" with {shown}" if shown else "") + ").", "ask": ask or f"{label}."}


def _decide(base: dict, n: int, call: dict) -> dict:
    """A sentence for the chat that starts the start card's step 6 (a card cannot draw another card)."""
    args = {k: base[k] for k in ("workspace", "source", "schema") if base.get(k)}
    plan = {k: base[k] for k in ("keys", "confirmed") if base.get(k)}
    if plan:
        args["plan"] = plan
    args["step"] = "decide"
    label = f"Decide the {n} open {'link' if n == 1 else 'links'}"
    return {"label": label, "why": WHY["decide"],
            "say": f"{label} (start with " + ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items()) + ").",
            "ask": f"{label}: show each with Accept, Reject and Skip and the counts underneath.",
            "start": args}


def _names(base: dict) -> dict:
    from .start_flow import build_names
    return build_names(base.get("source"), base.get("schema"))


def _same(tool: str, call: dict, step: dict) -> bool:
    """The step is the call the user just made: the same tool and the same distinguishing arguments."""
    if step.get("tool") != tool:
        return False
    a = step.get("arguments") or {}
    return all(bool(a.get(k)) == bool(call.get(k)) for k in DISTINCT if k != "dry_run") and \
        (a.get("dry_run", True) == call.get("dry_run", True))


def steps(tool: str, call: dict, answer: dict, checks: dict | None = None, can_build: bool = True) -> list[dict]:
    """The next steps for one answer, most useful first (the first has primary=True), at most MAX. `can_build` False
    (review_plan's card, which names no creating tool) turns a dry run into a sentence for the chat."""
    call = {k: v for k, v in (call or {}).items() if k != "ctx"}
    if not isinstance(answer, dict) or "workspace" not in call or "source" not in call:
        return []
    base = _base(call, answer)
    st = state(tool, call, answer, checks)
    out: list[dict] = []
    if st["checked"] is not True and tool != "validate_plan":
        out.append(_step("Check against the rows", "validate_plan", base, WHY["check"]))
    if st["failed_keys"]:
        out.append(_step("Propose a fix per failure", "validate_plan", {**base, "fixes": True}, WHY["keys"],
                         ask=f"Propose a fix for the {'key' if len(st['failed_keys']) == 1 else str(len(st['failed_keys'])) + ' keys'} "
                             "that repeat or are empty."))
    if st["open"]:
        out.append(_decide(base, len(st["open"]), call))
    if st["failed_links"]:
        n = len(st["failed_links"])
        out.append(_step("Show what points at nothing", "validate_plan",
                         {**base, "fixes": True, "tables": st["failed_tables"]}, WHY["orphans"],
                         ask=f"Show the {'link' if n == 1 else str(n) + ' links'} with rows that point at nothing, "
                             "and the proposed fix."))
    if st["amounts"]:
        out.append(_step("Use the line amounts", "validate_plan", {**base, "fixes": True}, WHY["amounts"],
                         ask="Show the header amounts that repeat on every line, and sum the line amounts instead."))
    if st["checked"] is not False and not st["open"] and not st["failed_keys"]:
        names = _names(base)
        build = []
        if tool == "ontology_draft":
            build.append(_step("Create the ontology (dry run first)", "create_ontology",
                               {**base, "name": names["create_ontology"], "dry_run": True}, WHY["ontology"]))
        build += [
            _step("Create the semantic model (dry run first)", "create_semantic_model",
                  {**base, "name": names["create_semantic_model"], "dry_run": True}, WHY["model"]),
            _step("Draft the gold views", "gold_views_draft", {k: v for k, v in base.items() if k in ("workspace", "source", "schema", "keys", "confirmed")}, WHY["gold"]),
            _step("Create the data agent (dry run first)", "create_data_agent",
                  {**base, "name": names["create_data_agent"], "dry_run": True}, WHY["agent"]),
            _step("Create the pipeline (dry run first)", "create_pipeline",
                  {**base, "name": names["create_pipeline"], "dry_run": True}, WHY["pipeline"]),
        ]
        out += build
    out = [s for s in out if not _same(tool, call, s)]
    from .mcp_apps_next import DRY_RUN_TOOLS, STEP_TOOLS                # a step no card may run becomes a sentence
    runnable = set(STEP_TOOLS) | (set(DRY_RUN_TOOLS) if can_build else set())
    out = [s if not s.get("tool") or s["tool"] in runnable else _as_sentence(s) for s in out]
    if tool in ("create_semantic_model", "create_ontology", "create_backend") and call.get("dry_run", True) is not False:
        out = [s for s in out if s.get("tool") != tool]               # its own Create is on the card already
    seen, keep = set(), []
    for s in out:
        if s["label"] not in seen:
            seen.add(s["label"])
            keep.append(s)
    keep = keep[:MAX]
    if keep:
        keep[0] = {**keep[0], "primary": True}
    return keep


def _as_sentence(s: dict) -> dict:
    return {"label": s["label"], "say": s["say"], "ask": s["ask"], "why": s.get("why", "")}
