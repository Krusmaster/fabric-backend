"""Gold views as materialized lake views (MLV): one wide view per fact table over the silver tables, generated from the
plan, with data quality rules that mirror the plan's keys and relationships. A Fabric PySpark notebook creates them;
nothing here talks to Fabric.

What the syntax and the rules rest on (MicrosoftDocs/fabric-docs a2de7f9, read 26 October 2026; learn.microsoft.com
/fabric/data-engineering/materialized-lake-views/...):
- create-materialized-lake-view.md (ms.date 09/30/2026): `CREATE [OR REPLACE] MATERIALIZED LAKE VIEW [IF NOT EXISTS]
  [workspace.lakehouse.schema].MLV_Identifier [( CONSTRAINT name CHECK (condition) [ON MISMATCH DROP | FAIL], ... )]
  [PARTITIONED BY (...)] [COMMENT "..."] [TBLPROPERTIES ("key"="val", ...)] AS select_statement`; OR REPLACE and IF NOT
  EXISTS can't be combined; names are case-insensitive and stored in lower case; all-uppercase schema names are not
  supported; no UDFs, no temporary views, no time travel in the SELECT.
- lakehouse-schemas.md: "Features like materialized lake views require schema-enabled lakehouses"; the get-started page
  asks for Fabric Runtime 1.3 and creates them with Spark SQL in a notebook.
- data-quality.md (03/18/2026): FAIL "stops MLV refresh at the first constraint violation. This is the default
  behavior"; DROP "continues processing and removes records that violate the constraint. The lineage view shows the
  count of dropped records." refresh-materialized-lake-view.md: only deterministic built-in functions in constraints.
- Status: materialized lake views are generally available since September 2026 (fundamentals/whats-new.md); data
  quality constraints, optimal refresh and time-based schedules carry no preview label; REFRESH_HINT, event-triggered
  schedules, the PySpark authoring API and the notebook utility are preview and are not used here.
- schedule-lineage-run.md (09/08/2026): the schedule is set in the lakehouse (Manage materialized lake views -> Manage
  schedules); materialized-lake-views-public-api.md and fabric-rest-api-specs a96c37a lakehouse/swagger.json:
  `POST /workspaces/{id}/lakehouses/{id}/jobs/refreshMaterializedLakeViews/instances` (run now; Lakehouse.Execute.All or
  Item.Execute.All) and `.../refreshMaterializedLakeViews/schedules` (also Lakehouse.ReadWrite.All or Item.ReadWrite.All;
  one active refresh schedule per lineage).

Every rule is DROP: a row that breaks one is left out of the view and counted in the lineage view, which is what the
silver notebook's quarantine does one layer down; FAIL would stop the whole refresh on one row. A CHECK sees one row
at a time, so a key's uniqueness cannot be a constraint: the silver tables are already de-duplicated on the key.

`spec()` is the plan of the views as data; `statements()` the SQL; `notebook_source()` the notebook; `run_select()`
executes a view's SELECT on any DB-API connection (the tests use SQLite and a local Spark).
"""
from __future__ import annotations

import heapq
import json
import re

from . import notebook as _nb
from . import privacy as _privacy
from .graphs import certainty
from .infer import Plan, PlanInputError, RULES

DEFAULT_SCHEMA = "gold"
GOLD_TOKEN, SILVER_TOKEN = "{GOLD_SCHEMA}", "{SILVER_SCHEMA}"      # in the notebook's SQL, replaced by the parameters' values
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
PROPERTY = "krusgraph.gold"


def q(name: str) -> str:
    """A Spark SQL identifier in backticks."""
    return "`" + str(name).replace("`", "``") + "`"


def _rule_text(rule: str) -> str:
    return RULES.get(rule, rule).split(";")[0].split(" — ")[0]


def _constraint_name(*parts: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", "_".join(parts).lower()).strip("_")[:120]


def safest_tree(plan: Plan, fact: str, within: set[str] | None = None) -> list[dict]:
    """From the fact, every table reachable by many-to-one steps, each over its safest path (Dijkstra on 1/certainty,
    graphs.WEIGHTS: declared and confirmed links first, then R1, R2, R3/R4). Steps in join order (a table's parent is
    joined before it). `within` keeps the walk to those tables (the ones a silver notebook built for `tables` holds)."""
    by_source: dict[str, list] = {}
    for r in plan.relationships:
        if r.target in plan.keys and r.source != r.target and (within is None or r.target in within):
            by_source.setdefault(r.source, []).append(r)
    best: dict[str, float] = {fact: 0.0}
    via: dict[str, tuple[str, object]] = {}
    heap = [(0.0, fact)]
    while heap:
        d, t = heapq.heappop(heap)
        if d > best.get(t, float("inf")) + 1e-12:
            continue
        for r in sorted(by_source.get(t, []), key=lambda x: (x.target, x.source_cols)):
            nd = d + 1 / certainty(r)
            if nd < best.get(r.target, float("inf")) - 1e-12:
                best[r.target] = nd
                via[r.target] = (t, r)
                heapq.heappush(heap, (nd, r.target))
    order = sorted(via, key=lambda t: (best[t], t))
    return [{"from": via[t][0], "to": t, "rel": via[t][1], "cost": round(best[t], 4)} for t in order]


def _unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        k = n.lower()
        seen[k] = seen.get(k, 0) + 1
        out.append(n if seen[k] == 1 else f"{n}_{seen[k]}")
    return out


def spec(plan: Plan, info: dict, silver_schema: str = "silver", gold_schema: str = DEFAULT_SCHEMA, tables: list[str] | None = None,
         show_personal_data: bool = False, within: list[str] | None = None) -> dict:
    """The views as data. Raises PlanInputError when the lakehouse has no schemas (MLV needs them), a schema name will
    not do, or a target would be a source or silver table."""
    from . import graphs
    schema = info.get("schema") or plan.schema.schema
    gold_schema, silver_schema = (gold_schema or "").strip(), (silver_schema or "").strip()
    if not info.get("schemas_enabled", True):
        raise PlanInputError("materialized lake views need a lakehouse created with schemas (Lakehouse schemas); this one has none. "
                             "Create a lakehouse with schemas and add the tables as shortcuts, or use create_views for T-SQL views.")
    for label, value in (("gold_schema", gold_schema), ("silver_schema", silver_schema)):
        if not _IDENT.match(value or ""):
            raise PlanInputError(f"{label}: letters, digits and underscores, starting with a letter")
        if value.isupper():
            raise PlanInputError(f"{label}: all-uppercase schema names are not supported for materialized lake views; use lower case")
    # materialized lake view names "are case-insensitive and stored in lowercase" (create-materialized-lake-view.md): one
    # spelling everywhere, so the notebook's guard checks exactly the name its CREATE statement writes
    gold_schema, silver_schema = gold_schema.lower(), silver_schema.lower()
    if gold_schema.lower() in (schema.lower(), silver_schema.lower()):
        raise PlanInputError(f"gold_schema {gold_schema!r} is the {'source' if gold_schema.lower() == schema.lower() else 'silver'} schema; "
                             "the gold views need a schema of their own")
    roles = graphs.analyze(plan)["roles"]
    facts = [t.name for t in plan.schema if roles[t.name]["role"] == "fact"]
    if tables:
        names = {t.name.lower(): t.name for t in plan.schema}
        missing = [t for t in tables if t.lower() not in names]
        if missing:
            raise PlanInputError("tables: not in the schema: " + ", ".join(repr(m) for m in missing))
        wanted = {names[t.lower()] for t in tables}
        not_facts = sorted(wanted - set(facts))
        if not_facts:
            raise PlanInputError("tables: only fact tables get a gold view; not a fact table in the plan: " + ", ".join(not_facts)
                                 + " (analyze_schema shows the roles)")
        facts = [f for f in facts if f in wanted]
    inside = None
    if within:
        names = {t.name.lower(): t.name for t in plan.schema}
        inside = {names[t.lower()] for t in within if t.lower() in names}
        facts = [f for f in facts if f in inside]
    flagged = _privacy.personal_columns(plan.schema)
    sources = {f"{schema}.{t.name}".lower() for t in plan.schema}
    silver = {f"{silver_schema}.{t.name}".lower() for t in plan.schema}
    views, omitted, kept = [], [], []
    for fact in sorted(facts, key=str.lower):
        target = f"{gold_schema}.{fact}".lower()
        if target in sources or target in silver:
            raise PlanInputError(f"the gold view for {fact} would be {target}, which is a {'source' if target in sources else 'silver'} table; "
                                 "choose another gold_schema")
        steps = safest_tree(plan, fact, inside)
        alias = {fact: "f"}
        for i, s in enumerate(steps, 1):
            alias[s["to"]] = f"d{i}"
        needed = {(fact, c.lower()) for c in plan.keys.get(fact, ([], ""))[0]}
        for s in steps:
            needed |= {(s["from"], c.lower()) for c in s["rel"].source_cols} | {(s["to"], c.lower()) for c in s["rel"].target_cols}
        columns, out_names = [], []
        for t in [fact] + [s["to"] for s in steps]:
            for c in plan.schema[t].column_names:
                f = flagged.get((t, c))
                if f and not show_personal_data and (t, c.lower()) not in needed:
                    omitted.append({"view": target, "table": t, "column": c, **f})
                    continue
                if f and not show_personal_data:
                    kept.append({"view": target, "table": t, "column": c, **f, "why_kept": "a key or join column of this view"})
                columns.append({"table": t, "column": c, "alias": alias[t], "personal": f})
                out_names.append(c if t == fact else f"{t}_{c}")
        for col, name in zip(columns, _unique(out_names)):
            col["as"] = name
        out_of = {(c["table"], c["column"].lower()): c["as"] for c in columns}
        constraints = []
        key, key_rule = plan.keys.get(fact, ([], None))
        if key:
            constraints.append({"name": _constraint_name(fact, "key", "present"),
                                "check": " AND ".join(f"{q(out_of[(fact, c.lower())])} IS NOT NULL" for c in key),
                                "why": f"the key of {fact} is {' + '.join(key)} (rule {key_rule}: {_rule_text(key_rule)}); a row without it "
                                       "identifies nothing"})
        for s in steps:
            r = s["rel"]
            ref = [out_of[(s["from"], c.lower())] for c in r.source_cols]
            found = [out_of[(s["to"], c.lower())] for c in r.target_cols]
            constraints.append({"name": _constraint_name(fact, *([] if s["from"] == fact else [s["from"]]), *r.source_cols, "in", s["to"]),
                                "check": "(" + " OR ".join(f"{q(x)} IS NULL" for x in ref) + ") OR ("
                                         + " AND ".join(f"{q(x)} IS NOT NULL" for x in found) + ")",
                                "why": f"{s['from']}.{'+'.join(r.source_cols)} points at {s['to']}.{'+'.join(r.target_cols)} (rule {r.rule}: "
                                       f"{_rule_text(r.rule)}" + (f"; {r.note}" if r.note else "") + "); a row whose reference finds no "
                                       f"{s['to']} is dropped, a NULL reference is kept (it says unknown, not wrong)"})
        views.append({"fact": fact, "name": target, "why": f"{fact} is a fact table ({roles[fact]['why'].split(';')[0]}); one row per {fact} "
                      f"row with {len(steps)} table(s) joined in over the safest many-to-one paths",
                      "joins": [{"from": s["from"], "to": s["to"], "on": [f"{a} = {b}" for a, b in zip(s["rel"].source_cols, s["rel"].target_cols)],
                                 "rule": s["rel"].rule, "certainty": certainty(s["rel"]), "alias": alias[s["to"]], "from_alias": alias[s["from"]],
                                 "source_cols": list(s["rel"].source_cols), "target_cols": list(s["rel"].target_cols)} for s in steps],
                      "columns": columns, "constraints": constraints, "tables": [fact] + [s["to"] for s in steps]})
    owner = f"{info.get('item_id') or info.get('item_name') or 'lakehouse'}/{schema}"
    return {"source": {"item": info.get("item_name") or "", "item_id": info.get("item_id") or "", "workspace_id": info.get("workspace_id") or "",
                       "schema": schema, "tables": sorted(t.name for t in plan.schema)},
            "silver_schema": silver_schema, "gold_schema": gold_schema, "owner": owner, "views": views,
            "personal_data": {"shown": bool(show_personal_data), "omitted": omitted, "kept_for_joins": kept,
                              "flagged": _privacy.findings({k: v for k, v in flagged.items() if k[0] in {t for v in views for t in v["tables"]}})}}


def select_sql(view: dict, silver_schema: str, quote=q) -> str:
    cols = ",\n    ".join(f"{c['alias']}.{quote(c['column'])} AS {quote(c['as'])}" for c in view["columns"])
    joins = "".join(f"\n    LEFT JOIN {quote(silver_schema)}.{quote(j['to'])} AS {j['alias']} ON "
                    + " AND ".join(f"{j['from_alias']}.{quote(a)} = {j['alias']}.{quote(b)}" for a, b in zip(j["source_cols"], j["target_cols"]))
                    for j in view["joins"])
    return f"SELECT\n    {cols}\nFROM {quote(silver_schema)}.{quote(view['fact'])} AS f{joins}"


def create_sql(view: dict, s: dict) -> str:
    """CREATE OR REPLACE MATERIALIZED LAKE VIEW with one CONSTRAINT per rule, each preceded by the rule that motivates it."""
    gold, name = view["name"].split(".", 1)
    lines = [f"-- {view['why']}."]
    lines += [f"-- join {j['from']}.{'+'.join(j['source_cols'])} -> {j['to']}.{'+'.join(j['target_cols'])}: rule {j['rule']}, certainty {j['certainty']}"
              for j in view["joins"]]
    lines.append(f"CREATE OR REPLACE MATERIALIZED LAKE VIEW {q(gold)}.{q(name)}")
    if view["constraints"]:
        lines.append("(")
        for i, c in enumerate(view["constraints"]):
            lines.append(f"    -- {c['why']}")
            lines.append(f"    CONSTRAINT {c['name']} CHECK ({c['check']}) ON MISMATCH DROP" + ("," if i < len(view["constraints"]) - 1 else ""))
        lines.append(")")
    comment = f"Krusgraph gold view of {view['fact']} from {s['silver_schema']}, generated from the plan; rules in the constraint comments"
    lines.append('COMMENT "' + comment.replace('"', "'") + '"')
    lines.append(f'TBLPROPERTIES ("{PROPERTY}"="' + s["owner"].replace('"', "'") + '")')
    lines.append("AS")
    lines.append(select_sql(view, s["silver_schema"]))
    return "\n".join(lines)


def statements(s: dict) -> list[dict]:
    return [{"name": v["name"], "sql": create_sql(v, s), "why": v["why"], "rules": [{"constraint": c["name"], "why": c["why"]} for c in v["constraints"]]}
            for v in s["views"]]


# ------------------------------------------------------------------ the notebook ---------------------------------

SETUP = '''SOURCE_SCHEMA = {source_schema}
# Written into every gold view as the table property krusgraph.gold: a table or view carrying another value (or none)
# belongs to someone else, and this notebook stops before touching it.
OWNER = {owner}
SOURCE_TABLES = {source_tables}
SILVER_TABLES = {silver_tables}
WRITES = {writes}


def q(*parts):
    return ".".join("`" + str(p).replace("`", "``") + "`" for p in parts if p)


def is_ours_or_absent(name):
    if not spark.catalog.tableExists(name):
        return True
    props = {{r[0]: r[1] for r in spark.sql(f"SHOW TBLPROPERTIES {{name}}").collect()}}
    return props.get("krusgraph.gold") == OWNER


# Guards, before anything is created: every view goes to GOLD_SCHEMA, never onto a source or a silver table, never onto a
# table or view this notebook did not create; and the silver tables it reads exist (run the silver notebook first).
_protected = {{f"{{SOURCE_SCHEMA}}.{{t}}".lower() for t in SOURCE_TABLES}} | {{f"{{SILVER_SCHEMA}}.{{t}}".lower() for t in SOURCE_TABLES}}
for _v in WRITES:
    _target = f"{{GOLD_SCHEMA}}.{{_v}}".lower()
    if _target in _protected or GOLD_SCHEMA.lower() in (SOURCE_SCHEMA.lower(), SILVER_SCHEMA.lower()):
        raise ValueError(f"{{_target}} is a source or silver table; choose another GOLD_SCHEMA. Nothing was created.")
    if not is_ours_or_absent(q(GOLD_SCHEMA, _v)):
        raise ValueError(f"{{_target}} exists and was not created by this notebook (for {{OWNER}}); nothing was created. "
                         "Choose another GOLD_SCHEMA.")
_missing = [t for t in SILVER_TABLES if not spark.catalog.tableExists(q(SILVER_SCHEMA, t))]
if _missing:
    raise ValueError(f"silver tables missing in {{SILVER_SCHEMA}}: {{', '.join(_missing)}}. Run the silver notebook (create_silver_notebook) "
                     "first; nothing was created.")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {{q(GOLD_SCHEMA)}}")
created = []'''


def cells(s: dict) -> list[tuple[str, str]]:
    src = s["source"]
    intro = (f"# Gold views for {src['item'] or 'the lakehouse'}.{src['schema']}\n\n"
             f"Generated by Krusgraph from the plan: {len(s['views'])} materialized lake view(s) in the schema `{s['gold_schema']}`, one "
             f"wide view per fact table over the silver tables in `{s['silver_schema']}`, joined over the safest many-to-one paths. "
             "Each view's constraints mirror the plan's keys and relationships (ON MISMATCH DROP: the lineage view counts the dropped "
             "rows). Source and silver tables are only read; the notebook stops before touching a table it did not create. "
             "Schedule the refresh in the lakehouse: Manage materialized lake views -> Manage schedules.")
    if s["personal_data"]["omitted"]:
        intro += ("\n\nLeft out because the column name looks like personal data: "
                  + ", ".join(f"{o['table']}.{o['column']} ({o['rule']})" for o in s["personal_data"]["omitted"])
                  + f". Generate again with {_privacy.PARAMETER}=true to include them.")
    params = (f"GOLD_SCHEMA = {json.dumps(s['gold_schema'])}     # where the gold views go; never the source or silver schema\n"
              f"SILVER_SCHEMA = {json.dumps(s['silver_schema'])}   # where create_silver_notebook wrote the silver tables")
    reads = sorted({t for v in s["views"] for t in v["tables"]}, key=str.lower)
    setup = SETUP.format(source_schema=json.dumps(s["source"]["schema"]), owner=json.dumps(s["owner"]),
                         source_tables=json.dumps(s["source"]["tables"]), silver_tables=json.dumps(reads),
                         writes=json.dumps([v["name"].split(".", 1)[1] for v in s["views"]]))
    out = [("markdown", intro), ("parameters", params), ("code", setup)]
    for v in s["views"]:
        sql = create_sql(v, s)
        # the schema names become the parameters' values at run time; the SQL is a plain (not f-) string with backslashes and
        # triple quotes escaped, so any table or column name survives as it is
        body = sql.replace(f"{q(s['gold_schema'])}.", f"`{GOLD_TOKEN}`.").replace(f"{q(s['silver_schema'])}.", f"`{SILVER_TOKEN}`.")
        body = body.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        name = v["name"].split(".", 1)[1]
        out.append(("code", "\n".join([f"# ---- {v['name']} ----", *[f"# {c['name']}: {c['why']}" for c in v["constraints"]],
                                       f'spark.sql("""\n{body}\n""".replace("{GOLD_TOKEN}", GOLD_SCHEMA.replace("`", "``"))'
                                       f'.replace("{SILVER_TOKEN}", SILVER_SCHEMA.replace("`", "``")))',
                                       f"created.append({json.dumps(name)})"])))
    out.append(("code", "print(f\"{len(created)} gold view(s) in {GOLD_SCHEMA}: {', '.join(created)}\")\n"
                        "display(spark.sql(f\"SHOW MATERIALIZED LAKE VIEWS IN {q(GOLD_SCHEMA)}\"))"))
    return out


def notebook_source(s: dict) -> str:
    src = s["source"]
    meta = _nb.notebook_metadata(src["workspace_id"], src["item_id"], src["item"]) if src["item_id"] else _nb.notebook_metadata()
    return _nb.fabric_source(cells(s), meta)


def written(s: dict) -> list[str]:
    """Every name the notebook creates, lower case, schema-qualified: the test that no target is a source or silver table."""
    return [v["name"].lower() for v in s["views"]]


def run_select(view: dict, s: dict, execute, quote=q) -> list[dict]:
    """The view's SELECT with its constraints applied as DROP does (rows that break one are left out), through
    `execute(sql) -> rows as dicts`. What a local engine can check: the SQL parses, every column exists, the rules hold."""
    where = " AND ".join(f"({c['check']})" for c in view["constraints"]) or "1 = 1"
    if quote is not q:
        where = re.sub(r"`([^`]*)`", lambda m: quote(m.group(1)), where)
    return execute(f"SELECT * FROM (\n{select_sql(view, s['silver_schema'], quote)}\n) AS v WHERE {where}")
