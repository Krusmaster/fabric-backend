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


# ------------------------------------------------------------------ the start page's example -----------------------
# What the start page shows when a relationship or a table is selected: the suggestion, a short reason, the data check
# and the question a person still has to answer, with the rule in full behind a disclosure. Every number comes from
# demo_plan() and demo_validation(), the same data the graph draws, so the text and the picture cannot disagree.

HOME_DEFAULT = "orders.customer_id>customers"


def _noun(table: str, n: int | None = None) -> str:
    words = table.replace("_", " ")
    return words if n is None or n != 1 else _singular(table).replace("_", " ")


def _singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("sses"):
        return name[:-2]
    return name[:-1] if name.endswith("s") else name


def _edge_id(source: str, cols: list[str], target: str) -> str:
    return f"{source}.{'+'.join(cols)}>{target}"


_SHORT_REL = {
    "R0": "The source declares this foreign key.",
    "R1": "The column name matches the {target} table and its key.",
    "R2": "The column has the same name as the key of {target}.",
    "R3": "All columns of the key of {target} appear in {source}.",
    "R4": "A weaker name match: a role or an abbreviation in front of the table's name. Check it before you rely on it.",
    "confirmed": "It was confirmed by hand.",
}


def _detail(rows: list[tuple[str, str]], technical: str, heading: str, status: str = "") -> str:
    import html
    items = "".join(f"<div><dt>{html.escape(k)}</dt><dd>{v}</dd></div>" for k, v in rows)
    return (f'<p class="detail-head"><span class="detail-status">{html.escape(status)}</span>{heading}</p>' if status else
            f'<p class="detail-head">{heading}</p>') + f'<dl class="detail-list">{items}</dl>' + \
           f'<details class="tech"><summary>Technical details</summary><p>{technical}</p></details>'


def home_details() -> dict[str, str]:
    """{edge id or "table:<name>": HTML of the detail panel}; for the demo hint also "<id>|accepted"."""
    import html
    e = html.escape
    p, v = demo_plan(), demo_validation()
    rows = {t["name"]: t["rows"] for t in p["tables"]}
    checked_rels = {_edge_id(r["source"], r["columns"], r["target"]): r for r in v["relationships"]}
    checked_keys = {k["table"]: k for k in v["keys"]}
    out: dict[str, str] = {}
    for r in p["relationships"]:
        rid = _edge_id(r["source"], r["source_cols"], r["target"])
        col, s, t = " + ".join(r["source_cols"]), r["source"], r["target"]
        c = checked_rels.get(rid)
        if c is None:
            check = "Not checked."
        elif not c["rows_with_value"]:
            check = f"No row in this sample has a value in {e(col)}, so there is nothing to check."
        elif not c["orphans"]:
            every = "" if c["rows_with_value"] == rows.get(s) else f" with a {e(col)}"
            check = (f"All {c['rows_with_value']} {e(_noun(s))}{every} in this sample reference an existing "
                     f"{e(_singular(t).replace('_', ' '))}.")
        else:
            check = f"{c['orphans']} of {c['rows_with_value']} {e(_noun(s))} in this sample point at no {e(_singular(t).replace('_', ' '))}."
        why = e(_SHORT_REL.get(r["rule"], "").format(source=s, target=t))
        technical = (f"Rule <code>{e(r['rule'])}</code>: {e(RULES.get(r['rule'], '').replace('`', ''))}. In the API for GraphQL the "
                     f"link becomes <code>{e(s)}.{e(r['field'])}</code> and <code>{e(t)}.{e(r['reverse'])}</code>. "
                     f"The check is the counting query <code>validate_plan</code> runs.")
        out[rid] = _detail([("Suggestion", f"<code>{e(s)}.{e(col)}</code> → <code>{e(t)}.{e(' + '.join(r['target_cols']))}</code>"),
                            ("Why", why), ("Data check", check),
                            ("Your review", f"Does <code>{e(col)}</code> mean the {e(_singular(t).replace('_', ' '))} that each "
                                            f"{e(_singular(s).replace('_', ' '))} refers to?")],
                           technical, f"<code>{e(s)}</code> → <code>{e(t)}</code>", "Suggested by the engine")
    for h in p["suggestions"]:
        hid = _edge_id(h["table"], [h["column"]], h["target"])
        sugg = f"<code>{e(h['table'])}.{e(h['column'])}</code> → <code>{e(h['target'])}.{e(' + '.join(h['target_cols']))}</code>"
        technical = (f"No rule from <code>K0</code> to <code>R4</code> matched <code>{e(h['column'])}</code>, so the engine left it "
                     f"unlinked. This line is a hint for the demo ({e(h['why'])}), not inference. With the tools, accepting it means "
                     f"passing it as a <code>confirmed</code> entry; <code>suggest_relationships</code> counts how many of its values "
                     f"exist in <code>{e(h['target'])}</code>.")
        for accepted in (False, True):
            decision = ('<div class="choice"><button type="button" class="btn sage small" data-decide="accept" aria-pressed="'
                        + ("true" if accepted else "false") + '">Accept in this demo</button><button type="button" class="btn ghost small" '
                        'data-decide="skip" aria-pressed="' + ("false" if accepted else "true") + '">Leave unlinked</button></div>')
            outcome = ("Accepted in this demo: each order now has a ship-to address in the picture. Nothing changed in Fabric."
                       if accepted else "Left unlinked: <code>ship_to_id</code> stays a plain number. Nothing changed in Fabric.")
            out[hid + ("|accepted" if accepted else "")] = _detail(
                [("Suggestion", sugg + " (an example in this demo)"),
                 ("Why", f"No naming rule matched: <code>{e(h['column'])}</code> does not name a table."),
                 ("Data check", "Not checked in this demo."),
                 ("Your decision", f"Accept it, and each order gets a ship-to address in what you build. Leave it unlinked, and "
                                   f"<code>{e(h['column'])}</code> stays a plain number. {decision}<span class=\"decision-outcome\">{outcome}</span>")],
                technical, f"<code>{e(h['table'])}.{e(h['column'])}</code>",
                "Accepted in this demo" if accepted else "Needs your decision")
    for t in p["tables"]:
        key, rule = t["key"], t["key_rule"] if t["key"] else "K3"
        name = t["name"]
        k = checked_keys.get(name)
        if not key:
            why = "No column names a key, so nothing can point at this table. It can still be queried."
            check, review = "Not checked: there is no key to check.", f"Is there a column that identifies one {e(_singular(name).replace('_', ' '))}?"
        else:
            kk = " + ".join(key)
            why = {"K0": "The source declares this primary key.",
                   "K1": f"<code>{e(kk)}</code> was given as the key: the demo passes it, as you would with <code>keys</code>.",
                   "K2": (f"The column is called <code>{e(kk)}</code>, so it is read as the key." if kk.lower() == "id" else
                          f"<code>{e(kk)}</code> is named after the table, so it is read as the key."),
                   "K4": f"The table links others: its leading references together, <code>{e(kk)}</code>, are the key.",
                   "K5": f"A line table: <code>{e(kk)}</code>, the reference to its header plus a line number."}.get(rule, "")
            if k is None:
                check = "Not checked."
            elif k["verdict"].startswith("unique"):
                check = f"<code>{e(kk)}</code> is unique and never empty in all {k['rows']} rows of this sample."
            else:
                check = e(k["verdict"])
            review = f"Is <code>{e(kk)}</code> what identifies one {e(_singular(name).replace('_', ' '))} in your data?"
        technical = f"Rule <code>{e(rule)}</code>: {e(RULES.get(rule, '').replace('`', ''))}."
        out["table:" + name] = _detail([("Key", f"<code>{e(' + '.join(key))}</code>" if key else "none"), ("Why", why),
                                        ("Data check", check), ("Your review", review)],
                                       technical, f"<code>{e(name)}</code> · {t['rows']} rows",
                                       {"K0": "Key declared in the source", "K1": "Key given"}.get(rule, "Key suggested by the engine") if key else "No key")
    return out


def home_relationship_list() -> str:
    """The relationships of the demo as links, the alternative to the graph on a narrow screen and without a pointer."""
    import html
    from urllib.parse import quote
    e = html.escape
    p = demo_plan()
    items = []
    first = [r for r in p["relationships"] if _edge_id(r["source"], r["source_cols"], r["target"]) == HOME_DEFAULT]
    for r in first + [r for r in p["relationships"] if r not in first]:
        rid = _edge_id(r["source"], r["source_cols"], r["target"])
        items.append(f'<li><a href="/explore#edge={quote(rid)}" data-edge="{e(rid)}"><span><code>{e(r["source"])}.{e("+".join(r["source_cols"]))}</code> → '
                     f'<code>{e(r["target"])}</code></span><span class="rel-tag">suggested</span></a></li>')
    for h in p["suggestions"]:
        hid = _edge_id(h["table"], [h["column"]], h["target"])
        items.append(f'<li><a href="/explore#edge={quote(hid)}" data-edge="{e(hid)}"><span><code>{e(h["table"])}.{e(h["column"])}</code> → '
                     f'<code>{e(h["target"])}</code></span><span class="rel-tag decide">needs your decision</span></a></li>')
    return "".join(items)
