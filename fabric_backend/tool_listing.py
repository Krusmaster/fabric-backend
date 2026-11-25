"""Round SM4 (fewer doors, docs/SMOOTH/PLAN.md row 3): which tools the hosted server lists by default.

Gustav, 19 November 2026: "Simple. Simple. Simple. Smooth!" 48 tools were listed; a person or a model meeting Krusgraph
for the first time saw 48 doors. The default listing now holds the guided path's own tools: Start Krusgraph, the plan,
the check, the review, the six creating tools of a data product, the catalog, the requirements match, the verifier,
lineage and the two GraphQL readers. Every other tool is still registered and still answers a `tools/call` by its name
(the cards' buttons and old prompts keep working); it is only left out of `tools/list`.

- KRUSGRAPH_ADVANCED_TOOLS=1 (an operator setting, off by default) lists every tool, as before SM4.
- The drafts (`semantic_model_draft`, `ontology_draft`, `silver_notebook_draft`, `gold_views_draft`,
  `drift_monitor_draft`, `export_item_definitions`) show what their creating tool's dry run shows; by default a card's
  step that names one of them names that dry run instead (ALIAS), so a button never points at an unlisted tool.
- The listing switches of n123 (KRUSGRAPH_READ_ONLY, KRUSGRAPH_NO_ROW_VALUES) still apply on top: a tool they remove is
  not registered at all.

Deterministic: a fixed list, no AI. The directory listing ("Krusgraph for Microsoft Fabric") is the maintainer's; the
tools that leave the default listing are HIDDEN below and in docs/DIRECTORY-READINESS.md.
"""
from __future__ import annotations

import os
import re

_NAMED = re.compile(r"\(([a-z]+(?:_[a-z]+)+)\b")      # "Label (create_pipeline with ...)": the tool a sentence names

ADVANCED = "KRUSGRAPH_ADVANCED_TOOLS"
CHANGES = "KRUSGRAPH_CHANGES"          # LFD5, LFD6: the change-by-chat tools (propose_change, apply_change), off by default
_ON = {"1", "true", "yes", "on"}

# The default listing, in the guided path's order (16 tools).
DEFAULT = (
    "start",
    "plan_backend", "validate_plan", "review_plan", "requirements_draft",
    "create_pipeline", "create_semantic_model", "create_data_agent", "create_report", "create_backend", "create_ontology",
    "publish_catalog", "verify_build", "lineage", "describe_backend", "query_graphql",
)

# LFD5: with KRUSGRAPH_CHANGES=1 (an operator setting, off by default) the change tools are registered and listed after
# the default ones; off, they are not registered at all and every listing is as before.
CHANGE_TOOLS = ("propose_change", "apply_change")         # LFD6: apply_change, a creating tool


def changes_on(environ=None) -> bool:
    """KRUSGRAPH_CHANGES: the change-by-chat tools (docs/CHANGES.md). Read at import for registration."""
    return (environ if environ is not None else os.environ).get(CHANGES, "").strip().lower() in _ON


def default_names(environ=None) -> tuple[str, ...]:
    """The default listing under the current settings: DEFAULT, and the change tools when KRUSGRAPH_CHANGES is on."""
    return DEFAULT + (CHANGE_TOOLS if changes_on(environ) else ())


# A draft and the creating tool whose dry run shows the same thing (the draft takes no name; the dry run does).
ALIAS = {
    "semantic_model_draft": "create_semantic_model",
    "ontology_draft": "create_ontology",
    "silver_notebook_draft": "create_pipeline",
    "gold_views_draft": "create_pipeline",
    "drift_monitor_draft": "create_pipeline",
}

DRY_RUN_LABEL = {"create_semantic_model": "Dry run the semantic model", "create_ontology": "Dry run the ontology",
                 "create_pipeline": "Dry run the pipeline"}

# One neutral clause for the instructions and the docs (no instruction to the model; DIR1).
CLAUSE = (f"{ADVANCED}=1 lists every tool; by default the listing holds the guided path's tools and the others still "
          "answer when called by name")


def sentence() -> str:
    """The instructions' sentence on the listing: a fact about what tools/list holds, never a request to the model.
    The same text whatever the setting, so the instructions do not depend on where the server runs."""
    names = default_names()
    return (f"By default tools/list holds {len(names)} tools: " + ", ".join(names) + ". The other tools named here "
            f"are registered and answer when called by name; the operator setting {ADVANCED}=1 lists them all. The "
            "drafts show what their creating tool's dry run shows.")


def advanced(environ=None) -> bool:
    return (os.environ if environ is None else environ).get(ADVANCED, "").strip().lower() in _ON


def listed(name: str, environ=None) -> bool:
    """True when `name` is in tools/list under the current setting."""
    return advanced(environ) or name in default_names(environ)


def hidden(names, environ=None) -> list[str]:
    """The tools of `names` that tools/list leaves out under the current setting, sorted."""
    return sorted(n for n in names if not listed(n, environ))


def filter_tools(tools: list, environ=None) -> list:
    """tools/list's entries (objects with .name) under the current setting, in their order."""
    return [t for t in tools if listed(getattr(t, "name", ""), environ)]


# ------------------------------------------------------------------ the cards' last state -----------------------------

# Where a card hands back to the living start card: the step of start that comes after the tool's answer.
_AFTER_DRY_RUN = ("semantic_model_draft", "semantic_view_draft", "ontology_draft", "silver_notebook_draft", "gold_views_draft",
                  "drift_monitor_draft", "export_item_definitions", "create_views", "create_silver_notebook",
                  "create_gold_views", "create_drift_monitor")
_AFTER_CHECK = ("validate_plan", "review_plan", "requirements_draft", "compare_semantic_model", "plan_drift")


def start_step(tool: str, call: dict, answer: dict) -> str:
    """The start step a card for this answer hands back to: data, check, decide, dry_run or done."""
    call = call or {}
    if not (call.get("workspace") and call.get("source")):
        return "data"
    creating = tool.startswith("create_") or tool == "publish_catalog"
    if creating and call.get("dry_run", True) is False and isinstance(answer, dict) and not answer.get("error"):
        return "done"
    if tool == "verify_build":
        return "done"
    if creating or tool in _AFTER_DRY_RUN:
        return "dry_run"
    if tool in _AFTER_CHECK:
        return "decide"
    return "check"


LABEL = {"data": "Back to Start: your data", "check": "Back to Start: check", "decide": "Back to Start: decide",
         "dry_run": "Back to Start: dry run", "done": "Back to Start: what next"}


def hand_back(tool: str, call: dict, answer: dict) -> dict:
    """A step that continues in the living Start Krusgraph card at the right step. A card cannot draw another card, so
    the step is a sentence for the chat (`say`/`ask`), with `start` holding start's arguments, as next_rules' decide."""
    call = {k: v for k, v in (call or {}).items() if k != "ctx"}
    step = start_step(tool, call, answer)
    args = {k: call[k] for k in ("workspace", "source", "schema") if isinstance(call.get(k), str) and call.get(k)}
    if step != "data":
        args["step"] = step
    label = LABEL[step]
    where = " › ".join(args[k] for k in ("workspace", "source", "schema") if k in args)
    ask = f"Go on in Start Krusgraph at {step.replace('_', ' ')}" + (f" for {where}" if where else "") + "."
    return {"label": label, "say": ask, "ask": ask, "start": args, "why": "The guided path continues from here."}


def forward(steps, environ=None) -> bool:
    """True when the steps hold a way on: a button for a listed tool, or a hand-back to Start."""
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        if isinstance(s.get("start"), dict):
            return True
        t = s.get("tool")
        if isinstance(t, str) and listed(t, environ):
            return True
        if isinstance(s.get("url"), str):
            return True
        if not t and any(listed(n, environ) for n in _NAMED.findall(str(s.get("say") or ""))):
            return True                                  # a sentence for the chat naming a listed tool's call
    return False


def default_step(s: dict, environ=None) -> dict | None:
    """A card's step under the default listing: unchanged when its tool is listed (or it names none); a draft becomes
    its creating tool's dry run; a step for another unlisted tool becomes None (the card drops it)."""
    if not isinstance(s, dict) or advanced(environ):
        return s
    t = s.get("tool")
    if not isinstance(t, str) or listed(t, environ):
        return s
    if t in ALIAS:
        args = dict(s.get("arguments") or {})
        if not args.get("name"):
            from .start_flow import build_names
            args["name"] = build_names(args.get("source"), args.get("schema")).get(ALIAS[t])
        args["dry_run"] = True
        old = str(s.get("label") or "")
        label = DRY_RUN_LABEL[ALIAS[t]] + (old[old.index(" for "):] if " for " in old else "")
        return {**s, "tool": ALIAS[t], "arguments": {k: v for k, v in args.items() if v is not None}, "label": label,
                "say": f"{label} ({ALIAS[t]}, as a dry run).", "ask": f"{label}."}
    return None
