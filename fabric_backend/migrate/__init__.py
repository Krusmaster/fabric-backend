"""Snowflake or Azure Databricks to Microsoft Fabric: a checked model and a migration plan, not just copied tables
(round MG1). docs/MIGRATE-DATABRICKS-SNOWFLAKE.md.

    metadata.read(folder, "snowflake"|"databricks")  the customer's exports of INFORMATION_SCHEMA / SHOW ... KEYS
    plan.build(model, prefer="lakehouse")            per object: Fabric target, how it lands (Microsoft's pages, dated),
                                                     column types that do not carry, view SQL against Fabric T-SQL;
                                                     the declared keys and links as candidates in a Krusgraph plan
    compare.counting_sql(...) / compare.compare(...) after landing: rows, key uniqueness, orphans and totals per table,
                                                     before and after
    plan_migration(...)                              all of it in one call (the CLI command and the local MCP tool)

Deterministic: fixed rules and counts, no model, no network. Reads local files; on the Fabric side it runs one
read-only counting query when it is given a connection. Creates nothing anywhere (dry run only). Tested on synthetic
exports written for the tests (tests/fixtures/mg1/), not on an export from a customer's account. Snowflake,
Databricks and Fabric are named only to say what is read and what is planned; Krusgraph is not affiliated with them.
"""
from __future__ import annotations

from . import compare, metadata, plan, sqlrules

__all__ = ["compare", "metadata", "plan", "sqlrules", "plan_migration"]


def plan_migration(export, source: str, schema: str | None = None, target: str = "lakehouse", fabric_schema=None,
                   before=None, after=None, fabric_execute=None, fabric_schema_name: str | None = None,
                   keys=None, confirmed=None, fabric_dialect: str = "tsql") -> dict:
    """The whole answer as a dict.

    export          the folder (or JSON file) of the source's metadata exports
    fabric_schema   a Schema of the landed tables (their INFORMATION_SCHEMA.COLUMNS); None: plan on the source's names
    before / after  {metric: value} from the counting queries (compare.read_results of the saved CSVs)
    fabric_execute  a read-only connection to the Fabric side: runs validate_plan's checks and the 'after' query
    """
    from .. import evidence
    m = metadata.read(export, source, schema)
    p, report = plan.build(m, target, fabric_schema, keys, confirmed)
    # what should arrive: the plan on the source's own names; each side's query in its own spelling
    p_src = p if fabric_schema is None else plan.model(m, None, keys, confirmed)[0]
    sp = compare.spec(p_src, m)
    src_names, fab_names = {}, {}
    for t in m.tables.values():
        src_names[t.name.lower()] = t.name
        for c in t.columns:
            src_names[f"{t.name.lower()}.{c.name.lower()}"] = c.name
        ft = plan._find(p.schema, t.name) if t.kind != "view" else None
        if ft is not None:
            fab_names[t.name.lower()] = ft.name
            by_norm = {metadata.norm(c): c for c in ft.column_names}
            for c in t.columns:
                if metadata.norm(c.name) in by_norm:
                    fab_names[f"{t.name.lower()}.{c.name.lower()}"] = by_norm[metadata.norm(c.name)]
    sp_fab = compare.present(sp, fab_names)
    fab_schema_name = fabric_schema_name or p.schema.schema
    report["after_landing"] = {
        "source_sql": compare.counting_sql(sp, m.source, m.schema, src_names),
        "fabric_sql": compare.counting_sql(sp_fab, "tsql", fab_schema_name, fab_names),
        "not_on_fabric_side": sorted(set(sp["tables"]) - set(sp_fab["tables"])),
        "how": "run source_sql in the source and save the result (metric,value) as CSV; run fabric_sql on the Fabric SQL analytics "
               "endpoint or Warehouse after landing (or let the local server run it); then compare",
    }
    if fabric_execute is not None:
        v = evidence.validate(p, fabric_execute, max_items=200)
        report["fabric_checks"] = {"summary": v.get("summary"),
                                   "keys": [{"table": k["table"], "verdict": k.get("verdict")} for k in v.get("keys", [])],
                                   "links": [{"source": r["source"], "target": r["target"], "orphans": r.get("orphans")}
                                             for r in v.get("relationships", [])],
                                   "header_amounts": [{"header": f["header"], "line": f["line"], "columns": list(f["amount_columns"])}
                                                      for f in (v.get("amount_levels") or {}).get("findings", [])]}
        if after is None and sp_fab["tables"]:
            after = compare.run(fabric_execute, compare.counting_sql(sp_fab, fabric_dialect, fab_schema_name, fab_names))
    if before is not None and after is not None:
        cmp = compare.compare(before, after, sp)
        report["comparison"] = cmp
        report["report_markdown"] = compare.markdown(cmp, metadata.LABEL[m.source], report.get("fabric_checks"))
    return {"plan": p, "report": report, "spec": sp}
