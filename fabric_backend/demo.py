"""The site's illustrative demo: the real `plan()` run on the synthetic shop schema from `seed.py`, as JSON.

Nothing here is hand-written schema data. `/explore`, the guided demo's graph on `/demo` and the partner workspace
read this JSON, so what the pages show is what the engine says — including the keyless `audit_log` and the
`ship_to_id` column that no naming rule links. For that column the pages show what `suggest_relationships` answers
on the same synthetic rows: its best candidate with the reasons and the count of matching values (home page round 1,
27 October 2026; before it the column carried a hand-written demo hint). Accepting it on a page is the page-local
equivalent of the tools' `confirmed=[...]`, and it decides what the column means; the count is the separate data
check.
"""
from __future__ import annotations

import json
from functools import lru_cache

from .infer import RULES, plan
from .seed import rows, schema

DEMO_KEYS = {"order_items": ["order_id", "line_no"]}      # given explicitly so the demo shows a K1 override (K5 would infer the same)


@lru_cache(maxsize=1)
def _demo_db():
    """The synthetic rows in an in-memory SQLite database, and an execute() that speaks the T-SQL the engine writes
    (COUNT_BIG becomes COUNT, TOP (n) becomes LIMIT n): the database behind the demo's data checks."""
    import datetime
    import re
    import sqlite3
    from .seed import SCHEMAS
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    for name, ddl in SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        data = [tuple(v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v for v in r) for r in rows()[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)

    def execute(sql: str):
        sql = sql.replace("COUNT_BIG(", "COUNT(")
        m = re.match(r"^\s*SELECT\s+TOP\s*\(?\s*(\d+)\s*\)?\s+", sql, re.I)
        if m:
            sql = "SELECT " + sql[m.end():] + f"\nLIMIT {int(m.group(1))}"
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return execute


def _check_sentence(c: dict) -> str:
    """One sentence for a candidate's data check, in the words of the table and the column."""
    ev = c.get("evidence") or {}
    if not ev.get("rows_with_value"):
        return ""
    src, col, tgt = c["source"], c["source_cols"][0], c["target"]
    n, d = ev["rows_with_value"], ev.get("distinct_values")
    if ev.get("matched") == n:
        return (f"All {n} {src} in this sample have a {col} that exists in {tgt}"
                + (f" ({d} different {tgt})." if d else "."))
    return f"{ev.get('matched', 0)} of {n} {src} in this sample have a {col} that exists in {tgt}."


@lru_cache(maxsize=1)
def demo_suggestions() -> list[dict]:
    """What suggest_relationships answers on the synthetic rows for the columns no naming rule links: the best candidate
    per column, with the engine's reasons, its score and its data check, and how the next candidate fared."""
    from . import graphs
    out = graphs.suggest(plan(schema("shop"), keys=DEMO_KEYS), _demo_db())
    best: dict[tuple, list[dict]] = {}
    for c in out["candidates"]:
        if len(c["source_cols"]) == 1:
            best.setdefault((c["source"], c["source_cols"][0]), []).append(c)
    found = []
    for (table, column), cands in best.items():
        cands = sorted(cands, key=lambda c: -c.get("final_score", c["score"]))
        top = cands[0]
        ev = top.get("evidence") or None
        entry = {"table": table, "column": column, "target": top["target"], "target_cols": top["target_cols"],
                 "source": "suggest_relationships", "why": top["why"], "score": top["score"],
                 "name_basis": top.get("name_basis", ""), "closure_via": top.get("closure_via", ""),
                 "evidence": ev, "check": _check_sentence(top), "confirmed": top["confirmed"]}
        nxt = next((c for c in cands[1:] if c.get("evidence")), None)
        if nxt:
            entry["runner_up"] = {"target": nxt["target"], "matched": nxt["evidence"]["matched"],
                                  "rows_with_value": nxt["evidence"]["rows_with_value"]}
        found.append(entry)
    return found


def demo_preview(n: int = 3) -> list[dict]:
    """The first orders of the synthetic seed, for the guided example's illustrative order view."""
    return [{"order_id": o[0], "customer_id": o[1], "order_date": o[2].isoformat(), "ship_to_id": o[3]} for o in rows()["orders"][:n]]


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
    # For a column no naming rule links: what suggest_relationships proposes on the same rows, checked against them.
    suggestions = [h for h in demo_suggestions() if any(u["table"] == h["table"] and u["column"] == h["column"] for u in unlinked)]
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
    from . import evidence
    s = schema("shop")
    out = evidence.validate(plan(s, keys=DEMO_KEYS), _demo_db())
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


# ------------------------------------------------------------------ the guided demo's example (/demo) --------------
# What /demo shows when a relationship or a table is selected: the suggestion, a short reason, the data check
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


def _plain_why(h: dict) -> str:
    """The engine's reasons for a suggestion, in plain words, from the fields suggest_relationships returns."""
    why = h.get("why", "")
    parts = []
    if "address role" in why:
        parts.append("the name reads as an address role (ship-to)")
    elif h.get("name_basis"):
        parts.append(f"the name resembles {h['target']} ({h['name_basis']})")
    if "matches the type" in why:
        parts.append(f"its type matches the key of {h['target']}")
    via = h.get("closure_via") or ""
    if via:
        middle = via.split(" -> ")[-1].split(" <- ")[0]
        parts.append(f"{h['table']} and {h['target']} already both point at {middle}")
    return "; ".join(parts[:-1]) + ("; and " if len(parts) > 1 else "") + parts[-1] if parts else "its name and type"


def home_details() -> dict[str, str]:
    """{edge id or "table:<name>": HTML of the detail panel}; for the engine's suggestion also "<id>|accepted"."""
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
        check = e(h["check"]) if h.get("evidence") and h.get("check") else "Not checked."
        technical = (f"No naming rule from <code>K0</code> to <code>R4</code> matched <code>{e(h['column'])}</code>, so the plan leaves it "
                     f"unlinked. <code>suggest_relationships</code> ranks it first (score {h['score']}): {e(h['why'])}. The data check "
                     f"counts how many of its values exist in <code>{e(h['target'])}</code>. With the tools, accepting it means passing "
                     f"it as a <code>confirmed</code> entry.")
        for accepted in (False, True):
            decision = ('<div class="choice"><button type="button" class="btn sage small" data-decide="accept" aria-pressed="'
                        + ("true" if accepted else "false") + '">Accept in this demo</button><button type="button" class="btn ghost small" '
                        'data-decide="skip" aria-pressed="' + ("false" if accepted else "true") + '">Leave unlinked</button></div>')
            outcome = ("Accepted in this demo: each order now has a delivery address in the picture. The data check above is separate: "
                       "it counts values, it does not decide what they mean. Nothing changed in Fabric."
                       if accepted else "Left unlinked: <code>ship_to_id</code> stays a plain number. Nothing changed in Fabric.")
            out[hid + ("|accepted" if accepted else "")] = _detail(
                [("Suggestion", sugg + " (from <code>suggest_relationships</code>)"),
                 ("Why", f"No naming rule matched: <code>{e(h['column'])}</code> does not name a table. "
                         f"The engine suggests {e(h['target'])}: {e(_plain_why(h))}."),
                 ("Data check", check),
                 ("Your decision", f"Accept it, and each order gets a delivery address in what you build. Leave it unlinked, and "
                                   f"<code>{e(h['column'])}</code> stays a plain number. {decision}<span class=\"decision-outcome\">{outcome}</span>")],
                technical, f"<code>{e(h['table'])}.{e(h['column'])}</code>",
                "Accepted in this demo" if accepted else "Suggested by the engine · needs your decision")
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


# ------------------------------------------------------------------ the guided example (/demo) -----------------------
# The home page brief of 27 October 2026, round 1, on a page of its own since round n17: one example all the way (an
# order, its customer, its delivery address), in four steps. The suggestion and its count are suggest_relationships' on
# the synthetic rows (demo_suggestions); the visitor's review is a separate act and never turns into a check. Every pane
# is server-rendered, so the page reads without JavaScript; site.js shows one step at a time and draws the decision on
# the graph as well. The pane headings are h2: they follow the page's h1.

GUIDE_STEPS = ("The question", "The suggestion", "Your review", "The result")


def _preview_table(orders: list[dict], accepted: bool) -> str:
    import html
    e = html.escape
    head = "<tr><th scope=\"col\">Order</th><th scope=\"col\" class=\"col-customer\">Customer</th><th scope=\"col\"><code>ship_to_id</code></th><th scope=\"col\">Delivery address</th></tr>"
    body = "".join(
        f"<tr><td>{o['order_id']}</td><td class=\"col-customer\">{o['customer_id']}</td><td>{o['ship_to_id']}</td><td>"
        + (f"address {o['ship_to_id']}" if accepted else '<span class="unconfirmed">not confirmed</span>')
        + "</td></tr>" for o in orders)
    return (f'<figure class="order-preview"><figcaption><span class="pill demo">Illustrative preview · synthetic data</span> '
            f'{"The order view with your decision" if accepted else "The order view today: <strong>Delivery address not confirmed</strong>"}</figcaption>'
            f'<div class="table-wrap"><table class="check"><thead>{head}</thead><tbody>{body}</tbody></table></div></figure>')


def home_guide() -> str:
    """The guided example's HTML: the step buttons, four panes, and the controls; {{…}} placeholders are filled later."""
    import html
    import json as _json
    e = html.escape
    sug = next((h for h in demo_suggestions() if (h["table"], h["column"]) == ("orders", "ship_to_id")), None)
    if sug is None:                                                       # the engine no longer suggests it: no guide
        return ""
    orders = demo_preview()
    first = orders[0]
    tgt, col = sug["target"], sug["column"]
    rel = f"orders.{col} → {tgt}.{' + '.join(sug['target_cols'])}"
    check = sug["check"] if sug.get("evidence") else "Not checked."
    why = _plain_why(sug)
    ru = sug.get("runner_up")
    other = (f" The next candidate, {ru['target']}, holds for only {ru['matched']} of {ru['rows_with_value']}: matching numbers "
             f"alone would not have picked the right table." if ru and ru["matched"] < ru["rows_with_value"] else "")
    confirmed = _json.dumps(sug["confirmed"])
    steps = "".join(f'<li><button type="button" class="guide-step" data-step="{i}" aria-pressed="{"true" if i == 1 else "false"}">'
                    f'<span class="step-n {c}">{i}</span><span>{e(t)}</span></button></li>'
                    for i, (t, c) in enumerate(zip(GUIDE_STEPS, ("coral", "lav", "sage", "mustard")), 1))
    pane1 = (f'<section class="guide-pane" data-pane="1" aria-labelledby="guide-h1"><h2 id="guide-h1">An order view needs each order’s delivery address</h2>'
             f'<p>Order {first["order_id"]} has customer {first["customer_id"]} and a <code>{e(col)}</code> of {first["ship_to_id"]}. The customer is '
             f'clear: <code>customer_id</code> is named after the customers table, so the plan links it. <code>{e(col)}</code> names no table, '
             f'so no naming rule links it, and the delivery address is not confirmed.</p>{_preview_table(orders, False)}</section>')
    pane2 = (f'<section class="guide-pane" data-pane="2" aria-labelledby="guide-h2"><h2 id="guide-h2">The engine suggests a table and counts the values</h2>'
             f'<dl class="detail-list"><div><dt>Suggestion</dt><dd><code>{e(rel)}</code>, from <code>suggest_relationships</code></dd></div>'
             f'<div><dt>Why</dt><dd>{e(why[:1].upper() + why[1:])}.</dd></div>'
             f'<div><dt>Data check</dt><dd>{e(check)}{e(other)}</dd></div>'
             f'<div><dt>What it does not say</dt><dd>A check counts values; it does not say what the column means. Only someone who knows '
             f'the business can say that <code>{e(col)}</code> is where an order is delivered.</dd></div></dl>'
             f'<details class="tech"><summary>Technical details</summary><p><code>suggest_relationships</code> ranks the columns no rule '
             f'links by name, type and triangles in the graph (score {sug["score"]}), then counts how many of their values exist in the '
             f'target key, on the synthetic rows of this demo. In the tools: <code>{e(confirmed)}</code> as a <code>confirmed</code> entry.</p></details></section>')
    pane3 = (f'<section class="guide-pane" data-pane="3" aria-labelledby="guide-h3"><h2 id="guide-h3">Does <code>{e(col)}</code> mean the address each order is delivered to?</h2>'
             f'<p>This is your decision, not the engine’s. Your answer applies to this demo only. Nothing changes in Fabric.</p>'
             f'<div class="choice"><button type="button" class="btn sage small" data-guide-decide="accept" aria-pressed="false">Yes, it is the delivery address</button>'
             f'<button type="button" class="btn ghost small" data-guide-decide="open" aria-pressed="true">Leave it open</button></div>'
             f'<p class="muted tiny">With the tools you pass the relationship as <code>confirmed</code>, and the next plan, data dictionary or API carries it.</p></section>')

    def card(variant: str) -> str:
        accepted = variant == "accepted"
        decision = (f"You accepted, in this demo, that <code>{e(col)}</code> is each order’s delivery address." if accepted else
                    f"You left it open. <span class=\"unconfirmed\">Delivery address not confirmed</span>")
        still = ("The check counts values in this sample at one moment; new rows can change it, and it does not ask whether the "
                 "address belongs to the order’s customer." if accepted else
                 f"What <code>{e(col)}</code> means. The check shows the values match; the meaning still needs someone who knows the business.")
        summary = (f"{{{{PRODUCT}}}} demo with synthetic data (schema shop).\nReviewed: {rel}, suggested by suggest_relationships.\n"
                   f"Data check: {check}\nDecision: " + (f"accepted in the demo as the delivery address." if accepted else "left open.")
                   + "\nStill open: " + ("the check is a count in this sample; the address's customer was not compared."
                                         if accepted else f"what {col} means.") + "\nNothing was changed in Fabric.")
        return (f'<div class="result-card" data-variant="{variant}"{" hidden" if accepted else ""}>'
                f'<p class="detail-head"><span class="detail-status">Demo with synthetic data</span>Your example, in short</p>'
                f'<dl class="detail-list"><div><dt>You reviewed</dt><dd><code>{e(rel)}</code>, suggested by <code>suggest_relationships</code></dd></div>'
                f'<div><dt>The data shows</dt><dd>{e(check)}</dd></div>'
                f'<div><dt>Your decision</dt><dd>{decision}</dd></div>'
                f'<div><dt>Still open</dt><dd>{still}</dd></div>'
                f'<div><dt>Next</dt><dd><ul class="next-list"><li>Document it: <code>data_dictionary</code> with the relationship in '
                f'<code>confirmed</code>. Status: {{{{STATUS_DATA_DICTIONARY}}}}.</li><li>Prepare a report: <code>semantic_model_draft</code>, a Power BI '
                f'model in TMDL. Status: {{{{STATUS_SEMANTIC_MODEL_DRAFT}}}}.</li><li>Prepare an app: <code>create_backend</code> with the same entry. '
                f'{{{{CREATE_API_STATUS}}}} (<a href="/docs#test-status">test status</a>).</li></ul></dd></div></dl>'
                f'{_preview_table(orders, accepted)}'
                f'<pre class="guide-summary" id="guide-summary-{variant}">{e(summary)}</pre>'
                f'<button type="button" class="btn ghost small" data-copy="#guide-summary-{variant}">Copy the summary</button>'
                f'</div><!-- /card -->')
    pane4 = (f'<section class="guide-pane" data-pane="4" aria-labelledby="guide-h4"><h2 id="guide-h4">What you can explain now</h2>'
             f'{card("open")}{card("accepted")}</section>')
    nav = ('<div class="guide-nav"><button type="button" class="btn ghost small" data-guide="back">Back</button>'
           '<button type="button" class="btn primary small" data-guide="next">Next</button>'
           '<button type="button" class="btn ghost small" data-guide="reset">Start over</button>'
           '<p class="muted tiny guide-status" aria-live="polite"></p></div>')
    return (f'<div class="guide" id="guide" data-edge="{e(_edge_id("orders", [col], tgt))}"><ol class="guide-steps">{steps}</ol>'
            f'<div class="guide-panes">{pane1}{pane2}{pane3}{pane4}</div>{nav}</div><!-- /guide -->')


# ------------------------------------------------------------------ what you can build (/explore) --------------------
# The last section of /explore (round n31): four cards, each the output of an engine function run on the synthetic shop
# plan when the page is built (join_path's safest path summed over the seed rows, semantic_model.draft and the
# header-amount check, rayfin_files, app_starter.starter on the API definition the plan makes). The status of each card
# is tool_status.label() of the tool it shows; nothing in a card is typed by hand.

def _sum_chart(p, db) -> dict | None:
    """A sum measure of semantic_model_draft, summed per name of the table furthest along join_path's safest path
    whose every step is many-to-one (a sum over such a path counts each row once)."""
    from . import semantic_model
    from .demo_app import _label_column
    from .paths import join_path
    measures = semantic_model.draft(p, {"item_name": "shop"}, "shop_model")["summary"]["measures"]
    m = next((x for x in measures if x["expression"].startswith("SUM(")), None)
    if m is None:
        return None
    source, column = m["table"], m["expression"].split("[", 1)[1].rstrip("])")
    validation = demo_validation()
    best = None
    for t in sorted(p.schema, key=lambda x: x.name):
        label = _label_column(t)
        if t.name == source or not label:
            continue
        safest = join_path(p, source, t.name, validation=validation).get("safest")
        if safest and all(s["direction"] == "many-to-one" for s in safest["steps"]) and (best is None or safest["hops"] > best[0]["hops"]):
            best = (safest, t.name, label)
    if best is None:
        return None
    safest, target, label = best
    h = safest["hops"]
    sql = (f"SELECT t{h}.[{label}] AS label, SUM(t0.[{column}]) AS total" + safest["sql"][safest["sql"].index("\nFROM "):]
           + f"\nGROUP BY t{h}.[{label}]\nORDER BY total DESC, label")
    bars = [{"label": r["label"], "value": r["total"]} for r in db(sql)]
    return {"tool": "join_path", "measure": m["name"], "expression": m["expression"], "source": source, "column": column,
            "target": target, "label": label, "path": safest["tables"], "steps": safest["steps"], "why": safest["why"],
            "question": f"{m['name']} ({source}.{column}) per {target}.{label}, along {' → '.join(safest['tables'])}",
            "sql": sql, "bars": bars}


def _model_preview(p) -> dict:
    import re
    from . import amounts, semantic_model
    d = semantic_model.draft(p, {"item_name": "shop"}, "shop_model")
    rels = []
    for block in d["parts"]["definition/relationships.tmdl"].split("relationship ")[1:]:
        f, t = re.search(r"fromColumn: (\S+)", block), re.search(r"toColumn: (\S+)", block)
        both = "crossFilteringBehavior: bothDirections" in block
        rels.append({"from": f.group(1), "to": t.group(1), "active": "isActive: false" not in block,
                     "filter": "both directions" if both else f"{t.group(1).split('.')[0]} filters {f.group(1).split('.')[0]}"})
    s = d["summary"]
    demo = amounts.demo()
    return {"tool": "semantic_model_draft", "relationships": rels, "measures": s["measures"], "inactive": s["inactive"],
            "keyless": s["keyless"], "header_amounts": s["header_amounts"], "amount_check": amounts.check(p)["summary"],
            "amount_rule": amounts.RULE, "amount_demo": {"header": demo["finding"]["header"], "line": demo["finding"]["line"],
                                                       "column": demo["finding"]["amount_columns"][0], "before": demo["before"],
                                                       "after": demo["after"], "lines_total": demo["lines_total"]},
            "files": sorted(d["parts"])}


def _rayfin_preview(p) -> dict:
    import re
    from .rayfin import rayfin_files
    files = rayfin_files(p)
    entities = []
    for path, src in files.items():
        m = re.search(r"export class (\w+) extends Source\(\{ schema: '([^']*)', table: '([^']*)'(?:, primaryKey: \[([^\]]*)\])?", src)
        if not m:
            continue
        links = [{"kind": k, "to": to} for k, to in re.findall(r"@(one|many)\(\(\) => (\w+)", src)]
        entities.append({"class": m.group(1), "table": m.group(3), "key": [x.strip(" '") for x in (m.group(4) or "").split(",") if x.strip()],
                         "links": links, "file": path})
    return {"tool": "rayfin_connector", "entities": entities, "files": list(files)}


def _app_preview(p) -> dict:
    from . import app_starter
    from .deploy import endpoint_url
    from .graphql import decode, definition
    from .server import describe_definition
    ws, api = "{workspace-id}", "{api-id}"                                     # placeholders: the demo has no workspace
    desc = describe_definition(decode(definition(p, "shop_api", ws, "{endpoint-id}", "SqlAnalyticsEndpoint")))
    s = app_starter.starter(desc, endpoint_url(ws, api), "shop_api", ws)
    return {"tool": "app_starter", "prompt": s["lovable_prompt"], "query": s["queries"][0], "queries": len(s["queries"])}


@lru_cache(maxsize=1)
def build_cards() -> dict:
    """The four cards of "What you can build automatically from this plan", computed from the demo plan and the seed rows."""
    p = plan(schema("shop"), keys=DEMO_KEYS)
    return {"chart": _sum_chart(p, _demo_db()), "model": _model_preview(p), "rayfin": _rayfin_preview(p), "app": _app_preview(p)}
