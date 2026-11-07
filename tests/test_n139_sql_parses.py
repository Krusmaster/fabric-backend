"""Round n139: every SQL file and SQL draft the engine writes parses with a real T-SQL parser (sqlglot, dialect tsql).

Found live on 7 November 2026: dbt_schema project=true (n114) wrote staging models where a column kept as the source
has it carried a trailing comment and the separating comma came after it, inside the comment:

    [city]  -- varchar: varchar without a length or precision in the metadata: kept as the source has it,
    row_number() over (...) as [_krusgraph_row]

so the next select item followed without a comma. The SQLite run in test_dbt_project.py did not see it: the shop seed
reports Spark types (string), which are all cast, and no column kept a comment. Here the shop schema is also read the
way a lakehouse SQL endpoint reports it (varchar, float, datetime2 without a length), next to n138's synthetic 15-table
fixture and every schema fixture in tests/fixtures/schemas (4 to 71 tables), and each piece of SQL must parse into statements, none of them an unparsed
Command, so a dropped comma or bracket fails CI.

dbt's Jinja is replaced before parsing: config() is removed, source('s', 't') becomes [s].[t] and ref('m') becomes [m].
The gold views are Spark SQL (materialized lake views), so their SELECT is parsed with the spark dialect.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from fabric_backend import answers, data_agent, dbt, evidence, fixes, gold, paths, seed, views
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan
from fabric_backend.schema import Schema

sqlglot = pytest.importorskip("sqlglot")
from sqlglot import exp  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"
# The shop seed's Spark types as a lakehouse SQL endpoint reports them: no length on varchar, which dbt.fabric_type
# cannot cast, so the staging model keeps the column with a comment (the live case).
ENDPOINT_TYPES = {"string": "varchar", "double": "float", "timestamp": "datetime2"}
SQL_START = re.compile(r"\s*(--[^\n]*\n\s*)*(SELECT|WITH|UPDATE|DELETE|INSERT|MERGE|ALTER|CREATE|DROP)\b", re.I)


def _endpoint_shop() -> Schema:
    s = seed.schema("shop")
    rows = [("shop", t.name, c.name, ENDPOINT_TYPES.get(c.data_type, c.data_type), i) for t in s for i, c in enumerate(t.columns, 1)]
    return Schema.from_information_schema(rows, schema="shop")


def _fifteen() -> Schema:
    """n138's synthetic 15-table fixture (tests/test_n138_card_polish.py FIFTEEN: keys and references, two
    self-references), typed as a SQL endpoint reports it: varchar and decimal without a length or precision, which the
    staging models keep with a comment, next to int keys and a datetime2 change time."""
    from test_n138_card_polish import FIFTEEN
    rows = []
    for t, key, refs in FIFTEEN:
        cols = list(dict.fromkeys([*key, *refs]))
        cols = [(c, "int") for c in cols] + [("name", "varchar"), ("amount", "decimal"), ("changed_at", "datetime2")]
        rows += [("dbo", t, c, typ, i) for i, (c, typ) in enumerate(cols, 1)]
    return Schema.from_information_schema(rows, schema="dbo")


def _fixture(name: str) -> Schema:
    fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    rows = [("dbo", t["name"], col, typ, i) for t in fx["tables"] for i, (col, typ) in enumerate(t["columns"], 1)]
    return Schema.from_information_schema(rows, schema="dbo")


SCHEMAS = {"shop": (lambda: seed.schema("shop"), "shop"), "shop_endpoint": (_endpoint_shop, "shop"), "fifteen": (_fifteen, "dbo")}
SCHEMAS.update({f.stem: ((lambda n=f.stem: _fixture(n)), "dbo") for f in sorted(FIXTURES.glob("*.json"))})


def _shop_validation(p):
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, rows in seed.rows().items():
        con.execute(f"CREATE TABLE shop.[{name}] ({seed.SCHEMAS[name]})")
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(rows[0]))})",
                        [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in rows])

    def execute(sql):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return evidence.validate(p, execute)


def without_jinja(sql: str) -> str:
    sql = re.sub(r"\{\{\s*config\([^}]*\)\s*\}\}", "", sql)
    sql = re.sub(r"\{\{\s*source\('([^']*)',\s*'([^']*)'\)\s*\}\}", r"[\1].[\2]", sql)
    sql = re.sub(r"\{\{\s*ref\('([^']*)'\)\s*\}\}", r"[\1]", sql)
    assert "{{" not in sql and "{%" not in sql, f"Jinja the test does not replace: {sql[:300]}"
    return sql


def parse_error(sql: str, dialect: str = "tsql") -> str | None:
    """None when `sql` parses into statements, none of them a Command sqlglot could not read; the error otherwise."""
    try:
        trees = sqlglot.parse(sql, read=dialect, error_level=sqlglot.ErrorLevel.RAISE)
    except sqlglot.errors.SqlglotError as e:
        return str(e)[:600]
    if not any(t is not None for t in trees):
        return "no statement"
    for t in trees:
        if isinstance(t, exp.Command):
            return f"not parsed, kept as a command: {t.sql()[:200]}"
    return None


def _strings(o, path=""):
    """Every string in a nested answer that is SQL by its first keyword, with its path."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(o, str) and SQL_START.match(o):
        yield path, o


def sql_pieces(name: str) -> list[tuple[str, str, str]]:
    """(where, sql, dialect) for every piece of SQL the drafts write for one schema."""
    make, schema = SCHEMAS[name]
    s = make()
    p = plan(s)
    validation = _shop_validation(p) if name == "shop" else None
    out = []
    project = dbt.project(p, schema, schema, validation=validation)
    sql_files = {k: v for k, v in project["files"].items() if k.endswith(".sql")}
    assert sql_files, "the dbt project has no SQL files"
    out += [(f"dbt {k}", without_jinja(v), "tsql") for k, v in sql_files.items()]
    v = views.statements(p, "krusgraph")
    out += [("views schema", v["schema_sql"], "tsql")] + [(f"views {x['name']}", x["sql"], "tsql") for x in v["views"]]
    names = [t.name for t in s]
    for a in names[:3]:
        for b in names:
            if a != b:
                try:
                    r = paths.join_path(p, a, b)
                except Exception:          # no path between the two: nothing to parse
                    continue
                out += [(f"join_path {a}->{b} #{i}", x["sql"], "tsql") for i, x in enumerate(r.get("paths", []))]
    out += [(f"key_sql {t}", evidence.key_sql(schema, t, c), "tsql") for t, (c, _) in p.keys.items()]
    out += [(f"relationship_sql {r.source}->{r.target}", evidence.relationship_sql(schema, r.source, r.source_cols, r.target, r.target_cols), "tsql")
            for r in p.relationships]
    out += [(f"sample_sql {t.name}", evidence.sample_sql(schema, t.name, t.column_names, 10, {c.name: c.data_type for c in t.columns}), "tsql")
            for t in s]
    out += [(f"data_agent example {i}", x["query"], "tsql") for i, x in enumerate(data_agent.fewshots(p, schema))]
    if name.startswith("shop"):
        for q, tables in [("total quantity per customer country", ["orders", "order_items", "customers"]),
                          ("how many orders per city", ["orders", "addresses"]),
                          ("number of products per category", ["products", "categories"])]:
            out += [(f"answer {q!r}{path}", sql, "tsql") for path, sql in _strings(answers.draft(p, q, tables))]
    if validation:
        out += [(f"fixes{path}", sql, "tsql") for path, sql in _strings(fixes.suggest(p, validation))]
    info = {"keys": {t: list(c) for t, (c, _) in p.keys.items()}}
    try:
        g = gold.spec(p, info)
    except Exception:                      # no fact table to build a gold view on
        g = None
    if g:
        out += [(f"gold {x['name']}", gold.select_sql(x, g["silver_schema"]), "spark") for x in g["views"]]
    return out


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_every_sql_draft_parses(name):
    pieces = sql_pieces(name)
    bad = [f"{where}: {err}\n{sql}" for where, sql, dialect in pieces if (err := parse_error(sql, dialect))]
    assert not bad, f"{len(bad)} of {len(pieces)} pieces of SQL do not parse:\n\n" + "\n\n".join(bad[:5])


def test_the_live_case_keeps_the_comma_before_the_comment():
    p = plan(_endpoint_shop())
    files = dbt.project(p, "shop", "shop")["files"]
    sql = next(v for k, v in files.items() if k.endswith("/stg_shop__addresses.sql"))
    assert "[city],  -- varchar: varchar without a length or precision in the metadata: kept as the source has it\n" in sql
    for k, v in files.items():
        for line in v.splitlines():
            code, sep, comment = line.partition("--")
            assert not (sep and comment.rstrip().endswith(",") and code.strip()), f"{k}: a comma inside a comment: {line}"
    for model in ("addresses", "audit_log", "categories", "customers", "products"):
        sql = next(v for k, v in files.items() if k.endswith(f"/stg_shop__{model}.sql"))
        assert parse_error(without_jinja(sql)) is None, sql


def test_the_parser_catches_a_dropped_comma():
    good = "select\n    [city],  -- varchar: kept,\n    [x] as [y]\nfrom [shop].[addresses]"
    assert parse_error(good) is None
    assert parse_error(good.replace("[city],  -- varchar: kept,", "[city]  -- varchar: kept,")) is not None
    assert parse_error("select [a], [b] from ([shop].[t]") is not None


def test_a_note_with_a_line_break_stays_one_comment():
    sql = "select\n    " + dbt._select_list([("[a]", "first line\nsecond, line"), ("[b]", None)], "    ") + "\nfrom [s].[t]"
    assert parse_error(sql) is None and "second, line" in sql.splitlines()[1]
