"""The site's illustrative demo: the real `plan()` run on the synthetic shop schema from `seed.py`, as JSON.

Nothing here is hand-written schema data. `/explore`, the start page graph and the partner workspace read this
JSON, so what the pages show is what the engine says — including the keyless `audit_log` and the `ship_to_id`
column that no rule links (the engine leaves it unlinked; the page lets you *confirm* it locally, which is the
`confirmed=[...]` mechanism of the real tools).
"""
from __future__ import annotations

import json
from functools import lru_cache

from .infer import RULES, plan
from .seed import rows, schema

DEMO_KEYS = {"order_items": ["order_id", "line_no"]}      # given explicitly so the demo shows a K1 override (K5 would infer the same)


def demo_plan() -> dict:
    s = schema("shop")
    p = plan(s, keys=DEMO_KEYS)
    counts = {name: len(data) for name, data in rows().items()}
    linked: set[tuple[str, str]] = set()
    for r in p.relationships:
        linked.update((r.source, c.lower()) for c in r.source_cols)
        linked.update((r.target, c.lower()) for c in r.target_cols)
    tables = []
    for t in s:
        key, rule = p.keys.get(t.name, ([], "K3"))
        tables.append({
            "name": t.name,
            "columns": [{"name": c.name, "type": c.data_type, "key": c.name in key,
                         "linked": (t.name, c.name.lower()) in linked} for c in t.columns],
            "key": key, "key_rule": rule, "rows": counts.get(t.name, 0),
        })
    unlinked = []
    for t in s:
        own = {c.lower() for c in p.keys.get(t.name, ([], ""))[0]}
        for c in t.column_names:
            if c.lower() in own or (t.name, c.lower()) in linked:
                continue
            if c.lower().endswith(("_id", "_key", "_no", "_nr")):
                unlinked.append({"table": t.name, "column": c,
                                 "note": "no rule matched: not named after another table, and not another table's key name"})
    # A hint for the one unlinked column, so the page can offer Accept/Skip. This is NOT engine output: the seed
    # happens to store address ids in orders.ship_to_id. It is labelled as a demo hint wherever it is shown.
    hints = [{"table": "orders", "column": "ship_to_id", "target": "addresses", "target_cols": ["address_id"],
              "source": "demo hint, not inferred", "why": "the synthetic seed stores address ids in this column"}]
    suggestions = [h for h in hints if any(u["table"] == h["table"] and u["column"] == h["column"] for u in unlinked)]
    return {
        "name": "shop", "label": "Illustrative demo", "engine": "fabric_backend.infer.plan",
        "keys_given": DEMO_KEYS, "summary": p.summary(), "rules": RULES,
        "tables": tables,
        "relationships": [{"source": r.source, "source_cols": r.source_cols, "target": r.target,
                           "target_cols": r.target_cols, "rule": r.rule, "field": r.field_name,
                           "reverse": r.reverse_name} for r in p.relationships],
        "ambiguous": p.ambiguous, "keyless": p.keyless, "unlinked": unlinked, "suggestions": suggestions, "mermaid": p.mermaid(),
    }


@lru_cache(maxsize=1)
def demo_validation() -> dict:
    """What `validate_plan` answers for the demo: the same `evidence.validate` checks, run over `seed.rows()` loaded into
    an in-memory SQLite database (the only translation: COUNT_BIG → COUNT). Computed, not hand-written."""
    import datetime
    import sqlite3
    from . import evidence
    from .seed import SCHEMAS
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, ddl in SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)

    def execute(sql: str):
        cur = con.execute(sql.replace("COUNT_BIG(", "COUNT("))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    s = schema("shop")
    out = evidence.validate(plan(s, keys=DEMO_KEYS), execute)
    con.close()
    out["suggested_keys"] = evidence.suggest_composite_keys(plan(s))        # what plan_backend suggests before any override
    out["computed"] = ("on the synthetic demo data (fabric_backend.seed.rows) in an in-memory SQLite database, with the same "
                       "checks validate_plan runs on a Fabric source")
    out["keys_given"] = DEMO_KEYS
    return out


@lru_cache(maxsize=1)
def demo_validation_json() -> str:
    return json.dumps(demo_validation(), indent=2, default=str)


def demo_plan_json() -> str:
    return json.dumps(demo_plan(), indent=1)
