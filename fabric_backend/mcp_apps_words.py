"""MCP Apps, round n172: what the cards say, in plain English.

The founder tried the cards in Claude on 8 November 2026 (demo_lh, schema shop) and found the mascots reading out tool
calls ("Check against the rows: run validate_plan with workspace="demo", ..."), a summary line nobody could read ("6
relationships R5 counted 1 code or role column(s) in the rows: 1 counting query(ies), at most 200 distinct values ..."),
and the same sentence three times (the title, Onto and the summary). This module writes the card's words from the same
facts the answer holds, and the card shows them instead:

- `lines`: the summary as short sentences ("7 tables, 6 with a key." ...). Onto says them, once; the card's own copy of
  them is shown only while the mascots are off (mascots are never the only carrier of information, docs/SITE.md).
- `thinker`: a question ("Shall I check these links against the rows?"); `builder`: what can be built, never the
  arguments. The buttons carry the arguments; no bubble shows argument syntax (WORDS_WITH_ARGUMENTS finds it, and the
  tests assert it never matches).

Only in `structuredContent` (key `kg_card`, mcp_apps.call_result), and only with KRUSGRAPH_MCP_APPS=1. The text answer is
unchanged: text-only clients keep the full next-step text (each action's `say`).
"""
from __future__ import annotations

import re

KEY = "kg_card"
# A bubble that reads out a call: name=value, or "run <tool> with/as".
WORDS_WITH_ARGUMENTS = re.compile(r"\b[a-z_]+=(?:\"|'|\[|\{|true\b|false\b|\d)|\brun [a-z]+_[a-z_]+\b|\b[a-z]+_[a-z_]+\(", re.I)
BY_NAME = ("R0", "R1", "R2", "R3", "R4")
BUILDER_PLAN = "I can build a semantic model, an ontology or an API from this plan. Each shows a dry run first."
THINKER_CHECK = "Shall I check these links against the rows?"
LIST_MAX = 3


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _listed(xs: list[str]) -> str:
    xs = list(xs)
    if len(xs) > LIST_MAX:
        return ", ".join(xs[:LIST_MAX]) + f" and {len(xs) - LIST_MAX} more"
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _link(source_cols, target: str) -> str:
    return f"{'+'.join(source_cols)} → {target}"


def plan_facts(plan) -> dict:
    """The facts the plan card speaks from, taken from the plan (infer.Plan) the answer was made from."""
    rels = list(plan.relationships)
    proposed = list(getattr(plan, "proposed", None) or [])
    return {
        "tables": len(plan.schema), "keyed": len(plan.keys), "keyless": list(plan.keyless),
        "links": len(rels),
        "by_name": sum(1 for r in rels if r.rule in BY_NAME),
        "from_values": [_link(r.source_cols, r.target) for r in rels if r.rule == "R5"],
        "confirmed": sum(1 for r in rels if r.rule == "confirmed"),
        "ambiguous": len(plan.ambiguous),
        "failed": [_link(x["source_cols"], x["target"]) for x in proposed if x.get("not_counted") == "failed"],
        "dropped": all("connection to the SQL endpoint dropped" in x.get("reason", "") for x in proposed if x.get("not_counted") == "failed"),
        "budget": sum(1 for x in proposed if x.get("not_counted") == "budget"),
        "unsupported": sum(1 for x in proposed if not x.get("not_counted")),
    }


def _why_failed(f: dict) -> str:
    return "the connection to the data dropped" if f.get("dropped", True) else "the counting query could not run"


def plan_lines(f: dict) -> list[str]:
    """The plan's summary as short sentences, from plan_facts."""
    out = [f"{_plural(f['tables'], 'table')}, " + ("each with a key." if f["keyed"] == f["tables"] and f["tables"] > 1
                                                    else f"{f['keyed']} with a key.")]
    n, parts = f["links"], []
    if f["by_name"]:
        parts.append(f"{f['by_name']} by name")
    if f["from_values"]:
        parts.append(f"{len(f['from_values'])} found from the values ({_listed(f['from_values'])})")
    if f["confirmed"]:
        parts.append(f"{f['confirmed']} you confirmed")
    other = n - f["by_name"] - len(f["from_values"]) - f["confirmed"]
    if other > 0:
        parts.append(f"{other} from a knowledge pack")
    if not n:
        out.append("No links found yet.")
    elif len(parts) == 1 and f["by_name"] == n:
        out.append(f"{_plural(n, 'link')}, all found by name." if n > 1 else "1 link, found by name.")
    else:
        out.append(f"{_plural(n, 'link')}: {', '.join(parts)}.")
    k = f["keyless"]
    if k:
        out.append(f"{_listed(k)} {'has' if len(k) == 1 else 'have'} no key, so nothing can point to {'it' if len(k) == 1 else 'them'}.")
    if f["failed"]:
        out.append(f"{_plural(len(f['failed']), 'more link')} could not be counted because {_why_failed(f)}: "
                   f"{_listed(f['failed'])}. Not counted is not rejected.")
    if f["budget"]:
        out.append(f"{_plural(f['budget'], 'more possible link was', 'more possible links were')} not counted in this call.")
    if f["unsupported"]:
        out.append(f"{_plural(f['unsupported'], 'more possible link')} did not fit the values, so "
                   f"{'it is' if f['unsupported'] == 1 else 'they are'} left out.")
    if f["ambiguous"]:
        out.append(f"{_plural(f['ambiguous'], 'column')} could point at more than one table; "
                   f"{'it is' if f['ambiguous'] == 1 else 'they are'} left out until you choose.")
    return out


def check_lines(answer: dict) -> list[str]:
    """validate_plan's summary as short sentences, from its totals."""
    t = answer.get("totals") if isinstance(answer.get("totals"), dict) else {}
    out = []
    k = t.get("keys") if isinstance(t.get("keys"), dict) else {}
    if k.get("checked"):
        out.append(f"{k.get('passed', 0)} of {_plural(k['checked'], 'key')} hold.")
    r = t.get("relationships") if isinstance(t.get("relationships"), dict) else {}
    if r.get("checked"):
        failed = int(r.get("failed") or 0)
        out.append(f"{r.get('passed', 0)} of {_plural(r['checked'], 'link')} hold"
                   + (", with no orphans." if not failed else f"; {failed} {'has' if failed == 1 else 'have'} rows that point at nothing."))
    a = t.get("amount_levels") if isinstance(t.get("amount_levels"), dict) else {}
    if a.get("checked"):
        bad = int(a.get("failed") or 0)
        out.append("Every header amount is on its own level." if not bad else
                   f"{_plural(bad, 'header amount repeats', 'header amounts repeat')} on every line, so "
                   f"{'it' if bad == 1 else 'they'} must not be summed over the lines.")
    n = int(answer.get("needs_attention") or 0)
    out.append("Nothing needs attention." if not n else f"{_plural(n, 'thing needs', 'things need')} attention.")
    return out


def _action_words(tool: str, answer: dict) -> dict:
    """The Thinker's and the Builder's sentences for an answer's actions: what they offer, never how it is called."""
    acts = [a for a in answer.get("actions") or [] if isinstance(a, dict)]
    kinds = {(a.get("kind"), a.get("tool")) for a in acts}
    out = {}
    names = [a.get("name") for a in acts if a.get("kind") == "create" and a.get("name")]
    if any(k == "create" for k, _ in kinds):
        out["builder"] = (f"This is the dry run: nothing exists yet. Press Create to make {names[0]} in Fabric."
                          if names else "This is the dry run: nothing exists yet. Press Create to make it in Fabric.")
    elif any(k == "link" for k, _ in kinds):
        out["builder"] = "It is in Fabric now. Open it there" + (
            ", or build a report on it (a dry run first)." if ("dry_run", "create_report") in kinds else ".")
    elif tool == "domain_draft" and any(k == "dry_run" for k, _ in kinds):
        out["builder"] = "Each data product can become an API for GraphQL or a semantic model. Each shows a dry run first."
    elif {("dry_run", "create_semantic_model"), ("dry_run", "create_ontology"), ("dry_run", "create_backend")} & kinds:
        out["builder"] = BUILDER_PLAN
    if ("call", "validate_plan") in kinds:
        out["thinker"] = THINKER_CHECK
    return out


def card(tool: str, answer: dict, stash: dict | None = None) -> dict | None:
    """{title?, lines?, onto?, thinker?, builder?} for the card, or None when there is nothing to say."""
    if not isinstance(answer, dict) or answer.get("error") or answer.get("kind") == "upgrade":
        return None
    stash = stash or {}
    out: dict = {}
    if answer.get("choose_schema"):
        return {"title": "Plan", "thinker": "Which schema shall I plan?"}
    if tool == "plan_backend" and stash.get("words"):
        f = stash["words"]
        out["title"] = "Plan"
        out["lines"] = plan_lines(f)
    elif tool == "validate_plan" and isinstance(answer.get("totals"), dict):
        out["title"] = "Plan check"
        out["lines"] = check_lines(answer)
    out.update(_action_words(tool, answer))
    if tool == "plan_backend" and stash.get("words", {}).get("failed"):
        f = stash["words"]["failed"]
        out["thinker"] = (f"I couldn't count {_listed(f)}: {_why_failed(stash['words'])}. Shall I count "
                          f"{'it' if len(f) == 1 else 'them'} again?")
    if tool == "validate_plan":                      # what needs attention is listed on the card; the Thinker points at it
        out.pop("thinker", None)
        n = int(answer.get("needs_attention") or 0)
        if n:
            out["thinker"] = (f"{'One thing needs' if n == 1 else str(n) + ' things need'} your attention, listed below. "
                              f"I would look at {'it' if n == 1 else 'them'} before building.")
    if out.get("lines"):
        out["onto"] = " ".join(out["lines"])
    for k in ("onto", "thinker", "builder"):         # never argument syntax in a bubble
        if k in out and WORDS_WITH_ARGUMENTS.search(out[k]):
            out.pop(k)
    return out or None


def extras(tool: str, answer: dict, stash: dict | None = None) -> dict:
    c = card(tool, answer, stash)
    return {KEY: c} if c else {}
