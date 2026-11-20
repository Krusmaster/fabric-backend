"""Round DA2 (19 November 2026): topics and example-query templates for a Fabric data agent, written by rules from what
Krusgraph already knows about the source. No language model and no AI here: the same plan and the same counts give the
same text, byte for byte. Nothing here calls Fabric; data_agent.apply writes what draft() returns.

What Microsoft Learn documents (read 19 November 2026; the sources and what is not documented are in
docs/DATA-AGENT-TOPICS-TEMPLATES.md):

- Topics (preview): "large, topic-based instructions that help a Fabric data agent generate SQL"; "available only for
  SQL data sources on the preview runtime"; "up to 1 million characters of topic content to each supported SQL data
  source"; "Use Markdown headings to organize the content into distinct subjects"; "Keep each topic self-contained.
  Include the relevant business definitions, tables, columns, relationships, filters, and calculation rules under the
  same topic heading" (fabric/data-science/data-agent-topics, updated 2026-09-10). Written one file per topic with
  Staging - Upload Datasource Topic: PUT /v1/workspaces/{ws}/dataAgents/{id}/staging/datasources/{dsId}/topics?fileName=
  {name}.md, body text/markdown that "May include YAML frontmatter with name and description fields"; "If a file with
  the same name already exists, it is replaced" (rest/api/fabric/dataagent/staging/upload-datasource-topic, updated
  2026-11-04, "Data Agent configuration management is currently in Preview").
- Example queries: {question, query} per data source, "Fewshots aren't supported for Semantic Model and Ontology
  datasources" (Staging - Create Datasource Fewshot); no parameter field is documented. Learn's own advice for values to
  fill in is a comment in the query ("-- substitute customer_id here", data-agent-example-queries, best practice 2), and
  every example "is validated against the schema of the selected data source". So the templates here are plain,
  runnable T-SQL, and the places to put a customer, a period or another filter are comments, not parameters.

Areas come from domains.propose_plan (the plan's tables grouped by their links, a knowledge pack's names where one
recognised them: order-to-cash and customer master on SAP-shaped data). Each topic holds, for its area's tables only:
what Krusgraph knows each table and its columns mean (the pack's description and note, keys with their rule, which
column points at which table, the amounts and their currency), the joins that were counted and held, with the counts as
evidence, the joins not to use without asking and why, and the known traps (a header amount summed over its lines, the
pack's traps that name a table of the area). Joins are called checked only when validate_plan counted them; without
counts the topic says so and lists none as checked.
"""
from __future__ import annotations

import re

from .evidence import qi
from .infer import Plan

TOPIC_PREFIX = "krusgraph-"                 # Krusgraph writes and replaces only topic files with this prefix
MAX_TOPIC_CHARS_PER_SOURCE = 1_000_000      # documented: "up to 1 million characters of topic content" per SQL source
MAX_TEMPLATES = 20                          # Krusgraph's own cap; Learn documents up to 100 example queries per source
TOP = 25                                    # the agent shows at most 25 rows (concept-data-agent, Limitations)
DATE_TYPES = ("date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "timestamp", "timestamp_ntz")
APPROVAL = ("A person approves this text by reading create_data_agent's dry run and calling it again with "
            "dry_run=false; Krusgraph writes nothing before that.")
# Learn, data-agent-add-datasources (updated 2026-09-30): the SQL category is "Lakehouse, Data Warehouse, SQL Database,
# Mirrored Databases"; Krusgraph's other sources (a mirrored catalog, a Snowflake database item) are not named there.
SQL_KINDS = ("Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase")


def _words(name: str) -> list[str]:
    from .infer import _words as w
    return w(name)


def _phrase(table: str) -> str:
    return " ".join(_words(table)) or table.lower()


def _singular(table: str) -> str:
    from .infer import _singulars
    words = _words(table) or [table.lower()]
    last = sorted(_singulars(words[-1]), key=lambda s: (len(s), s))[0]
    return " ".join(words[:-1] + [last])


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "area"


def _pack_tables(plan: Plan) -> tuple[dict[str, str], dict[str, dict], list[dict]]:
    """(schema table -> pack table name, pack table name -> its entry, the pack's traps with their text)."""
    pack = getattr(plan, "pack", None) or {}
    names = dict(pack.get("tables") or {})
    if not names:
        return {}, {}, []
    try:
        from . import sap_pack
        loaded = sap_pack.load(pack.get("pack", "sap"))
    except Exception:  # noqa: BLE001 - a pack that cannot be read gives no descriptions; the topic says less, never wrong
        return names, {}, []
    return names, loaded.get("tables", {}), list(loaded.get("traps", []))


def _label(plan: Plan, table: str, many: bool = False) -> str:
    """How a question names a table: the pack's own name with its description's first words (KNA1 (customer master)),
    else the table's words (customer, orders)."""
    names, entries, _ = _pack_tables(plan)
    en = (entries.get(names.get(table, ""), {}) or {}).get("en")
    if en:
        return f"{names[table]} ({en.split(',')[0].lower()})"
    return _phrase(table) if many else _singular(table)


# ------------------------------------------------------------------ areas ---------------------

def areas(plan: Plan, validation: dict | None = None) -> list[dict]:
    """[{name, slug, tables}] in the order domain_draft proposes them; tables no area took form one last area."""
    from . import domains
    d = domains.propose_plan(plan, validation)
    out = [{"name": x["name"], "slug": x.get("slug") or _slug(x["name"]), "tables": sorted(x["tables"])} for x in d["domains"]]
    taken = {t for a in out for t in a["tables"]}
    rest = sorted(t.name for t in plan.schema if t.name not in taken)
    if rest:
        out.append({"name": "other tables", "slug": "other-tables", "tables": rest})
    return out


# ------------------------------------------------------------------ evidence ------------------

def counted(validation: dict | None) -> dict[tuple, dict]:
    """validate_plan's relationship entries by (source, columns lowered, target)."""
    out = {}
    for v in (validation or {}).get("relationships", []):
        if "kind" not in v and "columns" in v:
            out[(v["source"], tuple(c.lower() for c in v["columns"]), v["target"])] = v
    return out


def evidence_line(v: dict | None, target: str) -> str:
    """The counts behind one join, as words: never a row value."""
    if not v:
        return "not counted"
    n, orphans = v.get("rows_with_value"), v.get("orphans")
    if not isinstance(n, int) or not isinstance(orphans, int):
        return str(v.get("verdict") or "counted")
    if n == 0:
        return "counted: no row has a value in the join columns, so nothing shows the join holds"
    rate = round(100 * (n - orphans) / n, 1)
    return f"counted: {n - orphans} of {n} rows with a value find their {target} row ({rate}% match)"


# ------------------------------------------------------------------ topics --------------------

def _table_lines(plan: Plan, t, schema: str, refs: dict, names: dict, entries: dict, personal: dict) -> list[str]:
    key, rule = plan.keys.get(t.name, ([], "K3"))
    entry = entries.get(names.get(t.name, ""), {})
    head = f"- `{schema}.{t.name}`"
    if entry.get("en"):
        head += f" ({names[t.name]}: {entry['en']})"
    head += (f": one row per {' + '.join(key)} (key rule {plan.label(rule)})." if key else
             ": no key found (rule K3); do not join to it as a dimension.")
    if entry.get("note"):
        head += f" {entry['note']}"
    lines = [head]
    for c in t.column_names:
        if (t.name, c) in personal and c not in key:
            continue
        said = []
        if c in key:
            said.append("part of the key")
        said += [f"points at {x}" for x in refs.get((t.name, c), [])]
        for a in entry.get("amounts", []):
            if a.get("column", "").lower() == c.lower():
                said.append(f"an amount at {a.get('level', 'its')} level, in the currency of {a.get('currency')}")
        if c.upper() in (entry.get("delta") or []):
            said.append("a date the pack lists for changes (delta)")
        if said:
            lines.append(f"  - `{c}`: {'; '.join(said)}.")
    left = [c for c in t.column_names if (t.name, c) in personal and c not in key]
    if left:
        lines.append(f"  - Left out as personal data by name: {', '.join(left)}. Do not select, group by or show them.")
    return lines


def topic(plan: Plan, area: dict, schema: str, joins: dict, validation: dict | None, amounts_: list[dict],
          personal: dict | None = None) -> dict:
    """One area's topic file: YAML front matter (name, description), then one Markdown heading for the area."""
    personal = personal or {}
    tables = set(area["tables"])
    names, entries, traps = _pack_tables(plan)
    by_count = counted(validation)
    refs: dict[tuple[str, str], list[str]] = {}
    for r in plan.relationships:
        for c in r.source_cols:
            ref = f"{r.target}.{'+'.join(r.target_cols)} (rule {plan.label(r.rule)})"
            if ref not in refs.setdefault((r.source, c), []):
                refs[(r.source, c)].append(ref)
    words = [(f"{names[t]} {entries[names[t]]['en']}" if entries.get(names.get(t, ""), {}).get("en") else _phrase(t))
             for t in area["tables"]]
    title = area["name"][:1].upper() + area["name"][1:]
    description = (f"Questions about {area['name']}: " + "; ".join(dict.fromkeys(words)))[:400]
    lines = ["---", f"name: {title}", f"description: {_yaml(description)}", "---", "", f"## {title}", "",
             f"Use these tables for questions about {area['name']}. Written by Krusgraph by rules from the plan"
             + (" and validate_plan's counts" if joins["validated"] else " (nothing was counted yet)") + f". {APPROVAL}", "",
             "### Tables and what their fields mean", ""]
    for t in plan.schema:
        if t.name in tables:
            lines += _table_lines(plan, t, schema, refs, names, entries, personal)

    def touches(e):
        return e["source"] in tables or e["target"] in tables

    safe = [e for e in joins["safe"] if touches(e)]
    lines += ["", "### Checked joins (use these)", ""]
    if safe:
        for e in safe:
            v = by_count.get((e["source"], tuple(c.split(".")[-1].strip().lower() for c in _left_cols(e)), e["target"]))
            origin = "confirmed by you, " if e["rule"] == "confirmed" else ""
            lines.append(f"- `{e['on']}`: {e['source']} to {e['target']}, many-to-one ({origin}rule {plan.label(e['rule'])}; "
                         f"{evidence_line(v, e['target'])}; the target key is unique).")
    else:
        lines.append("- None yet. " + ("No join of this area held when counted." if joins["validated"] else
                                       "No join was counted: create_data_agent with validate=true counts them."))
    unsafe = [e for e in joins["not_safe"] if touches(e)]
    if unsafe:
        lines += ["", "### Joins not to use without asking", ""]
        for e in unsafe:
            v = by_count.get((e["source"], tuple(c.split(".")[-1].strip().lower() for c in _left_cols(e)), e["target"]))
            extra = f"; {evidence_line(v, e['target'])}" if v else ""
            lines.append(f"- `{e['on']}` (rule {plan.label(e['rule'])}): {e['why']}{extra}.")
    trap_lines = [f"- {a['instruction']}" for a in amounts_ if a["table"] in tables or a["lines"] in tables]
    trap_lines += [f"- `{a['table']}.{a['column']}` could point at {' or '.join(a['candidates'])}: ask which before joining."
                   for a in plan.ambiguous if a["table"] in tables]
    area_pack = {names[t] for t in tables if t in names}
    for tr in traps:
        if any(re.search(rf"\b{re.escape(n)}\b", tr.get("text", "")) for n in area_pack):
            trap_lines.append(f"- {tr['title']}: {tr['text']}")
    lines += ["", "### Known traps", ""] + (trap_lines or ["- None known for these tables."])
    md = "\n".join(lines).rstrip() + "\n"
    return {"file_name": f"{TOPIC_PREFIX}{area['slug'].replace('_', '-')}.md", "name": title, "description": description,
            "tables": sorted(tables), "markdown": md, "chars": len(md)}


def _left_cols(e: dict) -> list[str]:
    """The source side's columns of a join entry's `on` text (a.x = b.y AND ...)."""
    return [part.split(" = ")[0] for part in e["on"].split(" AND ")]


def _yaml(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def topics(plan: Plan, schema: str, joins: dict, validation: dict | None, amounts_: list[dict],
           personal: dict | None = None) -> dict:
    """{"topics": [...], "left_out": [...]} : one topic per area, within the documented 1 million characters."""
    out, total, left = [], 0, []
    for a in areas(plan, validation):
        t = topic(plan, a, schema, joins, validation, amounts_, personal)
        if total + t["chars"] > MAX_TOPIC_CHARS_PER_SOURCE:
            left.append({"topic": t["file_name"], "why": "over the documented 1 million characters per data source"})
            continue
        total += t["chars"]
        out.append(t)
    return {"topics": out, "left_out": left, "chars": total}


# ------------------------------------------------------------------ templates -----------------

def _dates(t) -> list[str]:
    """Columns of a date type, then the pack's change dates; Krusgraph does not guess a date from a name."""
    return [c.name for c in t.columns if c.name in t.column_names
            and str(c.data_type).lower().split("(")[0] in DATE_TYPES]


def _filter_comments(plan: Plan, source: str, target_alias: str, target: str, target_cols: list[str], safe: list[dict],
                     extra_dates: list[str]) -> list[str]:
    key_filter = " AND ".join(f"{target_alias}.{qi(c)} = '<{c}>'" for c in target_cols)
    out = [f"-- For one {_label(plan, target)}, add: WHERE {key_filter}"]
    dates = _dates(plan.schema[source]) + [d for d in extra_dates if d in plan.schema[source].column_names and d not in _dates(plan.schema[source])]
    if dates:
        out.append(f"-- For one period, add: WHERE s.{qi(dates[0])} BETWEEN '<from>' AND '<to>'")
    for e in safe:
        if e["source"] == source and e["target"] != target:
            cols = [c.split(".", 1)[1] for c in _left_cols(e)]
            cond = " AND ".join(f"s.{qi(c)} = '<{c}>'" for c in cols)
            out.append(f"-- For one {_label(plan, e['target'])}, add: WHERE {cond}")
    return out


def templates(plan: Plan, schema: str, safe: list[dict], validation: dict | None, taken: set[str] | None = None,
              area_of: dict[str, str] | None = None) -> list[dict]:
    """One runnable example per checked join, grouped by the target's key, with comments that say where a customer, a
    period or another filter goes (Learn's advice; no parameter format is documented). Deterministic, at most
    MAX_TEMPLATES, never a question already in `taken`."""
    taken = set(taken or ())
    by_count = counted(validation)
    names, entries, _ = _pack_tables(plan)
    rels = {(r.source, r.target, " AND ".join(f"{r.source}.{a} = {r.target}.{b}" for a, b in zip(r.source_cols, r.target_cols))): r
            for r in plan.relationships}
    out = []
    order = {a: i for i, a in enumerate(dict.fromkeys((area_of or {}).values()))}
    for e in sorted(safe, key=lambda e: (order.get((area_of or {}).get(e["source"], ""), len(order)), e["source"], e["target"], e["on"])):
        r = rels.get((e["source"], e["target"], e["on"]))
        if r is None or e["source"] == e["target"]:
            continue
        src = _label(plan, e["source"], many=True)
        src += " rows" if src.endswith(")") else ""
        q = f"Which {_label(plan, e['target'])} has the most {src}?"
        if q in taken:
            own = [a for a, b in zip(r.source_cols, r.target_cols) if a.lower() != b.lower()] or list(r.source_cols)
            q = f"Which {_label(plan, e['target'])} has the most {src} by {', '.join(own)}?"
        if q in taken:
            continue
        taken.add(q)
        v = by_count.get((r.source, tuple(c.lower() for c in r.source_cols), r.target))
        count = qi(f"{r.source}_count")
        group = ", ".join(f"t.{qi(c)}" for c in r.target_cols)
        on = " AND ".join(f"s.{qi(a)} = t.{qi(b)}" for a, b in zip(r.source_cols, r.target_cols))
        delta = (entries.get(names.get(r.source, ""), {}) or {}).get("delta") or []
        sql = "\n".join([f"-- Template from the checked join {e['on']} (rule {plan.label(r.rule)}; {evidence_line(v, r.target)}).",
                         *_filter_comments(plan, r.source, "t", r.target, list(r.target_cols), safe, list(delta)),
                         f"SELECT TOP ({TOP}) {group}, COUNT_BIG(*) AS {count}",
                         f"FROM {qi(schema)}.{qi(r.source)} AS s",
                         f"JOIN {qi(schema)}.{qi(r.target)} AS t ON {on}",
                         f"GROUP BY {group}",
                         f"ORDER BY {count} DESC"])
        out.append({"question": q, "query": sql, "from": f"checked join {r.source} -> {r.target}",
                    "area": (area_of or {}).get(r.source, "")})
        if len(out) >= MAX_TEMPLATES:
            break
    return out


def gold_templates(views: list[dict], gold_schema: str, plan: Plan | None = None) -> list[dict]:
    """Per gold view: its rows counted per the first joined table whose key the view carries (each join key once, under
    the referencing column's name), with a period comment when the fact has a date column."""
    out = []
    for v in views:
        name = v["name"].split(".", 1)[-1]
        once = v.get("keys_once") or []
        for j in v.get("joins", []):
            cols = [x["same_as"] for x in once if x["table"] == j["to"] and x["column"] in j["target_cols"]]
            if len(cols) != len(j["target_cols"]):
                continue
            count = qi(f"{v['fact']}_count")
            group = ", ".join(qi(c) for c in cols)
            lines = [f"-- Template over the gold view {gold_schema}.{name}: one row per {v['fact']} row, joined over checked keys.",
                     f"-- For one {_label(plan, j['to']) if plan is not None else _singular(j['to'])}, add: WHERE " + " AND ".join(f"{qi(c)} = '<{c}>'" for c in cols)]
            if plan is not None and v["fact"] in plan.schema.tables:
                dates = _dates(plan.schema[v["fact"]])
                if dates:
                    lines.append(f"-- For one period, add: WHERE {qi(dates[0])} BETWEEN '<from>' AND '<to>'")
            lines += [f"SELECT TOP ({TOP}) {group}, COUNT_BIG(*) AS {count}", f"FROM {qi(gold_schema)}.{qi(name)}",
                      f"GROUP BY {group}", f"ORDER BY {count} DESC"]
            out.append({"question": (f"How many {_label(plan, v['fact'], many=True) if plan is not None else _phrase(v['fact'])} rows are there "
                                     f"per {_label(plan, j['to']) if plan is not None else _singular(j['to'])} in the gold view {name}?"),
                        "query": "\n".join(lines), "from": f"gold view {gold_schema}.{name}", "area": ""})
            break
        if len(out) >= MAX_TEMPLATES:
            break
    return out


def build(plan: Plan, schema: str, joins: dict, validation: dict | None, amounts_: list[dict], personal: dict | None = None,
          taken: set[str] | None = None) -> dict:
    """Topics and templates for one layer's tables in `schema`."""
    t = topics(plan, schema, joins, validation, amounts_, personal)
    area_of = {tb: a["name"] for a in areas(plan, validation) for tb in a["tables"]}
    return {"topics": t["topics"], "topics_left_out": t["left_out"], "topic_chars": t["chars"],
            "templates": templates(plan, schema, joins["safe"], validation, taken, area_of)}

