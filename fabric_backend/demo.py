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


def _fix_result(p, db) -> dict:
    """n161: the chat's "Fix data issues": what validate_plan(fixes=true) answers on the synthetic rows, computed when the
    plan JSON is built. The same counts (evidence.validate with validate_plan's ceiling of 200 items) and the same
    proposal (fix_plan.propose with the two extra read-only counts); per finding its fix, its counts before and after,
    whether it is mechanical or a business decision, and the decision's question with its options. Nothing is applied:
    the demo shows the proposal only."""
    from . import evidence, evidence_report, fix_plan
    v = evidence.validate(p, db, max_items=200)
    pr = fix_plan.propose(p, v, db)
    rep = evidence_report.report(p, v, generated_at="-")              # the table a repeated amount is joined with
    joined = {fix_plan._id(r["fix"]): r["fix"].get("line", "") for r in rep["checklist"]}
    keys = v["keys"]
    unique = [k for k in keys if k.get("nulls") == 0 and k.get("distinct") == k.get("rows")]
    held = [r for r in v["relationships"] if r.get("orphans") == 0]
    return {"tool": "validate_plan", "option": "fixes=true", "status": pr["status"], "summary": v["summary"],
            "keys": len(keys), "keys_unique": len(unique), "relationships": len(v["relationships"]), "hold": len(held),
            "counts": pr["counts"],
            "findings": [{"id": e["id"], "finding": e["finding"], "type": e["type"], "table": e["table"], "column": e["column"],
                          "joined_with": joined.get(e["id"], ""), "what_is_wrong": e["what_is_wrong"], "proposed_fix": e["proposed_fix"],
                          "before": e["counts"].get("before", {}), "expected_after": e["counts"].get("expected_after", {}),
                          "sums": e["counts"].get("sums", {}),
                          "questions": [{"ask": q["ask"], "options": q.get("options", [])} for q in e["questions"]]}
                         for e in pr["fixes"]]}


def _yaml_block(text: str, table: str, column: str) -> list[str]:
    """The lines of one column of one table in a sources file (dbt.schema_yml): its `- name:` line and everything indented
    under it, up to the next column or table."""
    lines, out, in_table, indent = text.splitlines(), [], False, None
    for line in lines:
        stripped, lead = line.lstrip(), len(line) - len(line.lstrip())
        if indent is not None:
            if stripped and lead <= indent:
                break
            out.append(line)
        elif stripped == f"- name: {table}":
            in_table, table_indent = True, lead
        elif in_table and stripped.startswith("- name: ") and lead <= table_indent:
            in_table = False
        elif in_table and stripped == f"- name: {column}":
            indent = lead
            out.append(line)
    pad = min((len(x) - len(x.lstrip()) for x in out if x.strip()), default=0)
    return [x[pad:] for x in out]


def _dbt_result(p, db) -> dict:
    """n161: the chat's "Draft a dbt project": what dbt_schema(project=true, check_rows=true) writes for the demo plan,
    computed when the plan JSON is built. The file tree, the first lines of one staging model (its select, without the
    comment header) and the tests the sources file has for one relationship: the first single-column relationship of the
    plan, and the staging model of its source table. Files only: nothing runs."""
    from . import dbt, dbt_flow, evidence
    v = evidence.validate(p, db)                             # check_rows: the marts join over relationships counted many-to-one
    out = dbt.project(p, "shop", p.schema.schema or "shop", "shop", v)
    files = out["files"]
    rel = next(r for r in p.relationships if len(r.source_cols) == 1 and len(r.target_cols) == 1)
    sources = dbt.sources_path("shop")
    stg = next(k for k in files if k.startswith("models/staging/") and k.endswith(f"__{rel.source}.sql"))
    body = [x for x in files[stg].splitlines() if x.strip() and not x.lstrip().startswith("--")]
    head = 12
    return {"tool": "dbt_schema", "option": "project=true", "project": out["project"], "files": sorted(files),
            "staging": len(out["models"]["staging"]), "marts": len(out["models"]["marts"]),
            "adapter": f'{out["adapter"]["package"]} {out["adapter"]["version"]}',
            "model": {"file": stg, "lines": body[:head], "more": max(0, len(body) - head)},
            "relationship": {"source": rel.source, "column": rel.source_cols[0], "target": rel.target, "field": rel.target_cols[0],
                             "file": sources, "lines": _yaml_block(files[sources], rel.source, rel.source_cols[0])},
            "not_templated": [{"table": x["table"], "part": x["part"], "why": x["why"]} for x in out["not_templated"]],
            "created": out["created"],
            "flow": dbt_flow.flow(files, with_code=True)}                   # n177: sources -> staging -> marts -> model


def _drafts(p) -> dict:
    """What the engine's drafts say about one plan, in counts: ontology_draft, semantic_model_draft, domain_draft, and
    validate_plan on the synthetic rows."""
    from . import domains, evidence, ontology, semantic_model
    o = ontology.summary(p)
    m = semantic_model.draft(p, {"item_name": "shop"}, "shop_model")["summary"]
    model = ontology._model(p, None)                      # the entity types, in plan order, with their key (None: keyless)
    names = {t.name for t, *_ in model}
    single = [r for r in p.relationships if r.source in names and r.target in names and len(r.source_cols) == 1 and len(r.target_cols) == 1]
    skipped = {(r["source"], tuple(r["columns"]), r["target"]) for r in m["not_expressible"]}
    off = {(r["source"], tuple(r["columns"]), r["target"]) for r in m["inactive"]}
    model_rels = [{"source": r.source, "columns": r.source_cols, "target": r.target,
                   "active": (r.source, tuple(r.source_cols), r.target) not in off}
                  for r in p.relationships if (r.source, tuple(r.source_cols), r.target) not in skipped]
    d = domains.propose_plan(p)
    v = evidence.validate(p, _demo_db())
    held = [r for r in v["relationships"] if r.get("orphans") == 0]
    return {
        "relationships": len(p.relationships),
        "validation": {"relationships": len(v["relationships"]), "hold": len(held), "summary": v["summary"]},
        "ontology": {"tool": "ontology_draft", "entity_types": o["entity_types"], "with_key": o["with_key"],
                     "relationship_types": o["relationship_types"],
                     # n93: what the chat's picture draws: each entity type with its table and whether it has a key, and
                     # each relationship type between two entity types
                     "entities": [{"name": ontology.entity_name(t.name), "table": t.name, "key": bool(key)} for t, key, *_ in model],
                     "links": [{"source": r.source, "target": r.target} for r in single]},
        "semantic_model": {"tool": "semantic_model_draft", "tables": m["tables"], "active": m["relationships_active"],
                           "table_names": list(m["roles"]), "relationships": model_rels,
                           "inactive": [{"source": r["source"], "columns": r["columns"], "target": r["target"]} for r in m["inactive"]],
                           "measures": len(m["measures"]), "date_table": (m.get("date_table") or {}).get("name", "")},
        "domains": {"tool": "domain_draft", "domains": [{"name": x["name"], "tables": x["tables"]} for x in d["domains"]],
                    "interfaces": [{"source": i["source"], "source_cols": i["source_cols"], "target": i["target"]} for i in d["interfaces"]],
                    "unassigned": [u["table"] for u in d["unassigned"]]},
        "fixes": _fix_result(p, _demo_db()),                                                      # n161
        "dbt": _dbt_result(p, _demo_db()),                                                        # n161
    }


@lru_cache(maxsize=1)
def demo_drafts() -> dict:
    """The start page's chat demo (n92): the drafts' counts for the demo plan as it is (`as_is`) and with the one
    suggestion confirmed (`with_suggestion`, the page-local equivalent of confirmed=[...]). Computed, not typed: the chat
    reads its numbers from /demo/plan.json, and tests/test_chat_demo.py says when they change."""
    sug = demo_suggestions()
    confirmed = [h["confirmed"] for h in sug if h["table"] == "orders" and h["column"] == "ship_to_id"]
    return {"as_is": _drafts(plan(schema("shop"), keys=DEMO_KEYS)),
            "with_suggestion": _drafts(plan(schema("shop"), keys=DEMO_KEYS, confirmed=confirmed))}


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
        "drafts": demo_drafts(),
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


# ------------------------------------------------------------------ what you can build (/use-cases) ------------------
# The cards "What you can build automatically from a plan" (round n31, on /use-cases since n55): four cards, each the output of an engine function run on the synthetic shop
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
