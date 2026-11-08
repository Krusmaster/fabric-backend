"""dbt from the plan: `schema_yml` writes a sources file (`unique` and `not_null` on key columns, `relationships` on every
single-column relationship), and `project` a whole dbt project draft as files: dbt_project.yml, that sources file,
one staging model per table (types for Fabric Data Warehouse, de-duplicated on the key) and marts per proposed domain
that join only over relationships the counts have shown to be many-to-one.

Followed (dbt-labs/docs.getdbt.com [8a6427d], read 25 October 2026):
- website/docs/reference/resource-properties/data-tests.md: the `data_tests` property on sources
  (`sources: - name: … tables: - name: … columns: - name: … data_tests:`), the four built-in generic tests, and
  "Any arguments … should be nested below the `arguments` property" (available in v1.10.5 and higher; older
  versions set the argument as a top-level property). `relationships` takes `to` (a Relation such as
  `source('<source>', '<table>')`) and `field`; "This test automatically excludes NULL values".
- website/docs/docs/build/sources.md: `sources`, `name`, `schema` ("By default, schema will be the same as name"),
  `database`, and the `unique` + `not_null` example on a source column.
Composite keys and composite-column relationships have no built-in test; they are written as comments (dbt_utils'
`unique_combination_of_columns` covers the first, if that package is installed) rather than invented.

The project (round n114) is written for the dbt-fabric adapter 1.12.0 (Microsoft-maintained, MIT; its README: "The
1.12.x adapter series requires dbt-core 1.12 or newer") on dbt-core 1.12, against a Fabric Data Warehouse, in T-SQL.
What the SQL rests on (read 6 November 2026, from the sources of the public pages, because docs.getdbt.com and
learn.microsoft.com did not resolve from where this was written):
- dbt-labs/docs.getdbt.com [fd3d8d9] website/docs/reference/resource-configs/fabric-configs.md: tables are the default
  materialization, views via `materialized='view'`; "Ephemeral materialization is not supported due to T-SQL not
  supporting nested CTEs" and "Nested CTEs … aren't supported in model materialization". So the models use no CTE at
  all: derived tables in FROM. "dbt-utils: Not supported at this time", so no package is assumed.
- the same commit, website/docs/docs/local/connect-data-platform/fabric-setup.md: "SQL analytics endpoints are
  read-only and so are not appropriate for Transformation workloads, use a Warehouse instead". A lakehouse is read
  through its SQL analytics endpoint as a source (`database:` names it) and the models are built in a Warehouse.
- MicrosoftDocs/fabric-docs [28d4ff3] docs/data-warehouse/data-types.md (ms.date 06/11/2026): the supported types,
  datetime2 and time "limited to 6 digits of precision", and the alternatives for unsupported ones (money → decimal,
  datetime → datetime2, nvarchar → varchar, tinyint → smallint, text → varchar, image → varbinary), and the Delta
  mapping (STRING → varchar(8000) in a lakehouse's SQL analytics endpoint, DOUBLE → float, TIMESTAMP → datetime2).
  `fabric_type` follows it and casts only where the target type is fully known; a varchar or decimal whose length or
  precision the metadata does not give is kept as the source has it, and a type without an alternative is reported.
- docs/data-warehouse/tsql-surface-area.md (ms.date 09/16/2026): nested CTEs are a preview feature there too.

dbt Labs publishes an MCP server, dbt-labs/dbt-mcp (Apache-2.0, LICENSE "Copyright 2025 dbt Labs"; 2.10.1 on PyPI, 3
November 2026; read from its README and .env.example at 0671ec0). With DBT_PROJECT_DIR pointing at a folder holding
these files, its dbt CLI tools (parse, compile, list, build, run, test) work on the draft; its README warns that those
commands "could modify your data models, sources, and warehouse objects". This draft sits beside it, not in it:
Krusgraph writes the files from the plan and runs nothing; a person reviews them, and whoever runs dbt, by hand or
through that server, decides when the Warehouse changes. Nothing here calls it.
"""
from __future__ import annotations

import re

from .infer import Plan

_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _y(s: str) -> str:
    """A YAML scalar: bare when it is a plain identifier, double-quoted otherwise."""
    return s if _SAFE.match(s) and s.lower() not in {"yes", "no", "true", "false", "null", "on", "off", "y", "n"} else '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def schema_yml(plan: Plan, source_name: str, schema: str, database: str | None = None,
               tables: list[str] | None = None, arguments_block: bool = True) -> str:
    """arguments_block=False writes test arguments at the top level (dbt before 1.10.5)."""
    wanted = {t.lower() for t in tables} if tables else None
    chosen = [t for t in plan.schema if not wanted or t.name.lower() in wanted]
    names = {t.name for t in chosen}
    pad = "              " if arguments_block else "            "
    out = ["version: 2", "", "# Generated by Krusgraph from the source's metadata; keys and relationships are inferred where the",
           "# source declares none (the rule is in the comment on each test). Fill in descriptions by hand.", "",
           "sources:", f"  - name: {_y(source_name)}"]
    if schema and schema != source_name:
        out.append(f"    schema: {_y(schema)}")
    if database:
        out.append(f"    database: {_y(database)}")
    out += ["    tables:"]
    for t in chosen:
        key, rule = plan.keys.get(t.name, ([], "K3"))
        rels = [r for r in plan.relationships if r.source == t.name and r.target in names]
        out.append(f"      - name: {_y(t.name)}")
        if len(key) > 1:
            out.append(f"        # composite key {'+'.join(key)} (rule {rule}): no built-in dbt test for a combination;")
            out.append("        # with the dbt_utils package: dbt_utils.unique_combination_of_columns, combination_of_columns: "
                       f"[{', '.join(_y(c) for c in key)}]")
        if not key:
            out.append("        # no key inferred (rule K3): no unique/not_null tests")
        multi = [r for r in rels if len(r.source_cols) > 1]
        for r in multi:
            out.append(f"        # relationship {'+'.join(r.source_cols)} -> {r.target} ({r.rule}) spans several columns; "
                       "the built-in relationships test takes one")
        out.append("        columns:")
        for c in t.columns:
            tests: list[list[str]] = []
            if c.name in key:
                tests.append([f"- unique  # key, rule {rule}"] if len(key) == 1 else [])
                tests.append([f"- not_null  # key, rule {rule}"])
            for r in rels:
                if len(r.source_cols) == 1 and r.source_cols[0] == c.name:
                    if arguments_block:
                        tests.append([f"- relationships:  # rule {r.rule}", "    arguments:",
                                      f"      to: source({_q(source_name)}, {_q(r.target)})", f"      field: {_y(r.target_cols[0])}"])
                    else:
                        tests.append([f"- relationships:  # rule {r.rule}", f"    to: source({_q(source_name)}, {_q(r.target)})",
                                      f"    field: {_y(r.target_cols[0])}"])
            tests = [x for x in tests if x]
            out.append(f"          - name: {_y(c.name)}")
            out.append(f"            description: \"\"  # {c.data_type}")
            if tests:
                out.append("            data_tests:")
                for lines in tests:
                    out += ["              " + lines[0]] + ["              " + ln for ln in lines[1:]]
    out.append("")
    return "\n".join(out)


def _q(s: str) -> str:
    return "'" + s.replace("'", "\\'") + "'"


# ------------------------------------------------------------------ the project (n114) -------------------------------

ADAPTER = "dbt-fabric"
ADAPTER_VERSION = "1.12.0"
CORE_VERSION = "1.12"
NOTHING_CREATED = ("A draft: these files were written from the plan and nothing was created or run, in Fabric or anywhere "
                   "else. Review them, put them in a dbt project folder with a profile for a Fabric Warehouse, and run dbt "
                   "yourself when you decide to.")
ROW = "_krusgraph_row"

# Spark/Delta type names (a lakehouse's own metadata, the shop seed) and T-SQL names, to the type in Fabric Data Warehouse
# (fabric-docs data-warehouse/data-types.md). None: kept as the source has it, the metadata lacks the length or precision.
_TYPES = {
    "int": "int", "integer": "int", "bigint": "bigint", "long": "bigint", "smallint": "smallint", "short": "smallint",
    "tinyint": "smallint", "byte": "smallint", "boolean": "bit", "bool": "bit", "bit": "bit", "double": "float",
    "float": "float", "real": "real", "date": "date", "timestamp": "datetime2(6)", "timestamp_ntz": "datetime2(6)",
    "datetime2": "datetime2(6)", "time": "time(6)", "datetime": "datetime2(3)", "smalldatetime": "datetime2(0)",
    "string": "varchar(8000)", "text": "varchar(max)", "ntext": "varchar(max)", "image": "varbinary(max)",
    "uniqueidentifier": "uniqueidentifier", "money": "decimal(19, 4)", "smallmoney": "decimal(10, 4)",
    "json": "varchar(max)", "binary": None, "varbinary": None, "varchar": None, "char": None, "nvarchar": None,
    "nchar": None, "decimal": None, "numeric": None, "dec": None,
}
_NO_EQUIVALENT = {"xml", "geography", "geometry", "sql_variant", "hierarchyid", "datetimeoffset", "vector", "variant",
                  "map", "array", "struct", "interval"}


def fabric_type(data_type: str) -> tuple[str | None, str]:
    """(the CAST target in Fabric Data Warehouse or None, why). None with a reason that starts "no " means the column
    cannot be typed by the template (it is reported); otherwise None keeps the source's own type."""
    t = (data_type or "").strip().lower()
    base = t.split("(")[0].strip()
    args = t[len(base):].strip()
    if base in ("decimal", "numeric", "dec") and args:
        return f"decimal{args.replace(' ', '').replace(',', ', ')}", "decimal with its precision and scale"
    if base in ("varchar", "char", "varbinary") and args:
        return base + args.replace(" ", ""), "as the source has it"
    if base in ("nvarchar", "nchar") and args:
        n = args.strip("()")
        if n == "max":
            return "varchar(max)", "nvarchar has no equivalent; varchar in a UTF-8 collation (data-types.md)"
        if n.isdigit():
            size = f"{4 * int(n)}" if 4 * int(n) <= 8000 else "max"
            return f"{base[1:]}({size})", f"{base} has no equivalent; {base[1:]} of four bytes per character (data-types.md)"
    if base in _NO_EQUIVALENT or base.startswith(("array", "map", "struct")):
        return None, f"no type in Fabric Data Warehouse for {base}: the column is kept as it is; decide how to store it"
    if base in _TYPES:
        target = _TYPES[base]
        if target is None:
            return None, f"{base} without a length or precision in the metadata: kept as the source has it"
        return target, "Fabric Data Warehouse type (data-types.md)"
    return None, f"no known type {data_type!r}: the column is kept as it is"


def _sq(name: str) -> str:
    return "[" + str(name).replace("]", "]]") + "]"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "x"


def snake(name: str) -> str:
    """A column or table name in snake_case for the staging models (n156): OrderID -> order_id, VBELN -> vbeln,
    "Unit Price" -> unit_price; a name that would start with a digit gets c_ in front."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", str(name))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower() or "x"
    return "c_" + s if s[0].isdigit() else s


def renames(plan: Plan, table: str) -> dict[str, str]:
    """{source column: staging column}: snake_case, except where two columns of the table would get the same name
    (both keep the source's), or the name is the row-number column's."""
    from collections import Counter
    cols = plan.schema[table].column_names
    want = {c: snake(c) for c in cols}
    seen = Counter(v.lower() for v in want.values())
    return {c: (v if seen[v.lower()] == 1 and v != ROW else c) for c, v in want.items()}


def _business(plan: Plan) -> dict[str, str]:
    """{table: business name} from the pack that recognised the tables (SAP: VBAK "Sales document, header")."""
    pack = getattr(plan, "pack", None)
    if not pack or not pack.get("tables"):
        return {}
    from . import sap_pack
    known = sap_pack.load(pack["pack"])["tables"]
    out = {}
    for t, n in pack["tables"].items():
        name = (known.get(n) or {}).get("en")
        if name:
            out[t] = f"{n}: {name} ({pack['pack']} pack)"
    return out


def _pack_delta(plan: Plan, table: str) -> list[str]:
    """The date columns a pack names for the table's delta loads (SAP VBAK: ERDAT, AEDAT) that the table has, in the
    pack's order."""
    pack = getattr(plan, "pack", None)
    if not pack or table not in (pack.get("tables") or {}):
        return []
    from . import sap_pack
    entry = sap_pack.load(pack["pack"])["tables"].get(pack["tables"][table]) or {}
    cols = {c.lower(): c for c in plan.schema[table].column_names}
    return [cols[d.lower()] for d in entry.get("delta", []) if d.lower() in cols]


def checked_relationships(plan: Plan, validation: dict | None) -> tuple[list, list[dict]]:
    """The relationships the counts showed to be many-to-one: the target's key on exactly the joined columns was counted
    unique (evidence.target_key_unique) and the relationship itself was counted with rows that have a value. The rest,
    each with the reason, so the draft can say why it does not join over them."""
    from .evidence import target_key_unique
    if validation is None:
        return [], [{"relationship": _rel_text(r), "why": "not counted: dbt_schema with check_rows=true counts the keys and the "
                     "relationships, and only a relationship whose target key was counted unique is joined"} for r in plan.relationships]
    counted = {(r["source"], tuple(c.lower() for c in r["columns"]), r["target"]): r for r in validation.get("relationships", [])
               if "kind" not in r}
    ok, not_ok = [], []
    for r in plan.relationships:
        c = counted.get(r.key)
        if c is None:
            why = "not counted (the check stopped at max_items)"
        elif not target_key_unique(validation.get("keys", []), r.target, r.target_cols):
            why = f"the key {'+'.join(r.target_cols)} of {r.target} was not counted unique, so a row can match more than one"
        elif not c.get("rows_with_value"):
            why = "no rows with a value: nothing was counted"
        else:
            ok.append(r)
            continue
        not_ok.append({"relationship": _rel_text(r), "why": why})
    return ok, not_ok


def _rel_text(r) -> str:
    return f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)} ({r.rule})"


def _summable(plan: Plan, table: str) -> list[str]:
    """Columns of a child table that add up when grouped to its parent: quantities and amounts (by name, or the pack's),
    never a price per unit, a key or a reference."""
    from . import amounts
    t = plan.schema[table]
    key = {c.lower() for c in plan.keys.get(table, ([], ""))[0]}
    refs = {c.lower() for r in plan.relationships if r.source == table for c in r.source_cols}
    packed = {x["column"].lower() for x in (plan.pack or {}).get("amounts", []) if x["table"] == table}
    return [c.name for c in t.columns if c.name.lower() not in key | refs and not amounts.is_price(c.name, c.data_type)
            and (amounts.is_quantity(c.name, c.data_type) or amounts.looks_like_amount(c.name, c.data_type) or c.name.lower() in packed)]


def _note(text: str) -> str:
    """A line comment's text on one line: a newline in a description would end the comment and leave the rest as SQL."""
    return " ".join(str(text).splitlines())


def _select_list(items: list[tuple[str, str | None]], indent: str) -> str:
    """Select items, one per line, each optionally with a trailing `-- note`. The separating comma comes before the
    comment: after it, the comment would swallow the comma and the next item would follow without one (n139)."""
    lines = []
    for i, (sql, note) in enumerate(items):
        line = sql + ("," if i < len(items) - 1 else "")
        lines.append(line + (f"  -- {_note(note)}" if note else ""))
    return f"\n{indent}".join(lines)


def _yaml_doc(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _exists(plan: Plan, table: str, r, models: dict[str, str], ren: dict[str, dict[str, str]], source_name: str) -> str:
    """exists (one row of the parent for this row's reference): over the parent's staging model when the project has
    one (so a parent row left out there is left out here too, as in silver), else over its source table."""
    if r.target in models and r.target != table:
        frm = f"{{{{ ref({_q(models[r.target])}) }}}}"
        pcols = [ren[r.target][c] for c in r.target_cols]
    else:
        frm = f"{{{{ source({_q(source_name)}, {_q(r.target)}) }}}}"
        pcols = list(r.target_cols)
    on = " and ".join(f"p.{_sq(b)} = s.{_sq(a)}" for a, b in zip(r.source_cols, pcols))
    return f"exists (select 1 from {frm} as p where {on})"


def _counts_text(d: dict) -> str:
    return ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in (d or {}).items()) or "not counted"


def _staging(plan: Plan, table: str, model: str, source_name: str, validation: dict | None, business: dict[str, str],
             not_templated: list[dict], todo: list[dict], ren: dict[str, dict[str, str]] | None = None,
             models: dict[str, str] | None = None, fixes: list[dict] | None = None) -> str:
    from .silver import _order_column
    t = plan.schema[table]
    ren = ren or {table: {c: c for c in t.column_names}}
    names = ren[table]
    models = models or {}
    fixes = fixes or []
    key, rule = plan.keys.get(table, ([], None))
    head = [f"-- {model}: one row per {'+'.join(key) if key else 'source row'} of {table}"
            + (f"; {business[table]}" if table in business else "") + ".",
            "-- Generated by Krusgraph from the plan for dbt-fabric 1.12 (Fabric Data Warehouse T-SQL). A draft: review it. "
            "Nothing was created or run."]
    renamed = [f"{c} -> {n}" for c, n in names.items() if c != n]
    if renamed:
        head.append("-- Renamed to snake_case: " + ", ".join(renamed) + ".")
    # n156: the fixes accepted from validate_plan(fixes=true), as staging logic
    key_fix = next((f for f in fixes if f["entry"]["silver"]["step"] == "key"), None)
    set_null: dict[str, str] = {}
    keep_if: list[str] = []
    for f in fixes:
        e, st = f["entry"], f["entry"]["silver"]
        line = (f"-- Fix {e['id']} (accepted from validate_plan(fixes=true), {e['type']}): counts before "
                f"{_counts_text(e['counts'].get('before'))}")
        if st["step"] == "reference":
            r = next((r for r in plan.relationships if r.source == table and r.target == st["parent"]
                      and [c.lower() for c in r.source_cols] == [c.lower() for c in st["columns"]]), None)
            if r is None:
                continue
            nulls = " or ".join(f"s.{_sq(c)} is null" for c in r.source_cols)
            cond = _exists(plan, table, r, models, ren, source_name)
            if f["choice"] == "set_null":
                for c in r.source_cols:
                    set_null[c] = cond
                after = next((x["after"] for x in e["choices"] if x["id"] == "set_null"), {})
                head.append(_note(line + f"; expected after {_counts_text(after)}. A reference with no row in {r.target} is "
                                         "set to NULL; the row stays."))
            else:
                keep_if.append(f"({nulls} or {cond})")
                head.append(_note(line + f"; expected after {_counts_text(e['counts'].get('expected_after'))}. A row whose "
                                         f"{'+'.join(r.source_cols)} has no row in {r.target} is left out here (a NULL is kept). "
                                         "dbt keeps no quarantine table: the silver notebook's krusgraph_quarantine does, and "
                                         "the source's relationships test lists them."))
        elif st["step"] == "move_amount":
            not_templated.append({"table": table, "model": model, "part": f"fix {e['id']}",
                                  "why": f"moving {st['amount_column']} to one row per {st['header_column']} is done by the silver "
                                         "notebook (create_silver_notebook with fixes); in dbt the marts never sum a header amount "
                                         "at line grain"})
        elif st["step"] == "key":
            head.append(_note(line + f"; expected after {_counts_text(e['counts'].get('expected_after'))}."))
    casts = []
    for c in t.columns:
        target, why = fabric_type(c.data_type)
        expr = f"cast({_sq(c.name)} as {target})" if target else _sq(c.name)
        if c.name in set_null:
            expr = f"case when {set_null[c.name]} then {expr} else null end"
        alias = names[c.name]
        sql = expr if (expr == _sq(c.name) and alias == c.name) else f"{expr} as {_sq(alias)}"
        if target:
            casts.append((sql, None))
        else:
            casts.append((sql, f"{c.data_type}: {why}"))
            if why.startswith("no "):
                not_templated.append({"table": table, "model": model, "part": f"type of {c.name}", "why": why})
    checked = {k["table"]: k for k in (validation or {}).get("keys", [])}
    src = f"{{{{ source({_q(source_name)}, {_q(table)}) }}}} as s"
    if not key:
        not_templated.append({"table": table, "model": model, "part": "de-duplication",
                              "why": "no key in the plan (rule K3): there is nothing to de-duplicate on, so every source row is kept"})
        head.append("-- No key in the plan: not de-duplicated (there is nothing to de-duplicate on).")
        body = "select\n    " + _select_list(casts, "    ") + f"\nfrom {src}" + (
            "\nwhere " + "\n    and ".join(keep_if) if keep_if else "")
    else:
        order, how = _order_column(t, None)
        order = [order] if order else _pack_delta(plan, table)
        if order and not how:
            how = "the dates the pack names for delta loads, in its order"
        if key_fix and key_fix["winner"]:
            order, how = [key_fix["winner"]], f"fix {key_fix['entry']['id']}, accepted"
        k = checked.get(table)
        counted = (f"counted: {k['verdict']}" if k else "not counted (check_rows=true counts it)")
        head.append(f"-- De-duplicated on the key {'+'.join(key)} (rule {rule}; {counted}); rows without the key are left out "
                    "here, and the source's not_null test reports them.")
        exact = key_fix is not None and key_fix["entry"]["counts"].get("differing_key_values") == 0
        if order:
            head.append(f"-- Of several rows with one key the latest by {', '.join(order)} is kept ({how}).")
            order_sql = ", ".join(f"{_sq(c)} desc" for c in order)
        elif exact:
            head.append(f"-- Rows that share the key are exact copies (fix {key_fix['entry']['id']}: validate_plan counted no key "
                        "value whose rows differ), so whichever is kept is the same row.")
            order_sql = "(select null)"
        else:
            head.append("-- TODO (customer): which of several rows with one key to keep. No load or change time column was found, "
                        "so the pick below is arbitrary; name the column that orders them.")
            order_sql = "(select null)"
            todo.append({"table": table, "model": model, "what": "which duplicate to keep",
                         "why": f"no load or change time column in {table}; the staging model keeps an arbitrary row per key"})
        inner = _select_list(casts + [(f"row_number() over (partition by {', '.join(_sq(c) for c in key)} order by {order_sql}) as {_sq(ROW)}", None)],
                             "        ")
        outer = ",\n    ".join(_sq(names[c.name]) for c in t.columns)
        not_null = " and ".join([f"{_sq(c)} is not null" for c in key] + keep_if)
        body = (f"select\n    {outer}\nfrom (\n    select\n        {inner}\n    from {src}\n"
                f"    where {not_null}\n) as deduplicated\nwhere {_sq(ROW)} = 1")
    return "\n".join(_note(h) for h in head) + "\n\n{{ config(materialized='view') }}\n\n" + body + "\n"


def _mart(plan: Plan, checked_plan: Plan, fact: str, model: str, models: dict[str, str], domain: dict | None,
          validation: dict, business: dict[str, str], not_templated: list[dict], todo: list[dict],
          ren: dict[str, dict[str, str]] | None = None) -> tuple[str | None, dict | None]:
    from . import amounts, privacy
    from .gold import safest_tree
    ren = ren or {t.name: {c: c for c in t.column_names} for t in plan.schema}
    key = plan.keys.get(fact, ([], ""))[0]
    if not key:
        not_templated.append({"table": fact, "model": model, "part": "mart",
                              "why": f"{fact} is a fact table without a key: the grain of a mart is unknown, so none is written"})
        return None, None
    steps = safest_tree(checked_plan, fact)
    key_cols = {c.lower() for c in key}
    children = [r for r in checked_plan.relationships if r.target == fact and r.source != fact
                and {c.lower() for c in r.target_cols} == key_cols and _summable(plan, r.source)]
    if not steps and not children:
        not_templated.append({"table": fact, "model": model, "part": "mart",
                              "why": f"no relationship from or to {fact} was counted many-to-one, so a mart would be its staging "
                                     "model again; none is written"})
        return None, None
    header = amounts.columns(plan)
    flagged = privacy.personal_columns(plan.schema)
    alias = {fact: "f"}
    for i, s in enumerate(steps, 1):
        alias[s["to"]] = f"d{i}"
    needed = {(fact, c.lower()) for c in key}
    for s in steps:
        needed |= {(s["from"], c.lower()) for c in s["rel"].source_cols} | {(s["to"], c.lower()) for c in s["rel"].target_cols}
    cols, names, left_out = [], [], []
    for t in [fact] + [s["to"] for s in steps]:
        for c in plan.schema[t].column_names:
            if t != fact and (t, c) in header and (t, c.lower()) not in needed:
                left_out.append(f"{t}.{c}: an amount on {t}; this mart has one row per {fact} row, so it would repeat once per row and "
                                f"a sum over the mart would count it several times ({amounts.LEVELS})")
                continue
            if (t, c) in flagged and (t, c.lower()) not in needed:
                left_out.append(f"{t}.{c}: looks like personal data ({flagged[(t, c)]['rule']}); add it here if the mart may show it")
                continue
            cols.append(f"{alias[t]}.{_sq(ren[t][c])}")
            names.append(ren[t][c] if t == fact else f"{snake(t)}_{ren[t][c]}")
    agg_sql, agg_cols = [], []
    for i, r in enumerate(sorted(children, key=lambda r: (r.source.lower(), r.source_cols)), 1):
        a = f"a{i}"
        measures = _summable(plan, r.source)
        rs, child = ren[r.source], snake(r.source)
        group = ", ".join(_sq(rs[c]) for c in r.source_cols)
        sel = [*(_sq(rs[c]) for c in r.source_cols), f"count(*) as {_sq(child + '_rows')}"]
        sel += [f"sum({_sq(rs[m])}) as {_sq(f'{child}_{rs[m]}_sum')}" for m in measures]
        on = " and ".join(f"f.{_sq(ren[fact][b])} = {a}.{_sq(rs[c])}" for c, b in zip(r.source_cols, r.target_cols))
        agg_sql.append(f"left join (\n    -- {r.source} summed to one row per {fact} before the join ({_rel_text(r)}), so no {fact} row repeats\n"
                       f"    select {', '.join(sel)}\n    from {{{{ ref({_q(models[r.source])}) }}}}\n    group by {group}\n) as {a}\n    on {on}")
        agg_cols += [f"{a}.{_sq(child + '_rows')}"] + [f"{a}.{_sq(f'{child}_{rs[m]}_sum')}" for m in measures]
        names += [f"{child}_rows"] + [f"{child}_{rs[m]}_sum" for m in measures]
    out_names = _unique_names(names)
    select = ",\n    ".join(f"{c} as {_sq(n)}" for c, n in zip(cols + agg_cols, out_names))
    joins = []
    counts = {(x["source"], tuple(c.lower() for c in x["columns"]), x["target"]): x for x in validation.get("relationships", [])}
    head = [f"-- {model}: one row per {fact} row ({'+'.join(key)})" + (f"; {business[fact]}" if fact in business else "") + ".",
            "-- Generated by Krusgraph for dbt-fabric 1.12 (Fabric Data Warehouse T-SQL). A draft: review it. Nothing was created or run.",
            "-- Joined only over relationships whose target key was counted unique (many-to-one), each over its safest path:"]
    for s in steps:
        r = s["rel"]
        on = " and ".join(f"{alias[s['from']]}.{_sq(ren[s['from']][a])} = {alias[s['to']]}.{_sq(ren[s['to']][b])}"
                          for a, b in zip(r.source_cols, r.target_cols))
        joins.append(f"left join {{{{ ref({_q(models[s['to']])}) }}}} as {alias[s['to']]}\n    on {on}")
        c = counts.get(r.key, {})
        head.append(f"--   {_rel_text(r)}: {c.get('verdict', 'counted')}")
    for line in left_out:
        head.append(f"-- Left out: {line}.")
    oa = amounts.order_amount_measures(checked_plan, tables=set(alias) | {r.source for r in children})
    for m in oa["measures"]:
        head.append(f"-- TODO (customer): what counts as revenue or an order amount. {m['table']}.{m['column']} is a quantity and "
                    f"{m['table']} has no amount; {m['dimension']}.{m['price']} is a price in reach. {m['price_note']} No amount is computed here.")
    head.append("-- TODO (customer): the business rules are not in the metadata (what counts as revenue, which statuses, "
                "cancelled or returned rows, currency); add them as filters and columns here.")
    todo.append({"table": fact, "model": model, "what": "business rules",
                 "why": "what counts as revenue, which statuses and which rows count are the customer's to decide"})
    sql = ("\n".join(_note(h) for h in head) + "\n\n{{ config(materialized='table') }}\n\n" + f"select\n    {select}\nfrom {{{{ ref({_q(models[fact])}) }}}} as f"
           + "".join("\n" + j for j in joins) + "".join("\n" + j for j in agg_sql) + "\n")
    info = {"model": model, "fact": fact, "grain": [ren[fact][c] for c in key], "domain": domain["slug"] if domain else None,
            "joins": [_rel_text(s["rel"]) for s in steps],
            "aggregated_before_join": [{"table": r.source, "to": fact, "by": [ren[r.source][c] for c in r.source_cols],
                                        "summed": [ren[r.source][m] for m in _summable(plan, r.source)]}
                                       for r in sorted(children, key=lambda r: (r.source.lower(), r.source_cols))],
            "left_out": left_out}
    return sql, info


def _unique_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        k = n.lower()
        seen[k] = seen.get(k, 0) + 1
        out.append(n if seen[k] == 1 else f"{n}_{seen[k]}")
    return out


def project(plan: Plan, source_name: str, schema: str, database: str | None = None, validation: dict | None = None,
            tables: list[str] | None = None, arguments_block: bool = True, fixes: list[dict] | None = None) -> dict:
    """A dbt project draft as files, for dbt-fabric 1.12 on dbt-core 1.12 and a Fabric Data Warehouse:

    - dbt_project.yml (staging as views, marts as tables) and models/sources/<source>.yml (`schema_yml`: tests from the
      plan's keys and relationships);
    - models/staging/<source>/stg_<source>__<table>.sql per table: every column cast to its Fabric Data Warehouse type
      where the metadata says enough, de-duplicated on the plan's key (the latest row by a load or change time column,
      the pack's change date for SAP, or an arbitrary one with a TODO), with unique and not_null tests on the key;
    - models/marts/<domain>/ per domain domains.propose_plan proposes: fct_<table> per fact table with a key, joined only
      over relationships the counts in `validation` (evidence.validate) showed to be many-to-one, over the safest path
      (gold.safest_tree); child tables summed to the fact's key in a derived table before the join, and a header's
      amount left out of a mart at line level, so no amount is counted once per line.
    Round n156: staging columns renamed to snake_case (renames; the sources file keeps the source's names); a key or a
    relationship over several columns tested by a singular test in tests/ (no package: dbt-fabric's documentation says
    dbt-utils is not supported); profiles.example.yml without a secret; README.md says how to run it; `fixes`, the
    accepted fixes from validate_plan(fixes=true) as fix_plan.resolve returns them, become staging logic (the latest row
    by the accepted column; an orphan left out, or its reference set to NULL).
    Returns {"files", "models", "not_templated", "todo", "checked", "domains", ...}; same plan, same answer."""
    from . import domains as _domains
    wanted = {t.lower() for t in tables} if tables else None
    chosen = [t.name for t in plan.schema if not wanted or t.name.lower() in wanted]
    src = _slug(source_name)
    name = f"krusgraph_{src}"
    business = _business(plan)
    not_templated: list[dict] = []
    todo: list[dict] = []
    models, used = {}, set()
    for t in chosen:
        m = f"stg_{src}__{_slug(t)}"
        while m in used:
            m += "_2"
        used.add(m)
        models[t] = m
    files: dict[str, str] = {}
    files[f"models/sources/{source_name}.yml"] = schema_yml(plan, source_name, schema, database, chosen, arguments_block)
    ren = {t: renames(plan, t) for t in chosen}
    by_table: dict[str, list[dict]] = {}
    for f in fixes or []:
        by_table.setdefault(f["entry"]["silver"]["table"], []).append(f)
    applied = [{"id": f["entry"]["id"], "table": f["entry"]["silver"]["table"], "step": f["entry"]["silver"]["step"],
                **({"winner": f["winner"]} if f.get("winner") else {}), **({"choice": f["choice"]} if f.get("choice") else {})}
               for f in fixes or [] if f["entry"]["silver"]["table"] in ren]
    stg_yml = ["version: 2", "", "models:"]
    for t in chosen:
        m = models[t]
        files[f"models/staging/{src}/{m}.sql"] = _staging(plan, t, m, source_name, validation, business, not_templated, todo,
                                                          ren, models, by_table.get(t))
        key = [ren[t][c] for c in plan.keys.get(t, ([], ""))[0]]
        stg_yml += [f"  - name: {m}", f"    description: {_y_text(business.get(t) or f'{t}, typed and de-duplicated on its key')}"]
        if len(key) == 1:
            stg_yml += ["    columns:", f"      - name: {_y(key[0])}", "        data_tests:", "          - unique", "          - not_null"]
        elif key:
            path = f"tests/{m}__unique_{'_'.join(key)}.sql"
            stg_yml.append(f"    # key {'+'.join(key)}: tested by {path} (a singular test; no package needed)")
            files[path] = _unique_test(m, key)
    files[f"models/staging/{src}/_stg_{src}__models.yml"] = _yaml_doc(stg_yml)
    for r in plan.relationships:                                         # n156: a reference over several columns
        if len(r.source_cols) > 1 and r.source in models and r.target in models:
            sc, tc = [ren[r.source][c] for c in r.source_cols], [ren[r.target][c] for c in r.target_cols]
            files[f"tests/{models[r.source]}__references_{_slug(r.target)}.sql"] = _relationship_test(r, models, sc, tc)

    ok, not_checked = checked_relationships(plan, validation)
    inside = set(chosen)
    ok = [r for r in ok if r.source in inside and r.target in inside]
    checked_plan = Plan(plan.schema, {t: k for t, k in plan.keys.items() if t in inside}, ok, pack=plan.pack)
    proposal = _domains.propose_plan(plan, validation)
    where = {t: d for d in proposal["domains"] for t in d["tables"]}
    from . import graphs
    roles = graphs.analyze(plan)["roles"]
    from . import amounts
    # a header that carries an amount of its own (orders.order_amount; not a price per unit) is a fact at its own level
    headers = {f["header"] for f in amounts.header_amounts(plan)
               if any(not amounts.is_price(c.name, c.data_type) for c in plan.schema[f["header"]].columns if c.name in f["amount_columns"])}
    facts = sorted((t for t in chosen if roles[t]["role"] == "fact" or t in headers), key=str.lower)
    marts: list[dict] = []
    per_domain: dict[str, list[dict]] = {d["slug"]: [] for d in proposal["domains"]}
    if validation is None and facts:
        not_templated.append({"table": ", ".join(facts), "model": None, "part": "marts",
                              "why": "nothing was counted, so no relationship is known to be many-to-one and no mart joins; "
                                     "dbt_schema with project=true and check_rows=true writes them"})
    else:
        for fact in facts:
            d = where.get(fact)
            m = f"fct_{_slug(fact)}"
            sql, info = _mart(plan, checked_plan, fact, m, models, d, validation, business, not_templated, todo, ren)
            if sql is None:
                continue
            folder = d["slug"] if d else "unassigned"
            files[f"models/marts/{folder}/{m}.sql"] = sql
            marts.append(info)
            per_domain.setdefault(folder, []).append(info)
    for d in proposal["domains"] + ([{"slug": "unassigned", "name": "unassigned", "name_reason": "tables no domain holds",
                                      "tables": []}] if per_domain.get("unassigned") else []):
        lines = ["version: 2", "",
                 f"# Domain {d['name']} (proposed by Krusgraph: {d['name_reason']}); tables: {', '.join(d['tables']) or 'none'}.",
                 "# A proposal from keys and relationships, not a decision: move models between folders as the teams own them."]
        if per_domain.get(d["slug"]):
            lines.append("models:")
            for info in per_domain[d["slug"]]:
                text = business.get(info["fact"]) or f"one row per {info['fact']} row"
                lines += [f"  - name: {info['model']}", f"    description: {_y_text(text)}"]
                if len(info["grain"]) == 1:
                    lines += ["    columns:", f"      - name: {_y(info['grain'][0])}", "        data_tests:", "          - unique", "          - not_null"]
                else:
                    path = f"tests/{info['model']}__unique_{'_'.join(info['grain'])}.sql"
                    lines.append(f"    # grain {'+'.join(info['grain'])}: tested by {path} (a singular test; no package needed)")
                    files[path] = _unique_test(info["model"], info["grain"])
        else:
            own = [f for f in facts if f in d["tables"]]
            lines.append("# No mart here: " + (f"its fact table(s) {', '.join(own)} are under not_templated in the answer and in README.md."
                                               if own else "no fact table among its tables."))
        files[f"models/marts/{d['slug']}/_{d['slug']}__models.yml"] = _yaml_doc(lines)
    files["dbt_project.yml"] = _yaml_doc([
        f"# dbt project draft written by Krusgraph from the plan of {schema}, for {ADAPTER} {ADAPTER_VERSION} on dbt-core {CORE_VERSION}",
        "# and a Fabric Data Warehouse (T-SQL). Nothing was created or run. The profile is yours to add (type: fabric).",
        f"name: {name}", "version: \"0.1.0\"", "config-version: 2", f"profile: {name}", "",
        "model-paths: [\"models\"]",
        *(["test-paths: [\"tests\"]"] if any(k.startswith("tests/") for k in files) else []),
        *(["require-dbt-version: [\">=1.10.5\", \"<2.0.0\"]  # data_tests with arguments:"] if arguments_block else []), "",
        "models:", f"  {name}:", "    staging:", "      +materialized: view",
        *(["    marts:", "      +materialized: table"] if marts else [])])
    from .quality_suites import profiles_yml
    files["profiles.example.yml"] = profiles_yml(name, schema)
    files["README.md"] = _readme(name, source_name, schema, database, models, marts, not_templated, todo, ok, not_checked, validation,
                                 applied, ren)
    files = dict(sorted(files.items()))
    return {"files": files, "project": name,
            "models": {"staging": [models[t] for t in chosen], "marts": [m["model"] for m in marts]},
            "marts": marts, "not_templated": not_templated, "todo": todo,
            "checked": {"counted": validation is not None, "joined_over": [_rel_text(r) for r in ok], "not_joined": not_checked},
            "domains": [{"slug": d["slug"], "name": d["name"], "tables": d["tables"]} for d in proposal["domains"]],
            "unassigned": proposal["unassigned"],
            "renamed": {t: {c: n for c, n in ren[t].items() if c != n} for t in chosen if any(c != n for c, n in ren[t].items())},
            "fixes": applied,
            "adapter": {"package": ADAPTER, "version": ADAPTER_VERSION, "dbt_core": CORE_VERSION, "target": "Fabric Data Warehouse (T-SQL)"},
            "created": NOTHING_CREATED}


def _y_text(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unique_test(model: str, cols: list[str]) -> str:
    c = ", ".join(_sq(x) for x in cols)
    return (f"-- {model}: {'+'.join(cols)} identifies one row. This test returns the values more than one row has, and passes "
            "when it returns none.\n-- dbt_utils' unique_combination_of_columns tests the same; it is not used, because "
            "dbt-fabric's documentation says dbt-utils is not supported.\n"
            f"select {c}, count(*) as [rows]\nfrom {{{{ ref({_q(model)}) }}}}\ngroup by {c}\nhaving count(*) > 1\n")


def _relationship_test(r, models: dict[str, str], sc: list[str], tc: list[str]) -> str:
    """A reference over several columns (the built-in relationships test takes one): the child rows with no NULL in the
    reference whose values have no row in the parent."""
    not_null = " and ".join(f"c.{_sq(x)} is not null" for x in sc)
    on = " and ".join(f"p.{_sq(b)} = c.{_sq(a)}" for a, b in zip(sc, tc))
    return (f"-- {models[r.source]}.{'+'.join(sc)} -> {models[r.target]}.{'+'.join(tc)} ({r.rule}): this test returns the rows "
            "whose reference has no row in the parent, and passes when it returns none. A NULL in the reference is not "
            "tested, as the built-in relationships test leaves NULL out.\n"
            f"select {', '.join(f'c.{_sq(x)}' for x in sc)}\nfrom {{{{ ref({_q(models[r.source])}) }}}} as c\n"
            f"where {not_null}\n    and not exists (select 1 from {{{{ ref({_q(models[r.target])}) }}}} as p where {on})\n")


def _readme(name, source_name, schema, database, models, marts, not_templated, todo, ok, not_checked, validation,
            applied=(), ren=None) -> str:
    out = [f"# {name}", "", f"A dbt project draft written by Krusgraph from the plan of `{schema}`"
           + (f" in `{database}`" if database else "") + f", for {ADAPTER} {ADAPTER_VERSION} on dbt-core {CORE_VERSION} and a "
           "Fabric Data Warehouse. " + NOTHING_CREATED, "",
           "The models are built in a Warehouse: a lakehouse's SQL analytics endpoint is read-only, so it is a source here "
           f"(`database:` in models/sources/{source_name}.yml), not a target.", "",
           "## Models", "", f"- staging ({len(models)}): views, one per table, typed and de-duplicated on the key",
           f"- marts ({len(marts)}): tables, one per fact table, in a folder per proposed domain", "",
           "## Joined over", ""]
    out += [f"- {_rel_text(r)}" for r in ok] or ["- nothing: " + ("no relationship was counted many-to-one" if validation is not None
                                                                   else "nothing was counted (check_rows=true)")]
    if not_checked:
        out += ["", "## Not joined over", ""] + [f"- {x['relationship']}: {x['why']}" for x in not_checked]
    if not_templated:
        out += ["", "## Not templated", ""] + [f"- {x['table']} ({x['part']}): {x['why']}" for x in not_templated]
    if todo:
        out += ["", "## For you to decide", ""] + [f"- {x['table']} ({x['what']}): {x['why']}" for x in todo]
    if applied:
        out += ["", "## Fixes in the staging models", "", "Accepted from validate_plan(fixes=true); each staging model says what it "
                "does and the counts before and expected after:", ""]
        out += [f"- {x['id']}" + (f" (latest by {x['winner']})" if x.get("winner") else "")
                + (f" ({x['choice']})" if x.get("choice") else "") for x in applied]
    renamed = {t: {c: n for c, n in m.items() if c != n} for t, m in (ren or {}).items()}
    if any(renamed.values()):
        out += ["", "## Renamed columns", "", "The staging models rename columns to snake_case; the sources file keeps the source's names.", ""]
        out += [f"- {t}: " + ", ".join(f"{c} -> {n}" for c, n in m.items()) for t, m in sorted(renamed.items()) if m]
    out += ["", "## A profile", "", "dbt reads the connection from a profile outside this folder (profiles.yml, `type: fabric`, "
            "with `server`, `database`, `schema` and an `authentication`: see the adapter's setup page). No credentials are "
            "written here: profiles.example.yml has placeholders in <angle brackets>.", "",
            "## How to run it", "",
            f"1. Install dbt-core {CORE_VERSION} and {ADAPTER} {ADAPTER_VERSION} (`pip install \"dbt-core~={CORE_VERSION}.0\" "
            f"\"{ADAPTER}=={ADAPTER_VERSION}\"`) and the ODBC Driver 18 for SQL Server.",
            "2. Copy profiles.example.yml to ~/.dbt/profiles.yml, fill in the placeholders, and sign in with `az login`.",
            "3. `dbt debug` checks the connection; `dbt parse` reads the project without touching the Warehouse.",
            "4. `dbt build` creates the staging views and the mart tables in the Warehouse and runs every test; read the models "
            "first, because this is the step that changes the Warehouse.",
            "",
            "Krusgraph has not run these commands on this project; the SQL was only checked to parse as T-SQL.", ""]
    return "\n".join(out)
