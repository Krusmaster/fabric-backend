"""CA1: data quality rules that follow from what Krusgraph proved, in a neutral form with the T-SQL that counts each
one (mustBe 0), and the same rule in the words of Microsoft Purview Data Quality's rule types, for a data quality
steward to create there (purview.py). Three kinds, only where the plan has the fact:

- unique_key: a table's key has no duplicates and no empty values (validate_plan: "unique in all N rows");
- no_orphans: every row with a value in the reference finds its row in the target (validate_plan: "0 orphans");
- rows_kept_after_join: totals at the right grain. Where validate_plan's amount levels found a header amount that a
  join with its line rows repeats, the line rows joined with the header are exactly the line rows with a value (the
  join neither drops nor repeats a line), and the header's amount is summed on the header table, never over the join.

A rule is "proven" only when validate_plan counted it and it held; otherwise it is "proposed" with what was counted, or
"not counted". Nothing here is a statement about the data beyond those counts."""
from __future__ import annotations


def _q(name: str) -> str:
    return "[" + str(name).replace("]", "]]") + "]"


def _t(schema: str, table: str) -> str:
    return f"{_q(schema)}.{_q(table)}"


def _state(verdict: str | None, ok: bool, checked_on: str | None) -> dict:
    if verdict is None:
        return {"status": "not counted", "verdict": None, "checked_on": None}
    return {"status": "proven" if ok else "proposed", "verdict": verdict, "checked_on": checked_on}


def rules(p, tables: list[str], schema: str, validation: dict | None = None, checked_on: str | None = None) -> list[dict]:
    mine = set(tables)
    low = {t.lower() for t in tables}
    v = validation or {}
    keys = {k["table"]: k for k in v.get("keys", []) if isinstance(k.get("rows"), int)}
    rels = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in v.get("relationships", [])
            if isinstance(r.get("orphans"), int)}
    out = []
    for t in tables:
        cols, rule = p.keys.get(t, ([], None))
        if not cols:
            continue
        k = keys.get(t)
        nulls = " OR ".join(f"{_q(c)} IS NULL" for c in cols)
        grp = ", ".join(_q(c) for c in cols)
        out.append({
            "id": f"{t}_key_unique".lower(), "kind": "unique_key", "table": t, "columns": list(cols),
            "rule": p.label(rule), "dimension": "uniqueness",
            "says": f"{t}.{'+'.join(cols)} has no duplicates and no empty values",
            "sql": (f"SELECT (SELECT COUNT_BIG(*) FROM {_t(schema, t)} WHERE {nulls}) + (SELECT COUNT_BIG(*) FROM "
                    f"(SELECT {grp} FROM {_t(schema, t)} GROUP BY {grp} HAVING COUNT_BIG(*) > 1) d)"),
            "must_be": 0,
            **_state(k and k.get("verdict"), bool(k) and str(k.get("verdict", "")).startswith("unique"), checked_on),
        })
    for r in p.relationships:
        if r.source not in mine or r.target not in mine or r.source == r.target:
            continue
        c = rels.get((r.source, tuple(x.lower() for x in r.source_cols), r.target))
        on = " AND ".join(f"t.{_q(b)} = s.{_q(a)}" for a, b in zip(r.source_cols, r.target_cols))
        some = " OR ".join(f"s.{_q(a)} IS NOT NULL" for a in r.source_cols)
        out.append({
            "id": f"{r.source}_{'_'.join(r.source_cols)}_no_orphans".lower(), "kind": "no_orphans",
            "table": r.source, "columns": list(r.source_cols), "target": r.target, "target_columns": list(r.target_cols),
            "rule": p.label(r.rule), "dimension": "consistency",
            "says": f"every {r.source}.{'+'.join(r.source_cols)} with a value finds its row in {r.target}",
            "sql": (f"SELECT COUNT_BIG(*) FROM {_t(schema, r.source)} s WHERE ({some}) AND NOT EXISTS "
                    f"(SELECT 1 FROM {_t(schema, r.target)} t WHERE {on})"),
            "must_be": 0,
            **_state(c and c.get("verdict"), bool(c) and c.get("orphans") == 0, checked_on),
        })
    for f in (v.get("amount_levels") or {}).get("findings", []):
        line, head = f.get("line"), f.get("header")
        if not line or not head or line.lower() not in low or head.lower() not in low:
            continue
        lc, hc = f.get("line_columns") or [], f.get("header_columns") or []
        if not lc or len(lc) != len(hc):
            continue
        on = " AND ".join(f"h.{_q(b)} = l.{_q(a)}" for a, b in zip(lc, hc))
        some = " AND ".join(f"l.{_q(a)} IS NOT NULL" for a in lc)
        k = keys.get(head)
        rk = rels.get((line, tuple(x.lower() for x in lc), head))
        held = bool(k) and str(k.get("verdict", "")).startswith("unique") and bool(rk) and rk.get("orphans") == 0
        amounts = ", ".join(f"{head}.{a}" for a in f.get("amount_columns", []))
        out.append({
            "id": f"{line}_{head}_rows_kept".lower(), "kind": "rows_kept_after_join", "table": line, "columns": list(lc),
            "target": head, "target_columns": list(hc), "rule": p.label(f.get("rule")), "dimension": "accuracy",
            "says": (f"{line} joined with {head} keeps each {line} row once, so {amounts or 'a ' + head + ' amount'} is "
                     f"summed on {head} itself and {line}'s own amounts over the join"),
            "sql": (f"SELECT ABS((SELECT COUNT_BIG(*) FROM {_t(schema, line)} l JOIN {_t(schema, head)} h ON {on}) - "
                    f"(SELECT COUNT_BIG(*) FROM {_t(schema, line)} l WHERE {some}))"),
            "must_be": 0,
            **_state("follows from the key of " + head + " and no orphans" if (k and rk) else None, held, checked_on),
            "grain": {"header": head, "line": line, "header_amounts": list(f.get("amount_columns", [])),
                      "do_instead": f.get("do_instead")},
        })
    return out
