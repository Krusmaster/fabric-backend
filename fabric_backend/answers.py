"""answer_query_draft: a question in Swedish or English plus the tables it is about -> a T-SQL query over the safest
join path, and a GraphQL query against an existing API for GraphQL item when one is named. Nothing is run here.

What is read from the question, and nothing more (anything else is listed under `assumptions`):
  aggregate   count ("how many", "number of", "hur många", "antal"), sum ("total", "sum", "summa", "totalt"),
              average ("average", "mean", "genomsnitt", "snitt")
  grouping    the table or column after "per", "by", "for each", "för varje", "efter", "fördelat på"
  counted     the table after "how many" / "antal" ("how many orders per customer" counts orders)
  top N       "top 5", "topp 5", "the 5 largest", "de 10 första", "5 största"
  latest      "latest", "newest", "most recent", "senaste", "nyaste": order by the first date column, newest first
  measure     for sum and average: a numeric column named in the question, else the first numeric column that is
              neither a key nor a reference
Words are matched to tables through the same names and synonym table the inference uses (kund -> customers).

The join path: from the table the question counts (or the one every other table is reached from by many-to-one
steps) to each other table, the safest path of graphs.safest_path (cost 1/certainty per rule), merged into one join
tree. Every step carries the rule that produced its relationship. GraphQL: Fabric's API for GraphQL groups only by a
table's own columns (groupBy, fabric-docs api-graphql-aggregations.md), so an aggregate over a join is offered as
T-SQL only, and the GraphQL answer says why; lists walk the relationship fields (ManyToOne as an object, OneToMany
as a connection with items), the way app_starter writes them.
"""
from __future__ import annotations

import re

from .evidence import qi
from .graphql import graphql_name
from .infer import SYNONYMS, Plan, PlanInputError, _TRANSLIT, _bases, _canon_bases, _norm, _singulars

COUNT = ("how many", "number of", "count of", "count the", "hur många", "hur manga", "antal", "antalet", "räkna", "rakna")
SUM = ("total", "sum of", "sum ", "summa", "summan", "totalt", "sammanlagd", "sammanlagt", "sammanlagda")
AVG = ("average", "mean", "genomsnitt", "snitt", "medel")
LATEST = ("latest", "newest", "most recent", "senaste", "nyaste")
GROUP = ("for each", "for every", "per", "by", "för varje", "for varje", "för var", "efter", "fördelat på", "fordelat pa", "grouped by", "grupperat på")
_TOP = re.compile(r"\b(?:top|topp|first|första|forsta|largest|biggest|highest|most|flest|största|storsta|högsta|hogsta|de|the|which|what|"
                  r"vilka|vilken|show|visa|list|lista)\s+(\d{1,4})\b"
                  r"|\b(\d{1,4})\s+(?:största|storsta|largest|biggest|highest|most|flest|first|första|forsta|högsta|hogsta|top|topp)\b")
_WORD = re.compile(r"[a-z0-9_åäöüß]+")
LABELS = ("name", "title", "label", "description", "namn", "benamning", "beskrivning", "displayname", "fullname")
NUMERIC = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "double", "money", "smallmoney", "long", "short")
DATES = ("date", "datetime", "datetime2", "timestamp", "smalldatetime", "datetimeoffset")


def _type(t, col: str) -> str:
    return next(((c.data_type or "").lower().split("(")[0].strip() for c in t.columns if c.name == col), "")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _table_for(word: str, candidates: list[str]) -> str | None:
    w = _norm(word)
    forms = {_norm(x) for x in _singulars(word.lower().translate(_TRANSLIT))} | {w}
    syn = SYNONYMS.get(word.lower().translate(_TRANSLIT))
    if syn:
        forms.add(_norm(syn))
    for t in candidates:
        if w == _norm(t) or forms & (_bases(t) | _canon_bases(t)):
            return t
    return None


def _column_for(word: str, plan: Plan, tables: list[str]) -> tuple[str, str] | None:
    """A column of one of the tables named by the word, directly or through the synonym table (land -> country)."""
    forms = {_norm(word)} | {_norm(x) for x in _singulars(word.lower().translate(_TRANSLIT))}
    syn = SYNONYMS.get(word.lower().translate(_TRANSLIT))
    if syn:
        forms.add(_norm(syn))
    return next(((t, c) for t in tables for c in plan.schema[t].column_names if _norm(c) in forms), None)


def _after(text: str, markers: tuple[str, ...]) -> list[list[str]]:
    """The words that follow each marker, up to three, for every place a marker occurs."""
    out = []
    low = text.lower()
    for m in markers:
        for hit in re.finditer(r"(?<![a-z0-9_åäö])" + re.escape(m) + r"(?![a-z0-9_åäö])", low):
            out.append(_words(low[hit.end():])[:3])
    return out


def understand(question: str, plan: Plan, tables: list[str]) -> dict:
    q = " " + question.lower() + " "
    everything = [t.name for t in plan.schema]
    aggregate = "count" if any(m in q for m in COUNT) else "avg" if any(m in q for m in AVG) else "sum" if any(m in q for m in SUM) else None
    top = None
    m = _TOP.search(q)
    if m:
        n = int(m.group(1) or m.group(2))
        top = n if 0 < n <= 1000 else None
    else:                                                      # "5 kunder", "10 orders": a number before a table's name
        ws = _words(q)
        for a, b in zip(ws, ws[1:]):
            if a.isdigit() and 0 < int(a) <= 1000 and _table_for(b, everything):
                top = int(a)
                break
    group_table = group_column = counted = None
    for words in _after(q, GROUP):
        for w in words:
            hit = _table_for(w, tables) or _table_for(w, everything)
            if hit:
                group_table = hit
                break
            col = _column_for(w, plan, tables)
            if col:
                group_column = col
                break
        if group_table or group_column:
            break
    if aggregate is None and any(m in q for m in (" most ", " flest ", " fewest ", " minst ")):
        aggregate = "count"                                   # "which customers have the most orders": a count per customer
    if aggregate == "count":
        for words in _after(q, COUNT + ("most", "flest", "fewest", "minst")):
            hit = next((h for h in (_table_for(w, tables) or _table_for(w, everything) for w in words) if h), None)
            if hit:
                counted = hit
                break
    measure = None
    if aggregate in ("sum", "avg"):
        said = set(_norm(w) for w in _words(q))
        for t in tables:
            for c in plan.schema[t].column_names:
                if _type(plan.schema[t], c) in NUMERIC and (_norm(c) in said or _norm(SYNONYMS.get(c.lower(), c)) in said):
                    measure = (t, c)
                    break
            if measure:
                break
    if aggregate and not (group_table or group_column):
        rest = [t for t in tables if t != counted]
        if counted and rest:
            group_table = rest[0]                             # "the most orders" with customers and orders: per customer
    mentioned = []
    for w in _words(q):
        col = _column_for(w, plan, tables)
        if col and list(col) not in mentioned:
            mentioned.append(list(col))
    return {"aggregate": aggregate, "top": top, "latest": any(m in q for m in LATEST), "group_table": group_table,
            "group_column": list(group_column) if group_column else None, "counted": counted, "measure": list(measure) if measure else None,
            "columns_named": mentioned}


def _label(plan: Plan, t: str) -> str:
    cols = plan.schema[t].column_names
    singular = {_norm(x) for x in _singulars(t)}
    for c in cols:
        n = _norm(c)
        if n in LABELS or any(n == s + "name" for s in singular):
            return c
    key = plan.keys.get(t, ([], ""))[0]
    return key[0] if key else cols[0]


def _grain(plan: Plan, tables: list[str]) -> str:
    """The table every other one is reached from by many-to-one steps only (the finest grain), else the first given."""
    from .graphs import safest_path
    for t in tables:
        if all((p := safest_path(plan, t, o)) is not None and all(s["forward"] for s in p) for o in tables if o != t):
            return t
    return tables[0]


def _join_tree(plan: Plan, root: str, others: list[str]) -> tuple[list[dict], dict[str, str], bool]:
    """The merged safest paths from root: steps in join order, alias per table, and whether a step fans out."""
    from .graphs import safest_path
    aliases, steps, fans_out = {root: "t0"}, [], False
    for other in others:
        if other == root:
            continue
        path = safest_path(plan, root, other)
        if path is None:
            raise PlanInputError(f"tables: no chain of relationships connects {root} and {other}; join_path suggests the missing one")
        for s in path:
            if s["to"] in aliases:
                continue
            aliases[s["to"]] = f"t{len(aliases)}"
            fans_out = fans_out or not s["forward"]
            steps.append(s)
    return steps, aliases, fans_out


def tsql(plan: Plan, question: str, tables: list[str]) -> dict:
    names = {t.name.lower(): t.name for t in plan.schema}
    missing = [t for t in tables if t.lower() not in names]
    if missing or not tables:
        raise PlanInputError("tables: name the tables the question is about; not in the schema: " + ", ".join(repr(m) for m in missing)
                             if missing else "tables: name the tables the question is about (list_tables shows them)")
    tables = list(dict.fromkeys(names[t.lower()] for t in tables))
    u = understand(question, plan, tables)
    involved = list(dict.fromkeys(tables + [x for x in (u["group_table"], u["counted"]) if x]))
    root = u["counted"] or _grain(plan, involved)
    steps, alias, fans_out = _join_tree(plan, root, [t for t in involved if t != root])
    schema = plan.schema.schema
    assumptions = []
    joins = []
    for s in steps:
        r = s["rel"]
        left, right = (r.source_cols, r.target_cols) if s["forward"] else (r.target_cols, r.source_cols)
        on = " AND ".join(f"{alias[s['from']]}.{qi(a)} = {alias[s['to']]}.{qi(b)}" for a, b in zip(left, right))
        joins.append(f"JOIN {qi(schema)}.{qi(s['to'])} AS {alias[s['to']]} ON {on}")
    select, group, order = [], [], []
    measure = None
    root_key = plan.keys.get(root, ([], ""))[0]
    if u["aggregate"]:
        if u["group_table"] and u["group_table"] != root:
            g = u["group_table"]
            cols = list(dict.fromkeys(plan.keys.get(g, ([], ""))[0] + [_label(plan, g)]))
            select += [f"{alias[g]}.{qi(c)}" for c in cols]
            group += [f"{alias[g]}.{qi(c)}" for c in cols]
        elif u["group_column"]:
            t, c = u["group_column"]
            select.append(f"{alias[t]}.{qi(c)}")
            group.append(f"{alias[t]}.{qi(c)}")
        if u["aggregate"] == "count":
            name = f"{root}_count"
            if fans_out and root_key:
                expr = "COUNT(DISTINCT " + " + '|' + ".join(f"CAST(t0.{qi(c)} AS varchar(400))" for c in root_key) + ")" if len(root_key) > 1 \
                    else f"COUNT(DISTINCT t0.{qi(root_key[0])})"
                assumptions.append(f"the path goes one-to-many, so each {root} row is counted once (DISTINCT on its key)")
            else:
                expr = "COUNT_BIG(*)"
        else:
            if u["measure"]:
                mt, mc = u["measure"]
            else:
                refs = {c.lower() for r in plan.relationships for c in r.source_cols if r.source == root}
                mt, mc = root, next((c for c in plan.schema[root].column_names if _type(plan.schema[root], c) in NUMERIC
                                     and c not in root_key and c.lower() not in refs), None)
                if mc is None:
                    raise PlanInputError(f"no numeric column in {root} to {'sum' if u['aggregate'] == 'sum' else 'average'}; name the column in the question")
                assumptions.append(f"the question names no column to {'sum' if u['aggregate'] == 'sum' else 'average'}: {root}.{mc} is the first numeric column that is neither key nor reference")
            measure = [mt, mc]
            name = f"{'total' if u['aggregate'] == 'sum' else 'average'}_{mc}"
            expr = f"SUM({alias[mt]}.{qi(mc)})" if u["aggregate"] == "sum" else f"AVG(CAST({alias[mt]}.{qi(mc)} AS float))"
            if fans_out and u["aggregate"] == "sum":
                assumptions.append("the path goes one-to-many, so a value can be counted more than once in the sum; check the grain")
        select.append(f"{expr} AS {qi(name)}")
        order.append(f"{qi(name)} DESC")
    else:
        select += [f"t0.{qi(c)}" for c in plan.schema[root].column_names]
        for t in involved:
            if t != root:
                cols = [c for tt, c in u["columns_named"] if tt == t] or [_label(plan, t)]
                select += [f"{alias[t]}.{qi(c)} AS {qi(t + '_' + c)}" for c in cols]
        if fans_out:
            back = next(s for s in steps if not s["forward"])
            assumptions.append(f"the path goes one-to-many ({back['from']} -> {back['to']}): a {root} row appears once per {back['to']} row")
        if u["latest"]:
            date_col = next((c for c in plan.schema[root].column_names if _type(plan.schema[root], c) in DATES), None)
            if date_col:
                order.append(f"t0.{qi(date_col)} DESC")
            else:
                assumptions.append(f"'latest' asked for, but {root} has no date column; ordered by its key")
        if not order and root_key:
            order += [f"t0.{qi(c)}" for c in root_key]
    top = u["top"] or (None if u["aggregate"] else 100)
    if u["aggregate"] and not group and u["top"]:
        top = None
    sql = (("SELECT " + (f"TOP ({top}) " if top else "")) + ", ".join(select) + f"\nFROM {qi(schema)}.{qi(root)} AS t0"
           + "".join("\n" + j for j in joins) + (("\nGROUP BY " + ", ".join(group)) if group else "")
           + (("\nORDER BY " + ", ".join(order)) if order and (group or not u["aggregate"]) else ""))
    if not u["aggregate"] and not u["top"]:
        assumptions.append("no number of rows asked for: the first 100")
    if u["aggregate"] and not (u["group_table"] or u["group_column"]):
        assumptions.append("no grouping asked for: one total")
    return {"understood": u, "root": root, "tables": involved, "measure": measure,
            "path": [{k: v for k, v in s.items() if k not in ("rel", "cost")} for s in steps], "sql": sql, "assumptions": assumptions,
            "_steps": steps}


def _types_by_table(description: dict) -> dict[str, dict]:
    return {str(t.get("source", "")).split(".")[-1].lower(): t for t in description.get("types", [])}


def graphql(plan: Plan, description: dict, answer: dict) -> dict:
    """The GraphQL query for an answer from tsql(), against the API described by describe_definition()."""
    types = _types_by_table(description)
    u, root = answer["understood"], answer["root"]
    rt = types.get(root.lower())
    if rt is None:
        return {"not_possible": f"the API has no type for {root}; describe_backend lists what it exposes"}
    if u["aggregate"]:
        group_fields = []
        if u["group_column"] and u["group_column"][0] == root:
            group_fields = [graphql_name(u["group_column"][1].lstrip("_"))]
        elif u["group_table"] and u["group_table"] != root:
            step = next((s for s in answer["_steps"] if s["to"] == u["group_table"] and s["from"] == root and s["forward"]), None)
            if step is None:
                return {"not_possible": f"Fabric's API for GraphQL groups only by a table's own columns, and {u['group_table']} is more than one "
                                        "many-to-one step from {root}; the T-SQL answers it".replace("{root}", root)}
            group_fields = [graphql_name(c.lstrip("_")) for c in step["rel"].source_cols]
        elif u["group_column"] or u["group_table"]:
            return {"not_possible": "Fabric's API for GraphQL groups only by the queried table's own columns; the T-SQL answers it"}
        if u["aggregate"] == "count":
            key = plan.keys.get(root, ([], ""))[0]
            field = graphql_name((key[0] if key else plan.schema[root].column_names[0]).lstrip("_"))
            agg = f"count(field: {field})"
        else:
            mt, mc = answer.get("measure") or [root, None]
            if mt != root or mc is None:
                return {"not_possible": f"the column to aggregate is in {mt}, not in {root}; GraphQL aggregates a table's own columns, the T-SQL answers it"}
            agg = f"{u['aggregate']}(field: {graphql_name(mc.lstrip('_'))})"
        missing = [f for f in group_fields + [agg.split("field: ")[1].rstrip(")")] if f not in rt.get("fields", [])]
        if missing:
            return {"not_possible": f"the API's {rt['type']} has no field {', '.join(missing)}"}
        if not group_fields:
            return {"not_possible": "Fabric documents its GraphQL aggregations with groupBy only; for one total, the T-SQL answers it"}
        query = (f"query {{ {rt['query_field']} {{ groupBy(fields: [{', '.join(group_fields)}]) {{ fields {{ {' '.join(group_fields)} }} "
                 f"aggregations {{ {agg} }} }} }} }}")
        notes = ["groups come back unordered and without a limit: sort and cut them in the client (Fabric's aggregations have no top N)"]
        if u["group_table"] and u["group_table"] != root:
            notes.append(f"grouped by the reference column ({', '.join(group_fields)}), not by {u['group_table']}'s name; the T-SQL returns the name")
        return {"query": query, "notes": notes}
    # a list: walk the relationship fields along the join tree
    children: dict[str, list[dict]] = {}
    for s in answer["_steps"]:
        children.setdefault(s["from"], []).append(s)

    def fields_of(table: str, n: int) -> list[str]:
        t = types[table.lower()]
        return [f for f in t.get("fields", []) if not f.startswith("_")][:n]

    def block(table: str, depth: int) -> str:
        parts = fields_of(table, 8 if depth == 0 else 4)
        for s in children.get(table, []):
            r, tt = s["rel"], types.get(s["to"].lower())
            if tt is None:
                raise LookupError(s["to"])
            want = (r.field_name if s["forward"] else r.reverse_name) or ""
            card = "ManyToOne" if s["forward"] else "OneToMany"
            rels = [x for x in types[table.lower()].get("relationships", []) if str(x.get("to", "")).split(".")[-1].lower() == s["to"].lower()
                    and x.get("cardinality") == card]
            rel = next((x for x in rels if x.get("field") == want), rels[0] if rels else None)
            if rel is None:
                raise LookupError(f"{table} -> {s['to']}")
            inner = block(s["to"], depth + 1)
            parts.append(f"{rel['field']} {{ {inner} }}" if card == "ManyToOne" else f"{rel['field']} {{ items {{ {inner} }} }}")
        return " ".join(parts)
    try:
        body = block(root, 0)
    except LookupError as e:
        return {"not_possible": f"the API has no relationship field for {e}; plan_drift shows what differs from today's plan"}
    args = [f"first: {u['top'] or 100}"]
    if u["latest"]:
        date_col = next((c for c in plan.schema[root].column_names if _type(plan.schema[root], c) in DATES), None)
        if date_col and graphql_name(date_col.lstrip("_")) in rt.get("fields", []):
            args.append(f"orderBy: {{ {graphql_name(date_col.lstrip('_'))}: DESC }}")
    return {"query": f"query {{ {rt['query_field']}({', '.join(args)}) {{ items {{ {body} }} }} }}", "notes": []}


def draft(plan: Plan, question: str, tables: list[str], description: dict | None = None, api: str | None = None) -> dict:
    a = tsql(plan, question, tables)
    out = {"question": question, "understood": a["understood"], "tables": a["tables"], "starts_at": a["root"],
           "path": a["path"], "tsql": a["sql"], "assumptions": a["assumptions"]}
    if description is not None:
        g = graphql(plan, description, a)
        out["graphql"] = dict(g, api=api)
    out["runs"] = ("nothing: the T-SQL runs on the source's SQL analytics endpoint or a warehouse" +
                   ("; query_graphql with question= and tables= runs the GraphQL version" if description is not None else ""))
    return out
