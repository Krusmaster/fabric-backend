"""BL19 (21 Nov 2026): the receipt as a notebook the customer runs (fabric_backend/receipt_notebook.py,
docs/RECEIPTS.md "Run it as a notebook").

Every code cell runs against a fake `spark` that executes the Spark SQL on SQLite with the synthetic shop and SAP demo
rows and prints the stated counts back as "same"; a planted extra row prints "changed"; no cell holds a row value, an
import, a %pip or a write.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3

import pytest

from fabric_backend import evidence, notebook, receipt_notebook, sap_demo, seed
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan as infer_plan
from fabric_backend.platforms import local

AT = dt.datetime(2026, 11, 21, 16, 40, tzinfo=dt.timezone.utc)


def _sap_db():
    """The SAP demo rows in SQLite with the connection kept, so a test can plant a row (as sap_demo.sqlite builds it)."""
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS sap")
    for name, (cols, _, rows) in sap_demo.tables().items():
        t = sap_demo.PREFIX + name.lower()
        con.execute(f"CREATE TABLE sap.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO sap.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
    return con


def _shop_db():
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, ddl in seed.SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v for v in r) for r in seed.rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
    return con


class _Row(dict):
    def asDict(self):                                   # noqa: N802 (pyspark's name)
        return dict(self)


class _Frame:
    def __init__(self, rows):
        self._rows = rows

    def collect(self):
        return self._rows


class FakeSpark:
    """spark.sql(...).collect()[0].asDict() over SQLite; only SELECT is accepted, so a write fails the test."""

    def __init__(self, con):
        self.con = con
        self.statements: list[str] = []

    def sql(self, statement: str):
        assert statement.lstrip().upper().startswith("SELECT"), statement
        self.statements.append(statement)
        cur = self.con.execute(sqlite_sql(statement))
        names = [d[0] for d in cur.description]
        return _Frame([_Row(zip(names, r)) for r in cur.fetchall()])


def _schema(name: str):
    return sap_demo.sqlite()[0] if name == "sap" else local.sample_source().schema


def _execute(con):
    def execute(sql):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return execute


DBS = {"sap": _sap_db, "shop": _shop_db}


def _build(name: str):
    con = DBS[name]()
    p = infer_plan(_schema(name))
    v = evidence.validate(p, _execute(con), 200)
    return con, p, v, receipt_notebook.cells(p, v, AT, f"sample {name}")


def _run(cells, con) -> tuple[list[str], FakeSpark]:
    spark, printed = FakeSpark(con), []
    ns = {"spark": spark, "print": lambda *a: printed.append(" ".join(str(x) for x in a)), "__builtins__": __builtins__}
    for kind, text in cells:
        if kind == "code":
            exec(compile(text, "<cell>", "exec"), ns)        # noqa: S102 (the test runs the notebook's own cells)
    return printed, spark


@pytest.mark.parametrize("name", sorted(DBS))
def test_every_cell_runs_to_the_stated_counts(name):
    con, p, v, cells = _build(name)
    printed, spark = _run(cells, con)
    numbers = [line for line in printed if re.match(r"\d+\. (same|changed): ", line)]
    assert numbers and len(numbers) == len(spark.statements)
    assert all(". same: " in line and "changed" not in line for line in numbers), [x for x in numbers if "changed" in x]
    assert printed[-1] == f"{len(numbers)} of {len(numbers)} numbers are the same as stated."
    assert all("`" in s and "[" not in s and "COUNT_BIG" not in s for s in spark.statements)   # Spark SQL, not T-SQL


def test_one_markdown_and_one_code_cell_per_number():
    con, p, v, cells = _build("sap")
    from fabric_backend import receipt
    from fabric_backend.dialects import DATABRICKS
    rows = receipt.build(p, v, AT, dialect=DATABRICKS)
    counted = [r for r in rows if r["sql"]]
    code = [t for k, t in cells if k == "code"]
    assert len(code) == len(counted) + 2                 # the helper and the summary
    for r in counted:
        assert any(t.startswith(f"krusgraph_check({r['n']}, ") for t in code)
        assert any(k == "markdown" and r["sentence"] in t for k, t in cells)
    assert cells[0][0] == "markdown" and cells[0][1].startswith("# Krusgraph receipt notebook")


def test_a_planted_row_prints_changed():
    con, p, v, cells = _build("sap")
    first = con.execute("SELECT * FROM sap.[sap_kna1] LIMIT 1").fetchone()
    con.execute(f"INSERT INTO sap.[sap_kna1] VALUES ({','.join('?' * len(first))})", first)
    printed, _ = _run(cells, con)
    changed = [line for line in printed if ". changed: " in line]
    assert changed and any("n: stated 4, now 5, changed" in line for line in changed)
    assert "numbers are the same as stated." in printed[-2] and printed[-1].startswith("Changed: ")
    assert any(". same: " in line for line in printed)   # the other numbers did not move


def test_no_cell_installs_imports_writes_or_reaches_out():
    for name in DBS:
        _, _, _, cells = _build(name)
        code = "\n".join(t for k, t in cells if k == "code")
        for word in ("%pip", "!pip", "import ", "open(", "requests", "http", ".write", "saveAsTable", "urllib", "socket"):
            assert word not in code, (name, word)
        for statement in ("INSERT", "UPDATE ", "DELETE", "DROP", "CREATE", "MERGE", "ALTER"):
            assert statement not in code.upper(), (name, statement)


def _cell_values(name: str) -> set[str]:
    if name == "shop":
        data = [r for rs in seed.rows().values() for r in rs]
    else:
        data = [r for _, _, rs in sap_demo.tables().values() for r in rs]
    values = set()
    for row in data:
        for x in row:
            if isinstance(x, (dt.date, dt.datetime)):
                values.add(x.isoformat())
            elif isinstance(x, str) and len(x.strip()) >= 4 and not x.strip().isdigit():
                values.add(x.strip())
            elif isinstance(x, float) and x != int(x):
                values.add(repr(x))
    return values


@pytest.mark.parametrize("name", sorted(DBS))
def test_no_cell_holds_a_row_value(name):
    schema = _schema(name)
    names = {t.lower() for t in schema.tables} | {c.name.lower() for t in schema.tables.values() for c in t.columns}
    _, p, v, cells = _build(name)
    text = json.dumps(receipt_notebook.ipynb(p, v, AT, f"sample {name}"))
    values = {x for x in _cell_values(name) if x.lower() not in names}
    assert values, "the sample should have values to look for"
    leaked = sorted(x for x in values if x in text)
    assert not leaked, leaked


def test_ipynb_is_nbformat_4():
    _, p, v, cells = _build("shop")
    nb = receipt_notebook.ipynb(p, v, AT, "sample shop")
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] >= 5
    assert nb["metadata"]["kernelspec"]["language"] == "Python" and nb["metadata"]["krusgraph"]["dialect"] == "databricks"
    assert len(nb["cells"]) == len(cells)
    ids = [c["id"] for c in nb["cells"]]
    assert len(set(ids)) == len(ids)
    for c, (kind, text) in zip(nb["cells"], cells):
        assert c["cell_type"] == kind and "".join(c["source"]) == text
        if kind == "code":
            assert c["outputs"] == [] and c["execution_count"] is None
    json.loads(json.dumps(nb))                           # plain JSON, ready to save as krusgraph-receipt.ipynb


def test_not_counted_items_get_no_code_cell():
    con = _sap_db()
    p = infer_plan(_schema("sap"))
    plain = _execute(con)

    def failing(sql):
        if "sap_vbap" in sql:
            raise RuntimeError("boom")
        return plain(sql)
    v = evidence.validate(p, failing, 200)
    assert v.get("not_counted")
    cells = receipt_notebook.cells(p, v, AT)
    nc = [t for k, t in cells if k == "markdown" and "Not counted, so there is no number" in t]
    assert len(nc) == len(v["not_counted"])
    printed, _ = _run(cells, con)
    assert not any("changed" in line for line in printed[:-1])


def test_cells_also_write_as_a_fabric_notebook_source():
    _, _, _, cells = _build("shop")
    text = notebook.fabric_source(cells, notebook.notebook_metadata())
    assert notebook.parse(text) == [(k, t.strip("\n")) for k, t in cells]


def test_module_prints_the_notebook(capsys):
    assert receipt_notebook.main(["--sample", "sap"]) == 0
    nb = json.loads(capsys.readouterr().out)
    assert nb["nbformat"] == 4 and nb["cells"][0]["source"][0].startswith("# Krusgraph receipt notebook")
