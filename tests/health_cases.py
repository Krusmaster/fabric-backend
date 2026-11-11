"""n200: a small lakehouse on SQLite for the health tests: the source tables, the silver tables and the quarantine the
silver notebook makes of them (silver.simulate), the gold views as tables of their SELECT (gold.run_select), and a
`spark` double that runs the generated notebooks' own cells on it (spark.sql, catalog.tableExists and listTables,
table(...).schema, createDataFrame(...).write...saveAsTable, and DESCRIBE HISTORY from a commit log the test sets).

Two samples: the shop seed with a bronze layer's problems (silver_cases.seed_rows, the keys GIVEN_KEYS) and the mill
(fabric_backend.mill, seed 7) with its planted problems (tests/fixtures/mill/planted_issues.json)."""
import datetime as dt
import json
import re
import sqlite3

from fabric_backend import gold, health, mill, pipeline, seed, silver
from fabric_backend.infer import plan
from silver_cases import GIVEN_KEYS, seed_rows

WS = "11111111-1111-1111-1111-111111111111"
NOW = dt.datetime(2026, 11, 11, 6, 0, tzinfo=dt.timezone.utc)
MARK = {"plan_id": "plan-0123456789ab", "schema_fingerprint": "sha256:00112233445566ff"}


def _cols(spec: str) -> list[tuple[str, str]]:
    return [(c.split()[0], c.split()[1].lower()) for c in spec.split(", ")]


def _value(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v


class Lakehouse:
    def __init__(self, name: str, source_schema: str, p, columns: dict[str, list[tuple[str, str]]], data: dict[str, list[dict]],
                 order_by=None):
        self.name, self.source_schema, self.plan = name, source_schema, p
        self.info = dict(workspace_id=WS, item_id="lh-1", item_name=name, item_kind="Lakehouse", schema=source_schema, schemas_enabled=True)
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.schemas = {"main"}
        self.types: dict[tuple[str, str], dict[str, str]] = {}
        self.commits: dict[str, list[dict]] = {}
        self.writes: list[tuple[str, int]] = []
        for s in (source_schema, "silver", "gold"):
            self.attach(s)
        self.silver_spec = silver.spec(p, self.info, order_by=order_by)
        self.gold_spec = gold.spec(p, self.info)
        for t, cols in columns.items():
            self.load(source_schema, t, cols, data.get(t, []))
            self.commit(f"{source_schema}.{t}", NOW - dt.timedelta(hours=3))
        sim = silver.simulate(self.silver_spec, data)
        self.quarantine = sim["quarantine"]
        for t, rows in sim["silver"].items():
            self.load("silver", t, columns[t], rows)
        self.load("silver", silver.QUARANTINE, [("source_table", "string"), ("rule", "string"), ("reason", "string"),
                                                ("row_json", "string")],
                  [{"source_table": q["source_table"], "rule": q["rule"], "reason": q["reason"], "row_json": "{}"} for q in self.quarantine])
        for v in self.gold_spec["views"]:
            rows = gold.run_select(v, self.gold_spec, self.execute)
            self.load("gold", v["name"].split(".", 1)[1], [(c["as"], "string") for c in v["columns"]], rows)

    # ---- SQLite underneath
    def attach(self, schema: str):
        if schema not in self.schemas:
            self.con.execute(f"ATTACH DATABASE ':memory:' AS `{schema}`")
            self.schemas.add(schema)

    def load(self, schema, table, cols, rows):
        names = [c for c, _ in cols]
        self.con.execute(f"DROP TABLE IF EXISTS `{schema}`.`{table}`")
        self.con.execute(f"CREATE TABLE `{schema}`.`{table}` ({', '.join('`' + c + '`' for c in names)})")
        self.con.executemany(f"INSERT INTO `{schema}`.`{table}` VALUES ({', '.join('?' * len(names))})",
                             [tuple(_value(r.get(c)) for c in names) for r in rows])
        self.types[(schema.lower(), table.lower())] = dict(cols)

    def execute(self, sql):
        return [dict(r) for r in self.con.execute(sql).fetchall()]

    @staticmethod
    def parts(name: str) -> tuple[str, str]:
        found = re.findall(r"`((?:[^`]|``)*)`", name) or name.split(".")
        found = [x.replace("``", "`") for x in found]
        return (found[0], found[1]) if len(found) == 2 else ("main", found[0])

    def exists(self, name: str) -> bool:
        schema, table = self.parts(name)
        if schema not in self.schemas:
            return False
        return bool(self.con.execute(f"SELECT 1 FROM `{schema}`.sqlite_master WHERE type IN ('table', 'view') AND lower(name) = lower(?)",
                                     (table,)).fetchall())

    # ---- Delta's table history, as the test sets it
    def commit(self, table: str, at: dt.datetime, operation: str = "WRITE"):
        self.commits.setdefault(table.lower(), []).insert(0, {"version": len(self.commits.get(table.lower(), [])),
                                                              "timestamp": at.replace(tzinfo=None), "operation": operation})

    def history_rows(self, name: str) -> list[dict]:
        schema, table = self.parts(name)
        key = (table if schema == "main" else f"{schema}.{table}").lower()
        if key not in self.commits:
            raise RuntimeError(f"DESCRIBE HISTORY is only supported for Delta tables: {name}")
        return list(self.commits[key])

    # ---- the specs the pipeline carries
    def check_spec(self, mark=None, schedule=None):
        return pipeline.check_spec(self.plan, self.silver_spec, self.gold_spec, mark or MARK, schedule)

    def drift_spec(self, mark=None):
        return health.drift_spec(self.plan, self.silver_spec, self.gold_spec, mark or MARK)

    def health_rows(self, name: str = "health") -> list[dict]:
        if not self.exists(f"`krusgraph`.`{name}`"):
            return []
        return self.execute(f"SELECT * FROM `krusgraph`.`{name}` ORDER BY checked_at, `check`, object, rule")

    def spark(self):
        return FakeSpark(self)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def collect(self):
        return [type("Row", (), {"asDict": lambda _r, d=d: dict(d), "__getitem__": lambda _r, k, d=d: d[k]})() for d in self._rows]


class _Field:
    def __init__(self, name, t):
        self.name = name
        self.dataType = type("T", (), {"simpleString": lambda _s, t=t: t})()


class FakeSpark:
    def __init__(self, lh: Lakehouse):
        self.lh = lh
        spark = self

        class Catalog:
            @staticmethod
            def tableExists(name):
                return lh.exists(name)

            @staticmethod
            def listTables(schema):
                return [type("Table", (), {"name": r["name"]})() for r in
                        lh.execute(f"SELECT name FROM `{schema}`.sqlite_master WHERE type = 'table'")]
        self.catalog = Catalog()
        self._spark = spark

    def sql(self, text):
        t = text.strip()
        if t.upper().startswith("CREATE SCHEMA IF NOT EXISTS"):
            self.lh.attach(self.lh.parts(t.split()[-1] + ".`x`")[0])
            return _Rows([])
        if t.upper().startswith("DESCRIBE HISTORY"):
            name = t.split()[2]
            limit = int(t.split()[-1]) if "LIMIT" in t.upper() else 1000
            return _Rows(self.lh.history_rows(name)[:limit])
        return _Rows(self.lh.execute(t))

    def table(self, name):
        schema, table = self.lh.parts(name)
        cols = self.lh.types[(schema.lower(), table.lower())]
        return type("DF", (), {"schema": type("S", (), {"fields": [_Field(c, ty) for c, ty in cols.items()]})()})()

    def createDataFrame(self, data, ddl):
        names = [re.sub(r"[`]", "", part.strip().split()[0]) for part in ddl.split(",")]
        lh = self.lh

        class Writer:
            def format(self, fmt):
                self.fmt = fmt
                return self

            def mode(self, mode):
                assert mode == "append", "the health table is only ever appended to"
                return self

            def saveAsTable(self, name):
                schema, table = lh.parts(name)
                lh.con.execute(f"CREATE TABLE IF NOT EXISTS `{schema}`.`{table}` ({', '.join('`' + n + '`' for n in names)})")
                lh.con.executemany(f"INSERT INTO `{schema}`.`{table}` VALUES ({', '.join('?' * len(names))})",
                                   [tuple(_value(v) for v in row) for row in data])
                lh.writes.append((name, len(data)))
        return type("DF", (), {"write": Writer()})()


def shop() -> Lakehouse:
    p = plan(seed.schema("shop"), GIVEN_KEYS)
    cols = {t: _cols(spec) for t, spec in seed.SCHEMAS.items()}
    return Lakehouse("shop_lh", "shop", p, cols, seed_rows(), order_by={"orders": "order_date"})


def mill_lakehouse() -> Lakehouse:
    p = plan(mill.schema())
    cols = {t: _cols(spec) for t, spec in mill.SCHEMAS.items()}
    data = {t: [dict(zip([c for c, _ in cols[t]], r)) for r in rows] for t, rows in mill.rows().items()}
    return Lakehouse("mill_lh", "mill", p, cols, data)


def run_cells(cells, spark, params: dict | None = None, guarded=None, stop_at=None):
    """Run a notebook's code cells as Fabric does (the parameters cell, then the pipeline's values on top)."""
    ns = {"spark": spark}
    if guarded is not None:
        ns["__builtins__"] = guarded
    for kind, code in cells:
        if kind == "markdown":
            continue
        exec(compile(code, "<notebook cell>", "exec"), ns)
        if kind == "parameters":
            ns.update(params or {})
        if stop_at and stop_at in code:
            break
    return ns


def no_row_values(rows: list[dict], lh: Lakehouse) -> None:
    """Asserts that the health rows hold no value from the data: every text is a name, a rule, a status or an id, and no
    key value, sample row or amount from the source rows appears."""
    allowed_text = re.compile(r"^[A-Za-z0-9_ .+()\-:,]*$")
    for r in rows:
        for k in ("check", "object", "rule", "status"):
            assert allowed_text.match(str(r[k] or "")), r
    values = set()
    for table, _cols in lh.types.items():
        if table[0] in ("silver", "gold", lh.source_schema.lower()) and not table[1].startswith("krusgraph"):
            for row in lh.execute(f"SELECT * FROM `{table[0]}`.`{table[1]}`"):
                values |= {str(v) for v in row.values() if isinstance(v, str) and len(v) > 3}
    for r in rows:
        for k in ("object", "rule"):
            for part in re.split(r"[.()+ ]", str(r[k] or "")):
                if part and part in values:
                    # a column or table name may coincide with a value only when it is a name in the plan
                    names = {t.name.lower() for t in lh.plan.schema} | {c.name.lower() for t in lh.plan.schema for c in t.columns}
                    assert part.lower() in names or part in ("silver", "gold", lh.source_schema), (part, r)
    assert all(set(r) == set(health_columns()) for r in rows)


def health_columns():
    return ["run_id", "checked_at", "plan_id", "schema_fingerprint", "check", "object", "rule", "status", "count", "baseline"]


def card_text(card: dict) -> str:
    return json.dumps(card)
