"""Round n130: what a Fabric data agent is told about the source, built from the plan, its ontology names and, when
validate_plan has counted it, the checked plan. create_data_agent's draft and dry run show it; nothing here calls Fabric.

The agent gets, in the shapes the Fabric data agent documentation describes:

- agent instructions (aiInstructions) in the documented headings (Objective, Data sources, Key terminology, Response
  guidelines, Handling common topics), with the business names the ontology draft gives each table (ontology.entity_name,
  plus a knowledge pack's own English name where one recognised the table);
- data source instructions with the tables and their grain, the joins that are safe and the joins that are not, and
  the header amounts that must not be summed over line rows (amounts.check, and validate_plan's amount_levels with the
  n106 flat-table findings when the plan was counted);
- a data source description;
- three to five example questions with their T-SQL from answer_query_draft (answers.draft), each over safe joins only,
  with a comment that names the joins.

Safe means checked: a many-to-one relationship that validate_plan counted and that held without orphans and without
a warning (its target key unique). A declared, confirmed or inferred relationship that was not counted is listed as not
checked, never as safe. Without counts, the examples use one table each. No row value is read or written here:
validate_plan's counts decide the status of a join, and only names, rules and statuses reach the text.

Limits, from Microsoft's public documentation (MicrosoftDocs/fabric-docs, main at 951e7d3, read 6 November 2026):
- docs/data-science/how-to-create-data-agent.md (ms.date 05/20/2026): "Here, you can write up to 15,000 characters in
  plain English-language text, to instruct the AI about how to handle queries." -> MAX_INSTRUCTIONS.
- docs/data-science/concept-data-agent.md (ms.date 05/11/2026), Limitations: "Users can provide up to 100 example queries
  per data source in their Data Agent."; questions, instructions and example queries in English; answers capped at
  25 rows and 25 columns.
- docs/data-science/data-agent-example-queries.md (ms.date 09/11/2025): the agent "automatically retrieves the most
  relevant examples—typically the top four"; every example query "is validated against the schema of the selected
  data source—queries that don't pass validation aren't sent to the agent"; comments in the query are recommended.
- docs/data-science/data-agent-configurations.md (ms.date 08/31/2026): the recommended headings for agent instructions
  and data source instructions; data source descriptions are used to route questions.
- docs/data-science/data-agent-configuration-best-practices.md (ms.date 08/27/2026): join keys and paths, table grain
  and "aggregate each table before joining" belong in the data source instructions.
The pages give no number for data source instructions or the data source description. This module holds the data
source instructions to the same 15,000 characters and the description to 1,000, as its own budget, and says so.
"""
from __future__ import annotations

from .infer import Plan, RULES, _singulars, _words

MAX_INSTRUCTIONS = 15_000          # agent instructions: documented
MAX_DATASOURCE_INSTRUCTIONS = 15_000  # data source instructions: not documented; our own budget
MAX_DESCRIPTION = 1_000            # data source description: not documented; our own budget
MAX_EXAMPLES_DOCUMENTED = 100      # example queries per data source: documented
EXAMPLES_RETRIEVED = 4             # "typically the top four": documented
MIN_EXAMPLES, MAX_EXAMPLES = 3, 5
MAX_ATTEMPTS = 30                  # answer_query_draft calls per build: a bound on time for wide schemas
MAX_PATH_HOPS = 3

LIMITS = {
    "instructions": {"max_chars": MAX_INSTRUCTIONS, "source": "fabric-docs docs/data-science/how-to-create-data-agent.md, ms.date 05/20/2026"},
    "datasource_instructions": {"max_chars": MAX_DATASOURCE_INSTRUCTIONS,
                                "source": "no number in the documentation (fabric-docs main at 951e7d3, read 6 November 2026); "
                                          "Krusgraph's own budget, the same as the agent instructions"},
    "datasource_description": {"max_chars": MAX_DESCRIPTION, "source": "no number in the documentation; Krusgraph's own budget"},
    "examples": {"max_per_datasource": MAX_EXAMPLES_DOCUMENTED, "typically_retrieved": EXAMPLES_RETRIEVED,
                 "source": "fabric-docs docs/data-science/concept-data-agent.md (ms.date 05/11/2026) and "
                           "data-agent-example-queries.md (ms.date 09/11/2025)"},
    "language": "English: the documentation says the data agent does not support other languages yet",
}


# ------------------------------------------------------------------ names ---------------------

def _phrase(table: str) -> str:
    return " ".join(_words(table)) or table.lower()


def _singular(table: str) -> str:
    words = _words(table) or [table.lower()]
    last = sorted(_singulars(words[-1]), key=lambda s: (len(s), s))[0]
    return " ".join(words[:-1] + [last])


def business_names(plan: Plan) -> list[dict]:
    """One entry per table: the ontology's entity type name, the words a user says, and a pack's own name if any."""
    from .ontology import entity_name
    pack = getattr(plan, "pack", None) or {}
    out = []
    for t in plan.schema:
        e = {"table": t.name, "entity": entity_name(t.name), "words": _phrase(t.name)}
        name = (pack.get("tables") or {}).get(t.name)
        if name:
            try:
                from . import sap_pack
                en = (sap_pack.table_info(name, pack.get("pack", "sap")) or {}).get("en")
            except Exception:  # noqa: BLE001 - a table another pack knows, or no description: the entity name stands
                en = None
            if en:
                e["pack_name"] = en
        out.append(e)
    return out


def _relationship_name(plan: Plan, r) -> str:
    from .ontology import _entity_relationship_name
    return _entity_relationship_name(r, plan)


# ------------------------------------------------------------------ joins ---------------------

def _on(r) -> str:
    return " AND ".join(f"{r.source}.{a} = {r.target}.{b}" for a, b in zip(r.source_cols, r.target_cols))


def _not_counted(plan: Plan, r, validated: bool) -> str:
    origin = {"R0": "declared as a foreign key in the source", "confirmed": "confirmed by you"}.get(r.rule, "inferred from the names")
    if validated:
        return f"{origin}; not counted (validate_plan's max_items was used up)"
    return f"{origin}; not counted: create_data_agent with validate=true counts it"


def joins(plan: Plan, validation: dict | None = None) -> dict:
    """{"safe": [...], "not_safe": [...]}: every relationship of the plan once, safe only when validate_plan counted it
    and it held without orphans and without a warning. Each entry has the join, the rule and why."""
    validated = validation is not None
    counted = {}
    for v in (validation or {}).get("relationships", []):
        if "kind" not in v:                                          # pack joins with conditions are listed below
            counted[(v["source"], tuple(c.lower() for c in v["columns"]), v["target"])] = v
    safe, not_safe = [], []
    for r in plan.relationships:
        e = {"source": r.source, "target": r.target, "on": _on(r), "rule": r.rule, "name": _relationship_name(plan, r),
             "direction": "many-to-one"}
        v = counted.get(r.key)
        verdict = str((v or {}).get("verdict", ""))
        if v is None:
            e["why"] = _not_counted(plan, r, validated)
            not_safe.append(e)
        elif verdict.startswith("holds") and "; but" not in verdict:
            e["checked"] = f"counted by validate_plan: every {r.source} row with a value finds its {r.target} row, and that key is unique"
            safe.append(e)
        elif verdict.startswith("holds"):
            e["why"] = "counted, but " + verdict.split("; but", 1)[1].strip() + "; a join repeats rows"
            not_safe.append(e)
        elif verdict.startswith("no rows with a value"):
            e["why"] = f"counted, but no {r.source} row has a value in {', '.join(r.source_cols)}: nothing shows the join holds"
            not_safe.append(e)
        else:
            e["why"] = (f"counted, and some {r.source} values have no {r.target} row (orphans): an inner join drops those rows, "
                        "a left join keeps them with empty columns")
            not_safe.append(e)
    for r in getattr(plan, "extended", []):
        not_safe.append({"source": r.source, "target": r.target, "on": _on(r), "rule": r.rule, "name": _relationship_name(plan, r),
                         "direction": "conditional", "why": f"not a key join ({getattr(r, 'kind', 'extended')}): it needs the "
                         "pack's extra condition and can match more than one row; not used in the examples"})
    return {"safe": safe, "not_safe": not_safe, "validated": validated}


def safe_paths(safe: list[dict], max_hops: int = MAX_PATH_HOPS) -> list[list[str]]:
    """Chains of two or more safe many-to-one joins (a -> b -> c), longest first, then by name: deterministic."""
    out_edges: dict[str, list[str]] = {}
    for e in safe:
        if e["source"] != e["target"]:
            out_edges.setdefault(e["source"], []).append(e["target"])
    found: set[tuple] = set()

    def walk(chain: list[str]):
        if len(chain) >= 3:
            found.add(tuple(chain))
        if len(chain) > max_hops:
            return
        for nxt in sorted(set(out_edges.get(chain[-1], []))):
            if nxt not in chain:
                walk(chain + [nxt])

    for start in sorted(out_edges):
        walk([start])
    return [list(p) for p in sorted(found, key=lambda p: (-len(p), p))]


# ------------------------------------------------------------------ amounts -------------------

def repeated_amounts(plan: Plan, validation: dict | None = None) -> list[dict]:
    """The header amounts a join with their lines repeats (amounts.check, or validate_plan's amount_levels), and the
    n106 flat-table amounts repeated on every row of a header value. Names and statuses only, no counts or values."""
    from . import amounts
    levels = (validation or {}).get("amount_levels") or amounts.check(plan)
    out = []
    for f in levels.get("findings", []):
        per = f.get("rows_per_header")
        if isinstance(per, dict):
            status = ("counted: more than one line per header in the data" if per.get("max_lines", 0) > 1
                      else "counted: one line per header in the data today; new lines would repeat it")
        else:
            status = "not counted"
        for col in f["amount_columns"]:
            out.append({"kind": "header", "table": f["header"], "column": col, "lines": f["line"],
                        "via": f"{f['line']}.{'+'.join(f['line_columns'])} -> {f['header']} (rule {plan.label(f['rule'])})",
                        "status": status, "is_price": amounts.is_price(col),
                        "instruction": (f"{f['header']}.{col} is one value per {f['header']} row; a join with {f['line']} repeats it "
                                        f"on every {f['line']} row. Never SUM({f['header']}.{col}) over {f['line']} rows: "
                                        + (f"it is a price, so multiply it by the quantity on each {f['line']} row, or report it per "
                                           f"{f['header']} without summing." if amounts.is_price(col) else
                                           f"sum it on {f['header']} first (one row per {f['header']}) and join the result."))})
    for e in levels.get("flat_tables", []):
        if e.get("pattern"):
            out.append({"kind": "flat", "table": e["table"], "column": e["amount_column"], "lines": e["table"],
                        "via": f"{e['table']}.{e['header_column']}", "status": "counted: repeated on every row of a header value",
                        "is_price": False,
                        "instruction": (f"{e['table']}.{e['amount_column']} repeats the same value on every row of one "
                                        f"{e['header_column']}. Never SUM it over the {e['table']} rows: take it once per "
                                        f"{e['header_column']} (MAX per {e['header_column']}), then sum.")})
    return out


# ------------------------------------------------------------------ examples ------------------

def _step_key(step: dict) -> tuple:
    return (step["from"], step["to"], tuple(step["on"]))


def _safe_steps(safe: list[dict], plan: Plan) -> set[tuple]:
    keys = set()
    rels = {(r.source, r.target, _on(r)): r for r in plan.relationships}
    for e in safe:
        r = rels[(e["source"], e["target"], e["on"])]
        keys.add((r.source, r.target, tuple(f"{a} = {b}" for a, b in zip(r.source_cols, r.target_cols))))
    return keys


def _comment(answer: dict, safe: list[dict]) -> str:
    if not answer.get("path"):
        return "-- One table, no join."
    by = {(e["source"], e["target"]): e for e in safe}
    parts = []
    for s in answer["path"]:
        e = by.get((s["from"], s["to"]))
        parts.append(f"{e['on']} ({e['name']}, rule {e['rule']}, checked)" if e else f"{s['from']} -> {s['to']}")
    return "-- Safe many-to-one join(s): " + "; ".join(parts) + "."


def _candidates(plan: Plan, safe: list[dict], amounts_: list[dict]) -> list[tuple[str, str, list[str], dict]]:
    """(group, question, tables, expectation) in order of preference; answer_query_draft decides whether each holds."""
    from . import amounts
    out = []
    for path in safe_paths(safe):
        out.append(("path", f"How many {_phrase(path[0])} are there per {_singular(path[-1])}?", path,
                    {"counted": path[0], "group_table": path[-1]}))
    lines = amounts.line_amounts(plan)
    for la in lines:
        for col in la["amounts"] + la["quantities"]:
            for path in [p for p in safe_paths(safe) if p[0] == la["line"]] + \
                        [[e["source"], e["target"]] for e in safe if e["source"] == la["line"]]:
                out.append(("line_amount", f"What is the total {' '.join(_words(col))} per {_singular(path[-1])}?", path,
                            {"measure": [la["line"], col], "group_table": path[-1]}))
    header = {(a["table"], a["column"]) for a in amounts_ if a["kind"] == "header" and not a["is_price"]}
    for table, col in sorted(header):
        for e in [e for e in safe if e["source"] == table]:
            out.append(("header_amount", f"What is the total {' '.join(_words(col))} per {_singular(e['target'])}?",
                        [table, e["target"]], {"measure": [table, col], "group_table": e["target"]}))
    for e in safe:
        out.append(("join", f"How many {_phrase(e['source'])} are there per {_singular(e['target'])}?", [e["source"], e["target"]],
                    {"counted": e["source"], "group_table": e["target"]}))
    sources = {r.source for r in plan.relationships}
    targets = {r.target for r in plan.relationships}
    tables = sorted((t.name for t in plan.schema),                 # keyed facts first, then keyed tables, keyless last
                    key=lambda n: (n not in plan.keys, n not in sources or n in targets, n not in sources))
    for t in tables:
        out.append(("table", f"How many {_phrase(t)} are there?", [t], {"counted": t}))
    return out


def examples(plan: Plan, safe: list[dict], amounts_: list[dict], show_personal_data: bool = False) -> tuple[list[dict], list[dict]]:
    """Three to five {question, query} pairs from answer_query_draft, each over safe joins only (or one table), and the
    candidates that were turned down with the reason. Deterministic: candidates in a fixed order, one per SQL."""
    from . import answers
    allowed = _safe_steps(safe, plan)
    picked: list[dict] = []
    refused: list[dict] = []
    seen_sql: set[str] = set()
    groups_taken: dict[str, int] = {}
    cands = _candidates(plan, safe, amounts_)
    attempts = 0
    # first pass: at most one per group, so the examples show different patterns; second pass fills up to the cap
    for rnd in (1, 2):
        for group, q, tables, expect in cands:
            if len(picked) >= MAX_EXAMPLES:
                break
            if any(p["question"] == q for p in picked) or (rnd == 1 and (groups_taken.get(group) or group == "table")):
                continue
            if group == "table" and len(picked) >= MIN_EXAMPLES:
                continue                                             # one-table counts only to reach three
            if attempts >= MAX_ATTEMPTS:
                break
            attempts += 1
            try:
                a = answers.draft(plan, q, tables, show_personal_data=show_personal_data)
            except Exception as e:  # noqa: BLE001 - a question the drafter cannot read is skipped, with the reason
                refused.append({"question": q, "why": f"answer_query_draft: {e}"})
                continue
            sql = a.get("tsql")
            u = a.get("understood") or {}
            if not sql:
                refused.append({"question": q, "why": "answer_query_draft drafted no T-SQL"})
                continue
            if any(u.get(k) != v for k, v in expect.items()):
                refused.append({"question": q, "why": "answer_query_draft read the question differently"})
                continue
            bad = [s for s in a.get("path", []) if not s.get("forward") or _step_key(s) not in allowed]
            if bad:
                refused.append({"question": q, "why": f"the path uses a join that is not checked ({bad[0]['from']} -> {bad[0]['to']})"})
                continue
            if sql in seen_sql:
                continue
            seen_sql.add(sql)
            groups_taken[group] = groups_taken.get(group, 0) + 1
            picked.append({"question": q, "query": _comment(a, safe) + "\n" + sql, "tables": list(a.get("tables", tables)),
                           "joins": [f"{s['from']} -> {s['to']}" for s in a.get("path", [])]})
    order = {"path": 0, "line_amount": 1, "header_amount": 2, "join": 3, "table": 4}
    group_of = {c[1]: c[0] for c in cands}
    picked.sort(key=lambda p: order[group_of[p["question"]]])
    if attempts >= MAX_ATTEMPTS and len(picked) < MIN_EXAMPLES:
        refused.append({"question": "", "why": f"stopped after {MAX_ATTEMPTS} drafted questions"})
    return picked, refused


# ------------------------------------------------------------------ text and budget -----------

def _fit(sections: list[tuple[str, list[str], int, str]], limit: int) -> tuple[str, list[dict]]:
    """Join the sections; while the text is longer than `limit`, drop the last line of the section with the highest
    cut order (sections with cut order 0 are never cut). Returns the text and what was cut, per section."""
    sections = [(h, list(lines), order, what) for h, lines, order, what in sections]

    def text() -> str:
        return "\n\n".join(h + ("\n" + "\n".join(lines) if lines else "") for h, lines, _, _ in sections if lines or not h.startswith("##"))

    cut: dict[str, int] = {}
    t = text()
    while len(t) > limit:
        candidates = [(order, i) for i, (h, lines, order, _) in enumerate(sections) if order > 0 and lines]
        if not candidates:
            break
        _, i = max(candidates)
        h, lines, order, what = sections[i]
        lines.pop()
        cut[what] = cut.get(what, 0) + 1
        t = text()
    if len(t) > limit:                                              # only uncuttable lines left: cut on a line, and say so
        keep = t[:limit].rsplit("\n", 1)[0]
        cut["text after the limit"] = len(t) - len(keep)
        t = keep
    return t, [{"left_out": n, "what": w} for w, n in cut.items()]


def build(plan: Plan, source_name: str, schema: str, personal_data: dict | None = None, validation: dict | None = None,
          show_personal_data: bool = False, item_kind: str = "Lakehouse") -> dict:
    """Everything create_data_agent gives the agent besides the REST plumbing. Deterministic for the same inputs."""
    from . import privacy
    personal_data = personal_data or {}
    names = business_names(plan)
    j = joins(plan, validation)
    amts = repeated_amounts(plan, validation)
    shots, refused = examples(plan, j["safe"], amts, show_personal_data)
    by_table = {n["table"]: n for n in names}

    # agent instructions, in the headings data-agent-configurations.md recommends
    terms = [f"- {n['entity']} ({n['words']}" + (f"; {n['pack_name']}" if n.get("pack_name") else "") + f"): table {schema}.{n['table']}"
             for n in names]
    status = ("Every join below was counted against the rows by validate_plan; only joins that held are called safe."
              if j["validated"] else
              "No join was counted against the rows for these instructions, so none is called safe yet; "
              "create_data_agent with validate=true counts them.")
    common = ["- Joins: use only the safe joins and paths in the data source instructions, from the many side to the one side. "
              "For any other join, say that it is not checked and ask before you use it.",
              "- Two tables that both point at the same table: aggregate each to that table's key first, then join; "
              "joining them row by row multiplies rows."]
    if amts:
        common.append("- Amounts: " + "; ".join(f"never SUM({a['table']}.{a['column']}) over {a['lines']} rows" for a in amts)
                      + ". The data source instructions say how to sum them instead.")
    response = ["- Name the tables and joins an answer used, and the rule behind each join.",
                "- Quote identifiers with square brackets and qualify tables with the schema.",
                "- Write read-only T-SQL; the agent shows at most 25 rows and 25 columns, so answer with aggregates."]
    if personal_data:
        response.append("- Do not select, group by or show columns that look like personal data by name: "
                        + "; ".join(f"{f['table']}.{f['column']}" for f in privacy.findings(personal_data))
                        + ". Group by the table's key instead.")
    agent_sections = [
        ("## Objective", [f"You answer questions about the {source_name} data (schema {schema}) with T-SQL on its SQL analytics "
                          "endpoint. Keys and relationships were inferred from names and carry the rule that produced them. " + status], 0, ""),
        ("## Data sources", [f"- {source_name} ({item_kind}), schema {schema}: {len(names)} table(s)."], 0, ""),
        ("## Key terminology", terms, 3, "key terminology lines (one per table)"),
        ("## Response guidelines", response, 0, ""),
        ("## Handling common topics", common, 0, ""),
    ]
    instructions, cut_agent = _fit(agent_sections, MAX_INSTRUCTIONS)

    # data source instructions: tables and grain, safe and unsafe joins, repeated amounts
    tables_full, tables_short = [], []
    for t in plan.schema:
        key, rule = plan.keys.get(t.name, ([], "K3"))
        cols = [c for c in t.column_names if (t.name, c) not in personal_data or c in key]
        grain = (f"one row per {'+'.join(key)} (rule {plan.label(rule)})" if key else "no key found (rule K3): do not join to it as a dimension")
        head = f"- {schema}.{t.name} ({by_table[t.name]['entity']}): {grain}"
        tables_full.append(head + f"; columns {', '.join(cols)}")
        tables_short.append(head)
    safe_lines = [f"- {e['source']} -> {e['target']}: {e['on']} ({e['name']}, rule {plan.label(e['rule'])}, many-to-one; {e['checked']})"
                  for e in j["safe"]] or ["- None. " + ("No relationship held when counted." if j["validated"] else
                                                        "Nothing was counted: run create_data_agent with validate=true.")]
    path_lines = [f"- {' -> '.join(p)}" for p in safe_paths(j["safe"])]
    unsafe_lines = [f"- {e['source']} -> {e['target']}: {e['on']} (rule {plan.label(e['rule'])}): {e['why']}" for e in j["not_safe"]]
    if plan.ambiguous:
        unsafe_lines += [f"- {a['table']}.{a['column']} could point at {' or '.join(a['candidates'])}: ask which before joining"
                         for a in plan.ambiguous]
    amount_lines = [f"- {a['instruction']} ({a['status']}; {a['via']})" for a in amts]
    used = {plan.keys.get(t.name, ([], "K3"))[1] for t in plan.schema} | {r.rule for r in plan.relationships}
    rules = [f"- {k}: {v.split(' (')[0]}" for k, v in RULES.items() if k in used and k != "confirmed"]
    def ds_sections(tables):
        return [
            ("## General knowledge", [f"Tables live in schema {schema} of {source_name}. {status}"], 0, ""),
            ("## Table descriptions", tables, 5, "table descriptions"),
            ("## Safe joins (checked, many-to-one)", safe_lines, 0, ""),
            ("## Safe paths", path_lines, 4, "safe paths"),
            ("## Joins that are not safe", unsafe_lines, 2, "joins that are not safe"),
            ("## Amounts that must not be summed over lines", amount_lines, 1, "repeated amounts"),
            ("## Rules behind the keys and joins", rules, 0, ""),
        ]
    ds_text, cut_ds = _fit(ds_sections(tables_full), MAX_DATASOURCE_INSTRUCTIONS)
    if cut_ds:                                                       # first drop the column lists, then cut lines
        ds_text, cut_ds = _fit(ds_sections(tables_short), MAX_DATASOURCE_INSTRUCTIONS)
        cut_ds.insert(0, {"left_out": len(tables_full), "what": "column lists in the table descriptions"})

    description_parts = [f"{source_name}, schema {schema}: " + ", ".join(n["words"] for n in names)]
    description = description_parts[0]
    cut_desc = []
    if len(description) > MAX_DESCRIPTION:
        kept = description[:MAX_DESCRIPTION - 4].rsplit(", ", 1)[0] + ", ..."
        cut_desc = [{"left_out": description.count(", ") - kept.count(", ") + 1, "what": "table names in the description"}]
        description = kept

    cut = ([{"part": "instructions", **c} for c in cut_agent] + [{"part": "datasource_instructions", **c} for c in cut_ds]
           + [{"part": "datasource_description", **c} for c in cut_desc])
    note_examples = (f"{len(shots)} example(s) from answer_query_draft over safe joins"
                     + ("" if j["safe"] else " (no join is checked, so each uses one table)")
                     + (f"; fewer than {MIN_EXAMPLES} because the plan offers no more" if len(shots) < MIN_EXAMPLES else ""))
    return {
        "instructions": instructions, "datasource_instructions": ds_text, "datasource_description": description,
        "fewshots": [{"question": s["question"], "query": s["query"]} for s in shots],
        "context": {
            "business_names": names, "safe_joins": j["safe"], "not_safe_joins": j["not_safe"], "safe_paths": safe_paths(j["safe"]),
            "repeated_amounts": [{k: a[k] for k in ("table", "column", "lines", "kind", "status")} for a in amts],
            "validated": j["validated"], "examples": note_examples,
            "examples_turned_down": refused[:10],
            "sizes": {"instructions": len(instructions), "datasource_instructions": len(ds_text),
                      "datasource_description": len(description), "examples": len(shots)},
            "limits": LIMITS, "cut": cut,
        },
    }
