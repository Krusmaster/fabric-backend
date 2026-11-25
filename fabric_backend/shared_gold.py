"""ON2 (25 November 2026, builds on ON1; docs/SMOOTH/COMBINE-SOURCES.md section 8): the conformed gold the shared
ontology binds to, built by a pipeline, and how Krusgraph sees that it is there.

ON1 drafts one shared Fabric IQ ontology over SAP and Dynamics 365 (shared_ontology.draft): Customer bound to
`gold.dim_customer`, Product to `gold.dim_product`, and each transaction table that points at a customer re-keyed to
`customer_key` in `gold.fact_<source>_<product>`. Every other entity type binds to its own source table in the product
lakehouse, which is already there (the source's schema). This module turns the draft's gold SQL into something that
runs and can be checked:

- **The notebook** (`notebook_source`): one PySpark notebook in the product lakehouse. It runs the gold SQL of the draft
  in order (each `xref_*`, then its `dim_*`, then the facts), all of it combine.gold_sql with `apart`: an ambiguous row
  (one that is in more than one matching pair, as combine.count counts it) is never merged and keeps its own key with
  `ambiguous` true; only one-to-one pairs share a key. Facts are Delta tables, so the SQL analytics endpoint and the
  ontology's OneLake binding both see them. Before it creates anything it stops when the gold schema is a source schema
  or when a table of that name exists and was not created by this notebook (the table property `krusgraph.gold`, as
  gold.py marks its views). Source tables are only read.
- **The check** (`checks`), the notebook's last cell: per accepted match, the rows of the xref counted as the match was
  counted (matched, ambiguous, only in each source) and compared with the counts the person accepted, and three
  invariants that fail the run: no source row has two keys, no ambiguous row was merged, each key is one row of the
  dimension. Counts that changed since the person accepted are printed, not failed: the rows may have moved on, and
  the rules still keep every ambiguous row apart.
- **The pipeline** (`pipeline_content`): one Notebook activity, the same activity pipeline.py writes, no schedule.
- **Is the gold there?** (`missing`): the product lakehouse's gold schema as the SQL analytics endpoint lists it,
  against every table and column the shared ontology binds in gold. `create_ontology` creates the shared ontology
  only when nothing is missing; otherwise it answers `not_yet` and names the pipeline.

Counts, names and SQL only; no row value. Unit-tested on the synthetic SAP + Dynamics 365 pair; not run against Fabric.
"""
from __future__ import annotations

import json

from .notebook import fabric_source, notebook_metadata
from .pipeline import ZERO_WORKSPACE, _activity
from .schema import Schema

GOLD = "gold"
OWNER_PROPERTY = "krusgraph.gold"
STEP = "Shared gold"


def bound(model: dict) -> dict[str, list[str]]:
    """{gold table: [the columns the shared ontology binds]} for every entity type bound in gold (the shared
    dimensions and the re-keyed facts), in the draft's order."""
    return {e["binding"]["table"]: [p["name"] for p in e["properties"]]
            for e in model["entities"] if e["binding"].get("built_by") == "gold_sql"}


def statements(model: dict) -> list[tuple[str, str]]:
    """[(table, Spark SQL)] in the order they must run: each xref before its dimension, the dimension before the facts
    that read the xref (the draft's own order)."""
    return list(model["gold_sql"].items())


def _concept(e: dict) -> str:
    return e["key"][: -len("_key")]


def checks(model: dict, gold: str = GOLD) -> list[dict]:
    """Per shared entity type: the counts SQL, the invariants (label, SQL that counts violations) and the counts the
    person accepted ({matched, ambiguous, only_a, only_b, rows})."""
    out = []
    def q(*p):
        return ".".join(f"`{x}`" for x in p)

    def twice(xref, cols):
        return (f"SELECT COUNT(*) FROM (SELECT {', '.join(cols)} FROM {xref} WHERE {cols[-1]} IS NOT NULL "
                f"GROUP BY {', '.join(cols)} HAVING COUNT(*) > 1) AS d")
    for e in model["entities"]:
        if not e["shared"]:
            continue
        c = _concept(e)
        xref, dim, key = q(gold, f"xref_{c}"), q(gold, f"dim_{c}"), e["key"]
        master, other = e["sources"][0], e["sources"][1]
        mx = [f"`{master['source']}_{k}`" for k in master["key"]]
        ox = [f"`{other['source']}_{k}`" for k in other["key"]]
        k = e["match"]["counts"]
        counts_sql = (f"SELECT COUNT(*) AS rows_, "
                      f"SUM(CASE WHEN only_in IS NULL THEN 1 ELSE 0 END) AS matched, "
                      f"SUM(CASE WHEN only_in = '{other['source']}' AND ambiguous THEN 1 ELSE 0 END) AS ambiguous, "
                      f"SUM(CASE WHEN only_in = '{other['source']}' AND NOT ambiguous THEN 1 ELSE 0 END) AS only_a, "
                      f"SUM(CASE WHEN only_in = '{master['source']}' AND NOT ambiguous THEN 1 ELSE 0 END) AS only_b "
                      f"FROM {xref}")
        out.append({
            "entity": e["name"], "concept": c, "match": e["match"]["id"], "xref": f"{gold}.xref_{c}", "dim": f"{gold}.dim_{c}",
            "sources": {"master": master["source"], "other": other["source"]},
            "counts_sql": counts_sql,
            "invariants": [
                [f"a {master['table']} row has more than one {key}", twice(xref, mx)],
                [f"a {other['table']} row has more than one {key}", twice(xref, ox)],
                ["an ambiguous row was merged", f"SELECT COUNT(*) FROM {xref} WHERE only_in IS NULL AND ambiguous"],
                [f"a {key} is more than one row of dim_{c}", f"SELECT COUNT(*) - COUNT(DISTINCT {key}) FROM {dim}"]],
            "accepted": {"matched": k["matched"], "ambiguous": k["ambiguous"], "only_a": k["only_a"], "only_b": k["only_b"],
                         "rows_": k["b_rows"] + k["a_rows"] - k["matched"]}})
    return out


CODE = r'''
def q(*parts):
    return ".".join("`" + str(p).replace("`", "``") + "`" for p in parts if p)


def is_ours_or_absent(name):
    if not spark.catalog.tableExists(name):
        return True
    props = {r[0]: r[1] for r in spark.sql(f"SHOW TBLPROPERTIES {name}").collect()}
    return props.get(OWNER_PROPERTY) == OWNER


# Guards, before anything is created: the gold schema is no source schema, and no table of these names exists that this
# notebook did not create. Source tables are only read.
if GOLD_SCHEMA.lower() in {s.lower() for s in SOURCE_SCHEMAS}:
    raise ValueError(f"{GOLD_SCHEMA} is a source schema; nothing was created.")
for _name, _sql in STATEMENTS:
    if not is_ours_or_absent(q(GOLD_SCHEMA, _name)):
        raise ValueError(f"{GOLD_SCHEMA}.{_name} exists and was not created by this notebook (for {OWNER}); nothing was created.")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {q(GOLD_SCHEMA)}")
for _name, _sql in STATEMENTS:
    spark.sql(_sql)
    spark.sql(f"ALTER TABLE {q(GOLD_SCHEMA, _name)} SET TBLPROPERTIES ('{OWNER_PROPERTY}' = '{OWNER}')")
    print(f"built {GOLD_SCHEMA}.{_name}")
'''

CHECK = r'''
import json

problems = []
for c in CHECKS:
    got = {k: int(v or 0) for k, v in spark.sql(c["counts_sql"]).collect()[0].asDict().items()}
    for label, sql in c["invariants"]:
        n = int(spark.sql(sql).collect()[0][0] or 0)
        if n:
            problems.append(f"{c['entity']}: {label} ({n})")
    changed = {k: {"accepted": v, "now": got.get(k)} for k, v in c["accepted"].items() if got.get(k) != v}
    print(json.dumps({"entity": c["entity"], "match": c["match"], "counts": got,
                      "changed_since_accepted": changed or None}))
if problems:
    raise ValueError("The shared gold breaks a rule: " + "; ".join(problems))
'''


def notebook_source(model: dict, *, label: str, workspace_id: str = "", item_id: str = "", item_name: str = "",
                    owner: str = "", gold: str = GOLD) -> str:
    """notebook-content.py (fabricGitSource) of the shared gold notebook, default lakehouse the product lakehouse."""
    st = statements(model)
    if not st:
        raise ValueError("no accepted match: there is no shared gold to build")
    sources = sorted({s["source"] for e in model["entities"] for s in e["sources"]})
    shared = [e for e in model["entities"] if e["shared"]]
    said = "; ".join(f"{e['name']} ({e['match']['id']}, {e['match']['rule']}): {e['match']['line']}" for e in shared)
    md = (f"# Shared gold for {label}\n\n"
          f"Generated by Krusgraph from the plan and the matches you accepted: {said}\n\n"
          f"Builds {', '.join(f'{gold}.{n}' for n, _ in st)} as Delta tables in this lakehouse. An ambiguous row (in more "
          "than one matching pair) is never merged: it keeps its own key and `ambiguous` is true. Only one-to-one pairs "
          "share a key. Source tables are only read; the notebook stops before touching a table it did not create. The "
          "last cell counts each match again and fails the run when a source row has two keys or an ambiguous row was "
          "merged.")
    consts = "\n".join([
        f"GOLD_SCHEMA = {json.dumps(gold)}",
        f"SOURCE_SCHEMAS = {json.dumps(sources)}",
        f"OWNER_PROPERTY = {json.dumps(OWNER_PROPERTY)}",
        f"OWNER = {json.dumps(owner or f'{item_id}/shared')}",
        "STATEMENTS = " + json.dumps([[n, s] for n, s in st], indent=1),
    ])
    cells = [("markdown", md), ("code", consts + "\n" + CODE),
             ("code", "CHECKS = " + json.dumps(checks(model, gold), indent=1) + "\n" + CHECK)]
    meta = notebook_metadata(workspace_id, item_id, item_name) if item_id else notebook_metadata()
    return fabric_source(cells, meta)


def notebook_cells_data(source: str) -> dict:
    """The constants a notebook_source text carries (STATEMENTS, CHECKS, GOLD_SCHEMA, ...), read back without running
    Spark: for the tests and for verify_build."""
    from .notebook import parse
    out: dict = {}
    for kind, text in parse(source):
        if kind != "code":
            continue
        for name in ("GOLD_SCHEMA", "SOURCE_SCHEMAS", "OWNER", "STATEMENTS", "CHECKS"):
            start = text.find(f"{name} = ")
            if start < 0 or name in out:
                continue
            body = text[start + len(name) + 3:]
            out[name] = json.JSONDecoder().raw_decode(body)[0]
    return out


def pipeline_content(notebook: str, label: str, ids: dict | None = None, workspace_id: str = ZERO_WORKSPACE) -> dict:
    """pipeline-content.json: one Notebook activity (pipeline.py's), no schedule."""
    from .git_export import logical_id
    nid = ids[notebook] if ids is not None else logical_id("Notebook", notebook)
    return {"properties": {
        "description": (f"Krusgraph pipeline for {label}: the shared gold ({notebook}), from the matches the person accepted; "
                        "its last cell fails the run when a rule is broken. No schedule."),
        "activities": [_activity(STEP, nid, workspace_id, None)]}}


def missing(gold_schema: Schema | None, model: dict) -> list[str]:
    """What the shared ontology binds in gold that the product lakehouse does not have: 'gold.dim_product' (no table)
    or 'gold.dim_customer.ambiguous' (no column). [] when the gold is built."""
    have: dict[str, set[str]] = {}
    for t in (gold_schema or Schema(schema=GOLD)):
        have[t.name.split(".")[-1].lower()] = {c.name.lower() for c in t.columns}
    out = []
    for table, cols in bound(model).items():
        got = have.get(table.lower())
        if got is None:
            out.append(f"{GOLD}.{table}")
            continue
        out += [f"{GOLD}.{table}.{c}" for c in cols if c.lower() not in got]
    return out
