"""Quality checks beyond dbt (round n122, LANDSCAPE idea 1): the checks `dbt.schema_yml` writes from the plan (unique and
not null on a key, a referential check on a relationship), drafted as a Great Expectations suite and as Soda checks, and
an optional dbt profiles.yml for Fabric beside the n114 project. Each check carries the rule behind it and, when the
rows were counted (evidence.validate), the counts: rows, nulls and distinct values of a key, rows with a value and
orphans of a relationship. Counts only; no row value is written. A draft: nothing is run or created.

Great Expectations: GX Core 1.24.1 (PyPI, 22 October 2026), read from great-expectations/great_expectations [379684f]
on 6 November 2026, because docs.greatexpectations.io did not resolve from where this was written:
- great_expectations/expectations/core/: `expect_column_values_to_be_unique` and `expect_column_values_to_not_be_null`
  (`column`), `expect_compound_columns_to_be_unique` (`column_list`) for a key of several columns, and every
  Expectation's `meta` ("a JSON-serializable dictionary … included in the output without modification").
- docs/docusaurus/docs/core/customize_expectations/use_sql_to_define_a_custom_expectation.md: GX has no documented
  Expectation that compares two tables, so a relationship is an `UnexpectedRowsExpectation` ("validation successful
  when no rows are returned") with `unexpected_rows_query` holding the orphan query and the `{batch}` named query for
  the table being validated; any other brace must be paired. The query is stated in `meta` too.
- docs/docusaurus/docs/core/introduction/try_gx_end_to_end.py: an Expectation serialised as `type` and `kwargs`. In GX
  Core a suite belongs to one Data Asset's batches, so the draft is one suite per table.

Soda: SodaCL as Soda Core v3 documents it (3.5.6 on the v3 branch of sodadata/soda-core [a3b72fd], docs/overview-main.md,
docs/scan-core.md and docs/how-core-works.md, read 6 November 2026; docs.soda.io did not resolve): `checks for
<dataset>:`, `missing_count(<column>) = 0`, `duplicate_count(<column>) = 0`, the referential check `values in
(<column>) must exist in <dataset> (<column>)`, and a check's `name:`. Soda Core 4 (4.30.0, 5 November 2026) replaced
SodaCL with a contract language; that is not written here. A key or relationship over several columns is written as a
comment with the SQL that finds the offending rows, because those pages show the one-column form only.
"""
from __future__ import annotations

import json

from .infer import Plan

GX_VERSION = "1.24.1"
SODA_VERSION = "3.5.6"
FORMATS = ("gx", "soda", "both")
NOTHING_RUN = ("A draft: these checks were written from the plan and nothing was run or created. Review them, then run "
               "them with Great Expectations or Soda yourself.")


def _counts(validation: dict | None):
    keys, rels = {}, {}
    if validation:
        for k in validation.get("keys", []):
            keys[k["table"]] = {"rows": k.get("rows"), "nulls": k.get("nulls"), "distinct": k.get("distinct"), "verdict": k.get("verdict")}
        for r in validation.get("relationships", []):
            if "kind" in r:
                continue
            rels[(r["source"], tuple(r["columns"]), r["target"])] = {
                "rows_with_value": r.get("rows_with_value"), "orphans": r.get("orphans"), "verdict": r.get("verdict")}
    return keys, rels


def _q(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def _orphan_sql(schema: str, r, batch: str) -> str:
    on = " AND ".join(f"t.{_q(tc)} = s.{_q(sc)}" for sc, tc in zip(r.source_cols, r.target_cols))
    not_null = " AND ".join(f"s.{_q(c)} IS NOT NULL" for c in r.source_cols)
    return (f"SELECT s.* FROM {batch} AS s WHERE {not_null} AND NOT EXISTS "
            f"(SELECT 1 FROM {_q(schema)}.{_q(r.target)} AS t WHERE {on})")


def _dup_sql(schema: str, table: str, cols: list[str]) -> str:
    c = ", ".join(_q(x) for x in cols)
    return f"SELECT {c}, COUNT(*) AS n FROM {_q(schema)}.{_q(table)} GROUP BY {c} HAVING COUNT(*) > 1"


def checks(plan: Plan, schema: str, validation: dict | None = None, tables: list[str] | None = None) -> list[dict]:
    """The checks the plan establishes, one per key (with not null per key column) and one per relationship, in a
    fixed order; the input of both formats."""
    wanted = {t.lower() for t in tables} if tables else None
    chosen = [t.name for t in plan.schema if not wanted or t.name.lower() in wanted]
    inside = set(chosen)
    kc, rc = _counts(validation)
    out: list[dict] = []
    for t in sorted(chosen, key=str.lower):
        key, rule = plan.keys.get(t, ([], "K3"))
        if key:
            out.append({"table": t, "kind": "key", "columns": list(key), "rule": rule, "counts": kc.get(t)})
        for r in sorted((r for r in plan.relationships if r.source == t and r.target in inside),
                        key=lambda r: (r.source_cols, r.target.lower())):
            out.append({"table": t, "kind": "relationship", "columns": list(r.source_cols), "target": r.target,
                        "target_columns": list(r.target_cols), "rule": r.rule,
                        "counts": rc.get((r.source, tuple(r.source_cols), r.target)), "_rel": r})
    return out


def _meta(c: dict) -> dict:
    m = {"krusgraph_rule": c["rule"], "check": c["kind"]}
    if c["kind"] == "relationship":
        m["references"] = f"{c['target']}({', '.join(c['target_columns'])})"
    m["counts"] = c["counts"] if c["counts"] is not None else "not counted (check_rows=true counts them)"
    return m


def gx_suites(plan: Plan, schema: str, validation: dict | None = None, tables: list[str] | None = None) -> dict[str, str]:
    """{path: JSON text}, one Great Expectations suite per table that has a check."""
    per: dict[str, list[dict]] = {}
    for c in checks(plan, schema, validation, tables):
        meta = _meta(c)
        ex = per.setdefault(c["table"], [])
        if c["kind"] == "key":
            if len(c["columns"]) == 1:
                ex.append({"type": "expect_column_values_to_be_unique", "kwargs": {"column": c["columns"][0]}, "meta": meta})
            else:
                ex.append({"type": "expect_compound_columns_to_be_unique", "kwargs": {"column_list": c["columns"]}, "meta": meta})
            for col in c["columns"]:
                ex.append({"type": "expect_column_values_to_not_be_null", "kwargs": {"column": col}, "meta": meta})
        else:
            sql = _orphan_sql(schema, c["_rel"], "{batch}")
            ex.append({"type": "unexpected_rows_expectation",
                       "kwargs": {"unexpected_rows_query": sql},
                       "description": f"Every {', '.join(c['columns'])} of {c['table']} exists in {meta['references']} (rule {c['rule']}).",
                       "meta": {**meta, "why_sql": "GX documents no Expectation that compares two tables; the query returns the orphans"}})
    files = {}
    for t, ex in per.items():
        suite = {"name": f"krusgraph_{t}", "expectations": ex,
                 "meta": {"generated_by": "Krusgraph from the plan", "great_expectations_version": GX_VERSION,
                          "data_asset": f"{schema}.{t}", "note": NOTHING_RUN}}
        files[f"quality/gx/{t}.json"] = json.dumps(suite, indent=2, sort_keys=False)
    return dict(sorted(files.items()))


def _sy(s: str) -> str:
    return s if s.replace("_", "").isalnum() and not s[0].isdigit() else '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _count_text(c: dict) -> str:
    n = c["counts"]
    if n is None:
        return "not counted"
    return ", ".join(f"{k} {v}" for k, v in n.items() if k != "verdict" and v is not None)


def soda_checks(plan: Plan, schema: str, validation: dict | None = None, tables: list[str] | None = None) -> str:
    """SodaCL checks YAML (Soda Core v3), one `checks for` block per table that has a check."""
    out = ["# SodaCL checks (Soda Core " + SODA_VERSION + ") written by Krusgraph from the plan of " + schema + ".",
           "# " + NOTHING_RUN, "# Each check names the rule behind it; counts are from check_rows, if it was run.", ""]
    current = None
    for c in checks(plan, schema, validation, tables):
        if c["table"] != current:
            if current is not None:
                out.append("")
            out.append(f"checks for {_sy(c['table'])}:")
            current = c["table"]
        cols, rule, counts = c["columns"], c["rule"], _count_text(c)
        if c["kind"] == "key":
            if len(cols) == 1:
                out += [f"  - duplicate_count({cols[0]}) = 0:", f"      name: {_sy(f'{cols[0]} is unique, key rule {rule}')}",
                        f"      # counts: {counts}"]
            else:
                out += [f"  # composite key {'+'.join(cols)} (rule {rule}; counts: {counts}) is unique when this returns no rows:",
                        f"  #   {_dup_sql(schema, c['table'], cols)}"]
            for col in cols:
                out += [f"  - missing_count({col}) = 0:", f"      name: {_sy(f'{col} is not null, key rule {rule}')}",
                        f"      # counts: {counts}"]
        else:
            ref = f"{c['target']}({', '.join(c['target_columns'])})"
            if len(cols) == 1:
                out += [f"  - values in ({cols[0]}) must exist in {c['target']} ({c['target_columns'][0]}):",
                        f"      name: {_sy(f'{cols[0]} exists in {ref}, rule {rule}')}", f"      # counts: {counts}"]
            else:
                sql = _orphan_sql(schema, c["_rel"], f"{_q(schema)}.{_q(c['table'])}")
                out += [f"  # relationship {'+'.join(cols)} -> {ref} (rule {rule}; counts: {counts}) holds when this returns no rows:",
                        f"  #   {sql}"]
    out.append("")
    return "\n".join(out)


def suites(plan: Plan, schema: str, fmt: str, validation: dict | None = None, tables: list[str] | None = None) -> dict[str, str]:
    """{path: text} for fmt "gx", "soda" or "both"."""
    if fmt not in FORMATS:
        raise ValueError(f"quality must be one of {', '.join(FORMATS)}, not {fmt!r}")
    files: dict[str, str] = {}
    if fmt in ("gx", "both"):
        files.update(gx_suites(plan, schema, validation, tables))
    if fmt in ("soda", "both"):
        files[f"quality/soda/checks_{schema}.yml"] = soda_checks(plan, schema, validation, tables)
    return dict(sorted(files.items()))


def profiles_yml(project_name: str, schema: str) -> str:
    """A dbt profiles.yml for dbt-fabric with placeholders and no secret: the Azure CLI tab of
    dbt-labs/docs.getdbt.com [fd45fe1] website/docs/docs/local/connect-data-platform/fabric-setup.md (`type: fabric`,
    `driver`, `server`, `port`, `database`, `schema`, `authentication: CLI` after `az login`), read 6 November 2026."""
    return "\n".join([
        "# dbt profile for a Fabric Data Warehouse (dbt-fabric). Placeholders in <angle brackets>: fill them in.",
        "# No secret is written here: authentication CLI uses your `az login` session. For a service principal, read its",
        "# secret from an environment variable with env_var(), never put it in this file.",
        f"{project_name}:",
        "  target: dev",
        "  outputs:",
        "    dev:",
        "      type: fabric",
        "      driver: \"ODBC Driver 18 for SQL Server\"",
        "      server: \"<sql-endpoint>.datawarehouse.fabric.microsoft.com\"  # the Warehouse's SQL connection string",
        "      port: 1433",
        "      database: \"<warehouse>\"  # in workspace <workspace>",
        f"      schema: {_sy(schema)}",
        "      authentication: CLI",
        ""])
