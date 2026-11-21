"""Round DBT1: the synthetic SAP, Salesforce and Dynamics 365 demos in SQLite, their dbt projects (dbt.project), and a
runner that builds the staging models and marts as views and runs a singular test's SQL on them. The SQL is T-SQL for
dbt-fabric; SQLite reads it here with [brackets] and the Jinja replaced (test_n139's without_jinja), only to show which
rows a test returns. Nothing runs dbt."""
from __future__ import annotations

import sqlite3

from fabric_backend import dbt, dynamics_demo, evidence, salesforce_demo, sap_demo
from fabric_backend.dialects import sqlite_sql
from fabric_backend.infer import plan
from test_n139_sql_parses import without_jinja

DEMOS = {"sap": (sap_demo, "sap"), "salesforce": (salesforce_demo, "salesforce"), "dynamics": (dynamics_demo, "dynamics")}


def tables(name: str) -> dict:
    mod, _ = DEMOS[name]
    if name == "sap":
        return {sap_demo.PREFIX + t.lower(): v for t, v in mod.tables().items()}
    return dict(mod.tables())


def project(name: str) -> tuple[dict, object, dict]:
    """(dbt.project's answer, the plan, validate_plan's counts) for a demo; the source is named as its schema."""
    mod, schema = DEMOS[name]
    s, execute = mod.sqlite()
    p = plan(s)
    v = evidence.validate(p, execute)
    return dbt.project(p, schema, schema, "lh", v), p, v


class Warehouse:
    """The demo rows in SQLite (the schema attached under the source's name), the staging models and marts as views."""

    def __init__(self, name: str, files: dict[str, str]):
        self.schema = DEMOS[name][1]
        self.con = sqlite3.connect(":memory:")
        self.con.execute(f"ATTACH DATABASE ':memory:' AS {self.schema}")
        self.cols = {}
        for t, (cols, _kinds, rows) in tables(name).items():
            self.cols[t] = cols
            self.con.execute(f"CREATE TABLE {self.schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
            self.con.executemany(f"INSERT INTO {self.schema}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
        self.files = files
        self.models()

    def lite(self, sql: str) -> str:
        return sqlite_sql(without_jinja(sql)).replace(f"[{self.schema}].", f"{self.schema}.").replace("(max)", "")

    def models(self, replace: dict[str, str] | None = None):
        """Every staging model and mart as a view (a view after the views it reads); `replace` swaps a mart's SQL."""
        models = {k.rsplit("/", 1)[1][:-4]: v for k, v in self.files.items() if k.startswith("models/") and k.endswith(".sql")}
        models.update(replace or {})
        for m in models:
            self.con.execute(f"DROP VIEW IF EXISTS [{m}]")
        left = dict(models)
        while left:
            done = []
            for m, sql in left.items():
                try:
                    self.con.execute(f"CREATE TEMP VIEW [{m}] AS {self.lite(sql)}")
                    done.append(m)
                except sqlite3.OperationalError:
                    pass
            assert done, f"views that never build: {sorted(left)}"
            for m in done:
                del left[m]

    def run(self, path: str) -> list[tuple]:
        return self.con.execute(self.lite(self.files[path])).fetchall()

    def failing(self, folder: str = "tests/krusgraph_checks/") -> dict[str, list[tuple]]:
        out = {}
        for k in self.files:
            if k.startswith(folder):
                rows = self.run(k)
                if rows:
                    out[k] = rows
        return out
