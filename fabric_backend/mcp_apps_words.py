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

n227 (founder's test in claude.ai, 12 November 2026): every tool gets a `kg_card`, and every card reads it first.
- `result`: one line that says what happened ("Created shop_api_3, an API for GraphQL, in Fabric."), never the plan
  again and never "no summary in it";
- `lines`: at most five short lines (LINES_MAX);
- `notes`: [{line, items}], repeated notes collapsed into one line each ("24 links need a combined key column; Krusgraph
  can add them in a gold view"), the list behind Show;
- no tool name in any of them (TOOL_NAME finds one, and the tests assert it never matches), numbers agree with their
  nouns (agree(): "1 table", "1 row", never "1 tables" or "column(s)"), and a label is never doubled.
The sentences are built from the answer's own counts and names: nothing is added that the tool did not answer.
"""
from __future__ import annotations

import re

KEY = "kg_card"
# A bubble that reads out a call: name=value, or "run <tool> with/as".
WORDS_WITH_ARGUMENTS = re.compile(r"\b[a-z_]+=(?:\"|'|\[|\{|true\b|false\b|\d)|\brun [a-z]+_[a-z_]+\b|\b[a-z]+_[a-z_]+\(", re.I)
BY_NAME = ("R0", "R1", "R2", "R3", "R4")
BUILDER_PLAN = "I can build a semantic model, an ontology or an API from this plan. Each shows a dry run first."
THINKER_CHECK = "Shall I check these links against the rows?"
BUILDER_AFTER_CHECK = ("After the check I can build a semantic model, an ontology or an API from this plan. Each shows a "
                       "dry run first.")
LIST_MAX = 3
LINES_MAX = 5                                   # n227: a card's summary is one result line and at most five lines
NOTE_ITEMS_MAX = 60
# n227: a tool's name in a sentence a person reads (list_workspaces, create_report ...); `start` is a plain word. The
# names are listed, not matched by shape: list_price and order_items are columns and tables, not tools.
TOOLS_NAMED = (
    "analyze_schema", "answer_query_draft", "app_readiness", "app_starter", "compare_semantic_model",
    "create_backend", "create_data_agent", "create_drift_monitor", "create_gold_views", "create_ontology",
    "create_pipeline", "create_report", "create_semantic_model", "create_silver_notebook", "create_views",
    "data_dictionary", "dbt_schema", "describe_backend", "domain_draft", "drift_monitor_draft",
    "export_item_definitions", "gold_views_draft", "join_path", "list_sources", "list_tables", "list_workspaces",
    "ontology_draft", "plan_backend", "plan_drift", "query_graphql", "rayfin_connector", "review_plan",
    "sample_rows", "sap_pack_draft", "semantic_model_draft", "silver_notebook_draft", "suggest_relationships",
    "validate_plan",
    "verify_build",
    "qlik_plan", "qlik_measures_draft", "qlik_reconcile_draft")
TOOL_NAME = re.compile(r"\b(?:" + "|".join(sorted(TOOLS_NAMED, key=len, reverse=True)) + r")\b")
SAP_PACK = "SAP pack: Krusgraph's list of known SAP keys"
# What each creating tool makes, for the result line.
MAKES = {"create_backend": "an API for GraphQL", "create_semantic_model": "a semantic model",
         "create_ontology": "an ontology", "create_report": "a report", "create_views": "views",
         "create_data_agent": "a data agent", "create_silver_notebook": "a notebook for the silver tables",
         "create_gold_views": "a notebook for the gold views", "create_drift_monitor": "a nightly drift monitor",
         "create_pipeline": "a pipeline"}
_PLAN_PREFIX = re.compile(r"^\d+ tables?, \d+ with keys?, \d+ relationships?(?:; |$)")
_SINGULAR = {"queries": "query", "entities": "entity", "keys": "key", "is": "is"}


def agree(text: str) -> str:
    """Numbers agree with their nouns: "1 column(s)" -> "1 column", "2 query(ies)" -> "2 queries", "1 tables" -> "1 table",
    "1 rows" -> "1 row". Only the noun right after a number is touched."""
    def opt(m):
        n, word, end = m.group(1), m.group(2), m.group(3)
        one = n == "1"
        if end == "(ies)":                       # "query(ies)": the y is already there
            stem = word[:-1] if word.endswith("y") else word
            return f"{n} {stem}{'y' if one else 'ies'}"
        if end == "(es)":
            return f"{n} {word}{'' if one else 'es'}"
        return f"{n} {word}{'' if one else 's'}"
    text = re.sub(r"\b(\d+) ((?:[A-Za-z]+ ){0,3}?[A-Za-z]+)(\(s\)|\(ies\)|\(es\))", opt, str(text))
    text = re.sub(r"\b1 (tables|rows|links|keys|columns|relationships|measures|schemas|files|items|views|orphans|"
                  r"candidates|checks|sources|workspaces|visuals|pages|notes)\b", lambda m: "1 " + m.group(1)[:-1], text)
    return re.sub(r"\b1 (queries|entities)\b", lambda m: "1 " + _SINGULAR[m.group(1)], text)


def undoubled(label: str) -> str:
    """"Total NETWR (sap_vbrk) (sap_vbrk)" -> "Total NETWR (sap_vbrk)": a bracket said twice in a row is said once."""
    return re.sub(r"(\([^()]+\))(?:\s*\1)+", r"\1", str(label))


def labelled(name: str, table: str | None) -> str:
    """A measure or column with its table in brackets, unless the name already ends with it."""
    name = undoubled(name)
    if not table or name.rstrip().endswith(f"({table})"):
        return name
    return f"{name} ({table})"


def plain(text: str) -> str:
    """One sentence a person reads: tool names out (TOOL_NAME), numbers agreeing, no doubled bracket."""
    t = undoubled(agree(str(text).strip()))
    t = TOOL_NAME.sub(lambda m: _TOOL_WORDS.get(m.group(0), "Krusgraph"), t)
    return t


# A tool's name in plain words, where an answer's own sentence names one.
_TOOL_WORDS = {"validate_plan": "the check against the rows", "plan_backend": "the plan", "review_plan": "the review",
               "create_backend": "Create", "create_semantic_model": "Create", "create_ontology": "Create", "create_report": "Create",
               "semantic_model_draft": "the semantic model draft", "ontology_draft": "the ontology draft",
               "gold_views_draft": "the gold views draft", "sample_rows": "showing rows", "list_workspaces": "the workspace list",
               "list_sources": "the source list", "list_tables": "the table list", "app_readiness": "the app check",
               "create_pipeline": "Create", "sap_pack_draft": "the SAP pack's list",
               "qlik_plan": "the plan from the load script", "qlik_measures_draft": "the measure drafts",
               "qlik_reconcile_draft": "the KPI comparison"}


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
        "sap": any(r.rule == "SAP pack" for r in rels),
        "sap_keys": sum(1 for _, rule in plan.keys.values() if rule == "SAP pack"),
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
        parts.append(f"{other} from {'the SAP pack' if f.get('sap') else 'a knowledge pack'}")
    if not n:
        out.append("No links found yet.")
    elif len(parts) == 1 and f["by_name"] == n:
        out.append(f"{_plural(n, 'link')}, all found by name." if n > 1 else "1 link, found by name.")
    else:
        out.append(f"{_plural(n, 'link')}: {', '.join(parts)}.")
    if f.get("sap") and (other > 0 or f.get("sap_keys")):       # n227: said the first time the words appear
        out.append(SAP_PACK + ".")
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
        if tool == "plan_backend" and "builder" not in out:       # n227: the builds come after the check
            out["builder"] = BUILDER_AFTER_CHECK
    return out


# ------------------------------------------------------------------ n227: one summary form for every tool -------------

def _note(line: str, items) -> dict:
    items = [plain(x) for x in items if isinstance(x, str) and x.strip()]
    out = {"line": plain(line), "items": items[:NOTE_ITEMS_MAX]}
    if len(items) > NOTE_ITEMS_MAX:
        out["more"] = len(items) - NOTE_ITEMS_MAX
    return out


def _is_are(n: int) -> str:
    return "is" if n == 1 else "are"


def _name_of(tool: str, answer: dict, call: dict) -> str:
    rep = answer.get("report") if isinstance(answer.get("report"), dict) else {}
    st = answer.get("started") if isinstance(answer.get("started"), dict) else {}
    for v in (call.get("name"), answer.get("name"), rep.get("name"), st.get("name")):
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def result_line(tool: str, answer: dict, call: dict) -> str | None:
    """A creating tool's one line: what the dry run is of, what was created or updated, or that Fabric is still working.
    The created item, by name and kind; never the plan again."""
    made = MAKES.get(tool)
    if not made:
        return None
    name = _name_of(tool, answer, call)
    if isinstance(answer.get("started"), dict):
        if answer.get("checked") and not (answer.get("operation") or {}).get("status"):
            return (f"{name or 'It'} is not in Fabric yet. It may still be on its way, or the create did not reach Fabric; "
                    "check again in a moment.")
        return (f"Fabric is still working on {name or 'it'}. Nothing needs to be sent again; check its status in a moment.")
    if answer.get("dry_run") is True:
        more = ""
        if answer.get("exists") is True:
            more = " It exists already and would be updated in place."
        elif answer.get("exists") is False:
            more = " It would be new."
        return f"Dry run of {name or made}: nothing was created." + more
    result = answer.get("result") if isinstance(answer.get("result"), dict) else {}
    if answer.get("checked") and result.get("status") == "Succeeded":
        return f"{name} is in Fabric now: {made}." if name else f"It is in Fabric now: {made}."
    if answer.get("dry_run") is False and result.get("status") == "Succeeded":
        verb = "Updated" if result.get("mode") == "updated" else "Created"
        return f"{verb} {name}, {made}, in Fabric." if name else f"{verb} {made} in Fabric."
    return None


def model_card(s: dict) -> dict:
    """A semantic model's summary (semantic_model.draft's `summary`): tables by role, relationships, measures, what has
    no key; the repeated notes collapsed."""
    lines, notes = [], []
    roles = s.get("roles") if isinstance(s.get("roles"), dict) else {}
    n_tables = int(s.get("tables") or len(roles) or 0)
    by: dict[str, int] = {}
    for r in roles.values():
        by[str(r)] = by.get(str(r), 0) + 1
    if n_tables:
        lines.append(_plural(n_tables, "table") + (": " + ", ".join(f"{n} {r}" for r, n in sorted(by.items(), key=lambda x: -x[1])) if by else "") + ".")
    act, ina = int(s.get("relationships_active") or 0), int(s.get("relationships_inactive") or 0)
    if act or ina:
        lines.append(f"{_plural(act + ina, 'relationship')}" + (", all active." if not ina else f": {act} active, {ina} inactive."))
    else:
        lines.append("No relationships in the model.")
    seen, measures = set(), []
    extra = s.get("order_amount") if isinstance(s.get("order_amount"), dict) else {}
    for m in list(s.get("measures") or []) + list(extra.get("measures") or []):
        if isinstance(m, dict) and m.get("name") and (m.get("table"), m["name"]) not in seen:
            seen.add((m.get("table"), m["name"]))
            measures.append(undoubled(str(m["name"])))
    lines.append(f"{_plural(len(measures), 'measure')}: {_listed(measures)}." if measures else "No measures.")
    keyless = [str(x) for x in s.get("keyless") or []]
    if keyless:
        lines.append(f"{_listed(keyless)} {'has' if len(keyless) == 1 else 'have'} no key.")
    heads = [h for h in s.get("header_amounts") or [] if isinstance(h, dict)]
    if heads:
        lines.append(f"{_plural(len(heads), 'header amount is', 'header amounts are')} not summed over the lines.")
        notes.append(_note(f"{_plural(len(heads), 'amount sits', 'amounts sit')} on a header table and would repeat on its lines.",
                           [f"{h.get('table')}.{h.get('column')}, not summed over {', '.join(h.get('lines') or [])}" for h in heads]))
    inactive = [r for r in s.get("inactive") or [] if isinstance(r, dict)]
    if inactive:
        notes.append(_note(f"{_plural(len(inactive), 'link is', 'links are')} inactive, because another path between the same tables is the active one.",
                           [f"{r.get('source')}.{'+'.join(r.get('columns') or [])} → {r.get('target')}" + (f" (rule {r['rule']})" if r.get("rule") else "")
                            for r in inactive]))
    hard = [r for r in s.get("not_expressible") or [] if isinstance(r, dict)]
    if hard:
        notes.append(_note(f"{_plural(len(hard), 'link needs', 'links need')} a combined key column; Krusgraph can add "
                           f"{'it' if len(hard) == 1 else 'them'} in a gold view.",
                           [f"{r.get('source')}.{'+'.join(r.get('columns') or [])} → {r.get('target')}" for r in hard]))
    comp = [str(x) for x in s.get("composite_keys") or []]
    if comp:
        notes.append(_note(f"{_plural(len(comp), 'table has', 'tables have')} a key of several columns.", comp))
    dt = s.get("date_table") if isinstance(s.get("date_table"), dict) else {}
    loose = [r for r in dt.get("not_related") or [] if isinstance(r, dict)]
    if loose:
        notes.append(_note(f"{_plural(len(loose), 'date column is', 'date columns are')} not related to the calendar table.",
                           [f"{r.get('fact')}.{r.get('column')}" + (f": {r['why']}" if r.get("why") else "") for r in loose]))
    return {"lines": lines[:LINES_MAX], "notes": notes}


_ONTO_KINDS = (("no key was found", "nokey"), ("composite key", "composite"), ("is not a string or integer", "keytype"),
               ("composite-column relationship", "link"))


def onto_card(s: dict) -> dict:
    """An ontology's summary (ontology.summary): entity types and relationship types; its notes in plain words, one
    line per kind with the names behind Show."""
    lines, notes = [], []
    n, k = int(s.get("entity_types") or 0), int(s.get("with_key") or 0)
    lines.append(f"{_plural(n, 'entity type')}, " + ("each with a key." if n and k == n and n > 1 else f"{k} with a key."))
    rels, skipped = int(s.get("relationship_types") or 0), int(s.get("skipped_relationships") or 0)
    lines.append(f"{_plural(rels, 'relationship type')}." if rels else "No relationship types.")
    groups: dict[str, list[str]] = {"nokey": [], "composite": [], "keytype": [], "link": [], "other": []}
    for note in s.get("notes") or []:
        if not isinstance(note, str) or not note.strip():
            continue
        kind = next((k2 for words, k2 in _ONTO_KINDS if words in note), "other")
        who = note.split(":", 1)[0].strip()
        if kind == "composite":
            cols = re.search(r"\[(.*?)\]", note)
            who += ": " + " + ".join(c.strip(" '\"") for c in cols.group(1).split(",")) if cols else ""
        elif kind == "link":
            who = re.sub(r"\s*\(.*$", "", who)
        groups[kind].append(who if kind != "other" else note)
    g = groups
    if g["nokey"]:
        m = len(g["nokey"])
        notes.append(_note(f"{_plural(m, 'entity type has', 'entity types have')} no key, so nothing can point at "
                           f"{'it' if m == 1 else 'them'}. You can set a key in Fabric if the table has one.", g["nokey"]))
    if g["composite"]:
        m = len(g["composite"])
        notes.append(_note(f"{_plural(m, 'entity type has', 'entity types have')} a key of several columns. An ontology key is one "
                           f"column, so {'it is' if m == 1 else 'they are'} kept without a key, with the key columns as properties.",
                           g["composite"]))
    if g["keytype"]:
        m = len(g["keytype"])
        notes.append(_note(f"{_plural(m, 'entity type has', 'entity types have')} a key that is neither text nor a whole number, so "
                           f"{'it is' if m == 1 else 'they are'} kept without a key.", g["keytype"]))
    if g["link"]:
        m = len(g["link"])
        notes.append(_note(f"{_plural(m, 'link runs', 'links run')} over several columns, so {'it is' if m == 1 else 'they are'} "
                           f"not {'a relationship type' if m == 1 else 'relationship types'}.", g["link"]))
    elif skipped:
        lines.append(f"{_plural(skipped, 'link is', 'links are')} not {'a relationship type' if skipped == 1 else 'relationship types'}.")
    for note in g["other"][:3]:
        notes.append(_note(note.split(". ")[0].rstrip(".") + ".", [note]))
    return {"lines": lines[:LINES_MAX], "notes": notes}


def report_card(rep: dict) -> dict:
    lines, notes = [], []
    vis = [v for v in rep.get("visuals") or [] if isinstance(v, (dict, str))]
    bound = rep.get("bound_to") if isinstance(rep.get("bound_to"), dict) else {}
    if bound.get("semantic_model"):
        lines.append(f"It reads the semantic model {bound['semantic_model']}.")
    pages = int(rep.get("pages") or 1)
    if vis:
        kinds: dict[str, int] = {}
        for v in vis:
            t = str(v.get("type") or v.get("visual") or "visual") if isinstance(v, dict) else "visual"
            kinds[t] = kinds.get(t, 0) + 1
        said = ", ".join(_plural(n, t.replace("_", " ")) for t, n in kinds.items()) if set(kinds) != {"visual"} else ""
        lines.append(f"{_plural(pages, 'page')} with {_plural(len(vis), 'visual')}" + (f": {said}." if said else "."))
    else:
        lines.append(f"{_plural(pages, 'page')}, blank: no visuals.")
        if isinstance(rep.get("why_empty"), str):
            lines.append(plain(rep["why_empty"]))
    left = [x for x in rep.get("left_out") or [] if isinstance(x, dict)]
    if left:
        notes.append(_note(f"{_plural(len(left), 'measure is', 'measures are')} not drawn.",
                           [f"{x.get('measure')}: {x.get('why')}" for x in left]))
    nd = rep.get("not_drawn")
    if isinstance(nd, list) and nd:
        notes.append(_note(f"{_plural(len(nd), 'visual is', 'visuals are')} left off the page.",
                           [x if isinstance(x, str) else "; ".join(f"{k}: {v}" for k, v in x.items()) if isinstance(x, dict) else "" for x in nd]))
    return {"lines": lines[:LINES_MAX], "notes": notes}


_CHANGE_WORDS = (("new_tables", "table"), ("new_relationships", "relationship field"), ("new_columns", "column"),
                 ("tables_gone", "table gone"), ("removed_columns", "column removed"), ("actions_changed", "action changed"))


def backend_card(answer: dict) -> dict:
    """create_backend: what the dry run would send, or the item that was created; not the plan again."""
    lines, notes = [], []
    if answer.get("dry_run") is True:
        ch = answer.get("changes") if isinstance(answer.get("changes"), dict) else {}
        adds = [_plural(len(ch[k]), w) for k, w in _CHANGE_WORDS[:3] if isinstance(ch.get(k), list) and ch[k]]
        gone = [_plural(len(ch[k]), w, w.replace("table gone", "tables gone").replace("column removed", "columns removed")
                        .replace("action changed", "actions changed")) for k, w in _CHANGE_WORDS[3:] if isinstance(ch.get(k), list) and ch[k]]
        if adds:
            lines.append("It would add " + _listed(adds) + ".")
        if gone:
            lines.append("It would also change: " + _listed(gone) + ".")
        if answer.get("would_change") is False:
            lines.append("Nothing would change: the API already has this definition.")
        passed = [c for c in answer.get("checks_passed") or [] if isinstance(c, str)]
        if passed:
            notes.append(_note(f"{_plural(len(passed), 'check')} passed before the dry run.", passed))
        if answer.get("not_checked"):
            lines.append("The keys and links were not checked against the rows in this step.")
    else:
        text = answer.get("card") if isinstance(answer.get("card"), str) else ""
        m = re.search(r"GraphQL endpoint:\s*(\S+)", text)
        if m:
            lines.append(f"Endpoint: {m.group(1)}")
        todo = [re.sub(r"^\s*\[ \]\s*", "", ln).strip() for ln in text.splitlines() if ln.strip().startswith("[ ]")]
        if todo:
            notes.append(_note(f"{_plural(len(todo), 'step is', 'steps are')} left to do in the Fabric portal.", todo))
    skipped = [x for x in answer.get("skipped_relationships") or []]
    if skipped:
        notes.append(_note(f"{_plural(len(skipped), 'link was', 'links were')} left out of the API.",
                           [x if isinstance(x, str) else f"{x.get('source')} → {x.get('target')}" + (f": {x['reason']}" if x.get("reason") else "")
                            for x in skipped if isinstance(x, (str, dict))]))
    kept = answer.get("names_kept_from_api")
    if isinstance(kept, list) and kept:
        lines.append(f"{_plural(len(kept), 'field name')} kept from the existing API.")
    return {"lines": lines[:LINES_MAX], "notes": notes}


_NAME_KEYS = ("name", "displayName", "schema", "table", "id")


def _names(xs: list) -> list[str]:
    out = []
    for x in xs:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            v = next((x[k] for k in _NAME_KEYS if isinstance(x.get(k), str) and x[k]), None)
            if v:
                out.append(v + (f" ({x['type']})" if isinstance(x.get("type"), str) and x["type"] not in ("Workspace",) else ""))
    return out


def _counted(n: int, noun: str) -> str:
    noun = noun.replace("_", " ")
    if not noun.endswith("s"):                       # "checklist" -> "7 checklist items"
        return f"{n} {noun} {'item' if n == 1 else 'items'}"
    one = noun[:-3] + "y" if noun.endswith("ies") else noun[:-1] if not noun.endswith("ss") else noun
    return f"{n} {one if n == 1 else noun}"


def generic_card(tool: str, answer: dict) -> dict:
    """Any other answer in one line, from its own summary, verdict, lists or numbers. Always a line: an answer is never
    "no summary in it"."""
    lines: list[str] = []
    s = answer.get("summary")
    if tool == "list_workspaces" and isinstance(answer.get("workspaces"), list):
        ws = _names(answer["workspaces"])
        return {"result": f"{_plural(len(ws), 'workspace')}: {_listed(ws)}." if ws else "No workspace was found for this account."}
    if tool == "list_sources" and isinstance(answer.get("sources"), list):
        src, apis = _names(answer["sources"]), _names(answer.get("graphql_apis") or [])
        out = {"result": f"{_plural(len(src), 'source')}: {_listed(src)}." if src else "No lakehouse, warehouse or database in this workspace."}
        if apis:
            out["lines"] = [f"{_plural(len(apis), 'API for GraphQL', 'APIs for GraphQL')}: {_listed(apis)}."]
        return out
    if tool == "list_tables" and answer and all(isinstance(v, list) for v in answer.values()):
        ts = list(answer)
        return {"result": f"{_plural(len(ts), 'table')}: {_listed(ts)}."}
    if tool == "sample_rows" and isinstance(answer.get("rows"), list):
        return {"result": f"{_plural(len(answer['rows']), 'row')} of {answer.get('table') or 'the table'}, "
                          f"{_plural(len(answer.get('columns') or []), 'column')}."}
    if tool == "answer_query_draft":
        ts = _names(answer.get("tables") or [])
        return {"result": "A draft query" + (f" over {_listed(ts)}" if ts else "") + "; nothing was run."}
    if tool == "query_graphql" and isinstance(answer.get("data"), dict):
        parts = [_counted(len(v), "rows") + f" of {k}" for k, v in answer["data"].items() if isinstance(v, list)]
        return {"result": "The query ran: " + _listed(parts) + "." if parts else "The query ran."}
    if isinstance(s, str) and s.strip():
        first = s.strip().splitlines()[0].strip()
        rest = _PLAN_PREFIX.sub("", first)
        text = rest if rest and rest != first else first
        text = plain(text[0].upper() + text[1:])
        return {"result": text if text.endswith((".", "?", "!")) else text + "."}
    if isinstance(answer.get("verdict"), str) and answer["verdict"].strip():
        text = plain(answer["verdict"].strip())
        text = text[0].upper() + text[1:]
        return {"result": text if text.endswith(".") else text + "."}
    files = [k for k in answer if "/" in k or re.search(r"\.[a-z]{2,5}$", k)]
    if files and len(files) >= len(answer) - 2:
        return {"result": f"{_plural(len(files), 'file')}: {_listed([f.rsplit('/', 1)[-1] for f in files])}."}
    nums = [(k, v) for k, v in answer.items() if isinstance(v, int) and not isinstance(v, bool)]
    lists = [(k, v) for k, v in answer.items() if isinstance(v, list)]
    dicts = [(k, v) for k, v in answer.items() if isinstance(v, dict) and k not in ("coverage", "rest", KEY)]
    if nums:
        return {"result": ", ".join(_counted(v, k) for k, v in nums[:4]) + "."}
    if lists:
        for k, v in lists[:LINES_MAX]:
            names = _names(v)
            short = names and len(names) == len(v) and all(len(x) <= 40 for x in names)
            lines.append(_counted(len(v), k) + (f": {_listed(names)}" if short else "") + ".")
        return {"result": lines[0], "lines": lines[1:]}
    if dicts:
        return {"result": ", ".join(_counted(len(v), "entries") + f" under {k.replace('_', ' ')}" for k, v in dicts[:3]) + "."}
    keys = [k.replace("_", " ") for k in answer if k != KEY]
    return {"result": f"The answer has {_plural(len(keys), 'part')}: {_listed(keys)}." if keys else "The answer is empty."}


def summary_card(tool: str, answer: dict, call: dict | None = None) -> dict:
    """{result, lines, notes} for one answer, the same form for a plan, a draft, a dry run and a created item (n227)."""
    call = call or {}
    s = answer.get("summary") if isinstance(answer.get("summary"), dict) else None
    out: dict = {}
    if s is not None and "relationships_active" in s:
        out = model_card(s)
        out["result"] = result_line(tool, answer, call) or "A semantic model draft: nothing was created."
        said = [x for x in answer.get("read_from_rows") or [] if isinstance(x, str)]
        if said and answer.get("dry_run") is not None:
            out.setdefault("notes", []).append(_note(f"{_plural(len(said), 'thing was', 'things were')} read from the rows for the model.", said))
    elif s is not None and "entity_types" in s:
        out = onto_card(s)
        out["result"] = result_line(tool, answer, call) or "An ontology draft: nothing was created."
    elif isinstance(answer.get("report"), dict):
        out = report_card(answer["report"])
        out["result"] = result_line(tool, answer, call) or "A report."
    elif tool == "create_backend" and ("dry_run" in answer or "started" in answer or "checked" in answer):
        out = backend_card(answer)
        out["result"] = result_line(tool, answer, call) or generic_card(tool, answer)["result"]
    else:
        out = generic_card(tool, answer)
        line = result_line(tool, answer, call)
        if line:
            if out.get("result") and out["result"] != line:
                out["lines"] = ([out["result"]] + list(out.get("lines") or []))[:LINES_MAX]
            out["result"] = line
    if isinstance(answer.get("started"), dict):                   # still running in Fabric: say only that
        out = {"result": out["result"]}
    out["result"] = plain(out["result"])
    out["lines"] = [plain(x) for x in out.get("lines") or [] if isinstance(x, str) and x.strip()][:LINES_MAX]
    if not out["lines"]:
        out.pop("lines")
    if not out.get("notes"):
        out.pop("notes", None)
    return out


TITLES = {"list_workspaces": "Workspaces", "list_sources": "Sources", "list_tables": "Tables", "sample_rows": "Rows",
          "semantic_model_draft": "Semantic model draft", "ontology_draft": "Ontology proposal", "gold_views_draft": "Gold views draft",
          "silver_notebook_draft": "Silver tables draft", "create_semantic_model": "Semantic model", "create_ontology": "Ontology",
          "create_backend": "API for GraphQL", "create_report": "Report", "data_dictionary": "Data dictionary",
          "domain_draft": "Data products", "dbt_schema": "dbt project", "review_plan": "Review"}


def card(tool: str, answer: dict, stash: dict | None = None, call: dict | None = None) -> dict | None:
    """{title?, result?, lines?, notes?, onto?, thinker?, builder?} for the card, or None when there is nothing to say
    (an error or a refusal: the card shows the error itself, with its next steps)."""
    started = isinstance(answer, dict) and isinstance(answer.get("started"), dict)   # n227: Fabric still works: not an error to show
    if not isinstance(answer, dict) or (answer.get("error") and not started) or answer.get("kind") == "upgrade":
        return None
    stash = stash or {}
    out: dict = {}
    own = answer.get(KEY)
    if isinstance(own, dict) and isinstance(own.get("result"), str) and own["result"].strip():
        # Q2: a tool that writes its card's words itself (the Qlik tools): the same form and the same rules as below
        out = {"result": plain(own["result"])}
        if isinstance(own.get("title"), str):
            out["title"] = own["title"]
        lines = [plain(x) for x in own.get("lines") or [] if isinstance(x, str) and x.strip()][:LINES_MAX]
        if lines:
            out["lines"] = lines
        notes = [_note(plain(n["line"]), n.get("items") or []) for n in own.get("notes") or []
                 if isinstance(n, dict) and isinstance(n.get("line"), str)]
        if notes:
            out["notes"] = notes
        if not WORDS_WITH_ARGUMENTS.search(out["result"]):
            out["onto"] = out["result"]
        return out
    if answer.get("choose_schema"):
        return {"title": "Plan", "thinker": "Which schema shall I plan?"}
    if tool == "start":                              # n227: the step's own sentence, said once by Onto
        said = answer.get("say") if isinstance(answer.get("say"), str) else ""
        return {"title": "Start Krusgraph", "result": plain(said), "onto": plain(said)} if said.strip() else None
    if tool == "plan_backend" and stash.get("words"):
        f = stash["words"]
        out["title"] = "Plan"
        out["lines"] = plan_lines(f)
    elif tool == "validate_plan" and isinstance(answer.get("totals"), dict):
        out["title"] = "Plan check"
        out["lines"] = check_lines(answer)
    else:                                            # n227: every other answer, in one form
        try:
            out.update(summary_card(tool, answer, call))
        except Exception:                            # noqa: BLE001 - a summary must never break the answer
            out.update({"result": "The answer is under Show details."})
        dry = answer.get("dry_run")
        title = TITLES.get(tool)
        if title and tool not in MAKES:              # a draft or a list: its title as it is
            out["title"] = title
        elif title:
            out["title"] = title + (": dry run" if dry is True else ": still working" if started
                                    else ": created" if dry is False or answer.get("checked") else "")
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
    if isinstance(answer.get("started"), dict):
        out["builder"] = "Fabric is still working on it. Check its status in a moment; I will not send it again."
    if out.get("result"):                            # Onto says the result, once; the lines stay on the card
        out["onto"] = out["result"]
    elif out.get("lines"):
        out["onto"] = " ".join(out["lines"])
    for k in ("onto", "thinker", "builder"):         # never argument syntax in a bubble
        if k in out and WORDS_WITH_ARGUMENTS.search(out[k]):
            out.pop(k)
    return out or None


def extras(tool: str, answer: dict, stash: dict | None = None, call: dict | None = None) -> dict:
    c = card(tool, answer, stash, call)
    return {KEY: c} if c else {}
