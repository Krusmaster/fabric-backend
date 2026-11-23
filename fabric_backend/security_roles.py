"""Row-level and object-level security drafted from the plan (round BL17, 21 November 2026; backlog B-24).

A buyer's IT asks "who sees which company's rows" before a model goes to a pilot's users. This module answers with a
draft, never with a change: nothing here talks to Fabric, reads a row or writes a role.

- `candidates(plan)`: the columns a role would filter on, by name rules and pack columns, each with its reason. The
  rules read column names only, never a value:
    S1  SAP company code: BUKRS (RBUKRS in ACDOCA)
    S2  SAP sales organisation: VKORG
    S3  SAP plant: WERKS
    S4  SAP client: MANDT (CLIENT in ADRC/ADR6, RCLNT in ACDOCA, only in a table the SAP pack recognises)
    B1  Business Central company: `$Company` (bc2adls; COMPANY as the pack compares it)
    G1  a generic company, region or country column: company, company_code, company_id, region, region_code,
        region_id, country, country_code, country_id (snake_case and CamelCase alike)
  S1-S4 and B1 are the systems' own names for the unit data is kept by, so any table that carries one is proposed. A
  G1 name is only proposed when the data is kept by it: it is in at least two tables, or it is part of a table's key.
  A `country` in one table and no key is an attribute of that table (where a customer lives), not a boundary the
  rows are kept by, so it is passed over with that reason (`passed_over`). The synthetic shop has only such a column
  (customers.country), so it proposes no role.
- `draft(plan, column, validation=None)`: TMDL for one role. Every table that carries the column gets a
  `tablePermission` whose DAX keeps the rows whose value the signed-in user is mapped to in `security_user_map`
  (columns user_principal_name, filter_column, filter_value; a table the customer fills in). Tables without the column
  are reached only over the plan's counted links: a relationship that `validate_plan` counted and that holds for
  every row with a value, followed from the one side to the many side, the direction a filter flows in a tabular
  model. A table with no such path is listed as not reached, never guessed into the role.
- `ols_draft(plan)`: object-level security, a `columnPermission` with `metadataPermission: none` for every column
  `privacy.py` flags, so a role that is not allowed to see personal data does not see those columns at all.
- `markdown(plan, validation=None)`: what each role does, which tables it reaches and how, which it does not, the
  object-level draft, and that nothing is written.

Syntax followed, read on Microsoft Learn on 21 November 2026:
- "Tabular Model Definition Language (TMDL)", learn.microsoft.com/analysis-services/tmdl/tmdl-overview: `role
  Role_Store1` / `modelPermission: read` / `tablePermission Store = 'Store'[Store Code] IN {1,10,20,30}`;
  TablePermission.FilterExpression is DAX, ColumnPermission.MetadataPermission an enum.
- "Object-level security (OLS)", learn.microsoft.com/fabric/security/service-admin-object-level-security:
  `tablePermission Customers` / `columnPermission Address` / `metadataPermission: none`.
The role files go under `definition/roles/` as the TMDL folder structure on the first page shows. USERPRINCIPALNAME()
is the DAX function for the signed-in user's name.

BL43 added a role to `semantic_model.draft` on request; BL46 offers the candidates in create_semantic_model's dry run
(`offer`, off by default) and takes the accepted ones by column (`accepted_columns`), as a key or a link is accepted.
"""
from __future__ import annotations

import re

from .infer import Plan
from .privacy import personal_columns
from .semantic_model import data_type, has_object, tmdl_name

MAP_TABLE = "security_user_map"
MAP_COLUMNS = [
    ("user_principal_name", "the signed-in user's name as Entra ID gives it (USERPRINCIPALNAME() in DAX)"),
    ("filter_column", "the column the role filters on, as written in the role (for example BUKRS)"),
    ("filter_value", "one value of that column the user may see, as text; one row per user and value"),
]
FILL_IN = (f"Fill this in: `{MAP_TABLE}` is a table the customer keeps in the lakehouse, one row per user and value "
           "they may see. Krusgraph does not create it, fill it or read it. A user with no row sees no rows of a filtered table.")

# rule id, kind, what it is, the normalised names (letters and digits, upper case), whether a single table may carry it
_RULES = [
    ("S1", "company code", "SAP's company code", ("BUKRS", "RBUKRS"), True),
    ("S2", "sales organisation", "SAP's sales organisation", ("VKORG",), True),
    ("S3", "plant", "SAP's plant", ("WERKS",), True),
    ("S4", "client", "SAP's client (the system's top-level split of all data)", ("MANDT", "CLIENT", "RCLNT"), True),
    ("B1", "company", "Business Central's company column ($Company in a bc2adls export)", ("COMPANY",), True),
    ("G1", "company", "a company column", ("COMPANY", "COMPANYCODE", "COMPANYID"), False),
    ("G1", "region", "a region column", ("REGION", "REGIONCODE", "REGIONID"), False),
    ("G1", "country", "a country column", ("COUNTRY", "COUNTRYCODE", "COUNTRYID"), False),
]


def _norm(column: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", column.upper())


def _is_bc(column: str) -> bool:
    return column.startswith("$")


def _rule_of(column: str, sap_table: bool = False):
    n = _norm(column)
    for rule in _RULES:
        if n not in rule[3]:
            continue
        if rule[0] == "B1" and not _is_bc(column):
            continue                                  # a plain `company` column is the generic rule, not BC's
        if rule[0] == "S4" and n != "MANDT" and not sap_table:
            continue                                  # CLIENT and RCLNT are SAP's client only in a table the SAP pack knows
        return rule
    return None


def _matches(plan: Plan) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """(rule id, kind) -> [(table, column)] for every column a rule names, in schema order."""
    out: dict[tuple[str, str], list[tuple[str, str]]] = {}
    sap = (plan.pack or {}).get("tables", {}) if (plan.pack or {}).get("pack") == "sap" else {}
    for t in plan.schema:
        for c in t.column_names:
            rule = _rule_of(c, t.name in sap)
            if rule:
                out.setdefault((rule[0], rule[1]), []).append((t.name, c))
    return out


def _pack_note(plan: Plan, tables: list[str]) -> str:
    pack = (plan.pack or {}).get("tables") or {}
    named = [f"{t} as {pack[t]}" for t in tables if t in pack]
    if not named:
        return ""
    return f"; the {(plan.pack or {}).get('pack', 'knowledge')} pack recognises {', '.join(named[:4])}" + (" and more" if len(named) > 4 else "")


def _all(plan: Plan) -> tuple[list[dict], list[dict]]:
    proposed, passed = [], []
    order = {(r[0], r[1]): i for i, r in enumerate(_RULES)}
    for (rid, kind), cols in sorted(_matches(plan).items(), key=lambda kv: order[kv[0]]):
        rule = next(r for r in _RULES if (r[0], r[1]) == (rid, kind))
        tables = list(dict.fromkeys(t for t, _ in cols))
        names = list(dict.fromkeys(c for _, c in cols))
        in_key = [t for t, c in cols if c.lower() in [k.lower() for k in plan.keys.get(t, ([], ""))[0]]]
        item = {"column": max(names, key=lambda n: sum(1 for _, c in cols if c == n)), "columns": cols, "kind": kind, "rule": rid,
                "tables": tables}
        if rule[4]:
            item["reason"] = (f"{rid}: {rule[2]} by its name ({', '.join(names)}), in {len(tables)} table"
                              f"{'s' if len(tables) != 1 else ''}{_pack_note(plan, tables)}")
            proposed.append(item)
        elif len(tables) >= 2 or in_key:
            why = f"in {len(tables)} tables" if len(tables) >= 2 else f"part of the key of {', '.join(in_key)}"
            item["reason"] = f"{rid}: {rule[2]} by its name ({', '.join(names)}), {why}, so the rows are kept by it"
            proposed.append(item)
        else:
            item["reason"] = (f"{rid}: {rule[2]} by its name ({', '.join(f'{t}.{c}' for t, c in cols)}), but in one table and "
                              "no key: an attribute of that table, not a boundary the rows are kept by. Not proposed")
            passed.append(item)
    return proposed, passed


def candidates(plan: Plan) -> list[dict]:
    """The columns a role would filter on: [{column, columns: [(table, column)], kind, rule, tables, reason}], the
    systems' own names first (company code, sales organisation, plant, client, BC company), then generic ones. Names
    only; no value is read."""
    return _all(plan)[0]


def passed_over(plan: Plan) -> list[dict]:
    """Columns a G1 name matched that are not proposed, each with why (one table, no key)."""
    return _all(plan)[1]


# ------------------------------------------------------------------ BL46: offered in the model dry run ------------

ACCEPT_HOW = ("Proposed, not added: nothing is added to the model unless you pass the roles you accept, by the column each "
              "filters on (roles=[\"BUKRS\"]). Each role filters the tables that carry its column; in the model the filter "
              "flows on over the relationships, from the one side to the many side. Names only: no row value is read.")


def accepted_columns(plan: Plan, roles) -> list[str]:
    """BL46: the candidates' columns for the roles a caller accepted (by column name, any case; RBUKRS finds BUKRS's
    candidate). Raises PlanInputError, in plain words with the roles proposed here, for a name no rule proposed."""
    from .infer import PlanInputError
    if roles is None:
        return []
    if not isinstance(roles, (list, tuple)) or not all(isinstance(r, str) and r.strip() for r in roles):
        raise PlanInputError("roles: a list of column names, such as [\"BUKRS\"], from the dry run's role_candidates")
    offered = ", ".join(c["column"] for c in candidates(plan)) or "none (no column here names a unit the rows are kept by)"
    out = []
    for r in roles:
        try:
            col = _find(plan, r.strip())["column"]
        except ValueError:
            raise PlanInputError(f"roles: {r.strip()!r} is not a role proposed for this source. The roles proposed here, by "
                                 f"the column each filters on: {offered}. Nothing was read or written.") from None
        if col not in out:
            out.append(col)
    return out


def offer(plan: Plan, tables: list[str] | None = None, added: list[dict] | None = None) -> dict:
    """BL46: the role candidates as the model dry run lists them, off by default: {proposed: [{role, column, kind, rule,
    filters, why, fits, added}], how, map_table, written: False}. `tables` is the model's table filter (a role whose
    tables are not all in it is not added); `added` is the summary's security_roles.added. Names only, never a value."""
    keep = None if not tables else {t.lower() for t in tables}
    done = {a["column"] for a in (added or [])}
    proposed = []
    for c in candidates(plan):
        filters = list(c["tables"])
        missing = [t for t in filters if keep is not None and t.lower() not in keep]
        item = {"role": role_name(c), "column": c["column"], "kind": c["kind"], "rule": c["rule"], "filters": filters,
                "why": c["reason"], "fits": not missing, "added": c["column"] in done}
        if missing:
            item["why_not"] = f"its tables {', '.join(missing)} are not in this model"
        proposed.append(item)
    return {"proposed": proposed, "how": ACCEPT_HOW, "map_table": MAP_TABLE, "written": False}


# ------------------------------------------------------------------ propagation over counted links ----------------

def counted_links(plan: Plan, validation: dict | None) -> list:
    """The plan's relationships that validate_plan counted and that hold for every row with a value."""
    held = set()
    for r in (validation or {}).get("relationships", []):
        if str(r.get("verdict", "")).startswith("holds"):
            held.add((r["source"], tuple(c.lower() for c in r["columns"]), r["target"]))
    return [r for r in plan.relationships if r.key in held]


def _find(plan: Plan, column: str) -> dict:
    n = _norm(column)
    for c in candidates(plan):
        if n in {_norm(x) for _, x in c["columns"]} or n == _norm(c["column"]):
            return c
    raise ValueError(f"{column!r} is not a column a role is proposed for here; candidates: "
                     f"{', '.join(c['column'] for c in candidates(plan)) or 'none'}")


def reach(plan: Plan, column: str, validation: dict | None = None) -> dict:
    """{direct: [(table, column)], reached: {table: [links on the path]}, not_reached: [tables]} for one candidate.
    A filter flows from a relationship's one side (target) to its many side (source), so a table is reached when it
    points, over counted links, at a table the role filters."""
    cand = _find(plan, column)
    direct = list(cand["columns"])
    filtered = {t for t, _ in direct}
    links = counted_links(plan, validation)
    path: dict[str, list] = {t: [] for t in filtered}
    frontier = sorted(filtered)
    while frontier:
        nxt = []
        for t in frontier:
            for r in sorted(links, key=lambda r: (r.source, r.source_cols, r.target)):
                if r.target == t and r.source not in path:
                    path[r.source] = path[t] + [r]
                    nxt.append(r.source)
        frontier = sorted(nxt)
    reached = {t: p for t, p in path.items() if t not in filtered}
    not_reached = [t.name for t in plan.schema if t.name not in path]
    return {"candidate": cand, "direct": direct, "reached": reached, "not_reached": not_reached}


# ------------------------------------------------------------------ TMDL -----------------------------------------

def _dax_table(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _dax_col(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def role_name(cand: dict) -> str:
    return f"Rows by {cand['kind']} ({cand['column']})"


def filter_expression(plan: Plan, table: str, column: str, map_key: str | None = None) -> str:
    """The DAX that keeps the rows of `table` whose `column` value the signed-in user is mapped to (under `map_key` in
    filter_column: the role's column, so ADRC's CLIENT is filtered by the MANDT rows of the map)."""
    t = plan.schema[table]
    sql_type = next((c.data_type for c in t.columns if c.name == column), "string")
    ref = f"{_dax_table(table)}{_dax_col(column)}"
    value = ref if data_type(sql_type) == "string" else f"FORMAT({ref}, \"\")"
    return (f"{value} IN CALCULATETABLE(VALUES({_dax_table(MAP_TABLE)}[filter_value]), "
            f"{_dax_table(MAP_TABLE)}[user_principal_name] = USERPRINCIPALNAME(), "
            f"{_dax_table(MAP_TABLE)}[filter_column] = \"{map_key or column}\")")


def map_table_tmdl() -> str:
    lines = [f"/// {FILL_IN}", f"table {MAP_TABLE}", ""]
    for col, what in MAP_COLUMNS:
        lines += [f"\t/// {what}", f"\tcolumn {col}", "\t\tdataType: string", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {col}", ""]
    lines += [f"\tpartition {MAP_TABLE} = entity", "\t\tmode: directLake", "\t\tsource", f"\t\t\tentityName: {MAP_TABLE}",
              "\t\t\texpressionSource: DatabaseQuery", ""]
    return "\n".join(lines)


def draft(plan: Plan, column: str, validation: dict | None = None) -> dict:
    """{name, parts: {path: TMDL}, reach} for one role on `column` (a name `candidates` proposed). Nothing is written."""
    r = reach(plan, column, validation)
    cand = r["candidate"]
    name = role_name(cand)
    lines = [f"/// Draft by Krusgraph: {cand['reason']}.",
             "/// Each table that carries the column keeps the rows whose value the user is mapped to in security_user_map.",
             f"role {tmdl_name(name)}", "\tmodelPermission: read", ""]
    for table, col in r["direct"]:
        lines += [f"\ttablePermission {tmdl_name(table)} = {filter_expression(plan, table, col, cand['column'])}", ""]
    lines += [f"\t/// The signed-in user sees only their own rows of {MAP_TABLE}.",
              f"\ttablePermission {MAP_TABLE} = {_dax_table(MAP_TABLE)}[user_principal_name] = USERPRINCIPALNAME()", ""]
    parts = {f"definition/roles/{name}.tmdl": "\n".join(lines), f"definition/tables/{MAP_TABLE}.tmdl": map_table_tmdl()}
    assert all(has_object(p) for p in parts.values())
    return {"name": name, "column": cand["column"], "parts": parts, "reach": r, "written": False}


def ols_draft(plan: Plan, role: str = "Without personal data") -> dict:
    """{name, parts, columns}: one role that hides every column privacy.py flags (metadataPermission: none). Empty
    parts when nothing is flagged."""
    flagged = personal_columns(plan.schema)
    by_table: dict[str, list[tuple[str, dict]]] = {}
    for (t, c), f in sorted(flagged.items()):
        by_table.setdefault(t, []).append((c, f))
    if not by_table:
        return {"name": role, "parts": {}, "columns": [], "written": False}
    lines = ["/// Draft by Krusgraph: object-level security for the columns privacy.py flags by name (rules P1-P6, or the pack).",
             f"role {tmdl_name(role)}", "\tmodelPermission: read", ""]
    cols = []
    for t, items in by_table.items():
        lines.append(f"\ttablePermission {tmdl_name(t)}")
        for c, f in items:
            lines += [f"\t\t/// {f['rule']}: {f['why']}", f"\t\tcolumnPermission {tmdl_name(c)}", "\t\t\tmetadataPermission: none"]
            cols.append({"table": t, "column": c, "rule": f["rule"], "why": f["why"]})
        lines.append("")
    return {"name": role, "parts": {f"definition/roles/{role}.tmdl": "\n".join(lines)}, "columns": cols, "written": False}


def all_parts(plan: Plan, validation: dict | None = None) -> dict[str, str]:
    """Every role draft and the map table, as TMDL parts."""
    parts: dict[str, str] = {}
    for c in candidates(plan):
        parts.update(draft(plan, c["column"], validation)["parts"])
    parts.update(ols_draft(plan)["parts"])
    return parts


# ------------------------------------------------------------------ the explanation -------------------------------

def _link(r) -> str:
    return f"{r.source}.{'+'.join(r.source_cols)} → {r.target}"


def markdown(plan: Plan, validation: dict | None = None) -> str:
    out = ["# Row-level and object-level security, drafted", "",
           "A draft from the plan's names and counted links. **Nothing is written**: no role, table or permission is created "
           "in Fabric or Power BI, and no row value is read. The TMDL below is for a person to review, fill in and apply.", ""]
    cands, passed = candidates(plan), passed_over(plan)
    if not cands:
        out += ["## Row-level security", "", "No column here names a unit the rows are kept by (company code, sales organisation, "
                "plant, client, company, or a region or country column in several tables or a key), so no role is proposed."]
        out += [f"- Passed over: {p['reason']}." for p in passed]
        out.append("")
    if cands and validation is None:
        out += ["No links were counted (no validate_plan result given), so each role reaches only the tables that carry its column.", ""]
    for c in cands:
        r = reach(plan, c["column"], validation)
        out += [f"## Role: {role_name(c)}", "", f"Why: {c['reason']}.", "",
                f"What it does: a user sees the rows of these tables whose `{c['column']}` is one of the values mapped to them in "
                f"`{MAP_TABLE}` (filter_column = \"{c['column']}\"). A user with no row there sees none of these rows.", "",
                "Filtered directly (the table carries the column):"]
        out += [f"- `{t}` on `{col}`" for t, col in r["direct"]]
        out += ["", "Reached over counted links (the filter flows from the one side to the many side):"]
        if r["reached"]:
            for t, p in sorted(r["reached"].items()):
                wide = any(len(x.source_cols) > 1 for x in p)
                out.append(f"- `{t}`: {' ; '.join(_link(x) for x in p)}"
                           + (" (a link of several columns: the model needs a combined key column first, see semantic_model)" if wide else ""))
        else:
            out.append("- none")
        out += ["", "Not reached (no counted path to a filtered table; the role does not filter them):"]
        out += [f"- `{t}`" for t in r["not_reached"]] or ["- none"]
        out.append("")
    if cands:
        out += [f"## The user map: `{MAP_TABLE}`", "", FILL_IN, "", "| Column | What |", "| --- | --- |"]
        out += [f"| `{c}` | {w} |" for c, w in MAP_COLUMNS]
        out.append("")
    ols = ols_draft(plan)
    out += ["## Object-level security", ""]
    if ols["columns"]:
        out += [f"Role `{ols['name']}` hides these columns (`metadataPermission: none`), each flagged by privacy.py:", ""]
        out += [f"- `{x['table']}.{x['column']}`: {x['rule']}, {x['why']}" for x in ols["columns"]]
    else:
        out.append("No column is flagged as personal data, so no object-level role is drafted.")
    out += ["", "Nothing here is applied. Next step (after the smooth chain): show these drafts in the model dry run and "
            "the review, accepted like a key or a link before anything is written.", ""]
    return "\n".join(out)
