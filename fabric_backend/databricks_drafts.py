"""Databricks drafts from the plan (round n13, Draft only): pure generators that turn a plan into Databricks SQL, a
Lakeflow pipeline, metric views and a bundle. Nothing here calls Databricks; the creating tools in mcp_server.py apply
two of them through the adapter (platforms/databricks.py), dry run by default.

What each piece rests on (docs.databricks.com and Databricks' own repositories, read 26 October 2026; docs.databricks.com
was read through search summaries because this environment could not open it, so the quotes there are close
paraphrases; databricks/cli, databricks/bundle-examples and databricks/dbt-databricks were read as source):

- Informational constraints (sql/language-manual/sql-ref-syntax-ddl-alter-table-add-constraint, tables/constraints,
  sql/user/queries/query-optimization-constraints; GA): `ALTER TABLE t ADD CONSTRAINT name PRIMARY KEY (cols) [RELY]`
  and `... FOREIGN KEY (cols) REFERENCES parent (cols) [RELY]`. Databricks does not enforce them. RELY lets the
  optimizer rewrite queries with the constraint (drop a DISTINCT, an aggregate or a join), and "it is the user's
  responsibility to check whether a constraint is satisfied", so RELY is written only where validate_plan's counts hold
  (a key unique and without NULLs; a reference without orphans to a unique key). A PRIMARY KEY's columns must be NOT
  NULL, and `ALTER TABLE t ALTER COLUMN c SET NOT NULL` is enforced on existing and new data, so it is written only when
  asked (set_not_null) and only for columns the counts show without NULLs. A FOREIGN KEY needs a PRIMARY KEY on the
  parent. There is no ADD CONSTRAINT IF NOT EXISTS: constraints already declared (K0, R0) are left out. Adding one
  needs ownership of the table (ALTER TABLE: "All other operations require ownership of the table"), SET NOT NULL
  needs MODIFY, a foreign key SELECT on the parent.
- The pipeline (Lakeflow pipelines, earlier Lakeflow Spark Declarative Pipelines and, before that, Delta Live Tables;
  ldp/developer/ldp-sql-ref-create-materialized-view, ldp/expectations, ldp/expectation-patterns):
  `CREATE OR REFRESH [PRIVATE] MATERIALIZED VIEW name (CONSTRAINT c EXPECT (expr) ON VIOLATION DROP ROW, ...) COMMENT
  '...' AS query`. An expectation sees one row and "cannot contain a subquery", so each reference is looked up in the
  query and checked on the row, and uniqueness is the query's job (row_number over the key); a PRIVATE materialized
  view is not published to the catalog. A pipeline reads other schemas and catalogs by full name and, in the default
  publishing mode, writes to several schemas. SQL notebooks use the Databricks source format (`-- Databricks notebook
  source`, cells split by `-- COMMAND ----------`).
- Metric views (metric-views/create/sql, business-semantics/metric-views/yaml-reference; GA per Databricks' blog of
  October 2026, some sub-features still labelled preview): `CREATE OR REPLACE VIEW name WITH METRICS LANGUAGE YAML AS $$
  ... $$`, YAML version 1.1 (Databricks Runtime 17.2 or a current SQL warehouse) with source, joins (name, source, on),
  dimensions and measures (name, expr), queried with MEASURE().
- Bundles (Declarative Automation Bundles, the name of Databricks Asset Bundles since March 2026; databricks/cli
  bundle/schema/jsonschema.json and databricks/bundle-examples lakeflow_pipelines_sql, default_sql): databricks.yml
  with bundle.name, include, variables and targets (mode: development / production); resources.pipelines with catalog,
  schema, serverless and libraries; resources.jobs with sql_task (warehouse_id, file) and pipeline_task.

Every target is in a schema of its own and never a source table: the generators refuse before writing anything else.
"""
from __future__ import annotations

import json
import re

from . import gold as _gold, privacy as _privacy, silver as _silver
from .dialects import DATABRICKS
from .infer import RULES, Plan, PlanInputError

Q = DATABRICKS.quote
LAKEFLOW = "Lakeflow pipeline (Lakeflow Spark Declarative Pipelines, formerly Delta Live Tables)"
NOTEBOOK_HEADER = "-- Databricks notebook source"
CELL = "\n\n-- COMMAND ----------\n\n"
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")


def _rule_text(rule: str | None) -> str:
    return RULES.get(rule or "", rule or "").split(";")[0].split(" — ")[0]


def _name(*parts: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", "_".join(parts).lower()).strip("_")[:120]


def _full(catalog: str, schema: str, table: str) -> str:
    return ".".join(Q(x) for x in (catalog, schema, table))


def _check_schema(label: str, value: str) -> str:
    value = (value or "").strip()
    if not _IDENT.match(value):
        raise PlanInputError(f"{label}: letters, digits and underscores, starting with a letter")
    return value


def _never_a_source(plan: Plan, catalog: str, targets: list[tuple[str, str]]) -> None:
    """Refuse when a target (schema, name) is one of the source tables."""
    sources = {(plan.schema.schema.lower(), t.name.lower()) for t in plan.schema}
    hit = [f"{catalog}.{s}.{n}" for s, n in targets if (s.lower(), n.lower()) in sources]
    if hit:
        raise PlanInputError(f"{', '.join(hit)} would be written, and {'it is a source table' if len(hit) == 1 else 'they are source tables'}; "
                             "choose another target schema")


# ------------------------------------------------------------------ informational constraints --------------------

def constraints(plan: Plan, catalog: str, validation: dict | None = None, set_not_null: bool = False) -> dict:
    """ALTER TABLE statements for the plan's keys (PRIMARY KEY) and relationships (FOREIGN KEY) that Unity Catalog does
    not declare yet, each with the rule behind it. With `validation` (evidence.validate's answer) RELY is added where the
    counts hold and a key the data contradicts is left out; without it nothing gets RELY."""
    schema = plan.schema.schema
    checked_keys = {k["table"]: k for k in (validation or {}).get("keys", [])}
    checked_rels = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in (validation or {}).get("relationships", [])}
    statements, skipped, declared = [], [], []
    pk_ok: set[str] = set()
    for table, (cols, rule) in sorted(plan.keys.items(), key=lambda kv: kv[0].lower()):
        t = plan.schema[table]
        full = _full(catalog, schema, table)
        if rule == "K0":
            declared.append({"table": table, "constraint": "PRIMARY KEY", "columns": cols})
            pk_ok.add(table)
            continue
        v = checked_keys.get(table)
        if v is not None and not v["verdict"].startswith("unique"):
            skipped.append({"table": table, "constraint": "PRIMARY KEY", "columns": cols, "rule": rule,
                            "why": f"validate_plan: {v['verdict']}; a primary key the data contradicts would mislead every reader of it"})
            continue
        nullable = [c for c in cols if next((x.nullable for x in t.columns if x.name == c), None) is not False]
        if nullable and not set_not_null:
            skipped.append({"table": table, "constraint": "PRIMARY KEY", "columns": cols, "rule": rule,
                            "why": f"{', '.join(nullable)} may hold NULLs by its definition, and a PRIMARY KEY needs NOT NULL columns; "
                                   "set_not_null=true adds ALTER COLUMN ... SET NOT NULL first (Delta enforces it on every later write)"})
            continue
        if nullable and v is None:
            skipped.append({"table": table, "constraint": "PRIMARY KEY", "columns": cols, "rule": rule,
                            "why": "SET NOT NULL fails on a column with NULLs and is enforced afterwards; validate=true first, so the "
                                   "counts show there are none"})
            continue
        rely = v is not None
        for c in nullable:
            statements.append({"kind": "not_null", "table": table, "columns": [c], "rule": rule,
                               "why": f"a PRIMARY KEY needs NOT NULL columns; validate_plan found no NULL in {table}.{c}",
                               "sql": f"ALTER TABLE {full} ALTER COLUMN {Q(c)} SET NOT NULL"})
        name = _name(table, "pk")
        statements.append({"kind": "primary_key", "table": table, "columns": cols, "rule": rule, "name": name, "rely": rely,
                           "why": f"key {' + '.join(cols)} by rule {rule} ({_rule_text(rule)})"
                                  + (f"; RELY because validate_plan: {v['verdict']}" if rely else "; NORELY: not checked against the data"),
                           "sql": f"ALTER TABLE {full} ADD CONSTRAINT {Q(name)} PRIMARY KEY ({', '.join(Q(c) for c in cols)})" + (" RELY" if rely else "")})
        pk_ok.add(table)
    for r in plan.relationships:
        if r.rule == "R0":
            declared.append({"table": r.source, "constraint": "FOREIGN KEY", "columns": r.source_cols, "references": r.target})
            continue
        if r.target not in pk_ok:
            skipped.append({"table": r.source, "constraint": "FOREIGN KEY", "columns": r.source_cols, "references": r.target, "rule": r.rule,
                            "why": f"a FOREIGN KEY needs a PRIMARY KEY on {r.target}, and that one is left out above"})
            continue
        v = checked_rels.get((r.source, tuple(c.lower() for c in r.source_cols), r.target))
        target_unique = checked_keys.get(r.target, {}).get("verdict", "").startswith("unique") or plan.keys[r.target][1] == "K0"
        rely = v is not None and v["verdict"].startswith("holds") and target_unique
        name = _name(r.source, *r.source_cols, "fk", r.target)
        statements.append({"kind": "foreign_key", "table": r.source, "columns": list(r.source_cols), "references": r.target,
                           "target_columns": list(r.target_cols), "rule": r.rule, "name": name, "rely": rely,
                           "why": f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)} by rule {r.rule} "
                                  f"({_rule_text(r.rule)}{'; ' + r.note if r.note else ''})"
                                  + (f"; RELY because validate_plan: {v['verdict']}" if rely else
                                     f"; NORELY: {v['verdict']}" if v is not None else "; NORELY: not checked against the data"),
                           "sql": f"ALTER TABLE {_full(catalog, schema, r.source)} ADD CONSTRAINT {Q(name)} FOREIGN KEY "
                                  f"({', '.join(Q(c) for c in r.source_cols)}) REFERENCES {_full(catalog, schema, r.target)} "
                                  f"({', '.join(Q(c) for c in r.target_cols)})" + (" RELY" if rely else "")})
    lines = [f"-- Informational constraints for {catalog}.{schema}, generated by Krusgraph from the plan. Databricks does not enforce",
             "-- PRIMARY KEY or FOREIGN KEY; RELY lets the optimizer use one, so it is written only where the counts held.",
             "-- Adding a constraint needs ownership of the table; ALTER COLUMN ... SET NOT NULL needs MODIFY and is enforced."]
    for st in statements:
        lines += ["", f"-- {st['why']}", st["sql"] + ";"]
    return {"catalog": catalog, "schema": schema, "statements": statements, "skipped": skipped, "declared": declared,
            "validated": validation is not None, "sql": "\n".join(lines) + "\n"}


# ------------------------------------------------------------------ the pipeline -------------------------------------

def _struct(cols: list[str], masked: set[str], alias: str = "") -> str:
    """to_json(named_struct(...)) of a row, personal columns as '***'; `alias` qualifies the columns (r.) where the
    query joins another table that may have a column of the same name."""
    parts = []
    for c in cols:
        parts.append("'" + c.replace("'", "") + "', " + ("'***'" if c.lower() in masked else alias + Q(c)))
    return "to_json(named_struct(" + ", ".join(parts) + "))"


def _silver_cells(plan: Plan, s: dict, catalog: str) -> tuple[list[str], list[str]]:
    """(cells, quarantine selects) of the silver notebook, one cell per table in the spec's order."""
    schema, silver_schema = s["source"]["schema"], s["silver_schema"]
    chosen = {t["table"] for t in s["tables"]}
    cells, quarantine = [], []
    for spec_t in s["tables"]:
        t = spec_t["table"]
        cols = plan.schema[t].column_names
        masked = {c.lower() for c in s["personal"].get(t, [])} if s["mask_personal_data"] else set()
        key, rule = spec_t["key"], spec_t["key_rule"]
        src = _full(catalog, schema, t)
        ranked, checked = _name(t, "_ranked"), _name(t, "_checked")
        ranked, checked = f"{t.lower()}__ranked" if _IDENT.match(f"{t}__ranked") else ranked, f"{t.lower()}__checked" if _IDENT.match(f"{t}__checked") else checked
        notes = [f"-- {t}: from {catalog}.{schema}.{t} into {catalog}.{silver_schema}.{t}."]
        if key:
            notes.append(f"-- Key {' + '.join(key)} by rule {rule} ({_rule_text(rule)}); a row without it identifies nothing and is dropped.")
            if spec_t["order_by"]:
                order = f"{Q(spec_t['order_by'])} DESC NULLS LAST"
                notes.append(f"-- Rows that share the key: the latest by {spec_t['order_by']} wins ({spec_t['order_why']}).")
            else:
                order = "xxhash64(" + ", ".join(Q(c) for c in cols) + ")"
                notes.append("-- Rows that share the key: one per key by a hash of its content, so a re-run keeps the same row "
                             "(no column is named like a load or change time; order_by names one).")
            rank = f"row_number() OVER (PARTITION BY {', '.join(Q(c) for c in key)} ORDER BY {order})"
        else:
            notes.append("-- No key (rule K3): copied without de-duplication.")
            rank = "1"
        expectations, lookups, helpers = [], [], []
        if key:
            expectations.append((f"-- {rule}: the key {' + '.join(key)} must be present",
                                 f"CONSTRAINT {_name(t, 'key', 'present')} EXPECT ({' AND '.join(Q(c) + ' IS NOT NULL' for c in key)}) ON VIOLATION DROP ROW"))
        for i, chk in enumerate(spec_t["checks"], 1):
            parent = chk["parent"]
            from_silver = chk["parent_from"] == "silver" and parent != t and parent in chosen
            ptable = _full(catalog, silver_schema, parent) if from_silver else _full(catalog, schema, parent)
            helper = f"_krusgraph_found_{i}"
            helpers.append(helper)
            on = " AND ".join(f"r.{Q(a)} = p{i}.{Q(b)}" for a, b in zip(chk["columns"], chk["parent_columns"]))
            lookups.append(f"LEFT JOIN (SELECT DISTINCT {', '.join(Q(c) for c in chk['parent_columns'])} FROM {ptable}) AS p{i} ON {on}")
            where = "silver" if from_silver else "source"
            why = (f"-- {chk['rule']}: {t}.{'+'.join(chk['columns'])} points at {parent}.{'+'.join(chk['parent_columns'])} "
                   f"({_rule_text(chk['rule'])}{'; ' + chk['note'] if chk.get('note') else ''}), checked against the {where} table; "
                   "a row whose reference finds nothing is dropped, a NULL reference stays (unknown, not wrong)")
            cond = "(" + " OR ".join(f"{Q(c)} IS NULL" for c in chk["columns"]) + f") OR {Q(helper)} IS NOT NULL"
            expectations.append((why, f"CONSTRAINT {_name(t, *chk['columns'], 'in', parent)} EXPECT ({cond}) ON VIOLATION DROP ROW"))
            q_sel = (f"SELECT '{t}' AS source_table, '{chk['rule']}' AS rule, 'reference {'+'.join(chk['columns'])} finds no row in {parent}' AS reason, "
                     f"{_struct(cols, masked, 'r.')} AS row_json, current_timestamp() AS checked_at\n"
                     f"FROM {ranked} AS r {lookups[-1]}\nWHERE r._krusgraph_rank = 1"
                     + "".join(f" AND r.{Q(c)} IS NOT NULL" for c in key)
                     + "".join(f" AND r.{Q(c)} IS NOT NULL" for c in chk["columns"])
                     + f" AND p{i}.{Q(chk['parent_columns'][0])} IS NULL")
            quarantine.append(q_sel)
        stage1 = (f"CREATE OR REFRESH PRIVATE MATERIALIZED VIEW {ranked}\n"
                  f"COMMENT 'rows of {t} numbered within their key; not published'\n"
                  f"AS SELECT *, {rank} AS _krusgraph_rank\nFROM {src}")
        constraint_lines = ",\n".join(f"  {w}\n  {c}" for w, c in expectations)
        stage2 = (f"CREATE OR REFRESH PRIVATE MATERIALIZED VIEW {checked}"
                  + (f" (\n{constraint_lines}\n)" if expectations else "")
                  + f"\nCOMMENT 'rows of {t} with their references looked up; not published'\n"
                  + "AS SELECT r.*" + "".join(f", p{i}.{Q(chk['parent_columns'][0])} AS {Q(h)}" for i, (chk, h) in enumerate(zip(spec_t["checks"], helpers), 1))
                  + f"\nFROM {ranked} AS r" + "".join("\n" + lk for lk in lookups) + "\nWHERE r._krusgraph_rank = 1")
        drop = ", ".join(["_krusgraph_rank"] + helpers)
        stage3 = (f"CREATE OR REFRESH MATERIALIZED VIEW {_full(catalog, silver_schema, t)}\n"
                  f"COMMENT {DATABRICKS.literal(f'Krusgraph silver table of {schema}.{t}, generated from the plan; rules in the comments of the pipeline source')}\n"
                  f"AS SELECT * EXCEPT ({drop})\nFROM {checked}")
        cells.append("\n".join(notes) + "\n" + stage1 + ";\n\n" + stage2 + ";\n\n" + stage3 + ";")
        if key:
            quarantine.append(f"SELECT '{t}' AS source_table, '{rule}' AS rule, 'the key {'+'.join(key)} is NULL' AS reason, "
                              f"{_struct(cols, masked)} AS row_json, current_timestamp() AS checked_at\nFROM {src}\nWHERE "
                              + " OR ".join(f"{Q(c)} IS NULL" for c in key))
            quarantine.append(f"SELECT '{t}' AS source_table, '{rule}' AS rule, 'another row with the same key {'+'.join(key)} won' AS reason, "
                              f"{_struct(cols, masked)} AS row_json, current_timestamp() AS checked_at\nFROM {ranked}\nWHERE _krusgraph_rank > 1"
                              + "".join(f" AND {Q(c)} IS NOT NULL" for c in key))
    return cells, quarantine


def _gold_cells(s: dict, catalog: str) -> list[str]:
    cells = []
    for v in s["views"]:
        gold_schema, name = v["name"].split(".", 1)
        lines = [f"-- {v['why']}."]
        lines += [f"-- join {j['from']}.{'+'.join(j['source_cols'])} -> {j['to']}.{'+'.join(j['target_cols'])}: rule {j['rule']}, certainty {j['certainty']}"
                  for j in v["joins"]]
        lines.append(f"CREATE OR REFRESH MATERIALIZED VIEW {_full(catalog, gold_schema, name)}")
        if v["constraints"]:
            lines.append("(")
            for i, c in enumerate(v["constraints"]):
                lines.append(f"  -- {c['why']}")
                lines.append(f"  CONSTRAINT {c['name']} EXPECT ({c['check']}) ON VIOLATION DROP ROW" + ("," if i < len(v["constraints"]) - 1 else ""))
            lines.append(")")
        lines.append("COMMENT " + DATABRICKS.literal(f"Krusgraph gold view of {v['fact']} from {s['silver_schema']}, generated from the plan; "
                                                      "rules in the expectation comments"))
        cols = ",\n    ".join(f"{c['alias']}.{Q(c['column'])} AS {Q(c['as'])}" for c in v["columns"])
        joins = "".join(f"\n    LEFT JOIN {_full(catalog, s['silver_schema'], j['to'])} AS {j['alias']} ON "
                        + " AND ".join(f"{j['from_alias']}.{Q(a)} = {j['alias']}.{Q(b)}" for a, b in zip(j["source_cols"], j["target_cols"]))
                        for j in v["joins"])
        lines.append(f"AS SELECT\n    {cols}\nFROM {_full(catalog, s['silver_schema'], v['fact'])} AS f{joins}")
        cells.append("\n".join(lines) + ";")
    return cells


def pipeline(plan: Plan, catalog: str, silver_schema: str = "silver", gold_schema: str = "gold", order_by: dict | None = None,
             tables: list[str] | None = None, show_personal_data: bool = False, name: str = "krusgraph") -> dict:
    """The silver and gold rules of the Fabric notebooks as a Lakeflow pipeline in SQL: two notebooks in Databricks'
    source format and the pipeline settings. Silver: per table, rows numbered within their key (the latest by the ordering
    column first), the key and every reference as expectations that drop the row, the clean rows published in
    `silver_schema`, and krusgraph_quarantine with each dropped row and its rule. Gold: one materialized view per fact
    table over the silver tables, joined over the safest many-to-one paths, the plan's keys and relationships as
    expectations. Personal columns are masked in the quarantine and left out of gold unless show_personal_data."""
    schema = plan.schema.schema
    silver_schema, gold_schema = _check_schema("silver_schema", silver_schema), _check_schema("gold_schema", gold_schema)
    info = {"schema": schema, "schemas_enabled": True, "item_name": f"{catalog}.{schema}", "item_id": f"{catalog}.{schema}"}
    s = _silver.spec(plan, info, silver_schema, order_by, tables, show_personal_data)
    g = _gold.spec(plan, info, silver_schema, gold_schema, None, show_personal_data, within=[t["table"] for t in s["tables"]])
    targets = [(silver_schema, t["table"]) for t in s["tables"]] + [(silver_schema, _silver.QUARANTINE)] + \
              [tuple(v["name"].split(".", 1)) for v in g["views"]]
    _never_a_source(plan, catalog, targets)
    cells, quarantine = _silver_cells(plan, s, catalog)
    if quarantine:
        cells.append("-- The rows the expectations above drop, with the rule and the reason (personal columns masked unless\n"
                     "-- show_personal_data); Databricks also counts them per expectation in the pipeline's event log.\n"
                     f"CREATE OR REFRESH MATERIALIZED VIEW {_full(catalog, silver_schema, _silver.QUARANTINE)}\n"
                     f"COMMENT 'Krusgraph quarantine: the rows the silver rules dropped, with the rule'\nAS\n"
                     + "\nUNION ALL\n".join(quarantine) + ";")
    head = (f"{NOTEBOOK_HEADER}\n\n-- Silver tables for {catalog}.{schema}, generated by Krusgraph from the plan as a {LAKEFLOW}.\n"
            "-- Never over a source table: every target is in " + f"{catalog}.{silver_schema}. Draft only; not yet run in Databricks.")
    silver_sql = head + CELL + CELL.join(cells) + "\n"
    gold_cells = _gold_cells(g, catalog)
    gold_sql = (f"{NOTEBOOK_HEADER}\n\n-- Gold views for {catalog}.{schema}, generated by Krusgraph from the plan as a {LAKEFLOW}.\n"
                f"-- Read from {catalog}.{silver_schema}, written to {catalog}.{gold_schema}. Draft only; not yet run in Databricks."
                + (CELL + CELL.join(gold_cells) if gold_cells else "\n-- No fact table in the plan: nothing to build.") + "\n")
    settings = {"name": name, "catalog": catalog, "schema": silver_schema, "serverless": True,
                "libraries": [{"notebook": {"path": "silver"}}, {"notebook": {"path": "gold"}}]}
    return {"catalog": catalog, "schema": schema, "silver_schema": silver_schema, "gold_schema": gold_schema,
            "files": {"silver.sql": silver_sql, "gold.sql": gold_sql}, "settings": settings,
            "silver_tables": [f"{catalog}.{silver_schema}.{t['table']}" for t in s["tables"]],
            "quarantine": f"{catalog}.{silver_schema}.{_silver.QUARANTINE}",
            "gold_views": [f"{catalog}.{v['name']}" for v in g["views"]],
            "steps": _silver.steps(s), "not_checked": s["not_checked"], "personal_data": g["personal_data"]}


# ------------------------------------------------------------------ metric views ----------------------------------

def _yaml_str(text: str) -> str:
    return json.dumps(str(text), ensure_ascii=False)              # a JSON string is a valid YAML double-quoted scalar


_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _yaml_name(*parts: str) -> str:
    """A table or join name for the YAML: catalog.schema.table as the docs write it when every part is a plain identifier,
    else in backticks inside a quoted string."""
    if all(_PLAIN.match(p) for p in parts):
        return ".".join(parts)
    return _yaml_str(".".join(Q(p) for p in parts))


def _ref(name: str) -> str:
    return name if _PLAIN.match(name) else Q(name)


def metric_views(plan: Plan, catalog: str, metrics_schema: str = "krusgraph", show_personal_data: bool = False) -> dict:
    """One metric view per fact table over its source table: the measures semantic_model_draft suggests (the row count,
    and sums only where summarizeBy sums) as SQL, the fact's own columns and those of the tables one many-to-one step
    away as dimensions (personal columns left out unless show_personal_data), those tables as star joins."""
    from . import graphs, semantic_model
    schema = plan.schema.schema
    metrics_schema = _check_schema("metrics_schema", metrics_schema)
    if metrics_schema.lower() == schema.lower():
        raise PlanInputError(f"metrics_schema {metrics_schema!r} is the source schema; the metric views need a schema of their own")
    roles = graphs.analyze(plan)["roles"]
    role_of = {t: r["role"] for t, r in roles.items()}
    facts = sorted((t.name for t in plan.schema if role_of.get(t.name) == "fact"), key=str.lower)
    ref_cols = {(r.source, c.lower()) for r in plan.relationships for c in r.source_cols}
    flagged = {} if show_personal_data else _privacy.personal_columns(plan.schema)
    views, omitted = [], []
    _never_a_source(plan, catalog, [(metrics_schema, f"{f}_metrics") for f in facts])
    for fact in facts:
        t = plan.schema[fact]
        measures = semantic_model.suggested_measures(plan, [t], role_of, ref_cols)
        joins = [r for r in plan.relationships if r.source == fact and r.target in plan.keys and r.target != fact]
        seen: set[str] = set()
        join_lines, dims = [], []
        for r in sorted(joins, key=lambda x: (x.target, x.source_cols)):
            if r.target in seen:
                continue                                              # one join per table; a second role needs its own name, by hand
            seen.add(r.target)
            on = " AND ".join(f"source.{Q(a)} = {_ref(r.target)}.{Q(b)}" for a, b in zip(r.source_cols, r.target_cols))
            join_lines += [f"  - name: {_yaml_name(r.target)}", f"    source: {_yaml_name(catalog, schema, r.target)}", f"    'on': {_yaml_str(on)}",
                           f"    # {r.rule}: {fact}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)} ({_rule_text(r.rule)})"]
        key = {c.lower() for c in plan.keys.get(fact, ([], ""))[0]}
        for c in t.column_names:
            if (fact, c) in flagged:
                omitted.append({"view": f"{fact}_metrics", "table": fact, "column": c, **flagged[(fact, c)]})
                continue
            if c.lower() in key or (fact, c.lower()) in ref_cols or any(m["column"] == c for m in measures):
                continue
            dims.append((f"{fact} {c}", Q(c)))
        for target in sorted(seen):
            tk = {x.lower() for x in plan.keys.get(target, ([], ""))[0]}
            for c in plan.schema[target].column_names:
                if (target, c) in flagged:
                    omitted.append({"view": f"{fact}_metrics", "table": target, "column": c, **flagged[(target, c)]})
                    continue
                if c.lower() not in tk:
                    dims.append((f"{target} {c}", f"{_ref(target)}.{Q(c)}"))
        yaml = ["version: 1.1", f"comment: {_yaml_str(f'Krusgraph metric view of {schema}.{fact}, generated from the plan')}",
                f"source: {_yaml_name(catalog, schema, fact)}"]
        if join_lines:
            yaml += ["joins:"] + join_lines
        if dims:
            yaml += ["dimensions:"] + [line for n, e in dims for line in (f"  - name: {_yaml_str(n)}", f"    expr: {_yaml_str(e)}")]
        yaml += ["measures:"]
        for m in measures:
            expr = "COUNT(1)" if m["column"] is None else f"SUM({Q(m['column'])})"
            yaml += [f"  - name: {_yaml_str(m['name'])}", f"    expr: {_yaml_str(expr)}", f"    comment: {_yaml_str(m['why'])}"]
        body = "\n".join(yaml)
        target = _full(catalog, metrics_schema, f"{fact}_metrics")
        views.append({"fact": fact, "name": f"{catalog}.{metrics_schema}.{fact}_metrics", "yaml": body,
                      "sql": f"CREATE OR REPLACE VIEW {target}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{body}\n$$",
                      "measures": [m["name"] for m in measures], "dimensions": [n for n, _ in dims], "joins": sorted(seen)})
    script = "\n\n".join([f"CREATE SCHEMA IF NOT EXISTS {Q(catalog)}.{Q(metrics_schema)};"] + [v["sql"] + ";" for v in views]) + "\n"
    return {"catalog": catalog, "schema": schema, "metrics_schema": metrics_schema, "views": views, "sql": script,
            "personal_data": {"shown": bool(show_personal_data), "omitted": omitted},
            "query": ("SELECT `<dimension>`, MEASURE(`<measure>`) FROM <metric view> GROUP BY ALL" if views else "")}


# ------------------------------------------------------------------ the bundle ------------------------------------

def bundle(name: str, catalog: str, pipeline_draft: dict, constraints_draft: dict, views_sql: str, metrics_draft: dict,
           host: str = "") -> dict[str, str]:
    """A Declarative Automation Bundle (formerly Databricks Asset Bundle) folder: databricks.yml, the pipeline and a job
    as resources, the notebooks and SQL files under src/. `databricks bundle validate` and `deploy` are run by you."""
    key = _name(name) or "krusgraph"
    host_line = f"      host: {host}" if host else "      host: https://<your-workspace>.cloud.databricks.com"
    files = {
        "databricks.yml": "\n".join([
            "# Generated by Krusgraph from the plan. Declarative Automation Bundles (formerly Databricks Asset Bundles):",
            "#   databricks bundle validate -t dev && databricks bundle deploy -t dev",
            "bundle:", f"  name: {key}", "", "include:", "  - resources/*.yml", "", "variables:",
            "  catalog:", "    description: The catalog that holds the source schema", f"    default: {catalog}",
            "  warehouse_id:", "    description: The SQL warehouse that runs the SQL files", "",
            "targets:", "  dev:", "    mode: development", "    default: true", "    workspace:", host_line,
            "  prod:", "    mode: production", "    workspace:", host_line, ""]),
        f"resources/{key}.pipeline.yml": "\n".join([
            "resources:", "  pipelines:", f"    {key}_pipeline:", f"      name: {key}_pipeline", "      catalog: ${var.catalog}",
            f"      schema: {pipeline_draft['silver_schema']}", "      serverless: true", "      libraries:",
            "        - notebook:", "            path: ../src/silver.sql", "        - notebook:", "            path: ../src/gold.sql", ""]),
        f"resources/{key}.job.yml": "\n".join([
            "# The SQL files run on the SQL warehouse; the pipeline refresh builds silver and gold. constraints.sql changes the",
            "# source tables' metadata (and SET NOT NULL, if present, their column definitions): it is a separate job, run it on purpose.",
            "resources:", "  jobs:", f"    {key}_build:", f"      name: {key}_build", "      tasks:",
            "        - task_key: views", "          sql_task:", "            warehouse_id: ${var.warehouse_id}", "            file:",
            "              path: ../src/views.sql",
            "        - task_key: refresh_pipeline", "          pipeline_task:", f"            pipeline_id: ${{resources.pipelines.{key}_pipeline.id}}",
            "        - task_key: metric_views", "          depends_on:", "            - task_key: refresh_pipeline", "          sql_task:",
            "            warehouse_id: ${var.warehouse_id}", "            file:", "              path: ../src/metric_views.sql",
            f"    {key}_constraints:", f"      name: {key}_constraints", "      tasks:", "        - task_key: constraints", "          sql_task:",
            "            warehouse_id: ${var.warehouse_id}", "            file:", "              path: ../src/constraints.sql", ""]),
        "src/silver.sql": pipeline_draft["files"]["silver.sql"],
        "src/gold.sql": pipeline_draft["files"]["gold.sql"],
        "src/constraints.sql": constraints_draft["sql"],
        "src/views.sql": views_sql,
        "src/metric_views.sql": metrics_draft["sql"],
    }
    files["README.generated.md"] = "\n".join([
        f"# {key}: generated by Krusgraph", "",
        f"A bundle for `{catalog}.{pipeline_draft['schema']}`, from the plan Krusgraph inferred (draft only; not yet deployed or run in",
        "Databricks). Check every file before you deploy it.", "",
        "| File | What it does |", "| --- | --- |",
        "| `databricks.yml` | the bundle, its variables (`catalog`, `warehouse_id`) and the `dev` / `prod` targets; set the workspace host |",
        f"| `resources/{key}.pipeline.yml` | the {LAKEFLOW} with the two notebooks, serverless |",
        f"| `resources/{key}.job.yml` | `{key}_build`: views, a pipeline refresh, metric views; `{key}_constraints`: the constraints, on its own |",
        f"| `src/silver.sql` | silver tables in `{pipeline_draft['silver_schema']}` with expectations per key and reference, and the quarantine |",
        f"| `src/gold.sql` | gold materialized views in `{pipeline_draft['gold_schema']}`, one per fact table |",
        "| `src/constraints.sql` | informational PRIMARY KEY / FOREIGN KEY constraints; RELY only where the counts held |",
        "| `src/views.sql` | wide views in a schema of their own |",
        "| `src/metric_views.sql` | one metric view per fact table |", "",
        "Rights: CREATE MATERIALIZED VIEW and USE SCHEMA on the silver and gold schemas; CREATE TABLE on the views' and metric views'",
        "schema; ownership of the source tables for the constraints; CAN USE on the SQL warehouse.", ""])
    return files
