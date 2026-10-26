"""fabric-backend CLI.

  fabric-backend plan   columns.csv [--keys keys.csv] [--mermaid out.mmd] [--json plan.json]
  fabric-backend definition columns.csv --name MyApi --workspace WS --source-item ID [--source-type ...] --out def.json
  fabric-backend deploy def.json --workspace WS
  fabric-backend rayfin columns.csv|metadata.json [--keys keys.csv] --connector sales [--source-type SqlAnalyticsEndpoint] [--out .]
  fabric-backend create --workspace WS --source <lakehouse name|id> --name MyApi --odbc "<connection string>"
  fabric-backend semantic-model columns.csv --name MyModel --sql-endpoint <host> --source-name <lakehouse> [--source-kind Lakehouse] [--schemas-enabled] [--out .]
  fabric-backend join-path columns.csv START END [--keys keys.csv] [--schema dbo]
  fabric-backend dictionary columns.csv [--source-name X] [--out dictionary.md]
  fabric-backend dbt columns.csv [--source-name X] [--database X] [--out schema.yml]
  fabric-backend analyze columns.csv [--json analysis.json]
  fabric-backend views columns.csv [--views-schema krusgraph]

`plan` and `definition` work offline from an INFORMATION_SCHEMA.COLUMNS export (csv with
table_schema, table_name, column_name, data_type, ordinal_position). `create` needs a SQL
connection (pyodbc) to the SQL analytics endpoint / warehouse and a Fabric token (az login, or
notebookutils inside Fabric).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import create
from .deploy import deploy
from .graphql import definition
from .infer import plan
from .rayfin import rayfin_files, write_rayfin
from .schema import Schema


def _csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _keys_arg(path: str | None) -> dict[str, list[str]] | None:
    if not path:
        return None
    out: dict[str, list[str]] = {}
    for r in _csv(path):
        out.setdefault(r["table_name"], []).append(r["column_name"])
    return out


def cmd_plan(a) -> int:
    p = plan(_source(a), _keys_arg(a.keys))
    print(p.summary())
    for r in p.relationships:
        print(f"  {r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)}  [{r.rule}]")
    for x in p.ambiguous:
        print(f"  ? {x['table']}.{x['column']} could point at {x['candidates']} — add to confirmed")
    if a.mermaid:
        Path(a.mermaid).write_text(p.mermaid(), encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps({
            "keys": {t: k for t, (k, _) in p.keys.items()},
            "relationships": [r.__dict__ for r in p.relationships], "ambiguous": p.ambiguous}, indent=2), encoding="utf-8")
    return 0


def cmd_definition(a) -> int:
    p = plan(_source(a), _keys_arg(a.keys))
    env = definition(p, a.name, a.workspace, a.source_item, a.source_type, writable=a.writable)
    Path(a.out).write_text(json.dumps(env, indent=2), encoding="utf-8")
    n = len(p.schema)
    print(f"wrote {a.out}: {n} types, {len(p.relationships)} relationships; skipped: {env.get('skipped_relationships', [])}")
    return 0


def cmd_deploy(a) -> int:
    env = json.loads(Path(a.definition).read_text(encoding="utf-8"))
    print(json.dumps(deploy(env, a.workspace), indent=2))
    return 0


def cmd_rayfin(a) -> int:
    p = plan(_source(a), _keys_arg(a.keys))
    files = rayfin_files(p, a.connector, a.source_type, relationships=not a.no_relationships)
    for path in write_rayfin(files, a.out):
        print("wrote", path)
    return 0


def cmd_ontology(a) -> int:
    from .ontology import ontology_files
    p = plan(_source(a), _keys_arg(a.keys))
    files = ontology_files(p, a.name, workspace_id=a.workspace, item_id=a.source_item, item_name=a.source_name or a.source_item,
                           item_kind=a.source_kind, schema=a.schema, sql_endpoint=a.sql_endpoint or "")
    for path in write_rayfin(files, a.out):                        # same writer: {relative path: text} under --out
        print("wrote", path)
    return 0


def _source(a) -> Schema:
    """The columns file: an INFORMATION_SCHEMA.COLUMNS export (CSV) or the metadata.json that `npx rayfin connector add`
    writes. With metadata.json and no --schema the file's first schema is used, and every command labels its output with
    the schema actually read."""
    if a.columns.endswith(".json"):
        src = Schema.from_rayfin_metadata(a.columns, None if a.schema == "dbo" else a.schema)
    else:
        src = Schema.from_information_schema(_csv(a.columns), schema=a.schema)
    a.schema = src.schema
    return src


def cmd_semantic_model(a) -> int:
    from .semantic_model import draft
    p = plan(_source(a), _keys_arg(a.keys))
    info = dict(workspace_id="", item_id="", item_name=a.source_name, item_kind=a.source_kind, schema=a.schema,
                sql_endpoint=a.sql_endpoint, sql_db=a.database or a.source_name,
                schemas_enabled=True if a.source_kind != "Lakehouse" else (True if a.schemas_enabled else None))
    out = draft(p, info, a.name)
    for path in write_rayfin(out["parts"], Path(a.out) / f"{a.name}.SemanticModel"):
        print("wrote", path)
    s = out["summary"]
    print(f"{s['tables']} tables, {s['relationships_active']} active and {s['relationships_inactive']} inactive relationships; see README.generated.md")
    return 0


def cmd_join_path(a) -> int:
    from .paths import join_path
    out = join_path(plan(_source(a), _keys_arg(a.keys)), a.start, a.end)
    if not out["paths"]:
        print(out["note"])
        for s in out.get("suggestions", []):
            print(f"  suggestion: confirmed={json.dumps(s['confirmed'])}  ({s['why']})")
        return 1
    for i, path in enumerate(out["paths"], 1):
        print(f"path {i}: " + " -> ".join(path["tables"]) + f"  ({path['hops']} hops, cost {path['cost']})")
        for st in path["steps"]:
            print(f"  {st['from']} -> {st['to']}  on {', '.join(st['on'])}  [{st['rule']} {st['certainty']}] {st['direction']}")
        print(path["sql"])
    if out.get("safest"):
        print("safest: " + " -> ".join(out["safest"]["tables"]) + f"  (cost {out['safest']['cost']}): {out['safest']['why']}")
    return 0


def cmd_dictionary(a) -> int:
    from .dictionary import data_dictionary
    md = data_dictionary(plan(_source(a), _keys_arg(a.keys)), a.source_name or Path(a.columns).stem, a.schema)
    Path(a.out).write_text(md, encoding="utf-8")
    print(f"wrote {a.out}")
    return 0


def cmd_dbt(a) -> int:
    from .dbt import schema_yml
    yml = schema_yml(plan(_source(a), _keys_arg(a.keys)), a.source_name or a.schema, a.schema, database=a.database, arguments_block=not a.legacy_arguments)
    Path(a.out).write_text(yml, encoding="utf-8")
    print(f"wrote {a.out}")
    return 0


def cmd_analyze(a) -> int:
    from .graphs import analyze
    p = plan(_source(a), _keys_arg(a.keys))
    out = analyze(p)
    print(p.summary().splitlines()[0] + "; " + out["summary"])
    print("roles:")
    for t, r in out["roles"].items():
        print(f"  {t}: {r['role']}  ({r['why']})")
    print("most central: " + ", ".join(f"{x['table']} (pagerank {x['pagerank']}, betweenness {x['betweenness']}, in {x['in']}, out {x['out']})" for x in out["centrality"]["top"][:5]))
    for g in out["areas"]:
        print(f"area {g['name']}: {', '.join(g['tables'])}")
    print(out["ambiguity"]["note"])
    for e in out["inactive_relationships"]:
        print(f"  inactive: {e['source']}.{'+'.join(e['columns'])} -> {e['target']} [{e['rule']} {e['certainty']}]: {e['why']}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


def cmd_views(a) -> int:
    from .views import statements
    st = statements(plan(_source(a), _keys_arg(a.keys)), a.views_schema)
    print(st["schema_sql"] + ";\nGO")                               # CREATE VIEW must be alone in its batch (T-SQL)
    for v in st["views"]:
        print(f"-- {v['why']}")
        print(v["sql"] + ";\nGO")
    return 0


def cmd_create(a) -> int:
    import pyodbc  # optional
    conn = pyodbc.connect(a.odbc)

    def execute(sql: str):
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    out = create(a.workspace, a.source, a.name, execute=execute, schema=a.schema, writable=a.writable, dry_run=a.dry_run)
    print(out["plan"].summary())
    if a.dry_run:
        print(json.dumps(out["definition"], indent=2)[:2000])
    else:
        print(json.dumps(out["result"], indent=2))
        print(out.get("card", ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-backend")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("plan"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--mermaid"); s.add_argument("--json"); s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("definition"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--name", required=True); s.add_argument("--workspace", required=True); s.add_argument("--source-item", required=True)
    s.add_argument("--source-type", default="SqlAnalyticsEndpoint"); s.add_argument("--writable", action="store_true")
    s.add_argument("--out", default="graphql.json"); s.set_defaults(fn=cmd_definition)

    s = sub.add_parser("deploy"); s.add_argument("definition"); s.add_argument("--workspace", required=True); s.set_defaults(fn=cmd_deploy)

    s = sub.add_parser("rayfin"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--connector", default="data"); s.add_argument("--source-type", default="SqlAnalyticsEndpoint")
    s.add_argument("--no-relationships", action="store_true"); s.add_argument("--out", default="."); s.set_defaults(fn=cmd_rayfin)

    s = sub.add_parser("ontology"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--name", required=True); s.add_argument("--workspace", required=True); s.add_argument("--source-item", required=True)
    s.add_argument("--source-name"); s.add_argument("--source-kind", default="Lakehouse"); s.add_argument("--sql-endpoint")
    s.add_argument("--out", default="."); s.set_defaults(fn=cmd_ontology)

    s = sub.add_parser("create"); s.add_argument("--workspace", required=True); s.add_argument("--source", required=True)
    s.add_argument("--name", required=True); s.add_argument("--odbc", required=True); s.add_argument("--schema", default="dbo")
    s.add_argument("--writable", action="store_true"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_create)

    s = sub.add_parser("semantic-model"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--name", required=True); s.add_argument("--sql-endpoint", required=True); s.add_argument("--source-name", required=True)
    s.add_argument("--source-kind", default="Lakehouse"); s.add_argument("--database"); s.add_argument("--schemas-enabled", action="store_true")
    s.add_argument("--out", default="."); s.set_defaults(fn=cmd_semantic_model)

    s = sub.add_parser("join-path"); s.add_argument("columns"); s.add_argument("start"); s.add_argument("end")
    s.add_argument("--keys"); s.add_argument("--schema", default="dbo"); s.set_defaults(fn=cmd_join_path)

    s = sub.add_parser("dictionary"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--source-name"); s.add_argument("--out", default="dictionary.md"); s.set_defaults(fn=cmd_dictionary)

    s = sub.add_parser("dbt"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--source-name"); s.add_argument("--database"); s.add_argument("--legacy-arguments", action="store_true")
    s.add_argument("--out", default="schema.yml"); s.set_defaults(fn=cmd_dbt)

    s = sub.add_parser("analyze"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--json"); s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("views"); s.add_argument("columns"); s.add_argument("--keys"); s.add_argument("--schema", default="dbo")
    s.add_argument("--views-schema", default="krusgraph"); s.set_defaults(fn=cmd_views)

    a = ap.parse_args(argv)
    from .infer import PlanInputError
    try:
        return a.fn(a)
    except (PlanInputError, ValueError, OSError) as e:      # a typo in --keys, a missing or wrong file: one line, no traceback
        print(f"fabric-backend: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
