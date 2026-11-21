"""Singular dbt tests from what Krusgraph has checked (round DBT1): dbt_schema(project=true) writes them to
tests/krusgraph_checks/ beside the project's other files (fabric_backend/dbt.py `project`).

- Every composite key of the plan: a test on the source table that returns the key values more than one row has. The
  sources file can test a one-column key with the built-in `unique`; a key over several columns has no built-in test,
  and the staging model's own test runs after the de-duplication, so it cannot see a duplicate in the source.
- Every relationship over several columns: a test on the source tables that returns the child rows whose reference has
  no row in the parent, counted the way validate_plan counts it (a NULL is no reference; under the SAP pack a blank
  outside the client column is none either).
- Every header amount that validate_plan's amount_levels found repeated over lines (VBAK.NETWR over VBAP), and the pack
  trap that names it where the pack's manifest has one with check `amount_level`: for a mart at the header's grain, a test
  that fails when the mart's sum of the amount differs from the header's own sum (a mart that sums the header amount
  over its lines gives more); for a mart at the line's grain, which leaves the header amount out, a test on its grain
  (as many rows as the line table, so a header amount added to it later could not be counted once per line unnoticed).

Each file starts with a comment saying which check or pack rule it comes from and what was counted. T-SQL for
dbt-fabric 1.12: no CTE (the adapter rejects nested CTEs, and a test is compiled inside one), no package (dbt-fabric's
documentation says dbt-utils is not supported). A test passes when it returns no rows, as dbt's singular tests do.
Deterministic: the same plan and counts give the same files. Nothing is run here.
"""
from __future__ import annotations

FOLDER = "tests/krusgraph_checks"
_CLIENT = ("MANDT", "RCLNT", "CLIENT")


def _dbt():
    from . import dbt
    return dbt


def _counted_key(validation: dict | None, table: str, cols: list[str]) -> str:
    want = [c.lower() for c in cols]
    for k in (validation or {}).get("keys", []):
        if k["table"] == table and [c.lower() for c in k["columns"]] == want:
            return f"counted: {k['verdict']}"
    return "not counted (dbt_schema with check_rows=true counts it)"


def _counted_rel(validation: dict | None, r) -> str:
    want = [c.lower() for c in r.source_cols]
    for x in (validation or {}).get("relationships", []):
        if x["source"] == r.source and x["target"] == r.target and [c.lower() for c in x["columns"]] == want:
            return f"counted: {x.get('verdict', 'counted')}"
    return "not counted (dbt_schema with check_rows=true counts it)"


def _traps(plan) -> list[dict]:
    """The pack's traps whose manifest check is amount_level, with the TABLE.COLUMN pairs their text names."""
    import re

    from . import pack_manifest
    pack = (plan.pack or {}).get("pack")
    if not pack:
        return []
    try:
        traps = pack_manifest.load(pack).get("traps") or []
    except (OSError, ValueError):
        return []
    out = []
    for t in traps:
        if t.get("check") == "amount_level":
            pairs = {(a.replace("_", "").lower(), b.replace("_", "").lower())
                     for a, b in re.findall(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\b", t.get("description", ""))}
            out.append({"pack": pack, "name": t["name"], "title": t.get("title", ""), "pairs": pairs})
    return out


def _trap_for(plan, traps: list[dict], table: str, column: str) -> dict | None:
    name = ((plan.pack or {}).get("tables") or {}).get(table, table)
    want = (str(name).replace("_", "").lower(), column.replace("_", "").lower())
    return next((t for t in traps if want in t["pairs"]), None)


def _source(dbt, source_name: str, table: str) -> str:
    return f"{{{{ source({dbt._q(source_name)}, {dbt._q(table)}) }}}}"


def _key_test(dbt, source_name: str, table: str, cols: list[str], rule: str, counted: str) -> str:
    c = ", ".join(dbt._sq(x) for x in cols)
    head = [f"-- From Krusgraph's key check (validate_plan, keys): {table} is identified by {'+'.join(cols)} (rule {rule}); {counted}.",
            f"-- Returns the values of {'+'.join(cols)} that more than one row of the source has; passes when it returns none.",
            "-- On the source, before the staging model keeps one row per key: a duplicate there would be hidden after it.",
            "-- No dbt-utils (dbt-fabric's documentation says it is not supported) and no CTE (dbt-fabric rejects nested CTEs)."]
    return ("\n".join(dbt._note(h) for h in head) + "\n"
            f"select {c}, count(*) as [rows]\nfrom {_source(dbt, source_name, table)}\ngroup by {c}\nhaving count(*) > 1\n")


def _orphan_test(dbt, source_name: str, r, counted: str) -> str:
    blank = r.rule == "SAP pack"
    has = [f"c.{dbt._sq(a)} is not null" for a in r.source_cols]
    if blank:                       # as validate_plan counts it: SAP writes "no value" as a blank, not NULL
        has += [f"ltrim(rtrim(c.{dbt._sq(a)})) <> ''" for a in r.source_cols if a.upper() not in _CLIENT]
    on = " and ".join(f"p.{dbt._sq(b)} = c.{dbt._sq(a)}" for a, b in zip(r.source_cols, r.target_cols))
    head = [f"-- From Krusgraph's relationship check (validate_plan, relationships): {dbt._rel_text(r)}; {counted}.",
            "-- Returns the rows whose reference has no row in the parent (orphans); passes when it returns none.",
            "-- A NULL in the reference is no reference" + (", and under the SAP pack a blank outside the client column is none either"
                                                             if blank else "") + ", as validate_plan counts it.",
            "-- The built-in relationships test takes one column; this one takes all of them. No dbt-utils, no CTE."]
    return ("\n".join(dbt._note(h) for h in head) + "\n"
            f"select {', '.join(f'c.{dbt._sq(x)}' for x in r.source_cols)}\nfrom {_source(dbt, source_name, r.source)} as c\n"
            f"where {' and '.join(has)}\n"
            f"    and not exists (select 1 from {_source(dbt, source_name, r.target)} as p where {on})\n")


def _from_text(finding: dict, column: str, trap: dict | None) -> list[str]:
    rows = finding.get("rows_per_header")
    counted = (f"counted: up to {rows['max_lines']} {finding['line']} rows per {finding['header']} row (average {rows['avg_lines']})"
               if isinstance(rows, dict) and rows.get("max_lines") is not None
               else "lines per header not counted" if isinstance(rows, str) and rows else "found from names and the pack")
    out = [f"-- From Krusgraph's amount check (validate_plan, amount_levels): {finding['header']}.{column} is an amount of the whole "
           f"{finding['header']} row, repeated on every {finding['line']} row in a join ({finding['line']}.{'+'.join(finding['line_columns'])} "
           f"-> {finding['header']}.{'+'.join(finding['header_columns'])}, rule {finding['rule']}); {counted}."]
    if trap:
        out.append(f"-- Pack rule: {trap['pack']} trap {trap['name']} ({trap['title']}).")
    return out


def _sum_test(dbt, mart: str, header_model: str, header: str, column: str, sources: list[str]) -> str:
    c = dbt._sq(column)
    head = sources + [
        f"-- {mart} has one row per {header} row. Returns the two sums of {column} when the mart's differs from {header}'s own; "
        "passes when it returns none.",
        f"-- A mart that joins the lines and carries {column} on each of them sums it once per line, and its total comes out larger."]
    return ("\n".join(dbt._note(h) for h in head) + "\n"
            f"select m.[total] as [mart_total], h.[total] as [{dbt._slug(header)}_total]\n"
            f"from (select sum(cast({c} as decimal(38, 4))) as [total] from {{{{ ref({dbt._q(mart)}) }}}}) as m\n"
            f"cross join (select sum(cast({c} as decimal(38, 4))) as [total] from {{{{ ref({dbt._q(header_model)}) }}}}) as h\n"
            "where abs(coalesce(m.[total], 0) - coalesce(h.[total], 0)) >= 0.01\n")


def _grain_test(dbt, mart: str, line_model: str, line: str, amounts: list[str], sources: list[str]) -> str:
    head = sources + [
        f"-- {mart} has one row per {line} row and leaves {', '.join(amounts)} out: a header amount cannot be summed over lines "
        "generically there, so this tests the grain instead.",
        f"-- Returns the two row counts when the mart has a different number of rows than {line}; passes when it returns none.",
        "-- A join that multiplies the lines (or a header amount added at this grain, joined over more rows) shows here."]
    return ("\n".join(dbt._note(h) for h in head) + "\n"
            f"select m.[rows] as [mart_rows], s.[rows] as [{dbt._slug(line)}_rows]\n"
            f"from (select count(*) as [rows] from {{{{ ref({dbt._q(mart)}) }}}}) as m\n"
            f"cross join (select count(*) as [rows] from {{{{ ref({dbt._q(line_model)}) }}}}) as s\n"
            "where m.[rows] <> s.[rows]\n")


def tests(plan, source_name: str, models: dict[str, str], ren: dict[str, dict[str, str]], marts: list[dict],
          mart_sql: dict[str, str], validation: dict | None) -> dict[str, str]:
    """{path under tests/krusgraph_checks/: SQL}. `models` maps a table to its staging model, `ren` its columns to the
    staging names, `marts` is project()'s mart info and `mart_sql` {mart model: its SQL}."""
    dbt = _dbt()
    src = dbt._slug(source_name)
    files: dict[str, str] = {}
    for t, (key, rule) in plan.keys.items():
        if len(key) > 1 and t in models:
            path = f"{FOLDER}/{src}__{dbt._slug(t)}__duplicate_{'_'.join(dbt._slug(c) for c in key)}.sql"
            files[path] = _key_test(dbt, source_name, t, list(key), rule, _counted_key(validation, t, key))
    for r in plan.relationships:
        if len(r.source_cols) > 1 and r.source in models and r.target in models:
            path = (f"{FOLDER}/{src}__{dbt._slug(r.source)}__orphans_{'_'.join(dbt._slug(c) for c in r.source_cols)}"
                    f"__in_{dbt._slug(r.target)}.sql")
            files[path] = _orphan_test(dbt, source_name, r, _counted_rel(validation, r))
    if validation is not None and marts:
        traps = _traps(plan)
        sums: dict[str, tuple] = {}
        grains: dict[str, tuple] = {}
        for f in (validation.get("amount_levels") or {}).get("findings", []):
            h, line = f["header"], f["line"]
            for m in marts:
                if m["fact"] == h and h in models:
                    for col in f["amount_columns"]:
                        name = ren[h][col]
                        if f" as {dbt._sq(name)}" not in mart_sql.get(m["model"], ""):
                            continue                                     # left out of the mart (personal data)
                        key = f"{FOLDER}/{m['model']}__{dbt._slug(name)}_summed_once.sql"
                        prev = sums.get(key)
                        sums[key] = (m["model"], models[h], h, name, (prev[4] if prev else []) + _from_text(f, col, _trap_for(plan, traps, h, col)))
                elif m["fact"] == line and line in models:
                    key = f"{FOLDER}/{m['model']}__one_row_per_{dbt._slug(line)}_row.sql"
                    prev = grains.get(key)
                    text = [x for col in f["amount_columns"] for x in _from_text(f, col, _trap_for(plan, traps, h, col))]
                    grains[key] = (m["model"], models[line], line, (prev[3] if prev else []) + [f"{h}.{c}" for c in f["amount_columns"]],
                                   (prev[4] if prev else []) + text)
        for path, (mart, hm, h, col, text) in sums.items():
            files[path] = _sum_test(dbt, mart, hm, h, col, list(dict.fromkeys(text)))
        for path, (mart, lm, line, amts, text) in grains.items():
            files[path] = _grain_test(dbt, mart, lm, line, list(dict.fromkeys(amts)), list(dict.fromkeys(text)))
    return dict(sorted(files.items()))


def readme_line(files: dict[str, str]) -> str | None:
    n = sum(1 for k in files if k.startswith(FOLDER + "/"))
    if not n:
        return None
    return (f"- {FOLDER}/ ({n}): singular tests from what Krusgraph checked (composite keys and references on the sources, "
            "header amounts per mart); each file's first lines say which check or pack rule it comes from")
