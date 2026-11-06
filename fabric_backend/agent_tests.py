"""Test questions for a Fabric data agent, drafted from the checked plan (round n131).

`questions(plan, checks)` turns a plan and the result of `evidence.validate` (validate_plan's full answer) into 10 to
20 questions a customer can put to their data agent. Each question carries:

- `sql`: T-SQL that gives the right answer. It joins only over relationships the checks found to hold without orphans
  and with a unique target key; everything else is answered from one table, without a join.
- `expected`: the shape of the answer (a count, a count per group, a sum, a sum per group) and how to compare it.
- `trap`: for the questions that test a finding, which finding (its id, as review_plan names it) and the mistake an
  answer would show: a header amount summed over its lines, rows lost to orphans in an inner join, rows repeated by
  a join to a target whose key is not unique (many-to-many).

The customer runs the SQL on their own SQL analytics endpoint to get the expected values and compares the agent's
answers with them (`SCORING`). Krusgraph runs neither the SQL nor the agent and keeps no answer; nothing here holds a
value read from a row. `create_data_agent` with test_questions=true returns them next to the agent's draft.
"""
from __future__ import annotations

from .evidence import qi
from .infer import Plan
from .review import key_id, rel_id

MIN_QUESTIONS, MAX_QUESTIONS = 10, 20
SUM_TOLERANCE = "absolute difference at most 0.01, or at most 0.1 % of the expected value when that is larger"
SCORING = ("Run each question's sql yourself and keep the result as the expected answer. Put the question to the data "
           "agent as written and compare its answer with that result: a count (or a count per group) is right only on an "
           f"exact match; a sum (or a sum per group) is right within a tolerance: {SUM_TOLERANCE}, which allows for rounding "
           "of decimals. Per group, every group must be present with the right value and no group may be added. A trap "
           "question answered wrongly usually shows the mistake its trap names (a doubled total, missing rows, repeated "
           "rows). Score = right answers / questions; report trap questions separately. Krusgraph neither runs the agent "
           "nor stores the answers.")


def _t(schema: str, table: str) -> str:
    return f"{qi(schema)}.{qi(table)}"


def _shape(kind: str, value: str, group_by: list[str] | None = None) -> dict:
    exact = kind.startswith("count")
    return {"kind": kind, "value": value, **({"group_by": group_by} if group_by else {}),
            "compare": "exact match" if exact else f"within tolerance ({SUM_TOLERANCE})"}


def _status(checks: dict) -> tuple[set[str], list[dict], list[dict], list[dict]]:
    """(tables with a unique key, safe relationships, relationships with orphans, many-to-many relationships)."""
    unique = {k["table"] for k in checks.get("keys", []) if k["verdict"].startswith("unique")}
    safe, orphans, many = [], [], []
    for r in checks.get("relationships", []):
        if r.get("kind"):                                        # a pack's extended join, not a key join
            if r.get("several"):
                many.append(r)
            continue
        if r.get("orphans", 0) > 0:
            orphans.append(r)
        if r["target"] not in unique:
            many.append(r)
        elif r["verdict"].startswith("holds") and not r.get("orphans") and "but" not in r["verdict"]:
            safe.append(r)
    return unique, safe, orphans, many


def _plain_columns(plan: Plan, table: str) -> list[str]:
    """Numeric columns that are neither the key nor a reference: what a sum can be asked over."""
    from .amounts import is_numeric, is_quantity, looks_like_amount
    key = {c.lower() for c in plan.keys.get(table, ([], ""))[0]}
    refs = {c.lower() for r in plan.relationships if r.source == table for c in r.source_cols}
    return [c.name for c in plan.schema[table].columns if c.name.lower() not in key | refs and is_numeric(c.data_type)
            and (looks_like_amount(c.name, c.data_type) or is_quantity(c.name, c.data_type))]


def _on(a: str, b: str, r: dict) -> str:
    return " AND ".join(f"{a}.{qi(x)} = {b}.{qi(y)}" for x, y in zip(r["columns"], r["target_columns"]))


def questions(plan: Plan, checks: dict) -> dict:
    """10 to 20 test questions from the plan and validate's full answer. Deterministic: the same plan and checks give
    the same questions in the same order. Fewer than 10 only when the plan offers no more, and then `note` says so."""
    from .amounts import is_price
    schema = plan.schema.schema
    unique, safe, orphans, many = _status(checks)
    findings = [f for f in (checks.get("amount_levels") or {}).get("findings", [])
                if isinstance(f.get("rows_per_header"), dict) and f["rows_per_header"].get("max_lines", 0) > 1]
    header_level = {(f["header"], c) for f in findings for c in f["amount_columns"]}
    traps: list[dict] = []
    plain: list[dict] = []

    for f in findings:                                            # a header amount that a join with its lines repeats
        h, line = f["header"], f["line"]
        fid = rel_id(line, f["line_columns"], h)
        for col in [c for c in f["amount_columns"] if not is_price(c)]:   # a unit price is not a total
            trap = {"kind": "header_amount", "finding": fid,
                    "mistake": f"summing {h}.{col} over the joined {line} rows counts it once per line, so the total "
                               f"comes out too high; it belongs to {h}, one row per {h}."}
            traps.append({"question": f"What is the total {col} over all {h}?",
                          "sql": f"SELECT SUM(h.{qi(col)}) AS {qi('total_' + col)} FROM {_t(schema, h)} AS h",
                          "expected": _shape("sum", "total_" + col), "trap": trap})
            dim = next((r for r in safe if r["source"] == h and len(r["columns"]) == 1), None)
            if dim:
                g = dim["columns"][0]
                traps.append({"question": f"What is the total {col} per {dim['target']}.{dim['target_columns'][0]}?",
                              "sql": f"SELECT h.{qi(g)}, SUM(h.{qi(col)}) AS {qi('total_' + col)} FROM {_t(schema, h)} AS h "
                                     f"GROUP BY h.{qi(g)} ORDER BY h.{qi(g)}",
                              "expected": _shape("sum_per_group", "total_" + col, [g]),
                              "trap": {**trap, "path": [rel_id(h, dim["columns"], dim["target"])]}})

    for r in orphans:                                             # references that find nothing
        s, t = r["source"], r["target"]
        fid = rel_id(s, r["columns"], t)
        traps.append({"question": f"How many {s} rows are there, including those whose {'+'.join(r['columns'])} finds no {t} row?",
                      "sql": f"SELECT COUNT_BIG(*) AS row_count FROM {_t(schema, s)}",
                      "expected": _shape("count", "row_count"),
                      "trap": {"kind": "orphan", "finding": fid,
                               "mistake": f"an inner join of {s} with {t} drops the {s} rows whose "
                                          f"{'+'.join(r['columns'])} finds no {t}, so the count comes out too low."}})
        cond = " AND ".join(f"s.{qi(c)} IS NOT NULL" for c in r["columns"])
        traps.append({"question": f"How many {s} rows have a {'+'.join(r['columns'])} that finds no {t} row?",
                      "sql": f"SELECT COUNT_BIG(*) AS orphan_rows FROM {_t(schema, s)} AS s WHERE {cond} AND NOT EXISTS "
                             f"(SELECT 1 FROM {_t(schema, t)} AS t WHERE {_on('s', 't', r)})",
                      "expected": _shape("count", "orphan_rows"),
                      "trap": {"kind": "orphan", "finding": fid,
                               "mistake": f"an answer from an inner join cannot see these rows and says 0."}})

    for r in many:                                                # a join that repeats rows
        s, t = r["source"], r["target"]
        fid = rel_id(s, r["columns"], t)
        g = r["columns"]
        traps.append({"question": f"How many {s} rows are there per {s}.{'+'.join(g)}?",
                      "sql": f"SELECT {', '.join(qi(c) for c in g)}, COUNT_BIG(*) AS row_count FROM {_t(schema, s)} "
                             f"GROUP BY {', '.join(qi(c) for c in g)} ORDER BY {', '.join(qi(c) for c in g)}",
                      "expected": _shape("count_per_group", "row_count", list(g)),
                      "trap": {"kind": "many_to_many", "finding": fid, "also": key_id(t) if not r.get("kind") else None,
                               "mistake": f"a join of {s} with {t} repeats a {s} row for every {t} row that matches it, "
                                          f"because {t} can hold more than one row per {'+'.join(r['target_columns'])}; "
                                          "the counts come out too high."}})

    for t in plan.schema:                                         # plain questions over unique keys and safe joins
        if t.name in unique and t.name not in {r["source"] for r in orphans}:   # asked above, as a trap
            plain.append({"question": f"How many {t.name} are there?",
                          "sql": f"SELECT COUNT_BIG(*) AS row_count FROM {_t(schema, t.name)}",
                          "expected": _shape("count", "row_count"), "trap": None})
    for r in safe:
        if len(r["columns"]) != 1:
            continue
        s, t, k = r["source"], r["target"], r["target_columns"][0]
        path = [rel_id(s, r["columns"], t)]
        plain.append({"question": f"How many {s} rows does each {t}.{k} have, including those with none?",
                      "sql": f"SELECT t.{qi(k)}, COUNT_BIG(s.{qi(r['columns'][0])}) AS row_count FROM {_t(schema, t)} AS t "
                             f"LEFT JOIN {_t(schema, s)} AS s ON {_on('s', 't', r)} GROUP BY t.{qi(k)} ORDER BY t.{qi(k)}",
                      "expected": _shape("count_per_group", "row_count", [k]), "trap": None, "path": path})
        for col in [c for c in _plain_columns(plan, s) if (s, c) not in header_level][:1]:
            plain.append({"question": f"What is the total {col} of {s} per {t}.{k}?",
                          "sql": f"SELECT t.{qi(k)}, SUM(s.{qi(col)}) AS {qi('total_' + col)} FROM {_t(schema, s)} AS s "
                                 f"JOIN {_t(schema, t)} AS t ON {_on('s', 't', r)} GROUP BY t.{qi(k)} ORDER BY t.{qi(k)}",
                          "expected": _shape("sum_per_group", "total_" + col, [k]), "trap": None, "path": path})

    for q in traps:
        if q["trap"].get("also") is None:
            q["trap"].pop("also", None)
    picked = traps[:MAX_QUESTIONS]
    picked += plain[:MAX_QUESTIONS - len(picked)]
    for i, q in enumerate(picked, 1):
        q["id"] = f"Q{i:02d}"
    out = {"summary": f"{len(picked)} test question(s), {sum(1 for q in picked if q['trap'])} of them testing a finding of the checks",
           "questions": [{k: q[k] for k in ("id", "question", "sql", "expected", "trap", "path") if k in q} for q in picked],
           "safe_paths": [rel_id(r["source"], r["columns"], r["target"]) for r in safe],
           "scoring": SCORING,
           "note": ("The right answer comes from running each sql yourself; Krusgraph does not run it, does not run the agent "
                    "and keeps no answer. Joins in the sql use only the relationships in safe_paths (checked: no orphans, a "
                    "unique target key); questions about a finding are answered from one table. The checks are counts at the "
                    "moment validate_plan ran; new rows can change both them and the expected values.")}
    if len(picked) < MIN_QUESTIONS:
        out["note"] += f" The plan offers only {len(picked)} question(s), fewer than {MIN_QUESTIONS}."
    return out


def demo() -> dict:
    """The shop schema in SQLite with three findings added: an order amount on orders (a header amount over
    order_items), an order line whose product does not exist (an orphan) and a category id held twice (a target key
    that is not unique). Returns the plan, its checks, the questions and the open
    connection (for tests, which run the sql); the questions themselves hold no value."""
    import sqlite3

    from .dialects import sqlite_sql
    from .evidence import validate
    from .infer import plan as make_plan
    from .schema import Column, Schema, Table
    from .seed import SCHEMAS, rows
    data = rows()
    ddl = dict(SCHEMAS, orders=SCHEMAS["orders"] + ", order_amount DOUBLE")
    data["orders"] = [o + (100.0 + o[0],) for o in data["orders"]]
    data["order_items"].append((100, 9, 99, 1.0))                   # product 99 does not exist
    data["categories"].append((3, "Accessories (copy)"))           # category 3 twice
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    s = Schema(schema="shop")
    for name, cols in ddl.items():
        parts = [c.split() for c in cols.split(", ")]
        con.execute(f"CREATE TABLE shop.[{name}] ({', '.join(f'[{a}] {b}' for a, b in parts)})")
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(parts))})",
                        [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in data[name]])
        s.tables[name] = Table(name, [Column(a, b.lower()) for a, b in parts], schema="shop")

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    p = make_plan(s)
    checks = validate(p, execute)
    out = {"plan": p, "checks": checks, "questions": questions(p, checks), "execute": execute, "connection": con}
    return out
