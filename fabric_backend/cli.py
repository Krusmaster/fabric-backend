"""fabric-backend CLI.

  fabric-backend plan   columns.csv [--keys keys.csv] [--mermaid out.mmd] [--json plan.json]
  fabric-backend definition columns.csv --name MyApi --workspace WS --source-item ID [--source-type ...] --out def.json
  fabric-backend deploy def.json --workspace WS
  fabric-backend rayfin columns.csv|metadata.json [--keys keys.csv] --connector inventory [--source-type SqlAnalyticsEndpoint] [--out .]
  fabric-backend create --workspace WS --source <lakehouse name|id> --name MyApi --odbc "<connection string>"

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
    p = plan(Schema.from_information_schema(_csv(a.columns), schema=a.schema), _keys_arg(a.keys))
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
    p = plan(Schema.from_information_schema(_csv(a.columns), schema=a.schema), _keys_arg(a.keys))
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
    src = (Schema.from_rayfin_metadata(a.columns, None if a.schema == "dbo" else a.schema) if a.columns.endswith(".json")
           else Schema.from_information_schema(_csv(a.columns), schema=a.schema))
    p = plan(src, _keys_arg(a.keys))
    files = rayfin_files(p, a.connector, a.source_type, relationships=not a.no_relationships)
    for path in write_rayfin(files, a.out):
        print("wrote", path)
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

    s = sub.add_parser("create"); s.add_argument("--workspace", required=True); s.add_argument("--source", required=True)
    s.add_argument("--name", required=True); s.add_argument("--odbc", required=True); s.add_argument("--schema", default="dbo")
    s.add_argument("--writable", action="store_true"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_create)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
