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

DEMO_KEYS = {"order_items": ["order_id", "line_no"]}      # composite keys cannot be guessed from names (K1)


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
def demo_plan_json() -> str:
    return json.dumps(demo_plan(), indent=1)
