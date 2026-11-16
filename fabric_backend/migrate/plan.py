"""From the source's metadata to a migration plan for Microsoft Fabric (round MG1).

For every table and view of the exported schema: the Fabric target (a Lakehouse Delta table or a Warehouse table),
how it can land (what Microsoft's documentation says Fabric offers for that kind of object today, with the page and its
date), the columns whose type does not carry over plainly, and for a view its SQL against Fabric T-SQL (sqlrules.py).
Then the model: the keys and links the source declares become candidates with the rule "Snowflake metadata" or
"Databricks metadata" (provenance "declared by metadata (...)"), the plan is made with them first (infer.plan, the same
way csn.py does for SAP CSN), and validate_plan / the before-and-after comparison count them in the rows.

Every rule below is a fixed lookup; nothing is inferred by a model. What a page says is quoted short and dated; where
no page was read the plan says "not read" instead of filling in.
"""
from __future__ import annotations

import re

from . import metadata as md
from . import sqlrules

READ_ON = "2026-11-16"
L = "https://learn.microsoft.com/en-us/fabric"
DOCS = {
    "mirror_snowflake": {"url": f"{L}/mirroring/snowflake", "page_date": "2025-09-16 (updated 2026-10-23)",
                         "says": "Managed tables: Yes; Iceberg tables: Yes (storage connection); Views and Materialized Views: Yes, "
                                 "'Supported with syncs every 12 hours'; External, Transient, Temporary, Dynamic tables: No. "
                                 "Permissions: CREATE STREAM, SELECT table, SHOW tables, DESCRIBE tables"},
    "mirror_snowflake_limits": {"url": f"{L}/mirroring/snowflake-limitations", "page_date": "2026-02-26 (updated 2026-10-23)",
                                "says": "'The maximum number of tables that can be mirrored into Fabric is 1,000 tables'; 'Mirror all data' takes the "
                                        "first 1,000 sorted by schema then table name; any DDL change triggers a reseed; Fabric doesn't replicate "
                                        "Snowflake RLS and CLS policies"},
    "mirror_databricks": {"url": f"{L}/mirroring/azure-databricks", "page_date": "2026-10-24 (updated 2026-10-28)",
                          "says": "'there is no data movement or data replication. Only the Azure Databricks catalog structure is mirrored to "
                                  "Fabric and the underlying catalog data is accessed through shortcuts'; 'Views and metric views don't appear'; "
                                  "'External tables that don't support Delta format will not be displayed'"},
    "mirror_databricks_limits": {"url": f"{L}/mirroring/azure-databricks-limitations", "page_date": "2025-12-19 (updated 2026-10-28)",
                                 "says": "Not supported: 'Tables with RLS/CLM policies', 'Lakehouse federated tables', 'Delta sharing tables', 'Views'"},
    "copy_job": {"url": f"{L}/data-factory/copy-job-connectors", "page_date": "2026-11-09",
                 "says": "Snowflake: source and destination, full load, watermark incremental, CDC source. Azure Databricks: source and "
                         "destination, full load, watermark incremental; not in the CDC table. Lakehouse table and Warehouse: automatic table creation"},
    "decision_guide": {"url": f"{L}/fundamentals/decision-guide-lakehouse-warehouse", "page_date": "2026-09-14",
                       "says": "Spark: Lakehouse; T-SQL: Warehouse. Multi-table transactions: Warehouse. 'Unstructured and structured data, or "
                               "you're not sure: Use Lakehouse'; 'Structured data only: Use Warehouse'"},
    "data_types": {"url": f"{L}/data-warehouse/data-types", "page_date": "2026-06-11",
                   "says": "Warehouse tables: json -> 'Use varchar'; datetimeoffset -> 'Use datetime2'; geography/geometry -> lat/long pair, "
                           "varbinary or varchar WKT; SQL analytics endpoint: 'Types that aren't listed in the table aren't represented as the "
                           "table columns' (listed: BIGINT, BOOLEAN, INT, TINYINT/SMALLINT, DOUBLE, FLOAT, DATE, TIMESTAMP, CHAR, VARCHAR, STRING, "
                           "BINARY, DECIMAL)"},
    "tsql": {"url": sqlrules.TSQL_PAGE, "page_date": "2026-09-16", "says": "QUALIFY, GROUP BY ALL and MERGE supported; recursive queries not supported"},
}

_SEMI = ("VARIANT", "OBJECT", "ARRAY", "MAP", "STRUCT")
_NUMERIC = ("NUMBER", "NUMERIC", "DECIMAL", "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "BYTEINT", "FLOAT", "DOUBLE", "REAL",
            "FLOAT4", "FLOAT8", "LONG", "SHORT", "BYTE")
MIRROR_TABLE_LIMIT = 1000


def _base(t: str) -> str:
    return re.split(r"[\s(<]", (t or "").strip().upper(), maxsplit=1)[0]


def column_findings(source: str, t: md.SrcTable) -> list[dict]:
    """The columns whose type does not land plainly, with what the data types page says."""
    out = []
    for c in t.columns:
        b = _base(c.data_type)
        why = None
        if b in _SEMI:
            why = (f"{b}: no persisted Warehouse type (the page: json -> varchar); on a Lakehouse SQL analytics endpoint a type not in "
                   "the mapping table is not represented as a column. Keep it in a Lakehouse and read it from Spark, or land it as JSON text")
        elif b in ("TIMESTAMP_TZ", "TIMESTAMP_LTZ") or (b == "TIMESTAMP" and "TIME ZONE" in c.data_type.upper()):
            why = f"{b}: Warehouse tables have no datetimeoffset ('Use datetime2'): the offset is not kept; store it in its own column if it matters"
        elif b == "TIMESTAMP_NTZ" and source == "databricks":
            why = "TIMESTAMP_NTZ is not in the SQL analytics endpoint's mapping table (TIMESTAMP is): the column would not be represented there"
        elif b in ("GEOGRAPHY", "GEOMETRY"):
            why = f"{b}: the page proposes a (latitude, longitude) pair, varbinary with well-known binary, or varchar with well-known text"
        elif b == "INTERVAL":
            why = "INTERVAL: not in the mapping table; not represented on the SQL analytics endpoint"
        if why:
            out.append({"column": c.name, "type": c.data_type, "short": b, "finding": why, "source": DOCS["data_types"]["url"]})
    return out


def landing(source: str, t: md.SrcTable) -> dict:
    """How this object can land in Fabric, from the pages in DOCS: {how, mirroring, alternative, doc, note}."""
    f = set(t.flags)
    if source == "snowflake":
        doc = "mirror_snowflake"
        if t.kind in ("view", "materialized view"):
            return {"how": "rebuild as a Fabric view from the translated SQL", "mirroring": "supported, 'syncs every 12 hours'",
                    "alternative": "mirror its rows during the parallel run", "doc": doc,
                    "note": "the view's logic must exist in Fabric after the move; mirroring carries its rows, not its definition"}
        blocked = sorted(f & {"transient", "temporary", "dynamic", "external"})
        if blocked:
            return {"how": "Copy job (Snowflake source: full load, watermark incremental, CDC)", "mirroring": f"not supported ({', '.join(blocked)} table)",
                    "alternative": "recreate where it is produced", "doc": "copy_job",
                    "note": f"the mirroring page lists {', '.join(blocked)} tables as not supported"}
        if "iceberg" in f:
            return {"how": "Mirroring (Snowflake), Iceberg table through a storage connection", "mirroring": "supported with a storage connection",
                    "alternative": "Copy job", "doc": doc, "note": "only Iceberg tables reachable through the same storage connection mirror together"}
        return {"how": "Mirroring (Snowflake)", "mirroring": "supported (managed table)",
                "alternative": "Copy job (full load, watermark incremental, CDC)", "doc": doc,
                "note": "mirroring replicates the rows into OneLake as Delta; Snowflake RLS and CLS policies are not replicated"}
    doc = "mirror_databricks"
    if t.kind == "view":
        return {"how": "rebuild as a Fabric view from the translated SQL", "mirroring": "not supported ('Views and metric views don't appear')",
                "alternative": None, "doc": doc, "note": "metric view: rebuild as measures in a semantic model" if "metric view" in f else None}
    if "federated" in f or t.kind == "foreign":
        return {"how": "land from the system it federates (manual)", "mirroring": "not supported (Lakehouse federated tables)",
                "alternative": None, "doc": "mirror_databricks_limits", "note": "the rows live in another system; Krusgraph does not read it"}
    if f & {"row filter", "column mask"}:
        return {"how": "Copy job (Azure Databricks source: full load, watermark incremental)", "mirroring": "not supported (Tables with RLS/CLM policies)",
                "alternative": None, "doc": "mirror_databricks_limits",
                "note": "the row filter or column mask is not carried: design OneLake or model security for it (manual)"}
    if t.format and t.format != "DELTA":
        return {"how": "Copy job (Azure Databricks source: full load, watermark incremental)", "mirroring": f"not shown ({t.format}, not Delta)",
                "alternative": None, "doc": doc, "note": "external tables that are not Delta are not displayed by mirroring"}
    return {"how": "Mirroring (Azure Databricks Unity Catalog) for the parallel run, then Copy job to own the data in Fabric",
            "mirroring": "supported (catalog structure mirrored; data read through shortcuts, no data movement)",
            "alternative": "OneLake shortcut to the Delta folder", "doc": doc,
            "note": "with mirroring alone the data stays in Databricks storage; a Copy job (not CDC for Azure Databricks) moves it"}


def target(t: md.SrcTable, prefer: str) -> dict:
    semi = [c.name for c in t.columns if _base(c.data_type) in _SEMI]
    if t.kind == "view" and semi:
        return {"target": "view on the SQL analytics endpoint (Lakehouse)", "rule": "T1 a view with semi-structured column(s) " +
                ", ".join(semi) + ": its tables are Lakehouse tables", "doc": "decision_guide"}
    if semi:
        return {"target": "Lakehouse Delta table", "rule": "T1 semi-structured column(s) " + ", ".join(semi) +
                ": the decision guide says Lakehouse for structured and unstructured data; Warehouse tables persist no such type",
                "doc": "decision_guide"}
    if t.kind == "view":
        return {"target": "view on the SQL analytics endpoint" if prefer == "lakehouse" else "Warehouse view",
                "rule": f"T3 a view follows the chosen target ({prefer})", "doc": "decision_guide"}
    if prefer == "warehouse":
        return {"target": "Warehouse table", "rule": "T2 the customer chose Warehouse (T-SQL development, multi-table transactions)", "doc": "decision_guide"}
    return {"target": "Lakehouse Delta table", "rule": "T2 the default, Lakehouse (Spark development; the mirrored rows are Delta in OneLake); "
            "pass target=warehouse for T-SQL development or multi-table transactions", "doc": "decision_guide"}


# ------------------------------------------------------------------------------------------------------ the model

def to_schema(m: md.SourceModel):
    """The tables (not the views) as a Krusgraph Schema, in the source's spelling."""
    from ..schema import Schema
    rows = [(m.schema, t.name, c.name, c.data_type.lower(), i + 1) for t in m.tables.values() if t.kind != "view"
            for i, c in enumerate(t.columns)]
    return Schema.from_information_schema(rows, schema=m.schema)


def _find(schema, name: str):
    tables = {t.name.lower(): t for t in schema}
    if name.lower() in tables:
        return tables[name.lower()]
    hits = [t for t in schema if md.norm(t.name) == md.norm(name)]
    return hits[0] if len(hits) == 1 else None


def _cols(table, cols: list[str]) -> list[str] | None:
    have = {c.lower(): c for c in table.column_names}
    norm = {md.norm(c): c for c in table.column_names}
    out = []
    for c in cols:
        x = have.get(str(c).lower()) or norm.get(md.norm(c))
        if x is None:
            return None
        out.append(x)
    return out


def candidates(m: md.SourceModel, schema) -> dict:
    """The declared keys and foreign keys in the schema's spelling: {keys, links, not_applied, matched}."""
    keys, links, not_applied, matched = {}, [], [], {}
    for t in m.tables.values():
        if t.kind == "view":
            continue
        st = _find(schema, t.name)
        if st is None:
            if t.primary_key or t.foreign_keys:
                not_applied.append({"object": t.name, "why": "no table of that name on the side the plan is made for"})
            continue
        matched[t.name] = st.name
        k, how = (t.primary_key, "PRIMARY KEY") if t.primary_key else ((t.uniques[0], "UNIQUE") if t.uniques else (None, None))
        if k:
            cols = _cols(st, k)
            if cols is None:
                not_applied.append({"object": f"{t.name} {how} ({', '.join(k)})", "why": f"{st.name} lacks a key column"})
            else:
                keys[st.name] = {"columns": cols, "declared": how}
    for t in m.tables.values():
        for fk in t.foreign_keys:
            label = f"{t.name}.{fk['name'] or '+'.join(fk['columns'])} -> {fk['ref_table']}"
            src, tgt = _find(schema, t.name), _find(schema, fk["ref_table"])
            if src is None or tgt is None:
                not_applied.append({"object": label, "why": "a table of the foreign key is not on the side the plan is made for"})
                continue
            sc, tc = _cols(src, fk["columns"]), _cols(tgt, fk["ref_columns"])
            if sc is None or tc is None:
                not_applied.append({"object": label, "why": "a column of the foreign key is missing there"})
                continue
            tk = keys.get(tgt.name, {}).get("columns")
            if not tk or [c.lower() for c in tk] != [c.lower() for c in tc]:
                if tk and sorted(c.lower() for c in tk) == sorted(c.lower() for c in tc):
                    order = [[c.lower() for c in tc].index(k.lower()) for k in tk]
                    sc, tc = [sc[i] for i in order], [tc[i] for i in order]
                else:
                    not_applied.append({"object": label, "why": f"it references {', '.join(tc)}, not {tgt.name}'s declared key "
                                                                f"({', '.join(tk) if tk else 'none declared'}); confirm it yourself if it is a link"})
                    continue
            links.append({"source": src.name, "source_cols": sc, "target": tgt.name, "target_cols": tc, "constraint": fk["name"]})
    return {"keys": keys, "links": links, "not_applied": not_applied, "matched": matched}


def model(m: md.SourceModel, schema=None, keys=None, confirmed=None):
    """infer.plan with the source's declared keys and links first: (plan, candidates). Keys and links the caller passes
    win. The declared ones carry rule `metadata.rule(source)`; nothing is counted here."""
    from ..infer import plan as _plan
    schema = schema if schema is not None else to_schema(m)
    cand = candidates(m, schema)
    given = {str(k).lower() for k in (keys or {})}
    mine = {t: v["columns"] for t, v in cand["keys"].items() if t.lower() not in given}
    links = [x for x in cand["links"] if x["target"] in mine and [c.lower() for c in mine[x["target"]]] == [c.lower() for c in x["target_cols"]]]
    p = _plan(schema, keys={**mine, **(keys or {})},
              confirmed=[{k: x[k] for k in ("source", "source_cols", "target", "target_cols")} for x in links] + list(confirmed or []))
    r, prov = md.rule(m.source), md.provenance(m.source)
    for t, cols in mine.items():
        if t in p.keys and p.keys[t][1] == "K1" and [c.lower() for c in p.keys[t][0]] == [c.lower() for c in cols]:
            p.keys[t] = (p.keys[t][0], r)
    ours = {(x["source"], tuple(c.lower() for c in x["source_cols"]), x["target"]): x for x in links}
    for rel in p.relationships:
        x = ours.get(rel.key)
        if x is not None and rel.rule == "confirmed":
            rel.rule = r
            rel.note = f"{prov}: FOREIGN KEY {x['constraint'] or ''} (not enforced by the source)".replace("  ", " ")
    cand["keys"] = {t: {**cand["keys"][t], "rule": r} for t in mine}
    cand["links"] = [{**x, "rule": r} for x in links]
    return p, cand


# ------------------------------------------------------------------------------------------------------ the plan

def build(m: md.SourceModel, prefer: str = "lakehouse", fabric_schema=None, keys=None, confirmed=None) -> tuple[object, dict]:
    """(plan, report). report: per object the target, the landing, the column findings and the view translation; the
    declared keys and links as candidates; what was not applied; the pages read."""
    prefer = str(prefer or "lakehouse").lower()
    if prefer not in ("lakehouse", "warehouse"):
        raise ValueError("target must be lakehouse or warehouse")
    p, cand = model(m, fabric_schema, keys, confirmed)
    objects, views = [], []
    mirrorable = sorted((m.schema, t.name) for t in m.tables.values()
                        if t.kind != "view" and landing(m.source, t)["how"].startswith("Mirroring"))
    beyond = set(n for _, n in mirrorable[MIRROR_TABLE_LIMIT:]) if m.source == "snowflake" else set()
    for t in sorted(m.tables.values(), key=lambda t: (t.kind == "view", t.name.lower())):
        land = landing(m.source, t)
        if t.name in beyond:
            land = {**land, "mirroring": "beyond the first 1,000 tables: not mirrored with 'Mirror all data'",
                    "how": "Copy job (Snowflake source)", "doc": "mirror_snowflake_limits"}
        o = {"object": t.name, "kind": t.kind, "source_type": t.raw_type, **({"flags": t.flags} if t.flags else {}),
             **({"comment": t.comment} if t.comment else {}), **target(t, prefer), "landing": land,
             "columns": len(t.columns), "column_findings": column_findings(m.source, t)}
        if t.kind == "view" or t.view_sql:
            tr = sqlrules.translate(t.view_sql or "", m.source, m.functions, t.name) if t.view_sql else \
                {"view": t.name, "status": "manual", "constructs": [], "tsql": None, "why": "no definition in views.csv"}
            o["sql"] = {"status": tr["status"], "constructs": len(tr["constructs"])}
            views.append(tr)
        objects.append(o)
    counts = {"objects": len(objects), "tables": sum(1 for o in objects if o["kind"] != "view"), "views": sum(1 for o in objects if o["kind"] == "view")}
    by_how: dict[str, int] = {}
    for o in objects:
        h = o["landing"]["how"].split(" (")[0].split(",")[0]
        by_how[h] = by_how.get(h, 0) + 1
    sql_status: dict[str, int] = {}
    for v in views:
        sql_status[v["status"]] = sql_status.get(v["status"], 0) + 1
    report = {
        "source": md.LABEL[m.source], "schema": m.schema, "prefer": prefer, "dry_run": True,
        "counts": counts, "landing_counts": by_how, "sql_counts": sql_status,
        "objects": objects, "views": views,
        "model": {"rule": md.rule(m.source), "provenance": md.provenance(m.source),
                  "status": "declared by metadata, not verified against the rows: validate_plan and the before/after comparison count it",
                  "keys": cand["keys"], "links": cand["links"], "not_applied": cand["not_applied"], "matched": cand["matched"],
                  "comments": {t.name: {"table": t.comment, "columns": {c.name: c.comment for c in t.columns if c.comment}}
                               for t in m.tables.values() if t.comment or any(c.comment for c in t.columns)}},
        "plan_summary": p.summary(),
        "docs": {k: {**v, "read": READ_ON} for k, v in DOCS.items()},
        "manual": manual_list(m, objects, views),
        "not_done": NOT_DONE,
        "ignored": m.ignored,
    }
    return p, report


NOT_DONE = [
    "connects to nothing: no Snowflake, Databricks or Fabric connection is opened by the plan; the files are the customer's exports",
    "creates nothing in Fabric: no mirrored database, Copy job, shortcut, table or view (dry run only)",
    "moves no rows; Fabric's mirroring or Copy job does, set up by a person",
    "translates no stored procedure, task, notebook, job, dbt model or dashboard; views only, by fixed rules",
    "applies no security: row access policies, masking, row filters and column masks are listed for a person",
    "counts prove counts: equal row counts, key counts and totals do not prove that every value is equal",
]


def manual_list(m: md.SourceModel, objects: list[dict], views: list[dict]) -> list[str]:
    out = []
    for o in objects:
        if "manual" in o["landing"]["how"] or (o["landing"].get("note") or "").endswith("(manual)"):
            out.append(f"{o['object']}: {o['landing']['how']}; {o['landing']['note']}")
        for c in o["column_findings"]:
            out.append(f"{o['object']}.{c['column']}: {c['short']} does not land as a plain column")
    for v in views:
        if v["status"] == "manual":
            out.append(f"view {v['view']}: {v['why']}")
    if m.source == "snowflake":
        out.append("Snowflake RLS and CLS policies are not replicated by mirroring: reconfigure security in Fabric")
    else:
        out.append("Unity Catalog grants, row filters and column masks are not carried: design OneLake security for them")
    return out
