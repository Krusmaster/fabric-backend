"""SQL-lineage spike, sqlglot side (throwaway; see README.md and docs/spikes/SQL-LINEAGE-SPIKE.md).

For every corpus statement: the equality join pairs between base-table columns (aliases, CTEs and derived tables
resolved) and the base-table origins of each output column. Writes results/sqlglot.json and schema.json.

What sqlglot gives out of the box: parse_one, qualify (aliases, star expansion, USING -> ON), Scope objects
(traverse_scope: sources per scope, CTE and derived-table scopes, parent links) and lineage(). What this file adds
(the glue, counted in the report): picking the equality predicates out of ON/WHERE, following a column through CTE
and derived-table projections to a base table, rewriting a MERGE into a SELECT, dropping lakehouse/schema prefixes so
one flat schema matches, and rendering {{ ref() }} / {{ config() }} with a regex. --raw turns those last four off
(results/sqlglot-raw.json): the out-of-the-box picture, with only the extraction itself.
"""
from __future__ import annotations

import argparse
import re

import sqlglot
from sqlglot import exp
from sqlglot.lineage import lineage
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

import spike_corpus as sc

DIALECT = {"tsql": "tsql", "spark": "spark"}
SQL_TYPE = {"string": "VARCHAR", "int": "INT", "boolean": "BOOLEAN"}


def render_jinja(sql: str) -> str:
    """Glue: the minimal dbt rendering a ref-only model needs (no macros, no control flow)."""
    sql = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}", "", sql, flags=re.S)
    sql = re.sub(r"\{\{\s*ref\(\s*'([^']+)'\s*\)\s*\}\}", r"\1", sql)
    return re.sub(r"\{\{\s*source\(\s*'[^']+'\s*,\s*'([^']+)'\s*\)\s*\}\}", r"\1", sql)


def resolve(col: exp.Column, scope: Scope, seen: int = 0) -> str | None:
    """Glue: follow a qualified column through CTE / derived-table projections (and outer scopes, for correlated
    references) to 'TABLE.COLUMN' of a base table; None when it ends in an expression, not a plain column."""
    s, src = scope, None
    while s is not None and src is None:
        src = s.sources.get(col.table)
        s = s.parent
    if isinstance(src, exp.Table):
        return f"{src.name}.{col.name}"
    if isinstance(src, Scope) and seen < 20:
        body = src.expression
        selects = body.selects if isinstance(body, exp.Select) else body.this.selects if isinstance(body, exp.SetOperation) else []
        for proj in selects:
            if proj.alias_or_name.upper() == col.name.upper():
                inner = proj.unalias()
                inner_scope = src if isinstance(body, exp.Select) else next(
                    (c for c in src.union_scopes if c.expression is body.this), src)
                return resolve(inner, inner_scope, seen + 1) if isinstance(inner, exp.Column) else None
    return None


def is_join_predicate(eq: exp.EQ) -> bool:
    """A conjunct (through AND / parentheses only) of a JOIN ON, WHERE, HAVING or MERGE ON; never a SET or CASE."""
    node = eq
    while isinstance(node.parent, (exp.And, exp.Paren)):
        node = node.parent
    parent = node.parent
    return isinstance(parent, (exp.Where, exp.Having)) or (isinstance(parent, exp.Join) and node.arg_key == "on")


def merge_as_select(merge: exp.Merge) -> exp.Select:
    """Glue: sqlglot has no scope model for MERGE; its target, USING source and ON become a SELECT with a JOIN."""
    return exp.select("1").from_(merge.this.copy()).join(merge.args["using"].copy(), on=merge.args["on"].copy())


def analyse(item: dict, schema: dict, raw: bool) -> dict:
    d = DIALECT[item["dialect"]]
    sql, glue = item["sql"], []
    if "{{" in sql and not raw:
        sql, _ = render_jinja(sql), glue.append("render_jinja")
    out = {"parse_ok": False, "error": None, "glue": glue, "joins": [], "lineage": {}}
    try:
        tree = sqlglot.parse_one(sql, read=d)
    except Exception as e:                                # noqa: BLE001 - a spike counts every failure
        out["error"] = f"parse: {type(e).__name__}: {str(e).splitlines()[0][:160]}"
        return out
    out["parse_ok"] = True
    for t in [] if raw else tree.find_all(exp.Table):    # glue: lh.dbo.VBAK -> VBAK, so one flat schema matches
        if t.args.get("db") or t.args.get("catalog"):
            t.set("db", None), t.set("catalog", None)
            if "strip_prefix" not in glue:
                glue.append("strip_prefix")
    query = tree
    if isinstance(tree, exp.Merge) and not raw:
        query, _ = merge_as_select(tree), glue.append("merge_as_select")
    elif isinstance(tree, (exp.Create, exp.Insert)):
        query = tree.expression
    try:
        query = qualify(query.copy(), schema=schema, dialect=d, validate_qualify_columns=False, identify=False)
    except Exception as e:                                # noqa: BLE001
        out["error"] = f"qualify: {type(e).__name__}: {str(e)[:160]}"
    pairs = set()
    for scope in traverse_scope(query):
        for eq in scope.find_all(exp.EQ):
            if not (isinstance(eq.left, exp.Column) and isinstance(eq.right, exp.Column) and is_join_predicate(eq)):
                continue
            a, b = resolve(eq.left, scope), resolve(eq.right, scope)
            if a and b and sc.norm(a).split(".")[0] != sc.norm(b).split(".")[0]:
                pairs.add(sc.pair(a, b))
    out["joins"] = sorted(pairs)
    if not isinstance(tree, exp.Merge) and isinstance(query, exp.Query):
        for name in query.named_selects:
            try:
                node = lineage(name, query, schema=schema, dialect=d)
            except Exception as e:                        # noqa: BLE001
                out["lineage"][name.upper()] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
                continue
            leaves = {sc.norm(f"{n.source.name}.{n.name.split('.')[-1]}") for n in node.walk()
                      if not n.downstream and isinstance(n.source, exp.Table)}
            out["lineage"][name.upper()] = sorted(leaves)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", action="store_true", help="no workaround glue (out-of-the-box behaviour)")
    args = ap.parse_args()
    raw = sc.demo_schema()
    sc.write_json(sc.HERE / "schema.json", raw)
    schema = {t: {c: SQL_TYPE.get(ty, ty) for c, ty in cols.items()} for t, cols in raw.items()}
    results = {it["id"]: analyse(it, schema, args.raw) for it in sc.load()}
    name = "sqlglot-raw.json" if args.raw else "sqlglot.json"
    sc.write_json(sc.RESULTS / name, {"tool": "sqlglot", "version": sqlglot.__version__, "results": results})
    print(f"wrote results/{name}: {sum(r['parse_ok'] for r in results.values())}/{len(results)} parsed")


if __name__ == "__main__":
    main()
