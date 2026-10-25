"""T-SQL views over the plan, in a schema of their own: one wide view per fact table (the table with its dimensions
joined in through the plan's relationships) and one view per relationship that is hard to read. Only
CREATE SCHEMA (when missing) and CREATE OR ALTER VIEW inside that schema; never DROP, never anything outside it.
Identifiers come from the source's metadata and are quoted as in evidence.qi.

Where this may run (MicrosoftDocs/fabric-docs [6b1f955], read 25 October 2026):
- docs/data-engineering/lakehouse-sql-analytics-endpoint.md: the SQL analytics endpoint is read-only over the Delta
  tables, and within that boundary you can "Create views, functions, and stored procedures — … T-SQL objects that
  persist in the SQL analytics endpoint"; "the experience and limitations are the same" for the endpoints of
  warehouses, mirrored databases and SQL databases. The same page: "Schema and table names can't contain / or \\".
- docs/data-warehouse/ingest-data-warehouse-tables-tsql.md shows CREATE SCHEMA in a warehouse.
So views are possible on a lakehouse's SQL analytics endpoint; if an endpoint still refuses the DDL (permissions,
or an endpoint type that does not allow it), the tool says so and suggests a warehouse.
"""
from __future__ import annotations

import re

from .evidence import qi
from .infer import Plan, Relationship, _singulars, _words

DEFAULT_SCHEMA = "krusgraph"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,119}$")


def schema_sql(target: str) -> str:
    """Create the views' schema when it does not exist; the name is validated, and the literal is escaped."""
    if not _NAME.match(target):
        raise ValueError("the views schema name must be letters, digits and underscores")
    lit = target.replace("'", "''")
    return f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{lit}') EXEC('CREATE SCHEMA {qi(target)}')"


def fact_tables(plan: Plan) -> list[str]:
    """Tables with two or more references out and none in: order lines, transactions, events."""
    out_deg: dict[str, int] = {}
    in_deg: dict[str, int] = {}
    for r in plan.relationships:
        out_deg[r.source] = out_deg.get(r.source, 0) + 1
        in_deg[r.target] = in_deg.get(r.target, 0) + 1
    return [t.name for t in plan.schema if out_deg.get(t.name, 0) >= 2 and in_deg.get(t.name, 0) == 0]


def dimension_chain(plan: Plan, fact: str) -> list[tuple[str, Relationship, str]]:
    """(alias of the table holding the reference, relationship, alias of the target) for every table reachable from the
    fact by following references many-to-one, breadth first, each table once (the first path wins)."""
    by_source: dict[str, list[Relationship]] = {}
    for r in plan.relationships:
        by_source.setdefault(r.source, []).append(r)
    alias = {fact: "f"}
    order = [fact]
    chain: list[tuple[str, Relationship, str]] = []
    i = 0
    while i < len(order):
        t = order[i]
        i += 1
        for r in sorted(by_source.get(t, []), key=lambda x: (x.target, x.source_cols)):
            if r.target in alias or r.target not in plan.keys:
                continue
            alias[r.target] = f"d{len(alias)}"
            order.append(r.target)
            chain.append((alias[t], r, alias[r.target]))
    return chain


def _unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        k = n.lower()
        seen[k] = seen.get(k, 0) + 1
        out.append(n if seen[k] == 1 else f"{n}_{seen[k]}")
    return out


def wide_view_sql(plan: Plan, fact: str, target: str) -> tuple[str, list[str]]:
    schema = plan.schema.schema
    chain = dimension_chain(plan, fact)
    cols = [f"f.{qi(c)}" for c in plan.schema[fact].column_names]
    aliases = list(plan.schema[fact].column_names)
    joins = []
    tables = [fact]
    for src_alias, r, tgt_alias in chain:
        on = " AND ".join(f"{src_alias}.{qi(a)} = {tgt_alias}.{qi(b)}" for a, b in zip(r.source_cols, r.target_cols))
        joins.append(f"    LEFT JOIN {qi(schema)}.{qi(r.target)} AS {tgt_alias} ON {on}")
        tables.append(r.target)
        for c in plan.schema[r.target].column_names:
            cols.append(f"{tgt_alias}.{qi(c)}")
            aliases.append(f"{r.target}_{c}")
    aliases = _unique(aliases)
    select = ",\n    ".join(f"{expr} AS {qi(a)}" for expr, a in zip(cols, aliases))
    sql = (f"CREATE OR ALTER VIEW {qi(target)}.{qi('vw_' + fact)} AS\nSELECT\n    {select}\nFROM {qi(schema)}.{qi(fact)} AS f\n"
           + "\n".join(joins))
    return sql.rstrip(), tables


def hard_relationships(plan: Plan) -> list[Relationship]:
    """Links a reader would not guess from the names: weaker rules (R2, R3, R4), confirmed ones, and references whose
    column names a role rather than the table (ship_to_id -> addresses)."""
    out = []
    for r in plan.relationships:
        bases = {b.lower() for b in _singulars(r.target)} | {r.target.lower()}
        role = r.field_name.lower() not in {b.replace("_", "") for b in bases} and r.field_name.lower() not in bases
        if r.rule in ("R2", "R3", "R4", "confirmed") or role:
            out.append(r)
    return out


def relationship_view_sql(plan: Plan, r: Relationship, target: str) -> str:
    schema = plan.schema.schema
    on = " AND ".join(f"s.{qi(a)} = t.{qi(b)}" for a, b in zip(r.source_cols, r.target_cols))
    s_cols = [f"s.{qi(c)} AS {qi(c)}" for c in plan.schema[r.source].column_names]
    t_cols = [f"t.{qi(c)} AS {qi(f'{r.target}_{c}')}" for c in plan.schema[r.target].column_names]
    name = f"vw_{r.source}_{r.field_name}"
    return (f"CREATE OR ALTER VIEW {qi(target)}.{qi(name)} AS\nSELECT\n    " + ",\n    ".join(_dedupe(s_cols + t_cols))
            + f"\nFROM {qi(schema)}.{qi(r.source)} AS s\n    LEFT JOIN {qi(schema)}.{qi(r.target)} AS t ON {on}")


def _dedupe(cols: list[str]) -> list[str]:
    names = _unique([c.rsplit(" AS ", 1)[1].strip("[]") for c in cols])
    return [c.rsplit(" AS ", 1)[0] + " AS " + qi(n) for c, n in zip(cols, names)]


def statements(plan: Plan, target: str = DEFAULT_SCHEMA) -> dict:
    """{"schema": <sql>, "views": [{"name", "sql", "why", "tables"}]} — the fact views first, then one per hard link."""
    views = []
    for fact in fact_tables(plan):
        sql, tables = wide_view_sql(plan, fact, target)
        views.append({"name": f"vw_{fact}", "sql": sql, "tables": tables,
                      "why": f"{fact} is a fact table ({len(tables) - 1} dimensions joined in through the plan's relationships)"})
    for r in hard_relationships(plan):
        reason = {"R2": "the column has the target key's name, not the target's name", "R3": "the link spans several columns",
                  "R4": "the column abbreviates or role-prefixes the target", "confirmed": "the link was given by hand, the names do not show it"
                  }.get(r.rule, f"the column names a role ({r.field_name}), not the table")
        views.append({"name": f"vw_{r.source}_{r.field_name}", "sql": relationship_view_sql(plan, r, target), "tables": [r.source, r.target],
                      "why": f"{r.source}.{'+'.join(r.source_cols)} -> {r.target} ({r.rule}): {reason}"})
    return {"schema": target, "schema_sql": schema_sql(target), "views": views}


def apply(stmts: dict, run) -> list[dict]:
    """Run the schema statement and each view through `run(sql)` (a DB-API statement runner), stopping at the first
    failure; returns one line per statement."""
    log = [{"statement": "schema", "name": stmts["schema"]}]
    run(stmts["schema_sql"])
    log[0]["status"] = "ok"
    for v in stmts["views"]:
        entry = {"statement": "view", "name": v["name"]}
        log.append(entry)
        run(v["sql"])
        entry["status"] = "ok"
    return log
